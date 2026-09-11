# Day 7 — Hybrid Consolidation, Metadata Filters, and Retrieval Eval Baseline

Date: 2026-09-11 target; started 2026-09-11.

Linear: HER-273 — Day 7 loop: hybrid procurement artifact + edge cases.

Related gate: HER-267 — Week 2 gate: hybrid search, reranking, retrieval evals.

Project rule: course-driven building, with Juan owning the core retrieval implementation. Hermes may scaffold docs and review; Juan writes the retrieval/eval code and tests.

## Course target for today

Boot.dev RAG course target:

- **Primary chapter:** Chapter 6 — **Hybrid Search** consolidation / review.
- **Exact lessons to reactivate or finish if any remain:**
  1. Keyword vs. Semantic Search — why each retriever has blind spots.
  2. Hybrid Search — combining lexical and semantic result lists.
  3. Score Normalization — why raw BM25 and cosine scores cannot be averaged directly.
  4. Weighted Combination — alpha-weighted blending after normalization.
  5. Reciprocal Rank Fusion — rank-based fusion that avoids score normalization.
- **Today’s Boot.dev task shape:** finish any incomplete Chapter 6 exercises/review, then convert the lesson ideas into procurement evidence: edge-case comparison, metadata filtering, golden queries, and a baseline eval table.

Companion sources:

- **Beyond Naive RAG / Ben Clavié:** revisit hybrid-search failure modes and vocabulary: vocabulary mismatch, query drift, domain shift, score fusion limitations, and why retrieval evaluation must be empirical.
- **Optional only, conceptual:** freeCodeCamp RAG From Scratch notes on RAG-Fusion and HyDE. Do not implement those today; use them only to name future routes.

## Day 7 objective

Turn Day 6’s hybrid implementation from a working algorithm into an evaluated procurement retrieval artifact. By the end of the day, you should be able to show — not merely claim — when BM25 wins, when dense retrieval wins, when hybrid fusion helps, and when hybrid still fails. The concrete output is a Day 7 consolidation layer: metadata-aware comparison, a first eval report, and a versioned golden query set that Day 8/9 reranking and evaluation work can reuse.

This is still a from-primitives learning day. Avoid LangChain, vector databases, production serving, agents, and rerankers unless they are read-only notes for later.

## Starting state

The repo currently has:

- `src/preprocessing.py` — shared corpus loading, text normalization, and tokenization.
- `src/retrieval.py` — TF-IDF and BM25 lexical retrieval.
- `src/semantic_search.py` — dense/cosine retrieval over documents.
- `src/chunking.py` — sentence-aware overlapping chunker.
- `src/chunked_search.py` — chunk-level semantic retrieval plus BM25-over-chunks helpers added during Day 6 follow-up.
- `src/hybrid_search.py` — `HybridSearch` with RRF and weighted/min-max fusion, now exercised with both whole-document IDs and chunk IDs.
- `data/corpus_v1/procurement_kb.jsonl` — 34 longer procurement documents with metadata.
- `data/corpus_v1/example_queries.jsonl` — 93 v1 golden-style queries with relevance grades, metadata filters, expected answers, and evidence quotes.
- `docs/corpus-v1.md` — already records v1 corpus baselines and query-set design notes.
- `docs/learning-log.md` through Day 6.
- Baseline check at start of Day 7: `./.venv/bin/pytest -q` → `64 passed`.

The key Day 6 weakness to carry forward is the exact-tie failure mode: candidates that appear in only one retriever’s top-k can tie under both RRF and weighted fusion, and the current tie-break may choose by incidental ID ordering rather than relevance. Day 7 should not hide this weakness; it should measure it and make the next fix obvious.

## Key concepts to nail today

### Hybrid search is not automatically better

Hybrid search only helps when the relevant document or chunk receives usable signal from the fused lists. If the correct answer is absent from BM25’s candidate set and a wrong candidate is absent from dense retrieval’s candidate set, both can become one-signal candidates. Under RRF, each rank-1-only candidate gets `1/(k+1)`. Under equal weighted fusion, each can get `0.5`. That is an exact-tie mode, not a solved retrieval problem.

Today’s job is to separate three cases:

1. **BM25 wins:** exact IDs, policy codes, supplier IDs, amounts, dates, acronyms, contract references.
2. **Dense wins:** paraphrased intent, synonyms, scenario phrasing, vocabulary mismatch.
3. **Hybrid wins:** queries where the right item has enough lexical and semantic signal together to outrank distractors that win only one method.

### Metadata filtering is retrieval control, not just convenience

The v1 corpus includes metadata fields such as `doc_type`, `category`, `subcategory`, `region`, `supplier`, `supplier_id`, `risk_tags`, `annual_value_eur`, `source_system`, and dates. Procurement users often imply filters in their question: “for EMEA”, “for a supplier renewal”, “in the contract”, “for Acme”, “policy only”, or “open RFP”. A retriever that ignores those fields can rank semantically similar but operationally irrelevant documents.

