# Day 27 — Responsive TypeScript Portfolio Preview and ProcureRAG Case Study

Date: 2026-10-26 kickoff.

Linear: HER-295 — Day 27 loop: responsive portfolio preview and ProcureRAG case study.

Related gate: HER-271 — Week 6 gate: live AI portfolio, ProcureRAG demo and readiness.

Primary context:

- [`docs/week6-portfolio-launch-plan-2026-10-26.md`](week6-portfolio-launch-plan-2026-10-26.md);
- [`docs/day-26-portfolio-contract.md`](day-26-portfolio-contract.md);
- the accepted portfolio contracts on `juanfpinzon/juanfpinzon.github.io` branch `0ct26-overhaul`:
  - `DESIGN.md`;
  - `docs/portfolio-content-inventory.md`;
  - `docs/adr/portfolio-demo-architecture.md`.

Project rule: Juan owns every portfolio implementation decision and every code, test, asset, deployment, account, and spending change in both repositories. Hermes writes this route and the learning-log evidence scaffold, then reviews, quizzes, and helps debug after Juan's serious attempt. Hermes does not write the TypeScript/React preview or any ProcureRAG `src/*.py` / `tests/test_*.py` implementation.

Day boundary: Day 27 builds the **responsive content and case-study preview**. It does not build the BFF, live chat, upstream authentication, persistent quota, Azure/Vercel production chain, or legacy-site cutover assigned to Days 28–30.

## Course and source target for today

**No new Boot.dev chapter today.** Day 27 is the product/interface layer that presents the evidence already built and reviewed. Reactivate prior ProcureRAG learning only to explain it accurately.

Budget **45–60 minutes** for the required readings. Record one applied implementation or rejection per source in `docs/learning-log.md`; checking a page without applying it does not complete the reading block.

### Source A — accepted Day 26 contracts, 15–20m

Read these completely before scaffolding the application:

1. Portfolio `DESIGN.md` - READ
   - exact visual tokens;
   - three-route information architecture;
   - recruiter and technical paths;
   - mobile/desktop wireframes;
   - WCAG 2.2 AA contract;
   - static Day 27 demo placeholder;
   - cut-first list.
2. Portfolio `docs/portfolio-content-inventory.md` - READ
   - approved career wording and employer separation;
   - evidence-strength labels;
   - legacy-project migration decisions;
   - exact publication/dataset/course-credential wording;
   - corrected CV and asset permissions;
   - remaining non-blocking questions.
3. Portfolio `docs/adr/portfolio-demo-architecture.md` - READ
   - repository and branch boundary;
   - Day 27 versus Day 28–30 scope;
   - accepted Next.js/Vercel direction;
   - no-live-chat and old-URL rules.

Applied question: what can the preview truthfully render today, and what must still say `in progress`, `historical/deleted`, `local only`, `unchecked`, or `not live`?

### Source B — Next.js `Server and Client Components`, 10–15m

Official page: <https://nextjs.org/docs/app/getting-started/server-and-client-components>

Read the exact section **`When to use Server and Client Components?`**, then the sections covering the `use client` boundary and reducing client JavaScript. - READ

Required takeaway:

- App Router pages and layouts are Server Components by default.
- Use Client Components only where state, event handlers, effects, custom hooks, or browser APIs are actually needed.
- A `use client` boundary pulls its imported module graph into the client bundle; putting it at the page/layout root sends unnecessary JavaScript.
- Day 27's pages are mostly static evidence and should remain server-rendered/pre-rendered. The static demo explanation needs no client component today; Day 28 can introduce the smallest interactive island for chat.

Applied decision to record: which Day 27 components, if any, genuinely need `use client`, and why? `None yet` is a valid and likely answer.

### Source C — Next.js `Metadata and OG images`, 10–15m

Official page: <https://nextjs.org/docs/app/getting-started/metadata-and-og-images>

Read the exact sections: - READ

