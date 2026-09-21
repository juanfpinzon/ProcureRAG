"""Day 14: turn Day 11-13's individual checks into a repeatable regression suite.

Every prior generation-eval day built one *layer*, run once, by hand, to
prove a point:

- Day 11 (`generation_eval.py`) wrote four deterministic checks and ran them
  against two hard-coded fixtures (Q001, Q091).
- Day 12 (`framework_eval.py`) added an optional live LLM-as-judge lane
  (DeepEval/RAGAS faithfulness, then contextual recall) with an honest
  `skipped`/`blocked`/`ok`/`error` result contract.
- Day 13 (`error_analysis.py`) added three more real fixtures (Q093, Q016,
  Q004) and a human-assigned root-cause label, so five real failures/passes
  could be read side by side as one small taxonomy.

None of that is a *regression suite* yet - it is a demo transcript. A demo
transcript proves "this ran once and here is what it said." A regression
suite proves something different and more useful: "here is what THIS case
is supposed to show, and whether today's run still shows it." The
distinction matters concretely for this project's very next step: Day 13
ends by recommending a retrieval-depth/diversity repair for Q091's and
Q093's missing primary documents. Once that repair actually happens,
someone needs to be able to answer "did it work, and did it break anything
that used to work?" in one command, not by re-reading prose.

**The case contract this module is built around** (see `REGRESSION_CASES`
and `CITATION_NEGATIVE_CASE` below - this is Day 14's "Block 2" design
worked out in code, not just in a doc):

- `case_id` / `query_id` / `case_role` - what this case is and which real
  (or synthetic) query it uses. `case_role` is one of `passing_control`,
  `retrieval_miss`, `chunk_gap`, `citation_negative`, `refusal_negative`.
- `sources` / `answer_text` / `required_terms` - the frozen fixture Day
  11/13 already proved out (imported, never re-typed here), or a small
  synthetic answer built for a negative test.
- `expected_missing_primary_doc_ids` - what `check_context_recall` should
  report *right now*, before any repair. For Q091 this is genuinely
  `["GUIDE-002", "POL-001"]` - a case is not "passing" by matching this; it
  is "as expected" by matching it, which is what a pre-repair regression
  suite actually needs to assert.
- `expected_missing_primary_doc_ids_after_repair` - the target state a
  successful Q091/Q093 retrieval repair (Day 13's recommended next step)
  must reach: an empty list. Recorded now, checked later, once that repair
  exists - see `docs/eval-report.md`'s Day 14 section for why this is
  deliberately not executed yet in Block 3A.
- `expected_citation_status` - almost always `"pass"`; `"fail"` for
  `CITATION_NEGATIVE_CASE`, because that case's entire point is proving the
  citation validator actually catches a hallucinated `[99]`.

**Two lanes, kept structurally separate** (the Day 14 route's central
instruction): `run_deterministic_suite` below never imports `deepeval`,
never reads an environment variable, never makes a network call - it is
exactly as safe to run in `pytest` or CI as Day 11's own tests. The live
lane (`attach_live_results`, wired to `--live`) is opt-in, reuses Day 12's
own `run_deepeval_faithfulness`/`run_deepeval_contextual_recall` unchanged,
and degrades to `status="blocked"` (never a crash) with no
`OPENROUTER_API_KEY` set - proved directly in
`tests/test_regression_suite.py`, not just asserted here.

**What this deliberately reuses instead of reinventing.** No new
deterministic check is written in this module. Every actual verdict comes
from `generation_eval.evaluate_generated_answer` (citation validity,
context recall) or from `generation.generate_answer` itself (the
empty-context refusal short-circuit). Day 14's only new idea is comparing
that existing output against a per-case *expectation*, and printing all
seven-plus cases as one table instead of one `print()` per case.
"""

import argparse
from datetime import datetime, timezone

from generation import INSUFFICIENT_EVIDENCE_ANSWER, generate_answer
from generation_eval import CURATED_FIXTURES, evaluate_generated_answer
from error_analysis import (
    Q004_ANSWER_TEXT,
    Q004_SOURCES,
    Q016_ANSWER_TEXT,
    Q016_SOURCES,
    Q093_ANSWER_TEXT,
    Q093_SOURCES,
)
from framework_eval import build_framework_eval_case, run_deepeval_contextual_recall, run_deepeval_faithfulness
from hybrid_search import load_example_queries

