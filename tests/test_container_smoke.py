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


def test_a_query_without_the_service_token_must_be_refused_with_401():
    smoke = _load_container_smoke_module()

    assert smoke.check_unauthenticated_refused(401, {"detail": "missing or invalid service credential"}) == []
    assert smoke.check_unauthenticated_refused(200, Q001_ANSWER) != []  # the image runs queries for anyone
    assert smoke.check_unauthenticated_refused(None, {"_error": "ConnectionResetError"}) != []


def test_image_mode_hands_the_token_to_docker_by_name_never_on_the_command_line(monkeypatch):
    """`--env NAME` without `=value` makes Docker copy the value from the
    `docker` process's own environment. So the token is in that environment,
    and in no command-line argument."""
    smoke = _load_container_smoke_module()
    calls = []
    monkeypatch.setattr(smoke, "docker", lambda *args, env=None: calls.append((args, env)) or "container-id")

    smoke.start_container("procurerag-api:ci-abc", 8000, "token-for-this-run-only")

    args, env = calls[0]
    assert ("--env", "PROCURERAG_SERVICE_TOKEN") in zip(args, args[1:])
    assert all("token-for-this-run-only" not in arg for arg in args)
    assert env["PROCURERAG_SERVICE_TOKEN"] == "token-for-this-run-only"


def test_health_requires_live_llm_false():
    smoke = _load_container_smoke_module()

    assert smoke.check_health({"status": "ok", "live_llm": False}) == []
    assert smoke.check_health({"status": "ok", "live_llm": True}) != []


def test_health_requires_live_llm_true_only_when_a_live_revision_is_expected():
    """Day 29: `--expect-live-llm` flips the expectation; it never accepts either answer."""
    smoke = _load_container_smoke_module()

    assert smoke.check_health({"status": "ok", "live_llm": True}, expect_live_llm=True) == []
    assert smoke.check_health({"status": "ok", "live_llm": False}, expect_live_llm=True) != []
    assert smoke.check_health({"status": "ok"}, expect_live_llm=True) != []  # missing is not true


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


DEPLOYMENT_TOKEN = "url-mode-test-token"


def _serve_measured_answers(monkeypatch, smoke, health=None):
    """Make the script's two HTTP helpers return the measured answers, and forbid docker.

    The fake API enforces the service token like the real one (Day 28): no
    token, or the wrong one, is a 401. The deployment's token is set in the
    environment, where URL mode reads it.
    """

    def no_docker(*args, **kwargs):
        raise AssertionError("URL mode must not call docker")

    sent = []

    def fake_post(url, body, token, timeout=60):
        route = "/query/stream" if url.endswith("/query/stream") else "/query"
        sent.append((route, body.get("query_id"), token))
        if token != DEPLOYMENT_TOKEN:
            return 401, {"detail": "missing or invalid service credential"}
        answers = {"Q001": (200, Q001_ANSWER), "Q091": (200, Q091_PENDING)}
        return answers.get(body.get("query_id"), (200, OFF_TOPIC_BLOCKED))

    monkeypatch.setattr(smoke.subprocess, "run", no_docker)
    monkeypatch.setattr(smoke, "http_get_json", lambda url, timeout=5: (200, health or {"status": "ok", "live_llm": False}))
    monkeypatch.setattr(smoke, "http_post_json", fake_post)
    monkeypatch.setenv(smoke.SERVICE_TOKEN_ENV_VAR, DEPLOYMENT_TOKEN)
    return sent


def test_url_mode_passes_on_the_measured_answers_without_touching_docker(monkeypatch, capsys):
    smoke = _load_container_smoke_module()
    _serve_measured_answers(monkeypatch, smoke)

    assert smoke.main(["--url", "https://procurerag-api.example.invalid/"]) == smoke.EXIT_PASSED
    output = capsys.readouterr().out
    assert "[skip] logs" in output
    assert "example.invalid" not in output  # the deployment's URL is never printed
    assert DEPLOYMENT_TOKEN not in output  # nor its token


def test_url_mode_without_the_deployment_token_is_a_usage_error(monkeypatch, capsys):
    """URL mode cannot invent a running deployment's token. Without it, the
    script stops before any request, and names the variable it needs."""
    smoke = _load_container_smoke_module()
    _serve_measured_answers(monkeypatch, smoke)
    monkeypatch.delenv(smoke.SERVICE_TOKEN_ENV_VAR)

    try:
        smoke.main(["--url", "https://procurerag-api.example.invalid"])
    except SystemExit as error:
        assert error.code == 2  # argparse's usage error
    else:
        raise AssertionError("URL mode ran without a token")
    assert "PROCURERAG_SERVICE_TOKEN" in capsys.readouterr().err


def test_url_mode_fails_when_the_deployed_revision_has_the_live_llm_on(monkeypatch):
    smoke = _load_container_smoke_module()
    _serve_measured_answers(monkeypatch, smoke, health={"status": "ok", "live_llm": True})

    assert smoke.main(["--url", "https://procurerag-api.example.invalid"]) == smoke.EXIT_CONTRACT_FAILED


def test_both_query_routes_are_probed_with_no_token_and_a_wrong_token(monkeypatch):
    """Day 29: four free refusals, `/query` and `/query/stream`, none with the real token."""
    smoke = _load_container_smoke_module()
    sent = _serve_measured_answers(monkeypatch, smoke)

    assert smoke.main(["--url", "https://procurerag-api.example.invalid"]) == smoke.EXIT_PASSED
    refusals = [(route, token) for route, _query_id, token in sent if token != DEPLOYMENT_TOKEN]
    assert sorted(refusals, key=str) == sorted(
        [("/query", None), ("/query", smoke.WRONG_TOKEN), ("/query/stream", None), ("/query/stream", smoke.WRONG_TOKEN)],
        key=str,
    )


def test_a_wrong_token_that_was_accepted_fails_the_smoke():
    smoke = _load_container_smoke_module()

    # A deployment that parsed the body first would answer 422, not 401.
    assert smoke.check_unauthenticated_refused(422, {"detail": "query: input should be a string"}) != []


def test_url_mode_against_a_live_revision_makes_no_paid_call(monkeypatch, capsys):
    """With `--expect-live-llm`, Q001 (a model call with the LLM on) is never
    sent with the real token. Q091 and the off-topic question stop before any
    model, so they still run."""
    smoke = _load_container_smoke_module()
    sent = _serve_measured_answers(monkeypatch, smoke, health={"status": "ok", "live_llm": True})

    assert smoke.main(["--url", "https://procurerag-api.example.invalid", "--expect-live-llm"]) == smoke.EXIT_PASSED
    authorized_query_ids = [query_id for _route, query_id, token in sent if token == DEPLOYMENT_TOKEN]
    assert "Q001" not in authorized_query_ids
    assert "Q091" in authorized_query_ids
    assert "[skip] Q001" in capsys.readouterr().out


def test_expect_live_llm_is_refused_in_image_mode():
    smoke = _load_container_smoke_module()

    try:
        smoke.main(["procurerag-api:ci-abc", "--expect-live-llm"])
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("image mode accepted --expect-live-llm")


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
