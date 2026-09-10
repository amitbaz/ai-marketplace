"""Bounded subprocess adapter.

Every external command the runtime runs goes through `run_argv`. The adapter
holds four properties that are easy to lose one call at a time:

* the command is a list and `shell=False`, so no argument is ever parsed as
  syntax by a shell;
* the child environment is built from an explicit allowlist, never from all of
  `os.environ`, so a token in the parent process is not handed to a test
  command written by someone else;
* stdout and stderr are bounded and redacted before they are returned, because
  a return value ends up in a model's context; and
* a timeout is reported as an ambiguous outcome, not retried. The command may
  already have reached an external system, so the caller decides, with a
  readback, whether anything happened.

Nothing here interprets what a command means. The caller supplies argv.
"""

import re
import subprocess
import time

from .errors import CabinetError

#: Maximum bytes kept from each captured stream before truncation.
OUTPUT_LIMIT = 1024 * 1024

#: Stable outcome classifications. `UNCERTAIN` is what a caller maps onto the
#: `uncertain` action state: the command may have dispatched before the clock
#: ran out, so repeating it is not safe without a readback.
COMPLETED = "completed"
UNCERTAIN = "timeout_after_possible_dispatch"

REDACTED = "[redacted]"

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Assignments and headers whose name reads as a secret: the value goes, the
# name stays, so a reader can still see which variable was set.
_NAMED_SECRET = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*(?:token|secret|password|passwd|api[_-]?key|key|"
    r"credential|cookie|authorization)[A-Za-z0-9_.-]*)"
    r"(\s*[:=]\s*|\s+)(\"|')?([^\s\"']+)")

# Values that are recognisably a credential wherever they appear.
_SECRET_VALUES = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{2,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*"
               r"PRIVATE KEY-----", re.S),
]


def build_env(allow=(), extra=None, environ=None):
    """Return a child environment holding only the named variables.

    `allow` names variables to copy from `environ` when they are set. `extra`
    supplies values directly. A variable absent from both is absent from the
    result: there is no fallback to the parent process.
    """

    if environ is None:
        import os

        environ = os.environ
    if isinstance(allow, (str, bytes)):
        raise CabinetError("ENV_INVALID", "allow must be a sequence of names")
    env = {}
    for name in allow:
        _check_env_name(name)
        if name in environ:
            _check_env_value(name, environ[name])
            env[name] = environ[name]
    if extra is not None:
        if not isinstance(extra, dict):
            raise CabinetError("ENV_INVALID", "extra must be a mapping")
        for name, value in extra.items():
            _check_env_name(name)
            _check_env_value(name, value)
            env[name] = value
    return env


def _check_env_name(name):
    if not isinstance(name, str) or not _NAME.match(name):
        raise CabinetError("ENV_INVALID",
                           "%r is not a plain environment variable name"
                           % (name,))


def _check_env_value(name, value):
    if not isinstance(value, str) or "\x00" in value:
        raise CabinetError("ENV_INVALID",
                           "the value of %s must be a string without a null "
                           "byte" % (name,))


def redact(text):
    """Return `text` with recognisable credential material removed.

    Two passes: values that are recognisably a credential anywhere, and then
    anything shaped like `name: value` where the name reads as a secret. The
    second pass is right for a log line and wrong for structured data — it
    rewrites `"key":"mit"` in a JSON document into invalid syntax. Use
    `redact_values` when the text has a shape worth preserving.
    """

    return _NAMED_SECRET.sub(
        lambda m: "%s%s%s" % (m.group(1), m.group(2), REDACTED),
        redact_values(text))


def redact_values(text):
    """Mask credential material without rewriting anything around it.

    Only values that are recognisably a credential on their own — a `ghp_`
    token, an AWS key id, a JWT, a PEM block — are replaced. Structure
    survives, so this is safe to run over a string that was parsed out of JSON
    and will be serialized again.
    """

    if not text:
        return text
    for pattern in _SECRET_VALUES:
        text = pattern.sub(REDACTED, text)
    return text


