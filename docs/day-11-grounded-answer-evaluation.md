# Day 11 — Grounded-Answer Evaluation + Completeness Checks

Date: 2026-09-15 target; started 2026-09-15.

Linear: HER-278 — Day 11 loop: groundedness + answer-completeness checks.

Related gate: HER-268 — Week 3 gate: grounded generation + RAG eval harness.

Project rule: course-driven building, with Juan owning the core implementation. Hermes may scaffold docs and review; Juan writes any `src/*.py` and `tests/test_*.py` code.

## Course target for today

Boot.dev RAG course target:

- **No new Boot.dev chapter is required today.** Day 11 is a bridge/eval day that deepens Chapter 10's source-cited generation work before moving into Chapter 11 Agentic.
- **Chapter 10 — Augmented Generation, exact lessons to reactivate/review:**
  1. **Augmented Generation** — retrieve context, augment the model input, and generate from that context.
  2. **LLM Summarization** — synthesize retrieved snippets into coherent output without dumping context verbatim.
  3. **Conflict Resolution in Summaries** — keep differently scoped or conflicting evidence separate instead of blending it into one unsupported answer.
  4. **Adding Citations** — attach claims to source-backed citations, not decorative bracket numbers.
  5. **Question Answering** — answer the buyer's question directly while staying inside retrieved evidence.
- **Chapter 11 — Agentic is explicitly deferred today.** The public Boot.dev course page labels Chapter 11 as **Agentic** and describes it as deploying autonomous agents that iteratively refine queries and navigate complex retrieval workflows. Do not start that build until Day 11's grounded-answer eval can catch the known Day 10 failure mode.

Companion sources and vocabulary:

- **DeepEval RAG metrics:** contextual relevancy, contextual precision, contextual recall on the retriever side; answer relevancy and faithfulness on the generator side. DeepEval's predefined metrics are mostly LLM-as-judge and return thresholded 0–1 scores with reasoning, so use the vocabulary today without integrating a new framework unless it stays lightweight and deterministic.
- **RAGAS metrics:** context precision, context recall, context entities recall, response relevancy, faithfulness, factual correctness, semantic similarity, and traditional metrics such as string presence/exact match. Treat these as the conceptual map for future framework-backed evals.
- **ProcureRAG Day 10 evidence:** `src/generation.py`, `tests/test_generation.py`, and `docs/eval-report.md` already prove structural citation validity. Today asks whether those citations actually support the answer and whether the answer is complete enough against `expected_answer`.

## Day 11 objective

Turn Day 10's source-cited answer generation into the first deterministic **grounded-answer evaluation layer**. The goal is not to make the answer more fluent or to add an agent. The goal is to catch cases where a generated answer looks clean — valid citations, no orphan source ids, reasonable prose — but is still incomplete or insufficiently supported.

Day 10's Q091 result is the anchor failure: the answer had valid source numbers and no orphan citations, yet it missed key expected evidence because retrieval did not surface `POL-001` and `GUIDE-002`. That is exactly the difference an interviewer will probe: **citation hygiene is necessary, but it is not the same as faithfulness, completeness, or answer correctness.**

By the end of today, Juan should be able to demonstrate and explain:

1. what structural citation validity checks and does not check;
2. how to compare a generated answer against expected procurement evidence;
3. how to flag a missing expected document/claim in a generated answer;
4. why deterministic fixtures are the first eval layer before LLM-as-judge;
5. how DeepEval/RAGAS concepts map to this project's code without adopting them prematurely.

## Starting state

The repo currently has:

- `src/generation.py` — source construction, prompt construction, citation extraction/validation, empty-context refusal, and an optional OpenRouter live client.
- `tests/test_generation.py` — 15 deterministic generation tests with fake clients and no network calls.
- `src/eval_metrics.py` — retrieval metrics, nDCG@5, filtered-adjusted evals, and error slices over the canonical v1 query set.
- `data/corpus_v1/example_queries.jsonl` — canonical 93-query source with `expected_answer`, `expected_relevant_ids`, `relevance_grades`, `metadata_filters`, and evidence quotes.
- `docs/eval-report.md` — Day 7–10 report including the Day 10 generated-answer transcript and the Q091 evidence gap.
- `docs/learning-log.md` — Day 10 leaves Day 11's next step as grounded-answer evaluation before Chapter 11 Agentic.

