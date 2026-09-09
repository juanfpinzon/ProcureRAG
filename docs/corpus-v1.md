# Corpus v1 — Realistic Procurement Knowledge Base

Date: 2026-09-09
Status: built, validated, not yet wired into `src/`

## Why v1 exists

Corpus v0 did its job: it was small enough to inspect by hand while preprocessing,
TF-IDF, BM25, and semantic search were being written from primitives. It has now
run out of signal.

| | v0 | v1 |
|---|---|---|
| Documents | 10 | 34 |
| Words / doc | ~60 | 725–913 (mean 827) |
| Total words | ~600 | 28,140 |
| Chunks (3 sentences, overlap 1) | 13 | 570 |
| Queries | 8 | 93 |
| TF-IDF P@1 | **1.00** | 0.87 |
| TF-IDF R@5 | **1.00** | 0.79 |

A benchmark scoring 1.00 measures nothing. Every retrieval improvement planned for
Week 2 onward — hybrid/RRF, reranking, metadata filtering — would have shown up as
no change at all on v0.

## Files

- Corpus: `data/corpus_v1/procurement_kb.jsonl`
- Golden query set: `data/corpus_v1/example_queries.jsonl`

v0 is left untouched. `src/preprocessing.py` still points at `corpus_v0`, so nothing
changes until you deliberately switch `DATA_PATH`.

## Baselines measured on v1

Run with the repo's own retrieval code, no modifications, whole corpus, 93 queries.
Gold sets average 2.7 relevant documents per query, which is why R@5 sits well below P@1.

| Method | Retrieval unit | P@1 | R@5 | R@10 | MRR |
|---|---|---|---|---|---|
| TF-IDF | document | 0.87 | 0.79 | 0.90 | 0.924 |
| BM25 | document | 0.86 | 0.75 | 0.90 | 0.910 |
| Dense (multi-qa-MiniLM) | document | 0.84 | 0.67 | 0.79 | 0.900 |
| Dense (multi-qa-MiniLM) | **chunk** | **0.91** | **0.80** | 0.88 | **0.948** |

Two things worth noticing:

1. **Chunking now pays for itself.** Chunk-level dense retrieval beats whole-document
   by +7 points P@1 and +13 points R@5. On v0 this comparison was not demonstrable —
   a 60-word document *is* a chunk.
2. **Lexical and dense fail differently.** BM25 wins on identifiers and exact figures;
   dense wins on paraphrase and scenario phrasing. That gap is the argument for hybrid
   fusion, and it is now visible in the numbers rather than asserted.

The 13 BM25 P@1 misses cluster on conceptual and procedural queries that get pulled
toward `FAQ-001` / `FAQ-002`, because FAQ documents share vocabulary with the whole
corpus while answering none of it specifically. That is a real lexical-retrieval
pathology, not a labelling mistake, and it is exactly what a reranker should fix.

## Corpus shape

All v0 fields are preserved with identical names and meanings, so anything written
against v0 still loads. New fields are additive.

| Field | Notes |
|---|---|
| `id`, `title`, `doc_type`, `category`, `region`, `supplier`, `owner`, `effective_date`, `risk_tags`, `text` | unchanged from v0 |
| `subcategory` | finer-grained category, for filtering exercises |
| `supplier_id` | e.g. `SUP-100482`; exact-match retrieval target |
| `version`, `status` | e.g. `4.2`, `active` |
| `language` | `en` throughout |
| `review_date`, `expiry_date` | `expiry_date` is null for policies, set for contracts |
| `confidentiality` | `Internal` / `Confidential` |
| `source_system` | Ariba Contracts, SAP S/4HANA, Ariba Sourcing, … |
| `annual_value_eur` | numeric, null where not applicable — enables numeric metadata filters |
| `related_ids` | cross-references between documents; all validated to resolve |
| `section_headings` | extracted headings, for structure-aware chunking later |
| `word_count`, `char_count` | precomputed |

Document types: policy (8), sop (8), contract-summary (6), guide (5), faq (2),
scorecard, audit-report, rfp, memo, glossary (1 each).

## Formatting conventions, and why they are what they are

