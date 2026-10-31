"""Day 29, Block 5: the FREE proof of the deployed chain (no paid model call).

    python3 scripts/deployed_proof.py free --site https://<project>.vercel.app
    python3 scripts/deployed_proof.py watch-kill-switch --site https://<project>.vercel.app
    python3 scripts/deployed_proof.py spoof-check --site https://<project>.vercel.app

Three modes, all built so that nothing reaches the LLM:

``free``: one pass over the deployed chain.
  1. The portfolio pages load (``/``, ``/procurerag``, ``/about``).
  2. The chat's kill-switch state, read for free: a POST of ``{}`` to
     ``/api/chat``. The BFF reads the kill switch FIRST, then rejects the
     body. So 422 means "switch on" and 503 means "off, or the store/config
     is broken". The body is refused before admission: no quota is used, and
     nothing reaches Azure. The function region comes from the reply's
     ``x-vercel-id`` header.
  3. ``GET /api/chat/status``: the typed warm-up answer, its latency (this is
     the cold-start measurement when the replica was asleep) and
     ``Cache-Control: no-store``. This uses one of the day's 15 status checks.
  3b. Everything a browser downloads for ``/procurerag`` (the HTML, every
     script it loads, and the status answer) is searched for the NAMES of
     server-only settings and for the Azure API's host. Only names are
     printed, never a matched value.
  4. Only if ``PROCURERAG_API_URL`` (the Azure base URL) is in the
     environment: direct ``/health`` is 200 without any credential, and
     ``/query`` and ``/query/stream`` answer 401 to no token and to a wrong
     one, with a body that would be a 422 if it were read. The URL is never
     printed.

``watch-kill-switch``: measures flip-to-effect. It repeats the free probe
  of step 2 every second and stops at the first change (422 -> 503 or back).
  Start it, flip the switch in Upstash, note the time you pressed Enter on
  the SET command, and read the two timestamps it prints: the last request
  that saw the old state and the first one that saw the new state.

``spoof-check``: does Vercel really overwrite a forged client address? It
  sends up to 4 status checks, each with a DIFFERENT forged
  ``x-vercel-forwarded-for``. If the forged values were trusted, each would be
  a new client with its own 3-a-day status allowance, and none would be
  refused. If Vercel overwrites them, all 4 come from ONE client (you), and
  the 4th at the latest is ``busy``. Run it with the chat switched on, on a
  day when you have not used your 3 status checks yet. It wakes the replica
  (``/health`` only, free).

What this does NOT do: the paid launch smoke (``scripts/chat_smoke.py``),
quota exhaustion (``busy`` for questions needs the counters set by hand, see
docs/day-29-runbook.md) or log inspection (Vercel and Azure dashboards).

Standard library only, like the other scripts. Exit code 0: every check
passed; 1: a check failed; 2: usage error.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Above the BFF's 90 s wait for a cold /health and the routes' 100 s limit.
REQUEST_TIMEOUT_SECONDS = 110

PAGES = ("/", "/procurerag", "/about")
QUERY_ROUTES = ("/query", "/query/stream")
WRONG_TOKEN = "deliberately-wrong-token"
# A body the API's schema would reject with 422, IF it were parsed. A 401
# instead shows the token is checked before the body is read.
UNPARSEABLE_IF_READ = b'{"query": 7}'
SERVICE_STATES = ("ready", "waking", "busy", "unavailable")
STATUS_CLIENT_DAILY_CAP = 3  # lib/chat/admission.ts, STATUS_CLIENT_DAILY_CAP

# Server-only setting names that must never appear in anything a browser
# downloads (the portfolio's tests/build-artifacts.spec.ts checks the same
# list on the local build; this checks the DEPLOYED one).
FORBIDDEN_IN_BROWSER = (
    "PROCURERAG_SERVICE_TOKEN",
    "PROCURERAG_API_URL",
    "PROCURERAG_CLIENT_HASH_SECRET",
    "PROCURERAG_BUDGET_DOMAIN",
    "UPSTASH_REDIS_REST",
    "KV_REST_API",
    "OPENROUTER_API_KEY",
    "NEXT_PUBLIC_",
)


# ---------------------------------------------------------------------------
# HTTP: one helper that never raises and never follows a redirect.
# ---------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is reported as what it is, never followed (it could carry a token elsewhere)."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def request(url, method="GET", body=None, headers=None):
    """Send one request. Returns ``(status, headers, body_bytes, seconds)``; status None if no HTTP answer."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    started = time.monotonic()
    try:
        with _OPENER.open(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, response.headers, response.read(), time.monotonic() - started
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read(), time.monotonic() - started
    except (urllib.error.URLError, OSError) as error:
        return None, {}, f"{type(error).__name__}".encode(), time.monotonic() - started


def json_state(body):
    """The ``state`` field of a JSON body, or None."""
    try:
        value = json.loads(body)
    except (ValueError, TypeError):
        return None
    return value.get("state") if isinstance(value, dict) else None


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Pure interpretations (unit-tested without a network).
# ---------------------------------------------------------------------------


def function_region(x_vercel_id):
    """The region a Vercel FUNCTION ran in, from ``x-vercel-id``; None for a static or missing answer.

    The header lists the regions the request passed through, then an id:
    ``<edge>::<function region>::<id>`` for a function. Only the function
    region is returned: the edge region is near the CALLER, i.e. a location
    hint about whoever ran this, and is never printed.
    """
    parts = (x_vercel_id or "").split("::")
    return parts[-2] if len(parts) >= 3 else None


def kill_switch_state(status):
    """What a POST of ``{}`` to /api/chat says about the kill switch (see the module docstring)."""
    if status == 422:
        return "on"
    if status == 503:
        return "off (or store/config unavailable)"
    return f"unexpected HTTP {status}"


def browser_leaks(texts, api_host):
    """The NAMES of what leaked into browser-visible text: setting names, or "the Azure API host". Never values."""
    found = set()
    for text in texts:
        found.update(name for name in FORBIDDEN_IN_BROWSER if name in text)
        if api_host and api_host in text:
            found.add("the Azure API host")
    return sorted(found)


def spoof_verdict(states):
    """Read the spoof-check's status states (in order). Returns ``(passed, explanation)``."""
    if not states:
        return False, "no request was answered"
    if states[0] == "busy":
        return False, "inconclusive: the first check was already busy (today's status limit is used up)"
    if "unavailable" in states:
        return False, "inconclusive: the chat is switched off or the store is unavailable"
    if "busy" in states:
        return True, f"forged addresses were ignored: busy after {states.index('busy')} check(s) from one real client"
    return False, f"FAIL: {len(states)} checks with forged addresses were all admitted as different clients"


# ---------------------------------------------------------------------------
# The modes.
# ---------------------------------------------------------------------------


def check(failures, ok, label, detail=""):
    print(f"[{'ok' if ok else 'FAIL'}] {label}{(': ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def chat_probe(site):
    """POST {} to /api/chat: free (refused before admission). Returns (status, headers, seconds)."""
    status, headers, _body, seconds = request(
        f"{site}/api/chat", "POST", b"{}", {"Content-Type": "application/json"}
    )
    return status, headers, seconds


def run_free(site, api_url):
    failures = []

    for path in PAGES:
        status, headers, _body, seconds = request(f"{site}{path}")
        is_html = "text/html" in (headers.get("content-type", "") if headers else "")
        check(failures, status == 200 and is_html, f"page {path}", f"HTTP {status} in {seconds:.2f} s")

    status, headers, seconds = chat_probe(site)
    check(failures, status in (422, 503), "kill switch (POST {} to /api/chat, free)", kill_switch_state(status))
    region = function_region(headers.get("x-vercel-id") if headers else None)
    check(failures, region == "dub1", "function region", str(region))

    status, headers, status_body, seconds = request(f"{site}/api/chat/status")
    state = json_state(status_body)
    no_store = (headers.get("cache-control", "") if headers else "") == "no-store"
    check(failures, state in SERVICE_STATES and no_store, "status route", f"HTTP {status}, state {state}, {seconds:.1f} s")

    _status, _headers, html, _seconds = request(f"{site}/procurerag")
    page = html.decode("utf-8", errors="replace")
    script_urls = [urllib.parse.urljoin(f"{site}/", src) for src in re.findall(r'<script[^>]+src="([^"]+)"', page)]
    texts = [page, status_body.decode("utf-8", errors="replace")]
    texts += [request(url)[2].decode("utf-8", errors="replace") for url in script_urls]
    leaks = browser_leaks(texts, urllib.parse.urlparse(api_url).hostname if api_url else None)
    check(failures, bool(script_urls) and not leaks, "browser-visible files hold no server-only value",
          f"{len(script_urls)} scripts searched" + (f"; found: {', '.join(leaks)}" if leaks else ""))

    if not api_url:
        print("[skip] direct Azure checks: PROCURERAG_API_URL is not set")
    else:
        status, _headers, body, seconds = request(f"{api_url}/health")
        try:
            health = json.loads(body)
        except ValueError:
            health = {}
        check(
            failures, status == 200 and health.get("status") == "ok", "Azure /health without credentials",
            f"HTTP {status} in {seconds:.1f} s, live_llm={health.get('live_llm')}",
        )
        for route in QUERY_ROUTES:
            for label, extra in (("no token", {}), ("wrong token", {"Authorization": f"Bearer {WRONG_TOKEN}"})):
                status, _headers, _body, _seconds = request(
                    f"{api_url}{route}", "POST", UNPARSEABLE_IF_READ, {"Content-Type": "application/json", **extra}
                )
                check(failures, status == 401, f"Azure {route} with {label} is 401 before the body is read", f"HTTP {status}")

    print(f"\n{len(failures)} failure(s)")
    return 1 if failures else 0


def run_watch(site, interval, max_seconds, probe=chat_probe, clock=utc_now, sleep=time.sleep, monotonic=time.monotonic):
    """Probe until the kill-switch state changes. Returns 0 on a change, 1 if none within ``max_seconds``."""
    status, _headers, _seconds = probe(site)
    first_state = kill_switch_state(status)
    last_old_at = clock()
    print(f"{last_old_at}  {first_state}  <- now flip the switch, and note the time you did")
    started = monotonic()
    while monotonic() - started < max_seconds:
        sleep(interval)
        status, _headers, _seconds = probe(site)
        state = kill_switch_state(status)
        at = clock()
        if state != first_state:
            print(f"{at}  {state}")
            print(f"\nlast request with the old state: {last_old_at}")
            print(f"first request with the new state: {at}")
            print("flip-to-effect <= (first new-state time) - (the time you ran the SET command)")
            return 0
        last_old_at = at
    print(f"no change within {max_seconds} s")
    return 1


def run_spoof_check(site):
    states = []
    for n in range(1, STATUS_CLIENT_DAILY_CAP + 2):
        forged = f"198.51.100.{n}"  # RFC 5737 documentation range: never a real client
        headers = {"x-vercel-forwarded-for": forged, "x-forwarded-for": forged, "x-real-ip": forged}
        status, _headers, body, seconds = request(f"{site}/api/chat/status", headers=headers)
        state = json_state(body)
        print(f"check {n} (forged address #{n}): HTTP {status}, state {state}, {seconds:.1f} s")
        states.append(state)
        if state == "busy":
            break
    passed, explanation = spoof_verdict(states)
    print(f"\n[{'ok' if passed else 'FAIL'}] {explanation}")
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Free (no paid call) proof of the deployed ProcureRAG demo chain.")
    parser.add_argument("mode", choices=["free", "watch-kill-switch", "spoof-check"])
    parser.add_argument("--site", required=True, help="the Vercel deployment's base URL, https://...")
    parser.add_argument("--interval", type=float, default=1.0, help="watch-kill-switch: seconds between probes")
    parser.add_argument("--max-seconds", type=float, default=600, help="watch-kill-switch: give up after this long")
    args = parser.parse_args(argv)

    site = args.site.rstrip("/")
    if not site.startswith("https://"):
        parser.error("--site must be an https:// URL")
    if args.mode == "free":
        api_url = os.environ.get("PROCURERAG_API_URL", "").strip().rstrip("/")
        if api_url and not api_url.startswith("https://"):
            parser.error("PROCURERAG_API_URL must be an https:// URL")
        return run_free(site, api_url)
    if args.mode == "watch-kill-switch":
        return run_watch(site, args.interval, args.max_seconds)
    return run_spoof_check(site)


if __name__ == "__main__":
    sys.exit(main())