Baseline checks at Day 11 kickoff:

```bash
./.venv/bin/pytest -q
# 135 passed in 2.44s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!
```

Current facts to carry forward:

- Structural citations are working: `validate_citations` catches orphan source ids and reports uncited sources.
- Structural citations are insufficient: Q091 had zero orphan citations but still missed the real approval-band evidence.
- The strongest overall retrieval row remains cross-encoder reranked Hybrid RRF chunk→document for P@1/MRR@10/nDCG@5, while first-stage Hybrid RRF chunk→document remains slightly better on aggregate R@5.
- The known weak slice remains `multi_doc`: Day 9 found reranked `multi_doc` P@1 at 0.600 over 5 queries, and Day 10 showed the downstream answer-level cost.
- No `src/generation_eval.py` or `tests/test_generation_eval.py` exists yet. Any such implementation is Juan-owned.

## Key concepts to nail today

### Citation validity is not the same as faithfulness

A citation checker can answer: "Did the model cite a source number that exists in the prompt?" It cannot, by itself, answer: "Does the cited source text actually support the sentence next to the citation?" Day 10's `validate_citations` is useful and should be reused, but it is only the first layer.

Today should make that boundary explicit in code and docs. A generated sentence such as "a EUR 120,000 renewal requires VP Procurement approval [3]" can have a valid `[3]` source id while still being only weakly supported or inferred beyond the text if source `[3]` only discusses EUR 60,000. That should be visible as a groundedness/support finding, not hidden behind a green citation check.

### Completeness is different from groundedness

An answer can be faithful to the sources it cites and still incomplete relative to the actual expected answer. Q091 is the example: if the retrieved top-5 omits `POL-001` and `GUIDE-002`, the generator can faithfully summarize the evidence it saw while still failing to mention the full approval band and renewal-timing evidence.

Completeness checks compare the answer and/or cited sources against the query's `expected_answer`, `expected_relevant_ids`, and evidence quotes. For a first deterministic layer, do not overreach into general semantic judgment. A practical Day 11 completeness check can ask: did the generated answer use or acknowledge the expected primary documents for a curated query? Did it include key expected terms/thresholds? Did it flag missing evidence when required primary documents were absent?

### Deterministic evals come before LLM-as-judge

DeepEval and RAGAS are important because they name the right dimensions: faithfulness, answer relevancy, context precision/recall, factual correctness, semantic similarity. But most framework metrics use another LLM as judge, which introduces model choice, prompt drift, cost, latency, and calibration questions.

ProcureRAG's first Day 11 artifact should be deterministic and interview-defensible: curated fixtures, explicit pass/fail findings, and real known failures. Framework-backed evals can come later once the hand-built checks define what "wrong" means on this corpus.

### Good failure reports matter as much as scores

A senior engineer should not accept a single `score=0.67` without diagnosis. The Day 11 eval should print or return useful findings: query id, check name, verdict, missing expected document ids or terms, cited source ids used, orphan citations if any, and a short reason.

The output should help Juan answer: "Was this a retrieval failure, a generation faithfulness failure, an answer completeness failure, or only a citation-format failure?" That diagnosis is the portfolio value.

## Target evidence by end of day

- [ ] Boot.dev Chapter 10 lessons 1–5 are reactivated briefly, with notes focused on evaluation implications rather than rebuilding generation.
- [ ] Juan designs a deterministic generation-eval contract before coding: input shape, fixture shape, check names, and output/finding shape.
- [ ] Juan builds a grounded-answer eval layer, likely `src/generation_eval.py`, that runs without network/API keys.
- [ ] Tests exist, likely `tests/test_generation_eval.py`, with at least one passing fixture and one intentionally failing fixture.
- [ ] Q091-style incomplete answers are caught automatically by at least one check, not only by manual reading.
- [ ] The eval distinguishes at least three concepts: citation validity, source support/faithfulness, and answer completeness.
- [ ] The eval report records what is deterministic today and what still requires human or LLM-as-judge review later.
- [ ] `docs/learning-log.md` has a Day 11 entry with real evidence, confusion, interview explanation, remaining weakness, and next step.

