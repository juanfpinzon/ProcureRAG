# Day 13 — Generation Error Analysis + Multi-Doc Repair Plan

Date: 2026-09-19 kickoff.

Linear: HER-280 — Day 13 loop: generation error analysis + multi-doc repair plan.

Related gate: HER-268 — Week 3 gate: grounded generation + RAG eval harness.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

Boot.dev RAG course target:

- **No new Boot.dev chapter is required today.** Day 13 is a project-evidence / error-analysis day inside Week 3.
- **Chapter 10 — Augmented Generation, completed and used as the baseline:**
  1. **Augmented Generation** — retrieve context, augment the model input, generate from that context.
  2. **LLM Summarization** — synthesize retrieved snippets into coherent output.
  3. **Conflict Resolution in Summaries** — avoid merging differently scoped evidence into one unsupported claim.
  4. **Adding Citations** — attach claims to traceable source ids.
  5. **Question Answering** — answer the buyer's question directly while staying inside retrieved evidence.
- **Chapter 11 — Agentic remains deferred today.** The project still has to turn Q091 and sibling failures into a clear diagnosis-and-repair loop before adding agentic retrieval workflows.

Companion docs to read today — **be selective and exact**:

### DeepEval docs — framework metric contrast

Use these pages as contrast tools, not as a mandate to add every metric today:

1. **DeepEval — `Contextual Recall`**
   URL: `https://deepeval.com/docs/metrics-contextual-recall`
   Read sections:
   - Overview / `What Contextual Recall Measures` — contextual recall evaluates whether `retrieval_context` aligns with `expected_output`.
   - `Required Test Case Arguments` — `input`, `actual_output`, `expected_output`, `retrieval_context`.
   - Basic Python usage enough to recognize `ContextualRecallMetric(threshold=..., include_reason=True)` and `LLMTestCase(...)`.
   - Day 13 mapping: this is the framework metric closest in spirit to Day 11 `check_context_recall`, because it can penalize missing information needed for the expected answer.

2. **DeepEval — `Contextual Precision`**
   URL: `https://deepeval.com/docs/metrics-contextual-precision`
   Read sections:
   - Overview — contextual precision evaluates whether relevant nodes in `retrieval_context` are ranked above irrelevant nodes.
   - `Required Test Case Arguments` — same four fields as contextual recall: `input`, `actual_output`, `expected_output`, `retrieval_context`.
   - Day 13 mapping: useful for reranker / ordering diagnosis, but do not let it replace this repo's existing P@1/R@5/MRR@10/nDCG@5 tables.

3. **DeepEval — `Answer Relevancy`**
   URL: `https://deepeval.com/docs/metrics-answer-relevancy`
   Read sections:
   - Overview — evaluates whether `actual_output` addresses `input`.
   - `Required Arguments` — only `input` and `actual_output`; no expected answer or retrieval context.
   - Caveat — an answer can be relevant and still wrong, incomplete, or unsupported.

### RAGAS docs — parity / ID-based contrast

1. **RAGAS — `Context Recall`**
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_recall/`
   Read sections:
   - `Overview` — context recall is about not missing relevant documents or pieces of information.
   - `LLM-Based Context Recall` — reference answer is broken into claims; each claim is checked against retrieved context.
   - `Non-LLM Context Recall` — contrast with deterministic string/context matching.
   - `ID-Based Context Recall` — compare `retrieved_context_ids` and `reference_context_ids`; this is especially relevant because ProcureRAG has stable `doc_id` and `chunk_id` fields.

2. **RAGAS — `Context Precision`**
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_precision/`
   Read sections:
   - `Overview` and `Core Definition` — mean precision@k for relevant chunks in ranked retrieved contexts.
   - `ContextPrecision` with reference answer — compares retrieved contexts against the reference answer.
   - `ContextUtilization` — no reference answer, uses generated response.
   - `Ranking Sensitivity` — score changes when the same relevant/irrelevant chunks are reordered.

