"""Day 25 (Block 3A): an MCP server that exposes the Day 21 guarded service as ONE tool.

**What MCP adds.** Day 21's FastAPI app is an HTTP contract: any HTTP client
can call `POST /query`, but someone has to write that client, for each
application that wants it. MCP (Model Context Protocol) is a contract for AI
applications instead. An MCP HOST (Claude Code, Claude Desktop, an IDE) runs
one MCP CLIENT per server it connects to. The client starts this file, asks
it what it offers (`tools/list`), and the host's model decides when to call a
tool (`tools/call`). Write the server once, and every MCP host can discover
and call it, with no ProcureRAG-specific code in any of them: M hosts and N
servers need M + N implementations, not M x N integrations.

**Who does what.**

    host (Claude Code, ...)   the user talks to it; ITS model reasons and decides to call the tool
      -> MCP client           one connection to this server: initialize, tools/list, tools/call
        -> this MCP server    checks the arguments, runs ProcureRAG, returns a typed result
          -> Day 21 service   the SAME guarded pipeline that runs behind POST /query
               entry guards -> approval boundary -> role-filtered retrieval -> graph -> output guard

The server is not an agent. It has no model of its own to reason with. With
the live LLM off (the default), it calls no model at all: retrieval and the
guards run, and a complete-evidence run ends `not_generated`, exactly as it
does over HTTP. The reasoning (when to call, what to do with the result)
stays in the host.

**One tool, no second pipeline.** `answer_procurement_question` is a thin
adapter. It builds Day 21's `QueryRequest` from its arguments and runs
`api.run_query_events`, the one function behind both `/query` and
`/query/stream`. So MCP and HTTP cannot drift into two policies: the input
guards (injection, PII, scope), the role filter, the approval gate, the
output guard, and the response shape are all Day 21's own code, reused
unchanged. A tool that called the retriever or the graph directly would skip
every one of them.

What this module adds is only what MCP itself needs:

- the argument schema a host reads in `tools/list`. The SDK builds it from the
  type hints of `answer_procurement_question`;
- the result schema (`output_schema`). It is Day 21's `QueryResponse`, the
  response model that already leaves the trace row on the server: ids, never
  chunk text;
- Day 21's two HTTP refusals turned into `ToolError`, the MCP way to say "this
  call failed, and here is why": a 422 for a `query_id` sent without its
  question, and a 429 for the rate limit;
- the service, built once per process (`lifespan`), not once per call;
- the reviewer's decision, asked from the USER through MCP elicitation, never
  taken from the model (see "Approval comes from the user");
- a crash reported with no text from the exception, in the result AND in
  the server's log, and no LangSmith tracing (see "Crashes, logs, and
  traces").

**One call, in order.** Each step can end the call, before the more expensive
steps after it:

    tools/call arguments
      -> [SDK: the tool's argument schema: lengths, role]  ................. is_error result, the tool never runs
      -> [ask_the_reviewer: would Day 21 stop at pending_approval?]  ....... yes, and the host can ask: the USER
                                                                             answers a form; nothing has run yet
      -> [Day 21's QueryRequest, with the user's decision if one came]
      -> [rate limit: this process's one budget]  ........................... ToolError, nothing runs
      -> [check_query_request: a labeled id, with ITS text?]  ................ ToolError, nothing runs
      -> [run_query_events: entry guards, approval boundary, guarded graph]
      -> QueryResponse: the structured result, and the same JSON as text

`blocked` and `pending_approval` are normal results, not errors. The request
was understood, and the answer is "no" or "not yet". An error is for a call
that could not run as asked.

**Approval comes from the user, not from the model.** Q091 and Q092 may need
a second, targeted retrieval pass, and Day 18's rule is that a PERSON
approves it. Over HTTP, the reviewer's decision is a field of the request
body. As a tool argument, it would be written by the host's model, which
could approve on its own. So this tool has no `decision` argument. It asks
the user directly, with MCP ELICITATION: the server sends a question and a
small form (`ReviewerAnswer`: approve, edit, or reject), the host shows it to
the user, and the answer comes back to the server without passing through the
model.

In the SDK, this is a RESOLVER. The tool's `review` parameter is
`Annotated[..., Resolve(ask_the_reviewer)]`: the SDK runs `ask_the_reviewer`
before the tool body, and puts its result in `review`. A resolved parameter is
not in the tool's input schema, so the model is never told about it, and a
value the model sends anyway is ignored. On the 2026-07-28 protocol, asking
takes two rounds of the same `tools/call`: the first one returns the question
(an `InputRequiredResult`), the host asks the user, and the host's retry
carries the answer.

`ask_the_reviewer` asks only when Day 21 itself would stop at
`pending_approval` (`pending_approval_preview`). So a request that is blocked
or refused never reaches a person, and nothing is retrieved before the person
has answered. When no usable answer comes, the call fails closed: nothing
runs, and the result is `pending_approval`, with a text that says why:

- the host did not declare elicitation support, so it cannot ask
  (`CANNOT_ASK_MESSAGE`);
- the user declined or dismissed the question (`NOT_DECIDED_MESSAGE`).

An answer that is not a usable decision (an `edit` with no follow-up query)
is an error result, so the host can ask again.

**Crashes, logs, and traces.** An exception's text can quote whatever it
was handed: a provider's error may repeat a URL, a header, or a key. The
SDK keeps a crash's text out of the RESULT (the model reads only "Error
executing tool ..."), but it LOGS the whole traceback, message included, to
stderr. Measured with mcp 2.3.0: a test's fake key, put in a provider
timeout, appeared verbatim in the server log. So `crash_details_withheld`
catches a crash before the SDK sees it, logs only the exception's TYPE
(`TimeoutError`), and raises a `ToolError` with a fixed message instead.
The SDK logs a `ToolError` as one INFO line, its message, with no traceback.

A LangSmith trace would send the same text out of the machine, with the
question and the retrieved evidence. Day 21 leaves tracing to the shell:
it is on only if the shell exports the `LANGSMITH_*` variables. Under MCP
that shell is the HOST's. Claude Code passes its whole environment to this
server, so an export made for other work would trace every call, and
nobody decided that here. So this server traces nothing, whatever the
environment says: `answer_question` runs the pipeline inside LangSmith's
own switch, `tracing_context(enabled=False)`, which wins over the
environment variables. To trace a run, use the HTTP API or the Day 19
scripts.

**The live LLM needs an explicit opt-in in the launch command.** Over HTTP,
the switch `PROCURERAG_LIVE_LLM` comes from the environment, or else from
`.env` (Day 21's `read_setting`). Under MCP that fallback is the wrong
default. A host may start this server with a reduced environment: the SDK's
own stdio client passes only `HOME`, `LOGNAME`, `PATH`, `SHELL`, `TERM`, and
`USER`. (Claude Code passes your whole shell environment instead, which
normally has no `PROCURERAG_LIVE_LLM` either.) The `.env` file would then
decide on its own, and this repo's `.env`
says `PROCURERAG_LIVE_LLM="1"` (checked on 2026-10-22). Every call would be a
paid call, and here it is the host's MODEL that decides how often to call. So
`build_mcp_service` reads the switch from the launch environment only: "1"
there turns it on, and no setting means off, whatever `.env` says. Once it is
on, the API key still comes from the environment or `.env`, as on Day 21.

**stdio, and why stdout is off limits.** `server.run()` (below, and what
`mcp run` and `mcp dev` call) serves over stdio: the host starts this file as
a child process, writes JSON-RPC requests to its stdin, and reads the
responses from its stdout. Nothing listens on a port, so there is no network
surface, and no authentication, TLS, or ingress to get right yet. It also
makes stdout the protocol channel. One stray `print()` there corrupts a
message, and the host drops the connection. So this module never prints. Its
diagnostic lines (the service build, the clean stop, and a crash's type) go
through `logging`, which `MCPServer` points at stderr when it is constructed. The
model-loading libraries write their warnings and progress to stderr too.
While serving, the SDK also diverts any flushed stray output to stderr, but
not before serving starts: a print flushed at import time still lands on
stdout (measured with mcp 2.3.0). `scripts/mcp_stdio_smoke.py` is the check:
a real stdio client that reads this process's stdout as JSON-RPC and nothing
else.

**Running it.**

    # the protocol tests: an in-memory client (no process, no port, no models, no key)
    uv run pytest -q tests/test_mcp_server.py

    # a real stdio client: starts this file, lists the tool, makes five calls (loads the models);
    # a scripted reviewer answers the two Q091 questions (decline, then reject)
    HF_HUB_OFFLINE=1 uv run python scripts/mcp_stdio_smoke.py

    # the MCP Inspector, in a browser (needs `npx`: the Inspector is a Node app)
    uv run mcp dev src/mcp_server.py

    # The commands below start the server from ANOTHER folder (the Inspector's, or the host's),
    # so they name this repository by its absolute path. Run them from the repository root:
    REPO_ROOT="$(pwd)"

    # the same Inspector, CLI mode: it starts its own server process, sends ONE request, prints
    # the JSON result, and exits (exit 5: an is_error result). It passes the server only the SDK's
    # allow-listed variables plus each -e, so the switch is stated in the command.
    npx -y @modelcontextprotocol/inspector@2.12.0 --cli -e PROCURERAG_LIVE_LLM=0 \
        -e LANGSMITH_TRACING=false -e LANGSMITH_TRACING_V2=false -e HF_HUB_OFFLINE=1 \
        --method tools/list -- uv run --directory "$REPO_ROOT" python src/mcp_server.py

    # one PAID call through the Inspector CLI: -e PROCURERAG_LIVE_LLM=1. The key comes from `.env`:
    # never pass it with -e, which would put it in your shell history. query_id=Q001 checks the
    # evidence against Q001's gold labels (its exact text is required).
    npx -y @modelcontextprotocol/inspector@2.12.0 --cli -e PROCURERAG_LIVE_LLM=1 \
        -e LANGSMITH_TRACING=false -e LANGSMITH_TRACING_V2=false -e HF_HUB_OFFLINE=1 \
        --method tools/call --tool-name answer_procurement_question \
        --tool-arg "query=What approval is required for a EUR 60,000 purchase order?" role=buyer query_id=Q001 -- \
        uv run --directory "$REPO_ROOT" python src/mcp_server.py

    # register it with Claude Code. "$REPO_ROOT" expands NOW, so Claude Code stores the absolute
    # path: it starts the server from its own folder. It also passes your whole shell environment
    # to the server by default, so the safe values are stated here. (The LangSmith flags are a
    # second safety: this server switches tracing off itself, see "Crashes, logs, and traces".)
    # PROCURERAG_LIVE_LLM=1 instead of 0 makes it a PAID server (the key comes from `.env`).
    claude mcp add procurerag -e PROCURERAG_LIVE_LLM=0 -e LANGSMITH_TRACING=false \
        -e LANGSMITH_TRACING_V2=false -e HF_HUB_OFFLINE=1 -- \
        uv run --directory "$REPO_ROOT" python src/mcp_server.py

`src/` must be on `sys.path` so that `import api` (and the modules `api`
imports) resolve. `python src/mcp_server.py` puts the script's own folder
there, and `mcp run` / `mcp dev` add the file's folder too.

**Honest limits.**

- The role is asserted by whoever writes the tool arguments, and under MCP that
  is the host's MODEL. Day 21's filter is still enforced on every call, but a
  model can claim `"buyer"` as easily as an HTTP caller can. A remote MCP
  server would authenticate the connection (the SDK supports OAuth) and take
  the role from the verified identity, never from an argument.
- Elicitation moves the decision from the model to the HOST. A host that
  shows the form to a person makes it a person's decision, but this server
  cannot prove that. A host may answer an elicitation by itself (Claude Code,
  for example, has an `Elicitation` hook that can respond without showing the
  dialog), and nothing records WHO answered. So the approval is still
  stateless and unattributed, as on Day 21. A real review needs an
  authenticated reviewer and a durable approval record.
- The question is asked BEFORE pass 1, as on Day 21, so it cannot show the
  measured evidence gap: only what would run. Asking after pass 1 would need
  the run to pause, and to resume across the host's retry: Day 18's
  checkpointer, not built here.
- A host without elicitation support can never approve the follow-up pass
  through this tool: Q091 and Q092 stay `pending_approval` there. That is the
  fail-closed choice. Over HTTP, the decision is still a request field.
- An unknown argument is ignored, not refused. The SDK's argument model drops
  keys it does not know (measured with mcp 2.3.0). Over HTTP the same key is a
  422. Here it fails closed: a `decision` the model sends anyway simply
  vanishes, and Q091 still waits for the user (tested).
- An argument-schema error repeats the start of the caller's own input
  (Pydantic's message includes `input_value=...`, truncated). That is the
  caller's own text, not server data. FastAPI's 422 does the same.
- The rate limit is one budget for the whole process (30 calls a minute). A
  stdio server has exactly one client, the host that started it. It is Day 21's
  learning-grade limiter, and it resets on every restart.
- The lifespan runs once per CONNECTION. That is once per process for stdio,
  where one process serves one host. The in-memory test client starts a new
  connection, so a new lifespan, for every `async with Client(server)`.
- Local stdio only. Remote Streamable HTTP needs authentication, TLS, origin
  checks, and a deployment: a separate problem, deliberately not solved here.
- A crash in a tool call is logged by its exception type only: no message, and
  no traceback, for the operator either. Debugging one means reproducing it
  outside the server (in a test, or over the HTTP API). A failure at startup
  (in `lifespan`) is not covered: the SDK logs it in full, before any call.
- No LangSmith traces from this server, even when you want one: it cannot be
  switched on (see "Crashes, logs, and traces").
- Every Day 21 limit still holds: free-text evidence is unchecked, trace rows
  are not persisted, the scope guard is a keyword list, and an LLM failure is a
  failure (here a sanitized `is_error` result, not a 500).
"""