- **`Static metadata`**;
- **`Generated metadata`** only to understand when it is unnecessary;
- **`File-based metadata`**, especially favicon, Open Graph image, `robots.txt`, and sitemap conventions.

Required takeaway:

- Static page titles and descriptions belong in the typed metadata API on Server Components.
- Day 27's three known routes do not need dynamic metadata fetching.
- Share images and icons are build artifacts with public claims; they must not imply a live demo, enterprise deployment, or answer-accuracy result that does not exist.

Applied decision to record: route title/description, canonical/share-image policy for the preview, and which file-based metadata artifacts are included or deliberately deferred.

### Source D — W3C `How to Meet WCAG 2.2`, 15–20m

Official quick reference: <https://www.w3.org/WAI/WCAG22/quickref/> - READ

Read and apply these exact Level A/AA criteria:

- **1.1.1 Non-text Content** — meaningful alternatives; empty alternatives for decoration;
- **1.4.3 Contrast (Minimum)** — text contrast;
- **1.4.10 Reflow** — no page-level two-dimensional scrolling at the required narrow/zoom view;
- **2.1.1 Keyboard** — every function available from a keyboard;
- **2.4.7 Focus Visible** — keyboard focus is visible;
- **2.5.8 Target Size (Minimum)** — minimum target sizing or a documented exception.

Required takeaway: accessibility is measured behavior, not a Lighthouse badge or a list of ARIA attributes. Verify DOM order, landmarks, heading order, skip link, keyboard navigation, focus ring, link purpose, image alternatives, table overflow, reduced motion, and reflow at actual viewports/zoom.

## Day 27 objective

By the end of Day 27, Juan should be able to answer:

> “How did I turn the approved evidence contract into a responsive, accessible TypeScript portfolio where a recruiter can understand my production-ML-to-RAG story in under a minute, a technical interviewer can inspect ProcureRAG's architecture, measurements, failures, and limits, and neither path implies that the Day 28–30 live chat or deployment already exists?”

The artifact is a reproducible local or preview-deployed **portfolio preview** with three routes, accurate content, a current CV path, verified links, production build evidence, and a three-minute walkthrough.

## Starting state

### ProcureRAG at kickoff

```text
date: 2026-10-26
branch/head: day-26 @ b2ca157
remote sync: origin/day-26, divergence 0/0
working tree before scaffold: clean
Python target: >=3.11
live LLM: forced off
LangSmith tracing: forced off
```

Fresh deterministic baseline:

```text
uv sync --locked --dev: 154 packages resolved, 146 checked, exit 0
uv lock --check: clean, exit 0
pytest: 452 passed in 14.78s, exit 0
compileall src tests scripts: clean, exit 0
Ruff src tests scripts: All checks passed!, exit 0
frozen fixture regression: 7/7 as expected, exit 0
current retrieval verification: 6/6 [OK], exit 0
graph regression: 6/6 contracts, 4 stand-in LLM calls, exit 0
no-paid portfolio contract probe: 19/19 scenarios + 2/2 checks, 0 failures, exit 0
git diff --check: clean, exit 0
```

The baseline used:

```text
PROCURERAG_LIVE_LLM=0
LANGSMITH_TRACING=false
LANGSMITH_TRACING_V2=false
DEEPEVAL_TELEMETRY_OPT_OUT=1
OMP_NUM_THREADS=1
```

No provider call or trace upload ran. Q091 remains a known answer-completeness failure; its frozen deterministic row also retains the `Band 3` term-level gap. Nothing is currently deployed.

### Portfolio at kickoff

Read-only audit of pushed branch `origin/0ct26-overhaul`:

```text
branch/head: 0ct26-overhaul @ 76c719e
remote sync: divergence 0/0
working tree in the audit clone: clean
live branch: master @ legacy Jekyll site; unchanged during Day 27
current stack: Jekyll / jekyll-theme-minimal
Node manifest: none
Node lockfile: none
Next.js application: not built
```

