# Eval Report — v1 Hybrid Consolidation Baseline

Date: 2026-09-11 (Day 7); Day 8 reranking addendum added 2026-09-12; Day 9
graded/filtered/error-slice addendum added 2026-09-14; Day 10 source-cited
generation addendum added 2026-09-14
Status: full baseline, 93/93 v1 queries, nine retrieval methods (six
required document-level rows + two chunk-level hybrid rows added as a Day 7
follow-up, plus Day 8's cross-encoder reranked chunk row — see "Day 8:
Cross-encoder reranking" below), plus Day 9's graded (nDCG@5), filtered-
adjusted (21 queries), and error-slice (query type / difficulty / filtered /
primary-count) evaluations — see "Day 9: Graded relevance, filter-adjusted
evaluation, and error slices" below. Day 10 adds the first answer-generation
layer on top of this retrieval baseline — see "Day 10: Source-cited answer
generation" below. This file still only evaluates *retrieval*; Day 10's
generation layer is evaluated separately, and only by deterministic
contract checks so far (see that section for exactly what is and is not
covered).

This is Day 7's evidence artifact: it turns Day 6's qualitative "hybrid
looked better on these five queries" demo into a measured baseline across
the whole v1 golden query set, adds metadata filtering, and gives the Day 6
exact-tie weakness a real (if partial) fix plus an honest account of what
that fix does and doesn't solve. A same-day follow-up then closed the
biggest gap the first version of this table itself pointed at: chunk-level
hybrid fusion, which turned out to be the strongest configuration tested.
Day 8 then added a second-stage cross-encoder reranker on top of that
chunk-level hybrid baseline — see the dedicated section below for whether
it helped, and where. Day 9 then went past binary relevance and one
aggregate number per method: graded relevance (nDCG@5), a filter-adjusted
ground truth for the 21 filtered queries, and error slices that pinpoint
exactly where the reranker's aggregate strength hides a real weakness
(`multi_doc` queries) — see that section for what moved and what didn't.

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
  this a fair comparison across every method with one relevance standard.
- **Metrics**: P@1, R@5, MRR@10 — defined and implemented in
  `src/eval_metrics.py` (`precision_at_1`, `recall_at_k`,
  `reciprocal_rank`), averaged over all 93 queries.
- **Retrieval depth**: every method's ranked list is cut to 10 before
  scoring (`RETRIEVAL_DEPTH` in `eval_metrics.py`) — enough headroom for R@5
  and for MRR to find a relevant result that landed just past rank 5,
  without different methods being compared at different depths.
- **Hybrid candidate pool**: BM25 and dense retrieval each contribute their
  own top **15** results into `HybridSearch` before fusion (`RRF`/`weighted`)
  truncates the *fused* list to the retrieval depth above. See "Tie-break
  decision" below for why 15, not the final depth itself. Same pool size for
  the chunk-level hybrid rows, just over chunks instead of whole documents.
- **Chunk→document rollup**: every chunk-level row (dense alone, hybrid RRF,
  hybrid weighted) runs its chunk-level search/fusion first, then keeps each
  document's *first* (best-ranked) chunk appearance and drops repeats —
  `eval_metrics.rollup_chunks_to_documents`. This is Block 2's stated rule:
  "a chunk hit counts for its `document_id`; do not overcomplicate." For the
  two hybrid chunk rows specifically, `document_id` is looked back up via
  the chunk index first, since `HybridSearch`'s fused output only carries
  `chunk_id` and per-method scores, not the extra fields either input
  retriever's results happened to have.
- **Reproduce**: `./.venv/bin/python src/eval_metrics.py`. Builds every index
  once, evaluates all nine rows (the eight described here plus Day 8's
  cross-encoder reranked row — see that section below), and prints one
  table. ~16s in the Day 8 run that produced the numbers in this report;
  exact wall-clock time depends on model load and cache state, not just
  row count, so treat that as a ballpark, not a guarantee.

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
| TF-IDF | document | 0.871 | 0.787 | 0.924 |
| BM25 | document | 0.860 | 0.754 | 0.910 |
| Dense (multi-qa-MiniLM) | document | 0.839 | 0.673 | 0.900 |
| Dense (multi-qa-MiniLM) | chunk→document | 0.925 | 0.768 | 0.954 |
| Hybrid RRF (BM25 + dense) | document | 0.860 | 0.763 | 0.922 |
| Hybrid weighted, α=0.5 (BM25 + dense) | document | 0.882 | 0.775 | 0.938 |
| Hybrid RRF (BM25 + dense) | chunk→document | **0.935** | **0.811** | **0.965** |
| Hybrid weighted, α=0.5 (BM25 + dense) | chunk→document | 0.925 | 0.801 | 0.961 |

The last two rows are past Day 7's required minimum of six — added as a
direct follow-up once the six-row table made the gap obvious (see point 3
below). They needed no new retrieval or fusion logic: `HybridSearch` already
supported `id_key="chunk_id"` fusion (Day 6's chunk-level demo),
`chunked_search.py` already had BM25-over-chunks, and
`rollup_chunks_to_documents` already existed for the "Dense chunk→document"
row above. The only new code is `eval_metrics.py`'s `_chunk_hybrid_retrieve`
helper, which wires those three existing pieces together and rolls the
fused chunk ranking up to documents — wiring, not new design, exactly as
anticipated in this section's previous draft.

TF-IDF/BM25/Dense-document numbers match `docs/corpus-v1.md`'s own v1
baseline within rounding, which cross-checks that this table's methodology
is scoring the same thing. Dense chunk→document differs slightly from that
doc's numbers (P@1 0.925 here vs 0.91 there, R@5 0.768 vs 0.80) — expected,
since the two tables use different chunk-candidate depths and rollup rules
going into the document-level score; not a discrepancy worth chasing further
for a first baseline.

**What this table actually says — exact pairwise comparisons, not
eyeballed superlatives.** (An earlier draft of the six-row version of this
section overclaimed twice — see the git history / `docs/learning-log.md`'s
review addendum for that correction. The numbers below are re-verified
against the eight-row table, not assumed to still hold.)

1. **Hybrid RRF at chunk granularity is the best row in this table on
   every metric** — P@1 0.935, R@5 0.811, MRR@10 0.965, each the single
   highest value in its column. This is the first row in this eval report
   that is unambiguously best across the board; every prior comparison
   (RRF vs. BM25, weighted vs. TF-IDF, dense-chunk vs. weighted-document)
   involved at least one metric going the other way.
2. **Chunk-level fusion beats chunk-level dense alone, on both fusion
   methods, on every metric.** Hybrid RRF chunk→document beats Dense
   chunk→document by +0.010 P@1, +0.043 R@5, +0.011 MRR@10; hybrid weighted
   chunk→document ties dense-chunk on P@1 (0.925 both) and beats it on R@5
   (+0.033) and MRR@10 (+0.007). Fusion *does* earn its place once it's
   fusing over the right retrieval unit — the whole-document table above
   couldn't show this because both signals going into it were already
   handicapped by the coarser unit.
3. **This confirms the "known limitation" flagged in the six-row version of
   this table**: whole-document hybrid wasn't the ceiling, and chunk-level
   hybrid — not just chunk-level dense alone — is measurably the strongest
   retrieval configuration tested on this corpus. The gap is real:
   Hybrid RRF chunk→document's R@5 (0.811) is +0.010 over the next-best row
   (its own weighted sibling, 0.801) and +0.024 over TF-IDF, the best
   whole-document row on R@5. Against whole-document weighted specifically —
   Day 7's own best document-level row — chunk-level RRF is ahead by +0.053
   P@1, +0.036 R@5, +0.027 MRR@10.
4. **Whole-document comparisons, unchanged from before and still worth
   stating precisely rather than by superlative**: RRF *ties* BM25 on P@1
   (0.860 both) and loses to TF-IDF on all three metrics; weighted beats
   BM25 and dense on all three metrics and beats TF-IDF on P@1/MRR@10 but
   not R@5 (TF-IDF's 0.787 > weighted's 0.775). TF-IDF remains a stronger
   document-level baseline than either single-method BM25 or whole-document
   RRF on this specific 93-query set — not a claim that TF-IDF generalizes
   better, only that it measurably didn't lose here.
5. **RRF vs. weighted, restated at chunk granularity**: RRF wins on all
   three metrics at chunk level too, reversing nothing about the whole
   RRF-vs-weighted trade-off itself (weighted is still more tunable and
   interpretable; RRF is still tuning-free) — it just means, on this
   corpus, rank-based consensus fusion currently outperforms
   magnitude-based fusion regardless of which retrieval unit it runs over.

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

## Day 8: Cross-encoder reranking

Date: 2026-09-12 (Day 8 addendum to this report)
Implementation: `src/reranking.py`; wired into the table above's evaluation
script as a ninth row (`src/eval_metrics.py`); tests in
`tests/test_reranking.py` (12 tests, all against fake scorers/models — no
live model download required for the standard test suite).

**Baseline being reranked**: Hybrid RRF chunk→document — P@1 0.935, R@5
0.811, MRR@10 0.965, the best first-stage row in the table above.
Reranking any other row would overstate the reranker's real contribution
by comparing it against a first-stage method already known to be weaker —
see `src/reranking.py`'s module docstring.

**Two-stage pipeline**:

1. **First stage** — `build_chunk_shortlist`: the identical chunk-level
   Hybrid RRF as the baseline row (`search_bm25_chunks` +
   `search_semantic_chunks`, fused via
   `HybridSearch(id_key="chunk_id").rrf()`), `CANDIDATE_POOL_SIZE` (15)
   chunks per query. Unchanged from Day 7 — the first stage's only job here
   is producing the exact same shortlist the baseline row already scores.
2. **Second stage** — `rerank_with_cross_encoder`: every one of those 15
   chunks is re-scored with `cross-encoder/ms-marco-TinyBERT-L2-v2`
   (~4M parameters, general web/search-trained on MS MARCO, not
   procurement-specific) against `(query, title + chunk_text)` pairs,
   sorted by that score, and assigned a `final_rank`. Every first-stage
   field (`first_stage_rank`, `first_stage_score`, `bm25_score`,
   `semantic_score`, `document_id`) is preserved on the result alongside
   the new `reranker_score` — the auditability contract
   `src/reranking.py`'s `rerank` docstring calls for: a reranked result can
   always explain itself, not just report its new position.
3. **Rollup** — the same rule every other chunk-level row uses: walk the
   reranked chunks best-first, keep each document's first (best-ranked)
   appearance, drop repeats (`rollup_chunks_to_documents`).

**Reproduce**: `./.venv/bin/python src/eval_metrics.py` — adds a
cross-encoder reranked row to the same table, ~16s total on a laptop CPU
(versus ~7s for the eight-row Day 7 table alone). Cross-encoder scoring 15
short pairs per query across 93 queries is cheap at this model size — no
subset/sampling was needed to get a full-93-query row.

### Aggregate result — 93/93 queries

| Method | Retrieval unit | P@1 | R@5 | MRR@10 |
|---|---|---|---|---|
| Hybrid RRF (BM25 + dense) | chunk→document | 0.935 | **0.811** | 0.965 |
| Cross-encoder reranked Hybrid RRF (BM25 + dense) | chunk→document | **0.978** | 0.806 | **0.984** |

**Measured, not assumed.** Reranking clearly improves both metrics that
score "is the single best answer ranked correctly": P@1 +0.043 (0.935 →
0.978) and MRR@10 +0.019 (0.965 → 0.984). It very slightly *reduces* R@5:
-0.005 (0.811 → 0.806). That is not a contradiction — it is the expected
shape of what a reranker can and cannot do. Reranking only ever *re-orders*
the same 15-chunk shortlist the first stage already retrieved; it cannot
pull in a document that never made that shortlist at all. Precision-style
metrics (does the *top* answer match) are exactly what re-ordering can
improve; a recall-style metric (is a relevant document *anywhere* in the
top 5) can only move if reranking pushes a relevant chunk across the
rank-5 boundary, in either direction — here that happened to net slightly
negative, not zero, but close to it. On a 93-query denominator, -0.005 is
roughly one query's worth of net movement, not a broad regression.

**Interview-ready framing**: reranking is a precision tool layered on an
already-good first stage, not a recall tool — recall is the first stage's
job. This is the "two-stage retrieval separates candidate recall from
final precision" framing from
`docs/day-08-reranking-two-stage-retrieval.md`, now with a number attached
to each half of that claim: a sharp P@1/MRR gain alongside a nearly flat
R@5 is what "the reranker is doing its actual job, not compensating for a
bad first stage" looks like. If R@5 had dropped sharply instead, that
would be evidence the shortlist itself needed work, not just the reranker.

### Q014 at chunk level — does chunk-level first-stage already fix it?

Day 7's clearest "hybrid still fails" case, restated: *"What uptime must a
business-critical SaaS service commit to?"* (expected: `CONTRACT-004`,
`POL-003`, `GUIDE-002`). At **whole-document** granularity, RRF and
weighted fusion both landed on `SOP-007` — a document moderately supported
by both BM25 and dense — over `CONTRACT-004`, which only dense ranked
highly. That consensus-over-strength failure is exactly what Day 8 set out
to test at chunk level.

**At chunk level, this specific failure is already gone before reranking
ever runs.** From `./.venv/bin/python src/reranking.py`'s Q014 section:

- First-stage top-1 (chunk-level Hybrid RRF, before any reranking):
  `POL-003::chunk-11` — a genuinely correct document (`POL-003` is in
  `expected_relevant_ids`), RRF score 0.0328.
- After cross-encoder reranking, top-1 is unchanged: still
  `POL-003::chunk-11` (cross-encoder score 3.1654). Ranks #2 and #3 do
  shift, from `CONTRACT-001`/`SOP-007` chunks (both wrong documents) to two
  different `GUIDE-002` chunks (also a correct document).

**Honest reading, not the one this day set out expecting**: reranking did
not need to fix Q014's document-level top-1, because moving from
whole-document to chunk-level fusion already fixed it — a different
mechanism (Day 7's chunking, not Day 8's reranking) closed this particular
gap. That is a real, useful finding, not a null result to bury: it shows
the whole-document RRF weakness Day 7 found is at least partly a
*retrieval-unit* artifact — a ~3-sentence chunk carries far less unrelated
text than its parent document, so a chunk-level BM25/dense signal is less
likely to get diluted into "moderate agreement across the board" the way a
whole document's aggregate score can — not purely a fusion-formula
weakness that only reranking could fix. What reranking *did* still do on
this query: clean up the shortlist below rank 1, promoting a second
correct document (`GUIDE-002`) into the top 3 over two incorrect ones —
visible in the `final_rank` vs. `first_stage_rank` fields, not something
an unchanged top-1 alone would show.

Two contrast queries checked in the same run (`src/reranking.py`'s
`DEMO_QUERY_IDS`):

- **Q009** (exact numeric threshold — shareholding percentage for
  beneficial-ownership checks; first stage already correct) — top-1 stays
  `POL-002::chunk-2` after reranking. Confirms reranking does not break a
  case that was not broken.
- **Q042** (Day 7's own "hybrid wins" example — purchasing card spending
  limits) — first-stage top-1 is `FAQ-001::chunk-14`; after reranking,
  top-1 becomes `SOP-004::chunk-2`. Both `FAQ-001` and `SOP-004` are in
  `expected_relevant_ids`, so this is a reorder between two already-correct
  answers, not a regression.

### Known caveats

- **Domain mismatch is real but not fatal on this corpus.**
  `cross-encoder/ms-marco-TinyBERT-L2-v2` is trained on MS MARCO
  web/search query-passage pairs, not procurement text — yet it still
  improved P@1 by 4.3 points here. That is evidence the model's general
  relevance-judgment ability transfers reasonably well to this domain, not
  proof it would hold on a larger or more idiosyncratic procurement
  corpus; a domain-mismatch failure could still show up on harder queries
  the 93-query v1 set does not cover.
- **Binary relevance only**, the same limitation as every other row in
  this report — `relevance_grades` is not used, so a promotion from a
  grade-1 to a grade-2 relevant document (or vice versa) is invisible to
  P@1/R@5/MRR here.
- **R@5's small drop is worth re-checking later, not dismissing.**
  Reranking cannot change which documents are present in the 15-chunk
  candidate set — it never retrieves anything new, only reorders what the
  first stage already found — so it cannot help or hurt *candidate-set*
  recall. It absolutely *can* move R@5 after truncation, though, by
  pushing a relevant document below rank 5 within that same candidate set,
  and the measured number here shows exactly that: R@5 went from 0.811 to
  0.806 as P@1 and MRR@10 both improved. 93 queries is a fairly small
  denominator for a 0.005 difference, so this should not be over-read as
  "reranking reliably costs 0.5 points of R@5" — but it is a real,
  measured effect, not a rounding artifact to wave away.
- **Not attempted today, in scope for later**: LLM-as-reranker
  (Boot.dev's "LLMs for Re-Ranking" / "LLM Batch Re-Ranking" lessons).
  `src/reranking.py`'s `rerank` function accepts any `score_fn`, so an
  LLM-judge scorer could plug into the same pipeline without changing
  `build_chunk_shortlist` or the auditability contract — left for a future
  day per today's scope (`docs/day-08-reranking-two-stage-retrieval.md`).

## Day 9: Graded relevance, filter-adjusted evaluation, and error slices

Date: 2026-09-14
Implementation: `src/eval_metrics.py` — `discounted_cumulative_gain`,
`ndcg_at_k`, `grades_for_query`, `evaluate_ndcg` (graded relevance);
`filter_adjusted_relevant_ids`, `filter_adjusted_grades`,
`build_filtered_queries` (filter-adjusted ground truth);
`slice_queries`, `evaluate_slices`, `primary_count` (error slices). Tests
in `tests/test_eval_metrics.py` — 23 new tests: hand-computed nDCG cases
(ties, a missing/unjudged id, an empty retrieved list, a query with no
relevant grades at all, the ideal ranking), filter-adjustment checked
against the real v1 queries the design doc names (Q001, Q007, Q019), and
the slice-aggregation helpers.

Every number below came from actually running
`./.venv/bin/python src/eval_metrics.py` on 2026-09-14 — none of it is
projected or hand-typed ahead of the code. That run now prints four
labeled sections (binary unfiltered, graded unfiltered, filtered-adjusted,
error slices) instead of one, in ~21s total on a laptop CPU (vs. ~16s for
the Day 8 nine-row table alone) — the small added cost is from the two new
*filtered* retrieve functions (21 queries each) and the nDCG table, not
from re-running the expensive cross-encoder pass a second time: every
method's `retrieve_fn` is memoized by `query_id` inside `main()`
(`_memoize_by_query_id`) specifically so the binary table, the graded
table, and every error slice can reuse one retrieval per query instead of
paying for it up to six times over.

### Manual relevance rubric (Boot.dev's "Manual Evaluation" lesson, applied)

Before adding a graded metric, the grades it consumes need a plain-English
definition, not just a number. This is what the v1 corpus's
`relevance_grades` field already encodes per document per query — this
rubric names what "2", "1", and "0" mean in procurement terms, and is what
every judgment in `data/corpus_v1/example_queries.jsonl` was already made
against, not a new standard invented today:

- **Grade 2 — primary.** The document that actually answers the question:
  it names the specific clause, threshold, band, supplier, or figure the
  query asks for, with enough scope and precision that a buyer could act on
  it without reading anything else. Example: for Q001 ("What approval is
  required for a EUR 60,000 purchase order?"), `POL-001` states the exact
  approval band and who signs off on it — that is the primary answer.
- **Grade 1 — secondary / partially relevant.** A document that is
  genuinely useful context but is not, on its own, a complete or precise
  enough answer — it might restate the same rule informally (an FAQ), cover
  a related but narrower or broader scope, or supply a supporting fact the
  primary document assumes. Example: for Q001, `FAQ-001` restates the same
  approval rule in plain language for requesters, but `POL-001` is still
  the authoritative source — FAQ-001 is useful, not the answer.
- **Grade 0 — not relevant.** A document that does not appear in
  `expected_relevant_ids` at all for that query. It might be topically
  adjacent (another policy, another supplier's contract) without answering
  *this* question, or unrelated altogether. Absence from the grades dict is
  what `grades_for_query`/`ndcg_at_k` treat as grade 0 by default — there
  is no need to enumerate every non-relevant document explicitly.

The reason this distinction matters for a metric, not just a human reader:
P@1/R@5/MRR@10 treat grade 2 and grade 1 as identical "hits". A system that
ranks `FAQ-001` above `POL-001` for Q001 scores exactly the same P@1 as one
that ranks them the other way around — even though the second system found
the actual authoritative clause first and the first system merely found
something *related* to it. nDCG@5 below is the metric built to see that
difference.

### Graded relevance: nDCG@5

**Why nDCG, in one sentence**: it asks "did the system rank the *best*
evidence first", not just "did it retrieve *something* acceptable" — see
the rubric above for what "best" (grade 2) vs. "acceptable" (grade 1) means
here. `ndcg_at_k` computes `DCG@k` of the actual ranking (each retrieved
document's grade, discounted by `1/log2(rank+1)` so a hit at rank 1 counts
in full and a hit further down counts for steadily less) divided by
`DCG@k` of the *ideal* ranking for that query (every graded document,
best-grade-first) — a score of 1.0 means the ranking put the best possible
grades into the best possible order in the top k slots.

93/93 v1 queries, same nine methods, k=5 (matching R@5's depth):

| Method | Retrieval unit | nDCG@5 |
|---|---|---:|
| TF-IDF | document | 0.818 |
| BM25 | document | 0.792 |
| Dense (multi-qa-MiniLM) | document | 0.740 |
| Dense (multi-qa-MiniLM) | chunk→document | 0.828 |
| Hybrid RRF (BM25 + dense) | document | 0.799 |
| Hybrid weighted, α=0.5 (BM25 + dense) | document | 0.822 |
| Hybrid RRF (BM25 + dense) | chunk→document | 0.863 |
| Hybrid weighted, α=0.5 (BM25 + dense) | chunk→document | 0.851 |
| Cross-encoder reranked Hybrid RRF (BM25 + dense) | chunk→document | **0.869** |

**Measured, not assumed.** The broad winner/loser story is consistent with
the binary P@1 table — the cross-encoder reranked row is still best,
chunk-level hybrid RRF is still the best first-stage row, dense-alone
(whole document) is still weakest — but the *strict* ranking is not
identical, and that difference is itself informative, not noise to
smooth over. Two pairs tie exactly on P@1 and nDCG@5 tells them apart:
Dense chunk→document and Hybrid weighted chunk→document tie at 0.925 P@1,
but nDCG@5 separates them (0.828 vs. **0.851** — weighted fusion ranks the
*primary* document better even though both find *a* relevant document at
rank 1 equally often); BM25 and Hybrid RRF (document) tie at 0.860 P@1,
and nDCG@5 again separates them (0.792 vs. **0.799**). In both cases the
nDCG-implied order is a tie-break, not an inversion of two methods P@1 had
already told apart — no method that clearly beats another on P@1 loses to
it on nDCG@5 anywhere in this table. So the correct claim is: **nDCG@5
confirms the broad story and breaks every P@1 tie, exposing ranking-
quality differences binary precision cannot see, not "the two metrics
agree in every respect."** That is expected in direction, not a
coincidence to explain away: a method that is better at ranking *any*
relevant document first is very likely also better at ranking the
*primary* one first, since a primary document is relevant by definition —
but "very likely" is not "always identical", and the ties above are where
that gap actually shows up. What nDCG adds beyond confirming that ordering
is *how much room is left* — every nDCG@5 number here is
noticeably below its own method's P@1 (e.g. the reranked row is 0.978 P@1
but only 0.869 nDCG@5), because P@1 only asks about rank 1, while nDCG@5
also credits (and can be hurt by) what happens at ranks 2-5 — a primary
document buried at rank 4 behind three secondary ones drags nDCG@5 down
even on a query where P@1 already gives full credit for something else
correct at rank 1, or where the top-1 answer is itself secondary rather
than primary. This is real, additional signal binary P@1/R@5/MRR@10 cannot
see at all.

### Filter-adjusted evaluation

**The methodology.** Reusing the unfiltered `expected_relevant_ids` to
score *filtered* retrieval would be unfair — 17 of the 21 v1 queries with a
`metadata_filters` value have at least one expected id their own filter
would exclude (see "Metadata filtering" above). `filter_adjusted_relevant_ids`
fixes this in three steps, applied per query:

1. Take the query's own `metadata_filters` and its own `expected_relevant_ids`.
2. Keep only the expected ids whose *own* document metadata satisfies that
   filter (`hybrid_search.matches_filters` — the identical rule
   `filter_ranked_results` already applies to retrieved documents, applied
   here to the gold documents instead).
3. Score filtered retrieval against that *adjusted* set, not the original
   one — `build_filtered_queries` does this for every filtered query at
   once, producing query rows `evaluate_method`/`evaluate_ndcg` can score
   completely unmodified.

**Real v1 examples, not synthetic ones** (`tests/test_eval_metrics.py`
checks these three against the actual corpus and query file):

| Query | Filter | Original `expected_relevant_ids` | Filter-adjusted gold |
|---|---|---|---|
| Q001 | `doc_type: policy` | `POL-001` (primary), `FAQ-001` (secondary) | `POL-001` — `FAQ-001` is a FAQ, not a policy |
| Q007 | `doc_type: policy` | `POL-002` (primary), `FAQ-002` (secondary), `POL-005` (secondary) | `POL-002`, `POL-005` — `FAQ-002` is dropped, but `POL-005` *survives* because it is also a policy |
| Q019 | `category: compliance` | `POL-005` (primary), `AUDIT-001` (secondary) | `POL-005` — `AUDIT-001`'s category is `procurement-operations`, not `compliance` |

Q007 is the case worth pointing at specifically: filter-adjustment is not
"keep only the primary document, drop every secondary one" — a secondary
document is kept whenever it happens to also match the filter (`POL-005`
here). The adjustment is about the *filter*, not about relevance grade.

**Retrieval also has to apply the filter, not just the gold set.**
`_filtered_chunk_shortlist` (in `eval_metrics.py`'s `main()`) reruns
BM25-over-chunks and dense-over-chunks against the *full* 570-chunk index
(not `CANDIDATE_POOL_SIZE`, for the exact reason `filter_ranked_results`'s
docstring and the Day 7 `POL-005`/Q007 regression test already
established — filtering a narrow pool can silently drop a real match that
ranks just outside it), filters each chunk by its *parent* document's
metadata, caps back down to `CANDIDATE_POOL_SIZE`, then fuses — the same
shortlist shape `reranking.build_chunk_shortlist` produces, so the
first-stage and reranked filtered rows below stay comparable to their
unfiltered counterparts everywhere except the filtering step itself.

**Results — 21/21 queries with a `metadata_filters` value:**

17/21 of those queries have at least one `expected_relevant_ids` entry
excluded by their own filter (checked programmatically, matching the count
in "Metadata filtering" above); 0 lose every gold id.

| Method | Retrieval unit | P@1 | R@5 | MRR@10 |
|---|---|---|---|---|
| Hybrid RRF (BM25 + dense), filtered | chunk→document | 1.000 | 0.948 | 1.000 |
| Cross-encoder reranked Hybrid RRF, filtered | chunk→document | 1.000 | 0.948 | 1.000 |

**Measured, not assumed — three findings, not one.**

1. **The R@5 jump from unfiltered to filtered is mostly a methodology
   correction, not a retrieval effect — and the two have to be reported
   separately, not conflated.** An earlier draft of this section compared
   0.762 (unfiltered retrieval, scored against the *original* gold) against
   0.948 (filtered retrieval, scored against *filter-adjusted* gold) and
   called the whole 0.186 gap a filtering benefit. That comparison changes
   two things at once — what got retrieved *and* what it was scored
   against — so it cannot isolate what filtering the *retrieval* itself
   contributed. Separating the two variables, over the same 21 queries:

   | Retrieval | Gold set | Hybrid RRF chunk→document R@5 | Reranked chunk→document R@5 |
   |---|---|---:|---:|
   | Unfiltered | Raw (original `expected_relevant_ids`) | 0.786 | 0.762 |
   | Unfiltered | Filter-adjusted | 0.925 | 0.901 |
   | Filtered | Filter-adjusted | 0.948 | 0.948 |
   | Filtered | Raw | 0.560 | 0.560 |

   Reading down each column: **switching from raw to adjusted gold (row 1
   → row 2), with retrieval held fixed, accounts for most of the movement**
   (+0.139 for Hybrid RRF, +0.139 for reranked) — that is the effect of
   fixing an unfair ground truth, not of filtering anything. **Actually
   filtering retrieval on top of that same adjusted gold (row 2 → row 3)
   is the real, apples-to-apples filtering effect**, and it is real but
   much smaller: +0.023 for Hybrid RRF (0.925 → 0.948), +0.047 for
   reranked (0.901 → 0.948). The fourth row (filtered retrieval scored
   against *raw* gold, 0.560) is included only to show why raw gold cannot
   be reused for filtered retrieval at all — it looks like a severe
   regression, but it is an artifact of penalizing a filtered retriever for
   correctly excluding out-of-scope secondary documents the filter was
   always going to remove, exactly the unfairness this whole methodology
   exists to correct.
2. **Both methods land on identical aggregate numbers, but not because
   reranking did nothing.** Two queries (Q007, Q055) have different
   document orderings after reranking than before it — reranking is doing
   real work — but P@1/R@5 only look at rank-1 identity and top-5
   membership, and neither of those two queries' reorderings crosses a
   metric-relevant boundary. The honest reading: **filtering narrows the
   candidate universe so much for these particular queries (several queries
   filter down to 1-4 candidate documents total) that first-stage retrieval
   is already at or near ceiling, leaving the reranker little headroom to
   move P@1/R@5 on this specific 21-query slice** — not evidence that
   reranking is generally useless under filtering.
3. **R@5's 0.948, not 1.000, has a specific, checked cause.** Three
   queries fall short of full recall in their filtered top 5: Q007 (R@5
   0.5 — `POL-005`, a real secondary match, ranks outside the filtered
   top 5 for this query), Q011 (R@5 0.75), and Q035 (R@5 0.667) — all three
   are multi-gold queries where a lower-priority correct document didn't
   make the cut, not a bug in the filtering or scoring code.

### Error slices

**Why**: an aggregate number across all 93 queries can hide which *class*
of query a method is weak on. `evaluate_slices` reruns the exact same
`evaluate_method` per group of queries, over the full unfiltered 93-query
set, for the two most important methods in this report — the best
first-stage row and the best overall row.

**By query type:**

| Query type | n | Hybrid RRF chunk→document (P@1/R@5/MRR@10) | Reranked (P@1/R@5/MRR@10) |
|---|---:|---|---|
| conceptual | 17 | 0.941 / 0.853 / 0.971 | 1.000 / 0.868 / 1.000 |
| lookup | 23 | 0.957 / 0.797 / 0.978 | 1.000 / 0.790 / 1.000 |
| multi_doc | 5 | 0.800 / 0.603 / 0.900 | **0.600** / 0.630 / 0.707 |
| numeric | 7 | 0.857 / 0.893 / 0.893 | 1.000 / 0.845 / 1.000 |
| procedural | 14 | 0.929 / 0.815 / 0.964 | 1.000 / 0.815 / 1.000 |
| supplier_specific | 13 | 1.000 / 0.737 / 1.000 | 1.000 / 0.737 / 1.000 |
| terminology | 6 | 1.000 / 0.944 / 1.000 | 1.000 / 0.944 / 1.000 |
| threshold | 8 | 0.875 / 0.833 / 0.938 | 1.000 / 0.792 / 1.000 |

**By difficulty:**

| Difficulty | n | Hybrid RRF chunk→document | Reranked |
|---|---:|---|---|
| easy | 15 | 0.867 / 0.911 / 0.933 | 1.000 / 0.867 / 1.000 |
| medium | 52 | 0.942 / 0.796 / 0.966 | 1.000 / 0.796 / 1.000 |
| hard | 26 | 0.962 / 0.783 / 0.981 | 0.923 / 0.791 / 0.944 |

**By filtered vs. unfiltered** (whether the query *carries* a filter — this
is unfiltered retrieval sliced by query property, not the filtered-adjusted
table above):

| Slice | n | Hybrid RRF chunk→document | Reranked |
|---|---:|---|---|
| filtered | 21 | 0.905 / 0.786 / 0.952 | 1.000 / 0.762 / 1.000 |
| unfiltered | 72 | 0.944 / 0.819 / 0.969 | 0.972 / 0.819 / 0.980 |

**By single- vs. multi-primary** (`primary_count(query_row) == 1` vs. `> 1`
— 45 queries have exactly one grade-2 document, 48 have two or more):

| Slice | n | Hybrid RRF chunk→document | Reranked |
|---|---:|---|---|
| single-primary | 45 | 0.911 / 0.785 / 0.950 | 1.000 / 0.796 / 1.000 |
| multi-primary | 48 | 0.958 / 0.835 / 0.979 | 0.958 / 0.816 / 0.969 |

**Largest weak slice — measured, then explained, not just flagged.**
`multi_doc` is the reranked method's weakest query-type slice: P@1 0.600
over 5 queries vs. 0.978 overall — the single biggest gap in this whole
error-slice analysis, and the *only* slice where the reranked method scores
below its own first-stage row (0.600 vs. 0.800). Tracing it to a specific
query: **Q091** ("What approvals and security evidence do I need for a EUR
120,000 SaaS renewal?", gold: `GUIDE-002`, `POL-001`, `POL-003`, `SOP-004`,
`SOP-006`) is correct at first stage (`POL-003` top-1) and *becomes wrong*
after reranking (`SOP-001` top-1, not in the gold set; `POL-003` drops to
rank 3). `Q092` was already wrong before reranking and stays wrong.
`Q005`/`Q016`/`Q093` are correct both before and after. **Honest reading**:
this is the one query-type slice, out of eight, where the cross-encoder
measurably hurts top-1 accuracy instead of helping or holding steady —
consistent with, and a sharper version of, the aggregate R@5 dip Day 8
already found (0.811 → 0.806), and a reasonable place to point at a
domain-mismatch explanation: `Q091` asks about a multi-part approval-plus-
security-evidence answer, and `ms-marco-TinyBERT-L2-v2` is a general
web/search model, not tuned to prefer a passage that is procedurally
correct over one that merely reads as more directly responsive to the
literal question text. Five queries is too small a slice to generalize
from confidently, but it is the clearest, most specific "next fix" this
report's error-slice analysis points at — see the next step in
`docs/learning-log.md`'s Day 9 entry.

### What Day 9 did not do

- No filtered nDCG table — `filter_adjusted_grades` is implemented and
  tested (including against the real Q001 query), but `main()` does not
  currently print a filtered graded table; the design doc's own "Report
  shape" only calls for one filtered table, and the binary one above
  already carries the filtered-evaluation methodology story end to end.
- No LLM-as-judge implementation or prototype — deferred entirely; the
  manual rubric above is what today's grades were (and still are) judged
  against, and Day 8's caveat about LLM-as-reranker risk applies just as
  much to LLM-as-judge (inconsistency, prompt/model drift, needing
  calibration against exactly this kind of human rubric before it could be
  trusted as a scorer).
- The filtered-adjusted table only covers the two "key methods"
  (first-stage chunk hybrid RRF, reranked chunk hybrid RRF), not all nine
  binary-table rows — chosen because those are the two rows every other
  Day 9 comparison (graded table, error slices) also focuses on, not
  because filtering the other seven would be harder to build.

## Day 10: Source-cited answer generation

Date: 2026-09-14
Implementation: `src/generation.py` — `build_sources`/`format_sources_block`
(the context contract: a ranked chunk list becomes numbered, citable
sources); `build_prompt`/`PROMPT_INSTRUCTIONS` (the augmentation step:
answer only from the numbered sources, cite specific ones, don't merge
conflicting evidence, refuse rather than guess); `extract_cited_source_ids`/
`validate_citations` (the citation contract: every `[n]` in the answer is
checked against the real numbered sources); `generate_answer`/
`INSUFFICIENT_EVIDENCE_ANSWER` (the generation boundary — a plain
`client(prompt) -> text` callable, fake in tests, live for the demo below);
`make_openrouter_client` (an optional live client — the official `openai`
Python SDK pointed at OpenRouter's OpenAI-compatible `base_url`, with
`python-dotenv`'s `load_dotenv()` reading `OPENROUTER_API_KEY` out of
`.env`; both are real `pyproject.toml` dependencies now, used only inside
this one function, and the `openai` import itself happens only after the
API-key check passes — see "Reproducibility hardening" below). Tests in
`tests/test_generation.py` — 15 deterministic tests, no network calls (14
from the initial build, plus one added the same day to cover the
blank-provider-content guard — see "Reproducibility hardening" below).

Everything below came from actually running the commands shown on
2026-09-14 — none of it is hand-typed or projected ahead of the code.

### Gate re-run before building

```
./.venv/bin/pytest -q
# 120 passed in 0.60s   (before Day 10's tests were added)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python src/eval_metrics.py
# Cross-encoder reranked Hybrid RRF chunk→document: P@1 0.978, R@5 0.806, MRR@10 0.984, nDCG@5 0.869
# Largest weak slice: reranked multi_doc P@1 0.600 over 5 queries
```

Same retrieval story Day 9 left off with: the reranked chunk-level Hybrid
RRF row is still the strongest overall, and `multi_doc` queries are still
the weakest slice. Day 10 exists to find out what that retrieval weakness
looks like once it reaches an actual generated answer — see "Demo output"
below, where it shows up exactly as expected.

### The context/citation contract

- **Context schema** (one dict per source, built by `build_sources` from a
  ranked chunk list): `source_id` (the 1-based citation number shown in the
  prompt), `doc_id`, `title`, `chunk_id`, `text`, `rank`, `score`. Sources
  are chunk-level, not rolled up to documents — two chunks from the same
  document can be, and in the Q091 demo below are, two separate numbered
  sources, so a citation can point at the exact quoted passage instead of
  just "somewhere in this document."
- **Prompt contract**: answer only from the numbered sources; cite the
  source for every specific claim (amount, threshold, percentage, supplier,
  date, approval role); if sources disagree or apply to different
  scopes, name the difference and cite each separately rather than merging
  them; refuse rather than guess when the sources are not enough; never
  invent a source number.
- **Citation contract**: `validate_citations` checks every `[n]` the model
  wrote against the real source list and reports `valid_ids` (real,
  traceable citations), `orphan_ids` (a citation to a source number that
  does not exist — a hallucinated citation), and `uncited_ids` (a real
  source that was retrieved but never cited). Both demo answers below came
  back with zero orphan citations.
- **Empty-context behavior**: `generate_answer` returns the fixed
  `INSUFFICIENT_EVIDENCE_ANSWER` and never calls the client at all when no
  sources were retrieved — tested directly in
  `tests/test_generation.py::test_generate_answer_with_empty_sources_refuses_without_calling_client`
  by handing it a client that raises if it is ever invoked.
- **Test boundary**: every deterministic test uses a small fake
  `client(prompt) -> text` function. `make_openrouter_client` (a real,
  live client) is imported by `main()` only, never by the test suite. The
  boundary holds at the *import* level too, not just the network level:
  `make_openrouter_client` validates `OPENROUTER_API_KEY` before importing
  `openai` at all, so a caller with no key (the entire test suite) never
  needs the `openai` package importable — `test_make_openrouter_client_raises_without_api_key_before_any_network_call`
  would fail with `ModuleNotFoundError` instead of the intended `RuntimeError`
  if that ordering were ever reversed.

### Demo output (real run, 2026-09-14, live OpenRouter call, post-review-fix)

`./.venv/bin/python src/generation.py`, with `OPENROUTER_API_KEY` set in
`.env` and the current default model (`inclusionai/ling-3.0-flash-fin:free`
— a free, non-reasoning, text-to-text OpenRouter model, confirmed live
against `https://openrouter.ai/api/v1/models` on 2026-09-14; see
`src/generation.py`'s `DEFAULT_OPENROUTER_MODEL` comment if that model is
ever retired). This is the output of the *sixth* live attempt today, after
the reproducibility fixes below — see "Reproducibility hardening" for why
it took six:

```
Q001 (threshold): What approval is required for a EUR 60,000 purchase order?
  retrieved sources:
    [1] FAQ-001 — FAQ — Purchase Orders, Approvals and Starting Work
    [2] FAQ-001 — FAQ — Purchase Orders, Approvals and Starting Work
    [3] POL-001 — Global Procurement Policy — Approval Thresholds and Delegation of Authority
    [4] FAQ-001 — FAQ — Purchase Orders, Approvals and Starting Work
    [5] FAQ-001 — FAQ — Purchase Orders, Approvals and Starting Work

  answer:
    For a EUR 60,000 purchase order, **VP Procurement approval with a Finance review** is required — not Category Manager approval.

    This is established by the following sources:

    - **[4]** states: *"A three-year service at €20,000 per year is a €60,000 commitment and needs VP Procurement approval with a Finance review, not Category Manager approval."*
    - **[5]** repeats the same rule: *"A three-year service at €20,000 per year is a €60,000 commitment and needs VP Procurement approval with a Finance review, not Category Manager approval."*

    Additionally, **[4]** clarifies that the approval level is determined by the **total committed value over the full term** of the commitment, not by the invoice amount or the amount falling within a single financial year. **[3]** confirms that approval bands apply to the total committed value expressed in EUR.

    **Note:** Separately, **[1]** and **[2]** indicate that a €60,000 purchase also triggers a competition requirement — three qualified bids are required above €25,000 and up to €250,000 of total committed value.

  citation check: {'cited_ids': [1, 2, 3, 4, 5], 'valid_ids': [1, 2, 3, 4, 5], 'orphan_ids': [], 'uncited_ids': []}

Q091 (multi_doc): What approvals and security evidence do I need for a EUR 120,000 SaaS renewal?
  retrieved sources:
    [1] SOP-001 — Standard Operating Procedure — Three-Bid Requirement and Sourcing Exception Handling
    [2] FAQ-001 — FAQ — Purchase Orders, Approvals and Starting Work
    [3] FAQ-001 — FAQ — Purchase Orders, Approvals and Starting Work
    [4] POL-003 — Information Security and Data Protection Requirements for Technology Suppliers
    [5] SOP-001 — Standard Operating Procedure — Three-Bid Requirement and Sourcing Exception Handling

  answer:
    ## Approvals and Security Evidence for a EUR 120,000 SaaS Renewal

    ### 1. Sourcing and Approval Requirements

    **Three qualified bids are required.** A EUR 120,000 commitment falls in the €25,000–€250,000 range, which mandates three qualified bids [2]. You cannot split the request to stay under a threshold [3].

    **VP Procurement approval with Finance review.** Based on the precedent in the sources, a commitment of this significance requires VP Procurement approval with a Finance review [3]. (The source explicitly states this for a €60,000 commitment; a €120,000 commitment is of equal or greater significance, so this approval level applies at minimum.)

    **Records must be maintained in Ariba Sourcing.** For every award above €25,000, the following must exist: the requirement document issued to suppliers, the invitation list with dates, the bids received (or the exception form), the comparison/evaluation record, the award recommendation, and the approval evidence. Records are retained for seven years [5].

    ### 2. Security and Data Protection Evidence

    **Annual certification refresh.** Certification evidence must be refreshed annually as part of continuous assurance [4].

    **Risk acceptance limits.** Risk acceptance may not exceed 12 months and may not be renewed more than once [4].

    **Lapsed certificates.** A lapsed certificate is treated as a control failure and triggers a review of whether the service may continue [4].

    ### 3. If Seeking a Sourcing Exception

    If you intend to single-source without three bids, any exception above €250,000 must be reviewed by Procurement Governance before the approver receives it [1]. For a €120,000 award (below €250,000), the standard three-bid rule applies per [2], but exception handling procedures still govern the process [1]. An approved exception is valid for a maximum of 12 months or the duration of the specific award, whichever is shorter [1]. On a second renewal, a plan and date for a competitive event (or a Category Council decision to designate the supplier as strategic/single-sourced) must be recorded [5].

    ---

    **Summary:** For a EUR 120,000 SaaS renewal, you need three qualified bids [2], VP Procurement approval with Finance review [3], full Ariba Sourcing records [5], and annual security certification evidence with risk acceptance not exceeding 12 months and not renewed more than once [4].

  citation check: {'cited_ids': [1, 2, 3, 4, 5], 'valid_ids': [1, 2, 3, 4, 5], 'orphan_ids': [], 'uncited_ids': []}
```

(Full untruncated source text is longer in the real terminal output; the
`[n]` header lines above are reproduced exactly, the answer text is
reproduced in full and unedited. See "Reproducibility hardening" below for
the five earlier, broken attempts from today that led here.)

**Q001 reads as a genuine success.** Every claim traces to a real source:
the approval role to `[4]`/`[5]`, the "total committed value over the full
term" rule to `[4]`, and the competition requirement to `[1]`/`[2]` — five
sources retrieved, five cited, zero orphans, zero left unused. Exactly the
"answer only from the sources, cite the specific claim" contract working
as designed.

**Q091 is the more important result, and it is genuinely more complete
than the earlier reasoning-model answer to the same question (see "A
live-only bug the deterministic tests couldn't catch" below for that
earlier transcript) — but it is worth being precise about *why*, and about
one place where it takes a small liberty the prompt's own rules do not
quite license.** The retrieved top-5 sources for this query still do *not*
include `POL-001` (the approval-bands policy — grade 2/primary for this
query) or `GUIDE-002` (the renewal-timing guide — also grade 2), even
though both are in `expected_relevant_ids` for Q091 and this is exactly
the `multi_doc` weak slice Day 9 already flagged (P@1 0.600 over 5
queries) — switching the generation model changed nothing about
*retrieval*, which is the point: this is a different model, same
retrieval gap. Zero orphan citations, every claim backed by a real source,
sources kept separate by section rather than blended into one number. But
look closely at the approval-level claim: rule 3 of `PROMPT_INSTRUCTIONS`
says "if the sources do not contain enough information to answer, say so
plainly instead of guessing," and the *previous* model's answer to this
exact question did exactly that ("[3] does not specify a VP approval
threshold for amounts above €60,000"). This run's answer instead
extrapolates — "a €120,000 commitment is of equal or greater significance,
so this approval level applies at minimum" — a caveated inference, not a
flat assertion, and still cited to `[3]`, but a real step past "the source
only states this for €60,000" toward guessing what a higher amount
probably needs. It is a small, honest illustration that "refuse rather
than guess" is a prompt *rule*, not a property automatically shared by
every model that receives it — worth catching by a future faithfulness
check (see "Next step" in `docs/learning-log.md`), not something today's
citation-only checks can flag. Either way, the deeper point stands: no
model reading only these five sources can correctly state the actual
expected answer (Band 3, €50,000–€250,000, VP Procurement approval),
because the retrieval step never surfaced the one document that states
it. **This is still the clearest piece of evidence in this project for
"retrieval quality and answer quality are different axes": a generator's
citation hygiene, or lack of it, cannot correct for a retrieval miss it
was never shown.** Good citations prove an answer is faithful to *what it
was given* — they say nothing about whether what it was given was
complete, or about exactly how far the model reasoned past it.

### A live-only bug the deterministic tests couldn't catch

The first live run today (against `DEFAULT_OPENROUTER_MODEL`,
`nvidia/nemotron-3.5-lightning:free`, called with the plain `openai` SDK
default request) did not produce the clean answers above. It produced
several paragraphs of the model's raw internal reasoning ("Let's examine
the sources... I'll cite [5] as the primary, or both...") narrating its way
through the citation rules, then trailed off mid-sentence into truncated,
garbled text once it ran out of output budget — `nvidia/nemotron-3.5-lightning`
is a *reasoning* model, and by default OpenRouter returns its
chain-of-thought as part of `message.content` instead of a clean final
answer. The fix, applied to `make_openrouter_client`, is an
OpenRouter-specific request extension passed through the `openai` SDK's
`extra_body` (not a normal keyword argument, since it is not part of the
standard OpenAI API): `extra_body={"reasoning": {"exclude": True}}`. With
that set, the model still reasons internally but only the final answer
comes back — exactly the two answers shown above.

This is worth recording for two reasons. First, it is real, not
hypothetical, evidence for this project's citation-gate philosophy: a
model can be perfectly capable and still return something unusable for a
user-facing answer for reasons that have nothing to do with retrieval or
prompt correctness. Second, it is exactly why the design doc insists live
LLM calls stay out of the deterministic `pytest` gate — no fake-client unit
test could have caught this, because the bug was in a specific model's
default response *shape* on a specific hosted provider, not in this
project's own prompt/citation logic. It was only visible by actually
running the live smoke test and reading the output.

### Reproducibility hardening (post-review fixes, same day)

External code review of this Day 10 addendum caught three real problems
with the state above, all worth recording honestly rather than quietly
patching:

1. **The live demo was not reproducible from the committed state.** The
   reviewer ran `./.venv/bin/python src/generation.py` and it hung for over
   300 seconds — past the reranker weights loading, before any answer —
   because `make_openrouter_client`'s `OpenAI(...)` client had no request
   timeout at all. A slow or momentarily overloaded free-tier backend could
   block `main()` indefinitely with no error and no way to tell "still
   working" from "stuck." **Fix**: `OPENROUTER_TIMEOUT_SECONDS = 60.0`,
   passed as `timeout=` to the `OpenAI(...)` constructor, so a hung request
   now fails loudly with a normal `openai` timeout exception inside a
   bounded window instead of hanging. `max_tokens` and `temperature=0.0`
   were also pinned explicitly on the request: `max_tokens` bounds
   worst-case latency/cost to a fixed budget instead of however long the
   model feels like generating, and `temperature=0` removes randomized
   sampling as a source of run-to-run variance (it does not *guarantee*
   byte-identical output run to run — a hosted provider can still change
   routing, quantization, or model weights between calls — but it is the
   honest, standard meaning of "as reproducible as a live third-party API
   call can be").

   Getting an actually-clean transcript out of this fix took six live
   attempts on 2026-09-14, each one a real finding, not a detour:
   - **700 tokens, original model (`nvidia/nemotron-3.5-lightning:free`,
     a reasoning model):** made things *worse* — cut the model off
     mid-chain-of-thought before `reasoning: {"exclude": True}` had a
     clean answer to hand back, so the raw "Here's a thinking process..."
     trace leaked into `message.content`, this time truncated by
     `max_tokens` instead of by the model's own budget. Reasoning tokens
     count against `max_tokens` even when excluded from the visible
     response, so too tight a cap starves the hidden reasoning pass.
   - **2000 tokens, same model:** fixed the easy query (Q001) but not the
     harder, four-source query (Q091) — same leaked trace, just cut off
     later. A question that has to reason about four sources under the
     "don't merge conflicting/differently-scoped evidence" rule needs a
     longer hidden reasoning pass than a single-source lookup, so "enough"
     tokens turned out to be query-dependent, not a fixed model property.
   - **4000 tokens, same model:** worse again, in a *different* way — Q001
     came back as a hallucinated, off-topic markdown table about LLM
     benchmarks (nothing to do with procurement), and Q091 again leaked a
     truncated reasoning trace, this time visibly degrading into
     incoherent text near the cutoff. Raising the budget further was
     chasing a moving target on a flaky free-tier reasoning model, not
     converging on a fix.
   - **Model switch** (`DEFAULT_OPENROUTER_MODEL` →
     `inclusionai/ling-3.0-flash-fin:free`, confirmed live against
     `https://openrouter.ai/api/v1/models` as free and reasoning-disabled
     by default): the actual fix for the chain-of-thought-leak failure
     class — a non-reasoning model has no hidden reasoning pass competing
     with `max_tokens` for budget. At 800 tokens this answered Q001
     cleanly but hit `max_tokens` on Q091 with **zero visible content at
     all** (`finish_reason="length"`) — which crashed `generate_answer`
     with an opaque `TypeError: expected string or bytes-like object, got
     'NoneType'` deep inside `extract_cited_source_ids`'s citation regex,
     nowhere near the actual live-provider cause. **Fix**: `client(prompt)`
     in `make_openrouter_client` now checks for blank/`None` content and
     raises a clear `RuntimeError` naming the model and the provider's
     `finish_reason`, right at the boundary where the live response comes
     back — covered by a new deterministic test,
     `test_make_openrouter_client_raises_a_clear_error_on_blank_provider_content`,
     which fakes the `openai` SDK's response shape rather than hitting the
     network.
   - **1600 tokens, new model:** Q001 stayed clean; Q091 finally produced
     a real, coherent, correctly-cited answer — just cut off mid-sentence
     before finishing its last section, a plain "budget was a bit too
     small" truncation rather than any of the earlier failure modes.
   - **2400 tokens, new model:** both queries came back clean, complete,
     fully cited, zero orphans — see "Demo output" above for the actual
     transcript this run produced. `MAX_ANSWER_TOKENS = 2400` was what was
     committed as of this write-up (2026-09-14).

   **Update, same day, later commit:** `MAX_ANSWER_TOKENS` was subsequently
   raised to `3000` (`fix: increase MAX_ANSWER_TOKENS to improve answer
   completeness`) without this section being revised to match — the
   sentence above is left as it was written, as an honest record of what
   was true at the time, rather than silently rewritten. **The current
   value is `3000`**, confirmed against `src/generation.py`'s
   `MAX_ANSWER_TOKENS`. See "Day 11: Grounded-answer evaluation +
   completeness checks" below for what this means for the
   `generation_eval.py` fixtures, which intentionally freeze this exact
   2400-token transcript rather than the current live output.

   The honest takeaway is not "2400 is now guaranteed forever" — it is
   that a free-tier hosted model's behavior at a given token budget is an
   empirical fact about that specific model on that specific day, not
   something that can be reasoned out from documentation alone. That is
   exactly why this module keeps live calls out of the deterministic
   `pytest` gate in the first place (see "What is tested deterministically
   vs. smoke-tested live" below) and why this whole debugging trail is
   recorded here rather than smoothed over.
2. **The lint gate was claimed but not actually available.** This addendum
   said "Compile/lint gates: ... clean, no output" without mentioning that
   `ruff` was never installed — the same gap Day 9 explicitly recorded
   (`No module named ruff`, see `docs/learning-log.md`), but this time left
   unstated instead of called out. **Fix**: added `ruff` to
   `[dependency-groups] dev` in `pyproject.toml` and ran `uv sync` so it is
   actually installed in `.venv`. Ruff ships hundreds of optional rule
   plugins; running it with zero configuration against the *whole*
   pre-Day-10 codebase surfaced 12 findings in files Day 10 never touched
   (import-sort opinions in `eval_metrics.py`/`hybrid_search.py`,
   implicit-string-concatenation warnings in `tests/test_chunking.py` and
   `tests/test_reranking.py`) — fixing all of that would be scope creep
   well past what Day 10 is about. Instead, `pyproject.toml` now pins
   `[tool.ruff.lint] select = ["E4", "E7", "E9", "F"]` — pycodestyle error
   classes plus pyflakes, ruff's own conventional minimal "default" rule
   set (real correctness issues: syntax errors, unused/undefined names —
   not style opinions). `./.venv/bin/python -m ruff check src tests`, the
   exact command the reviewer ran, now passes: `All checks passed!`.
3. **The optional-live-client import boundary was slightly leaky.**
   `make_openrouter_client` imported `from openai import OpenAI` *before*
   checking whether `OPENROUTER_API_KEY` was set. In a correctly-synced
   `.venv` this made no observable difference (the import always succeeds),
   but it meant the "fake-client tests don't need live-client dependencies"
   boundary held only by coincidence, not by construction — a stale or
   partial environment missing `openai` would fail the no-key guard test
   with `ModuleNotFoundError` instead of the intended `RuntimeError`. Since
   this is a learning repo, a boundary that happens to work rather than one
   that is structurally guaranteed is exactly the kind of gap worth
   correcting. **Fix**: the `openai` import now happens after the API-key
   `RuntimeError` check, inside the same function — no observable behavior
   change with a key present, but a caller with no key now never needs
   `openai` importable at all.

Non-blocking cleanup applied at the same time: `pyproject.toml` now depends
directly on `python-dotenv>=1.2.3` instead of the `dotenv` wrapper package
(`dotenv` is a thin package that itself just depends on `python-dotenv`;
depending on `python-dotenv` directly removes that indirection). The code's
`from dotenv import load_dotenv` import is unchanged — both packages expose
the same `dotenv` module name.

Gate re-run after all fixes (including the new blank-content regression
test from item 1 above, 134 → 135):

```
./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/pytest -q
# 135 passed in 0.59s

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

### What is tested deterministically vs. smoke-tested live

- **Deterministic (`tests/test_generation.py`, part of the standard
  `pytest` gate, no network)**: source numbering and field mapping, prompt
  contains every source id and the question, citation extraction/
  deduplication, orphan- and uncited-citation detection, the empty-context
  refusal short-circuit (asserted by a client that raises if called), a
  fake client's text passing through unchanged, a multi-source answer
  validating all its citations, and `make_openrouter_client` raising
  immediately (before any network call) when no API key is available.
- **Live smoke-test only (not part of the pytest gate)**: the actual
  OpenRouter call in `src/generation.py`'s `main()`, demoed above. It only
  runs at all when `OPENROUTER_API_KEY` is present (`python-dotenv`'s
  `load_dotenv()` loads it from `.env`); with no key, `main()` prints the
  retrieved sources and stops, rather than faking an answer. Each call is
  now bounded to `OPENROUTER_TIMEOUT_SECONDS` (60s) and
  `MAX_ANSWER_TOKENS` (currently `3000` — see the update note in
  "Reproducibility hardening" above) and runs at `GENERATION_TEMPERATURE`
  (0.0) — so a smoke run either produces an answer or fails loudly within a
  bounded window, never hangs silently.

### What remains unevaluated

Day 10 adds simple, deterministic *contract* checks (citations present, no
orphan citations, empty context refuses, a prompt actually contains its
sources) — it does not add faithfulness, completeness, or answer-relevance
scoring. Whether an answer is *fully correct*, not just *cited correctly*,
still requires either a human reading it against `expected_answer` (as
done by hand for Q001/Q091 above) or a future LLM-as-judge/RAGAS-style
layer scored against the same rubric discipline Day 9 used for retrieval
grades. That is explicitly next-layer work, not something this addendum
claims to have solved.

## Day 11: Grounded-answer evaluation + completeness checks

Date: 2026-09-15
Implementation: `src/generation_eval.py` — `primary_expected_doc_ids`/
`context_doc_ids` (the two small shared helpers); `check_citation_validity`
(reuses `generation.validate_citations` unchanged — citation hygiene is not
re-derived, only re-shaped into a finding); `check_context_recall` (compares
a query's grade-2/"primary" expected document ids against the doc ids
actually present in the retrieved `sources`, regardless of citation — the
check that catches a retrieval-side evidence gap); `check_expected_terms`
(hand-curated required terms/facts, for curated queries only);
`check_unsupported_inference` (a small hand-curated hedge-phrase scan — a
proxy flag, not a faithfulness proof); `evaluate_generated_answer` (runs all
four and returns one finding list); `make_finding` (the shared finding
dict shape); `CURATED_FIXTURES` (the real Q001/Q091 sources and answer
text Day 10's live run actually produced, hard-coded so no network call or
pipeline load is needed to demonstrate any of this). Tests in
`tests/test_generation_eval.py` — 16 deterministic tests, no network calls.

### Gate re-run before building

```
./.venv/bin/pytest -q
# 135 passed in 2.44s   (before Day 11's tests were added)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

### Why a fourth check layer, on top of Day 10's citations

Day 10 already proved citation hygiene: every `[n]` in a generated answer
either traces to a real retrieved source or is flagged as an orphan. Day
10's own Q091 transcript (see above) came back with **zero orphan
citations** — and it is still, provably, an incomplete answer: it cannot
state the buyer's real approval band (Band 3, €50,000–€250,000) or the
renewal usage-data evidence, because retrieval never put `POL-001` or
`GUIDE-002` in front of the model in the first place. A citation checker
has nothing to say about that, because every citation it *does* see really
is valid. Day 11 exists to make that second, different kind of failure
visible in code — not just in a paragraph of manual analysis, which is how
Day 10's write-up caught it.

### The four checks

1. **`citation_validity`** — unchanged from Day 10, reused not
   re-implemented. Fails on a hallucinated `[n]`.
2. **`context_recall`** — compares the query's *primary* (`relevance_grades
   == 2`, the same "primary" vocabulary `eval_metrics.primary_count` uses
   on the retrieval side) expected document ids against every doc id in
   the retrieved `sources`, independent of what got cited. A missing
   primary document here means no amount of careful generation could have
   produced a complete answer — the failure is at the retrieval boundary,
   not the generation boundary. This is the check that automatically
   catches Q091.
3. **`expected_terms`** — for a small, hand-curated set of queries, asserts
   that specific required facts/terms from the query's real
   `expected_answer` appear in the generated text. Deliberately *not*
   auto-derived from `expected_answer` — see "Known limitations" below for
   why a generic keyword extractor was rejected in favor of a smaller,
   honestly-scoped, hand-picked list.
4. **`unsupported_inference`** — scans the answer text for a short,
   hand-curated list of hedge/extrapolation phrases (`"at minimum"`,
   `"equal or greater"`, ...). A hit is `severity="warn"`, not `"fail"`: it
   flags a pattern worth a human or LLM-as-judge look, it does not itself
   prove a claim is unsupported. It is not a made-up example — the real
   Q091 transcript below contains this exact pattern.

### Demo output (real run, 2026-09-15, `./.venv/bin/python src/generation_eval.py`)

No network call, no API key, no retrieval pipeline load — `CURATED_FIXTURES`
hard-codes the exact retrieved sources and generated-answer text Day 10's
live run already produced for Q001 and Q091 (see "Demo output" above), so
this only re-checks output that already exists:

```
Q001 (threshold): What approval is required for a EUR 60,000 purchase order?
  [PASS] citation_validity: every [n] citation traces to a real retrieved source
  [PASS] context_recall: every primary (grade-2) expected document reached the retrieved context
  [PASS] unsupported_inference: no inference-marker phrasing detected
  [PASS] expected_terms: answer text contains every curated required term/fact

Q091 (multi_doc): What approvals and security evidence do I need for a EUR 120,000 SaaS renewal?
  [PASS] citation_validity: every [n] citation traces to a real retrieved source
  [FAIL] context_recall: primary document(s) ['GUIDE-002', 'POL-001'] were never retrieved - the retrieval step, not the generation step, is why the answer can't fully cover this query, regardless of how well it cites what it *did* receive
         expected: ['GUIDE-002', 'POL-001', 'POL-003']
         actual:   ['FAQ-001', 'POL-003', 'SOP-001']
  [WARN] unsupported_inference: answer contains inference-marker phrasing ['at minimum', 'equal or greater'] - a claim may extrapolate past what its cited source actually states; this is a flag for human/LLM-as-judge review, not a proven faithfulness violation
         expected: no hedged extrapolation beyond cited source text
         actual:   ['at minimum', 'equal or greater']
  [FAIL] expected_terms: answer text is missing required term(s)/fact(s): ['Band 3', 'usage data']
         expected: ['Band 3', 'usage data']
         actual:   []
```

**Reading this output is the actual Day 11 deliverable.** Q001 passes
every check — clean citations, its one primary document (`POL-001`) is in
context, its real required facts ("VP Procurement", "Finance review")
appear in the answer, and no hedge-phrase pattern. Q091 shows exactly the
three-way split the whole day exists to make visible: citation validity
passes (the answer is honest about what it *did* see), `context_recall`
fails and names precisely which primary documents were missing
(`GUIDE-002`, `POL-001`), `expected_terms` fails as the direct
downstream consequence (the answer never says "Band 3" or references
usage data, because the documents that would justify saying them were
never retrieved), and `unsupported_inference` flags the specific sentence
where the model reasoned past its evidence ("a €120,000 commitment is of
equal or greater significance, so this approval level applies at
minimum") instead of following the prompt's own rule to say "not enough
information" instead of guessing. Four different verdicts from one
answer, each backed by a concrete reason — not one collapsed score.

### A note on fixture freshness: these fixtures are historical Day 10 evidence, not live output

`CURATED_FIXTURES` in `src/generation_eval.py` hard-codes the exact
sources and answer text Day 10's live run produced on 2026-09-14, when
`MAX_ANSWER_TOKENS` was `2400` (see the "Reproducibility hardening"
update note above). `MAX_ANSWER_TOKENS` is `3000` now, and re-running `src/generation.py`'s
live demo today does **not** reproduce the Q001/Q091 transcripts above
byte-for-byte — Juan confirmed this directly by re-running the live demo:
a fresh call against the current 3000-token config produces different
wording for Q091 than the fixture below quotes.

This is a deliberate choice, not an oversight, but it is worth being
precise about what it does and does not cost:

- **What stays valid regardless of model/token drift**: `check_context_recall`
  depends only on `Q091_SOURCES`'s `doc_id`s and Q091's real
  `relevance_grades` — both fixed facts about what Day 10's retrieval step
  actually returned and what the corpus actually says is primary evidence,
  independent of any model, prompt, or token budget. `POL-001` and
  `GUIDE-002` were genuinely absent from that retrieval call's top-5; that
  fact does not change if the generation step is re-run with a bigger
  token budget. This is *why* Day 11 leans on `context_recall`, not
  `expected_terms`, as the check that "automatically catches Q091" — it is
  the one immune to this exact kind of drift.
- **What is tied to the frozen transcript specifically**: `check_expected_terms`
  and `check_unsupported_inference` both read `answer_text` directly, so
  their exact findings (which terms are missing, which hedge phrase is
  flagged) describe *this specific, frozen* 2400-token transcript. A fresh
  3000-token run might phrase its hedge past `POL-001`'s missing threshold
  differently, or not at all — that would not mean the underlying
  retrieval gap was fixed, only that the symptom looked different on this
  specific answer's wording.
- **Why freezing the fixture is still the right call for today's scope**
  (matching the Day 11 design doc's "deterministic fixtures before
  LLM-as-judge" principle): a curated fixture's job is to be a fixed,
  known input a check's logic can be regression-tested against — the same
  reason `tests/test_generation.py` uses synthetic fixed chunk text rather
  than re-running retrieval. Re-generating the fixture from a fresh live
  call every time the model config changes would make `tests/test_generation_eval.py`
  non-deterministic and network-dependent, defeating the entire point of
  this being a `pytest`-gate-safe, no-API-key eval layer. The known next
  step, if this project wants the fixture to track current model behavior,
  is to capture a new live transcript under `MAX_ANSWER_TOKENS = 3000` and
  either replace `CURATED_FIXTURES` or add it as a second, clearly-labeled
  fixture alongside the historical one — not something this addendum
  claims to have done.

### What is deterministic today vs. what still needs human/LLM-as-judge review

- **Deterministic and trustworthy as far as it goes**: `citation_validity`
  and `context_recall` are both exact-match checks over ids — a document
  id is either in `sources` or it isn't, a citation number either maps to
  a real source or it doesn't. No judgment call, no threshold to tune.
- **Deterministic, but honestly narrow**: `expected_terms` is a
  case-insensitive substring match against a hand-curated list. It is
  precise (in the sense that it cannot be fooled by paraphrase-nearness
  scoring going wrong) but literal — a correct answer that states the same
  fact in different words fails it, and it only exists at all for the
  queries someone actually curated a term list for (two, today). Building
  a generic version of this (derive required terms from `expected_answer`
  automatically for all 93 queries) was deliberately rejected: it would
  either need real NLP (fact/claim extraction) or a keyword heuristic
  loose enough to silently mis-grade queries nobody checked by hand — the
  exact "broad fake metric that cannot explain itself" the Day 11 design
  doc warns against.
- **A proxy, not a proof**: `unsupported_inference`'s hedge-phrase list is
  the shallowest check here, and it says so in its own `severity="warn"`
  rather than `"fail"`. It can only ever flag phrasing patterns, never
  confirm or rule out that a specific claim is actually unsupported by its
  cited source — that is exactly the kind of judgment call an
  LLM-as-judge pass (DeepEval's faithfulness metric, or RAGAS's, both
  named in `docs/day-11-grounded-answer-evaluation.md`) is built for, and
  this project has not adopted either yet.
- **A named, real gap in `expected_terms`'s matching**: the real Q091
  transcript already contains the substring `"12 months"` — twice — for a
  reason that has *nothing* to do with the renewal-timing evidence
  `GUIDE-002` would have provided (it is POL-003's risk-acceptance-window
  clause instead). `Q091_REQUIRED_TERMS` uses `"usage data"` specifically
  to avoid this collision — a plain substring check cannot tell *which*
  sense of a phrase it is matching, so a required term has to be chosen
  carefully, by a human who has read the actual text, not picked
  mechanically from `expected_answer`. This is recorded here rather than
  smoothed over because it is a genuine limitation of check 3's method,
  not just of this one fixture.
- **A named, real gap in `context_recall`**: a query with zero grade-2
  documents in `relevance_grades` passes this check vacuously (there is
  nothing to check), which is a different thing from "checked and
  confirmed complete." `check_context_recall`'s docstring says this
  explicitly rather than letting a vacuous pass read the same as a real
  one.

### Mapping to DeepEval/RAGAS vocabulary (concepts reused, no framework adopted)

- `context_recall` here is the deterministic, id-level ancestor of
  DeepEval's *contextual recall* / RAGAS's *context recall* — both ask "did
  retrieval bring back what a correct answer needs", scored here as exact
  set membership over curated `relevance_grades` rather than an
  LLM-judged score.
- `citation_validity` plus `unsupported_inference` together are a narrow,
  deterministic slice of *faithfulness* (DeepEval) / *faithfulness*
  (RAGAS) — "does the answer's language stay inside its evidence" — with
  citation validity proving the *traceability* half exactly, and the
  hedge-phrase scan only ever approximating the *support* half.
  Answer-relevancy scoring (is the answer actually about the question
  asked) is not attempted at all today.
- `expected_terms` is this project's hand-curated, substring-level stand-in
  for *factual correctness* (RAGAS) / a curated-query slice of *answer
  relevancy* (DeepEval) — checking specific required facts rather than a
  general semantic-similarity score against `expected_answer`.

## Day 12: DeepEval/RAGAS faithfulness harness

Date: 2026-09-15
Implementation: `src/framework_eval.py` — `build_framework_eval_case` (the
framework-neutral eval case: ProcureRAG's own `query_id`/`input`/
`actual_output`/`expected_output`/`retrieval_context`/`source_metadata`/
`deterministic_findings` vocabulary, built from a query row + `sources` +
`answer_text`, independent of any framework); `deepeval_status`/
`ragas_status` (the dependency/API-key boundary, returned as a plain
`(status, reason)` pair, never a raised `ModuleNotFoundError`);
`to_deepeval_test_case`/`to_ragas_sample` (reshape the neutral case into
each framework's own vocabulary); `run_deepeval_faithfulness`/
`run_ragas_faithfulness` (`live=False` by default — skip immediately, no
import, no network; `live=True` runs the real judge call, through
`FaithfulnessMetric`/`Faithfulness` respectively); `make_eval_result` (the
shared result-dict shape). Tests in `tests/test_framework_eval.py` — 16
deterministic tests, no network calls (verified: see "Gate re-run" below).

### Gate re-run before building

```
./.venv/bin/pytest -q
# 151 passed in 1.84s   (Day 12 kickoff baseline, before this day's work)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

### Fixing the environment before writing any adapter code

Both `deepeval` and `ragas` were already `pyproject.toml` dependencies
before today (added in a prior session), but neither was actually in a
working state — this section documents the real, reproducible blockers
found and how each was fixed, per today's instruction not to fake a live
score and not to skip past a broken environment silently.

1. **DeepEval's configured judge model was a typo.**
   `.deepeval/.deepeval` (written by an earlier `deepeval set-openrouter`
   run) recorded `"OPENROUTER_MODEL_NAME": "openai/gpt-4.o-mini"` — note the
   literal `.` between `gpt-4` and `o-mini`. Checked directly against
   OpenRouter's live model list
   (`GET https://openrouter.ai/api/v1/models`): `openai/gpt-4.o-mini` does
   not exist; the real slug is `openai/gpt-4o-mini`. This would have failed
   every live DeepEval call with a "model not found" error, silently, the
   first time `--live` was ever used. Fixed by re-running the CLI, which is
   also how `deepeval diagnose` confirmed it stuck:

   ```
   ./.venv/bin/deepeval set-openrouter --model="openai/gpt-4o-mini" --temperature=0.0
   # 🙌 Congratulations! You're now using OpenRouter `openai/gpt-4o-mini` for all evals that require an LLM.
   ```

2. **RAGAS did not import at all.** `import ragas` raised
   `ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'`.
   Root cause: `ragas==0.3.1`'s `ragas/llms/base.py` does an unconditional,
   top-level `from langchain_community.chat_models.vertexai import
   ChatVertexAI`. `langchain-community`'s `Requires-Dist` in `ragas`'s own
   metadata has no upper-bound pin, so `uv` resolved the newest
   `langchain-community` (`0.4.2`, released 2026-05-22) — which no longer
   ships a `chat_models/vertexai.py` submodule at all (confirmed by
   inspecting `langchain_community-0.4.2`'s installed files directly; the
   last version that still has it is `0.3.31`, confirmed by downloading that
   wheel from PyPI and listing its contents). This is a real upstream
   packaging bug in `ragas==0.3.1` (an unbounded dependency on a package
   that later removed a module it imports unconditionally), **not** a
   Python-version problem — `ragas`'s own metadata declares
   `Requires-Python: >=3.9`, and this project's Python 3.11.7 satisfies it
   with room to spare. (The earlier note in the Day 12 route doc about
   needing Python 3.12 for something called `rag_eval` does not correspond
   to anything in this repo's dependency graph — no such package name
   appears anywhere in `uv.lock`, and nothing `ragas` actually depends on
   requires 3.12.) Fixed by pinning `langchain-community` below the
   breaking major version:

   ```
   uv add "langchain-community<0.4"
   # - langchain-community==0.4.2
   # + langchain-community==0.3.31
   ```

3. **A second, unrelated `ragas` import error surfaced immediately after
   fix 2**: `ModuleNotFoundError: No module named 'PIL'`. `ragas/prompt/
   multi_modal_prompt.py` does an unconditional `from PIL import Image`, and
   that module is reached through `ragas`'s own top-level import chain
   (`ragas` → `ragas.evaluation` → `ragas.metrics` →
   `ragas.metrics.base` → `ragas.prompt` → `ragas.prompt.multi_modal_prompt`)
   — even though `Pillow` is not declared anywhere in `ragas`'s
   `Requires-Dist` (checked directly in its PyPI metadata: no `Pillow`/`PIL`
   entry at all, not even under an optional extra). A second real, undeclared
   packaging bug. Fixed with `uv add pillow`.

After both fixes, `import ragas` succeeds cleanly and
`./.venv/bin/pytest -q` still passes (167/167, see below) — the two `uv add`
commands only changed `pyproject.toml`/`uv.lock`, nothing in `src`/`tests`
depends on the newly-added `pillow` or the pinned `langchain-community`
directly.

### The adapter contract

`build_framework_eval_case(query_row, sources, answer_text,
deterministic_findings=None)` builds one plain dict in ProcureRAG's own
vocabulary — deliberately not shaped like either framework yet:

| Field | Source |
|---|---|
| `query_id` | `query_row["query_id"]` |
| `input` | `query_row["query"]` |
| `actual_output` | `answer_text`, as-is |
| `expected_output` | `query_row["expected_answer"]` |
| `retrieval_context` | `[source["text"] for source in sources]`, order preserved |
| `source_metadata` | `source_id`/`doc_id`/`chunk_id`/`rank` per source, order preserved |
| `deterministic_findings` | Day 11's `evaluate_generated_answer(...)` output, passed straight through, `[]` if not supplied |

Two small, separate functions reshape that one dict per framework, so the
vocabulary mismatch the Day 12 reading list warns about is visible in code,
not hidden inside one big function:

| ProcureRAG (neutral) | DeepEval `LLMTestCase` | RAGAS `SingleTurnSample` |
|---|---|---|
| `input` | `input` | `user_input` |
| `actual_output` | `actual_output` | `response` |
| `expected_output` | `expected_output` | *(not used by `Faithfulness`)* |
| `retrieval_context` | `retrieval_context` | `retrieved_contexts` |

`deepeval_status()`/`ragas_status()` each return a plain `("available",
None)` / `("blocked", reason)` pair — never raise — checked by importing the
package inside the function body (an `import deepeval`/`import ragas` that
can fail is exactly what `tests/test_framework_eval.py` proves via
`monkeypatch.setitem(sys.modules, "deepeval", None)`, without needing to
actually uninstall either package) and then checking
`OPENROUTER_API_KEY` is set. **`deepeval_status()`/`ragas_status() ==
"available"` means only "the package imports and a key is present" — not
"a live call is guaranteed to work."** Day 12 itself proved that gap is
real: DeepEval's status would have read `"available"` the entire time its
configured model was the `openai/gpt-4.o-mini` typo (see "Fixing the
environment" above) — a correctly-spelled key with a broken model behind
it is invisible to this check. Precise scope, not a silent overclaim: a
`"blocked"` result is trustworthy (the call genuinely cannot proceed), an
`"available"` result only means the two cheap, local preconditions this
function actually checks are met.

`run_deepeval_faithfulness`/`run_ragas_faithfulness` both default to
`live=False`, which returns a `status="skipped"` result *before* importing
anything framework-specific — proven, not just asserted, by
`test_run_deepeval_faithfulness_defaults_to_skipped_without_touching_deepeval`,
which sets `sys.modules["deepeval"] = None` and confirms the function still
returns cleanly. **This guarantee is narrower than "the deterministic test
suite never imports the frameworks."** It is not — several adapter-shape
tests (`test_to_deepeval_test_case_maps_neutral_fields_by_name`,
`test_to_ragas_sample_maps_the_same_fields_under_ragas_vocabulary`)
directly construct a real `LLMTestCase`/`SingleTurnSample`, which requires
`deepeval`/`ragas` to be importable. The precise guarantee is: **the
default runner path (`live=False`) never imports either framework or
touches the network; the deterministic adapter-shape tests do import
DeepEval/RAGAS, but make no live calls.**

### Demo output — first pass (real run, 2026-09-15, abbreviated source snippets)

**Superseded by the code-review fixes below — kept here as the honest
historical record of what motivated them, not as current evidence.** The
`Q001_SOURCES`/`Q091_SOURCES` fixtures used for this run held short,
hand-picked representative quotes rather than the literal full retrieved
chunk text (see `generation_eval.py`'s original comment above
`CURATED_FIXTURES`). See "Code-review fixes" further below for why that
mattered and what changed.

Deterministic path first — proves the adapter/status wiring with zero
network calls:

```
./.venv/bin/pytest -q
# 167 passed in 1.12s   (151 Day-11-and-earlier + 16 new Day 12 tests)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

Live path — `./.venv/bin/python src/framework_eval.py --live`, four real
OpenRouter calls (`openai/gpt-4o-mini`, ~$0.0001 total at OpenRouter's
published per-token pricing for this model):

```
Q001: What approval is required for a EUR 60,000 purchase order?
  [PASS] deepeval/faithfulness: score=0.80 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))
         reason: The score is 0.80 because the actual output incorrectly implies that a €60,000
         purchase requires competition, while the retrieval context clearly states it does not
         trigger a competition requirement due to being below the €250,000 threshold.
  [FAIL] ragas/faithfulness: score=0.43 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))

Q091: What approvals and security evidence do I need for a EUR 120,000 SaaS renewal?
  [PASS] deepeval/faithfulness: score=0.80 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))
         reason: The score is 0.80 because the actual output incorrectly states that only one bid
         is needed for a commitment of EUR 120,000, while the retrieval context specifies that
         three qualified bids are required. Additionally, it fails to mention that records for
         awards above €25,000 must be retained for seven years, which is not limited to Ariba
         Sourcing.
  [PASS] ragas/faithfulness: score=0.55 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))
```

### A noisy-but-harmless DeepEval warning, and what it actually means

The first `--live` runs printed a `UserWarning` on every DeepEval call:
`Structured outputs not supported for model 'openai/gpt-4o-mini'. Falling
back to regular generation with JSON parsing. Error: ... 'required' is
required to be supplied and to be an array including every key in
properties. Missing 'reason'.`

Traced to the exact cause, in DeepEval's own installed source: DeepEval
tries OpenAI's *strict* JSON-schema structured-output mode for every
internal judge sub-call. Its own `FaithfulnessVerdict` schema
(`deepeval/metrics/faithfulness/schema.py`) declares
`reason: Optional[str] = Field(default=None)` — Pydantic correctly puts
`reason` in the schema's `properties` but *not* in `required`, since it's
optional. OpenAI's strict mode requires every property to also be listed as
required; DeepEval's `_schema_response_format`
(`deepeval/models/llms/gateway_model.py:391-412`) never patches the schema
to satisfy that, so the provider (OpenRouter, proxying `openai/gpt-4o-mini`
to Azure/OpenAI) rejects the request with exactly this 400 every time. This
is a real, confirmed bug in `deepeval==4.2.3` — checked directly against
PyPI, still the latest release, so it is not fixed by upgrading. It is not
caused by this project's model/key configuration or by OpenRouter.

It is also **harmless**: `gateway_model.py`'s own `except Exception:` block
catches this and falls back to plain (non-schema-constrained) JSON parsing,
which succeeds and is where every real score/reason in this doc actually
came from — the warning only says "the fast path failed, here is the
slow-but-working path," not "this run is broken." `run_deepeval_faithfulness`
in `src/framework_eval.py` now suppresses this one, narrowly-matched warning
message around the `metric.measure(...)` call (not warnings in general),
with a comment pointing at the exact upstream lines above.

### Live scores are not fully reproducible even at temperature=0.0

Three independent `--live` runs of the exact same Q001/Q091 fixtures, same
day, same model, produced different DeepEval scores and reason text each
time — RAGAS was steadier, but not perfectly so:

| Run | DeepEval Q001 | DeepEval Q091 | RAGAS Q001 | RAGAS Q091 |
|---|---|---|---|---|
| 1 (this doc's main demo output, above) | 0.80 | 0.80 | 0.43 | 0.55 |
| 2 (Juan's own run) | 0.80 | 0.92 | 0.43 | 0.64 |
| 3 (after the warning fix, above) | 1.00 | 0.80 | 0.43 | 0.55 |

DeepEval's Q001 reason text changed materially each time it ran (run 1 and
2 both invented a confused, backwards critique of the
€25,000–€250,000 three-qualified-bids rule — in *different* wrong ways each
time; run 3 instead returned "no contradictions present" and scored 1.00).
RAGAS's Q001 score was identical (0.43) across all three runs; its Q091
score matched on two of three (0.55, 0.64, 0.55).

Two things worth taking from this, not one: first, the same class of
judge-reasoning error (confusion about the three-bid competition threshold)
showed up independently in two of three DeepEval runs — this is not a
one-off fluke, it is a real, recurring failure mode for this judge model on
this specific rule. Second, `temperature=0.0` (set for both frameworks —
see `JUDGE_MODEL`'s usage in `run_ragas_faithfulness` and
`GENERATION_TEMPERATURE` in `generation.py` for the same caveat on the
answer-generation side) reduces but does not eliminate run-to-run variance
on a hosted third-party API — a single live score, from either framework,
is a sample, not a fixed ground truth. RAGAS's steadier scores here are
based on only three runs and should not be read as a general "RAGAS is more
reproducible than DeepEval" claim without a larger sample.

### Code-review fixes (same day, after the first pass above)

A review of the first pass raised four points, addressed in order of
severity:

1. **Important — the fixtures' abbreviated source text weakened the
   faithfulness evidence.** `Q001_SOURCES`/`Q091_SOURCES` held short,
   hand-picked *representative* quotes (`generation_eval.py`'s own original
   comment said so explicitly), not the literal chunk text Day 10's model
   actually saw. That was fine for Day 11's deterministic checks (they only
   read `doc_id`/citation ids/`answer_text`, never `sources[].text`), but a
   faithfulness judge scores the answer *against* `retrieval_context` —
   abbreviated context meant DeepEval/RAGAS were never evaluating the real
   prompt evidence, which made every faithfulness score and every "Q091 is
   faithful because..." claim above weaker than presented. **Fixed** by
   re-running the actual retrieval pipeline (`chunk_corpus` →
   `build_chunk_lexical_index`/`build_chunk_semantic_index` →
   `two_stage_rerank`, no LLM involved, fully deterministic) for Q001/Q091
   and confirming the retrieved `doc_id` order still matches Day 10's
   original transcript exactly for both queries — proof the swap is a
   faithful *replacement*, not a different, unverified retrieval run.
   `Q001_SOURCES`/`Q091_SOURCES` in `src/generation_eval.py` now carry the
   full chunk text and the real `chunk_id`. One side benefit surfaced by
   this: the old abbreviated quote for source `[2]`/`[3]` in each fixture
   ("A purchase cannot be split into smaller orders...") does not actually
   appear anywhere in the real chunk text for that position — a mild
   inaccuracy in the original hand-picked placeholder, corrected as a side
   effect of this fix.
2. **Medium — the RAGAS judge call had no timeout or output cap.** Day 10
   already learned, live, that an unbounded OpenRouter call can hang or
   truncate silently. DeepEval's `FaithfulnessMetric` manages its own
   OpenRouter client internally (no per-call knob exposed here), but
   `run_ragas_faithfulness` builds its `ChatOpenAI` object by hand — so it
   now reuses `generation.OPENROUTER_TIMEOUT_SECONDS` (the same 60s bound)
   and a new `JUDGE_MAX_TOKENS`. That constant needed a real trial, same as
   Day 10's `MAX_ANSWER_TOKENS`: a first guess of 1024 worked for Q001 but
   RAGAS's `Faithfulness` failed outright on Q091
   (`status="error"`, `"The LLM generation was not completed. Please
   increase the max_tokens and try again."`) — Q091 is both the longer
   answer and the query with five full-length chunks after fix 1, so its
   internal claims-then-verdicts generation needed more room. Raised to
   4096, confirmed both queries complete. (Genuinely useful side effect: this
   was the first live exercise of `run_ragas_faithfulness`'s
   `status="error"` path, previously only proven not to interfere with the
   deterministic `live=False` tests — see "Caveats" below.)
3. **Medium — `langchain-openai` was a direct import but only a transitive
   dependency.** `src/framework_eval.py` does `from langchain_openai import
   ChatOpenAI` directly, but `pyproject.toml` only had it pulled in via
   `ragas`. Given this session already hit two separate real `ragas`
   packaging/import bugs (see "Fixing the environment" above), an
   undeclared direct import is exactly the kind of thing that breaks
   silently on a future `ragas` version bump. **Fixed**: `uv add
   langchain-openai` — same resolved version, now declared directly.
4. **Medium/Low — imprecise wording about what the deterministic test suite
   touches.** The docs and code comments said the deterministic suite
   "never reaches deepeval/ragas" — true for the default `live=False`
   runner path, but not for the adapter-shape tests
   (`test_to_deepeval_test_case_maps_neutral_fields_by_name`,
   `test_to_ragas_sample_maps_the_same_fields_under_ragas_vocabulary`),
   which do construct real `LLMTestCase`/`SingleTurnSample` objects (both
   real dependencies) — they just never touch the network. Corrected
   throughout `src/framework_eval.py`'s docstrings and above: **the default
   runner path (`live=False`) never imports either framework or touches the
   network; the deterministic adapter-shape tests do import DeepEval/RAGAS,
   but make no live calls.**
5. **Low — `deepeval_status()`/`ragas_status() == "available"` is
   import/key readiness, not full model readiness.** Documented explicitly
   in both functions' docstrings now: `"available"` means the package
   imports and `OPENROUTER_API_KEY` is set — nothing more. Day 12's own
   model-name typo (point 1 under "Fixing the environment") is the concrete
   proof this gap is real: `deepeval_status()` would have read
   `"available"` the entire time that typo was live, because a broken model
   string isn't visible to an import check or a key-presence check.

### Demo output — current (real run, 2026-09-15, after all fixes above)

```
Q001: What approval is required for a EUR 60,000 purchase order?
  [PASS] deepeval/faithfulness: score=0.80 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))
         reason: The score is 0.80 because the actual output incorrectly implies that a €60,000
         purchase requires three qualified bids, while the retrieval context states it only
         requires VP Procurement approval and a Finance review.
  [PASS] ragas/faithfulness: score=0.64 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))

Q091: What approvals and security evidence do I need for a EUR 120,000 SaaS renewal?
  [PASS] deepeval/faithfulness: score=1.00 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))
         reason: The score is 1.00 because there are no contradictions present, indicating that
         the actual output aligns perfectly with the retrieval context.
  [PASS] ragas/faithfulness: score=1.00 (threshold=0.5, judge_model=openai/gpt-4o-mini (OpenRouter))
```

Full-context table, extending the reproducibility table above with the two
runs that used the corrected fixtures:

| Run | Context | DeepEval Q001 | DeepEval Q091 | RAGAS Q001 | RAGAS Q091 |
|---|---|---|---|---|---|
| 4 | full chunk text, `JUDGE_MAX_TOKENS=1024` | 0.80 | 0.80 | 0.57 | **error** (max_tokens too small) |
| 5 (above) | full chunk text, `JUDGE_MAX_TOKENS=4096` | 0.80 | 1.00 | 0.64 | 1.00 |

RAGAS's Q001 score moved out of its previously rock-steady 0.43 (identical
across three abbreviated-context runs) to 0.57–0.64 once given the real
chunk text — a real, evidence-driven change, not noise, and a direct
confirmation that the abbreviated snippets were not just "less complete"
but were measurably distorting the score. Q091 now scores a clean 1.00 on
both frameworks with the fuller context — both the answer's claims and the
context they draw on are now genuinely visible to the judge, and there is
nothing left in-context for either judge to flag as unsupported.

