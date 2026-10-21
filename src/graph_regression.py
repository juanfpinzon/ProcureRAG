"""Day 24: a graph-aware regression gate for the ProcureRAG agent graph.

**Why this module exists.** Before Day 24, two commands described the graph,
but neither one could fail:

- `regression_suite.py` checks frozen single-pass fixtures and, with
  `--verify-retrieval`, the current retrieval pipeline. It never runs the
  graph, so it cannot see a route, a retrieval pass count, an approval pause,
  or a stop reason.
- `agent_graph.py --all-queries-summary` runs every labeled query through the
  graph and PRINTS the route distribution. It has no expectation to compare
  against and always exits 0, so a broken router would still look green in CI.

This module is the missing gate: a short list of COMMITTED case contracts
(`GRAPH_CASES`), each saying which route the graph must take on real
retrieval, how many retrieval passes it may run, whether it pauses for
approval, why it must stop, what evidence is missing before and after, and how
many LLM calls it may make. Any difference is printed per case and turns the
process exit code non-zero.

**Which graph.** The one the API serves: `agent_observability.build_observed_graph`
(Day 17's router + Day 18's approval pause + Day 19's structured generation),
driven by `agent_observability.run_and_trace`, which pauses, answers the
approval request with the case's decision, and returns a validated
`AgentRunTrace`. Nothing graph-related is rebuilt here. The only new code is
the case list, two small call-counting wrappers, and the comparison.

**The cases, and what was measured before writing them (2026-10-20, live
local retrieval, `agent_graph.py` and `--all-queries-summary`).**

| case | measured route | why it is in the gate |
|---|---|---|
| Q001 | `generate`, 1 pass | the plain control: complete evidence, no recursion |
| Q005 | `generate`, 1 pass | a second control on the `multi_doc` config, so the contract is not tuned to Q001 |
| Q091 | `recursive_retrieve -> generate`, 2 passes | missing "Band 3" chunk, repaired by the one approved follow-up |
| Q092, approved | `recursive_retrieve -> generate`, 2 passes | two missing documents, BOTH recovered by the follow-up |
| Q092, rejected | `report_gap`, 1 pass | bounded abstention: no approved follow-up, so no answer and no LLM call |
| Q012 | `report_gap`, 1 pass | the 15-query "gap with no follow-up defined" class |

A correction to the Day 24 route doc, from measurement: it describes Q092 as
"bounded failure: one follow-up, evidence still incomplete, report_gap". On
the real pipeline that is not what happens. The follow-up recovers both
`CONTRACT-005` and `POL-002` and the run ends `fixed_after_second_pass`, the
same result Days 16-19 recorded. Writing the route doc's version into this
gate would make it red on day one, or, worse, tempt someone to "fix" retrieval
until it fails again. So Q092 has two committed cases instead: the measured
recovery (approved) and the bounded abstention the route doc was really
after (rejected: a gap report naming both documents, and zero LLM calls).

**How "zero LLM calls" is made a real check.** With no LLM client wired in,
"the graph made 0 LLM calls" is true for every route, so it proves nothing.
The deterministic lane therefore wires in a stand-in client
(`deterministic_stand_in_client`) that answers instantly and is COUNTED. A
`generate` route must call it exactly once. A `report_gap` route must never
call it, even though it is right there. If a router change ever sent a gap to
`generate`, the count would show it.

**Two lanes, one contract.**

- Default (deterministic, merge-blocking in CI): all six cases, real local
  retrieval (the two models), the stand-in client, no key, no network call
  except the one-time model download.
- `--live` (manual, protected `live-eval` GitHub environment): the three-case
  live slice (Q001, Q091, Q092 rejected) with the real OpenRouter client,
  capped at `LIVE_LLM_CALL_BUDGET` logical calls (see that constant for the
  SDK's own transport retries). The same route contract is checked,
  plus a small answer-quality check on the two answered cases: the model
  answered (no decline), the citations pass Day 10's contract, and the answer
  contains each curated required term from that query's `expected_answer`
  (the same `Q001_REQUIRED_TERMS` / `Q091_REQUIRED_TERMS` Day 11/14 use).

**Exit codes (what CI reads).**

- `0`: every case matched its contract.
- `1`: a contract or quality failure. The graph ran and did something other
  than what the case says. That is product drift.
- `2`: an infrastructure failure. The check could not run: the models could
  not be loaded, the live key is missing, or the provider call failed. This
  is not a quality verdict, and must not be read as one.

If both kinds happen in one run, `1` wins: a real drift is a finding even
when another case could not be evaluated.

**Honest limits.**

- No real query reaches `still_missing_after_max_passes` (a follow-up that
  runs but does not fix the gap). That route is covered only by fake
  retrieval in `tests/test_agent_graph.py`.
- The diagnosis still reads gold labels (`relevance_grades`), so this is
  eval-time orchestration over labeled queries, exactly as Days 16-19 said.
- The live quality check is a literal, case-insensitive substring check over
  a few curated terms, not a semantic judge. A correct paraphrase ("Band
  three") fails it, and a term used in the wrong sentence passes it.
- The two retrieval models are downloaded from their repositories' default
  revision. A new upstream revision would show up here as drift, not as a
  "model changed" message (the CI job prints the snapshot it tested).
"""

