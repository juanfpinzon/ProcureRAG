"""Day 12: bridge ProcureRAG's generated answers into DeepEval and RAGAS.

Day 11 (`generation_eval.py`) proved something narrow on purpose: four
*deterministic*, hand-written checks over a `(query, sources, answer_text)`
triple. They are cheap, reproducible, and explainable in one sentence each -
but they also only catch what someone thought to write a check for. Day 11's
own module docstring says this explicitly: "no LLM-as-judge call, no semantic
similarity model ... no framework integration (DeepEval/RAGAS)".

Day 12 adds that missing layer, without touching Day 11 at all. This module
answers a narrower question than "is DeepEval/RAGAS good?" - it answers
"what does a real *judge model* say about faithfulness, when asked the same
question about the same two calibration fixtures (Q001, Q091) Day 11 already
proved deterministic checks work against?"

**Why faithfulness first, and why Q001/Q091 as the calibration pair.**
Faithfulness asks one specific question: "does every claim in `actual_output`
hold up against what's actually in `retrieval_context`?" It is the framework
metric closest to Day 11's `check_unsupported_inference` (a hand-curated
hedge-phrase heuristic) - except a real judge model reads the *whole*
sentence and its cited evidence, not just a fixed phrase list.

Q001's real Day 10 transcript is clean: every claim traces to a source that
was actually retrieved. A faithfulness judge should score it high.

Q091 is the interesting case, and the whole point of running it through a
live judge instead of just reading the score off a leaderboard: Q091's real
transcript *also* only makes claims its retrieved sources support - it
never invents anything. So a faithfulness judge can plausibly score Q091
just as high as Q001, even though Day 11's `check_context_recall` already
proved Q091 is missing two primary documents (`POL-001`, `GUIDE-002`) that
never reached the model's context in the first place. **Faithfulness asks
"is the answer honest about what it saw?", not "did it see enough?"** - a
high faithfulness score on Q091 would not contradict Day 11's failing
`context_recall` finding, it would *confirm* the two checks are measuring
different things. That contrast, seen in real judge output rather than
asserted in prose, is Day 12's actual deliverable.

**The adapter boundary, made explicit instead of implicit.** DeepEval's
`LLMTestCase` and RAGAS's `SingleTurnSample` both want roughly "the
question, the answer, the context the model saw" - but they use different
field names (`input`/`actual_output`/`retrieval_context` vs.
`user_input`/`response`/`retrieved_contexts`), and RAGAS additionally wants
its own LLM object wired up by hand rather than reading a CLI-configured
default the way DeepEval does. Rather than have one function silently
special-case both frameworks, `build_framework_eval_case` below builds one
framework-neutral dict first (ProcureRAG's own vocabulary), and a small,
separate `to_..._*` function per framework does nothing but rename/reshape
that dict into what the framework wants. A reader can see exactly which
field maps to which, for both frameworks, in one place each.

**The dependency/key boundary.** `deepeval` and `ragas` are real
`pyproject.toml` dependencies here (not optional extras), but a *live* judge
call still needs `OPENROUTER_API_KEY` and a network connection - neither of
which a deterministic test suite should ever depend on. Every `run_*`
function below defaults to `live=False` and returns a `status="skipped"`
result immediately, before importing anything framework-specific or reading
any environment variable - flipping `live=True` is the only way to reach the
network, and even then a missing key or an unimportable framework degrades
to a `status="blocked"` result instead of a raised `ModuleNotFoundError` or
a bare provider exception. `tests/test_framework_eval.py` proves both of
those paths without ever calling OpenRouter.

To be precise about what "deterministic" covers here: the default
`live=False` runner path never imports `deepeval`/`ragas` at all, so it
would work even if neither were installed. The adapter-shape tests
(`to_deepeval_test_case`/`to_ragas_sample`) are a different, narrower
guarantee - they *do* import the real `LLMTestCase`/`SingleTurnSample`
classes (both are real `pyproject.toml` dependencies, so this is expected,
not accidental), they just never reach the network. "Deterministic" means
"no live call, no network, reproducible" throughout this file - not "never
imports a framework."

**What this deliberately does not do.** No contextual-precision or RAGAS
context-recall framework metrics, and no answer-relevancy metric - Day 12's
scope was one metric (faithfulness) through two frameworks, calibrated
against two known fixtures; that stays true here for RAGAS.

**Day 13 addition: DeepEval contextual recall.** `run_deepeval_contextual_recall`
below adds exactly one more DeepEval metric, for a reason the Day 12 run
itself surfaced: faithfulness structurally cannot catch Q091's real problem
(missing primary documents), because it only ever asks "is the answer
honest about the context it saw" - never "did it see enough." Contextual
recall asks a different question that actually uses the two ingredients
faithfulness ignores, `expected_output` and `retrieval_context` - "does the
retrieved context contain what `expected_output` needed?" - which is the
framework metric closest in spirit to Day 11's own `check_context_recall`.
It reuses the exact same `to_deepeval_test_case` adapter, the exact same
`live=False`-by-default/`status` contract, and the exact same
skip/blocked/ok/error shape as `run_deepeval_faithfulness` - the only thing
that changes is which DeepEval metric class gets constructed and measured.
See `docs/eval-report.md`'s Day 13 section for the live Q001/Q091 run this
was calibrated against, and why its reason text still needs a human check
against the deterministic evidence, exactly like faithfulness's reason did
in Day 12.
"""

