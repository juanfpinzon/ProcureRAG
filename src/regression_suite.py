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
is supposed to show, and whether today's run still shows it." Day 13 ended
by recommending a retrieval-depth/diversity repair for Q091's and Q093's
missing primary documents but explicitly left it unattempted until a
harness existed to measure it. That harness is `run_deterministic_suite`
below (Block 3A); the repair itself, verified against it, is Block 3B - see
that section further down for how `expected_missing_primary_doc_ids` went
from documenting a known failure to asserting a verified fix.

**The case contract this module is built around** (see `REGRESSION_CASES`
and `CITATION_NEGATIVE_CASE` below - this is Day 14's "Block 2" design
worked out in code, not just in a doc):

- `case_id` / `query_id` / `case_role` - what this case is and which real
  (or synthetic) query it uses. `case_role` is one of `passing_control`,
  `retrieval_miss`, `chunk_gap`, `citation_negative`, `refusal_negative`.
  A case's `case_id`/`case_role` are stable identifiers, not a live status
  report - `retrieval-miss-q091` keeps that name even after Block 3B's
  repair, the same way a bug ticket keeps its id after the bug is fixed.
- `retrieval_config` - which `reranking.py` config (`DEFAULT_RETRIEVAL_CONFIG`
  or `MULTI_DOC_RETRIEVAL_CONFIG`) the attached `sources` were actually
  retrieved under - carried on the case for traceability, the same
  "retrieval_config: top_k, reranker, diversity cap" field the route doc's
  suggested trace schema asks for, without needing a separate trace file
  (see "Trace / evidence capture decision" in `docs/eval-report.md`).
- `sources` / `answer_text` / `required_terms` - the frozen fixture Day
  11/13/14 already proved out (imported, never re-typed here), or a small
  synthetic answer built for a negative test.
- `expected_missing_primary_doc_ids` - what `check_context_recall` should
  report *right now*, given this case's current `sources`. Before Block 3B,
  Q091's value here was genuinely `["GUIDE-002", "POL-001"]`; after Block
  3B's repair (and this case's `sources` being replaced by a real,
  post-repair capture), it is `[]`. A case is not "passing" by matching
  this; it is "as expected" by matching it, whichever state is current.
- `required_chunk_ids` / `expected_missing_chunk_ids` - Block 3B's
  chunk-level extension of the same idea, for `chunk-gap-q016`: specific
  `chunk_id`s (not just `doc_id`s) that must be present in `sources`, so a
  document-level pass can never quietly hide a missing fact - see
  `evaluate_case` below.
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

