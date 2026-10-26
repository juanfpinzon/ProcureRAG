# Week 6 portfolio launch plan and research — 2026-10-26

**Gate:** HER-271. **Status:** planning contract, not an implemented or deployed portfolio.
**Canonical study plan:** [study-plan / Linear alignment](docs/study-plan-linear-alignment-2026-09-09.md).

## Outcome and positioning

Week 6 is no longer an optional polish/overrun buffer. Ship a persistent, HTTPS, CV-linkable portfolio combining Juan's production ML, research and procurement-domain experience with his recent hands-on LLM/RAG upskilling. **This is an experienced ML practitioner deepening LLM/agent engineering, not a beginner entering AI from scratch.** ProcureRAG is the flagship: an independent procurement-intelligence copilot learning project, with RAG as its evidence layer, not a generic PDF chatbot or a claimed employer/production procurement product.

A recruiter should quickly understand the target role, earlier experience, what Juan personally built, why the project exists, what was learned, and where to inspect code/evidence or try it. A technical interviewer should find reproducible measurements, failure analysis, architecture and trade-offs. The procurement demo answers questions against the project's synthetic knowledge base, not against Juan's biography.

This is a research-backed recommended direction. The supplied August 2026 CV is now the career baseline; Day 26 confirms changes since August, public-safe employer wording, visual direction, hosting account/domain and spending ceiling rather than requesting a CV from scratch. Scaffolding does not authorize new cloud expenditure, account changes, public deployment, email automation or code implementation by Hermes.

## Evidence reviewed before replanning

- ProcureRAG `main` was clean and synchronized after `git fetch origin`, at `994b116` on 2026-10-26.
- Read the whole existing alignment, current README, Day 25 learning-log ending, Day 25/Week 5 eval-report inventory, API contracts, package manifest, HER-271 and prior weekly parent/child patterns.
- Linear HER-270 and all five Week 5 children are Done. Its 2026-10-25 closure is the gate authority; older repo sections saying "ready for review" describe the handoff before closure, not current ticket state.
- Fresh local baseline: 438 tests passed; compileall and Ruff passed. The first run inherited tracing and got LangSmith monthly-quota HTTP 429 warnings. A repeat with `LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false PROCURERAG_LIVE_LLM=0` passed all 438 tests without those warnings. Public-demo observability must not depend on paid SaaS trace availability.
- Azure deployment, digest-gated promotion and manual rollback were exercised, then disposable resources deleted. **Nothing is currently live.** MCP is local stdio only.
- The API has `/health`, `/query` and `/query/stream`. It returns typed statuses, source IDs, findings and caveats. Source refs contain `source_id`, `doc_id`, `chunk_id`, `cited`, **not snippets or public URLs**.
- Free-text requests have no gold labels: the current graph cannot diagnose their evidence gaps. A labeled replay requires the exact matching question. Do not advertise general autonomous multi-step research or conversational memory.
- Caller-asserted roles, stateless/unattributed approval, per-process rate limits and raw-text trace sensitivity are not public-launch controls. Q091 live-answer completeness remains red despite repaired retrieval.

## Existing portfolio audit: keep the evidence, replace the hierarchy

