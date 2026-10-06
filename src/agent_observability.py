"""Day 19 (Block 3A): structured trace rows and a structured result for the Day 18 graph.

**What Day 18 left unstructured.** `agent_control_plane.py` can pause, resume,
and replay a run, but its evidence is printed text: `state["trace"]` lines,
the approval request, and a checkpoint table. That is fine for a human
reading one run. It falls short in three ways:

- It cannot be compared across runs. Nothing is saved once the process
  exits, and comparing two runs means re-reading two terminal logs.
- It cannot be validated. Nothing checks that a run's output has the
  fields a reviewer, a UI, or an eval needs, or that their values make sense.
- The final answer is an ad hoc string. Downstream code can only tell
  "answered" from "refused" from "no LLM ran" by scraping prose such as
  `"[not generated: ..."` or `"Not answered: ..."`.

**Two contracts, both Pydantic models.**

1. `AgentResult`: the structured OUTPUT of one run, i.e. what downstream code
   consumes. An explicit `status` (`answered` / `model_declined` /
   `gap_report` / `not_generated`), an `evidence_status`, the missing
   evidence by name, a checked citation report, caveats, and `run_id`, the
   handle back to the trace row that explains it.
2. `AgentRunTrace`: one TRACE ROW per finished run, i.e. how the result came
   to be. Run metadata, the route, the HITL decision, one entry per retrieval
   pass (query, config, chunks added), the before/after diagnoses, the
   result, Day 18's human-readable trace lines, and the LangSmith handle.

Rows are written as JSONL, one JSON object per line
(`write_trace_rows` / `read_trace_rows`), so the evidence outlives the
process and two runs can be compared field by field.

**Observe, don't change.** This module never edits a node, a router, or
the retrieval policy. It runs the unchanged Day 18 graph
(`build_controlled_graph`) and reads what the graph already produced:

- the final state, returned by `graph.invoke`;
- the pass-1 context, read back from the checkpointer
  (`pass_one_sources_from_history`). The final state only holds the MERGED
  context, but Day 18's checkpointer saved a snapshot after every step, so
  the "before" context is still there.

**Why Pydantic, when Day 17 already has a `TypedDict` state?** A `TypedDict`
is only a type hint, and nothing checks it while the program runs:
`{"stop_reason": "gave_up"}` is accepted silently. A Pydantic `BaseModel`
validates when it is built. Wrong types, unknown enum values, missing
fields, and unknown keys raise a `ValidationError` that names the exact
field. That turns "the output drifted" from a silent bug into a loud,
testable failure. Pydantic also gives three things a TypedDict can't:

- JSON serialization (`model_dump_json`);
- JSON parsing with validation (`model_validate_json`);
- a JSON Schema (`model_json_schema`), the same kind of schema that
  OpenAI Structured Outputs and LangChain's `create_agent(response_format=...)`
  hand to a model.

**Structured generation (the Q092 fix).** The first live `--generate` run
(2026-10-05) exposed a hole. Q092 had complete evidence, the model replied
in prose that "the sources do not contain enough information", and the
result was labeled `answered`, because the old wrapper could only see that
an LLM had produced some text. Now `structured_generate_node` makes the LLM
answer in the `generation.GeneratedAnswer` schema, so "I could not answer
from these sources" arrives as a boolean field
(`answerable_from_sources`), enforced by the provider (`response_format`
json_schema, strict) and validated again here. `build_result` maps a `false`
to the new status `model_declined`. The two parts of the result now come
from two contracts:

- the graph's own state (route, evidence) fills the deterministic part;
- the model's structured reply fills its verdict.

**Local evidence vs. LangSmith.** The JSONL rows are the CI-safe evidence:
they need no credentials, and every test builds them with fakes. LangSmith is
the live, SaaS view of the same runs. It is switched on only by environment
variables (`LANGSMITH_TRACING_V2=true` + `LANGSMITH_API_KEY`, loaded from
`.env` by `main()`). When it is on, each row records the LangSmith project
and the ids of the root runs it produced, so the local row and the SaaS trace
point at each other (see `run_and_trace`).

**Honest limits.**

- Same eval-time limitation as Day 16-18: `evidence_status` comes from the
  gold-label diagnosis (`relevance_grades`), so it only exists for the 93
  labeled queries.
- `status="answered"` plus `citations.passed=True` means "the answer cites
  real retrieved sources". It does NOT mean "the answer is complete". That is
  an eval question, measured elsewhere.
"""

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from langgraph.types import Command
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from agent_control_plane import (
    DECISION_APPROVE,
    DECISION_EDIT,
    DECISION_REJECT,
    build_controlled_graph,
    thread_config,
)
from agent_graph import (
    MAX_RETRIEVAL_PASSES,
    ROUTE_GENERATE,
    ROUTE_REPORT_GAP,
    generate_node,
    make_initial_state,
)
from agentic_retrieval import (
    STOP_FIXED_AFTER_SECOND_PASS,
    STOP_NO_MISSING_EVIDENCE,
    TRIGGER_MISSING_CHUNK,
    TRIGGER_MISSING_DOC,
)
from generation import INSUFFICIENT_EVIDENCE_ANSWER, generate_structured_answer
from generation_eval import context_doc_ids

