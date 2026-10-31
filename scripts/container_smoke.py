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
refuses a query without the service token (Day 28), runs local retrieval for
a labeled question, stops at the approval boundary, blocks an off-topic
question, and logs no traceback or secret-like text. Since Day 29 it also
refuses both query routes (`/query`, `/query/stream`) with a WRONG token, and
before reading the body. It says nothing about
answer quality, and nothing about any other image: it must be run against the
exact tag the workflow just built.

**The service token (Day 28).** The API refuses to start without
`PROCURERAG_SERVICE_TOKEN`, and refuses every query without it. In image mode
the script makes a fresh random token for this one run and hands it to the
container by NAME only (`--env PROCURERAG_SERVICE_TOKEN`, with the value in
the `docker` command's own environment), so the value never appears on a
command line, in `ps`, or in this script's output.

**Second mode: a deployment that is already running** (the deploy workflow's
last step, after Azure has switched to the new revision):

    PROCURERAG_SERVICE_TOKEN=<the deployment's token> python3 scripts/container_smoke.py --url https://<app-fqdn>

The same HTTP probes, sent to that URL, with the token read from this
process's environment (it must match the deployment's). Nothing is started
or removed, so no `docker` is needed. There is no log probe in this mode:
the logs live on the platform, not in a local container. The deploy workflow
checks the logs of the same image in its local container smoke, before the
image is pushed, and (Day 29) passes the deployment's token from its
`production` environment secret.

**A revision with the live LLM on (Day 29):**

    PROCURERAG_SERVICE_TOKEN=... python3 scripts/container_smoke.py --url https://<app-fqdn> --expect-live-llm

`/health` must then report `live_llm: true`, and the Q001 retrieval probe is
SKIPPED: with the LLM on, Q001 would be answered by the model, i.e. a paid
call, and a smoke must never spend money. Every other probe stays, because
none of them reaches the model: the credential refusals stop before the
body is read, Q091 stops at the approval boundary, and the off-topic question
is blocked by the input guard. Q001's retrieval was already proven on the
same image in image mode, before the push.

**Exit codes** (both modes).

- `0`: every probe passed.
- `1`: the service is healthy, but an endpoint or log contract differs
  (API smoke failure).
- `2`: the service never became healthy: the container exited, or `/health`
  did not answer within the budget (packaging/startup failure).

