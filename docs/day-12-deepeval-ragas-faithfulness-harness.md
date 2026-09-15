# Day 12 — DeepEval/RAGAS Faithfulness Harness

Date: 2026-09-15 target; started 2026-09-15.

Linear: HER-279 — Day 12 loop: DeepEval/RAGAS faithfulness harness.

Related gate: HER-268 — Week 3 gate: grounded generation + RAG eval harness.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

Boot.dev RAG course target:

- **No new Boot.dev chapter is required today.** You have completed Chapter 10, and Day 12 deliberately switches from Boot.dev course content to framework-backed RAG evaluation concepts.
- **Chapter 10 — Augmented Generation, completed and used as the baseline:**
  1. **Augmented Generation** — retrieve context, augment the model input, generate from that context.
  2. **LLM Summarization** — synthesize retrieved snippets into coherent output.
  3. **Conflict Resolution in Summaries** — avoid merging differently scoped evidence into one unsupported claim.
  4. **Adding Citations** — attach claims to traceable source ids.
  5. **Question Answering** — answer the buyer's question directly while staying inside retrieved evidence.
- **Chapter 11 — Agentic remains deferred today.** The project still needs one calibrated LLM-as-judge / framework-eval layer before moving into agentic retrieval workflows. The point is to understand answer evaluation, not to add an agent.

Companion docs to read today — **be selective and exact**:

### DeepEval docs — primary reading path

Read these pages in this order:

1. **DeepEval — `Introduction to LLM Evaluation Metrics`**  
   URL: `https://deepeval.com/docs/metrics-introduction`  
   Read sections:
   - `Core Concept` — test case vs. metric, 0–1 scores, reasons, threshold pass/fail.
   - `Metric Categories` → `RAG Metrics` — retriever vs. generator split.
   - `Required Test Case Parameters` — each metric needs specific fields.
   - Skim `Why Use deepeval Metrics?` only for the tradeoff vocabulary: LLM-as-judge, reasoning, caching, pytest integration, Confident AI ecosystem.

2. **DeepEval — `Faithfulness`**  
   URL: `https://deepeval.com/docs/metrics-faithfulness`  
   Read sections:
   - `Purpose` / overview — faithfulness checks whether `actual_output` factually aligns with `retrieval_context`.
   - `Difference from HallucinationMetric` — RAG faithfulness is about contradiction/support against retrieved context, not generic model hallucination.
   - `Required Arguments` — `input`, `actual_output`, `retrieval_context`.
   - Usage example enough to know the object shape: `FaithfulnessMetric(...)`, `LLMTestCase(...)`, `evaluate(...)`.
   - If time permits: skim optional parameters (`threshold`, `model`, `include_reason`, `strict_mode`, async/verbose/template) because they become Day 12 design knobs.

3. **DeepEval — `Answer Relevancy`**  
   URL: `https://deepeval.com/docs/metrics-answer-relevancy`  
   Read sections:
   - `Overview` — evaluates whether `actual_output` addresses `input`; referenceless; does not require expected answer.
   - `Required Arguments` — `input`, `actual_output`.
   - `How Is It Calculated` / calculation notes if visible — statement extraction and relevance judging; be able to explain why this is not the same as factual correctness.

4. **DeepEval — `Contextual Relevancy`**  
   URL: `https://deepeval.com/docs/metrics-contextual-relevancy`  
   Read sections:
   - `Overview` — retriever-quality metric: is retrieved context relevant to the user input?
   - `Required Arguments` — `input`, `actual_output`, `retrieval_context`; note that `actual_output` is required by the test case shape even though the metric primarily evaluates context vs. input.

5. **DeepEval — `Contextual Recall`**  
   URL: `https://deepeval.com/docs/metrics-contextual-recall`  
   Read sections:
   - `What It Measures` — whether `retrieval_context` contains the information needed to support `expected_output`.
   - `Required Test Case Arguments` — `input`, `actual_output`, `expected_output`, `retrieval_context`.
   - Compare this directly to ProcureRAG Day 11 `check_context_recall`, which is deterministic id-level recall over primary documents.

