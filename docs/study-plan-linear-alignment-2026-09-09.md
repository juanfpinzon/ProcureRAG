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
| Week 6 | Days 26–30; original Oct 12–16 slot superseded | HER-271 | Live AI-engineer portfolio + guarded ProcureRAG chat + interview readiness | Portfolio research; Next.js/TypeScript, GitHub Pages/Vercel and Azure official docs; accessibility/security; repo evidence; interview practice | Persistent CV-linkable site, preserved prior ML/research/engineering work, flagship case study, genuine service-backed procurement chat, measured launch gates, CV entry, two post drafts and mocks |

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

**Replanned 2026-10-26, before daily-ticket scaffolding.** Week 6 is a portfolio launch sprint, not an optional buffer. The canonical alignment file lives in `docs/`, not the repo root. The [Week 6 portfolio launch plan and research](week6-portfolio-launch-plan-2026-10-26.md), also in `docs/`, contains the old-site audit, inspiration findings, source links, architecture alternatives, public-demo security contract and scoped daily reading map.

#### Starting state and launch gap

- HER-270 and all five Week 5 children are Done in Linear. The repo's older "ready for review" gate sections are historical handoff evidence, not the current gate status.
- API, model-baked Docker image, real Azure deployment/rollback, eval-gated CI/CD and a local stdio MCP tool have been exercised. Disposable Azure resources were deleted: **no backend is currently live**.
- Carry forward Q091's red live-answer completeness, caller-asserted roles, stateless approvals, process-local quotas, sensitive traces and free-text evidence-gap diagnosis limitations. A green API response is not a correct answer.

#### Portfolio content and design direction

- Replace the dated Jekyll/Minimal presentation at `juanfpinzon.github.io` without discarding its substantive work. The portfolio repo's default branch is `master`; inspect its manifest and publishing configuration before migration.
- Preserve and reframe U-NET spine detection, resume NER/publication/dataset/notebooks, DICOM2STL and CS231n foundations. Separate Juan's contribution, historical research, professional experience and personal learning; verify facts, data-sharing permissions, legacy links and the current CV rather than recycling the 2021 resume as current.
- Make ProcureRAG the flagship procurement-intelligence copilot learning project: intentions, business problem, ownership, retrieval primitives, evaluations, agent controls, serving/deployment, failures, learnings and next roadmap. Synthetic data is explicit; do not market it as enterprise-ready or a generic PDF chatbot.
- Use a fast recruiter path (role, selected work, CV/contact/demo) and a deeper engineering path (case study, diagram, metrics with methodology, code, failure analysis). Every project tells problem → contribution → decisions → evidence → limitations/learnings.
- Research references: Hafsa's role-first hero, transition story and outcome-oriented project blocks; Eugene Yan's navigation/prototypes; Hamel Husain's eval-led writing; Chip Huyen's human production-AI narrative; Shreya Shankar's links between research and artifacts. These are curated references, not an objective "best portfolio" ranking.
- Recommended visual candidate: readable editorial engineering with restrained color and strong hierarchy, optionally charcoal/cream inspired by Hafsa. Juan chooses the actual design contract on Day 26. No cloned identity, gratuitous 3D, skill-percentage bars or animation-dependent content. English first; full bilingual expansion is stretch.

#### CV, LinkedIn and certificate update — 2026-10-26