One finding survived the fix, which matters as much as the ones that
didn't: DeepEval's Q001 reason (run 5, above) still incorrectly says the
answer "incorrectly implies that a €60,000 purchase requires three
qualified bids" — the same confused reading of the €25,000–€250,000
three-bid rule seen in three of five total live runs now (1, 2, and 5),
worded differently each time. Giving the judge better evidence fixed
RAGAS's numeric divergence; it did not fix this specific, recurring
DeepEval reasoning error. That distinction — "more context helps some
failure modes and not others" — is a more honest and more useful finding
than either "the fix solved everything" or "the fix didn't matter."

### A live judge's reasoning can be wrong — a real example, not a hypothetical

This is the original example from Run 1 (the first-pass, abbreviated-context
demo output above) — kept in full because the same underlying error recurred,
worded differently, in the current corrected-fixture output too (see "Code-review
fixes" above): DeepEval's Q001 reason claims the retrieval context "clearly states it does
not trigger a competition requirement due to being below the €250,000
threshold." That is backwards. Source `[1]`/`[2]`'s real text (see
`Q001_SOURCES` in `src/generation_eval.py`) says three qualified bids are
required **above €25,000 and up to €250,000** — €60,000 is inside that
range, so competition *does* apply, and the real Q001 answer text says
exactly that (`"a €60,000 purchase also triggers a competition
requirement — three qualified bids are required above €25,000..."`,
correctly cited `[1][2]`). The judge model still returned a plausible,
confidently-worded reason for a sub-1.0 score — it just got the direction of
its own cited evidence wrong.

