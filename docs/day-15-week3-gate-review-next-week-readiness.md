# Day 15 — Week 3 Gate Review + Next-Week Readiness

Date: 2026-09-21 kickoff.

Linear: HER-282 — Day 15 loop: Week 3 gate review + next-week readiness.

Related gate: HER-268 — Week 3 gate: grounded generation + RAG eval harness.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

Boot.dev RAG course target:

- **No new Boot.dev chapter is required before the gate review.** Day 15 is a consolidation / gate-readiness day for Week 3.
- **Chapter 10 — Augmented Generation, completed and used as the Week 3 baseline:**
  1. **Augmented Generation** — retrieve context, augment the model input, generate from that context.
  2. **LLM Summarization** — synthesize retrieved snippets into coherent output.
  3. **Conflict Resolution in Summaries** — avoid merging differently scoped evidence into one unsupported claim.
  4. **Adding Citations** — attach claims to traceable source ids.
  5. **Question Answering** — answer the buyer's question directly while staying inside retrieved evidence.
- **Chapter 11 — Agentic is preview-only today, and only after HER-268 is clean.** Verified Boot.dev Chapter 11 lesson names:
  1. **Recursive RAG**
  2. **Agentic Search**

Companion sources to reactivate selectively:

- DeepEval / RAGAS metric vocabulary from Days 12–14: faithfulness, answer relevancy, contextual recall, contextual precision, and ID-based context recall.
- Langfuse evaluation vocabulary from Day 14: dataset, experiment, code evaluator, score, trace.
- Week 4 alignment from `docs/study-plan-linear-alignment-2026-09-09.md`: after Week 3 closes, move toward LangGraph / agentic workflows, observability, guardrails, structured outputs, and interview drills.

## Day 15 objective

Turn the Week 3 grounded-generation work into a gate-ready portfolio story. The target is not to add a flashy new agent. The target is to prove that ProcureRAG now has a source-cited answer path, deterministic generation-eval checks, an optional live judge lane, real error analysis, and a regression suite that caught and verified the Q091/Q093/Q016 retrieval repair.

Day 14's `### Next step` says Week 3 can close, but it also names one responsible check before treating the Day 14 multi-doc repair as a general improvement: re-measure `MULTI_DOC_RETRIEVAL_CONFIG` against the full `multi_doc` slice, not only Q091/Q093/Q016. Day 15 should make that final gate evidence explicit and prepare the clean handoff into Week 4 / Chapter 11.

## Starting state

The repo currently has:

- `src/generation.py` — source-cited generation, prompt construction, citation validation, empty-context refusal, and optional OpenRouter live client. Its real entry point now uses `retrieval_config_for_query_type`, so `multi_doc` queries get the repaired deeper/diverse config.
- `src/generation_eval.py` — deterministic generated-answer checks: citation validity, document-level context recall, expected terms, unsupported-inference phrase flags, and curated Q001/Q091 fixtures.
- `src/framework_eval.py` — DeepEval/RAGAS bridge with explicit live/skipped/blocked/error result contracts.
- `src/error_analysis.py` — Day 13 five-case taxonomy over Q001, Q091, Q093, Q016, and Q004; deliberately preserves frozen pre-repair evidence.
- `src/regression_suite.py` — Day 14 fixture regression suite with deterministic, optional live, and current-pipeline retrieval verification lanes.
- `src/reranking.py` — `DEFAULT_RETRIEVAL_CONFIG` and `MULTI_DOC_RETRIEVAL_CONFIG` (`pool_size=80`, `top_k=10`, `max_chunks_per_document=2`), selected through `retrieval_config_for_query_type(query_type)`.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query source; do not create a duplicate `data/golden_queries.jsonl`.
- `docs/eval-report.md` — retrieval, generation, deterministic answer-eval, framework-eval, error-analysis, regression-suite, and Day 14 repair evidence.
- `docs/learning-log.md` — Day 14 evidence says the regression suite and targeted repair are green; the remaining check is full `multi_doc` slice remeasurement before moving into Chapter 11 Agentic.

Baseline checks at Day 15 kickoff:

```bash
./.venv/bin/pytest -q
# 206 passed in 3.05s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# 7/7 frozen cases as_expected; current retrieval verification OK for 6 checked retrieval cases
```

