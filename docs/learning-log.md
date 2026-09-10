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

## 2026-09-10 — Day 4: Semantic Search Checkpoint

### What I built or drafted

- Drafted Day 4 route in `docs/day-04-semantic-search-checkpoint.md`.
- Starting from the Day 3 TF-IDF + BM25 lexical baseline.
- Added `src/semantic_search.py` with an explainable cosine-similarity
  retriever, using the small
  `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` model.
- Kept model loading separate from retrieval functions so unit tests can use
  deterministic fake vectors without downloading a model.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Completed
- Exercises completed or attempted: Completed for the semantic-search path

### Retrieval artifact or bridge evidence

- Route taken: Primary semantic artifact
- Model: `multi-qa-MiniLM-L6-cos-v1`, 384-dimensional normalized embeddings
- Query demonstrated: `What vendor vetting is required before working with a risky supplier?`
- Expected relevant document: `POL-002`
- TF-IDF top-1: `SOP-002` (`3.5066`)
- BM25 top-1: `SOP-002` (`3.2488`)
- Semantic top-1: `POL-002` (`0.6284`)
- Five-query top-1 comparison:
  - high-risk supplier checks → `POL-002` / `POL-002` / `POL-002`
  - vendor vetting paraphrase → `SOP-002` / `SOP-002` / `POL-002`
  - Northstar model-training use → `CONTRACT-002` / `CONTRACT-002` / `CONTRACT-002`
  - SOC 2 / ISO 27001 evidence → `POL-003` / `POL-003` / `POL-003`
  - invoice variance over `3%` → `SOP-002` / `SOP-002` / `SOP-002`
  - Result order in each row: TF-IDF / BM25 / semantic
- Evidence commands:
  - `./.venv/bin/pytest -q` → `22 passed`
  - `./.venv/bin/python -m compileall -q src tests` → passed
  - `./.venv/bin/python src/semantic_search.py` → comparison output above

### What failed or was confusing

- Dense retrieval returns a score for every document, even when the query and
  document share no exact token. That is useful for paraphrases, but it also
  means a dense score should not be treated as proof that an exact identifier,
  amount, acronym, or legal name is present.

### What became clearer

- Normalized embeddings make cosine similarity easy to interpret as vector
  direction: documents pointing in a similar semantic direction rank higher.
  This complements lexical precision rather than replacing it.

### What I can now explain in an interview

- An embedding is a numeric vector representation of text where related
  meanings should be placed near one another. Cosine similarity compares the
  direction of the query vector with each document vector, so a paraphrase can
  match even when the exact words differ. TF-IDF and BM25 remain stronger for
  exact procurement identifiers, standards, percentages, amounts, and legal
  names. Hybrid retrieval combines both signals because dense and lexical
  retrieval fail in different ways.

### What remains weak

- Evaluating an embedding model on a larger labeled procurement set, handling
  long documents, and choosing a defensible hybrid-scoring strategy remain
  open weaknesses.

### Next step

- Move to Boot.dev Chapter 5 — Chunking before making hybrid search the main
  build target. Whole-document TF-IDF, BM25, and semantic retrieval are now
  enough to motivate chunk-level retrieval; hybrid search belongs after the
  retrieval unit is clear.

## 2026-09-11 — Day 5: Chunking Foundations

### What I built or drafted

- Drafted Day 5 route in `docs/day-05-chunking-foundations.md`.
- Starting from the Day 4 semantic-search artifact and the Day 2/3 lexical baselines.
- Artifact attempted or built: Block 3A, `src/chunking.py` (sentence splitter +
  overlapping sentence-window chunker + document/corpus chunk metadata),
  `tests/test_chunking.py`, `src/chunked_search.py` (chunk-level semantic
  index/search + whole-document vs chunk-level comparison), and
  `tests/test_chunked_search.py`.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Chapter 5 — Chunking - Completed
  - Minimum target: lessons 1–3 (`Chunking`, `Chunk Overlap`, `Semantic Chunking`)
  - Good 6-hour target: lessons 4–5 (`Chunked Semantic Embeddings`, `Chunked Semantic Search`)
  - Stretch: lesson 6 (`Chunked Edge Cases`)
  - Defer/read-only unless required today: lessons 7–8 (`ColBERT`, `Late Chunking`)