def bound(text, limit):
    """Return at most `limit` bytes of `text`, marking any loss.

    The bound is in bytes because that is what `OUTPUT_LIMIT` promises;
    slicing characters would let multibyte output run several times over it.
    """

    if text is None:
        return ""
    if not isinstance(text, str):
        text = text.decode("utf-8", "replace")
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", "ignore") + (
        "\n[cabinet: output truncated at %d bytes]" % limit)


def _check_argv(argv):
    if isinstance(argv, (str, bytes)) or not isinstance(argv, (list, tuple)):
        raise CabinetError("ARGV_INVALID",
                           "a command must be a list of strings, not %s"
                           % type(argv).__name__)
    if not argv:
        raise CabinetError("ARGV_INVALID", "a command must name a program")
    for index, word in enumerate(argv):
        if not isinstance(word, str):
            raise CabinetError("ARGV_INVALID",
                               "argv[%d] is %s, not a string"
                               % (index, type(word).__name__))
        if "\x00" in word:
            raise CabinetError("ARGV_INVALID",
                               "argv[%d] contains a null byte" % index)
    return list(argv)


def _check_cwd(cwd):
    text = str(cwd)
    if not text.startswith("/"):
        raise CabinetError("UNSAFE_PATH",
                           "a working directory must be absolute: %r" % (text,))
    if ".." in text.split("/") or "\x00" in text:
        raise CabinetError("UNSAFE_PATH",
                           "a working directory must not traverse: %r" % (text,))
    return text


def run_argv(argv, cwd, env, timeout, runner=subprocess.run,
             output_limit=OUTPUT_LIMIT, clock=time.monotonic,
             input_text=None, redact_output=True):
    """Run `argv` and return a bounded, redacted result.

    The returned dictionary carries `returncode`, `stdout`, `stderr`,
    `timed_out`, `duration` and `classification`. It never carries the
    environment, and a timeout is classified rather than retried here.

    `input_text` is written to the child's standard input. It exists so a
    request body travels as data rather than as words in a command line: a
    title someone wrote is never parsed by anything on its way to the
    provider. With no input the child gets no standard input at all.

    `redact_output` may be turned off only by a caller that parses the output
    structurally and returns selected fields rather than the text. Redaction
    rewrites anything shaped like `key: value`, which is a safe thing to do to
    a log line and a corrupting thing to do to JSON — `"key":"mit"` in a
    licence object comes back as invalid syntax. A caller that turns it off
    owns redacting whatever it surfaces from the result.
    """

    argv = _check_argv(argv)
    cwd = _check_cwd(cwd)
    if env is None or not isinstance(env, dict):
        raise CabinetError(
            "ENV_INVALID",
            "a child environment must be built with build_env; the parent "
            "environment is never inherited")
    for name, value in env.items():
        _check_env_name(name)
        _check_env_value(name, value)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise CabinetError("FIELD_INVALID", "timeout must be a number of seconds")
    if timeout <= 0:
        raise CabinetError("FIELD_INVALID", "timeout must be positive")

    if input_text is not None and not isinstance(input_text, str):
        raise CabinetError("FIELD_INVALID",
                           "standard input must be text already serialized")
    fed = {"input": input_text} if input_text is not None \
        else {"stdin": subprocess.DEVNULL}

    clean = redact if redact_output else (lambda text: text)

    started = clock()
    try:
        completed = runner(argv, cwd=cwd, env=dict(env), timeout=timeout,
                           shell=False, capture_output=True, text=True,
                           check=False, **fed)
    except subprocess.TimeoutExpired as expired:
        return {
            "returncode": None,
            "stdout": bound(clean(_captured(expired.stdout)), output_limit),
            "stderr": bound(redact(_captured(expired.stderr)), output_limit),
            "timed_out": True,
            "duration": clock() - started,
            "classification": UNCERTAIN,
        }
    return {
        "returncode": completed.returncode,
        "stdout": bound(clean(_captured(completed.stdout)), output_limit),
        "stderr": bound(redact(_captured(completed.stderr)), output_limit),
        "timed_out": False,
        "duration": clock() - started,
        "classification": COMPLETED,
    }


def _captured(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value