# ---------------------------------------------------------------------------
# Pull Day 11's already-committed Q001/Q091 fixtures out of CURATED_FIXTURES
# by query_id, rather than re-typing their sources/answer_text/required_terms
# a second time here - the same "reuse the frozen transcript" rule every
# earlier day in this project already follows.
# ---------------------------------------------------------------------------


def _fixture(query_id):
    return next(f for f in CURATED_FIXTURES if f["query_id"] == query_id)


_Q001 = _fixture("Q001")
_Q091 = _fixture("Q091")


# ---------------------------------------------------------------------------
# The regression case list: five real cases (two controls, two retrieval
# misses, one chunk-level gap) - one plain dict per case, no class, no
# builder function. This is Block 3A step 1: "start with a pure data case
# list" - a reader can see every case's full expectation just by reading
# this list top to bottom, before any evaluation code runs at all.
# ---------------------------------------------------------------------------

REGRESSION_CASES = [
    {
        "case_id": "control-q001",
        "query_id": "Q001",
        "case_role": "passing_control",
        "source_fixture_kind": "committed_fixture",
        "sources": _Q001["sources"],
        "answer_text": _Q001["answer_text"],
        "required_terms": _Q001["required_terms"],
        "expected_missing_primary_doc_ids": [],
        "expected_missing_primary_doc_ids_after_repair": None,  # not a repair target
        "expected_citation_status": "pass",
        "table_note": None,
        "notes": (
            "Easy single-threshold control (POL-001/FAQ-001 both reach context). "
            "Must stay fully clean after any multi_doc top-k or diversity change - "
            "a regression here would mean a retrieval change hurt the easy case, "
            "not just failed to help the hard one."
        ),
    },
    {
        "case_id": "control-q004",
        "query_id": "Q004",
        "case_role": "passing_control",
        "source_fixture_kind": "committed_fixture",
        "sources": Q004_SOURCES,
        "answer_text": Q004_ANSWER_TEXT,
        "required_terms": None,
        "expected_missing_primary_doc_ids": [],
        "expected_missing_primary_doc_ids_after_repair": None,
        "expected_citation_status": "pass",
        "table_note": None,
        "notes": (
            "Second control, deliberately NOT multi_doc (single primary doc, "
            "POL-001). Guards against a multi-doc-specific repair being credited "
            "with a win that is really just noise, and against a multi-doc-only "
            "regression test suite that would never notice a generation-wide bug."
        ),
    },
    {
        "case_id": "retrieval-miss-q091",
        "query_id": "Q091",
        "case_role": "retrieval_miss",
        "source_fixture_kind": "committed_fixture",
        "sources": _Q091["sources"],
        "answer_text": _Q091["answer_text"],
        "required_terms": _Q091["required_terms"],
        "expected_missing_primary_doc_ids": ["GUIDE-002", "POL-001"],
        "expected_missing_primary_doc_ids_after_repair": [],
        "expected_citation_status": "pass",
        "table_note": "repair target: missing docs -> []",
        "notes": (
            "The Day 13 anchor case. Citations are already clean and Day 12's "
            "live faithfulness judge scored this 1.00 - faithfulness cannot see "
            "this failure, only check_context_recall can. A prompt-only change "
            "must NOT move this signal; only a real retrieval-depth/diversity "
            "change should."
        ),
    },
    {
        "case_id": "retrieval-miss-q093",
        "query_id": "Q093",
        "case_role": "retrieval_miss",
        "source_fixture_kind": "committed_fixture",
        "sources": Q093_SOURCES,
        "answer_text": Q093_ANSWER_TEXT,
        "required_terms": None,
        "expected_missing_primary_doc_ids": ["CONTRACT-001"],
        "expected_missing_primary_doc_ids_after_repair": [],
        "expected_citation_status": "pass",
        "table_note": "repair target: missing docs -> []",
        "notes": (
            "A second, distinct retrieval_miss: a missing contract turns a "
            "genuinely scoped 'it varies by contract' answer into a false "
            "universal one, entirely honestly and with clean citations - the "
            "sharpest case for why context_recall must be a hard gate, not just "
            "a live judge opinion."
        ),
    },
    {
        "case_id": "chunk-gap-q016",
        "query_id": "Q016",
        "case_role": "chunk_gap",
        "source_fixture_kind": "committed_fixture",
        "sources": Q016_SOURCES,
        "answer_text": Q016_ANSWER_TEXT,
        "required_terms": None,
        "expected_missing_primary_doc_ids": [],
        "expected_missing_primary_doc_ids_after_repair": None,  # not the same repair target as Q091/Q093
        "expected_citation_status": "pass",
        "table_note": "doc-level pass; GUIDE-001's 40% chunk never retrieved",
        "notes": (
            "Contrast case: document-level check_context_recall PASSES (both "
            "GUIDE-001 and POL-004 reached context), but the specific GUIDE-001 "
            "chunk carrying the 'logistics price <=40%' figure was never "
            "retrieved - a different chunk of the same document was. No "
            "automated chunk/fact-level check exists yet (see docs/eval-report.md "
            "Day 13's caveats); this row exists so that gap stays visible in the "
            "suite output instead of hiding behind a passing document-level check."
        ),
    },
]