- Exercises completed or attempted: Completed (3A, chunking artifact)

### Chunking artifact / retrieval evidence

- Route taken: Chunking artifact + chunked semantic retrieval (Block 3A, both
  the required chunker and the Good-6-hour-target chunk-level search).
- Chunking strategy: sentence-aware sliding window, not arbitrary character/
  token cuts. `split_into_sentences` splits on sentence-ending punctuation
  followed by whitespace + a capital letter (a heuristic that correctly
  avoids splitting mid-abbreviation for this corpus, e.g. `"Ltd. may process"`
  stays one sentence because `"may"` isn't capitalized, while `"approval.
  Supplier names"` correctly splits). `chunk_sentences(sentences,
  max_sentences, overlap)` then slides a window over the sentence list with
  step = `max_sentences - overlap`, stopping as soon as a window reaches the
  last sentence (avoids a redundant trailing chunk on short documents).
- Chunk metadata shape: `{chunk_id, document_id, chunk_index, text, title}`.
  `chunk_id` is deterministic (`f"{document_id}::chunk-{chunk_index}"`), not
  random, so re-chunking the same document produces identical ids.
- Whole-document vs chunk-level comparison, if attempted: yes, in
  `src/chunked_search.py::main()`, for 2 queries. Both granularities returned
  the correct expected document as the top result:
  - `"What happens when invoice price variance is over 3%?"` → `SOP-002`
    (whole-doc score 0.5687 vs chunk `SOP-002::chunk-0` score 0.5951 — the
    chunk dropped one trailing sentence unrelated to the variance rule and
    still matched, with a higher score).
  - `"When can we skip the three-bid requirement?"` → `SOP-001` (whole-doc
    score 0.7019 vs chunk `SOP-001::chunk-0` score 0.7019 — exact tie. This
    document is only 3 sentences, so its one chunk covers the same body text
    as the whole document.)
  - **Correction from review** (see below): my first version of this
    comparison embedded whole documents as `title + text` but chunks as
    `text` only, so it wasn't isolating the retrieval unit — a query phrase
    that happened to match a title (e.g. "three-bid requirement" matching the
    title "Three-bid requirement exceptions") gave the whole-document side an
    unfair, unrelated advantage. `build_chunk_semantic_index` now embeds
    `title + chunk text` too, so both sides share the same embedded-text
    contract and the only real variable left is how much body text is in the
    embedding — the actual retrieval unit. The numbers above are post-fix.
  - Caveat worth recording: on this 10-document, 2–5-sentence-per-document
    toy corpus, whole-document and chunk-level results are still close
    (`SOP-001` is now an exact tie) because documents are already short
    enough that one chunk nearly equals the whole document. The
    retrieval-unit argument matters far more on realistic multi-page
    policies/contracts, which this corpus doesn't have yet — matches the
    doc's warning not to overfit conclusions to the tiny corpus.
- Baseline commands:
  - `./.venv/bin/pytest -q` → `48 passed` (22 pre-existing + 26 new chunking/
    chunked-search tests, after fixing the title-embedding review finding
    below and adding edge-case tests for sentence splitting)
  - `./.venv/bin/python -m compileall -q src tests` → passed
  - `./.venv/bin/python src/retrieval.py` → unchanged from Day 3 (TF-IDF/BM25
    still rank `POL-003`, `SOP-001`, `POL-001`/`SOP-002` correctly)
  - `./.venv/bin/python src/semantic_search.py` → unchanged from Day 4
  - `./.venv/bin/python src/chunking.py` → 10 documents → 13 chunks
    (`max_sentences=3`, `overlap=1`)
  - `./.venv/bin/python src/chunked_search.py` → comparison output above
- Chunking evidence summary:
  - Chunk size: `max_sentences=3` (default)
  - Overlap: `overlap=1` (default)
  - Example source document: `SOP-002` — "Invoice mismatch handling" (4 sentences)
  - Example chunks:
    - `SOP-002::chunk-0`: "Invoices are matched against purchase order, goods
      receipt, and contracted pricing. A price variance over 3% or quantity
      variance over 5 units requires buyer review. Suppliers should not be
      paid until mismatch resolution is documented."
    - `SOP-002::chunk-1`: "Suppliers should not be paid until mismatch
      resolution is documented. Repeated invoice mismatches should trigger
      supplier performance review." (first sentence repeats — the overlap)
- Most important reason chunking helps RAG: the LLM should receive the
  passage that actually answers the question, not a whole document padded
  with unrelated sentences. Chunking is what makes the retrieval unit small
  enough for that to be possible.
- Most important chunking risk: getting the window wrong in either direction.
  Too small and a clause loses the surrounding context that gives it meaning
  (a `3%` variance rule floating with no subject); too large and retrieval
  gets diluted back toward whole-document behavior, and overlap set too high
  just duplicates near-identical chunks into the index for no benefit.
- Hybrid-search note: deferred until after chunk-level retrieval is understood.

### What failed or was confusing

- My first version of `chunk_sentences` advanced the sliding window by a
  fixed step on every iteration, with no exit check. On a document short
  enough to fit in one window (e.g. `SOP-001`, 3 sentences, `max_sentences=3`),
  that produced a second, useless chunk containing only the last sentence -
  something already fully covered by the first chunk. I fixed it by breaking
  out of the loop as soon as a window reaches the last sentence, instead of
  always advancing by `step` and checking afterward. `tests/test_chunking.py`
  has a test (`test_chunk_sentences_stops_once_a_window_reaches_the_end`)
  pinned to exactly this case so it can't silently regress.
- The whole-document vs chunk-level comparison in `chunked_search.py` was
  less dramatic than I expected. For `SOP-001` the two are nearly identical,
  because the whole document is only 3 sentences - one chunk *is* basically
  the whole document. It took building it and looking at the actual output to
  realize the comparison only proves the retrieval-unit argument on longer
  documents, and this corpus doesn't have any yet.
- Bigger one, caught in review, not by me: my first version of
  `build_chunk_semantic_index` embedded bare chunk text, while the
  whole-document index (via `preprocess_data`) embeds `title + text`. That's
  not a controlled comparison - it changes two things at once (retrieval unit
  *and* whether the title is part of what's embedded), not just the retrieval
  unit. It surfaced concretely on `"When can we skip the three-bid
  requirement?"`: the phrase is almost verbatim in `SOP-001`'s title, so the
  whole-document side got a score boost that had nothing to do with chunking.
  My own "mostly noise" explanation for that gap was wrong - it was a real,
  specific confound. Fixed by embedding `title + chunk text` on the chunk
  side too (same combination `preprocess_data` uses), which is also just
  correct RAG practice: real chunking pipelines commonly prepend the source
  title/section heading to each chunk before embedding, precisely because a
  chunk alone can lose the context that made it findable.