6. **DeepEval — `Contextual Precision`**  
   URL: `https://deepeval.com/docs/metrics-contextual-precision`  
   Read sections:
   - `Overview` — whether relevant chunks are ranked above irrelevant chunks; especially useful for retriever/reranker evaluation.
   - `Required Test Case Arguments` — `input`, `actual_output`, `expected_output`, `retrieval_context`.
   - Map this to ProcureRAG's existing P@1/R@5/MRR@10/nDCG@5 and reranking evidence; DeepEval's judge may grade semantic relevance, while the project already has id/grade-based metrics.

7. **DeepEval — `RAGAS` wrapper page**  
   URL: `https://deepeval.com/docs/metrics-ragas`  
   Skim only after reading the native metrics. The key fact is that DeepEval exposes a RAGAS aggregate/wrapper around answer relevancy, faithfulness, contextual precision, and contextual recall, but DeepEval's docs recommend its native RAG metrics for debuggability, judge reasoning, JSON confinement, pytest integration, and Confident AI support.

### RAGAS docs — parity/contrast reading path

Read these pages in this order:

1. **RAGAS — `Metrics` overview**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/`  
   Read sections:
   - `Available Metrics` → `Retrieval Augmented Generation` taxonomy.
   - Note the names: `Context Precision`, `Context Recall`, `Context Entities Recall`, `Noise Sensitivity`, `Response Relevancy`, `Faithfulness`.
   - Also note non-RAG comparison metrics: `Factual Correctness`, `Semantic Similarity`, and traditional non-LLM metrics.

2. **RAGAS — `Faithfulness`**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/`  
   Read sections:
   - Definition: factual consistency of `response` with `retrieved_contexts`, score 0–1.
   - Formula: supported response claims divided by total response claims.
   - Example enough to recognize the API shape: `Faithfulness(llm=...)`, `.ascore(user_input=..., response=..., retrieved_contexts=[...])`.
   - Interview point: this is the closest framework analogue to the missing Day 11 claim-level support check.

3. **RAGAS — `Response Relevancy` / `Answer Relevancy`**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/answer_relevance/`  
   Read sections:
   - Definition: how directly and appropriately the response addresses user input; score 0–1-ish.
   - Calculation: generate artificial questions from the response and compare them to the original question with embeddings/cosine similarity.
   - Caveat: relevancy does not prove factual correctness; a very on-topic answer can still be wrong.

4. **RAGAS — `Context Recall`**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_recall/`  
   Read sections:
   - Definition: how many relevant documents/pieces of information were retrieved; recall is about not missing important evidence.
   - LLM-based path: breaks the `reference` answer into claims and checks whether each is attributable to retrieved context.
   - Skim `Non LLM Based Context Recall` / `ID Based Context Recall` if visible — this is the closest to ProcureRAG's deterministic Day 11 `check_context_recall`.

5. **RAGAS — `Context Precision`**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_precision/`  
   Read sections:
   - Definition: retriever ranks relevant chunks above irrelevant chunks.
   - Formula: mean of precision@k for relevant chunks in the retrieved list.
   - Skim variants: with reference answer, without reference, with reference contexts, and ID-based context precision. The ID-based variant is especially relevant because ProcureRAG has stable `doc_id` and `chunk_id` fields.

6. **RAGAS — `Context Entities Recall`**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_entities_recall/`  
   Read sections:
   - Definition: entity overlap between reference and retrieved contexts.
   - Formula: common entities divided by reference entities.
   - Procurement mapping: possible future use for supplier IDs, contract IDs, approval roles, thresholds, and named systems like Ariba/SAP — not the Day 12 primary build.

7. **RAGAS — `Factual Correctness`**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/factual_correctness/`  
   Read sections:
   - Definition: compares generated `response` to `reference`, decomposes both into claims, uses NLI-style factual overlap.
   - Modes: precision, recall, F1. This is the framework analogue to Day 11's curated `expected_terms` check, but claim-based rather than substring-based.

8. **RAGAS — `Semantic Similarity`**  
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/semantic_similarity/`  
   Read sections:
   - Definition: embedding/cosine similarity between generated response and reference answer.
   - Caveat: similarity can be high even when a critical numeric threshold or approval role is wrong, so do not use it alone for procurement QA.

