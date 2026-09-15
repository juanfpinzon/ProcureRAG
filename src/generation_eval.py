"""Day 11: does a generated, cited answer actually hold up?

Day 10 (`generation.py`) proved something narrow and useful: every `[n]`
citation in a generated answer can be traced back to a real retrieved
source, or it is flagged as an "orphan" (a hallucinated citation number).
That is **citation validity** - it answers "did the model cite a real
source id?" It does not answer three harder questions a buyer, or an
interviewer, would ask next:

1. Was the *right* evidence even retrieved, so a correct answer was even
   possible? (**context/retrieval recall**)
2. Does the answer actually say the things the query's known-correct
   `expected_answer` says it should? (**completeness**)
3. Does the answer's language stay inside what its cited sources actually
   support, or does it quietly extrapolate past them? (**faithfulness**,
   approximated here, not proven)

`docs/eval-report.md`'s Day 10 section already found a real example of the
gap between "citations are clean" and "the answer is actually right": Q091
("What approvals and security evidence do I need for a EUR 120,000 SaaS
renewal?"). The live Day 10 transcript for Q091 has zero orphan citations
and reads as a coherent, well-organized answer - and it still cannot state
the buyer's real approval band (Band 3, EUR 50,000-250,000) or the renewal
usage-data evidence, because retrieval never surfaced `POL-001` or
`GUIDE-002` in the first place. A citation checker has nothing to say about
that failure, because every citation it *does* see is genuinely valid. This
module exists to make that second kind of failure visible in code, not just
in a paragraph of prose in a report.

**The four checks, each answering one narrow question:**

1. `check_citation_validity` - reuses `generation.validate_citations`
   unchanged. Fails if the answer cites a source number that was never
   retrieved (a hallucinated citation).
2. `check_context_recall` - compares the query's *primary* (grade-2)
   expected document ids (`relevance_grades`, the same "primary" vocabulary
   `eval_metrics.primary_count` already uses) against the doc ids actually
   present in the retrieved `sources` - regardless of whether the model
   chose to cite them. This is deliberately a *retrieval* check, not a
   generation check: a document that never reached the prompt could not
   possibly be cited correctly, no matter how careful the generation step
   is. This is the check that automatically catches Q091's failure.
3. `check_expected_terms` - for a small, hand-curated set of queries only
   (see "Deterministic, not universal" below), asserts that specific
   required facts/terms from the query's real `expected_answer` appear
   somewhere in the generated answer text.
4. `check_unsupported_inference` - scans the answer text for a short,
   hand-curated list of hedge/extrapolation phrases ("at minimum", "equal
   or greater", ...). This is a coarse proxy for faithfulness, not a proof
   of it: finding one of these phrases means "a human (or a future
   LLM-as-judge pass) should look at whether this claim actually follows
   from its cited source", not "this claim is definitely wrong". The real
   Q091 transcript below contains exactly this pattern - the model reasons
   "a EUR 120,000 commitment is of equal or greater significance, so this
   approval level applies at minimum", which is a caveated inference past
   what its cited source ([3], written for a EUR 60,000 example) actually
   states.

**Deterministic, not universal.** Checks 1 and 2 run on *any* query that
carries `relevance_grades` - nothing about them is specific to Q001 or
Q091. Check 3 (expected terms) only runs when the caller supplies a
`required_terms` list, because there is no field in
`data/corpus_v1/example_queries.jsonl` that names which exact words a
correct answer must use - inventing a generic keyword-extractor out of
`expected_answer` would be exactly the "broad fake metric that cannot
explain itself" the Day 11 design doc warns against. Curating that list by
hand, for a small number of queries, and being honest that it only covers
those queries, is the deliberately smaller and more defensible choice.

**What this deliberately does not do.** No LLM-as-judge call, no semantic
similarity model, no general claim-segmentation NLP, no framework
integration (DeepEval/RAGAS) - see `docs/day-11-grounded-answer-evaluation.md`
for why deterministic, hand-inspectable checks come first. Check 4 in
particular is a known-shallow heuristic (see its own docstring) and the eval
report says so explicitly rather than dressing it up as more than it is.

**Test boundary.** Every check function here is a pure function over plain
dicts and strings - no network call, no model load, nothing that needs
`OPENROUTER_API_KEY`. `CURATED_FIXTURES` below hard-codes the exact
retrieved-source shape and generated-answer text Day 10's real, already
committed live run produced for Q001 and Q091 (see `docs/eval-report.md`,
"Day 10: Source-cited answer generation" -> "Demo output") - so both this
module's `main()` and `tests/test_generation_eval.py` re-check output that
already happened, rather than generating anything new.
"""

