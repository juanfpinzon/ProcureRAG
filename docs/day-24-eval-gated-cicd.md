# Day 24 — Eval-Gated CI/CD and Graph-Aware Regression Evidence

Date: 2026-10-20 kickoff.

Linear: HER-292 — Day 24 loop: eval-gated CI/CD and graph-aware regression evidence.

Related gate: HER-270 — Week 5 gate: serving, Azure, CI/CD, MCP.

Project rule: Juan owns every workflow, regression/eval implementation, test, script, deployment configuration, and any change under `src/` or `tests/`. Hermes may scaffold this route, review evidence, quiz, and help debug after a serious attempt; Hermes does not replace Juan's implementation.

## Course target for today

**No new Boot.dev chapter today.** Day 24 is a production CI/CD bridge. It turns the verified Day 21–23 API, container, retrieval, graph, and deployment behavior into explicit gates, while keeping paid/provider-dependent checks outside untrusted pull-request execution.

Today's exact source target is **120–150 minutes**. Read the named sections rather than browsing whole documentation trees.

### Block A — Python and locked dependency CI, 25–30m

1. **GitHub Docs — `Building and testing Python`** - Read

   <https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python>
   - `Introduction` / workflow-template shape.
   - `Specifying a Python version`.
   - `Installing dependencies`.
   - `Caching dependencies`.
   - `Testing your code` and linting examples.
   - ProcureRAG question: why must CI select Python 3.11 instead of trusting the runner's default interpreter?

2. **Astral docs — `Using uv in GitHub Actions`** - Read

   <https://docs.astral.sh/uv/guides/integration/github/>
   - `Installation` with `astral-sh/setup-uv`.
   - Pinning an exact `uv` version.
   - `Setting up Python` using the project's `.python-version`.
   - `Syncing and running` with `uv sync --locked --dev` and `uv run`.
   - `Caching` and pruning the cache after CI.
   - ProcureRAG question: what does `--locked` prove that a successful unpinned install does not?

### Block B — Workflow syntax, events, and security boundaries, 45–55m

3. **GitHub Docs — `Workflow syntax for GitHub Actions`** - Read

   <https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions>
   - `on` for `pull_request`, `push`, and `workflow_dispatch`.
   - `permissions`.
   - `env` at workflow/job/step scope.
   - `jobs.<job_id>.needs`, `if`, `timeout-minutes`, and `concurrency`.
   - ProcureRAG question: which jobs can run on an untrusted pull request, and which need an intentionally privileged event?

4. **GitHub Docs — `Secure use reference`** - Read

   <https://docs.github.com/en/actions/reference/security/secure-use>
   - Principle of least privilege for `GITHUB_TOKEN`.
   - Full-length commit-SHA pinning for third-party and first-party actions.
   - Secrets and transformed-secret masking.
   - Untrusted input and shell-injection guidance.
   - The danger of checking out untrusted PR code from privileged `pull_request_target` or `workflow_run` jobs.
   - ProcureRAG question: why is `pull_request_target` the wrong default for running this repository's tests?

5. **GitHub Docs — `Manually running a workflow`** - Read

   <https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/manually-run-a-workflow>
   - `workflow_dispatch` requirements and inputs.
   - Branch/ref choice when launching a manual run.
   - ProcureRAG question: which input should select `live-eval`, `deploy`, or `live-eval-and-deploy`, and which ref is eligible?

6. **GitHub Docs — `Control the concurrency of workflows and jobs`** - Read

   <https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/control-workflow-concurrency>
   - Workflow-level versus job-level concurrency.
   - `cancel-in-progress` for superseded PR CI.
   - A non-canceling production deployment group.
   - ProcureRAG question: why should a newer PR run cancel an older PR run, while a deployment should never overlap another deployment?

7. **GitHub Docs — `Managing environments for deployment`** - Read

   <https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments>
   - Required reviewers and preventing self-review.
   - Deployment branch/tag restrictions.
   - Environment secrets and variables.
   - Protection rules applying before secrets become available.
   - ProcureRAG question: what does an environment approval gate protect that a Boolean workflow input does not?

