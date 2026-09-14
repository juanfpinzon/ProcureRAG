# Day 10 — Source-Cited Augmented Generation + Week 2 Gate Review

Date: 2026-09-14 target; started 2026-09-14.

Linear: HER-276 — Day 10 loop: eval consolidation + Week 2 gate review.

Related gate: HER-267 — Week 2 gate: hybrid search, reranking, retrieval evals.

Project rule: course-driven building, with Juan owning the core generation implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

Boot.dev RAG course target:

- **Primary chapter:** Chapter 10 — **Augmented Generation**.
- **Exact lessons verified from the public Boot.dev Chapter 10 lesson menu:**
  1. **Augmented Generation** — connect retrieval to generation: retrieve context, augment the prompt, and generate from that context.
  2. **LLM Summarization** — synthesize several retrieved results into a coherent response instead of dumping raw chunks.
  3. **Conflict Resolution in Summaries** — handle overlapping or conflicting retrieved evidence without pretending all sources agree.
  4. **Adding Citations** — attach source references to generated claims so the answer is auditable.
  5. **Question Answering** — produce direct user-facing answers from retrieved context.
- **Important discrepancy vs. Linear HER-276 text:** the ticket was drafted as a Week 2 consolidation day and names stale artifacts like `src/evaluation.py`, `tests/test_evaluation.py`, and `data/golden_queries.jsonl`. The live repo evidence uses `src/eval_metrics.py`, `tests/test_eval_metrics.py`, and canonical `data/corpus_v1/example_queries.jsonl`; Day 9's learning log says the retrieval-eval harness is now strong enough to move into source-cited augmented generation. Treat this route as: **start Chapter 10 generation, while preserving HER-276's Week 2 gate-review responsibility.**

Companion sources:

- **RAGAS / RAG triad concepts** — use the evaluation vocabulary from Day 9: context relevance, faithfulness/groundedness, and answer relevance. Do not integrate RAGAS as a framework today unless it is only referenced conceptually.
- **DeepLearning.AI / advanced RAG evaluation framing** — optional conceptual reinforcement for grounded generation and citation checking.
- **Day 7–9 project evidence** — `docs/eval-report.md`, `docs/corpus-v1.md`, `src/eval_metrics.py`, and `src/reranking.py` are the actual baseline. Do not create duplicate golden-query or evaluation files just because the old Linear ticket used earlier placeholder names.

## Day 10 objective

Build the first interview-defensible **source-cited answer-generation layer** on top of the existing retrieval stack. Up to Day 9, ProcureRAG can retrieve, rerank, and evaluate context deeply; it still cannot answer a procurement question in natural language with citations. Today should close that gap without turning into a framework integration day.

By the end of the day, Juan should be able to explain and demonstrate:

1. how the system chooses retrieved chunks/documents as context;
2. how the prompt constrains the LLM to answer only from retrieved evidence;
3. how citations map answer claims back to retrieved source ids/chunks;
4. what happens when evidence is incomplete, conflicting, or multi-document;
5. how answer-generation quality will later be evaluated separately from retrieval quality.

This is the bridge from Week 2 retrieval into Week 3 grounded generation. HER-276 still needs the Week 2 gate lens: before building the generator, make sure the retrieval/eval baseline is clean and can be summarized clearly.

## Starting state

The repo currently has:

- `src/preprocessing.py` — corpus loading, text normalization, and tokenization.
- `src/retrieval.py` — TF-IDF and BM25 lexical retrieval.
- `src/semantic_search.py` — dense/cosine document retrieval.
- `src/chunking.py` — sentence-aware overlapping chunker.
- `src/chunked_search.py` — chunk-level dense retrieval and BM25-over-chunks.
- `src/hybrid_search.py` — RRF/weighted fusion plus metadata-filtering utilities.
- `src/reranking.py` — two-stage cross-encoder reranking over chunk-level Hybrid RRF shortlists.
- `src/eval_metrics.py` — binary retrieval metrics, nDCG@5, filtered-adjusted evals, and error slices.
- `data/corpus_v1/procurement_kb.jsonl` — 34 realistic procurement documents.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query golden set with expected answers, relevant ids, grades, filters, and evidence quotes.
- `docs/eval-report.md` — current Day 7/8/9 metrics report.

Baseline checks at Day 10 kickoff:

```bash
./.venv/bin/pytest -q
# 120 passed in 0.60s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python src/eval_metrics.py
# v1 baseline: 93 queries, 34 documents, 570 chunks, retrieval depth=10, candidate pool=15
# Cross-encoder reranked Hybrid RRF chunk→document: P@1 0.978, R@5 0.806, MRR@10 0.984, nDCG@5 0.869
# Filtered-adjusted rows: both key chunk methods P@1 1.000 / R@5 0.948 / MRR@10 1.000 over 21 filtered queries
# Largest weak slice: reranked multi_doc P@1 0.600 over 5 queries
```

Current retrieval/eval facts to carry forward:

- Strongest overall retrieval row: **Cross-encoder reranked Hybrid RRF chunk→document** for P@1/MRR@10/nDCG@5.
- Strongest first-stage row: **Hybrid RRF chunk→document**; it still has slightly higher aggregate R@5 than the reranked row (`0.811` vs. `0.806`).
- Filtered retrieval is now methodology-safe: filtered candidates are scored against filter-adjusted gold, not raw unfiltered gold.
- The clearest known weakness is `multi_doc` generation risk: on Q091, reranking demotes a correct first-stage document and makes the top-1 document wrong. That matters more once a generator turns the retrieved context into an answer.
- No answer-generation module exists yet. Any `src/generation.py` / `tests/test_generation.py` work is Juan-owned.

## Key concepts to nail today

### Augmentation is the contract between retrieval and generation

Retrieval decides *what evidence enters the prompt*. Generation decides *how to turn that evidence into an answer*. A good RAG system needs an explicit interface between them: ranked context items with stable ids, titles, source document ids, chunk text, ranks, and scores. If that interface is vague, citations become decorative and debugging hallucinations becomes guesswork.

Today, Juan should design the smallest useful context contract before writing generator code. The answer generator should not receive a blob of anonymous text. It should receive a list of source objects where each citation in the answer can be traced back to a retrieved document or chunk.

### Grounded generation is different from fluent summarization

An LLM can write a polished procurement answer from memory or from plausible-sounding context. ProcureRAG's bar is stricter: every specific claim — threshold, supplier, clause, date, percentage, approval band — should be supported by provided context. If the retrieved evidence does not contain the answer, the system should say it lacks enough evidence rather than inventing.

For a procurement portfolio project, this matters more than style. A fluent but uncited answer about a €250,000 approval threshold is worse than a cautious answer that cites the exact policy and says what remains unknown.

### Citations must be source-backed, not just bracket numbers

Boot.dev's citation lesson is the key project artifact today. Citations should map to real source ids, ideally with enough metadata to verify them: `doc_id`, `title`, and `chunk_id` where available. Bracket markers like `[1]` are only useful if the system also prints or returns a source list that explains exactly what `[1]` means.

A practical Day 10 target is a deterministic citation formatter and prompt/context builder, plus an optional live LLM call. Tests can and should avoid external APIs by using fake generated text or fake client responses, but the contract should be ready for OpenRouter/OpenAI-compatible usage later.

### Multi-document and conflicting evidence are where generation becomes real

Day 9 found `multi_doc` is the weak slice. Day 10 should not only demo an easy lookup query. Use at least one multi-document query — especially Q091 or Q093 — because these force the generator to synthesize several evidence sources and avoid over-compressing nuance into one confident but incomplete answer.

Conflict resolution does not require a full contradiction-detection system today. It can be a rule in the prompt and a small demo: if sources disagree or scope differs, name the difference and cite each source separately rather than merging them into one false average.

### Evaluation now splits into retrieval eval and answer eval

Day 9's metrics say whether the right context was retrieved. They do not say whether the final answer is faithful, complete, well-cited, or safe. Today should record that boundary clearly. The first answer-generation artifact can have simple deterministic checks — citations present, cited ids exist, answer refuses when no context, prompt contains context ids — while fuller faithfulness/answer-relevance evaluation remains the next layer.

## Target evidence by end of day