# ---------------------------------------------------------------------------
# Vocabulary. Each `Literal[...]` type lists the ONLY values a field may
# hold. Pydantic rejects anything else, including a different spelling or
# letter case ("Answered" is not "answered").
#
# The values are written out as plain strings because the typing spec only
# allows literal values inside `Literal[...]`. `Literal[STOP_...]` with a
# constant happens to work at runtime, but type checkers (e.g. VS Code's
# Pylance) flag it. The Day 16-18 vocabularies still have ONE source of
# truth, the constants in those modules:
# `test_schema_vocabularies_match_the_graph_constants` fails if a constant is
# ever renamed and the matching value here is not.
# ---------------------------------------------------------------------------

# agent_graph.ROUTE_GENERATE / ROUTE_RECURSIVE_RETRIEVE / ROUTE_REPORT_GAP
RouteLabel = Literal["generate", "recursive_retrieve", "report_gap"]

# Day 16's four stop reasons (agentic_retrieval.STOP_*), plus Day 18's
# reviewer rejection (agent_control_plane.STOP_FOLLOWUP_REJECTED).
StopReason = Literal[
    "no_missing_evidence",
    "fixed_after_second_pass",
    "trigger_detected_no_followup_query_defined",
    "still_missing_after_max_passes",
    "followup_rejected_by_reviewer",
]

# agentic_retrieval.TRIGGER_MISSING_DOC / TRIGGER_MISSING_CHUNK
TriggerReason = Literal["missing_doc", "missing_chunk"]

# agent_control_plane.DECISION_APPROVE / DECISION_EDIT / DECISION_REJECT
ReviewerDecision = Literal["approve", "edit", "reject"]

# New in Day 19: WHAT the run produced. Downstream code switches on this
# field instead of parsing the answer text.
#
# Two different "refusals" are kept apart on purpose:
# - `gap_report`: the GRAPH refused. Its gold-label diagnosis found evidence
#   missing, so no LLM was called.
# - `model_declined`: the graph found the evidence complete and called the
#   LLM, but the MODEL said the sources were not enough (Q092 on 2026-10-05).
#   Retrieval and generation fail independently, so each failure gets its
#   own value.
STATUS_ANSWERED = "answered"  # the LLM answered from complete evidence
STATUS_MODEL_DECLINED = "model_declined"  # complete evidence, but the LLM said it could not answer from it
STATUS_GAP_REPORT = "gap_report"  # evidence still missing: the graph refused and named the gap
STATUS_NOT_GENERATED = "not_generated"  # evidence complete, but no LLM call was made (no client, or an empty context)
ResultStatus = Literal["answered", "model_declined", "gap_report", "not_generated"]

# New in Day 19: the state of the evidence in the FINAL context. It mirrors
# Day 16's trigger priority: a missing document outranks a missing chunk.
#
# A reviewer rejection is deliberately NOT an evidence status. It is a reason
# the run STOPPED (`stop_reason="followup_rejected_by_reviewer"`). The
# evidence itself is still just "missing docs" or "missing chunks". Keeping
# the two fields orthogonal means neither one has to encode the other.
EVIDENCE_COMPLETE = "complete"
EVIDENCE_MISSING_DOCS = "missing_docs"
EVIDENCE_MISSING_CHUNKS = "missing_chunks"
EvidenceStatus = Literal["complete", "missing_docs", "missing_chunks"]

# The trace row's format version. Bump it whenever a field is added, removed,
# or changes meaning, or a value is added. Each row then says which contract
# it was written under, so an old JSONL file is never silently misread by
# newer code.
#
#   v1 (2026-10-05): first version.
#   v2 (2026-10-05): added status "model_declined" (the Q092 fix).
#   v3 (2026-10-06): "not_generated" now means "no LLM call was made": no
#       client wired in, OR an empty context. v2 labeled an empty context
#       "model_declined", although no model had been asked. No field or
#       value was added; one value's meaning widened.
#
# Writers always write the CURRENT version. Readers accept every version
# they understand (`READABLE_SCHEMA_VERSIONS`), and check each row against
# the vocabulary of the version it CLAIMS: a v1 row may not use
# "model_declined", which v1 did not have (see `AgentRunTrace`). A meaning
# change like v3's can't be checked row by row. A reader that cares reads
# "not_generated" on a v1/v2 row as "no client". A change that removed or
# renamed a field would instead need a migration step, or a reader that
# rejects the old version.
TRACE_SCHEMA_VERSION = 3
READABLE_SCHEMA_VERSIONS = Literal[1, 2, 3]


# ---------------------------------------------------------------------------
# The models. The fields have no default values on purpose: the producer must
# state every one of them explicitly, so a forgotten field fails loudly
# instead of quietly taking a default. A field typed `X | None` is still
# REQUIRED: the producer has to say `None` out loud, e.g. "this run had no
# approval".
# ---------------------------------------------------------------------------


class ContractModel(BaseModel):
    """Base class for every Day 19 model: unknown keys are an error.

    Pydantic's default (`extra="ignore"`) silently DROPS keys it does not
    know. Here that would mean a misspelled key like `stop_reson` vanishes
    without a word. `extra="forbid"` reports it by name instead. It also
    makes the JSON Schema say `"additionalProperties": false`, which is what
    provider-native structured output (e.g. OpenAI's strict mode) requires.
    """

    model_config = ConfigDict(extra="forbid")


