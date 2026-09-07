# Day 1 — Preprocessing + Corpus Scope

Date: 2026-09-07  
Linear: HER-262 — Monday loop: Boot.dev preprocessing and corpus scope  
Project rule: course-driven building, with Juan owning the core implementation.

## Day 1 objective

Start Boot.dev RAG with the preprocessing chapter and turn it into a small ProcureRAG artifact: a documented procurement corpus choice plus a Juan-written first draft of the preprocessing approach.

Today is not about building the whole RAG stack. It is about making the first retrieval substrate real.

## Target evidence by end of day

- [ ] Boot.dev preprocessing checkpoint completed or meaningfully attempted.
- [ ] Corpus v0 selected and documented.
- [ ] Juan drafts the preprocessing rules himself.
- [ ] Juan writes/sketches the first preprocessing function or pseudocode himself.
- [ ] One tiny before/after example demonstrates what the preprocessing keeps/removes.
- [ ] `docs/learning-log.md` gets a Day 1 entry.
- [ ] Juan can explain preprocessing trade-offs from memory for 3–5 minutes.

## Recommended 6-hour split

### Block 1 — Course/exercises, 2.5–3h

Focus only on Boot.dev preprocessing.

Capture notes in this shape:

| Concept | What it does | Why it matters for retrieval | Risk if done badly |
|---|---|---|---|
| normalization | | | |
| tokenization | | | |
| stop words | | | |
| stemming/lemmatization | | | |
| preserving domain terms | | | |

### Block 2 — ProcureRAG corpus decision, 45–60m

Choose the first tiny corpus. Keep it small enough to understand manually.

Recommended v0 corpus options:

1. **Procurement policy snippets** — best for business relevance.
2. **Supplier onboarding / RFP snippets** — best for query realism.
3. **Synthetic procurement KB mini-corpus** — best for speed if no real documents are ready.

Decision rule: choose the corpus that lets you write 5 realistic queries today.

Document:

- Corpus source:
- Number of docs/snippets:
- Why this corpus matches ProcureRAG:
- What metadata matters later: supplier, category, country, document type, date, owner, risk/compliance tag.
- What must be preserved during preprocessing: acronyms, supplier names, legal terms, amounts, dates, category names.
- What can be removed/normalized: boilerplate, punctuation noise, casing, extra whitespace, low-value stop words.

### Block 3 — Juan-owned preprocessing draft, 1.5–2h

Juan writes the first version. Hermes can review/debug after the attempt.

Minimum draft behavior:

- input: one raw document/snippet string
- output: normalized tokens or normalized text plus tokens
- handles lowercasing / whitespace cleanup
- handles punctuation deliberately, not blindly
- preserves procurement-significant terms
- includes one before/after example

Suggested files Juan may create when ready:

- `src/procurerag/preprocessing.py`
- `tests/test_preprocessing.py`
- `data/corpus_v0/` or `data/sample_corpus.jsonl`

Do not overbuild package structure today. A simple module + tiny test is enough.

### Block 4 — Evidence + interview drill, 30–45m

Fill the Day 1 entry in `docs/learning-log.md`.

Then answer without notes:

1. Why does preprocessing change retrieval quality? Because its the entry point for our data, if not read and loaded properly will mean issues later on.
2. What is one term you must not remove in a procurement corpus? Acronyms or supplier names suffixes.
3. When can lowercasing hurt? Lowercasing can hurt when casing carries meaning: acronyms like PO/RFP/DPA/GDPR, supplier legal names, product names, or display/audit traceability. For retrieval tokens, lowercasing helps matching; for display and evidence, original casing should be preserved.
4. Why might stemming improve recall but hurt precision? Will expand the universe of matching terms, but at same time increasing chances of going on wrong direction (lower precision)
5. What preprocessing mistake would make BM25 worse tomorrow? Handling punctiations.

## Hermes review protocol

When Juan has a serious attempt ready, ask Hermes for review with:

> Review my Day 1 ProcureRAG preprocessing attempt. Check retrieval correctness, edge cases, tests, and whether I can defend the design in an interview. Do not rewrite it for me unless I ask for a hint.

Hermes should review, quiz, and debug — not replace the core implementation.

## Stop condition

Day 1 is complete when there is a small, explainable preprocessing artifact and a learning-log entry. It does not need to be elegant. It needs to be understood.