- **Current career input is supplied, not missing:** use `JuanFernandoPinzon_CV_Aug2026.pdf` as the baseline, then refresh it for post-August ProcureRAG work and confirm public-safe wording. The old website still links to its 2021 PDF; replace that download during implementation, not by silently editing the original attachment.
- Position Juan as an **experienced production-ML practitioner with procurement-domain depth extending into LLM/RAG/agent engineering**, not a beginner career reset. The CV reports PepsiCo Data Product Management Associate Manager (Jan 2026–Present), Data Science Sr. Analyst (May 2022–Jan 2026), and Novel Software Systems ML Researcher / DL Consultant (Aug 2019–May 2022). Give production forecasting/Azure/PySpark, governance/retraining, research and current procurement AI roadmap work proper weight. Keep actual job titles; a target Senior AI Engineer headline is not a held employer title or years of LLM experience.
- Preserve compact earlier ITMS/Aritex/STF experience, NSU master's degree / ICESI bachelor's degree, and both publication links. Employer achievements/metrics are CV-reported; approve public wording and keep independent synthetic ProcureRAG separate from employer systems, data and endorsement.
- Add two supporting **course-completion credentials**: Boot.dev **Learn Retrieval Augmented Generation**, **18 September 2026**; Hugging Face **The MCP Course: Unit 1 — 1. Fundamentals of MCP**, **22 October 2026**. Pair them with actual ProcureRAG evidence. Do not imply the full MCP course, professional/vendor certification, independently verified credential URLs or completed Microsoft Azure AI Engineer Associate (CV says **in progress**).
- LinkedIn direct access is auth-walled; extraction returned the headline/summary only. Its ML/production/procurement narrative supports continuity, but "5+ years" versus the CV's "7 years" needs consistent as-of/scope wording. Full Experience is not claimed reviewed; a profile export/screenshots can finish exact reconciliation later.
- Publication corrections for the working CV/site: linked NER paper is journal **Vol. 65 (2020)**, not the CV's 2021; the dataset README documents **545 CVs**, not the old site's 500 shorthand. The market/time-series paper is **AGI 2022 proceedings, published online 14 January 2023**, with a 2022 arXiv preprint. The companion research brief contains primary links and verification boundaries.
- August CV Projects currently lists Hermes/OpenClaw but not ProcureRAG: add ProcureRAG as flagship and label Hermes/OpenClaw as configuration/extensions/integrations over credited existing frameworks. Match every new technical claim to built evidence; do not claim planned TypeScript as already delivered. Add a small credentials section below substantive work/experience, not a badge-first homepage.

#### Architecture recommendation and boundaries

**Default recommendation, to be confirmed on Day 26:** Next.js App Router + TypeScript in the existing portfolio repo on Vercel, with pre-rendered content and a thin same-origin backend-for-frontend (BFF). The BFF calls the existing guarded FastAPI service in its Azure Container Apps container. Python remains the retrieval/AI core; TypeScript supplies the product/interface layer. Repositories remain separate.

- **Use HTTP for website chat, not MCP in the request path.** Existing MCP is local stdio and remains a developer-facing integration over the same service. Remote MCP adds host/protocol/auth work without helping this browser demo.
- **GitHub Pages is a valid static frontend fallback**, but cannot host Python or a runtime POST BFF. It still needs a separate secure gateway/service and exact browser-origin policy. Serving the UI/gateway with the Python container is another scope-saving fallback. Vercel supports FastAPI, but moving the model-backed service there requires a measured runtime/bundle/cold-start fit check, not an assumption.
- **Public launch requires both boundaries secured.** Provider/service secrets stay server-side; the backend must verify the BFF credential/identity and refuse direct unauthenticated query/stream calls. CORS and a frontend proxy alone are not authentication.
- **Public-demo policy is server-owned and least-privileged.** Use an explicitly approved synthetic subset; no role selector, browser-supplied privilege escalation, automatic approval, uploads or writes. BFF identity is not enterprise visitor identity. `pending_approval` stays fail-closed publicly; privileged walkthroughs remain local/reviewer-controlled.
- Free text omits `query_id`; presets map exact approved questions server-side. Preserve caveats that evidence gaps are unchecked for unlabeled questions. A chat transcript display does not imply persistent or context-aware multi-turn memory.
- Reuse `QueryResponse` statuses, safe text, findings, caveats and source IDs. The API currently has no source snippets/URLs: resolve verified public synthetic-corpus anchors or define a reviewed source-serving contract. Do not invent citations, snippets or trace links. Escape/sanitize model output.
- Ship JSON `/query` first; stage-progress SSE is stretch, not claimed token streaming. Test unavailable, cold-start, timeout, invalid, throttled, blocked, declined, gap, not-generated and pending states without hiding them behind an answer bubble.
- Before paid/public traffic, enforce persistent atomic global/client/concurrency quotas, reserved generation budget, input/body/output/timeout/retry bounds, upstream auth, a tested kill switch and a Juan-approved numeric spending ceiling. Azure budget alerts are not a spending stop. Test actual proxy/client identity rather than trusting arbitrary forwarded headers.
- Choose scale-to-zero versus warm capacity from measured end-to-end latency and cost. Earlier Azure cold starts were 59–72 seconds without live generation; verify the BFF platform timeout before adopting the route. Default to sanitized metadata/tracing off and no raw public transcripts.

#### Daily scope: five six-hour loops

