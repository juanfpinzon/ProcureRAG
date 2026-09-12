# Eval Report — v1 Hybrid Consolidation Baseline

Date: 2026-09-11 (Day 7); Day 8 reranking addendum added 2026-09-12
Status: full baseline, 93/93 v1 queries, nine retrieval methods (six
required document-level rows + two chunk-level hybrid rows added as a Day 7
follow-up, plus Day 8's cross-encoder reranked chunk row — see "Day 8:
Cross-encoder reranking" below)

This is Day 7's evidence artifact: it turns Day 6's qualitative "hybrid
looked better on these five queries" demo into a measured baseline across
the whole v1 golden query set, adds metadata filtering, and gives the Day 6
exact-tie weakness a real (if partial) fix plus an honest account of what
that fix does and doesn't solve. A same-day follow-up then closed the
biggest gap the first version of this table itself pointed at: chunk-level
hybrid fusion, which turned out to be the strongest configuration tested.
Day 8 then added a second-stage cross-encoder reranker on top of that
chunk-level hybrid baseline — see the dedicated section below for whether
it helped, and where.

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

## Known limitations / next steps

- **The baseline table is unfiltered text retrieval only — no
  metadata-aware baseline exists yet, and it is not a simple addition.**
  None of `src/eval_metrics.py`'s closures (eight as of Day 7, plus Day 8's
  reranked row — nine total) read `query_row["metadata_filters"]`. Building one needs its own methodology,
  not just applying `filter_ranked_results` inside each closure: as the
  "sharper, related finding" above shows, 17 of 21 filtered queries have at
  least one `expected_relevant_ids` entry their own filter would exclude, so
  a filtered baseline needs a *filter-adjusted* ground truth per query (drop
  the ids the filter itself was always going to exclude before scoring
  recall against what's left) — reusing the unfiltered `expected_relevant_ids`
  as-is would penalize every method for correctly filtering out documents
  the filter was supposed to remove.
- **Done, no longer a gap**: chunk-level hybrid (BM25-over-chunks +
  dense-over-chunks, fused, rolled up to documents) is now in the table
  above as two rows, and — confirming the suspicion this bullet originally
  raised — Hybrid RRF chunk→document is the single best row on every
  metric. The forward-looking implication: Day 8+ reranking should be
  benchmarked against *chunk-level hybrid RRF* (0.935/0.811/0.965) as the
  baseline to beat, not whole-document hybrid — reranking on top of the
  weaker whole-document baseline would understate how much of the
  remaining gap a reranker actually closes.
- Binary relevance only. `relevance_grades` (graded 1/2) is unused; a
  graded metric (nDCG) would score a primary-document hit higher than a
  secondary-document hit, which this baseline currently treats as
  equivalent.
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