Accepted Day 26 inputs already present on `0ct26-overhaul`:

- `DESIGN.md` — editorial-light tokens, wireframes, IA, accessibility contract;
- `docs/portfolio-content-inventory.md` — approved evidence/copy/permissions;
- `docs/adr/portfolio-demo-architecture.md` — accepted architecture and day boundaries;
- `docs/JuanFernandoPinzon_CV_Oct2026.pdf` and semantic HTML source;
- `assets/img/pic-juan.png` — approved source photo requiring a deliberate head-and-shoulders crop and optimization.

Important branch rule: create the Day 27 implementation branch from the accepted `0ct26-overhaul` head, not from stale `master`. Keep `master` publishing the legacy Jekyll site until Day 30 migration checks pass. Do not run a scaffolder blindly against the non-empty repository; inspect its proposed overwrites and preserve the accepted contracts/CV/assets.

## Key concepts to nail today

### 1. The content hierarchy is the product

The homepage should answer the recruiter questions in one scroll:

1. Who is Juan and what role is he targeting?
2. What production ML and procurement evidence supports that direction?
3. What is ProcureRAG, what did Juan personally build, and what is demonstrably measured?
4. Which earlier research and engineering artifacts are worth opening?
5. Where are the current CV and contact links?

Do not invert this hierarchy into a certificate wall, framework-logo grid, or generic `AI engineer` hero. Experience and reproducible work lead; course awards support them.

### 2. The case study must separate evidence lanes

The ProcureRAG page should visibly distinguish:

- **demonstrated and reproducible:** retrieval ranking on the named 34-document/93-query synthetic benchmark, tests, deterministic regressions, eval-gated CI;
- **demonstrated locally:** bounded graph, guardrails/HITL, FastAPI, container, local stdio MCP;
- **historical/deleted:** the prior Azure deployment and rollback exercise;
- **red or limited:** Q091 live-answer completeness, caller-asserted roles, stateless approval, process-local limits, free-text evidence gaps, source IDs without snippets/URLs;
- **not built yet:** public BFF/chat, authenticated upstream, persistent quota, current hosted service.

`P@1 = 0.978` is retrieval-ranking precision at a stated cutoff, not answer accuracy. `430+ tests` is a stable summary; the exact current count should appear only with a commit/date.

### 3. Server-first keeps the preview honest and light

The Day 27 content is static. Use Server Components and pre-rendered routes by default. Do not mark the root layout or whole pages `use client` for a mobile menu, theme toggle, or future chat that is not in scope. If a small interaction is necessary, isolate it at the lowest practical boundary and verify that the static content remains visible without JavaScript.

The static demo section is explanatory content only: approved example questions, synthetic-data disclosure, known states/limitations, and `Live demo: in progress`. It must not simulate an answer, call ProcureRAG, or imply that the BFF exists.

### 4. Responsive and accessible are tested properties

A desktop screenshot is not evidence of responsive behavior. Verify at minimum:

- 320 px and 375 px widths;
- a representative tablet/intermediate width;
- 1280 px and 1440 px widths;
- 400% browser zoom or the equivalent 320 CSS px reflow condition;
- keyboard-only navigation from the address bar through skip link, header, every link/control, and footer;
- visible focus, sensible DOM order, landmarks, heading order, descriptive link text, image alternatives, reduced motion, and no page-level horizontal overflow.

Wide metric tables may scroll inside a named, keyboard-focusable region; the page itself must not scroll sideways.

### 5. The preview must preserve the live-site migration boundary

Day 27 can produce a local production build and, if Juan has approved account access, a non-production preview URL. It does not replace the live Jekyll `master` site, alter Pages publishing, buy a domain, or rewrite the old CV URL.

A preview deployment is evidence only if its URL and exact commit are recorded. A local build is still useful and can pass Day 27 if preview access is blocked, but the blocker must be explicit and Day 30 launch remains open.

