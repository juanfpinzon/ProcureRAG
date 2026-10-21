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


# ---------------------------------------------------------------------------
# URL mode (`--url`): the deploy workflow's post-deployment smoke. The HTTP
# layer is replaced by the measured answers, and `subprocess.run` (every
# docker call goes through it) is made to fail the test if it is ever used.
# ---------------------------------------------------------------------------


def _serve_measured_answers(monkeypatch, smoke, health=None):
    """Make the script's two HTTP helpers return the measured answers, and forbid docker."""

    def no_docker(*args, **kwargs):
        raise AssertionError("URL mode must not call docker")

    def fake_post(url, body, timeout=60):
        answers = {"Q001": (200, Q001_ANSWER), "Q091": (200, Q091_PENDING)}
        return answers.get(body.get("query_id"), (200, OFF_TOPIC_BLOCKED))

    monkeypatch.setattr(smoke.subprocess, "run", no_docker)
    monkeypatch.setattr(smoke, "http_get_json", lambda url, timeout=5: (200, health or {"status": "ok", "live_llm": False}))
    monkeypatch.setattr(smoke, "http_post_json", fake_post)


def test_url_mode_passes_on_the_measured_answers_without_touching_docker(monkeypatch, capsys):
    smoke = _load_container_smoke_module()
    _serve_measured_answers(monkeypatch, smoke)

    assert smoke.main(["--url", "https://procurerag-api.example.invalid/"]) == smoke.EXIT_PASSED
    output = capsys.readouterr().out
    assert "[skip] logs" in output
    assert "example.invalid" not in output  # the deployment's URL is never printed


def test_url_mode_fails_when_the_deployed_revision_has_the_live_llm_on(monkeypatch):
    smoke = _load_container_smoke_module()
    _serve_measured_answers(monkeypatch, smoke, health={"status": "ok", "live_llm": True})

    assert smoke.main(["--url", "https://procurerag-api.example.invalid"]) == smoke.EXIT_CONTRACT_FAILED


def test_url_mode_reports_a_service_that_never_answers_as_a_startup_failure(monkeypatch):
    smoke = _load_container_smoke_module()
    _serve_measured_answers(monkeypatch, smoke)

    # A zero-second budget: the wait loop never gets to ask, exactly like a
    # revision that never answers. It must exit 2 without asking docker for logs.
    assert smoke.main(["--url", "https://procurerag-api.example.invalid", "--health-budget", "0"]) == (
        smoke.EXIT_STARTUP_FAILED
    )


def test_exactly_one_target_is_required():
    smoke = _load_container_smoke_module()

    for argv in ([], ["procurerag-api:ci-abc", "--url", "https://procurerag-api.example.invalid"]):
        try:
            smoke.main(argv)
        except SystemExit as error:
            assert error.code == 2  # argparse's usage error
        else:
            raise AssertionError(f"{argv} was accepted")
