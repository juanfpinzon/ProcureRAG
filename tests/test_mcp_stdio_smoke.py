import importlib.util
from pathlib import Path

import pytest


def _load_mcp_stdio_smoke_module():
    """Load `scripts/mcp_stdio_smoke.py` by path, like `tests/test_container_smoke.py`
    does for its script. Importing it starts nothing: the server is only
    launched by `main()`."""
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "mcp_stdio_smoke.py"
    spec = importlib.util.spec_from_file_location("mcp_stdio_smoke", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The smoke's process checks read the server's stderr, which the SDK writes
# through Rich (80 columns when stderr is not a terminal). Where a long line
# wraps depends on the numbers in it, so the checks are shown passing on two
# real wraps and failing on a broken log. No server is started here: the
# real run is `scripts/mcp_stdio_smoke.py` itself.
# ---------------------------------------------------------------------------

# Measured on the Mac on 2026-10-25 (the real server, started with its stdin
# closed), padding included. The source location follows "6.0 s".
MAC_READY = (
    "                    INFO     ProcureRAG service ready in 6.0 s mcp_server.py:361\n"
    "                             (pid 8164, live LLM: False)                        \n"
)
MAC_STOPPED = (
    "                    INFO     ProcureRAG MCP server stopped     mcp_server.py:371\n"
    "                             (pid 8164)                                         \n"
)
MAC_STDERR = MAC_READY + MAC_STOPPED

# As reported from a Linux run in the 2026-10-25 review (the excerpt starts at
# the message, without Rich's time and level columns). The load took 96.4 s,
# and the source location landed between "96.4" and "s": the startup line the
# first version of the smoke could not find.
LINUX_READY = (
    "ProcureRAG service ready in 96.4  mcp_server.py:361\n"
    "                         s (pid 1560422, live LLM: False)\n"
)


@pytest.mark.parametrize(
    ("stderr_text", "expected"),
    [(MAC_READY, ("6.0", "8164", "False")), (LINUX_READY, ("96.4", "1560422", "False"))],
    ids=["macos-measured", "linux-reported"],
)
def test_the_startup_line_is_found_wherever_rich_put_the_source_location(stderr_text, expected):
    smoke = _load_mcp_stdio_smoke_module()

    assert smoke.READY_PATTERN.findall(smoke.flatten_log(stderr_text)) == [expected]


def test_a_clean_real_log_passes_every_stderr_check(monkeypatch):
    smoke = _load_mcp_stdio_smoke_module()
    monkeypatch.setattr(smoke, "process_is_gone", lambda pid: True)  # pid 8164 belonged to a past run

    assert smoke.check_server_stderr(MAC_STDERR) == ([], ("6.0", "8164", "False"))


@pytest.mark.parametrize(
    ("stderr_text", "problem"),
    [
        ("", "built exactly once, saw 0"),
        (MAC_READY + MAC_READY + MAC_STOPPED, "built exactly once, saw 2"),
        (MAC_STDERR.replace("live LLM: False", "live LLM: True"), "'live LLM: True'"),
        (MAC_READY, "no clean-shutdown line"),  # killed: it never left its lifespan
        (MAC_STDERR + "Traceback (most recent call last):\n", "contains a traceback"),
        (MAC_STDERR + "provider timed out for key sk-or-v1-not-a-real-key\n", "secret-like text"),
    ],
    ids=["no-build", "two-builds", "live-llm-on", "no-clean-stop", "traceback", "secret"],
)
def test_each_stderr_check_fails_on_a_broken_log(monkeypatch, stderr_text, problem):
    smoke = _load_mcp_stdio_smoke_module()
    monkeypatch.setattr(smoke, "process_is_gone", lambda pid: True)

    problems, _ = smoke.check_server_stderr(stderr_text)

    assert any(problem in reported for reported in problems), problems


def test_the_stderr_check_fails_if_the_server_process_is_still_running(monkeypatch):
    smoke = _load_mcp_stdio_smoke_module()
    monkeypatch.setattr(smoke, "process_is_gone", lambda pid: False)

    problems, _ = smoke.check_server_stderr(MAC_STDERR)

    assert problems == ["the server process 8164 is still running after shutdown"]