## Artifact contract Juan should build himself

Build the preview in the portfolio repository on a new Day 27 branch from `origin/0ct26-overhaul`.

### A. Reproducible TypeScript application baseline

The branch should have:

- a TypeScript/React framework manifest matching the accepted Next.js App Router decision, or an explicitly documented fallback approved from the ADR;
- exactly one package-manager lockfile;
- a recorded Node runtime/version policy;
- real scripts for development, typecheck, lint, test, and production build;
- no credentials or public environment-variable placeholders that look like real secrets;
- the accepted Day 26 docs, CV, and inventory retained.

Record the exact scaffolding command and framework/package-manager versions after creation. The kickoff repository has no Node manifest, so this route does not fabricate commands as if they already exist.

### B. Three preview routes

1. `/` — recruiter path
   - selected hero and supporting line;
   - Barcelona and truthful `since 2019` / production-since-2022 framing;
   - three-row experience summary;
   - flagship ProcureRAG card with methodology-labeled chips;
   - NER, market/time-series, DICOM2STL, and U-NET cards plus CS231n archive line;
   - two exactly scoped course-credential lines;
   - CV, GitHub, LinkedIn, and email links;
   - `Live demo: in progress`, not a fake `Try demo` success path.
2. `/procurerag` — technical path
   - problem and intended users;
   - personal ownership and synthetic-data/employer separation;
   - retrieval → evaluation → bounded graph → guardrails/HITL → API/container/Azure/CI/MCP progression;
   - architecture diagram plus text alternative;
   - metric table with benchmark, cutoff, date/commit, and reproduction links;
   - Q091 failure and the current security/identity/quota/free-text/source limitations;
   - static demo explanation and approved presets, clearly non-live;
   - reproduction links/commands and roadmap.
3. `/about` — complete context
   - CV-sourced experience chronology and education;
   - procurement roots and ML research continuity;
   - publication/research links;
   - credentials subordinate to experience/projects;
   - current CV/contact.

### C. Asset and metadata baseline

- Serve the corrected October 2026 CV at `/cv.pdf` or an equally stable documented route.
- Create an intentional head-and-shoulders crop from `assets/img/pic-juan.png`; optimize it rather than merely converting the 1.9 MB source.
- Keep approved text-only course credentials; do not publish the private certificate images or invent issuer verification links.
- Use semantic HTML and truthful static metadata for each route.
- Add only share/OG imagery whose visible claims are true for Day 27. No `Live demo`, answer-accuracy, employer endorsement, or enterprise-readiness implication.
- Preserve source/license credit for DICOM2STL and employer-versus-independent-project boundaries.

### D. Evidence and test baseline

Choose a small test strategy appropriate to the actual scaffold. At minimum, evidence should catch:

- all three routes building/rendering;
- navigation and the corrected CV route;
- exact high-risk claims (`2020`, `545`, `Unit 1`, `synthetic`, `retrieval ranking—not answer accuracy`, `in progress`);
- no unsupported `live`/production/employer-affiliation copy;
- the primary external links and their expected destinations;
- no secret-like server value in browser assets;
- no page-level horizontal overflow at the target viewports.

The exact test framework is Juan's decision. Record what the checks prove and what remains manual.

## Target evidence checklist

### Source and branch discipline

- [ ] Day 26's accepted design, inventory, and ADR are read completely.
- [ ] The implementation branch starts from portfolio `0ct26-overhaul` at or after `76c719e`, not legacy-only `master`.
- [ ] `master` and Pages publishing remain untouched during Day 27.
- [ ] The exact scaffold command, Node version, package manager, framework version, and lockfile are recorded.
- [ ] Only one package-manager lockfile exists.

### Recruiter path and career evidence