This is precisely the Day 12 mindset the design doc asks for: **a framework
metric is not automatically a better ground truth.** A score and a reason
string are still an LLM's output, not a fact — Q001's role as a
"known-clean" calibration anchor is what makes an error like this
*catchable at all*: without already knowing Q001's transcript is fully
supported by its cited sources, this reason would have read as a plausible
critique instead of a judge mistake. Neither framework's score should be
taken as a gate without a human spot-check against a case whose real answer
is already known.

### What Q001/Q091 calibration actually showed

(Numbers below are from Run 5, the current authoritative run with the
corrected full-chunk-text fixtures — see "Code-review fixes" above. The
finding is unchanged from the first-pass run, and is if anything more
pronounced now.)

- **Neither framework cleanly separated Q001 (known-clean) from Q091
  (known-incomplete) the way Day 11's deterministic checks do — if anything,
  both frameworks rated the *incomplete* answer as more faithful.** DeepEval
  scored Q001 0.80 vs. Q091 1.00; RAGAS scored Q001 0.64 vs. Q091 1.00. If
  the goal were "does faithfulness alone catch Q091's missing-evidence
  problem", the answer is no — and that is expected, not a bug: faithfulness
  asks "is the answer honest about the sources it saw," not "did it see
  enough." Q091's real answer never invents anything beyond its five
  sources; it is faithful *and* incomplete, which is exactly the distinction
  Day 11's `check_context_recall` (which does fail on Q091, cleanly, for
  `POL-001`/`GUIDE-002`) exists to catch and faithfulness structurally
  cannot.