### Block C — Docker build/test gate, 25–30m

8. **Docker Docs — `Docker Build GitHub Actions`** - Read

   <https://docs.docker.com/build/ci/github-actions/>
   - Official Buildx and build-push actions.
   - Build summary/artifact behavior.
   - Pin action references before using them in the repository.

9. **Docker Docs — `Test before push with GitHub Actions`** - Read

   <https://docs.docker.com/build/ci/github-actions/test-before-push/>
   - Build and load a local image.
   - Test that exact image before any registry push.
   - Reuse build cache rather than rebuilding unrelated artifacts.
   - ProcureRAG question: why does “Dockerfile parsed” not prove `/health`, Q001, Q091, and blocked-input behavior?

10. **Docker Docs — `Cache management with GitHub Actions`** - Read

    <https://docs.docker.com/build/ci/github-actions/cache/>
    - `gha` cache backend.
    - `cache-from` versus `cache-to`.
    - Cache-write restrictions and cache poisoning boundaries.
    - ProcureRAG question: why is cache a performance optimization and never acceptance evidence by itself?

### Block D — protected Azure promotion, 25–35m

11. **GitHub Docs — `OpenID Connect`** - Read

    <https://docs.github.com/en/actions/concepts/security/openid-connect>
    - Short-lived cloud tokens versus long-lived client secrets.
    - Repository/ref/environment claims in the token.
    - Job-scoped `id-token: write`.

12. **Microsoft Learn — `Use the Azure Login action with OpenID Connect`** - Read

    <https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect>
    - Federated identity credential.
    - Azure client, tenant, and subscription identifiers.
    - Least-privilege role assignment.
    - `azure/login` with OIDC; no Azure client secret.

13. **Microsoft Learn — `Deploy to Azure Container Apps with GitHub Actions`** - Read

    <https://learn.microsoft.com/en-us/azure/container-apps/github-actions>
    - Build-from-Dockerfile versus deploy-existing-image paths.
    - Unique immutable image tags such as `${{ github.sha }}` rather than `latest`.
    - GitHub-to-ACR push authentication versus Container Apps-to-ACR pull authentication.
    - Managed identity with `AcrPull` for the app.
    - ProcureRAG question: what must already exist before a deployment job can update a revision, given that Day 23 deleted its disposable resource group?

### Source-note rule

For each source, record one ProcureRAG-specific takeaway in `docs/learning-log.md`. A checked box with no applied takeaway is not completion.

## Day 24 objective

Build and exercise a CI/CD contract that can answer:

> “Which checks run on every pull request with no secrets, which checks load the real local models, which behaviors are proven at the API/container boundary, which graph paths and answer-quality expectations are evaluated, what exactly blocks a merge or deployment, how are paid live checks invoked and budgeted, and how does a successfully evaluated image become an immutable deployment candidate?”

A successful day is **not** merely adding `.github/workflows/ci.yml`. The workflow must execute remotely, its commands must match locally reproducible commands, and every green status must have a precise claim. A check that prints a table but exits zero on drift is evidence, not a gate.

## Starting state

### Day 23 handoff

Day 23 closed with evidence for a real Azure Container Apps deployment:

- `linux/amd64` image built and pushed to ACR;
- image digest `sha256:f66462bcef47a98fd7e6f8b3f736f1866426db3b7b19fd2ed4ac3893f4ecef09`;
- baked MiniLM and TinyBERT models, runtime `HF_HUB_OFFLINE=1`;
- one deterministic Container Apps revision with live LLM and tracing off;
- public `/health`, Q001, Q091, off-topic, and prompt-injection smokes;
- 59.07-second cold `/health`, about 0.150-second warm `/health`, and about 0.219-second warm Q001;
- explicit HTTP startup/readiness/liveness probes;
- managed-identity ACR pull and no provider key in the deterministic deployment;
- complete deletion of `rg-procurerag-day23` on 2026-10-19/20.