from eval_metrics import grades_for_query
from generation import validate_citations
from hybrid_search import load_example_queries

# ---------------------------------------------------------------------------
# Check 4's hand-curated hedge/extrapolation phrases (see module docstring)
# ---------------------------------------------------------------------------

# Deliberately short and hand-picked, not learned or NLP-derived. Every
# phrase here is the kind of thing a model writes when it is reasoning past
# what its cited source actually says, rather than quoting/paraphrasing it -
# "equal or greater" and "at minimum" are both literally present in the real
# Q091 transcript below, next to a claim its cited source doesn't fully
# support (see the module docstring's walkthrough).
INFERENCE_MARKER_PHRASES = (
    "at minimum",
    "equal or greater",
    "by extension",
    "presumably",
    "it is reasonable to assume",
    "likely applies",
    "should also apply",
)


# ---------------------------------------------------------------------------
# Small helpers: what "primary expected document" and "retrieved context"
# mean, reused by more than one check below
# ---------------------------------------------------------------------------


def primary_expected_doc_ids(query_row):
    """Return the set of grade-2 ("primary") expected document ids.

    Reuses `eval_metrics.grades_for_query` and the exact "primary" = grade 2
    vocabulary `eval_metrics.primary_count` already established on the
    retrieval side, instead of inventing a second definition of "primary"
    for the generation side. A primary document is evidence a *correct*
    answer cannot do without; a secondary (grade-1) document is
    corroborating context, so `check_context_recall` below deliberately
    does not demand secondary documents show up in context too - only
    missing primary evidence is treated as a hard failure.
    """
    grades = grades_for_query(query_row)
    return {doc_id for doc_id, grade in grades.items() if grade == 2}


def context_doc_ids(sources):
    """Return the set of doc ids actually present in the retrieved context.

    This reads `sources` (the `generation.build_sources` output shape) for
    *every* document that reached the prompt, regardless of whether the
    model went on to cite it. That is the point: retrieval context recall
    and citation behavior are different questions, and collapsing them into
    one number would hide which one actually failed.
    """
    return {source["doc_id"] for source in sources}


# ---------------------------------------------------------------------------
# The finding contract: one small, inspectable dict shape every check
# returns, instead of a bare True/False a human would have to go re-derive
# the reason for.
# ---------------------------------------------------------------------------


def make_finding(*, query_id, check, passed, severity, message, expected, actual, cited_doc_ids):
    """Build one finding dict - the Day 11 output contract, in one place.

    Every field the Day 11 design doc's "Block 2" contract asks for:
    `query_id` and `check` say *what was tested*; `passed`/`severity` say
    *the verdict* (`severity` is `"info"` on a pass, `"fail"` for a
    deterministic contract violation, `"warn"` for a heuristic flag that
    needs human/LLM-as-judge follow-up - see `check_unsupported_inference`);
    `message` is a one-line human-readable reason; `expected`/`actual` are
    the concrete evidence behind that reason, so a failure is diagnosable
    without re-running anything; `cited_doc_ids` is attached to every
    finding (not just citation-related ones) so a reader always has "what
    did the answer actually cite" next to any other finding about it,
    without cross-referencing a separate report.
    """
    return {
        "query_id": query_id,
        "check": check,
        "passed": passed,
        "severity": severity,
        "message": message,
        "expected": expected,
        "actual": actual,
        "cited_doc_ids": cited_doc_ids,
    }


# ---------------------------------------------------------------------------
# Check 1 — citation validity (reuses Day 10's validate_citations)
# ---------------------------------------------------------------------------