class RetrievalPass(ContractModel):
    """One retrieval pass, described by what it did to the context.

    Pass 1 runs the buyer's question. Pass 2 (Q091/Q092 only) runs the
    approved or edited follow-up. Because Day 16's merge is additive-only,
    "what pass 2 added" is exactly the chunks appended after the pass-1
    context. Those chunks are the evidence a Q091/Q092 review is about.
    """

    pass_number: int = Field(ge=1, le=MAX_RETRIEVAL_PASSES)
    query_text: str  # the text actually sent to retrieval on this pass
    retrieval_config: dict[str, int | None]  # pool_size / top_k / max_chunks_per_document (None = no cap)
    added_chunk_ids: list[str]  # chunks this pass ADDED to the context, in context order
    context_size_after: int = Field(ge=0)  # number of sources in the context after this pass
    context_doc_ids_after: list[str]  # sorted doc ids present in the context after this pass


class EvidenceDiagnosis(ContractModel):
    """One `diagnose` node result: Day 17's diagnosis dict, now type-checked.

    The field names match the dict `agent_graph.diagnose_node` writes, so
    Pydantic can validate that dict directly. `diagnoses[0]` is the "before"
    evidence (after pass 1) and `diagnoses[-1]` the "after".
    """

    after_pass: int = Field(ge=1, le=MAX_RETRIEVAL_PASSES)
    missing_doc_ids: list[str]
    missing_chunk_ids: list[str]
    trigger_reason: TriggerReason | None  # None = nothing missing


class ApprovalRecord(ContractModel):
    """Day 18's `approval` dict: what the reviewer decided at the HITL pause."""

    decision: ReviewerDecision
    proposed_followup_query: str
    approved_followup_query: str | None  # None after a reject
    message: str | None  # the reviewer's optional reason


class CitationCheck(ContractModel):
    """`generation.validate_citations`' report, plus an explicit pass/fail flag.

    `passed` encodes Day 10's citation contract: "every citation marker maps
    to a source id ... no orphan citations and no uncited source claims".
    Concretely, at least one citation points at a real source, and no
    citation points at a source that was never retrieved.
    """

    cited_ids: list[int]  # every [n] the answer cites
    valid_ids: list[int]  # cited AND present in the context
    orphan_ids: list[int]  # cited but NOT in the context: a hallucinated citation
    uncited_ids: list[int]  # in the context but never cited
    passed: bool

    @model_validator(mode="after")
    def _passed_must_agree_with_the_lists(self):
        """A summary flag has to agree with the data it summarizes.

        `mode="after"` runs this once every field has passed its own type
        check, so it can compare fields with each other. Without it, a
        producer (or later an LLM filling in this schema) could claim
        `passed=True` next to a non-empty `orphan_ids`, and a UI that only
        reads the flag would show a green tick on a hallucinated citation.
        """
        expected = bool(self.valid_ids) and not self.orphan_ids
        if self.passed != expected:
            raise ValueError(
                f"passed={self.passed} contradicts valid_ids={self.valid_ids} / orphan_ids={self.orphan_ids}: "
                "passed means at least one valid citation and no orphan citations"
            )
        return self


class AgentResult(ContractModel):
    """The structured OUTPUT of one graph run: what a UI, an eval, or an API returns.

    Before Day 19, downstream code had to read `state["answer"]` and guess
    which kind of string it was. Now `status` says it directly, and the other
    fields are machine-checkable instead of buried in prose.
    """

    run_id: UUID  # audit handle: the `AgentRunTrace.run_id` that explains this result
    status: ResultStatus
    evidence_status: EvidenceStatus
    text: str  # for humans: the answer, the model's decline, the gap report, or the not-generated marker
    missing_doc_ids: list[str]  # from the FINAL diagnosis; empty when evidence is complete
    missing_chunk_ids: list[str]
    citations: CitationCheck | None  # present only when an LLM wrote `text` ("answered" / "model_declined")
    caveats: list[str]  # things a reader should know before trusting `text`

    @model_validator(mode="after")
    def _status_must_agree_with_the_evidence(self):
        """The core safety contract of the graph, written as data rules.

        1. `evidence_status` must agree with the missing-id lists.
        2. Only a `gap_report` may have incomplete evidence, and a
           `gap_report` must have it. The graph never calls the LLM on
           missing evidence, and never refuses by itself on complete evidence.
           (`model_declined` is the MODEL refusing, on complete evidence.)
        3. A citation report exists if, and only if, an LLM wrote the text
           (`answered` or `model_declined`). A decline can still cite what it
           did find.
        """
        nothing_missing = not self.missing_doc_ids and not self.missing_chunk_ids
        evidence_complete = self.evidence_status == EVIDENCE_COMPLETE

        if evidence_complete != nothing_missing:
            raise ValueError(
                f"evidence_status={self.evidence_status!r} contradicts missing_doc_ids={self.missing_doc_ids} "
                f"/ missing_chunk_ids={self.missing_chunk_ids}"
            )
        if self.status == STATUS_GAP_REPORT and evidence_complete:
            raise ValueError("a 'gap_report' must name missing evidence, but evidence_status is 'complete'")
        if self.status != STATUS_GAP_REPORT and not evidence_complete:
            raise ValueError(
                f"status {self.status!r} needs complete evidence, but evidence_status is "
                f"{self.evidence_status!r}: only a 'gap_report' may have missing evidence"
            )
        llm_wrote_the_text = self.status in (STATUS_ANSWERED, STATUS_MODEL_DECLINED)
        if llm_wrote_the_text != (self.citations is not None):
            raise ValueError(
                "citations must be present for status 'answered'/'model_declined' (an LLM wrote the text) "
                "and absent (None) otherwise"
            )
        return self