import os
import warnings

from dotenv import load_dotenv

from generation import OPENROUTER_BASE_URL, OPENROUTER_TIMEOUT_SECONDS

# ---------------------------------------------------------------------------
# Both frameworks are pointed at the exact same OpenRouter judge model, so a
# DeepEval-vs-RAGAS score comparison on the same fixture is actually
# apples-to-apples - a different judge model underneath would confound
# "which framework says what" with "which judge model said it".
#
# DeepEval reads its model from `.deepeval/.deepeval` (written by the
# `deepeval set-openrouter --model=openai/gpt-4o-mini` CLI command this
# project already ran - see `docs/eval-report.md`'s Day 12 section), so
# `run_deepeval_faithfulness` below passes `model=None` and lets DeepEval use
# that CLI-configured default rather than hard-coding it a second time here.
# RAGAS has no such CLI/global config - `run_ragas_faithfulness` below has to
# build its own LLM object by hand, so JUDGE_MODEL is the one place that
# value is spelled out in this file.
# ---------------------------------------------------------------------------
JUDGE_MODEL = "openai/gpt-4o-mini"

# Day 10 (`generation.py`) already learned this lesson the hard way, live:
# an unbounded free-tier OpenRouter call can hang, and an unbounded
# `max_tokens` gives no predictable worst-case cost/latency - see
# `OPENROUTER_TIMEOUT_SECONDS`'s and `MAX_ANSWER_TOKENS`'s own comments in
# `generation.py`. DeepEval's `FaithfulnessMetric` manages its own internal
# OpenRouter client (built from the `deepeval set-openrouter` config) and
# doesn't expose a per-call timeout/token-cap knob to this file - but RAGAS's
# `ChatOpenAI` is built by hand right here (see `run_ragas_faithfulness`), so
# it gets the same two guards Day 10's answer-generation client has: reusing
# `OPENROUTER_TIMEOUT_SECONDS` (the exact same 60s bound, not a re-guessed
# one) and a judge-specific token cap.
#
# `JUDGE_MAX_TOKENS` genuinely needed a real trial, the same way
# `MAX_ANSWER_TOKENS` did in `generation.py`: RAGAS's `Faithfulness` doesn't
# just ask one short question - internally it extracts a claims list from
# `actual_output`, then generates a verdict *per claim* against
# `retrieval_context`, so its token need scales with both the answer length
# and how much context it was given. A first guess of 1024 ran fine for
# Q001 but failed outright on Q091 (`status="error"`, "The LLM generation
# was not completed. Please increase the max_tokens and try again.") - Q091
# is both the longer answer and the query with five full-length retrieved
# chunks (see the Day 12 fixture update above), so its claims/verdicts
# generation needs more room. 4096 is generous enough that neither
# calibration fixture hits the cap; it is not tuned tighter than that for
# the same reason Day 10 eventually gave up tuning `MAX_ANSWER_TOKENS`
# precisely and instead picked a comfortably large fixed budget - cost here
# is negligible either way at OpenRouter's per-token pricing for this model.
JUDGE_MAX_TOKENS = 4096