# The citation-orphan negative case. Deliberately synthetic (the design doc
# explicitly allows this: "can be synthetic because this is a validator
# boundary test") - it reuses Q001's real query row and real sources, so
# context_recall behaves normally, and only changes the answer text to add a
# citation number, [99], that does not exist in Q001's five real sources
# (only [1]-[5] are real - see generation_eval.Q001_SOURCES). The point is
# narrow: prove check_citation_validity actually flags a hallucinated
# citation, not just that it passes on already-clean transcripts.
CITATION_NEGATIVE_CASE = {
    "case_id": "citation-negative-synthetic",
    "query_id": "Q001",
    "case_role": "citation_negative",
    "source_fixture_kind": "synthetic_negative",
    "sources": _Q001["sources"],
    "answer_text": "VP Procurement approval with a Finance review is required [4][99].",
    "required_terms": None,
    "expected_missing_primary_doc_ids": [],
    "expected_missing_primary_doc_ids_after_repair": None,
    "expected_citation_status": "fail",  # the point of this case: we WANT a fail here
    "table_note": "synthetic [99] citation; expects citation_validity=fail",
    "notes": (
        "Synthetic answer text over Q001's real sources, citing [99] - a source "
        "number that was never retrieved. This case's own 'expected_verdict' is "
        "citation_validity=fail; if it ever comes back 'pass' instead, the "
        "validator itself has regressed, not the answer quality."
    ),
}


# ---------------------------------------------------------------------------
# One evaluator for every REGRESSION_CASES / CITATION_NEGATIVE_CASE entry.
# Block 3A step 2: reuse evaluate_generated_answer, don't duplicate its
# checks - this function only adds the "does the actual result match this
# case's own expectation" comparison on top.
# ---------------------------------------------------------------------------