def check_citation_validity(query_row, citations, cited_doc_ids):
    """Fail if the answer cites a source number that was never retrieved.

    `citations` is the dict `generation.validate_citations` already
    returns - this function does not re-parse `[n]` markers itself, it only
    turns that existing report into a Day 11 finding. This is necessary but,
    per the module docstring, nowhere near sufficient: an answer can pass
    this check perfectly (as both Q001 and Q091's real transcripts do) and
    still be incomplete - see `check_context_recall` below for the check
    that actually catches that.
    """
    orphan_ids = citations["orphan_ids"]
    passed = len(orphan_ids) == 0
    return make_finding(
        query_id=query_row["query_id"],
        check="citation_validity",
        passed=passed,
        severity="info" if passed else "fail",
        message=(
            "every [n] citation traces to a real retrieved source"
            if passed
            else f"answer cites source number(s) {orphan_ids} that do not exist in "
            "the retrieved sources - a hallucinated citation"
        ),
        expected="no citation numbers outside the retrieved source list",
        actual={"cited_ids": citations["cited_ids"], "orphan_ids": orphan_ids},
        cited_doc_ids=cited_doc_ids,
    )


# ---------------------------------------------------------------------------
# Check 2 — expected document coverage / retrieval-context recall
# ---------------------------------------------------------------------------


def check_context_recall(query_row, sources, cited_doc_ids):
    """Fail if a primary expected document never reached the retrieved context.

    This is the check that automatically catches Q091's known failure:
    `POL-001` and `GUIDE-002` are both grade-2 ("primary") for Q091, but
    neither is in the five sources Day 10's real retrieval step returned
    for that query - so no amount of careful, well-cited generation could
    have produced the correct approval-band or renewal-timing evidence.
    This check flags *that*, at the retrieval boundary, instead of only
    being discoverable by a human reading the final answer and noticing
    something felt incomplete.

    A query with zero grade-2 documents in `relevance_grades` has nothing
    for this check to enforce, and it passes vacuously - a real limitation
    worth naming (see `docs/eval-report.md`'s Day 11 addendum) rather than
    quietly treating "nothing to check" the same as "checked and fine".
    """
    primary_ids = primary_expected_doc_ids(query_row)
    retrieved_ids = context_doc_ids(sources)
    missing = sorted(primary_ids - retrieved_ids)
    passed = len(missing) == 0
    return make_finding(
        query_id=query_row["query_id"],
        check="context_recall",
        passed=passed,
        severity="info" if passed else "fail",
        message=(
            "every primary (grade-2) expected document reached the retrieved context"
            if passed
            else f"primary document(s) {missing} were never retrieved - the retrieval "
            "step, not the generation step, is why the answer can't fully cover this "
            "query, regardless of how well it cites what it *did* receive"
        ),
        expected=sorted(primary_ids),
        actual=sorted(retrieved_ids),
        cited_doc_ids=cited_doc_ids,
    )


# ---------------------------------------------------------------------------
# Check 3 — expected answer terms/evidence (curated queries only)
# ---------------------------------------------------------------------------


def check_expected_terms(query_row, answer_text, required_terms, cited_doc_ids):
    """Fail if the answer text is missing a hand-curated required term/fact.

    `required_terms` is supplied by the caller (see `CURATED_FIXTURES`
    below), never derived automatically from `expected_answer` - see the
    module docstring's "Deterministic, not universal" section for why a
    hand-curated list, honestly scoped to a few queries, beats a generic
    keyword extractor that would silently mis-grade every other query.
    Matching is a plain case-insensitive substring check - simple enough to
    read and trust at a glance, at the cost of being fooled by a term used
    in an unrelated sentence. That tradeoff is named, not hidden - see
    `docs/eval-report.md`'s Day 11 addendum for a worked example of exactly
    that failure mode (the string "12 months" appears in both a renewal
    document and an unrelated security-risk clause).
    """
    answer_lower = answer_text.lower()
    missing = [term for term in required_terms if term.lower() not in answer_lower]
    present = [term for term in required_terms if term not in missing]
    passed = len(missing) == 0
    return make_finding(
        query_id=query_row["query_id"],
        check="expected_terms",
        passed=passed,
        severity="info" if passed else "fail",
        message=(
            "answer text contains every curated required term/fact"
            if passed
            else f"answer text is missing required term(s)/fact(s): {missing}"
        ),
        expected=list(required_terms),
        actual=present,
        cited_doc_ids=cited_doc_ids,
    )


