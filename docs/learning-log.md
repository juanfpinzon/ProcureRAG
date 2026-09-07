# ProcureRAG Learning Log

Use one entry per study/build day. Keep entries short, evidence-based, and interview-facing.

## 2026-09-07 — Day 1: Preprocessing + Corpus Scope

### What I built or drafted

- Preprocessing module that loads JSONL corpus rows, combines title + text, normalizes whitespace, preserves display text casing, and emits lowercase retrieval tokens.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Preprocessing chapter completed
- Exercises completed or attempted: Completed in Boot.dev

### Corpus decision

- Corpus v0 selected: synthetic procurement KB mini-corpus
- Why this corpus: small, non-confidential, inspectable, and suitable for learning preprocessing/retrieval behavior from first principles
- Expected query types: approval thresholds, supplier onboarding, SaaS security requirements, logistics RFP scoring, contract-specific lookups, invoice mismatches

### What failed or was confusing

- Deciding whether preprocessing should preserve casing or lowercase everything.

### What became clearer

- Retrieval tokens and display/audit text can have different normalization contracts.

### What I can now explain in an interview

- Why lowercasing helps lexical matching but can damage display fidelity and acronym/entity traceability.

### What remains weak

- Tokenization decisions around punctuation, legal suffixes like Ltd./Inc., stop-word removal, and whether punctuation tokens should remain for TF-IDF.

### Next step

- Move into TF-IDF / inverted index work for HER-263 after preprocessing v0 is understandable.

## 2026-09-08 — Day 2: TF-IDF + Inverted Index

### What I built or drafted

- Added a dependency-free inverted index and raw TF-IDF search in `src/retrieval.py`.
- Reused the Day 1 preprocessing for both documents and queries.
- Improved tokenization for currency amounts, percentages, dates, hyphenated terms, and dotted acronyms.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Completed 
- Exercises completed or attempted: Completed

### Retrieval artifact

- Indexed corpus: 10 documents from `data/corpus_v0/procurement_kb.jsonl`
- Query demonstrated: `What approval is required for a €60,000 purchase order?`
- Expected top document: `POL-001`
- Actual top document: `POL-001` with score `6.4140`

### What failed or was confusing

- A term present in every document has IDF `0`, so it adds no ranking signal and is excluded from results.
- Raw TF-IDF does not understand synonyms; `skip` and `exceptions` only work when other shared terms provide enough evidence.

### What became clearer

- Document frequency counts documents containing a term, not every occurrence of the term.
- IDF makes rare procurement terms such as standards, amounts, and supplier names more informative than common words.
- Matching preprocessing rules are required for a query token and document token to meet.

### What I can now explain in an interview

- The inverted index maps each token to document term counts, and TF-IDF combines document/query frequency with corpus-wide rarity to rank matches.

### What remains weak

- Document-length normalization and the differences between raw TF-IDF and BM25 still need practice.

### Next step

- Practice explaining the ranking and the `skip` versus `exceptions` limitation before moving to BM25 or the next retrieval block.
