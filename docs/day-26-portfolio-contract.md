# Day 26 — AI Portfolio Narrative, Design, and Launch Architecture

Date: 2026-10-26 kickoff.

Linear: HER-294 — Day 26 loop: AI portfolio narrative, design and launch architecture.

Related gate: HER-271 — Week 6 gate: live AI portfolio, ProcureRAG demo and readiness.

Primary Week 6 context: [`docs/week6-portfolio-launch-plan-2026-10-26.md`](week6-portfolio-launch-plan-2026-10-26.md). Read it before this route; it contains the evidence audit, career and credential baseline, architecture alternatives, public-demo security contract, and five-day scope.

Project rule: Juan owns implementation in both repositories, all portfolio code/design artifacts, all ProcureRAG `src/`, `tests/`, deployment, account, and spending decisions. Hermes writes this route and the learning-log evidence scaffold, then reviews, quizzes, and helps debug after Juan's serious attempt. This kickoff does not provision services, spend money, publish the site, modify the public portfolio, or write implementation code.

## Course and source target for today

**No new Boot.dev chapter today.** Day 26 converts the completed RAG/agent/service work into an evidence-backed portfolio and launch contract. Reactivate earlier learning only where it supports a truthful case-study claim.

Budget **75–100 minutes** for the required readings and audit. Record one applied decision or rejection per source in `docs/learning-log.md`; a checked box without a ProcureRAG/portfolio implication is not completion.

### Block A — canonical Week 6 context and current evidence, 20–25m

1. **Week 6 portfolio launch plan and research — 2026-10-26**
   - [`docs/week6-portfolio-launch-plan-2026-10-26.md`](week6-portfolio-launch-plan-2026-10-26.md)
   - Read the full document, especially:
     - `Outcome and positioning`;
     - `Existing portfolio audit`;
     - `Career and credential evidence update`;
     - `Minimum information architecture`;
     - `Architecture recommendation and alternatives`;
     - `Launch-critical service and security contract`;
     - `Quality gate`;
     - `Five day loops and scope control`.
   - Applied question: which Day 26 decisions unblock Day 27 without pretending that Day 28–30 implementation or deployment already exists?

2. **Canonical study-plan / Linear alignment — Week 6 gate HER-271**
   - [`docs/study-plan-linear-alignment-2026-09-09.md`](study-plan-linear-alignment-2026-09-09.md), `Week 6 gate — HER-271`.
   - Applied question: which carry-forward weaknesses must remain visible on the site and in the launch contract—especially Q091 answer completeness, caller-asserted roles, stateless approval, process-local limits, sensitive traces, and unlabeled-query evidence limits?

3. **Current ProcureRAG evidence**
   - `README.md`;
   - `docs/eval-report.md`, including the Week 5 inventory;
   - the end of `docs/learning-log.md`, especially Day 25 and its `### Next step`;
   - `src/api.py`: `ApiStatus`, `QueryRequest`, `QueryResponse`, and the `Honest limits` comments/docs;
   - `docs/test-queries.md` and `docs/corpus-v1.md` for the synthetic-data and labeled-query boundaries.
   - Applied question: which claims are demonstrated, which are local-only, which are historical/deleted, and which remain red?

### Block B — old portfolio source and inspiration, 30–40m

4. **Current rendered portfolio and repository**
   - <https://juanfpinzon.github.io/>
   - <https://github.com/juanfpinzon/juanfpinzon.github.io>, default branch `master`.
   - Inspect: `_config.yml`, `Gemfile`, `index.md`, `_layouts/default.html`, assets, current CV link, publishing settings, and all public links used by the four legacy work areas.
   - Kickoff observation: the repository is Jekyll/Minimal with no `package.json`; `Gemfile` delegates to the local gemspec; `_config.yml` still describes Juan as `Data Scientist and Machine Learning Researcher/Developer` and links a 2021 CV; `index.md` covers U-NET spine work, CS231n, resume NER, and DICOM2STL but no ProcureRAG or current production-ML/procurement narrative.
   - Applied question: what is preserved, rewritten, archived, redirected, or withheld—and why?