# ---------------------------------------------------------------------------
# The neutral case: ProcureRAG's own eval-case shape, independent of any
# framework - see the module docstring's "adapter boundary" section.
# ---------------------------------------------------------------------------


def build_framework_eval_case(query_row, sources, answer_text, deterministic_findings=None):
    """Turn one ProcureRAG (query, sources, answer) triple into a plain,
    framework-neutral dict - the Day 12 "canonical eval case" from the
    design doc's Block 2.

    Nothing here is DeepEval- or RAGAS-shaped yet; that reshaping happens
    one step later, in `to_deepeval_test_case`/`to_ragas_sample`, so this
    function stays reusable no matter which framework (or a third one,
    later) ends up consuming it.

    `sources` is expected to be the exact list `generation.build_sources`
    (or `generation_eval._source`, for the curated fixtures) already
    produces - each entry has `source_id`, `doc_id`, `chunk_id`, `text`,
    `rank`. List order is preserved end-to-end here on purpose:
    `retrieval_context` and `source_metadata` below are built with a plain
    list comprehension, not a set or a sort, because a judge model reading
    "source 1, source 2, ..." in a different order than the prompt actually
    used it in would be evaluating a subtly different thing than what was
    really generated.

    `deterministic_findings` is Day 11's own output
    (`generation_eval.evaluate_generated_answer(...)`), passed straight
    through unchanged rather than recomputed here. Carrying it alongside the
    framework-eval case (instead of in a separate, uncorrelated report) is
    what makes the Day 12 calibration story readable: a human (or this
    module's `main()`) can print "Day 11 said X" right next to "the live
    judge said Y" for the *same* case, which is the whole point of today.
    `None` (the default) means the caller didn't run Day 11's checks for
    this case - left as `[]` rather than skipped, so `deterministic_findings`
    is always a list a caller can safely iterate without a `None` check.
    """
    return {
        "query_id": query_row["query_id"],
        "input": query_row["query"],
        "actual_output": answer_text,
        # Real rows in data/corpus_v1/example_queries.jsonl always carry
        # `expected_answer`; `.get(..., "")` only matters for a hand-built
        # synthetic query_row in a unit test that doesn't bother supplying
        # one.
        "expected_output": query_row.get("expected_answer", ""),
        "retrieval_context": [source["text"] for source in sources],
        "source_metadata": [
            {
                "source_id": source["source_id"],
                "doc_id": source["doc_id"],
                "chunk_id": source["chunk_id"],
                "rank": source["rank"],
            }
            for source in sources
        ],
        "deterministic_findings": deterministic_findings if deterministic_findings is not None else [],
    }


# ---------------------------------------------------------------------------
# Dependency/key status: can a live judge call even be attempted? Checked as
# a plain (status, reason) pair rather than an exception, so both `run_*`
# functions below and `tests/test_framework_eval.py` can inspect it without
# a try/except - see the module docstring's "dependency/key boundary".
# ---------------------------------------------------------------------------