Therefore Day 24 inherits a **verified deployment design but no live Azure resource to update**. Do not imply that a deploy job has passed unless Juan deliberately recreates infrastructure and records it. A workflow that only validates/builds an image is CI and release-candidate preparation, not a completed Azure deployment.

### Current repository baseline

Kickoff on 2026-10-20:

```text
branch: main
commit: 6e45949
origin: https://github.com/juanfpinzon/ProcureRAG.git
git status: clean
.github/: absent; no existing GitHub Actions workflow
.python-version: 3.11
Hermes VM Python: 3.11.15
Hermes VM uv: 0.11.11
```

Deterministic kickoff gates, with provider and tracing switches forced off:

```text
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false PROCURERAG_LIVE_LLM=0 \
  ./.venv/bin/pytest -q
357 passed in 6.10s

./.venv/bin/python -m compileall -q src tests
clean, no output

./.venv/bin/python -m ruff check src tests
All checks passed!
```

The first combined `regression_suite.py --verify-retrieval` attempt loaded MiniLM and then exited `132` (`Illegal instruction`) before the cross-encoder completed. The isolated retry forced `HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1`; both models loaded and every frozen/current-pipeline case passed:

```text
fixture lane: exit 0; all 7 frozen cases matched
current retrieval lane: exit 0
control-q001, control-q004, Q091, Q093, Q016, and citation-negative pipeline checks: [OK]
The current retrieval pipeline still matches every case's expectation.
```

Treat the first crash as a host/runtime observation, not a retrieval regression. The CI contract should set a bounded thread count (`OMP_NUM_THREADS=1`) for model-backed jobs and preserve enough output to distinguish process/runtime failure from eval drift.

### Existing gates and their actual claims

| Existing command/artifact | What it proves | What it does **not** prove |
|---|---|---|
| `pytest -q` | 357 deterministic unit/integration/boundary tests pass; API tests use faked retrieval/LLM where documented | fresh model download, real retrieval output, real container startup, or live answer quality |
| `compileall -q src tests` | Python source compiles | imports/runtime paths work |
| `ruff check src tests` | configured E4/E7/E9/F lint checks pass | behavior or full style/type correctness |
| `regression_suite.py` | seven frozen fixture cases still match their committed expectations | current retrieval pipeline output |
| `regression_suite.py --verify-retrieval` | current local embedding/reranking pipeline still satisfies the six real retrieval/citation expectations | LangGraph route behavior or generated answer quality |
| `agent_graph.py --all-queries-summary` | whole-corpus route distribution and `report_gap` cases are visible | expected route assertions, `expected_answer` quality, or non-zero exit on drift |
| `tests/test_api.py` | typed API/guard/HITL contracts over HTTP through `TestClient` with controlled fakes | real Uvicorn/model/container startup |
| Day 22/23 Docker smokes | real image startup and selected endpoint contracts | every future image built by CI |
| `regression_suite.py --live` | optional DeepEval over existing single-pass fixtures | graph-path answer quality; by itself it degrades to `blocked` without a key rather than acting as a fail-closed promotion gate |

## Key design decision: three lanes, not one misleading gate

### Lane 1 — fast deterministic merge gate

Runs on every `pull_request` to `main` and every push to `main`. It must:

- use no repository/environment secret;
- set `permissions: contents: read` unless a job proves it needs more;
- set `PROCURERAG_LIVE_LLM=0`, `LANGSMITH_TRACING=false`, and `LANGSMITH_TRACING_V2=false` explicitly;
- select Python from `.python-version`;
- install a pinned `uv` and run `uv sync --locked --dev`;
- run pytest, compileall, Ruff, and the frozen fixture regression;
- fail immediately on a non-zero command;
- use a PR concurrency group that cancels superseded runs;
- never use `pull_request_target` to execute checked-out PR code.

This lane is the minimum required branch-protection check.

### Lane 2 — model-backed deterministic artifact gate

Still provider-free and secret-free, but slower. It should run on PR/push unless real measured duration/cost justifies moving part of it to push/manual. It must distinguish:

1. **Current retrieval verification** — real MiniLM + cross-encoder, `OMP_NUM_THREADS=1`, `regression_suite.py --verify-retrieval`.
2. **Graph route regression** — assertions for control, recursive recovery, and bounded failure; not only a printed route table.
3. **Docker build** — build the real `linux/amd64` image with `push: false`.
4. **Container smoke** — load/run that exact image and verify `/health`, Q001, one pending-approval request, and one blocked input.

The model download/cache may use network and a keyed cache, but it must use **no LLM/provider secret**. Cache hits do not replace the checks. Because the code currently asks model repositories for their default revision, record the remaining model-pin caveat rather than calling the entire model supply chain immutable.

### Lane 3 — protected live eval and deployment promotion

Runs only through an intentional `workflow_dispatch` or a separately protected workflow. It must:

- reference a GitHub environment such as `live-eval` or `production`;
- require an approved trusted ref, preferably `main` or an immutable release tag/SHA;
- obtain secrets only after environment protection passes;
- set a small explicit case/call budget;
- record model/provider and threshold policy;
- make missing credentials a clear **failure** when this lane is selected as a promotion gate, not a green “blocked” result;
- use a non-overlapping deployment concurrency group;
- use Azure OIDC and job-level `id-token: write` if deployment is enabled;
- deploy an image identified by commit SHA and preferably digest, not `latest`;
- smoke the new revision before declaring promotion complete;
- preserve rollback and cleanup evidence.

Live eval may remain manual/informational today. It becomes a deployment gate only when its pass/fail thresholds, retry policy, and false-positive policy are explicit.

## Graph-aware regression contract Juan should implement

Do not copy the single-pass fixture evaluator and rename it “graph eval.” Exercise the compiled graph and record route evidence.

Minimum deterministic cases:

| Case | Expected graph behavior | Required gate assertion |
|---|---|---|
| Q001 control | complete first-pass evidence; direct generation route; no recursive retrieval | one retrieval pass, expected route/stop reason, no unexpected gap |
| Q091 recursive recovery | first pass exposes the known evidence gap; one approved/allowed recursive pass repairs it; then generation route | exactly two retrieval attempts, expected route history, final missing evidence empty |
| Q092 bounded failure | first pass exposes a gap; one follow-up is attempted; evidence remains incomplete | exactly two retrieval attempts, terminal `report_gap`, remaining gap named, **zero LLM calls** |

Recommended additional control: Q005, so a second ordinary graph path guards against overfitting the route assertions to Q001.

Minimum live answer-quality slice:

- **Q001:** generate through the graph, evaluate the generated answer against the query row's `expected_answer`, and run deterministic citation validity/support checks.
- **Q091:** generate only after recursive recovery, then evaluate against `expected_answer` and citations. This is the missing graph-path answer-quality evidence from Week 4.
- **Q092:** do **not** force an answer to make a metric happy. Its expected quality behavior is bounded abstention/reporting after the permitted follow-up. Score route/abstention correctness, remaining-gap accuracy, and zero LLM calls.

The implementation may extend `src/regression_suite.py` or create a focused graph-regression entry point. Juan decides after tracing existing helpers. Whatever shape is chosen must:

- use committed case definitions, not silently bless the current output as the expected output;
- print a concise per-case summary;
- return non-zero on deterministic route/contract drift;
- return non-zero on a selected live promotion threshold failure;
- separate infrastructure/provider failure from quality failure;
- avoid dumping provider keys or unnecessary raw confidential context;
- cap live cost and case count;
- be covered by deterministic tests with fake retrieval/LLM clients before a real provider call.

## Gate matrix to implement and fill