import logging
import math
import os
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated, Literal

from fastapi import HTTPException
from langsmith import tracing_context
from mcp.server import MCPServer
from mcp.server.mcpserver import (
    AcceptedElicitation,
    CancelledElicitation,
    Context,
    DeclinedElicitation,
    Elicit,
    ElicitationResult,
    Resolve,
)
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, ValidationError

# The Day 21 module, imported whole, so every reused piece reads as
# `api.<name>` below: the request and response models, the service, the
# `query_id` check, and the pipeline itself.
import api

logger = logging.getLogger(__name__)

SERVER_NAME = "ProcureRAG"

# The rate limiter counts per client. Over HTTP a client is a network
# address. A stdio server has exactly ONE client, the host that started this
# process, so every call counts against this one key.
STDIO_CLIENT = "stdio-host"

# The two ways a call can end at `pending_approval` under MCP. They replace
# Day 21's `PENDING_APPROVAL_MESSAGE`, which tells an HTTP caller to "send
# the same request again with a 'decision'". This tool has no `decision`
# argument, so that sentence would send the model into a loop of ignored
# retries.
CANNOT_ASK_MESSAGE = (
    "Waiting for approval: this question may need a second, targeted retrieval pass, and a person must approve "
    "it first. This MCP host cannot show that question to its user (it did not declare elicitation support), so "
    "nothing has run, and the pass cannot be approved here. Use an MCP host that supports elicitation, or "
    "ProcureRAG's HTTP API."
)

