# Day 9 — Evaluation Harness: Graded Relevance, Filtered Evals, and Error Slices

Date: 2026-09-14 target; started 2026-09-14.

Linear: HER-275 — Day 9 loop: Boot.dev Ch9 evaluation + retrieval metrics.

Related gate: HER-267 — Week 2 gate: hybrid search, reranking, retrieval evals.

Project rule: course-driven building, with Juan owning the core evaluation implementation. Hermes may scaffold docs and review; Juan writes the metric/filter/error-analysis code and tests.

## Course target for today

Boot.dev RAG course target:

- **Primary chapter:** Chapter 9 — **Evaluation**.
- **Exact lessons verified from the Boot.dev Chapter 9 lesson menu:**
  1. **Manual Evaluation** — define what a good result means before trusting automated scores.
  2. **Golden Dataset** — curate labeled query/result examples so retrieval changes can be compared fairly.
  3. **Precision Metrics** — measure how much of the retrieved set is relevant.
  4. **Recall Metrics** — measure how much of the relevant set is retrieved.
  5. **F1 Score** — combine precision and recall when one number is useful, while remembering what it hides.
  6. **Error Analysis** — inspect misses by category so the next fix targets a real failure mode.
  7. **LLM Evaluation** — use an LLM judge only after defining criteria and validating it against expert/human expectations.
- **Important discrepancy vs. Linear HER-275 text:** the ticket description mentions MRR/MAP/nDCG as if they are Boot.dev lesson names. The public Boot.dev Chapter 9 menu verified for this route lists the seven lessons above. ProcureRAG should still build beyond the Boot.dev minimum where project evidence demands it — especially nDCG from existing `relevance_grades` — but those are project extensions, not verified Boot.dev lesson titles.

Companion sources:

- **RAGAS docs / RAG triad concepts** — context precision, context recall, faithfulness/groundedness, and answer relevance. Today is retrieval-eval first; generation evals become the main target in Week 3.
- **Hugging Face RAG Evaluation cookbook or similar lightweight RAG-eval reference** — optional conceptual read for nDCG-style retrieval scoring and LLM-as-judge validation patterns.
- **Day 7/8 project evidence** — `docs/eval-report.md`, `docs/corpus-v1.md`, and the current `src/eval_metrics.py` are the real baseline. Do not restart from a toy `data/golden_queries.jsonl` if `data/corpus_v1/example_queries.jsonl` already carries 93 labeled queries.

## Day 9 objective

Turn the current binary retrieval-eval baseline into a more interview-defensible evaluation harness. Day 7/8 already built `src/eval_metrics.py` with P@1, R@5, MRR@10 over the canonical 93-query v1 set, and Day 8 added the reranked row. Day 9 should **not duplicate that work in a new parallel evaluator unless Juan deliberately chooses to rename/refactor it**.

The goal today is to formalize the missing parts that the existing report already identified:

1. **Graded relevance:** use `relevance_grades` so a primary document (grade 2) scores higher than a secondary document (grade 1), instead of treating both as identical hits.
2. **Filtered-eval methodology:** define and implement a defensible way to score queries with `metadata_filters` without penalizing retrievers for correctly removing gold documents that the filter itself excludes.
3. **Error slices:** group metrics by query type, difficulty, filtered vs. unfiltered, and other corpus labels so the next improvement is chosen from measured weaknesses, not vibes.
4. **Manual/LLM evaluation rubric:** write a small procurement-specific rubric for relevance judgments. LLM judging can be designed or optionally prototyped, but should not become a dependency for the standard deterministic test suite today.

This is still a from-primitives learning day. Avoid RAGAS/DeepEval framework integration, LangChain evaluators, vector-database dashboards, serving, or source-cited answer generation today. Those are later gates. Build the concepts in the repo first.

## Starting state

The repo currently has:

- `src/preprocessing.py` — shared corpus loading, text normalization, and tokenization.
- `src/retrieval.py` — TF-IDF and BM25 lexical retrieval.
- `src/semantic_search.py` — dense/cosine retrieval over documents.
- `src/chunking.py` — sentence-aware overlapping chunker.
- `src/chunked_search.py` — chunk-level semantic retrieval and BM25-over-chunks.
- `src/hybrid_search.py` — RRF/weighted fusion plus metadata-filtering utilities.
- `src/reranking.py` — two-stage cross-encoder reranking over chunk-level Hybrid RRF shortlists.
- `src/eval_metrics.py` — current binary P@1 / R@5 / MRR@10 baseline over the canonical 93-query set.
- `data/corpus_v1/procurement_kb.jsonl` — 34 realistic procurement documents.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query v1 golden set with `expected_relevant_ids`, `relevance_grades`, `metadata_filters`, `expected_answer`, and verbatim evidence quotes.
- `docs/eval-report.md` — Day 7/8 report with nine retrieval rows and known limitations.

Baseline checks at start of Day 9:

```bash
./.venv/bin/pytest -q
# 97 passed in 1.00s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python src/eval_metrics.py
# 93 queries, 34 documents, 570 chunks, retrieval depth=10, candidate pool=15
# Cross-encoder reranked Hybrid RRF chunk→document: P@1 0.978, R@5 0.806, MRR@10 0.984
```

Current measured retrieval table:

| Method | P@1 | R@5 | MRR@10 |
|---|---:|---:|---:|
| TF-IDF (document) | 0.871 | 0.787 | 0.924 |
| BM25 (document) | 0.860 | 0.754 | 0.910 |
| Dense (document) | 0.839 | 0.673 | 0.900 |
| Dense chunk→document | 0.925 | 0.768 | 0.954 |
| Hybrid RRF (document) | 0.860 | 0.763 | 0.922 |
| Hybrid weighted (document) | 0.882 | 0.775 | 0.938 |
| Hybrid RRF chunk→document | 0.935 | 0.811 | 0.965 |
| Hybrid weighted chunk→document | 0.925 | 0.801 | 0.961 |
| Cross-encoder reranked Hybrid RRF chunk→document | **0.978** | 0.806 | **0.984** |

Corpus/eval facts to carry forward:

- Query set: 93 queries; types include lookup (23), conceptual (17), procedural (14), supplier-specific (13), threshold (8), numeric (7), terminology (6), multi_doc (5).
- Difficulty split: 15 easy, 52 medium, 26 hard.
- `relevance_grades` exists for all 93 queries: 147 grade-2 primary judgments and 102 grade-1 secondary judgments.
- 21 queries have `metadata_filters`.
- 17 of those 21 filtered queries have at least one `expected_relevant_ids` entry excluded by the query's own filter. No filtered query loses *all* gold documents after applying its intended filter.
- Existing eval table is **unfiltered text retrieval only**. It does not read `query_row["metadata_filters"]`.

The Day 8 weakness to carry forward is not “we have no evals.” It is sharper: **the evals are still binary and mostly aggregate.** They prove that reranking improved top-of-list precision, but they cannot yet tell whether the top result is primary vs. secondary, which query slices are weak, or what a filtered query should count as recall.

## Key concepts to nail today

### Manual evaluation defines the target before metrics automate it

Boot.dev starts Chapter 9 with manual evaluation for a reason: metrics are only as good as the relevance definition behind them. In ProcureRAG, “relevant” is not just “topically similar.” A result is highly relevant when it directly answers the buyer/procurement question with the right clause, threshold, supplier, evidence, and scope. A marginal result may discuss the same category but miss a condition, supplier, or exact figure.

Today’s evaluation harness should make that visible. The v1 query set already distinguishes grade 2 primary relevance from grade 1 partial relevance. Treating both as equal was fine for Day 7’s first baseline; it is not enough for the next stage.

### Graded relevance answers a different question from binary P@1/R@5/MRR@10

Binary metrics ask: “did any acceptable relevant document appear?” Graded metrics ask: “did the system rank the *best* evidence above merely related evidence?”