- [ ] A first-time visitor can identify Juan's ML/AI direction, Barcelona location, production forecasting, procurement context, ProcureRAG flagship, current CV, GitHub, LinkedIn, and email within two interactions.
- [ ] The hero uses the approved production-ML-to-RAG wording and does not claim a held `Senior AI Engineer` title or years of LLM experience.
- [ ] PepsiCo production ML/current Digital Procurement, Novel Software research, and earlier procurement roots remain distinct and accurately titled.
- [ ] Employer claims remain CV-reported/public-approved; no internal dashboard, confidential architecture, employer data, affiliation, or endorsement is implied.
- [ ] ProcureRAG is labeled an independent learning project over the synthetic Vantera corpus.

### Earlier work, publications, credentials, and assets

- [ ] NER is a 2020 journal article and the dataset is `545 CVs with NER annotations (as documented in the dataset README)`.
- [ ] The market paper says `AGI 2022 proceedings (published 2023)` and links the DOI/preprint correctly.
- [ ] DICOM2STL credits David T. Chen/NIAID and scopes Juan's contribution.
- [ ] U-NET is a client PoC, not a deployed clinical product; asset use follows the recorded owner decision.
- [ ] CS231n stays a foundation/archive item.
- [ ] Boot.dev `Learn Retrieval Augmented Generation` and Hugging Face `The MCP Course, Unit 1: Fundamentals of MCP` have exact titles/dates/scopes.
- [ ] Azure AI Engineer Associate remains `in progress` in the CV and is not shown as earned.
- [ ] The private award images remain unpublished.
- [ ] The approved source photo has a deliberate optimized head-and-shoulders crop with suitable alt text.
- [ ] The tagged corrected CV is reachable through the preview's current-CV link.

### ProcureRAG case study

- [ ] The case study names intended users/problem, Juan's ownership, synthetic corpus, progression, architecture, measurements, failures, and roadmap.
- [ ] Metrics name method, corpus, query count, cutoff, date/commit, and reproduction path.
- [ ] `P@1 0.978` is labeled retrieval-ranking precision, never answer accuracy.
- [ ] The exact test count is tied to a date/commit; short surfaces use `430+`.
- [ ] Q091's answer-completeness failure and deterministic `Band 3` gap remain visible.
- [ ] Local-only, historical/deleted, red/limited, and not-built evidence lanes are visually distinguishable in words, not color alone.
- [ ] The Azure exercise is historical/deleted; the current backend is not described as live.
- [ ] The static demo section says `in progress`, makes no request, simulates no answer, and does not imply memory, public auth, source snippets, or a live BFF.

### Responsive/accessibility behavior

- [ ] One `h1` per page, correct heading order, landmarks, `lang="en"`, skip link, and descriptive text links.
- [ ] Keyboard-only navigation reaches every interactive element in sensible order; no trap exists.
- [ ] Focus remains visible against the actual background; `outline: none` has no unpaired use.
- [ ] Token contrast remains at or above the accepted ratios; new colors have recorded ratios.
- [ ] Reflow works at 320 px and 400% zoom without page-level horizontal scroll.
- [ ] 375 px mobile and 1440 px desktop captures/observations match the intended hierarchy.
- [ ] Wide tables, if any, scroll only inside a labeled focusable region.
- [ ] Reduced-motion mode removes nonessential transitions; content never depends on reveal animation.
- [ ] Meaningful images have useful alt text; decorative images use empty alt text; diagrams have a visible text equivalent.
- [ ] Target sizes meet the WCAG 2.2 contract or a documented exception.
- [ ] Core content and navigation remain meaningful without JavaScript; the static demo includes its no-JS explanation.

### Build and preview evidence

