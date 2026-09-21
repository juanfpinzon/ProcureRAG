# Day 14 — Eval Regression Suite + Trace Evidence

Date: 2026-09-21 kickoff.

Linear: HER-281 — Day 14 loop: eval regression suite + trace evidence.

Related gate: HER-268 — Week 3 gate: grounded generation + RAG eval harness.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

Boot.dev RAG course target:

- **No new Boot.dev chapter is required today.** Day 14 is a project-evidence / operational-eval day inside Week 3.
- **Chapter 10 — Augmented Generation, completed and used as the baseline:**
  1. **Augmented Generation** — retrieve context, augment the model input, generate from that context.
  2. **LLM Summarization** — synthesize retrieved snippets into coherent output.
  3. **Conflict Resolution in Summaries** — avoid merging differently scoped evidence into one unsupported claim.
  4. **Adding Citations** — attach claims to traceable source ids.
  5. **Question Answering** — answer the buyer's question directly while staying inside retrieved evidence.
- **Chapter 11 — Agentic remains deferred today.** Day 13's evidence says the immediate weakness is not agentic routing yet; it is making the generation-eval loop repeatable enough to safely test the Q091/Q093 multi-doc repair.

Companion docs to read today — **be selective and exact**:

### DeepEval docs — regression metric vocabulary

Use these pages to name the regression-suite columns and to decide which live metrics are allowed in the optional path:

1. **DeepEval — `RAG Evaluation Quickstart`**
   URL: `https://deepeval.com/docs/getting-started-rag`
   Read sections:
   - `Create a dataset` — why eval examples should be stable, repeatable test cases.
   - `Write your test file` — how test cases are paired with metrics.
   - `Run your test file` / `Run an evaluation` — the concept of one command producing a scored run.
   - `Which RAG metrics should I use?` — generator metrics (`Answer Relevancy`, `Faithfulness`) vs retriever metrics (`Contextual Relevancy`, `Contextual Precision`, `Contextual Recall`).
   - Day 14 mapping: this is the shape for a local ProcureRAG regression command, even if the first version stays deterministic and framework calls remain optional.

2. **DeepEval — `Faithfulness`**
   URL: `https://deepeval.com/docs/metrics-faithfulness`
   Read sections:
   - Overview — faithfulness checks whether `actual_output` aligns with `retrieval_context`.
   - `Required Arguments` — `input`, `actual_output`, `retrieval_context`.
   - Day 14 caveat: Q091 already proved high faithfulness can coexist with missing primary context; do not use faithfulness as the only verdict.

3. **DeepEval — `Answer Relevancy`**
   URL: `https://deepeval.com/docs/metrics-answer-relevancy`
   Read sections:
   - Overview — whether `actual_output` addresses `input`.
   - `Required Arguments` — `input`, `actual_output`.
   - Caveat — relevant answers can still be unsupported, incomplete, or retrieval-starved.

4. **DeepEval — `Contextual Recall`**
   URL: `https://deepeval.com/docs/metrics-contextual-recall`
   Read sections:
   - Overview / `What Contextual Recall Measures` — whether `retrieval_context` contains what `expected_output` needs.
   - `Required Test Case Arguments` — `input`, `actual_output`, `expected_output`, `retrieval_context`.
   - Day 14 caveat: Day 13 live runs showed contextual recall is useful but variable and still softer than deterministic doc-id/chunk-id gates.

5. **DeepEval — `Contextual Precision`**
   URL: `https://deepeval.com/docs/metrics-contextual-precision`
   Read sections:
   - Overview — whether relevant chunks rank above irrelevant chunks.
   - `Required Test Case Arguments` — `input`, `actual_output`, `expected_output`, `retrieval_context`.
   - Day 14 mapping: useful for future reranker/regression comparisons, but today's deterministic suite should still preserve P@1/R@5/MRR@10/nDCG@5 and explicit primary-doc coverage.

