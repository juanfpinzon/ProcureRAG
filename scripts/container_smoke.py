"""Day 24: smoke-test ONE built ProcureRAG image, the way CI gates it.

**What this is.** The executable version of `docs/docker-runbook.md` steps 4-7
(run, wait for health, smoke, logs, clean up). The runbook shows the same
requests as `curl` commands for a human to read. This script sends exactly
those requests and ASSERTS the answers, so the GitHub Actions job and a person
at a terminal check the same contract. Change one, change the other.

    python3 scripts/container_smoke.py procurerag-api:ci-<sha>

It uses only the Python standard library (plus the `docker` CLI), so the
Docker CI job needs no `uv sync` just to run it.

**What it proves, and what it does not.** That THIS image starts with no key
and no network access to the Hub, loads its baked models, answers `/health`,
runs local retrieval for a labeled question, stops at the approval boundary,
blocks an off-topic question, and logs no traceback or secret-like text. It
says nothing about answer quality, and nothing about any other image: it must
be run against the exact tag the workflow just built.

**Exit codes.**

- `0`: every probe passed.
- `1`: the container is healthy, but an endpoint or log contract differs
  (API smoke failure).
- `2`: the container never became healthy: it exited, or `/health` did not
  answer within the budget (packaging/startup failure).

The container is ALWAYS removed at the end (`finally`), even when a probe
fails or the script is interrupted, so a failed CI run leaves nothing behind.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

CONTAINER_NAME = "procurerag-smoke"

# The runtime contract from `docs/docker-runbook.md` ("Runtime configuration"),
# passed explicitly even where the image already sets the same default, so the
# command itself shows the configuration under test. `OMP_NUM_THREADS=1`
# bounds the model's CPU threads, the setting Day 24's kickoff needed on the
# Hermes VM. No API key is passed, and none may be needed.
RUN_ENV = {
    "PROCURERAG_LIVE_LLM": "0",
    "LANGSMITH_TRACING": "false",
    "LANGSMITH_TRACING_V2": "false",
    "HF_HUB_OFFLINE": "1",
    "OMP_NUM_THREADS": "1",
}

# One CPU and 2 GiB: close to the Day 23 Azure Container Apps replica, so a
# memory or startup regression shows up here and not first in the cloud.
CPU_LIMIT = "1"
MEMORY_LIMIT = "2g"

# Measured cold `/health` was 59 s on Azure (Day 23) and 51 s on the Hermes
# VM. The budget is well above both, because a fixed short sleep would turn a
# slow-but-healthy start into a false failure. Polling returns as soon as the
# server is ready, so a fast start costs nothing extra.
DEFAULT_HEALTH_BUDGET_SECONDS = 240
POLL_INTERVAL_SECONDS = 2

# The exact request bodies from `docs/docker-runbook.md` step 5.
Q001_REQUEST = {"query": "What approval is required for a EUR 60,000 purchase order?", "role": "buyer", "query_id": "Q001"}
Q091_REQUEST = {
    "query": "What approvals and security evidence do I need for a EUR 120,000 SaaS renewal?",
    "role": "buyer",
    "query_id": "Q091",
}
OFF_TOPIC_REQUEST = {"query": "What is the capital of France?", "role": "buyer"}

# The runbook's step 6 pattern for "secret-like text" in the logs.
SECRET_LIKE = re.compile(r"api_key|token|secret|sk-or|lsv2_", re.IGNORECASE)

EXIT_PASSED = 0
EXIT_CONTRACT_FAILED = 1
EXIT_STARTUP_FAILED = 2


class StartupFailure(Exception):
    """The container exited, or `/health` never answered within the budget."""


# ---------------------------------------------------------------------------
# Docker and HTTP helpers.
# ---------------------------------------------------------------------------


def docker(*args):
    """Run one `docker` command and return its stdout. Raises if docker fails."""
    completed = subprocess.run(["docker", *args], capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def start_container(image, port):
    """Start the image in the background, published on the host loopback only.

    No `--rm`: if the container crashes during startup, its logs must still be
    readable to explain why. `remove_container` deletes it at the end instead.
    """
    env_flags = [flag for name, value in RUN_ENV.items() for flag in ("--env", f"{name}={value}")]
    docker(
        "run", "--detach", "--name", CONTAINER_NAME,
        "--publish", f"127.0.0.1:{port}:8000",
        "--cpus", CPU_LIMIT, "--memory", MEMORY_LIMIT,
        *env_flags,
        image,
    )


def container_exists():
    return subprocess.run(["docker", "inspect", CONTAINER_NAME], capture_output=True).returncode == 0


def container_is_running():
    try:
        return docker("inspect", "--format", "{{.State.Running}}", CONTAINER_NAME) == "true"
    except subprocess.CalledProcessError:
        return False  # the container no longer exists


def container_logs(tail=None):
    """The container's logs. Uvicorn writes to stderr, so stdout and stderr are both read."""
    tail_flags = ["--tail", str(tail)] if tail else []
    completed = subprocess.run(["docker", "logs", *tail_flags, CONTAINER_NAME], capture_output=True, text=True)
    return completed.stdout + completed.stderr