### What became clearer

- Overlap is a step-size problem, not a duplication toggle: `step =
  max_sentences - overlap`. With `max_sentences=3, overlap=1`, each new
  window starts 2 sentences after the previous one, so exactly one sentence
  (the boundary sentence) appears in both windows. Seeing the actual output
  (`SOP-002::chunk-0` and `chunk-1` sharing "Suppliers should not be paid
  until mismatch resolution is documented.") made this concrete instead of
  abstract.
- The sentence-boundary heuristic (split after `.`/`!`/`?` only when followed
  by whitespace + a capital letter) is doing real work, not just window
  dressing: it's the difference between `"Northstar Analytics Ltd. may
  process..."` staying one sentence (correct - "Ltd." isn't a sentence end)
  and `"...Legal approval. Supplier names must..."` correctly splitting into
  two. Naive "split on every period" would have broken every legal suffix and
  every €X,XXX.XX-style amount in this corpus.
- Chunk ids need to be deterministic (built from `document_id` +
  `chunk_index`), not random, or re-indexing the same corpus twice would
  silently produce a different chunk store each time - which would break any
  downstream caching or comparison across runs.

### What I can now explain in an interview

- Why RAG systems chunk: the LLM should get the relevant passage, not an
  entire document - chunking is what makes retrieval precise and keeps the
  prompt budget under control.
- The chunk-size trade-off: small chunks are precise but can drop the
  surrounding context a sentence needs to make sense; large chunks keep
  context but dilute retrieval and waste tokens, since the model still gets
  every unrelated sentence in the window along with the relevant one.
- Why overlap helps: a sentence sitting right on a chunk boundary still shows
  up in full context in at least one chunk, because the window's tail repeats
  as the next window's head. Overlap set too high, though, means most of each
  new chunk just repeats the one before it - more chunks to embed and rank,
  without much new information per chunk.
- Why sentence/semantic chunking beats arbitrary token cuts: an arbitrary
  cut can split a clause or a definition mid-thought and change what it
  means once it's retrieved on its own; splitting on sentence boundaries
  keeps each chunk a complete thought.
- Why chunking comes before hybrid search: hybrid search combines lexical and
  dense ranking signals, but both signals still need to be ranking the right
  *unit*. If the system is ranking whole documents, improving how they're
  scored doesn't fix the underlying problem - the LLM still gets a whole
  document instead of the one passage that answers the question. Fix the
  retrieval unit first, then combine signals over that unit.

### What remains weak

- The abbreviation heuristic is still just a heuristic: `"Dr. Smith approved
  it."` would incorrectly split into two sentences, because the regex can't
  tell a title-cased abbreviation from a real sentence end. It happens not to
  break on this corpus (checked directly against every document), but it
  isn't a general solution - that's Boot.dev's "Chunked Edge Cases" lesson,
  and I only implemented the whitespace/empty-fragment/unpunctuated-text
  edge cases from it, not the abbreviation-detection part.
- The whole-document vs chunk-level comparison doesn't yet prove chunking
  helps *this* corpus - with the title-embedding confound fixed, `SOP-001`'s
  whole-doc and chunk scores are now an exact tie (`0.7019` both), because
  every document here is short enough that one chunk covers the same body
  text as the whole document. I have the mechanism built, tested, and now
  controlled correctly, but not evidence of it winning on a real
  precision/recall question - I'd need a genuinely long document (a
  multi-page MSA or policy) to see the gap the Day 5 doc describes.