The formatting was chosen empirically by running candidate layouts through
`chunking.split_into_sentences` before writing 28,000 words against them.

- **Section headings are Title Case on their own line, with no trailing period.**
  The sentence splitter therefore fuses a heading onto the first sentence of its
  section — `"Approval Bands Band 1 (below €5,000): approval by…"`. That is
  desirable: the heading travels with the content as retrieval context.
- **Clause references are inline** (`Under Clause 7.3, …`) or written as
  `Clause 12.4 (Limitation of Liability).` Both split cleanly.
- **Tabular content is written as `Tier 1 (spend above €500,000): …` lines.**
  Each becomes its own sentence, so a table row is independently retrievable.
- **Line-leading clause numbers (`4.1 Requests must…`) are deliberately avoided.**
  `SENTENCE_BOUNDARY_PATTERN` requires a capital letter after the period, so
  `"…approval. 4.2 Requests…"` never splits, and an entire numbered section collapses
  into one unsplittable 400-word "sentence". Real procurement PDFs are full of this.
  It is the strongest argument for a structure-aware chunker, and `section_headings`
  plus the `\n\n` block structure in `text` are there so you can build one.

Sentence stats after these choices: mean 24 words, max 104, and only 3 of 1,157
sentences exceed 80 words.

## Golden query set

93 queries. Every one of the 34 documents is *a* primary answer (`relevance_grades`
value `2`) for at least one query. "Primary" is a set membership, not a rank: 48
queries have multiple grade-2 documents (see "Multi-document queries" below), and
within a tied group `expected_relevant_ids` does not promise any particular
sub-order — only that primaries as a group precede secondaries. Two documents,
`SOP-008` (Q005, Q006, Q052) and `MEMO-001` (Q061, Q075, Q088, Q093), are always
tied with another grade-2 document and so never happen to be the first id listed;
checking "primary" by list position alone will miss them.

| Field | Purpose |
|---|---|
| `query_id` | `Q001`–`Q093` |
| `query` | natural phrasing, as a buyer would actually ask |
| `query_type` | lookup, threshold, numeric, procedural, conceptual, terminology, supplier_specific, multi_doc |
| `difficulty` | easy (15) / medium (52) / hard (26) |
| `expected_answer` | ground-truth answer text, for Week 3 generation evals |
| `evidence` | `{doc_id, quote}` pairs — **125 quotes, every one verified as a verbatim substring of its document** |
| `expected_relevant_ids` | v0-compatible name; grade-2 (primary) ids as a group precede grade-1 (secondary) ids, but ties within a group aren't further ordered |
| `relevance_grades` | `2` = primary, `1` = partially relevant — for nDCG and graded recall |
| `metadata_filters` | expected filter values, for metadata-filtering exercises |
| `reason` | v0-compatible name; what the query is designed to test |

Because `expected_relevant_ids` keeps its v0 name and shape, existing eval code runs
against v1 unchanged; `relevance_grades`, `evidence`, and `expected_answer` are opt-in.

The eight v0 queries all survive as v1 queries (Q001, Q007, Q011, Q016, Q032, Q035,
Q053, Q057), so before/after comparison on the original questions is still possible.

### What the queries are built to stress

- **Exact identifiers**: `RFP-EMEA-2026-0141`, `MSA-ACM-2024-018`, `INV-ACM-2026-0331`,
  `SUP-100482` — all survive `TOKEN_PATTERN` as single tokens.
- **Adjacent numbers that are easy to conflate**: Northstar's 45-day deletion vs
  90-day backup rotation; 30-day sub-processor notice vs 20-day objection window;
  Meridian's 5% / 10% / 25% credit tiers.
- **Vocabulary gaps**: "uptime" vs "availability", "holiday" vs "absence",
  "contractor" vs "contingent worker", "small supplier" vs "SME", "skip" vs "waived".
- **Answers defined by exclusion**: where you may *not* source a callback number;
  what does *not* count as an emergency; what is *not* benchmark evidence.
- **Acronym bridging**: `GRNI` asked as an acronym, expanded only in `GLOSSARY-001`
  and used in full form in `SOP-002`.