def redacted(logs):
    """The logs safe to print in CI: every secret-like line is replaced by a marker.

    Used whenever log lines are shown for debugging, so the log check below
    and the debugging output follow the same rule: a line that might hold a
    key is never printed.
    """
    return "\n".join(
        "[line hidden: secret-like keyword]" if SECRET_LIKE.search(line) else line for line in logs.splitlines()
    )


def http_get_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, json.load(response)


def _parse_body(raw_bytes):
    """JSON if the body is JSON. Otherwise the start of the raw text, e.g. a plain "Internal Server Error"."""
    text = raw_bytes.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text[:300]}


def http_post_json(url, body, timeout=60):
    """POST a JSON body and return `(status_code, body_dict)`. Never raises.

    - 2xx: the parsed answer.
    - 4xx/5xx: urllib raises `HTTPError`, which still carries the status and
      body, so they are returned like any other answer.
    - No HTTP answer at all (the server died, the connection was reset, a
      timeout): status `None` and the error. Every probe treats a status
      other than 200 as a failure, so this turns red instead of crashing the
      script before the logs are printed.
    """
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _parse_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _parse_body(error.read())
    except (urllib.error.URLError, OSError) as error:  # OSError covers resets and timeouts
        return None, {"_error": f"{type(error).__name__}: {error}"}


def wait_for_health(base_url, budget_seconds):
    """Poll `/health` until it answers 200, or fail fast if the container dies.

    Returns `(seconds_until_healthy, health_json)`. While the models load,
    Uvicorn is not accepting connections yet, so a refused connection is the
    expected "still starting" answer, not a failure.
    """
    started = time.monotonic()
    while time.monotonic() - started < budget_seconds:
        if not container_is_running():
            raise StartupFailure("the container exited before /health answered")
        try:
            status, body = http_get_json(f"{base_url}/health")
            if status == 200:
                return time.monotonic() - started, body
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass  # not listening yet
        time.sleep(POLL_INTERVAL_SECONDS)
    raise StartupFailure(f"/health did not answer 200 within {budget_seconds} s")


def remove_container():
    """Force-remove the container if it exists. Never raises: this runs in `finally`."""
    subprocess.run(["docker", "rm", "--force", CONTAINER_NAME], capture_output=True, text=True)


# ---------------------------------------------------------------------------
# The probes. Each one returns a list of failure messages ([] = passed).
# ---------------------------------------------------------------------------


def check_health(health):
    failures = []
    if health.get("status") != "ok":
        failures.append(f"/health status is {health.get('status')!r}, expected 'ok'")
    if health.get("live_llm") is not False:
        failures.append(f"/health live_llm is {health.get('live_llm')!r}, expected false: no provider may be wired in")
    return failures


def check_q001(status_code, body):
    """A labeled question with complete evidence: local retrieval runs, no LLM.

    Five sources, as Day 22/23 measured, including POL-001, Q001's primary
    (grade-2) document. The EXACT chunk list is the model-backed CI lane's
    claim (`regression_suite.py --verify-retrieval`), not this smoke's.
    """
    if status_code != 200:
        return [f"Q001 returned HTTP {status_code}, expected 200: {body}"]
    failures = []
    doc_ids = sorted({source["doc_id"] for source in body.get("sources", [])})
    if body.get("status") != "not_generated":
        failures.append(f"Q001 status is {body.get('status')!r}, expected 'not_generated' (live LLM off)")
    if body.get("run_id") is None:
        failures.append("Q001 has no run_id, so the graph did not run")
    if len(body.get("sources", [])) != 5:
        failures.append(f"Q001 returned {len(body.get('sources', []))} sources, expected 5")
    if "POL-001" not in doc_ids:
        failures.append(f"Q001 sources {doc_ids} do not include its primary document POL-001")
    return failures


def check_q091_pending(status_code, body):
    """A question that may need the approval-gated second pass, sent with no decision.

    The API must stop BEFORE any retrieval: `pending_approval`, an approval
    request, no sources, and no `run_id` (the graph never ran).
    """
    if status_code != 200:
        return [f"Q091 returned HTTP {status_code}, expected 200: {body}"]
    failures = []
    if body.get("status") != "pending_approval":
        failures.append(f"Q091 status is {body.get('status')!r}, expected 'pending_approval'")
    if body.get("approval_request") is None:
        failures.append("Q091 has no approval_request")
    if body.get("sources"):
        failures.append(f"Q091 returned sources {body['sources']}, expected none before approval")
    if body.get("run_id") is not None:
        failures.append("Q091 has a run_id, so the graph ran before approval")
    return failures