### RAGAS docs — parity / future metric path

1. **RAGAS — `Metrics` reference**
   URL: `https://docs.ragas.io/en/latest/references/metrics`
   Read sections:
   - `Available Metrics` → `Retrieval Augmented Generation`.
   - `Context Precision`, `Context Recall`, `Response Relevancy`, `Faithfulness` names and required-column concept.
   - Day 14 mapping: record why RAGAS is a future or optional live path, not required for the CI-safe command.

2. **RAGAS — `Context Recall`**
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/context_recall/`
   Read sections:
   - `Overview` — not missing relevant documents or information.
   - `LLM-Based Context Recall` — reference claims checked against retrieved context.
   - `Non-LLM Context Recall` / `ID-Based Context Recall` if visible — strongest conceptual match to ProcureRAG's stable `doc_id`/`chunk_id` ground truth.

3. **RAGAS — `Faithfulness`**
   URL: `https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/`
   Read sections:
   - Overview — claims in `response` should be supported by `retrieved_contexts`.
   - Calculation steps — statement extraction, support checking, score.
   - Day 14 caveat: same structural limitation as DeepEval faithfulness for retrieval-starved cases.

### Langfuse docs — optional trace/evidence path only

Read these only after the local suite shape is clear:

1. **Langfuse — `Evaluation Overview`**
   URL: `https://langfuse.com/docs/evaluation/overview`
   Read sections:
   - `Getting Started` — online vs offline evaluation.
   - Feature table rows for `Datasets`, `Experiments`, `Code Evaluators`, `Scores via API/SDK`, and `CI/CD experiments`.
   - Day 14 mapping: Langfuse is optional; do not let SaaS setup block the repeatable local suite.

2. **Langfuse — `LLM Evaluation Concepts`**
   URL: `https://langfuse.com/docs/evaluation/core-concepts`
   Read sections:
   - `Trace`, `Score`, `Dataset`, `Experiment`, `Evaluator` vocabulary.
   - `Evaluation Methods` table — especially `Code evaluators` for deterministic checks and `Scores via API/SDK` for custom pipelines.

3. **Langfuse — `LLM Evaluation Scores`**
   URL: `https://langfuse.com/docs/evaluation/scores/overview`
   Read sections:
   - Scores as the universal object for evaluation results.
   - Score types and comments.
   - Attaching scores to traces / observations / sessions / dataset runs.

4. **Langfuse — `LLM-as-a-Judge`**
   URL: `https://langfuse.com/docs/scores/model-based-evals`
   Read sections:
   - Observations vs traces vs experiments.
   - `Why target Experiments` — reproducible controlled test datasets.
   - Day 14 mapping: if tracing is attempted, local JSONL is acceptable; Langfuse is stretch, not mandatory.

## Day 14 objective

Package the Week 3 generation-eval work into a **repeatable regression suite** before making the next retrieval repair. By the end of the day, Juan should have one CI-safe command that runs curated generation-eval cases, prints a readable table, and records enough evidence that Q001/Q004 controls, Q091/Q093 multi-doc failures, Q016 chunk-level gap, and citation/refusal edge cases can be compared across future retrieval/prompt/model changes.

The route reconciles HER-281 with the latest Day 13 evidence: Day 13's `### Next step` says the next technical repair is the Q091/Q093 multi-doc top-k/diversity experiment. Day 14 should first make that experiment auditable. A repair is only credible if the suite can show which signal moved and which controls did not regress.

## Starting state

The repo currently has:

- `src/generation.py` — source-cited answer generation, prompt construction, citation validation, empty-context refusal, and optional OpenRouter live client.
- `src/generation_eval.py` — deterministic generated-answer checks: citation validity, document-level context recall, expected terms, unsupported-inference phrase flags, and curated Q001/Q091 fixtures.
- `src/framework_eval.py` — DeepEval/RAGAS bridge, faithfulness runners, and Day 13 DeepEval contextual-recall runner with live/skipped/blocked/error result contract.
- `src/error_analysis.py` — Day 13 five-case taxonomy and case-record contract over Q001, Q091, Q093, Q016, and Q004.
- `tests/test_generation_eval.py`, `tests/test_framework_eval.py`, `tests/test_error_analysis.py` — deterministic tests for the eval layers; no standard test path should require a live API key.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query source; do not create a duplicate `data/golden_queries.jsonl`.
- `docs/eval-report.md` — retrieval, generation, deterministic answer-eval, framework-eval, and Day 13 error-analysis evidence.
- `docs/learning-log.md` — Day 13's next step points to implementing and verifying the multi-doc repair, ahead of adding RAGAS ID-based context recall or moving into Chapter 11 Agentic.

Baseline checks at Day 14 kickoff:

```bash
./.venv/bin/pytest -q
# 177 passed in 4.38s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

Current facts to carry forward:

- Q001 and Q004 are passing controls that should stay clean.
- Q091 is the anchor `retrieval_miss`: `POL-001` and `GUIDE-002` are missing from the generation context.
- Q093 is a second `retrieval_miss`: `CONTRACT-001` is missing, causing a falsely universal deadband answer.
- Q016 is a `chunk_level_retrieval_gap`: document-level recall passes, but the specific `GUIDE-001` chunk carrying the logistics ≤40% fact is missing.
- Day 13 recommended the first repair as multi-doc generation-context depth (`top_k` 5 → 8–10), optionally paired with a per-document diversity cap in the pre-rerank chunk shortlist.
- Framework/live judge scores are useful evidence samples, not stable golden outputs. Deterministic doc-id/chunk-id checks own the regression verdict.

## Key concepts to nail today

### A regression suite is a contract, not a demo transcript

A demo transcript proves one run happened. A regression suite defines cases, expected behavior, deterministic verdicts, optional live verdicts, and a stable output shape so future changes can be compared against the same yardstick. Day 14 should produce the yardstick.

For ProcureRAG, the suite should answer: if Juan changes retrieval depth, source diversity, prompt wording, judge model, or provider, which cases improved, which got worse, and which live-only evidence is too variable to treat as a hard gate?

### Separate CI-safe checks from live evidence

The suite needs two lanes:

1. **CI-safe deterministic lane** — no network, no live provider, no API key. This lane should be safe to run under `pytest` and as a script. It should include fixture-backed cases, citation validity, context recall, expected terms where curated, taxonomy label / missing-doc checks, and a readable table.
2. **Optional live lane** — live answer generation, DeepEval/RAGAS metrics, or Langfuse/JSONL trace capture. This lane must record timestamp, model, temperature/token budget, timeout, provider/key status, and clear `skipped`/`blocked`/`ok`/`error` statuses.

Do not let the live lane block the deterministic suite. A portfolio reviewer should be able to clone the repo and run the CI-safe command even without OpenRouter or Langfuse credentials.

### The suite should protect the Day 13 repair signal

The immediate future repair is multi-doc retrieval/context construction. The regression suite therefore needs to preserve the signal Day 13 named:

- Q091/Q093 should report missing primary docs before the repair and empty missing-primary-doc lists after a successful repair.
- Q016 should make chunk/fact-level coverage visible instead of hiding behind document-level pass.
- Q001/Q004 should stay passing controls after any top-k or diversity change.

A prompt-only improvement that makes answers read better but leaves missing primary evidence unchanged should not be counted as a retrieval repair.

### Trace evidence can be local first

Langfuse is useful vocabulary and a future observability path, but Day 14 does not require SaaS setup. A local JSONL trace artifact can be enough if it records the right fields:

```text
run_id
timestamp
mode: deterministic | live
query_id / query_type / difficulty
retrieval_config: top_k, reranker, diversity cap, filters
retrieved_doc_ids / chunk_ids / ranks
answer_text or answer_hash for live runs
deterministic_findings
framework_results, if run
root_cause_label / verdict
model/provider settings, if live
```

If local JSONL is chosen, either document whether it is committed sample evidence or ignored runtime evidence. Do not leave ambiguous generated artifacts in the repo.

## Target evidence by end of day

- [ ] Exact docs-reading notes record the DeepEval/RAGAS/Langfuse sections above, not a vague “read eval docs” checkbox.
- [ ] Juan defines the regression-case contract before coding: query id, case role, expected deterministic checks, optional framework checks, expected verdict, and why the case exists.
- [ ] One command runs the curated generation-eval regression suite and prints a readable table.
- [ ] The suite includes at minimum:
  - [ ] a passing easy/single-source control (Q001);
  - [ ] a passing non-multi-doc control (Q004);
  - [ ] a hard multi-doc missing-document case (Q091);
  - [ ] a second multi-doc / conflicting-scope missing-document case (Q093);
  - [ ] a chunk/fact-level gap case (Q016);
  - [ ] a citation-orphan negative case, synthetic is acceptable if clearly labeled;
  - [ ] an insufficient-evidence / empty-context refusal case, synthetic or existing fixture acceptable if clearly labeled.
- [ ] The output separates CI-safe deterministic verdicts from optional live-provider / judge-provider results.
- [ ] If a live path is run, every result records timestamp, provider/model, temperature, token/output budget, timeout, and `skipped`/`blocked`/`ok`/`error` status.
- [ ] If trace capture is added, the trace schema is documented local JSONL evidence is committed intentionally.
- [ ] `docs/eval-report.md` gets a Week 3 generation-eval regression table: case id, role, expected behavior, retrieval status, generation status, deterministic checks, framework/judge status, verdict, caveat.
- [ ] `docs/learning-log.md` Day 14 entry is filled with real evidence and the remaining weakness before HER-268 gate review.

## Recommended 6-hour split

### Block 0 — Reactivate baseline and Day 13 repair signal, 25–35m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/error_analysis.py
```

