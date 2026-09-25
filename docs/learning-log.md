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

## 2026-09-11 — Day 7: Hybrid Consolidation + Retrieval Eval Baseline

### What I built or drafted

- Drafted Day 7 route in `docs/day-07-hybrid-consolidation-evals.md`.
- Starting from the Day 6 hybrid search artifact and the v1 corpus/query set.
- Artifact built:
  - `src/hybrid_search.py` — added `CANDIDATE_POOL_SIZE` (the Day 6 exact-tie
    mitigation), `load_example_queries`, metadata filtering
    (`build_metadata_index`, `matches_filters`, `filter_ranked_results`), and
    `run_edge_case_comparison` (10 hand-picked v1 queries, BM25/dense/RRF/
    weighted top-1 side by side, plus a deliberate wrong-filter failure-mode
    demo). `HybridSearch` itself (the RRF/weighted math) is unchanged.
  - `src/eval_metrics.py` (new) — `precision_at_1`, `recall_at_k`,
    `reciprocal_rank`, `rollup_chunks_to_documents`, `evaluate_method`, and a
    `main()` that builds every index once and evaluates all six baseline
    rows over the full 93-query v1 set.
  - `docs/eval-report.md` (new) — the full baseline table plus the metadata
    filtering contract, tie-break decision (with the actual before/after
    numbers), and edge-case findings.
  - `data/golden_queries.jsonl` — **not created**. `data/corpus_v1/example_queries.jsonl`
    is used directly as the canonical query source (see `docs/eval-report.md`
    for why); introducing a second file would just be one more thing that
    could drift out of sync with it.
  - `tests/test_hybrid_search.py` — 7 new tests for `matches_filters` and
    `filter_ranked_results` (AND logic, list-valued `risk_tags` membership,
    filter-before-slice ordering, chunk→parent-document lookup, the
    filter-removes-correct-document failure mode, and one test against the
    real corpus).
  - `tests/test_eval_metrics.py` (new) — 9 tests for the metric functions
    and the chunk→document rollup, using small hand-computed examples so
    they don't depend on the corpus or a model.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Chapter 6 — Hybrid Search consolidation/review.
  - Lesson 1: `Keyword vs. Semantic Search` — completed
  - Lesson 2: `Hybrid Search` — completed
  - Lesson 3: `Score Normalization` — completed
  - Lesson 4: `Weighted Combination` — completed
  - Lesson 5: `Reciprocal Rank Fusion` — completed
- Companion source: Beyond Naive RAG hybrid/failure-mode sections — deferred.
- Optional conceptual source: freeCodeCamp RAG From Scratch RAG-Fusion/HyDE — _TODO (Juan): deferred.

### Hybrid consolidation / retrieval-eval evidence

- **Golden query source**: `data/corpus_v1/example_queries.jsonl`, 93 queries,
  used directly (see `docs/eval-report.md`, "Golden query source").
- **Metadata filtering contract**:
  - Supported fields: any field on a raw corpus row (`doc_type`, `category`,
    `region`, `supplier`, `risk_tags`, ...) via equality, with list-valued
    fields (`risk_tags`) matched by membership. Multiple filter fields
    combine with AND.
  - Filter timing: after scoring, before truncating to the caller's final
    `top_k` — each retriever contributes the *full* 34-document corpus as
    candidates, non-matching candidates are dropped from that full list, and
    only then is it sliced down. Rejected filtering the corpus before
    building the BM25 index: it would make IDF/avg-length statistics depend
    on which filter was active, so the same query against the same document
    could score differently per filter — confusing, and free to avoid at 34
    documents. (First version of this used `CANDIDATE_POOL_SIZE=15` instead
    of the full corpus — a real bug, caught in review, not by me; see below.)
  - Chunk behavior: a chunk carries no metadata of its own; it is filtered
    by its parent document's metadata via `document_id`
    (`filter_ranked_results(..., document_id_key="document_id")`).
  - Failure mode, measured not assumed: applying a deliberately wrong filter
    to Q001 removes its correct document (POL-001) entirely and silently —
    no error, a different (wrong) document becomes top-1 instead. See
    `docs/eval-report.md` for the exact output.
- **Edge-case comparison** (full detail and query IDs in `docs/eval-report.md`):
  - BM25 wins on 10/93 queries (dense's top-1 wrong, BM25's correct) —
    e.g. Q009 (exact shareholding percentage), Q042 (exact card spending
    limit).
  - Dense wins on 8/93 queries — e.g. Q014 ("uptime", vocabulary/paraphrase
    gap), Q002 (definitional question, little lexical overlap).
  - Hybrid wins, measured at two bars: strict ("both single methods wrong,
    hybrid correct") = 0/93 on this corpus, same finding Day 6 already
    suspected on its 5-query demo, now confirmed on the full set. Weaker but
    real ("hybrid's top-1 differs from both single methods' own top-1, and
    is correct") = 2/93 for RRF (Q009, Q042), 1/93 for weighted (Q042).
  - Hybrid still fails on Q014 — dense alone is correct, but *both* RRF and
    weighted land on a wrong, moderately-consistent-on-both-sides distractor
    instead. Same structural cause as the tie-break finding below.
- **Eval table** (full 93-query set, unfiltered text retrieval, eight rows —
  `docs/eval-report.md` has the write-up and the filtered-vs-unfiltered
  distinction). The first six rows are the required minimum; the last two
  (chunk-level hybrid) were added same-day as a direct follow-up once the
  six-row table pointed straight at the gap — see "What became clearer"
  below:

  | Method | Unit | P@1 | R@5 | MRR@10 |
  |---|---|---|---|---|
  | TF-IDF | document | 0.871 | 0.787 | 0.924 |
  | BM25 | document | 0.860 | 0.754 | 0.910 |
  | Dense | document | 0.839 | 0.673 | 0.900 |
  | Dense | chunk→document | 0.925 | 0.768 | 0.954 |
  | Hybrid RRF | document | 0.860 | 0.763 | 0.922 |
  | Hybrid weighted (α=0.5) | document | 0.882 | 0.775 | 0.938 |
  | Hybrid RRF | chunk→document | **0.935** | **0.811** | **0.965** |
  | Hybrid weighted (α=0.5) | chunk→document | 0.925 | 0.801 | 0.961 |

  Headline finding, now with a clean answer instead of a hedged one: Hybrid
  RRF at chunk granularity is the single best row in the table on **every**
  metric — the first row in this eval report where that's true without a
  caveat. It beats chunk-dense-alone (the previous best row) by +0.010 P@1,
  +0.043 R@5, +0.011 MRR@10, and beats whole-document weighted (the best
  document-level row) by +0.053/+0.036/+0.027. Fusion *does* earn its keep —
  it just needed to be fusing over the right retrieval unit first. The
  six-row version of this table's headline finding ("retrieval unit matters
  more than fusion did here") undersold it slightly: it wasn't that fusion
  didn't help, it's that fusion hadn't been tried over chunks yet. All the
  whole-document comparisons from the review-correction pass still hold
  unchanged (RRF ties BM25 on P@1, loses to TF-IDF on all three metrics;
  weighted loses to TF-IDF on R@5 only) — those weren't wrong, they were
  just no longer the most interesting row in the table once chunk-level
  hybrid existed to compare against.

- **Tie-break decision (Day 6 weakness)**: widened the per-retriever
  candidate pool fed into `HybridSearch` before fusing (3 → 15), instead of
  changing `HybridSearch`'s own tie-break rule. Measured on the Day 6
  "vendor vetting" query: at pool=3 the fused top-1 (CONTRACT-006) was tied
  with the correct document (POL-002) and won only alphabetically; at
  pool=15 the tie is gone, but the new sole winner (SOP-007) is *still
  wrong* — POL-002 never appears anywhere in BM25's top 15 at all (a real
  lexical gap, not a too-narrow-`top_k` artifact), so widening the pool
  can't manufacture a signal that genuinely isn't there. Full numbers and
  the "what this fixes vs. doesn't fix" breakdown are in
  `docs/eval-report.md`.
- **Baseline commands** (real output, captured 2026-09-11):

  ```
  $ ./.venv/bin/pytest -q
  ........................................................................ [ 88%]
  .........                                                                [100%]
  81 passed in 0.20s

  $ ./.venv/bin/python -m compileall -q src tests
  (no output — clean compile)

  $ ./.venv/bin/python -m ruff check .
  No module named ruff — not installed in .venv; not run.

  $ ./.venv/bin/python src/eval_metrics.py
  v1 baseline (unfiltered text retrieval): 93 queries, 34 documents, 570 chunks, retrieval depth=10, candidate pool=15

  | Method                      |   P@1 |   R@5 | MRR@10 |
  |------------------------------|-------|-------|--------|
  | TF-IDF (document)           | 0.871 | 0.787 | 0.924 |
  | BM25 (document)             | 0.860 | 0.754 | 0.910 |
  | Dense (document)            | 0.839 | 0.673 | 0.900 |
  | Dense chunk->document       | 0.925 | 0.768 | 0.954 |
  | Hybrid RRF (document)       | 0.860 | 0.763 | 0.922 |
  | Hybrid weighted (document)  | 0.882 | 0.775 | 0.938 |
  ```

  (Re-run after the review fixes below — same numbers, since those fixes
  only touched the metadata-filtered edge-case path, not this unfiltered
  table; `pytest` count updated to 83 with the new regression tests.)

  Re-run again after adding the two chunk-level hybrid rows (same-day
  follow-up, this section):

  ```
  $ ./.venv/bin/pytest -q
  83 passed in 0.21s

  $ ./.venv/bin/python src/eval_metrics.py
  v1 baseline (unfiltered text retrieval): 93 queries, 34 documents, 570 chunks, retrieval depth=10, candidate pool=15

  | Method                           |   P@1 |   R@5 | MRR@10 |
  |----------------------------------|-------|-------|--------|
  | TF-IDF (document)                | 0.871 | 0.787 | 0.924 |
  | BM25 (document)                  | 0.860 | 0.754 | 0.910 |
  | Dense (document)                 | 0.839 | 0.673 | 0.900 |
  | Dense chunk->document            | 0.925 | 0.768 | 0.954 |
  | Hybrid RRF (document)            | 0.860 | 0.763 | 0.922 |
  | Hybrid weighted (document)       | 0.882 | 0.775 | 0.938 |
  | Hybrid RRF chunk->document       | 0.935 | 0.811 | 0.965 |
  | Hybrid weighted chunk->document  | 0.925 | 0.801 | 0.961 |
  ```

  First six rows unchanged, as expected (no change to those closures).
  `pytest` count unchanged too — the two new closures compose
  already-tested pieces (`search_bm25_chunks`, `search_semantic_chunks`,
  `HybridSearch.rrf`/`.weighted`, `rollup_chunks_to_documents`), so no new
  unit tests were added for them specifically, matching how the existing
  `hybrid_rrf_retrieve`/`dense_chunk_retrieve` closures aren't separately
  unit tested either — their correctness rests on the pieces they compose
  already being tested, not on retesting the composition itself.

  `./.venv/bin/python src/hybrid_search.py` output (Day 6 comparisons plus
  the new Day 7 edge-case section) is long-form; full transcript wasn't
  pasted here, but every number it prints is reproducible by re-running it
  and is summarized above and in `docs/eval-report.md`.

### What failed or was confusing

- The pool-size investigation initially looked like a clean "fix": widening
  `CANDIDATE_POOL_SIZE` from 3 to 15 does make the Day 6 exact tie disappear.
  It took actually inspecting per-retriever ranks (not just the fused
  top-1) to notice the new winner was *also wrong* — the fix removes the
  arbitrary-alphabetical-tiebreak defect but doesn't touch the deeper cause
  (RRF favoring cross-retriever consensus over one retriever's strong,
  correct, single-sided signal). Easy to have stopped at "tie gone, ship
  it" and missed that the ranking was still bad for a different reason.
- Metadata filtering removing the correct document is "obviously true" in
  the abstract, but seeing it happen *silently* (no error, no empty-result
  signal, just a different, wrong top-1) on a real query (Q001 with a
  deliberately wrong filter) made the actual operational risk concrete in a
  way the abstract description didn't.
- Weighted combination and RRF disagreeing on Q009's top-1 (`POL-002` for
  RRF, `FAQ-002` for weighted — both technically correct, since the query
  has 3 valid answers) was a good reminder that "hybrid agrees with itself"
  is not something to assume; the two fusion methods use genuinely
  different information (rank position vs. normalized magnitude) and can
  legitimately land on different, individually-defensible answers.

**Caught in review, not by me — four issues, all confirmed against real
data before fixing, not just taken on faith:**

1. **Metadata filtering only filtered `CANDIDATE_POOL_SIZE=15` candidates,
   not the full ranked list, contradicting my own documented contract**
   ("filter after scoring, before truncating to final `top_k`" implies
   operating on the *full* list — 15 is not the full list on a 34-document
   corpus). Verified concretely: Q007's secondary document `POL-005` ranks
   20th in BM25's raw ordering for that query — outside the top 15, so the
   original code silently dropped it while still finding `POL-002` (ranked
   1st) and reporting "filtering worked." Fixed in
   `run_edge_case_comparison` (`src/hybrid_search.py`) to retrieve the full
   corpus specifically when a query has a filter, then filter that down to
   `CANDIDATE_POOL_SIZE` before fusion — so filtering sees everything, and
   fusion still works over the same-sized pool it always did. Added
   `test_filtering_a_narrow_candidate_pool_can_lose_a_relevant_document_that_filtering_the_full_list_finds`
   as a permanent regression check, using this exact Q007/POL-005 case.