Day 7 should test metadata filtering on a small, inspectable set. Do not over-engineer. The point is to prove the contract:

- filter before retrieval or after retrieval? record which one you chose;
- filter at document level or chunk level? record the implications;
- what happens when the filter removes the correct document? record the failure mode.

### Evaluation turns anecdotes into evidence

Day 6 used five comparison queries plus constructed tests. Day 7 starts the transition from demos to metrics. The v1 query file already has `expected_relevant_ids`, `relevance_grades`, `metadata_filters`, `expected_answer`, and evidence quotes. That is enough to compute simple retrieval metrics without LLM generation:

- **P@1:** whether the top result is relevant.
- **R@5:** how many relevant documents appear in the top five.
- **MRR:** how early the first relevant result appears.

If time is tight, calculate these manually for a small subset first, then leave a clear contract for a full harness on Day 9.

## Target evidence by end of day

- [ ] Boot.dev Chapter 6 is finished or reactivated, with any remaining exercise/review notes captured.
- [ ] Day 6 exact-tie weakness is explicitly addressed: fixed, measured, or documented as a known failure with a next-step design.
- [ ] Metadata filtering is designed and attempted against v1 corpus fields (`doc_type`, `category`, `region`, `supplier`, `risk_tags`, or equivalent).
- [ ] `src/hybrid_search.py` comparison output shows BM25 vs dense vs hybrid on procurement edge cases.
- [ ] `docs/eval-report.md` exists or is updated with a v1 baseline table.
- [ ] A golden query source is started or normalized:
  - preferred: use `data/corpus_v1/example_queries.jsonl` as the canonical v1 source and document why; or
  - if HER-273’s expected path is required, create `data/golden_queries.jsonl` as a curated first subset / alias path with at least 8 queries.
- [ ] Baseline table includes, at minimum, these rows or a clearly justified subset:
  - TF-IDF document retrieval
  - BM25 document retrieval
  - Dense document retrieval
  - Dense chunk→document retrieval
  - Hybrid RRF
  - Hybrid weighted
