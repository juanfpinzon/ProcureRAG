# Day 3 — Keyword Search + BM25

Date: 2026-09-09 target; started 2026-09-08 11:19 CEST  
Linear: HER-264 — Wednesday loop: keyword search and BM25  
Project rule: course-driven building, with Juan owning the core retrieval implementation.

## Day 3 objective

Turn the Day 2 TF-IDF artifact into a more defensible lexical retriever by adding a BM25-style scoring path and explaining why document-length normalization, term saturation, and tunable relevance parameters improve plain TF-IDF.

Today is still not about embeddings, vector databases, LangChain, rerankers, or production RAG. It is about being able to explain BM25 from first principles and compare it against the raw TF-IDF ranker you already built.

## Starting state

Day 2 produced:

- `src/retrieval.py` with a dependency-free inverted index, raw TF-IDF scoring, and deterministic top-k search.
- `tests/test_retrieval.py` with coverage for index construction, query TF, document TF, IDF, empty/unknown queries, top-k limits, and deterministic tie-breaking.
- Improved tokenization in `src/preprocessing.py` for currency amounts, percentages, dates, hyphenated terms, and dotted acronyms.
- 8/8 example queries rank the expected document first under the current TF-IDF smoke check.

Day 3 should extend this artifact rather than replacing it. Keep the TF-IDF path visible so you can compare both methods in an interview.

## Target evidence by end of day

- [ ] Boot.dev keyword search / BM25 checkpoint completed or meaningfully attempted.
- [ ] Juan can explain why raw TF-IDF can over-reward long documents.
- [ ] The index stores enough document-length information to support BM25.
- [ ] A BM25 scoring function exists or is sketched in ProcureRAG.
- [ ] At least three corpus queries can be run through both TF-IDF and BM25.
- [ ] One test or printed comparison demonstrates the top document for BM25.
- [ ] `docs/learning-log.md` gets a Day 3 entry.
- [ ] Juan can explain one ranking difference or non-difference between TF-IDF and BM25.

## Recommended 6-hour split

### Block 0 — Reactivate Day 2 context, 20–30m

Run:

```bash
uv run pytest -q
uv run python src/retrieval.py
```

Then answer from memory:

1. What does the inverted index store today?
2. Where is document frequency calculated?
3. Why does a term present in every document contribute no TF-IDF signal?
4. What exactly is missing for document-length normalization?

### Block 1 — Course/exercises, 2–2.5h

Focus only on Boot.dev keyword search / BM25 material.

Capture notes in this shape:

| Concept | What it measures | Why it improves retrieval | Procurement example |
|---|---|---|---|
| keyword search | | | |
| document length | | | |
| average document length | | | |
| term saturation | | | |
| BM25 `k1` | | | |
| BM25 `b` | | | |

Minimum understanding target:

- Keyword search ranks documents from lexical overlap between query terms and indexed document terms.
- Raw TF-IDF can reward repeated terms linearly, which may favor longer documents.
- BM25 keeps IDF but adds term-frequency saturation, so repeated terms help less after a point.
- BM25 normalizes by document length relative to average document length.
- `k1` controls how quickly term frequency saturates.
- `b` controls how strongly document length normalization applies.

### Block 2 — Design the BM25 extension contract, 45–60m

Before coding, write a short design note in this file or your scratchpad:

- What extra index fields are needed?

  **Suggested answer:** Keep the existing `documents`, `inverted_index`, `document_frequency`, and `document_count`, then add `document_lengths` and `average_document_length`. Document length can be `len(document["tokens"])`.

- Which function remains the TF-IDF baseline?

  **Suggested answer:** Keep `score_query(index, query)` and `search(index, query, top_k=3)` as the Day 2 baseline. Add new BM25-specific functions rather than changing the meaning of existing TF-IDF names.

- What BM25 function names are understandable?

  **Suggested answer:** `score_query_bm25(index, query, k1=1.5, b=0.75)` and `search_bm25(index, query, top_k=3, k1=1.5, b=0.75)` are explicit enough for a learning artifact.

- What should BM25 return?

  **Suggested answer:** Same shape as TF-IDF search: `[{"id": "POL-001", "score": 3.21}]`, sorted by descending score and then document id for deterministic ties.

- What is the formula in plain English?

  **Suggested answer:** For each query token that appears in the corpus, add an IDF-weighted contribution for each matching document. The contribution increases with document term frequency, but saturates based on `k1`, and is discounted or boosted by how long the document is compared with the average length using `b`.

Keep it dependency-free today. Python stdlib is enough.

### Block 3 — Juan-owned BM25 implementation attempt, 2–2.5h

Juan writes the first version. Hermes can review/debug after the attempt.

Recommended files Juan may modify when ready:

- `src/retrieval.py`
- `tests/test_retrieval.py`

Suggested implementation steps, not mandatory exact structure:

1. Add document lengths and average document length to `build_index()`.
2. Add a small `calculate_bm25_idf(document_count, document_frequency)` helper if useful.
3. Add `score_query_bm25()` using the existing inverted index postings.
4. Add `search_bm25()` with the same top-k and deterministic tie behavior as `search()`.
5. Add tests for length fields, BM25 returning expected top documents, empty/unknown queries, and top-k behavior.
6. Add a comparison smoke print or tiny script that shows TF-IDF vs BM25 top results for a few example queries.

Do not overbuild ranking configuration, classes, pipelines, or package structure today. A few small functions are enough if Juan can explain every line.

### Block 4 — Comparison + interview drill, 45–60m

Run both retrieval methods against at least these queries:

1. `What approval is required for a €60,000 purchase order?` → expected top: `POL-001`
2. `Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?` → expected top: `POL-003`
3. `When can we skip the three-bid requirement?` → expected top: `SOP-001`
4. Optional stress query: `approval supplier procurement data` — inspect whether long/common policy docs get too much credit.

Fill the Day 3 entry in `docs/learning-log.md`.

Then answer without notes:

1. What problem does BM25 solve that raw TF-IDF does not?
2. Why should term frequency saturate instead of increasing linearly forever?
3. What does document length normalization protect against?
4. What do `k1` and `b` control?
5. Why is BM25 still lexical, not semantic?
6. What kind of query would still fail even after BM25?
7. How would you explain BM25 to a recruiter in 60 seconds?

## Hermes review protocol

When Juan has a serious attempt ready, ask Hermes:

> Review my Day 3 ProcureRAG BM25 attempt. Check scoring math, index fields, tests, retrieval behavior, and whether I can defend BM25 vs TF-IDF in an interview. Do not rewrite it for me unless I ask for hints.

Hermes should review, quiz, and debug — not replace the core implementation.

## Stop condition

Day 3 is complete when there is a small, explainable BM25 or BM25-like lexical retrieval artifact, at least one tested BM25 query ranks the expected document first, and the learning log explains BM25 vs raw TF-IDF. It does not need to beat TF-IDF on every tiny-corpus query. It needs to be understood.
