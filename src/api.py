"""Day 21 (Block 3A): a FastAPI service boundary around the Day 20 guarded graph.

**From script to service.** Days 16-20 run as scripts. A person runs a CLI
command and reads what it prints. That person is the OPERATOR, and the
operator is trusted: they pick the query ids, the approval decision, and the
flags. A service has CALLERS instead, and a caller is not trusted. So a
service needs an explicit contract at its edge:

- what a caller may send (`QueryRequest`): the question, the caller's role,
  an optional labeled `query_id`, and an optional reviewer decision;
- how often a caller may send it: past the rate limit, HTTP 429
  (`SlidingWindowRateLimiter`);
- what is refused before any retrieval runs: a malformed or too-long body
  (HTTP 422), an injection attempt, an off-topic question. That covers
  EVERY text the caller wrote, the reviewer decision's text included;
- what this caller is allowed to see: the caller's role against each
  document's `confidentiality` label (`ROLE_CLEARANCE`);
- what happens when the graph would need a human (`pending_approval`);
- what comes back (`QueryResponse`): a typed status, user-safe text, the
  sources, and the guard findings. Never the raw trace row.

The service does not make the RAG system smarter. It makes the contract
explicit, and enforces it on every request.

**Endpoints.**

    GET  /health        liveness: app name and version. Never touches the pipeline.
    POST /query         one request in, one JSON `QueryResponse` out.
    POST /query/stream  the same request, answered as Server-Sent Events:
                        progress events first, then the same `QueryResponse`
                        as the last event.

**One request, in order.** Each step can end the request, and each one runs
before the more expensive steps after it:

    JSON body
      -> [rate limit: has this client used up its requests?]  HTTP 429, nothing else runs
      -> [Pydantic: shape, lengths, role, decision]  ........ HTTP 422, the endpoint never runs
      -> [check_query_request: a labeled id, with ITS text?]  HTTP 422 otherwise
      -> [Day 20 input guard, on every caller text]  ........ injection -> "blocked"; PII is redacted
      -> [scope guard, on every text sent to retrieval]  .... off-topic -> "blocked"
      -> [approval boundary: may pause, but no decision?]  .. yes -> "pending_approval", nothing ran
      -> [Day 20 GuardedPipeline, on a role-filtered retriever]
      -> QueryResponse: status, user-safe text, sources, findings, caveats

**Two kinds of request: free text and labeled.** Gold labels (which
documents a question needs) describe ONE question's text. They are not a
setting that can be attached to any text. So the API keeps the two apart:

- free text (no `query_id`): the production path. No labels apply, so the
  graph cannot measure an evidence gap, and the response says the evidence
  is unchecked (`UNLABELED_CAVEAT`);
- labeled (`query_id` plus that question's exact text): it replays one of
  the 93 evaluation questions, with the labels that really describe it.
  Any other text with a labeled id is a 422 (`check_query_request`).

**Streaming: one pipeline, two transports.** `run_query_events` is the only
place the steps above are written. It is a generator that yields one event
per stage. `/query/stream` sends every event as it is produced. `/query`
runs the same generator and returns only the last event. So the two
endpoints cannot drift apart: the stream is the JSON response plus the
progress events that led to it.

**Why `def` and not `async def`.** FastAPI runs an `async def` endpoint ON
the event loop, the one thread that serves every connection. The pipeline is
synchronous, CPU-bound code (embedding, cross-encoder reranking). Called
from `async def`, it would freeze the whole server for every other caller
until it finished. FastAPI runs a plain `def` endpoint (and a plain `def`
generator for streaming) in a worker thread pool instead, so the event loop
stays free. `async def` only pays off when the work AWAITS something, such
as an async LLM or database client.

The live LLM call (when switched on, see below) is the one part that is NOT
CPU work: it is a network wait of a few seconds. In a worker thread that
wait is harmless, but it occupies the thread for the whole call. An async
LLM client would free the thread while waiting, which matters only at a
concurrency this local service does not have.

**The LLM is opt-in.** The served app calls the live LLM only when it is
started with the switch `PROCURERAG_LIVE_LLM=1`, set either on the command
line or as a line in `.env` (`make_llm_client`, `read_setting`). It uses the same
client as Day 19's `--generate`: OpenRouter, with structured output
(`GeneratedAnswer`), so a run can end `answered` or `model_declined`. Off
(the default), a complete-evidence run ends `not_generated`. Off is the
default because every call costs money (the default model, `openai/gpt-4o`,
is paid), and this service's rate limit is only a learning-grade one (see
"Honest limits"). That is the same reason every earlier day gated live
calls behind `--generate`.

**Honest limits.**

- The role is CALLER-ASSERTED. There is no authentication: anyone can send
  `"role": "buyer"`. Production takes the role from a verified identity
  (e.g. a signed token's claims), never from the request body. What IS real
  here is the enforcement: the filter, and the tests that prove it.
- Authorization is a POST-filter. Retrieval ranks every chunk and the filter
  then drops the ones this role may not see. So a requester's context can be
  smaller than `top_k`, and the ranking work for confidential chunks is
  still done. The production pattern is a PRE-filter: a metadata filter
  inside the index, so `top_k` is filled with chunks the caller may see.
- The graph's diagnosis still needs gold labels (Day 16-20's eval-time
  limit). Labels exist only for the 93 labeled questions, so every
  free-text request (the production path) runs with none: the graph cannot
  see an evidence gap, and the response says so in `caveats`.
- Approval is a stateless RE-SUBMISSION, not a resume. `pending_approval`
  is returned BEFORE any retrieval. The caller then sends the same request
  again, with a `decision`. A real review queue would pause the graph after
  pass 1, show the reviewer the measured gap, and resume the same run from a
  durable checkpointer (Day 18). The decision is also caller-asserted, like
  the role: nothing records WHO approved.
- The scope guard is a keyword allow-list (see `PROCUREMENT_TERMS`). It
  refuses a procurement question phrased without any listed term, and lets
  through an off-topic one that happens to contain one ("is a risky cost
  worth it?").
- The rate limit is learning-grade (`SlidingWindowRateLimiter`, OWASP
  LLM10). It lives in this one process's memory, so:
  - it resets on every restart;
  - with several Uvicorn workers, each counts on its own, and the real
    limit is the limit times the number of workers;
  - behind a proxy, every caller arrives from the proxy's address, so one
    busy caller would use up everyone's budget.
  The production version runs at the ingress (Day 22/23: container/Azure),
  or keeps its counts in a store every worker shares (e.g. Redis). It still
  matters here: with the live LLM on, every in-scope request with complete
  evidence is one paid call, and the limit caps how many one client can
  make. Keep the server on 127.0.0.1 regardless.
- Stream events mark STAGE boundaries the API controls: before the graph
  runs and after it finishes. `GuardedPipeline.run` is one blocking call, so
  the context/action/output findings arrive together, after the graph is
  done. Node-by-node progress would need `graph.stream()`, and token
  streaming would need a streaming LLM client.
- Trace rows are not persisted. Each run still builds and validates its
  Day 19 `AgentRunTrace`, but the API only returns that row's `run_id`, and
  the row itself is gone when the request ends. An audit trail needs the
  rows written somewhere durable (with the guard findings: a `schema_version`
  bump), which is a later day's job.
- Startup is not network-free. Loading the two models contacts the Hugging
  Face Hub (startup prints an "unauthenticated requests to the HF Hub"
  warning). With the models already cached, `HF_HUB_OFFLINE=1` loads both
  without the Hub (checked on 2026-10-14).
- An LLM failure is an HTTP 500, not a status. A provider timeout, an HTTP
  error, or a reply cut off into invalid JSON raises inside the request.
  `/query` answers 500. `/query/stream` has already sent "200 OK", so its
  stream just stops before the `result` event (tested). There is no retry
  and no fallback answer.
- Live answers are not evaluated here. A schema-valid, cited answer can
  still be wrong (Day 19's Band 4 answer passes every guard). Answer quality
  is still a separate eval problem.

**Running it locally** (bound to 127.0.0.1: reachable from this machine only).
The server answers once Uvicorn prints "Application startup complete", i.e.
after the models have loaded (about 12 s on 2026-10-14):

    # retrieval only, no LLM (free)
    LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false \\
        ./.venv/bin/python -m uvicorn api:app --app-dir src --host 127.0.0.1 --port 8000

    # with the live LLM (paid: one OpenRouter call per complete-evidence request)
    PROCURERAG_LIVE_LLM=1 LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false \\
        ./.venv/bin/python -m uvicorn api:app --app-dir src --host 127.0.0.1 --port 8000

If `.env` already has `PROCURERAG_LIVE_LLM="1"`, the first command ALSO
calls the live LLM, because the file is the fallback for the switch. For a
free run in that case, override it on the command line:
`PROCURERAG_LIVE_LLM=0 LANGSMITH_TRACING=false ...`. Check what a running
server actually built with `curl http://127.0.0.1:8000/health` (`live_llm`).

`--app-dir src` puts `src/` on `sys.path`, which is how `api` finds the
other modules (`agent_guardrails`, ...).

A script that sends many requests (say, all 93 labeled questions) will meet
the rate limit: past 30 requests a minute it gets HTTP 429, with a
`Retry-After` header saying how many seconds to wait before trying again.

Secrets: this module never calls `load_dotenv()`, so `.env` is never loaded
into the process environment. It reads exactly TWO values from `.env`, the
switch `PROCURERAG_LIVE_LLM` and (when the switch is on)
`OPENROUTER_API_KEY`, each only if the environment does not already have it
(`read_setting`). LangSmith therefore stays off unless your shell itself
exports the `LANGSMITH_*` variables. The two `=false` settings above make
sure of that.
"""

