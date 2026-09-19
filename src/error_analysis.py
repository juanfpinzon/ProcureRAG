"""Day 13: turn individual generated-answer failures into a failure taxonomy.

Day 11 (`generation_eval.py`) and Day 12 (`framework_eval.py`) each built one
*layer* of evaluation: deterministic checks, then a live LLM-as-judge score.
Both already proved a specific, important gap on Q091: the answer can be
"faithful" (Day 12) and can pass citation hygiene (Day 11's
`check_citation_validity`) while still being wrong for a buyer, because Day
11's `check_context_recall` shows two primary documents never reached the
model's context in the first place.

Day 13 asks a different, higher-level question than either of those checks
can answer on its own: **looking across several real cases, what is actually
going wrong, and who owns the fix?** A single check can only say "this one
thing passed or failed for this one query." A human has to read several
cases side by side to notice a pattern - "every failure so far is a
retrieval problem, not a prompt problem" is not something any individual
`check_*` function in `generation_eval.py` was ever designed to say. That is
what this module is for: a small, fixed **failure taxonomy** (one label per
case, chosen by a human reading the evidence - see `ROOT_CAUSE_LABELS`
below) and a **case record** shape that carries the evidence a reader needs
to check that label without re-running anything.

This is deliberately *not* a general tracing/observability platform. It is
five real, hand-picked cases (`CASES` below), each built from either an
already-committed Day 10 transcript (Q001, Q091 - reused from
`generation_eval.CURATED_FIXTURES`, not re-typed) or a fresh, real run of
this project's own retrieval pipeline plus a live OpenRouter generation call
(Q093, Q016, Q004 - captured on 2026-09-19, see each fixture's comment for
the exact command). See `docs/eval-report.md`'s Day 13 section for the full
per-case write-up and the recommended Q091/multi-doc repair path this
taxonomy leads to.

**Why a human picks the label, not a heuristic.** `build_case_record` below
does not *compute* `human_root_cause_label` - it requires the caller to pass
one in, and only checks that it is a real label from `ROOT_CAUSE_LABELS`.
This mirrors the Hamel/Shreya "open coding" idea the Day 13 design doc
points at: a human reads the real evidence (the query, what was retrieved,
what was generated, Day 11's deterministic findings) and decides *why* it
failed. Automating that decision would just be inventing a second opinion
without ever having looked at a single trace - exactly the "metric shopping
before error analysis" trap the design doc warns against.

**What this reuses instead of duplicating.** Every actual pass/fail
judgement here (citation validity, context recall) is Day 11's
`evaluate_generated_answer` output, unchanged - this module only reshapes
those findings into a `(root cause, evidence, repair)` record a reader can
scan quickly. No new detection logic is added; Day 13 is an analysis layer
on top of Day 11/12, not a fifth deterministic check.
"""

from generation_eval import CURATED_FIXTURES, _source, evaluate_generated_answer

# ---------------------------------------------------------------------------
# The failure taxonomy: six labels, each meant to point at a different owner
# for the fix - see the Day 13 design doc's "Retrieval failure and generation
# failure are different owners" section. A case gets exactly one label; real
# secondary observations go in its free-text `notes` instead of a second
# label, so the table below always answers "what do I fix first?" with one
# unambiguous word per row.
# ---------------------------------------------------------------------------

ROOT_CAUSE_LABELS = (
    # Retrieval never surfaced a primary document at all - Day 11's
    # `check_context_recall` fails, and no prompt/generation change could
    # have fixed it, because the evidence was never shown to the model.
    "retrieval_miss",
    # The evidence was retrieved *somewhere* in the pipeline, but never made
    # it into the prompt shown to the generator (e.g. cut by a `max_sources`
    # cap). Distinct from `retrieval_miss`: the fix here is "show the model
    # more of what was already found", not "search differently."
    "context_truncation_or_construction",
    # A cited source id is real (Day 11's `check_citation_validity` passes),
    # but the specific claim next to that citation is not actually
    # supported by that source's text - a citation that points at the wrong
    # evidence, not a hallucinated one.
    "citation_source_support_gap",
    # All the right documents reached the model's context, but the answer
    # still leaves out something the query genuinely needed - the retrieval
    # step did its job; the generation step under-used what it was given.
    "answer_completeness_gap",
    # A deterministic finding (Day 11) and a live judge score (Day 12)
    # disagree, or the judge's own stated reason does not hold up against
    # the real evidence - see `docs/eval-report.md`'s Day 12 DeepEval
    # reasoning-error example for a real instance of this.
    "judge_or_metric_disagreement",
    # Every Day 11 check passes and the answer matches `expected_answer` -
    # the control case a taxonomy needs so "everything is broken" isn't the
    # only story it can tell.
    "passes_control",
)


