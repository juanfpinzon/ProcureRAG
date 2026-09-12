# Day 8 — Reranking + Two-Stage Retrieval

Date: 2026-09-12 target; started 2026-09-12.

Linear: HER-274 — Day 8 loop: Boot.dev Ch8 reranking.

Related gate: HER-267 — Week 2 gate: hybrid search, reranking, retrieval evals.

Project rule: course-driven building, with Juan owning the core retrieval/reranking implementation. Hermes may scaffold docs and review; Juan writes the reranking/eval code and tests.

## Course target for today

Boot.dev RAG course target:

- **Primary chapter:** Chapter 8 — **Reranking**.
- **Exact lessons shown in the Boot.dev Chapter 8 lesson menu:**
  1. **Re-ranking** — why first-stage retrieval should collect candidates before a more expensive second pass re-scores them.
  2. **LLMs for Re-Ranking** — using an LLM to judge query/document relevance, plus why cost/latency can make this impractical for every candidate.
  3. **LLM Batch Re-Ranking** — batching candidate judgments so the reranker can compare multiple retrieved results more efficiently.
  4. **Cross-Encoder Re-Ranking** — using a cross-encoder reranker such as `cross-encoder/ms-marco-TinyBERT-L2-v2` to score query/document pairs directly.
- **Today’s Boot.dev task shape:** understand the two-stage pattern, then translate it into ProcureRAG: first retrieve a shortlist with the current best first-stage method, then rerank that shortlist and measure whether the ordering improves.

Companion sources:

- **Beyond Naive RAG / Ben Clavié:** reranking and failure-mode sections, especially the argument that reranking exists because first-stage retrievers optimize recall/coverage, not final ordering precision.
- **Pinecone rerankers / two-stage retrieval article:** optional conceptual read for the bi-encoder vs. cross-encoder latency/accuracy tradeoff.

## Day 8 objective

Turn Day 7’s strongest first-stage retrieval baseline into a two-stage retrieval pipeline. The key shift is: **do not rerank the weaker whole-document hybrid result and then claim a large win.** Day 7 established the real baseline to beat: **Hybrid RRF over chunks, rolled up to documents — P@1 0.935, R@5 0.811, MRR@10 0.965** in `docs/eval-report.md`.

By the end of Day 8, you should be able to explain and show whether a reranker improves final ordering on top of that already-strong shortlist, especially on the open Day 7 weakness: first-stage fusion can prefer cross-retriever consensus over a document/chunk that is strongly correct on only one signal.

This is still a from-primitives learning day. It is fine to call a local `sentence_transformers.CrossEncoder` model for scoring, but avoid LangChain reranker wrappers, Cohere APIs, vector databases, agents, serving, or source-cited generation today. The interview target is understanding the architecture and tradeoffs, not hiding them behind a framework.

## Starting state

The repo currently has:

- `src/preprocessing.py` — shared corpus loading, text normalization, and tokenization.
- `src/retrieval.py` — TF-IDF and BM25 lexical retrieval.
- `src/semantic_search.py` — dense/cosine retrieval over documents.
- `src/chunking.py` — sentence-aware overlapping chunker.
- `src/chunked_search.py` — chunk-level semantic retrieval and BM25-over-chunks.
- `src/hybrid_search.py` — `HybridSearch` with RRF and weighted/min-max fusion, plus metadata filtering utilities and edge-case demos.
- `src/eval_metrics.py` — P@1 / R@5 / MRR@10 evaluation over the canonical v1 query set.
- `data/corpus_v1/procurement_kb.jsonl` — 34 realistic procurement documents.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query v1 golden set with `expected_relevant_ids`, `relevance_grades`, `metadata_filters`, expected answers, and evidence quotes.
- `docs/eval-report.md` — Day 7 eight-row baseline table.

Baseline check at start of Day 8:

```bash
./.venv/bin/pytest -q
# 83 passed in 0.90s
```

`git status --short` was clean before this Day 8 scaffold was created.