import math
import os
import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from dotenv import dotenv_values
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field, model_validator

from agent_control_plane import ALLOWED_DECISIONS, decision_error
from agent_graph import ROUTE_RECURSIVE_RETRIEVE, make_initial_state
from agent_guardrails import (
    BLOCKED_INPUT_MESSAGE,
    GuardedPipeline,
    GuardFinding,
    guard_user_query,
    may_pause_for_approval,
)
from agent_observability import STATUS_GAP_REPORT, ContractModel, ReviewerDecision
from generation import GeneratedAnswer, make_openrouter_client

APP_TITLE = "ProcureRAG API"
APP_VERSION = "0.1.0"  # the `[project] version` in pyproject.toml: change the two together

# ---------------------------------------------------------------------------
# The boundary's policy: how long a question may be, and who may see what.
# ---------------------------------------------------------------------------

# The longest of the 93 labeled queries is 97 characters (measured on
# `example_queries.jsonl`). 500 leaves room for a buyer who adds some context,
# and still refuses a pasted document. Length is also a cost lever (OWASP
# LLM10, unbounded consumption): every character is embedded and reranked,
# and later sent to an LLM.
MAX_QUERY_CHARS = 500

# A reviewer decision carries two more texts the caller writes (see
# `ApprovalDecision`). An edited `followup_query` is a second query sent to
# retrieval, so it gets the question's cap, `MAX_QUERY_CHARS`. A `message` is
# a short reason ("not worth a second pass"), never a document. It is copied
# into the trace row and shown back in the response, so it gets a smaller cap.
MAX_DECISION_MESSAGE_CHARS = 200

# Who the caller is, as far as this API knows. Two roles are enough to show
# the mechanism:
# - a "requester" is any employee who raises a purchase request;
# - a "buyer" is procurement staff.
Role = Literal["requester", "buyer"]

# Which `confidentiality` labels each role may see. The corpus has two:
# 24 documents are "Internal", and 10 are "Confidential" (the six supplier
# contract summaries, a supplier scorecard, an internal audit report, an RFP
# packet, and a category council memo).
#
# Any other label, or a document with no known label, is visible to NO role.
# That is "fail closed": a document someone forgot to label stays hidden
# instead of quietly becoming public.
ROLE_CLEARANCE = {
    "requester": frozenset({"Internal"}),
    "buyer": frozenset({"Internal", "Confidential"}),
}

# ---------------------------------------------------------------------------
# The status vocabulary the API returns.
#
# Day 19's four result statuses come straight from the trace row's `result`.
# Two more exist only at the API edge, because only the API can know them:
#
# - "blocked": the user did not get the agent's text. Either an entry guard
#   refused the request, or the output guard withheld an uncited answer.
#   (The trace row still says "answered" in that second case. The row records
#   what the MODEL did, and this status records what the USER got.)
# - "pending_approval": the question may need the follow-up retrieval pass,
#   and no reviewer decision came with it. Nothing ran.
#
# There is deliberately no "error" status. "The evidence is missing" is a
# normal outcome for a RAG system, and it has its own status. A crash is not
# normal, and it stays an HTTP 500.
# ---------------------------------------------------------------------------

ApiStatus = Literal["answered", "model_declined", "gap_report", "not_generated", "blocked", "pending_approval"]

OFF_TOPIC_MESSAGE = (
    "Blocked at the API entry point: the question, or an edited follow-up query, does not look like procurement "
    "(the findings name which). ProcureRAG answers from Vantera's procurement policies, procedures, and supplier "
    "contracts. Nothing was retrieved and no model was called."
)

PENDING_APPROVAL_MESSAGE = (
    "Waiting for approval: this question may need a second, targeted retrieval pass, and that action needs a "
    "reviewer's decision before it can run. Nothing has been retrieved yet. Send the same request again with a "
    "'decision': approve, edit (with your own 'followup_query'), or reject."
)

RESTRICTED_GAP_MESSAGE = (
    "Not answered: some of the evidence this question needs is in documents your role is not cleared to see, "
    "and no answer is built from partial evidence. Ask a colleague with buyer access."
)