def _has_openrouter_key():
    """Whether `OPENROUTER_API_KEY` is set in the current process environment.

    Deliberately does *not* call `load_dotenv()` itself - see
    `generation.py`'s own `main()`, which calls it exactly once, at the
    live-demo entry point, not inside every function that might need the
    key. If this helper called `load_dotenv()` on every check, a test that
    used `monkeypatch.delenv("OPENROUTER_API_KEY", ...)` to simulate a
    missing key would have it silently refilled from the real `.env` file on
    the very next call - which would make the "no-key" test path
    untestable. `main()` below calls `load_dotenv()` once, up front, exactly
    like `generation.main()` does.
    """
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def deepeval_status():
    """Return `("available", None)` or `("blocked", reason)` for DeepEval.

    The `import deepeval` here is deliberately inside the function body, not
    a module-level import at the top of this file - the same "fail-safe
    optional dependency" pattern `generation.make_openrouter_client` already
    uses for the `openai` package. In this project `deepeval` genuinely is
    installed (`pyproject.toml`), so this branch is not expected to trigger
    day-to-day - but keeping the check real (not hard-coded to always
    succeed) is what lets `tests/test_framework_eval.py` prove the
    "dependency missing" contract with `monkeypatch.setitem(sys.modules,
    "deepeval", None)` instead of just asserting it in a docstring.

    IMPORTANT: `"available"` here means exactly "the package imports and
    `OPENROUTER_API_KEY` is set" - two cheap, local, pre-network checks. It
    is *not* a guarantee that a live call will actually succeed. Day 12
    itself proved that gap is real: DeepEval's configured judge model was a
    typo (`openai/gpt-4.o-mini` instead of `openai/gpt-4o-mini`, see
    `docs/eval-report.md`'s "Fixing the environment" section) for a while
    with a correct key present the whole time - `deepeval_status()` would
    have returned `"available"` throughout, because a broken model string
    isn't something an import check or a key-presence check can see.
    """
    try:
        import deepeval  # noqa: F401
    except ImportError as exc:
        return "blocked", f"deepeval is not importable: {exc}"

    if not _has_openrouter_key():
        return "blocked", (
            "OPENROUTER_API_KEY is not set - put it in .env or export it "
            "before running a live DeepEval judge."
        )
    return "available", None


def ragas_status():
    """Return `("available", None)` or `("blocked", reason)` for RAGAS.

    Mirrors `deepeval_status` exactly, for the same reason: `ragas` is a
    real dependency here too, but the check stays real (not hard-coded) so
    the "not importable" branch is provable in a test, not just asserted.
    """
    try:
        import ragas  # noqa: F401
    except ImportError as exc:
        return "blocked", f"ragas is not importable: {exc}"

    if not _has_openrouter_key():
        return "blocked", (
            "OPENROUTER_API_KEY is not set - put it in .env or export it "
            "before running a live RAGAS judge."
        )
    return "available", None


# ---------------------------------------------------------------------------
# The result contract: one small, inspectable dict shape every framework
# metric run returns - the Day 12 "Result shape" from the design doc's
# Block 2, mirroring `generation_eval.make_finding`'s role for Day 11.
# ---------------------------------------------------------------------------


def make_eval_result(
    *, framework, metric, query_id, score, threshold, passed, reason, status, error, judge_model
):
    """Build one framework-eval result dict - the Day 12 output contract.

    `status` is one of four plain strings, always set, always inspectable
    without re-deriving it from the other fields:

    - `"skipped"` - the default (`live=False`): no import, no key check, no
      network call happened at all. This is the status every deterministic
      test run gets, and the reason the default test suite never touches
      OpenRouter.
    - `"blocked"` - `live=True` was passed, but `deepeval_status`/
      `ragas_status` says the dependency or `OPENROUTER_API_KEY` isn't
      available. Still zero network calls.
    - `"ok"` - a real judge call happened and returned a real score.
    - `"error"` - `live=True`, the dependency/key were fine, but the live
      call itself raised (a provider hiccup, a malformed response, a
      timeout). Caught and reported here rather than left to crash the
      whole run, so one flaky query doesn't take down a Q001+Q091 sweep.

    `score`/`passed`/`reason`/`judge_model` are all `None` unless
    `status == "ok"` - a caller should always check `status` first rather
    than assuming `score` is a number.
    """
    return {
        "framework": framework,
        "metric": metric,
        "query_id": query_id,
        "score": score,
        "threshold": threshold,
        "passed": passed,
        "reason": reason,
        "status": status,
        "error": error,
        "judge_model": judge_model,
    }


# ---------------------------------------------------------------------------
# DeepEval adapter: neutral case -> LLMTestCase -> FaithfulnessMetric
# ---------------------------------------------------------------------------


def to_deepeval_test_case(case):
    """Reshape one neutral eval case into DeepEval's `LLMTestCase`.

    Only the three fields `FaithfulnessMetric` actually requires -`input`,
    `actual_output`, `retrieval_context` - plus `expected_output`, which
    faithfulness itself ignores but a later contextual-recall pass (not
    built today - see the module docstring) would need, so building it in
    here now costs nothing and saves a second near-identical adapter
    function later.
    """
    from deepeval.test_case import LLMTestCase

    return LLMTestCase(
        input=case["input"],
        actual_output=case["actual_output"],
        expected_output=case["expected_output"],
        retrieval_context=case["retrieval_context"],
    )