import argparse
import json
import os
import sys

from agent_control_plane import DECISION_REJECT, STOP_FOLLOWUP_REJECTED
from agent_graph import ROUTE_GENERATE, ROUTE_RECURSIVE_RETRIEVE, ROUTE_REPORT_GAP
from agent_guardrails import AUTO_APPROVE_FOR_DEMO
from agent_observability import STATUS_ANSWERED, STATUS_GAP_REPORT, build_observed_graph, run_and_trace
from agentic_retrieval import (
    STOP_FIXED_AFTER_SECOND_PASS,
    STOP_NO_FOLLOWUP_QUERY_DEFINED,
    STOP_NO_MISSING_EVIDENCE,
)
from generation_eval import Q001_REQUIRED_TERMS, Q091_REQUIRED_TERMS

# ---------------------------------------------------------------------------
# Exit codes and the live budget.
# ---------------------------------------------------------------------------

EXIT_PASSED = 0
EXIT_CONTRACT_FAILED = 1  # the graph did something other than its committed contract
EXIT_INFRASTRUCTURE = 2  # the check could not run (models, key, provider)

# The live slice makes exactly two LLM calls when everything is right: one
# for Q001, one for Q091 (Q092 rejected must make none). The budget is that
# number, not "a little extra just in case": a third call already means a
# case broke its contract, so it is refused instead of paid for.
#
# What the budget counts: LOGICAL calls, i.e. calls to `client(prompt)`. Below
# that, the OpenAI SDK (`openai` 3.13, used by `make_openrouter_client`)
# retries a failed request on its own, up to 2 more times by default
# (`max_retries=2`), on connection errors, timeouts, 429, and 5xx. So the
# worst case is 2 calls x 3 HTTP attempts, each with the 60 s
# `OPENROUTER_TIMEOUT_SECONDS`. A failed attempt that never produced an
# answer is normally not billed, but a timed-out one may be.
LIVE_LLM_CALL_BUDGET = 2

# How each case is labeled in the results.
CATEGORY_PASSED = "passed"
CATEGORY_CONTRACT = "contract_failure"
CATEGORY_INFRASTRUCTURE = "infrastructure_failure"

# The reviewer's decision for the rejected-Q092 case. The message ends up in
# the trace row's `approval.message`, so the row says why the pass never ran.
REJECT_FOR_REGRESSION = {
    "type": DECISION_REJECT,
    "message": "graph regression: the follow-up pass is declined on purpose to check bounded abstention",
}


# ---------------------------------------------------------------------------
# The committed case contracts. One plain dict per case, no class: read this
# list top to bottom and you know every expectation before any code runs.
#
# Every `expected_*` key is compared with the actual value of the same name
# (see `actual_contract_values`). Missing evidence is one sorted list of doc
# ids and chunk ids together, the same "first_pass_missing / final_missing"
# view `agent_graph.py`'s summary table prints.
#
# `decision` answers the approval pause. `AUTO_APPROVE_FOR_DEMO` is Day 20's
# explicit, labeled stand-in for "approved without a human" (its message is
# written into the trace row), so CI never approves silently. Cases that can
# never pause pass `None`, and `run_and_trace` never uses it.
#
# `live_required_terms`: the curated `expected_answer` terms the live answer
# must contain. `None` means "no answer is scored for this case".
# `in_live_slice`: whether `--live` runs this case at all.
# ---------------------------------------------------------------------------

