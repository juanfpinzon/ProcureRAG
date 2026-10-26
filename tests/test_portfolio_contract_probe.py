import importlib.util
import sys
from pathlib import Path

import pytest


def _load_probe_module():
    """Load `scripts/portfolio_contract_probe.py` by path, like `tests/test_mcp_stdio_smoke.py`
    does for its script. Importing it runs no scenario: only `main()` does.

    The script puts `src/` on `sys.path` so that it can `import api`. Every
    other test file keeps `src` there only while a module's own imports
    resolve, so `sys.path` is put back right after the load.
    """
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "portfolio_contract_probe.py"
    saved_path = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location("portfolio_contract_probe", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved_path


def _send_that_must_not_be_called(upstream_body):
    raise AssertionError(f"the BFF called upstream with {upstream_body}, but it should have refused first")


def test_every_scenario_and_contract_check_passes(capsys):
    """The whole probe, exactly as `uv run python scripts/portfolio_contract_probe.py` runs it."""
    probe = _load_probe_module()

    assert probe.main() == 0
    assert "0 failure(s)." in capsys.readouterr().out


def test_the_probe_leaves_the_shared_api_app_without_its_fake_service():
    """`api` is one shared module (`tests/test_mcp_server.py` uses it too), so the probe must clean up."""
    probe = _load_probe_module()

    probe.main()

    assert probe.api.get_service not in probe.api.app.dependency_overrides


def test_only_an_exact_preset_text_gets_its_query_id():
    probe = _load_probe_module()
    preset_text = probe.LABELED_QUERIES["Q001"]["query"]

    assert probe.build_upstream_request(preset_text) == {"query": preset_text, "role": "requester", "query_id": "Q001"}
    assert probe.build_upstream_request(preset_text + " ") == {"query": preset_text + " ", "role": "requester"}
    # A labeled question that is NOT a public preset is free text too, even word for word.
    q091_text = probe.LABELED_QUERIES["Q091"]["query"]
    assert probe.build_upstream_request(q091_text) == {"query": q091_text, "role": "requester"}


@pytest.mark.parametrize(
    "extra_field",
    [{"role": "buyer"}, {"query_id": "Q001"}, {"decision": {"type": "approve"}}],
    ids=["role", "query_id", "decision"],
)
def test_the_browser_cannot_send_a_role_a_query_id_or_a_decision(extra_field):
    probe = _load_probe_module()
    body = probe.browser_json({"question": probe.LABELED_QUERIES["Q001"]["query"], **extra_field})

    http_status, view = probe.handle_browser_request(body, _send_that_must_not_be_called)

    assert (http_status, view.state) == (422, "invalid_question")


def test_the_kill_switch_answers_before_validation_or_any_upstream_call():
    probe = _load_probe_module()

    http_status, view = probe.handle_browser_request(b"not even json", _send_that_must_not_be_called, demo_enabled=False)

    assert (http_status, view.state) == (503, "unavailable")


def test_the_longest_valid_question_fits_in_the_body_cap():
    """The byte cap must never refuse a question the character cap allows.

    An emoji is one character but 4 bytes of UTF-8, the most any character
    takes, so 500 of them is the largest body a valid question can produce.
    """
    probe = _load_probe_module()

    largest_valid_body = probe.browser_json({"question": "\N{GRINNING FACE}" * probe.MAX_QUESTION_CHARS})

    assert len(largest_valid_body) <= probe.MAX_BODY_BYTES


@pytest.mark.parametrize(
    ("header_value", "expected"),
    [("30", 30), ("0", 0), (None, None), ("Wed, 21 Oct 2026 07:28:00 GMT", None), ("-5", None), ("soon", None)],
    ids=["seconds", "zero", "missing", "date", "negative", "garbage"],
)
def test_retry_after_keeps_only_a_whole_number_of_seconds(header_value, expected):
    probe = _load_probe_module()

    assert probe.parse_retry_after(header_value) == expected