Reviewed the rendered [live site](https://juanfpinzon.github.io/), links, desktop screenshot and [repository](https://github.com/juanfpinzon/juanfpinzon.github.io). The default branch is **`master`**, not `main`. Source files inspected: `_config.yml`, `Gemfile`, `_layouts/default.html`, plus the recursive asset tree. It is Jekyll `jekyll-theme-minimal`, with an existing public PDF at `/docs/Resume-Juan-Pinzon_11.09.21.pdf`.

| Existing asset | Migration decision |
|---|---|
| U-NET spine/vertebra detection in PyTorch/fast.ai, DICOM preprocessing and OpenCV postprocessing | Preserve as historical applied-ML case study with Juan's contribution, verified dates and data-sharing restrictions. Do not publish private medical data or imply a deployed clinical product. |
| Resume/CV NER, Flair/PyTorch, SEPLN 2020 paper, public annotated dataset and notebooks | Promote the publication and reproducible public artifacts. Follow-up source checks confirm journal Vol. 65 (2020) and the README's documented 545-CV dataset wording; correct the CV's 2021 and old site's 500 shorthand in working drafts. Retain the honest finding that the research did not meet production expectations. |
| DICOM2STL, VTK/SimpleITK, Autobone context | Preserve as engineering experience, with a clean input → pipeline → output story and a verified public repo. Do not claim ownership of the whole commercial system. |
| CS231n implementations | Keep as foundational learning in an archive/secondary section, not equal billing with ProcureRAG or professional work. |
| Existing contact/profile links, images, notebook URLs, 2021 CV | Audit every destination and asset permission. Replace the live 2021 download with an approved update based on the supplied August 2026 CV; preserve useful historical URLs or provide a migration map. Do not leave the current-CV input marked missing. |

Observed limitations: narrow two-column theme, large images and long justified paragraphs, no AI-engineer hero or ProcureRAG entry, icon-only primary links, and no quick project/evidence navigation. The old work is substantive; the presentation undersells it. Correct obvious copy issues such as "100,000 thousand" only after checking the intended fact with Juan.

## Career and credential evidence update — supplied 2026-10-26

### Sources and verification boundaries

- Read both pages of Juan-supplied `JuanFernandoPinzon_CV_Aug2026.pdf` using local PDF text extraction. Inspected `bootdev_certificate-2.png` and `MCP-huggingface-certificate.webp` visually, including an enlarged Boot.dev credential-ID crop. Originals remain in the local chat attachment directory `/home/hermes/.hermes/.hermes/desktop-attachments/`; they have **not** been copied into either public repo, edited, uploaded to Linear or published.
- LinkedIn URL: https://www.linkedin.com/in/juanfpinzon/ . Direct browser access redirected to an authentication wall. Web extraction returned the public headline and summary, not a complete experience/certification audit. Retrieved headline: **"AI Transformation | Data Science & ML Engineering | LLM Applications & Agentic AI | Digital Strategy at Scale"**. The summary describes production ML across NLP, forecasting and CV, Azure/Python/PyTorch/PySpark, PepsiCo transformation and current procurement/agentic focus. Do not use unrelated same-name profiles or an inconsistent extractor country field as career evidence.
- Career dates, responsibilities and business outcomes below are **CV-reported/user-supplied**, not independently audited employment/performance facts. Preserve the real job titles and require Juan to approve public-safe wording; use publisher/repository records for citations and artifact claims.

### Career narrative to build around

| CV-reported experience | Portfolio treatment |
|---|---|
| PepsiCo, Data Product Management Associate Manager, Jan 2026–Present | Current Digital Procurement AI roadmap/prototyping and stakeholder/architecture experience. Keep the actual title; do not relabel it as a held Senior AI Engineer job or imply completed enterprise LLM production deployments. |
| PepsiCo, Data Science Sr. Analyst, May 2022–Jan 2026 | Give production forecasting, PySpark/Azure Databricks/Data Factory and governance/monitoring/retraining design prominent space. Add approved procurement analytics/adoption work as domain and delivery evidence. These experiences should not be buried below course certificates. |
| Novel Software Systems, Machine Learning Researcher / DL Consultant, Aug 2019–May 2022 | Connect biomedical/CV and NLP research, resume NER and market/time-series work to the published artifacts and original portfolio. Clearly distinguish research/client contribution from ownership of whole products. |
| ITMS, Business / Systems Analyst, Nov 2018–Aug 2019 | Compact earlier-experience row supporting requirements translation and QA skills. |
| Aritex de Colombia S.A.S., Production Planning Analyst, Aug–Dec 2016; STF Group, Procurement & Inventory Analyst, Jan 2014–Jul 2016 | Compact domain-background rows: procurement, operations, inventory and analytical automation explain why the ProcureRAG use case is informed rather than arbitrary. |
| NSU M.Sc. Big Data Analytics & AI, 2017–2019; Universidad ICESI B.B.A., 2015 | Keep education concise but visible. This is an existing technical/business foundation, not a new AI qualification earned during ProcureRAG. |

Recommended draft positioning, subject to Juan's copy approval: **"ML/AI engineer with production forecasting and procurement experience, building evidence-driven RAG and agentic applications."** A senior-targeted variant can be used if Juan wants to retain the supplied CV's target headline, but seniority must be supported by prior production ownership and interview evidence, not inferred from certificates or a new website. Do not describe all prior ML tenure as years of LLM/agent experience.

Keep employer experience and public demos separated. ProcureRAG is an independent, synthetic-data project informed by procurement knowledge: no PepsiCo affiliation, internal platform recreation, employer endorsement, confidential architecture, supplier data or production-use claim. Only approved high-level role/outcome wording is public. The CV's numerical business claims (millions of rows, 4+ weeks to near-real-time, 100+ procurement members, 20% obsolete-inventory reduction) are CV-reported: use only approved wording and the correct attribution; do not invent public verification links or copy internal dashboards.

### Supplied learning credentials

| Issuer / exact title | Recipient and date visible on artifact | Allowed claim / implementation evidence to pair with it |
|---|---|---|
| Boot.dev, **Learn Retrieval Augmented Generation**, certificate of completion | Juan Fernando Pinzon; **September 18, 2026**; visible credential ID `5a4079c0-0848-4b54-b4a8-fb847526d2d6` | Completed that course. Pair it with Juan's retrieval primitives, hybrid/reranking and evaluation artifacts in ProcureRAG. The certificate's printed "Topics mastered" label is not independent proof of interview/production mastery. |
| Hugging Face, **The MCP Course: Unit 1**, **1. Fundamentals of MCP**, certificate of achievement | Juan Pinzon; **2026-10-22**; no credential ID or verification URL visible | Completed Unit 1/Fundamentals, **not the whole MCP course**. Pair it with the existing local stdio tool, typed protocol tests and smoke evidence; do not imply a production remote MCP service. |

Neither supplied image shows a public verification URL; none has been independently validated against an issuer credential record. Do not fabricate a Verify button, use a course landing page as credential verification, or claim a new professional/vendor certification. Show title/issuer/date and an approved accessible certificate image/link; add a genuine issuer credential URL only when supplied and checked. Both are supporting **course-completion credentials**, below experience and project evidence.

The CV lists Microsoft Azure AI Engineer Associate as **in progress**, not earned; preserve that status unless new proof changes it. Other CV-listed courses/credentials are not newly verified by these two attachments. Dates for those must not be guessed.

### CV, LinkedIn and publication consistency checklist

1. **Career-tenure wording:** CV says "7 years"; the extracted LinkedIn summary says "5+ years". These can be compatible, but unify the chosen public wording and as-of date after Juan confirms his intended scope. Do not infer seven years of generative-AI work. Maintain the real role chronology; full LinkedIn Experience remains unreviewed without an export/screenshots.
2. **NER paper year:** CV says SEPLN 2021, but the [journal record](http://journal.sepln.org/sepln/ojs/ojs/index.php/pln/article/view/6276) lists *Procesamiento del Lenguaje Natural*, **Vol. 65 (2020)** and names Juan F. Pinzon as an author. Use **2020** for that linked publication unless Juan identifies a different edition; correct the working CV/website draft, not the original attachment silently.
3. **NER dataset wording:** the [repository README](https://github.com/juanfpinzon/resume-dataset) says **545 CVs with NER Annotations**. Attribute that as the documented dataset size, not a fresh independent record count; avoid the old site's "500" shorthand. Link the project/publication, not individual resumes or personal data in a demo.
4. **Market/time-series paper:** [arXiv:2204.12928](https://arxiv.org/abs/2204.12928) verifies Juan Pinzon's coauthorship and the 2022 preprint. The [Springer chapter](https://link.springer.com/chapter/10.1007/978-3-031-19907-3_4) / [DOI](https://doi.org/10.1007/978-3-031-19907-3_4) confirms **AGI 2022 proceedings**, published online **14 January 2023**, pp. 30–39. This is a conference-year versus publication-year distinction, not evidence the CV invented the conference. Prefer an explicit citation such as "AGI 2022 proceedings (published 2023)" plus the 2022 preprint link.
5. **Current Projects section:** August CV currently features OpenClaw/Hermes but no ProcureRAG. Add ProcureRAG as the flagship, with checked repository/eval evidence and a working live URL only after launch. Keep Hermes/OpenClaw secondary as self-hosting, configuration/extensions, workflow/context engineering and personally authored integration work; credit the underlying projects and do not imply Juan authored their agent frameworks.
6. **Skills proof:** group production Python/PySpark/SQL/Azure/ML experience separately from newly demonstrated LLM/RAG/LangGraph/FastAPI/Docker/CI/MCP skills and planned TypeScript work. No unbuilt frontend/deployment capability becomes a CV claim merely because it is in Week 6 tickets.
7. **Final publication gate:** maintain a factual crosswalk across CV, site and the accessible LinkedIn headline/summary; draft LinkedIn edits if useful, but do not change the live profile or original CV without a separate publishing/editing step. A full LinkedIn export is helpful for exact Experience synchronization but not a blocker to starting the portfolio from the supplied CV.

## Inspiration research: observations versus recommendations

These are selected strong references, **not an objective ranking of the world's best portfolios**. Portfolio observations were retrieved on 2026-10-26; visual claims below are limited to the two sites inspected in the browser.

| Source | Observed pattern | Borrow for Juan / avoid |
|---|---|---|
| [Hafsa Mrabet](https://hafsa.hechoporpersonas.com/) | Clear role-first hero, career-transition narrative, experience navigation, numbered project blocks with `RETO`, outcome text, technology tags and detail links; embedded chat launcher. Visually: charcoal backgrounds, cream serif headlines, gold emphasis, green calls to action, portrait and generous spacing. | Borrow role clarity, human story and problem → contribution → outcome cards. Recommend an editorial engineering direction, not a clone. Do not copy unsupported absolute claims such as zero delivered bugs. Scroll-reveal sections were initially blank in a full-page capture: keep Juan's core content readable without animation/JS. Chat presence does not prove its architecture or answer quality; no chat was submitted. |
| [Eugene Yan](https://eugeneyan.com/) | Short role/value proposition and explicit Writing, Speaking, Prototyping and About routes; prototype/app links and technical writing. | Put a short recruiter path before the deep technical path. Link the working demo and evidence directly. Do not bury the flagship beneath an uncurated chronological blog feed. |
| [Hamel Husain](https://hamel.dev/) | Applied-AI positioning, linked OSS contributions, focused writing about debugging/measuring AI and an eval guide. | Make failure analysis and evaluation a differentiator. Use actual ProcureRAG evidence, not reputation-style social proof or borrowed authority. |
| [Chip Huyen](https://huyenchip.com/) | Human personal story plus concise AI-to-production focus, public tools, GitHub, research and books. | Connect prior experience to current direction, with concrete artifacts rather than a wall of framework logos. Do not mimic established-expert credentials Juan has not earned. |
| [Shreya Shankar](https://www.sh-reya.com/) | A concise research/engineering narrative links DocETL, papers, GitHub and CV. | Surface Juan's real NER publication/dataset as evidence beside his new applied-AI work. Do not turn an industry-targeted portfolio into an academic CV directory. |

**Recommended style:** editorial, technically literate and human. Use strong type hierarchy, a restrained accent, real project diagrams/screenshots, readable left-aligned copy, visible text links and short evidence summaries. A dark/cream direction inspired by Hafsa is a candidate, not a pre-approved design system. Day 26 selects tokens and one wireframe. Avoid gratuitous 3D, custom cursors, autoplay chat, typing theatrics, skill-percentage bars and generic AI gradients. Motion must be optional and respect reduced-motion preferences. English first for Barcelona/international hiring; a short Spanish summary is optional, full bilingual duplication is stretch.

## Minimum information architecture

1. Home: Juan, experienced ML/AI + production/procurement positioning, featured ProcureRAG, visible `Try demo`, `Read case study`, `CV`, `GitHub`, `Contact`.
2. ProcureRAG case study: business problem/intended users; learning goals; personal ownership; primitives → evals → bounded graph → guarded service progression; architecture; reproducible retrieval and generation evidence; failures/limits; live demo; next roadmap.
3. Selected work/research: NER/publication/dataset, medical CV, DICOM2STL and the verified market/time-series paper; distinguish research, personal learning and professional contributions. Existing Hermes/OpenClaw customization can be a compact secondary systems example if ownership is accurate.
4. Experience/about: CV-sourced PepsiCo production forecasting and current Digital Procurement role, Novel Software research plus compact prior chronology and education. Confirm post-August changes/public-safe wording; no invented roles, tenure or impact.
5. Learning credentials: the two supplied course awards with exact title, issuer/date/unit scope and links to corresponding ProcureRAG evidence. Small and subordinate to projects/experience; accessible image text, no invented verification links or completed Azure credential.
6. Writing/contact: two technical draft artifacts can remain unpublished; mailto/LinkedIn is sufficient, no contact form/email service required.

For every project use: problem → Juan's role → key technical decisions → result/evidence → limitations/learnings → links. For metrics include commit/date, benchmark/corpus, cutoff, method and reproduction link. `P@1=0.978` is retrieval ranking precision, **not** 97.8% answer accuracy. Synthetic corpus and the Q091 failure must remain visible.

## Architecture recommendation and alternatives

**Recommended default, to confirm on Day 26:** Next.js App Router + TypeScript in the existing portfolio repository, deployed on Vercel; pre-render portfolio/case-study content; use a small server-side backend-for-frontend (BFF) for chat. Keep Python models/retrieval in the existing ProcureRAG container on Azure Container Apps. Keep repositories separate and link release evidence across both. Reusing the repo does not require replacing its live site before preview and migration checks pass.

```text
Browser portfolio + procurement chat
  → same-origin TypeScript BFF (validate, limit, reserve quota, enforce demo policy)
  → authenticated HTTPS ProcureRAG FastAPI boundary
  → existing guarded retrieval / bounded graph / generation pipeline
  → typed safe result → validated UI + source references

Local AI host → existing stdio MCP adapter → same guarded ProcureRAG service
```

| Option | Benefit | Cost / decision |
|---|---|---|
| Next.js/Vercel + BFF + Azure container | React/TypeScript product-layer evidence, preview deploys, server-only credentials, reuses Week 5 artifact | Recommended; two hosted components plus shared quota store. Verify account eligibility, regions, runtime timeout and cost before choosing. |
| GitHub Pages static portfolio + separate authenticated API gateway/BFF + Azure | Retains the familiar Pages URL and static-host simplicity | Valid fallback. Pages cannot run Python or a runtime Next.js POST handler. Gateway still required for credentials/cost policy; configure exact allowed browser origins. No secret can live in static JS. |
| Portfolio and gateway served with the Python container | One deployment and one origin | Valid scope-saving fallback if learning Next.js blocks launch; less TypeScript/React depth. Record the trade-off. |
| Move the complete model-backed service to Vercel Functions | Fewer vendors in theory; Vercel supports FastAPI | Not the default: revalidate bundle, CPU/memory and model-loading constraints first. The existing CPU image/models were already measured on Azure. Do not claim FastAPI is unsupported on Vercel. |
| Browser → remote MCP | Protocol reuse for an AI-host product | Not needed for a web form/chat. Existing stdio cannot be called from a browser. Remote MCP adds a host/client, discovery/elicitation, transport and auth work without improving this demo. Keep it a documented developer integration; defer remote MCP. |

### Launch-critical service and security contract

- The browser never receives provider/service credentials. Keep secrets out of `NEXT_PUBLIC_*`, bundles, source maps, logs and artifacts. The BFF is a fixed upstream adapter, **not** an arbitrary-URL proxy or a second RAG/LLM pipeline.
- Protect Azure `/query` and `/query/stream` with verified BFF service identity/token (or equivalent ingress authentication); reject direct unauthenticated calls before retrieval. A secret held by an unprotected proxy and CORS alone do not secure the upstream.
- Anonymous visitors get only the documented public synthetic demo subset, with a fixed least-privileged server policy. No role selector; reject escalation/decision fields; no uploads, writes or supplier data. Current `requester` permits synthetic `Internal`, not `Confidential`; explicitly approve the public allowlist rather than relabeling all data as public.
- BFF identity is **service** identity, not proof of a visitor's employment role. No claims of enterprise user authentication, multi-tenancy or durable approval. Pending approval remains fail-closed in public mode; privileged approval demos stay local/reviewer-controlled.
- Use server-owned suggested-question/preset mappings. Free text omits `query_id`; never attach a gold ID to edited text. Explain that free-text evidence completeness is unchecked today. A visible message list is UI history, not persistent conversational memory.
- Preserve `answered`, `model_declined`, `gap_report`, `not_generated`, `blocked`, `pending_approval`, findings/caveats and 422/429/timeout/unavailable states. Only render safe text; escape/sanitize model Markdown/HTML and allowlist citation URLs. Current sources are IDs: use verified synthetic-corpus anchors or add a reviewed source-serving contract, never invent snippet text or file links.
- Start with JSON `/query`. Progress SSE is stretch after the vertical slice works; current `/query/stream` streams stage events plus a final answer, not token-by-token generation. Verify cancellation semantics: a disconnected browser does not prove a provider call stopped.
- Enforce limits outside process memory: persistent atomic quota reservations for global daily requests and in-flight requests, per-client limits using trusted platform client metadata, input ≤500 characters and total body cap, provider timeout/output-token limits, bounded retries and no automatic duplicate billable resubmission. Resetting a cookie must not bypass the global cap. Fail closed if quota storage is unavailable.
- Set a numeric Juan-approved cloud/LLM ceiling before provision or paid smoke. Reserve worst-case generation budget before calling, reconcile afterward, and test exhaustion at tiny limits. Budgets/alerts do not themselves stop Azure spending. Limit replicas/concurrency, record registry/log/storage costs, and test a manual kill switch and rollback.
- Choose measured scale-to-zero versus one warm replica. Previous Azure cold starts were 59–72 s without live generation. Test the complete browser → BFF → model chain against the selected platform's actual timeout; show warming/timeout states, or use a scope-saving deployment route. No blindly repeated POSTs to warm the service.
- Default to tracing off/sanitized operational metadata. Publish provider/retention disclosure and "do not enter personal or confidential data"; no public raw traces, prompt logs or real-user transcript retention by default.

### Quality gate: working web plumbing is not correct procurement advice

Before public launch, use a small versioned demo smoke set: at least three answerable questions plus a paraphrase, an unanswerable/abstention case, a blocked/injection case and the known hard Q091 case under its documented allowed role. Record expected evidence/claims and actual behavior, not only HTTP status. Generated answers require genuine provider calls through the real deployed chain; fake, frozen and `not_generated` results are separate evidence lanes.

Q091 must either pass an evidence-backed repair with regression protection, or remain an explicit known failure and be withheld/guarded in the public experience. A disclaimer alone is not a fix. Do not present a complete-looking unsafe answer as accepted procurement guidance. If live generation or safe public access cannot be delivered, keep the page honest and mark HER-271 incomplete; screenshots, recordings and retrieval-only mode preserve progress but do not satisfy the live-chat gate.

## Five day loops and scope control

Each day targets roughly six hours including a short explanation drill. No new Boot.dev chapter: reactivate completed fundamentals and use exact official framework/security/deployment sections, not another broad course. Daily route docs and learning-log skeletons are created at each kickoff, not fabricated as completed work now.

| Day | Goal / artifact | Minimum acceptance |
|---|---|---|
| 26 | Portfolio content/evidence inventory, experienced-ML/AI narrative, wireframe/design contract, API threat model and hosting ADR | Use supplied Aug 2026 CV and two course awards; reconcile tenure/paper years/credential scope and approve employer wording; all legacy areas triaged; architecture/data/role/budget/timeout decisions before deployment; no-paid contract probe. |
| 27 | Responsive TypeScript portfolio preview, experience/research/credentials and flagship case study | Recruiter path + prominent production ML/procurement experience, prior work/publications, correctly labeled course awards, real evidence links and updated CV/contact; accessible mobile/desktop preview, no unsupported live claims. |
| 28 | Secured local procurement-chat vertical slice | Typed BFF over existing guarded service, live generated/cited answer on approved paid smoke, public data policy, no privilege/approval bypass, source references, error states and deterministic adapter/UI tests. |
| 29 | Persistent hosted demo and launch hardening | Real two-repo deployed chain, authenticated upstream, global atomic quota and kill-switch tests, cold/warm measurements, rollback and fresh live quality evidence on the deployed digest; portfolio stays usable if chat fails. |
| 30 | Public launch, CV/LinkedIn consistency, post artifacts and separate HER-271 gate review | August CV refreshed with ProcureRAG and earned course awards, citation years/ownership/current role reconciled, Azure still in-progress; public URL/browser/quality/security checks, two drafts and 45–60 minute defense/mock. |

**Critical path:** confirmed story/contract → portfolio preview → secured end-to-end chat → hosted safety/quality → final recruiter review. Cut bilingual expansion, custom domain, 3D, public remote MCP, durable enterprise HITL and token streaming before cutting the real live chat, security boundary, source evidence or current CV. If this exceeds five learning days, document the overrun rather than redefining launch as a mock. Preserve the parent's current due date unless Juan explicitly reschedules; the old Week 6 table dates are historical, not dates for Days 26–30.

## Implementation ownership and verification

Juan owns implementation in both repos and all ProcureRAG `src/`/`tests/` changes. Hermes owns planning/route docs, reviews, quizzes and Linear. No backend code or portfolio code is written as part of this scaffold. New artifact paths in daily tickets are proposed contracts, not claims those files already exist.

At kickoff, inspect the chosen portfolio manifest/lockfile and define exact install/typecheck/lint/test/build commands; do not assume it already has `npm test` or a particular framework. Backend baseline uses explicit tracing/live switches, then pytest/compile/Ruff and existing retrieval/graph regressions. Record each command's exit code separately. Paid provider tests are opt-in, bounded and never required for ordinary untrusted PR CI. Cross-repo deploy evidence records both commits, frontend deployment URL, backend image digest/revision and the tested contract.

## Exact companion-source reading map

These are scoped docs readings, not a requirement to complete entire courses. Framework versions/imports must match the installed manifests at day kickoff.

- Day 26: [Next.js, Static Exports](https://nextjs.org/docs/app/guides/static-exports), `Supported Features` / `Unsupported Features`; [GitHub, Creating a GitHub Pages site](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site), `Creating your site`; [MCP Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), `stdio` / `Streamable HTTP`. Protocol version is reference material, not a claim about the repo's negotiated 2026-07-28 version.
- Day 27: [Next.js, Server and Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components), `When to use Server and Client Components`; [Metadata and OG images](https://nextjs.org/docs/app/getting-started/metadata-and-og-images); [W3C WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/), Keyboard / Focus Visible / Contrast (Minimum) / Reflow.
- Day 28: [Next.js, Route Handlers](https://nextjs.org/docs/app/getting-started/route-handlers), `Convention` / `Supported HTTP Methods` / `Caching`; [Environment Variables](https://nextjs.org/docs/app/guides/environment-variables), `Bundling Environment Variables for the Browser`; [FastAPI, CORS](https://fastapi.tiangolo.com/tutorial/cors/), `Origin` / `Wildcards` / `Use CORSMiddleware`; read current `src/api.py` request/response contracts and its `Honest limits`.
- Day 29: [Azure Container Apps, Authentication and authorization](https://learn.microsoft.com/en-us/azure/container-apps/authentication), `Considerations for using built-in authentication`; [Azure, Create and manage budgets](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets), `Create a budget in the Azure portal`; [Vercel Functions Limits](https://vercel.com/docs/functions/limitations), duration/memory/bundle limits for the chosen plan; [Vercel FastAPI support](https://vercel.com/docs/frameworks/backend/fastapi), `Vercel Functions`. Reuse the project's Azure/Docker/CI runbooks instead of repeating deployment tutorials.
- Day 30: [Eugene Yan, How to Interview and Hire ML/AI Engineers](https://eugeneyan.com/writing/how-to-interview/); [Hamel, Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/); existing learning-log interview answers and README/eval-report. Draft one post about retrieval/eval trade-offs and one about shipping a guarded service with honest answer-quality limits.

Source checks distinguish official hosting capabilities from recommended architecture. No pricing quote, free-tier guarantee, new domain registration or cloud mutation is part of this plan.