def run_deepeval_faithfulness(case, threshold=0.5, live=False):
    """Run DeepEval's `FaithfulnessMetric` against one case.

    `live=False` (the default) returns a `status="skipped"` result
    immediately - no `import deepeval`, no environment read, no network
    call. This is what makes it safe for `evaluate_generated_answer`-style
    code (or a pytest run) to call this function unconditionally without
    ever risking a live API call by accident.
    """
    if not live:
        return make_eval_result(
            framework="deepeval",
            metric="faithfulness",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="skipped",
            error="live=False (the default) - pass live=True to actually call the judge model.",
            judge_model=None,
        )

    status, reason = deepeval_status()
    if status == "blocked":
        return make_eval_result(
            framework="deepeval",
            metric="faithfulness",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="blocked",
            error=reason,
            judge_model=None,
        )

    try:
        from deepeval.metrics import FaithfulnessMetric

        # model=None: use the OpenRouter default already configured via
        # `deepeval set-openrouter` (see JUDGE_MODEL's comment above) rather
        # than wiring a second, possibly-drifting model string in here.
        metric = FaithfulnessMetric(threshold=threshold, model=None, include_reason=True)
        test_case = to_deepeval_test_case(case)

        # DeepEval's `Verdicts` schema (deepeval/metrics/faithfulness/schema.py)
        # has an *optional* `reason` field. When DeepEval asks the provider for
        # a strict JSON-schema-constrained response, OpenAI's strict mode
        # requires every field in the schema to also be listed as `required` -
        # DeepEval's own schema builder
        # (deepeval/models/llms/gateway_model.py:_schema_response_format)
        # doesn't do that, so this specific request is rejected by the
        # provider every time, and DeepEval catches that itself and silently
        # retries with plain (non-schema-constrained) JSON parsing - which
        # works fine and is where the real score/reason below come from. This
        # is a real bug inside deepeval==4.2.3 (confirmed: still the latest
        # PyPI release), not something wrong with this project's model/key
        # setup - the warning is suppressed here, narrowly, because it is
        # pure noise about a fallback that already succeeds.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message=r"Structured outputs not supported for model .*", category=UserWarning
            )
            metric.measure(test_case)
    except Exception as exc:  # noqa: BLE001 - a live provider/judge failure degrades to a reported status, see make_eval_result's docstring
        return make_eval_result(
            framework="deepeval",
            metric="faithfulness",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="error",
            error=str(exc),
            judge_model=None,
        )

    return make_eval_result(
        framework="deepeval",
        metric="faithfulness",
        query_id=case["query_id"],
        score=metric.score,
        threshold=threshold,
        passed=metric.success,
        reason=metric.reason,
        status="ok",
        error=None,
        # Read from the metric itself (e.g. "openai/gpt-4o-mini
        # (OpenRouter)") rather than hard-coded, so this always reflects
        # what DeepEval actually used, not what this file assumes it used.
        judge_model=metric.evaluation_model,
    )