UNLABELED_CAVEAT = (
    "no query_id was given, so there are no gold labels to check the evidence against: the graph cannot see an "
    "evidence gap and treats the evidence as complete. Treat this result as unchecked."
)

# A request without a `query_id` still needs a row in the graph's input
# shape (`agent_graph.make_initial_state`). These two values fill it. The id
# also starts the run's checkpointer thread id.
UNLABELED_QUERY_ID = "unlabeled"
UNLABELED_QUERY_TYPE = "unlabeled"  # not "multi_doc", so retrieval uses the default config


# ---------------------------------------------------------------------------
# The scope guard: is this a procurement question at all?
#
# Same shape as Day 20's `INJECTION_PATTERNS`: plain regex, case-insensitive,
# matched on whole words. A question is in scope if it contains at least ONE
# of these terms. `\w*` after a stem accepts its other forms
# ("approv\w*" -> approve, approval, approvers). Short acronyms get no `\w*`,
# and the `\b ... \b` around the whole group makes every term a whole word:
# "cip" (an Incoterm) is not matched inside "cipher".
#
# Where the terms come from: the knowledge base's own domain (its document
# categories, contract vocabulary, and the six supplier names in its
# `supplier` field). They were then checked against the 93 labeled queries.
# That check is a regression test (no labeled query is refused), NOT evidence
# that the list generalizes: it was written with those queries in view.
# ---------------------------------------------------------------------------

PROCUREMENT_TERMS = (
    # buying and sourcing
    r"procur\w*", r"purchas\w*", r"buy\w*", r"requisition\w*", r"sourc\w*", r"spend\w*", r"budget\w*",
    r"tender\w*", r"bid\w*", r"rfps?", r"rfqs?", r"quot\w*", r"award\w*",
    # suppliers and contracts
    r"suppl\w*", r"vendor\w*", r"contract\w*", r"subcontract\w*", r"agreement\w*", r"onboard\w*", r"renew\w*",
    r"terminat\w*", r"clause\w*", r"liabilit\w*", r"indemn\w*", r"insur\w*", r"incoterms?", r"ddp", r"cip",
    r"slas?", r"service levels?", r"service credits?", r"uptime", r"sub-processors?",
    # money: invoices, payments, prices
    r"invoic\w*", r"pay\w*", r"paid", r"pric\w*", r"cost\w*", r"saving\w*", r"surcharge\w*", r"index\w*",
    r"deadband", r"bank\w*", r"fraud\w*", r"toleran\w*", r"variance\w*", r"grni", r"goods",
    # governance, risk, and compliance
    r"approv\w*", r"delegat\w*", r"thresholds?", r"exceptions?", r"polic(?:y|ies)", r"audit\w*", r"complian\w*",
    r"risk\w*", r"due diligence", r"beneficial own\w*", r"sanction\w*", r"briber\w*", r"gifts?", r"hospitality",
    r"facilitation", r"esg", r"ecovadis", r"deforestation", r"sustainab\w*", r"scorecards?", r"kpis?",
    # spend categories in this knowledge base
    r"logistic\w*", r"freight", r"transport\w*", r"packaging", r"saas", r"software", r"licen[cs]\w*", r"cloud",
    r"consultan\w*", r"contingent", r"ir35", r"milestones?", r"statement of work", r"day-rate",
    # the six suppliers in the knowledge base (the corpus `supplier` field)
    r"acme", r"northstar", r"batavia", r"meridian", r"orion", r"cobalt",
)

PROCUREMENT_SCOPE_PATTERN = re.compile(r"\b(?:" + "|".join(PROCUREMENT_TERMS) + r")\b", re.IGNORECASE)


def guard_procurement_scope(query):
    """Scope guard: one `off_topic` BLOCK finding if no procurement term appears, else no finding.

    It runs before retrieval, so an off-topic question costs no embedding,
    no reranking, and no model call. Without it, "What is the capital of
    France?" would still retrieve the 5 "closest" procurement chunks (the
    default `top_k`). The graph would then call that context complete,
    because a question with no gold labels has nothing to miss.
    """
    if PROCUREMENT_SCOPE_PATTERN.search(query):
        return []
    return [
        GuardFinding(
            guard="off_topic",
            layer="input",
            action="block",
            detail="no procurement term found in the text, so it was refused before retrieval",
        )
    ]


def guard_retrieval_text(text):
    """Every check on one text that will be SENT TO RETRIEVAL, in order. Returns `(text_to_run, findings)`.

    `text_to_run` is None when the text is blocked. Otherwise it is the text
    retrieval will get: the original, or the PII-redacted version.

    1. Day 20's input guard, reused unchanged. Injection BLOCKS; PII is
       REDACTED. It runs first: an injection attempt is a security event and
       should be reported as one, even when it is also off-topic.
    2. The scope guard, on the redacted text: the scope decision never needs
       the buyer's email address.
    """
    text_to_run, findings = guard_user_query(text)
    if text_to_run is None:
        return None, findings

    scope_findings = guard_procurement_scope(text_to_run)
    if scope_findings:
        return None, findings + scope_findings
    return text_to_run, findings


def findings_about(field_name, findings):
    """The same findings, each `detail` starting with the request field it is about.

    For example "decision.message: redacted 1 email before retrieval and the
    LLM". The guards themselves only see a string, so they cannot say which
    field it came from. Without the prefix, a client could not tell a
    redaction in the question from one in the reviewer's message.
    """
    return [finding.model_copy(update={"detail": f"{field_name}: {finding.detail}"}) for finding in findings]


def run_entry_guards(body):
    """Every check on the text a CALLER wrote. Returns `(query_to_run, decision_to_run, findings)`.

    `query_to_run` is None when the request is blocked. Otherwise the graph
    runs on `query_to_run` and `decision_to_run` (None when no decision came):
    the caller's texts, with any PII redacted.

    A request carries up to three texts the caller wrote. Each one gets the
    checks that fit where it goes next:

        text                      where it goes                          checks
        query                     retrieval (pass 1), the LLM prompt     injection, PII, scope
        decision.followup_query   retrieval (pass 2)                     injection, PII, scope
        decision.message          the trace row, the response            injection, PII

    - An edited follow-up REPLACES the proposed follow-up query (Day 18), so
      it is a second question sent to the retriever. If only `query` were
      checked, a caller could write anything into `followup_query` and skip
      every guard: the question would be the clean front door, and the
      follow-up an unguarded side door.
    - The message never reaches retrieval or the model, so it gets no scope
      check: "not worth a second pass" is a good reason without a single
      procurement word. But the graph copies it into the trace row, the
      `excessive_agency` finding, and (on a reject) the caveats and the gap
      text. So an injection phrase blocks it, and PII is redacted.

    Both decision texts are guarded HERE, before the graph runs. So the graph
    only ever receives the redacted decision, and every copy it makes
    downstream is redacted too. Redacting each copy on the way out instead
    would need a check in every place the decision ends up, and the first
    place someone forgot would leak.

    The question is checked first, then the follow-up, then the message. The
    first block ends the checks.
    """
    query_to_run, findings = guard_retrieval_text(body.query)
    if query_to_run is None or body.decision is None:
        return query_to_run, None, findings

    decision_to_run = body.decision.as_graph_decision()  # a new dict: `body` itself is never changed

    if body.decision.followup_query is not None:
        followup_to_run, followup_findings = guard_retrieval_text(body.decision.followup_query)
        findings = findings + findings_about("decision.followup_query", followup_findings)
        if followup_to_run is None:
            return None, None, findings
        decision_to_run["followup_query"] = followup_to_run

    if body.decision.message is not None:
        message_to_record, message_findings = guard_user_query(body.decision.message)
        findings = findings + findings_about("decision.message", message_findings)
        if message_to_record is None:
            return None, None, findings
        decision_to_run["message"] = message_to_record

    return query_to_run, decision_to_run, findings