## Recommended 6-hour split

### Block 0 — Reactivate baseline + Day 10 failure, 30–40m

Run:

```bash
./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
```

Then reread:

- `docs/eval-report.md` → Day 10 "Source-cited answer generation" and Q091 discussion.
- `docs/learning-log.md` → Day 10 "What remains weak" and "Next step".
- `src/generation.py` → `validate_citations`, `generate_answer`, and the demo query ids.

Answer from memory:

1. What did `validate_citations` prove on Q091?
   **Expected:** the answer cited only real source numbers and had no orphan citations.
2. What did it not prove?
   **Expected:** whether each cited source actually supported the attached claim, and whether the answer was complete against `expected_answer`.
3. Which missing documents made Q091 incomplete?
   **Expected:** `POL-001` for approval bands and `GUIDE-002` for renewal playbook/timing evidence.
4. Why is this a retrieval-vs-generation boundary?
   **Expected:** the generator can only answer from the sources it receives; missing top-5 evidence is a retrieval/context problem even if the generated prose is faithful to the visible sources.

### Block 1 — Course/framework concept pass, 60–75m

Reactivate Boot.dev Chapter 10 through an evaluation lens:

| Lesson | Day 11 eval implication |
|---|---|
| Augmented Generation | The prompt is only as complete as the retrieved context; eval must inspect both answer and context. |
| LLM Summarization | A coherent summary can omit required facts; completeness checks are needed. |
| Conflict Resolution in Summaries | Differently scoped evidence should be preserved; eval should flag over-merged claims. |
| Adding Citations | Valid source ids are necessary but not enough; support must be checked. |
| Question Answering | Direct answers should be judged for faithfulness, relevance, and completeness. |

Skim companion metric vocab only far enough to map terms:

- DeepEval: faithfulness, answer relevancy, contextual precision/recall/relevancy.
- RAGAS: faithfulness, response relevancy, context precision/recall, factual correctness, semantic similarity, string presence/exact match.

Do not install DeepEval/RAGAS today unless the deterministic route is already done.

### Block 2 — Design the Day 11 artifact contract, 45–60m

Before coding, write the contract in a scratchpad or learning log:

- **Input:** query row from `data/corpus_v1/example_queries.jsonl`; generated answer text; Day 10 `sources`; Day 10 citation report.
- **Fixture shape:** curated examples for Q001 success and Q091 failure; include the answer text, sources/cited ids, and expected finding(s).
- **Check 1 — citation validity:** reuse `validate_citations`; fail on orphan ids.
- **Check 2 — expected document coverage:** compare cited source `doc_id`s or supplied context `doc_id`s against selected `expected_relevant_ids` / primary evidence for curated queries.
- **Check 3 — expected answer terms/evidence:** for curated queries only, assert that key required facts from `expected_answer` or evidence quotes appear or are explicitly flagged missing.
- **Check 4 — unsupported/caveated inference:** flag claims that appear to infer beyond a cited source when the source text does not contain the relevant threshold/role/figure. This can start as fixture-based, not universal NLP.
- **Output:** list of finding dicts such as `query_id`, `check`, `passed`, `severity`, `message`, `expected`, `actual`, `cited_doc_ids`.

Keep the first version simple and inspectable. A small deterministic rule that catches Q091 is better than a broad fake metric that cannot explain itself.

### Block 3A — Primary route: Juan-owned deterministic grounded-answer eval, 2–2.5h

Recommended files Juan may create or modify when ready:

- `src/generation_eval.py` — likely place for fixture loading, check functions, finding formatting, and a small CLI/demo.
- `tests/test_generation_eval.py` — deterministic tests over passing and failing fixtures.
- `docs/eval-report.md` — Day 11 addendum describing methodology, example findings, and limitations.
- `docs/learning-log.md` — Day 11 evidence after building.

Suggested implementation steps, not mandatory exact structure:

1. Load canonical queries with existing helpers or direct JSONL parsing.
2. Define a small `EvaluationFinding` shape or plain dict contract.
3. Reuse `generation.validate_citations` instead of duplicating citation parsing.
4. Create a Q001 passing fixture that proves clean citation + expected key fact coverage.
5. Create a Q091 failing fixture based on Day 10's known incomplete-answer behavior.
6. Add a check that reports missing required evidence/documents rather than only returning `False`.
7. Add tests for each check and one end-to-end fixture evaluation.
8. Add a CLI/demo that prints per-query findings in a human-readable format.
9. Update `docs/eval-report.md` with the real command output and the meaning of each finding.

Do not implement LangGraph agents, MCP, tracing, vector DB migration, a web UI, or a broad LLM-as-judge framework today. Those belong to later gates.

Finally, fill in learning-log questions for Day 11.

### Block 3B — Fallback route: completeness first, claim support later, 60–90m

Use this if claim-level support checking becomes too large for one day.

Still produce evidence:

1. Finish the Chapter 10 eval-concept review.
2. Define the finding/output contract.
3. Implement expected document / expected key-fact completeness checks for Q091 and one passing control query.
4. Document claim-level source-support as the next layer.
5. Record why deterministic completeness is a valid first step and why it is not full faithfulness.

The non-negotiable output is a failing Q091-style fixture. If the known Day 10 failure still only fails by human reading, Day 11 has not landed.

### Block 4 — Interview drill, 45–60m

Answer without notes:

1. Why are valid citations necessary but insufficient?

   **Expected answer shape:** valid citations prove the model cited real source ids from the prompt; they do not prove the cited text supports the attached claim or that the answer includes all required evidence.

2. What is the difference between faithfulness and completeness?

   **Expected answer shape:** faithfulness asks whether the answer's claims are supported by the provided context; completeness asks whether the answer covers the required answer/evidence for the query. An answer can be faithful to incomplete context and still incomplete overall.

3. How did Q091 expose the retrieval/generation boundary?

   **Expected answer shape:** generation produced a cited answer from the top-5 sources it saw, but retrieval omitted `POL-001` and `GUIDE-002`, so the generated answer could not fully state the correct approval-band and renewal-playbook evidence.

4. Why start with deterministic fixtures instead of DeepEval/RAGAS immediately?

   **Expected answer shape:** deterministic fixtures are reproducible, cheap, inspectable, and calibrated to the corpus's known failures. LLM-as-judge frameworks are useful later, but need a rubric and examples first.

5. What should a useful eval finding include?

   **Expected answer shape:** query id, check name, pass/fail/severity, expected evidence or fact, actual cited/context docs, and a reason that separates retrieval miss, unsupported claim, incomplete answer, and citation-format failure.

6. How would you map this project to RAGAS/DeepEval terms later?

   **Expected answer shape:** retrieval rows map to context precision/recall/relevancy; generated answer support maps to faithfulness/groundedness; query-answer match maps to answer/response relevancy; expected-answer coverage maps to factual correctness or semantic similarity, with human-calibrated examples.

## Hermes review protocol

When Juan has a serious Day 11 attempt ready, ask Hermes:

> Review my Day 11 ProcureRAG grounded-answer eval work. Check the Chapter 10 reactivation evidence, deterministic generation-eval contract, Q001/Q091 passing and failing fixtures, tests, CLI/demo output, eval-report update, and whether I can explain citation validity vs. faithfulness vs. answer completeness vs. retrieval-context recall in an AI Engineer interview. Do not rewrite the implementation for me unless I explicitly ask for hints.

Hermes should review, quiz, run gates, and debug by pointing to issues — not replace Juan's implementation.

## Stop condition

Day 11 is complete when there is a deterministic answer-eval artifact, not just a metric vocabulary note:

1. Chapter 10 evaluation implications are recorded.
2. A generation-eval contract exists with named checks and useful findings.
3. Q091-style incomplete answer behavior is caught automatically by at least one check.
4. At least one passing and one failing fixture are covered by tests.
5. The eval runs without network/API keys.
6. Docs distinguish citation validity, source support/faithfulness, answer completeness, and retrieval context recall.
7. Juan can explain why valid citations are necessary but not sufficient.

Do not close HER-278 on route creation alone. The route is the kickoff; Juan's eval code, tests, evidence, and interview explanation are the acceptance criteria.