def evaluate_case(case_spec, query_row):
    """Run Day 11's checks for one case and compare the result to its expectation.

    `deterministic_match` is the heart of the "regression" idea: it is NOT
    "did every check pass" (Q091 and Q093 are *supposed* to fail
    context_recall today, and CITATION_NEGATIVE_CASE is *supposed* to fail
    citation_validity) - it is "does today's actual result equal what this
    case declared it should be." That is what lets a future retrieval change
    be compared against a known baseline instead of just re-reading raw
    pass/fail flags out of context.
    """
    findings = evaluate_generated_answer(
        query_row,
        case_spec["sources"],
        case_spec["answer_text"],
        required_terms=case_spec["required_terms"],
    )
    findings_by_check = {finding["check"]: finding for finding in findings}
    context_recall = findings_by_check["context_recall"]
    citation_validity = findings_by_check["citation_validity"]

    # Same "expected minus actual" arithmetic Day 13's build_case_record
    # already uses - repeated here (not imported) because it is two lines,
    # and importing a private helper across modules for two lines would be
    # a worse trade than just reading it again.
    missing_primary_doc_ids = sorted(set(context_recall["expected"]) - set(context_recall["actual"]))
    citation_status = "pass" if citation_validity["passed"] else "fail"

    deterministic_match = (
        missing_primary_doc_ids == case_spec["expected_missing_primary_doc_ids"]
        and citation_status == case_spec["expected_citation_status"]
    )

    return {
        "case_id": case_spec["case_id"],
        "query_id": case_spec["query_id"],
        "role": case_spec["case_role"],
        "source_fixture_kind": case_spec["source_fixture_kind"],
        "query_type": query_row.get("query_type"),
        "difficulty": query_row.get("difficulty"),
        "missing_primary_doc_ids": missing_primary_doc_ids,
        "expected_missing_primary_doc_ids": case_spec["expected_missing_primary_doc_ids"],
        "citation_status": citation_status,
        "expected_citation_status": case_spec["expected_citation_status"],
        "table_note": case_spec["table_note"],
        "notes": case_spec["notes"],
        "deterministic_match": deterministic_match,
        "live_status": None,  # filled in later by attach_live_results, if --live was passed
        "findings": findings,
    }


def evaluate_refusal_case():
    """The insufficient-evidence / empty-context refusal boundary test.

    This is the one case that cannot go through `evaluate_case` above: there
    is no retrieved context to run `check_context_recall` against, and
    nothing to cite, so the thing actually worth proving is different -
    that `generation.generate_answer` refuses instead of guessing, and never
    even calls the model, when `sources` is empty. `_client_that_must_not_be_called`
    mirrors the exact fake-client pattern `tests/test_generation.py` already
    uses for this: if `generate_answer` ever called it, this test would fail
    with a loud `AssertionError` naming the actual bug, instead of silently
    invoking a model that was never supposed to run.
    """

    def _client_that_must_not_be_called(prompt):
        raise AssertionError(
            "generate_answer must not call the client at all when sources is empty - "
            "an empty context has nothing true to say, so falling through to a live "
            "model call here would be exactly the ungrounded-guess failure mode Day "
            "10's refusal short-circuit exists to prevent."
        )

    result = generate_answer(
        "What is the refund policy for a cancelled purchase order?",
        sources=[],
        client=_client_that_must_not_be_called,
    )

    refused_correctly = result["answer"] == INSUFFICIENT_EVIDENCE_ANSWER
    citation_status = "pass" if not result["citations"]["orphan_ids"] else "fail"
    deterministic_match = refused_correctly and citation_status == "pass"

    return {
        "case_id": "refusal-negative-synthetic",
        "query_id": None,
        "role": "refusal_negative",
        "source_fixture_kind": "synthetic_negative",
        "query_type": None,
        "difficulty": None,
        "missing_primary_doc_ids": None,  # not a meaningful concept with zero sources
        "expected_missing_primary_doc_ids": None,
        "citation_status": citation_status,
        "expected_citation_status": "pass",
        "table_note": "empty context must trigger refusal; client never called",
        "notes": (
            "Synthetic query, empty sources. generate_answer must return the fixed "
            "INSUFFICIENT_EVIDENCE_ANSWER text and never invoke the client - proving "
            "the empty-context short-circuit still holds, the same contract "
            "tests/test_generation.py already checks at the unit level."
        ),
        "deterministic_match": deterministic_match,
        "live_status": None,
        "findings": [],
    }


# ---------------------------------------------------------------------------
# The CI-safe deterministic lane: no import of deepeval/ragas, no
# environment read, no network call anywhere in this function's call graph.
# ---------------------------------------------------------------------------