class LangSmithHandle(ContractModel):
    """Where to find this run in LangSmith. Only set when tracing was on.

    One `graph.invoke` becomes one root run (one trace) in LangSmith. A run
    that paused for approval was invoked twice (the first call, then the
    resume), so it has two root run ids. The shared `thread_id` (added to
    the metadata of both by LangGraph) groups them in the LangSmith UI.
    """

    project: str
    root_run_ids: list[UUID] = Field(min_length=1)


class AgentRunTrace(ContractModel):
    """One JSONL row = one FINISHED graph run: how its result was produced."""

    # --- Run metadata: which run is this, and from which code? ---
    schema_version: READABLE_SCHEMA_VERSIONS  # run_and_trace always writes TRACE_SCHEMA_VERSION
    run_id: UUID  # this row's own id (not a LangSmith id, see `langsmith`)
    thread_id: str  # the checkpointer key: `graph.get_state_history(thread_config(thread_id))`
    created_at: AwareDatetime  # timezone REQUIRED: naive timestamps can't be compared across machines
    code_version: str | None  # `git describe --always --dirty`, e.g. "fc228a7-dirty"
    query_id: str
    query_type: str
    query: str

    # --- Control flow: which path did the graph take, and why did it stop? ---
    route_history: list[RouteLabel] = Field(min_length=1)
    stop_reason: StopReason
    approval: ApprovalRecord | None  # None = the run never paused for approval

    # --- Evidence: what each pass retrieved, and what was still missing ---
    retrieval_passes: list[RetrievalPass] = Field(min_length=1, max_length=MAX_RETRIEVAL_PASSES)
    diagnoses: list[EvidenceDiagnosis] = Field(min_length=1, max_length=MAX_RETRIEVAL_PASSES)

    # --- Outcome, Day 18's human-readable lines, and the live handle ---
    result: AgentResult
    trace_lines: list[str]  # `state["trace"]`, unchanged: one line per node that ran
    langsmith: LangSmithHandle | None  # None = tracing was off, nothing was sent

    @model_validator(mode="after")
    def _must_describe_one_finished_run(self):
        """Rules that span the row and its nested result.

        - The result's `run_id` must point back at THIS row. Otherwise the
          audit handle on the result leads to the wrong run.
        - The route must end on an end node (`generate` or `report_gap`). A run
          still paused at the approval point has no outcome yet, so it is not
          a finished trace row.
        - An LLM-written result (one with a citation report) needs a
          non-empty final context. Day 10's grounding rule never sends an
          empty context to a model, so an "answer" or a "decline" on zero
          sources cannot have come from one.
        """
        if self.result.run_id != self.run_id:
            raise ValueError(f"result.run_id {self.result.run_id} does not match the row's run_id {self.run_id}")
        if self.route_history[-1] not in (ROUTE_GENERATE, ROUTE_REPORT_GAP):
            raise ValueError(
                f"route_history {self.route_history} does not end on 'generate' or 'report_gap': "
                "a trace row must describe a finished run"
            )
        if self.result.citations is not None and self.retrieval_passes[-1].context_size_after == 0:
            raise ValueError(
                f"status {self.result.status!r} says an LLM wrote the text, but the final context is empty: "
                "no model is ever called on an empty context"
            )
        return self

    @model_validator(mode="after")
    def _must_use_only_its_own_versions_vocabulary(self):
        """Check the row against the contract of the version it CLAIMS.

        Accepting old versions is only half of schema evolution. The other
        half: an old row must not use a value its version did not have yet.
        `model_declined` was added in v2, so a v1 row carrying it was not
        written by v1 code. It was edited by hand or mislabeled, and it is
        rejected instead of being read as if it were fine.
        """
        if self.schema_version < 2 and self.result.status == STATUS_MODEL_DECLINED:
            raise ValueError("status 'model_declined' was added in schema_version 2: a v1 row cannot carry it")
        return self


# ---------------------------------------------------------------------------
# Builders: graph state (plain dicts) -> validated models.
#
# Every model is built through its constructor, so validation runs at the
# moment the row is built. If the graph ever produced something outside the
# contract (a new stop reason nobody added here, a diagnosis with an extra
# key), the build fails at once with a ValidationError naming the field. The
# problem does not wait to be discovered in a dashboard weeks later.
# ---------------------------------------------------------------------------