In image mode, the container is ALWAYS removed at the end (`finally`), even
when a probe fails or the script is interrupted, so a failed CI run leaves
nothing behind.
"""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

CONTAINER_NAME = "procurerag-smoke"

# The API's service-token setting (Day 28, `api.SERVICE_TOKEN_ENV_VAR`).
SERVICE_TOKEN_ENV_VAR = "PROCURERAG_SERVICE_TOKEN"

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

# Day 29: the credential-refusal probes. A wrong token is sent with a body the
# schema would reject (422) IF it were parsed: getting 401 instead shows that
# the token is checked before the body is even read (Day 28's middleware).
WRONG_TOKEN = "not-the-deployment-token"
UNPARSEABLE_IF_READ = {"query": 7}
QUERY_ROUTES = ("/query", "/query/stream")

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


def docker(*args, env=None):
    """Run one `docker` command and return its stdout. Raises if docker fails.

    `env`: the environment of the `docker` process itself (None: this
    script's own). `start_container` uses it to hand over the token.
    """
    completed = subprocess.run(["docker", *args], capture_output=True, text=True, check=True, env=env)
    return completed.stdout.strip()


def start_container(image, port, service_token):
    """Start the image in the background, published on the host loopback only.

    No `--rm`: if the container crashes during startup, its logs must still be
    readable to explain why. `remove_container` deletes it at the end instead.

    The service token goes in by NAME: `--env PROCURERAG_SERVICE_TOKEN` with
    no `=value` tells Docker to copy the value from the `docker` command's
    own environment. So the value is never part of the command line, which
    other processes on the machine (`ps`) and error messages can show.
    """
    env_flags = [flag for name, value in RUN_ENV.items() for flag in ("--env", f"{name}={value}")]
    docker(
        "run", "--detach", "--name", CONTAINER_NAME,
        "--publish", f"127.0.0.1:{port}:8000",
        "--cpus", CPU_LIMIT, "--memory", MEMORY_LIMIT,
        *env_flags,
        "--env", SERVICE_TOKEN_ENV_VAR,
        image,
        env={**os.environ, SERVICE_TOKEN_ENV_VAR: service_token},
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


def http_post_json(url, body, token, timeout=60):
    """POST a JSON body and return `(status_code, body_dict)`. Never raises.

    `token`: the service token, sent as `Authorization: Bearer <token>`.
    None sends no credential at all (the refusal probe).

    - 2xx: the parsed answer.
    - 4xx/5xx: urllib raises `HTTPError`, which still carries the status and
      body, so they are returned like any other answer.
    - No HTTP answer at all (the server died, the connection was reset, a
      timeout): status `None` and the error. Every probe treats a status
      other than 200 as a failure, so this turns red instead of crashing the
      script before the logs are printed.
    """
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _parse_body(response.read())
    except urllib.error.HTTPError as error:
        return error.code, _parse_body(error.read())
    except (urllib.error.URLError, OSError) as error:  # OSError covers resets and timeouts
        return None, {"_error": f"{type(error).__name__}: {error}"}


def wait_for_health(base_url, budget_seconds, local_container=True):
    """Poll `/health` until it answers 200, or fail fast if the container dies.

    Returns `(seconds_until_healthy, health_json)`. While the models load,
    Uvicorn is not accepting connections yet, so a refused connection is the
    expected "still starting" answer, not a failure.

    `local_container=False` (URL mode): there is no local container to watch,
    so only the time budget can end the wait. Behind Azure's ingress, a
    scaled-to-zero app holds the first request while a replica starts, so a
    timed-out attempt is also "still starting".
    """
    started = time.monotonic()
    while time.monotonic() - started < budget_seconds:
        if local_container and not container_is_running():
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


def check_health(health, expect_live_llm=False):
    """`/health` must say "ok", and `live_llm` must be exactly what this run expects.

    Image mode always expects false: no provider may be wired in. URL mode
    expects true only with `--expect-live-llm`, i.e. for a revision deployed
    on purpose with paid generation on.
    """
    failures = []
    if health.get("status") != "ok":
        failures.append(f"/health status is {health.get('status')!r}, expected 'ok'")
    if health.get("live_llm") is not expect_live_llm:
        failures.append(f"/health live_llm is {health.get('live_llm')!r}, expected {str(expect_live_llm).lower()}")
    return failures


def check_unauthenticated_refused(status_code, body):
    """A query with no (or a wrong) service token: the API must refuse it with 401 (Day 28), before running anything."""
    if status_code != 401:
        return [f"a query without a valid service token returned HTTP {status_code}, expected 401: {body}"]
    return []


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


def credential_refusal_probes(base_url):
    """Both query routes, with no token and with a wrong one: four 401s, all free.

    No refused request reaches retrieval or a model, so these are safe to send
    to any deployment, live LLM or not.
    """
    probes = []
    for route in QUERY_ROUTES:
        url = f"{base_url}{route}"
        probes.append((f"{route} without a token", check_unauthenticated_refused(*http_post_json(url, Q001_REQUEST, None))))
        probes.append((
            f"{route} with a wrong token (and a body that would be a 422)",
            check_unauthenticated_refused(*http_post_json(url, UNPARSEABLE_IF_READ, WRONG_TOKEN)),
        ))
    return probes


def http_probes(base_url, health, token, expect_live_llm=False):
    """The HTTP contract, identical for a local container and a deployed revision.

    The refusal probes send no token or a wrong one; every other query sends
    `token`. With `expect_live_llm`, the Q001 probe is left out: it would be a
    paid model call (see the module docstring).
    """
    query_url = f"{base_url}/query"
    probes = [("/health contract", check_health(health, expect_live_llm)), *credential_refusal_probes(base_url)]
    if not expect_live_llm:
        probes.append(("Q001 labeled, local retrieval", check_q001(*http_post_json(query_url, Q001_REQUEST, token))))
    probes.append(("Q091 without a decision", check_q091_pending(*http_post_json(query_url, Q091_REQUEST, token))))
    probes.append(("off-topic question", check_off_topic_blocked(*http_post_json(query_url, OFF_TOPIC_REQUEST, token))))
    return probes


def print_probes(probes):
    """Print one [ok]/[FAIL] line per probe, with its failures. Returns True if any probe failed."""
    failed = False
    for name, failures in probes:
        print(f"[{'FAIL' if failures else 'ok'}] {name}")
        for failure in failures:
            print(f"       - {failure}")
        failed = failed or bool(failures)
    return failed


def smoke_running_service(base_url, health_budget, token, expect_live_llm=False):
    """URL mode: the HTTP probes against a service someone else started (e.g. an Azure revision).

    The URL itself is never printed: in a public CI log it would advertise
    the endpoint, which wakes (and bills) a scaled-to-zero replica even when
    it refuses the request. (The deploy workflow also masks it.) The token
    is never printed either.
    """
    try:
        seconds, health = wait_for_health(base_url, health_budget, local_container=False)
    except StartupFailure as error:
        print(f"STARTUP FAILURE: {error}")
        print(f"\nexit code: {EXIT_STARTUP_FAILED}")
        return EXIT_STARTUP_FAILED
    print(f"[ok] /health answered after {seconds:.1f} s: {health}")

    failed = print_probes(http_probes(base_url, health, token, expect_live_llm))
    if expect_live_llm:
        print("[skip] Q001 labeled, local retrieval: a PAID call with the live LLM on (proven in image mode before the push)")
    print("[skip] logs: not readable over HTTP (the image's own logs are checked in image mode)")

    print(f"\nexit code: {EXIT_CONTRACT_FAILED if failed else EXIT_PASSED}")
    return EXIT_CONTRACT_FAILED if failed else EXIT_PASSED


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gate the HTTP/log contract of one ProcureRAG image or deployment.")
    parser.add_argument("image", nargs="?", help="the exact image tag to start and test, e.g. procurerag-api:ci-<sha>")
    parser.add_argument("--url", help="instead of an image: the base URL of a running deployment, e.g. https://<fqdn>")
    parser.add_argument("--port", type=int, default=8000, help="host loopback port to publish (default 8000)")
    parser.add_argument(
        "--health-budget", type=int, default=DEFAULT_HEALTH_BUDGET_SECONDS,
        help=f"seconds to wait for /health (default {DEFAULT_HEALTH_BUDGET_SECONDS})",
    )
    parser.add_argument(
        "--expect-live-llm", action="store_true",
        help="URL mode only: the revision was deployed with PROCURERAG_LIVE_LLM=1 (skips the paid Q001 probe)",
    )
    args = parser.parse_args(argv)
    # Exactly one target: an image to start, or a URL that is already serving.
    if (args.image is None) == (args.url is None):
        parser.error("give either an IMAGE to start, or --url of a running deployment (not both)")
    if args.expect_live_llm and not args.url:
        parser.error("--expect-live-llm applies to --url only: image mode never wires in a provider")
    if args.url:
        # A running deployment has its own token; this script cannot invent
        # it. The error names the variable, never a value.
        token = os.environ.get(SERVICE_TOKEN_ENV_VAR, "")
        if not token.strip():
            parser.error(f"--url needs the deployment's service token in the environment variable {SERVICE_TOKEN_ENV_VAR}")
        return smoke_running_service(args.url.rstrip("/"), args.health_budget, token, args.expect_live_llm)

    # Image mode: a fresh token for this one container, never printed.
    token = secrets.token_urlsafe(32)
    base_url = f"http://127.0.0.1:{args.port}"
    remove_container()  # a leftover container from an interrupted run would block the name/port
    try:
        # Startup: `docker run` itself can fail (e.g. the tag was never
        # built), or the server can die or hang while loading. All of these
        # are packaging/startup failures, reported with the log tail.
        try:
            start_container(args.image, args.port, token)
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

        probes = http_probes(base_url, health, token)
        # The logs are read AFTER the requests, so they include every request's handling.
        probes.append(("logs", check_logs(container_logs())))

        failed = print_probes(probes)

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
