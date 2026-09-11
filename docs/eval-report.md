# Eval Report — v1 Hybrid Consolidation Baseline

Date: 2026-09-11 (Day 7)
Status: full baseline, 93/93 v1 queries, document-level unless noted

This is Day 7's evidence artifact: it turns Day 6's qualitative "hybrid
looked better on these five queries" demo into a measured baseline across
the whole v1 golden query set, adds metadata filtering, and gives the Day 6
exact-tie weakness a real (if partial) fix plus an honest account of what
that fix does and doesn't solve.

## Golden query source

**`data/corpus_v1/example_queries.jsonl` is the canonical query source**, used
directly rather than copied into a separate `data/golden_queries.jsonl`. It
already has everything Day 7 needs per query — `expected_relevant_ids`,
`relevance_grades`, `metadata_filters`, `expected_answer`, evidence quotes —
and `docs/corpus-v1.md` documents its provenance and verification in detail.
Introducing a second file would just be a second thing that could drift out
of sync with it for no benefit. `hybrid_search.load_example_queries()` reads
it directly.

## Methodology

- **Relevance judgment**: binary, via `expected_relevant_ids` (grade-2
  "primary" and grade-1 "secondary" ids count equally). The corpus also
  carries graded `relevance_grades` for a future nDCG-style metric — not
  used here, matching `docs/corpus-v1.md`'s own baseline table and keeping
  this a fair comparison across six methods with one relevance standard.
- **Metrics**: P@1, R@5, MRR@10 — defined and implemented in
  `src/eval_metrics.py` (`precision_at_1`, `recall_at_k`,
  `reciprocal_rank`), averaged over all 93 queries.
- **Retrieval depth**: every method's ranked list is cut to 10 before
  scoring (`RETRIEVAL_DEPTH` in `eval_metrics.py`) — enough headroom for R@5
  and for MRR to find a relevant result that landed just past rank 5,
  without the six methods being compared at six different depths.
- **Hybrid candidate pool**: BM25 and dense retrieval each contribute their
  own top **15** results into `HybridSearch` before fusion (`RRF`/`weighted`)
  truncates the *fused* list to the retrieval depth above. See "Tie-break
  decision" below for why 15, not the final depth itself.
- **Chunk→document rollup**: "Dense chunk→document" runs chunk-level dense
  search, then keeps each document's *first* (best-ranked) chunk appearance
  and drops repeats — `eval_metrics.rollup_chunks_to_documents`. This is
  Block 2's stated rule: "a chunk hit counts for its `document_id`; do not
  overcomplicate."
- **Reproduce**: `./.venv/bin/python src/eval_metrics.py`. Builds every index
  once, evaluates all six rows, prints this table. Takes ~13s on a laptop
  CPU — nearly all of it embedding the 93 query strings.

## Baseline table (unfiltered text retrieval)

93/93 v1 queries, 34 documents, 570 chunks. **Metadata filtering is not
applied anywhere in this table** — every method ranks the whole corpus for a
query's text, regardless of that query's own `metadata_filters` value. See
"Known limitations" below for why a filtered version of this table needs its
own methodology rather than a one-line change. MRR here is **MRR@10**: every
method's ranked list is cut to depth 10 (see "Methodology" above) before
scoring, so a relevant result found only past rank 10 scores 0.0, the same
as one never found at all — worth naming precisely rather than implying an
unbounded MRR this table doesn't compute.

| Method | Retrieval unit | P@1 | R@5 | MRR@10 |
|---|---|---|---|---|
| TF-IDF | document | 0.871 | **0.787** | 0.924 |
| BM25 | document | 0.860 | 0.754 | 0.910 |
| Dense (multi-qa-MiniLM) | document | 0.839 | 0.673 | 0.900 |
| Dense (multi-qa-MiniLM) | chunk→document | **0.925** | 0.768 | **0.954** |
| Hybrid RRF (BM25 + dense) | document | 0.860 | 0.763 | 0.922 |
| Hybrid weighted, α=0.5 (BM25 + dense) | document | **0.882** | 0.775 | 0.938 |

