# ProcureRAG Study Plan ↔ Linear Alignment — 2026-09-09

## Why this alignment exists

The original gap plan is broader than Boot.dev. Boot.dev is the Week 1 retrieval-from-primitives spine, but the full offer-readiness plan also includes Ben Clavié / Beyond Naive RAG, freeCodeCamp RAG From Scratch, RAGAS/DeepEval, DeepLearning.AI courses, LangChain Academy, guardrails material, serving/deployment, MCP, and interview drilling.

The initial Linear plan correctly protected the principle that Juan writes the core implementation, but it became ambiguous in two ways:

1. **Daily loop vs weekly gate got blurred.** HER-266 was framed as a Friday/Week 1 exit test, while HER-261 was also the Week 1 gate. Going forward, daily loop tickets define the study/build route; weekly gate tickets define evidence and interview readiness.
2. **Course targets were too vague.** Future day scaffolds must name exact course chapters/lessons when known, and explicitly identify non-Boot.dev companion sources.

## Operating rule going forward

- **Daily route docs/tickets:** name exact course chapter/lessons, artifact target, baseline commands, learning-log evidence fields, and the review prompt.
- **Weekly gate tickets:** validate cumulative evidence against the market gap plan: repo artifacts, tests/evals, explanation drill, and next-week adjustment.
- **Boot.dev is not the whole plan:** use it as the from-primitives backbone, then layer the other sources at the correct stage.
- **Friday afternoon remains market-facing when energy allows:** applications, CV bullets, interview prep, or a mock — but not at the cost of the week’s technical gate.

## Corrected high-level schedule

This alignment accepts the actual Week 1 pace: Juan completed preprocessing, TF-IDF, BM25, and semantic search by hand; chunking is the next correct Boot.dev step. The original 4-week + 1-week polish plan remains the target shape, but Linear should track a realistic 6-week version if the 30h/week plan compresses under real learning load.

| Week | Dates | Linear gate | Primary focus | Course sources | Build/evidence target |
|---|---|---|---|---|---|
| Week 1 | Sep 7–11 | HER-261 | Retrieval foundations by hand | Boot.dev Ch. 1–5; Ben Clavié/Beyond Naive RAG skim | preprocessing, TF-IDF, BM25, semantic search, chunking foundations, learning log, explanation drill |
| Week 2 | Sep 14–18 | HER-267 | Advanced retrieval + retrieval evals | Boot.dev Ch. 6 Hybrid Search, Ch. 8 Reranking, Ch. 9 Evaluation; Beyond Naive RAG; RAGAS docs | RRF/hybrid, reranker, metadata filtering, precision@k/recall@k/MRR, golden query/QA set started |
| Week 3 | Sep 21–25 | HER-268 | Grounded generation + eval harness | Boot.dev Ch. 10 Augmented Generation; DeepLearning.AI Building & Evaluating Advanced RAG; DeepEval/RAGAS/Langfuse docs | source-cited answer generation, context relevance/groundedness/answer relevance evals, error analysis |
| Week 4 | Sep 28–Oct 2 | HER-269 | LangGraph agents + observability + guardrails | LangChain Academy Intro to LangGraph modules 0–6; HF Agents skim; DeepLearning.AI Guardrails; OWASP LLM Top 10; Instructor/Pydantic | `create_agent`/state graph/tools/HITL, tracing, prompt-injection + PII guardrails, structured outputs |
| Week 5 | Oct 5–9 | HER-270 | Serving, deployment, CI/CD, MCP | freeCodeCamp Production RAG; Venelin FastAPI RAG; Microsoft Learn Azure; HF MCP; Anthropic MCP | async streaming FastAPI, Docker, Azure/fallback deploy, eval-gated CI, one MCP server/tool |
| Week 6 | Oct 12–16 | HER-271 | Portfolio polish + interview readiness | RAG/system-design question banks; repo docs; technical-post drafts | README, architecture diagram, eval report, CV Projects entry, two posts, daily mocks/live-coding reps |

## Week 1 specific correction

HER-266 should no longer be interpreted as the same thing as HER-261.

- **HER-266 = active Day 5 loop:** Boot.dev Chapter 5 — Chunking foundations.
- **HER-261 = Week 1 gate:** cumulative evidence review after Day 5 is complete.

Day 5 course target:

- Minimum: Boot.dev Chapter 5 lessons 1–3 — `Chunking`, `Chunk Overlap`, `Semantic Chunking`.
- Good 6-hour target: lessons 4–5 — `Chunked Semantic Embeddings`, `Chunked Semantic Search`.
- Stretch: lesson 6 — `Chunked Edge Cases`.
- Defer/read-only unless course requires: lessons 7–8 — `ColBERT`, `Late Chunking`.
- Defer as main build target: Boot.dev Chapter 6 — `Hybrid Search`; begin in Week 2 after chunk-level retrieval is understood.

## Gate definitions

### Week 1 gate — HER-261

Passes only when:

- Day 1–5 learning-log entries include exact course checkpoints and repo evidence.
- Tests/compile/smoke checks pass.
- Repo contains small, explainable artifacts for preprocessing, TF-IDF, BM25, semantic search, and chunking or chunking design.
- Juan can explain why naive vector RAG fails on exact IDs/part numbers, why BM25 helps lexical retrieval, and why chunking comes before hybrid search.

### Week 2 gate — HER-267

Passes only when:

- Hybrid retrieval is implemented or clearly scoped after chunk-level retrieval exists.
- RRF or another transparent fusion method is explained.
- Reranking is implemented or deliberately deferred with reason.
- Retrieval evals include precision@k/recall@k/MRR or a justified equivalent.
- Golden query/QA set is started and versioned.

### Week 3 gate — HER-268

Passes only when:

- ProcureRAG can generate grounded, source-cited answers from retrieved evidence.
- Error analysis records actual failures, not just green test output.
- At least two code-based evals and one LLM-as-judge eval exist or are scoped.
- Juan can explain faithfulness, context relevance, answer relevance, and LLM-as-judge risks.

### Week 4 gate — HER-269

Passes only when:

- LangGraph / LangChain 1.x `create_agent` patterns are understood and represented in the repo.
- Tool use, state, memory/HITL or routing are implemented or clearly scoped.
- Observability/tracing evidence exists.
- Prompt injection, PII, and structured-output guardrails are tested or documented.

### Week 5 gate — HER-270

Passes only when:

- There is an async/streaming FastAPI surface or a deliberately scoped equivalent.
- Docker build works.
- Azure deployment or documented fallback exists.
- CI can run tests/evals as a merge/deploy gate.
- One MCP server/tool exists or is demonstrably scaffolded.

### Week 6 gate — HER-271

Passes only when:

- README, architecture diagram, eval report, and CV Projects entry are credible.
- Two technical posts exist as drafts or scheduled outlines.
- System-design and live-coding reps have been rehearsed.
- Hermes final readiness review says the repo tells a senior hands-on AI Engineer story.

## Future daily scaffold requirement

Every future `start ProcureRAG Day N` response must include:

1. exact course source(s), chapter(s), and lesson(s);
2. the artifact Juan should build himself;
3. fallback route if course pace blocks implementation;
4. evidence fields to update in `docs/learning-log.md`;
5. baseline verification commands;
6. the exact review prompt to send Hermes when ready.