| Check/job | PR | Push to `main` | Manual live | Deployment | Secrets | Blocks merge? | Blocks deploy? |
|---|---:|---:|---:|---:|---|---:|---:|
| locked dependency sync | yes | yes | inherited | inherited | none | yes | yes |
| pytest | yes | yes | inherited | inherited | none | yes | yes |
| compileall | yes | yes | inherited | inherited | none | yes | yes |
| Ruff | yes | yes | inherited | inherited | none | yes | yes |
| frozen fixture regression | yes | yes | optional | inherited | none | yes | yes |
| current retrieval verification | recommended | yes | optional | inherited | none | recommended yes | yes |
| deterministic graph route regression | yes | yes | inherited | inherited | none | yes | yes |
| Docker build, no push | yes or justified push-only | yes | no | inherited | none | selected policy | yes |
| container API smoke | with Docker job | yes | no | post-build | none | selected policy | yes |
| Q001/Q091 live graph answer eval | no | no | explicit | before deploy if promoted | provider key; optional trace key | no by default | explicit policy |
| Q092 bounded-abstention live check | no | no | explicit | before deploy if promoted | provider key should remain unused for Q092 | no by default | explicit policy |
| image push | no | no | no | explicit | OIDC/registry auth | no | yes |
| Azure revision update + smoke | no | no | no | explicit protected environment | Azure OIDC | no | yes |

Juan must replace “recommended,” “selected policy,” and “explicit policy” with the chosen final behavior and rationale.

## Required workflow security contract

- Pin every `uses:` dependency to a verified full commit SHA and leave the human-readable release tag in a comment.
- Set workflow-level `permissions: contents: read`.
- Add `id-token: write` only to the Azure deployment job.
- Do not grant `contents: write`, `pull-requests: write`, or `packages: write` unless a concrete step requires it.
- Do not expose provider/Azure secrets to `pull_request` jobs.
- Do not use `pull_request_target` to run repository code.
- Do not interpolate PR titles, branch names, issue text, or other untrusted context directly into shell scripts.
- Put live/deploy secrets in protected environments, not the deterministic workflow environment.
- Use OIDC for Azure; do not create a long-lived Azure client secret for convenience.
- Use unique image tags (`github.sha`) and record the pushed digest.
- Give the deployment identity only the narrow Azure roles/scopes needed for ACR push and Container App update.
- Do not print `az account get-access-token`, complete environment dumps, or secret values.

## Exact local command map

### Fast lane

```bash
export PROCURERAG_LIVE_LLM=0
export LANGSMITH_TRACING=false
export LANGSMITH_TRACING_V2=false
export OMP_NUM_THREADS=1

uv sync --locked --dev
uv run pytest -q
uv run python -m compileall -q src tests
uv run python -m ruff check src tests
uv run python src/regression_suite.py
git diff --check
```

### Model-backed lane

On a host with the two cached models, use `HF_HUB_OFFLINE=1`. On a fresh GitHub runner, either allow the exact model download and cache it, or pin/provision the model snapshots first. Do not set offline mode against an empty cache and call the resulting failure an application regression.

```bash
PROCURERAG_LIVE_LLM=0 \
LANGSMITH_TRACING=false \
LANGSMITH_TRACING_V2=false \
OMP_NUM_THREADS=1 \
uv run python src/regression_suite.py --verify-retrieval

PROCURERAG_LIVE_LLM=0 \
LANGSMITH_TRACING=false \
LANGSMITH_TRACING_V2=false \
OMP_NUM_THREADS=1 \
uv run python src/agent_graph.py --all-queries-summary
```

The second command remains descriptive until Juan adds explicit graph assertions/non-zero failure semantics. Do not register the descriptive summary itself as a required quality check.

### Docker artifact lane

The exact implementation belongs to Juan. The final lane must preserve this evidence chain:

1. Build the repository `Dockerfile` for `linux/amd64`, `push: false`.
2. Load/tag the exact test image locally.
3. Run it with:
   - `PROCURERAG_LIVE_LLM=0`;
   - `LANGSMITH_TRACING=false`;
   - `LANGSMITH_TRACING_V2=false`;
   - `HF_HUB_OFFLINE=1`;
   - `OMP_NUM_THREADS=1`;
   - one CPU / 2 GiB when feasible.
