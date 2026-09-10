# Day 6 — Hybrid Search Foundations for ProcureRAG

Date: 2026-09-10 target; started 2026-09-10.

Linear: HER-272 — Day 6 loop: Boot.dev Ch6 hybrid search foundations.

Related gate: HER-267 — Week 2 gate: hybrid search, reranking, retrieval evals.

Project rule: course-driven building, with Juan owning the core retrieval implementation.

## Course target for today

Boot.dev RAG course target:

- **Primary chapter:** Chapter 6 — **Hybrid Search**
- **Lessons:**
  1. Keyword vs. Semantic Search — why neither alone suffices
  2. Hybrid Search — combining both signals
  3. Score Normalization — min-max, z-score, why raw scores are incomparable
  4. Weighted Combination — alpha-weighted blending of normalized scores
  5. Reciprocal Rank Fusion — rank-based fusion that sidesteps normalization
- **Companion:** Beyond Naive RAG — hybrid search and fusion sections for failure-mode vocabulary (naive score averaging, domain mismatch).

## Day 6 objective

Move from single-method retrieval to hybrid retrieval that combines lexical (BM25) and semantic (dense) signals over chunks. By the end of the day, you should understand why raw BM25 scores and cosine similarities cannot be directly combined, how RRF avoids the normalization problem entirely, and how a weighted combination with score normalization works when you want to tune the balance between exact-match and semantic-match signals.

This is not a LangChain or vector-database day. The portfolio artifact should stay small, inspectable, and explainable.

## Starting state

Day 5 produced:

- `src/chunking.py` — sentence-aware sliding-window chunker with overlap
- `src/chunked_search.py` — chunk-level semantic retrieval with whole-doc vs chunk comparison
- `src/retrieval.py` — TF-IDF and BM25 lexical retrieval over whole documents
- `src/semantic_search.py` — dense retrieval over whole documents
- `src/preprocessing.py` — shared preprocessing and tokenization
- 48 tests passing, clean compile, clean lint
- `docs/learning-log.md` through Day 5

The next learning edge is: **no single retrieval method is sufficient for procurement queries**. BM25 dominates on exact identifiers (PO numbers, policy codes, currency amounts), but misses paraphrases. Dense retrieval catches paraphrases, but blurs exact identifiers. Hybrid retrieval combines both so the system can handle both types of queries.

## Key concepts to nail today

### Why raw scores are incomparable

BM25 scores are unbounded positive reals whose range depends on corpus statistics (document frequency, average document length). Cosine similarity is bounded [−1, 1] (and in practice [0, 1] for normalized embeddings). A BM25 score of 15.37 and a cosine score of 0.63 cannot be meaningfully averaged — they live on completely different scales.

Two principled ways to combine them:

1. **Score normalization + weighted combination:** Normalize each retriever's scores to a common scale (min-max to [0,1], or z-score), then blend with a weight α ∈ [0,1] where `hybrid_score = α × semantic_norm + (1−α) × lexical_norm`. The weight controls the balance. The normalization step is the hard part — min-max is sensitive to outliers, z-score can produce negative values.

2. **Reciprocal Rank Fusion (RRF):** Ignore raw scores entirely. For each retriever, rank results by score. Then `rrf_score(d) = Σ 1/(k + rank_i(d))` where k is a constant (typically 60). Documents that rank high in both lists get a high combined score. RRF sidesteps the normalization problem entirely because it only uses ranks, not scores.

### Why RRF is the simpler and often better choice for interview explanations

- No normalization step to get wrong.
- No α to tune (though k matters for tie-breaking).
- Robust to score-scale differences and outliers.
- Works even when one retriever returns only a subset of documents (BM25 returns nothing for out-of-vocabulary queries; dense returns something for everything).

### When weighted combination still matters

- When you want to explicitly control the balance between exact-match and semantic-match signals (e.g., a procurement system where exact-identifier queries should dominate 80/20).
- When you need the score itself to be interpretable (e.g., "this result is 73% semantic match, 27% lexical match").
- When you want to compare raw retrieval quality before and after reranking (Day 8).

## Target evidence by end of day