GRAPH_CASES = [
    {
        "case_id": "control-q001",
        "query_id": "Q001",
        "decision": None,
        "expected_route": [ROUTE_GENERATE],
        "expected_retrieval_calls": 1,
        "expected_approval": None,  # complete evidence: the graph never asks
        "expected_stop_reason": STOP_NO_MISSING_EVIDENCE,
        "expected_first_pass_missing": [],
        "expected_final_missing": [],
        "expected_llm_calls": 1,
        "in_live_slice": True,
        "live_required_terms": Q001_REQUIRED_TERMS,  # ("VP Procurement", "Finance review")
    },
    {
        "case_id": "control-q005",
        "query_id": "Q005",
        "decision": None,
        "expected_route": [ROUTE_GENERATE],
        "expected_retrieval_calls": 1,
        "expected_approval": None,
        "expected_stop_reason": STOP_NO_MISSING_EVIDENCE,
        "expected_first_pass_missing": [],
        "expected_final_missing": [],
        "expected_llm_calls": 1,
        "in_live_slice": False,
        "live_required_terms": None,
    },
    {
        "case_id": "recursive-recovery-q091",
        "query_id": "Q091",
        "decision": AUTO_APPROVE_FOR_DEMO,
        "expected_route": [ROUTE_RECURSIVE_RETRIEVE, ROUTE_GENERATE],
        "expected_retrieval_calls": 2,
        "expected_approval": "approve",
        "expected_stop_reason": STOP_FIXED_AFTER_SECOND_PASS,
        # POL-001 is present after pass 1, but only through chunk-3. Either
        # "Band 3" chunk would satisfy the requirement, so both are named.
        "expected_first_pass_missing": ["POL-001::chunk-5", "POL-001::chunk-6"],
        "expected_final_missing": [],
        "expected_llm_calls": 1,
        "in_live_slice": True,
        "live_required_terms": Q091_REQUIRED_TERMS,  # ("Band 3", "usage data")
    },
    {
        "case_id": "recursive-recovery-q092",
        "query_id": "Q092",
        "decision": AUTO_APPROVE_FOR_DEMO,
        "expected_route": [ROUTE_RECURSIVE_RETRIEVE, ROUTE_GENERATE],
        "expected_retrieval_calls": 2,
        "expected_approval": "approve",
        # Measured: the one follow-up recovers BOTH missing documents (see the
        # module docstring for why this is not the route doc's "bounded failure").
        "expected_stop_reason": "still_missing_after_max_passes",
        "expected_first_pass_missing": ["CONTRACT-005", "POL-002"],
        "expected_final_missing": [],
        "expected_llm_calls": 1,
        "in_live_slice": False,
        "live_required_terms": None,
    },
    {
        "case_id": "bounded-abstention-q092-rejected",
        "query_id": "Q092",
        "decision": REJECT_FOR_REGRESSION,
        "expected_route": [ROUTE_REPORT_GAP],
        "expected_retrieval_calls": 1,  # the declined follow-up never runs
        "expected_approval": "reject",
        "expected_stop_reason": STOP_FOLLOWUP_REJECTED,
        "expected_first_pass_missing": ["CONTRACT-005", "POL-002"],
        "expected_final_missing": ["CONTRACT-005", "POL-002"],
        "expected_llm_calls": 0,  # never answer on incomplete evidence
        "in_live_slice": True,  # live: proves the REAL client stays unused
        "live_required_terms": None,  # nothing is answered, so nothing is scored
    },
    {
        "case_id": "unrecoverable-gap-q012",
        "query_id": "Q012",
        "decision": None,  # no follow-up is defined for Q012, so it can never pause
        "expected_route": [ROUTE_REPORT_GAP],
        "expected_retrieval_calls": 1,
        "expected_approval": None,
        "expected_stop_reason": STOP_NO_FOLLOWUP_QUERY_DEFINED,
        "expected_first_pass_missing": ["CONTRACT-002"],
        "expected_final_missing": ["CONTRACT-002"],
        "expected_llm_calls": 0,
        "in_live_slice": False,
        "live_required_terms": None,
    },
]


# ---------------------------------------------------------------------------
# Counting wrappers: the two injected boundaries, retrieval and the LLM, are
# wrapped so the gate can count what ACTUALLY happened, independently of what
# the graph wrote into its own state.
# ---------------------------------------------------------------------------