Then reread:

- `docs/eval-report.md` — Day 13 section, especially “The five cases,” “DeepEval contextual recall,” and “Recommended Q091 / multi-doc repair path.”
- `docs/learning-log.md` — Day 13 “What remains weak” and “Next step.”
- `src/generation_eval.py` — finding contract and Q001/Q091 fixtures.
- `src/error_analysis.py` — case record shape and five-case taxonomy.
- `src/framework_eval.py` — live/skipped/blocked/error result contract.

Answer from memory:

1. Which case is the document-level retrieval miss anchor?
2. Which case proves document-level context recall can pass while fact-level recall fails?
3. Which cases must stay passing controls after a multi-doc top-k/diversity change?

### Block 1 — Focused reading, 45–75m

Read the companion docs listed above and capture a compact table:

| Source | What it contributes to Day 14 | Required fields / objects | ProcureRAG mapping | Caveat |
|---|---|---|---|---|
| DeepEval RAG quickstart | one-command eval run vocabulary | dataset/test cases + metrics | local regression command | framework not required for deterministic lane |
| DeepEval Faithfulness | generator support against retrieved context | `input`, `actual_output`, `retrieval_context` | Q001/Q091 existing live judge path | can pass retrieval-starved answers |
| DeepEval Contextual Recall | retrieved context vs expected output | `input`, `actual_output`, `expected_output`, `retrieval_context` | Q001/Q091 calibration | live judge variable; doc-id gate remains stronger |
| RAGAS Context Recall / Faithfulness | parity metric vocabulary | required columns / samples | future optional lane | do not add all metrics before suite contract |
| Langfuse Scores / Experiments | trace/score vocabulary | trace, score, dataset, experiment | optional local JSONL or future SaaS | stretch; not mandatory today |

Do not install or configure Langfuse in this block.

### Block 2 — Design the regression contract, 45–60m