If time is tight, read DeepEval pages 1–6 and RAGAS pages 1–5. Treat RAGAS pages 6–8 as stretch/contrast.

## Day 12 objective

Build the **first framework-eval bridge** around ProcureRAG's generated-answer evaluation layer without weakening the deterministic baseline.

Day 11 made Q091's failure visible through deterministic checks: primary context recall failed because `POL-001` and `GUIDE-002` never reached the generated-answer context; expected terms failed because the answer omitted `Band 3` / renewal usage data; unsupported inference was flagged by hand-curated hedge phrases. Day 12 asks: what would a real evaluation framework add, and what would it still miss?

By the end of today, Juan should be able to demonstrate and explain:

1. how a ProcureRAG `(query, answer, sources, expected_answer)` record maps to DeepEval / RAGAS metric inputs;
2. the difference between deterministic gates, LLM-as-judge metrics, and embedding-similarity metrics;
3. why Q001 and Q091 are calibration anchors before trusting any framework score;
4. what exact dependency/API-key boundaries keep CI deterministic;
5. why judge scores need reasons, thresholds, and human calibration rather than blind pass/fail automation.

## Starting state

The repo currently has:

- `src/generation.py` — source construction, prompt construction, citation extraction/validation, empty-context refusal, and optional OpenRouter live client.
- `src/generation_eval.py` — Day 11 deterministic answer-eval checks: `citation_validity`, `context_recall`, `expected_terms`, and `unsupported_inference`, plus curated Q001/Q091 fixtures.
- `tests/test_generation_eval.py` — 16 deterministic tests covering the Day 11 eval contract and Q001/Q091 fixtures.
- `src/eval_metrics.py` — retrieval metrics, nDCG@5, filtered-adjusted evals, and error slices over the canonical v1 query set.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query source with `expected_answer`, `expected_relevant_ids`, `relevance_grades`, `metadata_filters`, and evidence quotes.
- `docs/eval-report.md` — retrieval and generation-eval report through Day 11.
- `docs/learning-log.md` — Day 11 leaves two reasonable Day 12 options: expand deterministic curated fixtures or build the first LLM-as-judge faithfulness pass calibrated against Q001/Q091.

Baseline checks at Day 12 kickoff:

```bash
./.venv/bin/pytest -q
# 151 passed in 1.84s

./.venv/bin/python -m compileall -q src tests
# clean, no output
```

Current facts to carry forward:

- Deterministic CI is green before Day 12 starts.
- Q001 is the known-good generation-eval fixture.
- Q091 is the known-incomplete fixture: citation validity passes, but context recall and expected terms fail.
- No framework-backed DeepEval or RAGAS dependency exists in `pyproject.toml` yet.
- No live judge score should be faked. If framework install/model access is blocked, document the blocker and keep the adapter/test contract as the evidence.

## Key concepts to nail today

### A framework metric is not automatically a better ground truth

DeepEval and RAGAS are useful because they operationalize RAG-eval vocabulary into repeatable objects: faithfulness, answer relevancy, contextual precision, contextual recall, factual correctness, semantic similarity. But most of the powerful metrics involve an LLM judge. That means scores depend on judge model choice, prompt templates, thresholds, context formatting, provider reliability, and calibration examples.

The Day 12 mindset is: **framework metrics are another measurement layer, not an oracle.** Q001 and Q091 are your calibration anchors. If a faithfulness/context-recall setup cannot distinguish Q001's clean answer from Q091's missing-primary-evidence answer, the setup is not trustworthy yet, even if it returns a polished numeric score.

### DeepEval and RAGAS use similar words, but input contracts matter