class BudgetExceeded(Exception):
    """The graph tried to make more LLM calls than the run allows.

    Raised BEFORE the call, so the extra call is never made (and never paid
    for). It is a contract failure: the committed cases add up to exactly the
    budget, so going over means some case called the model when it must not.
    """


class ProviderError(Exception):
    """The live provider call itself failed (network, 401, 429, timeout, empty reply).

    Only `as_provider_boundary` raises this, so ONLY failures at the provider
    boundary are classified as infrastructure. A bug in our own graph code
    still crashes with its own traceback instead of hiding behind
    "infrastructure".
    """


class CallCounter:
    """Wrap a callable, count its calls, and optionally refuse calls over a budget.

    Used twice: around `retrieve_fn(query_text, config)` (no budget, a fresh
    counter per case) and around the LLM `client(prompt)` (one counter for the
    whole run, with the live budget). `*args` lets one class wrap both shapes.
    """

    def __init__(self, function, budget=None):
        self.function = function
        self.budget = budget
        self.calls = 0

    def __call__(self, *args):
        if self.budget is not None and self.calls >= self.budget:
            raise BudgetExceeded(f"call {self.calls + 1} refused: the budget for this run is {self.budget}")
        self.calls += 1
        return self.function(*args)


def as_provider_boundary(client):
    """Wrap the live client so any failure of the call itself becomes a `ProviderError`.

    Only the exception's type and the start of its message are kept. That is
    enough to tell a 401 from a 429 from a timeout, without copying a long
    provider payload into the CI log.
    """

    def call(prompt):
        try:
            return client(prompt)
        except Exception as error:
            raise ProviderError(f"{type(error).__name__}: {str(error)[:200]}") from error

    return call


# The deterministic lane's LLM: valid `GeneratedAnswer` JSON (the shape the
# live structured client returns), citing source [1], which exists in every
# non-empty context. So the `generate` node runs its real code path
# (`generate_structured_answer`, citation validation, `answered` status)
# without any provider.
STAND_IN_ANSWER = json.dumps(
    {
        "answer": "Deterministic CI stand-in answer: no model was called [1].",
        "answerable_from_sources": True,
    }
)


def deterministic_stand_in_client(prompt):
    return STAND_IN_ANSWER


# ---------------------------------------------------------------------------
# Running one case and comparing it with its contract.
# ---------------------------------------------------------------------------


def actual_contract_values(trace, retrieval_calls, llm_calls):
    """The actual value for every `expected_*` key of a case, read from one finished run.

    `trace` is the validated `AgentRunTrace` from `run_and_trace`. The two
    counts come from the wrappers above. `diagnoses[0]` is the evidence after
    pass 1, `diagnoses[-1]` the evidence the run stopped on.
    """
    first, final = trace.diagnoses[0], trace.diagnoses[-1]
    return {
        "route": list(trace.route_history),
        "retrieval_calls": retrieval_calls,
        "approval": trace.approval.decision if trace.approval else None,
        "stop_reason": trace.stop_reason,
        "first_pass_missing": sorted(first.missing_doc_ids + first.missing_chunk_ids),
        "final_missing": sorted(final.missing_doc_ids + final.missing_chunk_ids),
        "llm_calls": llm_calls,
    }


def contract_failures(case, actual, trace):
    """Compare one run with its committed contract. Returns a list of failure messages ([] = passed)."""
    failures = [
        f"{field}: expected {case['expected_' + field]!r}, got {actual_value!r}"
        for field, actual_value in actual.items()
        if actual_value != case["expected_" + field]
    ]

    # A gap report must NAME what is still missing, so a reviewer can see why
    # the graph stopped. Checked against the result text the API would return.
    if trace.result.status == STATUS_GAP_REPORT:
        unnamed = [item for item in actual["final_missing"] if item not in trace.result.text]
        if unnamed:
            failures.append(f"gap report does not name still-missing evidence {unnamed}")

    return failures


def live_quality_failures(case, trace):
    """The `--live` answer checks, for cases that score an answer. Returns failure messages.

    1. The model answered (`answered`), instead of declining.
    2. The citations pass Day 10's contract: at least one citation points at a
       real source, and none points at a source that was never retrieved
       (`CitationCheck.passed`, computed by Day 19's code, reused here).
    3. Each curated required term appears in the answer. Same rule as
       `generation_eval.check_expected_terms`: case-insensitive substring.
    """
    required_terms = case["live_required_terms"]
    if required_terms is None:
        return []

    result = trace.result
    failures = []
    if result.status != STATUS_ANSWERED:
        failures.append(f"quality: expected status 'answered', got {result.status!r}")
    if result.citations is None or not result.citations.passed:
        failures.append(f"quality: citations fail Day 10's contract ({result.citations})")
    missing_terms = [term for term in required_terms if term.lower() not in result.text.lower()]
    if missing_terms:
        failures.append(f"quality: answer is missing required term(s) {missing_terms} from expected_answer")
    return failures


