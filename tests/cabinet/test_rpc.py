"""Protocol tests for the Cabinet stdio MCP server.

Every test here drives a real `RpcServer` over a real pipe pair from the
client side, because the properties under test are ordering properties: an
`elicitation/create` request has to leave the server while the `tools/call`
that caused it is still unanswered, and a `ping` has to be answered while a
tool call is parked on an owner dialog. A test that called the server's
methods directly would prove none of that.

Run with:

    PYTHONPATH=plugins/cabinet/scripts:tests/cabinet \
      python3 -m unittest discover -s tests/cabinet -p test_rpc.py
"""

import json
import unittest

from support import RpcHarness, ServiceCase

from cabinet_runtime import rpc
from cabinet_runtime.approval import BATCH_SCHEMA


class RpcCase(ServiceCase):
    """A company, a service, and a client talking to it over pipes."""

    protocol = "2025-11-25"
    capabilities = None
    handshake = True

    def setUp(self):
        super().setUp()
        self.elicitor = rpc.StdioElicitor(timeout=5.0)
        self.service.elicitor = self.elicitor
        self.client = RpcHarness(self.service, self.elicitor).start()
        self.addCleanup(self.client.close)
        if self.handshake:
            self.initialized = self.client.initialize(
                protocol=self.protocol, capabilities=self.capabilities)

    def call_tool(self, name, arguments=None):
        return self.client.request("tools/call",
                                   {"name": name,
                                    "arguments": arguments or {}})

    def grants(self):
        return [row for row in self.store.get_grants()]