### Error-analysis method — why today is not “just add another metric”

Read one of these two Hamel/Shreya eval references:

1. **Hamel Husain + Shreya Shankar — `Q: Why is “error analysis” so important in AI evals, and how is it performed?`**
   URL: `https://hamel.dev/blog/posts/evals-faq/why-is-error-analysis-so-important-in-llm-evals-and-how-is-it-performed.html`
   Read sections:
   - `Creating a Dataset` — gather representative traces; synthetic data can start the loop if production data is absent.
   - `Open Coding` — read traces and write open-ended notes; prefer the first upstream failure when errors cascade.
   - `Axial Coding` — group notes into a failure taxonomy.
   - `Iterative Refinement` — continue until new traces stop revealing new failure modes.

2. Optional skim: **Hamel — `Automating Error Analysis`**
   URL: `https://hamel.dev/notes/llm/ai-product-engineering/evals-error-analysis.html`
   Focus: build a failure-mode taxonomy from human review instead of asking a model to invent one before looking at data.

## Day 13 objective

Build the first **generation error-analysis loop** for ProcureRAG: classify generated-answer failures by root cause, starting with the known `multi_doc` weakness and Q091, then recommend the next repair path with evidence.

Day 12 proved a crucial lesson: DeepEval/RAGAS faithfulness can pass Q091 because faithfulness asks whether the answer is supported by the context it saw, not whether the retriever fetched enough context. Day 13 turns that lesson into a diagnostic workflow. By the end of the day, Juan should be able to explain, for each inspected failure, whether the root cause is retrieval, context construction/truncation, citation/source support, answer completeness, or judge uncertainty — and what to fix next.

## Starting state

The repo currently has:

- `src/generation.py` — source-cited answer generation, prompt construction, citation validation, empty-context refusal, and optional OpenRouter live client.
- `src/generation_eval.py` — deterministic Day 11 checks: citation validity, context recall, expected terms, unsupported-inference phrase flags, and curated Q001/Q091 fixtures.
- `src/framework_eval.py` — Day 12 framework-eval bridge: neutral eval case, DeepEval/RAGAS faithfulness adapters, live/skipped/blocked/error result statuses, OpenRouter judge configuration for RAGAS.
- `tests/test_generation.py`, `tests/test_generation_eval.py`, `tests/test_framework_eval.py` — deterministic tests for generation, deterministic eval, and framework-eval adapter boundaries.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query source with `expected_answer`, `expected_relevant_ids`, `relevance_grades`, `metadata_filters`, and evidence quotes.
- `docs/eval-report.md` — retrieval, generation, deterministic answer-eval, and Day 12 DeepEval/RAGAS evidence.
- `docs/learning-log.md` — Day 12's next step points to DeepEval contextual recall as the metric closest to Day 11 `check_context_recall`.

Baseline checks at Day 13 kickoff:

```bash
./.venv/bin/pytest -q
# 167 passed in 3.69s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

Current facts to carry forward:

- Q001 remains the known-good control.
- Q091 remains the known-incomplete case: Day 11 `check_context_recall` fails because `POL-001` and `GUIDE-002` are absent; Day 12 faithfulness passes because the answer is mostly faithful to the incomplete retrieved context.
- Day 9 already identified `multi_doc` as the weak slice and Q091 as the concrete case where reranking can hurt top-1/top-k behavior.
- The canonical query source is `data/corpus_v1/example_queries.jsonl`; do not create a duplicate golden-query file.
- Live LLM/provider output is useful evidence only if current, bounded, and documented. Do not invent judge or generation scores.

## Key concepts to nail today

### Error analysis starts from traces, not metric shopping

The temptation after Day 12 is to add DeepEval contextual recall and call the day done. That metric is relevant, but it should serve a diagnosis, not replace one. The error-analysis loop is: inspect concrete cases, write failure notes, group failures into a taxonomy, then decide which metric or test makes each failure hard to miss next time.

For ProcureRAG, a “trace” can be a compact record containing the query row, retrieved source ids/chunks, generated answer, citations, deterministic findings, optional framework findings, and a human root-cause label. Day 13 does not need a production tracing platform. It needs five clear traces and a taxonomy that can survive review.

### Retrieval failure and generation failure are different owners

Q091 is the anchor example. The generated answer can be honest about the sources it was given and still be incomplete because the retriever never surfaced `POL-001` and `GUIDE-002`. That is not primarily a prompt bug. A prompt cannot cite evidence it never saw.

The classification should separate at least these root causes:

- **Retrieval miss** — expected primary document/chunk absent from retrieved context.
- **Context construction / truncation** — expected evidence was retrieved somewhere upstream but not shown to the generator.
- **Citation / source-support issue** — cited source id exists, but the claim next to it is not actually supported by that source text.
- **Answer completeness issue** — answer omits an expected point even though the evidence is present.
- **Judge uncertainty / metric disagreement** — deterministic and LLM-as-judge signals disagree, or the judge's reason is wrong/unclear.

### Multi-doc failures need document coverage, not just one better top-1

The `multi_doc` slice is not solved by making the first result better if the answer genuinely needs several documents. Day 13 should make Juan practice asking: did the context cover all primary evidence groups? Did a reranker move one relevant source up while pushing another out? Is `top_k=5` too tight for composite questions? Would per-document diversity, larger generation context, alternate first-stage pool, or a context-recall gate help more than prompt wording?

The deliverable is not necessarily a final repair implementation. It is a defensible repair plan with evidence: what failed, why it failed, what you would try first, and how you would know it worked.

### Framework metrics are calibration tools, not oracles

DeepEval contextual recall is a strong Day 13 candidate because it uses `expected_output` and `retrieval_context`, exactly the ingredients faithfulness ignored. But Day 12 showed a live judge can produce a plausible-looking but wrong reason. If Juan adds or runs contextual recall, the result must be compared to the deterministic doc-id `check_context_recall` and the actual evidence quotes, not accepted blindly.

## Target evidence by end of day

- [ ] Exact docs-reading notes record the DeepEval/RAGAS/Hamel sections above, not a vague “read eval docs” checkbox.
- [ ] Juan defines a small trace / case record shape before coding or reporting: query id, query type, expected primary docs, retrieved docs/chunks, generated answer source ids, deterministic findings, optional judge findings, human root-cause label, recommended repair.
- [ ] At least **5 generated-answer cases** are classified by failure cause, including Q091 and at least one easy control such as Q001.
- [ ] The report separates retrieval misses from generation/prompt/citation failures.
- [ ] Q091 root cause is stated precisely: missing primary evidence (`POL-001`, `GUIDE-002`) in the generation context, not merely “bad answer.”
- [ ] A recommended repair path is documented with tradeoffs and expected verification signal.
- [ ] Tests or fixtures make at least the known Q091 classification / context-recall failure hard to lose silently.
- [ ] If DeepEval contextual recall or RAGAS context recall is run live, `docs/eval-report.md` records the exact command, scores, reasons if available, model/key status, and caveats.
- [ ] `docs/learning-log.md` Day 13 entry is filled with real evidence and remaining weakness before the Week 3 gate.

## Recommended 6-hour split

### Block 0 — Reactivate baseline and define the inspection lens, 25–35m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
```

Then reread:

- `docs/eval-report.md` — Day 9 `multi_doc` / Q091 slice, Day 10 Q091 generation transcript, Day 11 deterministic eval section, Day 12 framework-eval section.
- `docs/corpus-v1.md` — `Multi-document queries` section, especially Q091 and Q093.
- `src/generation_eval.py` — Q001/Q091 fixtures and `check_context_recall`.
- `src/framework_eval.py` — neutral case shape and how `expected_output` is already carried.
- `data/corpus_v1/example_queries.jsonl` — inspect Q001, Q091, and candidate sibling multi-doc rows.