- **DeepEval's sub-1.0 Q001 score is itself informative, but not for the
  reason DeepEval gave.** A well-calibrated human reading both the real
  Q001 transcript and DeepEval's stated reason can tell the judge's
  arithmetic-direction is wrong (see above) — which is a different, and
  arguably more useful, Day 12 finding than "the harness works": it shows
  *why* a judge score needs a reason attached, and why that reason still
  needs a human who already knows the ground truth to check it.
- **RAGAS gives no reason at all** — `Faithfulness.single_turn_score(...)`
  returns a bare float, full stop. Without DeepEval's `reason` string next
  to it, RAGAS's below-1.0 score on the known-clean Q001 fixture (0.43 on
  the abbreviated-context fixture, 0.64 on the current corrected one — see
  "Code-review fixes" above) would have been much harder to investigate or
  trust either way, in either version. This is a real, structural capability
  gap between the two frameworks' public APIs, not an oversight in
  `run_ragas_faithfulness`.

### What is deterministic today vs. what needs a live judge (and a human)

| Layer | Example | Network/API key? | Trustworthy as a sole gate? |
|---|---|---|---|
| Day 11 deterministic checks | `check_context_recall`, `check_citation_validity` | No | Yes, within their narrow, named scope |
| DeepEval/RAGAS faithfulness (`live=False`) | adapter shape, `status="skipped"`/`"blocked"` | No | N/A — no score produced |
| DeepEval/RAGAS faithfulness (`live=True`) | the scores/reason above | Yes | **No** — see the reasoning-error example above; useful as a second opinion, not a gate |