def build_result(final_state, run_id):
    """Turn the graph's final state into an `AgentResult`.

    Each field comes from state the graph already wrote:

    - `status`, checked in this order:
      1. The last route was `report_gap`: the graph refused (`gap_report`).
      2. There is no citation report: no LLM call was made
         (`not_generated`). `structured_generate_node` writes
         `citations=None` exactly when it makes no call: no client wired in,
         or an empty context. That is an implicit convention, and this field
         replaces it with an explicit one. (Day 17's plain node writes
         `None` only for "no client". With a client and an empty context it
         returns a citation report for its fixed refusal, and
         `AgentRunTrace` then rejects the row instead of letting it pass as
         `answered`. Day 19 never runs that node with a client.)
      3. The model's structured verdict `answerable_from_sources` is
         `False`: it declined (`model_declined`). This is read from a FIELD
         the model filled in, never from the wording of its answer. The key
         is absent when Day 17's plain-text generate node was used. Then
         there is no verdict, and the run counts as `answered`, as in v1.
      4. Otherwise: `answered`.
    - `evidence_status` and the missing ids: the FINAL diagnosis.
    - `caveats`: the Day 18 reviewer decision, orphan citations, and an
      empty context, i.e. facts a reader should know before trusting `text`.
    """
    final_diagnosis = final_state["diagnoses"][-1]
    approval = final_state.get("approval")  # absent unless the run paused (see Day 18's `NotRequired`)
    citations = final_state["citations"]

    if final_state["route_history"][-1] == ROUTE_REPORT_GAP:
        status = STATUS_GAP_REPORT
    elif citations is None:
        status = STATUS_NOT_GENERATED
    elif final_state.get("answerable_from_sources") is False:  # `is False`: absent (None) must not count
        status = STATUS_MODEL_DECLINED
    else:
        status = STATUS_ANSWERED

    # Same priority as Day 16's `decide_trigger`: a missing doc outranks a missing chunk.
    if final_diagnosis["trigger_reason"] == TRIGGER_MISSING_DOC:
        evidence_status = EVIDENCE_MISSING_DOCS
    elif final_diagnosis["trigger_reason"] == TRIGGER_MISSING_CHUNK:
        evidence_status = EVIDENCE_MISSING_CHUNKS
    else:
        evidence_status = EVIDENCE_COMPLETE

    caveats = []
    if approval is not None and approval["decision"] == DECISION_EDIT:
        caveats.append(
            f"the follow-up query was edited by a reviewer: {approval['proposed_followup_query']!r} "
            f"-> {approval['approved_followup_query']!r}"
        )
    if approval is not None and approval["decision"] == DECISION_REJECT:
        caveats.append(
            f"a reviewer rejected the follow-up retrieval pass: {approval['message'] or 'no reason given'}"
        )
    if citations is not None and citations["orphan_ids"]:
        caveats.append(f"the answer cites source id(s) {citations['orphan_ids']} that were not in the retrieved context")
    if status == STATUS_NOT_GENERATED and not final_state["sources"]:
        # Says WHO stopped the run: retrieval came back empty, not "no client
        # configured" and not the model refusing.
        caveats.append("no LLM was called because the retrieved context was empty")

    citation_check = None
    if citations is not None:
        # `**citations` unpacks the four lists from `validate_citations`;
        # `passed` is the one field this module adds on top.
        citation_check = CitationCheck(
            **citations,
            passed=bool(citations["valid_ids"]) and not citations["orphan_ids"],
        )

    return AgentResult(
        run_id=run_id,
        status=status,
        evidence_status=evidence_status,
        text=final_state["answer"],
        missing_doc_ids=final_diagnosis["missing_doc_ids"],
        missing_chunk_ids=final_diagnosis["missing_chunk_ids"],
        citations=citation_check,
        caveats=caveats,
    )


def build_retrieval_passes(final_state, pass_one_sources):
    """Rebuild one `RetrievalPass` per pass from the pass-1 and final contexts.

    This works because Day 16's `merge_sources` is additive-only. The
    final context is the pass-1 sources, unchanged and in the same order,
    followed by the chunks pass 2 appended. So everything after
    `len(pass_one_sources)` was added by pass 2. A chunk pass 2 returned
    that was ALREADY in context is not counted as "added", because it added
    no new evidence.
    """
    config = final_state["retrieval_config"]

    passes = [
        RetrievalPass(
            pass_number=1,
            query_text=final_state["query"],
            retrieval_config=config,
            added_chunk_ids=[source["chunk_id"] for source in pass_one_sources],
            context_size_after=len(pass_one_sources),
            context_doc_ids_after=sorted(context_doc_ids(pass_one_sources)),
        )
    ]

    if final_state["retrieval_passes"] > 1:
        final_sources = final_state["sources"]
        added_sources = final_sources[len(pass_one_sources):]
        passes.append(
            RetrievalPass(
                pass_number=2,
                # After an "edit", Day 18 overwrote `followup_query` with the
                # reviewer's text, so this is the query that ACTUALLY ran.
                # The original proposal is kept in `approval`.
                query_text=final_state["followup_query"],
                retrieval_config=config,  # pass 2 reuses pass 1's config unchanged (Day 16 contract)
                added_chunk_ids=[source["chunk_id"] for source in added_sources],
                context_size_after=len(final_sources),
                context_doc_ids_after=sorted(context_doc_ids(final_sources)),
            )
        )

    return passes