def run_case(case, query_row, retrieve_fn, llm, live=False):
    """Run one case through a fresh graph and classify the outcome.

    A fresh graph per case means a fresh in-memory checkpointer and a fresh
    retrieval counter, so one case can never leak state into the next. The
    LLM counter `llm` is shared by the whole run (it holds the live budget),
    so this case's own calls are the difference before/after.
    """
    retrieval = CallCounter(retrieve_fn)
    graph = build_observed_graph(retrieval, client=llm)
    llm_calls_before = llm.calls

    result = {"case_id": case["case_id"], "query_id": case["query_id"], "actual": None, "answer_text": None}

    try:
        trace = run_and_trace(graph, query_row, case["decision"])
    except ProviderError as error:
        return {**result, "category": CATEGORY_INFRASTRUCTURE, "failures": [f"provider: {error}"]}
    except BudgetExceeded as error:
        return {**result, "category": CATEGORY_CONTRACT, "failures": [f"llm budget: {error}"]}
    except ValueError as error:
        # The run did not finish with a valid trace. Two known ways:
        # - the model's reply broke the `GeneratedAnswer` schema (truncated,
        #   or prose instead of JSON). `generate_structured_answer` raises
        #   pydantic's `ValidationError`, a subclass of `ValueError`. The
        #   provider DID answer, so this is an answer failure, not
        #   infrastructure;
        # - the run is still paused after the decision (`run_and_trace`'s
        #   ValueError): a broken case definition.
        # Recording it per case, instead of letting it crash the process,
        # keeps the remaining cases running. In the live lane that includes
        # the Q092-rejected zero-call check.
        message = f"run did not finish: {type(error).__name__}: {str(error)[:300]}"
        return {**result, "category": CATEGORY_CONTRACT, "failures": [message]}

    actual = actual_contract_values(trace, retrieval.calls, llm.calls - llm_calls_before)
    failures = contract_failures(case, actual, trace)
    if live:
        failures += live_quality_failures(case, trace)

    return {
        **result,
        "actual": actual,
        "answer_text": trace.result.text,
        "category": CATEGORY_CONTRACT if failures else CATEGORY_PASSED,
        "failures": failures,
    }


def run_graph_regression(cases, queries_by_id, retrieve_fn, llm, live=False):
    """Run every case in order and return one result dict per case."""
    return [run_case(case, queries_by_id[case["query_id"]], retrieve_fn, llm, live=live) for case in cases]


def exit_code_for(results):
    """The process exit code for a finished run: contract drift (1) beats infrastructure (2) beats pass (0).

    No results at all is NOT a pass: nothing was checked, so it is reported as
    "could not check" (2). An empty case list must never show up green.
    """
    if not results:
        return EXIT_INFRASTRUCTURE
    categories = {result["category"] for result in results}
    if CATEGORY_CONTRACT in categories:
        return EXIT_CONTRACT_FAILED
    if CATEGORY_INFRASTRUCTURE in categories:
        return EXIT_INFRASTRUCTURE
    return EXIT_PASSED


# ---------------------------------------------------------------------------
# Printing: one line per case, then every failure in full.
# ---------------------------------------------------------------------------


def _print_results(results, live):
    print(f"{'case_id':<34} {'route':<34} {'retr':>4} {'llm':>3}  verdict")
    print("-" * 90)
    for result in results:
        actual = result["actual"]
        if actual is None:  # the run never finished (provider error / budget)
            route, retrieval_calls, llm_calls = "(run did not finish)", "-", "-"
        else:
            route = " -> ".join(actual["route"])
            retrieval_calls, llm_calls = actual["retrieval_calls"], actual["llm_calls"]
        print(f"{result['case_id']:<34} {route:<34} {retrieval_calls:>4} {llm_calls:>3}  {result['category']}")

    failed = [result for result in results if result["failures"]]
    for result in failed:
        print(f"\n{result['case_id']} ({result['category']}):")
        for failure in result["failures"]:
            print(f"  - {failure}")
        # The live answer is printed only when a live case FAILED, so a
        # reviewer can read what the model actually said. The corpus is the
        # repo's own synthetic one; a passing run keeps the log short.
        if live and result["answer_text"] and result["category"] == CATEGORY_CONTRACT:
            print(f"  answer text: {result['answer_text']}")