NOT_DECIDED_MESSAGE = (
    "Waiting for approval: the user was asked whether to run a second, targeted retrieval pass, and did not choose "
    "(the question was declined or dismissed). Nothing has run. Call the tool again only if the user wants to be "
    "asked again."
)

# What the model reads when a call crashed (see `crash_details_withheld`).
# Fixed text: nothing from the exception itself.
CRASH_MESSAGE = "internal error: ProcureRAG could not finish this call (the details are withheld)."


class ReviewerAnswer(BaseModel):
    """The form the user fills in, when a question needs a reviewer's decision.

    The SDK turns this model into the JSON Schema the host renders as a form,
    the same way it turns type hints into a tool's argument schema. An
    elicitation form only takes flat, primitive fields (str, int, float,
    bool, or a Literal of strings), so the decision is three plain fields
    here, not Day 21's `ApprovalDecision` model. `as_decision` converts it,
    and `ApprovalDecision` then checks it with Day 18's own rules.

    The limits are Day 21's: the edited follow-up is a second query sent to
    retrieval, and the message is a short recorded reason.
    """

    decision: Literal["approve", "edit", "reject"] = Field(
        description=(
            "approve: run the proposed follow-up retrieval pass. edit: run your own follow-up query instead. "
            "reject: no second pass (ProcureRAG answers from the first pass, or reports what is missing)."
        )
    )
    followup_query: str = Field(
        default="",
        max_length=api.MAX_QUERY_CHARS,
        description="Only for edit: the follow-up query to run instead of the proposed one.",
    )
    message: str = Field(
        default="",
        max_length=api.MAX_DECISION_MESSAGE_CHARS,
        description="Optional: the reason for your decision. It is recorded with the run.",
    )

    def as_decision(self):
        """The same decision as Day 21's `ApprovalDecision`, which an HTTP caller would send.

        A form has no "not given", only an empty field, so "" becomes None.
        The follow-up text is kept only for an `edit`, the one decision that
        uses it: text left in that field by a user who then chose approve or
        reject must not change what runs.

        Raises a Pydantic `ValidationError` if Day 18's rules refuse it (an
        `edit` with no follow-up query).
        """
        return api.ApprovalDecision(
            type=self.decision,
            followup_query=(self.followup_query or None) if self.decision == "edit" else None,
            message=self.message or None,
        )