def run_deterministic_suite(queries_by_id=None):
    """Evaluate every regression case and return one result row per case.

    `queries_by_id` defaults to a fresh `load_example_queries()` read (the
    real 93-query corpus) so `main()` below can call this with no arguments;
    tests pass their own dict so they don't re-read the corpus file in every
    test function. This function's own body never imports `deepeval`/`ragas`
    and never touches `os.environ` - the live lane is entirely opt-in, added
    afterwards by `attach_live_results`.
    """
    if queries_by_id is None:
        queries_by_id = {row["query_id"]: row for row in load_example_queries()}

    rows = [evaluate_case(case, queries_by_id[case["query_id"]]) for case in REGRESSION_CASES]
    rows.append(evaluate_case(CITATION_NEGATIVE_CASE, queries_by_id[CITATION_NEGATIVE_CASE["query_id"]]))
    rows.append(evaluate_refusal_case())
    return rows


# ---------------------------------------------------------------------------
# The optional live lane: opt-in only, reuses Day 12/13's own
# skip/blocked/ok/error contract unchanged.
# ---------------------------------------------------------------------------


def _with_trace_metadata(result):
    """Attach the run metadata Day 14 asks every live result to carry.

    Written as honestly as the rest of this project's live-eval code: DeepEval's
    judge client is configured once via the `deepeval set-openrouter` CLI
    command (see `framework_eval.py`'s module docstring) and does not expose a
    per-call temperature or max-tokens argument to this codebase the way
    `run_ragas_faithfulness`'s hand-built `ChatOpenAI` does. Recording `None`
    for those two fields is honest about a real boundary, not a missing
    feature of this function - inventing a number this project does not
    actually control would be worse than admitting it isn't visible here.
    """
    return {
        **result,
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": "openrouter",
        "temperature": None,  # not exposed by DeepEval's CLI-configured client
        "token_budget": None,  # not exposed by DeepEval's CLI-configured client
    }


def attach_live_results(rows, queries_by_id):
    """Add a DeepEval faithfulness + contextual-recall result to each eligible row.

    Only the five real `REGRESSION_CASES` are judged - `CITATION_NEGATIVE_CASE`
    and the refusal case are synthetic boundary tests, not real generated
    answers, so asking a faithfulness judge to score them would produce a
    number that means nothing. Those two rows get a short explanatory string
    instead of a result dict, so the table still explains itself rather than
    printing a blank.

    `run_deepeval_faithfulness`/`run_deepeval_contextual_recall` are called
    with `live=True` unchanged from Day 12/13 - if `OPENROUTER_API_KEY` is
    missing, both degrade to `status="blocked"` on their own; this function
    never checks the key itself and never wraps the call in a try/except,
    because that safety net already lives in `framework_eval.py`.
    """
    case_specs_by_id = {case["case_id"]: case for case in REGRESSION_CASES}

    for row in rows:
        case_spec = case_specs_by_id.get(row["case_id"])
        if case_spec is None:
            row["live_status"] = "n/a - synthetic case, not judged for faithfulness/context recall"
            continue

        query_row = queries_by_id[case_spec["query_id"]]
        framework_case = build_framework_eval_case(query_row, case_spec["sources"], case_spec["answer_text"])
        row["live_status"] = {
            "faithfulness": _with_trace_metadata(run_deepeval_faithfulness(framework_case, live=True)),
            "contextual_recall": _with_trace_metadata(
                run_deepeval_contextual_recall(framework_case, live=True)
            ),
        }


# ---------------------------------------------------------------------------
# The table printer: Block 3A step 3's nine columns, hand-rolled (no table
# library is a project dependency, and eight short columns don't need one).
# ---------------------------------------------------------------------------


def _format_missing_docs(value):
    return ", ".join(value) if value else "-"


def _format_live_status(live_status):
    if live_status is None:
        return "not run (pass --live)"
    if isinstance(live_status, str):
        return live_status
    parts = []
    for metric_name, result in live_status.items():
        if result["status"] == "ok":
            parts.append(f"{metric_name}={result['status']}({result['score']:.2f})")
        else:
            parts.append(f"{metric_name}={result['status']}")
    return ", ".join(parts)