def pass_one_sources_from_history(graph, config):
    """Read the pass-1 context back from the checkpointer.

    The final state only holds the MERGED context. But Day 18's
    checkpointer saved a snapshot after every step, and `sources` only
    changes in `retrieve` (which sets `retrieval_passes=1`) and in
    `recursive_retrieve` (which sets it to 2). So any snapshot with
    `retrieval_passes == 1` still holds pass 1's context exactly as it was.
    The checkpointer is doing double duty here: it is the HITL resume store,
    and also the place this module reads "before" evidence from, without
    adding a single line to the graph.
    """
    for snapshot in graph.get_state_history(config):  # newest snapshot first
        if snapshot.values.get("retrieval_passes") == 1:
            return snapshot.values["sources"]
    raise ValueError(f"no pass-1 snapshot on thread {config['configurable']['thread_id']!r}")


# ---------------------------------------------------------------------------
# Structured generation: the `generate` node Day 19 runs.
# ---------------------------------------------------------------------------


def structured_generate_node(state, client):
    """Day 17's `generate` node, except the LLM must answer in the `GeneratedAnswer` schema.

    Everything about the graph stays the same: it is still the node called
    "generate", reached only on complete evidence, with the same stop
    reasons, route label, and `citations` report. The one difference is
    that the model's verdict, "could I answer from these sources?", comes
    back as the boolean `answerable_from_sources` and is written to state,
    where `build_result` reads it.

    With no client (tests, the default demo), it delegates to Day 17's own
    node, so the "not generated" behavior is exactly the same as before.

    Rule: `answerable_from_sources` is written ONLY after a real model call.
    Every path without a call writes `citations=None` and no verdict, so
    `build_result` labels it `not_generated`, never `model_declined`.
    """
    if client is None:
        return generate_node(state, client=None)

    # Same rule as Day 17's node: the router only sends a run here on
    # complete evidence, so the only question is "after one pass or two?".
    passes = state["retrieval_passes"]
    stop_reason = STOP_NO_MISSING_EVIDENCE if passes == 1 else STOP_FIXED_AFTER_SECOND_PASS

    if not state["sources"]:
        # Day 10's grounding rule: an empty context is never sent to a model.
        # The evidence can still count as "complete" here when the gold labels
        # require no document at all. The live retriever always returns
        # sources, so this needs a fake or broken retriever, but it must
        # still be labeled honestly: no call was made, so there is no model
        # verdict (a 2026-10-06 review found v2 calling this "model_declined").
        return {
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "citations": None,  # "no LLM wrote this text" -> `not_generated`
            "stop_reason": stop_reason,
            "route_history": [ROUTE_GENERATE],
            "trace": [
                f"generate (structured): evidence complete after {passes} pass(es), "
                "but the context is empty -> no LLM call"
            ],
        }

    result = generate_structured_answer(state["query"], state["sources"], client)
    citations = result["citations"]
    verdict = "answered" if result["answerable_from_sources"] else "MODEL DECLINED (sources insufficient)"

    return {
        "answer": result["answer"],
        "citations": citations,
        "answerable_from_sources": result["answerable_from_sources"],
        "stop_reason": stop_reason,
        "route_history": [ROUTE_GENERATE],
        "trace": [
            f"generate (structured): evidence complete after {passes} pass(es) -> {verdict}, "
            f"citing sources {citations['valid_ids']}, orphan citations {citations['orphan_ids']}"
        ],
    }


def build_observed_graph(retrieve_fn, client=None):
    """The graph Day 19 runs: Day 18's controlled graph, with structured generation.

    Same nodes, edges, routers, approval point, and checkpointer as
    `build_controlled_graph`. Only the function behind the `generate` node
    is swapped. `client` must return `GeneratedAnswer` JSON text (live:
    `make_openrouter_client(response_model=GeneratedAnswer)`).
    """
    return build_controlled_graph(retrieve_fn, client=client, generate_node_fn=structured_generate_node)


# ---------------------------------------------------------------------------
# Running one query and producing its row.
# ---------------------------------------------------------------------------


def _invoke_config(base_config, trace_row_id, query_id):
    """The config for ONE `graph.invoke` call, plus the LangSmith root run id it will create.

    `run_id` in a LangChain/LangGraph config sets the id of the ROOT run
    that call creates. That is the id a LangSmith trace is filed under.
    Choosing it up front, instead of letting LangChain generate a random one,
    is what lets the local row record exactly which LangSmith trace to open.

    `metadata` goes the other way. LangSmith stores it on the run, so a trace
    found in the LangSmith UI can be traced back to its local row
    (`trace_row_id`) and filtered by `query_id`.
    """
    root_run_id = uuid4()
    config = {
        **base_config,  # Day 18's thread_config: the thread_id + tags
        "run_id": root_run_id,
        "tags": [*base_config["tags"], "day19-observability"],
        "metadata": {"trace_row_id": str(trace_row_id), "query_id": query_id},
    }
    return config, root_run_id