### Caveats

- Only one metric (faithfulness) was run live today, through both
  frameworks, exactly as the design doc recommends ("pick one first live
  metric, not every metric at once"). Answer relevancy, contextual
  precision/recall, and factual correctness are adapter-ready (the neutral
  case already carries `expected_output`/`retrieval_context`) but not
  wired to a metric call.
- `run_deepeval_faithfulness`/`run_ragas_faithfulness` catch any exception
  from the live call itself and degrade to `status="error"` rather than
  crash. This *was* exercised live (Run 4, "Code-review fixes" above):
  `run_ragas_faithfulness` hit a real `max_tokens`-too-small provider error
  on Q091 and returned a clean `status="error"` result instead of crashing
  the sweep, which is exactly the contract this path is for. Only
  DeepEval's error path remains proven solely by the deterministic
  `live=False` tests in `tests/test_framework_eval.py`, not by a live
  failure.
- Both live judge calls used `openai/gpt-4o-mini` via OpenRouter, the same
  model for both frameworks (`JUDGE_MODEL` in `src/framework_eval.py`), so
  the DeepEval-vs-RAGAS score gap above reflects the two frameworks'
  different faithfulness prompts/scoring logic, not two different judge
  models.
- The RAGAS judge call now sets an explicit `timeout` (reusing
  `generation.OPENROUTER_TIMEOUT_SECONDS`) and `max_tokens`
  (`JUDGE_MAX_TOKENS=4096`, `src/framework_eval.py`) — DeepEval's
  `FaithfulnessMetric` does not expose an equivalent per-call knob through
  its public API, so that side of the live-boundary contract is bounded
  only by whatever DeepEval's own internal client defaults to.

## Day 13: Generation error analysis + multi-doc repair plan

Date: 2026-09-19
Implementation: `src/error_analysis.py` (new) — `ROOT_CAUSE_LABELS` (the
six-label failure taxonomy); `build_case_record` (turns one
`(query, sources, answer_text)` triple plus a human-written label/notes/
repair/verification into one Day 13 case record, by reusing Day 11's
`evaluate_generated_answer` unchanged rather than re-implementing any
check); `build_cases` (the five real Day 13 cases: Q001/Q091 reused from
`generation_eval.CURATED_FIXTURES`, plus new Q093/Q016/Q004 fixtures built
from a real retrieval + live generation run today). `src/framework_eval.py`
gained one addition — `run_deepeval_contextual_recall`, DeepEval's
`ContextualRecallMetric` wired with the exact same `live=False`-default/
skip/blocked/ok/error contract as `run_deepeval_faithfulness`. Tests:
`tests/test_error_analysis.py` (new, 8 tests) and two new tests in
`tests/test_framework_eval.py` for the contextual-recall wiring — all
deterministic, zero network calls.

### Gate re-run before building

```
./.venv/bin/pytest -q
# 167 passed in 2.37s   (Day 13 kickoff baseline, before this day's work)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

### Companion reading notes (Block 1)

| Source / metric | What it measures | Required fields | ProcureRAG mapping | Caveat |
|---|---|---|---|---|
| DeepEval `ContextualRecallMetric` | Whether `retrieval_context` contains what `expected_output` needed | `input`, `actual_output`, `expected_output`, `retrieval_context` (confirmed directly from the installed `deepeval==4.2.3` constructor signature: `ContextualRecallMetric(threshold=0.5, model=None, include_reason=True, ...)`) | `query_row["query"]`, generated answer, `query_row["expected_answer"]`, `[source["text"] for source in sources]` — identical adapter fields Day 12's `to_deepeval_test_case` already builds | An LLM judge sentence-matches `expected_output` against context; it is not the same operation as comparing `doc_id` sets, and — as today's live run below shows — can pass a case even when whole primary *documents* are missing, if the sentences it does check happen to be covered elsewhere |
| DeepEval Contextual Precision | Whether relevant chunks in `retrieval_context` are ranked above irrelevant ones | same four fields as contextual recall | ranked `sources[].text` + `expected_answer` | Not run today — it is a ranking-order metric, not a missing-evidence one; the design doc says to use it as contrast, not as a replacement for this project's existing P@1/R@5/MRR@10/nDCG@5 tables (`docs/eval-report.md`, Day 7–9) |
| DeepEval Answer Relevancy | Whether `actual_output` addresses `input` | `input`, `actual_output` only | not run today | Explicitly the wrong tool for Day 13: an answer can be perfectly on-topic and still wrong or incomplete, which is exactly the failure mode this day is about |
| RAGAS Context Recall (LLM-based / non-LLM / ID-based) | Whether retrieved context covers a reference answer's claims | LLM-based: `user_input`/`retrieved_contexts`/`reference`; ID-based: `retrieved_context_ids`/`reference_context_ids` | ID-based variant maps directly onto this project's stable `doc_id`/`chunk_id` fields — closest framework analogue to `generation_eval.check_context_recall` | Not run live today (DeepEval's contextual recall was the one live metric this day added, per the design doc's "pick one first metric" instruction from Day 12); the ID-based variant remains the most promising RAGAS candidate for a future day, since it would compare doc-id sets the same deterministic way `check_context_recall` already does |
| RAGAS Context Precision (reference / `ContextUtilization` / ranking sensitivity) | Mean precision@k of relevant chunks, with or without a reference answer | reference-based needs `reference`; `ContextUtilization` needs only the generated response | not run today | A ranking-quality metric, same caveat as DeepEval's contextual precision above |
| Hamel/Shreya error analysis (`Creating a Dataset` → `Open Coding` → `Axial Coding` → `Iterative Refinement`) | How to find real failure modes before writing more evals | representative traces + human-written open-ended notes, later grouped into a taxonomy | This is the actual method Day 13 follows: `build_cases` in `src/error_analysis.py` is five real traces, each hand-labeled by reading its actual evidence (open coding), grouped under `ROOT_CAUSE_LABELS` (axial coding) | The taxonomy is not "iteratively refined" past this first pass yet — five cases is enough to notice `retrieval_miss` appearing twice for two different reasons (Q091, Q093) and a fifth, different label (`answer_completeness_gap`, Q016) show up, but the design doc's own "iterative refinement" step (keep going until new cases stop revealing new failure modes) genuinely needs more than five cases to claim saturation |

### The failure taxonomy and case-record shape (Block 2)

`ROOT_CAUSE_LABELS` (`src/error_analysis.py`) — seven labels, one per case,
each pointing at a different owner for the fix:

- `retrieval_miss` — a primary *document* never reached the retrieved
  context at all; no generation/prompt change could have fixed it (Q091,
  Q093).
- `context_truncation_or_construction` — evidence was found somewhere
  upstream but cut before it reached the prompt (not exercised by today's
  five cases — named because it is a real, distinct failure mode a future
  case could hit, e.g. a `max_sources` cap dropping a relevant chunk that
  first-stage retrieval *did* surface).
- `chunk_level_retrieval_gap` — the right *document* reached context
  (document-level `check_context_recall` passes), but the specific *chunk*
  of that document carrying the fact `expected_answer` needs was never
  retrieved — a different chunk of the same document was (Q016, below).
  Still a retrieval/context-construction failure, not a generation one:
  the model cannot cite a fact from a chunk it was never shown, even from a
  document it otherwise saw. Added after Q016's real evidence showed
  `answer_completeness_gap` (below) would have mislabeled a retrieval-side
  failure as a generation-side one — see "Q016" below for the full
  correction.
- `citation_source_support_gap` — a citation points at a real source, but
  the specific claim next to it isn't actually supported by that source's
  text (not exercised by today's five cases; distinct from an orphan
  citation, which Day 11's `check_citation_validity` already catches).
- `answer_completeness_gap` — every chunk of every needed document reached
  context (at both the document level and the specific-fact/chunk level —
  see `chunk_level_retrieval_gap` above for the narrower case this label
  excludes), but the answer still omits something the query needed. **Not
  exercised by today's five cases** — Q016 was originally labeled this way
  and was corrected to `chunk_level_retrieval_gap` after closer reading
  showed the missing evidence never reached the model at all (see "Q016"
  below).
- `judge_or_metric_disagreement` — a deterministic finding and a live judge
  score disagree, or the judge's stated reason doesn't hold up (see the
  DeepEval contextual-recall run below — a real, borderline instance of
  this: DeepEval didn't flatly disagree with Day 11, but its pass score
  on Q091 tells a much softer story than Day 11's clean fail).
- `passes_control` — every Day 11 check passes and the answer matches
  `expected_answer` (Q001, Q004).

Each case record (`build_case_record`) carries: `query_id`, `query_type`,
`difficulty`, `question`, `expected_primary_doc_ids` /
`retrieved_doc_ids` / `missing_primary_doc_ids` (all read straight off Day
11's `check_context_recall` finding), `cited_doc_ids` /
`citation_status` (off `check_citation_validity`), one
`human_root_cause_label` (validated against `ROOT_CAUSE_LABELS`, `ValueError`
otherwise — see `test_build_case_record_rejects_an_unrecognized_root_cause_label`),
free-text `notes` / `recommended_repair` / `verification_signal`, and the
full Day 11 `findings` list attached for anyone who wants the underlying
detail. The label, notes, repair, and verification are **human-written**,
not computed — see `src/error_analysis.py`'s module docstring for why
automating the label itself would just be inventing a second, unverified
opinion instead of doing the open-coding step the Hamel/Shreya method
actually asks for.

### The five cases (Block 2/3A)

| Query | Type / difficulty | Expected primary docs | Retrieved primary docs | Context recall | Citation validity | Root cause | Recommended repair |
|---|---|---|---|---|---|---|---|
| Q001 | threshold / easy | POL-001 | POL-001 (+ FAQ-001, secondary) | pass | pass | `passes_control` | none needed |
| Q091 | multi_doc / hard | GUIDE-002, POL-001, POL-003 | POL-003 only | **fail** (missing GUIDE-002, POL-001) | pass | `retrieval_miss` | raise multi_doc top-k / re-check reranked shortlist depth |
| Q093 | multi_doc / hard | CONTRACT-001, CONTRACT-003, GUIDE-003, MEMO-001 | CONTRACT-003, GUIDE-003, MEMO-001 (+ GUIDE-001, secondary) | **fail** (missing CONTRACT-001) | pass | `retrieval_miss` | per-document diversity cap on the chunk shortlist |
| Q016 | multi_doc / hard | GUIDE-001, POL-004 | GUIDE-001, POL-004 (both present at the document level) | pass (document-level) | pass | `chunk_level_retrieval_gap` | retrieve a second chunk per document for multi_doc queries |
| Q004 | lookup / medium | POL-001 | POL-001 | pass | pass | `passes_control` | none needed |

Full per-case sources, real generated-answer text, and the exact
notes/repair/verification-signal reasoning are in `src/error_analysis.py`
(`Q093_SOURCES`/`Q093_ANSWER_TEXT`, `Q016_SOURCES`/`Q016_ANSWER_TEXT`,
`Q004_SOURCES`/`Q004_ANSWER_TEXT`, and `build_cases`'s per-case `notes`
arguments) — not re-typed here to avoid the report and the code drifting
out of sync with each other.

**Exact capture command (Q093/Q016/Q004 sources + answer text), run from
repo root on 2026-09-19** — real deterministic retrieval
(`chunk_corpus` → `build_chunk_lexical_index`/`build_chunk_semantic_index`
→ `two_stage_rerank`, `top_k=5`, fully deterministic, no LLM) followed by
one live OpenRouter call per query through `generation.generate_answer`
with the default model. `PYTHONPATH=src` is required here because these
modules are plain scripts, not an installed package — see
`tests/test_generation_eval.py`'s own `_load_module` docstring for the same
constraint on the test side:

```bash
PYTHONPATH=src ./.venv/bin/python -c "
from dotenv import load_dotenv
load_dotenv()
from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
from chunking import chunk_corpus
from hybrid_search import load_example_queries
from preprocessing import load_data
from reranking import load_cross_encoder, two_stage_rerank
from semantic_search import load_embedding_model
from generation import build_sources, generate_answer, make_openrouter_client

data = load_data()
chunks = chunk_corpus(data)
embedding_model = load_embedding_model()
chunk_lexical_index = build_chunk_lexical_index(chunks)
chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
cross_encoder_model = load_cross_encoder()
queries_by_id = {q['query_id']: q for q in load_example_queries()}
client = make_openrouter_client()

for qid in ['Q093', 'Q016', 'Q004']:
    row = queries_by_id[qid]
    reranked = two_stage_rerank(row['query'], chunk_lexical_index, chunk_semantic_index, embedding_model, cross_encoder_model, top_k=5)
    sources = build_sources(reranked)
    result = generate_answer(row['query'], sources, client)
    print(qid, [s['doc_id'] for s in sources])
    print(result['answer'])
    print(result['citations'])
"
```

Re-running just the retrieval half of this (no `client`/`generate_answer`
call) reproduces the exact same `doc_id` order shown in the table above,
confirming retrieval is deterministic; the live `generate_answer` call can
produce different wording on a different run (see the judge-variance
caveat under "DeepEval contextual recall" below for the same point applied
to a judge call instead of a generation call) — the frozen
`Q093_ANSWER_TEXT`/`Q016_ANSWER_TEXT`/`Q004_ANSWER_TEXT` transcripts in
`src/error_analysis.py` are this specific 2026-09-19 run, not a
guaranteed-reproducible-verbatim output of this command on a later day.

### Q091: the precise root-cause statement the design doc asks for

Q091's root cause is **missing primary evidence, not a bad answer.**
`POL-001` (the source that actually states the Band 3 approval-band
definition) and `GUIDE-002` (the source with the "start 12 months out with
usage data" renewal-timing guidance) never reached the five sources the
reranker handed to the generator. Every claim the model does make is
honestly derived from what it *did* see (`SOP-001`, `FAQ-001`, `POL-003`)
— Day 12's live faithfulness run already scored this 1.00/1.00
(DeepEval/RAGAS) for exactly that reason. The visible symptom
(`"a €120,000 commitment is of equal or greater significance, so this
approval level applies at minimum"` — reasoning from precedent instead of
citing the real rule) is a *downstream consequence* of the missing
evidence, not an independent prompt bug: no amount of prompt tuning can
make a model cite a document it was never shown.