# ---------------------------------------------------------------------------
# The contract: request, response, and stream payload models.
#
# They extend Day 19's `ContractModel`, so an unknown key is an error. On a
# request that matters even more than inside the pipeline: a caller who
# misspells "decision" as "decison" gets a 422 that names the bad key,
# instead of the field silently vanishing and the query coming back as
# "pending_approval" for no visible reason.
#
# One difference from Day 19: optional REQUEST fields here have defaults.
# Day 19's models describe what the pipeline PRODUCES, so every field must be
# stated. A request model describes what a CALLER may leave out.
# ---------------------------------------------------------------------------


class ApprovalDecision(ContractModel):
    """A reviewer's answer to Day 18's approval gate, as a caller sends it.

    `{"type": "approve"}`, `{"type": "edit", "followup_query": "..."}`, or
    `{"type": "reject", "message": "why"}`: the same vocabulary as Day 18.

    The validator calls Day 18's own `decision_error`, so the API and the
    graph accept exactly the same decisions. A bad one (say, an "edit" with no
    `followup_query`) becomes a 422 here. Without this check it would reach the
    graph, which re-asks instead of raising (Day 18, gotcha 3). The run would
    stay paused, `run_and_trace` would raise a `ValueError`, and the caller
    would get an HTTP 500 for what was really their own mistake.

    The schema checks the decision's SHAPE and its LENGTHS. What its two texts
    SAY (an injection phrase, an email address, an off-topic follow-up) is
    checked later, by the same entry guards as the question
    (`run_entry_guards`).
    """

    type: ReviewerDecision
    followup_query: str | None = Field(default=None, max_length=MAX_QUERY_CHARS)
    message: str | None = Field(default=None, max_length=MAX_DECISION_MESSAGE_CHARS)

    @model_validator(mode="after")
    def _must_be_a_decision_the_graph_accepts(self):
        error = decision_error(self.as_graph_decision())
        if error is not None:
            raise ValueError(error)
        return self

    def as_graph_decision(self):
        """The plain dict Day 18's `approve_followup_node` expects, e.g. `{"type": "approve"}`."""
        return self.model_dump(exclude_none=True)


class QueryRequest(ContractModel):
    """What a caller sends to `/query` and `/query/stream`."""

    # Checked by Pydantic before the endpoint runs: an empty or over-long
    # question is a 422, and nothing downstream ever sees it.
    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    # Required, with no default: the caller must say who they are. A missing
    # role is a 422, not a silent guess.
    role: Role
    # Optional, and only for EVALUATION: one of the 93 labeled query ids, sent
    # together with that question's exact text. It selects the question's
    # gold labels, which the graph's evidence diagnosis needs. Leave it out
    # for any other question: that is a free-text request (see "Two kinds of
    # request" in the module docstring).
    query_id: str | None = None
    # Optional: the reviewer's answer, for a query that may pause for approval.
    decision: ApprovalDecision | None = None


class SourceRef(ContractModel):
    """One chunk in the final context, i.e. something the answer can cite as `[source_id]`.

    Only ids, never the chunk text: a client that wants the text can look it
    up, and the response stays small. Every chunk listed here has already
    passed the role filter and the context guard.
    """

    source_id: int  # the `n` in the answer's `[n]` citations
    doc_id: str
    chunk_id: str
    cited: bool  # True if the answer cites it, and it really was in the context


class ApprovalRequest(ContractModel):
    """What a reviewer needs in order to decide, returned with `pending_approval`.

    A smaller version of Day 18's `build_approval_request`. That one is built
    after pass 1, so it can name the measured gap. This one is built before
    any retrieval, so it can only say what WOULD run (see `note`).
    """

    query_id: str
    query: str  # the question, after PII redaction: exactly what would run
    proposed_action: Literal["recursive_retrieve"]
    proposed_followup_query: str
    allowed_decisions: list[ReviewerDecision]
    note: str


class QueryResponse(ContractModel):
    """What `/query` returns, and what the last `/query/stream` event carries.

    Built from Day 20's `GuardedResponse`, but deliberately SMALLER than it.
    The trace row stays on the server: it keeps the model's unredacted text
    as audit evidence (Day 20), so it is not safe to show a user. `run_id` is
    that row's id. It is meant to lead an auditor from this response to the
    row, but today the row is NOT saved anywhere (see "Honest limits").
    """

    status: ApiStatus
    query_id: str | None
    text: str  # the only field meant to be displayed as text
    sources: list[SourceRef]
    findings: list[GuardFinding]  # every guard that fired, in request order. Never contains a sensitive value
    approval_request: ApprovalRequest | None  # present only with "pending_approval"
    run_id: UUID | None  # the Day 19 trace row's id; None when the graph never ran
    caveats: list[str]

    @model_validator(mode="after")
    def _approval_request_only_when_pending(self):
        """A "pending_approval" without the request is useless to a client, and a request on any other status is noise."""
        if (self.status == "pending_approval") != (self.approval_request is not None):
            raise ValueError("approval_request must be present for status 'pending_approval' and absent otherwise")
        return self


class ValidatedRequest(ContractModel):
    """Payload of the `request_validated` stream event: the request passed every entry check."""

    query_id: str | None
    role: Role
    query: str  # what will run, after PII redaction


class RetrievalStarted(ContractModel):
    """Payload of the `retrieval_started` stream event: the guarded graph is now running."""

    role: Role
    visible_confidentiality: list[str]  # the labels this role's retrieval is filtered to


class HealthResponse(ContractModel):
    """What `/health` returns."""

    status: Literal["ok"]
    app: str
    version: str
    # Whether THIS running server was built with an LLM client, i.e. was
    # started with the switch on. It is what startup built, not what `.env`
    # says now: editing `.env` changes nothing until a restart, and health
    # must not pretend otherwise. And it is not reachability: health never
    # calls the provider to check. A health check that made a paid call on
    # every probe would cost money every few seconds.
    live_llm: bool