# ---------------------------------------------------------------------------
# The real retrieval pipeline: the only part of this module that loads models.
# ---------------------------------------------------------------------------


def build_live_retrieve_fn():
    """Build the real `retrieve_fn` exactly as Days 16-21 do (corpus, two local models, both indexes).

    Its own function so tests can replace it, and so `main()` can classify a
    failure here (download, disk, model load) as infrastructure.
    """
    from agentic_retrieval import make_live_retrieve_fn
    from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
    from chunking import chunk_corpus
    from preprocessing import load_data
    from reranking import load_cross_encoder
    from semantic_search import load_embedding_model

    chunks = chunk_corpus(load_data())
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()
    return make_live_retrieve_fn(chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Day 24: run committed route contracts (Q001, Q005, Q091, Q092 approved/rejected, Q012) "
        "through the ProcureRAG agent graph on real local retrieval. Exit 0 = every contract holds, "
        "1 = contract/quality drift, 2 = infrastructure (models, key, provider)."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=f"Run the live slice (Q001, Q091, Q092 rejected) with the real OpenRouter client, at most "
        f"{LIVE_LLM_CALL_BUDGET} LLM calls, and also score the two answers. Needs OPENROUTER_API_KEY in "
        "the process environment (.env is NOT read). Default: deterministic, no provider.",
    )
    args = parser.parse_args(argv)

    if args.live:
        # Check the key FIRST, before ~10 s of model loading. A missing key is
        # an infrastructure failure of a lane someone deliberately selected,
        # so it is red (exit 2), never a quiet "blocked" and never green.
        # `.env` is deliberately not loaded: in CI the key comes from the
        # protected environment's secret, and locally `.env` could also switch
        # on LangSmith tracing as a side effect.
        if not os.environ.get("OPENROUTER_API_KEY"):
            print("INFRASTRUCTURE: OPENROUTER_API_KEY is not set in the process environment. "
                  "The live lane cannot run, which is not a quality verdict. (exit 2)")
            return EXIT_INFRASTRUCTURE

        from generation import DEFAULT_OPENROUTER_MODEL, GeneratedAnswer, make_openrouter_client

        model = os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        live_client = make_openrouter_client(model=model, response_model=GeneratedAnswer)
        llm = CallCounter(as_provider_boundary(live_client), budget=LIVE_LLM_CALL_BUDGET)
        cases = [case for case in GRAPH_CASES if case["in_live_slice"]]
        print(f"lane: LIVE | provider: openrouter | model: {model} | "
              f"cases: {len(cases)} | LLM call budget: {LIVE_LLM_CALL_BUDGET}")
    else:
        llm = CallCounter(deterministic_stand_in_client)
        cases = GRAPH_CASES
        print(f"lane: deterministic | LLM: counted stand-in, no provider | cases: {len(cases)}")

    from hybrid_search import load_example_queries

    queries_by_id = {row["query_id"]: row for row in load_example_queries()}

    print("Loading the corpus and the two local retrieval models...")
    try:
        retrieve_fn = build_live_retrieve_fn()
    except Exception as error:
        # Everything in that function is "get the models and the corpus
        # ready", so a failure there is model supply / host runtime, never a
        # route verdict.
        print(f"INFRASTRUCTURE: the retrieval pipeline could not be built: {type(error).__name__}: {error} (exit 2)")
        return EXIT_INFRASTRUCTURE

    results = run_graph_regression(cases, queries_by_id, retrieve_fn, llm, live=args.live)
    _print_results(results, live=args.live)

    exit_code = exit_code_for(results)
    verdicts = {
        EXIT_PASSED: "every graph contract holds",
        EXIT_CONTRACT_FAILED: "contract/quality drift",
        EXIT_INFRASTRUCTURE: "infrastructure failure: not a quality verdict",
    }
    print(f"\nLLM calls made in this run: {llm.calls}")
    print(f"exit code: {exit_code} ({verdicts[exit_code]})")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
