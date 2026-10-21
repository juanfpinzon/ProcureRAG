import importlib.util
from pathlib import Path


def _load_container_smoke_module():
    """Load `scripts/container_smoke.py` by path. It is a standalone script
    (standard library only), so unlike the `src` modules it needs no
    `sys.path` change for its own imports.
    """
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "container_smoke.py"
    spec = importlib.util.spec_from_file_location("container_smoke", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# The probe checks are pure functions over (status, JSON body). A check that
# quietly stopped failing would make the Docker CI job a false green, so each
# one is shown passing on the measured answer and failing on a wrong one. No
# Docker is needed: the real container run is the CI job itself.
# ---------------------------------------------------------------------------

# The shapes measured from the real container on 2026-10-20.
Q001_ANSWER = {
    "status": "not_generated",
    "run_id": "5f0c7a3e-0000-4000-8000-000000000001",
    "sources": [{"doc_id": doc_id} for doc_id in ("POL-001", "FAQ-001", "POL-001", "FAQ-001", "FAQ-001")],
}
Q091_PENDING = {"status": "pending_approval", "approval_request": {"query_id": "Q091"}, "sources": [], "run_id": None}
OFF_TOPIC_BLOCKED = {"status": "blocked", "findings": [{"guard": "off_topic"}], "run_id": None}


def test_health_requires_live_llm_false():
    smoke = _load_container_smoke_module()

    assert smoke.check_health({"status": "ok", "live_llm": False}) == []
    assert smoke.check_health({"status": "ok", "live_llm": True}) != []


def test_q001_passes_on_the_measured_answer_and_fails_when_the_llm_ran_or_retrieval_changed():
    smoke = _load_container_smoke_module()

    assert smoke.check_q001(200, Q001_ANSWER) == []
    assert smoke.check_q001(200, {**Q001_ANSWER, "status": "answered"}) != []  # a provider was used
    assert smoke.check_q001(200, {**Q001_ANSWER, "sources": Q001_ANSWER["sources"][:4]}) != []
    assert smoke.check_q001(500, {"_raw": "Internal Server Error"}) != []
    assert smoke.check_q001(None, {"_error": "ConnectionResetError"}) != []  # the server died mid-request


def test_q091_must_stop_before_retrieval():
    smoke = _load_container_smoke_module()

    assert smoke.check_q091_pending(200, Q091_PENDING) == []
    # The graph ran without a decision: a run_id and sources are both wrong.
    ran_anyway = {**Q091_PENDING, "run_id": "5f0c7a3e-0000-4000-8000-000000000002", "sources": [{"doc_id": "POL-001"}]}
    assert len(smoke.check_q091_pending(200, ran_anyway)) == 2


def test_off_topic_must_be_blocked_by_the_off_topic_guard():
    smoke = _load_container_smoke_module()

    assert smoke.check_off_topic_blocked(200, OFF_TOPIC_BLOCKED) == []
    assert smoke.check_off_topic_blocked(200, {**OFF_TOPIC_BLOCKED, "status": "not_generated"}) != []


def test_log_check_names_the_keyword_and_line_but_never_prints_the_line():
    smoke = _load_container_smoke_module()
    fake_key = "sk-or-v1-THIS-IS-NOT-A-REAL-KEY"
    logs = f"INFO: startup complete\nDEBUG: key={fake_key}\nTraceback (most recent call last):\n"

    failures = smoke.check_logs(logs)
    printed = smoke.redacted(logs)

    assert "logs contain 1 traceback(s)" in failures
    assert any("log line 2" in failure and "'sk-or'" in failure for failure in failures)
    assert all(fake_key not in failure for failure in failures)
    assert fake_key not in printed  # the debugging tail hides it too
    assert smoke.check_logs("INFO: startup complete\nINFO: GET /health 200\n") == []
