"""Newline-delimited JSON-RPC over stdio for the Cabinet service.

The server implements the smallest surface a Cabinet session needs:
`initialize`, the initialized notification, `ping`, `tools/list`,
`tools/call`, cancellation, and the matching of client responses to server
requests. It declares one capability, `tools`, and it never asks the client
for model sampling: the whole point of the process boundary is that the model
drives the service and not the other way round.

Three structural properties, none of them advisory:

* **The reader never runs a tool.** One thread reads, a serialized writer
  emits, and a bounded pool of one or two workers runs `tools/call`. An owner
  approval blocks its worker while the reader keeps taking messages, which is
  the only way the answer to that dialog can ever arrive.
* **A dialog answer is matched, not assumed.** A server request carries its
  own identifier; a response under any other identifier answers nothing, and a
  replayed response finds no pending request at all. `Store.save_grant` then
  refuses a second answer to the same approval, so a captured accept cannot be
  turned into a second grant at either layer.
* **A dialog that does not return is not a yes.** `StdioElicitor.request`
  waits with a timeout and yields a cancel outcome, so every path that is not
  an owner accept creates no grant.

Version negotiation covers `2025-11-25` and `2025-06-18`, with each version's
own elicitation shape. A client that did not advertise form elicitation cannot
be asked to approve anything, and the refusal is a stable Cabinet code rather
than a silently missing dialog.
"""

import json
import queue
import threading

from .errors import CabinetError

#: Released protocol versions this server speaks, newest first. Draft
#: proposals are not in this tuple and must not be added to it.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18")
LATEST_PROTOCOL = PROTOCOL_VERSIONS[0]

#: Versions whose elicitation request carries an explicit `mode`.
FORM_MODE_VERSIONS = ("2025-11-25",)

#: Largest single message accepted from the client, in bytes.
MAX_MESSAGE_BYTES = 1024 * 1024

DEFAULT_WORKERS = 2
DEFAULT_DIALOG_TIMEOUT = 900.0
SHUTDOWN_JOIN_SECONDS = 2.0

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

SERVER_NAME = "cabinet"
SERVER_VERSION = "0.9.0"

_OVERSIZE = object()
_SHUTDOWN = object()


def elicitation_form_supported(capabilities, protocol):
    """Whether this client can show the owner a form dialog."""

    if not isinstance(capabilities, dict):
        return False
    declared = capabilities.get("elicitation")
    if not isinstance(declared, dict):
        return False
    if protocol in FORM_MODE_VERSIONS:
        # 2025-11-25 lets a client name its modes (`form`, `url`). An empty
        # object is the backwards-compatible declaration of form support, and
        # it is what Claude Code 2.1.267 sends (observed live: the client
        # negotiates 2025-11-25 with `"elicitation": {}`). Only a client that
        # names modes without `form` is refused.
        if not declared:
            return True
        return isinstance(declared.get("form"), dict)
    return True


def elicitation_params(message, schema, protocol):
    """The `elicitation/create` parameters for the negotiated version."""

    params = {}
    if protocol in FORM_MODE_VERSIONS:
        params["mode"] = "form"
    params["message"] = message
    params["requestedSchema"] = schema
    return params


def tool_result(payload, is_error=False):
    """An MCP tool result carrying the same payload as text and as data."""

    text = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}],
            "structuredContent": payload, "isError": bool(is_error)}