- **Near-synonyms that retrieval conflates**: sole source vs single source.

### Multi-document queries

48 queries have more than one primary document, and 5 are typed `multi_doc`. These
are natural composites rather than engineered traps — the kind of question where the
answer genuinely lives in several places:

- Q005 — the emergency-documentation rule is stated in `POL-001`, `SOP-008`, and `FAQ-001`.
- Q016 — price weighting: a 60% policy ceiling (`POL-004`), tightened to 40% for logistics
  (`GUIDE-001`), applied at 30% in a live cold-chain event (`RFP-001`).
- Q091 — a €120k SaaS renewal needs the approval band, the security evidence, and the
  renewal playbook together.
- Q093 — "what deadband applies to our indexation clauses?" is correctly answered
  "it depends": 3% for Acme fuel, 2% for Batavia resin, 2–3% recommended in `GUIDE-003`.

Q093 is the useful one for generation evals: a model that answers with a single
confident percentage is wrong even though it quoted a real number from the corpus.

## Deliberate design choices

**Realistic, not adversarial.** There are no superseded-version pairs, no confusable
supplier names, and no unanswerable queries. Documents carry `version` fields and say
things like "Version 4.2 supersedes version 4.1", but the superseded versions are not
in the corpus. Overlap between related documents is the natural kind — a policy states
a rule and the SOP that implements it restates it — which is realistic and still makes
recall@k meaningful. If a harder tier is wanted later, add it as v2 rather than
retrofitting v1, so the baselines above stay comparable.

**Internally consistent.** Every threshold, date, supplier ID, and contract reference
was authored against a single fixed set of facts, then validated. €5,000 / €50,000 /
€250,000 approval bands, the €25,000 three-bid threshold, the 3% / 5-unit / €50 invoice
tolerances, and the 150% liability cap hold across all 34 documents. The audit report's
finding about €4,800 and €4,900 requisitions is only meaningful because the €5,000
threshold is stated consistently elsewhere.

**Synthetic and non-confidential.** The buying entity (Vantera Group N.V.) and all
suppliers are fictional. v0's two named suppliers, Acme Logistics S.L. and Northstar
Analytics Ltd., are carried forward with their v0 facts intact — 98.5% OTD, 90-day
renewal notice before 2027-05-12, no model training without written approval,
30-day sub-processor notice, 45-day deletion — and expanded around.

## Suggested next steps

1. Point `DATA_PATH` at `corpus_v1` and re-run the Day 1–5 artifacts. Expect the
   preprocessing output to become too long to eyeball, which is itself the lesson.
2. Reproduce the baseline table above and commit it as the Week 2 starting line.
3. Build the eval harness against `relevance_grades` (nDCG) rather than only
   `expected_relevant_ids`, since 48 queries have multiple primary documents.
4. Implement RRF over BM25 + chunk-level dense, and check it against the 13 BM25
   misses specifically — that is where the fusion should earn its place.
5. Only then reach for a reranker, and measure it on the same 93 queries.

## Verification performed

- All 34 KB rows and 93 query rows parse as JSON; IDs unique in both files.
- All `related_ids` resolve to documents in the corpus; no self-references.
- All 125 evidence quotes verified verbatim against their document text (Q019's
  POL-005 evidence was originally one quote that joined two table-row
  sentences across a line break with a space instead of the newline that is
  actually there; split into two quotes, one per sentence, matching how every
  other tabular row in the corpus is already evidenced).
- All `expected_relevant_ids` and `relevance_grades` keys resolve; sets agree.
- Every `metadata_filters` entry matches at least one gold document.
- Every document has `relevance_grades` value `2` (primary) for at least one
  query — checked via the grades, not via `expected_relevant_ids[0]`, since 48
  queries have tied primaries and list position doesn't break the tie.
- 25 domain-token probes (`€50,000`, `3%`, `ISO 27001`, `S.L.`, `B.V.`,
  `MSA-ACM-2024-018`, `SUP-100482`, `IR35`, …) survive `TOKEN_PATTERN` intact.
- `pytest tests/` — 48 passed. `src/` was not modified.