def run_deepeval_contextual_recall(case, threshold=0.5, live=False):
    """Run DeepEval's `ContextualRecallMetric` against one case.

    Line-for-line the same shape as `run_deepeval_faithfulness` above -
    same `live=False`-by-default skip, same `deepeval_status()` blocked
    check, same `status="error"` catch-all - because the only thing that
    actually differs between "faithfulness" and "contextual recall" here is
    which DeepEval metric class gets built and measured. Keeping that
    structure identical (rather than writing one generic
    `_run_deepeval_metric(metric_class, ...)` helper) is a deliberate,
    small amount of repetition: with only two metrics, a reader can compare
    this function to `run_deepeval_faithfulness` line by line and see
    exactly what changed, instead of chasing an extra layer of indirection
    for a two-case abstraction that doesn't earn its keep yet.

    Unlike faithfulness, `ContextualRecallMetric` reads `expected_output`
    (the query's real `expected_answer`) as well as `retrieval_context` -
    both already present on `to_deepeval_test_case`'s output, unchanged
    from Day 12, since faithfulness simply never needed that third field
    before now.
    """
    if not live:
        return make_eval_result(
            framework="deepeval",
            metric="contextual_recall",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="skipped",
            error="live=False (the default) - pass live=True to actually call the judge model.",
            judge_model=None,
        )

    status, reason = deepeval_status()
    if status == "blocked":
        return make_eval_result(
            framework="deepeval",
            metric="contextual_recall",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="blocked",
            error=reason,
            judge_model=None,
        )

    try:
        from deepeval.metrics import ContextualRecallMetric

        metric = ContextualRecallMetric(threshold=threshold, model=None, include_reason=True)
        test_case = to_deepeval_test_case(case)

        # Same known deepeval==4.2.3 strict-JSON-schema quirk documented in
        # detail on `run_deepeval_faithfulness` above - DeepEval itself
        # already catches this and falls back to a working, unconstrained
        # JSON parse, so the warning is pure noise here too.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message=r"Structured outputs not supported for model .*", category=UserWarning
            )
            metric.measure(test_case)
    except Exception as exc:  # noqa: BLE001 - see make_eval_result's docstring on "error"
        return make_eval_result(
            framework="deepeval",
            metric="contextual_recall",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="error",
            error=str(exc),
            judge_model=None,
        )

    return make_eval_result(
        framework="deepeval",
        metric="contextual_recall",
        query_id=case["query_id"],
        score=metric.score,
        threshold=threshold,
        passed=metric.success,
        reason=metric.reason,
        status="ok",
        error=None,
        judge_model=metric.evaluation_model,
    )


# ---------------------------------------------------------------------------
# RAGAS adapter: neutral case -> SingleTurnSample -> Faithfulness
# ---------------------------------------------------------------------------


def to_ragas_sample(case):
    """Reshape one neutral eval case into RAGAS's `SingleTurnSample`.

    Same three ideas as DeepEval's `LLMTestCase`, different vocabulary:
    `input` -> `user_input`, `actual_output` -> `response`,
    `retrieval_context` -> `retrieved_contexts` (plural). This vocabulary
    mismatch is exactly what the design doc's "DeepEval and RAGAS use
    similar words, but input contracts matter" section warns about - having
    both `to_..._*` functions in one file, side by side, makes that mapping
    visible instead of buried in two different modules.
    """
    from ragas import SingleTurnSample

    return SingleTurnSample(
        user_input=case["input"],
        response=case["actual_output"],
        retrieved_contexts=case["retrieval_context"],
    )


def run_ragas_faithfulness(case, threshold=0.5, live=False):
    """Run RAGAS's `Faithfulness` metric against one case.

    Same `live=False`-by-default contract as `run_deepeval_faithfulness` -
    see that function's docstring.

    Unlike DeepEval, RAGAS has no CLI/global model config to fall back on:
    `Faithfulness(llm=...)` needs an actual LLM object handed to it. That
    object is a `langchain_openai.ChatOpenAI` pointed at OpenRouter's
    OpenAI-compatible endpoint - the exact same `base_url` (imported from
    `generation.py`, not re-typed) and the same `OPENROUTER_API_KEY` that
    `generation.make_openrouter_client` uses for live answer generation,
    wrapped in RAGAS's own `LangchainLLMWrapper` so RAGAS's metric code can
    call it. `JUDGE_MODEL` (not DeepEval's CLI config) is the source of
    truth for which model that is.

    Also unlike DeepEval, `Faithfulness.single_turn_score(...)` returns only
    a bare float - no reason/explanation text comes back from RAGAS's public
    API the way `FaithfulnessMetric.reason` does. `reason` is reported as
    `None` below, not invented, and `passed` is computed here
    (`score >= threshold`) rather than read off the metric, because RAGAS's
    metric objects don't carry a threshold/pass concept the way DeepEval's
    do.
    """
    if not live:
        return make_eval_result(
            framework="ragas",
            metric="faithfulness",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="skipped",
            error="live=False (the default) - pass live=True to actually call the judge model.",
            judge_model=None,
        )

    status, reason = ragas_status()
    if status == "blocked":
        return make_eval_result(
            framework="ragas",
            metric="faithfulness",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="blocked",
            error=reason,
            judge_model=None,
        )

    try:
        from langchain_openai import ChatOpenAI
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness

        chat_model = ChatOpenAI(
            model=JUDGE_MODEL,
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=OPENROUTER_BASE_URL,
            temperature=0.0,
            timeout=OPENROUTER_TIMEOUT_SECONDS,
            max_tokens=JUDGE_MAX_TOKENS,
        )
        faithfulness_metric = Faithfulness(llm=LangchainLLMWrapper(chat_model))
        score = faithfulness_metric.single_turn_score(to_ragas_sample(case))
    except Exception as exc:  # noqa: BLE001 - see make_eval_result's docstring on "error"
        return make_eval_result(
            framework="ragas",
            metric="faithfulness",
            query_id=case["query_id"],
            score=None,
            threshold=threshold,
            passed=None,
            reason=None,
            status="error",
            error=str(exc),
            judge_model=None,
        )

    return make_eval_result(
        framework="ragas",
        metric="faithfulness",
        query_id=case["query_id"],
        score=score,
        threshold=threshold,
        passed=score >= threshold,
        reason=None,  # RAGAS's public API genuinely does not return one - see docstring above
        status="ok",
        error=None,
        judge_model=f"{JUDGE_MODEL} (OpenRouter)",
    )