class HandshakeTest(RpcCase):
    handshake = False

    def test_the_server_declares_tools_and_nothing_else(self):
        result = self.client.initialize()["result"]
        self.assertEqual(result["protocolVersion"], "2025-11-25")
        self.assertEqual(list(result["capabilities"]), ["tools"])
        self.assertNotIn("sampling", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "cabinet")

    def test_an_unsupported_version_falls_back_to_the_latest_supported(self):
        result = self.client.initialize(protocol="1999-01-01",
                                        capabilities={})["result"]
        self.assertEqual(result["protocolVersion"], rpc.LATEST_PROTOCOL)

    def test_the_older_supported_version_is_negotiated_when_asked_for(self):
        result = self.client.initialize(protocol="2025-06-18")["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_a_tool_call_before_initialize_is_refused(self):
        message_id = self.client.request("tools/list")
        answer = self.client.take(lambda m: m.get("id") == message_id)
        self.assertEqual(answer["error"]["code"], rpc.INVALID_REQUEST)

    def test_ping_is_answered_before_initialize(self):
        message_id = self.client.request("ping")
        answer = self.client.take(lambda m: m.get("id") == message_id)
        self.assertEqual(answer["result"], {})


class ToolListingTest(RpcCase):

    def test_every_tool_carries_a_closed_schema(self):
        message_id = self.client.request("tools/list")
        tools = self.client.take(lambda m: m.get("id") == message_id)
        names = []
        for tool in tools["result"]["tools"]:
            names.append(tool["name"])
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertIs(schema["additionalProperties"], False)
            self.assertTrue(tool["description"])
        self.assertIn("cabinet_doctor", names)
        self.assertIn("cabinet_request_owner_approval", names)

    def test_the_listed_names_match_the_profile_registry(self):
        from cabinet_runtime import profiles

        message_id = self.client.request("tools/list")
        tools = self.client.take(lambda m: m.get("id") == message_id)
        listed = sorted(tool["name"] for tool in tools["result"]["tools"])
        expected = sorted("cabinet_%s" % name
                          for name in profiles.SERVICE_METHODS)
        self.assertEqual(listed, expected)


class ApprovalTranscriptTest(RpcCase):
    """The transcript the F4 brief pins, driven end to end."""

    def test_the_grant_arrives_only_after_the_owner_answers(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})

        dialog = self.client.server_request("elicitation/create")
        self.assertEqual(dialog["params"]["mode"], "form")
        self.assertEqual(dialog["params"]["requestedSchema"], BATCH_SCHEMA)
        self.assertIn("Approve work batch B001", dialog["params"]["message"])

        # Nothing has been granted while the question is still open.
        self.assertIsNone(self.client.answer(call_id, timeout=0.5))
        self.assertEqual(self.grants(), [])

        self.client.respond(dialog["id"],
                            {"action": "accept", "content": {"approve": True}})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        payload = answer["result"]["structuredContent"]
        self.assertIs(answer["result"]["isError"], False)
        self.assertTrue(payload["granted"])
        self.assertEqual(payload["reason"], "approved")
        self.assertEqual(len(self.grants()), 1)

    def test_a_decline_creates_no_grant(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")
        self.client.respond(dialog["id"], {"action": "decline"})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        payload = answer["result"]["structuredContent"]
        self.assertFalse(payload["granted"])
        self.assertEqual(payload["reason"], "declined")
        self.assertEqual(self.grants(), [])

    def test_an_accept_carrying_a_false_approve_creates_no_grant(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")
        self.client.respond(dialog["id"],
                            {"action": "accept", "content": {"approve": False}})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertFalse(answer["result"]["structuredContent"]["granted"])
        self.assertEqual(self.grants(), [])

    def test_a_response_under_another_id_answers_nothing(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")
        self.client.respond("%s-not-mine" % dialog["id"],
                            {"action": "accept", "content": {"approve": True}})
        self.assertIsNone(self.client.answer(call_id, timeout=0.5))
        self.assertEqual(self.grants(), [])

        self.client.respond(dialog["id"], {"action": "decline"})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertEqual(answer["result"]["structuredContent"]["reason"],
                         "declined")

    def test_a_replayed_response_creates_no_second_grant(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")
        accept = {"action": "accept", "content": {"approve": True}}
        self.client.respond(dialog["id"], accept)
        self.client.take(lambda m: m.get("id") == call_id)
        # The captured response, replayed verbatim, twice.
        self.client.respond(dialog["id"], accept)
        self.client.respond(dialog["id"], accept)
        pong = self.client.request("ping")
        self.client.take(lambda m: m.get("id") == pong)
        self.assertEqual(len(self.grants()), 1)

    def test_the_dialog_is_not_reopened_by_a_second_approval_call(self):
        first = self.call_tool("cabinet_request_owner_approval",
                               {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")
        self.client.respond(dialog["id"],
                            {"action": "accept", "content": {"approve": True}})
        self.client.take(lambda m: m.get("id") == first)

        second = self.call_tool("cabinet_request_owner_approval",
                                {"batch_id": "B001", "revision": 1})
        repeat = self.client.server_request("elicitation/create")
        self.client.respond(repeat["id"],
                            {"action": "accept", "content": {"approve": True}})
        self.client.take(lambda m: m.get("id") == second)
        self.assertEqual(len(self.grants()), 1)


class OlderProtocolTest(RpcCase):
    protocol = "2025-06-18"

    def test_the_dialog_carries_no_mode_field(self):
        self.call_tool("cabinet_request_owner_approval",
                       {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")
        self.assertNotIn("mode", dialog["params"])
        self.assertEqual(dialog["params"]["requestedSchema"], BATCH_SCHEMA)
        self.client.respond(dialog["id"], {"action": "cancel"})


class NoElicitationTest(RpcCase):
    capabilities = {}

    def test_approval_is_refused_when_the_client_cannot_show_a_form(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertIs(answer["result"]["isError"], True)
        payload = answer["result"]["structuredContent"]
        self.assertEqual(payload["error"]["code"], "ELICITATION_UNSUPPORTED")
        self.assertEqual(self.grants(), [])

    def test_the_refusal_records_no_pending_approval_request(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        self.client.take(lambda m: m.get("id") == call_id)
        kinds = [event["kind"] for event in self.store.get_events()]
        self.assertNotIn("approval.requested", kinds)

    def test_reads_still_work_without_an_elicitation_capability(self):
        call_id = self.call_tool("cabinet_doctor")
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertIs(answer["result"]["isError"], False)


class NoFormModeTest(RpcCase):
    """2025-11-25 with elicitation but without the form mode."""

    capabilities = {"elicitation": {"url": {}}}

    def test_a_url_only_client_cannot_be_asked_for_approval(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertEqual(answer["result"]["structuredContent"]["error"]["code"],
                         "ELICITATION_UNSUPPORTED")


class TransportErrorTest(RpcCase):

    def test_malformed_json_is_a_parse_error(self):
        self.client.send_raw(b"{not json at all\n")
        answer = self.client.take(lambda m: "error" in m)
        self.assertEqual(answer["error"]["code"], rpc.PARSE_ERROR)

    def test_a_message_over_the_bound_is_refused_and_the_stream_recovers(self):
        oversize = b'{"jsonrpc":"2.0","id":9,"method":"ping","pad":"' \
            + b"x" * (rpc.MAX_MESSAGE_BYTES + 64) + b'"}\n'
        self.client.send_raw(oversize)
        answer = self.client.take(lambda m: "error" in m and m.get("id") is None)
        self.assertEqual(answer["error"]["code"], rpc.PARSE_ERROR)
        self.assertIn("1048576", answer["error"]["message"])
        pong = self.client.request("ping")
        self.assertEqual(self.client.take(lambda m: m.get("id") == pong)
                         ["result"], {})

    def test_an_unknown_method_is_method_not_found(self):
        message_id = self.client.request("resources/list")
        answer = self.client.take(lambda m: m.get("id") == message_id)
        self.assertEqual(answer["error"]["code"], rpc.METHOD_NOT_FOUND)

    def test_a_tools_call_without_an_object_for_params_is_invalid(self):
        self.client.send({"jsonrpc": "2.0", "id": 77, "method": "tools/call",
                          "params": "cabinet_doctor"})
        answer = self.client.take(lambda m: m.get("id") == 77)
        self.assertEqual(answer["error"]["code"], rpc.INVALID_PARAMS)

    def test_an_unknown_tool_name_is_invalid_params(self):
        call_id = self.call_tool("cabinet_delete_everything")
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertEqual(answer["error"]["code"], rpc.INVALID_PARAMS)

    def test_arguments_that_are_not_an_object_are_invalid_params(self):
        self.client.send({"jsonrpc": "2.0", "id": 78, "method": "tools/call",
                          "params": {"name": "cabinet_doctor",
                                     "arguments": ["nope"]}})
        answer = self.client.take(lambda m: m.get("id") == 78)
        self.assertEqual(answer["error"]["code"], rpc.INVALID_PARAMS)

    def test_a_notification_is_never_answered(self):
        self.client.send({"jsonrpc": "2.0", "method": "notifications/unknown"})
        pong = self.client.request("ping")
        answer = self.client.take(lambda m: m.get("id") == pong)
        self.assertEqual(answer["result"], {})
        self.assertEqual(self.client.held, [])


class DomainErrorTest(RpcCase):

    def test_a_domain_error_carries_its_cabinet_code_in_both_places(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B404", "revision": 1})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        result = answer["result"]
        self.assertIs(result["isError"], True)
        self.assertEqual(result["structuredContent"]["error"]["code"],
                         "BATCH_NOT_FOUND")
        self.assertIn("BATCH_NOT_FOUND", result["content"][0]["text"])

    def test_an_unknown_argument_is_refused_by_the_tool_schema(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1,
                                  "approved": True})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertEqual(answer["result"]["structuredContent"]["error"]["code"],
                         "FIELD_UNKNOWN")
        self.assertEqual(self.grants(), [])


class ConcurrencyTest(RpcCase):

    def test_a_tools_call_on_an_open_dialog_does_not_block_a_ping(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")

        pong = self.client.request("ping")
        self.assertEqual(self.client.take(lambda m: m.get("id") == pong)
                         ["result"], {})
        listing = self.client.request("tools/list")
        self.assertIn("tools",
                      self.client.take(lambda m: m.get("id") == listing)
                      ["result"])

        self.client.respond(dialog["id"], {"action": "cancel"})
        answer = self.client.take(lambda m: m.get("id") == call_id)
        self.assertEqual(answer["result"]["structuredContent"]["reason"],
                         "cancelled")
        self.assertEqual(self.grants(), [])

    def test_a_cancelled_call_produces_no_response(self):
        call_id = self.call_tool("cabinet_request_owner_approval",
                                 {"batch_id": "B001", "revision": 1})
        dialog = self.client.server_request("elicitation/create")
        self.client.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                          "params": {"requestId": call_id,
                                     "reason": "owner walked away"}})
        self.client.respond(dialog["id"], {"action": "decline"})
        pong = self.client.request("ping")
        self.client.take(lambda m: m.get("id") == pong)
        self.assertIsNone(self.client.answer(call_id, timeout=0.5))


class ElicitorUnitTest(unittest.TestCase):
    """The elicitor's own refusals, without a company behind it."""

    def test_an_unattached_elicitor_never_returns_a_grant(self):
        from cabinet_runtime.errors import CabinetError

        elicitor = rpc.StdioElicitor()
        with self.assertRaises(CabinetError) as caught:
            elicitor.request("approve?", BATCH_SCHEMA)
        self.assertEqual(caught.exception.code, "ELICITATION_UNSUPPORTED")

    def test_the_elicitor_checks_the_capability_itself(self):
        """The service pre-checks too; this is the guard underneath it."""

        from cabinet_runtime.errors import CabinetError

        class Server:
            protocol = "2025-11-25"

            @staticmethod
            def supports_form_elicitation():
                return False

            @staticmethod
            def request_from_client(*_args):
                raise AssertionError("no dialog may be opened")

        elicitor = rpc.StdioElicitor()
        elicitor.attach(Server())
        self.assertFalse(elicitor.available())
        with self.assertRaises(CabinetError) as caught:
            elicitor.request("approve?", BATCH_SCHEMA)
        self.assertEqual(caught.exception.code, "ELICITATION_UNSUPPORTED")

    def test_the_dialog_parameters_match_the_negotiated_version(self):
        new = rpc.elicitation_params("m", BATCH_SCHEMA, "2025-11-25")
        old = rpc.elicitation_params("m", BATCH_SCHEMA, "2025-06-18")
        self.assertEqual(new["mode"], "form")
        self.assertNotIn("mode", old)
        self.assertEqual(new["requestedSchema"], BATCH_SCHEMA)
        self.assertEqual(json.loads(json.dumps(old)), old)

    def test_form_support_is_read_per_protocol_version(self):
        self.assertTrue(rpc.elicitation_form_supported(
            {"elicitation": {"form": {}}}, "2025-11-25"))
        self.assertFalse(rpc.elicitation_form_supported(
            {"elicitation": {}}, "2025-11-25"))
        self.assertTrue(rpc.elicitation_form_supported(
            {"elicitation": {}}, "2025-06-18"))
        self.assertFalse(rpc.elicitation_form_supported({}, "2025-06-18"))


if __name__ == "__main__":
    unittest.main()