# ---------------------------------------------------------------------------
# The service: built once per process, before the first request.
# ---------------------------------------------------------------------------


def build_mcp_service():
    """Day 21's real service, with the paid LLM switched on only by the launch environment.

    `os.environ.setdefault` writes "0" only when the launch environment does
    not set `PROCURERAG_LIVE_LLM` at all. A value set there ("1" included) is
    left alone. Day 21's `read_setting` looks at the environment first, so
    from this line on `.env` is never consulted for the switch (see "The live
    LLM needs an explicit opt-in" in the module docstring).

    Everything else is Day 21's `build_live_service`, unchanged: the LLM
    client first (so a missing key fails in milliseconds), then the two
    retrieval models, the labeled queries, and the corpus's confidentiality
    labels.
    """
    os.environ.setdefault(api.LIVE_LLM_ENV_VAR, "0")
    return api.build_live_service()


@asynccontextmanager
async def lifespan(_server):
    """Startup: build the service ONCE, before the server answers any request.

    The MCP version of Day 21's FastAPI `lifespan`. The SDK enters it when the
    server starts serving (for stdio: once per process) and gives the yielded
    object to every tool call as `ctx.request_context.lifespan_context`. So
    the two models load once, and every call shares them, and the same rate
    limiter. Building the service inside the tool instead would reload the
    models on every call (about 12 s each), and give every call a new, empty
    limiter: no limit at all.

    `build_mcp_service` blocks while the models load, and that is harmless
    here: the server reads no request until this function has yielded. The
    host's `initialize` request waits in the stdin pipe meanwhile.

    The tests replace `build_mcp_service` with a function that returns a fake
    service. That is this server's testing seam, the MCP counterpart of
    Day 21's `app.dependency_overrides`.
    """
    started = time.perf_counter()
    service = build_mcp_service()
    # stderr, never stdout (see "stdio, and why stdout is off limits"). One
    # line per process, so it also shows how many times the service was built.
    logger.info(
        "ProcureRAG service ready in %.1f s (pid %d, live LLM: %s)",
        time.perf_counter() - started,
        os.getpid(),
        service.client is not None,
    )
    yield service
    # Reached only on a CLEAN shutdown: the host closed stdin, the serve loop
    # ended, and the SDK left this lifespan. A process that had to be killed
    # never logs it.
    logger.info("ProcureRAG MCP server stopped (pid %d)", os.getpid())