# The four stream event names, in the order they can appear:
#
#   request_validated  -> the request passed the entry guards (absent if it was blocked)
#   guard_finding      -> one per finding, in request order (input findings first)
#   retrieval_started  -> the guarded graph starts (absent if blocked or pending)
#   result             -> ALWAYS the last event, exactly once: the full `QueryResponse`
#
# Because `result` is always last and always present, a client can tell "the
# server finished" from "the connection died": no `result` means failure.
StreamEventName = Literal["request_validated", "guard_finding", "retrieval_started", "result"]


# ---------------------------------------------------------------------------
# The live LLM: an explicit, opt-in switch.
#
# A server has no command-line flags of its own (Uvicorn owns the command
# line), so the switch is an environment variable. That is also how a
# container platform will configure it later (Day 22/23): environment
# variables set on the container, not a file baked into the image.
# ---------------------------------------------------------------------------

LIVE_LLM_ENV_VAR = "PROCURERAG_LIVE_LLM"

# The repository's `.env` file (gitignored). Read for TWO values only, the
# switch above and `OPENROUTER_API_KEY` (see `read_setting`). It is a module
# constant so a test can point it at a temporary file, and never reads yours.
DOTENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def read_setting(name):
    """One setting: from the process environment if it is set there, otherwise from the `.env` file.

    The environment wins, for two reasons:

    - a container platform injects its settings as environment variables,
      and there is no `.env` file inside an image;
    - on your machine, a one-off value on the command line overrides the
      file. `PROCURERAG_LIVE_LLM=0 ... uvicorn ...` gives a free run even
      while `.env` says "1".

    "Set in the environment" means PRESENT, even with an empty value. An
    empty value is still a decision someone made: `PROCURERAG_LIVE_LLM= uvicorn ...`
    means "off". The shorter `os.environ.get(name) or dotenv_values(...)`
    gets this wrong. `or` treats "" like a missing value, and moves on to the
    file. So with "1" in `.env`, that empty value turned the paid LLM ON, the
    opposite of what it said. Hence `name in os.environ`, which asks "is it
    there?", not "is it truthy?".

    `dotenv_values` READS the file into a dict. Unlike `load_dotenv`, it
    copies nothing into `os.environ`, so the file's other lines (LangSmith,
    Tavily) never reach this process. Quotes are stripped:
    `PROCURERAG_LIVE_LLM="1"` reads as "1". Returns None if neither place
    has the setting.
    """
    if name in os.environ:
        return os.environ[name]
    return dotenv_values(DOTENV_PATH).get(name)


def live_llm_enabled():
    """True only if the switch `PROCURERAG_LIVE_LLM` is "1", in the environment or in `.env`.

    Exactly "1", nothing looser: unset, empty, "0", or "false" all mean off.
    A paid call should never happen by accident.
    """
    return read_setting(LIVE_LLM_ENV_VAR) == "1"


def make_llm_client():
    """The structured LLM client the served app uses, or None when the live LLM is off.

    With the switch on, this is Day 19's live client:
    `make_openrouter_client(response_model=GeneratedAnswer)`. The provider is
    asked for JSON in the `GeneratedAnswer` schema, and
    `structured_generate_node` validates it again. Same model
    (`OPENROUTER_MODEL`, else `openai/gpt-4o`), same 60 s timeout, same
    `MAX_ANSWER_TOKENS` budget as every `--generate` run.

    The switch and the API key both come from `read_setting`: the process
    environment first, otherwise the local `.env` file. This server takes
    those two values from `.env`, and nothing else.

    No key at all: `make_openrouter_client` raises `RuntimeError`. This
    function runs at startup (first thing in `build_live_service`), so a
    missing key stops the server before it ever accepts a request, instead
    of failing on the first paid request. An EMPTY key in the environment
    counts as no key: it wins over `.env` (see `read_setting`), and then
    stops startup the same way.
    """
    if not live_llm_enabled():
        return None

    return make_openrouter_client(api_key=read_setting("OPENROUTER_API_KEY"), response_model=GeneratedAnswer)


# ---------------------------------------------------------------------------
# The rate limit (OWASP LLM10, unbounded consumption): how many requests one
# client may send to the query endpoints.
#
# 30 requests in any 60 seconds is far more than a person typing questions
# needs, and it caps what one client can spend: with the live LLM on, at most
# 30 paid calls a minute. `/health` is never limited. A container platform
# probes it every few seconds, and a throttled probe would report a healthy
# server as down.
# ---------------------------------------------------------------------------

RATE_LIMIT_MAX_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60