Current facts to carry forward:

- Q091/Q093 document-level missing-doc failures were repaired by the `multi_doc` config, not by prompt prose.
- Q016's `GUIDE-001::chunk-2` fact-level gap is now a computed required-chunk check.
- Q091 still has a visible term-level gap: `Band 3` is missing from the answer text because the repaired retrieval reaches a useful `POL-001` chunk, but not the exact threshold chunk. This is visible via `expected_missing_terms`, not hidden behind `as_expected`.
- The full `multi_doc` slice is exactly: Q005, Q016, Q091, Q092, Q093.
- The Day 14 targeted repair was verified on Q016/Q091/Q093; Day 15 should check Q005 and Q092 too before calling the `multi_doc` config broadly safe.

## Key concepts to nail today

### A gate review is a narrative with evidence, not just green tests

Green tests say the code still runs. A portfolio gate says the repo now tells a coherent story: retrieval foundations produced a measurable baseline; reranking improved top-rank precision but exposed multi-doc weakness; generation made answers user-facing but could not compensate for missing evidence; evals caught that distinction; error analysis turned it into a repair plan; the regression suite made the repair measurable.

Day 15 should make that story explicit in `docs/eval-report.md` and `docs/learning-log.md`, using command output and case names instead of vague claims.

### `multi_doc` repair needs slice-level evidence

Day 14 fixed Q091/Q093/Q016, but the corpus has five `multi_doc` queries: Q005, Q016, Q091, Q092, Q093. Before Week 3 closes, Juan should compare default vs repaired retrieval config over all five. The check should answer:

1. Did the repair keep the known wins for Q016/Q091/Q093?
2. Did it help, hurt, or leave Q005/Q092 unchanged?
3. Did it change P@1/R@5/MRR@10/nDCG@5 or missing-primary-doc / missing-chunk signals in a way worth documenting?
4. Is the config still scoped to `query_type == "multi_doc"`, so controls like Q001/Q004 retain the original retrieval behavior?

The honest outcome may be mixed. A portfolio-ready report does not need to claim the config is universally better; it needs to state exactly what moved and what remains caveated.

### Faithfulness, recall, and answer completeness are different axes

Q091 is the interview anchor. Faithfulness can be high when an answer is honest about incomplete context. Context recall catches whether primary docs arrived. Expected-term checks catch whether the generated answer actually says the needed fact. Required-chunk checks catch whether the fact-bearing chunk reached the prompt.

The strongest Week 3 story is that ProcureRAG now measures these layers separately instead of pretending one metric owns the whole RAG quality story.

### Agentic work starts after the gate, not before it

Boot.dev Chapter 11's **Recursive RAG** and **Agentic Search** naturally follow this week: an agent can decide to reformulate, retrieve again, or decompose a multi-part query. But Day 15's job is to decide what the first agentic loop should improve, based on Week 3 evidence. If Q091 still has a `Band 3` term-level gap, a future agentic path should be motivated by that concrete failure, not by “agents” as a buzzword.

## Target evidence by end of day

- [ ] Full gate commands run and logged:
  - [ ] `./.venv/bin/pytest -q`
  - [ ] `./.venv/bin/python -m compileall -q src tests`
  - [ ] `./.venv/bin/python -m ruff check src tests`
  - [ ] `./.venv/bin/python src/regression_suite.py`
  - [ ] `./.venv/bin/python src/regression_suite.py --verify-retrieval`
  - [ ] `./.venv/bin/python src/eval_metrics.py`
  - [ ] optional live: `./.venv/bin/python src/regression_suite.py --live`
  - [ ] optional live smoke: `./.venv/bin/python src/generation.py`
- [ ] `docs/eval-report.md` has a Day 15 gate-review addendum that summarizes Week 3 acceptance criteria against real artifacts.
- [ ] The full `multi_doc` slice (Q005/Q016/Q091/Q092/Q093) is measured under default vs repaired config, or a precise blocker is recorded.
- [ ] Q091's residual `Band 3` term-level gap is named with owner, impact, and possible next repair signal.
- [ ] `docs/learning-log.md` Day 15 entry is filled with gate verdict, verification outputs, full-slice findings, interview explanation, and next Week 4 step.
- [ ] No TODO placeholders remain for completed Week 3 evidence.
- [ ] Hermes can review HER-268 and either close the Week 3 gate or list exact remaining tasks.

