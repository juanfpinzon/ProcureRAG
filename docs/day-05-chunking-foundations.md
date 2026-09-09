# Day 5 — Chunking Foundations for ProcureRAG

Date: 2026-09-11 target; started 2026-09-09 10:28 CEST; corrected 2026-09-09 after Juan’s course-sequencing question  
Linear: HER-266 — Day 5 loop: Boot.dev Ch5 chunking foundations  
Related gate: HER-261 — Week 1 gate: Boot.dev foundations + retrieval basics  
Project rule: course-driven building, with Juan owning the core retrieval implementation.

## Course target for today

Boot.dev RAG course target:

- **Primary chapter:** Chapter 5 — **Chunking**
- **Minimum lessons for today:**
  1. Chunking
  2. Chunk Overlap
  3. Semantic Chunking
- **Good 6-hour target:**
  4. Chunked Semantic Embeddings
  5. Chunked Semantic Search
- **Stretch only if energy is high:**
  6. Chunked Edge Cases
- **Read-only / defer unless the course requires it today:**
  7. ColBERT
  8. Late Chunking

Do **not** make Chapter 6 Hybrid Search the main target today. Hybrid search comes after chunking because, in a real RAG system, retrieval usually happens over chunks/snippets rather than entire long documents.

## Day 5 objective

Move from document-level retrieval to chunk-level retrieval. By the end of the day, you should understand why RAG systems chunk documents, how overlap preserves context, why sentence/semantic boundaries are safer than arbitrary splits, and how chunk-level retrieval changes evidence quality.

This is not a vector-database or LangChain day. The portfolio artifact should stay small, inspectable, and explainable.

## Starting state

Day 4 produced:

- `src/retrieval.py` with dependency-free TF-IDF and BM25 retrieval paths over whole documents.
- `src/semantic_search.py` with dense retrieval over whole documents using cosine similarity and `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`.
- `tests/test_retrieval.py` and `tests/test_semantic_search.py` covering the current learning artifacts.
- `docs/learning-log.md` with Day 4 evidence showing semantic search fixed the `vendor vetting` / `supplier due diligence` paraphrase miss where TF-IDF and BM25 ranked `SOP-002` first.

The next learning edge is: **whole-document retrieval is too coarse once documents get long**. RAG needs relevant snippets, not just relevant files.

## Target evidence by end of day

