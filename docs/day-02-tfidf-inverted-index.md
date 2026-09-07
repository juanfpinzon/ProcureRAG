# Day 2 — TF-IDF + Inverted Index

Date: 2026-09-08 target; prepared 2026-09-07 14:11 CEST  
Linear: HER-263 — Tuesday loop: TF-IDF from course to ProcureRAG  
Project rule: course-driven building, with Juan owning the core implementation.

## Day 2 objective

Translate Boot.dev TF-IDF learning into a small, explainable ProcureRAG lexical retrieval artifact: a tiny inverted index over `data/corpus_v0/procurement_kb.jsonl` plus ranked retrieval for at least one query from `data/corpus_v0/example_queries.jsonl`.

Today is not about LangChain, embeddings, vector databases, or production RAG. It is about being able to explain why a document ranks above another using term frequency, inverse document frequency, and preprocessing choices.

## Starting state

Day 1 produced:

- 10-document synthetic procurement mini-corpus in `data/corpus_v0/procurement_kb.jsonl`.
- 8 example queries in `data/corpus_v0/example_queries.jsonl`.
- `src/preprocessing.py` with JSONL loading, whitespace normalization, original display text preservation, and lowercase retrieval tokens.
- `tests/test_preprocessing.py` with 3 passing tests.

Day 2 should reuse that preprocessing rather than rewriting it.

## Target evidence by end of day

- [ ] Boot.dev TF-IDF checkpoint completed or meaningfully attempted.
- [ ] Juan can explain TF, IDF, and TF-IDF without notes.
- [ ] A tiny inverted index exists or is sketched in ProcureRAG.
- [ ] At least one ranked query runs against the v0 corpus.
- [ ] A test or printed example shows the expected top document for one query.
- [ ] `docs/learning-log.md` gets a Day 2 entry.
- [ ] Juan can explain one ranking failure and how preprocessing affects it.

## Recommended 6-hour split

### Block 0 — Reactivate Day 1 context, 15–20m

Run/read:

```bash
uv run pytest -q
uv run python src/preprocessing.py
```

Then answer from memory:

1. What does `preprocess_text()` preserve for display?
2. What does it lowercase for retrieval?
3. Which tokens are procurement-sensitive and should not disappear?

### Block 1 — Course/exercises, 2–2.5h

Focus only on Boot.dev TF-IDF / inverted index material.

Capture notes in this shape:

| Concept | What it measures | Why it improves retrieval | Procurement example |
|---|---|---|---|
| term frequency | | | |
| document frequency | | | |
| inverse document frequency | | | |
| TF-IDF score | | | |
| inverted index | | | |

Minimum understanding target:

- TF: how much a term appears in one document.
- DF: how many documents contain a term.
- IDF: how rare/informative a term is across the corpus.
- TF-IDF: a term should matter more when it is frequent in a document and rare across the corpus.
- Inverted index: map token → documents/positions/counts so retrieval does not scan blindly later.

### Block 2 — Design the ProcureRAG retrieval contract, 45–60m

Before coding, write a short design note in this file or your own scratchpad:

- What is the input? Example: raw corpus rows from `load_data()`.

  **Answer:** The retrieval builder accepts the raw rows returned by `load_data()` and calls `preprocess_data()` internally. This keeps indexing tied to the existing preprocessing rules instead of duplicating them.

- What is indexed? Example: `id`, `normalized_text`, and `tokens` from `preprocess_data()`.

  **Answer:** For each document, index its `id`, `normalized_text`, and lowercase `tokens`. The current preprocessing combines the title and body, so both are searchable. The token counts and document length can be derived from `tokens` for scoring.

- What does the inverted index store? Example: token → document id → term count.

  **Answer:** Store `token → document_id → term_count`, for example `"approval" → {"POL-001": 2}`. Also keep the total document count and document frequency for each token so IDF can be calculated.

- What does query preprocessing reuse? Example: `preprocess_text(query)["tokens"]`.

  **Answer:** Query processing reuses `preprocess_text(query)["tokens"]`. This gives documents and queries the same lowercasing, whitespace normalization, punctuation handling, amount handling, and acronym handling.

- What does `search(query, top_k=3)` return? Example: ranked document ids with scores.

  **Answer:** It returns up to three matching documents ordered by descending TF-IDF score, for example `[{"id": "POL-001", "score": 2.41}]`. An empty or all-unknown query returns `[]`; documents with no matching terms are excluded. Ties should use a deterministic secondary order such as document ID.

Keep it dependency-free today. Python stdlib is enough.

### Block 3 — Juan-owned implementation attempt, 2–2.5h

Juan writes the first version. Hermes can review/debug after the attempt.

Recommended files Juan may create when ready:

- `src/retrieval.py`
- `tests/test_retrieval.py`

Suggested functions to design, not mandatory names:

- build an inverted index from preprocessed docs
- compute document frequency per token
- compute IDF per token
- score one query against documents
- return top-k ranked document ids

Do not overbuild classes today. A few small functions are enough if Juan can explain them.

Suggested first queries:

1. `What approval is required for a €60,000 purchase order?` → expected top: `POL-001`
2. `Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?` → expected top: `POL-003`
3. `When can we skip the three-bid requirement?` → expected top: `SOP-001` but likely harder because of synonym mismatch (`skip` vs `exceptions`). This is a good failure to explain.

### Block 4 — Evidence + interview drill, 45–60m

Fill the Day 2 entry in `docs/learning-log.md`.

Then answer without notes:

1. Why does IDF downweight common words?
2. Why can TF-IDF retrieve `POL-003` for `SOC 2 ISO 27001` better than raw keyword counting?
3. What is an inverted index, and why does it matter for scaling retrieval?
4. Why will TF-IDF fail on `skip the three-bid requirement` if the document says `exceptions are allowed`?
5. What preprocessing choice from Day 1 most affects Day 2 ranking?
6. How would BM25 improve or change plain TF-IDF later?

## Hermes review protocol

When Juan has a serious attempt ready, ask Hermes:

> Review my Day 2 ProcureRAG TF-IDF / inverted-index attempt. Check retrieval correctness, scoring math, edge cases, tests, and whether I can defend the ranking behavior in an interview. Do not rewrite it for me unless I ask for hints.

Hermes should review, quiz, and debug — not replace the core implementation.

## Stop condition

Day 2 is complete when there is a small, explainable lexical retrieval artifact that ranks at least one corpus query correctly and a learning-log entry that explains TF-IDF vs raw keyword matching. It does not need to be production-ready. It needs to be understood.