# The server object. `mcp run` and `mcp dev` find it by this name (they look
# for `mcp`, `server`, or `app`). Constructing it also configures `logging`
# (level INFO, to stderr).
server = MCPServer(SERVER_NAME, version=api.APP_VERSION, lifespan=lifespan)


# ---------------------------------------------------------------------------
# Crashes: reported and logged without the exception's text.
# (See "Crashes, logs, and traces" in the module docstring.)
# ---------------------------------------------------------------------------


@contextmanager
def crash_details_withheld(where):
    """Turn a crash inside the `with` block into a `ToolError` that carries nothing from it.

    Used around the two pieces of code the SDK runs for one tool call: the
    resolver (`ask_the_reviewer`) and the tool body. `where` names which one,
    for the log line.

    - A `ToolError` passes through unchanged. It is a refusal this module
      wrote for the caller (the rate limit, a refused `query_id`, an unusable
      answer), and the model needs its text to correct the call.
    - Anything else is a crash. It is logged as its exception TYPE only, at
      ERROR, with no message and no traceback, and replaced by a `ToolError`
      with the fixed `CRASH_MESSAGE`.
    - `from None` drops the crash from the new error's traceback. Without it,
      Python would attach the crash as the new error's context, and any
      printed traceback of the new error would end with the crash's message:
      "During handling of the above exception, another exception occurred".
    """
    try:
        yield
    except ToolError:
        raise
    except Exception as crash:
        logger.error(
            "%s crashed with %s (its message and traceback are withheld: they may quote a key or a URL)",
            where,
            type(crash).__name__,
        )
        raise ToolError(CRASH_MESSAGE) from None