That matters for procurement. If a question asks what deadband applies to indexation clauses, a guide with general recommendations may be partially relevant, but the specific supplier contract may be primary. A binary metric can mark both as equally correct; an nDCG-style metric rewards the system for putting the primary evidence first.

A practical Day 9 target is **nDCG@5 or nDCG@10** over document ids using `relevance_grades` (`2` primary, `1` partial, missing = `0`). Juan can implement the formula directly instead of pulling in scikit-learn. The learning win is understanding discounted gain, ideal ranking, and why rank position matters.

### Filtered retrieval needs adjusted ground truth, not just filtered candidates

The current metadata filtering code can filter a ranked result list. But a fair filtered-eval table needs to adjust the gold set too. Example already measured in Day 7: Q001 has filter `doc_type: policy`; `FAQ-001` is in `expected_relevant_ids` as a secondary answer, but it is not a policy. If the filtered retriever correctly removes `FAQ-001`, recall should not penalize it for missing a document the filter explicitly excludes.

The defensible method:

1. For each query with `metadata_filters`, apply the filter to the corpus metadata.
2. Build a **filtered gold set** by keeping only relevant ids whose documents satisfy the query filter.
3. Score post-filter retrieved ids against that filtered gold set.
4. Record how many gold ids were excluded by the filter so the report remains auditable.

Do not reuse unfiltered `expected_relevant_ids` for filtered recall. That would measure “did the retriever violate the filter,” not “did it retrieve relevant in-scope documents.”

### Error analysis turns a score table into an engineering roadmap

Aggregate metrics can hide the next best fix. Day 8’s reranked row has strong P@1/MRR@10 but a tiny R@5 drop. Day 9 should explain where that movement happens:

- query type: lookup vs. conceptual vs. numeric vs. multi_doc;
- difficulty: easy / medium / hard;
- filtered vs. unfiltered;
- single-primary vs. multi-primary queries;
- methods: first-stage chunk-level Hybrid RRF vs. reranked Hybrid RRF.

The output does not need to be a fancy dashboard. A few deterministic tables in `docs/eval-report.md` or a small `main()` printout are enough if they reveal which failure class to fix next.

### LLM evaluation is useful only after the rubric is explicit

Boot.dev’s `LLM Evaluation` lesson asks for a 0–3 relevance score. ProcureRAG can borrow the idea, but the standard repo tests should not depend on an external LLM call. Today’s better target is:

- write a procurement-specific 0–3 rubric;
- create a small sample of retrieved result judgments to validate by hand;
- optionally add a pluggable LLM-judge function or prompt template if time remains;
- keep all automated tests deterministic with fake judge outputs or static examples.

## Target evidence by end of day