### Q093: a second retrieval miss, and a sharper version of the same risk

Q093's `expected_answer` is explicitly scoped: "it varies by contract" —
Batavia's clause uses a 2% deadband (`CONTRACT-003`), Acme's fuel surcharge
uses 3% (`CONTRACT-001`), and the negotiation guide recommends a 2–3% range
in general (`GUIDE-003`). Only `CONTRACT-001` failed to reach context.
The live-generated answer, quoted in full in `src/error_analysis.py`,
states: *"the deadband that applies to your indexation clauses is
**plus or minus 2%**"* — clean citations, zero orphans, and still wrong for
any buyer whose contract is actually Acme's. This is the sharpest version
of the design doc's "it depends" risk named in Block 2: a retrieval miss on
a query whose correct answer is genuinely scoped per-document does not just
produce an incomplete answer, it can produce a **confidently wrong,
falsely-universal one** — worse than an honest "I don't have enough
evidence," and harder to catch by only skimming the answer, since the
citations attached to the wrong claim are all individually valid.

### Q016: document-level retrieval succeeded, chunk-level retrieval didn't

Q016 is the deliberate contrast to Q091/Q093: document-level
`check_context_recall` **passes** — both `GUIDE-001` and `POL-004` are in
the retrieved context. But `GUIDE-001` (source `[3]`) is never cited, and
the live-generated answer never states the "in logistics, price should not
exceed 40%" category-guidance tier that `expected_answer` names alongside
the 60% policy ceiling and the 30% temperature-controlled-transport figure
— both of which the answer *does* state correctly. The retrieved
`GUIDE-001` chunk in context (`Q016_SOURCES[2]`) only covers evaluation
*dimensions*, not the 40% figure — that sentence lives in a *different*
chunk of the same document that this `top_k=5` pass didn't happen to
surface.