- [ ] Boot.dev Chapter 6 lessons completed or meaningfully attempted.
- [ ] Juan can explain why raw BM25 and cosine scores are incomparable.
- [ ] Juan can explain why RRF sidesteps the normalization problem.
- [ ] Juan can explain the α weight in weighted combination and what α=0, α=0.5, α=1 mean.
- [ ] A `src/hybrid_search.py` module exists with:
  - A `HybridSearch` class that takes BM25 results and semantic results as inputs
  - RRF fusion method with configurable k parameter
  - Weighted combination method with configurable α and score normalization (min-max and/or z-score)
  - Per-method scores preserved for debuggability
- [ ] `tests/test_hybrid_search.py` covers:
  - Hybrid beats both lexical-only and semantic-only on at least one procurement query with an exact identifier
  - RRF and weighted combination produce consistent top-1 results on the v1 corpus
  - α=1.0 degrades to semantic-only; α=0.0 degrades to lexical-only
  - The k parameter in RRF affects tie-breaking but not top-1 on the v1 corpus
- [ ] `docs/learning-log.md` gets a Day 6 entry with exact Boot.dev lessons, artifact evidence, confusion, interview explanation, weaknesses, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline, 20–30m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python src/retrieval.py
./.venv/bin/python src/semantic_search.py
./.venv/bin/python src/chunked_search.py
```

Then answer from memory:

1. What are the two retrieval methods we have, and what does each one do well?
   **Expected:** BM25 excels at exact token matches (identifiers, amounts, acronyms). Dense/semantic retrieval excels at paraphrase and meaning matches where the exact words differ.
2. Why can't you just average a BM25 score and a cosine similarity score?
   **Expected:** They're on different scales. BM25 is unbounded; cosine is [0,1]. Averaging them would let the higher-magnitude scores dominate regardless of retrieval quality.
3. What retrieval unit should hybrid search operate over?
   **Expected:** Chunks, not whole documents — the retrieval unit from Day 5. Whole-document hybrid search can be a comparison baseline, but chunk-level is the production path.

### Block 1 — Boot.dev Chapter 6 lessons, 2–2.5h

Primary target:

1. **Keyword vs. Semantic Search** — recap of why neither alone suffices for real queries.
2. **Hybrid Search** — combining both retrieval signals.
3. **Score Normalization** — min-max, z-score, why raw scores are incomparable.
4. **Weighted Combination** — alpha-weighted blending of normalized scores.
5. **Reciprocal Rank Fusion** — rank-based fusion that sidesteps normalization.

Capture notes in this shape:

| Lesson | Plain-English takeaway | Procurement example | Implementation implication |
|---|---|---|---|
| Keyword vs. Semantic | | | |
| Hybrid Search | | | |
| Score Normalization | | | |
| Weighted Combination | | | |
| RRF | | | |

Minimum understanding target:

- Raw BM25 scores and cosine similarities cannot be directly averaged.
- RRF uses only ranks, so it avoids the normalization problem entirely.
- Weighted combination needs a normalization step first (min-max or z-score), then an α weight to balance the two signals.
- α=0 means pure lexical, α=1 means pure semantic, α=0.5 means equal weight.

### Block 2 — Design the hybrid search contract, 45–60m

Before coding, write a short design note:

- **Input shape:** HybridSearch takes two lists of scored results (one from BM25, one from semantic) and combines them.
- **Should hybrid search operate over chunks or whole documents?**
  **Suggested answer:** Start with whole documents for clarity and comparison with Week 1 baselines. Add a chunk-level hybrid method as a second step. The hybrid logic (RRF, weighted combo) is the same regardless of retrieval unit.
- **What should the output shape be?**
  **Suggested answer:** Same shape as individual retriever output (`{id, score}` for whole-doc, `{chunk_id, document_id, text, score}` for chunks), plus the per-method scores for debuggability.
- **What should stay unchanged?**
  **Suggested answer:** The existing TF-IDF, BM25, and semantic search modules. Day 6 adds a new hybrid module that *uses* their outputs — it should not modify them.

### Block 3A — Primary route: Juan-owned hybrid search artifact, 1.5–2h

Recommended files Juan may create or modify when ready:

- `src/hybrid_search.py`
- `tests/test_hybrid_search.py`
- `docs/learning-log.md`

Suggested implementation steps, not mandatory exact structure:

1. Define a `HybridSearch` class that accepts BM25 results and semantic results as inputs.
2. Implement RRF fusion: `rrf_score(d) = 1/(k + rank_bm25(d)) + 1/(k + rank_semantic(d))` with configurable k (default 60).
3. Implement score normalization: min-max normalization to [0,1] for each retriever's scores.
4. Implement weighted combination: `hybrid_score = α × semantic_norm + (1−α) × lexical_norm` with configurable α (default 0.5).
5. Add a main() demo that runs all retrieval methods on the Day 4 comparison queries and shows where hybrid beats both.
6. Add tests covering the four acceptance criteria above.
7. Record what changed in the Day 6 learning log.

Do not add metadata filtering, reranking, evaluation metrics, or production serving today. Those are Days 7–9.

Finally, fill in learning question for the Day on learning-log.md

### Block 3B — Fallback route: hybrid search design only, 60–90m

Use this route if the course material takes most of the day.

Still produce evidence:

1. Finish lessons 1–5.
2. Write the hybrid search design in the learning log or this doc.
3. List 3 procurement queries where hybrid should beat both single methods:
   - `"What approval is required for a €60,000 purchase order?"` — BM25 catches the exact amount; semantic catches "approval required".
   - `"Which suppliers need SOC 2 Type II or ISO 27001 evidence?"` — BM25 catches the exact standards; semantic catches "suppliers need evidence".
   - `"What happens when invoice variance is over 3%?"` — BM25 catches the exact percentage; semantic catches "invoice variance".
4. Defer implementation with a concrete next step.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. Why can't you average a BM25 score and a cosine similarity score directly?

   **Expected answer shape:** They're on different scales. BM25 scores are unbounded positive reals; cosine similarity is bounded [0,1] for normalized embeddings. Averaging them would let the higher-magnitude scale dominate regardless of retrieval quality.

2. What is Reciprocal Rank Fusion, and why does it avoid the normalization problem?

   **Expected answer shape:** RRF assigns each document a score based on its rank position in each retriever's result list: `score(d) = Σ 1/(k + rank_i(d))`. Because it only uses rank positions (1st, 2nd, 3rd...) and not raw scores, it doesn't matter that BM25 and cosine similarity are on different scales. A document ranked #1 by both retrievers gets a high combined score regardless of the raw scores.

3. What does the α weight in weighted combination control?

   **Expected answer shape:** α controls the balance between semantic and lexical signals. α=1.0 means pure semantic (dense retrieval only), α=0.0 means pure lexical (BM25 only), α=0.5 means equal weight. It requires score normalization first so the two scales are comparable.

4. When would you prefer RRF over weighted combination?

   **Expected answer shape:** When you want a robust, tuning-free combination. RRF has one parameter (k) that rarely needs tuning and sidesteps normalization entirely. Use weighted combination when you need to explicitly control the balance or when the scores themselves need to be interpretable.

5. What procurement queries should hybrid search handle better than either method alone?

   **Expected answer shape:** Queries that combine exact identifiers (PO numbers, policy codes, currency amounts like €60,000, standards like ISO 27001) with paraphrased intent ("what approval is required", "which suppliers need evidence"). BM25 handles the exact part; semantic handles the paraphrase part.

6. What retrieval unit should hybrid search operate over?

   **Expected answer shape:** Chunks, not whole documents. The Day 5 chunking module established that the retrieval unit should be small enough to give the LLM just the relevant passage. Hybrid search combines signals over the same retrieval unit.

## Hermes review protocol

When Juan has a serious Day 6 attempt ready, ask Hermes:

> Review my Day 6 ProcureRAG hybrid search attempt. Check the RRF implementation, weighted combination with normalization, tests, and whether I can explain score incomparability, RRF, and α in an AI Engineer interview. Do not rewrite the implementation for me unless I ask for hints.

Hermes should review, quiz, and debug — not replace the core implementation.

## Stop condition

Day 6 is complete when there is hybrid search evidence, not just course progress:

1. exact Boot.dev Chapter 6 lessons completed/attempted are recorded;
2. tests / compile / smoke output is captured;
3. a hybrid search artifact exists with RRF and weighted combination;
4. the learning log explains score incomparability, RRF, weighted combination, one confusion/failure, remaining weakness, and the next step;
5. Juan can explain why hybrid search matters for procurement queries with exact identifiers.

Do not close HER-272 on passing tests alone. The learning evidence and explanation drill are part of the acceptance criteria.