DeepEval's `LLMTestCase` fields vary by metric. Faithfulness needs `input`, `actual_output`, and `retrieval_context`. Answer relevancy needs `input` and `actual_output`. Contextual precision/recall need `input`, `actual_output`, `expected_output`, and `retrieval_context`. Contextual relevancy is referenceless but still uses `retrieval_context` against `input`.

RAGAS uses closely related but not identical names: `user_input`, `response`, `retrieved_contexts`, `reference`, sometimes `reference_contexts` or IDs depending on the variant. Day 12 should not bury this mapping inside one large function. Make the adapter boundary explicit so an interviewer can see how ProcureRAG's data model is translated into each framework's expected shape.

### Pick one first live metric, not every metric at once

The best first live path is DeepEval `FaithfulnessMetric` or RAGAS `Faithfulness`, because Day 11's biggest stated gap is claim-level source support. Second priority is answer/response relevancy, because it checks whether the generated answer actually addresses the buyer's question. Contextual precision/recall are important, but this project already has strong deterministic id/grade retrieval metrics; framework context metrics should be used as contrast, not as replacements.

If time is limited, produce a clean adapter + one live/stubbed faithfulness path + deterministic no-key tests. That is better than half-integrating DeepEval, RAGAS, Langfuse, and new retrieval code in the same day.

### Calibration examples are part of the artifact

Do not run a judge against one happy-path query and call it done. Use at least Q001 and Q091:

- Q001 should score high on faithfulness/context support and answer relevancy.
- Q091 is subtle: the answer may be faithful to the retrieved context but incomplete relative to reference evidence. A pure faithfulness metric may not punish missing `POL-001`/`GUIDE-002` if it only asks whether the answer is supported by the sources it saw. Context recall or factual correctness may surface the missing evidence more directly.

This distinction is exactly the lesson. Day 12 should explain which metric catches which failure and which metric is blind to it.

## Target evidence by end of day