The Day 7 weakness to carry forward is not “hybrid is bad”; it is sharper: **RRF and weighted fusion can still reward moderate agreement across BM25+dense over a strong, correct single-signal result.** Day 7 measured that at whole-document level on Q014. Day 8 should check whether that same pattern appears at chunk granularity, then test whether reranking fixes the final order.

## Key concepts to nail today

### Two-stage retrieval separates candidate recall from final precision

A first-stage retriever should be fast and broad enough to collect plausible candidates. In ProcureRAG, the best current first-stage method is chunk-level Hybrid RRF. It is cheap enough to run over the corpus and good enough to produce a strong shortlist.

A reranker should be slower but more precise. It should look at the query and each candidate passage together, then assign a new relevance score. That is why reranking should happen over a shortlist, not the entire corpus. The procurement framing: first stage finds 10–25 plausible clauses/chunks; reranking decides which clauses actually answer this specific buyer question.

### Bi-encoder vs. cross-encoder is the core architecture distinction

The existing semantic retriever is a bi-encoder pattern: document/chunk embeddings are computed independently from query embeddings, then compared by cosine similarity. This is fast and cacheable, but the query and document do not interact until the final dot-product/cosine step.

A cross-encoder scores a `(query, candidate_text)` pair jointly. It can notice that “uptime” and “availability commitment” are connected in this exact candidate, or that a candidate mentions the same numbers but answers a different policy question. That extra interaction is why it can improve precision — and why it is too expensive as the first-stage retriever.

### Reranking must preserve auditability

Do not throw away the first-stage scores. A useful result row should keep enough information to explain the final rank:

- candidate id (`chunk_id`, and parent `document_id` if reranking chunks);
- original first-stage score/rank (`rrf_score`, maybe BM25/dense scores if available);
- reranker score;
- candidate text used for reranking;
- final rank after reranking.

This is especially important for procurement: if a reranker promotes a different clause, you need to explain whether it did so because the text actually answers the query, not because an opaque model made the table prettier.

### Measuring “reranker helped” is harder than eyeballing one query

Day 7’s baseline is already strong. A cross-encoder may improve Q014-like failures but reduce another exact-ID or numeric query if the model is trained on general web/search data rather than procurement-specific clauses. Day 8 should measure both:

1. **Targeted case study:** what happens to the known Day 7 failure family?
2. **Aggregate table:** what happens to P@1 / R@5 / MRR@10 across all 93 queries?

If the aggregate row does not beat chunk-level Hybrid RRF, that is still a valid Day 8 outcome if the report explains why and records the exact numbers. Do not overclaim.

## Target evidence by end of day