# ---------------------------------------------------------------------------
# Check 4 — unsupported/caveated inference (heuristic proxy, not a proof)
# ---------------------------------------------------------------------------


def check_unsupported_inference(query_row, answer_text, cited_doc_ids):
    """Flag hedge/extrapolation phrasing that may reach past a cited source.

    This is the weakest check here on purpose, and the docs say so: a
    substring match against `INFERENCE_MARKER_PHRASES` cannot know whether
    a flagged sentence is actually unsupported - it can only say "this
    phrasing pattern is the kind a model uses when it's reasoning past its
    evidence, go look". A hit is `severity="warn"`, not `"fail"`, precisely
    because it is a flag for human/LLM-as-judge review, not a proven
    violation - unlike checks 1-3, which are hard, inspectable contract
    violations.
    """
    answer_lower = answer_text.lower()
    found = [phrase for phrase in INFERENCE_MARKER_PHRASES if phrase in answer_lower]
    passed = len(found) == 0
    return make_finding(
        query_id=query_row["query_id"],
        check="unsupported_inference",
        passed=passed,
        severity="info" if passed else "warn",
        message=(
            "no inference-marker phrasing detected"
            if passed
            else f"answer contains inference-marker phrasing {found} - a claim may "
            "extrapolate past what its cited source actually states; this is a flag "
            "for human/LLM-as-judge review, not a proven faithfulness violation"
        ),
        expected="no hedged extrapolation beyond cited source text",
        actual=found,
        cited_doc_ids=cited_doc_ids,
    )


# ---------------------------------------------------------------------------
# The entry point: run every check for one (query, sources, answer) triple
# ---------------------------------------------------------------------------


def evaluate_generated_answer(query_row, sources, answer_text, required_terms=None):
    """Run all Day 11 checks for one generated answer and return its findings.

    `citations` and `cited_doc_ids` are each computed exactly once here and
    handed to every check that needs them, instead of every check re-parsing
    the answer's `[n]` markers itself - the same "reuse, don't duplicate"
    instruction the Day 11 design doc gives for `validate_citations`.

    `required_terms=None` (the default) skips `check_expected_terms`
    entirely rather than forcing a fake "not applicable" finding into the
    list - a query with no curated terms simply was not asked that
    question, which is different from asking it and getting a pass.
    """
    citations = validate_citations(answer_text, sources)
    doc_id_by_source_id = {source["source_id"]: source["doc_id"] for source in sources}
    cited_doc_ids = sorted({doc_id_by_source_id[sid] for sid in citations["valid_ids"]})

    findings = [
        check_citation_validity(query_row, citations, cited_doc_ids),
        check_context_recall(query_row, sources, cited_doc_ids),
        check_unsupported_inference(query_row, answer_text, cited_doc_ids),
    ]
    if required_terms is not None:
        findings.append(
            check_expected_terms(query_row, answer_text, required_terms, cited_doc_ids)
        )
    return findings


# ---------------------------------------------------------------------------
# Curated fixtures: the real Q001/Q091 sources and answer text Day 10's
# live run actually produced (see docs/eval-report.md, "Demo output"),
# hard-coded here so this module and its tests never need network access,
# an API key, or the embedding/reranking pipeline to demonstrate the Day 11
# checks against a real, already-known failure.
#
# `sources[].text` below are the literal full retrieved chunk texts (and
# `chunk_id`, the real chunk id, not a placeholder) - re-derived by
# re-running the exact retrieval pipeline (`chunk_corpus` ->
# `build_chunk_lexical_index`/`build_chunk_semantic_index` ->
# `two_stage_rerank`) for Q001/Q091 on 2026-09-15, the same day this fixture
# was updated for Day 12's framework-eval review. This is not a live/network
# step - retrieval here is BM25 + local sentence-transformer embeddings + a
# local cross-encoder reranker, all deterministic given the same corpus and
# models, no LLM call involved - and the resulting `doc_id` order was
# confirmed to match Day 10's original transcript exactly for both queries,
# which is what makes swapping in the fuller text a faithful *replacement*
# rather than a different, unverified retrieval run. Earlier versions of
# this fixture used short representative quotes instead of the full chunk
# text; that was adequate for Day 11's deterministic checks (which only
# depend on `doc_id`/citation ids/`answer_text`, never on `sources[].text`
# itself), but Day 12's DeepEval/RAGAS faithfulness metrics score the
# generated answer *against `retrieval_context`* - an abbreviated context
# would have meant the live judge was never evaluating the actual evidence
# Day 10's model saw. `doc_id`/`title` still match Day 10's real transcript
# exactly. `answer_text` in both fixtures is still the real, unedited Day 10
# transcript text, unchanged by this update.
# ---------------------------------------------------------------------------