TF-IDF/BM25/Dense-document numbers match `docs/corpus-v1.md`'s own v1
baseline within rounding, which cross-checks that this table's methodology
is scoring the same thing. Dense chunk→document differs slightly from that
doc's numbers (P@1 0.925 here vs 0.91 there, R@5 0.768 vs 0.80) — expected,
since the two tables use different chunk-candidate depths and rollup rules
going into the document-level score; not a discrepancy worth chasing further
for a first baseline.

**What this table actually says — exact pairwise comparisons, not
eyeballed superlatives.** An earlier draft of this section claimed "hybrid
beats every individual document-level method on P@1, R@5, and MRR". Review
flagged that RRF actually *ties* BM25 on P@1, not beats it. Re-checking every
other superlative claim in this section against the exact numbers (rather
than patching just the flagged line) turned up two more of the same kind of
error unprompted: weighted does not have the best R@5 among document-level
rows (TF-IDF does), and chunk-level dense does not beat whole-document
weighted on *every* metric (weighted's R@5 is higher). All three are
corrected below:

1. **RRF vs. BM25**: RRF *ties* BM25 on P@1 (0.860 both — not a win), and
   beats it on R@5 (0.763 > 0.754) and MRR@10 (0.922 > 0.910). **RRF vs.
   TF-IDF**: RRF is behind TF-IDF on all three metrics (0.860/0.763/0.922
   vs. 0.871/0.787/0.924). RRF is a real, if modest, improvement over BM25
   and a clear one over dense alone — it is not an improvement over TF-IDF
   on this table.
2. **Weighted vs. every document-level single method**: weighted beats BM25
   and dense on all three metrics, and beats TF-IDF on P@1 (0.882 > 0.871)
   and MRR@10 (0.938 > 0.924) — but *loses* to TF-IDF on R@5 (0.775 <
   0.787). Weighted is the best document-level row on P@1 and MRR@10, not
   on all three metrics.
3. **Chunk-level dense retrieval *alone* beats whole-document hybrid RRF on
   all three metrics, and beats whole-document weighted on P@1 and MRR@10 —
   but *loses* to weighted on R@5** (0.768 < 0.775). Even stated with that
   correction, this is still the least comfortable finding in this table and
   the most useful one: hybrid fusion over the wrong retrieval unit (whole
   documents) does not close the gap chunk-level retrieval opens on P@1 and
   MRR@10, no matter which fusion method is used. `hybrid_search.py` already
   supports `id_key="chunk_id"` fusion (Day 6's chunk-level demo) — running
   chunk-level BM25 + chunk-level dense through `HybridSearch` and adding
   that as a seventh row is the obvious next baseline, not attempted today
   to keep Day 7 to the six required rows.
4. **TF-IDF is a stronger baseline on this corpus than either single-method
   BM25 or RRF** — worth stating on its own, not just as a footnote to the
   RRF comparison above. TF-IDF's R@5 (0.787) is the best of any
   document-level row, and its MRR@10 (0.924) is third overall, ahead of
   BM25 and RRF. This corpus's short documents and modest vocabulary size
   may be part of why raw term frequency (no length normalization, no
   saturation) is competitive here; it is not a claim that TF-IDF
   generalizes better than BM25, only that it measurably didn't lose on
   this specific 93-query set.

## Metadata filtering

Implemented in `src/hybrid_search.py`: `build_metadata_index`,
`matches_filters`, `filter_ranked_results`. Tested in
`tests/test_hybrid_search.py` (synthetic cases for the filter logic itself,
plus one test against the real corpus).

**Filter timing — after scoring, before truncating to the caller's final
`top_k`.** Each retriever is asked for the *full* corpus (`top_k=len(data)`,
all 34 documents) as its candidate list, non-matching candidates are dropped
from that full list, and *then* it is sliced to the requested size. Filtering
the corpus *before* building the BM25 index instead was considered and
rejected: BM25's IDF and average-document-length statistics would then
depend on which filter was applied, so the same query against the same
document could score differently depending on what filter happened to be
active — confusing to reason about, and free to avoid at 34 documents
(scoring everything, then filtering, costs nothing measurable here).

**Real bug caught in review, not by me: the first version of this filtering
used `CANDIDATE_POOL_SIZE=15` (the *tie-mitigation* pool size, see "Tie-break
decision" below) as a stand-in for "the full ranked list", instead of the
actual full corpus.** Those are two different concerns that happened to
reuse the same constant. Concretely, on Q007 ("What checks are needed before
onboarding a new high-risk supplier?", filter `doc_type: policy`): the
correct secondary document `POL-005` ranks 20th in BM25's raw ordering for
this query — inside the 34-document corpus, but outside the top 15.
Filtering only the top-15 pool silently dropped it before the filter ever
saw it; filtering the full corpus finds it. Fixed by retrieving the full
corpus specifically when a query has a filter (`run_edge_case_comparison`
in `src/hybrid_search.py`), then filtering that down to
`CANDIDATE_POOL_SIZE` before fusion — so filtering sees everything, and
fusion still works over the same-sized candidate set it always did.
`tests/test_hybrid_search.py::test_filtering_a_narrow_candidate_pool_can_lose_a_relevant_document_that_filtering_the_full_list_finds`
reproduces this exact case with real data as a permanent regression check.

**Document level, not chunk level.** A chunk carries only `chunk_id`,
`document_id`, `text`, `title` — no `doc_type`/`region`/etc. of its own
(see `chunking.chunk_document`). `filter_ranked_results(..., document_id_key="document_id")`
filters a chunk by its *parent document's* metadata.

**What happens when the filter removes the correct document — measured, not
assumed.** `hybrid_search.run_edge_case_comparison()` runs Q001 ("What
approval is required for a EUR 60,000 purchase order?") through its real
filter (`doc_type: policy`, which correctly keeps POL-001) and then through
a deliberately wrong one (`doc_type: contract-summary`):

```
unfiltered BM25 top-1:                  POL-001
filter={'doc_type': 'policy'} (the query's real filter) -> top-1: POL-001
filter={'doc_type': 'contract-summary'} (deliberately wrong) -> results: ['CONTRACT-003', 'CONTRACT-004', 'CONTRACT-001']
```

POL-001 does not disappear because it scored worse — it disappears because
it fails the filter outright, and CONTRACT-003 (an unrelated document that
happens to still pass the wrong filter) becomes top-1 instead, silently. No
error, no "0 results" warning, no indication anything went wrong short of
reading the answer. That is the real risk metadata filtering introduces: a
correct filter narrows usefully, but a *wrong* filter value fails silently
and confidently. `tests/test_hybrid_search.py::test_metadata_filter_can_remove_the_correct_document_and_change_the_top1`
covers this as a permanent regression check.

Checked programmatically across all 21 v1 queries that carry a
`metadata_filters` value, filtering each query's own full-corpus BM25
ranking with its own real filter: for every one, at least one expected
relevant id survives filtering — none of the real, author-intended filters
in the v1 query set accidentally exclude their own correct answer entirely.
That is a property of how the query set was built (`docs/corpus-v1.md`:
"every `metadata_filters` entry matches at least one gold document"), not a
guarantee this filtering code itself provides — a wrong filter value, as
shown above, removes the correct document exactly as designed.

**A sharper, related finding worth separating from the check above: "at
least one" is not "all".** 17 of those same 21 queries have *at least one*
`expected_relevant_ids` entry that the query's *own* filter would exclude —
e.g. Q001 expects `FAQ-001` as a secondary answer, but its filter is
`doc_type: policy`, and `FAQ-001` is a FAQ, not a policy. That's expected
and correct behavior (a secondary, partially-relevant document need not
share the primary document's type), but it means "P@1/R@5/MRR against
`expected_relevant_ids`" and "P@1/R@5/MRR against a *filtered* candidate
set" are not the same evaluation — the second needs its own,
filter-adjusted ground truth per query, not the first table's ground truth
reused as-is. See "Known limitations" below.

## Tie-break decision (Day 6 weakness)

Day 6 found a real exact-tie pathology: two candidates that are each the
*best* result for one retriever but entirely absent from the other's (narrow,
top-3) list can land on the identical fused score under RRF, and the
existing tie-break (sort by document id) then decides the winner
alphabetically — a decision with nothing to do with relevance.

**Decision: widen the per-retriever candidate pool before fusing**
(`CANDIDATE_POOL_SIZE=15`, `src/hybrid_search.py`), rather than changing
`HybridSearch`'s tie-break rule itself. Considered alternatives and why they
weren't the pick: preferring whichever candidate appears in *more* lists
doesn't help the specific pathology (both tied candidates are, by
construction, in exactly one list each); reintroducing a raw-score
tie-break for RRF specifically would defeat the reason RRF was chosen (it
exists precisely to avoid comparing BM25 scores to cosine scores).

**Measured, not assumed — on the Day 6 "vendor vetting" query**
(`"What vendor vetting is required before working with a risky supplier?"`,
expected: POL-002):

| Candidate pool | RRF top-1 | Tied at top? |
|---|---|---|
| 3 (Day 6 behaviour) | CONTRACT-006 | **Yes** — tied with POL-002, alphabetical id decided it |
| 15 (Day 7 fix) | SOP-007 | No — single unambiguous winner |

The tie is gone at pool=15. **But the new winner is still wrong** — this is
the honest half of the finding. Inspecting why: POL-002 (correct) is
semantic rank 1 but never appears anywhere in BM25's top 15 at all (a real
lexical gap: "vendor vetting" shares essentially no vocabulary with
POL-002's actual wording). SOP-007 is only rank 4 on *both* sides, but
"moderately good on both" beats "excellent on one, invisible on the other"
under RRF's rank-sum formula (`1/64 + 1/64 = 0.0313` vs. `0 + 1/61 = 0.0164`).
Weighted combination does better here without fully solving it either —
its normalized scores let POL-002's large semantic margin count for more,
landing it at rank 2 (`0.500`, a near-tie with CONTRACT-006's `0.511`) rather
than off the fused list — but neither fusion method gets it to top-1.

**What this decision does and doesn't fix, stated precisely:**

- **Fixed**: the *artificial* exact tie caused purely by too-small `top_k`
  truncation before fusion — a candidate that would have picked up a real,
  if small, term from the other retriever's list now gets the chance to.
- **Not fixed, and not fixable by widening `top_k` alone**: RRF's structural
  preference for cross-retriever consensus over single-retriever strength.
  A document entirely absent from one retriever's list — a genuine, not
  artificial, gap — cannot out-rank a mediocre-but-present-everywhere
  distractor under RRF's rank-sum formula, no matter how deep the pool goes.
- **Next-step design** (Day 8+): this is what a cross-encoder reranker is
  for — re-score the fused shortlist against the query directly instead of
  trusting rank-sum consensus, which is exactly the gap this finding
  exposes. Alternatively, query expansion / synonym handling on the BM25
  side would give POL-002 a real (not artificial) foothold in that list to
  begin with.

`tests/test_hybrid_search.py` keeps the pre-existing chunk/document tie
tests from Day 6 (still passing, still correct — they test `HybridSearch`'s
formula in isolation, which is unchanged) and adds the metadata-filter tests
above; the pool-size investigation itself is captured here and in
`docs/learning-log.md` rather than as a unit test, since it's an empirical
finding about this specific corpus/query pair, not a property `HybridSearch`
itself guarantees.

## Edge-case comparison

10 queries hand-picked from the v1 query set by `query_id`
(`hybrid_search.EDGE_CASE_QUERY_IDS`) to cover exact identifiers, numeric
thresholds, supplier-specific questions, vocabulary-gap paraphrases,
multi-document questions, and metadata-filtered questions. Full output:
`./.venv/bin/python src/hybrid_search.py` (Day 7 section at the end).

**BM25 wins** (correct top-1; dense's top-1 is wrong) — scanned across all
93 queries, not just the 10 edge cases; 10 of 93 queries fit this pattern.
Two representative ones:

- **Q009** — *"At what shareholding percentage must we verify beneficial
  ownership?"* BM25 top-1 `FAQ-002` (correct); dense top-1 `AUDIT-001`
  (wrong — a plausible-sounding but unrelated audit-report document). The
  query is really asking for one exact number; BM25's exact-token match
  wins over dense's topical-but-imprecise similarity.
- **Q042** — *"What are the purchasing card spending limits?"* BM25 top-1
  `FAQ-001` (correct); dense top-1 `GUIDE-002` (wrong). Same pattern: a
  numeric-limit lookup where lexical overlap beats semantic similarity.

**Dense wins** (correct top-1; BM25's top-1 is wrong) — 8 of 93 queries.
Two representative ones:

- **Q014** — *"What uptime must a business-critical SaaS service commit
  to?"* Dense top-1 `CONTRACT-004` (correct); BM25 top-1 `SOP-007` (wrong).
  This is also the clearest "hybrid still fails" case below.
- **Q002** — *"Is the approval level based on the annual spend or the whole
  contract value?"* Dense top-1 `POL-001` (correct); BM25 top-1 `GUIDE-003`
  (wrong). A conceptual/definitional question with little lexical overlap
  between the query and the answer sentence — exactly the paraphrase gap
  BM25 cannot bridge and dense retrieval is built for.

**Hybrid wins** — measured precisely rather than asserted. At the strict bar
("both single methods wrong at document level, hybrid correct") **0 of 93**
queries qualify — same finding Day 6's comparison already suspected for its
5-query demo, now confirmed for the full set. At a real but weaker bar
("hybrid's top-1 is a *different* document from both single methods' own
top-1, and is correct") RRF does this on **2 of 93** (`Q009`, `Q042`) and
weighted on 1 of 93 (`Q042`). Concretely for `Q042` — *"What are the
purchasing card spending limits?"* (expected: `FAQ-001` or `SOP-004`): BM25's
own top-1 is `FAQ-001` (already correct) and dense's own top-1 is `GUIDE-002`
(wrong), but both RRF and weighted land on `SOP-004` — a document that was
BM25-rank-4 and dense-rank-2, not the top pick of either, but well-supported
enough on both sides to outrank BM25's own rank-1. Real fusion behaviour,
just a modest effect at whole-document granularity, consistent with the
baseline table's headline finding that whole-document hybrid isn't the
retrieval-unit ceiling on this corpus.

**Hybrid still fails** — **Q014** (`"What uptime must a business-critical
SaaS service commit to?"`, expected: `CONTRACT-004`/`GUIDE-002`/`POL-003`).
Dense alone gets this right (`CONTRACT-004` top-1). Both RRF and weighted
get it *wrong* (`SOP-007` top-1 for both) — `SOP-007` is BM25-rank-1
*and* dense-rank-3, a document with real (moderate) signal on both sides,
while `CONTRACT-004` (correct) never appears anywhere in BM25's top-15 at
all. This is the same structural pattern as the tie-break investigation
above — cross-retriever consensus outranking one retriever's strong,
correct, single-sided signal — caught here on both fusion methods at once,
not just RRF. It is this baseline's clearest evidence that hybrid fusion is
not a strict improvement over the best single method on every query, only
on average.

## Known limitations / next steps

- **The baseline table is unfiltered text retrieval only — no
  metadata-aware baseline exists yet, and it is not a simple addition.**
  `src/eval_metrics.py`'s six closures never read `query_row["metadata_filters"]`.
  Building one needs its own methodology, not just applying
  `filter_ranked_results` inside each closure: as the "sharper, related
  finding" above shows, 17 of 21 filtered queries have at least one
  `expected_relevant_ids` entry their own filter would exclude, so a
  filtered baseline needs a *filter-adjusted* ground truth per query
  (drop the ids the filter itself was always going to exclude before
  scoring recall against what's left) — reusing the unfiltered
  `expected_relevant_ids` as-is would penalize every method for correctly
  filtering out documents the filter was supposed to remove.
- Baseline table is document-level for hybrid; a chunk-level hybrid row
  (BM25-over-chunks + dense-over-chunks, fused, rolled up to documents) is
  the natural seventh row and — per the table's own finding that chunk-level
  dense alone already beats whole-document hybrid — plausibly the strongest
  one. Not built today; `hybrid_search.py`'s Day 6 chunk-level demo already
  shows the fusion mechanics work over `id_key="chunk_id"`, so this is
  wiring, not new design.
- Binary relevance only. `relevance_grades` (graded 1/2) is unused; a
  graded metric (nDCG) would score a primary-document hit higher than a
  secondary-document hit, which this baseline currently treats as
  equivalent.
- The RRF-vs-consensus finding above (Q014, and the pool-size
  investigation) is this baseline's strongest argument for reranking next:
  first-stage retrieval — lexical, dense, or fused — has a structural blind
  spot for "correct but only recognized by one signal", which is exactly
  what a reranker scoring the shortlist against the query directly is
  positioned to fix.
- Metadata filtering supports equality-per-field only (plus list-membership
  for `risk_tags`). No OR, no numeric ranges (e.g. `annual_value_eur` over a
  threshold) — not needed to prove the contract against the v1 query set,
  which never asks for more.