Before coding, write down the case contract. Suggested fields:

```text
case_id
query_id
case_role: passing_control | retrieval_miss | chunk_gap | citation_negative | refusal_negative
query_type / difficulty
expected_primary_doc_ids
expected_missing_doc_ids_before_repair
expected_chunk_gap, if applicable
source_fixture_kind: committed_fixture | synthetic_negative | live_capture
ci_safe_checks
optional_live_checks
expected_verdict_before_repair
expected_verdict_after_repair, if this case is a repair target
notes
```

Minimum case roles:

1. `passing_control` — Q001.
2. `passing_control` — Q004.
3. `retrieval_miss` — Q091, missing `POL-001` and `GUIDE-002` before repair.
4. `retrieval_miss` — Q093, missing `CONTRACT-001` before repair.
5. `chunk_gap` — Q016, document-level pass but fact/chunk-level miss.
6. `citation_negative` — an answer that cites `[99]` or another absent source id; can be synthetic because this is a validator boundary test.
7. `refusal_negative` — empty/no-context answer should refuse rather than invent; can reuse `generation.py` behavior or a small fixture.

### Block 3A — Primary route: Juan-owned regression suite, 2–2.5h

Recommended files Juan may create or modify when ready:

- `src/generation_eval.py` or an adjacent small module — to add the regression runner / case list / table printer.
- `src/error_analysis.py` — only if reusing the Day 13 case records directly is the cleanest path.
- `src/framework_eval.py` — only if adding optional live framework columns to the suite; keep `live=False` as the default.
- `tests/test_generation_eval.py`, `tests/test_error_analysis.py`, or a new deterministic test — to make the case contract and output shape hard to regress.
- `docs/eval-report.md` — Day 14 Week 3 generation-eval regression table and command output.
- `docs/learning-log.md` — Day 14 evidence after building.

Suggested implementation steps, not mandatory exact structure:

1. Start with a pure data case list over the known fixtures and synthetic negatives.
2. Add a function that evaluates one case into a small result dict. Prefer reusing `evaluate_generated_answer`, `build_cases`, and `build_framework_eval_case` over duplicating checks.
3. Add a table printer that outputs one row per case with: `case_id`, `query_id`, `role`, `deterministic_verdict`, `missing_docs`, `citation_status`, `chunk_gap_or_notes`, `live_status`, `overall_verdict`.
4. Make the default command CI-safe: no provider call, no Langfuse call, no requirement for `OPENROUTER_API_KEY`.
5. If adding optional live support, require an explicit flag such as `--live` and preserve the `skipped` / `blocked` / `ok` / `error` result shape.
6. If adding trace capture, start with local JSONL and a documented schema. Sample trace evidence belongs under docs/ .
7. Update `docs/eval-report.md` with the command, current table output, known hard failures, and which failures are expected before the Q091/Q093 repair.
8. Fill in the learning-log Day 14 entry.

A plausible command target is the one already named in HER-281:

```bash
./.venv/bin/python src/generation_eval.py --regression-suite
```

If Juan chooses a separate module instead, record the actual command in `docs/eval-report.md` and in the learning log. The important part is one repeatable command, not this exact filename.

### Block 3B — Stretch route: run the first repair experiment after the suite exists, 60–90m

Only do this after the regression command exists.

Experiment target from Day 13:

- Increase generation-context depth for `multi_doc` queries from 5 to 8–10 sources.
- Optionally add a per-document diversity cap to the pre-rerank chunk shortlist so Q093-like questions do not spend multiple slots on the same document while missing another primary document.

Verification signal:

- Q091: `missing_primary_doc_ids` moves from `['GUIDE-002', 'POL-001']` to `[]`.
- Q093: `missing_primary_doc_ids` moves from `['CONTRACT-001']` to `[]`.
- Q001 and Q004 still pass every deterministic check.
- Q016's chunk-level gap is either explicitly still open or addressed by a chunk/fact-level coverage signal; do not hide it behind document-level pass.