**This is not a generation failure — it is misclassified as one if labeled
`answer_completeness_gap`.** The model never saw the 40%-logistics chunk at
all; it cannot be faulted for "under-using evidence it was given" when that
specific evidence never reached it. The correct label is
`chunk_level_retrieval_gap`: a genuinely different failure from Q091/Q093's
document-level `retrieval_miss`, but still owned by retrieval/context
construction, not generation. The distinction matters for the same reason
the whole taxonomy exists — it tells a reader *where* to spend the next
engineering hour. This is also a real limitation of the deterministic
`check_context_recall` itself, worth naming plainly: it only asks "did this
`doc_id` reach context," never "did the specific chunk with the fact I need
reach context," so "context_recall passed" is not proof the answer had
everything it needed.

### DeepEval contextual recall, live, Q001 + Q091 (Block 3A step 5)

Command — run from repo root; `PYTHONPATH=src` is required for the same
reason as the retrieval/generation capture command above (these modules
are plain scripts, not an installed package, so `generation_eval`,
`hybrid_search`, and `framework_eval` won't resolve without it):

```bash
PYTHONPATH=src ./.venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv()
from generation_eval import CURATED_FIXTURES
from hybrid_search import load_example_queries
from framework_eval import build_framework_eval_case, run_deepeval_contextual_recall
queries_by_id = {r['query_id']: r for r in load_example_queries()}
for fixture in CURATED_FIXTURES:
    q = queries_by_id[fixture['query_id']]
    case = build_framework_eval_case(q, fixture['sources'], fixture['answer_text'])
    print(run_deepeval_contextual_recall(case, live=True))
"
```

(The narrow entry point above is `run_deepeval_contextual_recall` only, for
exactly the Q001/Q091 calibration pair the design doc asks to check first.
`./.venv/bin/python src/framework_eval.py --live` also works from repo
root without `PYTHONPATH` — it's the module's own `if __name__ ==
"__main__"` entry point — but it additionally runs both frameworks'
faithfulness metrics on every fixture, which is more than this specific
check needs.)

**Real output is provider/judge-variable — this was directly reproduced,
not assumed.** Two consecutive re-runs of the exact command above, back to
back, `openai/gpt-4o-mini` via OpenRouter, threshold 0.5:

```
Run 1 — Q001: score=1.00 passed=True
  reason: The score is 1.00 because the expected output perfectly aligns with the information provided
  in node 4 regarding the €60,000 commitment requiring VP Procurement approval and the cumulative
  nature of approvals.
Run 1 — Q091: score=0.50 passed=True
  reason: The score is 0.50 because while the sentence about the €120,000 needing VP Procurement
  approval connects well with node 1 regarding procurement governance, the requirements for ISO 27001
  and the renewal process are not addressed in the retrieval context, leading to a partial alignment.

Run 2 — Q001: score=1.00 passed=True
  reason: The score is 1.00 because the expected output is fully supported by the information in the
  retrieval context, specifically referencing the €60,000 commitment and the approval requirements
  detailed in nodes 3 and 4.
Run 2 — Q091: score=0.80 passed=True
  reason: The score is 0.80 because most of the sentences in the expected output are well-supported by
  the nodes in the retrieval context, particularly the requirements for approvals and certifications.
  However, the specific mention of 'HICP plus 2 percentage points' does not have a corresponding node,
  which slightly lowers the score.
```

A later independent re-run (same command, same fixtures, done in review)
saw Q001 dip to 0.75 while Q091 landed at 0.80–1.00 across two more runs —
both queries showed real score movement, Q001 included, and every single
run of Q091 still passed. **The exact scores above should not be treated as
a stable, reproducible ground truth** — `temperature=0.0` on the judge call
narrows sampling variance but does not eliminate it on a hosted API (see
`generation.py`'s own caveat about this same limitation for the
answer-generation model), and DeepEval's internal claims-then-verdicts
process for this metric gives the judge more surface area for run-to-run
disagreement than a single faithfulness score does.

**Comparison to the deterministic `check_context_recall` — the exact
comparison the design doc requires before trusting a live judge:**

- **Q001**: both checks agree in spirit across every run observed — a clear
  pass, even though the exact score wobbles (0.75–1.00). Deterministic:
  pass (`POL-001` present, unambiguous doc-id set membership, no variance
  possible).
- **Q091**: the two checks tell a **very different story on every single
  run**, and this — not any one exact score — is the headline Day 13
  finding from adding this metric. Day 11's deterministic
  `check_context_recall` fails cleanly and specifically, identically every
  time it runs: `POL-001` and `GUIDE-002` are named as missing. DeepEval's
  contextual recall **passed Q091 in all four runs observed** (0.50, 0.80,
  0.80, 1.00 — every one at or above the 0.5 threshold), while never
  flagging the missing Band-3 approval-band citation or the missing
  12-months-out usage-data renewal guidance as the reason for its
  imperfect score — it flagged narrower gaps instead (an unaddressed ISO
  27001 mention in one run, the "HICP plus 2 percentage points" detail in
  another). **A framework contextual-recall score, even one built for
  exactly this purpose, consistently under-caught what a deterministic
  `doc_id` check catches immediately, precisely, and every time.** This is
  the same lesson Day 12 learned about faithfulness, one layer deeper: a
  better-targeted framework metric is real, visible progress (every
  observed Q091 score here is below faithfulness's 1.00 on the same case),
  but it remains a softer, sentence-level, provider-variable judgment call
  that a human has to check against ground truth on every run — not a
  replacement for the deterministic, doc-id-based gate, which needs no such
  check because it has no such variance.

This case is labeled `judge_or_metric_disagreement` in spirit (see
`ROOT_CAUSE_LABELS` above) even though it is layered on top of Q091's
primary `retrieval_miss` label — the case record only carries one label,
and `retrieval_miss` is the actual root cause; the judge-disagreement is
recorded in Q091's `notes` field instead of a second label, per this
module's one-label-per-case design.

### Recommended Q091 / multi-doc repair path

**Root cause, stated precisely (restated from above):** Q091 fails because
two primary documents (`POL-001`, `GUIDE-002`) never reach the five-source
generation context the reranker builds — not because of prompt wording,
not because of a citation bug, and not because faithfulness or contextual
recall (both run live) reliably catch it, since neither does, cleanly.

**Recommended first repair:** raise `top_k` in
`reranking.two_stage_rerank`/`generation.build_sources` specifically for
`multi_doc`-type queries (e.g. 5 → 8–10), rather than editing the prompt.
This is the cheapest, most targeted next experiment given today's evidence:
Q091's own real transcript shows the model already handles multiple
documents correctly when it has them (Q016's answer correctly separates the
60%/30–50%/30% tiers from three different sources) — the actual bottleneck
observed today is retrieval depth on `multi_doc` queries, not the
generator's ability to synthesize multiple sources.

**A second, complementary repair worth testing alongside it (motivated by
Q093):** add a per-document diversity cap to the chunk shortlist before
reranking — e.g. no more than 2 chunks from the same `doc_id` in the
pre-rerank pool — so a `multi_doc` query whose relevant evidence is spread
across 4–5 different contracts/policies (like Q093) doesn't have its
shortlist filled by several chunks of the same 1–2 documents before a
different, equally relevant document ever gets a chance to compete for a
slot. A flat top-k increase alone does not guarantee this: Q093's `top_k=5`
pool already spent 2 of 5 slots on the same `MEMO-001` document.

**Tradeoffs:**

- A larger `top_k` means a longer prompt (more tokens, higher generation
  cost/latency per Day 10's `MAX_ANSWER_TOKENS` budget) and a slightly
  higher chance of the model encountering conflicting-scope evidence it has
  to actively resolve (the exact prompt rule #2 in `generation.py` already
  exists for) rather than just ignoring quietly.
- A per-document diversity cap can push out a strong, correctly single-doc
  answer's best supporting chunk (e.g. two genuinely useful chunks from the
  same policy for a `threshold`-type query) in favor of a less relevant
  chunk from a different document, purely to satisfy the cap — it needs to
  be scoped to `multi_doc`-type queries, not applied globally.
- Neither repair touches the prompt itself, deliberately: per this design
  doc's "How would you decide whether to fix retrieval or prompt wording?"
  drill answer, the evidence gathered today says the bottleneck is
  retrieval depth/diversity, not the generator's handling of what it's
  given — so prompt-tuning around this would be optimizing the wrong layer.

**Verification signal:** re-run `error_analysis.build_cases` (or just
`generation_eval.check_context_recall`) for Q091 and Q093 after either
change — both must report an empty `missing_primary_doc_ids` list. A
prompt-only change would leave that signal untouched, which is exactly why
it — not a higher faithfulness/contextual-recall score, and not a human
"the answer reads better now" impression — is the right thing to check
before calling either repair successful. A regression check on Q001 and
Q004 (the two `passes_control` cases) after the change is equally
important: both must still pass every Day 11 check, proving the fix didn't
trade a `multi_doc` improvement for a widened, noisier context that
confuses the easy cases.

### Artifact / test evidence

```
./.venv/bin/pytest -q
# 177 passed in 1.11s   (167 baseline + 8 new in tests/test_error_analysis.py + 2 new in
#                         tests/test_framework_eval.py)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

Files created/modified: `src/error_analysis.py` (new), `src/framework_eval.py`
(`run_deepeval_contextual_recall` added, `main()` updated to run it),
`tests/test_error_analysis.py` (new), `tests/test_framework_eval.py`
(two tests added), `docs/eval-report.md` (this section), `docs/learning-log.md`
(Day 13 entry filled in).

### Code-review fixes (same day, after the first pass above)

A review of the first Day 13 pass raised five points, addressed in order of
severity:

1. **Required — Q016 was mislabeled `answer_completeness_gap`.** That
   label's own definition requires all needed evidence to have reached
   context, with generation under-using it — but Q016's own recorded
   evidence already showed the missing "logistics ≤40%" fact was never in
   any retrieved chunk at all. **Fixed** by adding a seventh taxonomy
   label, `chunk_level_retrieval_gap` (document-level recall passes,
   chunk-level/fact-level recall fails), and relabeling Q016 with it
   throughout this section, the case table, and `src/error_analysis.py`.
   This is the correction that matters most for Day 13's stated purpose —
   the original label put a retrieval-owned failure in the generation
   column.
2. **Required — the documented live contextual-recall command was not
   reproducible from repo root.** It imported `generation_eval`/
   `hybrid_search`/`framework_eval` directly with no `src` on
   `PYTHONPATH`, and failed with `ModuleNotFoundError` on an actual
   from-scratch re-run. **Fixed** by prefixing it with `PYTHONPATH=src`
   (see "DeepEval contextual recall" below), and noting
   `./.venv/bin/python src/framework_eval.py --live` as the alternative
   entry point that needs no `PYTHONPATH`.
3. **Required/Medium — the recorded live contextual-recall scores (Q001
   1.00, Q091 0.80) were presented as fixed facts rather than one sample of
   a variable judge call.** Re-running the corrected command twice showed
   real movement (Q091: 0.50, then 0.80); an independent review re-run saw
   Q001 dip to 0.75 and Q091 land at 0.80–1.00. **Fixed** by replacing the
   single "real output" block with multiple actual runs and rewriting the
   comparison-to-deterministic-check conclusion around the defensible
   claim — not an exact score, but that the judge consistently passes Q091
   across a real score range while deterministic recall is invariant.
4. **Medium — the Q093/Q016/Q004 fixture comments claimed an "exact
   command" that did not actually exist anywhere in the repo.** **Fixed**
   by adding the real, actually-run `PYTHONPATH=src` retrieval+generation
   capture command under "The five cases" below, and confirming its
   retrieval half reproduces the exact `doc_id` order in the case table.
5. **Nit — a stale docstring in `to_deepeval_test_case`** still said
   contextual recall was "not built today," true in Day 12 and false after
   this day's `run_deepeval_contextual_recall` addition. **Fixed.**

### Caveats

- Only five cases were inspected, not a larger sample — enough to see two
  distinct flavors of `retrieval_miss` and one `chunk_level_retrieval_gap`
  that document-level `check_context_recall` structurally cannot detect,
  but the Hamel/Shreya "iterative refinement" step (keep sampling until new
  traces stop revealing new failure modes) has not been run to saturation
  yet — a reasonable next-day scope, not a Day 13 gap being hidden.
  `context_truncation_or_construction`, `citation_source_support_gap`, and
  `answer_completeness_gap` are all real, named labels in
  `ROOT_CAUSE_LABELS` that no case today happened to need — notably,
  `answer_completeness_gap` (a genuine generation-owned completeness
  failure) is now an open question rather than an assumed-common failure
  mode, after Q016 turned out not to be an instance of it.
- DeepEval contextual recall was run live for Q001/Q091 only, per the
  design doc's "run it against Q001/Q091 first, not all 93 queries"
  instruction — it was not run for Q093/Q016/Q004, so its
  agrees/disagrees-with-deterministic pattern is confirmed for exactly two
  cases, not generalized further.
- RAGAS context recall (LLM-based, non-LLM, or ID-based) was not wired or
  run this session — DeepEval's contextual recall was the one live metric
  this day added, matching the "pick one first metric" instruction Day 12
  already established as this project's convention.
- Q093/Q016/Q004's retrieved sources and generated answers are each from
  one live run captured on 2026-09-19 (`generation.DEFAULT_OPENROUTER_MODEL`,
  temperature 0.0) — like Day 10's own transcripts, this is a frozen,
  hard-coded fixture from here on (`src/error_analysis.py`), not something
  re-generated on every test run; a different live run on a different day
  could produce different wording (though the underlying retrieval gaps,
  being deterministic BM25 + local embeddings + local reranker, would not
  change unless the pipeline itself changes).

## Known limitations / next steps

- **Done, no longer a gap (Day 9)**: the nine-row table above is still
  unfiltered-only, but a filtered-adjusted baseline now exists as its own,
  clearly labeled section — "Day 9: Graded relevance, filter-adjusted
  evaluation, and error slices" → "Filter-adjusted evaluation". It does
  exactly what this bullet originally asked for: a *filter-adjusted*
  ground truth per query (`filter_adjusted_relevant_ids`/
  `build_filtered_queries`), not the unfiltered `expected_relevant_ids`
  reused as-is, scored against retrieval that actually applies the filter.
  17 of 21 filtered queries do have at least one `expected_relevant_ids`
  entry their own filter would exclude, confirming the concern this bullet
  raised. Isolated apples-to-apples (same filter-adjusted gold on both
  sides — see "Filter-adjusted evaluation" finding 1 above for why raw
  gold can't be the comparison point), filtering retrieval on top of the
  gold-set fix still measurably helps: R@5 0.901 → 0.948 for the reranked
  method, 0.925 → 0.948 for first-stage Hybrid RRF.
- **Done, no longer a gap**: chunk-level hybrid (BM25-over-chunks +
  dense-over-chunks, fused, rolled up to documents) is now in the table
  above as two rows, and — confirming the suspicion this bullet originally
  raised — Hybrid RRF chunk→document is the single best row on every
  metric. The forward-looking implication: Day 8+ reranking should be
  benchmarked against *chunk-level hybrid RRF* (0.935/0.811/0.965) as the
  baseline to beat, not whole-document hybrid — reranking on top of the
  weaker whole-document baseline would understate how much of the
  remaining gap a reranker actually closes.
- **Done, no longer a gap (Day 9)**: `relevance_grades` is now used by
  `ndcg_at_k`/`evaluate_ndcg` — see "Day 9" → "Graded relevance: nDCG@5".
  The binary table above is still binary (kept that way deliberately, for
  comparability with Day 7/8's own numbers), but it is no longer the only
  view: nDCG@5 confirms the same method ranking as P@1 while showing real
  headroom P@1 alone couldn't (e.g. the reranked row's 0.978 P@1 vs. 0.869
  nDCG@5) — evidence that ranking the *primary* document first is a
  measurably harder bar than ranking *any* relevant document first.
- **Done, tested, and more nuanced than assumed**: the RRF-vs-consensus
  finding above (Q014, and the pool-size investigation) was this baseline's
  strongest argument for reranking next. Day 8's "Q014 at chunk level"
  section (below) tested exactly the open question this bullet raised —
  whether the same consensus-over-strength pattern shows up at chunk
  granularity — and found it does not reproduce there: chunk-level
  first-stage fusion already ranks Q014's correct document first, before
  reranking runs at all. Reranking still measurably helped in aggregate
  (P@1 +0.043, MRR@10 +0.019 across all 93 queries), just not by fixing
  *this specific* failure, which turned out to be at least partly a
  retrieval-unit artifact rather than a pure fusion-formula weakness. See
  the Day 8 section for the full account, including the (small, and
  explained) R@5 tradeoff.
- Metadata filtering supports equality-per-field only (plus list-membership
  for `risk_tags`). No OR, no numeric ranges (e.g. `annual_value_eur` over a
  threshold) — not needed to prove the contract against the v1 query set,
  which never asks for more.