# ---------------------------------------------------------------------------
# The adapter: one tool call against the Day 21 service.
# ---------------------------------------------------------------------------


def answer_question(service, query, role, query_id=None, decision=None):
    """Run one question through the Day 21 service. Returns a `QueryResponse`, or raises `ToolError`.

    This is the whole adapter. It is a plain function, apart from the MCP
    decorator below, so that a test can call it directly with a fake service
    (the first of the three test layers). The steps follow "One call, in
    order" in the module docstring.
    """
    # Day 21's own request model. The SDK has already checked the same
    # lengths and values against the tool's argument schema, so this always
    # passes on the MCP path. It is here so that HTTP and MCP run on ONE
    # request model: a rule added to `QueryRequest` later cannot be skipped
    # by this adapter.
    body = api.QueryRequest(query=query, role=role, query_id=query_id, decision=decision)

    # The rate limit, counted before anything else runs (as over HTTP). A
    # refused call is not counted, so retrying too early does not push the
    # wait further out.
    wait_seconds = service.rate_limiter.admit(STDIO_CLIENT)
    if wait_seconds is not None:
        raise ToolError(
            f"rate limit: at most {service.rate_limiter.max_requests} calls per "
            f"{service.rate_limiter.window_seconds} s. Retry in {math.ceil(wait_seconds)} s."
        )

    # The labeled-id check. `check_query_request` is the FastAPI dependency
    # behind `/query`, so it reports a refusal as `HTTPException(422)`, whose
    # `detail` is already written for the caller ("unknown query_id 'Q999':
    # ..."). Calling the same function keeps ONE rule: MCP only changes how the
    # refusal is delivered. `ToolError` puts that message in the result, where
    # the model reads it and can correct the call (for example, leave
    # `query_id` out).
    try:
        api.check_query_request(body, service)
    except HTTPException as refusal:
        raise ToolError(refusal.detail) from refusal

    # The one guarded pipeline, exactly as `POST /query` runs it. Its last
    # event is always ("result", QueryResponse): blocked and pending_approval
    # included.
    #
    # With LangSmith tracing OFF, whatever the environment says (see
    # "Crashes, logs, and traces"). `tracing_context` sets a context variable
    # that LangSmith checks before its environment variables, and LangGraph
    # carries it into every node it runs. `list(...)` runs the whole generator
    # inside the `with` block: a generator only runs while it is iterated.
    with tracing_context(enabled=False):
        events = list(api.run_query_events(service, body))
    _, response = events[-1]
    return response


# ---------------------------------------------------------------------------
# The reviewer: asked through MCP elicitation, only when Day 21 would wait.
# (See "Approval comes from the user, not from the model".)
# ---------------------------------------------------------------------------