- [ ] Boot.dev Chapter 5 Chunking lessons 1–3 completed or meaningfully attempted.
- [ ] If energy allows, lessons 4–5 completed or meaningfully attempted.
- [ ] Juan can explain why chunking improves RAG context quality.
- [ ] Juan can explain the trade-off between chunk size and retrieval precision/recall.
- [ ] Juan can explain why overlap helps and why too much overlap can create duplication/noise.
- [ ] A small ProcureRAG chunking artifact exists or is sketched.
- [ ] If ready: chunked semantic retrieval compares whole-document vs chunk-level results for at least 2 procurement questions.
- [ ] `docs/learning-log.md` gets a Day 5 entry with exact Boot.dev lessons, artifact evidence, confusion, interview explanation, weaknesses, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline, 20–30m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python src/semantic_search.py
```

Then answer from memory:

1. What is the current retrieval unit?  
   **Expected:** A whole document from `procurement_kb.jsonl`.
2. Why is whole-document retrieval acceptable for the tiny corpus but not enough for realistic policies/contracts?  
   **Expected:** Real documents are long; the answer may live in one paragraph or clause, and passing the whole document can waste context or bury the relevant sentence.
3. Why does chunking belong before hybrid search?  
   **Expected:** Hybrid combines retrieval signals, but both lexical and dense signals should usually rank retrievable chunks/snippets, not only whole documents.

### Block 1 — Boot.dev Chapter 5 lessons, 2–2.5h

Primary target:

1. **Chunking** — why split documents into smaller retrievable units.
2. **Chunk Overlap** — why neighbouring chunks repeat a little context.
3. **Semantic Chunking** — why sentence/paragraph boundaries preserve meaning better than arbitrary token cuts.

If the first three lessons are clear, continue:

4. **Chunked Semantic Embeddings** — embed chunks rather than whole documents.
5. **Chunked Semantic Search** — retrieve the best chunks for a query.

Stretch:

6. **Chunked Edge Cases** — note the edge cases, but do not overbuild today.

Defer unless the course forces it:

7. **ColBERT**
8. **Late Chunking**

Capture notes in this shape:

| Lesson | Plain-English takeaway | Procurement example | Implementation implication |
|---|---|---|---|
| Chunking | | | |
| Chunk Overlap | | | |
| Semantic Chunking | | | |
| Chunked Semantic Embeddings | | | |
| Chunked Semantic Search | | | |

Minimum understanding target:

- A chunk is the retrieval unit passed into ranking and later into the LLM context.
- Smaller chunks improve precision but can lose context.
- Larger chunks preserve context but can dilute retrieval and waste prompt budget.
- Overlap helps preserve context across boundaries, but too much overlap creates duplicates.
- Semantic/sentence chunking avoids splitting a clause or sentence in a way that changes meaning.

### Block 2 — Design the chunking contract, 45–60m

Before coding, write a short design note in this file or your scratchpad:

- What should a chunk contain?

  **Suggested answer:** `chunk_id`, `document_id`, `chunk_index`, `text`, and lightweight metadata copied from the source document when useful.

- What should the first chunking function do?

  **Suggested answer:** Start with a simple sentence-aware chunker. Given text, split into sentence groups with a configurable maximum sentence count and optional overlap.

- What should stay unchanged?

  **Suggested answer:** Keep the existing whole-document TF-IDF, BM25, and semantic functions visible. Day 5 should add chunk-level behavior, not erase the Week 1 baseline.

- What file names would be understandable?

  **Suggested answer:** If ready, use `src/chunking.py` and `tests/test_chunking.py`. If you add retrieval over chunks, either keep it in a small `src/chunked_search.py` file or add a clearly separated chunked section in `src/semantic_search.py`.

- What is enough for Day 5?

  **Suggested answer:** A chunking function with tests plus one small chunk-level retrieval comparison is enough. Do not add production chunk stores, metadata filters, rerankers, async pipelines, or a UI today.

### Block 3A — Primary route: Juan-owned chunking artifact, 1.5–2h

Recommended files Juan may create or modify when ready:

- `src/chunking.py`
- `tests/test_chunking.py`
- optionally `src/chunked_search.py` or a small chunked section in `src/semantic_search.py`
- `docs/learning-log.md`

Suggested implementation steps, not mandatory exact structure:

1. Add a sentence splitter for policy/contract text.
2. Add a `chunk_text(text, max_sentences=3, overlap=1)` function.
3. Preserve source metadata: document id, chunk index, and chunk text.
4. Add tests for no overlap, overlap, short text, empty text, and deterministic chunk ids.
5. If ready, embed/search chunks and compare against whole-document semantic retrieval for 2 queries.
6. Record what changed in the Day 5 learning log.

Do not overfit to the tiny corpus. The point is to understand the retrieval unit, not to claim production-ready chunking.

### Block 3B — Fallback route: chunking design only, 60–90m

Use this route if the course material takes most of the day.

Still produce evidence:

1. Finish lessons 1–3.
2. Write the chunk schema in the learning log or this doc.
3. List 3 procurement examples where whole-document retrieval is too coarse:
   - a 50-page MSA with one renewal clause;
   - a security policy with one SOC 2 exception paragraph;
   - an invoice SOP where the `3%` variance rule appears inside one section.
4. Defer implementation with a concrete next step.

This fallback can count only if the learning log names the exact lessons completed and the next implementation step is clear.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. Why do RAG systems chunk documents?

   **Expected answer shape:** Because the LLM should receive the relevant passage, not a huge document. Chunking improves retrieval precision and controls prompt context size.

2. What is the chunk-size trade-off?

   **Expected answer shape:** Small chunks are precise but may miss surrounding context. Large chunks preserve context but can dilute retrieval and waste tokens.

3. Why use overlap?

   **Expected answer shape:** Overlap keeps important context when a relevant sentence sits near a chunk boundary. Too much overlap duplicates content and can crowd out diversity.

4. Why does sentence or semantic chunking help?

   **Expected answer shape:** It preserves complete thoughts. Arbitrary token cuts can split clauses, definitions, or exceptions in ways that damage retrieval and answer grounding.

5. Why defer hybrid search until after chunking?

   **Expected answer shape:** Hybrid search combines lexical and dense signals, but the unit being ranked should be right first. If the system ranks overly broad whole documents, hybrid scoring may improve ranking while still returning poor context.

6. What should Week 2 build next?

   **Expected answer shape:** First finish chunk-level retrieval, then compare lexical, semantic, and hybrid search over chunks with evaluation evidence. After that, move toward source-cited answer generation.

## Hermes review protocol

When Juan has a serious Day 5 attempt ready, ask Hermes:

> Review my Day 5 ProcureRAG chunking attempt. Check the chunking design, tests, chunk metadata, whole-document vs chunk-level retrieval comparison, and whether I can explain chunk size, overlap, and semantic chunking in an AI Engineer interview. Do not rewrite the implementation for me unless I ask for hints.

If Juan took the fallback route, ask:

> Review my Day 5 ProcureRAG chunking notes. Check whether the exact Boot.dev lessons are reflected, whether the chunking design is defensible, and whether the next implementation step is concrete.

Hermes should review, quiz, and debug — not replace the core implementation.

## Stop condition

Day 5 is complete when there is chunking evidence, not just course progress:

1. exact Boot.dev Chapter 5 lessons completed/attempted are recorded;
2. tests / compile / smoke output is captured;
3. a chunking artifact exists or a clearly justified chunking design fallback is recorded;
4. the learning log explains chunk size, overlap, semantic chunking, one confusion/failure, remaining weakness, and the next step;
5. Juan can explain why chunking comes before hybrid search in this learning sequence.

Do not close HER-266 or HER-261 on passing tests alone. The learning evidence and explanation drill are part of the acceptance criteria.