- [ ] Typecheck, lint, tests, and production build pass using the committed manifest and lockfile.
- [ ] The production output has no TypeScript/build warnings treated as harmless without explanation.
- [ ] Preview console and network inspection show no unexpected runtime errors, failed first-party requests, mixed content, or credentials in client assets.
- [ ] Internal links and the current CV route pass; external evidence/contact links are checked and failures recorded honestly.
- [ ] A preview URL and exact commit are recorded, or a reproducible local command and explicit preview-access blocker are recorded.
- [ ] The live legacy site is unchanged.
- [ ] The completed Day 27 learning-log section contains real evidence or explicit blockers, not success-shaped placeholders.
- [ ] Juan gives the three-minute portfolio walkthrough and answers the interview drill.

## Recommended 6-hour split

### Block 0 — Reactivate the accepted contract, 25–30m

- Read HER-295, this route, Day 26's closure and final `### Next step`.
- Fetch both repositories and verify the exact starting heads/status.
- Confirm the Day 26 portfolio branch contains the accepted contracts, corrected CV, and source photo.
- Write three sentences:
  1. the recruiter's first-minute question;
  2. the technical interviewer's evidence question;
  3. the most dangerous false-live or metric overclaim Day 27 must prevent.

### Block 1 — Exact readings and component-boundary plan, 45–60m

- Complete Sources A–D above.
- Record one applied decision or rejection per source.
- Draw the server/client component boundary before scaffolding.
- Decide the minimum metadata/file-based metadata set.
- Translate the accepted wireframes into route/section/component responsibilities without changing the content hierarchy.

Stop condition before build:

- explain why most of Day 27 can remain Server Components;
- name the only interactive islands, if any;
- name every page and its audience;
- identify which claims are demonstrated, local-only, historical, red, and unbuilt;
- explain how the preview stays useful without JavaScript or chat.

### Block 2 — Juan-owned scaffold and design system, 70–80m

- Scaffold the selected TypeScript/App Router baseline without overwriting accepted Day 26 artifacts blindly.
- Record actual versions and commands.
- Implement global layout, tokens, typography, header/footer, skip link, focus treatment, responsive container, and metadata baseline.
- Keep `master` and live Pages untouched.

Checkpoint:

- a production build can render a minimal version of all three routes;
- no credential or BFF placeholder enters browser code;
- the page remains readable with JavaScript disabled.

### Block 3A — Recruiter path and accurate content, 75–90m

- Build `/` and `/about` from the inventory, not from memory or old-site prose.
- Add current experience, selected work/research, correctly scoped credentials, CV, contact, and optimized photo crop.
- Check publication years, dataset wording, role titles, employer separation, upstream credit, and credential scope at the point of use.

### Block 3B — ProcureRAG technical path, 75–90m

- Build `/procurerag` with architecture, progression, evidence table, failure analysis, reproducibility, roadmap, and static demo explanation.
- Link claims to canonical repository evidence instead of copying large stale report dumps.
- Keep Q091 and the public-demo gaps visible.
- Do not implement or simulate Day 28 chat.

### Block 4 — Verification and preview, 55–70m

- Run the actual typecheck/lint/test/build scripts.
- Test internal routes and external evidence/contact links.
- Inspect 320/375/intermediate/1280/1440 widths, 400% zoom, keyboard/focus, reduced motion, no-JS behavior, console, and network.
- Search built client assets for forbidden secret names and unsupported live claims without printing any credential value.
- If approved and available, create a non-production preview and record URL + commit. Otherwise record the exact local production command and blocker.

### Block 5 — Evidence and walkthrough, 25–35m

- Replace every Day 27 TODO with evidence or an explicit blocker.
- Record screenshots/observations by viewport, command/exit code, artifact path, and exact commit.
- Give the three-minute recruiter-to-technical walkthrough.
- Answer the interview drill.
- Send the review prompt below. Do not move HER-295 to Done before review.

### Fallback route if framework pace blocks

A legitimate fallback is:

- preserve the accepted branch and contracts;
- establish a reproducible typed manifest/lockfile and global design tokens;
- complete `/`, `/procurerag`, and `/about` as static accessible routes with the full evidence hierarchy;
- pass typecheck/lint/build and the most important content/link checks;
- record preview access or the exact blocker;
- cut dark-mode toggle, animation, blog, analytics, bilingual copy, custom domain, and any extra interaction.

