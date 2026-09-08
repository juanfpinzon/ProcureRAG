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

## 2026-09-09 — Day 3: Keyword Search + BM25

### What I built or drafted

- Drafted Day 3 route in `docs/day-03-keyword-search-bm25.md`.
- Started from the Day 2 TF-IDF / inverted-index baseline.
- Added a dependency-free BM25 scoring path while keeping the TF-IDF path
  available for comparison.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Completed
- Exercises completed or attempted: Completed

### Retrieval artifact

- BM25 index fields added: `document_lengths` and
  `average_document_length` (`47.2` tokens across 10 documents).
- BM25 scoring uses the standard positive IDF variant with defaults
  `k1=1.5` and `b=0.75`, plus term-frequency saturation and document-length
  normalization.
- BM25 queries demonstrated:
  - `When can we skip the three-bid requirement?` → `SOP-001` (`4.7321`)
  - `Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?` →
    `POL-003` (`15.3740`)
  - `What approval is required for a €60,000 purchase order?` →
    `SOP-002` (`4.3560`), followed by `POL-001` (`3.7765`)
- Expected top document(s): `SOP-001` and `POL-003` ranked first as expected;
  the approval query was expected to favor `POL-001` from the Day 2 TF-IDF
  result.
- Actual top document(s) / score(s): BM25 preserved the expected top result
  for the three-bid and SaaS queries, but changed the approval-query ranking.

### What failed or was confusing

- BM25 ranked `SOP-002` above `POL-001` for the approval query because the
  existing tokenizer keeps stop words and `is` appears only in `SOP-002`.
  This is a useful reminder that BM25 is still lexical and that a tiny corpus
  can make an ordinary word look highly informative.

### What became clearer

- Raw TF-IDF increases the benefit of repeated terms linearly. BM25 limits
  that benefit with term-frequency saturation, so repeated mentions do not
  dominate indefinitely.
- Document length is compared with the corpus average, allowing BM25 to
  discount unusually long documents and slightly boost shorter ones.
- `k1` controls how quickly term frequency saturates, while `b` controls the
  strength of length normalization.

### What I can now explain in an interview

- BM25 is a lexical ranker that keeps IDF but replaces raw linear term
  frequency with a saturating function and normalizes for document length.
  It improves the fairness of keyword matching, but it cannot understand
  synonyms or meaning that is absent from the indexed tokens.

### What remains weak

- How to tune `k1` and `b` on a larger labeled corpus, and when stop-word or
  synonym handling should be added without damaging procurement identifiers.

### Next step

- Compare lexical retrieval failures with the next retrieval approach while
  keeping the TF-IDF and BM25 baselines available for evaluation.