class SlidingWindowRateLimiter:
    """At most `max_requests` per client in ANY `window_seconds`-long stretch of time.

    Learning-grade: in memory, in this one process (see "Honest limits").

    The algorithm is a "sliding window log". For each client, it keeps the
    times of that client's recent requests, oldest first. On a new request:

    1. forget every time that is now older than the window;
    2. count what is left. Under the limit: record this request, and let it
       through. At the limit: refuse it. The client must wait until the
       OLDEST recorded request leaves the window, and that wait becomes the
       response's `Retry-After` header.

    A refused request is not recorded. So a client that retries too early
    does not push its own wait further out.

    Compare the simpler "fixed window": a counter that resets at the start
    of every minute. It lets a client send 30 requests at 0:59 and 30 more
    at 1:00, i.e. 60 in two seconds. A sliding window never allows more than
    30 in any 60 seconds.

    Two details matter for correctness:

    - The clock is injected (`clock`). The server uses `time.monotonic`,
      which only ever moves forward. The wall clock (`time.time`) can jump,
      e.g. when the computer syncs its time, and a jump backwards would
      stretch every window. Tests pass a fake clock, so they can check the
      window exactly, without sleeping.
    - The lock. FastAPI runs the `def` endpoints, and this check, in a thread
      pool, so two requests can check at the same moment. Without the lock,
      both could see "29 of 30 used", and both would get through.
    """

    def __init__(
        self, max_requests=RATE_LIMIT_MAX_REQUESTS, window_seconds=RATE_LIMIT_WINDOW_SECONDS, clock=time.monotonic
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._recent = defaultdict(deque)  # {client: the times of its recent requests, oldest first}
        self._lock = threading.Lock()

    def admit(self, client):
        """Let one request from `client` through, or refuse it.

        Returns None if the request may go ahead (and records it). Returns the
        number of seconds to wait if it may not.
        """
        now = self._clock()
        with self._lock:
            recent = self._recent[client]
            while recent and recent[0] <= now - self.window_seconds:
                recent.popleft()  # older than the window: it no longer counts
            if len(recent) >= self.max_requests:
                return recent[0] + self.window_seconds - now
            recent.append(now)
            return None


# ---------------------------------------------------------------------------
# The service: everything a request needs, built once per process.
# ---------------------------------------------------------------------------


@dataclass
class ProcureRAGService:
    """The long-lived objects behind the API.

    The same injected boundaries as every day since Day 16: `retrieve_fn`
    (retrieval) and `client` (the LLM). The live server builds them once at
    startup (`build_live_service`). Tests build this class directly, with
    fakes, so no model, network, or credential is involved.

    - `labeled_queries`: `{query_id: labeled row}`, the gold labels behind the
      graph's evidence diagnosis.
    - `doc_confidentiality`: `{doc_id: "Internal" | "Confidential"}`, from the
      corpus. The authorization filter reads it.
    - `case_overrides`: Day 16's follow-up table. None means the real one
      (`AGENTIC_CASE_OVERRIDES`). Tests pass their own for synthetic ids.
    - `rate_limiter`: ONE limiter for the whole service, so every request
      counts against the same budget. Tests pass a small one, with a fake
      clock.
    """

    retrieve_fn: Callable
    client: Callable | None
    labeled_queries: dict[str, dict]
    doc_confidentiality: dict[str, str]
    case_overrides: dict | None = None
    # `default_factory`: a NEW limiter for each service. A plain
    # `= SlidingWindowRateLimiter()` default would be built once, when the
    # class is defined, and every service (every test, too) would share its
    # counts.
    rate_limiter: SlidingWindowRateLimiter = field(default_factory=SlidingWindowRateLimiter)

    def may_see(self, role, doc_id):
        """True if `role` is cleared for this document's label. An unknown document fails closed (False)."""
        return self.doc_confidentiality.get(doc_id) in ROLE_CLEARANCE[role]

    def retrieve_fn_for(self, role):
        """A `retrieve_fn` that only ever returns chunks `role` may see: the authorization filter.

        It wraps the real retriever in the same way Day 20's context guard
        does. And since `GuardedPipeline` wraps THIS function with the context
        guard, the order on every retrieval pass (pass 1, and the follow-up
        pass) is:

            real retrieval -> role filter (here) -> injection guard (Day 20) -> diagnose -> LLM

        So a withheld chunk is never seen by the context guard, the
        diagnosis, the model, the trace row, or the response.

        The kept sources are not renumbered here: the context guard, which
        runs right after this filter, renumbers whatever it keeps 1..n
        (Day 20's `guard_retrieved_sources`).
        """

        def authorized_retrieve(query_text, config):
            return [source for source in self.retrieve_fn(query_text, config) if self.may_see(role, source["doc_id"])]

        return authorized_retrieve


def load_live_pipeline():
    """Everything slow, or read from disk: `(retrieve_fn, corpus documents, labeled queries)`.

    The same build steps as Day 16-20's `main()`. It is slow (it loads the
    embedding model and the cross-encoder), which is why it runs once, at
    startup. It is its own function so that a test can replace it, and run
    the REAL startup path (`lifespan` -> `build_live_service`) in
    milliseconds.
    """
    from agentic_retrieval import make_live_retrieve_fn
    from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
    from chunking import chunk_corpus
    from hybrid_search import load_example_queries
    from preprocessing import load_data
    from reranking import load_cross_encoder
    from semantic_search import load_embedding_model

    documents = load_data()
    chunks = chunk_corpus(documents)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()

    retrieve_fn = make_live_retrieve_fn(chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model)
    return retrieve_fn, documents, load_example_queries()


def build_live_service():
    """The real service: live retrieval, the LLM client (if switched on), the labeled queries, and the corpus labels.

    The LLM client is built FIRST. With the live LLM switched on but no API
    key, startup fails in milliseconds, before 12 s of model loading.
    """
    client = make_llm_client()  # None unless PROCURERAG_LIVE_LLM=1
    retrieve_fn, documents, labeled_queries = load_live_pipeline()

    return ProcureRAGService(
        retrieve_fn=retrieve_fn,
        client=client,
        labeled_queries={row["query_id"]: row for row in labeled_queries},
        doc_confidentiality={doc["id"]: doc["confidentiality"] for doc in documents},
    )


# ---------------------------------------------------------------------------
# The FastAPI app, and its two dependencies.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app):
    """Startup and shutdown. The code before `yield` runs once, BEFORE the server accepts any request.

    That is why the models are loaded here: Uvicorn only starts serving (and
    so `/health` only starts answering) once the pipeline is ready. A
    container platform that probes `/health` therefore never routes a query
    to a server still loading its models. `build_live_service` blocks the
    event loop while it runs, which is harmless here: nothing is being served
    yet.

    In tests, `TestClient(app)` WITHOUT a `with` block never runs the
    lifespan, so no model is loaded, and most tests replace `get_service`
    instead. The startup tests do use `with`, after replacing
    `load_live_pipeline` with a fake.
    """
    app.state.service = build_live_service()
    yield


app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description="A typed, guarded HTTP boundary around the ProcureRAG agent graph (Day 21).",
    lifespan=lifespan,
)


def get_service(request: Request):
    """Dependency: the service built at startup.

    Endpoints never touch `app.state` themselves. They ASK for a service
    (`ServiceDep`), and FastAPI calls this function to provide it. That
    indirection is the testing seam: a test sets
    `app.dependency_overrides[get_service] = lambda: fake_service`, and every
    endpoint gets the fake. No endpoint code changes.
    """
    return request.app.state.service


ServiceDep = Annotated[ProcureRAGService, Depends(get_service)]


def enforce_rate_limit(request: Request, service: ServiceDep):
    """Dependency: HTTP 429 when this client has used up its requests for now.

    It is attached to the two query routes with `dependencies=[...]`, not as
    an endpoint parameter, because it gives the endpoint nothing: it can only
    refuse. FastAPI solves a route's `dependencies` BEFORE the endpoint's own
    parameters, so a refused request costs no field validation, no
    retrieval, and no LLM call. (Measured: once the limit is used up, a body
    with no `role` gets 429, not 422. Only a body that is not JSON at all is
    refused earlier, with a 422 while FastAPI reads it, and is not counted.)
    And, like `check_query_request`, it runs before a stream starts, so
    `/query/stream` can still answer 429.

    "Client" here means the network address the request came from
    (`request.client.host`). There is no authenticated identity to count by
    (see "Honest limits"). `Retry-After` is the standard HTTP header that
    tells a client how long to wait. It takes whole seconds, so the wait is
    rounded UP: rounding down would invite a retry that is still too early.
    """
    client = request.client.host if request.client is not None else "unknown"
    wait_seconds = service.rate_limiter.admit(client)
    if wait_seconds is not None:
        retry_after = math.ceil(wait_seconds)
        raise HTTPException(
            status_code=429,
            detail=(
                f"rate limit: at most {service.rate_limiter.max_requests} requests per "
                f"{service.rate_limiter.window_seconds} s from one client. Retry in {retry_after} s."
            ),
            headers={"Retry-After": str(retry_after)},
        )