def pending_approval_preview(service, body):
    """The `pending_approval` response Day 21 would give this request without a decision, or None.

    It runs NO retrieval, so the person can be asked before anything runs.
    It reuses Day 21's own pipeline instead of copying its order of checks:

    - `check_query_request` first, as the tool does. A refused `query_id` gets
      no question; the tool body refuses it a moment later, with Day 21's
      message;
    - then `run_query_events`, read only up to its approval boundary. It is a
      generator, and yields one event per stage: the entry guards come first,
      then a request that may pause ends with a `pending_approval` result,
      BEFORE the `retrieval_started` event. So stopping at `retrieval_started`
      runs exactly the entry guards and the approval boundary, in Day 21's
      order. Stopping there is safe: a generator runs only when it is asked
      for its next event, so the retrieval code after that event never starts.

    A blocked request ends with a `blocked` result, and gets None: an attack
    is reported as an attack, never shown to a person as a question.
    """
    try:
        api.check_query_request(body, service)
    except HTTPException:
        return None

    for event_name, payload in api.run_query_events(service, body):
        if event_name == "result":
            return payload if payload.status == "pending_approval" else None
        if event_name == "retrieval_started":
            return None  # it would retrieve now: no approval is needed, and nothing has run
    return None


def host_can_ask(ctx):
    """True if the host declared that it can show the user an elicitation FORM.

    A client declares its capabilities when it connects. Asking a host that
    did not declare elicitation would be a protocol error, not a question, so
    `ask_the_reviewer` checks first, and falls back to `pending_approval`.

    The rule is the SDK's own (`mcp.server.mcpserver.resolve`): a bare
    `elicitation: {}`, the only shape before the form/URL modes existed,
    counts as form support; a host that declared URL mode only does not.
    """
    capabilities = ctx.client_capabilities
    elicitation = capabilities.elicitation if capabilities is not None else None
    return elicitation is not None and (elicitation.form is not None or elicitation.url is None)


async def ask_the_reviewer(
    query: str, role: api.Role, query_id: str | None, ctx: Context[api.ProcureRAGService]
) -> ReviewerAnswer | Elicit[ReviewerAnswer] | None:
    """The resolver behind the tool's `review` parameter: ask the user, or decide there is nothing to ask.

    The SDK runs it before the tool body, and fills its parameters the way
    it fills a tool's: `query`, `role`, and `query_id` are the tool's own
    (already validated) arguments, matched by name, and `ctx` is the Context.

    It returns one of two things:

    - `Elicit(message, ReviewerAnswer)`: "ask the user this". The SDK sends the
      question, and the tool receives the outcome: the filled-in form, or a
      decline, or a cancel;
    - None: there is nothing to ask (the question would not wait for
      approval), or nobody to ask (the host cannot show a form). The tool then
      runs with no decision, exactly as Day 21 would.

    On the 2026-07-28 protocol, the SDK runs this function on both rounds of
    the call. The second time, it returns the same question, and the SDK
    matches it to the host's answer instead of asking again. So the message
    must come out the same both times. It does: it is built only from the
    request.
    """
    service = ctx.request_context.lifespan_context
    # The entry guards run here, before the tool body: a crash in them would
    # reach the SDK from this function.
    with crash_details_withheld("ask_the_reviewer"):
        pending = pending_approval_preview(service, api.QueryRequest(query=query, role=role, query_id=query_id))
    if pending is None or not host_can_ask(ctx):
        return None

    request = pending.approval_request  # the same object Day 21 returns with pending_approval
    return Elicit(
        "ProcureRAG may need a second, targeted retrieval pass to answer this question:\n\n"
        f"    {request.query}\n\n"
        f"Proposed follow-up query: {request.proposed_followup_query}\n\n"
        f"{request.note} Approve it, edit it (write your own follow-up query), or reject it.",
        ReviewerAnswer,
    )


# ---------------------------------------------------------------------------
# The tool: what a host discovers in `tools/list` and invokes with `tools/call`.
#
# The SDK reads the whole contract from this one function:
# - the tool NAME is the function name;
# - the DESCRIPTION the model reads is the docstring;
# - the ARGUMENT schema comes from the type hints. `Annotated[..., Field(...)]`
#   adds a description and limits per argument. A parameter with a default is
#   optional. `ctx` is injected by the SDK, and `review` is filled by its
#   resolver, so neither appears in the schema: the model cannot set them;
# - the RESULT schema (`output_schema`) comes from the return annotation,
#   `api.QueryResponse`. The SDK also checks the returned value against it.
#
# A plain `def`, not `async def`, for Day 21's reason: the pipeline is
# synchronous, CPU-bound work (embedding, reranking). The SDK runs a plain
# `def` tool in a worker thread, so the server's event loop stays free.
# ---------------------------------------------------------------------------


