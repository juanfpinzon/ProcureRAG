# Day 4 — Semantic Search Checkpoint

Date: 2026-09-10 target; started 2026-09-08 14:53 CEST  
Linear: HER-265 — Thursday loop: semantic search checkpoint  
Project rule: course-driven building, with Juan owning the core retrieval implementation.

## Day 4 objective

Move from lexical retrieval into semantic-search thinking without losing the Day 2/3 lexical baselines. The goal is not to install a production vector database yet. The goal is to understand what an embedding represents, how cosine similarity ranks vectors, why dense retrieval can find meaning beyond exact token overlap, and where dense retrieval can still fail.

Today has two valid routes:

1. **Primary route — semantic search if course pace allows:** build or sketch a small embedding/cosine retrieval artifact in ProcureRAG and compare it against TF-IDF and BM25.
2. **Fallback route — lexical reinforcement if semantic search is premature:** strengthen the lexical baseline with stop-word/synonym failure analysis and clearer tests/docs, then carry those observations into dense retrieval tomorrow.

Either route should produce interview-facing evidence. Course completion alone does not close the day.

## Starting state

Day 3 produced:

- `src/retrieval.py` with dependency-free TF-IDF and BM25 ranking paths.
- `tests/test_retrieval.py` with coverage for index construction, TF-IDF scoring, BM25 scoring, empty/unknown queries, top-k limits, and deterministic tie-breaking.
- `docs/learning-log.md` with Day 3 evidence explaining BM25 term-frequency saturation, document-length normalization, and the `SOP-002` vs `POL-001` stop-word miss.
- Known baseline behavior:
  - TF-IDF top-1 is 8/8 on `data/corpus_v0/example_queries.jsonl`.
  - BM25 top-1 is 7/8; its miss is explainable and useful.

Keep both lexical paths visible. Semantic search should be compared against them, not used as a replacement before you understand the trade-offs.

## Target evidence by end of day

- [ ] Semantic-search / embeddings course checkpoint completed or meaningfully attempted.
- [ ] Juan can explain embeddings as numeric representations that place similar meanings near each other.
- [ ] Juan can explain cosine similarity without hand-waving.
- [ ] If ready: a small embedding/cosine retrieval artifact exists in ProcureRAG.
- [ ] If ready: at least three example queries compare TF-IDF, BM25, and semantic search.
- [ ] If not ready: lexical failure cases are documented clearly enough to motivate dense retrieval.
- [ ] `docs/learning-log.md` gets a Day 4 entry with evidence, confusion, and interview explanation.
- [ ] Juan can state when semantic search fails and why hybrid retrieval is needed.

## Recommended 6-hour split

### Block 0 — Reactivate lexical baseline, 20–30m

Run:

```bash
uv run pytest -q
uv run python src/retrieval.py
```

Then answer from memory:

1. What does BM25 fix compared with raw TF-IDF?
2. Why did BM25 rank `SOP-002` above `POL-001` for the €60,000 approval query?
3. What kind of procurement query will lexical retrieval struggle with even after BM25?
4. Why should semantic search be compared against lexical baselines instead of replacing them immediately?

### Block 1 — Course/exercises, 2–2.5h

Focus on the semantic search / embeddings checkpoint.

Capture notes in this shape:

| Concept | Plain-English meaning | Retrieval use | Procurement example |
|---|---|---|---|
| embedding | | | |
| vector dimension | | | |
| cosine similarity | | | |
| nearest neighbor | | | |
| dense retrieval | | | |
| lexical retrieval | | | |
| hybrid retrieval | | | |

Minimum understanding target:

- An embedding is a numeric vector representing text in a way that can preserve some semantic similarity.
- Cosine similarity compares vector direction, not raw token overlap.
- Dense retrieval can help with synonyms and paraphrases, such as “vendor vetting” matching “supplier due diligence.”
- Dense retrieval can still fail on exact identifiers, numbers, acronyms, legal clauses, and domain-specific constraints.
- Hybrid retrieval exists because lexical and dense methods fail in different ways.

### Block 2 — Design the semantic retrieval contract, 45–60m

Before coding, write a short design note in this file or your scratchpad:

- Which lexical functions remain the baseline?

  **Suggested answer:** Keep `search(index, query, top_k=3)` for TF-IDF and `search_bm25(index, query, top_k=3)` for BM25. Do not change their behavior to make semantic search easier.

- What new file or function names would be understandable?

  **Suggested answer:** If you are ready for code, use a clearly separate path such as `src/semantic_search.py` or explicit functions like `embed_text()`, `cosine_similarity()`, `score_query_semantic()`, and `search_semantic()`. Keep it small and explainable.

- What should semantic search return?

  **Suggested answer:** Same outer shape as the lexical search functions: `[{"id": "POL-002", "score": 0.83}]`, sorted by descending score and then document id for deterministic ties.

- What is the formula in plain English?

  **Suggested answer:** Convert the query and each document into vectors, compare the query vector with each document vector using cosine similarity, then rank documents by similarity.

- What dependency policy should apply today?

  **Suggested answer:** Prefer the smallest path that supports learning. If the course gives a local embedding approach, use it. If it requires a hosted API or large package, first implement/verify cosine similarity and document the dependency choice before installing anything.

### Block 3A — Primary route: Juan-owned semantic attempt, 2–2.5h

Only take this route if the course checkpoint makes embeddings/cosine retrieval concrete enough.

Recommended files Juan may create or modify when ready:

- `src/semantic_search.py` or a small isolated section in `src/retrieval.py`
- `tests/test_semantic_search.py` or additional retrieval tests
- optionally `docs/learning-log.md` after the attempt