Answer from memory:

1. Why did Day 12 faithfulness pass Q091?
2. Which exact primary docs are missing from Q091's generated-answer context?
3. What is the difference between “retrieved but not cited” and “never retrieved / never shown”? 

### Block 1 — Focused reading, 60–90m

Read the companion docs listed above and capture a compact table:

| Source / metric | What it measures | Required fields | ProcureRAG mapping | Caveat |
|---|---|---|---|---|
| DeepEval Contextual Recall | Context supports expected answer | `input`, `actual_output`, `expected_output`, `retrieval_context` | query, generated answer, `expected_answer`, source texts | LLM judge may reason incorrectly; compare to doc-id recall |
| DeepEval Contextual Precision | Relevant chunks ranked above irrelevant chunks | same four fields | ranked source texts + expected answer | ranking metric; not a complete answer-quality metric |
| RAGAS Context Recall | Reference claims supported by retrieved contexts | `user_input`, `retrieved_contexts`, `reference` | query, source texts, `expected_answer` | API variants; ID-based path may be more deterministic |
| RAGAS ID-Based Context Recall | Expected ids appear in retrieved ids | retrieved ids + reference ids | source `doc_id`/`chunk_id` vs primary ids | closest to Day 11 deterministic recall |
| Hamel/Shreya error analysis | Find real failure modes before writing evals | traces + human labels | Q001/Q091/multi-doc case notes | needs human judgment; metrics follow taxonomy |

Do not install new packages in this block.

### Block 2 — Design the failure taxonomy and trace contract, 45–60m

Before coding, write down the shape of one case. Suggested fields:

```text
query_id
query_type / difficulty
question
expected_primary_doc_ids
expected_answer_summary
retrieved_source_ids / doc_ids / chunk_ids / ranks
generated_answer_summary
citation_status
context_recall_status
framework_status, if run
human_root_cause_label
notes
recommended_repair
verification_signal
```

Minimum taxonomy labels:

- `retrieval_miss`
- `context_truncation_or_construction`
- `citation_source_support_gap`
- `answer_completeness_gap`
- `judge_or_metric_disagreement`
- `passes_control`

Pick at least 5 cases:

1. Q001 — easy control, should pass.
2. Q091 — required anchor failure.
3. Q093 — multi-doc “it depends” / conflicting numeric answer risk.
4. One more `multi_doc` query from `docs/corpus-v1.md` (Q005 or Q016 are good candidates).
5. One non-`multi_doc` hard or medium query where retrieval/generation should be straightforward, to prevent overfitting the taxonomy to only Q091-like cases.

### Block 3A — Primary route: Juan-owned error-analysis workflow, 2–2.5h

Recommended files Juan may create or modify when ready:

- `docs/eval-report.md` — Day 13 section with taxonomy, case table, root-cause notes, recommended repair path, and real command output.
- `docs/learning-log.md` — Day 13 evidence after building.
- `src/generation_eval.py` or a small adjacent module — only if Juan decides the taxonomy or trace builder belongs in code. (Yes)
- `tests/test_generation_eval.py` or a new deterministic test — only if Juan adds code that must make Q091's classification / missing-context failure reproducible.
- `src/framework_eval.py` / `tests/test_framework_eval.py` — only if Juan chooses to wire DeepEval contextual recall or RAGAS context recall as a second framework metric. (Yes)

Suggested implementation steps, not mandatory exact structure:

1. Start by extracting or manually assembling the five case records. Do not begin with a generic framework abstraction.
2. For each case, record expected primary docs from `relevance_grades` and actual retrieved/generated context docs from the fixture or fresh deterministic retrieval.
3. Label each case with one primary root cause and optional secondary notes.
4. For Q091, explicitly distinguish:
   - faithfulness to shown context;
   - missing primary docs in shown context;
   - answer incompleteness relative to `expected_answer`.