## Recommended 6-hour split

### Block 0 — Reactivate baseline and scope, 25–35m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
./.venv/bin/python src/regression_suite.py
./.venv/bin/python src/regression_suite.py --verify-retrieval
```

Then reread:

- `docs/learning-log.md` — Day 14 "Next step" and review-feedback fixes.
- `docs/eval-report.md` — Day 14 Block 3B and code-review fixes.
- `src/reranking.py` — `DEFAULT_RETRIEVAL_CONFIG`, `MULTI_DOC_RETRIEVAL_CONFIG`, and `retrieval_config_for_query_type`.
- `src/regression_suite.py` — current case expectations, especially Q091 expected missing terms and `--verify-retrieval`.
- `src/generation.py` — confirm the real generation entry point uses query-type config.

Answer from memory:

1. Which part of Q091 is fixed, and which part is still open?
2. Why is `as_expected` not the same thing as "every check passed"?
3. Why is the repaired config scoped only to `multi_doc`?

### Block 1 — Gate inventory, 45–60m

Create a compact artifact inventory in notes before editing docs:

| Gate criterion | Evidence artifact | Command / file | Pass? | Caveat |
|---|---|---|---|---|
| Grounded generation path exists | `src/generation.py`, tests | `pytest`, `src/generation.py` optional smoke | TODO | TODO |
| 2+ code-based evals | `generation_eval.py`, `regression_suite.py`, tests | `pytest`, `src/regression_suite.py` | TODO | TODO |
| 1 LLM-as-judge eval | `framework_eval.py`, `--live` optional lane | `src/regression_suite.py --live` if run | TODO | live variability caveat |
| Error analysis | `error_analysis.py`, Day 13/14 report | docs + tests | TODO | frozen pre-repair vs current repaired state must stay distinct |
| Regression failure mode | Q091/Q093/Q016 suite cases | `--verify-retrieval` | TODO | Q091 `Band 3` term-level gap remains open |
| Interview explanation | learning-log Day 15 | self-quiz | TODO | TODO |

Do not close HER-268 if any row is still hand-wavy.

### Block 2 — Full `multi_doc` slice remeasurement, 60–90m

Before adding new code, decide the smallest honest measurement path. Acceptable routes:

1. **Preferred:** extend the existing eval/report path in a Juan-owned way so the full `multi_doc` slice can be reproduced with one command or a clearly documented command snippet.
2. **Fallback:** use a temporary notebook/scratch command to calculate the table, then record the exact command and output in `docs/eval-report.md` without committing scratch code.
3. **Blocked:** if model loading/provider/runtime blocks the measurement, record the blocker and do not claim broad config safety.

Minimum table:

| Query | Default config evidence | Repaired config evidence | Verdict |
|---|---|---|---|
| Q005 | TODO | TODO | TODO |
| Q016 | TODO | TODO | chunk gap should remain addressed |
| Q091 | TODO | TODO | missing docs fixed; `Band 3` term gap still visible |
| Q092 | TODO | TODO | TODO |
| Q093 | TODO | TODO | missing `CONTRACT-001` should remain fixed |

Useful fields: top retrieved doc ids, top retrieved chunk ids, missing primary doc ids, missing required chunk ids where defined, P@1/R@5/MRR@10/nDCG@5 if easy to compute, and any query where the repaired config worsens top-rank quality.

### Block 3A — Primary route: update gate evidence, 90–120m

Recommended files Juan may update after measurement:

- `docs/eval-report.md` — add a Day 15 Week 3 gate-review section with the artifact inventory, full `multi_doc` slice result, and HER-268 acceptance check.
- `docs/learning-log.md` — fill the Day 15 entry with real commands and explanation.
- Optional Juan-owned code/tests only if the measurement needs to become a permanent command.

Suggested structure for the Day 15 report addendum:

1. **Gate verdict:** pass / not yet, with one sentence.
2. **Verification outputs:** exact command outputs, not paraphrase.
3. **Artifact inventory:** generation, deterministic eval, framework/live eval, error analysis, regression suite, current-pipeline verification.
4. **Full multi-doc slice:** default vs repaired config table.
5. **Remaining weakness:** Q091 `Band 3` term/chunk gap and what signal would close it.
6. **Week 4 handoff:** what Chapter 11 / agentic loop should try first and what it must not obscure.

### Block 3B — Fallback route: gate-readiness without new measurement code, 45–75m

Use this if full-slice remeasurement takes longer than expected.

Still produce:

1. A gate inventory with every artifact and command that already exists.
2. A clear statement that the full `multi_doc` slice remains unmeasured, with Q005/Q092 named explicitly.
3. A precise next task for the measurement before broad claims about `MULTI_DOC_RETRIEVAL_CONFIG`.
4. No fake metrics and no invented live-judge output.

This fallback can still be useful, but it should not close HER-268 as broadly as a measured full-slice pass would.

### Block 4 — Interview drill + Week 4 handoff, 45–60m

Answer without notes:

1. Why is Q091 the best single story for Week 3?

   **Expected answer shape:** It shows every RAG layer separately: retrieval missed primary docs, generation could still cite honestly, faithfulness could pass despite incomplete context, context recall caught missing docs, expected terms caught a residual answer gap, and the regression suite made the repair measurable.

2. What does `MULTI_DOC_RETRIEVAL_CONFIG` change, and why only for `multi_doc`?

   **Expected answer shape:** It uses deeper first-stage pools, more generation context, and a per-document cap to surface multiple primary documents instead of redundant chunks from the same few docs. It stays scoped to `multi_doc` because easy/lookup/threshold controls already work under the default config and widening globally risks unnecessary noise.

3. Why is faithfulness not enough to close a RAG gate?

   **Expected answer shape:** Faithfulness checks whether the answer is supported by retrieved context. It does not know whether the retrieved context omitted a primary source. A faithful answer can still be incomplete.

4. What would prove the remaining Q091 `Band 3` weakness is fixed?

   **Expected answer shape:** Either the exact `POL-001` threshold chunk reaches context and the answer includes `Band 3`, or a deliberate answer policy says the band remains unstated because the exact threshold chunk is absent. The suite must show the missing-term/chunk signal changing, not just a nicer answer.

5. Why should Chapter 11 Agentic start from evidence, not framework enthusiasm?

   **Expected answer shape:** Agents add control flow — reformulation, recursive retrieval, tool choice — but they should be motivated by a concrete failure. For ProcureRAG, the current candidate is a multi-hop/multi-doc gap like Q091 where a second retrieval pass might ask specifically for approval-band thresholds after first-pass context is incomplete.

6. What should HER-268 closure say if the gate passes?

   **Expected answer shape:** It should list real command outputs, artifacts, review-caught issues/fixes, known non-blocking caveats, interview-readiness summary, and the next weakness going into Week 4.

## Hermes review protocol

When Juan has a serious Day 15 gate pass ready, ask Hermes:

> Week 3 gate review ready. Review Day 15 ProcureRAG evidence for HER-282 / HER-268: full verification commands, eval-report Day 15 addendum, learning-log Day 15 entry, full multi_doc slice remeasurement over Q005/Q016/Q091/Q092/Q093, Q091 Band 3 residual handling, deterministic vs live eval separation, and Week 4 Chapter 11 readiness. Do not rewrite implementation code for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, verify the evidence, and either close HER-268/HER-282 or return precise remaining tasks. Hermes must not replace Juan's implementation.

## Stop condition

Day 15 is complete when Week 3 is honestly gate-reviewable:

1. The full verification gates are green or any blocker is explicitly named.
2. `docs/eval-report.md` and `docs/learning-log.md` tell a coherent Week 3 story with real command output.
3. The full `multi_doc` slice has been measured under the repaired config, or the lack of measurement is recorded as the reason not to make broad claims.
4. Q091's residual `Band 3` term-level gap is visible, not hidden behind a green summary.
5. Juan can explain faithfulness vs context recall vs answer completeness vs chunk/fact coverage.
6. HER-268 is ready for closure review, or the exact remaining task list is short enough to execute next.
7. Chapter 11 Agentic has a concrete first target only after the Week 3 gate is clean.

Do not close HER-282 on route creation alone. The route is the kickoff; Juan's gate evidence, full-slice measurement, and interview explanation are the acceptance criteria.