- No evaluation harness yet - "top-1 is the expected document" is a
  reasonable smoke check, but it isn't the same as measuring
  precision/recall across a labeled query set the way a real retrieval
  evaluation would.

### Next step

- Add at least one genuinely long source document (a multi-page MSA or
  policy, not a 3-4 sentence entry) so the whole-document vs chunk-level
  comparison can show a real precision difference instead of a near-tie.
- Then compare lexical (TF-IDF/BM25), semantic, and hybrid search over
  chunks - not whole documents - with actual evaluation evidence, before
  moving toward source-cited answer generation.

## 2026-09-10 — Day 6: Hybrid Search Foundations

### What I built or drafted

- Drafted Day 6 route in `docs/day-06-hybrid-search-foundations.md`.
- Starting from the Day 5 chunking artifact and the Day 2–4 lexical/semantic
  baselines (unchanged — Day 6 only adds a module that consumes their
  output).
- Artifact attempted or built: Block 3A, `src/hybrid_search.py` — a
  `HybridSearch` class that takes a BM25 result list and a semantic result
  list (default `{id, score}` shape, same as Day 3/4) and fuses them two
  ways: `rrf(k=60)` (Reciprocal Rank Fusion) and `weighted(alpha=0.5)`
  (min-max normalization + alpha-weighted blend). Both methods preserve each
  candidate's raw per-method scores (and, for `weighted`, the normalized
  scores too) on every result, for debuggability. Plus `tests/test_hybrid_search.py`.