5. If adding DeepEval contextual recall, run it against Q001/Q091 first, not all 93 queries. Compare its reason to deterministic `check_context_recall` and evidence quotes.
6. Recommend one repair path and one verification signal. Examples:
   - increase generation context top-k only for multi-doc queries and verify Q091 source coverage;
   - add per-document diversity to chunk selection and verify primary-doc coverage on `multi_doc` slice;
   - add a context-recall gate that blocks generation/evidence claims when primary docs are absent;
   - rerun candidate-pool / reranker analysis before changing the prompt.
7. Update `docs/eval-report.md` with the case table and command output.
8. Fill in the learning-log Day 13 entry.

### Block 3B — Fallback route: docs-first taxonomy + deterministic fixtures, 60–90m

Use this if live generation or live judge calls are flaky.

Still produce evidence:

1. Use committed Day 10/11/12 fixtures and deterministic retrieval/eval output.
2. Classify Q001, Q091, and three query rows from the corpus with a docs-first table.
3. Document exactly which live steps are blocked or deferred.
4. Create no fake live scores.
5. Record the repair plan as a hypothesis with a verification checklist.

The non-negotiable output is a clear taxonomy and Q091 repair recommendation, not a perfect tracing platform.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. Why can a generated answer be faithful but incomplete?

   **Expected answer shape:** Faithfulness checks whether answer claims are supported by retrieved context. If retrieval omitted required evidence, the answer can be faithful to the incomplete context while still missing the correct answer.

2. What made Q091 a better calibration case than only Q001?

   **Expected answer shape:** Q001 is a clean control; Q091 is a known failure where missing primary docs (`POL-001`, `GUIDE-002`) cause downstream incompleteness despite valid citations and passing faithfulness.

3. What is the difference between contextual recall and contextual precision?

   **Expected answer shape:** Contextual recall asks whether retrieved context contains the information needed for the expected answer; contextual precision asks whether relevant chunks are ranked ahead of irrelevant chunks.

4. How would you decide whether to fix retrieval or prompt wording?

   **Expected answer shape:** First inspect whether required evidence was in the context. If absent, fix retrieval/context construction. If present but unused or misused, inspect prompt/generation/citation support. Do not prompt-engineer around missing evidence.

5. What is an error taxonomy and why is it better than adding generic metrics first?

   **Expected answer shape:** A taxonomy is a human-labeled grouping of real failure modes. It tells you which evals to write and which fixes to prioritize, rather than optimizing metrics that may not correspond to observed failures.

6. What verification signal would prove a Q091 repair helped?

   **Expected answer shape:** The generation context includes all needed primary evidence, deterministic context recall passes, answer completeness improves against expected terms/evidence, and any live judge metric is consistent with the evidence rather than merely high-scoring.

## Hermes review protocol

When Juan has a serious Day 13 attempt ready, ask Hermes:

> Review my Day 13 ProcureRAG generation error analysis and multi-doc repair plan. Check the exact docs-reading evidence, failure taxonomy, at least five classified cases including Q091, separation of retrieval vs generation vs judge failures, any contextual-recall metric wiring if present, eval-report update, deterministic tests/compile/lint output, and whether the recommended Q091 repair path is evidence-backed. Do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan's implementation.

## Stop condition

Day 13 is complete when there is a reproducible error-analysis artifact, not just a new metric name:

1. Exact companion reading notes are recorded.
2. At least five cases are inspected and classified, including Q091 and one passing control.
3. Q091's root cause is explained precisely and connected to Day 9/10/11/12 evidence.
4. Retrieval/context/generation/judge failure categories are separated.
5. A repair path is recommended with tradeoffs and a verification checklist.
6. Any code Juan adds has deterministic tests; no standard test path makes live network calls.
7. Baseline gates pass: `pytest`, `compileall`, and `ruff`.
8. Juan can explain why error analysis comes before metric expansion in a production RAG loop.

Do not close HER-280 on route creation alone. The route is the kickoff; Juan's classified cases, evidence, repair plan, and interview explanation are the acceptance criteria.