5. **Curated inspiration—not templates to clone**
   - [Hafsa Mrabet](https://hafsa.hechoporpersonas.com/): role-first hero, transition story, and problem/outcome project blocks. Borrow hierarchy and narrative clarity; avoid unsupported absolutes and animation-dependent core content.
   - [Eugene Yan](https://eugeneyan.com/): short role/value statement and clear Writing, Speaking, Prototyping, and About routes. Borrow fast navigation plus deeper evidence.
   - [Hamel Husain](https://hamel.dev/): evaluation-led applied-AI positioning. Borrow honest failure analysis and measurable evidence, not reputation by association.
   - [Chip Huyen](https://huyenchip.com/): human story plus concise production-AI focus, public tools, research, and writing. Borrow continuity between experience and current direction.
   - [Shreya Shankar](https://www.sh-reya.com/): concise research/engineering narrative linking projects, papers, GitHub, and CV. Borrow evidence linkage without turning the site into an academic directory.
   - Applied question: choose one concrete pattern to borrow and one to reject from each reference.

### Block C — hosting and integration boundaries, 25–35m

6. **Next.js — `Static Exports`**
   - <https://nextjs.org/docs/app/guides/static-exports>
   - Read the exact sections `Supported Features` and `Unsupported Features`.
   - Required takeaway: a static export can emit HTML/CSS/JS and build-time data, but dynamic request-dependent server behavior is not available. Static-export route handlers support build-time `GET`, not a runtime chat `POST`; default `next/image` optimization also needs a server or custom loader.
   - Applied question: why can a static portfolio live on GitHub Pages while a credential-holding chat BFF cannot?

7. **GitHub Pages — `Creating a GitHub Pages site`**
   - <https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site>
   - Read `Creating your site`, including publishing source, entry-file placement, Actions/static-generator options, and public-data warning.
   - Required takeaway: Pages serves static artifacts and does not provide a Python or runtime POST backend. A Next.js static export is possible through a build workflow, but it still needs a separate secure gateway for chat.

8. **MCP Specification 2025-11-25 — `Transports`**
   - <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>
   - Read `stdio` and `Streamable HTTP`, including stdout/stderr rules and Streamable HTTP origin/authentication guidance.
   - This protocol version is reference material; it is not a claim about ProcureRAG's measured `2026-07-28` negotiation.
   - Required takeaway: the existing MCP adapter is a local host-managed stdio integration. A browser form should use HTTP through the guarded service/BFF; exposing remote MCP would add a separate network/auth/session problem without helping this web demo.

## Day 26 objective

By the end of Day 26, Juan should be able to answer:

> “What evidence supports my experienced-ML-to-LLM narrative, what belongs on the recruiter path versus the technical path, what will the Day 27 portfolio preview actually contain, why is the recommended browser architecture Next.js/BFF over the existing Python service rather than static Pages or MCP alone, and what public-data, identity, cost, timeout, and quality decisions must be fixed before any paid/public deployment?”

The artifact is a **content, design, architecture, and safety contract**, not a theme implementation. Day 27 should begin with decisions rather than unresolved biography, unverified metrics, or an unsafe chat boundary.

## Starting state

### ProcureRAG at kickoff

```text
date: 2026-10-26
branch: main
commit: 44a21c7 (Merge pull request #12 from juanfpinzon/week-6-planning)
git status: clean and synchronized with origin/main
Python target: >=3.11
live LLM: forced off for baseline
LangSmith tracing: forced off for baseline
```

Fresh deterministic baseline:

```text
uv sync --locked --dev: 154 packages resolved, 146 checked
uv lock --check: clean
pytest: 438 passed in 9.70s
compileall src tests scripts: clean
Ruff src tests scripts: All checks passed!
frozen fixture regression: 7/7 as expected, exit 0
current retrieval verification: 6 x [OK], exit 0
graph regression: 6/6 contracts passed, 4 counted stand-in LLM calls, exit 0
git diff --check: clean
git status --short: clean
```

The current retrieval pipeline still matches the frozen expectations. Q091's deterministic row still records a term-level `Band 3` gap, while Day 24's live generation evidence remains red because the answer omitted the recovered `usage data` step. Do not turn either fact into a blanket answer-accuracy claim.

### Existing portfolio baseline

The live portfolio and `juanfpinzon/juanfpinzon.github.io` `master` branch currently provide:

- Jekyll `jekyll-theme-minimal`, not Next.js;
- no Node manifest or TypeScript build contract yet;
- a 2021 CV download and dated title/description;
- substantial historical U-NET spine, CS231n, resume NER, and DICOM2STL material;
- no ProcureRAG flagship case study, current production-ML/procurement experience, course-award section, or live-demo architecture;
- known copy/evidence work: `100,000 thousand`, paper/dataset year/count consistency, contribution/ownership boundaries, and private medical-data restrictions.

The supplied August 2026 CV and two course-award images are evidence inputs, not yet public assets. They remain outside the public repositories. Day 26 must define an approved handoff rather than silently publishing attachments.

### Week 5 handoff to preserve

- HER-270 and all five children are Done in Linear.
- FastAPI, Docker, a real but deleted Azure deployment, eval-gated CI/CD, rollback, and local stdio MCP were exercised.
- Nothing is currently live.
- The browser-facing service should reuse `QueryRequest`, `QueryResponse`, and the guarded application boundary.
- Six domain statuses exist: `answered`, `model_declined`, `gap_report`, `not_generated`, `blocked`, `pending_approval`.
- Source references are IDs and citation flags—not snippets or public URLs.
- Free text has no trustworthy gold `query_id`; its evidence completeness is not diagnosed.
- Current roles are caller-asserted, approvals are stateless/unattributed, quotas are process-local, and raw traces may be sensitive.

## Key concepts to nail today

### 1. The portfolio story starts from demonstrated continuity, not a career reset

Juan already has production ML, Azure/PySpark, forecasting, research, and procurement-domain experience. ProcureRAG should show a deliberate extension into retrieval, evaluation, bounded agents, serving, deployment, and MCP. The site must keep actual employer titles separate from a target-role headline and must not turn recent RAG coursework into invented years of LLM experience.

The recommended draft positioning is:

> ML/AI engineer with production forecasting and procurement experience, building evidence-driven RAG and agentic applications.

Juan may revise that wording, but the final narrative must preserve the same evidence hierarchy: experience and shipped/reproducible work first; course-completion credentials support the story rather than leading it.

### 2. A fast recruiter path and a deep technical path serve different questions

The recruiter path should answer in under a minute: who Juan is, target role, strongest experience, flagship project, selected earlier work, location/contact/CV, and whether a working demo exists.

The technical path should answer: what Juan personally built, architecture and trade-offs, benchmark/corpus/cutoff methodology, evals and failure analysis, safety boundaries, reproducibility, limitations, and next roadmap. A metric such as `P@1=0.978` is retrieval-ranking precision on a named benchmark—not 97.8% answer accuracy.

### 3. Content inventory is an evidence and permissions exercise

For each legacy item, record:

- keep, rewrite, archive, or remove;
- Juan's actual contribution and ownership boundary;
- public evidence links and current link status;
- data/asset sharing permission;
- factual corrections and source;
- which recruiter/technical question it answers.

The medical project must not expose private images/data or imply a deployed clinical product. The NER work should retain the honest non-production result and link the 2020 journal record plus the repository README's documented 545-CV dataset. DICOM2STL should distinguish Juan's code contribution from ownership of the whole product. CS231n remains useful foundational evidence but should not compete with ProcureRAG or production experience.

### 4. Static frontend, runtime BFF, and Python service are separate trust boundaries

Recommended Day 26 decision to confirm:

```text
Browser portfolio
  -> same-origin TypeScript BFF
     validates shape, enforces public demo policy, reserves quota, holds service credential
  -> authenticated ProcureRAG FastAPI
     runs existing guards, role/data policy, retrieval, bounded graph, optional LLM
  <- QueryResponse-shaped safe result
<- validated UI state and reviewed source references

Local AI host
  -> existing stdio MCP adapter
  -> same guarded ProcureRAG service
```

A BFF does not automatically secure an unauthenticated upstream. The Python API must reject direct unauthenticated public calls before retrieval. CORS is not authentication. Browser code must never receive provider or upstream credentials.

### 5. Public demo policy must be server-owned and least-privileged

Day 26 must decide the public synthetic-data allowlist and role behavior. Do not put a role picker in the browser and trust it. Do not expose `approve`/`edit` decisions anonymously or auto-approve a recursive step. `pending_approval` stays fail-closed in public mode; privileged HITL remains a local/reviewer flow unless a later authenticated, attributable design replaces it.

Exact presets may carry a server-owned `query_id` only when the text matches the labeled question. Edited/free text must omit it. The UI must preserve all six domain statuses and separately handle validation, throttling, timeout, and unavailable HTTP outcomes.

### 6. Cost controls and quality gates are launch requirements, not polish

Before a paid/public call, the contract needs:

- a Juan-approved numeric cloud and LLM ceiling;
- a persistent atomic global quota reservation and in-flight cap;
- trusted client metadata for any client limit;
- input/body/output/time/retry bounds;
- a fail-closed quota-store policy;
- a tested kill switch;
- scale-to-zero versus warm-capacity decision based on measured end-to-end latency;
- sanitized logs/traces and a retention statement.

Azure budgets alert; they do not stop spending. A disconnected browser does not prove provider work stopped. A healthy API, `not_generated` response, or valid citation does not prove a correct generated answer.

## Artifact contract Juan should design before implementation

Create these in the portfolio repository, or record clearly justified equivalent paths:

1. `docs/portfolio-content-inventory.md`
   - legacy migration/permission table;
   - career/CV/site/accessible-LinkedIn fact crosswalk;
   - publication and dataset corrections;
   - course-award scope and asset/publication decision;
   - evidence links, owners, approval state, and unresolved gaps.

2. `DESIGN.md`
   - chosen visual direction and design tokens;
   - mobile and desktop wireframe;
   - minimum information architecture;
   - recruiter versus technical navigation;
   - accessibility and reduced-motion rules;
   - content fallback if JavaScript or chat is unavailable.

3. `docs/adr/portfolio-demo-architecture.md`
   - status and owner;
   - accepted architecture and rejected alternatives;
   - repository/hosting boundaries;
   - browser → BFF → API contract;
   - public synthetic-data/role policy;
   - upstream authentication and secret boundary;
   - quota/budget/timeout/kill-switch/logging decisions;
   - scale/cold-start strategy;
   - migration/old-URL/rollback policy;
   - open decisions that block provisioning.

4. A small **no-paid contract probe**, owned by Juan
   - use a fake/injected service or existing no-live mode;
   - validate one typed browser/BFF request shape against the current `QueryRequest`/`QueryResponse` contract;
   - record the six status mappings plus 422/429/timeout/unavailable UI states;
   - prove free text omits `query_id`, presets map exact text server-side, and sources remain IDs only;
   - make no provider call and no public deployment.

Do not build the Day 27 UI today unless all four contracts are complete and Juan intentionally records the scope advance.

## Target evidence checklist

### Evidence and narrative

- [ ] The Week 6 plan and alignment are read, with carry-forward weaknesses listed.
- [ ] All four legacy areas are triaged: U-NET spine, resume NER/publication/dataset/notebooks, DICOM2STL, and CS231n.
- [ ] Each legacy item records contribution, public evidence, permissions, stale links, and keep/rewrite/archive decision.
- [ ] The NER record uses journal Vol. 65 (2020) and the repository's documented 545-CV wording.
- [ ] The market/time-series work is labeled `AGI 2022 proceedings (published 2023)` with the 2022 preprint where used.
- [ ] `100,000 thousand` and any other uncertain numeric claim are flagged for Juan confirmation, not silently guessed.
- [ ] The August 2026 CV is the career baseline; post-August changes and public-safe employer wording are confirmed or explicitly pending.
- [ ] Actual employer titles, employer-versus-personal-project separation, and target-role headline are unambiguous.
- [ ] CV `7 years` versus accessible LinkedIn `5+ years` has approved scope/as-of wording or a named blocker.
- [ ] Boot.dev RAG and Hugging Face MCP Unit 1 awards have exact issuer/title/date/scope; no invented issuer verification URL or completed Azure certification.
- [ ] ProcureRAG is framed as an independent synthetic-data procurement-intelligence copilot learning project, not an employer deployment or PDF chatbot.

### Design and information architecture

- [ ] One visual direction is selected, with tokens and rejected alternatives.
- [ ] Mobile and desktop wireframes cover home, ProcureRAG case study/demo, selected work/research, experience/about, small credentials section, CV, GitHub, LinkedIn, and contact.
- [ ] Recruiter and technical paths are both clear.
- [ ] Core content works without animation and respects reduced motion, keyboard/focus, contrast, and reflow expectations.
- [ ] The Day 27 preview scope is explicit; bilingual duplication, custom domain, 3D, and elaborate motion remain stretch/cut-first.

### Architecture and public-demo contract

- [ ] ADR compares Next.js/Vercel+BFF+Azure, static Pages+gateway, and single-container fallback.
- [ ] Accepted route names repository boundaries, owner accounts, region, migration/old-URL policy, runtime timeout, and rollback/fallback.
- [ ] Browser uses HTTP; local stdio MCP remains separate; remote MCP is deferred.
- [ ] Provider/upstream secrets stay server-side and the backend rejects direct unauthenticated public query/stream calls.
- [ ] Public synthetic corpus allowlist and fixed least-privileged policy are recorded; there is no role picker or anonymous approval path.
- [ ] Preset versus free-text `query_id` behavior is recorded.
- [ ] All six domain statuses plus 422/429/timeout/unavailable are mapped to honest UI states.
- [ ] Source-ID-only behavior is explicit; no invented snippets, file URLs, or trace links.
- [ ] JSON `/query` is the first vertical slice; progress SSE is stretch and not called token streaming.
- [ ] Persistent atomic quota, concurrency, body/input/output/retry/timeout, owner, retention, kill-switch, and fail-closed decisions are recorded.
- [ ] Juan approves numeric cloud/LLM ceilings before provisioning or paid smoke, or the blocker is explicit.
- [ ] Scale-to-zero versus warm-capacity decision accounts for the measured prior 59–72 second Azure cold start and actual BFF timeout.
- [ ] Q091 is either withheld/guarded in the planned public experience or assigned an evidence-backed repair gate; a disclaimer is not treated as a fix.

### Evidence and explanation

- [ ] The no-paid local contract probe runs and records command, exit code, request/response shape, and limitations.
- [ ] No public deployment, provider call, account change, or unapproved publication occurs during Day 26.
- [ ] The learning log contains real outputs or explicit blockers, not success-shaped TODO replacements.
- [ ] Juan gives a 15–20 minute no-notes architecture explanation and answers the interview drill.

## Recommended 6-hour split

### Block 0 — Reactivate the evidence baseline, 25–30m

- Read HER-294, the Week 6 plan, this route, and Day 25's final `### Next step`.
- Confirm ProcureRAG branch/status and compare the fresh gate output with the kickoff baseline above.
- Inspect the current portfolio repository/default branch and rendered site; do not assume a Node/Next.js manifest exists.
- Write three sentences: strongest existing evidence, most dangerous public overclaim, and the decision Day 26 must settle before Day 27.

### Block 1 — Exact readings and old-site audit, 75–100m

- Complete Blocks A–C above. DONE.
- Record one applied takeaway/rejection per source.
- Check every current portfolio destination used by the four legacy areas.
- Do not clone a reference site's identity, copy, or unsupported claims.

Minimum reading stop condition:

- explain what static export/Pages can and cannot host;
- explain why browser HTTP/BFF and local MCP are separate integrations;
- name the current portfolio's actual stack and default branch;
- name the evidence/permission work for all four legacy areas;
- identify the Week 5 caveats that constrain public launch.

### Block 2 — Content/evidence contract, 55–65m

Build the inventory and crosswalk before writing polished marketing copy:

1. legacy item decision table;
2. career chronology and public-safe wording;
3. publications/dataset/certificate facts and source strength;
4. ProcureRAG evidence claims and explicit limitations;
5. asset/publication permissions and owner;
6. unresolved questions for Juan, each with a blocking/non-blocking label.

Select one hero/value proposition draft and one shorter alternative. Both should reflect production ML and procurement continuity, not a beginner reset.

### Block 3 — Wireframe and design contract, 50–60m

- Choose one visual direction and token set.
- Draw mobile and desktop information hierarchy.
- Separate recruiter and technical paths.
- Decide where experience, ProcureRAG, earlier work/research, credentials, CV/contact, and the chat entry point appear.
- Define no-JS/chat-down behavior and accessibility constraints.
- Do not implement the full interface today.

### Block 4A — Hosting/security ADR and no-paid probe, 80–95m

- Compare the three architecture options with evidence.
- Record the accepted route and rejected alternatives.
- Resolve or assign every public-data, role, auth, secret, quota, budget, timeout, cold-start, logging, retention, and kill-switch decision.
- Map the API contract and UI states.
- Run the smallest no-paid local contract probe; record what it proves and does not prove.

### Block 4B — fallback if decisions or assets block, 45–60m

A legitimate fallback is:

- complete inventory, crosswalk, IA, wireframe, and architecture options;
- identify every unresolved decision, owner, deadline, and downstream block;
- finish the no-paid probe;
- choose the simplest viable provisional Day 27 preview route;
- do not provision, publish unapproved biography/assets, or claim launch readiness.

This is useful Day 26 progress, but unresolved launch-critical auth/data/budget decisions remain blockers for Day 28–29.

### Block 5 — Evidence, explanation, and handoff, 30–40m

- Replace every Day 26 TODO with evidence or an explicit blocker.
- Record artifact paths and exact probe/gate commands.
- Give the no-notes architecture explanation.
- Answer the interview drill.
- Send the review prompt below. Do not move HER-294 to Done before review.

## Baseline and review commands

From the ProcureRAG root:

```bash
export PROCURERAG_LIVE_LLM=0
export LANGSMITH_TRACING=false
export LANGSMITH_TRACING_V2=false
export DEEPEVAL_TELEMETRY_OPT_OUT=1
export OMP_NUM_THREADS=1

uv sync --locked --dev
uv lock --check
uv run pytest -q
uv run python -m compileall -q src tests scripts
uv run python -m ruff check src tests scripts
uv run python src/regression_suite.py
HF_HUB_OFFLINE=1 uv run python src/regression_suite.py --verify-retrieval
HF_HUB_OFFLINE=1 uv run python src/graph_regression.py
git diff --check
git status --short
```

Record each command and exit code separately. `HF_HUB_OFFLINE=1` is valid only when model artifacts are already cached; a missing cache is an infrastructure blocker, not a pass.

In the portfolio repository, inspect the actual post-decision manifest and lockfile before naming commands. The kickoff repository has no `package.json`, so do not invent `npm test`, `npm run lint`, or a framework build as existing gates. Once Juan creates the Day 27 scaffold, record its real install, typecheck, lint, test, and build commands.

A live provider smoke is out of scope for Day 26 unless Juan explicitly opts in after approving numeric budget and timeout/output bounds. Fake and `not_generated` results do not prove live generation.

## Interview drill

1. **What is the one-sentence portfolio narrative, and what evidence supports it?**
   - Expected answer shape: experienced production ML plus procurement-domain experience extending into evidence-driven RAG/agent engineering; cite production forecasting/Azure/PySpark, research/publications, and the measured ProcureRAG progression without inventing employer deployment or years of LLM experience.

2. **Why lead with experience and projects rather than course certificates?**
   - Expected answer shape: certificates show structured learning, while roles, artifacts, measurements, failures, code, and reproducible evidence demonstrate applied capability. The awards are accurately scoped supporting evidence.

3. **What is the difference between the recruiter path and the technical path?**
   - Expected answer shape: recruiter path gives role/value, strongest experience, flagship, selected work, CV/contact quickly; technical path explains ownership, architecture, methods, evals, failure analysis, trade-offs, reproducibility, and limits.

4. **Why recommend Next.js/Vercel with a BFF instead of only GitHub Pages?**
   - Expected answer shape: Pages/static export can host the portfolio UI but not a runtime credential-holding POST handler. A BFF keeps secrets server-side, validates requests, and enforces quota/policy before the Python service. Static Pages remains possible with a separate gateway.

5. **Why use HTTP for browser chat rather than the existing MCP server?**
   - Expected answer shape: the browser needs an application HTTP contract; existing MCP is local stdio for AI hosts and has no browser-callable endpoint. Remote MCP would add host/protocol/auth/session/deployment work and does not replace the guarded API.

6. **Why is a BFF secret not enough to secure ProcureRAG?**
   - Expected answer shape: an attacker can bypass the BFF if the upstream remains public and unauthenticated. The backend must verify service identity/credentials before retrieval; CORS is not authentication; credentials must never enter browser bundles.

7. **How do exact presets differ from free text?**
   - Expected answer shape: an exact approved preset can map server-side to its real labeled `query_id`; edited/free text omits the id because the current graph cannot infer its gold evidence completeness. Never attach a convenient gold id to different text.

8. **Which API outcomes must the UI preserve?**
   - Expected answer shape: `answered`, `model_declined`, `gap_report`, `not_generated`, `blocked`, and `pending_approval`, plus validation, throttling, timeout, and unavailable transport outcomes. Do not collapse them all into a successful answer bubble.

9. **Why are citation validity and answer quality separate?**
   - Expected answer shape: a citation may point to a real retrieved source while the answer omits or misstates the needed claim. Q091 is the concrete example; valid plumbing or citations do not prove complete procurement advice.

10. **What makes the public synthetic-data policy least-privileged?**
    - Expected answer shape: server-owned approved subset/role, no browser role picker or privilege escalation, no anonymous approvals/writes/uploads, fail-closed pending state, and explicit disclosure that the corpus is synthetic.

11. **Why does an Azure budget not cap spend?**
    - Expected answer shape: it alerts rather than atomically refusing requests. A launch needs persistent global/in-flight quota reservations, provider/output/time/retry bounds, replica limits, and a tested kill switch.

12. **What must remain visibly incomplete after Day 26?**
    - Expected answer shape: no TypeScript preview, secured vertical slice, persistent deployment, public launch, or current live-generation proof exists yet; Q091 quality and identity/HITL/quota/trace limitations remain. Day 26 supplies decisions and contracts, not implementation evidence.

## Hermes review protocol

When Juan sends the review prompt, Hermes will:

1. read the content inventory, design contract/wireframe, architecture ADR, probe evidence, and completed Day 26 learning-log entry;
2. verify career, publication, dataset, credential, project-ownership, and employer-versus-personal claims against the cited evidence;
3. inspect the old-site migration table for all four required legacy areas, permissions, stale links, and unresolved numeric copy;
4. check that the visual/IA contract gives experience and ProcureRAG appropriate hierarchy and remains accessible without animation/chat;
5. challenge the accepted architecture against the rejected alternatives and actual static/runtime capabilities;
6. trace browser → BFF → API trust boundaries, public role/data policy, preset/free-text handling, status/source mapping, and direct-upstream refusal;
7. verify budget/quota/timeout/kill-switch/logging/cold-start decisions are concrete or honestly blocking;
8. reproduce the no-paid contract probe and rerun ProcureRAG deterministic gates;
9. distinguish planning/probe evidence from unbuilt UI, paid generation, and deployment evidence;
10. quiz Juan on the twelve questions above without rewriting either repository's implementation.

## Review prompt to send Hermes

> “Day 26 portfolio contract is ready. Please review the legacy evidence migration, supplied August CV/accessible LinkedIn/certificate reconciliation, production-ML/procurement-to-LLM narrative, design/wireframe, hosting ADR, public synthetic-data/role policy, secret/auth/cost boundaries, exact API status/source contract and no-paid probe. Reproduce the deterministic gates and quiz me on HTTP versus MCP and deployment trade-offs. Juan owns implementation.”

## Stop condition

Day 26 is ready for review only when:

1. the four legacy areas have evidence/permission/migration decisions;
2. the career, publication, dataset, certificate, ownership, and ProcureRAG claims have a source-backed crosswalk with unresolved items named;
3. one visual direction and mobile/desktop information architecture are selected;
4. a status-bearing ADR chooses the hosting/integration route and records rejected alternatives;
5. public synthetic-data, role, upstream auth, secret, quota, budget, timeout, cold-start, logging/retention, and kill-switch decisions are fixed or explicitly blocking;
6. all six API statuses, source-ID-only behavior, exact presets, free text, and error states are mapped;
7. the no-paid local contract probe is reproducible and the deterministic baseline remains green;
8. the learning log contains no false-complete TODOs;
9. Juan can deliver the 15–20 minute explanation and answer the interview drill without notes;
10. no public deployment, paid call, unapproved biography/asset publication, or implementation by Hermes occurred.

Do not close HER-294 on route creation or baseline gates alone. First complete the Juan-owned artifacts, send the review prompt, and pass review. Day 27 then turns the approved contract into a responsive TypeScript portfolio preview.