No new Boot.dev chapter is required. Reactivate completed fundamentals and use exact official docs sections listed in the research plan; daily routes must carry those source names/URLs forward.

| Day | Goal | Acceptance focus |
|---|---|---|
| 26 | Evidence/content audit, experienced-ML/AI narrative, wireframe and architecture/public-demo contract | Supplied Aug 2026 CV + two course awards; public-safe experience, consistent tenure/citations/credential scope; chosen repo/hosting/design, synthetic-data/role/budget/timeout decisions and no-paid probe |
| 27 | Responsive TypeScript portfolio preview + experience/research/credentials + ProcureRAG case study | Production ML/procurement experience, legacy work/publications, accurately scoped course awards, honest results/learnings/limits, refreshed CV/contact and accessible mobile/desktop preview |
| 28 | Guarded service-backed procurement chat vertical slice | Typed BFF, backend credential validation, least privilege, sources/caveats, negative paths and a genuine bounded live generated answer; fake tests separate |
| 29 | Persistent hosted demo + cost/security/reliability hardening | Actual deployed frontend → BFF → authenticated API → model path, atomic quota exhaustion/kill switch, cold/warm behavior, rollback and deployed-artifact quality evidence |
| 30 | Public launch + CV/LinkedIn consistency/writing/interview package + separate weekly gate | Refreshed Aug CV with ProcureRAG/courses, accurate citations/ownership/current role and in-progress Azure status; stable public URLs, browser matrix, evidence, two drafts and 45–60 minute defense |

Scope cut order: full bilingual site, custom domain, 3D/animation, remote MCP, enterprise durable HITL and token streaming first. Do not cut real live chat, security, source evidence or an accurate CV to claim a five-day win. A fallback/mock preserves progress but does not pass the launch gate; record an overrun if needed. Original Week 6 calendar dates are historical; this scaffold does not silently reschedule the current Linear due date.

Passes only when:

- A persistent HTTPS portfolio is usable from a clean browser and linked from the updated CV; home, ProcureRAG case study, selected earlier work, verified experience and contact are present.
- The real deployed procurement chat produces current generated answers using ProcureRAG's service, with verified source references, synthetic-data disclosure and honest limitations. A recording, hard-coded reply, retrieval-only `not_generated` response or screenshot alone does not pass.
- The launch smoke set includes at least three answerable questions, a paraphrase, abstention/unanswerable, blocked input and Q091 evidence. Q091 is either repaired with regression evidence or explicitly withheld/guarded publicly; a disclaimer alone is not a repair.
- Backend direct-call rejection, privilege/approval tampering, input bounds, persistent quota exhaustion, kill switch, sanitized errors/logs, source rendering and timeout/unavailable behavior are exercised. No browser secrets or unrestricted billable upstream remain.
- Public URLs, both repo commits, frontend deployment and backend image digest/revision are recorded; tested rollback and cold/warm behavior, hosting retention/owner/budget and no-secret CI gates are documented.
- Accessibility/responsive checks cover keyboard/focus/contrast/reduced motion and mobile/desktop; the portfolio and evidence remain readable if chat is unavailable.
- README, architecture diagram, eval report and CV Projects entry agree with the live behavior, metric methodology, personal ownership and known failures. No fabricated production impact or guaranteed senior-readiness claim.
- Updated CV, site and accessible LinkedIn headline/summary use consistent role/tenure/citation claims, preserve employer-versus-personal-project separation and credit underlying agent frameworks. The two supplied course awards have exact issuer/title/date/unit scope and accessible evidence; Azure remains in-progress unless new proof is supplied. Missing issuer URLs are labeled unavailable, not invented, and full LinkedIn Experience is not claimed audited.
- Two substantive technical-post drafts exist; short daily explanation reps and a final 45–60 minute architecture/implementation defense plus live-coding rep are recorded.
- All five daily children pass review, then Hermes performs a separate HER-271 readiness review. A deployed interface alone cannot close the learning gate.

Juan owns all implementation in both repos; Hermes scaffolds docs/tickets, reviews and quizzes. No implementation, hosting purchase or public-site change is part of this planning update.

## Future daily scaffold requirement

Every future `start ProcureRAG Day N` response must include:

1. exact course source(s), chapter(s), and lesson(s);
2. the artifact Juan should build himself;
3. fallback route if course pace blocks implementation;
4. evidence fields to update in `docs/learning-log.md`;
5. baseline verification commands;
6. the exact review prompt to send Hermes when ready.
 