- [ ] Baseline table includes P@1, R@5, and MRR, even if some values are marked `TODO` with the exact command or manual method needed.
- [ ] `docs/learning-log.md` has a Day 7 entry with evidence, confusion, interview explanation, remaining weakness, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline, 20–30m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python src/hybrid_search.py
```

If you prefer `uv`, use the ticket’s equivalent commands, but keep the actual command output in the learning log.

Then answer from memory:

1. What did Day 6 build?
   **Expected:** a generic `HybridSearch` combiner that fuses already-ranked BM25 and semantic results using RRF or normalized weighted combination, and now supports non-default ID keys like `chunk_id`.
2. What Day 6 failure matters most today?
   **Expected:** exact ties where each candidate appears in only one retriever’s result list; current deterministic ID tie-break is not a relevance signal.
3. Why does v1 matter?
   **Expected:** v0 is too small/easy; v1 has 34 longer documents, 570 chunks, 93 queries, metadata filters, and visible lexical-vs-dense failure differences.

### Block 1 — Boot.dev Chapter 6 finish/review + companion notes, 60–90m

Reactivate the five Chapter 6 lessons:

| Lesson | Today’s proof target |
|---|---|
| Keyword vs. Semantic Search | Identify at least two v1 queries where BM25 wins and two where dense wins. |
| Hybrid Search | Show at least one query where fusion improves or at least explain why the corpus did not produce one. |
| Score Normalization | Explain why BM25 and cosine scores cannot be averaged raw. |
| Weighted Combination | Explain what alpha changes and why min-max normalization can still tie. |
| Reciprocal Rank Fusion | Explain why rank-only fusion is robust but can still tie one-signal candidates. |

Companion note target from Beyond Naive RAG:

- Write 3–5 bullets naming hybrid failure modes in procurement language: exact-ID miss, paraphrase miss, query drift, domain shift, metadata mismatch, and top-k truncation.

### Block 2 — Design the Day 7 artifact contract, 45–60m

Before coding, write a short note in your scratchpad or the learning log:

- **Canonical query source:** `data/corpus_v1/example_queries.jsonl` remains the source of truth,  and our golden data set for evaluating moving forward.
- **Metadata filter contract:** Which fields are supported today? Suggested minimum: one categorical filter (`doc_type` or `category`) and one supplier/region/risk-style filter if time allows.
- **Filter timing:** Is filtering applied before retrieval, after retrieval, or inside a wrapper that filters candidate documents before scoring? State the trade-off.
- **Chunk→document scoring:** If hybrid runs over chunks, how do chunk results roll up to document-level P@1/R@5/MRR? Suggested first rule: a chunk hit counts for its `document_id`; do not overcomplicate.
- **Tie-break design:** Do you keep current ID tie-break for determinism, widen top-k, prefer candidates present in more lists, or add a secondary score? Make the choice explicit.

### Block 3A — Primary route: Juan-owned consolidation artifact, 2–2.5h

Recommended files Juan may create or modify when ready:

- `src/hybrid_search.py`
- `src/chunked_search.py` if needed to expose chunk-level retrieval cleanly
- `tests/test_hybrid_search.py`
- `tests/test_chunked_search.py` only if chunk-level behavior changes
- `docs/eval-report.md`
- `data/golden_queries.jsonl` only if you decide not to use `data/corpus_v1/example_queries.jsonl` directly
- `docs/learning-log.md`

Suggested implementation steps, not mandatory exact structure:

1. Add or expose a comparison function that runs BM25, dense, Hybrid RRF, and Hybrid weighted on the same v1 query set.
2. Add metadata-filter support in the smallest shape that works: pass filter criteria, restrict candidate documents/chunks, and preserve enough metadata in outputs to debug why something matched.
3. Pick 8–12 representative v1 queries covering exact identifiers, numeric thresholds, supplier-specific questions, paraphrases, multi-document questions, and metadata-filtered questions.
4. Produce a baseline table in `docs/eval-report.md` with P@1, R@5, and MRR for the rows listed above. If you only complete a subset, label the table clearly as `subset baseline`.
5. Add tests for the metadata filter and for at least one edge case where filtering changes the ranking or candidate set.
6. Re-run the baseline commands and paste the real output into the learning log.

Do not implement reranking, source-cited answer generation, RAGAS/DeepEval, LangChain, API serving, or MCP today. Those belong to later gates.

Finally, fill in the learning questions for Day 7 from learning-log.md

### Block 3B — Fallback route: eval foundation without new retrieval code, 60–90m

Use this route if Boot.dev review or metric design consumes the day.

Still produce evidence:

1. Finish/reactivate Chapter 6 lessons.
2. Create or update `docs/eval-report.md` with the baseline table structure and known values from `docs/corpus-v1.md`.
3. Select at least 8 golden queries from `data/corpus_v1/example_queries.jsonl` and document why each was chosen.
4. Write the metadata-filter contract and tie-break decision as prose.
5. Defer code changes with a concrete next step.

The non-negotiable output is the eval foundation. Metadata filtering can move to Day 8 morning if needed, but the query set and table shape should exist before reranking.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. When does BM25 beat semantic search in procurement RAG?

   **Expected answer shape:** Exact identifiers and rare strings: supplier IDs, contract IDs, policy codes, currency amounts, dates, acronyms, and standards. Dense embeddings can blur distinct identifiers that look semantically related.

2. When does semantic search beat BM25?

   **Expected answer shape:** Paraphrased intent and vocabulary mismatch: “vendor vetting” vs. “supplier onboarding checks”, “availability” vs. “uptime”, scenario-style questions where exact words differ.

3. Why is hybrid search not guaranteed to improve every query?

   **Expected answer shape:** Fusion only combines available candidate signals. If the right item appears in one retriever and a distractor appears in the other, both can be one-signal candidates and tie. Top-k truncation and tie-break rules matter.

4. What does metadata filtering add beyond retrieval scoring?

   **Expected answer shape:** It constrains the search space using operational facts like document type, supplier, region, risk tag, or date. A semantically similar document in the wrong region/type can be irrelevant even if its text matches.

5. What do P@1, R@5, and MRR tell you?

   **Expected answer shape:** P@1 asks whether the top answer is relevant. R@5 asks how many known relevant documents appear in the first five. MRR rewards the first relevant result appearing early; rank 1 is best, rank 2 is half credit, etc.

6. How would you explain RRF vs weighted fusion to an interviewer?

   **Expected answer shape:** RRF combines rank positions and ignores raw scores, making it robust when score scales differ. Weighted fusion normalizes each retriever’s scores first and blends them with alpha, which is tunable but more sensitive to normalization and candidate-set quirks.

## Hermes review protocol

When Juan has a serious Day 7 attempt ready, ask Hermes:

> Review my Day 7 ProcureRAG hybrid consolidation. Check metadata filtering, the golden query source, eval-report baseline table, hybrid-vs-BM25-vs-dense comparisons, tests, and whether I can explain procurement-specific hybrid wins/failures in an AI Engineer interview. Do not rewrite the implementation for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan’s implementation.

## Stop condition

Day 7 is complete when there is consolidation evidence, not just a green test run:

1. Boot.dev Chapter 6 remaining work/review is recorded.
2. Tests / compile / smoke output is captured.
3. Metadata filtering is implemented or explicitly deferred with a written contract.
4. A golden query source is established (`data/corpus_v1/example_queries.jsonl` as canonical, or `data/golden_queries.jsonl` as curated subset).
5. `docs/eval-report.md` has a v1 baseline table with P@1, R@5, and MRR rows for lexical, dense, and hybrid methods, even if some values are still `TODO` with the exact follow-up command.
6. The learning log explains at least one hybrid win, one hybrid non-win/failure, and the remaining retrieval weakness.
7. Juan can explain why hybrid search matters for procurement corpora and why retrieval evaluation is required before moving to reranking.

Do not close HER-273 on passing tests alone. The eval table, golden-query source, and interview explanation are part of the acceptance criteria.