4. Poll `/health` with a budget above the measured 59-second cold start; do not use a fixed 5-second sleep.
5. Assert `live_llm=false`.
6. Send exact canonical Q001 and verify expected status/sources.
7. Send exact canonical Q091 or Q092 without a decision and verify `pending_approval`, no run id, and no sources.
8. Send one off-topic or injection-shaped request and verify `blocked`.
9. Inspect logs for traceback and secret-like output.
10. Always remove the container in a cleanup/finally step.

Use `docs/docker-runbook.md` as the command source. Do not create a second smoke contract that drifts from it.

## Recommended 6-hour split

### Block 0 — Baseline and gate inventory, 20–30m

- Re-run the fast lane and current retrieval verification with all live/tracing switches forced off.
- Write one sentence for what each command proves and does not prove.
- Confirm no `.github/workflows` baseline exists.
- Fill the final event/job matrix before writing YAML.

### Block 1 — Exact readings, 120–150m

Complete Blocks A–D above. Record one ProcureRAG-specific takeaway per source.

Do not start with a copied template before deciding:

1. triggers;
2. job boundaries;
3. required permissions;
4. cache boundaries;
5. secret availability;
6. exit-code semantics;
7. merge/deploy policy.

### Block 2 — Design the gate contract, 35–45m

Decide and record:

- one workflow versus separate `ci.yml` / `live-eval.yml` / `deploy.yml` files;
- PR/push/manual triggers;
- job dependency graph;
- exact Python and uv versions;
- full-SHA-pinned actions;
- required check names for branch protection;
- whether Docker is PR-required or push-required, based on measured runtime;
- model and Docker cache keys;
- graph regression case contracts and failure exits;
- live case/call budget and thresholds;
- whether deployment is implemented today or left as an explicitly blocked/manual future lane because Day 23 resources were deleted.

Recommended route: separate **deterministic CI** from **protected live/deploy**. A single YAML can technically branch on event/input, but separate workflows make the secret boundary and required-check behavior easier to audit.

### Block 3 — Juan-owned implementation, 90–120m

Juan implements:

1. deterministic CI workflow;
2. graph-aware deterministic regression entry point/tests;
3. Docker build/container smoke gate;
4. optional manual live-eval workflow or a documented deferral with exact next steps;
5. optional Azure promotion workflow only if the target infrastructure and OIDC trust are deliberately configured.

Implementation rule: start with the smallest fast job and get one real remote run green before adding model, Docker, live, or deploy complexity. This keeps failures attributable to one layer.

### Block 4 — Local and remote verification, 45–60m

Required evidence:

- local commands pass;
- workflow is accepted by GitHub, not merely parsed by a generic YAML library;
- one real PR or temporary branch run executes the deterministic jobs;
- check names are stable enough for branch-protection selection;
- no secret is present in PR-job configuration or logs;
- a deliberate failing change or targeted test proves at least one required check becomes red/non-zero, then is reverted;
- Docker build and smoke run against the exact image produced by the workflow, or the deferral is explicit;
- workflow run URL and commit SHA are recorded;
- branch protection is configured or documented as a remaining repository-setting step.

If remote Actions cannot run, record the exact blocker and leave remote status **pending**. Local green commands cannot be relabeled “CI passed.”

### Block 5 — Learning log and interview drill, 30–40m

Fill every Day 24 evidence table, then answer the interview drill without notes.

## Target evidence by end of day

### Sources and design

- [ ] Every exact source section is read and has a ProcureRAG-specific takeaway.
- [ ] Final event/job/secret/gate matrix is recorded.
- [ ] Each check's claim and non-claim is explicit.
- [ ] Action refs, Python, uv, and dependency install are pinned/reproducible.

### Deterministic CI

- [ ] Workflow exists under `.github/workflows/` and GitHub accepts it.
- [ ] Pull requests and pushes to `main` execute the intended jobs.
- [ ] `permissions: contents: read` is the default.
- [ ] Live LLM and LangSmith tracing are explicitly disabled.
- [ ] `uv sync --locked --dev`, pytest, compileall, Ruff, and frozen fixture regression pass.
- [ ] Current retrieval verification passes with bounded model-thread settings.
- [ ] Deterministic graph assertions cover Q001, Q091, and Q092 and return non-zero on drift.
- [ ] No provider key is referenced by any PR job.