If this repair is too much for Day 14, leave it as the next step. Do not rush the repair before the regression harness can measure it.

### Block 3C — Fallback route: docs-first suite contract + deterministic tests, 60–90m

Use this if table printing or trace capture takes longer than expected.

Still produce evidence:

1. A documented regression case table in `docs/eval-report.md` with the seven minimum cases.
2. A test or fixture contract that makes the case list shape explicit.
3. A clear statement that the executable `--regression-suite` command is not yet finished and exactly what remains.
4. No fake live scores and no invented trace output.

The non-negotiable Day 14 output is a repeatable eval contract; live observability is optional.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. Why is a regression suite different from a demo transcript?

   **Expected answer shape:** A transcript proves one run happened. A regression suite defines stable cases, expected checks, command output, and pass/fail or expected-failure semantics so changes can be compared over time.

2. Why should ProcureRAG separate deterministic checks from live judge scores?

   **Expected answer shape:** Deterministic checks are cheap, reproducible, CI-safe, and exact over known ids/facts. Live judges add semantic judgment but can vary by provider, model, prompt, and run; they are evidence samples, not hard gates unless calibrated and bounded.

3. What does Q091 test that Q001 does not?

   **Expected answer shape:** Q001 is a passing control where the needed evidence reaches context. Q091 tests a retrieval-starved multi-doc answer: citations can be valid and faithfulness can pass, while required primary docs (`POL-001`, `GUIDE-002`) are absent.

4. Why does Q016 need a chunk-level/fact-level signal?

   **Expected answer shape:** Document-level recall passes because `GUIDE-001` appears, but the specific chunk with the logistics ≤40% fact does not. A doc-id-only check can falsely reassure; the missing fact is still a retrieval/context gap.

5. What would prove the Q091/Q093 repair helped?

   **Expected answer shape:** The regression suite shows missing primary docs become empty for Q091 and Q093, controls Q001/Q004 remain passing, citation checks remain clean, and optional live answer/judge evidence agrees or is documented as variable.

6. Why is Langfuse optional today?

   **Expected answer shape:** Observability is useful, but the project first needs a local, reproducible, credential-free regression suite. A local JSONL trace with the right schema can be enough; SaaS tracing should not derail the core eval contract.

## Hermes review protocol

When Juan has a serious Day 14 attempt ready, ask Hermes:

> Review my Day 14 ProcureRAG eval regression suite and trace evidence. Check the exact docs-reading evidence, regression case contract, one-command CI-safe runner, minimum case coverage (Q001, Q004, Q091, Q093, Q016, citation negative, refusal negative), deterministic vs live result separation, eval-report table, trace schema/evidence decision, tests/compile/lint output, and whether any Q091/Q093 repair claim is supported by missing-doc signals rather than just better prose. Do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan's implementation.

## Stop condition

Day 14 is complete when the Week 3 eval loop is operationally repeatable:

1. Exact companion reading notes are recorded.
2. A regression-case contract exists and covers passing controls, known hard failures, and negative validator/refusal cases.
3. One command runs the CI-safe curated suite and prints a readable table.
4. The suite clearly separates deterministic checks from optional live judge/provider checks.
5. `docs/eval-report.md` contains the Day 14 Week 3 generation-eval regression table and command output.
6. Any trace capture has a documented schema and a clear committed-vs-runtime artifact decision.
7. If a Q091/Q093 repair is attempted, it is verified by missing-doc signals and control-case non-regression, not by subjective answer prose alone.
8. Baseline gates pass: `pytest`, `compileall`, and `ruff`.
9. Juan can explain how this suite would be used before changing retrieval, prompt wording, or model provider.

Do not close HER-281 on route creation alone. The route is the kickoff; Juan's regression suite, evidence table, and interview explanation are the acceptance criteria.