2. **The eval baseline table doesn't apply `metadata_filters` at all, but
   nothing in the report said so explicitly** — a reader could reasonably
   assume Day 7's "metadata-aware" artifact meant the baseline table was
   metadata-aware too. It isn't, and making it so isn't a one-line change:
   checked and confirmed 17 of the 21 filtered queries have at least one
   `expected_relevant_ids` entry their *own* filter would exclude (e.g.
   Q001 expects `FAQ-001` as a secondary answer, but its filter is
   `doc_type: policy`, and FAQ-001 isn't a policy). A filtered baseline
   would need filter-adjusted ground truth per query, not the same
   `expected_relevant_ids` reused as-is — genuinely separate methodology,
   not a toggle. Relabeled the table "unfiltered text retrieval" everywhere
   and documented why in `docs/eval-report.md`'s "Known limitations."
3. **The eval-report table analysis overclaimed "hybrid beats every
   individual method on all three metrics."** Review flagged the specific
   case (RRF ties BM25 on P@1, 0.860 both — not a win). Re-checking every
   other superlative in that section against the exact numbers, rather than
   patching just the flagged line, turned up two more unprompted: TF-IDF
   actually has the best R@5 among document-level rows (0.787, ahead of
   weighted's 0.775), and chunk-level dense does *not* beat whole-document
   weighted on every metric (weighted's R@5 edges it out). All three
   corrected with exact pairwise numbers in `docs/eval-report.md`. The
   underlying finding survives (retrieval unit matters more than fusion
   here) even though several of the specific superlatives supporting it
   didn't — a useful distinction to be able to draw under review, not just
   "my numbers were wrong, disregard the conclusion."
4. **Non-blocking polish, also addressed**: relabeled "MRR" as "MRR@10"
   throughout, since every method's list is truncated to depth 10 before
   scoring; added a caveat + a new test
   (`test_weighted_alpha_zero_can_still_surface_a_candidate_bm25_never_returned`)
   showing the existing "alpha=0/1 degrades exactly to single-method
   ranking" test only holds for symmetric candidate sets — with an
   asymmetric one, a document entirely absent from BM25 can still surface
   in an `alpha=0.0` ranking at a 0.0 floor, once `top_k` asks for more
   results than BM25's own list contained; strengthened the real-corpus
   filter test to assert the exact top-1 (`POL-001`), not just "some policy
   document survived."

Re-ran the full suite after all four fixes: `./.venv/bin/pytest -q` →
`83 passed` (81 + 2 new tests). The unfiltered eval table's numbers are
unchanged by any of this — the metadata-filtering bug only affected the
filtered edge-case demo path, not the baseline table, which never applied
filtering in the first place (issue 2, above).

### What became clearer

- **Fusion needed the right retrieval unit to prove itself, and the eval
  table said so directly.** Once the six-row table showed chunk-dense-alone
  beating whole-document hybrid, the natural next question wasn't "is
  fusion good?" (already answered: yes, at whole-document level, modestly)
  but "what does fusion do once it's applied to the unit that's already
  winning?" Wiring chunk-level BM25 + chunk-level dense through the same
  unchanged `HybridSearch` class answered it same-day: Hybrid RRF
  chunk→document (0.935/0.811/0.965) beats chunk-dense-alone
  (0.925/0.768/0.954) on every metric. This is the cleanest result in the
  whole report — no caveats, no "beats on 2 of 3 metrics" — and it only
  showed up because the eval table made the gap concrete enough to chase
  immediately instead of filing it as a someday-later TODO.
- BM25 wins and dense wins are not evenly split by query "type" label in the
  corpus — they're driven by whether the specific words in the query happen
  to overlap with the specific words in the answer, which correlates with
  but isn't identical to `query_type` (e.g. some `numeric` queries are
  BM25-favorable because the number itself is the differentiator; others
  aren't, if the surrounding phrasing is paraphrased).
- Why evals matter before reranking: the eval table's least comfortable
  finding (chunk-level dense alone beats whole-document hybrid) is exactly
  the kind of thing a demo of 5 queries would never surface, because none of
  Day 6's comparison queries happened to expose it. Reranking or any other
  Day 8+ improvement built on top of whole-document hybrid, without this
  table, would have been optimizing the wrong retrieval unit.
- The Day 6 "exact tie" bug and the Q014 "hybrid still fails" case are the
  *same underlying phenomenon* wearing two different hats: RRF (and, more
  weakly, weighted combination) structurally reward being decent-on-both
  sides over being excellent-on-one-side. A tie is just the most visible
  symptom of that; a confident wrong answer (Q014) is the same cause without
  the visible symptom, which makes it more dangerous, not less.

### What I can now explain in an interview

- **When BM25 beats dense in procurement RAG**: exact identifiers, numbers,
  and rare tokens — a supplier ID, a currency threshold, a percentage. Two
  real v1 examples: Q009 (a specific shareholding percentage) and Q042 (a
  specific spending limit). Dense embeddings compress these into a
  general "this is about compliance thresholds" direction and can confuse
  one exact number for a topically-similar but wrong document.
- **When dense beats BM25**: paraphrase and vocabulary mismatch between the
  query and the answer's actual wording. Q014 ("uptime" vs. the corpus's
  actual phrasing) and Q002 (a conceptual "is it X or Y" question with
  little lexical overlap with its answer sentence) are both cases where
  BM25's top-1 was wrong and dense's was right.
- **Why hybrid can still tie or fail**: fusion only combines the candidate
  signal each retriever actually produced. RRF sums rank positions; a
  document present in only one list contributes only one term, and — this
  is the sharper version I can now state precisely — RRF's rank-sum formula
  structurally favors a document that is moderately ranked by *both*
  retrievers over one that is the best result of *one* retriever and absent
  from the other. Measured concretely on Q014: dense alone is correct, but
  both RRF and weighted pick a worse, both-sides-moderate distractor
  instead. Widening the candidate pool fed into fusion removes artificial
  ties caused by too-narrow top-k, but does not fix this structural
  preference — that needs a reranker, or better lexical recall, not more
  candidates.
- **What metadata filtering adds beyond scoring**: it's a hard constraint on
  the candidate *set*, not another signal blended into the score. A
  semantically perfect match in the wrong document type/region/supplier
  should not just rank lower — it should be unreachable, because a
  procurement user filtering "policy only" wants that guarantee, not a soft
  preference. The real risk it introduces: a *wrong* filter value fails
  silently, returning a confident but incorrect top-1 rather than an error —
  demonstrated concretely on Q001 in `docs/eval-report.md`.
- **P@1, R@5, MRR@10 in plain English**: P@1 — is the very first answer
  right? R@5 — of everything actually relevant, how much shows up if I'm
  willing to skim 5 results? MRR@10 — on average, how far down the (first
  10) list is the first useful thing, with an answer at rank 1 counting
  fully and one at rank 2 counting half as much, and so on — capped at 10
  because that's where every method's ranked list was cut before scoring.

### What remains weak

- ~~Chunk-level hybrid fusion is not in the baseline table yet.~~ **Done,
  same day**: it's in the table now as two rows (`eval_metrics.py`'s
  `_chunk_hybrid_retrieve`, wiring `HybridSearch(id_key="chunk_id")` over
  `chunked_search.py`'s existing chunk-level BM25/dense, rolled up with the
  existing `rollup_chunks_to_documents`). Hybrid RRF chunk→document came out
  best on every metric — see the eval table above. What replaces this as
  the open item: whether the Q014 RRF-favors-consensus failure mode
  (below) also shows up at chunk granularity is untested; the chunk-level
  numbers being better *on average* doesn't mean that specific structural
  weakness is gone, only that it wasn't measured at this granularity today.
- No metadata-aware baseline exists. The current eval table is unfiltered
  text retrieval only, and building a filtered one is a real, separate
  methodology problem (17 of 21 filtered queries have a relevant id their
  own filter would exclude), not a one-line addition — see
  `docs/eval-report.md`, "Known limitations."
- Binary relevance only (`expected_relevant_ids`); `relevance_grades`
  (1 = secondary, 2 = primary) is unused, so a primary-document hit and a
  secondary-document hit currently score identically.
- The RRF-favors-consensus-over-strength finding (Q014, and the tie-break
  investigation) is now measured and understood, but not fixed — it's an
  argued case for reranking next, not a patch applied today.
- Metadata filtering supports equality (plus list membership for tag-style
  fields) only — no OR, no numeric ranges (e.g. `annual_value_eur` over a
  threshold). Not exercised by any v1 query, so not built.

### Next step

- Day 8: move from first-stage hybrid retrieval toward reranking and a
  stronger evaluation harness, using the Day 7 baseline table and golden
  query source as the comparison line. The chunk-level-hybrid lead from
  earlier today is now done (see the eval table above), which sharpens what
  Day 8 should actually target: (1) **benchmark reranking against Hybrid RRF
  chunk→document (0.935/0.811/0.965), not whole-document hybrid** — that's
  now the real baseline to beat, and reranking on top of the weaker
  whole-document number would overstate how much a reranker adds; (2) check
  whether the RRF-favors-consensus-over-strength pattern (Q014, the
  tie-break investigation) still shows up at chunk granularity now that
  it's the best-performing configuration — untested today, and the kind of
  thing that's easy to assume is "probably fine" precisely because the
  aggregate numbers look good; (3) a reranker or graded-relevance metric
  aimed at that pattern once its chunk-level status is known, since it's a
  structural blind spot in first-stage fusion, not a tuning problem `alpha`
  or `k` can solve away.

## 2026-09-12 — Day 8: Reranking + Two-Stage Retrieval

### What I built or drafted

- Drafted Day 8 route in `docs/day-08-reranking-two-stage-retrieval.md`.
- Starting from the Day 7 chunk-level Hybrid RRF baseline and v1 canonical
  query set.
- Artifact built (Block 3A, primary route — live cross-encoder, not the
  fake-scorer fallback): `src/reranking.py` (first-stage shortlist builder,
  generic `rerank` abstraction, cross-encoder scorer, two-stage pipeline,
  Q014-focused demo), `tests/test_reranking.py` (12 tests, all against fake
  scorers — no live model download in the standard suite), a ninth row
  wired into `src/eval_metrics.py`, and a new "Day 8: Cross-encoder
  reranking" section in `docs/eval-report.md`.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Chapter 8 — Reranking.
  - Lesson 1: `Re-ranking` — Completed
  - Lesson 2: `LLMs for Re-Ranking` — Completed
  - Lesson 3: `LLM Batch Re-Ranking` — Completed
  - Lesson 4: `Cross-Encoder Re-Ranking` — Completed
- Exercises completed or attempted: Completed
- Companion source notes: Beyond Naive RAG reranking/failure modes — Deferred.

### Two-stage reranking contract

- First-stage retriever / candidate source: chunk-level Hybrid RRF, unchanged
  from Day 7 — `search_bm25_chunks` + `search_semantic_chunks` fused via
  `HybridSearch(id_key="chunk_id").rrf()` (`reranking.build_chunk_shortlist`).
- Shortlist size before reranking: 15 (`hybrid_search.CANDIDATE_POOL_SIZE`,
  reused rather than introducing a second tunable number — within the
  design doc's suggested 10–25 range).
- Candidate text passed to reranker: `title + chunk text`
  (`reranking.build_candidate_text`) — same "title + body" convention the
  Day 7 chunk indexes already use. Raw `chunk["text"]` (title-free) is kept
  separately on every result as the citeable passage.
- Reranker used: local `sentence_transformers.CrossEncoder`,
  `cross-encoder/ms-marco-TinyBERT-L2-v2`, forced to `device="cpu"`
  (`reranking.load_cross_encoder`) — downloaded and ran successfully in
  this environment, so the primary route (not the fake-scorer fallback)
  was used for the live numbers below. `reranking.rerank` itself is
  scorer-agnostic (`score_fn` parameter), so the same function is unit
  tested against fake scores with no model involved.
- Result fields preserved for auditability: `chunk_id`, `document_id`,
  `title`, `text`, `first_stage_rank`, `first_stage_score`, `bm25_score`,
  `semantic_score`, plus the new `reranker_score` and `final_rank` —
  matches the design doc's expected shape exactly.

### Reranking / evaluation evidence

- Baseline to beat: Day 7 Hybrid RRF chunk→document — P@1 `0.935`, R@5
  `0.811`, MRR@10 `0.965`.
- Query set: `data/corpus_v1/example_queries.jsonl`, full 93/93 queries —
  no subset needed; the reranked row added ~9s to the eval script's total
  runtime (~16s vs. Day 7's ~7s).
- Q014 / consensus-over-strength check at chunk level: **does not
  reproduce at chunk granularity.** First-stage chunk-level Hybrid RRF
  already ranks `POL-003::chunk-11` (correct) top-1 for Q014, before
  reranking runs — the whole-document consensus-over-strength failure Day 7
  measured is at least partly a retrieval-unit artifact, not purely a
  fusion-formula weakness. Reranking left top-1 unchanged but promoted a
  second correct document (`GUIDE-002`) into the top 3. Full write-up:
  `docs/eval-report.md`, "Day 8: Cross-encoder reranking" → "Q014 at chunk
  level".
- Reranked metric row(s) (real numbers, `./.venv/bin/python src/eval_metrics.py`):
  Cross-encoder reranked Hybrid RRF chunk→document — P@1 `0.978` (+0.043),
  R@5 `0.806` (-0.005), MRR@10 `0.984` (+0.019). Reranking improved the two
  metrics that score top-of-list precision and slightly reduced the one
  recall metric — explained (not just reported) in `docs/eval-report.md`:
  reranking can only reorder the existing 15-chunk shortlist, never pull in
  a document that was never retrieved at all.
- Baseline commands:
  - `./.venv/bin/pytest -q` → `95 passed in 0.21s` (was `83 passed` before
    Day 8; +12 from `tests/test_reranking.py`).
  - `./.venv/bin/python -m compileall -q src tests` → clean, no output.
  - `./.venv/bin/python src/reranking.py` → ran the live Q014/Q009/Q042
    demo against the real cross-encoder; output captured in
    `docs/eval-report.md`'s Q014 section.
  - `./.venv/bin/python src/eval_metrics.py` → printed the nine-row table
    above in ~16s.
  - `./.venv/bin/python -m ruff check .` → not installed in `.venv`
    (`No module named ruff`) — not attempted further; `compileall` was
    used as the syntax/import gate instead, matching how earlier days in
    this log handle the same gap.

### What failed or was confusing

- Expected the cross-encoder to be the mechanism that fixed Q014 (Day 7's
  whole-document consensus-over-strength failure). It wasn't — chunk-level
  first-stage RRF already got Q014 right on its own, before reranking ran
  at all. First read that as "the reranker did nothing useful on this
  query," before catching that it still cleaned up ranks #2–#3 and helped
  clearly across the other 92 queries — a null result on one targeted case
  isn't the same as a null result overall.
- R@5 dropping slightly (0.811 → 0.806) while P@1 and MRR@10 both rose felt
  like a contradiction at first — "reranking made it worse?" — until
  working through *why*: reranking can only reorder the 15 chunks the
  first stage already retrieved. It can push a relevant chunk across the
  rank-5 boundary either direction, but it can never pull in a chunk that
  was never in the shortlist. That's a structural ceiling, not a bug.
- `reranker_score` (e.g. `3.16`, `-6.27`) has no fixed scale or probability
  meaning, unlike RRF's roughly `[0, 0.033]` range or cosine's `[0, 1]`
  range — briefly caught myself about to compare a first-stage RRF score
  against a `reranker_score` directly before remembering they're not
  comparable at all; the fields sit side by side only for audit/debugging,
  never combined into one number.

### What became clearer

- Two-stage retrieval isn't "the reranker fixes what the first stage got
  wrong" in general — it's "the first stage owns recall, the reranker owns
  precision-of-ordering within whatever the first stage already found."
  The 93-query numbers make that concrete: P@1/MRR@10 up, R@5 essentially
  flat. That's what a reranker doing its actual job looks like, not a
  coincidence.
- Bi-encoder vs. cross-encoder stopped being abstract once I had to read
  `build_chunk_shortlist` (bi-encoder: embed once, compare via cosine,
  cacheable) right next to `score_with_cross_encoder` (feeds `(query,
  candidate_text)` into the model together, one forward pass per pair,
  nothing to cache) side by side in the same module.
- Q014 "not reproducing" at chunk level was the most useful surprise:
  Day 7's whole-document RRF weakness wasn't purely "RRF's formula prefers
  consensus over strength" in the abstract — some of that failure was
  really "a whole document's aggregate BM25/dense score gets diluted by
  its other unrelated sentences," which chunking alone (no reranking
  needed) partly fixes. Two different mechanisms for what looked like one
  problem.

### What I can now explain in an interview

- **Two-stage retrieval**: first-stage retrieval (BM25, dense, RRF fusion)
  has to run over the *whole* corpus for every query, so it has to be
  cheap — a bi-encoder's per-item embedding is precomputed once and reused
  across every future query, and BM25 is just an inverted-index lookup.
  That speed comes at the cost of only ever comparing independently
  computed representations. A reranker is allowed to be expensive
  precisely because it only ever runs over the shortlist the first stage
  already narrowed down (15 chunks here, not 570) — it trades throughput
  for the ability to look at the query and candidate together.
- **Bi-encoder vs. cross-encoder**: a bi-encoder (`semantic_search.py`'s
  embedding model) encodes the query and every document independently and
  compares the two vectors afterward (cosine similarity) — fast,
  cacheable, but query and document never interact before that final
  comparison. A cross-encoder (`ms-marco-TinyBERT-L2-v2` here) feeds
  `(query, candidate_text)` into the same model together in one forward
  pass, so it can pick up on interactions a bi-encoder's late comparison
  can miss — at the cost of needing a fresh forward pass for every single
  pair, with nothing reusable across queries.
- **Latency/accuracy tradeoff**: concretely, on this project — first-stage
  retrieval over the whole 570-chunk corpus is milliseconds (BM25/cosine
  lookups); the cross-encoder step adds ~9 seconds across all 93 queries
  because it's scoring 15 pairs per query, not the whole corpus. Rerank
  the whole corpus instead of a shortlist and that cost scales by roughly
  38x (570/15) per query — which is exactly why reranking only ever
  touches the first stage's output, never the corpus directly.
- **Procurement-specific reranking risk**: the model used today
  (`ms-marco-TinyBERT-L2-v2`) is trained on general web/search pairs, not
  procurement clauses, and it still measurably helped (P@1 +0.043) — but
  that's one 93-query corpus, not proof it generalizes. The real risk case
  is exact identifiers/numeric thresholds (PO numbers, percentages,
  currency amounts) where a general-purpose reranker might favor a passage
  that reads as topically fluent over one with the exact right number —
  Q009 (an exact shareholding-percentage query) staying correct after
  reranking is a good sign, but it's one query, not a stress test.

### What remains weak

- Domain-mismatch risk is measured as "didn't hurt on this 93-query set,"
  not "verified safe" — a general web/search-trained cross-encoder against
  procurement-specific identifiers/clauses is still an open risk on harder
  or larger query sets than v1's.
- R@5's small drop (-0.005) is explained mechanistically but not yet
  stress-tested at scale — on a larger query set it could resolve to
  genuinely flat, or to a small but real recurring cost; 93 queries isn't
  enough to tell which.
- LLM-as-reranker (Boot.dev lessons 2–3) wasn't implemented, only designed
  for — `rerank`'s `score_fn` parameter is already pluggable for it, so
  today's evidence is cross-encoder-only, not a full comparison across
  reranking approaches.
- No latency/serving-budget number was set or tested against — "~9s added
  for 93 queries" is a batch-eval number, not a per-query production
  latency measurement. Explicitly out of scope for today per the design
  doc, but a real gap before this could back a live system.
- Graded relevance (`relevance_grades`) still isn't used anywhere,
  reranking included — a reranker could be moving a document from grade-1
  to grade-2 relevance (or the reverse) and none of P@1/R@5/MRR would show
  it.

### Next step

- Day 9: formalize the retrieval evaluation harness beyond binary
  P@1/R@5/MRR@10 — likely graded relevance (`relevance_grades` / nDCG),
  filtered-eval methodology, and clearer error slices before moving into
  source-cited answer generation.

## 2026-09-14 — Day 9: Evaluation Harness — Graded Relevance, Filtered Evals, and Error Slices

### What I built or drafted

- Drafted Day 9 route in `docs/day-09-evaluation-harness-graded-filtered.md`.
- Extended (did not replace) the Day 7/8 binary evaluation harness in
  `src/eval_metrics.py`: `discounted_cumulative_gain`, `ndcg_at_k`,
  `grades_for_query`, `evaluate_ndcg` (graded relevance);
  `filter_adjusted_relevant_ids`, `filter_adjusted_grades`,
  `build_filtered_queries` (filter-adjusted ground truth);
  `slice_queries`, `evaluate_slices`, `primary_count` (error slices);
  plus a `_memoize_by_query_id` helper inside `main()` so every method's
  `retrieve_fn` is only ever computed once per query, no matter how many
  of the new tables reuse it.
- Artifact built: Block 3A only (per Day 9's own split) — graded metric +
  filter-adjusted evaluation + error slices, all wired into `main()`'s
  printout and into `docs/eval-report.md`. Block 3B (rubric + synthetic-
  only nDCG fallback) was not needed — the full route landed in one pass.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Chapter 9 — Evaluation.
  - Lesson 1: `Manual Evaluation` — Completed. Wrote the procurement
    relevance rubric (grade 2/1/0, see `docs/eval-report.md`'s "Manual
    relevance rubric" section) before writing `ndcg_at_k`, not after.
  - Lesson 2: `Golden Dataset` — Completed. Reused
    `data/corpus_v1/example_queries.jsonl` unchanged rather than building a
    new fixture (see "Evaluation contract" below).
  - Lesson 3: `Precision Metrics` — Completed. P@1 unchanged from Day 7;
    nDCG@5 is the first metric that can tell P@1's "a relevant document is
    first" apart from "the *best* relevant document is first".
  - Lesson 4: `Recall Metrics` — Completed. R@5's multi-document weakness
    from Day 7 shows up sharply in the `multi_doc` error slice (0.603-0.630
    R@5, the lowest of any query type for both methods tested).
  - Lesson 5: `F1 Score` — Completed, decided against implementing it.
    P@1/R@5 are reported side by side and both used in the slice tables;
    an F1@k would collapse them into one number and specifically hide the
    R@5 dip Day 8 already found and this day's slices sharpen further -
    the two numbers are more useful separately here than combined.
  - Lesson 6: `Error Analysis` — Completed. Four slice dimensions (query
    type, difficulty, filtered/unfiltered, single/multi-primary) computed
    for the two most important methods; the `multi_doc` finding below is
    the direct product of this lesson.
  - Lesson 7: `LLM Evaluation` — Completed conceptually; not implemented.
    See "What remains weak" below for why, and the risk this lesson flags.
- Companion source notes: RAGAS / RAG-triad concepts (context precision,
  context recall, faithfulness) were read for context but not used today -
  those are answer-generation evals, out of scope until source-cited
  generation exists (Day 10+).

### Evaluation contract / methodology evidence

- Canonical query source: `data/corpus_v1/example_queries.jsonl`, confirmed
  still canonical - no new fixture created. All Day 9 functions read
  `query_row["relevance_grades"]` / `query_row["metadata_filters"]` from
  this file directly, the same way Day 7/8's functions already read
  `expected_relevant_ids` from it.
- Manual relevance rubric (full text in `docs/eval-report.md`):
  - **Grade 2 / primary**: the document that directly answers the
    question with the specific clause, threshold, supplier, or figure - a
    buyer could act on it alone. Example: Q001's `POL-001` states the
    exact approval band.
  - **Grade 1 / secondary**: useful context that is not itself the
    complete, precise answer - an FAQ restating a policy informally, a
    narrower/broader-scope document, or supporting evidence. Example:
    Q001's `FAQ-001` restates the same rule informally.
  - **Grade 0 / not relevant**: absent from `expected_relevant_ids`
    entirely; `grades_for_query`/`ndcg_at_k` treat any id not present in
    the grades dict as grade 0 by default, so this never needs to be
    enumerated explicitly.
- Graded metric implemented: **nDCG@5**. `discounted_cumulative_gain(gains)
  = sum(gain_i / log2(rank_i + 1))`; `ndcg_at_k` divides the actual
  ranking's DCG@5 by the *ideal* ranking's DCG@5 (every graded document,
  best-grade-first). Tested with hand-computed cases: the ideal ranking
  (nDCG=1.0), a reversed primary/secondary order (nDCG≈0.860, hand-derived
  via the exact log2 formula), an unjudged id scored as gain 0 mid-ranking,
  tied grades (order among ties doesn't matter), an empty retrieved list
  (nDCG=0.0, not an error), and a query with no relevant grades at all
  (nDCG=0.0, guards the divide-by-zero rather than raising).
- Filter-adjusted evaluation method:
  - How filtered gold ids are computed: `filter_adjusted_relevant_ids`
    keeps only the ids in `expected_relevant_ids` whose *own* document
    metadata satisfies the query's *own* `metadata_filters`, via the exact
    same `hybrid_search.matches_filters` rule `filter_ranked_results`
    already applies on the retrieved side. `build_filtered_queries` does
    this for every filtered query at once, producing rows the existing
    `evaluate_method`/`evaluate_ndcg` score with zero changes.
  - Real v1 examples checked: **Q001** (`FAQ-001` dropped, not a policy),
    **Q007** (`FAQ-002` dropped, `POL-005` *kept* - a secondary document
    can survive filtering if it also matches), **Q019** (`AUDIT-001`
    dropped, wrong category) - all three asserted directly against the
    real corpus and query file in `tests/test_eval_metrics.py`, not just
    against synthetic data.
  - Number of filtered queries scored: **21/93** (all queries with a
    `metadata_filters` value); 17/21 have at least one gold id excluded by
    their own filter, 0/21 lose every gold id - matching the counts
    `docs/eval-report.md`'s Day 7 "Metadata filtering" section already
    established.
- Error slices produced (full tables in `docs/eval-report.md`):
  - By query type: strongest slice is `terminology`/`supplier_specific`
    (1.000 P@1 for both methods); weakest by far is **`multi_doc`**
    (reranked method: 0.600 P@1, the only slice where reranking scores
    *below* first-stage retrieval - see "What became clearer" below).
  - By difficulty: `hard` is actually the reranked method's *weakest*
    difficulty slice (0.923 P@1), not `easy`/`medium` (both 1.000) -
    counter-intuitive at first glance, explained by `hard`'s overlap with
    `multi_doc` (several hard queries are also multi-document ones).
  - Filtered vs. unfiltered: unfiltered *retrieval* on the 21
    filter-carrying queries (no filter applied) already scores 1.000 P@1
    for the reranked method but only 0.762 R@5 *against the original,
    unadjusted gold*. That 0.762 is not the right number to compare
    filtering against, though - scored against the *same filter-adjusted*
    gold the filtered table uses, unfiltered retrieval already reaches
    0.901 R@5 (most of the jump is the gold-set fix, not retrieval
    filtering). Filtering retrieval on top of that is real but smaller:
    0.901 → 0.948. See "Evaluation artifact" below for the full four-way
    breakdown that separates these two effects.
  - Single- vs. multi-primary: fairly balanced split (45 vs. 48 queries);
    first-stage RRF is meaningfully weaker on single-primary (0.911 vs.
    0.958 P@1), but the reranker erases that gap entirely (1.000 vs. 0.958
    - if anything now slightly favoring single-primary).

### Evaluation artifact / metric evidence

- Baseline carried forward from Day 8:
  - `./.venv/bin/pytest -q` at Day 9 kickoff → `97 passed in 1.00s`.
  - `./.venv/bin/python -m compileall -q src tests` at Day 9 kickoff → clean, no output.
  - `./.venv/bin/python src/eval_metrics.py` at Day 9 kickoff → 93 queries, 34 documents, 570 chunks; cross-encoder reranked Hybrid RRF chunk→document P@1 `0.978`, R@5 `0.806`, MRR@10 `0.984`.
- After Block 3A:
  - `./.venv/bin/pytest -q` → **`120 passed in 0.23s`** (97 + 23 new Day 9
    tests: nDCG hand-computed cases, filter-adjustment on real v1 queries,
    slice-helper tests - zero regressions in the 97 Day 7/8 tests).
  - `./.venv/bin/python -m compileall -q src tests` → clean, no output.
  - `./.venv/bin/python src/eval_metrics.py` → same binary numbers as Day 8
    (0.978/0.806/0.984 for the reranked row - confirms the refactor into
    memoized `retrieve_fn`s changed nothing about what gets computed),
    total runtime ~21s (vs. ~16s for the Day 8 table alone, despite adding
    a graded table, a filtered table, and 8 slice tables - memoization is
    what kept that cheap).
- New graded metric table (nDCG@5, 9 methods): best is the reranked row at
  **0.869**, worst is whole-document dense at **0.740** - the broad
  winner/loser story matches the binary table (same best row, same
  first-stage row, same weakest row), but the *strict* ranking is not
  identical: nDCG@5 breaks two exact P@1 ties (Dense chunk→document vs.
  Hybrid weighted chunk→document, tied at 0.925 P@1, split 0.828 vs. 0.851
  nDCG@5; BM25 vs. Hybrid RRF document, tied at 0.860 P@1, split 0.792 vs.
  0.799 nDCG@5) rather than merely confirming an order P@1 had already
  fully settled. Every number also sits well below its own method's P@1
  (0.978 P@1 vs. 0.869 nDCG@5 for the reranked row), showing real,
  previously invisible room between "found something relevant" and
  "found the *primary* evidence, ranked well".
- New filtered-adjusted table (21 queries): both first-stage and reranked
  chunk-hybrid rows land on **P@1 1.000 / R@5 0.948 / MRR@10 1.000** -
  identical in aggregate (though not in exact document order for 2 of the
  21 queries), because filtering narrows the candidate universe so much
  for these specific queries that first-stage retrieval is already near
  ceiling before the reranker ever runs.
- **R@5 four-way breakdown, to isolate what filtering the gold set vs.
  filtering retrieval each contribute** (a review finding on the first
  draft of this section - it had conflated the two): scoring the same 21
  queries under unfiltered retrieval + raw gold, unfiltered retrieval +
  filter-adjusted gold, filtered retrieval + filter-adjusted gold, and
  filtered retrieval + raw gold:

  | Retrieval | Gold | Hybrid RRF chunk R@5 | Reranked chunk R@5 |
  |---|---|---:|---:|
  | Unfiltered | Raw | 0.786 | 0.762 |
  | Unfiltered | Adjusted | 0.925 | 0.901 |
  | Filtered | Adjusted | 0.948 | 0.948 |
  | Filtered | Raw | 0.560 | 0.560 |

  Fixing the gold set alone (row 1 → row 2, retrieval unchanged) accounts
  for most of the movement (+0.139 both methods) - that's the methodology
  correction, not a retrieval result. Filtering retrieval on top of the
  *same* adjusted gold (row 2 → row 3) is the real filtering effect, and
  it's real but smaller: +0.023 for Hybrid RRF, +0.047 for reranked. Row 4
  (filtered retrieval scored against raw gold, 0.560) exists only to show
  why raw gold can't be reused for filtered retrieval - it reads as a
  collapse, but it's an artifact of penalizing correct filtering.
- New error-slice tables: 4 dimensions × 2 methods = 8 tables; see
  "Evaluation contract" above for the headline findings from each.
- Tests added: 23 new tests in `tests/test_eval_metrics.py` - 6 for
  `discounted_cumulative_gain`/`ndcg_at_k` hand-computed cases, 2 for
  `grades_for_query`/`evaluate_ndcg`, 3 synthetic + 3 real-corpus tests for
  `filter_adjusted_relevant_ids`/`filter_adjusted_grades`, 2 for
  `build_filtered_queries`, 3 for `slice_queries`/`evaluate_slices`, 1 for
  `primary_count` (exact counts: `git diff tests/test_eval_metrics.py`
  shows 23 new `def test_` lines).
- `docs/eval-report.md` update: new "Day 9: Graded relevance, filter-
  adjusted evaluation, and error slices" section (rubric, nDCG@5 table +
  interpretation, filter-adjustment methodology + Q001/Q007/Q019 walk-
  through + results table + three named findings, four slice tables + the
  `multi_doc`/Q091 root-cause trace); two "Known limitations" bullets from
  Day 7 (unfiltered-only, binary-only) updated to "Done, no longer a gap".

### What failed or was confusing

- Almost missed that reusing `evaluate_method` unmodified for the filtered
  table required *also* memoizing the two new filtered retrieve functions
  separately from the nine unfiltered ones - they are genuinely different
  closures (different filtering step), so the existing per-method
  memoization for the binary/graded tables doesn't automatically cover
  them; each needed its own `_memoize_by_query_id` wrap.
- First assumption about the filtered table was wrong: expected reranking
  to show a clearer win under filtering (fewer distractors, cleaner
  shortlist). Instead both methods tied exactly in aggregate - the real
  explanation (filtering already shrinks the candidate set so much that
  there's little left to rerank) took tracing actual per-query shortlists,
  not just reading the aggregate numbers, to find (see
  `docs/eval-report.md`'s "three findings, not one").
- Filtered recall correctly *not* penalizing a retriever for respecting a
  filter turned out to matter concretely on Q007: `POL-005` (a real
  secondary match) is excluded from that query's filtered top-5 anyway
  (R@5 0.5 there) for a *different*, legitimate reason (ranking, not
  filter-exclusion) - a reminder that "filter-adjusted" fixes one specific
  unfairness, not every source of imperfect recall.

### What became clearer

- Binary and graded metrics answering genuinely different questions is not
  just a slogan - it showed up as a real, sizeable gap in the numbers
  (0.978 P@1 vs. 0.869 nDCG@5 for the same method), not a rounding
  difference. A method can be excellent at "put something acceptable
  first" while still leaving real room in "put the single best answer
  first, and keep it there through rank 5".
- Filtered evaluation needing adjusted ground truth is not just a fairness
  argument - Q007 makes concrete that "keep only the primary document" and
  "keep only documents matching the filter" are *different* rules
  (`POL-005`, a secondary document, survives filtering precisely because
  it also matches, not because it's primary).
- The most useful thing error slicing did today: it found that the
  cross-encoder reranker, which looks purely positive in every aggregate
  number this project has produced (P@1 +0.043, MRR@10 +0.019, nDCG@5
  above first-stage on every method), has exactly one query-type slice
  (`multi_doc`, 5 queries) where it measurably makes things *worse*
  (0.800 → 0.600 P@1), traceable to one specific query (Q091) where the
  reranker demotes the correct document from rank 1 to rank 3. An
  aggregate table alone would never have surfaced that a general
  web-trained cross-encoder can specifically struggle with multi-part,
  multi-document procurement questions.

### What I can now explain in an interview

- **Precision@k vs. recall@k vs. F1@k**: precision asks "of what I
  retrieved, how much is relevant"; recall asks "of what's relevant, how
  much did I retrieve"; F1 combines them into one number but hides *which*
  one is weak - decided against adding F1@k here specifically because P@1
  and R@5 are already reported together and F1 would have blurred exactly
  the R@5 dip this project's own slice analysis needed to see clearly.
- **nDCG@k, in plain English**: assign a gain per document by its
  relevance grade, discount that gain by how far down the ranking it
  appears (`1/log2(rank+1)` - full credit at rank 1, steadily less below
  it), sum those discounted gains to get DCG, then divide by the DCG of
  the *ideal* ranking for that same query (every graded document,
  best-first) so the score is normalized to [0, 1] regardless of how many
  relevant documents a query happens to have.
- **Why manual evaluation and a domain rubric come before LLM-as-judge
  automation**: a rubric written *before* scoring (grade 2/1/0 in
  procurement terms, done today) is what any later judge - human or LLM -
  has to be calibrated against; skipping straight to an LLM score without
  one risks an authoritative-looking number nobody has actually defined.
- **Why filtered evaluation needs adjusted ground truth**: scoring a
  correctly-filtered result list against unfiltered gold ids punishes a
  retriever for doing exactly what was asked - excluding a document the
  filter itself was always going to exclude is correct behavior, not a
  miss, and Q007's `POL-005` case shows the fix is "match the filter",
  not "match the primary grade".
- **What error analysis adds beyond an aggregate table**: it can reveal a
  measurable regression (multi_doc P@1 dropping under reranking) that
  every single aggregate metric this project has computed so far -
  including today's own nDCG@5 - reports as a net positive, because the
  aggregate's gains elsewhere outweigh this one slice's loss.
- **What's risky about LLM-as-judge**: same risk profile as Day 8's
  LLM-as-reranker caveat - inconsistency across runs, prompt/model drift,
  and a plausible-sounding but wrong judgment being indistinguishable from
  a correct one without a calibration rubric exactly like the one written
  today; it should never be the only gate, and wasn't attempted today for
  that reason (see below).

### What remains weak

- **LLM-as-judge**: designed for conceptually (Boot.dev's Lesson 7,
  completed as reading/reasoning) but not implemented or even prototyped -
  no pluggable judge function or prompt template exists yet, unlike Day
  8's reranker (`score_fn` was already pluggable for an LLM scorer). Left
  fully for a later day, per today's explicit scope boundary.
- **Filtered nDCG**: `filter_adjusted_grades` is implemented and tested,
  but `main()` doesn't print a filtered *graded* table - only filtered
  binary metrics. The design doc's "Report shape" only asked for one
  filtered table, so this is a deliberate scope cut, not an oversight, but
  it means the filtered-adjusted section can't yet show whether filtering
  changes *which* document ranks first among several in-scope candidates,
  only whether the right document is retrieved at all.
- **The `multi_doc`/Q091 finding is n=5** - real and specific (traced to
  one exact query), but too small a slice to generalize a "reranker is bad
  at multi-document procurement questions" claim from confidently. It's
  the clearest next-fix candidate this report has, not a proven pattern.
- Generation evals (faithfulness/groundedness, context relevance, answer
  relevance) are still entirely out of scope - retrieval evaluation is now
  meaningfully deeper, but nothing here evaluates a generated answer yet.

### Next step

- Day 10: move into source-cited augmented generation once the
  retrieval-eval harness is strong enough to tell whether generated
  answers are grounded in the right context - it now is. Two concrete
  carry-overs from today, specifically: (1) the `multi_doc`/Q091-style
  failure (reranker demoting a correct document in a multi-part question)
  is worth re-checking once generation exists, since a wrong top-1 chunk
  feeding a generator is a much more visible failure than a wrong top-1
  document in a retrieval-only table; (2) verify the exact Boot.dev
  Chapter 10 lesson menu at Day 10 kickoff before writing the route, the
  same verification discipline Day 9 applied to Chapter 9's menu.

## 2026-09-14 — Day 10: Source-Cited Augmented Generation + Week 2 Gate Review

### What I built or drafted

- Drafted Day 10 route in `docs/day-10-augmented-generation-week2-gate.md`.
- Block 3A implementation: `src/generation.py` (context/citation contract,
  prompt construction, the fake/live generation boundary, and an optional
  live OpenRouter client) plus `tests/test_generation.py` (15 deterministic
  tests). See "Generation contract / methodology evidence" and "Generation
  artifact / test evidence" below for the design and "Day 10: Source-cited
  answer generation" in `docs/eval-report.md` for the full run output.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Chapter 10 — Augmented Generation.
  - Lesson 1: `Augmented Generation` — Completed.
  - Lesson 2: `LLM Summarization` — Completed.
  - Lesson 3: `Conflict Resolution in Summaries` — Completed.
  - Lesson 4: `Adding Citations` — Completed.
  - Lesson 5: `Question Answering` — Completed.
- Companion source notes: RAGAS/RAG-triad vocabulary (context relevance,
  faithfulness/groundedness, answer relevance) used only as *vocabulary*
  today, per the design doc's own scope boundary — not integrated as a
  framework, and no RAGAS score was computed. Day 10's actual checks
  (citations present, no orphan citations, empty context refuses) are
  closer to a *faithfulness precondition* than to faithfulness itself: they
  confirm every claim is traceable to a source, not that the source
  actually supports the claim, and not that the answer is complete. That
  distinction is exactly what Q091 (below) makes concrete.

### Week 2 gate / retrieval baseline evidence

- Baseline commands at kickoff:
  - `./.venv/bin/pytest -q` → `120 passed in 0.60s`.
  - `./.venv/bin/python -m compileall -q src tests` → clean, no output.
  - `./.venv/bin/python src/eval_metrics.py` → reranked chunk Hybrid RRF row P@1 `0.978`, R@5 `0.806`, MRR@10 `0.984`, nDCG@5 `0.869`; filtered-adjusted key rows P@1 `1.000`, R@5 `0.948`, MRR@10 `1.000`; largest weak slice `multi_doc` P@1 `0.600` over 5 queries.
- Week 2 story Juan can whiteboard: strongest overall row is cross-encoder
  reranked Hybrid RRF chunk→document (P@1/MRR@10/nDCG@5); first-stage
  Hybrid RRF chunk→document is still marginally ahead on aggregate R@5
  (0.811 vs. 0.806). Filtering is methodology-safe (scored against
  filter-adjusted gold, not raw gold). The named weak spot carried into
  Day 10 on purpose: `multi_doc` queries (P@1 0.600 over 5 queries) — Q091's
  live demo below shows exactly what that weakness looks like once it
  reaches a generated answer, not just a retrieval table.

### Generation contract / methodology evidence

- Context schema chosen: chunk-level, not rolled up to documents — one dict
  per source with `source_id` (the 1-based `[n]` citation number), `doc_id`,
  `title`, `chunk_id`, `text`, `rank`, `score` (`generation.build_sources`).
  Chunk-level (rather than document-level) so a citation can point at the
  exact quoted passage, not just "somewhere in this document."
- Prompt contract (`generation.PROMPT_INSTRUCTIONS`/`build_prompt`): answer
  only from the numbered sources; cite the source for every specific claim
  (amount, threshold, %, supplier, date, approval role); if sources
  disagree or apply to different scopes, name the difference and cite each
  separately instead of merging; refuse rather than guess when the sources
  are not enough; never invent a source number.
- Citation contract (`generation.validate_citations`): every `[n]` in the
  answer is checked against the real numbered sources and classified as
  `valid_ids` (traceable), `orphan_ids` (hallucinated — cites a source
  number that does not exist), or `uncited_ids` (retrieved but never
  cited). Zero orphan citations in both live demo answers (Q001, Q091).
- Empty-context behavior: `generate_answer` returns a fixed
  `INSUFFICIENT_EVIDENCE_ANSWER` and never calls the client at all when
  `sources` is empty — tested by handing it a client that raises if it is
  ever called
  (`test_generate_answer_with_empty_sources_refuses_without_calling_client`).
- Conflict / multi-source behavior: no contradiction-detection code — it's
  a prompt rule (rule 2 above), demoed by Q091's 5-source, 4-citation
  answer rather than by a dedicated conflict-detector module. Q093 (the
  other suggested conflicting-evidence query, indexation deadbands that
  genuinely differ by contract) was not run live today — a reasonable next
  smoke-test target, not something claimed as done.

### Generation artifact / test evidence

- Files created or modified: `src/generation.py` (new), `tests/test_generation.py`
  (new, 15 tests), plus this doc set (`docs/eval-report.md` Day 10 section,
  this entry). `pyproject.toml` gained real runtime dependencies
  `python-dotenv` and `openai` (used only inside
  `make_openrouter_client`/`main()`), plus `ruff` in `[dependency-groups]
  dev` and a pinned `[tool.ruff.lint] select` — see "Review feedback
  addressed" below.
- Deterministic tests: `./.venv/bin/pytest -q` → `135 passed` (was 120
  before Day 10's tests were added; 134 after the initial 14, then 135
  after one more was added same-day for the blank-provider-content guard —
  see "Review feedback addressed" below. None of these 15 tests touch the
  network).
- Compile/lint gates: `./.venv/bin/python -m compileall -q src tests` →
  clean, no output. `./.venv/bin/python -m ruff check src tests` → `All
  checks passed!` (ruff was not installed at first — same gap Day 9
  recorded — fixed same day; see "Review feedback addressed" below).
- Demo / smoke output: `./.venv/bin/python src/generation.py` against Q001
  (easy, threshold) and Q091 (hard, multi_doc) — full transcript in
  `docs/eval-report.md`'s "Day 10: Source-cited answer generation" →
  "Demo output" section (current version is the sixth live attempt that
  day — see "Review feedback addressed" below for why). Short version:
  Q001's answer was correct and fully cited; Q091's answer was thorough,
  well-structured, and fully cited, but still not fully correct, because
  retrieval (not generation) missed `POL-001` and `GUIDE-002` in the top-5
  shortlist — the `multi_doc` weakness from the Week 2 gate baseline, now
  visible at the answer layer. Worth noting honestly: this final Q091
  answer takes a small caveated inference beyond €60,000 ("this approval
  level applies at minimum") rather than the flatter refusal an earlier
  model gave to the same question — a real, model-dependent difference in
  how strictly "refuse rather than guess" gets followed, not something
  today's citation checks can catch.
- Optional live LLM call: yes — `make_openrouter_client` now uses the
  official `openai` SDK pointed at OpenRouter's `base_url`, and
  `python-dotenv`'s `load_dotenv()` reads `OPENROUTER_API_KEY` from `.env`.
  Model: OpenRouter's free `inclusionai/ling-3.0-flash-fin:free` (switched
  same day from `nvidia/nemotron-3.5-lightning:free` — see "Review
  feedback addressed" below for why). It is
  imported by `main()` only; the pytest gate never touches the network
  (confirmed: `make_openrouter_client` raises `RuntimeError` before any
  request if no key is present, and that is the only thing about it a test
  exercises). **A real bug surfaced on the first live run**: this model is
  a reasoning model, and by default its chain-of-thought came back as
  `message.content` instead of a clean answer (several paragraphs of
  "let's examine the sources..." trailing into truncated garbled text).
  Fixed with OpenRouter's `reasoning: {"exclude": True}` request extension,
  passed via the `openai` SDK's `extra_body` — see
  `docs/eval-report.md`'s "A live-only bug the deterministic tests
  couldn't catch" for the full story. No unit test could have caught this;
  it only showed up by actually running the live smoke test. The call is
  now also bounded: `OPENROUTER_TIMEOUT_SECONDS` (60s, passed as the
  `openai` client's `timeout=`), `MAX_ANSWER_TOKENS` (2400 when this entry
  was written; raised to 3000 later the same day by a separate commit —
  see `docs/eval-report.md`'s Day 11 addendum for the current value and
  why Day 11's fixtures still freeze this original 2400-token transcript
  on purpose), and `GENERATION_TEMPERATURE` (0.0) — added after external review found the
  original client had no timeout at all and could hang indefinitely
  against a slow free-tier backend. See "Review feedback addressed" below.

### Review feedback addressed (same day)

External code review of this Day 10 addendum caught three real gaps, all
worth recording rather than quietly fixing:

1. **Live demo not reproducible.** The reviewer's own run of
   `./.venv/bin/python src/generation.py` hung past 300 seconds with no
   answer, because `make_openrouter_client` built its `OpenAI(...)` client
   with no request timeout — a slow provider could block forever with no
   error. Fixed by adding `timeout=OPENROUTER_TIMEOUT_SECONDS` (60s) to the
   client, plus pinning `max_tokens` and `temperature=0.0` on the request
   so latency/cost are bounded and sampling variance is minimized. Getting
   a genuinely clean transcript out of that fix took six live re-runs, not
   one, and each failure was a real finding rather than noise:
   `max_tokens=700` cut the original reasoning model off mid chain-of-
   thought, so its internal trace leaked into the answer (again — see the
   bug documented above); `2000` fixed the easy query but not the hard
   one; `4000` made it worse in a new way (Q001 came back as a
   hallucinated, off-topic table; Q091 still leaked a garbled trace) —
   raising the token budget further on that model was chasing a moving
   target, not converging. The actual fix was switching
   `DEFAULT_OPENROUTER_MODEL` to a non-reasoning free model
   (`inclusionai/ling-3.0-flash-fin:free`), which sidesteps the whole
   chain-of-thought-leak failure class. That swap immediately surfaced a
   *second* real bug: the new model returned blank content on the harder
   query, and `generate_answer` crashed with an opaque `TypeError` instead
   of a clear error — fixed by adding an explicit blank-content check to
   `make_openrouter_client` (now covered by a 15th deterministic test).
   Two more token-budget increases (1600, then 2400) later, both demo
   queries finally came back clean, complete, and fully cited — see the
   updated "Demo / smoke output" above and `docs/eval-report.md`'s
   "Reproducibility hardening" for the full six-attempt transcript trail.
2. **Ruff claimed but not installed.** This entry originally listed
   "Compile/lint gates" as clean without saying `ruff` was never in
   `.venv` — the exact gap Day 9 explicitly recorded, left unstated here.
   Fixed by adding `ruff` to `pyproject.toml`'s dev group and running
   `uv sync`. Running it with zero config against the whole codebase
   surfaced 12 findings in files Day 10 never touched (import-sort/string-
   concatenation style opinions in earlier days' code) — fixing those would
   be scope creep, so `pyproject.toml` now pins
   `[tool.ruff.lint] select = ["E4", "E7", "E9", "F"]` (ruff's own
   conventional minimal rule set: real correctness issues, not style). The
   reviewer's exact command, `./.venv/bin/python -m ruff check src tests`,
   now passes cleanly.
3. **A slightly leaky test boundary.** `make_openrouter_client` imported
   `openai` *before* checking for an API key, so the "fake-client tests
   don't need live-client dependencies" boundary held by coincidence (it
   worked in a synced `.venv`) rather than by construction (a partial
   environment missing `openai` would have failed the no-key guard test
   with `ModuleNotFoundError`, not the intended `RuntimeError`). Fixed by
   moving the import below the key check.

Non-blocking cleanup applied at the same time: `pyproject.toml` now depends
directly on `python-dotenv` instead of the `dotenv` wrapper package it
resolved to before — same `from dotenv import load_dotenv` import in the
code, one fewer indirection in the dependency tree. Full details and the
gate re-run output for all of the above are in `docs/eval-report.md`'s
"Reproducibility hardening (post-review fixes, same day)".

### What failed or was confusing

- The first live run did not produce a usable answer at all: instead of a
  short cited answer, `nvidia/nemotron-3.5-lightning:free` returned several
  paragraphs of its own internal reasoning ("Let's examine the sources...
  I'll cite [5] as the primary, or both...") narrating its way through the
  citation rules, then cut off mid-sentence into garbled, truncated text.
  The confusing part was realizing this had nothing to do with the prompt
  contract - the four rules in `PROMPT_INSTRUCTIONS` were followed
  correctly *inside* the reasoning trace, they just never made it to a
  clean final answer, because this is a reasoning model and OpenRouter
  returns its chain-of-thought as part of `message.content` by default.
  Better prompting could not have fixed this; it needed a provider-level
  request option (`reasoning: {"exclude": True}`, via `extra_body`) that
  has nothing to do with RAG at all.
- Genuinely expected Q091's citation check to at least hint that something
  was wrong (an orphan citation, a refusal, something visibly broken).
  Instead it came back with zero orphan citations, every claim backed by a
  real source, and an honest "no single source provides a combined
  threshold for EUR 120,000" - a textbook well-behaved answer by every
  check this project has - while still missing the actual expected answer
  (Band 3, VP Procurement) because `POL-001` never made it into the top-5
  shortlist. A clean citation check gave zero signal that retrieval, not
  generation, was the actual problem.
- Chunk-level citations mean the same document can appear as two different
  source numbers in one prompt (`[2]` and `[3]` were both `FAQ-001` in the
  Q091 run). Correct and auditable (each points at a different quoted
  chunk), but it reads a little oddly in a user-facing answer - an
  unresolved UX question, not a bug, and not something today's scope asked
  to solve.

### What became clearer

- "Retrieval quality and answer quality are different axes" stopped being
  a slogan I could recite and became something I actually watched happen:
  Q091's answer passed every deterministic check this project has (cited,
  no orphans, honest about the gap) and was still wrong relative to
  `expected_answer`, for a reason entirely outside the generator's control.
  Good citations prove an answer is faithful to *what it was given* - they
  say nothing about whether what it was given was the right evidence.
- Why citations are an interface, not decoration: `validate_citations`
  turns "the model wrote [4]" into a checkable fact - does source 4 exist
  in the list it was actually given - which is the difference between a
  citation a person has to manually verify against the source text and one
  code can flag as an orphan automatically. That is the whole reason
  `source_id` exists as a stable field instead of the model inventing its
  own labels.
- Why Q091 is a harder generation test than Q001: Q001 needed one claim
  from one source. Q091 needed four *separate* claims (approval role,
  three-bid requirement, record-keeping, security evidence) from four
  different documents, kept apart rather than blended into one confident
  composite number - "don't merge conflicting/differently-scoped evidence"
  is easy to write as a prompt rule and only actually gets tested when a
  query forces the model to hold several sources apart at once.
- The live/fake client boundary is not just a testing-hygiene nicety -
  today's reasoning-leak bug is proof it is load-bearing. The bug lived
  entirely inside a live provider's default response *shape*, not in this
  project's prompt or citation logic, so no fake-client test could have
  exercised it even in principle. Deterministic tests prove the contract;
  only a live smoke run can prove the contract survives contact with an
  actual model.

### What I can now explain in an interview

- **Augmented generation:** the query is never sent to the model alone.
  Retrieval produces ranked chunks; `build_sources` turns them into
  numbered, citable sources; `build_prompt` "augments" the question with
  those sources plus explicit rules (answer only from them, cite specific
  claims, refuse if insufficient); only that combined prompt reaches the
  model. Generation is grounded in retrieved project evidence instead of
  the model's own parametric memory.
- **Source-cited answers:** every retrieved chunk gets a small stable
  `source_id` (`[1]`, `[2]`, ...) tied to its real `doc_id`/`chunk_id`. The
  model is told to cite that number next to every specific claim.
  `validate_citations` then checks every `[n]` the model actually wrote
  against the real numbered list, splitting them into `valid_ids` (real),
  `orphan_ids` (a citation to a source number that does not exist -
  hallucinated), and `uncited_ids` (retrieved but never used). A citation
  is either traceable or flagged, never just a decorative bracket.
- **Retrieval quality vs. answer quality:** retrieval quality asks whether
  the right evidence made it into the shortlist (Day 9's P@1/R@5/nDCG@5);
  answer quality asks whether the model used what it *did* get faithfully
  and completely. They are measured differently and can diverge in either
  direction. Q091 is the concrete case: perfect citation hygiene, an
  honest "sources don't fully specify this," and still an incomplete
  answer, because `POL-001` was never in the top-5 the generator saw.
  Good generation cannot correct a retrieval miss it was never shown.
- **Conflict handling:** not a separate contradiction-detection system -
  it's a prompt rule (`PROMPT_INSTRUCTIONS` rule 2: if sources disagree or
  apply to different scopes, name the difference and cite each separately
  instead of merging them into one number). Demoed by Q091: approval role,
  bidding requirement, record-keeping, and security evidence stayed as
  four separately-cited points instead of one blended, overconfident
  answer.
- **Live LLM test boundary:** `generate_answer(query, sources, client)`
  takes `client` as a plain `prompt -> text` callable. Tests pass a fake
  function returning canned text, so the entire prompt/citation/empty-
  context contract is deterministic and network-free.
  `make_openrouter_client` builds a real one, imported only by `main()`,
  never by the test suite. Unit tests should verify *this project's*
  logic, not a third-party model's behavior - and today's reasoning-leak
  bug is direct evidence why: it was a live-provider-only failure mode, so
  it could only ever have been caught by actually running the live call,
  never by a fake-client unit test, however thorough.

### What remains weak

- No faithfulness/groundedness or answer-relevance *scoring* exists yet —
  today's checks are structural (citations present, no orphans, empty
  context refuses), not "is this answer actually correct and complete."
  Q091's answer above had perfect citation hygiene and was still
  incomplete; nothing automated caught that today, a human comparison
  against `expected_answer` did.
- The `multi_doc` retrieval weakness (Day 9) now has a concrete downstream
  cost: it silently shows up as missing evidence in a generated answer,
  not just a lower P@1 number. Not re-fixed today — Day 10's scope was the
  generation layer, not going back to retrieval.
- Today's committed transcript is still one sample per query, not a
  distribution — but it is worth being honest about how much variance
  actually showed up along the way: six live re-runs across two different
  free models (chasing the reproducibility fixes in "Review feedback
  addressed" below) produced answers ranging from clean and complete, to
  fully hallucinated and off-topic, to a hard crash on blank content. That
  is not a one-off fluke; it is a real property of relying on a free-tier
  hosted model for a "reproducible" demo, and it is exactly why this
  module keeps live calls out of the deterministic `pytest` gate.
- No LangGraph agents, serving, RAGAS/DeepEval integration, or streaming —
  out of scope by design for Day 10 (see the design doc).

### Next step

- Day 11: deepen grounded-answer evaluation before moving on to Chapter 11
  Agentic - source-cited generation is solid at the *contract* level
  (citations present, traceable, empty-context refuses), but Q091 proved
  today that contract passing and answer correctness are not the same
  thing, and right now the only way to tell them apart is a human reading
  the output against `expected_answer` by hand. The concrete next-layer
  candidates, in priority order: (1) a faithfulness/groundedness check
  that verifies a cited source's text actually *supports* the claim next
  to it, not just that the source number exists - a stronger bar than
  today's `validate_citations`; (2) an answer-completeness check against
  `expected_answer` for at least the `multi_doc` slice, so a case like
  Q091 is caught automatically instead of by manual inspection; (3) as a
  secondary, parallel track - not blocking (1)/(2) - revisit the `multi_doc`
  retrieval gap itself (`POL-001`/`GUIDE-002` missing from Q091's top-5),
  since Day 10 gave that Day 9 weak slice a concrete, visible downstream
  cost for the first time.

## 2026-09-15 — Day 11: Grounded-Answer Evaluation + Completeness Checks

### What I built or drafted

- Drafted Day 11 route in `docs/day-11-grounded-answer-evaluation.md`.
- Built `src/generation_eval.py` (four deterministic checks — citation
  validity, retrieval-context recall, curated expected-terms coverage,
  hedge-phrase inference flag — plus `evaluate_generated_answer` wiring
  them together and `CURATED_FIXTURES` holding Day 10's real Q001/Q091
  sources and answer text) and `tests/test_generation_eval.py` (16
  deterministic tests, no network calls). See `docs/eval-report.md`'s "Day
  11: Grounded-answer evaluation + completeness checks" for the full
  contract, real command output, and known limitations.

### Course checkpoint completed

- Boot.dev RAG chapter/lesson: Chapter 10 — Augmented Generation, reactivated as an evaluation lens before moving to Chapter 11 Agentic.
  - Lesson 1: `Augmented Generation` — Completed.
  - Lesson 2: `LLM Summarization` — Completed.
  - Lesson 3: `Conflict Resolution in Summaries` — Completed.
  - Lesson 4: `Adding Citations` — Completed.
  - Lesson 5: `Question Answering` — Completed.
- Companion source notes: DeepEval/RAGAS vocabulary for faithfulness, answer/response relevancy, context precision/recall/relevancy, factual correctness, semantic similarity, and deterministic string/exact-match checks — used only as a mapping target, not integrated. `context_recall` is the deterministic, id-level ancestor of contextual/context recall; `citation_validity` + `unsupported_inference` together are a narrow, deterministic slice of faithfulness; `expected_terms` is a hand-curated, substring-level stand-in for factual correctness. See `docs/eval-report.md`'s Day 11 "Mapping to DeepEval/RAGAS vocabulary" section.

### Baseline evidence

- Kickoff checks:
  - `./.venv/bin/pytest -q` → `135 passed in 2.44s`.
  - `./.venv/bin/python -m compileall -q src tests` → clean, no output.
  - `./.venv/bin/python -m ruff check src tests` → `All checks passed!`.
- Starting weakness: Day 10's Q091 answer had valid citations and zero orphan source ids, but still missed key expected evidence because `POL-001` and `GUIDE-002` were absent from the top-5 context. Day 11 exists to make that kind of gap visible in deterministic eval output.

### Generation-eval contract / methodology evidence

- Eval input shape: `evaluate_generated_answer(query_row, sources, answer_text, required_terms=None)`
  — `query_row` is a real row from `data/corpus_v1/example_queries.jsonl`
  (needs `query_id` and `relevance_grades`), `sources` is Day 10's
  `generation.build_sources` output shape, `answer_text` is the generated
  answer string, `required_terms` is an optional hand-curated tuple of
  facts a curated query's answer must mention.
- Finding/output shape (`make_finding`): `query_id`, `check`, `passed`,
  `severity` (`"info"`/`"fail"`/`"warn"`), `message`, `expected`, `actual`,
  `cited_doc_ids` — every finding carries `cited_doc_ids`, not just
  citation-related ones, so a reader never has to cross-reference a
  separate report.
- Checks implemented (`src/generation_eval.py`):
  - Citation validity / orphan source ids: `check_citation_validity` —
    reuses `generation.validate_citations` unchanged, fails on a
    hallucinated `[n]`.
  - Retrieval-context recall / missing expected docs: `check_context_recall`
    — compares grade-2 ("primary") `relevance_grades` doc ids against every
    doc id in the retrieved `sources`, independent of citation. This is
    the check that automatically catches Q091.
  - Answer completeness against expected answer/evidence: `check_expected_terms`
    — case-insensitive substring match against a hand-curated
    `required_terms` list, curated queries only.
  - Source-support / faithfulness proxy: `check_unsupported_inference` —
    scans for a hand-curated list of hedge/extrapolation phrases
    (`"at minimum"`, `"equal or greater"`, ...); a hit is `severity="warn"`,
    a flag for human/LLM-as-judge review, not a proven violation.

### Artifact / test evidence

- Files created: `src/generation_eval.py`, `tests/test_generation_eval.py`.
  Files modified: `docs/eval-report.md` (new "Day 11" section),
  `docs/learning-log.md` (this entry).
- Deterministic tests: `./.venv/bin/pytest -q` → `151 passed in 0.67s`
  (135 before Day 11 + 16 new in `tests/test_generation_eval.py`).
- Compile/lint gates: `./.venv/bin/python -m compileall -q src tests` →
  clean, no output. `./.venv/bin/python -m ruff check src tests` → `All
  checks passed!`.
- Demo / CLI output: `./.venv/bin/python src/generation_eval.py` — see
  `docs/eval-report.md`'s Day 11 "Demo output" section for the full,
  real, unedited transcript.
- Q091 failure evidence: `context_recall` fails automatically and names
  the exact missing primary documents (`GUIDE-002`, `POL-001`);
  `expected_terms` fails as the direct downstream consequence (the answer
  never says "Band 3" or references usage data); `unsupported_inference`
  flags the exact sentence where the model reasoned past its evidence
  ("...equal or greater significance, so this approval level applies at
  minimum"). All three run against Q091's *real* `relevance_grades` loaded
  from `data/corpus_v1/example_queries.jsonl`, not a hand-typed stand-in
  (`tests/test_generation_eval.py::test_curated_q091_fixture_is_caught_automatically_not_just_by_reading_it`).
- Passing-control evidence: Q001's real Day 10 transcript passes all four
  checks — `POL-001` (its one primary document) is in the retrieved
  context, its citations have zero orphans, its curated required terms
  ("VP Procurement", "Finance review") both appear in the answer, and no
  hedge-phrase pattern is present
  (`tests/test_generation_eval.py::test_curated_q001_fixture_passes_every_check`).


### What failed or was confusing

- Three failure classes are easy to conflate at first, and only one of them was covered before today: (1) an **orphan citation** — cites `[7]` when only 5 sources exist (Day 10's `validate_citations` catches this). (2) A **valid-but-unsupported citation** — cites `[3]`, and `[3]` is real, but the sentence next to it claims more than `[3]` actually says (nothing in this project mechanically proves this; `check_unsupported_inference`'s hedge-phrase scan is only a weak, indirect proxy for it — that's *why* it's `severity="warn"`, not `"fail"`). (3) An answer whose individual cited claims are all fine, but that omits required evidence entirely because that evidence was never retrieved (`check_context_recall` catches this — it's the new one Day 11 adds).
- `check_context_recall` deliberately checks **every retrieved source**, not just the cited ones. It would be an easy, wrong shortcut to check it against cited docs only — that would just be re-measuring citation behavior again, not the actual retrieval gap.
- The `"12 months"` collision in Q091's real transcript (POL-003's unrelated risk-acceptance clause happens to use the same phrase `GUIDE-002`'s renewal-timing evidence would have used) is the clearest proof that a plain substring check for `check_expected_terms` is fragile by construction — not a bug to fix later, a property of the method that has to be worked around by picking required terms carefully, by hand, after reading the real text.

### What became clearer

- Why a source id proves *traceability*, not *support*: `[3]` existing and being cited only proves the model didn't invent a source number out of nothing. It proves nothing about whether the sentence sitting next to `[3]` is actually what source `[3]`'s text says.
- Why completeness needs *reference evidence*, not just a coherent-sounding answer: an answer can be fluent, internally consistent, and still wrong by omission if the right chunk never reached the prompt. `expected_answer` / `relevance_grades` are the only way to catch that from outside the model — reading the answer alone can't, because there's nothing in the answer itself that flags what's missing.
- Why retrieval-context recall and generated-answer faithfulness are separate axes, not two views of the same thing: they are genuinely different systems (retrieval vs. generation) failing in different ways, and Q091 proves they move independently — it has *good* faithfulness behavior (zero orphan citations, no fabricated source numbers) and *bad* context recall (two of three primary documents missing) at the same time.

### What I can now explain in an interview

- **Citation validity vs. source support:** citation validity (`check_citation_validity`, reusing Day 10's `validate_citations`) only proves a `[n]` number maps to a real retrieved source — an integrity check on the numbering, blind to sentence content. Source support/faithfulness would require actually reading the cited source's text and confirming it backs the specific claim next to it. Day 11 does not solve this: `check_unsupported_inference`'s hedge-phrase scan is a shallow, hand-curated proxy, not a real support check — which is exactly why it returns `severity="warn"` instead of `"fail"`.
- **Faithfulness/groundedness vs. answer completeness:** faithfulness asks "is everything the answer states backed by the context it actually saw?" Completeness asks "does the answer cover everything the query needs, including evidence retrieval never surfaced?" An answer can be perfectly faithful to an incomplete context and still be a wrong/incomplete answer overall — that is exactly Q091: faithful to what it saw (no orphan citations), incomplete relative to `expected_answer` (missing `POL-001`/`GUIDE-002`), and those two properties are measured by different checks (`unsupported_inference` vs. `context_recall` + `expected_terms`) because they can fail independently.
- **Why Q091 is a better eval target than only Q001:** Q001 passes every check trivially, because its one primary document (`POL-001`) was retrieved and its answer echoes the retrieved sources directly — it proves the happy path works, but proves nothing about whether the eval layer can *catch* a failure. Q091 is a real, already-documented failure (`multi_doc`, two of three primary documents missing from the retrieved context) that a citation-only check is structurally blind to — it's the fixture that actually tests whether Day 11's checks do their job, not just whether they run without crashing.
- **Why deterministic fixtures come before LLM-as-judge frameworks:** the deterministic checks here are exact set/substring comparisons — reproducible, free, and inspectable in a few lines, calibrated against a failure this project already knows is real (Q091). An LLM-as-judge metric (DeepEval/RAGAS faithfulness) needs its own rubric, its own model choice, and its own calibration examples before its score means anything at all — building the hand-checked baseline first is what would let a future judge model's score actually be graded against something known-correct, instead of trusted on faith.
- **How this maps to DeepEval/RAGAS terms later:** `check_context_recall` is the deterministic, id-level ancestor of DeepEval's contextual recall / RAGAS's context recall (exact set membership here, an LLM judgment call there). `check_citation_validity` plus `check_unsupported_inference` together are a narrow, deterministic slice of faithfulness — citation validity proves the *traceability* half exactly, the hedge-phrase scan only ever approximates the *support* half. `check_expected_terms` is a hand-curated, substring-level stand-in for factual correctness / a curated slice of answer relevancy. Answer relevancy itself (is the answer actually on-topic for the question asked) isn't attempted at all yet.

### What remains weak

- `CURATED_FIXTURES` freezes Day 10's real transcript, captured when
  `MAX_ANSWER_TOKENS` was 2400 — that value is 3000 now (bumped the same
  day, `docs/eval-report.md`'s Day 11 addendum has the full note), and a
  fresh live run confirmed the Q091 wording actually differs today.
  `check_context_recall` is unaffected (it only reads `sources`/
  `relevance_grades`, not `answer_text`), but `check_expected_terms` and
  `check_unsupported_inference` are graded against a frozen transcript,
  not current model behavior — a deliberate tradeoff for determinism, but
  a real one, not a hidden one.
- `check_expected_terms` only has curated terms for 2 of the 93 v1 queries (Q001, Q091) — there is no generic coverage, by design, and extending it means hand-reading more `expected_answer`s.
- `check_unsupported_inference`'s hedge-phrase list is hand-picked and small — a model that extrapolates without using one of those specific phrases sails through undetected.
- `check_context_recall` passes vacuously on any query with zero grade-2 (`relevance_grades`) documents — a real gap named in its own docstring, not hidden.
- No real claim-level source-support check exists yet — confirming that a *specific* cited sentence is actually backed by its source's text (not just that the source number is real) is still the single largest gap the Day 11 design doc named up front.
- The underlying `multi_doc` retrieval weakness (Day 9's reranked `multi_doc` P@1 at 0.600 over 5 queries) is still unfixed — Day 11 only makes its downstream effect on the generated answer visible in code; it does not repair retrieval.
- No framework-backed (DeepEval/RAGAS) run has happened yet — comparing this project's hand-built checks against a real LLM-judge score, to see where they agree and disagree, is still future work.

### Next step

- Two real options, per the design doc's own framing of Day 11 as a bridge day: (a) extend `check_expected_terms`-style curated fixtures to a wider sample of the 93 queries before trusting the pattern generally, or (b) the harder step — a first LLM-as-judge faithfulness pass, calibrated against Q001 (known-good) and Q091 (known-incomplete) as anchor examples, so a judge model's score has something concrete to be checked against. Either is reasonable before starting Chapter 11 Agentic; the design doc's own stop condition only requires that this deterministic layer exist and be explainable, not that the next layer already be built.

## 2026-09-15 — Day 12: DeepEval/RAGAS Faithfulness Harness

### What I built or drafted

- Drafted Day 12 route in `docs/day-12-deepeval-ragas-faithfulness-harness.md`.
- `src/framework_eval.py` — the framework-eval bridge: a framework-neutral eval-case builder (`build_framework_eval_case`), dependency/key status checks (`deepeval_status`, `ragas_status`), per-framework adapters (`to_deepeval_test_case`, `to_ragas_sample`), and per-framework live-judge runners (`run_deepeval_faithfulness`, `run_ragas_faithfulness`), all behind an explicit `live=False`-by-default parameter.
- `tests/test_framework_eval.py` — 16 new deterministic tests (adapter shape, source-order preservation, no-key behavior, no-dependency behavior via `sys.modules` patching, and proof that `live=False` never imports the framework).
- Fixed two real, reproducible environment blockers before any of the above could run live: DeepEval's OpenRouter judge model was misconfigured (a typo, `openai/gpt-4.o-mini` instead of `openai/gpt-4o-mini`), and RAGAS failed to import at all (an upstream packaging bug — see "What failed or was confusing" below). Both fixed and verified live.
- `docs/eval-report.md` — new "Day 12" section: environment fixes, the adapter contract, real command output (deterministic + live), a caught judge-reasoning error, and the Q001/Q091 calibration interpretation.

### Course / framework checkpoint completed

- Boot.dev RAG chapter/lesson: **No new Boot.dev chapter today.** Chapter 10 — Augmented Generation is completed and serves as the baseline; Chapter 11 — Agentic remains deferred until this eval layer is understood.
- DeepEval docs read (all marked completed in the route doc before building):
  - `Introduction to LLM Evaluation Metrics` — core concept is test case + metric → 0–1 score + reason + threshold pass/fail; RAG metrics split into retriever-side (contextual precision/recall/relevancy) vs. generator-side (faithfulness, answer relevancy) metrics; every metric has a fixed required-field contract on `LLMTestCase`.
  - `Faithfulness` — checks whether `actual_output` factually aligns with `retrieval_context`; required fields `input`/`actual_output`/`retrieval_context`; distinct from `HallucinationMetric` because it's scoped to *this answer's cited context*, not general world-knowledge hallucination.
  - `Answer Relevancy` — referenceless, only needs `input`/`actual_output`; checks whether the answer addresses the question, not whether it's factually correct — an answer can be perfectly on-topic and still wrong.
  - `Contextual Relevancy` — retriever-quality metric: is `retrieval_context` relevant to `input`; still requires `actual_output` on the test case even though the metric itself barely uses it.
  - `Contextual Recall` — needs `input`/`actual_output`/`expected_output`/`retrieval_context`; checks whether the retrieved context contains what's needed to support the *expected* answer, not the actual one — closest framework analogue to `generation_eval.check_context_recall`, except DeepEval's version is LLM-judged text overlap and this project's is deterministic doc-id set membership.
  - `Contextual Precision` — same four required fields as contextual recall; checks whether relevant chunks are ranked above irrelevant ones — maps to this project's existing P@1/R@5/MRR@10/nDCG@5, but judged semantically rather than via graded relevance labels.
  - `RAGAS` wrapper page (skimmed) — DeepEval can wrap RAGAS's own metrics, but DeepEval's docs recommend its native metrics for debuggability/reasoning/JSON confinement/pytest integration — confirms building directly against both frameworks' native APIs (as done today) rather than through DeepEval's RAGAS wrapper was the right call for actually *comparing* them.
- RAGAS docs read (all marked completed in the route doc before building):
  - `Metrics` overview — taxonomy: Context Precision, Context Recall, Context Entities Recall, Noise Sensitivity, Response Relevancy, Faithfulness (RAG-specific), plus Factual Correctness/Semantic Similarity as non-RAG comparison metrics.
  - `Faithfulness` — factual consistency of `response` vs. `retrieved_contexts`, formula = supported claims / total claims, API shape `Faithfulness(llm=...).ascore(user_input=..., response=..., retrieved_contexts=[...])` — matches what `run_ragas_faithfulness` actually calls (via the sync `single_turn_score(SingleTurnSample(...))` wrapper instead of the async `ascore`, for a simpler teaching-module call site).
  - `Response Relevancy`/`Answer Relevancy` — generates synthetic questions from the response and compares them to the real question via embedding cosine similarity; explicitly does not prove factual correctness.
  - `Context Recall` — LLM-based: breaks the `reference` answer into claims and checks each against retrieved context; a non-LLM/ID-based variant exists and is the closer analogue to `generation_eval.check_context_recall`.
  - `Context Precision` — mean precision@k of relevant chunks in the retrieved list; has reference/no-reference/ID-based variants, with the ID-based one especially relevant given this project's stable `doc_id`/`chunk_id` fields.
  - Skimmed: Context Entities Recall (entity overlap, future procurement-entity use), Factual Correctness (claim-decomposition precision/recall/F1 — framework analogue to `check_expected_terms`), Semantic Similarity (embedding cosine similarity — explicitly warned not to use alone, since it can stay high even when a critical number or approval role is wrong).

### Baseline evidence

- Kickoff checks:
  - `./.venv/bin/pytest -q` → `151 passed in 1.84s`.
  - `./.venv/bin/python -m compileall -q src tests` → clean, no output.
- Starting weakness: Day 11 has deterministic Q001/Q091 eval fixtures, but no framework-backed LLM-as-judge score yet. The key open question is whether DeepEval/RAGAS faithfulness/context metrics agree with the hand-built deterministic findings and where they disagree.

### Framework-eval adapter / methodology evidence

- Adapter input shape chosen: a plain dict (`build_framework_eval_case`) with `query_id`/`input`/`actual_output`/`expected_output`/`retrieval_context`/`source_metadata`/`deterministic_findings` — matches the rest of the project's plain-dict convention (no dataclasses/pydantic anywhere in `generation.py`/`generation_eval.py`), built once and reshaped per framework by two small `to_*` functions rather than one function branching on framework.
- Framework(s) attempted: both DeepEval and RAGAS, both reached a real live call successfully after fixing the two environment blockers (see below).
- Metric targeted: faithfulness only, through both frameworks, per the design doc's "pick one first live metric" guidance.
- Result shape chosen: `framework`, `metric`, `query_id`, `score`, `threshold`, `passed`, `reason`, `status`, `error`, `judge_model` (`make_eval_result`) — `status` is one of `"skipped"` (`live=False`, the default, zero network), `"blocked"` (dependency/key missing), `"ok"`, or `"error"` (live call raised, caught rather than crashing a multi-query sweep).
- No-key/no-dependency behavior: `deepeval_status()`/`ragas_status()` return `("blocked", reason)` — never raise — checked by an in-function `import` (proven "not installed" via `monkeypatch.setitem(sys.modules, "deepeval"/"ragas", None)`, since both are real installed dependencies here) and an `OPENROUTER_API_KEY` presence check. `run_*_faithfulness(case, live=False)` (the default) returns `status="skipped"` *before* importing the framework at all — proven, not just asserted, by a test that poisons `sys.modules` and confirms the function still returns cleanly.
- Calibration examples:
  - Q001 expected behavior: should score high on faithfulness (its real transcript only makes claims its cited sources support). Actual: DeepEval 0.80/PASS, RAGAS 0.43/FAIL — see "What failed or was confusing" for why DeepEval's *reason* for not scoring 1.0 was itself factually wrong, and RAGAS gave no reason at all to check.
  - Q091 expected behavior: per the design doc's own prediction, faithfulness might *not* catch Q091's missing-evidence problem, because the real transcript never invents anything beyond its five retrieved sources — it's faithful to what it saw, just incomplete. Actual: exactly that. DeepEval 0.80/PASS, RAGAS 0.55/PASS — both frameworks passed Q091 on faithfulness, while Day 11's deterministic `check_context_recall` still correctly fails it for missing `POL-001`/`GUIDE-002`. This is the clean confirmation the design doc predicted, seen in real judge output.

### Artifact / test evidence

- Files created/modified: `src/framework_eval.py` (new), `tests/test_framework_eval.py` (new), `docs/eval-report.md` (Day 12 section added), `docs/learning-log.md` (this entry), `pyproject.toml`/`uv.lock` (`langchain-community` pinned `<0.4`, `pillow` added), `.deepeval/.deepeval` (model name corrected via CLI, not hand-edited).
- Deterministic tests: `./.venv/bin/pytest -q` → `167 passed in 1.12s` (151 prior + 16 new, zero network calls — the new tests explicitly poison `sys.modules` for `deepeval`/`ragas` in several cases and still pass, proving no accidental import happens on the `live=False` path).
- Compile/lint gates: `./.venv/bin/python -m compileall -q src tests` → clean; `./.venv/bin/python -m ruff check src tests` → `All checks passed!`.
- Framework/live judge status: **ran live**, both frameworks, both fixtures — `./.venv/bin/python src/framework_eval.py --live` — 4 real OpenRouter calls via `openai/gpt-4o-mini`, real scores and (for DeepEval) real reason text recorded verbatim in `docs/eval-report.md`.
- Eval report update: `docs/eval-report.md` → new "Day 12: DeepEval/RAGAS faithfulness harness" section — environment-fix writeup, adapter contract tables, deterministic + live command output, a documented DeepEval judge-reasoning error, the Q001/Q091 calibration interpretation, a deterministic-vs-judge trust table, and caveats.

### What failed or was confusing

- **RAGAS didn't import at all, for two separate reasons, before any adapter code could even be tested.** First: `ragas==0.3.1`'s `ragas/llms/base.py` does an unconditional top-level `from langchain_community.chat_models.vertexai import ChatVertexAI` — but `ragas`'s own PyPI metadata has no upper-bound pin on `langchain-community`, so `uv` had resolved `langchain-community==0.4.2` (released 2026-05-22), which no longer ships that submodule at all (confirmed by listing the installed package's files, and by downloading the `0.3.31` wheel from PyPI directly and confirming *it* still has the file). Fixed with `uv add "langchain-community<0.4"`. Second, immediately after: `ragas/prompt/multi_modal_prompt.py` does an unconditional `from PIL import Image`, and `Pillow` is not declared anywhere in `ragas`'s `Requires-Dist` — a second, real, undeclared-dependency packaging bug. Fixed with `uv add pillow`. Both are genuine upstream `ragas==0.3.1` packaging issues, not local misconfiguration — and notably, neither has anything to do with Python version (`ragas`'s own metadata declares `Requires-Python: >=3.9`, well under this project's 3.11.7). The route doc's note about a Python 3.12 requirement for something called `rag_eval` doesn't correspond to anything in this repo's actual dependency graph.
- **DeepEval's previously-configured OpenRouter model was a typo that would have silently broken every live call.** `.deepeval/.deepeval` had `"OPENROUTER_MODEL_NAME": "openai/gpt-4.o-mini"` (an extra `.`) from an earlier `deepeval set-openrouter` run. Checked against OpenRouter's live `/models` endpoint: that exact string doesn't exist; `openai/gpt-4o-mini` does. Re-ran `deepeval set-openrouter --model="openai/gpt-4o-mini"` to fix it, confirmed via `deepeval diagnose`.
- **A live judge's stated reason can be confidently wrong.** DeepEval's Q001 faithfulness reason claimed the retrieval context "clearly states it does not trigger a competition requirement due to being below the €250,000 threshold" — backwards: €60,000 is *above* the €25,000 floor that triggers the three-bid requirement, and the real Q001 answer correctly says so, citing the right sources. The judge still produced a fluent, wrong-direction explanation for a sub-1.0 score. Caught only because Q001's real answer text was already known to be correct — exactly the point of using it as a calibration anchor rather than trusting the first live score that comes back.
- Expected confusion, confirmed exactly as predicted: faithfulness stayed high (both frameworks passed) on Q091 despite it being a known-incomplete answer, because faithfulness only checks the answer against the context it *did* see — it has no way to know `POL-001`/`GUIDE-002` should have been there. Context recall (Day 11's deterministic version) is what actually catches that, and did.

### What became clearer

- The Day 11 vs. Day 12 boundary is not "deterministic checks are the rough draft, framework metrics are the real answer" — it's two genuinely different failure classes, and today's live run proved it rather than just asserting it: Day 11's `check_context_recall` is the *only* layer that caught Q091's real problem (missing primary documents); DeepEval/RAGAS faithfulness, run live, both said Q091 was fine.
- A framework score without a reason (RAGAS) is much harder to trust or debug than a framework score with a wrong reason (DeepEval) — at least the wrong reason is falsifiable against the known-good Q001 transcript. A bare float has nothing to push back against.
- "Add a framework judge" is not a one-line `pip install` in practice — both frameworks needed real environment debugging (a config typo, two separate unrelated upstream packaging bugs) before a single live call would succeed, which is itself a realistic, worth-remembering lesson about framework-eval adoption cost.

### What I can now explain in an interview

- **Faithfulness vs answer relevancy:** faithfulness checks whether the answer's claims are supported by the retrieved context it was given (`input`/`actual_output`/`retrieval_context`); answer relevancy checks whether the answer actually addresses the question asked (`input`/`actual_output` only, no context needed). An answer can be faithful but off-topic, or relevant but unsupported by its sources — they catch different failure modes and neither implies the other.
- **Context recall vs context precision:** context recall asks "does the retrieved context contain what's needed to support the *expected* answer" (recall — are we missing evidence); context precision asks "are the relevant chunks ranked above the irrelevant ones" (precision — is the good evidence buried under noise). Both need `expected_output` (or a reference), unlike faithfulness/relevancy.
- **Why Q001/Q091 calibrate the judge:** without a case whose real answer is already known to be fully correct (Q001) and one known to be subtly incomplete (Q091), a judge's score has nothing concrete to be checked against — today's DeepEval Q001 run is the proof: the score alone (0.80) looked plausible, but only cross-checking against the known-correct Q001 transcript revealed the *reason* behind that score was factually backwards.
- **Why LLM-as-judge scores need thresholds, reasons, and caveats:** a bare score is a single number produced by a model that can misread its own cited evidence, as shown today, live, not hypothetically. A reason string makes that checkable by a human; a threshold makes pass/fail explicit and adjustable; without both, a score is unfalsifiable.
- **How ProcureRAG data maps to DeepEval/RAGAS test cases:** `query_row["query"]` → `input`/`user_input`; the generated answer text → `actual_output`/`response`; `[source["text"] for source in sources]`, order preserved → `retrieval_context`/`retrieved_contexts`; `query_row["expected_answer"]` → `expected_output` (DeepEval only uses this for contextual recall, not faithfulness; RAGAS's `Faithfulness` doesn't use it at all).

### What remains weak

- Only faithfulness was run live; answer relevancy, contextual recall/precision, and factual correctness are adapter-ready (the neutral case already carries `expected_output`) but genuinely untested against a live judge — the DeepEval-vs-RAGAS reasoning gap seen today on faithfulness might look different on a metric that uses `expected_output`.
- Both live results are a single sample per (query, framework) pair — no repeated-run variance check was done, so whether DeepEval's 0.80/0.80 or RAGAS's 0.43/0.55 would hold up across repeated calls (temperature is set to 0.0 for both, but that doesn't guarantee byte-identical judge output on a hosted API — see `generation.py`'s own caveat about this for the answer-generation model) is unverified.
- (Corrected by the review-feedback pass below: RAGAS's `status="error"` path *was* exercised live, by a real `max_tokens`-too-small provider failure on Q091.) DeepEval's `status="error"` path specifically still remains proven only by the deterministic `live=False` tests, not by a real live failure.
- No claim-level, sentence-by-sentence support check exists yet at either the deterministic or framework layer for *individual* citations (e.g. "is citation `[3]` specifically supported by source 3's text, not just some source somewhere") — Day 11's own named gap, still open after Day 12.

### Next step

- Wire DeepEval's contextual recall (needs `expected_output`, already in the neutral case) as a second live metric, specifically because it is the framework metric closest in spirit to Day 11's `check_context_recall` — a natural next calibration test would be whether contextual recall, unlike faithfulness, *does* penalize Q091 for its missing `POL-001`/`GUIDE-002` evidence, the way this session's plain faithfulness run did not.

### Review-feedback fixes (same day)

A review of the first Day 12 pass raised five points; all five addressed, most important first:

1. **The Q001/Q091 fixtures' `sources[].text` were abbreviated representative quotes, not the literal chunks Day 10's model actually saw** — fine for Day 11's deterministic checks (doc-id/citation-based, never touch `text`), but a real problem for a faithfulness judge, which scores the answer *against* `retrieval_context`. Fixed by re-running the real retrieval pipeline (deterministic, no LLM) for Q001/Q091, confirming the retrieved `doc_id` order still matched Day 10's original transcript exactly, and swapping in the full chunk text + real `chunk_id` in `src/generation_eval.py`. Re-running the live judges afterward showed this wasn't cosmetic: RAGAS's Q001 score moved off a rock-steady 0.43 (identical across three abbreviated-context runs) to 0.57–0.64, and Q091 went from 0.55–0.92 range to a clean 1.00 on both frameworks. One DeepEval reasoning error about the three-bid threshold rule survived the fix unchanged, though — better evidence didn't fix every failure mode, which is itself the finding worth keeping.
2. **The RAGAS judge call (`ChatOpenAI`, built by hand in `run_ragas_faithfulness`) had no timeout or token cap** — the same live-provider-hang/truncation risk Day 10 already hit once. Fixed by reusing `generation.OPENROUTER_TIMEOUT_SECONDS` and adding `JUDGE_MAX_TOKENS`. That constant needed its own real trial, same as Day 10's `MAX_ANSWER_TOKENS`: 1024 worked for Q001 but RAGAS genuinely failed on Q091 with "the LLM generation was not completed" — caught cleanly by the existing `status="error"` path rather than crashing, which was a good, if accidental, first live proof that path actually works. Raised to 4096.
3. **`langchain_openai` was imported directly but only declared transitively** (pulled in via `ragas`) — a real dependency-discipline gap, especially right after two separate live `ragas` packaging bugs this same day. Fixed with `uv add langchain-openai` (same resolved version, now direct).
4. **Docs said the deterministic test suite "never reaches deepeval/ragas"** — true only for the default `live=False` runner path. The adapter-shape tests (`to_deepeval_test_case`/`to_ragas_sample`) do import and construct real `LLMTestCase`/`SingleTurnSample` objects; they just never touch the network. Corrected the wording everywhere it appeared: default runner path never imports either framework; adapter-shape tests do import, but stay network-free.
5. **`deepeval_status()`/`ragas_status() == "available"` only means "importable + key present," not "a live call will work"** — Day 12's own model-typo bug (point 1 back in the original build) is the proof: that check would have read `"available"` the whole time the typo was live, since a broken model string isn't visible to an import or key-presence check. Documented explicitly in both functions' docstrings rather than left implicit.

What this confirmed about the review process itself: the first-pass harness wasn't wrong about its *mechanics* (adapter shape, dependency boundary, live/skip gating all held up under review) — the gaps were in evidence fidelity (abbreviated context), operational hardening (no timeout/cap), dependency hygiene (transitive-only import), and precision of claims (what "deterministic" actually covers). All four are exactly the kind of thing that's invisible from inside the code that wrote itself and obvious from a second, adversarial read — which is the whole argument for getting one before calling a harness "done."

## 2026-09-19 — Day 13: Generation Error Analysis + Multi-Doc Repair Plan

### What I built or drafted

- Drafted Day 13 route in `docs/day-13-generation-error-analysis-multidoc-repair-plan.md`.
- `src/error_analysis.py` (new): a six-label failure taxonomy
  (`ROOT_CAUSE_LABELS`), a `build_case_record` function that reuses Day 11's
  `evaluate_generated_answer` unchanged and packages its findings into one
  human-labeled case, and `build_cases`, which assembles the five real Day
  13 cases (Q001/Q091 reused from `generation_eval.CURATED_FIXTURES`;
  Q093/Q016/Q004 built from a fresh, real retrieval run plus one live
  OpenRouter generation call each, captured today).
- `src/framework_eval.py`: added `run_deepeval_contextual_recall`, wiring
  DeepEval's `ContextualRecallMetric` with the exact same
  skip/blocked/ok/error contract `run_deepeval_faithfulness` already uses.
- `tests/test_error_analysis.py` (new, 8 tests) and two new tests in
  `tests/test_framework_eval.py` for the contextual-recall wiring.
- `docs/eval-report.md` — new "Day 13: Generation error analysis + multi-doc
  repair plan" section with the full case table, root-cause writeups, the
  live DeepEval contextual-recall comparison, and the recommended repair
  path.

### Course / framework checkpoint completed

- Boot.dev RAG chapter/lesson: **No new Boot.dev chapter today.** Chapter 10 — Augmented Generation remains the baseline; Chapter 11 — Agentic is still deferred until the generation-eval / error-analysis loop is explainable.
  - Chapter 10 Lesson 1: `Augmented Generation` — reactivated.
  - Chapter 10 Lesson 2: `LLM Summarization` — reactivated.
  - Chapter 10 Lesson 3: `Conflict Resolution in Summaries` — reactivated.
  - Chapter 10 Lesson 4: `Adding Citations` — reactivated.
  - Chapter 10 Lesson 5: `Question Answering` — reactivated.
- DeepEval docs checkpoint:
  - `Contextual Recall` — needs `input`/`actual_output`/`expected_output`/`retrieval_context` (confirmed against the installed `deepeval==4.2.3` `ContextualRecallMetric` constructor signature directly, not just the docs page). Maps onto ProcureRAG as: `query_row["query"]` → `input`, the generated answer → `actual_output`, `query_row["expected_answer"]` → `expected_output`, `[source["text"] for source in sources]` → `retrieval_context` — the same four fields `to_deepeval_test_case` already builds for faithfulness, since faithfulness just never used the third one. Ran it live against Q001/Q091 today (see `docs/eval-report.md`): it is the framework metric closest to `check_context_recall` in spirit, but scored Q091 0.80/PASS despite two whole primary documents being absent — a real, live-caught limitation, not a hypothetical one.
  - `Contextual Precision` — ranking-order metric: are relevant chunks ranked above irrelevant ones, same four required fields as contextual recall. Not run live today. It answers a different question than P@1/R@5/MRR@10/nDCG@5 (which use this project's own graded relevance labels, not an LLM judge's semantic read) and is not a replacement for them — a good future contrast metric, not a priority ahead of the error-analysis work this day was actually about.
  - `Answer Relevancy` — only needs `input`/`actual_output`, no expected answer or retrieval context. Explicitly the wrong metric for Day 13's question: an answer can be perfectly on-topic (highly "relevant") and still be exactly Q091's failure mode — incomplete because of missing evidence — since relevancy never looks at whether the right evidence was retrieved at all.
- RAGAS docs checkpoint:
  - `Context Recall` — LLM-based variant breaks a reference answer into claims and checks each against retrieved context; a non-LLM/string-matching variant exists as a deterministic contrast; the ID-based variant compares `retrieved_context_ids` against `reference_context_ids` directly — the closest RAGAS analogue to this project's own `check_context_recall`, since ProcureRAG already has stable `doc_id`/`chunk_id` fields on every source. Not wired or run live this session (DeepEval's contextual recall was the one live metric added today, per the "pick one first metric" convention Day 12 established) — a natural next-day candidate specifically because the ID-based variant would compare doc-id sets the same deterministic way the existing check already does, rather than relying on an LLM's sentence-level judgment.
  - `Context Precision` — mean precision@k of relevant chunks; has a reference-answer variant, a no-reference `ContextUtilization` variant, and documented ranking-sensitivity behavior (the score moves if the same relevant/irrelevant chunks are reordered). Not run today; same ranking-vs-coverage distinction as DeepEval's contextual precision above.
- Error-analysis method checkpoint:
  - Hamel/Shreya error-analysis reading — the actual method this day followed, not just read about: **Creating a Dataset** (five real traces — Q001/Q091 reused from already-committed Day 10 transcripts, Q093/Q016/Q004 from a fresh real retrieval + live generation run today, not synthetic placeholders); **Open Coding** (each case's `notes` in `src/error_analysis.py` is a human-written, open-ended read of that case's real evidence — e.g. noticing Q093's answer states one contract's deadband as if it were universal, which nothing in Day 11's existing checks was looking for); **Axial Coding** (grouping those open-coded notes into `ROOT_CAUSE_LABELS` — noticing `retrieval_miss` needed to cover two genuinely different situations, and that Q016 needed a sixth kind of label — `answer_completeness_gap` — because "context_recall passed" turned out not to mean "nothing is missing"); **Iterative Refinement** — explicitly *not* claimed complete after five cases (see `docs/eval-report.md`'s Day 13 caveats): `context_truncation_or_construction` and `citation_source_support_gap` are real labels no case today happened to need, and five traces is not enough to claim the taxonomy has stopped revealing new failure modes.

### Baseline evidence

- Kickoff checks:
  - `./.venv/bin/pytest -q` → `167 passed in 3.69s`.
  - `./.venv/bin/python -m compileall -q src tests` → clean, no output.
  - `./.venv/bin/python -m ruff check src tests` → `All checks passed!`.
- Starting weakness: Q091 remains the known anchor where Day 11 deterministic context recall fails for missing primary evidence (`POL-001`, `GUIDE-002`), while Day 12 faithfulness can still pass because the answer is judged against the incomplete context it saw.

### Failure taxonomy / case-inspection evidence

- Case record shape chosen (`build_case_record` in `src/error_analysis.py`):
  `query_id`, `query_type`, `difficulty`, `question`,
  `expected_primary_doc_ids` / `retrieved_doc_ids` /
  `missing_primary_doc_ids` (all read straight off Day 11's
  `check_context_recall` finding, not recomputed), `cited_doc_ids` /
  `citation_status` (off `check_citation_validity`), one
  `human_root_cause_label` (validated against `ROOT_CAUSE_LABELS`,
  `ValueError` on anything else), free-text `notes` /
  `recommended_repair` / `verification_signal` (human-written, not
  computed), and the full Day 11 `findings` list attached for anyone who
  wants the underlying detail without re-running anything.
- Failure taxonomy labels (`ROOT_CAUSE_LABELS`) — seven, after a review
  correction added the fifth one below (see "What failed or was confusing"):
  - `retrieval_miss` — a primary *document* never reached the retrieved
    context at all; no prompt or generation change could have fixed it,
    because the model was never shown the evidence.
  - `context_truncation_or_construction` — the evidence was found
    somewhere upstream in the pipeline but got cut before reaching the
    prompt (e.g. a `max_sources` cap). Not exercised by today's five cases,
    but named because it is a real, distinct way a case like this could
    fail without being a retrieval-miss.
  - `chunk_level_retrieval_gap` — the right *document* reached context
    (document-level `check_context_recall` passes), but the specific
    *chunk* of that document carrying the needed fact was never retrieved
    — a different chunk of the same document was. Q016's real failure
    mode, added after a review correction (see below) reclassified it away
    from `answer_completeness_gap`.
  - `citation_source_support_gap` — a citation points at a real, retrieved
    source (so `check_citation_validity` passes), but the specific claim
    next to that citation isn't actually supported by that source's text.
    Different from an orphan citation, which Day 11 already catches; also
    not exercised by today's five cases.
  - `answer_completeness_gap` — every chunk of every needed document
    reached context (both at the document level and the specific-chunk
    level), but the answer still leaves out something the query genuinely
    needed. **Not exercised by today's five cases** — Q016 was originally
    (mis)labeled this way; see "What failed or was confusing" for the
    correction.
  - `judge_or_metric_disagreement` — a deterministic finding and a live
    judge score disagree, or the judge's stated reason doesn't hold up
    against the real evidence. Q091's DeepEval contextual-recall run is a
    real, borderline example: not a flat contradiction, but a passing score
    (0.50–1.00 across repeated runs, see below) that tells a much softer
    story than Day 11's clean, invariant fail.
  - `passes_control` — every Day 11 check passes and the answer matches
    `expected_answer`. Q001 and Q004.

| Query | Slice / difficulty | Expected primary docs | Observed context docs | Root-cause label | Evidence note | Recommended repair / signal |
|---|---|---|---|---|---|---|
| Q001 | threshold / easy control | POL-001 | POL-001 (+ FAQ-001 secondary) | `passes_control` | Every Day 11 check passes; required terms present. | None needed — calibration control. |
| Q091 | multi_doc / hard anchor | `GUIDE-002`, `POL-001`, `POL-003` | `POL-003` only | `retrieval_miss` | Missing `POL-001`/`GUIDE-002` in generated-answer context is the known anchor finding; citations still clean, faithfulness 1.00/1.00 (Day 12). | Raise multi_doc top-k; verify `missing_primary_doc_ids == []`. |
| Q093 | multi_doc / hard sibling | `CONTRACT-001`, `CONTRACT-003`, `GUIDE-003`, `MEMO-001` | `CONTRACT-003`, `GUIDE-003`, `MEMO-001` (+`GUIDE-001` secondary) | `retrieval_miss` | Missing `CONTRACT-001` (Acme's 3% figure) makes the answer state Batavia's 2% deadband as if universal — a false-universal answer, not just an incomplete one. | Per-document diversity cap on the pre-rerank chunk shortlist. |
| Q016 | multi_doc / hard sibling | `GUIDE-001`, `POL-004` | `GUIDE-001`, `POL-004` (both present at the document level) | `chunk_level_retrieval_gap` | Document-level `check_context_recall` passes, but `GUIDE-001` is never cited: the specific chunk carrying the "logistics ≤40%" tier from `expected_answer` was never retrieved (a different `GUIDE-001` chunk was). Not a generation failure — the model never saw this chunk. | Retrieve a second chunk per document for multi_doc queries. |
| Q004 | lookup / medium, non-multi_doc contrast | POL-001 | POL-001 | `passes_control` | Straightforward single-document query works normally outside the multi_doc slice. | None needed — second calibration control. |

### Contextual-recall / framework evidence, if attempted

- DeepEval contextual recall: ran live, Q001 and Q091, via
  `run_deepeval_contextual_recall(case, live=True)` (`openai/gpt-4o-mini`,
  threshold 0.5, run with `PYTHONPATH=src` from repo root — see
  `docs/eval-report.md`'s Day 13 section for the exact command; the first
  documented command was missing `PYTHONPATH=src` and failed with
  `ModuleNotFoundError` when actually re-run from repo root, caught and
  fixed in review). Re-run twice back to back: Q001 scored 1.00 both
  times; Q091 scored **0.50 then 0.80 — PASS both times** at the 0.5
  threshold. Neither run's reason names the missing Band-3 approval-band
  citation or the missing 12-months-out usage-data guidance; each flagged a
  narrower, different gap instead (an unaddressed ISO 27001 mention in one
  run, the "HICP plus 2 percentage points" detail in the other). A later
  independent re-run (during review) saw Q001 dip to 0.75 and Q091 land at
  0.80–1.00 — confirming both queries' exact scores move between runs, not
  just Q091's.
- RAGAS context recall / ID-based context recall: not run this session —
  DeepEval's contextual recall was the one live metric added today, per
  the "pick one first metric" convention Day 12 already established. The
  ID-based RAGAS variant remains the most promising next candidate,
  specifically because it would compare `doc_id` sets the same
  deterministic way `check_context_recall` already does.
- Comparison to deterministic Day 11 `check_context_recall`: **they
  disagree in an important way on Q091, on every run observed.** Day 11's
  check fails cleanly, identically, every time: `POL-001` and `GUIDE-002`
  are named as missing, with no run-to-run variance possible (it's set
  membership over stable `doc_id`s, not an LLM judgment call). DeepEval's
  contextual recall **passed Q091 in all four runs observed** (0.50, 0.80,
  0.80, 1.00) and never once named the actual missing primary documents as
  its reason. **The stable finding is not the exact score - it's that the
  framework judge can pass Q091 across a real score range while
  deterministic context recall identifies the same missing primary
  evidence every time, with no variance to caveat.**
- Caveat: only two fresh live runs were captured this session (plus one
  independent review re-run reported back), not a large repeated-sample
  study - enough to prove real variance exists, not enough to characterize
  its distribution. `OPENROUTER_API_KEY` was present and every call
  succeeded on the first attempt; no dependency/key blocker was hit this
  session (unlike Day 12's environment-fixing detour). The documented
  command itself needed a fix mid-review (see above) - a reminder that a
  command block in a report is itself something worth actually re-running
  from a clean shell before trusting it, not just copy-pasted from a
  working session's history.

### Artifact / test evidence

- Files created or modified: `src/error_analysis.py` (new),
  `src/framework_eval.py` (`run_deepeval_contextual_recall` added, `main()`
  updated), `tests/test_error_analysis.py` (new), `tests/test_framework_eval.py`
  (two tests added), `docs/eval-report.md` (Day 13 section added),
  `docs/learning-log.md` (this entry).
- Deterministic tests: `./.venv/bin/pytest -q` → `177 passed in 1.11s`
  (167 baseline + 8 new in `tests/test_error_analysis.py` + 2 new in
  `tests/test_framework_eval.py`, zero network calls).
- Compile/lint gates: `./.venv/bin/python -m compileall -q src tests` →
  clean; `./.venv/bin/python -m ruff check src tests` → `All checks
  passed!`.
- Demo / eval output: `./.venv/bin/python src/error_analysis.py` prints all
  five cases' root cause, evidence, and repair recommendation with zero
  network calls (every fixture is already-captured real evidence);
  `./.venv/bin/python src/framework_eval.py --live` now also runs
  `run_deepeval_contextual_recall` for Q001/Q091 alongside the existing
  Day 12 faithfulness calls.
- Eval report update: `docs/eval-report.md` → new "Day 13: Generation error
  analysis + multi-doc repair plan" section — companion-reading table,
  taxonomy/case-record shape, the five-case table, precise Q091/Q093/Q016
  root-cause writeups, the live DeepEval contextual-recall comparison, the
  recommended repair path with tradeoffs, and caveats.

### Recommended Q091 / multi-doc repair path

- Root cause statement: Q091 fails because `POL-001` and `GUIDE-002` never
  reach the five-source generation context the reranker builds — not
  because of prompt wording, not a citation bug, and not something either
  live judge metric (faithfulness or contextual recall) reliably flags,
  since neither does, cleanly.
- Recommended first repair: raise `top_k` in `two_stage_rerank`/
  `build_sources` specifically for `multi_doc`-type queries (5 → 8-10) —
  the cheapest, most targeted experiment, since Q016's real transcript
  already proves the generator correctly synthesizes multiple sources once
  it has them; the bottleneck observed today is retrieval depth, not
  generation quality.
- A second, complementary repair (motivated by Q093, where 2 of 5 shortlist
  slots went to the same `MEMO-001` document): add a per-document diversity
  cap to the pre-rerank chunk shortlist so a flat top-k increase can't be
  filled by the same 1-2 documents again on a query whose evidence is
  spread across 4-5 different contracts/policies.
- Tradeoffs: a larger top-k means a longer, costlier prompt and a higher
  chance of conflicting-scope evidence the model has to actively resolve
  (already covered by `generation.py`'s prompt rule #2, but exercised more
  often); a diversity cap can push out a genuinely strong second chunk from
  the same document on a single-document query, so it should be scoped to
  `multi_doc`-type queries only, not applied globally.
- Verification signal: re-run `check_context_recall` (or
  `error_analysis.build_cases`) for Q091 and Q093 after either change -
  both must report an empty `missing_primary_doc_ids` list. A prompt-only
  change would leave that signal untouched. Q001 and Q004 (the two
  `passes_control` cases) must still pass every Day 11 check afterward, to
  prove the fix didn't trade a multi_doc improvement for a noisier context
  that confuses the easy cases.

### What failed or was confusing

- Nothing environment-related failed on the first pass this session
  (`OPENROUTER_API_KEY` was already correctly configured from Day 12's
  fixes) - the real "failure" worth recording is conceptual: DeepEval's
  contextual recall, the metric explicitly chosen because it uses the two
  fields faithfulness ignores, still consistently passed Q091 across every
  live run (0.50-1.00, all above the 0.5 threshold). Reading its reason
  text closely showed why: it checks whether *sentences* in
  `expected_answer` are supported, and enough of the model's
  precedent-based reasoning reads as approval-adjacent to a judge that the
  specific missing citation (the real Band-3 rule from `POL-001`) doesn't
  get flagged as clearly as a doc-id-based check flags a missing document.
- Retrieving real sources for Q093 surfaced a case sharper than the plan
  anticipated: it wasn't just "an incomplete answer" but a **confidently
  wrong, falsely-universal one** (stating Batavia's 2% deadband as if it
  applied to every contract) - a more concerning failure mode than Q091's,
  because the citations attached to the wrong claim are all individually
  valid, so skimming the answer for citation hygiene alone would not catch
  it.
- A first-pass review of this exact entry caught two real mistakes worth
  naming here directly, not just fixing quietly (see "Review-feedback
  fixes" below for the full account): Q016 was originally labeled
  `answer_completeness_gap` (a generation-owned failure) when the actual
  evidence - the missing fact living in a chunk of `GUIDE-001` that was
  never retrieved at all - describes a retrieval-owned failure instead;
  and the documented live contextual-recall command was missing
  `PYTHONPATH=src`, so it failed with `ModuleNotFoundError` the first time
  someone actually tried to run it from a clean shell rather than an
  already-configured one.

### What became clearer

- Retrieval failure and generation failure really are different owners,
  confirmed with three separate real cases today, not just Q091: Q091 and
  Q093 are both `retrieval_miss` (missing documents), Q016 is
  `chunk_level_retrieval_gap` (the right document, the wrong chunk of it) -
  all three are retrieval/context-construction failures, and none of
  today's five cases turned out to need `answer_completeness_gap` (a
  genuine generation-owned failure) at all. That only became visible after
  a corrected label, which is itself the point of a review step: the first
  labeling pass called Q016 a generation failure because the answer "left
  something out," without checking closely enough whether the model had
  ever actually been shown the missing fact.
- Document-level `check_context_recall` has a real blind spot Day 11 never
  needed to name until Q016 exposed it: a document reaching context is not
  the same as the specific fact needed reaching context. That gap needed the
  new `chunk_level_retrieval_gap` label, so it can stay retrieval-owned
  without collapsing into either whole-document `retrieval_miss` or
  generation-owned `answer_completeness_gap`.
- Aggregate metrics (P@1/R@5/nDCG@5, or even a live faithfulness/contextual
  recall score) would not have surfaced any of today's three real failure
  descriptions on their own - only reading actual retrieved sources next to
  the actual generated text, case by case, surfaced "states one contract's
  number as universal" and "the right document was there but the wrong
  chunk of it was."

### What I can now explain in an interview

- **Faithful but incomplete answers:** an answer is scored against the
  context it was actually shown - if retrieval never surfaced a required
  document, the answer can honestly report everything it saw (faithful)
  while still missing what a correct answer needs (incomplete). Q091
  proves this live: 1.00/1.00 faithfulness, and Day 11's deterministic
  check still correctly fails it for two missing primary documents.
- **Error taxonomy:** open coding is reading real traces and writing
  open-ended notes about what actually went wrong in each one, without
  presupposing the categories; axial coding is grouping those notes into a
  small set of labels afterward. Today's five cases ended up needing seven
  labels, not because seven were picked in advance, but because Q016's
  evidence didn't fit the labels Q091 alone would have suggested - and the
  first label tried for Q016 (`answer_completeness_gap`) was itself wrong
  until a closer, adversarial read of the evidence showed the missing fact
  had never reached the model at all, which is a retrieval failure, not a
  generation one. That correction is itself an example of iterative
  refinement working as intended, not a mistake to hide.
- **Contextual recall vs contextual precision:** contextual recall asks
  whether the retrieved context contains what the *expected* answer
  needed - a missing-evidence question. Contextual precision asks whether
  the relevant chunks that were retrieved are ranked above the irrelevant
  ones - a ranking-quality question. A retrieval pass can have perfect
  precision (no noise in what it returned) while still failing recall
  (missing something it never returned at all), and vice versa.
- **Repair selection:** first check whether the required evidence was ever
  in the generation context at all - at both the document level AND the
  chunk level (a deterministic doc-id/chunk-id check, not a live judge
  score). If it's absent at either level, fix retrieval/context
  construction - no prompt change can make a model cite evidence it never
  saw, whether the whole document was missing (Q091, Q093) or just the one
  chunk with the fact that mattered (Q016). Only if the evidence was
  genuinely present, in full, and still unused, misused, or contradicted
  should the investigation move to prompt/generation/citation behavior.
  Today's evidence is a real, worked example of applying that decision rule
  to three different real cases, all three of which turned out to be
  retrieval-owned once checked closely enough - which is itself a finding:
  it's easy to mistake "the answer left something out" for a generation
  problem before checking whether the model ever had the fact at all.

### What remains weak

- The taxonomy has not reached "iterative refinement" saturation - five
  cases is enough to justify seven labels, not enough to claim no eighth
  failure mode exists. `context_truncation_or_construction`,
  `citation_source_support_gap`, and `answer_completeness_gap` are all
  named but unexercised - notably, no case found today actually needed
  `answer_completeness_gap` (a genuine generation-owned completeness
  failure), which after the Q016 correction is now an open question rather
  than an assumed-common failure mode.
- No repair from today's recommended path has actually been implemented or
  re-verified yet - Day 13's deliverable is the diagnosis and a
  evidence-backed repair plan with a stated verification signal, not the
  repair itself (per the design doc's own stop condition).
- Document-level `check_context_recall` still cannot see a chunk-level gap
  like Q016's - that limitation is now named, but no chunk-level coverage
  check has been built to close it.
- Chapter 11 Agentic remains appropriately deferred: today's evidence shows
  the generation-eval loop is diagnostic (it can explain *why* Q091/Q093
  fail and propose a specific, verifiable fix), which is the bar the design
  doc set before adding agentic retrieval workflows on top of a still-being
  -tuned retrieval layer.

### Next step

- Implement the recommended Q091/Q093 repair (multi_doc top-k increase,
  optionally combined with a per-document diversity cap on the pre-rerank
  shortlist) and re-run `check_context_recall`/`error_analysis.build_cases`
  on Q091, Q093, Q001, and Q004 to confirm the verification signal moves
  without regressing the two controls - the natural next building step
  given today's evidence, ahead of adding RAGAS ID-based context recall or
  moving into Chapter 11 Agentic.

### Review-feedback fixes (same day)

A review of the first Day 13 pass raised five points; all five addressed,
required/most-important first:

1. **Q016 was mislabeled `answer_completeness_gap`.** That label means "all
   needed evidence reached context, generation under-used it" - but Q016's
   own recorded evidence already said the missing "logistics ≤40%" fact
   was never in the retrieved chunk at all, which makes it a
   retrieval/context-construction failure, not a generation one. **Fixed**
   by adding a new, seventh taxonomy label, `chunk_level_retrieval_gap`
   (document-level recall passes, chunk-level/fact-level recall fails), and
   relabeling Q016 with it in `src/error_analysis.py`, `docs/eval-report.md`,
   and this entry. This is the correction that matters most: Day 13's whole
   purpose is separating retrieval/context/generation/judge failure owners,
   and the original label put a retrieval failure in the generation column.
2. **The documented live contextual-recall command was not reproducible
   from repo root.** It imported `generation_eval`/`hybrid_search`/
   `framework_eval` directly without `src` on `PYTHONPATH`, and failed with
   `ModuleNotFoundError` when actually re-run from a clean shell instead of
   an already-configured one. **Fixed** by prefixing the command with
   `PYTHONPATH=src` in `docs/eval-report.md`, and noting
   `./.venv/bin/python src/framework_eval.py --live` as the alternative
   entry point that needs no `PYTHONPATH` (at the cost of also running both
   frameworks' faithfulness metrics, more than the narrow Q001/Q091
   contextual-recall check needs).
3. **The recorded live contextual-recall scores (Q001 1.00, Q091 0.80) were
   presented as fixed facts rather than one sample of a variable judge
   call.** Re-running the corrected command twice showed real movement:
   Q091 scored 0.50 then 0.80 (both PASS); a further independent re-run
   during review saw Q001 dip to 0.75 and Q091 land at 0.80-1.00. **Fixed**
   by replacing the single "real output" block with multiple actual runs
   and rewriting the comparison-to-deterministic-check section around the
   correct, defensible claim: not that DeepEval scores Q091 at exactly
   0.80, but that it consistently passes Q091 across a real score range
   while deterministic context recall identifies the same missing evidence
   with zero variance, every time.
4. **The Q093/Q016/Q004 fixture comments claimed an "exact command" that
   did not actually exist anywhere in the repo.** `src/error_analysis.py`
   pointed to `docs/eval-report.md`'s Day 13 section for it, but no such
   command was written down. **Fixed** by adding the real, actually-run
   `PYTHONPATH=src` retrieval+generation capture command to
   `docs/eval-report.md`'s "The five cases" section, and confirming the
   retrieval half of it reproduces the exact same `doc_id` order recorded
   in the case table (retrieval is deterministic; the live generation call
   is not, so the frozen fixture text is this specific 2026-09-19 run, not
   a byte-for-byte-reproducible output of the command on a later day).
5. **A stale docstring in `to_deepeval_test_case` still said contextual
   recall was "not built today."** True when written in Day 12, false
   after Day 13 added `run_deepeval_contextual_recall`. **Fixed** - the
   docstring now describes both metrics that actually consume the
   `expected_output` field it builds.

What this confirmed, the same lesson Day 12's own review-feedback pass
already taught: a first-pass artifact's *mechanics* held up fine (the
taxonomy shape, the case-record contract, the live-run wiring), but a
label's correctness, a command's actual reproducibility, and a score's
actual stability are all exactly the kind of thing that looks right from
inside the session that produced them and needs a second, adversarial read
- ideally one that actually re-runs the commands from a clean shell - to
catch.

## 2026-09-21 — Day 14: Eval Regression Suite + Trace Evidence

Linear: HER-281 — Day 14 loop: eval regression suite + trace evidence.

Route doc: `docs/day-14-eval-regression-suite-trace-evidence.md`.

Related gate: HER-268 — Week 3 gate: grounded generation + RAG eval harness.

### Course / docs target

- Boot.dev: no new chapter today. Reactivate Chapter 10 — `Augmented
  Generation`, `LLM Summarization`, `Conflict Resolution in Summaries`,
  `Adding Citations`, and `Question Answering` as the generation baseline.
- DeepEval docs: RAG quickstart, `Faithfulness`, `Answer Relevancy`,
  `Contextual Recall`, and `Contextual Precision`.
- RAGAS docs: metrics reference, `Context Recall`, and `Faithfulness`.
- Langfuse docs, optional/stretch only: Evaluation Overview, Core Concepts,
  Scores, and LLM-as-a-Judge.

All twelve doc sections above were fetched and read directly this session
(not recalled from general training knowledge) — the full compact table is
in `docs/eval-report.md`'s Day 14 section, "Reading notes (Block 1)". The
three findings that actually shaped today's design:

1. DeepEval's own quickstart splits RAG metrics into **generator**
   (`Answer Relevancy`, `Faithfulness`) vs **retriever** (`Contextual
   Relevancy`, `Contextual Precision`, `Contextual Recall`) metrics —
   confirming Day 12/13's choice to wire faithfulness (generator) and
   contextual recall (retriever) as the two metrics worth attaching to the
   suite's optional live lane, rather than adding all five.
2. RAGAS's Context Recall page documents a real **ID-based** variant
   (matched ids ÷ total reference ids) — the strongest conceptual match to
   this project's own `check_context_recall`. It stays a deliberately
   deferred future path: `check_context_recall` already gives ProcureRAG
   the deterministic, doc-id-exact version of the same idea, in code this
   project owns, so adding RAGAS's version today would be a second
   implementation of a question already answered.
3. Langfuse's own vocabulary maps cleanly onto what the suite already does
   without any SaaS setup: `REGRESSION_CASES` is the **dataset**, one suite
   run is the **experiment**, `evaluate_case` is a **code evaluator**. Its
   docs also flag that trace-level evaluators are deprecated in Langfuse v4
   in favor of experiment-level evaluation — reinforcing that an
   experiment (offline, dataset-based), not live tracing, is the right
   shape for a project with no production traffic yet.

### Objective

Package the Week 3 generation-eval work into a repeatable regression suite
before changing retrieval or prompts. The suite should make the Day 13
repair signal operational: Q091/Q093 missing-doc failures should be visible,
Q016's chunk/fact-level gap should not be hidden behind document-level
recall, and Q001/Q004 controls should guard against regressions.

### Regression suite command and case list

A separate module, not a `generation_eval.py` flag — see
`docs/eval-report.md`'s Day 14 "Why a separate module" section for the
reasoning (keeping Day 11's checks and Day 14's suite-runner in different
files, the same split Day 13 already made for `error_analysis.py`).

```bash
./.venv/bin/python src/regression_suite.py            # deterministic lane, no network, no PYTHONPATH needed
./.venv/bin/python src/regression_suite.py --live     # + DeepEval faithfulness/contextual recall
```

The final case list (seven cases — `src/regression_suite.py`'s
`REGRESSION_CASES` + `CITATION_NEGATIVE_CASE` + the code-built refusal
case):

| Case | Role | Expected behavior | Why included |
|---|---|---|---|
| Q001 | passing control | `missing_primary_doc_ids=[]`, citation pass | easy control; must stay stable after any retrieval-depth/diversity change |
| Q004 | passing control | `missing_primary_doc_ids=[]`, citation pass | non-`multi_doc` control so a `multi_doc`-specific repair can't be credited with an unrelated win |
| Q091 | retrieval miss | `missing_primary_doc_ids=["GUIDE-002","POL-001"]` (pre-repair) | anchor multi-doc missing-primary-doc failure; faithfulness alone scores this 1.00, proving only `check_context_recall` catches it |
| Q093 | retrieval miss | `missing_primary_doc_ids=["CONTRACT-001"]` (pre-repair) | conflicting-scope multi-doc failure; a missing contract silently becomes a false-universal answer |
| Q016 | chunk/fact-level gap | `missing_primary_doc_ids=[]`, `table_note` names the chunk gap | proves doc-id-level recall passing is not proof the needed *fact* reached the model |
| citation negative (synthetic) | validator negative | `citation_status="fail"` is the *expected*, correct outcome | the one case whose contract wants a check to fail — proves the validator still catches a hallucinated `[99]` |
| refusal negative (synthetic) | insufficient evidence / empty context | fixed refusal text returned, client never invoked | proves `generate_answer`'s empty-context short-circuit still holds |

### Table / result summary

Full real output (deterministic and `--live`) is in `docs/eval-report.md`'s
Day 14 "The regression suite's real output" section. Summary: all 7 cases
report `deterministic_match=True` / `overall_verdict="as_expected"` in the
deterministic lane; with `--live`, all 5 real fixture cases report
`status="ok"` for both DeepEval metrics and `overall_verdict="as_expected
(live ok)"`, while the 2 synthetic negative cases are correctly left
unjudged (`"n/a - synthetic case, not judged for faithfulness/context
recall"`) rather than given a meaningless score.

### Trace / evidence capture decision

**No separate JSONL file — the suite's own row dicts, printed as the two
captured tables in `docs/eval-report.md`, are this day's committed trace
evidence**, explicitly labeled as one 2026-09-21 snapshot rather than a
live-updating source of truth. Reasoning (full version in
`docs/eval-report.md`): Day 13 already had to walk back a single "real
output" score block into "multiple actual runs" after finding a live
judge's score is genuinely variable (Q091's contextual recall ranged
0.50–1.00 across real runs that day). Committing one JSONL file as *the*
evidence would repeat that exact mistake — treating a variable live-judge
sample as a stable, checked-in fact. The deterministic lane needs no
persistence at all: it is fully reproducible from the already-committed
fixtures in `src/error_analysis.py`/`src/generation_eval.py` every time it
runs.

When run with `--live`, every result does carry the fields the route doc
asks for: `run_timestamp_utc`, `provider="openrouter"`, `judge_model`,
`status` (`ok`/`blocked`/`error`), and honestly-`None` `temperature`/
`token_budget` fields — DeepEval's judge client is configured once via the
`deepeval set-openrouter` CLI command and doesn't expose either knob to
this project's code, unlike RAGAS's hand-built `ChatOpenAI`. Recording
`None` is the honest boundary, not a gap.

### Verification evidence

```bash
./.venv/bin/pytest -q
# 191 passed in 1.84s   (177 baseline + 14 new in tests/test_regression_suite.py)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py
# 7/7 cases "as_expected"

./.venv/bin/python src/regression_suite.py --live
# 5/5 real fixture cases "as_expected (live ok)"; 2 synthetic cases correctly unjudged
```

### What became operationally repeatable

- Before touching retrieval, prompts, or the model provider, one command —
  `./.venv/bin/python src/regression_suite.py` — now shows in one table
  whether Q001/Q004 are still clean, whether Q091/Q093 still show their
  known missing docs (or have finally lost them), whether Q016's chunk-gap
  caveat is still visible, and whether the citation/refusal validator
  boundaries still behave as designed.
- `deterministic_match`, `missing_primary_doc_ids`, and `citation_status`
  are exact, reproducible, no-network comparisons — stable enough to be a
  hard CI gate.
- `live_status` (DeepEval faithfulness/contextual recall scores) stays
  evidence, never a gate — `overall_verdict`'s `(live ok)`/`(live
  inconclusive)` suffix makes that distinction visible in the same table
  instead of a second, disconnected report.

### What failed or was confusing

Nothing environment-related failed today — `OPENROUTER_API_KEY` was
already configured from Day 12/13, so the `--live` run succeeded on the
first attempt and produced real scores (see the captured table in
`docs/eval-report.md`). The one real design question worth naming: the
refusal-negative case has no retrieved context at all, so it could not
reuse `evaluate_case`/`evaluate_generated_answer` the way every other case
does — it needed its own small function (`evaluate_refusal_case`) built
directly around `generation.generate_answer`'s empty-context
short-circuit. Trying to force it through the same code path as the other
six cases would have meant inventing a fake `relevance_grades` just to
make `check_context_recall` behave, which would have tested the fake data,
not the real refusal contract.

### What I can now explain in an interview

- **Regression suite vs demo transcript:** a transcript proves one run
  happened; a suite defines cases, each with its own *expected* state
  (`expected_missing_primary_doc_ids`, `expected_citation_status`), so a
  future run can be compared against a known baseline instead of read cold.
- **Deterministic vs live evals:** deterministic checks (`missing docs`,
  `citation status`) are exact, reproducible, and CI-safe; live judges
  (DeepEval faithfulness/contextual recall) add semantic evidence but
  genuinely vary run to run (proven, not assumed, by Day 13's repeated
  runs) — evidence, never the hard gate.
- **Q091/Q093 repair signal:** a real retrieval-depth/diversity repair must
  move `missing_primary_doc_ids` to `[]` for both cases; a prompt-only
  change that makes the answer read better without moving that list is not
  a repair, by this suite's own definition.
- **Q016 chunk-level gap:** document-level `check_context_recall` passing
  (both `GUIDE-001` and `POL-004` retrieved) does not prove the specific
  chunk carrying the needed fact reached the model — a different chunk of
  the same document did instead. No automated check catches this yet; the
  suite keeps the gap visible via a `table_note` rather than hiding it
  behind a passing document-level check.
- **Why citation-negative and refusal-negative are "as_expected" even
  though a check "fails":** a regression suite's verdict is "does the
  actual result match what this case declared it should be," not "did
  every check pass." `citation-negative-synthetic` *wants*
  `citation_status="fail"` — that's what proves the validator still works.
- **Trace evidence:** a separate JSONL file wasn't needed — the suite's own
  row dicts, captured as two tables in `docs/eval-report.md`, already carry
  every field the route doc's suggested schema asks for, and avoid
  re-committing a live judge score that Day 13 already proved is variable.

### What remains weak (as of Block 3A, before the repair below)

- The Q091/Q093 repair itself (multi-doc top-k increase, optional
  per-document diversity cap) has **not** been implemented — only made
  measurable. `expected_missing_primary_doc_ids_after_repair` (`[]` for
  both) is recorded on each case spec as the target, but nothing in
  `src/regression_suite.py` runs the repaired pipeline yet. This is Day
  14's Block 3B, explicitly deferred per the route doc's "do not rush the
  repair before the regression harness can measure it" instruction.
- Chunk/fact-level coverage is **named, not implemented** — `chunk-gap-q016`'s
  `table_note` is a hand-written string, not a computed check. A real
  chunk-level check (e.g. asserting a specific `chunk_id` — not just
  `doc_id` — appears in `sources`) is a real, deferred next step.
- RAGAS ID-based context recall remains deferred, as a deliberate choice:
  `check_context_recall` already gives ProcureRAG the deterministic,
  doc-id-exact version of the same idea, in code this project owns.
- Langfuse tracing remains deferred behind the local suite, per the route
  doc's own instruction — the suite's row-dict shape is a straightforward
  reshaping target for a future Langfuse experiment if that's ever needed,
  but nothing today depends on it.

## Block 3B — the repair, attempted and verified the same day

Diagnosis first, code second, capture third — in that order, not a guess.
Running the real pipeline (no code changes yet) showed the route doc's
suggested "top-k 5→8-10" alone could not work: `POL-001`'s best chunk for
Q091 ranked BM25 #52 / semantic #21 — both outside the default
`pool_size=15` each retriever contributes *before* fusion, so no amount of
raising the final `top_k` (which only trims an already-fused list) could
surface it. The real fix needed two parts, both verified with the real
cross-encoder before being called a fix: a much deeper first-stage pool
(`pool_size=80`, found by measuring the smallest pool at which each target
chunk entered the fused list at all — 50 for Q091, 25 for Q093) **and** a
per-document diversity cap (`max_chunks_per_document=2`), because the
wider pool alone let a handful of already-well-represented documents
(`FAQ-001`, `AUDIT-001`, `SOP-001`) crowd `GUIDE-002` back out of the final
top-10 after reranking (final_rank 8 → 14 with a bigger pool and no cap).
Combining both put both `POL-001` and `GUIDE-002` inside `top_k=10`
reliably (final_rank 6 and 10).

Implemented in `src/reranking.py`: `build_chunk_shortlist` gained
`max_chunks_per_document=None` (default preserves old behavior exactly —
confirmed by the full test suite passing unchanged before writing a single
new test), and `retrieval_config_for_query_type(query_type)` picks between
`DEFAULT_RETRIEVAL_CONFIG` (unchanged Day 7/8 behavior) and
`MULTI_DOC_RETRIEVAL_CONFIG` (`pool_size=80, top_k=10,
max_chunks_per_document=2`) — scoped to `query_type == "multi_doc"` only,
so Q001/Q004 cannot regress by construction, not just by re-testing.

Real retrieval + real live generation was then captured under that config
for Q091, Q093, and Q016 (2026-09-21). Results, verified by missing-doc
signals, not prose:

- **Q091**: `missing_primary_doc_ids` `['GUIDE-002', 'POL-001']` → `[]`.
  Honest residual: the retrieved `POL-001` chunk explains *how* committed
  value is calculated, not the actual Band 1/2/3 thresholds (a different
  chunk of the same document has those) — so `Q091_REQUIRED_TERMS`'s
  "Band 3" check still fails even though "usage data" now passes. Named,
  not hidden — the same `chunk_level_retrieval_gap` pattern as Q016,
  recurring on a different document.
- **Q093**: `missing_primary_doc_ids` `['CONTRACT-001']` → `[]`. The
  live-captured answer now correctly names both contracts (Batavia ±2%,
  Acme ±3%) instead of one false-universal figure — a real repair, not
  better prose, because the missing evidence itself arrived.
- **Q016**: document-level recall always passed; the real target was the
  specific `GUIDE-001::chunk-2` chunk (the "≤40%" fact), now present and
  cited `[5]` in the live answer. This is verified by a real, new,
  computed check — `required_chunk_ids`/`missing_chunk_ids` in
  `evaluate_case` — not just a hand-written note, closing the "named, not
  implemented" gap from Block 3A above.

`src/regression_suite.py`'s three affected case specs now assert this
*current* state (`expected_missing_primary_doc_ids=[]` for Q091/Q093,
`expected_missing_chunk_ids=[]` for Q016) using the real post-repair
sources/answers — a deliberate re-baseline, exactly as anticipated.
`error_analysis.py`'s own Q091/Q093/Q016 fixtures are untouched, kept as
Day 13's frozen evidence of the original failure; its own tests still pass
unchanged.

```bash
./.venv/bin/pytest -q
# 198 passed (191 baseline + 6 new in tests/test_reranking.py + net changes in
#             tests/test_regression_suite.py to assert the post-repair state)
./.venv/bin/python -m compileall -q src tests   # clean
./.venv/bin/python -m ruff check src tests      # All checks passed!
./.venv/bin/python src/regression_suite.py         # 7/7 as_expected
./.venv/bin/python src/regression_suite.py --live  # 5/5 as_expected (live ok)
```

### What remains weak (after Block 3B)

- Q091's residual chunk-level gap on `POL-001` (the "Band 3" phrase) is
  real and not wired as an automated `required_chunk_ids` check the way
  Q016's was — a natural next small addition, not a hidden problem.
- The new `MULTI_DOC_RETRIEVAL_CONFIG` (`pool_size=80`, cap=2) has only
  been verified against Q091/Q093/Q016 specifically, not re-measured
  against the full `multi_doc` slice of the 93-query set or against Day
  7-9's aggregate P@1/R@5/MRR@10/nDCG@5 baseline — a targeted fix for three
  known cases, not yet proven as a general `multi_doc` improvement.
- RAGAS ID-based context recall and Langfuse tracing remain deferred, same
  reasoning as Block 3A.

### Next step

The regression suite is green (7/7 deterministic, 5/5 live-confirmed) and
the Q091/Q093/Q016 repair is now implemented and verified by missing-doc
and missing-chunk signals, not prose — Week 3's gate (HER-268) can close.
Q091's own "Band 3" residual is now wired (see "Review-feedback fixes"
below — `expected_missing_terms`, not `required_chunk_ids`, since it's a
term-in-answer-text gap rather than a missing-chunk-id gap, but the same
"visible, not hidden" idea). The next reasonable remaining step is to
re-measure `MULTI_DOC_RETRIEVAL_CONFIG` against the full `multi_doc` query
slice before treating it as a general win, ahead of moving into Chapter 11
Agentic.

### Review-feedback fixes (same day)

A review of the Block 3B pass raised five points; all five addressed, most
severe first (full technical detail in `docs/eval-report.md`'s matching
"Code-review fixes" section):

1. **High — Q091's real "Band 3" failure printed as `as_expected`.**
   `deterministic_match` never looked at `check_expected_terms`'s result,
   so a real, known deterministic failure was invisible in the table.
   **Fixed** by adding `expected_missing_terms` (the same "expected minus
   actual" pattern `expected_missing_chunk_ids` already used) and folding
   it into `deterministic_match` - Q091's row now explicitly prints
   `"term-level gap OPEN: missing ['Band 3']"`.
2. **High — the repair never reached the real generation entry point.**
   `generation.py`'s `main()` still called `two_stage_rerank(...,
   top_k=5)` directly - `retrieval_config_for_query_type` only ever ran
   inside the fixture-capture script. **Fixed** by wiring the query-type
   config into `generation.py` itself; re-running `python src/generation.py`
   live now shows Q091 retrieving 10 sources (including POL-001,
   GUIDE-002) versus Q001's unchanged 5.
3. **Medium — frozen fixtures can't notice a later retrieval-pipeline
   change.** The suite only ever evaluated `case_spec["sources"]`, a
   fixture from 2026-09-21. **Fixed** by adding a third lane,
   `--verify-retrieval`, that rebuilds sources from the CURRENT pipeline
   (real local models, no API key, but real wall-clock time) and compares
   against the same expectations - and by naming the default command a
   "fixture" regression suite so the distinction is explicit.
4. **Medium — earlier Block 3A doc sections read as current after Block
   3B changed the expected state.** **Fixed** with explicit
   "historical/superseded" callouts in `docs/eval-report.md` pointing at
   the current Block 3B section, rather than editing history to look
   right in hindsight.
5. **Low — "covers every field" overclaimed the trace-schema coverage.**
   **Fixed** by both weakening the wording and closing part of the actual
   gap - `mode`, `retrieved_doc_ids`, `retrieved_chunk_ids`, and
   `answer_hash` are now real fields on every row.

```bash
./.venv/bin/pytest -q                                       # 206 passed (198 + 8 new)
./.venv/bin/python -m compileall -q src tests                # clean
./.venv/bin/python -m ruff check src tests                   # All checks passed!
./.venv/bin/python src/regression_suite.py --verify-retrieval # 6/6 [OK] vs the live pipeline
./.venv/bin/python src/generation.py                          # Q091 now retrieves 10 sources, live
```

## 2026-09-21 — Day 15: Week 3 Gate Review + Next-Week Readiness

Linear: HER-282 — Day 15 loop: Week 3 gate review + next-week readiness.

Route doc: `docs/day-15-week3-gate-review-next-week-readiness.md`.

Related gate: HER-268 — Week 3 gate: grounded generation + RAG eval harness.

### Course / docs target

- Boot.dev: no new chapter required before the Week 3 gate review.
- Reactivate Chapter 10 — `Augmented Generation`, `LLM Summarization`,
  `Conflict Resolution in Summaries`, `Adding Citations`, and `Question
  Answering`.
- Preview only after the gate is clean: Chapter 11 — `Recursive RAG` and
  `Agentic Search`.
- Companion docs: Day 12–14 DeepEval/RAGAS/Langfuse metric vocabulary and
  `docs/study-plan-linear-alignment-2026-09-09.md` for Week 4 readiness.

### Objective

Week 3 is gate-ready, with one real, newly-found gap named instead of
hidden. The Week 3 story, in one paragraph: retrieval foundations
(Days 1-7) produced a measured baseline; reranking (Day 8) improved
top-rank precision but exposed a `multi_doc` weakness the aggregate numbers
couldn't hide once sliced by query type; generation (Day 10) made answers
user-facing and source-cited but can't invent evidence retrieval never
found; deterministic and framework evals (Days 11-12) caught the difference
between "the answer sounds complete" and "the primary document actually
arrived"; error analysis (Day 13) turned three observed failures into a
concrete repair plan; the regression suite (Day 14) made that repair
measurable and caught it holding on Q091/Q093/Q016. Day 15 exists because
Day 14's own repair was only checked against 3 of the corpus's 5 `multi_doc`
queries — this entry is the missing full-slice measurement, and it found
that the repair does NOT generalize to Q092. That is not a failed gate; it
is the gate doing its job — see "Full multi_doc slice remeasurement" below.

### Artifact inventory / gate verdict

| Gate criterion | Evidence artifact | Command / file | Verdict | Caveat |
|---|---|---|---|---|
| Grounded generation path exists | `src/generation.py` (citation validation, empty-context refusal, real entry point reads `retrieval_config_for_query_type`) | `pytest`; `src/generation.py` optional live smoke | Pass | Live smoke not re-run today (no prompt/path change since Day 14) — Day 14's transcript stands |
| 2+ code-based evals | `src/generation_eval.py` (citation validity, context recall, expected terms), `src/regression_suite.py` (deterministic lane, `--verify-retrieval` lane) | `pytest`; `src/regression_suite.py --verify-retrieval` | Pass | None |
| 1 LLM-as-judge eval exists or is scoped | `src/framework_eval.py` (DeepEval faithfulness + RAGAS contextual recall bridge), wired into `regression_suite.py --live` | `src/regression_suite.py --live` (not run today) | Scoped, not re-run | Live variability + cost — Day 12/14's captured live results remain current evidence; contract (skip/blocked/ok/error) is tested unconditionally in `tests/test_framework_eval.py` |
| Error analysis captures real failures | `src/error_analysis.py` (5-case taxonomy: Q001, Q091, Q093, Q016, Q004; frozen PRE-repair evidence kept separate from `regression_suite.py`'s current, repaired state) | docs + `tests/test_error_analysis.py` | Pass | Frozen vs. current state must stay visibly distinct — confirmed still true (Block 3B's own commentary is explicit about which fixtures are pre- vs post-repair) |
| Regression/failure-mode checks exist | `src/regression_suite.py` (7 deterministic cases) + `src/multi_doc_slice_eval.py` (new: full 5-query `multi_doc` slice, both configs) | `src/regression_suite.py --verify-retrieval`; `src/multi_doc_slice_eval.py` | Pass, with one open finding | Q091's `Band 3` term gap stays open by design; Q092's missing-doc gap is NEW, found by today's full-slice run, not previously known |
| Interview explanation is ready | This entry's "What I can now explain" section below | self-quiz | Pass | None |

**Gate verdict for HER-268: ready for closure review.** Every row above is
either a clean pass or a pass with an explicitly named, non-blocking
caveat — no row is hand-wavy, and no caveat is hidden inside a green
summary. The Q092 finding does not block the gate; it is exactly the kind
of evidence a gate review is supposed to surface before Week 4 starts.

### Verification outputs

Real output, this run (2026-09-21):

```bash
./.venv/bin/pytest -q
# 206 passed in 1.80s (before adding src/multi_doc_slice_eval.py — it has no
# tests of its own, and re-running after adding it still shows 206 passed)

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py
# All 7 cases match their currently expected state (frozen fixtures) —
# same table as Day 14, re-confirmed, including retrieval-miss-q091's
# printed "term-level gap OPEN: missing ['Band 3']" note.

./.venv/bin/python src/regression_suite.py --verify-retrieval
# 7/7 frozen cases as_expected; 6/6 real-query cases [OK] against the
# CURRENT retrieval pipeline (re-run live against the real corpus/models,
# not read from a cached fixture).

./.venv/bin/python src/eval_metrics.py
# Largest weak slice (Cross-encoder reranked Hybrid RRF chunk->document, by
# query_type): 'multi_doc' — P@1 0.600 over 5 queries, vs. 0.978 overall.
# (This number is unchanged from Day 7-9 by design — this table always used
# the DEFAULT_RETRIEVAL_CONFIG pool_size=15; see the new script below for
# the REPAIRED-config comparison this table was never meant to show.)

./.venv/bin/python src/multi_doc_slice_eval.py
# New Day 15 script — see "Full multi_doc slice remeasurement" below for
# the real per-query table it produced. Its own printed sanity check:
# "default-config P@1 across the 5-query multi_doc slice: 0.600" — matches
# eval_metrics.py's number above exactly, confirming the new script
# measures the same thing the same way.
```

Not re-run today (no cost/behavior justification since Day 14):
`src/regression_suite.py --live`, `src/generation.py`'s live smoke. Day
14's captured live transcripts remain the current live evidence.

### Full multi_doc slice remeasurement

New script: `src/multi_doc_slice_eval.py` (full method + design rationale in
its module docstring; full per-query diagnostic detail and the "answering
the route doc's four questions" writeup lives in `docs/eval-report.md`'s Day
15 section — this is the summary table only, not a duplicate of that
writeup).

| Query | Default config evidence | Repaired config evidence | Verdict |
|---|---|---|---|
| Q005 | All 3 primary docs reach context. P@1 1.000 R@5 1.000 MRR@10 1.000 nDCG@5 1.000 | Same — unaffected. Same P@1/R@5/MRR@10/nDCG@5 | Unchanged (already fine) |
| Q016 | Both primary docs reach context, but the specific fact chunk (`GUIDE-001::chunk-2`) does not | Same doc-level recall; `GUIDE-001::chunk-2` now also reaches context | chunk gap remains addressed, reconfirmed |
| Q091 | Missing: GUIDE-002, POL-001. R@5 0.200 | All primary docs reach context. R@5 0.600 | Missing docs fixed; `Band 3` term gap still visible (separate, tracked signal) |
| Q092 | Missing: CONTRACT-005, POL-002. R@5 0.200 | **Still missing** CONTRACT-005, POL-002. R@5 0.200 (unchanged) | **Not fixed** — new finding, see below |
| Q093 | Missing: CONTRACT-001. R@5 0.750 | All primary docs reach context. R@5 1.000 | Fixed, matches `regression_suite.py` |

Notes:

- Q016/Q091/Q093 remain fixed under the current pipeline — reconfirmed by a
  second, independently-written measurement path (this script), not just by
  re-reading `regression_suite.py`'s own frozen fixtures.
- Q005 was already fine before the repair and stays fine; it neither
  benefits nor regresses.
- **Q092 does not improve.** Same two primary docs missing from generation
  context under both configs. Root-cause diagnostic (see eval-report.md):
  CONTRACT-005 IS found by first-stage retrieval (BM25 rank 1) but the
  cross-encoder reranker itself scores it too low to survive `top_k=10` — a
  reranker-judgment miss, not a pool-depth miss. POL-002 is weaker in the
  repaired first-stage/fusion path: one chunk appears at BM25 rank 79, but
  no POL-002 chunk survives the `pool_size=80` RRF + diversity-cap shortlist;
  even a `pool_size=200` diagnostic only gets POL-002 into the shortlist,
  where the reranker still leaves it outside generation context.
- **Honest verdict: `MULTI_DOC_RETRIEVAL_CONFIG` is a targeted repair,
  verified on 4 of 5 `multi_doc` queries (Q016 chunk-level, Q091, Q093
  fixed; Q005 unaffected-and-fine) — not a full-slice improvement.** Q092
  is real, un-fixed evidence against the broader "multi_doc repair" framing,
  and should be described that way going forward, not glossed over.

### Error-analysis highlights and remaining weaknesses

- **Q091**: two genuinely different gaps, now measured separately. The
  missing-*document* gap (GUIDE-002, POL-001 never reaching context) is
  fixed — confirmed today by a second measurement path, not just Day 14's
  fixture. What remains is a missing-*chunk* gap one level deeper: the
  POL-001 chunk that DOES reach context (`chunk-3`) explains how total
  committed value is calculated, not the actual Band 1/2/3 EUR thresholds
  (`chunk-4`, never retrieved). `expected_missing_terms=["Band 3"]` in
  `regression_suite.py` keeps this a tracked, asserted gap, not a silently
  passing green row.
- **Q093**: the missing `CONTRACT-001` problem remains fixed — reconfirmed
  today (R@5 0.750 → 1.000, all primary docs reach context under the
  repaired config).
- **Q016**: `GUIDE-001::chunk-2` remains present under the repaired config
  — reconfirmed today by directly inspecting the reranked chunk list
  (`chunk_ids reaching context` includes `GUIDE-001::chunk-2` under
  `repaired`, does not under `default`), independent of
  `regression_suite.py`'s own hard-coded fixture.
- **Q005**: no finding — already fine before and after the repair.
- **Q092**: new finding from today's full-slice check (was never measured
  before Day 15). CONTRACT-005 and POL-002 both stay outside generation
  context under either config, for two structurally different reasons (see
  "Full multi_doc slice remeasurement" above). This is the one real gap
  Day 15 surfaced that Day 14 did not know about.

### What I can now explain in an interview

- **Retrieval quality vs. answer quality.** A retriever can be measured
  (P@1/R@5/MRR@10/nDCG@5) completely independently of whether the generator
  writes a good answer — Q091's default-config retrieval scored R@5=0.200
  (two primary docs missing) while its generated answer was still honest
  and well-formatted; a fluent answer says nothing about whether the right
  evidence arrived.
- **Faithfulness vs. context recall vs. answer completeness vs. chunk/fact
  coverage — four different axes, each catching something the others
  can't.** Faithfulness (DeepEval/RAGAS, Day 12) asks "is the answer
  supported by what it was given" — it can score high on an *incomplete*
  context, because it never asks whether the context itself was complete.
  Context recall (`check_context_recall`, Day 11) asks "did the primary
  *document* arrive" — it caught Q091/Q093's original missing-doc failures,
  but is document-grained: it can't see that only the wrong *chunk* of a
  present document arrived (Q016), or that a present document is missing
  one specific *fact* (Q091's Band 3, even after the document itself
  arrived). Expected-term checks (`check_expected_terms`) catch the answer
  actually stating a needed fact. None of these four subsumes the others —
  Week 3's whole point is that ProcureRAG now measures all four separately
  instead of trusting one green metric to mean "the answer is good."
- **Why LLM-as-judge scores are evidence samples, not hard gates.**
  `framework_eval.py`'s DeepEval/RAGAS lane is opt-in, costs a live API
  call, and has real result-variance run to run — it is treated as a
  second, corroborating signal alongside the deterministic checks, never as
  the sole pass/fail gate. The deterministic lane (`generation_eval.py`,
  `regression_suite.py`) is what CI/regression actually depends on, exactly
  because it is free, fast, and reproducible.
- **Why Q091 drove the eval design.** It is the one query where every
  layer shows something different: retrieval missed two primary docs
  (context recall), the answer stayed honest about the gap instead of
  guessing (faithfulness could still pass), the missing docs got fixed by a
  measured retrieval-config repair (Day 14), and even after that repair a
  narrower, real gap remained — a term the answer still can't state because
  the exact chunk with the number never arrived (`Band 3`). One query,
  five distinct lessons.
- **Why an agentic/recursive retrieval loop should be motivated by a
  specific failure signal, not by framework enthusiasm.** Today's Q092
  diagnostic is the concrete argument: CONTRACT-005 is a *reranker*
  judgment miss (found by BM25 at rank 1, then scored too low by the
  cross-encoder to survive `top_k`), while POL-002 is a combined
  first-stage/fusion + reranker-ranking miss (weak enough that `pool_size=80`
  drops it before reranking, and still not promoted into top-10 even when a
  deeper diagnostic pool surfaces it). These need different fixes — a query
  reformulation / re-rank retry for one, and a retrieval/fusion/reranking
  strategy that can surface and promote POL-002 for the other. "Add an
  agent" without this diagnosis would be guessing at which of two different
  problems it's even trying to solve.

### What remains weak

- **Q091's `Band 3` term/chunk gap.** Owner: retrieval targeting for
  POL-001 (two different chunks answer two different relevant questions).
  Impact: the answer correctly declines to state the exact approval band
  rather than guessing. Next signal: `POL-001::chunk-4` reaching context
  (checkable the same way `chunk-gap-q016` already checks
  `GUIDE-001::chunk-2` — a real `required_chunk_ids` assertion), or a
  deliberate, asserted decision that the band stays unstated.
- **Q092's missing-doc gap (new today).** Owner: retrieval — a reranker
  relevance-judgment miss for CONTRACT-005, plus a combined
  first-stage/fusion + reranker-ranking miss for POL-002. Impact: any real
  answer to Q092 today would omit both documents' requirements. Next signal:
  two separate checks, one per cause (see eval-report.md's Day 15 section
  for exactly what each would need).

Neither gap blocks HER-268 — both are retrieval-completeness gaps the eval
harness already surfaces honestly (via context recall / the new full-slice
script), not faithfulness failures generation is hiding.

### Next step

**HER-268 is ready for closure review.** Every gate command is green, the
full `multi_doc` slice has been measured under both configs (not assumed
safe), Q091's residual gap stays visible and asserted, and Q092's new gap is
named with an owner and a concrete next signal rather than glossed over.
Hand this to Hermes using the route doc's review protocol message.

Week 4 / Chapter 11 first target, grounded in today's evidence (not
framework enthusiasm): a **Recursive RAG** pass motivated specifically by
Q091's `Band 3` gap (reformulate toward "approval band EUR thresholds"
after a first pass returns POL-001 without the right chunk) and/or Q092's
reranker miss (retry retrieval when the reranker's own top scores are low
enough to suggest low confidence, rather than accepting a low-confidence
shortlist as final). Both are real, measured failures — the agentic work
starts from them, not from "agents" as a generic next feature.

## 2026-09-25 — Day 16: Recursive RAG Pass for Q091/Q092 Gaps

Linear: HER-283 — Day 16 loop: Recursive RAG pass for Q091/Q092 gaps.

Route doc: `docs/day-16-recursive-rag-q091-q092-agentic-search.md`.

Related gate: HER-269 — Week 4 gate: LangGraph agents, observability, guardrails.

### Course / docs target

- Boot.dev Chapter 11 — `Agentic`:
  - `Recursive RAG` - Completed
  - `Agentic Search` - Completed
- Companion vocabulary only: LangChain Academy — Introduction to LangGraph,
  Module 1 `Introduction`: `Lesson 1: Motivation`, `Lesson 2: Simple Graph`,
  `Lesson 5: Router`, and `Lesson 6: Agent`.
- Project baseline: Day 15 full `multi_doc` slice evidence in
  `docs/eval-report.md` and this learning log.

### Objective

_TODO: Fill in after building._

Expected shape:

- Explain how the Day 16 recursive-retrieval work starts from Week 3's
  measured failures, not from generic agent enthusiasm.
- Name the exact trigger signal chosen for Q091 and Q092.
- State whether today's artifact is a working recursive retrieval loop or the
  fallback decision/evidence contract.

### Baseline verification at kickoff

```bash
./.venv/bin/pytest -q
# 206 passed in 4.88s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# 7/7 frozen fixture cases as_expected; 6/6 current retrieval-pipeline checks [OK]
# Q091 remains visible as: term-level gap OPEN: missing ['Band 3']

./.venv/bin/python src/multi_doc_slice_eval.py
# Q005 fine; Q016 chunk gap addressed; Q091 missing docs fixed but Band 3 term gap remains;
# Q092 still missing CONTRACT-005 and POL-002; Q093 fixed
```

### Chapter 11 notes

_TODO: Fill in._

Expected shape:

- `Recursive RAG`: what second-pass retrieval means, when it triggers, and how
  it stops.
- `Agentic Search`: what makes the loop agentic/bounded rather than just a
  bigger `top_k`.
- LangGraph vocabulary used, if any: state, node, conditional edge, router,
  agent.

### Recursive retrieval trigger contract

_TODO: Fill in._

Expected table shape:

| Query | First-pass signal | Follow-up query/action | Stop condition | Evidence owner |
|---|---|---|---|---|
| Q091 | TODO | TODO | TODO | TODO |
| Q092 | TODO | TODO | TODO | TODO |
| Control | TODO | TODO | TODO | TODO |

Hints:

- Q091 should separate `POL-001` document presence from the exact
  `POL-001::chunk-4` / `Band 3` gap.
- Q092 should separate `CONTRACT-005`'s reranker miss from `POL-002`'s
  weaker first-stage/fusion + reranker miss.

### Q091 before/after evidence

_TODO: Fill in._

Record:

- First-pass retrieved doc ids and chunk ids.
- Whether `POL-001::chunk-4` reached context.
- Whether `Band 3` remains in `missing_terms`.
- Follow-up query used.
- Second-pass retrieved doc ids and chunk ids.
- Final verdict: fixed, still open, or sharper diagnosis.

### Q092 before/after evidence

_TODO: Fill in._

Record separately:

- `CONTRACT-005`: first-stage / reranker behavior and whether it reaches
  generation context after the second pass.
- `POL-002`: first-stage / fusion / reranker behavior and whether it reaches
  generation context after the second pass.
- Whether the result proves a fix, proves a different repair owner, or remains
  blocked.

### Control / no-second-pass evidence

_TODO: Fill in._

Expected shape:

- Name the control query (`Q001`, `Q005`, or another justified case).
- Show why first-pass evidence is already complete.
- Show the recursive loop does not trigger, or stops immediately with a clear
  no-op reason.

### Verification evidence after Juan's build

_TODO: Fill in with exact command output._

Minimum expected commands:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py --verify-retrieval
./.venv/bin/python src/multi_doc_slice_eval.py
# plus the new Day 16 recursive retrieval command, if implemented
```

### What improved

_TODO: Fill in._

Expected shape:

- Which missing docs/chunks/terms moved from missing to present.
- Which explanation became more interview-defensible.
- Which checks or tests now make the behavior repeatable.

### What remains weak

_TODO: Fill in._

Expected shape:

- Any Q091 residual gap (especially `Band 3` / `POL-001::chunk-4`).
- Any Q092 residual gap, split by `CONTRACT-005` vs `POL-002`.
- Cost/noise tradeoffs from running a second pass.
- Whether LangGraph/framework integration is still deferred.

### What I can now explain in an interview

_TODO: Fill in._

Expected bullets:

- Recursive RAG as a conditional, bounded second retrieval pass driven by a
  measured evidence gap.
- Difference between static top-k/pool-size tuning and dynamic agentic search.
- Why Q091 and Q092 require different trigger/repair logic.
- How to prevent recursive retrieval from amplifying noise or running forever.

### Next step

_TODO: Fill in after review._

Likely route if Day 16 is clean: move from the local recursive-retrieval
contract into a small LangGraph-shaped state/edge representation, or into the
next Week 4 focus from HER-269 (observability/trace evidence) if the agentic
loop needs inspection before guardrails.