class RpcServer:
    """Serve one stdio client for the lifetime of the process."""

    def __init__(self, reader, writer, service, elicitor=None,
                 workers=DEFAULT_WORKERS, server_info=None, log=None):
        self.reader = reader
        self.writer = writer
        self.service = service
        self.elicitor = elicitor
        self.workers = max(1, min(2, int(workers)))
        self.server_info = dict(server_info or {"name": SERVER_NAME,
                                                "version": SERVER_VERSION})
        self.protocol = None
        self.client_capabilities = {}
        self.client_info = {}
        self.initialized = False
        self._log = log or (lambda text: None)
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending = {}
        self._request_counter = 0
        self._cancelled = set()
        self._jobs = queue.Queue()
        self._threads = []
        self._stopped = threading.Event()
        if elicitor is not None and hasattr(elicitor, "attach"):
            elicitor.attach(self)

    # --- lifecycle ---------------------------------------------------------

    def serve(self):
        """Read messages until the client closes the stream."""

        self._start_workers()
        try:
            while not self._stopped.is_set():
                line = self._read_line()
                if line is None:
                    break
                if line is _OVERSIZE:
                    self._send_error(
                        None, PARSE_ERROR,
                        "message exceeds the %d byte limit" % MAX_MESSAGE_BYTES)
                    continue
                if not line.strip():
                    continue
                self._handle(line)
        finally:
            self.stop()

    def stop(self):
        """Release every waiter and stop the workers. Idempotent."""

        if self._stopped.is_set():
            return
        self._stopped.set()
        with self._pending_lock:
            waiting = list(self._pending.values())
            self._pending.clear()
        for event, _slot in waiting:
            event.set()
        for _ in self._threads:
            self._jobs.put(_SHUTDOWN)
        for thread in self._threads:
            thread.join(timeout=SHUTDOWN_JOIN_SECONDS)

    def _start_workers(self):
        for index in range(self.workers):
            thread = threading.Thread(target=self._work, daemon=True,
                                      name="cabinet-tool-%d" % index)
            self._threads.append(thread)
            thread.start()

    # --- reading -----------------------------------------------------------

    def _read_line(self):
        """Return one bounded line, `None` at end of stream, or `_OVERSIZE`.

        A reader closed underneath this thread is end of stream, not an error.
        It happens whenever the other side goes away while a read is parked —
        the ordinary way a client disconnects, and the ordinary way a test
        tears its harness down. Letting the exception escape would leave a
        traceback on stderr for a shutdown that worked.
        """

        try:
            chunk = self.reader.readline(MAX_MESSAGE_BYTES + 2)
            if not chunk:
                return None
            if len(chunk.rstrip(b"\r\n")) > MAX_MESSAGE_BYTES:
                while not chunk.endswith(b"\n"):
                    chunk = self.reader.readline(MAX_MESSAGE_BYTES + 2)
                    if not chunk:
                        break
                return _OVERSIZE
            return chunk
        except (ValueError, OSError):
            return None

    def _handle(self, line):
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as problem:
            self._send_error(None, PARSE_ERROR, "invalid JSON: %s" % problem)
            return
        if not isinstance(message, dict):
            self._send_error(None, INVALID_REQUEST,
                             "a message must be a JSON object")
            return
        if "method" in message:
            self._dispatch(message)
        else:
            self._resolve(message)

    def _dispatch(self, message):
        method = message.get("method")
        message_id = message.get("id")
        is_request = message_id is not None
        if not isinstance(method, str):
            if is_request:
                self._send_error(message_id, INVALID_REQUEST,
                                 "method must be a string")
            return
        if method == "notifications/cancelled":
            self._record_cancellation(message.get("params"))
            return
        if method == "notifications/initialized":
            self.initialized = True
            return
        if not is_request:
            return
        if method == "initialize":
            self._send_result(message_id, self._initialize(message.get("params")))
            return
        if method == "ping":
            self._send_result(message_id, {})
            return
        if self.protocol is None:
            self._send_error(message_id, INVALID_REQUEST,
                             "the connection has not been initialized")
            return
        if method == "tools/list":
            self._send_result(message_id, {"tools": self.service.tools()})
            return
        if method == "tools/call":
            self._jobs.put((message_id, message.get("params")))
            return
        self._send_error(message_id, METHOD_NOT_FOUND,
                         "unknown method %s" % method)

    def _initialize(self, params):
        params = params if isinstance(params, dict) else {}
        requested = params.get("protocolVersion")
        self.protocol = requested if requested in PROTOCOL_VERSIONS \
            else LATEST_PROTOCOL
        capabilities = params.get("capabilities")
        self.client_capabilities = capabilities \
            if isinstance(capabilities, dict) else {}
        client_info = params.get("clientInfo")
        self.client_info = client_info if isinstance(client_info, dict) else {}
        return {"protocolVersion": self.protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": self.server_info}

    def supports_form_elicitation(self):
        return elicitation_form_supported(self.client_capabilities,
                                          self.protocol)

    # --- tool calls --------------------------------------------------------

    def _work(self):
        while True:
            job = self._jobs.get()
            if job is _SHUTDOWN:
                return
            message_id, params = job
            try:
                self._run_tool(message_id, params)
            except Exception as problem:          # never lose a request
                self._send_error(message_id, INTERNAL_ERROR,
                                 "%s: %s" % (type(problem).__name__, problem))

    def _run_tool(self, message_id, params):
        if not isinstance(params, dict):
            self._send_error(message_id, INVALID_PARAMS,
                             "tools/call params must be an object")
            return
        name = params.get("name")
        if not isinstance(name, str) or not self.service.has_tool(name):
            self._send_error(message_id, INVALID_PARAMS,
                             "unknown tool %s" % (name,))
            return
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            self._send_error(message_id, INVALID_PARAMS,
                             "tool arguments must be an object")
            return
        try:
            payload = self.service.call(name, arguments)
        except CabinetError as problem:
            self._send_result(message_id, tool_result(problem.to_dict(), True))
            return
        self._send_result(message_id, tool_result(payload))

    def _record_cancellation(self, params):
        if not isinstance(params, dict):
            return
        request_id = params.get("requestId")
        if request_id is None:
            return
        with self._pending_lock:
            self._cancelled.add(_key(request_id))

    # --- server requests ---------------------------------------------------

    def request_from_client(self, method, params, timeout):
        """Send a server request and wait for its correlated response.

        Returns the response result, or `None` when no answer arrived. A
        `None` is never turned into consent by any caller.
        """

        if self.protocol is None:
            raise CabinetError("ELICITATION_UNSUPPORTED",
                               "the client has not initialized")
        if self._stopped.is_set():
            raise CabinetError("ELICITATION_UNSUPPORTED",
                               "the connection is closing")
        request_id = self._new_request_id()
        event = threading.Event()
        slot = {}
        with self._pending_lock:
            self._pending[_key(request_id)] = (event, slot)
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method,
                    "params": params})
        answered = event.wait(timeout)
        with self._pending_lock:
            self._pending.pop(_key(request_id), None)
        if not answered:
            self._send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                        "params": {"requestId": request_id,
                                   "reason": "no answer within the timeout"}})
            return None
        if "result" in slot:
            return slot["result"]
        return None

    def _resolve(self, message):
        """Route a client response to the request that is waiting for it."""

        request_id = message.get("id")
        with self._pending_lock:
            entry = self._pending.pop(_key(request_id), None)
        if entry is None:
            self._log("dropped a response with no pending request: %s"
                      % (request_id,))
            return
        event, slot = entry
        if "result" in message:
            slot["result"] = message["result"]
        else:
            slot["error"] = message.get("error")
        event.set()

    def _new_request_id(self):
        with self._pending_lock:
            self._request_counter += 1
            return "cabinet-%d" % self._request_counter

    # --- writing -----------------------------------------------------------

    def _send_result(self, message_id, result):
        with self._pending_lock:
            if _key(message_id) in self._cancelled:
                self._cancelled.discard(_key(message_id))
                return
        self._send({"jsonrpc": "2.0", "id": message_id, "result": result})

    def _send_error(self, message_id, code, text):
        self._send({"jsonrpc": "2.0", "id": message_id,
                    "error": {"code": code, "message": text}})

    def _send(self, message):
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self._write_lock:
            try:
                self.writer.write(data)
                self.writer.flush()
            except (BrokenPipeError, ValueError, OSError):
                self._stopped.set()