def _source(source_id, doc_id, title, text, chunk_id=None):
    return {
        "source_id": source_id,
        "doc_id": doc_id,
        "title": title,
        "chunk_id": chunk_id if chunk_id is not None else f"{doc_id}::chunk-{source_id}",
        "text": text,
        "rank": source_id,
        "score": None,
    }


Q001_SOURCES = [
    _source(1, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "Tell Procurement Operations your genuine required date at intake so the "
            "realistic route can be chosen. Do I need three quotes Three qualified bids "
            "are required above €25,000 and up to €250,000 of total committed value. "
            "Above €250,000 a formal request for proposal is required.",
            chunk_id="FAQ-001::chunk-12"),
    _source(2, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "Above €250,000 a formal request for proposal is required. Below €25,000 no "
            "formal competition is needed, though you should still be able to show the "
            "price is reasonable. If competition is genuinely not possible, a sourcing "
            "exception must be approved before the award, not afterwards.",
            chunk_id="FAQ-001::chunk-13"),
    _source(3, "POL-001", "Global Procurement Policy — Approval Thresholds and Delegation of Authority",
            "Approval Bands The following approval bands apply to the total committed "
            "value expressed in EUR. Amounts in other currencies are converted at the "
            "monthly Group corporate rate published by Treasury on the first working day "
            "of each month. Band 1 (below €5,000): approval by the Budget Owner for the "
            "cost centre being charged.",
            chunk_id="POL-001::chunk-4"),
    _source(4, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "Do not ask a colleague to approve on the approver's behalf using their "
            "account. How is the approval level decided By the total committed value of "
            "the commitment over its full term, not by the invoice amount and not by the "
            "amount falling in this financial year. A three-year service at €20,000 per "
            "year is a €60,000 commitment and needs VP Procurement approval with a "
            "Finance review, not Category Manager approval.",
            chunk_id="FAQ-001::chunk-5"),
    _source(5, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "A three-year service at €20,000 per year is a €60,000 commitment and needs "
            "VP Procurement approval with a Finance review, not Category Manager "
            "approval. If you are unsure of the value, use a good-faith estimate at the "
            "top of the expected range. Can I split a request to keep it under a "
            "threshold No.",
            chunk_id="FAQ-001::chunk-6"),
]

# `Q001_SOURCES`/`Q091_SOURCES` above were re-derived from a live re-run of
# the real retrieval pipeline on 2026-09-15 (see the block comment above
# `_source`) - notice source [2] above is *not* a restatement of the
# three-qualified-bids rule the way the pre-Day-12-review placeholder text
# implied it was. This is exactly the kind of thing full chunk text
# surfaces that a hand-picked representative quote can hide: the real
# citation [2] in `Q001_ANSWER_TEXT` below is topically adjacent (the same
# competition-threshold section) but does not itself repeat the "three
# qualified bids" sentence - only source [1] does. A faithfulness judge
# reading the *real* `retrieval_context` sees that distinction; a judge
# reading only the old abbreviated placeholder could not have.

# Real, unedited Day 10 transcript for Q001 - see docs/eval-report.md,
# "Demo output", lines under "Q001 (threshold): ...".
Q001_ANSWER_TEXT = (
    "For a EUR 60,000 purchase order, **VP Procurement approval with a Finance review** "
    "is required — not Category Manager approval.\n\n"
    "This is established by the following sources:\n\n"
    "- **[4]** states: *\"A three-year service at €20,000 per year is a €60,000 commitment "
    "and needs VP Procurement approval with a Finance review, not Category Manager "
    "approval.\"*\n"
    "- **[5]** repeats the same rule: *\"A three-year service at €20,000 per year is a "
    "€60,000 commitment and needs VP Procurement approval with a Finance review, not "
    "Category Manager approval.\"*\n\n"
    "Additionally, **[4]** clarifies that the approval level is determined by the **total "
    "committed value over the full term** of the commitment, not by the invoice amount or "
    "the amount falling within a single financial year. **[3]** confirms that approval "
    "bands apply to the total committed value expressed in EUR.\n\n"
    "**Note:** Separately, **[1]** and **[2]** indicate that a €60,000 purchase also "
    "triggers a competition requirement — three qualified bids are required above €25,000 "
    "and up to €250,000 of total committed value."
)