**Block 3B update (same day): the Q091/Q093/Q016 repair, verified here.**
Day 13 recommended a concrete fix - deepen and diversify multi-doc
retrieval - but explicitly left it unverified pending this suite. Once the
suite existed, `reranking.py` gained `max_chunks_per_document` (a
per-document cap on the pre-rerank shortlist) and
`retrieval_config_for_query_type` (a documented, measured `multi_doc`
config: `pool_size=80, top_k=10, max_chunks_per_document=2`, replacing the
default `pool_size=15, top_k=5`). A real retrieval + real live generation
run under that new config was captured for Q091, Q093, and Q016 - see
`Q091_REPAIRED_SOURCES` etc. below - and the result is asserted here, not
just narrated: `retrieval-miss-q091`/`retrieval-miss-q093` now expect
`missing_primary_doc_ids == []` (down from the real, historical
`["GUIDE-002", "POL-001"]` / `["CONTRACT-001"]`), and `chunk-gap-q016` now
carries a real, computed `required_chunk_ids` check - not a hand-written
note - proving `GUIDE-001::chunk-2` (the chunk with the "logistics price
<=40%" fact) is actually present, instead of only claiming it. See
`docs/eval-report.md`'s Day 14 Block 3B section for the full diagnostic
trail (per-method ranks, fused ranks at several pool sizes, before/after
reranked order) that justifies these exact numbers rather than guessing
them.
"""

import argparse
from datetime import datetime, timezone

from generation import INSUFFICIENT_EVIDENCE_ANSWER, generate_answer
from generation_eval import CURATED_FIXTURES, _source, evaluate_generated_answer
from error_analysis import Q004_ANSWER_TEXT, Q004_SOURCES
from framework_eval import build_framework_eval_case, run_deepeval_contextual_recall, run_deepeval_faithfulness
from hybrid_search import load_example_queries
from reranking import DEFAULT_RETRIEVAL_CONFIG, MULTI_DOC_RETRIEVAL_CONFIG

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
# Block 3B repair fixtures: real retrieval + real live generation, captured
# 2026-09-21 under `reranking.retrieval_config_for_query_type("multi_doc")`
# (`pool_size=80, top_k=10, max_chunks_per_document=2` - see that function
# and `MULTI_DOC_RETRIEVAL_CONFIG` in reranking.py for exactly why those
# numbers, not a guess). Command used to capture these (see
# docs/eval-report.md's Day 14 Block 3B section for the full script):
# build `two_stage_rerank(query, ..., **retrieval_config_for_query_type(
# "multi_doc"))`, then `generation.build_sources` and a real
# `generation.generate_answer` call through `make_openrouter_client()`.
#
# These SUPERSEDE the pre-repair sources/answer for the three case specs
# below. `error_analysis.py`'s own Q091/Q093/Q016 fixtures are deliberately
# left untouched - they are Day 13's frozen evidence of the ORIGINAL
# failure (missing POL-001/GUIDE-002, missing CONTRACT-001, the missed
# GUIDE-001 40% chunk) and stay that way for history; this module's case
# specs below now assert the CURRENT, repaired state instead.
# ---------------------------------------------------------------------------

Q091_REPAIRED_SOURCES = [
    _source(1, "SOP-001", "Standard Operating Procedure — Three-Bid Requirement and Sourcing Exception Handling",
            "The approver must be independent of the requesting business function. Procurement Governance "
            "reviews every exception above €250,000 before the approver receives it, and may return the "
            "request for further evidence. Duration and Renewal Limits An approved exception is valid for a "
            "maximum of 12 months or for the duration of the specific award, whichever is shorter.",
            chunk_id="SOP-001::chunk-12"),
    _source(2, "SOP-006", "Standard Operating Procedure — Contract Renewal, Expiry and Evergreen Management",
            "The 120-day alert is the operative one: it is the point at which a renewal decision process must "
            "formally start, because it leaves enough time to run a competitive event where the decision is "
            "not to renew. Renewal Decision Path At 120 days the Category Manager assesses current "
            "performance from the most recent scorecards, whether the requirement is still needed at the "
            "same volume, whether the pricing remains competitive against the market, whether the terms "
            "remain compliant with current policy, particularly on security, data protection, and "
            "responsible sourcing, and whether the supplier's risk profile has changed. The outcome is one "
            "of four decisions: renew as is, renew with renegotiated terms, run a competitive event, or exit "
            "and terminate.",
            chunk_id="SOP-006::chunk-3"),
    _source(3, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "Tell Procurement Operations your genuine required date at intake so the realistic route can be "
            "chosen. Do I need three quotes Three qualified bids are required above €25,000 and up to "
            "€250,000 of total committed value. Above €250,000 a formal request for proposal is required.",
            chunk_id="FAQ-001::chunk-12"),
    _source(4, "FAQ-001", "FAQ — Purchase Orders, Approvals and Starting Work",
            "A three-year service at €20,000 per year is a €60,000 commitment and needs VP Procurement "
            "approval with a Finance review, not Category Manager approval. If you are unsure of the value, "
            "use a good-faith estimate at the top of the expected range. Can I split a request to keep it "
            "under a threshold No.",
            chunk_id="FAQ-001::chunk-6"),
    _source(5, "POL-003", "Information Security and Data Protection Requirements for Technology Suppliers",
            "Risk acceptance may not exceed 12 months and may not be renewed more than once. Renewal and "
            "Continuous Assurance Certification evidence is refreshed annually. A lapsed certificate is "
            "treated as a control failure and triggers a review of whether the service may continue.",
            chunk_id="POL-003::chunk-13"),
    # POL-001 - the primary document Day 13 found missing - now reaches
    # context via the deeper multi_doc pool_size. Note the specific chunk
    # retrieved (chunk-3) covers HOW total committed value is calculated,
    # not the actual Band 1/2/3 EUR thresholds (those live in a different
    # POL-001 chunk - see this case's "notes" below for what that means for
    # the answer text).
    _source(6, "POL-001", "Global Procurement Policy — Approval Thresholds and Delegation of Authority",
            "For a multi-year agreement, total committed value means the aggregate charge over the full "
            "contractual term including all committed renewals, licence uplifts, indexation at the "
            "contractually agreed cap, and any minimum volume commitment. Where the value cannot be "
            "determined precisely, the requester must use a documented good-faith estimate at the upper end "
            "of the expected range, and re-approve if the actual value exceeds the approved band. Approval "
            "Bands The following approval bands apply to the total committed value expressed in EUR.",
            chunk_id="POL-001::chunk-3"),
    _source(7, "CONTRACT-004", "Cloud Services Agreement Summary — Meridian Cloud Services, Inc. (CSA-MER-2026-001)",
            "Support personnel outside the European Union may access data only through a documented "
            "break-glass process with Vantera approval per instance, logged and reviewed monthly. The data "
            "processing addendum incorporates Standard Contractual Clauses for any onward transfer, and "
            "Meridian maintains ISO 27001, SOC 2 Type II, and ISO 27018 certifications, with evidence "
            "refreshed annually. Breach notification is required within 24 hours of Meridian becoming aware.",
            chunk_id="CONTRACT-004::chunk-9"),
    _source(8, "SOP-001", "Standard Operating Procedure — Three-Bid Requirement and Sourcing Exception Handling",
            "On the second renewal the buyer must record a plan and a date for a competitive event or a "
            "Category Council decision to designate the supplier as strategic and single-sourced by design. "
            "Record Keeping and Audit Trail The following must exist in Ariba Sourcing for every award above "
            "€25,000: the requirement document issued to suppliers, the invitation list with dates, the bids "
            "received or the exception form, the comparison or evaluation record, the award recommendation, "
            "and the approval evidence. Records are retained for seven years.",
            chunk_id="SOP-001::chunk-14"),
    _source(9, "POL-008", "Contract Standards Policy — Liability, Insurance, Term and Termination",
            "Cyber liability of €5,000,000 for Tier-1 data suppliers as defined in the information security "
            "policy. Product liability of €10,000,000 for suppliers of food-contact materials, ingredients, "
            "and finished goods. Employer's liability at the statutory minimum, or £5,000,000 in the United "
            "Kingdom.",
            chunk_id="POL-008::chunk-7"),
    # GUIDE-002 - the second primary document Day 13 found missing - also
    # now reaches context.
    _source(10, "GUIDE-002", "Category Playbook — Software, SaaS and Cloud Procurement",
            "Start Twelve Months Before Renewal The single highest-value action in this category is starting "
            "early. At 12 months before renewal, pull actual usage data: licences assigned versus licences "
            "consumed in the last 90 days, feature usage by module, consumption against any committed "
            "spend, and the number of users who have not logged in for 60 days. At 9 months, establish "
            "whether the requirement still exists in its current form and whether a credible alternative "
            "exists, including doing nothing, consolidating into an existing platform, or reducing scope.",
            chunk_id="GUIDE-002::chunk-1"),
]

# Real, live OpenRouter transcript, captured 2026-09-21 under the repaired
# multi_doc config above. Both primary documents cited: [6] (POL-001) and
# [10] (GUIDE-002, the "usage data" evidence Day 13 found missing). This is
# a genuine repair, not just better prose - `check_context_recall` now
# passes because the primary documents are actually present in `sources`,
# not because the answer merely reads more complete.
#
# Honest residual, worth keeping visible rather than hidden: the specific
# POL-001 chunk retrieved (chunk-3, above) explains HOW total committed
# value is calculated, not the actual Band 1/2/3 EUR thresholds themselves
# (a *different* POL-001 chunk, chunk-4, has those - see
# generation_eval.Q001_SOURCES). So the answer correctly says it cannot
# state the exact band name ("Confirm the exact approval level with
# Procurement Governance") instead of inventing one - honest, not wrong,
# but this is precisely Day 13's `chunk_level_retrieval_gap` pattern
# appearing again, now for POL-001 specifically. `Q091_REQUIRED_TERMS`
# below is left unchanged ("Band 3", "usage data") on purpose: it now
# documents exactly this - "usage data" passes (the retrieval_miss is
# fixed), "Band 3" still fails (a narrower, still-open chunk-level gap) -
# see docs/eval-report.md's Day 14 Block 3B section for the full read.
Q091_REPAIRED_ANSWER_TEXT = (
    "## Approvals and Security Evidence for a EUR 120,000 SaaS Renewal\n\n"
    "### 1. Sourcing and Bidding Requirement\n\n"
    "At **EUR 120,000 total committed value**, this falls in the **€25,000–€250,000 band**, which requires "
    "**three qualified bids** [3]. You cannot split the request to stay under a threshold [4].\n\n"
    "If you need to deviate from the three-bid requirement, note that Procurement Governance reviews every "
    "exception above **€250,000** before the approver receives it [1] — though at €120,000 you are below "
    "that specific escalation threshold.\n\n"
    "### 2. Approval Level\n\n"
    "Based on the stated example, a commitment of **€60,000** (three years at €20,000/year) requires **VP "
    "Procurement approval with a Finance review**, not Category Manager approval [4]. At **€120,000**, you "
    "should expect at least that level of approval — and potentially higher, depending on the approval "
    "bands in [6], which are expressed against total committed value. The exact band definitions are not "
    "listed in the provided sources, so confirm with Procurement Governance if the €120,000 figure pushes "
    "you into a higher band.\n\n"
    "**Important**: For a multi-year agreement, total committed value includes all committed renewals, "
    "licence uplifts, indexation at the contractually agreed cap, and any minimum volume commitment [6]. If "
    "€120,000 is only the first year, the total committed value over the full term may be significantly "
    "higher.\n\n"
    "### 3. Renewal-Specific Process\n\n"
    "- **120 days before renewal**: The Category Manager must formally start the renewal decision process, "
    "assessing performance scorecards, whether the requirement still exists at the same volume, pricing "
    "competitiveness, policy compliance (especially security, data protection, responsible sourcing), and "
    "supplier risk profile [2].\n"
    "- **12 months before renewal**: Pull actual usage data (licences assigned vs. consumed, feature usage, "
    "consumption against committed spend, inactive users) [10].\n"
    "- **9 months before renewal**: Establish whether the requirement still exists in its current form and "
    "whether a credible alternative exists [10].\n"
    "- **On the second renewal**: Record a plan and date for a competitive event, or obtain a Category "
    "Council decision to designate the supplier as strategic and single-sourced by design [8].\n\n"
    "### 4. Security Evidence Required\n\n"
    "- **Annual certification refresh**: Certification evidence (e.g., ISO 27001, SOC 2 Type II, ISO 27018 "
    "or equivalent) must be refreshed annually. A lapsed certificate is treated as a control failure and "
    "triggers a review of whether the service may continue [5].\n"
    "- **Risk acceptance limits**: Risk acceptance may not exceed **12 months** and may not be renewed more "
    "than **once** [5].\n"
    "- **Cyber liability insurance**: If the SaaS supplier qualifies as a **Tier-1 data supplier** under the "
    "information security policy, **€5,000,000 cyber liability** coverage is required [9].\n"
    "- **Data processing addendum**: If the supplier processes data outside the EU, Standard Contractual "
    "Clauses must be incorporated, and any break-glass access must be documented, logged, and reviewed "
    "monthly [7].\n\n"
    "### Summary\n\n"
    "| Requirement | Source |\n"
    "|---|---|\n"
    "| Three qualified bids (€25K–€250K) | [3] |\n"
    "| VP Procurement + Finance review (at least at €60K band) | [4] |\n"
    "| No splitting to avoid thresholds | [4] |\n"
    "| 120-day renewal decision process | [2] |\n"
    "| Usage data at 12 months, viability at 9 months | [10] |\n"
    "| Second-renewal competitive event plan or Category Council designation | [8] |\n"
    "| Annual certification refresh (ISO 27001/SOC 2/ISO 27018 or equivalent) | [5] |\n"
    "| Risk acceptance ≤ 12 months, max one renewal | [5] |\n"
    "| €5M cyber liability if Tier-1 data supplier | [9] |\n\n"
    "**Note**: The specific approval band for €120,000 is not explicitly listed in the provided sources — "
    "only the €60,000 example is given [4]. Confirm the exact approval level with Procurement Governance, "
    "particularly if the total committed value over the full term exceeds €120,000 [6]."
)


Q093_REPAIRED_SOURCES = [
    _source(1, "CONTRACT-003", "Supply Agreement Summary — Batavia Packaging B.V. (SA-BAT-2025-007)",
            "A deadband of plus or minus 2% applies: an index movement within the deadband does not trigger "
            "a price change and is carried forward to the next quarterly review. Price changes require 60 "
            "days' written notice, take effect on the first day of the following quarter, and must be "
            "supported by the published index values and the calculation. Vantera holds open-book audit "
            "rights over the cost model and may audit the indexation calculation once per contract year on "
            "10 business days' notice.",
            chunk_id="CONTRACT-003::chunk-5"),
    _source(2, "GUIDE-003", "Negotiation Guide — Cost Models, Price Indexation and Should-Cost Analysis for "
            "Direct Materials",
            "The deadband, typically 2% to 3%, prevents small movements from triggering changes, and the "
            "clause must state whether movements inside the deadband are ignored or carried forward to the "
            "next review. The lag and notice period should be at least 30 to 60 days so that plans and "
            "customer prices can be adjusted. A cap and collar should be considered where extreme "
            "volatility would be unmanageable for either party.",
            chunk_id="GUIDE-003::chunk-7"),
    _source(3, "MEMO-001", "Category Council Decision Memo — Packaging Resin Indexation Review 2026",
            "Decision 3: The Council confirms that Vantera's interpretation is that the carry-forward "
            "accumulates until the cumulative movement since the last price change exceeds the deadband, at "
            "which point the full cumulative movement is applied. This interpretation will be confirmed in "
            "the same clarifying amendment as Decision 2. Where Batavia does not accept the interpretation, "
            "the matter escalates to the contract dispute process rather than being settled informally at "
            "category level.",
            chunk_id="MEMO-001::chunk-9"),
    _source(4, "MEMO-001", "Category Council Decision Memo — Packaging Resin Indexation Review 2026",
            "Target: 2026-09-30. Issue 2 — Deadband Carry-Forward Ambiguity The agreement states that an "
            "index movement within the plus or minus 2% deadband does not trigger a price change and is "
            "carried forward to the next quarterly review. It does not state whether the carry-forward "
            "accumulates across multiple consecutive quarters, or whether it resets.",
            chunk_id="MEMO-001::chunk-7"),
    _source(5, "GUIDE-001", "RFP Scoring and Award Guide — Logistics and Transport Categories",
            "A fuel surcharge must specify the published index used, the baseline index value and date, the "
            "fuel-attributable percentage of the rate, the review frequency, the deadband, and the lag "
            "between index movement and rate change. A bidder offering a low base rate with an aggressive "
            "fuel mechanism, for example no deadband and a high fuel-attributable percentage, will normally "
            "be more expensive within a year. Ask every bidder to price the same historical index series "
            "through their proposed mechanism, which converts an opaque clause into a comparable number.",
            chunk_id="GUIDE-001::chunk-7"),
    _source(6, "GUIDE-003", "Negotiation Guide — Cost Models, Price Indexation and Should-Cost Analysis for "
            "Direct Materials",
            "The baseline must state the index value and the date it corresponds to, since a mechanism "
            "without a baseline cannot be recalculated. The review frequency should be quarterly for most "
            "materials and monthly only for highly volatile inputs, because more frequent reviews create "
            "administrative cost and price instability. The deadband, typically 2% to 3%, prevents small "
            "movements from triggering changes, and the clause must state whether movements inside the "
            "deadband are ignored or carried forward to the next review.",
            chunk_id="GUIDE-003::chunk-6"),
    _source(7, "CONTRACT-003", "Supply Agreement Summary — Batavia Packaging B.V. (SA-BAT-2025-007)",
            "The corrugated portfolio is indexed to the published European testliner and fluting price "
            "index, and the flexible portfolio is indexed to the ICIS polyethylene contract price for "
            "north-west Europe. Indexation applies only to the raw material component of the price, which "
            "is fixed in Schedule 2 at 62% for corrugated articles and 71% for flexible articles, with the "
            "balance representing conversion, waste, energy, and margin, which are fixed for the first 24 "
            "months. A deadband of plus or minus 2% applies: an index movement within the deadband does not "
            "trigger a price change and is carried forward to the next quarterly review.",
            chunk_id="CONTRACT-003::chunk-4"),
    # CONTRACT-001 - the primary document Day 13 found missing (Acme's 3%
    # fuel-surcharge deadband) - now reaches context.
    _source(8, "CONTRACT-001", "Master Services Agreement Summary — Acme Logistics S.L. (MSA-ACM-2024-018)",
            "Base rates are fixed for the first 24 months of the term and are then subject to annual review "
            "linked to the Spanish transport labour cost index, capped at the lower of the index movement "
            "or 3.5%. A separate fuel surcharge mechanism applies monthly, indexed to the published Spanish "
            "gasoil price, with a deadband of plus or minus 3%: the surcharge adjusts only where the "
            "monthly average gasoil price moves outside that band relative to the baseline, and the "
            "adjustment is applied to the fuel-attributable portion of the rate, stated in Schedule 2 as "
            "22% of the base rate. Acme must provide the index reference and the calculation with each "
            "surcharge adjustment, and Vantera has open-book audit rights over the calculation.",
            chunk_id="CONTRACT-001::chunk-9"),
    _source(9, "GUIDE-001", "RFP Scoring and Award Guide — Logistics and Transport Categories",
            "Ask bidders to price the accessorials explicitly, because a low linehaul rate combined with "
            "aggressive accessorial charging is a common bidding strategy and is invisible in a rate-card "
            "comparison. Fuel Surcharge Mechanisms Compare the mechanism, not the current value. A fuel "
            "surcharge must specify the published index used, the baseline index value and date, the "
            "fuel-attributable percentage of the rate, the review frequency, the deadband, and the lag "
            "between index movement and rate change.",
            chunk_id="GUIDE-001::chunk-6"),
    _source(10, "POL-001", "Global Procurement Policy — Approval Thresholds and Delegation of Authority",
            "For a multi-year agreement, total committed value means the aggregate charge over the full "
            "contractual term including all committed renewals, licence uplifts, indexation at the "
            "contractually agreed cap, and any minimum volume commitment. Where the value cannot be "
            "determined precisely, the requester must use a documented good-faith estimate at the upper end "
            "of the expected range, and re-approve if the actual value exceeds the approved band. Approval "
            "Bands The following approval bands apply to the total committed value expressed in EUR.",
            chunk_id="POL-001::chunk-3"),
]

# Real, live OpenRouter transcript, captured 2026-09-21 under the repaired
# multi_doc config. This is the qualitative fix Day 13 called for: instead
# of stating Batavia's 2% deadband as if it were the single universal
# figure, the answer now names BOTH contracts explicitly - Batavia
# (CONTRACT-003, [1][7]) at plus-or-minus 2%, Acme (CONTRACT-001, [8]) at
# plus-or-minus 3% - because CONTRACT-001 actually reached context this
# time. A false-universal answer became a correctly-scoped one because the
# missing evidence arrived, not because the prompt got better at hedging.
Q093_REPAIRED_ANSWER_TEXT = (
    "The deadband depends on which contract you are referring to, as different agreements specify different "
    "values:\n\n"
    "**Batavia Packaging B.V. (SA-BAT-2025-007):** A deadband of **±2%** applies to both the corrugated "
    "portfolio (indexed to the European testliner and fluting price index) and the flexible portfolio "
    "(indexed to the ICIS polyethylene contract price for north-west Europe). An index movement within the "
    "deadband does not trigger a price change and is carried forward to the next quarterly review [1][7]. "
    "The Category Council has confirmed that the carry-forward accumulates until the cumulative movement "
    "since the last price change exceeds the deadband, at which point the full cumulative movement is "
    "applied [3].\n\n"
    "**Acme Logistics S.L. (MSA-ACM-2024-018):** A deadband of **±3%** applies to the monthly fuel "
    "surcharge mechanism, indexed to the published Spanish gasoil price. The surcharge adjusts only where "
    "the monthly average gasoil price moves outside that band relative to the baseline, and the adjustment "
    "is applied to the fuel-attributable portion of the rate (22% of the base rate) [8].\n\n"
    "**General guidance** (not contract-specific) notes that deadbands are **typically 2% to 3%**, and that "
    "the clause should state whether movements inside the deadband are ignored or carried forward to the "
    "next review [2][6].\n\n"
    "If your question relates to a specific contract not covered above, the sources do not contain "
    "information about other deadband values."
)


Q016_REPAIRED_SOURCES = [
    _source(1, "POL-004", "Competitive Sourcing and Bidding Policy",
            "Price may not exceed 60% of the total evaluation weighting for any category, and for services "
            "categories where quality of delivery drives value, price should normally sit between 30% and "
            "50%. Evaluation must be performed by a panel of at least three people, of whom at least one is "
            "from the requesting business function and at least one is from Procurement. Individual scores "
            "and the consensus rationale are recorded in Ariba Sourcing and retained for seven years.",
            chunk_id="POL-004::chunk-5"),
    _source(2, "POL-004", "Competitive Sourcing and Bidding Policy",
            "Evaluation Integrity The evaluation model, including criteria and weightings, must be defined "
            "and approved before bids are opened. Weightings may not be changed after bid opening. Price "
            "may not exceed 60% of the total evaluation weighting for any category, and for services "
            "categories where quality of delivery drives value, price should normally sit between 30% and "
            "50%.",
            chunk_id="POL-004::chunk-4"),
    _source(3, "GUIDE-001", "RFP Scoring and Award Guide — Logistics and Transport Categories",
            "It is guidance rather than policy, but the weighting limits and the process requirements it "
            "references are mandatory under the Competitive Sourcing and Bidding Policy. Recommended "
            "Evaluation Criteria A logistics evaluation model should score providers across six dimensions: "
            "price and total cost of ownership, service coverage and network fit, service level performance "
            "and operational capability, carbon reporting and environmental performance, claims handling "
            "and quality management, and implementation approach and timeline. Additional dimensions such "
            "as technology and visibility, financial stability, and labour standards should be added where "
            "they materially differentiate.",
            chunk_id="GUIDE-001::chunk-1"),
    _source(4, "RFP-001", "RFP Packet Summary — Temperature-Controlled Transport EMEA (RFP-EMEA-2026-0141)",
            "Evaluation Model Weightings were fixed and approved before the request for proposal was issued "
            "and may not be changed after bid opening. Price and total cost of ownership: 30%. Capped at "
            "30% rather than 40% because this is temperature-controlled transport, where the cost of a "
            "failure materially exceeds the rate difference between bidders.",
            chunk_id="RFP-001::chunk-13"),
    # This is the chunk Day 13 found missing: GUIDE-001::chunk-2, the one
    # that actually carries the "logistics price <=40%" figure - a
    # different chunk of the same document (chunk-1, above) reached context
    # before, but not this one. It is present now.
    _source(5, "GUIDE-001", "RFP Scoring and Award Guide — Logistics and Transport Categories",
            "Additional dimensions such as technology and visibility, financial stability, and labour "
            "standards should be added where they materially differentiate. Weighting Guidance Price should "
            "not exceed 40% of the total score in logistics categories, and for temperature-controlled and "
            "pharmaceutical-grade transport it should not exceed 30%. This is not a preference for "
            "expensive suppliers; it reflects the fact that in transport the cheapest bid frequently "
            "becomes the most expensive contract once failed deliveries, re-deliveries, claims, and "
            "emergency backup transport are included.",
            chunk_id="GUIDE-001::chunk-2"),
    _source(6, "CONTRACT-005", "Framework Agreement Summary — Orion Facility Services, S.A. (FA-ORI-2026-002)",
            "Annual price review takes effect on 1 March each year and is limited to the pass-through of "
            "mandatory increases in the applicable collective agreement wage rates and statutory social "
            "security contributions, evidenced by the published agreement, plus a maximum 1% for other "
            "costs. Orion must not apply a general inflation uplift to the labour element in addition to "
            "the collective agreement pass-through. Transfer of Undertakings and Termination The parties "
            "acknowledge that Spanish transfer of undertakings rules may apply on entry and exit, and Orion "
            "must provide anonymised workforce data annually so that Vantera can inform a future bidder.",
            chunk_id="CONTRACT-005::chunk-13"),
    _source(7, "GUIDE-003", "Negotiation Guide — Cost Models, Price Indexation and Should-Cost Analysis for "
            "Direct Materials",
            "Negotiating the Non-Indexed Elements Conversion, waste, and margin are where genuine "
            "negotiation lives. Useful levers include specification simplification such as reducing "
            "substrate weight, colour count, or tolerance where the technical function permits, run length "
            "and changeover reduction achieved by consolidating articles, yield improvement through joint "
            "work on scrap rates, packaging and pallet configuration to improve transport fill, payment "
            "terms and their working capital value, and volume consolidation across plants where a "
            "supplier's footprint permits. Each of these produces a cost change that can be evidenced, "
            "which is what makes the saving durable.",
            chunk_id="GUIDE-003::chunk-11"),
    _source(8, "CONTRACT-005", "Framework Agreement Summary — Orion Facility Services, S.A. (FA-ORI-2026-002)",
            "Failure to achieve 90% for two consecutive months triggers a corrective action plan, and three "
            "consecutive months entitles Vantera to remove a site from the framework without demobilisation "
            "compensation. Pricing and Indexation Pricing is per site per month for the base scope, with an "
            "hourly rate card for additional and reactive work. Annual price review takes effect on 1 March "
            "each year and is limited to the pass-through of mandatory increases in the applicable "
            "collective agreement wage rates and statutory social security contributions, evidenced by the "
            "published agreement, plus a maximum 1% for other costs.",
            chunk_id="CONTRACT-005::chunk-12"),
    _source(9, "SOP-005", "Standard Operating Procedure — Supplier Segmentation, Performance Reviews and "
            "Scorecards",
            "Delivery (25 points): on-time in-full performance, lead time adherence, and order fill rate. "
            "Cost (20 points): cost reduction delivered against the agreed baseline, price stability, "
            "invoice accuracy, and adherence to the agreed indexation mechanism. Service and responsiveness "
            "(15 points): query response time, issue resolution time, quality of account management, and "
            "flexibility on urgent requests.",
            chunk_id="SOP-005::chunk-5"),
    _source(10, "FAQ-002", "FAQ — Supplier Onboarding, Invoicing and Payment Status",
            "Suppliers with turnover below €10,000,000 are paid Net 30. In Spain the statutory maximum of "
            "60 days applies and cannot be extended. The clock starts on receipt of a valid invoice, which "
            "means one quoting a valid purchase order number, matching the order and the goods receipt, "
            "showing the correct legal entity and VAT registration, and submitted through the Ariba "
            "Network.",
            chunk_id="FAQ-002::chunk-8"),
]

# Real, live OpenRouter transcript, captured 2026-09-21. Unlike the
# pre-repair transcript (error_analysis.Q016_ANSWER_TEXT), this answer
# explicitly names the logistics-specific "40%" ceiling and the
# temperature-controlled "30%" figure, citing [5] - GUIDE-001::chunk-2, the
# exact chunk Day 13 found missing. This is real evidence the chunk-level
# gap is ADDRESSED, not just still open - see `REQUIRED_CHUNK_IDS` below
# for the actual deterministic check this claim is verified against,
# rather than only asserted here in prose.
Q016_REPAIRED_ANSWER_TEXT = (
    "The maximum weighting you can give to price depends on the category of the tender:\n\n"
    "**General rule (any category):** Price may not exceed **60%** of the total evaluation weighting. This "
    "is the overarching cap under the Competitive Sourcing and Bidding Policy [1][2].\n\n"
    "**Logistics and transport categories:** More restrictive guidance applies. Price should not exceed "
    "**40%** of the total score in logistics categories generally, and **30%** for temperature-controlled "
    "and pharmaceutical-grade transport [5]. This is reflected in the specific RFP for Temperature-"
    "Controlled Transport EMEA, where price and total cost of ownership was capped at **30%** [4].\n\n"
    "**Key constraints that apply across all categories:**\n"
    "- The evaluation model, including criteria and weightings, must be defined and approved **before** "
    "bids are opened, and weightings may not be changed after bid opening [2].\n"
    "- Evaluation must be performed by a panel of at least three people, including at least one from the "
    "requesting business function and at least one from Procurement [1].\n\n"
    "So in summary: the absolute maximum is **60%** for any category under policy, but if your tender falls "
    "within logistics or transport — particularly temperature-controlled — the applicable cap is lower at "
    "**40%** or **30%** respectively [1][2][4][5]."
)


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
        "retrieval_config": DEFAULT_RETRIEVAL_CONFIG,  # non-multi_doc: untouched by Block 3B
        "sources": _Q001["sources"],
        "answer_text": _Q001["answer_text"],
        "required_terms": _Q001["required_terms"],
        "expected_missing_primary_doc_ids": [],
        "expected_citation_status": "pass",
        "required_chunk_ids": (),
        "expected_missing_chunk_ids": [],
        "table_note": None,
        "notes": (
            "Easy single-threshold control (POL-001/FAQ-001 both reach context). "
            "query_type is 'threshold', not 'multi_doc', so "
            "retrieval_config_for_query_type never changes its retrieval config - "
            "this case cannot regress from the Block 3B repair by construction, "
            "and did not (re-verified after the repair)."
        ),
    },
    {
        "case_id": "control-q004",
        "query_id": "Q004",
        "case_role": "passing_control",
        "source_fixture_kind": "committed_fixture",
        "retrieval_config": DEFAULT_RETRIEVAL_CONFIG,  # non-multi_doc: untouched by Block 3B
        "sources": Q004_SOURCES,
        "answer_text": Q004_ANSWER_TEXT,
        "required_terms": None,
        "expected_missing_primary_doc_ids": [],
        "expected_citation_status": "pass",
        "required_chunk_ids": (),
        "expected_missing_chunk_ids": [],
        "table_note": None,
        "notes": (
            "Second control, deliberately NOT multi_doc (single primary doc, "
            "POL-001; query_type is 'lookup'). Guards against a multi-doc-specific "
            "repair being credited with a win that is really just noise, and "
            "against a multi-doc-only regression suite that would never notice a "
            "generation-wide bug."
        ),
    },
    {
        "case_id": "retrieval-miss-q091",
        "query_id": "Q091",
        "case_role": "retrieval_miss",
        "source_fixture_kind": "committed_fixture",
        "retrieval_config": MULTI_DOC_RETRIEVAL_CONFIG,
        "sources": Q091_REPAIRED_SOURCES,
        "answer_text": Q091_REPAIRED_ANSWER_TEXT,
        "required_terms": _Q091["required_terms"],  # ("Band 3", "usage data") - see notes below
        "expected_missing_primary_doc_ids": [],  # REPAIRED - was ["GUIDE-002", "POL-001"] pre-repair
        "expected_citation_status": "pass",
        "required_chunk_ids": (),
        "expected_missing_chunk_ids": [],
        "table_note": "REPAIRED 2026-09-21: missing docs were ['GUIDE-002','POL-001'], now []",
        "notes": (
            "Day 13's anchor retrieval_miss, REPAIRED in Block 3B: under "
            "reranking.MULTI_DOC_RETRIEVAL_CONFIG (pool_size=80, top_k=10, "
            "max_chunks_per_document=2), both POL-001 and GUIDE-002 now reach "
            "context - this row's `sources`/`answer_text` are a real live capture "
            "under that config, not the original Day 13 transcript (still frozen, "
            "unchanged, in error_analysis.py for history). Honest residual: the "
            "specific POL-001 chunk retrieved (chunk-3) explains HOW total "
            "committed value is calculated, not the actual Band 1/2/3 EUR "
            "thresholds (a different POL-001 chunk, chunk-4, has those) - so "
            "check_expected_terms below will still FAIL on 'Band 3' even though "
            "it now passes on 'usage data'. That is a real, narrower, still-open "
            "chunk-level gap - named here, not hidden, exactly the pattern Q016 "
            "already established below."
        ),
    },
    {
        "case_id": "retrieval-miss-q093",
        "query_id": "Q093",
        "case_role": "retrieval_miss",
        "source_fixture_kind": "committed_fixture",
        "retrieval_config": MULTI_DOC_RETRIEVAL_CONFIG,
        "sources": Q093_REPAIRED_SOURCES,
        "answer_text": Q093_REPAIRED_ANSWER_TEXT,
        "required_terms": None,
        "expected_missing_primary_doc_ids": [],  # REPAIRED - was ["CONTRACT-001"] pre-repair
        "expected_citation_status": "pass",
        "required_chunk_ids": (),
        "expected_missing_chunk_ids": [],
        "table_note": "REPAIRED 2026-09-21: missing docs were ['CONTRACT-001'], now []",
        "notes": (
            "Day 13's second retrieval_miss, REPAIRED in Block 3B: CONTRACT-001 "
            "(Acme's 3% fuel-surcharge deadband) now reaches context under the "
            "same MULTI_DOC_RETRIEVAL_CONFIG, and the live-captured answer now "
            "correctly names BOTH contracts and both figures (Batavia 2%, Acme "
            "3%) instead of stating one as a false universal - a real, verified "
            "qualitative fix, not just better prose, because the missing evidence "
            "genuinely arrived this time."
        ),
    },
    {
        "case_id": "chunk-gap-q016",
        "query_id": "Q016",
        "case_role": "chunk_gap",
        "source_fixture_kind": "committed_fixture",
        "retrieval_config": MULTI_DOC_RETRIEVAL_CONFIG,
        "sources": Q016_REPAIRED_SOURCES,
        "answer_text": Q016_REPAIRED_ANSWER_TEXT,
        "required_terms": None,
        "expected_missing_primary_doc_ids": [],  # was already [] before AND after - doc-level always passed
        "expected_citation_status": "pass",
        # The actual, computed chunk-level check the Day 14 route doc asked
        # for ("make chunk/fact-level coverage visible instead of hiding
        # behind document-level pass") - not a hand-written note. See
        # evaluate_case below for how this turns into `missing_chunk_ids`.
        "required_chunk_ids": ("GUIDE-001::chunk-2",),
        "expected_missing_chunk_ids": [],  # REPAIRED - was ["GUIDE-001::chunk-2"] pre-repair
        "table_note": None,  # computed dynamically in evaluate_case from required_chunk_ids instead
        "notes": (
            "Day 13's chunk_level_retrieval_gap, ADDRESSED in Block 3B (this is "
            "the 'addressed by a chunk/fact-level coverage signal' branch the "
            "route doc allows, not the 'still open' one): document-level recall "
            "always passed here (both GUIDE-001 and POL-004 reached context "
            "before AND after), so the pre-repair failure was purely that "
            "GUIDE-001::chunk-2 - the specific chunk with the 'logistics price "
            "<=40%' figure - was never retrieved, while a different chunk of the "
            "same document was. Under MULTI_DOC_RETRIEVAL_CONFIG this chunk now "
            "reaches context (verified by `required_chunk_ids` below, a real "
            "check, not a hand-written claim) and the live-captured answer cites "
            "it directly [5]."
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
    "retrieval_config": DEFAULT_RETRIEVAL_CONFIG,  # Q001's real sources, unaffected by Block 3B
    "sources": _Q001["sources"],
    "answer_text": "VP Procurement approval with a Finance review is required [4][99].",
    "required_terms": None,
    "expected_missing_primary_doc_ids": [],
    "expected_citation_status": "fail",  # the point of this case: we WANT a fail here
    "required_chunk_ids": (),
    "expected_missing_chunk_ids": [],
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
    "did every check pass" (CITATION_NEGATIVE_CASE is *supposed* to fail
    citation_validity) - it is "does today's actual result equal what this
    case declared it should be." That is what lets a future retrieval change
    be compared against a known baseline instead of just re-reading raw
    pass/fail flags out of context.

    Block 3B addition: a real chunk-level coverage check, not just the
    document-level one. `required_chunk_ids` (empty for every case except
    `chunk-gap-q016`) names specific `chunk_id`s that must be present in
    `sources` - `missing_chunk_ids` is the same "expected minus actual"
    arithmetic `missing_primary_doc_ids` already uses, just at chunk
    granularity. This is what lets Q016 prove "the specific fact-carrying
    chunk arrived", something `check_context_recall`'s document-level
    `missing_primary_doc_ids` is structurally unable to see (a document can
    have ten chunks and only one of them matter for a given fact).
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

    required_chunk_ids = set(case_spec["required_chunk_ids"])
    actual_chunk_ids = {source["chunk_id"] for source in case_spec["sources"]}
    missing_chunk_ids = sorted(required_chunk_ids - actual_chunk_ids)

    deterministic_match = (
        missing_primary_doc_ids == case_spec["expected_missing_primary_doc_ids"]
        and citation_status == case_spec["expected_citation_status"]
        and missing_chunk_ids == case_spec["expected_missing_chunk_ids"]
    )

    # For a case that actually declares a chunk-level requirement, compute
    # the table note from the real check result instead of using a static,
    # hand-written string that could silently go stale the next time
    # `sources` changes - this is the "chunk/fact-level coverage signal,
    # not hidden behind document-level pass" the Day 14 route doc asks for.
    table_note = case_spec["table_note"]
    if required_chunk_ids:
        if missing_chunk_ids:
            table_note = f"chunk-level gap OPEN: missing {missing_chunk_ids}"
        else:
            table_note = f"chunk-level gap ADDRESSED: {sorted(required_chunk_ids)} present"

    return {
        "case_id": case_spec["case_id"],
        "query_id": case_spec["query_id"],
        "role": case_spec["case_role"],
        "source_fixture_kind": case_spec["source_fixture_kind"],
        "retrieval_config": case_spec["retrieval_config"],
        "query_type": query_row.get("query_type"),
        "difficulty": query_row.get("difficulty"),
        "missing_primary_doc_ids": missing_primary_doc_ids,
        "expected_missing_primary_doc_ids": case_spec["expected_missing_primary_doc_ids"],
        "citation_status": citation_status,
        "expected_citation_status": case_spec["expected_citation_status"],
        "missing_chunk_ids": missing_chunk_ids,
        "table_note": table_note,
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
        "retrieval_config": None,  # no retrieval ran at all - synthetic, empty sources
        "query_type": None,
        "difficulty": None,
        "missing_primary_doc_ids": None,  # not a meaningful concept with zero sources
        "expected_missing_primary_doc_ids": None,
        "citation_status": citation_status,
        "expected_citation_status": "pass",
        "missing_chunk_ids": None,  # not a meaningful concept with zero sources
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
        print("\nAll cases match their currently expected state.")


if __name__ == "__main__":
    main()