def run_and_trace(graph, query_row, decision=None, *, case_overrides=None, code_version=None, langsmith_project=None):
    """Run one labeled query through the controlled graph and return its validated trace row.

    1. Give the run a fresh `run_id` (this row) and `thread_id` (its
       checkpointer key). A unique thread per run means one compiled graph
       can trace many queries without their checkpoints mixing.
    2. Invoke the graph. If it pauses at Day 18's approval point, resume it
       once with `decision` (default: approve). A non-pausing run (the 76
       `generate` and 15 `report_gap` queries) finishes in one call, and
       `decision` is never used.
    3. Read the pass-1 context back from the checkpointer.
    4. Build the row. Validation runs right here: if the graph produced
       anything outside the contract, this raises `pydantic.ValidationError`.

    `langsmith_project` is passed in rather than read from the environment
    here, so tests never depend on environment variables or credentials.
    `main()` sets it only when tracing is actually on. When it is None, the
    row's `langsmith` field is None, because recording run ids that were never
    sent anywhere would be a handle pointing at nothing.
    """
    if decision is None:
        decision = {"type": DECISION_APPROVE}

    run_id = uuid4()
    query_id = query_row["query_id"]
    thread_id = f"{query_id}-{run_id.hex[:8]}"  # readable in LangSmith's thread view, unique per run
    base_config = thread_config(thread_id)

    first_config, first_root_run_id = _invoke_config(base_config, run_id, query_id)
    final_state = graph.invoke(make_initial_state(query_row, case_overrides), first_config)
    root_run_ids = [first_root_run_id]

    if "__interrupt__" in final_state:
        # Paused before `recursive_retrieve`: answer the pending approval request.
        resume_config, resume_root_run_id = _invoke_config(base_config, run_id, query_id)
        final_state = graph.invoke(Command(resume=decision), resume_config)
        root_run_ids.append(resume_root_run_id)

    if "__interrupt__" in final_state:
        # Day 18 re-asks instead of raising when a decision is malformed, so
        # the run is STILL paused and has no outcome to record.
        error = final_state["__interrupt__"][0].value.get("error")
        raise ValueError(f"{query_id}: still paused after resuming with {decision!r} ({error})")

    pass_one_sources = pass_one_sources_from_history(graph, base_config)

    langsmith = None
    if langsmith_project is not None:
        langsmith = LangSmithHandle(project=langsmith_project, root_run_ids=root_run_ids)

    return AgentRunTrace(
        schema_version=TRACE_SCHEMA_VERSION,
        run_id=run_id,
        thread_id=thread_id,
        created_at=datetime.now(timezone.utc),
        code_version=code_version,
        query_id=query_id,
        query_type=query_row["query_type"],
        query=query_row["query"],
        route_history=final_state["route_history"],
        stop_reason=final_state["stop_reason"],
        # `approval` and `diagnoses` are passed as the plain dicts the graph
        # wrote. Pydantic converts each dict into its model (`ApprovalRecord`,
        # `EvidenceDiagnosis`) and checks every key and value on the way in.
        approval=final_state.get("approval"),
        retrieval_passes=build_retrieval_passes(final_state, pass_one_sources),
        diagnoses=final_state["diagnoses"],
        result=build_result(final_state, run_id),
        trace_lines=final_state["trace"],
        langsmith=langsmith,
    )


# ---------------------------------------------------------------------------
# The local artifact: JSONL, one validated row per line.
# ---------------------------------------------------------------------------