# expected_answer for Q001 hinges on the approval role ("VP Procurement...
# Finance review") - both phrases the real transcript above actually uses.
# It does *not* literally say "Band 3" (it argues from precedent instead of
# naming the band), which is exactly why this required-terms list is a
# hand-curated, honest subset of expected_answer rather than the whole
# thing pasted in.
Q001_REQUIRED_TERMS = ("VP Procurement", "Finance review")


Q091_SOURCES = [
    _source(1, "SOP-001", "Standard Operating Procedure — Three-Bid Requirement and Sourcing Exception Handling",
            "The approver must be independent of the requesting business function. "
            "Procurement Governance reviews every exception above €250,000 before the "
            "approver receives it, and may return the request for further evidence. "
            "Duration and Renewal Limits An approved exception is valid for a maximum of "
            "12 months or for the duration of the specific award, whichever is shorter.",
            chunk_id="SOP-001::chunk-12"),
    _source(2, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "Tell Procurement Operations your genuine required date at intake so the "
            "realistic route can be chosen. Do I need three quotes Three qualified bids "
            "are required above €25,000 and up to €250,000 of total committed value. "
            "Above €250,000 a formal request for proposal is required.",
            chunk_id="FAQ-001::chunk-12"),
    _source(3, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "A three-year service at €20,000 per year is a €60,000 commitment and needs "
            "VP Procurement approval with a Finance review, not Category Manager "
            "approval. If you are unsure of the value, use a good-faith estimate at the "
            "top of the expected range. Can I split a request to keep it under a "
            "threshold No.",
            chunk_id="FAQ-001::chunk-6"),
    _source(4, "POL-003", "Information Security and Data Protection Requirements for Technology Suppliers",
            "Risk acceptance may not exceed 12 months and may not be renewed more than "
            "once. Renewal and Continuous Assurance Certification evidence is refreshed "
            "annually. A lapsed certificate is treated as a control failure and triggers "
            "a review of whether the service may continue.",
            chunk_id="POL-003::chunk-13"),
    _source(5, "SOP-001", "Standard Operating Procedure — Three-Bid Requirement and Sourcing Exception Handling",
            "On the second renewal the buyer must record a plan and a date for a "
            "competitive event or a Category Council decision to designate the supplier "
            "as strategic and single-sourced by design. Record Keeping and Audit Trail "
            "The following must exist in Ariba Sourcing for every award above €25,000: "
            "the requirement document issued to suppliers, the invitation list with "
            "dates, the bids received or the exception form, the comparison or "
            "evaluation record, the award recommendation, and the approval evidence. "
            "Records are retained for seven years.",
            chunk_id="SOP-001::chunk-14"),
]