Do not fall back to:

- editing Jekyll `master` directly;
- a screenshot-only mock;
- a generic template filled with skill bars/logos;
- fabricated live chat;
- hiding the Q091 or synthetic-data limitations;
- publishing private award assets;
- weakening current-CV, evidence, accessibility, or employer-separation requirements.

The fallback preserves Day 27 progress but does not satisfy later live-chat/launch gates.

## Baseline and review commands

### ProcureRAG

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
uv run python scripts/portfolio_contract_probe.py
git diff --check
git status --short
```

Record each exit code separately. `HF_HUB_OFFLINE=1` is valid only when the required model artifacts are cached; a missing cache is an infrastructure blocker, not a pass.

### Portfolio

The kickoff branch has no Node manifest or lockfile, so there is no honest fixed command list yet. After Juan creates the scaffold, record the real commands from the committed manifest and lockfile. The minimum gate shape is:

```text
locked install
actual typecheck script
actual lint script
actual test script
actual production build script
preview or production-server smoke against the built artifact
internal/external link check
responsive/accessibility/no-JS/console/network inspection
git diff --check
git status --short
```

Do not substitute a development server for a production build. Do not claim an automated accessibility pass proves manual keyboard, focus, reflow, or copy accuracy. No live provider smoke is part of Day 27.

## Interview drill

1. **What should a recruiter understand in the first minute?**
   - Expected answer shape: experienced ML practitioner in Barcelona; production forecasting and procurement depth; ProcureRAG as the flagship extension into evidence-driven RAG/agents; current CV/contact; no career-reset framing.

2. **Why are the course awards visually secondary?**
   - Expected answer shape: they prove structured learning, while roles, publications, code, reproducible measurements, failures, and shipped exercises prove application. MCP is Unit 1 only.

3. **Why use Server Components for most of this preview?**
   - Expected answer shape: the content is static and evidence-heavy; server/pre-rendered output reduces client JavaScript, works before hydration, supports metadata, and keeps the future chat boundary small. Client Components are for actual browser interactivity, not a default architecture label.

4. **What makes the case-study metrics defensible?**
   - Expected answer shape: each number names method, corpus, query count, cutoff, date/commit, and reproduction path; P@1/MRR/nDCG are retrieval metrics, not answer correctness.

5. **Why show Q091 prominently instead of hiding it?**
   - Expected answer shape: a valid citation and repaired retrieval do not guarantee a complete answer. The failure demonstrates evaluation judgment and determines the public preset policy; a disclaimer is not a repair.

6. **How do demonstrated, local-only, historical, red, and unbuilt claims differ?**
   - Expected answer shape: reproducible current evidence versus a local artifact, a deleted past deployment, a failing quality lane, or planned future work. The UI uses those labels to prevent launch theater.

7. **Why is the static demo section not a fake chat?**
   - Expected answer shape: it explains the future contract and approved questions but sends no request and returns no simulated answer. It remains labeled `in progress`; Day 28 supplies the secured local vertical slice.

8. **How did you verify accessibility beyond a score?**
   - Expected answer shape: keyboard path, visible focus, semantic order/landmarks/headings, 320 px/400% reflow, target sizes, contrast, text alternatives, reduced motion, no-JS behavior, and page-versus-table overflow—plus any automated checks as supporting evidence.

9. **Why keep the live Jekyll site untouched today?**
   - Expected answer shape: Day 27 is a preview branch; cutover requires URL migration, old-CV-path handling, browser/link checks, rollback, and launch evidence. Preview quality does not authorize production migration.

10. **How do you distinguish Juan's work from employer and upstream work?**
    - Expected answer shape: exact held roles and approved CV-reported contributions; ProcureRAG is independent/synthetic; DICOM2STL credits upstream; no employer data/endorsement; client PoCs are not claimed as owned deployed products.

11. **What remains unbuilt after Day 27?**
    - Expected answer shape: BFF, service-token auth, live chat, quota store, paid model path, persistent Azure/Vercel chain, deployed smoke/rollback, public cutover, LinkedIn final reconciliation, and weekly gate review.

12. **What would you cut first if the six-hour block overruns?**
    - Expected answer shape: bilingual duplication, custom domain, manual dark toggle, motion, illustration/3D, blog, analytics, and optional interactions before evidence, current CV, responsive/accessibility, honest limitations, or build reproducibility.

## Hermes review protocol

When Juan sends the review prompt, Hermes will:

1. fetch both repositories and record exact branch heads and divergence before reading evidence;
2. read the full Day 27 implementation, manifest/lockfile, tests, content data, metadata, assets, and completed learning-log section;
3. compare every high-risk career/project/publication/credential claim against the accepted Day 26 inventory;
4. verify the implementation starts from the accepted contract branch and that legacy `master`/Pages remain unchanged;
5. inspect the Server/Client Component boundary and client bundle for unnecessary or secret-bearing code;
6. run the actual locked install, typecheck, lint, tests, production build, and built-artifact smoke;
7. verify all three routes, current CV path, internal links, external evidence links, metadata, and static/no-JS content;
8. inspect recruiter and technical paths at mobile and desktop widths;
9. exercise keyboard/focus/reflow/reduced-motion behavior and check the architecture/table alternatives;
10. cross-check every metric and live/local/historical/red/unbuilt label against ProcureRAG's current evidence;
11. confirm the demo remains static and honestly `in progress`, with no BFF/provider/public deployment claim;
12. rerun ProcureRAG's deterministic gates and no-paid contract probe with live/tracing disabled;
13. inspect preview console/network and check that browser assets contain no credentials;
14. quiz Juan on the twelve questions above without rewriting his implementation.

## Review prompt to send Hermes

> “Day 27 portfolio preview is ready. Please fetch both repos and review the implementation branch against the accepted Day 26 design/inventory/ADR. Check the recruiter path, production ML/procurement experience, preserved work/publications, scoped course awards, current CV/contact, ProcureRAG ownership/architecture/eval claims, Q091 and synthetic-data limitations, Server/Client boundary, responsive/accessibility/no-JS behavior, real build/test evidence, preview URL or blocker, and that no Day 28–30 chat/deployment work is falsely presented as live. Juan owns implementation.”

## Stop condition

Day 27 is ready for review only when:

1. a reproducible TypeScript/App Router preview branch exists from the accepted Day 26 portfolio branch;
2. one committed lockfile and real typecheck/lint/test/build scripts exist;
3. `/`, `/procurerag`, and `/about` implement the approved recruiter and technical paths;
4. the current tagged CV, optimized photo crop, experience, earlier work, publications, credentials, and contact links are correctly represented;
5. ProcureRAG's metrics, evidence lanes, Q091 failure, synthetic-data disclosure, ownership, and known limits are accurate and linked;
6. the static demo is clearly not live and sends no request;
7. responsive, keyboard, focus, contrast, reflow, reduced-motion, image/diagram alternative, and no-JS checks have real evidence;
8. locked install, typecheck, lint, tests, production build, link checks, console/network checks, and built-artifact smoke pass or have explicit blockers;
9. a preview URL + commit or reproducible local command + deployment blocker is recorded;
10. the live Jekyll `master` site remains unchanged;
11. the learning log has no false-complete TODOs and Juan can deliver the three-minute walkthrough plus interview drill;
12. no BFF, provider call, public upstream, paid operation, live-site cutover, or implementation by Hermes was performed.

Do not close HER-295 on route creation, a pretty screenshot, or a successful development server alone. First complete the Juan-owned preview, send the review prompt, and pass review. Day 28 then adds the secured local procurement-chat vertical slice over this honest static foundation.