# ---------------------------------------------------------------------------
# The case record: one small, inspectable dict per inspected query
# ---------------------------------------------------------------------------


def build_case_record(
    query_row,
    sources,
    answer_text,
    *,
    human_root_cause_label,
    notes,
    recommended_repair,
    verification_signal,
):
    """Assemble one Day 13 case record from a (query, sources, answer) triple.

    Runs Day 11's `evaluate_generated_answer` once and reads the two findings
    that matter most for root-causing a generation failure -
    `context_recall` (a retrieval-side question: did the evidence even
    arrive?) and `citation_validity` (a generation-side question: did the
    model only cite evidence it was actually given?) - straight out of that
    existing output, rather than re-implementing either check here.

    `human_root_cause_label` is required and validated against
    `ROOT_CAUSE_LABELS` (a `ValueError` on anything else) - see the module
    docstring for why this is a human judgement call this function only
    checks the shape of, not one it computes itself. `notes`,
    `recommended_repair`, and `verification_signal` are similarly
    human-written free text: what a person reviewing five cases actually
    concluded, not something inferrable from the answer text alone.
    """
    if human_root_cause_label not in ROOT_CAUSE_LABELS:
        raise ValueError(
            f"{human_root_cause_label!r} is not a recognized root-cause label - "
            f"pick one of {ROOT_CAUSE_LABELS}."
        )

    findings = evaluate_generated_answer(query_row, sources, answer_text)
    findings_by_check = {finding["check"]: finding for finding in findings}
    context_recall = findings_by_check["context_recall"]
    citation_validity = findings_by_check["citation_validity"]

    missing_primary_doc_ids = sorted(set(context_recall["expected"]) - set(context_recall["actual"]))

    return {
        "query_id": query_row["query_id"],
        "query_type": query_row["query_type"],
        "difficulty": query_row.get("difficulty"),
        "question": query_row["query"],
        "expected_primary_doc_ids": context_recall["expected"],
        "retrieved_doc_ids": context_recall["actual"],
        "missing_primary_doc_ids": missing_primary_doc_ids,
        "cited_doc_ids": citation_validity["cited_doc_ids"],
        "context_recall_status": "pass" if context_recall["passed"] else "fail",
        "citation_status": "pass" if citation_validity["passed"] else "fail",
        "human_root_cause_label": human_root_cause_label,
        "notes": notes,
        "recommended_repair": recommended_repair,
        "verification_signal": verification_signal,
        # The full Day 11 finding list, kept attached rather than discarded -
        # a reader who wants the `unsupported_inference`/`expected_terms`
        # detail behind this case's label can find it here without
        # re-running `evaluate_generated_answer` a second time.
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# New fixtures: real sources + a real generated answer for Q093/Q016/Q004,
# captured the same way Day 12 re-verified Q001/Q091 (see
# `generation_eval.py`'s own fixture comment) - a live run of this project's
# actual retrieval pipeline (`chunk_corpus` ->
# `build_chunk_lexical_index`/`build_chunk_semantic_index` ->
# `two_stage_rerank`, `top_k=5`, no LLM involved, fully deterministic),
# followed by one live OpenRouter call through `generation.generate_answer`
# with the default model (see `generation.DEFAULT_OPENROUTER_MODEL`). Run on
# 2026-09-19; see `docs/eval-report.md`'s Day 13 section for the exact
# command and full transcript this was captured from.
# ---------------------------------------------------------------------------

Q093_SOURCES = [
    _source(1, "CONTRACT-003", "Supply Agreement Summary — Batavia Packaging B.V.",
            "A deadband of plus or minus 2% applies: an index movement within the deadband does not "
            "trigger a price change and is carried forward to the next quarterly review. Price changes "
            "require 60 days' written notice, take effect on the first day of the following quarter, and "
            "must be supported by the published index values and the calculation. Vantera holds "
            "open-book audit rights over the cost model and may audit the indexation calculation once "
            "per contract year on 10 business days' notice.",
            chunk_id="CONTRACT-003::chunk-5"),
    _source(2, "GUIDE-003", "Negotiation Guide — Indexation and Price Adjustment Clauses",
            "The deadband, typically 2% to 3%, prevents small movements from triggering changes, and the "
            "clause must state whether movements inside the deadband are ignored or carried forward to "
            "the next review. The lag and notice period should be at least 30 to 60 days so that plans "
            "and customer prices can be adjusted. A cap and collar should be considered where extreme "
            "volatility would be unmanageable for either party.",
            chunk_id="GUIDE-003::chunk-7"),
    _source(3, "MEMO-001", "Category Council Decision Memo",
            "Decision 3: The Council confirms that Vantera's interpretation is that the carry-forward "
            "accumulates until the cumulative movement since the last price change exceeds the deadband, "
            "at which point the full cumulative movement is applied. This interpretation will be "
            "confirmed in the same clarifying amendment as Decision 2. Where Batavia does not accept the "
            "interpretation, the matter escalates to the contract dispute process rather than being "
            "settled informally at category level.",
            chunk_id="MEMO-001::chunk-9"),
    _source(4, "MEMO-001", "Category Council Decision Memo",
            "Target: 2026-09-30. Issue 2 — Deadband Carry-Forward Ambiguity The agreement states that an "
            "index movement within the plus or minus 2% deadband does not trigger a price change and is "
            "carried forward to the next quarterly review. It does not state whether the carry-forward "
            "accumulates across multiple consecutive quarters, or whether it resets.",
            chunk_id="MEMO-001::chunk-7"),
    _source(5, "GUIDE-001", "Logistics Category Sourcing Guide",
            "A fuel surcharge must specify the published index used, the baseline index value and date, "
            "the fuel-attributable percentage of the rate, the review frequency, the deadband, and the "
            "lag between index movement and rate change. A bidder offering a low base rate with an "
            "aggressive fuel mechanism, for example no deadband and a high fuel-attributable percentage, "
            "will normally be more expensive within a year. Ask every bidder to price the same historical "
            "index series through their proposed mechanism, which converts an opaque clause into a "
            "comparable number.",
            chunk_id="GUIDE-001::chunk-7"),
]

# Real, live OpenRouter transcript, captured 2026-09-19 (see this module's
# fixture-block comment above for the exact command). Note what it does NOT
# say: `expected_answer` for Q093 is explicitly "it varies by contract" and
# names Acme's fuel-surcharge deadband as plus-or-minus **3%** (a different
# contract, `CONTRACT-001`) alongside Batavia's plus-or-minus 2% - but
# `CONTRACT-001` was never retrieved (see `Q093_SOURCES` above: only
# CONTRACT-003, GUIDE-003, MEMO-001, and GUIDE-001 came back), so the model
# never saw it and confidently answers "the deadband ... is plus or minus
# 2%" as if that were the single, universal figure. This is `retrieval_miss`,
# not a prompt or citation bug: every citation below is genuinely valid, and
# the answer is fully honest about the four sources it did see - it is
# wrong only because a fifth, contract-specific source never reached it.
Q093_ANSWER_TEXT = (
    "Based on your sources, the deadband that applies to your indexation clauses is **plus or minus "
    "2%**.\n\n"
    "**Specific contract term:**\n"
    "- **CONTRACT-003** (Supply Agreement Summary — Batavia Packaging B.V.) states: *\"A deadband of "
    "plus or minus 2% applies: an index movement within the deadband does not trigger a price change "
    "and is carried forward to the next quarterly review.\"* [1]\n\n"
    "**Confirmation from internal decisions:**\n"
    "- **MEMO-001** (Category Council Decision Memo) references *\"the plus or minus 2% deadband\"* in "
    "both Decision 2 and Issue 2, confirming this is the operative figure in your agreement. [3][4]\n\n"
    "**Important context on how it works:**\n"
    "- Movements within the ±2% deadband are **carried forward** to the next quarterly review rather "
    "than ignored. Per the Category Council's Decision 3, Vantera's interpretation is that the "
    "carry-forward **accumulates** until the cumulative movement since the last price change exceeds "
    "the deadband, at which point the full cumulative movement is applied. This interpretation is to "
    "be confirmed in a clarifying amendment. [3]\n\n"
    "**Note on general guidance vs. your contract:**\n"
    "- The general negotiation guide (GUIDE-003) states that deadbands are *\"typically 2% to 3%\"* "
    "across the industry, but your specific contract term is **±2%**, which is the figure that governs "
    "your agreement. [2]\n\n"
    "**Summary:** Your indexation clauses carry a **±2% deadband**, with movements inside the deadband "
    "carried forward and accumulating until they exceed the threshold."
)


Q016_SOURCES = [
    _source(1, "POL-004", "Competitive Sourcing and Bidding Policy",
            "Price may not exceed 60% of the total evaluation weighting for any category, and for "
            "services categories where quality of delivery drives value, price should normally sit "
            "between 30% and 50%. Evaluation must be performed by a panel of at least three people, of "
            "whom at least one is from the requesting business function and at least one is from "
            "Procurement. Individual scores and the consensus rationale are recorded in Ariba Sourcing "
            "and retained for seven years.",
            chunk_id="POL-004::chunk-5"),
    _source(2, "POL-004", "Competitive Sourcing and Bidding Policy",
            "Evaluation Integrity The evaluation model, including criteria and weightings, must be "
            "defined and approved before bids are opened. Weightings may not be changed after bid "
            "opening. Price may not exceed 60% of the total evaluation weighting for any category, and "
            "for services categories where quality of delivery drives value, price should normally sit "
            "between 30% and 50%.",
            chunk_id="POL-004::chunk-4"),
    _source(3, "GUIDE-001", "Logistics Category Sourcing Guide",
            "It is guidance rather than policy, but the weighting limits and the process requirements it "
            "references are mandatory under the Competitive Sourcing and Bidding Policy. Recommended "
            "Evaluation Criteria A logistics evaluation model should score providers across six "
            "dimensions: price and total cost of ownership, service coverage and network fit, service "
            "level performance and operational capability, carbon reporting and environmental "
            "performance, claims handling and quality management, and implementation approach and "
            "timeline. Additional dimensions such as technology and visibility, financial stability, and "
            "labour standards should be added where they materially differentiate.",
            chunk_id="GUIDE-001::chunk-1"),
    _source(4, "RFP-001", "RFP-EMEA-2026-0141 — Temperature-Controlled Transport",
            "Evaluation Model Weightings were fixed and approved before the request for proposal was "
            "issued and may not be changed after bid opening. Price and total cost of ownership: 30%. "
            "Capped at 30% rather than 40% because this is temperature-controlled transport, where the "
            "cost of a failure materially exceeds the rate difference between bidders.",
            chunk_id="RFP-001::chunk-13"),
    _source(5, "POL-004", "Competitive Sourcing and Bidding Policy",
            "Competition Requirements by Value Competition requirements are based on the total committed "
            "value of the award as defined in the Global Procurement Policy. Below €25,000: no formal "
            "competition required, although the buyer should evidence that pricing is reasonable, for "
            "example through a catalogue price, a published rate, or a prior comparable purchase. "
            "€25,000 up to €250,000: at least three qualified bids must be obtained and compared on a "
            "like-for-like basis. Above €250,000: a formal request for proposal must be run through Ariba "
            "Sourcing, with a written scope of work, a published evaluation model, and a documented award "
            "recommendation.",
            chunk_id="POL-004::chunk-1"),
]

# Real, live transcript captured 2026-09-19. Unlike Q093, retrieval fully
# succeeded here - both primary documents (GUIDE-001, POL-004) are in
# `Q016_SOURCES` above, so this is NOT a `retrieval_miss` case. The gap is
# one level downstream: `expected_answer` names three tiers - the 60%
# policy ceiling, the 30-50% services band, AND a stricter "in logistics
# price should not exceed 40%" category rule - but that 40%-logistics-cap
# sentence is not in GUIDE-001's retrieved chunk (source [3] here only
# covers evaluation *dimensions*, not the 40% figure, which lives in a
# GUIDE-001 chunk this top_k=5 retrieval pass didn't happen to surface).
# GUIDE-001 (the right document) reached the model - source [3] - but was
# never cited (`uncited_ids` includes 3), and the general logistics-40% rule
# never appears in the answer at all. The answer correctly reports the 60%
# ceiling, the 30-50% services band, and the 30% temperature-controlled RFP
# figure - it is not wrong, it is simply less complete than the full
# `expected_answer`, and the retrieved evidence for the missing piece is a
# narrower slice-of-a-slice than context_recall's document-level check can
# see (see this case's `notes` in `docs/eval-report.md` for that limitation
# spelled out).
Q016_ANSWER_TEXT = (
    "**Maximum Price Weighting in Tender Evaluation**\n\n"
    "Under the general Competitive Sourcing and Bidding Policy (POL-004), **price may not exceed 60% of "
    "the total evaluation weighting for any category** [1][2]. This is the overarching ceiling.\n\n"
    "However, specific categories may have lower caps. For example, in the **Temperature-Controlled "
    "Transport EMEA** tender (RFP-EMEA-2026-0141), price and total cost of ownership is **capped at "
    "30%** rather than the general 60%, because \"the cost of a failure materially exceeds the rate "
    "difference between bidders\" [4].\n\n"
    "Additionally, for **services categories where quality of delivery drives value**, price should "
    "**normally sit between 30% and 50%** [1][2].\n\n"
    "**Summary:**\n"
    "- **General maximum:** 60% of total evaluation weighting [1][2]\n"
    "- **Services (quality-driven):** Normally 30%–50% [1][2]\n"
    "- **Temperature-controlled transport (specific RFP):** 30% [4]\n\n"
    "The applicable cap depends on the specific category and any pre-approved evaluation model for that "
    "tender."
)


Q004_SOURCES = [
    _source(1, "POL-001", "Global Procurement Policy — Approval Thresholds and Delegation of Authority",
            "Delegation by email, verbal instruction, or shared credentials is prohibited. A delegation "
            "may not exceed 30 consecutive calendar days without renewal, and the delegating approver "
            "remains accountable for decisions taken under their authority. Emergency Purchases Where a "
            "genuine business continuity risk exists, for example a production line stoppage, a food "
            "safety incident, or a security incident, work may begin before a purchase order is issued "
            "with verbal approval from an approver holding the appropriate band authority.",
            chunk_id="POL-001::chunk-12"),
    _source(2, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "What counts as an emergency An emergency is a safety risk, a food safety or quality risk, a "
            "regulatory breach, a production stoppage or imminent stoppage, a failure to supply a "
            "customer, or a material security incident. A deadline you have known about for weeks, an "
            "expiring budget, an approver on holiday, or a contract you let lapse are not emergencies. "
            "Using the emergency route for these is a control breach and is reported.",
            chunk_id="FAQ-001::chunk-2"),
    _source(3, "POL-001", "Global Procurement Policy — Approval Thresholds and Delegation of Authority",
            "Detected splitting is reported to Internal Audit as a control breach and is reported "
            "quarterly to the Audit Committee. Delegation During Absence An approver may delegate their "
            "authority temporarily using the formal delegation function in SAP S/4HANA, and only to an "
            "employee at the same grade or above. Delegation by email, verbal instruction, or shared "
            "credentials is prohibited.",
            chunk_id="POL-001::chunk-11"),
    _source(4, "POL-001", "Global Procurement Policy — Approval Thresholds and Delegation of Authority",
            "Segregation of Duties The person who raises a requisition may not approve it, regardless of "
            "their delegated authority. The person who approves a purchase order may not perform goods "
            "receipt for that order, and may not release the corresponding payment run. Requisitions may "
            "not be split into smaller commitments to avoid a higher approval band.",
            chunk_id="POL-001::chunk-9"),
    _source(5, "SOP-001", "Standard Operating Procedure — Three-Bid Requirement and Sourcing Exception Handling",
            "The approver must be independent of the requesting business function. Procurement "
            "Governance reviews every exception above €250,000 before the approver receives it, and may "
            "return the request for further evidence. Duration and Renewal Limits An approved exception "
            "is valid for a maximum of 12 months or for the duration of the specific award, whichever is "
            "shorter.",
            chunk_id="SOP-001::chunk-12"),
]

# Real, live transcript captured 2026-09-19. Q004 is not `multi_doc` (its
# only primary/grade-2 document is POL-001) and its `expected_answer` is a
# single fact - the 30-day delegation limit - which the answer states
# correctly, with a valid citation [1], and nothing else in it is
# unsupported. This is Day 13's second control case, alongside Q001: proof
# that "straightforward" queries outside the `multi_doc` slice keep working
# normally, so the taxonomy below isn't just describing one query type's
# problems.
Q004_ANSWER_TEXT = (
    "According to the Global Procurement Policy, an approver may delegate their authority temporarily "
    "while on holiday, but **a delegation may not exceed 30 consecutive calendar days without renewal** "
    "[1]. The delegation must be carried out using the formal delegation function in SAP S/4HANA, and "
    "only to an employee at the same grade or above [3]. The delegating approver remains accountable "
    "for decisions taken under their authority [1].\n\n"
    "It is also worth noting that an approver being on holiday is **not** considered an emergency under "
    "the policy [2], so the emergency route (verbal approval) cannot be used to bypass formal delegation "
    "procedures."
)


# ---------------------------------------------------------------------------
# The five Day 13 cases: reusing Day 10/11's already-committed Q001/Q091
# fixtures unchanged, plus the three new fixtures above. Each case's
# human-written label/notes/repair/verification is the actual conclusion
# reached after reading its real evidence - see `docs/eval-report.md`'s Day
# 13 section for the full per-case discussion this summarizes.
# ---------------------------------------------------------------------------


def _fixture(query_id):
    return next(f for f in CURATED_FIXTURES if f["query_id"] == query_id)


def build_cases(queries_by_id):
    """Build all five Day 13 case records against real query rows.

    `queries_by_id` is `{query_id: query_row}` from
    `hybrid_search.load_example_queries()` - passed in rather than loaded
    here, so this function (and `CASES` below) stays a pure function of
    already-loaded data, easy to call once from `main()` or from a test
    without re-reading the corpus file every time.
    """
    q001_fixture = _fixture("Q001")
    q091_fixture = _fixture("Q091")

    return [
        build_case_record(
            queries_by_id["Q001"],
            q001_fixture["sources"],
            q001_fixture["answer_text"],
            human_root_cause_label="passes_control",
            notes=(
                "Every Day 11 check passes: citations are clean, both primary/secondary "
                "documents (POL-001, FAQ-001) reached context, and the required terms "
                "('VP Procurement', 'Finance review') are both present. The easy-case "
                "anchor the taxonomy needs so 'everything fails' isn't the only story."
            ),
            recommended_repair="None needed - this case is the calibration control, not a failure.",
            verification_signal="Stays passing on every Day 11 check across future changes; a regression here would mean a change broke the easy case, not just the hard one.",
        ),
        build_case_record(
            queries_by_id["Q091"],
            q091_fixture["sources"],
            q091_fixture["answer_text"],
            human_root_cause_label="retrieval_miss",
            notes=(
                "Citation validity passes (zero orphans) and Day 12's live faithfulness "
                "judge scored this 1.00/1.00 (DeepEval/RAGAS) - the answer is fully honest "
                "about what it saw. But POL-001 (the actual Band 3 approval-threshold text) "
                "and GUIDE-002 (the 12-months-out renewal timing guidance) never reached the "
                "retrieved context at all, so the answer can only reason from precedent "
                "('a EUR 120,000 commitment is of equal or greater significance...') instead "
                "of citing the real rule, and never mentions the renewal-timing evidence. "
                "This is the Day 13 anchor case: faithful to what it saw, incomplete because "
                "of what it never saw."
            ),
            recommended_repair=(
                "Increase generation top-k specifically for multi_doc queries (e.g. from 5 to "
                "8-10 sources) and re-check whether POL-001/GUIDE-002 enter the reranked "
                "shortlist at a deeper cutoff, before touching the prompt at all - see "
                "docs/eval-report.md's Day 13 recommended repair path for the full tradeoff "
                "discussion."
            ),
            verification_signal=(
                "Re-run check_context_recall for Q091 after the top-k change: it must report "
                "an empty missing-primary-doc list. A prompt-only change would not move this "
                "signal, which is exactly why it is the right thing to check before declaring "
                "victory."
            ),
        ),
        build_case_record(
            queries_by_id["Q093"],
            Q093_SOURCES,
            Q093_ANSWER_TEXT,
            human_root_cause_label="retrieval_miss",
            notes=(
                "expected_answer is explicitly 'it varies by contract': Batavia's clause uses "
                "a 2% deadband, Acme's fuel surcharge uses 3% (CONTRACT-001), and the "
                "negotiation guide recommends a 2-3% range. CONTRACT-001 never reached the "
                "retrieved context (only CONTRACT-003, GUIDE-003, MEMO-001 x2, and GUIDE-001 "
                "did), so the model - honestly, and with clean citations - answers as if 2% "
                "were the single universal figure. This is the sharpest illustration of the "
                "Day 13 design doc's 'it depends' risk: a retrieval miss on a conflicting-"
                "scope multi_doc query does not just omit a fact, it silently converts a "
                "genuinely scoped answer into a false universal one."
            ),
            recommended_repair=(
                "Add per-document diversity to the chunk shortlist for multi_doc queries (cap "
                "how many chunks the same doc_id can contribute before broadening the pool), "
                "since the current top-5 shortlist here happened to fill up without ever "
                "reaching CONTRACT-001 - a document-diversity cap gives every distinct "
                "contract a better chance to surface, which a bigger flat top-k alone does "
                "not guarantee."
            ),
            verification_signal=(
                "check_context_recall for Q093 must report CONTRACT-001 present in retrieved "
                "context, and the regenerated answer should name both the 2% and 3% figures "
                "with their respective contracts rather than stating one number as universal."
            ),
        ),
        build_case_record(
            queries_by_id["Q016"],
            Q016_SOURCES,
            Q016_ANSWER_TEXT,
            human_root_cause_label="answer_completeness_gap",
            notes=(
                "Contrast case: both primary documents (GUIDE-001, POL-004) DID reach the "
                "retrieved context here - check_context_recall passes. But GUIDE-001 (source "
                "[3]) is never cited, and the answer omits the 'in logistics price should not "
                "exceed 40%' category-guidance tier that expected_answer names alongside the "
                "60% policy ceiling and the 30% temperature-controlled figure. The document "
                "was present; the specific fact was not in the chunk that got retrieved from "
                "it, and the model did not flag the gap. Proof that 'multi_doc' failures are "
                "not all the same failure - this one is a narrower, chunk-level completeness "
                "gap, not a document-level retrieval miss."
            ),
            recommended_repair=(
                "Retrieve more chunks per document (or a second chunk) for GUIDE-001 "
                "specifically on this query, rather than treating one retrieved chunk per "
                "document as sufficient evidence that the document's full guidance reached "
                "the model - document-level context_recall cannot see this gap, which is "
                "itself worth naming as a limitation of that check."
            ),
            verification_signal=(
                "The regenerated answer should name the logistics-specific 40% ceiling "
                "alongside the 60% policy ceiling and the 30% temperature-controlled figure; "
                "a chunk-level (not just document-level) coverage check against "
                "expected_answer's named figures would catch this before a human has to "
                "re-read the transcript."
            ),
        ),
        build_case_record(
            queries_by_id["Q004"],
            Q004_SOURCES,
            Q004_ANSWER_TEXT,
            human_root_cause_label="passes_control",
            notes=(
                "Non-multi_doc contrast case, chosen per the Day 13 plan to prevent "
                "overfitting the taxonomy to only Q091-like multi-document failures. Single "
                "primary document (POL-001), retrieved and correctly cited; the answer states "
                "the real 30-day delegation limit and matches expected_answer. Confirms "
                "straightforward, single-document queries keep working normally outside the "
                "multi_doc slice - the taxonomy's failures above are not a general regression."
            ),
            recommended_repair="None needed - a second, non-multi_doc calibration control.",
            verification_signal="Stays passing on every Day 11 check; a regression here would point at a generation/prompt-wide bug, not a multi-doc-specific one.",
        ),
    ]


# ---------------------------------------------------------------------------
# CLI/demo: print the five-case taxonomy table as plain text
# ---------------------------------------------------------------------------


def _print_case(case):
    print(f"\n{case['query_id']} ({case['query_type']}/{case['difficulty']}): {case['question']}")
    print(f"  root cause: {case['human_root_cause_label']}")
    print(f"  context recall: {case['context_recall_status']}  citation validity: {case['citation_status']}")
    if case["missing_primary_doc_ids"]:
        print(f"  missing primary doc(s): {case['missing_primary_doc_ids']}")
    print(f"  notes: {case['notes']}")
    print(f"  recommended repair: {case['recommended_repair']}")
    print(f"  verification signal: {case['verification_signal']}")


def main() -> None:
    """Build and print all five Day 13 cases - no network call, no API key.

    Every case here is either a reused, already-committed Day 10 transcript
    (Q001, Q091) or a fixture hard-coded from a real, already-completed live
    run (Q093, Q016, Q004 - see each fixture's own comment for when/how that
    run happened). Re-running `main()` re-checks that existing evidence
    through Day 11's deterministic checks; it never calls a model itself.
    """
    from hybrid_search import load_example_queries

    queries_by_id = {row["query_id"]: row for row in load_example_queries()}
    for case in build_cases(queries_by_id):
        _print_case(case)


if __name__ == "__main__":
    main()