# ---------------------------------------------------------------------------
# CLI/demo: Q001 + Q091, faithfulness through both frameworks, plus Day 13's
# DeepEval contextual recall
# ---------------------------------------------------------------------------


def _print_eval_result(result):
    label = f"{result['framework']}/{result['metric']}"
    if result["status"] in ("skipped", "blocked", "error"):
        print(f"  [{result['status'].upper()}] {label}: {result['error']}")
        return
    mark = "PASS" if result["passed"] else "FAIL"
    print(
        f"  [{mark}] {label}: score={result['score']:.2f} "
        f"(threshold={result['threshold']}, judge_model={result['judge_model']})"
    )
    if result["reason"]:
        print(f"         reason: {result['reason']}")


def main() -> None:
    """Build Q001/Q091 framework-eval cases and run every wired metric.

    No `--live` flag means: build both cases (no network needed for that -
    they're plain dict reshaping over `generation_eval.CURATED_FIXTURES`,
    the same already-committed Day 10 transcripts Day 11 uses) and print
    `status="skipped"` for every metric, proving the adapter wiring end to
    end without spending a live API call. Pass `--live` to actually call
    OpenRouter for both Q001 and Q091 - faithfulness through both
    frameworks plus Day 13's DeepEval contextual recall, six live calls
    total, using the cheap `openai/gpt-4o-mini` model (see
    `docs/eval-report.md`'s Day 12/13 sections for real cost/output).
    """
    import argparse

    from generation_eval import CURATED_FIXTURES
    from hybrid_search import load_example_queries

    parser = argparse.ArgumentParser(
        description="Day 12/13: DeepEval + RAGAS faithfulness, plus DeepEval contextual recall, "
        "over the Q001/Q091 calibration fixtures."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually call the OpenRouter judge model (6 live calls). Default: adapter-only, no network.",
    )
    args = parser.parse_args()

    if args.live:
        # Same one-call-at-the-entry-point pattern as generation.main() -
        # see _has_openrouter_key's docstring for why this isn't done inside
        # every function that might need the key.
        load_dotenv()

    queries_by_id = {row["query_id"]: row for row in load_example_queries()}

    for fixture in CURATED_FIXTURES:
        query_row = queries_by_id[fixture["query_id"]]
        case = build_framework_eval_case(query_row, fixture["sources"], fixture["answer_text"])

        print(f"\n{case['query_id']}: {case['input']}")
        _print_eval_result(run_deepeval_faithfulness(case, live=args.live))
        _print_eval_result(run_ragas_faithfulness(case, live=args.live))
        _print_eval_result(run_deepeval_contextual_recall(case, live=args.live))


if __name__ == "__main__":
    main()