- [ ] Boot.dev Chapter 9 lessons 1–7 are completed or reactivated, with notes captured.
- [ ] Juan writes a short relevance rubric that distinguishes grade 2 primary, grade 1 partial, and grade 0 non-relevant results in procurement terms.
- [ ] Existing `src/eval_metrics.py` is extended, or an explicitly chosen replacement is created, to support at least one graded metric such as nDCG@5 or nDCG@10.
- [ ] Tests cover the graded metric with hand-computed examples, including ties, missing ids, empty retrieved lists, and an ideal ranking.
- [ ] A filter-adjusted gold-set function exists and is tested against real v1 examples such as Q001/Q007/Q019, proving that excluded secondary documents are not counted against filtered recall.
- [ ] A filtered-eval row/table is produced for the 21 queries with metadata filters, clearly labeled as **filtered retrieval over filter-adjusted gold**, not mixed into the unfiltered table without explanation.
- [ ] Error slices are produced for at least query type and difficulty, preferably also filtered vs. unfiltered and single-primary vs. multi-primary.
- [ ] `docs/eval-report.md` is updated with Day 9 results, caveats, and exact metric labels.
- [ ] `docs/learning-log.md` has a Day 9 entry with real evidence, confusion, interview explanation, remaining weakness, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline, 20–30m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python src/eval_metrics.py
```

Then answer from memory:

1. What is the strongest current retrieval row?
   **Expected:** Cross-encoder reranked Hybrid RRF chunk→document for P@1/MRR@10 (0.978 / 0.984), while first-stage Hybrid RRF chunk→document still has slightly better R@5 (0.811 vs. 0.806).
2. What does the current table *not* measure?
   **Expected:** graded relevance, filtered retrieval against adjusted gold sets, and per-slice failure patterns.
3. Why not create `data/golden_queries.jsonl` from scratch?
   **Expected:** `data/corpus_v1/example_queries.jsonl` is already the canonical 93-query source with expected ids, grades, filters, expected answers, and evidence quotes. Duplicating it would create drift.

### Block 1 — Boot.dev Chapter 9 evaluation lessons, 75–105m

Work through or reactivate the seven Chapter 9 lessons:

| Lesson | ProcureRAG proof target |
|---|---|
| Manual Evaluation | Write a procurement-specific relevance rubric before adding more metrics. |
| Golden Dataset | Explain why v1’s 93-query file is the canonical golden set and what would make v2 necessary later. |
| Precision Metrics | Re-explain P@1/P@k and why high precision does not mean high recall. |
| Recall Metrics | Re-explain R@5 and why multi-document questions make recall harder than top-1 accuracy. |
| F1 Score | Decide whether F1@k is useful here or less informative than showing P/R separately. |
| Error Analysis | Produce at least two slice tables and identify the next failure class. |
| LLM Evaluation | Draft or prototype a 0–3 judge rubric, but keep repo tests deterministic. |

Capture 3–5 bullets in the learning log connecting these lessons to procurement RAG: exact thresholds, multi-document answers, filters, primary vs. secondary evidence, and why eval criteria matter before source-cited generation.

### Block 2 — Design the Day 9 artifact contract, 45–60m

Before coding, write the contract in a scratchpad or the learning log:

- **Canonical input:** `data/corpus_v1/example_queries.jsonl`, not a duplicate `data/golden_queries.jsonl`.
- **Binary metrics to preserve:** P@1, R@5, MRR@10 should stay comparable with Day 7/8.
- **Graded metric:** recommended nDCG@5 or nDCG@10, using `relevance_grades` as document gains.
- **Filtered evaluation:** only score the 21 queries with filters in a separate table, using filter-adjusted gold ids.
- **Error slices:** define small aggregation helpers that group by `query_type`, `difficulty`, `bool(metadata_filters)`, and maybe number of primary docs.
- **Report shape:** keep one unfiltered aggregate table for comparability, add one graded table, one filtered table, and a compact “largest weak slice” summary.
- **LLM judge boundary:** optional design/prototype only; no external API dependency in normal tests.

### Block 3A — Primary route: Juan-owned evaluation extension, 2–2.5h

Recommended files Juan may create or modify when ready:

- `src/eval_metrics.py` — likely extension point for graded metrics and slice aggregation.
- `tests/test_eval_metrics.py` — likely extension point for deterministic tests.
- `docs/eval-report.md` — Day 9 results and caveats.
- `docs/learning-log.md` — Day 9 evidence after building.
- Optional: `docs/evaluation-rubric.md` if the relevance rubric becomes long enough to deserve its own doc.

Suggested implementation steps, not mandatory exact structure:

1. Implement `discounted_cumulative_gain` and `ndcg_at_k` directly, using small lists/dicts rather than adding a dependency.
2. Add `grades_for_query(query_row)` or equivalent that maps document id → relevance grade.
3. Add `filter_adjusted_relevant_ids(query_row, documents_by_id)` and/or `filter_adjusted_grades(query_row, documents_by_id)` using the same filter semantics as `hybrid_search.matches_filters`.
4. Add tests with hand-computed examples first, then one or two tests against real v1 query ids that are already known from the docs (Q001, Q007, Q019).
5. Add slice aggregation helpers that can evaluate an existing retrieval function by query subset.
6. Compare at least two important methods in slice tables: Hybrid RRF chunk→document vs. Cross-encoder reranked Hybrid RRF chunk→document.
7. Update `docs/eval-report.md` with numbers and caveats. Label each table precisely: binary unfiltered, graded unfiltered, filtered-adjusted, error slices.
8. Fill in the Day 9 learning-log entry with real output, not placeholders.

Do not implement source-cited answer generation, LangChain, RAGAS/DeepEval, vector databases, API serving, or MCP today. Those belong to later gates.

### Block 3B — Fallback route: rubric + deterministic metric tests, 60–90m

Use this if Boot.dev or metric design runs long.

Still produce evidence:

1. Finish/reactivate the Chapter 9 lessons.
2. Write the manual relevance rubric.
3. Implement and test nDCG@k on synthetic examples only.
4. Write the filtered-eval methodology in `docs/eval-report.md` or the learning log, even if the full filtered table is deferred.
5. Leave the exact next command Juan should run to finish the full metric table.

The non-negotiable output is conceptual clarity plus at least one deterministic metric improvement. Do not fabricate graded or filtered table numbers if the code did not actually compute them.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. Why does manual evaluation come before automated metrics?

   **Expected answer shape:** metrics encode a relevance definition; without a human/domain rubric, they can optimize the wrong behavior. Manual examples define what “good” means before automation scales it.

2. What is the difference between precision@k and recall@k?

   **Expected answer shape:** precision asks how many retrieved top-k results are relevant; recall asks how many known relevant results were retrieved in top-k. A system can have high P@1 and low recall on multi-document questions.

3. Why did ProcureRAG need graded relevance after Day 8?

   **Expected answer shape:** binary metrics count primary and partial documents equally. Graded relevance rewards ranking the best evidence above merely related evidence, which matters for clauses, suppliers, thresholds, and multi-document answers.

4. How would you compute nDCG@k in plain English?

   **Expected answer shape:** assign gain by relevance grade, discount gains lower in the ranking, sum them to get DCG, then divide by the ideal DCG for the same query so the score is normalized between 0 and 1.

5. Why does filtered evaluation require adjusted ground truth?

   **Expected answer shape:** if a query filter excludes a secondary gold document, the retriever should not be penalized for respecting the filter. Score post-filter results against only the relevant ids that are in scope for that filter.

6. What does error analysis add beyond an aggregate table?

   **Expected answer shape:** it shows which class of questions is weak — numeric, conceptual, filtered, multi-doc, hard — so the next retrieval/generation fix is targeted rather than anecdotal.

7. What is risky about LLM-as-judge evaluation?

   **Expected answer shape:** the judge may misunderstand procurement criteria, be inconsistent, overrate fluent but wrong answers, or drift by prompt/model. It must be calibrated against human/domain examples and should not be the only gate.

## Hermes review protocol

When Juan has a serious Day 9 attempt ready, ask Hermes:

> Review my Day 9 ProcureRAG evaluation work. Check the Boot.dev Chapter 9 evidence, relevance rubric, graded metric implementation, filter-adjusted evaluation methodology, error-slice tables, eval-report updates, tests, compile/lint gates, and whether I can explain precision, recall, F1, nDCG, filtered gold sets, and LLM-as-judge risks in an AI Engineer interview. Do not rewrite the implementation for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan’s implementation.

## Stop condition

Day 9 is complete when the evaluation work produces evidence, not just new functions:

1. Boot.dev Chapter 9 evaluation lessons are recorded.
2. A procurement-specific relevance rubric exists.
3. Tests / compile / smoke output is captured.
4. At least one graded metric is implemented and tested.
5. Filtered-eval methodology is implemented or explicitly documented with the exact blocker.
6. `docs/eval-report.md` distinguishes binary unfiltered, graded unfiltered, filtered-adjusted, and slice/error-analysis results.
7. The learning log explains which retrieval configuration looks strongest after graded/filtered/slice analysis, and which weakness should feed Day 10.
8. Juan can explain precision, recall, F1, nDCG, error analysis, and LLM-as-judge caveats without notes.

Do not close HER-275 on passing tests alone. The rubric, report, methodology, and interview explanation are part of the acceptance criteria.