- [ ] Boot.dev Chapter 8 lessons 1–4 are completed or reactivated, with notes captured.
- [ ] A two-stage reranking contract is written before coding: first-stage method, shortlist size, candidate text format, reranker score shape, and rollup rule.
- [ ] Juan-owned artifact is implemented or partially implemented, likely in `src/reranking.py`.
- [ ] Tests exist for reranking behavior without relying on a live model download for every unit test.
- [ ] The reranker preserves first-stage score/rank plus reranker score for debuggability.
- [ ] `docs/eval-report.md` is updated with at least one reranking row against the same 93-query source and same metric labels: P@1, R@5, MRR@10.
- [ ] Reranking is benchmarked against **Hybrid RRF chunk→document (0.935 / 0.811 / 0.965)**, not only against whole-document baselines.
- [ ] Q014 or an equivalent consensus-over-strength failure case is checked at chunk level and written up, whether the reranker fixes it or not.
- [ ] `docs/learning-log.md` has a Day 8 entry with real evidence, confusion, interview explanation, remaining weakness, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline, 20–30m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python src/eval_metrics.py
```

Optional, if you need to inspect Day 7 qualitative failures again:

```bash
./.venv/bin/python src/hybrid_search.py
```

Then answer from memory:

1. What is the best Day 7 baseline?
   **Expected:** Hybrid RRF over chunks, rolled up to documents, with P@1 0.935, R@5 0.811, MRR@10 0.965.
2. Why not rerank whole-document hybrid first?
   **Expected:** because it is no longer the best first-stage pipeline; reranking it would overstate the reranker’s value by comparing against a weaker baseline.
3. What failure should reranking target?
   **Expected:** cases where first-stage fusion over-rewards moderate agreement across BM25+dense and under-ranks a candidate that is strongly correct on only one signal.

### Block 1 — Boot.dev Chapter 8 reranking lessons, 75–105m

Work through or reactivate the four Chapter 8 lessons:

| Lesson | ProcureRAG proof target |
|---|---|
| Re-ranking | Explain two-stage retrieval: chunk-level hybrid retrieves candidates, reranker re-scores final shortlist. |
| LLMs for Re-Ranking | Explain why LLM-as-judge can be accurate but expensive/slower and must be carefully prompted/evaluated. |
| LLM Batch Re-Ranking | Explain batching candidates and why comparing candidates in one call can change cost/latency and calibration. |
| Cross-Encoder Re-Ranking | Implement or prototype a cross-encoder scorer for `(query, candidate_text)` pairs, ideally with `cross-encoder/ms-marco-TinyBERT-L2-v2` or another small local model available through `sentence-transformers`. |

Capture 3–5 bullets in the learning log connecting these lessons to procurement RAG: exact IDs, policy clauses, supplier-specific questions, latency budget, and why reranking should operate on retrieved chunks.

### Block 2 — Design the Day 8 artifact contract, 45–60m

Before coding, write the contract in a scratchpad or at the top of `docs/learning-log.md`:

- **First-stage input:** recommended default is chunk-level Hybrid RRF using `CANDIDATE_POOL_SIZE=15`, then keeping a reranker shortlist of 10–25 chunks.
- **Candidate text:** use the source title plus chunk text for scoring context, but preserve the raw chunk text separately as the passage a later generator would cite.
- **Reranker interface:** suggested shape: `rerank(query, candidates, top_k)` returns candidates sorted by reranker score while preserving original score/rank fields.
- **Model loading:** load the cross-encoder once, not once per candidate. If GPU acceleration errors, force CPU. If model download is slow, unit-test with a fake scorer and leave the live model demo as a smoke command.
- **Rollup:** if scoring chunks, roll up to document IDs using the first/best reranked chunk per document before calculating document-level P@1/R@5/MRR@10.
- **Evaluation comparison:** add rows that make the baseline explicit, for example:
  - Hybrid RRF chunk→document (existing baseline)
  - Cross-encoder reranked Hybrid RRF chunks → documents
  - Optional: LLM-reranked shortlist, if implemented and cost-controlled
- **Success definition:** measured, not assumed. Improvement on a targeted Q014-like failure is good; aggregate improvement across all 93 queries is better; a measured non-improvement with a correct explanation still counts as learning.

### Block 3A — Primary route: Juan-owned reranking artifact, 2–2.5h

Recommended files Juan may create or modify when ready:

- `src/reranking.py`
- `tests/test_reranking.py`
- `src/eval_metrics.py` only if adding reranked eval rows
- `docs/eval-report.md`
- `docs/learning-log.md`

Suggested implementation steps, not mandatory exact structure:

1. Build a function that produces a chunk-level Hybrid RRF shortlist for one query using the Day 7 pieces (`build_chunk_lexical_index`, `search_bm25_chunks`, `search_semantic_chunks`, `HybridSearch(id_key="chunk_id")`).
2. Add a reranker abstraction that accepts a query and a candidate list. Keep it testable with a fake scoring function/model.
3. Add cross-encoder scoring for live runs: score `[query, title + chunk_text]` pairs, store `reranker_score`, sort descending, and truncate.
4. Preserve original first-stage fields in each result so you can explain a reranked decision.
5. Add a demo over a small set of representative v1 queries, including Q014 if possible.
6. Add an eval row over all 93 queries if runtime is acceptable. If runtime is too slow, run a documented subset and write the exact command that will produce the full row later.
7. Update `docs/eval-report.md` with numbers and caveats, especially whether the reranker beats or fails to beat the existing chunk-level Hybrid RRF baseline.

Do not implement source-cited answer generation, LangChain, vector database migration, API serving, RAGAS/DeepEval, or MCP today. Those belong to later gates.

### Block 3B — Fallback route: reranking design + fake-scorer harness, 60–90m

Use this if Boot.dev or model-download issues consume the day.

Still produce evidence:

1. Finish/reactivate the Chapter 8 lessons.
2. Create the reranker interface and unit tests using a fake scorer that deterministically changes candidate order.
3. Record the live cross-encoder blocker exactly: model name, command run, error/latency, and planned fix.
4. Update `docs/eval-report.md` with a “reranking planned / fake scorer only” section rather than fabricating model results.
5. Leave the next command Juan should run for the real model smoke test.

The non-negotiable output is the two-stage contract plus a testable path toward real reranking. Do not fake a P@1 improvement if the model did not actually run.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. Why is reranking a second-stage step instead of the first retriever?

   **Expected answer shape:** first-stage retrieval must be fast and broad over the whole corpus; reranking is more expensive but more precise, so it scores only a shortlist.

2. What is the difference between a bi-encoder and a cross-encoder?

   **Expected answer shape:** a bi-encoder embeds query and document separately and compares vectors, which is cacheable and fast; a cross-encoder scores the query/document pair jointly, which is slower but can model richer interactions.

3. Why should Day 8 benchmark against chunk-level Hybrid RRF, not document-level hybrid?

   **Expected answer shape:** Day 7 showed chunk-level Hybrid RRF is the strongest baseline; comparing a reranker only against weaker document-level hybrid would overstate the gain.

4. How can a reranker fix the Q014-style failure mode?

   **Expected answer shape:** first-stage RRF can favor a candidate moderately supported by both retrievers over one strongly supported by only dense search. A cross-encoder directly scores the query against candidate text and may promote the actually answering clause even without BM25 support.

5. What fields should a reranked result preserve for auditability?

   **Expected answer shape:** chunk/document id, original first-stage rank/score, reranker score, candidate text, parent title/document id, and final rank.

6. What could make a reranker worse?

   **Expected answer shape:** domain mismatch, short/poor candidate text, over-favoring semantic plausibility over exact identifiers, insufficient candidate recall, latency constraints, or evaluating against binary relevance when graded relevance matters.

## Hermes review protocol

When Juan has a serious Day 8 attempt ready, ask Hermes:

> Review my Day 8 ProcureRAG reranking work. Check the two-stage retrieval contract, cross-encoder or fake-scorer design, Q014/chunk-level failure analysis, eval-report reranking rows, tests, compile/lint gates, and whether I can explain bi-encoder vs cross-encoder tradeoffs in an AI Engineer interview. Do not rewrite the implementation for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan’s implementation.

## Stop condition

Day 8 is complete when there is reranking evidence, not just a new file:

1. Boot.dev Chapter 8 reranking lessons are recorded.
2. Tests / compile / smoke output is captured.
3. The first-stage shortlist and reranker interface are clearly documented.
4. The reranker is evaluated against the Day 7 chunk-level Hybrid RRF baseline, or the exact blocker to doing so is documented.
5. `docs/eval-report.md` distinguishes first-stage retrieval rows from reranked rows and labels metrics precisely as P@1, R@5, and MRR@10.
6. The learning log explains whether reranking helped, hurt, or was inconclusive, with real evidence.
7. Juan can explain two-stage retrieval, bi-encoder vs cross-encoder, and latency/accuracy tradeoffs without notes.

Do not close HER-274 on passing tests alone. The reranking comparison, evidence write-up, and interview explanation are part of the acceptance criteria.