def check_query_request(body: QueryRequest, service: ServiceDep):
    """Dependency: the parsed request body, after the checks Pydantic cannot do alone.

    Pydantic already checked the body's shape. What it cannot check needs the
    service's labeled queries. Both checks are about `query_id`, and each
    failure raises `HTTPException(422)`:

    1. The id must be one of the labeled queries.
    2. The question must be THAT id's question, word for word.

    Why the second check: an id selects gold labels, i.e. which documents
    its question needs. Those labels describe one particular question, not
    whatever text arrives with the id. Without the check, a caller could send
    the cleaning-contractor question with the id of an approval-band
    question. The graph would then measure the cleaning contract's evidence
    against the approval question's labels, and report a POL-001 approval
    policy as "missing": a confident gap report about a question nobody
    asked. The same mismatch could also fake "evidence complete", or trigger
    an approval pause meant for another question.

    "Word for word" is meant literally: one extra space makes it a different
    text. Any other wording is a different question, so it goes in as free
    text, without a `query_id`.

    Why these checks are a dependency, and not the first lines of the endpoint:
    FastAPI solves every dependency BEFORE it calls the endpoint, so a
    dependency can still answer 422. That matters for `/query/stream`. Once
    a stream has started, its status line ("200 OK") has already been sent,
    and an error can no longer change it.

    The endpoints get the body ONLY through this dependency (`CheckedQuery`),
    never as a second `body: QueryRequest` parameter of their own. FastAPI
    validates a body once for each place it is declared, so declaring it in
    both places validated it twice, and every 422 listed each error twice
    (measured).
    """
    if body.query_id is None:
        return body  # free text: no labels are involved, so there is nothing to check

    labeled_row = service.labeled_queries.get(body.query_id)
    if labeled_row is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"unknown query_id {body.query_id!r}: it must be one of the {len(service.labeled_queries)} "
                "labeled queries (it selects their gold labels), or be left out"
            ),
        )
    if body.query != labeled_row["query"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"query_id {body.query_id!r} selects the gold labels of one labeled question, and this query is "
                "not that question's exact text. Send its exact text to replay it, or leave query_id out to ask "
                "anything else as free text (its evidence is then unchecked)"
            ),
        )
    return body


CheckedQuery = Annotated[QueryRequest, Depends(check_query_request)]


def query_row_for(body, service):
    """The query row the graph runs on, in `agent_graph.make_initial_state`'s input shape.

    - With a `query_id`: that labeled row, exactly as labeled.
      `check_query_request` has already made sure the caller's text IS the
      row's text, so the row's gold labels describe the question that runs.
    - Without one: a free-text row, with no gold labels (see
      `UNLABELED_CAVEAT`).
    """
    if body.query_id is None:
        return {
            "query_id": UNLABELED_QUERY_ID,
            "query": body.query,
            "query_type": UNLABELED_QUERY_TYPE,
            "relevance_grades": {},
        }
    # The shared row itself, read-only: nothing downstream changes it
    # (`GuardedPipeline.run` makes its own copy before it redacts anything).
    return service.labeled_queries[body.query_id]


# ---------------------------------------------------------------------------
# Building the response for each way a request can end.
# ---------------------------------------------------------------------------


def blocked_response(body, findings):
    """An entry guard refused the request. The graph never ran, so there is no trace row and no `run_id`."""
    off_topic = any(finding.guard == "off_topic" for finding in findings)
    return QueryResponse(
        status="blocked",
        query_id=body.query_id,
        text=OFF_TOPIC_MESSAGE if off_topic else BLOCKED_INPUT_MESSAGE,
        sources=[],
        findings=findings,
        approval_request=None,
        run_id=None,
        caveats=[],
    )


def pending_approval_response(body, query_row, query_to_run, findings, service):
    """The query may need the follow-up pass, and no decision came with it: say so, and run nothing.

    This is Day 20's fail-closed rule, translated for a caller. In Day 20,
    `GuardedPipeline.run` raises a `ValueError` here: inside a program, a
    missing decision is a programming error. At the API edge it is a normal
    product state, so it becomes a typed response with what a reviewer needs.
    It is never an auto-approval, and never a 500.

    The proposed follow-up comes from `make_initial_state`, i.e. from the
    same Day 16 table the graph's router reads.
    """
    followup_query = make_initial_state(query_row, service.case_overrides)["followup_query"]
    return QueryResponse(
        status="pending_approval",
        query_id=body.query_id,
        text=PENDING_APPROVAL_MESSAGE,
        sources=[],
        findings=findings,  # e.g. a PII redaction, so the reviewer knows the query was changed
        approval_request=ApprovalRequest(
            query_id=query_row["query_id"],
            query=query_to_run,
            proposed_action=ROUTE_RECURSIVE_RETRIEVE,
            proposed_followup_query=followup_query,
            allowed_decisions=list(ALLOWED_DECISIONS),
            note=(
                "Pass 1 has not run, so the evidence gap is not measured yet. The decision is used only if "
                "pass 1 leaves required evidence missing."
            ),
        ),
        run_id=None,
        caveats=[],
    )


def sources_from_trace(trace):
    """The final context as `SourceRef`s, rebuilt from the trace row.

    The final context is pass 1's chunks followed by the chunks pass 2
    appended, numbered 1..n in that order (the same rule as Day 20's
    `gap_filling_source_ids`). `cited` uses the VALID citation ids only, so
    an orphan `[7]` never marks anything as cited.
    """
    final_context = [chunk_id for retrieval_pass in trace.retrieval_passes for chunk_id in retrieval_pass.added_chunk_ids]
    citations = trace.result.citations  # None when no LLM wrote the text
    cited_ids = set(citations.valid_ids) if citations is not None else set()
    return [
        SourceRef(source_id=number, doc_id=chunk_id.split("::")[0], chunk_id=chunk_id, cited=number in cited_ids)
        for number, chunk_id in enumerate(final_context, start=1)
    ]


def restricted_gap(result, role, service):
    """True if a gap report's missing evidence includes a document this role may not see.

    Day 17's gap report NAMES the missing documents ("... primary
    document(s) ['CONTRACT-005', 'POL-002'] ..."). After the role filter
    removed a confidential document, that sentence would tell a requester that
    a confidential document exists, and is what they would need. That is a
    side-channel leak: no content, but still a disclosure. A chunk id names
    its document (`<doc_id>::chunk-<n>`), so missing chunks are checked too.
    """
    missing_doc_ids = set(result.missing_doc_ids) | {chunk_id.split("::")[0] for chunk_id in result.missing_chunk_ids}
    return any(not service.may_see(role, doc_id) for doc_id in missing_doc_ids)