@server.tool(
    title="Answer a procurement question",
    # A hint for the host, not a security control (a host may ignore it). It
    # is accurate: the tool writes nothing, sends nothing, and stores nothing,
    # so a host may run it without asking first. `open_world_hint` is left
    # unset on purpose: with the live LLM switched on, a call does reach an
    # outside provider.
    annotations=ToolAnnotations(read_only_hint=True),
)
def answer_procurement_question(
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=api.MAX_QUERY_CHARS,
            description="The procurement question, in plain words.",
        ),
    ],
    role: Annotated[
        api.Role,
        Field(
            description=(
                "Who is asking: 'requester' (any employee; sees Internal documents) or 'buyer' (procurement "
                "staff; also sees Confidential supplier contracts). Asserted by the caller, not authenticated: "
                "use the role the user actually has."
            )
        ),
    ],
    ctx: Context[api.ProcureRAGService],
    # Filled by `ask_the_reviewer`, never by the model. `ElicitationResult[...]`
    # asks for the whole outcome (accepted, declined, or cancelled), so the
    # body below decides what each one means.
    review: Annotated[ElicitationResult[ReviewerAnswer], Resolve(ask_the_reviewer)],
    query_id: Annotated[
        str | None,
        Field(
            description=(
                "Evaluation replay only: one of ProcureRAG's 93 labeled question ids (e.g. 'Q001'), sent with "
                "that question's exact text. Leave it out for every other question."
            )
        ),
    ] = None,
) -> api.QueryResponse:
    """Answer a question about Vantera's procurement policies, procedures, and supplier contracts, with sources.

    Every call runs ProcureRAG's guarded pipeline: input guards (prompt injection, PII redaction, procurement
    scope), a confidentiality filter for the caller's role, a human-approval gate, and an output guard that
    withholds uncited answers. When a question needs a second retrieval pass, the server asks the USER to
    approve, edit, or reject it, in a form the host shows. There is no argument for that decision: never
    invent one. Read `status` first:

    - answered: `text` is the answer. Its [n] citations refer to `sources` by `source_id`.
    - not_generated: the evidence was found (see `sources`), but this server runs without a live LLM, so no
      answer text was written.
    - gap_report / model_declined: no answer could be built from the evidence. `text` says why.
    - blocked: a guard refused the question or withheld the answer. `text` and `findings` say which.
    - pending_approval: nothing has run. A person's decision was needed and none came: `text` says why. Do not
      call again unless the user asks to be asked again.
    """
    # What `lifespan` yielded: the one service this process built at startup.
    service = ctx.request_context.lifespan_context

    # The whole body: a crash anywhere in it (the LLM provider included)
    # reaches the SDK as `CRASH_MESSAGE`, never as its own text.
    with crash_details_withheld("answer_procurement_question"):
        # The user's answer, if there is one. `AcceptedElicitation` with no
        # data is the resolver's None: nothing was asked, so no decision is
        # passed.
        decision = None
        if isinstance(review, AcceptedElicitation) and review.data is not None:
            try:
                decision = review.data.as_decision()
            except ValidationError as error:
                # Day 18's rule refused the answer (an edit with no follow-up
                # query). An error result, so the host can ask again.
                reason = error.errors()[0]["msg"]
                raise ToolError(f"the reviewer's answer is not a decision ProcureRAG can run: {reason}") from error

        response = answer_question(service, query, role, query_id=query_id, decision=decision)

        # With no decision, a question that may pause ends at
        # `pending_approval`, before anything runs (Day 21's fail-closed
        # rule). Its text is replaced, to say why no decision came.
        if response.status == "pending_approval":
            user_said_no = isinstance(review, DeclinedElicitation | CancelledElicitation)
            text = NOT_DECIDED_MESSAGE if user_said_no else CANNOT_ASK_MESSAGE
            response = response.model_copy(update={"text": text})
        return response


if __name__ == "__main__":
    # No argument: the stdio transport. It blocks for the life of the server.
    # Under the `__main__` guard because `mcp run`, `mcp dev`, and the tests
    # IMPORT this file, and an import must not start a server.
    server.run()