def check_off_topic_blocked(status_code, body):
    """An off-topic question: the scope guard blocks it before retrieval."""
    if status_code != 200:
        return [f"off-topic request returned HTTP {status_code}, expected 200: {body}"]
    failures = []
    guards = [finding.get("guard") for finding in body.get("findings", [])]
    if body.get("status") != "blocked":
        failures.append(f"off-topic status is {body.get('status')!r}, expected 'blocked'")
    if "off_topic" not in guards:
        failures.append(f"off-topic findings {guards} do not include 'off_topic'")
    if body.get("run_id") is not None:
        failures.append("off-topic request has a run_id, so the graph ran")
    return failures


def check_logs(logs):
    """No traceback, and nothing that looks like a key, in the container's own logs.

    A secret-like line is never printed: if it held a real key, echoing it
    into a CI log would leak exactly what this check looks for. What IS
    printed is the matched keyword and the line number. The pattern is broad
    on purpose ("token" also matches a harmless "tokenizers" warning), so a
    false alarm has to be debuggable without seeing the line.
    """
    failures = []
    tracebacks = logs.count("Traceback")
    if tracebacks:
        failures.append(f"logs contain {tracebacks} traceback(s)")
    for line_number, line in enumerate(logs.splitlines(), start=1):
        match = SECRET_LIKE.search(line)
        if match:
            failures.append(f"log line {line_number} contains secret-like keyword {match.group(0)!r} (line not printed)")
    return failures


# ---------------------------------------------------------------------------
# The run.
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Start one ProcureRAG image and gate its HTTP/log contract.")
    parser.add_argument("image", help="the exact image tag to test, e.g. procurerag-api:ci-<sha>")
    parser.add_argument("--port", type=int, default=8000, help="host loopback port to publish (default 8000)")
    parser.add_argument(
        "--health-budget", type=int, default=DEFAULT_HEALTH_BUDGET_SECONDS,
        help=f"seconds to wait for /health (default {DEFAULT_HEALTH_BUDGET_SECONDS})",
    )
    args = parser.parse_args(argv)
    base_url = f"http://127.0.0.1:{args.port}"

    remove_container()  # a leftover container from an interrupted run would block the name/port
    try:
        # Startup: `docker run` itself can fail (e.g. the tag was never
        # built), or the server can die or hang while loading. All of these
        # are packaging/startup failures, reported with the log tail.
        try:
            start_container(args.image, args.port)
            print(f"started {args.image} as {CONTAINER_NAME} ({CPU_LIMIT} CPU, {MEMORY_LIMIT} memory, {RUN_ENV})")
            seconds, health = wait_for_health(base_url, args.health_budget)
        except (StartupFailure, subprocess.CalledProcessError) as error:
            detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else error
            print(f"STARTUP FAILURE: {detail}")
            if container_exists():
                print("Last container log lines:")
                print(redacted(container_logs(tail=30)))
            print(f"\nexit code: {EXIT_STARTUP_FAILED}")
            return EXIT_STARTUP_FAILED
        print(f"[ok] /health answered after {seconds:.1f} s: {health}")

        probes = [
            ("/health contract", check_health(health)),
            ("Q001 labeled, local retrieval", check_q001(*http_post_json(f"{base_url}/query", Q001_REQUEST))),
            ("Q091 without a decision", check_q091_pending(*http_post_json(f"{base_url}/query", Q091_REQUEST))),
            ("off-topic question", check_off_topic_blocked(*http_post_json(f"{base_url}/query", OFF_TOPIC_REQUEST))),
        ]
        # The logs are read AFTER the requests, so they include every request's handling.
        probes.append(("logs", check_logs(container_logs())))

        failed = False
        for name, failures in probes:
            print(f"[{'FAIL' if failures else 'ok'}] {name}")
            for failure in failures:
                print(f"       - {failure}")
            failed = failed or bool(failures)

        if failed:
            # The server's own traceback, if any, is in these lines, and the
            # `finally` below deletes the container, so this is the last
            # chance to show them.
            print("\nLast container log lines:")
            print(redacted(container_logs(tail=40)))

        print(f"\nexit code: {EXIT_CONTRACT_FAILED if failed else EXIT_PASSED}")
        return EXIT_CONTRACT_FAILED if failed else EXIT_PASSED
    finally:
        remove_container()
        print(f"cleanup: container {CONTAINER_NAME} removed")


if __name__ == "__main__":
    sys.exit(main())