### Docker/API artifact gate

- [ ] Real `linux/amd64` Docker image builds with `push: false` on PR/CI.
- [ ] The exact image is started and health-polled with an appropriate cold-start budget.
- [ ] `/health`, Q001, pending approval, and blocked input pass.
- [ ] Logs contain no unexpected traceback or secret-like output.
- [ ] Cleanup runs even when a smoke assertion fails.

### Live/deployment boundary

- [ ] Live eval is manual/protected and has a bounded case/call budget.
- [ ] Q001 and Q091 are evaluated through the graph against `expected_answer` plus citation checks.
- [ ] Q092 proves bounded abstention and zero LLM calls rather than forcing an answer.
- [ ] Missing secrets fail a deliberately selected promotion lane clearly.
- [ ] If deployment exists, it uses protected environment approval, OIDC, unique image identity, non-overlapping concurrency, revision smoke, and rollback evidence.
- [ ] If deployment does not run because Day 23 resources were deleted, that state is labeled pending—not passed.

### Evidence quality

- [ ] At least one real GitHub Actions run URL and commit SHA are recorded.
- [ ] A deliberate negative test proves a required check can fail.
- [ ] Branch-protection status is recorded.
- [ ] Local and remote timings are recorded separately.
- [ ] `git diff --check` passes and `git status --short` contains only intentional Day 24 artifacts.
- [ ] No secret, token, raw credential, or accidental `.env` content enters Git, logs, Linear, or chat.

## Failure semantics

Use these categories in evidence and debugging:

| Failure layer | Example | Owner / next move |
|---|---|---|
| workflow syntax/event | GitHub rejects YAML or job never triggers | workflow structure; inspect Actions UI/event/ref |
| permission/secret boundary | token denied or secret unavailable | verify event, `permissions`, environment approval; do not broaden globally |
| dependency/lock | `uv sync --locked` rejects drift | reconcile `pyproject.toml` and `uv.lock`; never drop `--locked` to turn CI green |
| deterministic code | pytest/compile/Ruff/frozen regression fails | fix implementation or expectation with evidence |
| host/runtime | exit 132, OOM, timeout | runner CPU/memory/thread/model runtime; do not call quality regression yet |
| model supply/cache | Hub download/rate/revision/cache miss | pin/provision/cache models; cache miss is not quality drift |
| retrieval drift | current pipeline misses committed expected evidence | inspect embedding/reranker/corpus changes |
| graph route drift | wrong attempts/route/stop reason or unwanted LLM call | inspect state graph/control-plane behavior |
| answer-quality drift | route completes but generated answer/citations miss threshold | inspect retrieved context versus generation/judge; preserve artifact |
| Docker packaging | build or image startup fails | Dockerfile/build context/base/dependency/model bake |
| API smoke | image healthy but endpoint contract differs | serving/config/guard/HITL boundary |
| provider live eval | 401/429/timeout/model outage | provider/account/infrastructure; separate from quality verdict |
| Azure promotion | OIDC, ACR push/pull, revision, probe, ingress | deployment identity/platform layer; use immutable handles |

## Interview drill

1. **Why split fast deterministic, model-backed deterministic, and live/deployment lanes?**
   - Expected answer shape: they have different trust, latency, cost, and failure semantics. Fast tests should protect every PR without secrets. Local-model retrieval/container checks are still deterministic but heavier. Live generation/judging and cloud promotion need secrets, budgets, approvals, and retry policy.

2. **What does `uv sync --locked` add to CI?**
   - Expected answer shape: it installs from the committed lock and fails if project metadata requires lock regeneration. A successful unconstrained install can silently choose new dependency versions and is not reproducible evidence.