def build_query_response(body, query_row, guarded, findings, service):
    """Translate Day 20's `GuardedResponse` into the user-safe `QueryResponse`.

    - `status`: "blocked" if the user did not get the agent's text,
      otherwise the trace row's own status.
    - `text`: Day 20's user-safe `GuardedResponse.text` (redacted, or the
      withheld message), except for a restricted gap (see `restricted_gap`).
    - `findings`: passed in by `run_query_events`, which knows them all: the
      entry findings (the decision's included) and then the graph's.
    - Nothing else from the trace row except ids: the sources, the `run_id`,
      and the caveats `build_result` wrote for the reader.
    """
    trace = guarded.trace
    result = trace.result

    # The input guard ran before this point, so `blocked` here can only mean
    # that the OUTPUT guard withheld an uncited answer.
    status = "blocked" if guarded.blocked else result.status

    text = guarded.text
    if result.status == STATUS_GAP_REPORT and restricted_gap(result, body.role, service):
        text = RESTRICTED_GAP_MESSAGE

    caveats = list(result.caveats)
    if query_row["query_id"] == UNLABELED_QUERY_ID:
        caveats.append(UNLABELED_CAVEAT)

    return QueryResponse(
        status=status,
        query_id=body.query_id,
        text=text,
        sources=sources_from_trace(trace),
        findings=findings,
        approval_request=None,
        run_id=trace.run_id,
        caveats=caveats,
    )


# ---------------------------------------------------------------------------
# The one pipeline behind both query endpoints.
# ---------------------------------------------------------------------------


def run_query_events(service, body) -> Iterator[tuple[StreamEventName, BaseModel]]:
    """Run one request through every stage, yielding `(event_name, payload)` as each stage finishes.

    The last item is always `("result", QueryResponse)`. A generator is a
    natural fit here: each `yield` hands one event to whoever is iterating
    (the SSE endpoint sends it at once), and the function then continues
    from where it stopped.
    """
    query_row = query_row_for(body, service)

    # Stage 1: the entry guards, on every text the caller wrote (the question,
    # and the decision's follow-up and message), before anything else sees them.
    query_to_run, decision_to_run, entry_findings = run_entry_guards(body)
    for finding in entry_findings:
        yield "guard_finding", finding
    if query_to_run is None:
        yield "result", blocked_response(body, entry_findings)
        return

    yield "request_validated", ValidatedRequest(query_id=body.query_id, role=body.role, query=query_to_run)

    # Stage 2: the approval boundary. It comes AFTER the entry guards (an
    # injection attempt shaped like Q091 must be "blocked", not
    # "pending_approval") and BEFORE any retrieval (nothing runs without a
    # decision).
    if body.decision is None and may_pause_for_approval(query_row, service.case_overrides):
        yield "result", pending_approval_response(body, query_row, query_to_run, entry_findings, service)
        return

    # Stage 3: the Day 20 guarded graph, on a retriever filtered to this role.
    yield "retrieval_started", RetrievalStarted(
        role=body.role, visible_confidentiality=sorted(ROLE_CLEARANCE[body.role])
    )

    # A NEW pipeline for every request, for two reasons:
    # - the role filter is per request, and the retriever is fixed when the
    #   pipeline is built;
    # - `GuardedPipeline` keeps the current run's context findings on the
    #   instance (Day 20: "not thread-safe"). Worker threads serve requests in
    #   parallel, so one shared pipeline could mix two runs' findings.
    # Building one only compiles the small graph. The expensive models stay
    # shared, inside `service.retrieve_fn`.
    pipeline = GuardedPipeline(service.retrieve_fn_for(body.role), client=service.client)
    # The ORIGINAL row goes in. `run` repeats Day 20's input guard on the
    # question (a pure function, so it finds exactly what stage 1 found) and
    # redacts it exactly as Day 20 does. The decision goes in ALREADY guarded
    # (stage 1): `run` never checks a decision's text, so that is this API's job.
    guarded = pipeline.run(query_row, decision_to_run, case_overrides=service.case_overrides)

    # Every input finding was streamed in stage 1, the decision's included
    # (and `run` never sees those). Stream the rest (context, action, output)
    # now, in request order.
    later_findings = [finding for finding in guarded.findings if finding.layer != "input"]
    for finding in later_findings:
        yield "guard_finding", finding

    yield "result", build_query_response(body, query_row, guarded, entry_findings + later_findings, service)


# ---------------------------------------------------------------------------
# The endpoints. Each one is thin: parse (FastAPI), run (`run_query_events`),
# and shape the output. The return annotation is the response contract:
# FastAPI validates the returned value against it, and publishes it in the
# OpenAPI schema at /docs.
# ---------------------------------------------------------------------------


@app.get("/health")
def health(request: Request) -> HealthResponse:
    """Liveness: the process is up and answering HTTP.

    It deliberately does not ask for the service through `get_service`, so it
    never builds or calls the pipeline, and never contacts a provider. A
    health check that loads models or calls an LLM would be slow, cost money,
    and fail for reasons unrelated to "is this server up?".

    For `live_llm` it only LOOKS at what startup stored on `app.state`. If
    no service was built (as in most tests, which skip startup), there is no
    client, so the answer is False.

    It is also never rate-limited: it has no `enforce_rate_limit`
    dependency (see `RATE_LIMIT_MAX_REQUESTS` for why).
    """
    service = getattr(request.app.state, "service", None)
    live_llm = service is not None and service.client is not None
    return HealthResponse(status="ok", app=APP_TITLE, version=APP_VERSION, live_llm=live_llm)


@app.post("/query", dependencies=[Depends(enforce_rate_limit)])
def query(body: CheckedQuery, service: ServiceDep) -> QueryResponse:
    """Answer one question with one JSON `QueryResponse`.

    By the time this line runs, FastAPI has already checked the rate limit
    (or answered 429), validated `body` and checked its `query_id` (or
    answered 422), and has the service ready. It runs the same events as the
    stream, and keeps only the last one, the result.
    """
    events = list(run_query_events(service, body))
    _, response = events[-1]  # always ("result", QueryResponse)
    return response


@app.post("/query/stream", response_class=EventSourceResponse, dependencies=[Depends(enforce_rate_limit)])
def query_stream(body: CheckedQuery, service: ServiceDep) -> Iterator[ServerSentEvent]:
    """The same request, answered as Server-Sent Events (SSE).

    SSE is one long HTTP response with the content type `text/event-stream`.
    The server writes one event at a time into it, and each event is a few
    `field: value` lines, ending with a blank line:

        event: request_validated
        data: {"query_id":"Q001","role":"buyer","query":"..."}
        id: 1

    - `event` is the event name. A browser's `EventSource` can listen per
      name: `addEventListener("result", ...)`.
    - `data` is the payload. FastAPI serializes the Pydantic model to JSON.
    - `id` is a sequence number. A reconnecting browser sends the last one
      back (`Last-Event-ID`). This server does not resume streams, so it is
      only a sequence number here.

    `response_class=EventSourceResponse`, together with this function being
    a generator (`yield`), is what makes FastAPI stream it. As a plain `def`
    generator, it is iterated in a worker thread (see "Why `def`").

    It is a POST, because the request has a JSON body. A browser's built-in
    `EventSource` can only send GET, so a web client would read this stream
    with `fetch()` instead.
    """
    for sequence, (event_name, payload) in enumerate(run_query_events(service, body), start=1):
        yield ServerSentEvent(event=event_name, data=payload, id=str(sequence))