def write_trace_rows(rows, path):
    """Write rows as JSONL, overwriting `path`.

    `model_dump_json()` turns each row into a single-line JSON string. UUIDs and
    datetimes become strings, and nested models become nested objects. One
    run per line means the file can be grepped, diffed, appended to, or
    loaded into pandas/jq without a custom parser.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(row.model_dump_json() + "\n")


def read_trace_rows(path):
    """Read a JSONL file back into validated `AgentRunTrace` rows.

    `model_validate_json` parses AND validates in one step. A row that was
    edited by hand into something invalid, or written under a different
    `schema_version`, raises here instead of flowing into a comparison.
    """
    with Path(path).open(encoding="utf-8") as handle:
        return [AgentRunTrace.model_validate_json(line) for line in handle if line.strip()]


# ---------------------------------------------------------------------------
# Demo / evidence capture.
#
# Default queries: one control (Q001: `generate`), the two recursive cases
# (Q091: missing chunk, Q092: missing docs), and one `report_gap` case for
# contrast (Q014: numeric, missing CONTRACT-004, no follow-up defined).
# Retrieval is live (local models, no API key). Generation is opt-in with
# --generate (OpenRouter, paid), as in Day 17/18, but here it is STRUCTURED:
# the model must reply in the `GeneratedAnswer` schema.
# ---------------------------------------------------------------------------

DEMO_QUERY_IDS = ["Q001", "Q091", "Q092", "Q014"]
DEFAULT_TRACE_PATH = Path("docs/traces/day19-agent-traces-V3.jsonl")


def current_code_version():
    """`git describe --always --dirty`, e.g. "fc228a7-dirty", or None outside a git checkout.

    "-dirty" means uncommitted changes were present, so the short sha alone
    would NOT reproduce the code that produced the row. Recording that
    honestly is the point.
    """
    try:
        completed = subprocess.run(
            ["git", "describe", "--always", "--dirty"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def langsmith_project_if_tracing():
    """The LangSmith project runs will be sent to, or None if tracing is off.

    Must be called AFTER `load_dotenv()`. LangSmith caches environment
    lookups (`langsmith.utils.get_env_var` is wrapped in `lru_cache`), so a
    check made before `.env` is loaded would keep its stale answer for the
    whole process.

    Note: `.env` sets `LANGSMITH_TRACING_V2`, and LangSmith checks that
    variable BEFORE the shorter `LANGSMITH_TRACING`. Setting only
    `LANGSMITH_TRACING=false` on the command line does not switch tracing
    off. The route doc's commands set both.
    """
    from langsmith import utils as langsmith_utils

    if not langsmith_utils.tracing_is_enabled():
        return None
    return langsmith_utils.get_tracer_project()


def _print_row(row):
    passes = {retrieval_pass.pass_number: retrieval_pass for retrieval_pass in row.retrieval_passes}
    before, after = row.diagnoses[0], row.diagnoses[-1]
    approval = row.approval.decision if row.approval else "(no pause)"

    print(f"\n{row.query_id} ({row.query_type}) run_id={row.run_id} thread={row.thread_id}")
    print(f"  route:   {' -> '.join(row.route_history)} | stop: {row.stop_reason} | approval: {approval}")
    print(
        f"  pass 1:  {passes[1].context_size_after} sources from {passes[1].context_doc_ids_after} "
        f"| missing docs {before.missing_doc_ids or '-'} chunks {before.missing_chunk_ids or '-'}"
    )
    if 2 in passes:
        print(f"  pass 2:  query {passes[2].query_text!r}")
        print(
            f"           +{len(passes[2].added_chunk_ids)} chunks {passes[2].added_chunk_ids} "
            f"-> {passes[2].context_size_after} sources "
            f"| missing docs {after.missing_doc_ids or '-'} chunks {after.missing_chunk_ids or '-'}"
        )
    if row.langsmith:
        print(f"  langsmith: project {row.langsmith.project!r}, root runs {[str(i) for i in row.langsmith.root_run_ids]}")
    print("  result (the structured output contract):")
    # `exclude` keeps the long human text out of this console view. It is still in the JSONL row.
    print("    " + row.result.model_dump_json(indent=2, exclude={"text"}).replace("\n", "\n    "))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Day 19: run queries through the Day 18 controlled graph and write one validated, "
        "structured trace row per run (JSONL). Records LangSmith root run ids when tracing is on."
    )
    parser.add_argument("--query-ids", nargs="+", default=DEMO_QUERY_IDS, help="labeled corpus query ids to run")
    parser.add_argument(
        "--decision",
        choices=[DECISION_APPROVE, DECISION_REJECT],
        default=DECISION_APPROVE,
        help="the reviewer's decision for every run that pauses (default: approve)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_TRACE_PATH, help="JSONL file to write (overwritten)")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Also call the live LLM (OpenRouter, needs OPENROUTER_API_KEY) on the 'generate' route, with "
        "structured output, so status can be 'answered' or 'model_declined'. Default: no LLM, status "
        "'not_generated' on complete evidence.",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv

    from agentic_retrieval import make_live_retrieve_fn
    from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
    from chunking import chunk_corpus
    from generation import GeneratedAnswer, make_openrouter_client
    from hybrid_search import load_example_queries
    from preprocessing import load_data
    from reranking import load_cross_encoder
    from semantic_search import load_embedding_model

    # Must run before `langsmith_project_if_tracing()` (see its docstring).
    load_dotenv()
    langsmith_project = langsmith_project_if_tracing()

    # Same live pipeline as Day 16-18's main(). Nothing retrieval-related is rebuilt.
    data = load_data()
    chunks = chunk_corpus(data)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()
    retrieve_fn = make_live_retrieve_fn(chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model)

    # `response_model=GeneratedAnswer` sends the schema as a strict
    # `response_format`, so the client returns JSON text instead of prose.
    client = make_openrouter_client(response_model=GeneratedAnswer) if args.generate else None
    graph = build_observed_graph(retrieve_fn, client=client)

    if args.decision == DECISION_APPROVE:
        decision = {"type": DECISION_APPROVE}
    else:
        decision = {"type": DECISION_REJECT, "message": "rejected from the Day 19 CLI demo"}

    code_version = current_code_version()
    queries_by_id = {query["query_id"]: query for query in load_example_queries()}

    print(f"LangSmith tracing: {'ON, project ' + repr(langsmith_project) if langsmith_project else 'off'}")
    print(f"code version: {code_version}")

    rows = []
    for query_id in args.query_ids:
        row = run_and_trace(
            graph,
            queries_by_id[query_id],
            decision,
            code_version=code_version,
            langsmith_project=langsmith_project,
        )
        _print_row(row)
        rows.append(row)

    write_trace_rows(rows, args.output)
    # Read the file straight back through the schema: proof that what is on
    # disk is valid against the contract, not just what was in memory.
    reloaded = read_trace_rows(args.output)
    print(f"\nWrote {len(rows)} trace row(s) to {args.output}; re-read and re-validated {len(reloaded)}.")

    if langsmith_project:
        # LangChain uploads runs from a background thread. Without this wait,
        # the process could exit before the last traces are sent.
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
        print(f"LangSmith: traces flushed to project {langsmith_project!r}. Find a run by its root run id above.")


if __name__ == "__main__":
    main()