- [ ] DeepEval/RAGAS docs reading notes record the exact pages/sections above, not a vague "read RAGAS docs" checkbox.
- [ ] Juan designs the framework-eval adapter contract before coding: ProcureRAG input shape, framework test-case shape, metric result shape, no-key behavior, dependency boundary.
- [ ] Juan builds or extends an eval harness, likely in `src/generation_eval.py` or a small adjacent module, without network calls in unit tests.
- [ ] At least one framework path is implemented or cleanly stubbed behind explicit dependency/API-key checks. Preferred first metric: faithfulness.
- [ ] Tests cover data-shaping / adapter logic and no-key/no-dependency behavior without calling a live judge.
- [ ] Q001 and Q091 are used as calibration examples, and the docs explain what the selected metric does and does not catch.
- [ ] `docs/eval-report.md` records metric definitions, command output, dependency/key status, threshold choice, score/reason output if live scoring ran, and caveats if it did not.
- [ ] `docs/learning-log.md` has a Day 12 entry with real evidence, confusion, interview explanation, remaining weakness, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline and verify green state, 25–35m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
```

Then reread:

- `docs/day-11-grounded-answer-evaluation.md` — especially target evidence, Q091 explanation, and stop condition.
- `src/generation_eval.py` — `evaluate_generated_answer`, `CURATED_FIXTURES`, Q001/Q091 required terms.
- `tests/test_generation_eval.py` — how the deterministic fixtures prove Q001 pass / Q091 fail.
- `docs/eval-report.md` — Day 11 addendum and the Day 10 Q091 transcript.

Answer from memory:

1. What did Day 11's `context_recall` catch on Q091?  
   **Expected:** `POL-001` and `GUIDE-002` were primary expected docs but absent from retrieved context.
2. Why can a faithfulness metric miss that same problem?  
   **Expected:** faithfulness usually asks whether the answer is supported by the retrieved context it saw; it may not penalize evidence that never reached the prompt unless paired with context recall / reference completeness.
3. Why is Q001 useful but insufficient?  
   **Expected:** it proves happy-path wiring; it does not prove the harness detects subtle missing-evidence failures.

### Block 1 — DeepEval/RAGAS focused reading, 90–120m

Use the exact reading list above. Capture notes in the learning log or scratchpad under these headings:

| Framework/page | What it measures | Required fields | ProcureRAG mapping | Caveat |
|---|---|---|---|---|
| DeepEval Faithfulness | answer support vs retrieved context | `input`, `actual_output`, `retrieval_context` | query, generated answer, source texts | may not catch missing-but-unretrieved docs |
| DeepEval Answer Relevancy | answer addresses query | `input`, `actual_output` | query, generated answer | not factual correctness |
| DeepEval Contextual Recall | retrieved context supports expected answer | `input`, `actual_output`, `expected_output`, `retrieval_context` | query, answer, `expected_answer`, source texts | judge/model dependent |
| RAGAS Faithfulness | supported response claims / total claims | `user_input`, `response`, `retrieved_contexts` | query, generated answer, source texts | judge/model dependent |
| RAGAS Context Recall | reference claims attributable to context | `reference`, `retrieved_contexts`, plus query | `expected_answer`, source texts | closest to missing-evidence check |
| RAGAS Factual Correctness | response/reference claim overlap | `response`, `reference` | generated answer, `expected_answer` | may need precision vs recall mode choice |

Do not install anything in this block. First understand the input contracts.

### Block 2 — Design the Day 12 adapter contract, 45–60m

Before coding, write down a compact contract:

- **Canonical ProcureRAG eval case:**
  - `query_id`
  - `input` / buyer question
  - `actual_output` / generated answer
  - `expected_output` / `expected_answer`
  - `retrieval_context` / list of source texts, preserving order
  - `source_metadata` / `source_id`, `doc_id`, `chunk_id`, `rank`
  - `deterministic_findings` from Day 11
- **Framework case builder:** one function that turns a ProcureRAG fixture/query row into a plain framework-neutral dict.
- **DeepEval adapter:** converts the neutral dict into `LLMTestCase` only inside a function that first checks dependency/key availability.
- **RAGAS adapter:** converts the neutral dict into `.ascore(...)` arguments only inside a function that first checks dependency/key availability.
- **Result shape:** `framework`, `metric`, `query_id`, `score`, `threshold`, `passed`, `reason`, `status`, `error`, `judge_model`.
- **No-key behavior:** deterministic tests must prove missing dependency/API key returns a clear blocked status or raises the project's own controlled error — not `ModuleNotFoundError`, not a fake score.

Preferred design: keep the Day 11 deterministic checks callable exactly as they are. Add the framework path as an optional layer, not a replacement.

### Block 3A — Primary route: Juan-owned framework-eval adapter + one metric, 2–2.5h

Recommended files Juan may create or modify when ready:

- `src/generation_eval.py` — if the framework adapter stays small and clearly separated.
- Or `src/framework_eval.py` / `src/judge_eval.py` — if a separate optional-framework boundary reads cleaner.
- `tests/test_generation_eval.py` or a new `tests/test_framework_eval.py` — deterministic adapter/no-key tests only.
- `docs/eval-report.md` — Day 12 addendum with real command output and caveats.
- `docs/learning-log.md` — Day 12 evidence after building.
- `pyproject.toml` / `uv.lock` — only if Juan deliberately chooses to install DeepEval or RAGAS today.

Suggested implementation steps, not mandatory exact structure:

1. Build a neutral `FrameworkEvalCase` shape from existing Q001/Q091 curated fixtures plus real query rows loaded from `data/corpus_v1/example_queries.jsonl`.
2. Write tests that assert Q001/Q091 map to the expected fields and preserve source order.
3. Add a controlled optional dependency boundary, e.g. a function that imports DeepEval inside the function body and returns/raises a clear blocked status if absent.
4. Implement one metric path first, preferably DeepEval `FaithfulnessMetric` or RAGAS `Faithfulness`.
5. Keep live judge execution behind an explicit CLI flag or function parameter. The default test suite must not call any live LLM judge.
6. If a live judge key/model is available, run Q001 and Q091 and record score + reason exactly.
7. If live judging is blocked, run the adapter/demo in blocked mode and document the blocker honestly.
8. Update `docs/eval-report.md` with methodology, real command output, and the calibration interpretation.
9. Fill in the Day 12 learning-log entry.

### Block 3B — Fallback route: adapter + calibration rubric, 60–90m

Use this if DeepEval/RAGAS installation or provider access becomes the bottleneck.

Still produce evidence:

1. Finish the docs reading table.
2. Build the framework-neutral eval case adapter.
3. Add deterministic tests for case construction, source ordering, and missing dependency/key behavior.
4. Write a manual calibration rubric for Q001, Q091, and one optional third query, explaining expected metric behavior.
5. Document the live-score blocker in `docs/eval-report.md` without inventing scores.

The non-negotiable output is a clean contract and calibration plan. A fake `score=0.92` is worse than no framework run.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. What is the difference between faithfulness and answer relevancy?

   **Expected answer shape:** faithfulness checks whether answer claims are supported by retrieved context; answer relevancy checks whether the answer addresses the user's question. An answer can be relevant but unsupported, or faithful to incomplete context but incomplete overall.

2. Why might Q091 pass a faithfulness metric but still be a bad answer?

   **Expected answer shape:** if the answer only makes claims supported by the retrieved sources, faithfulness can be high; but retrieval omitted primary documents (`POL-001`, `GUIDE-002`), so the answer remains incomplete relative to reference evidence. Context recall / factual correctness / expected-answer comparison are needed too.

3. What are the required inputs for DeepEval faithfulness vs contextual recall?

   **Expected answer shape:** faithfulness needs `input`, `actual_output`, `retrieval_context`; contextual recall needs `input`, `actual_output`, `expected_output`, `retrieval_context` because it checks whether context supports the expected answer.

4. What is the RAGAS faithfulness formula in plain language?

   **Expected answer shape:** decompose the response into claims; count how many are supported by retrieved context; score = supported claims / total response claims.

5. Why keep deterministic tests if DeepEval/RAGAS exist?

   **Expected answer shape:** deterministic tests are cheap, reproducible, CI-safe, and calibrated to known failures. LLM judges add semantic judgment but introduce model drift, cost, latency, prompt variance, and threshold calibration questions.

6. What should an eval result record besides `score`?

   **Expected answer shape:** framework, metric, query id, judge model, threshold, pass/fail, reason, input fields used, retrieval context ids, dependency/key status, and caveats.

7. How would you explain DeepEval/RAGAS to an interviewer without overselling them?

   **Expected answer shape:** they are evaluation frameworks that operationalize RAG metrics and provide judge reasons, but they are not ground truth. I calibrate them against known-good/known-bad fixtures and keep deterministic checks for hard guarantees.

## Hermes review protocol

When Juan has a serious Day 12 attempt ready, ask Hermes:

> Review my Day 12 ProcureRAG DeepEval/RAGAS faithfulness harness. Check the docs-reading evidence, framework-eval adapter contract, Q001/Q091 calibration, deterministic no-key/no-dependency tests, live judge status if any, eval-report update, and whether I can explain faithfulness vs answer relevancy vs context recall vs factual correctness in an AI Engineer interview. Do not rewrite the implementation for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan's implementation.

## Stop condition

Day 12 is complete when there is a framework-eval bridge or an honestly blocked framework-eval adapter, not just notes that DeepEval/RAGAS exist:

1. Exact DeepEval/RAGAS docs pages and sections are recorded in the learning evidence.
2. A ProcureRAG → framework-eval case adapter contract exists.
3. Q001 and Q091 are used as calibration anchors.
4. Deterministic tests cover adapter/data-shaping and missing dependency/key behavior.
5. At least one framework metric path is implemented, or the blocker is explicit and reproducible.
6. `docs/eval-report.md` states which scores are deterministic, which are judge-based, and which are not safe as sole gates.
7. Juan can explain why LLM-as-judge metrics add value but must be calibrated.

Do not close HER-279 on route creation alone. The route is the kickoff; Juan's eval harness, tests, evidence, and interview explanation are the acceptance criteria.