- Follow-up pass after a review of the first version: fixed a real bug (see
  "What failed or was confusing" below), then extended `HybridSearch` to
  chunks — `src/chunked_search.py` gained `build_chunk_lexical_index` /
  `search_bm25_chunks` (BM25 over chunks, the missing counterpart to Day 5's
  chunk-level semantic search — reuses `retrieval.calculate_bm25_idf`
  rather than reimplementing BM25's IDF a second time), and
  `hybrid_search.py main()` now runs a second, chunk-level comparison using
  `HybridSearch(..., id_key="chunk_id")` against the same two chunks the
  Day 5 comparison used.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Chapter 6 — Hybrid Search — completed all 5
  lessons (Keyword vs. Semantic Search, Hybrid Search, Score Normalization,
  Weighted Combination, Reciprocal Rank Fusion).
- Exercises completed or attempted: Completed.

| Lesson | Plain-English takeaway | Procurement example | Implementation implication |
|---|---|---|---|
| Keyword vs. Semantic | Lexical matches exact tokens; dense matches meaning. Neither is a superset of the other. | "SOC 2 Type II" (BM25 wins) vs. "which suppliers need evidence" (semantic wins) | Need both signals, not a "better" single retriever. |
| Hybrid Search | Combine both retrievers' outputs into one ranking instead of picking one. | A query that mixes an exact PO number with a paraphrase needs both. | `HybridSearch` takes two already-ranked lists as input; it doesn't re-retrieve. |
| Score Normalization | Raw scores from different retrievers live on different, incomparable scales. | BM25 `17.8` vs. cosine `0.41` for the same query — can't average directly. | Min-max normalize each retriever's scores to `[0,1]` *before* blending with alpha. |
| Weighted Combination | `hybrid = alpha*semantic_norm + (1-alpha)*lexical_norm`. Alpha is a tunable dial. | `alpha=0.2` to make exact-identifier queries dominate in a procurement system. | Normalization must happen per-retriever, over that retriever's own candidate set, before blending. |
| RRF | `score(d) = sum(1/(k+rank_i(d)))` — uses only rank position, never raw score. | Works even when BM25 returns nothing (OOV query) but semantic returns something for everything. | No normalization step at all; only one parameter (`k`, default 60) to reason about. |

### Hybrid search artifact / retrieval evidence

- Route taken: Block 3A, primary hybrid search artifact.
- Ran `src/hybrid_search.py main()` over the real 34-document v1 corpus and
  the Day 4 `COMPARISON_CASES` queries (real BM25 index, real cached
  `multi-qa-MiniLM-L6-cos-v1` embeddings — no synthetic data):
  - `"What checks are needed before onboarding a new high-risk supplier?"` →
    BM25 top-1 `POL-002` (correct), semantic top-1 `POL-002` (correct), RRF
    top-1 `POL-002`, weighted top-1 `POL-002`. Both single methods already
    agreed; hybrid just confirms.
  - `"What vendor vetting is required before working with a risky supplier?"`
    → BM25 top-1 `CONTRACT-006` (**wrong**), semantic top-1 `POL-002`
    (correct). RRF top-1 came out `CONTRACT-006` — **wrong**, an exact tie
    (`0.0164` both) broken by alphabetical document id instead of relevance.
    Weighted combination has the same exact tie (`0.5000` both) with the same
    wrong winner. See "What failed or was confusing" below.
  - `"Can Northstar use company data for model training?"` → both single
    methods correct (`CONTRACT-002`); RRF and weighted both correct too.
  - `"Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?"` → both
    single methods correct (`POL-003`); RRF and weighted both correct.
  - `"What happens when invoice price variance is over 3%?"` → BM25 top-1
    `FAQ-002` (**wrong** — "variance" and "3%" both appear in an unrelated
    FAQ), semantic top-1 `SOP-002` (correct). RRF top-1 `SOP-002` (correct,
    `0.0325` vs. `0.0164`), weighted top-1 `SOP-002` (correct, `0.8844` vs.
    `0.5000`). **This is the real, on-corpus case where hybrid recovers from
    a single method's mistake** — BM25 alone gets it wrong; both fusion
    methods get it right by trusting the (correct) semantic signal.
  - None of these 5 queries has *both* single methods failing at once on
    this corpus — see the "Hybrid beats both" test note below.
- Chunk-level hybrid search evidence, same `main()` run, now over Day 5's
  570 chunks (34 documents) instead of whole documents — after a follow-up
  fix, using the *same five* `COMPARISON_CASES` queries as the whole-document
  section above, not the narrower 2-query `chunked_search.COMPARISON_QUERIES`
  set (the demo originally used different query counts for the two sections,
  which made them harder to compare — see below):
  - `"What checks are needed before onboarding a new high-risk supplier?"` →
    BM25-over-chunks top-1 `FAQ-002::chunk-12` (**wrong document**),
    semantic-over-chunks top-1 `POL-002::chunk-1` (correct). RRF top-1 came
    out `FAQ-002::chunk-12` — **wrong**, an exact tie (`0.0164` both) broken
    by alphabetical chunk id (`"FAQ-002..." < "POL-002..."`). Weighted has
    the same exact tie (`0.5000` both) with the same wrong winner. **This is
    the same exact-tie failure mode from the whole-document "vendor vetting"
    query above, now hit by a different query at chunk granularity** —
    concrete evidence (not just a hypothesis) that fusing over a smaller
    unit doesn't remove the underlying cause: a candidate with only one
    retriever's signal, tied against another candidate with only the other
    retriever's signal.
  - `"What vendor vetting is required before working with a risky
    supplier?"` → BM25-over-chunks top-1 `SOP-001::chunk-5` (wrong),
    semantic-over-chunks top-1 `POL-002::chunk-6` (correct). RRF top-1
    `POL-002::chunk-6` — correct, but for the same reason as the failure
    above: another exact tie (`0.0164` both), this time broken *correctly*
    only because `"POL-002..." < "SOP-001..."` alphabetically. Same
    mechanism, opposite outcome by luck of the id ordering, not because the
    tie-break got any smarter.
  - `"Can Northstar use company data for model training?"` and `"Which SaaS
    suppliers need SOC 2 Type II or ISO 27001 evidence?"` → both single
    methods already agree on the same chunk in each case
    (`CONTRACT-002::chunk-3`, `POL-003::chunk-4`); RRF and weighted both
    correct, no tie involved.
  - `"What happens when invoice price variance is over 3%?"` → BM25-over-
    chunks top-1 `FAQ-002::chunk-12` (wrong — a different chunk restating
    the same 3%/€50/5-unit tolerances), semantic-over-chunks top-1
    `SOP-002::chunk-3` (correct). RRF top-1 `SOP-002::chunk-3` (correct,
    `0.0325` vs. `0.0323` — a real margin, not a tie), weighted top-1
    `SOP-002::chunk-3` (correct, `0.7964` vs. `0.5000`). The chunk-level
    mirror of the whole-document recovery case: BM25 alone still gets
    distracted by the same near-duplicate phrasing at chunk granularity, and
    both fusion methods still recover the right chunk because there's an
    actual score gap here, not a tie.
  - Net: 4 of 5 queries land on the correct top-1 chunk; the one failure is
    the exact-tie mode, not a new problem. This confirms Block 2's design
    note in practice, not just in theory — the fusion math genuinely didn't
    change between whole-document and chunk-level use, *including its known
    weakness*.
- Constructed test case (`tests/test_hybrid_search.py`,
  `test_hybrid_beats_both_single_methods_on_an_identifier_plus_paraphrase_query`):
  hand-built ranks where the correct record is runner-up (rank 2) in *both*
  lists, while two different distractor documents each win one list and rank
  last in the other. RRF and weighted combination both correctly rank the
  runner-up-in-both document first. This is the general "hybrid beats both"
  failure mode the Day 6 doc describes; the real v1 corpus at this size just
  didn't happen to produce a live example of it for these 5 queries.
- Baseline commands (after the review follow-up pass):
  - `./.venv/bin/pytest -q` → `64 passed` (48 pre-existing + 11 hybrid
    search tests + 5 new chunk-level-BM25 tests in `test_chunked_search.py`)
  - `./.venv/bin/python -m compileall -q src tests` → passed
  - `./.venv/bin/python src/retrieval.py` → unchanged from Day 3
  - `./.venv/bin/python src/semantic_search.py` → unchanged from Day 4
  - `./.venv/bin/python src/chunked_search.py` → unchanged from Day 5 (its
    own `main()` still only runs the whole-doc-vs-chunk semantic comparison;
    the new BM25-over-chunks functions are exercised by `hybrid_search.py`'s
    `main()` and by tests instead)
  - `./.venv/bin/python src/hybrid_search.py` → whole-document comparison
    output above, plus the chunk-level comparison output above

### What failed or was confusing

- The `"vendor vetting"` query exposed a real RRF/weighted failure, not just
  a hypothetical one: `CONTRACT-006` (BM25 rank 1, absent from semantic's
  top-3) and `POL-002` (absent from BM25's top-3, semantic rank 1) land on
  an *exact* fused-score tie under both RRF and weighted combination — each
  has exactly one term contributing, and `1/(k+1)` is `1/(k+1)` regardless of
  which retriever it came from. My tie-break rule (sort by score, then by
  document id) picked `CONTRACT-006` only because `"CONTRACT-006" <
  "POL-002"` alphabetically — that's not a relevance judgment, it's
  incidental. I initially expected fusion to "obviously" fix every case where
  one retriever finds the right answer, and this showed that's false: fusion
  only helps when the correct document has *some* signal in both lists (even
  a weak one) to add to. A document entirely absent from one retriever's
  top-k is competing on one term only, and ties among one-term candidates are
  resolved arbitrarily. A real system would need a wider top-k per retriever
  (so more borderline-relevant documents get *some* score on both sides) or
  a smarter tie-break to make this case reliable.
- Caught in review, not by me: `_ranks_by_position` and `_scores_by_id` (the
  two helpers `rrf()`/`weighted()` use to re-key a result list by id)
  hardcoded `result["id"]` instead of using `HybridSearch`'s own `id_key`.
  The constructor already accepted `id_key="chunk_id"` and the class
  docstring already claimed chunk support — but that claim was untested and,
  it turned out, wrong: the first real chunk-level call would have raised
  `KeyError: 'id'` immediately, since chunk results are keyed by
  `"chunk_id"`, not `"id"`. I'd written "the class is written generically
  enough to support chunks" in this log before ever actually calling it that
  way — asserting a capability I hadn't exercised. Fixed by giving both
  helpers an `id_key` parameter (default `"id"`) and having `HybridSearch`
  pass its own `id_key` through everywhere, instead of assuming `"id"`; the
  chunk-level section added below is what actually exercises it now.

### What became clearer

- RRF's `k` parameter is not just a "how much does rank matter" dial in the
  abstract — I could show numerically (and then confirm on real v1-corpus
  ranks, in `test_rrf_k_parameter_changes_lower_rank_order_but_not_top1`)
  that a small `k` rewards a document with one excellent rank and one poor
  rank, while a large `k` rewards a document with a better *sum* of ranks
  across both lists, even if neither rank is great. This falls directly out
  of `1/(k+r)` being convex in `r`: for a fixed rank sum, an unbalanced split
  scores higher than a balanced split, and how much higher shrinks as `k`
  grows. `k=60` (the standard default) makes that unbalanced-vs-balanced gap
  small but not zero — which is exactly the corpus case I used for the test.
- Min-max normalization being monotonic is what makes `alpha=0.0` and
  `alpha=1.0` clean, provable degenerate cases rather than approximations:
  since normalization only rescales (never reorders) a single retriever's
  own scores, multiplying the *other* side by zero reproduces that
  retriever's exact ranking, not just something close to it.
- Why the two fusion methods are meant to be compared, not just implemented
  side by side: RRF is "robust and un-tunable" (no normalization step, one
  parameter that rarely needs adjusting) at the cost of ranking a document
  entirely on ordinal position, while weighted combination stays
  interpretable ("73% semantic, 27% lexical") and tunable, at the cost of
  needing a normalization step that can behave oddly with outliers or, as
  above, produce the same kind of exact tie RRF can.

### What I can now explain in an interview

- Why raw BM25 scores and cosine similarities cannot be directly averaged:
  BM25 is an unbounded positive real whose magnitude depends on corpus
  statistics (document frequency, average length); cosine similarity from a
  normalized embedding model is bounded to roughly `[0,1]`. Averaging `17.8`
  and `0.41` lets the larger-magnitude number dominate for a reason that has
  nothing to do with relevance.
- How RRF sidesteps the normalization problem: it never looks at the raw
  score at all, only the rank position within each retriever's own list —
  `score(d) = sum(1/(k+rank_i(d)))`. "1st place" means the same thing whether
  the underlying number was a BM25 score or a cosine similarity, so there's
  nothing to rescale.
- What the alpha weight in weighted combination controls: the balance
  between semantic and lexical, after both sides are min-max normalized onto
  `[0,1]`. `alpha=0.0` is pure lexical (semantic term zeroed out),
  `alpha=1.0` is pure semantic (lexical term zeroed out), `alpha=0.5` is
  equal weight; both extremes exactly reproduce that single retriever's own
  ranking, not just something close to it, because normalization is
  monotonic.
- When to prefer RRF vs. weighted combination: RRF when you want something
  robust and effectively tuning-free (one parameter, `k`, that rarely needs
  adjusting) and don't need the score itself to mean anything; weighted
  combination when you need to explicitly bias toward exact-match or
  paraphrase signals (e.g. `alpha=0.2` for a procurement system where exact
  identifiers should dominate) or want an interpretable score.
- Why hybrid search matters for procurement queries with exact identifiers:
  a query like `"What approval is required for a €60,000 purchase order?"`
  has two parts — an exact amount BM25 is built to catch, and a paraphrased
  intent ("approval required") semantic search is built to catch. Neither
  retriever alone reliably covers both parts of the same query; fusion lets
  the system get credit for whichever signal actually fired, per document.

### What remains weak

- The exact-tie failure mode documented above (two single-term candidates,
  one per retriever, resolved by alphabetical id instead of relevance) is a
  real gap, not a hypothetical one — it happened on this corpus's actual
  data. I have it identified and tested (so it can't regress silently), but
  I haven't fixed it; a real fix would need either a wider per-retriever
  top-k before fusing, or a tie-break informed by something other than
  document id (e.g. prefer whichever candidate exists in *more* lists, or
  fall back to the raw score of whichever list it did appear in). Confirmed
  this isn't specific to whole-document fusion: after aligning the
  chunk-level demo to use the same five queries as the whole-document
  section (previously it only ran 2 easier queries), the `"high-risk
  supplier"` query hit the identical failure at chunk granularity — and the
  `"vendor vetting"` chunk-level query only came out *correct* because
  `"POL-002..."` happened to sort before `"SOP-001..."` alphabetically, not
  because anything about the tie-break is actually reliable. Fusing over a
  smaller unit doesn't remove the underlying cause (a candidate with only
  one retriever's signal); if anything, seeing it hit 2 of 5 queries once
  chunk-level got the same query coverage as whole-document is a stronger
  signal this needs fixing before Day 7 treats hybrid as done, not a weaker
  one.
- The chunk-level integration tests freeze real semantic-model scores (so
  the test suite doesn't need to load a model) guarded by only a chunk-count
  assertion (`len(chunks) == 570`). That guard catches a document being
  added, removed, or re-chunked differently — it would *not* catch a
  document's text being edited in a way that happens to produce the same
  chunk count. It's a real but narrow gap in how "stale" gets detected, not
  a correctness gap in the fusion logic itself.
- No evaluation harness yet — same gap Day 5 ended on. "Hybrid gets the
  right top-1" is still a smoke check on 5 queries plus one constructed
  example, not precision/recall over the `data/corpus_v1/example_queries.jsonl`
  golden set.

### Next step

- Day 7: hybrid consolidation — metadata filtering, procurement edge cases,
  golden query set v1, baseline eval table. Worth folding in: run hybrid
  search (RRF and weighted) against `example_queries.jsonl`'s
  `expected_relevant_ids`/`relevance_grades` to get an actual precision/recall
  number instead of single-query smoke checks, and decide the tie-break fix
  for the exact-tie gap found today before treating hybrid as "done."