# Real, unedited Day 10 transcript for Q091 - see docs/eval-report.md,
# "Demo output", lines under "Q091 (multi_doc): ...". Note the sentence in
# section 1: "a €120,000 commitment is of equal or greater significance, so
# this approval level applies at minimum" - a real, live example of
# check_unsupported_inference's target pattern, not a made-up one.
Q091_ANSWER_TEXT = (
    "## Approvals and Security Evidence for a EUR 120,000 SaaS Renewal\n\n"
    "### 1. Sourcing and Approval Requirements\n\n"
    "**Three qualified bids are required.** A EUR 120,000 commitment falls in the "
    "€25,000–€250,000 range, which mandates three qualified bids [2]. You cannot split "
    "the request to stay under a threshold [3].\n\n"
    "**VP Procurement approval with Finance review.** Based on the precedent in the "
    "sources, a commitment of this significance requires VP Procurement approval with a "
    "Finance review [3]. (The source explicitly states this for a €60,000 commitment; a "
    "€120,000 commitment is of equal or greater significance, so this approval level "
    "applies at minimum.)\n\n"
    "**Records must be maintained in Ariba Sourcing.** For every award above €25,000, the "
    "following must exist: the requirement document issued to suppliers, the invitation "
    "list with dates, the bids received (or the exception form), the comparison/evaluation "
    "record, the award recommendation, and the approval evidence. Records are retained for "
    "seven years [5].\n\n"
    "### 2. Security and Data Protection Evidence\n\n"
    "**Annual certification refresh.** Certification evidence must be refreshed annually "
    "as part of continuous assurance [4].\n\n"
    "**Risk acceptance limits.** Risk acceptance may not exceed 12 months and may not be "
    "renewed more than once [4].\n\n"
    "**Lapsed certificates.** A lapsed certificate is treated as a control failure and "
    "triggers a review of whether the service may continue [4].\n\n"
    "### 3. If Seeking a Sourcing Exception\n\n"
    "If you intend to single-source without three bids, any exception above €250,000 must "
    "be reviewed by Procurement Governance before the approver receives it [1]. For a "
    "€120,000 award (below €250,000), the standard three-bid rule applies per [2], but "
    "exception handling procedures still govern the process [1]. An approved exception is "
    "valid for a maximum of 12 months or the duration of the specific award, whichever is "
    "shorter [1]. On a second renewal, a plan and date for a competitive event (or a "
    "Category Council decision to designate the supplier as strategic/single-sourced) must "
    "be recorded [5].\n\n"
    "---\n\n"
    "**Summary:** For a EUR 120,000 SaaS renewal, you need three qualified bids [2], VP "
    "Procurement approval with Finance review [3], full Ariba Sourcing records [5], and "
    "annual security certification evidence with risk acceptance not exceeding 12 months "
    "and not renewed more than once [4]."
)

# "Band 3" (the actual approval-band name, from POL-001) and "usage data"
# (the renewal-timing evidence, from GUIDE-002) are both genuinely absent
# from the real transcript above - not because the model reasoned poorly,
# but because POL-001 and GUIDE-002 never reached its retrieved context in
# the first place (see check_context_recall). Note "12 months" appears
# twice in the real transcript already, for an *unrelated* reason (security
# risk-acceptance duration, from POL-003) - which is exactly why "usage
# data" is the safer required term for the renewal-timing gap than "12
# months" would have been; see check_expected_terms's docstring.
Q091_REQUIRED_TERMS = ("Band 3", "usage data")


CURATED_FIXTURES = [
    {
        "query_id": "Q001",
        "sources": Q001_SOURCES,
        "answer_text": Q001_ANSWER_TEXT,
        "required_terms": Q001_REQUIRED_TERMS,
    },
    {
        "query_id": "Q091",
        "sources": Q091_SOURCES,
        "answer_text": Q091_ANSWER_TEXT,
        "required_terms": Q091_REQUIRED_TERMS,
    },
]


# ---------------------------------------------------------------------------
# CLI/demo: print a human-readable finding report for both curated fixtures
# ---------------------------------------------------------------------------


def _print_findings(findings):
    for finding in findings:
        mark = "PASS" if finding["passed"] else finding["severity"].upper()
        print(f"  [{mark}] {finding['check']}: {finding['message']}")
        if not finding["passed"]:
            print(f"         expected: {finding['expected']}")
            print(f"         actual:   {finding['actual']}")


def main() -> None:
    """Run the Day 11 checks against both curated fixtures and print a report.

    No network call, no API key, no retrieval pipeline load: `CURATED_FIXTURES`
    above already hard-codes the exact sources/answer-text Day 10's real live
    run produced, so this only re-checks output that already exists.
    `load_example_queries()` is still used to pull the real `query_row` for
    each fixture (its `relevance_grades`, `expected_answer`, etc.) rather than
    duplicating that data here too.
    """
    queries_by_id = {row["query_id"]: row for row in load_example_queries()}

    for fixture in CURATED_FIXTURES:
        query_row = queries_by_id[fixture["query_id"]]
        findings = evaluate_generated_answer(
            query_row,
            fixture["sources"],
            fixture["answer_text"],
            required_terms=fixture["required_terms"],
        )

        print(f"\n{query_row['query_id']} ({query_row['query_type']}): {query_row['query']}")
        _print_findings(findings)


if __name__ == "__main__":
    main()