- [ ] Boot.dev Chapter 10 lessons 1–5 are completed or reactivated, with notes captured.
- [ ] Week 2 gate baseline is re-run and summarized: tests, compile, `src/eval_metrics.py`, and the key retrieval/eval story from Day 7–9.
- [ ] Juan designs a context object / citation contract before generation code: source id, title, document id, chunk id where available, text, rank, and score fields.
- [ ] Juan builds a minimal answer-generation layer that takes retrieved context and returns a user-facing answer plus citations. Recommended repo shape: `src/generation.py` and `tests/test_generation.py`, but Juan decides the final structure.
- [ ] Tests are deterministic and do **not** require a live LLM call. They should cover prompt construction, citation/source mapping, empty-context behavior, and at least one multi-source answer shape.
- [ ] If a live LLM call is attempted, it is optional/smoke-only and kept outside the standard test suite. The repo currently has no OpenAI/OpenRouter dependency in `pyproject.toml`; Juan should add one only if he chooses the live route today.
- [ ] A demo query runs against the existing retrieval stack and prints an answer with source citations. Include at least one easy query and one multi-document query such as Q091 or Q093.
- [ ] `docs/eval-report.md` or a short generation report section records what is tested deterministically, what was smoke-tested live, and what remains unevaluated.
- [ ] `docs/learning-log.md` has a Day 10 entry with real evidence, confusion, interview explanation, remaining weakness, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline + gate lens, 30–40m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python src/eval_metrics.py
```

Then answer from memory:

1. What is the strongest current retrieval row?
   **Expected:** Cross-encoder reranked Hybrid RRF chunk→document for P@1/MRR@10/nDCG@5, while first-stage Hybrid RRF chunk→document is still slightly better on aggregate R@5.
2. What did Day 9 add beyond binary metrics?
   **Expected:** nDCG@5 over `relevance_grades`, filter-adjusted gold for filtered retrieval, and error slices by query type/difficulty/filter/single-vs-multi-primary.
3. What is the known weakness Day 10 should stress-test?
   **Expected:** multi-document questions, especially Q091/Q093-style synthesis where reranking or top-1 framing can over-favor one source and miss the full answer.
4. What stale assumptions in HER-276 should you ignore?
   **Expected:** do not create `data/golden_queries.jsonl` or `src/evaluation.py` just because the ticket text says so; the canonical files are `data/corpus_v1/example_queries.jsonl` and `src/eval_metrics.py`.

### Block 1 — Boot.dev Chapter 10 lessons, 75–105m

Work through or reactivate the five Chapter 10 lessons:

| Lesson | ProcureRAG proof target |
|---|---|
| Augmented Generation | Explain the retrieve → augment prompt → generate answer pipeline in your own words. |
| LLM Summarization | Draft how multiple retrieved snippets become one procurement answer without dumping context verbatim. |
| Conflict Resolution in Summaries | Define what the answer should do when policies/contracts differ by scope, supplier, date, or threshold. |
| Adding Citations | Implement or design source-backed citations where `[1]` maps to a real document/chunk. |
| Question Answering | Produce direct answers to buyer-style questions using retrieved procurement evidence only. |

Capture 3–5 bullets in the learning log connecting these lessons to procurement RAG: source traceability, thresholds, multi-document answers, filter scope, and hallucination avoidance.

### Block 2 — Design the Day 10 artifact contract, 45–60m

Before coding, write the contract in a scratchpad or the learning log:

- **Retrieval input:** probably the existing chunk-level Hybrid RRF + cross-encoder reranked shortlist, rolled up or preserved as chunks depending on the citation design.
- **Context schema:** each source should preserve `doc_id`, `title`, optional `chunk_id`, `text`, `rank`, and score/debug fields.
- **Prompt contract:** answer only from provided context; cite specific sources; say when evidence is missing; keep procurement thresholds/figures exact.
- **Citation contract:** every citation marker in the answer maps to a source id in a returned source list. No orphan citations and no uncited source claims.
- **Empty-context behavior:** return a safe insufficient-evidence response, not a best guess.
- **Conflict behavior:** if sources disagree or apply to different scopes, present the distinction and cite both.
- **Test boundary:** fake LLM/client in tests; live OpenRouter/OpenAI-compatible call is optional and not a standard gate.

### Block 3A — Primary route: Juan-owned source-cited answer generation, 2–2.5h

Recommended files Juan may create or modify when ready:

- `src/generation.py` — likely place for context formatting, prompt construction, citation formatting, and optional client boundary.
- `tests/test_generation.py` — deterministic tests with fake generated responses / fake model clients.
- `docs/eval-report.md` — short Day 10 generation addendum or a pointer to a separate report.
- `docs/learning-log.md` — Day 10 evidence after building.
- Optional: `docs/generation-report.md` if the generation evidence becomes too large for `eval-report.md`.

Suggested implementation steps, not mandatory exact structure:

1. Build a small source/context formatter from retrieved chunk/document results.
2. Build a prompt that includes numbered sources and explicit citation rules.
3. Add a generation boundary that can accept a fake client in tests and, an OpenAI-compatible client for live smoke tests (openrouter/free i will provide API key in .env file).
4. Add citation/source-list formatting so `[1]` maps to a real source object, not just an inline decoration.
5. Add deterministic tests first: prompt contains source ids, empty context refuses, citation mapping validates, multi-source answer includes multiple citations, fake client output passes through with sources.
6. Wire a small demo: retrieve context for one easy query and one multi-document query, call the generator boundary, print answer + sources.
7. Update docs with actual commands and output. Do not hand-type model results as if they were run.

Do not implement LangGraph agents, FastAPI serving, vector DB migration, RAGAS/DeepEval framework integration, streaming UI, MCP, or production deployment today. Those belong to later gates.

### Block 3B — Fallback route: prompt/citation contract without live LLM, 60–90m

Use this if Chapter 10 or dependency setup runs long.

Still produce evidence:

1. Finish/reactivate the five Chapter 10 lessons.
2. Write the context schema and prompt template.
3. Implement deterministic citation/source formatting and tests without a live model.
4. Add a fake-client generation test that proves the boundary shape works.
5. Record the exact live-model blocker or next command in the learning log.

The non-negotiable output is not a model demo; it is a **grounded-generation contract** that can be tested and explained.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. What does “augmented” mean in Retrieval-Augmented Generation?

   **Expected answer shape:** the LLM prompt is augmented with retrieved external context, so generation is grounded in project/domain evidence instead of only parametric model memory.

2. Why does ProcureRAG need citations?

   **Expected answer shape:** procurement answers include thresholds, clauses, suppliers, and dates that must be auditable. Citations let a user verify where a claim came from and let engineers debug whether a failure was retrieval or generation.

3. What is the difference between retrieval quality and answer quality?

   **Expected answer shape:** retrieval quality asks whether the right context is in the shortlist; answer quality asks whether the model used that context faithfully, completely, and clearly, with citations. Good retrieval can still produce a bad answer.

4. How should the system behave when retrieved sources conflict or apply to different scopes?

   **Expected answer shape:** do not average or hide the difference. State the scope distinction, cite each source, and avoid a single overconfident answer unless the evidence supports it.

5. Why should tests not depend on a live LLM call?

   **Expected answer shape:** live calls are slow, flaky, cost-bearing, and nondeterministic. Unit tests should verify prompt/citation/control-flow contracts with fake clients; live calls belong in optional smoke tests.

6. How can a generator hallucinate even when retrieval is correct?

   **Expected answer shape:** it can overgeneralize, omit qualifiers, combine incompatible sources, invent missing thresholds, or cite a source that does not support the claim. Grounding requires prompt constraints, citation checks, and later faithfulness evaluation.

7. Why is Q091/Q093 a better generation test than only Q001?

   **Expected answer shape:** Q001 is a simple lookup; Q091/Q093 require multi-document synthesis and scope handling. They expose whether the generator can combine evidence without flattening nuance.

## Hermes review protocol

When Juan has a serious Day 10 attempt ready, ask Hermes:

> Review my Day 10 ProcureRAG augmented-generation work. Check the Boot.dev Chapter 10 evidence, Week 2 gate baseline, context/citation contract, deterministic generation tests, optional live smoke output, docs updates, and whether I can explain grounded generation, citations, retrieval-vs-answer evaluation, conflict handling, and live-LLM test boundaries in an AI Engineer interview. Do not rewrite the implementation for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan’s implementation.

## Stop condition

Day 10 is complete when there is generation evidence, not just a prompt idea:

1. Boot.dev Chapter 10 Augmented Generation lessons 1–5 are recorded.
2. Week 2 retrieval/eval baseline is re-run and the strongest/weakest findings are summarized.
3. A context + citation contract exists and is exercised by deterministic tests.
4. A minimal generated answer path exists, either with a fake client plus optional live smoke or with a clearly documented blocker.
5. At least one demo stresses multi-source procurement answering, not only an easy lookup.
6. Docs record what is deterministic, what is live-smoke-only, and what remains weak.
7. The learning log explains what changed from retrieval-only evals to answer-generation evals.
8. Juan can explain augmented generation and citations without notes.

Do not close HER-276 on route creation alone. The route is the kickoff; Juan’s Chapter 10 work, tests, evidence, and Week 2 gate explanation are the acceptance criteria.