def _overall_verdict(row):
    """Combine the deterministic match with whatever live evidence exists.

    A regression here is always decided by the deterministic lane -
    `deterministic_match is False` means an actual missing-doc list or
    citation verdict no longer matches what this case declared it should be,
    which is exactly the signal Day 13's recommended repair must move for
    Q091/Q093 (and must NOT move for Q001/Q004). Live judge results, when
    present, only ever refine the label from "as_expected" to
    "as_expected (live ok)" / "as_expected (live inconclusive)" - they are
    evidence samples, per the Day 14 route doc, never a hard gate on their
    own.
    """
    if not row["deterministic_match"]:
        return "REGRESSION"

    live_status = row["live_status"]
    if live_status is None or isinstance(live_status, str):
        return "as_expected"

    statuses = {result["status"] for result in live_status.values()}
    if statuses == {"ok"}:
        return "as_expected (live ok)"
    return "as_expected (live inconclusive)"


# One (header, cell-getter) pair per column, in print order - matches Block
# 3A step 3's column list exactly.
_TABLE_COLUMNS = (
    ("case_id", lambda row: row["case_id"]),
    ("query_id", lambda row: row["query_id"] or "-"),
    ("role", lambda row: row["role"]),
    ("deterministic_verdict", lambda row: "match" if row["deterministic_match"] else "MISMATCH"),
    ("missing_docs", lambda row: _format_missing_docs(row["missing_primary_doc_ids"])),
    ("citation_status", lambda row: row["citation_status"]),
    ("chunk_gap_or_notes", lambda row: row["table_note"] or "-"),
    ("live_status", lambda row: _format_live_status(row["live_status"])),
    ("overall_verdict", lambda row: _overall_verdict(row)),
)


def render_table(rows):
    """Render one row per case as a plain, fixed-width text table.

    Column widths are computed once over the whole row set
    (`max(len(...) for every cell in that column)`), so every column lines
    up under its header regardless of content length - the same idea a real
    table library implements, small enough here to read start to finish.
    """
    header = [name for name, _ in _TABLE_COLUMNS]
    body = [[str(getter(row)) for _, getter in _TABLE_COLUMNS] for row in rows]

    widths = [
        max(len(header[i]), *(len(line[i]) for line in body)) if body else len(header[i])
        for i in range(len(_TABLE_COLUMNS))
    ]

    def _format_line(cells):
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths))

    lines = [_format_line(header), _format_line(["-" * width for width in widths])]
    lines.extend(_format_line(line) for line in body)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the deterministic suite (and, with `--live`, the judge lane) and print it.

    No flags at all: deterministic-only, no network, no `OPENROUTER_API_KEY`
    required - this is the command a portfolio reviewer with no credentials
    can run and still see the full seven-case regression table. `--live`
    additionally runs DeepEval's faithfulness and contextual-recall metrics
    for the five real fixture cases; with no key present those simply report
    `status="blocked"` per case rather than failing the whole run.
    """
    parser = argparse.ArgumentParser(
        description="Day 14: CI-safe generation-eval regression suite over Q001/Q004/Q091/Q093/Q016 "
        "plus a citation-negative and a refusal-negative boundary case."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also run DeepEval faithfulness + contextual recall for the five real fixture cases "
        "(needs OPENROUTER_API_KEY; degrades to status=blocked without one). Default: "
        "deterministic-only, no network.",
    )
    args = parser.parse_args()

    queries_by_id = {row["query_id"]: row for row in load_example_queries()}
    rows = run_deterministic_suite(queries_by_id)

    if args.live:
        from dotenv import load_dotenv

        # Same one-call-at-the-entry-point pattern generation.main() and
        # framework_eval.main() already use - see generation.py's
        # `make_openrouter_client` docstring for why this isn't done inside
        # every function that might need the key.
        load_dotenv()
        attach_live_results(rows, queries_by_id)

    print(render_table(rows))

    regressions = [row for row in rows if not row["deterministic_match"]]
    if regressions:
        print(f"\n{len(regressions)} case(s) no longer match their expected state:")
        for row in regressions:
            print(f"  - {row['case_id']}: expected {row['expected_missing_primary_doc_ids']!r}, "
                  f"got {row['missing_primary_doc_ids']!r} "
                  f"(citation expected={row['expected_citation_status']!r}, "
                  f"got={row['citation_status']!r})")
    else:
        print("\nAll cases match their expected pre-repair state.")


if __name__ == "__main__":
    main()