3. **Why force `PROCURERAG_LIVE_LLM=0` and both LangSmith flags false?**
   - Expected answer shape: process environments can inherit settings. Day 24's kickoff already observed accidental LangSmith attempts in an earlier baseline. CI must state the no-paid/no-trace contract rather than trust runner defaults or `.env` absence.

4. **Why is a printed eval report not automatically a gate?**
   - Expected answer shape: CI gates use process exit status. If drift prints “failed” but exits zero, GitHub sees green. Expectations and thresholds must map to non-zero exit codes, while artifacts preserve detailed diagnostics.

5. **What is graph-aware about the Q091/Q092 regression?**
   - Expected answer shape: it asserts state transitions and bounded behavior, not only final retrieval. Q091 must expose a first-pass gap, perform exactly one recursive pass, repair it, and proceed. Q092 must stop after one allowed follow-up, report the remaining gap, and never call the LLM.

6. **Why should Q092 not be scored as a normal generated answer?**
   - Expected answer shape: its correct behavior is abstention/reporting under incomplete evidence. Forcing generation would reward violation of the control policy. Its quality measures are route, bound, gap accuracy, and zero model calls.

7. **Why not run live LLM eval on every PR?**
   - Expected answer shape: secrets must not reach untrusted code; outputs are stochastic; provider outages/quotas create false negatives; every run costs money; and retried runs can multiply cost. Use small protected manual/release slices and keep deterministic controls merge-blocking.

8. **Why pin actions to full commit SHAs?**
   - Expected answer shape: tags can move. A full verified SHA makes the action source immutable for that workflow revision and reduces supply-chain risk; the release tag remains as a comment for maintainability.

9. **Why is a Docker build a separate gate from pytest?**
   - Expected answer shape: the Dockerfile, allow-list context, Linux CPU wheel source, model bake, platform architecture, user/permissions, and startup command are packaging/runtime surfaces not exercised by host pytest.

10. **What does OIDC improve for Azure deployment?**
    - Expected answer shape: GitHub exchanges a job-scoped identity token for short-lived Azure access under a federated trust. No reusable Azure client secret is stored. Claims and narrow role assignments constrain repo/ref/environment and resource scope.

11. **What is eval-gated deployment in this project?**
    - Expected answer shape: build one immutable image, run deterministic tests/retrieval/graph/container gates, optionally run the protected bounded live eval, then promote that same SHA/digest. Do not rebuild between evaluation and deployment, and smoke the resulting revision.

12. **How do you distinguish CI flakiness from product regression?**
    - Expected answer shape: classify the first failed layer, preserve exit/error/runner evidence, rerun only within a declared policy, and compare deterministic cases. Exit 132/OOM/provider 429 are infrastructure/runtime categories; a stable wrong route, source set, answer, or citation is product drift.

## Review prompt to send Hermes

> “Day 24 eval-gated CI/CD work is ready for review. Please inspect the workflow triggers/permissions/action pins, deterministic environment, locked sync, pytest/compile/Ruff/retrieval/graph failure semantics, Docker/API smoke, protected live/deploy boundary, real Actions run evidence, learning log, and secret exposure. Q001/Q091/Q092 graph contracts and the merge-versus-deploy gate matrix are included.”

Do not move HER-292 to Done before that review. Remote CI evidence is required for closure unless GitHub Actions itself is blocked and the ticket is explicitly left open with the exact blocker.

## Constraints / non-goals

- Juan writes all workflow and ProcureRAG implementation/test code.
- Hermes writes route/log scaffolding only, then reviews and quizzes.
- Do not redesign retrieval, the graph, API, or Docker architecture unless a failing gate proves a specific defect.
- Do not add secrets to make deterministic checks pass.
- Do not run paid/provider live eval automatically on pull requests.
- Do not deploy from untrusted PR code.
- Do not use long-lived Azure credentials when OIDC is available.
- Do not call a generic YAML parse, local command run, Docker build, or old Day 23 deployment “GitHub Actions passed.”
- Do not call an image tag immutable; record SHA/digest.
- Do not close HER-292 with TODO placeholders, missing remote handles, or green commands that cannot fail on the behavior they claim to gate.