def _key(message_id):
    """A hashable identity for a JSON-RPC id of any allowed type."""

    return (type(message_id).__name__, message_id)


class StdioElicitor:
    """F3's elicitor interface, carried over the server's request plumbing.

    Every non-answer is the same non-answer: a client that cannot show a form
    refuses with a stable code, and a dialog that times out, is cancelled or
    arrives malformed becomes a cancel outcome. None of them is a grant.
    """

    def __init__(self, timeout=DEFAULT_DIALOG_TIMEOUT):
        self.timeout = float(timeout)
        self.server = None

    def attach(self, server):
        self.server = server

    def available(self):
        """Whether a dialog could be shown right now.

        The service asks this before it records an approval request, so a
        client that can never answer does not leave a pending question behind.
        """

        return (self.server is not None and self.server.protocol is not None
                and self.server.supports_form_elicitation())

    def request(self, message, schema):
        server = self.server
        if server is None or server.protocol is None:
            raise CabinetError("ELICITATION_UNSUPPORTED",
                               "no initialized client connection is available")
        if not server.supports_form_elicitation():
            raise CabinetError(
                "ELICITATION_UNSUPPORTED",
                "the connected client did not advertise form elicitation, so "
                "the owner cannot be asked")
        params = elicitation_params(message, schema, server.protocol)
        answer = server.request_from_client("elicitation/create", params,
                                            self.timeout)
        if not isinstance(answer, dict):
            return {"action": "cancel"}
        return answer