Suggested implementation steps, not mandatory exact structure:

1. Add a tiny, inspectable `cosine_similarity()` helper and tests for identical, orthogonal, and zero-vector cases.
2. Decide how embeddings are represented today: course-provided vectors, a local model, or a deliberately tiny toy vector map for understanding only. (small general purpose model from sentence transformes eg: all-MiniLM-L6-v2, if there is a more procurement tailored public model available let me know)
3. Add a function that builds document vectors for the existing 10-document corpus.
4. Add semantic scoring/search that returns the same result shape as TF-IDF and BM25.
5. Compare at least three queries across TF-IDF, BM25, and semantic search.
6. Record one case where semantic search helps and one case where lexical retrieval is safer.

Do not overbuild vector stores, LangChain wrappers, async pipelines, caching, or production infrastructure today. If you cannot explain every line, the artifact is too large for Day 4.

### Block 3B — Fallback route: lexical reinforcement, 1.5–2h

Use this route if the semantic course material is not ready yet.

Focus on turning the Day 3 stop-word/synonym issue into evidence:

1. Write a short note listing lexical failure patterns visible in this corpus.
2. Add or sketch queries that are likely to fail with TF-IDF/BM25 because of synonyms or paraphrases.
3. Compare exact-token-sensitive queries where lexical retrieval should remain strong: `SOC 2`, `ISO 27001`, `€60,000`, `3%`, `Acme Logistics S.L.`.
4. Explain why dense retrieval may help the synonym cases but may blur exact identifiers.
5. Leave a clear next-step note for dense/hybrid retrieval.

This fallback still counts as progress if the learning log explains why semantic retrieval is the next move.

### Block 4 — Comparison + interview drill, 45–60m

Use at least these comparison queries:

1. `What checks are needed before onboarding a new high-risk supplier?`

   **Expected document:** `POL-002`  
   **Right answer:** Complete KYC, sanctions screening, tax validation, and bank-account verification; high-risk suppliers also require enhanced due diligence and Legal approval.

2. `What vendor vetting is required before working with a risky supplier?`

   **Expected document:** `POL-002`  
   **Right answer:** Complete supplier due diligence before issuing a PO; a high-risk supplier requires enhanced due diligence and Legal approval. This is the synonym/paraphrase stress case for semantic search.

3. `Can Northstar use company data for model training?`

   **Expected document:** `CONTRACT-002`  
   **Right answer:** No, not without written approval under the DPA.

4. `Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?`

   **Expected document:** `POL-003`  
   **Right answer:** SaaS suppliers handling company data must provide ISO 27001 certification or SOC 2 Type II evidence. This is the exact-identifier case where lexical retrieval should remain strong.

5. `What happens when invoice price variance is over 3%?`

   **Expected document:** `SOP-002`  
   **Right answer:** A price variance over 3% requires buyer review, and payment waits until mismatch resolution is documented. This is the numeric/domain-specific case where lexical precision matters.

Fill the Day 4 entry in `docs/learning-log.md`.

Then answer without notes:

1. What is an embedding?

   **Answer:** An embedding is a numeric vector representation of text. Texts with similar meaning should ideally have vectors that are close together, even if they do not share the exact same words.

2. What does cosine similarity compare?

   **Answer:** Cosine similarity compares the direction of two vectors. In retrieval, it estimates whether a query vector points in a similar semantic direction to a document vector.

3. What problem can semantic search solve that BM25 cannot?

   **Answer:** Semantic search can match paraphrases or synonyms when the same idea is expressed with different words, such as “vendor vetting” and “supplier due diligence.” BM25 needs token overlap.

4. Why can semantic search be worse than lexical search?

   **Answer:** It can blur exact terms, numbers, acronyms, supplier names, dates, and policy constraints. For procurement, exact identifiers like `SOC 2`, `€60,000`, `3%`, or a supplier legal name can matter more than general semantic similarity.

5. Why does hybrid retrieval exist?

   **Answer:** Hybrid retrieval combines lexical precision with dense semantic matching. Lexical search protects exact terms and identifiers; dense retrieval helps with synonyms and intent. Together they reduce each method’s blind spots.

6. How would you explain dense vs lexical retrieval to a recruiter in 60 seconds?

   **Answer:** Lexical retrieval ranks documents by exact token overlap and term statistics, so it is fast, transparent, and strong for exact identifiers. Dense retrieval converts text into embedding vectors and ranks by vector similarity, so it can match meaning even when words differ. Dense retrieval is useful for paraphrases, but it can miss or blur exact procurement constraints, which is why a practical RAG system often compares or combines lexical and dense retrieval.

## Hermes review protocol

When Juan has a serious attempt ready, ask Hermes:

> Review my Day 4 ProcureRAG semantic search attempt. Check vector math, retrieval behavior, comparison against TF-IDF/BM25, tests, and whether I can defend dense vs lexical vs hybrid retrieval in an interview. Do not rewrite it for me unless I ask for hints.

If Juan took the fallback route, ask:

> Review my Day 4 ProcureRAG lexical-to-semantic bridge notes. Check whether the failure cases actually motivate semantic/hybrid retrieval and whether the next implementation step is well scoped.

Hermes should review, quiz, and debug — not replace the core implementation.

## Stop condition

Day 4 is complete when there is either:

1. a small, explainable semantic/cosine retrieval artifact with tests or smoke evidence, plus comparison against TF-IDF/BM25; **or**
2. a documented lexical failure analysis that cleanly motivates semantic retrieval, if the course material was not ready yet.

In both cases, the learning log must include course progress, repo evidence, one confusion/failure, one interview explanation, and the next weakness. Do not close the day on course progress alone.
