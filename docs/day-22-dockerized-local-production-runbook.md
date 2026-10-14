# Day 22 — Dockerized Local Production Runbook

Date: 2026-10-15 kickoff.

Linear: HER-290 — Day 22 loop: Dockerized local production runbook.

Related gate: HER-270 — Week 5 gate: serving, Azure, CI/CD, MCP.

Project rule: course-driven building, with Juan owning the implementation. Hermes may scaffold this route, review, quiz, and help debug after a serious attempt; Juan writes the `Dockerfile`, `.dockerignore`, runbook/config artifacts, and any changes under `src/` or `tests/`.

## Course target for today

**No new Boot.dev chapter today.** Day 22 is a production-packaging bridge day. The goal is to turn Day 21's working local FastAPI service into a reproducible container artifact without hiding secrets, model-download behavior, startup cost, or the service's current safety limits.

Use these exact source pages and sections.

### Primary container sources

1. **FastAPI docs — `FastAPI in Containers - Docker`**

   <https://fastapi.tiangolo.com/deployment/docker/>
   - `Containers and Docker`.
   - `What is a Container Image`.
   - `Container Images`.
   - `Build a Docker Image for FastAPI`.
   - `Docker Cache`.
   - `Start the Docker Container`.
   - `Check it`.
   - `Build a Docker Image with a Single-File FastAPI` only as structure comparison; ProcureRAG keeps its existing `src/` layout.
   - `Deployment Concepts`.
   - `One Process per Container`.
   - `Multiple Processes - Workers`.
   - `Base Docker Image` — note that the old `tiangolo/uvicorn-gunicorn-fastapi` image is deprecated. Build from an official Python image instead.

2. **Astral uv docs — `Using uv in Docker`**

   <https://docs.astral.sh/uv/guides/integration/docker/>
   - `Installing uv`.
   - `Installing a project`.
   - `Using the environment`.
   - `Intermediate layers`.
   - `Non-editable installs`.
   - `Using the pip interface` only for comparison; prefer the existing `pyproject.toml` + `uv.lock` contract.
   - The explicit `.dockerignore` guidance for `.venv`.
   - The reproducibility guidance: pin the uv image/version and run `uv sync --locked` rather than resolving fresh dependency versions.

3. **Docker Docs — `Build context` → `Filesystem contexts` → `Local directories` and `Dockerfile and Dockerfile.dockerignore files`**

   <https://docs.docker.com/build/building/context/#dockerignore-files>
   - What enters the build context.
   - How `.dockerignore` removes `.env`, `.venv`, caches, git history, local reports, and other files that must not enter the image build context.

4. **Docker Docs — `Dockerfile reference`**

   <https://docs.docker.com/reference/dockerfile/>
   - `FROM`, `WORKDIR`, `COPY`, `RUN`, `ENV`, `EXPOSE`, `USER`, `CMD`, and `HEALTHCHECK`.
   - Exec-form `CMD` rather than a shell-form command.
   - `HEALTHCHECK` timing, including a startup grace period for ProcureRAG's model loading.
   - Build secrets are not runtime secrets; never use `ARG` or `ENV` to bake API keys into an image.

### ProcureRAG production-RAG sections to reactivate

The freeCodeCamp course was completed on Day 21. Reactivate these exact sections rather than redoing the whole course:

- **freeCodeCamp — `Production RAG with LangChain & Vector Databases`**

  <https://www.freecodecamp.org/news/production-rag-with-langchain-vector-databases/>
  - `Scaling RAG Systems`.
  - `The Real Costs of Vector Search`.
  - `Production Hosting`.
  - `Three Pillars of Production Visibility`.
  - `Security Checklist`.

Use them to write the container latency/cost/config note. Do not add a vector database, observability vendor, or cloud deployment today.

### Preview only — not implementation scope today

- Microsoft Learn — `Deploy a Flask or FastAPI web app as a container in Azure Container Apps`.
- Microsoft Learn — `Quickstart: Deploy your first container app with containerapp up`.

Read only enough to understand why Day 22 must leave a clear image tag, container port, `/health`, runtime environment contract, and reproducible startup command for Day 23.

## Day 22 objective

Package the real Day 21 API into a local container and produce a runbook another engineer can execute from a clean checkout:

> “What exactly enters the image, how are locked dependencies installed, which process starts the service, when is the container healthy, where do the Hugging Face models come from, which configuration is runtime-only, and how can a reviewer prove the no-key path without exposing secrets or spending money?”

By the end of Day 22, Juan should be able to explain the path from `docker build` to a healthy `/query` response and distinguish:

- image-build time from container-start time;
- image configuration from runtime secrets;
- container port from host port;
- Docker layer cache from uv/Hugging Face caches;
- liveness/health from answer correctness;
- deterministic no-key smoke from optional paid live-model smoke.

## Starting state

### Day 21 service baseline

The current repo already has the service that Day 22 must package:

- `src/api.py` — FastAPI app with `/health`, `/query`, and `/query/stream`.
- `tests/test_api.py` — HTTP-level deterministic coverage with fake retrieval/model boundaries.
- `pyproject.toml` — Python `>=3.11`; runtime dependencies include FastAPI `>=0.143.1`, Uvicorn `>=0.54.0`, sentence-transformers, LangGraph/LangChain, Pydantic, and the existing retrieval/eval stack.
- `uv.lock` — the resolved dependency graph to preserve in the image.
- `data/corpus_v1/` — the canonical 34-document / 93-query local corpus; it is required by the live local retrieval path.
- The working local startup command is:

```bash
PROCURERAG_LIVE_LLM=0 LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false \
  ./.venv/bin/python -m uvicorn api:app --app-dir src --host 127.0.0.1 --port 8000
```

Inside a container, the service must bind to `0.0.0.0`; on the host, publish it to loopback unless there is an intentional reason to expose it more broadly.

### Day 21 behavior and caveats to preserve honestly

- Live LLM calls are opt-in through `PROCURERAG_LIVE_LLM=1`; the default container smoke must keep this off.
- `OPENROUTER_API_KEY` is required only for the opt-in live path and must be injected at runtime, never copied into the image.
- The app can read selected values from `.env`, but Day 22 must **not copy or mount the developer's real `.env` by default**. Container environment variables are the primary contract.
- The in-process rate limiter resets on restart, is per worker, and trusts the observed client address. Therefore run one Uvicorn worker today and do not describe the limiter as distributed or deployment-grade.
- The role is caller-asserted; authentication is still missing.
- Approval is stateless re-submission, not durable pause/resume.
- Free-text evidence completeness is unchecked.
- Trace rows are not persisted.
- The local retrieval pipeline loads two model artifacts. Day 21 measured roughly 8–12 seconds of startup with cached models; uncached startup contacts the Hugging Face Hub.
- `/health` proves that the process is alive and the service object was built. It does not prove answer correctness or provider health.

### Kickoff verification — 2026-10-15

```bash
./.venv/bin/pytest -q
# 357 passed in 6.94s

./.venv/bin/python -m compileall -q src tests
# clean, no output

./.venv/bin/python -m ruff check src tests
# All checks passed!

./.venv/bin/python src/regression_suite.py --verify-retrieval
# All frozen cases matched their expected state.
# The current retrieval pipeline matched every case's expectation.
```

The tests emitted non-failing LangSmith HTTP 429 ingest warnings because tracing settings were available in the kickoff shell. Use `LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false` for the Day 22 container and verification path so a deterministic local gate makes no SaaS trace calls.

Git was clean on `main` at commit `a3f5dd9` before this Day 22 route/log scaffold.

Docker availability on the Hermes VM at kickoff:

```text
docker --version
bash: docker: command not found
```

That is an exact local tooling blocker, not Docker completion evidence. Juan should build/run on a machine with Docker Engine or Docker Desktop available. Day 22 cannot be marked Docker-complete until an actual image build and container run have been recorded somewhere.

No `Dockerfile`, `.dockerignore`, compose file, or `.env.example` existed at kickoff.

## Key concepts to nail today

### 1. The image is a reproducible package, not a copy of the laptop

A correct build starts from a declared Python base image and installs the project from `pyproject.toml` plus `uv.lock`. It must not copy the host `.venv`: that environment is platform-specific and may contain host paths, compiled wheels for the wrong architecture, caches, and developer-only state.

The explanation to practice:

> “The lockfile chooses the resolved dependency versions; the container build creates a fresh environment for the image's operating system and architecture.”

Order layers so dependency installation can be reused when only source/docs change. Do not optimize blindly: first make the build correct, then inspect whether the dependency layer is being invalidated unnecessarily.

### 2. Build context is a security boundary

`.dockerignore` acts before `COPY`. It should keep at least these categories out of the build context:

- `.env`, `.env.*`, credentials, tokens, and local secret material;
- `.venv`, Python bytecode, pytest/Ruff caches;
- `.git` and local editor/OS files;
- local trace/output files not required at runtime;
- large caches and models unless the chosen model-packaging strategy deliberately includes them.

A `.gitignore` is not a substitute for `.dockerignore`. Git may ignore a secret while Docker still sends it to the builder unless `.dockerignore` excludes it.

If Juan creates `.env.example`, it may contain variable names and safe defaults only. It must not be copied from `.env`, and it is documentation rather than a production secret store.

### 3. Runtime configuration must remain runtime-only

Safe default runtime values for the deterministic path include:

```text
PROCURERAG_LIVE_LLM=0
LANGSMITH_TRACING=false
LANGSMITH_TRACING_V2=false
```

`OPENROUTER_API_KEY` has no image default and should not be passed for the free smoke. If live smoke is later required, pass it through a runtime secret/environment mechanism and never print it, inspect it, or include it in image history.

Do not use Dockerfile `ARG`, `ENV`, `COPY .env`, or a committed compose value to carry a real API key. Build-time secrets and runtime secrets solve different problems; ProcureRAG should not need provider credentials at build time.

### 4. Model packaging is the central Day 22 design decision

The application is not only Python code. The live local retrieval path needs model artifacts used by sentence-transformers/cross-encoder components. Choose and document one bounded strategy:

| Strategy | Reproducibility | Image size/build time | Startup network | Best use today |
|---|---|---|---|---|
| Bake/prefetch exact model artifacts during build | strongest local run reproducibility | largest/slower image | none after build | preferred if Juan can make the cache path explicit and prove an offline run |
| Warm a named runtime cache volume before the real run | host cache survives container restarts | smaller image; first run slower | first warm-up needs network | acceptable if the runbook clearly separates warm-up from offline steady-state |
| Download into the writable container on every start | weakest | smaller image | every fresh start needs network | document as a fallback/blocker, not a production-ready claim |

Juan: I prefer the Warm a named runtime cache volume before the real run option.

Whichever path Juan chooses, record:

- exact model identifiers and cache location;
- whether build or first start requires network;
- whether a fresh container can start with `--network none` after preparation;
- measured image size and startup time;
- the trade-off for Day 23/Azure cold starts.

Do not claim “offline” merely because the Python packages are in the image. The model files are a separate dependency boundary.

### 5. One process and a truthful health check

Use one Uvicorn process today. Multiple workers would multiply model memory and create independent rate-limit counters. The process should use an exec-form command so signals reach Uvicorn correctly, bind `0.0.0.0` inside the container, and expose the chosen container port.

A health check should call `/health` and allow enough startup grace for model initialization. A slim Python image may not include `curl`; a standard-library Python probe avoids adding an OS package solely for health checking.

The container health check answers “did this service start and construct its local service?” It does not evaluate retrieval relevance, citation validity, or live-provider availability. Those stay separate smoke/eval gates.

### 6. Port mappings have two sides

Inside the container, Uvicorn must listen on `0.0.0.0:8000` so Docker networking can reach it. On the host, prefer:

```text
127.0.0.1:8000 -> container 0.0.0.0:8000
```

That keeps the local prototype off the LAN while still proving Docker networking. Explain why `EXPOSE 8000` documents the image contract but does not itself publish the port; `docker run -p ...` creates the host mapping.

### 7. Latency and cost evidence must name the layer

Record separate numbers rather than one vague “request latency”:

- image build duration and whether Docker cache was warm/cold;
- image size;
- cold container startup until healthy;
- warm deterministic `/health` latency;
- warm deterministic `/query` latency;
- optional live-model latency only if explicitly enabled and bounded;
- model-download bytes/time if the chosen strategy downloads at build or startup.

For cost, distinguish:

- local CPU/RAM and image storage;
- Hugging Face/model egress and cold-start implications;
- optional OpenRouter token spend;
- future Azure compute/registry/logging cost.

Day 22 does not need a cloud invoice or load test. It needs honest boundaries and enough measurements to inform Day 23.

## Target evidence by end of day

### Source and design evidence

- [ ] Exact source sections above are marked complete or summarized in `docs/learning-log.md`.
- [ ] The image contract is written before or alongside the build:
  - [ ] Python/base image decision;
  - [ ] uv installation/version-pinning decision;
  - [ ] locked dependency-install command;
  - [ ] project files copied into the runtime image;
  - [ ] non-root user decision;
  - [ ] one-worker Uvicorn command;
  - [ ] container port and health-check command;
  - [ ] model artifact/cache strategy.
- [ ] Runtime configuration table distinguishes safe defaults, optional live settings, and secrets.

### Artifact evidence — Juan-owned

- [ ] A root `Dockerfile` exists and can be explained instruction by instruction.
- [ ] A root `.dockerignore` exists and excludes `.env`, `.env.*` except a deliberately safe `.env.example` if one is created, `.venv`, caches, git history, and local artifacts not needed at runtime.
- [ ] A runbook exists, either as a clear Day 22 section in `docs/learning-log.md` or a focused doc such as `docs/docker-runbook.md`.
- [ ] Optional compose config is included only if it makes the runtime contract clearer; compose is not required.
- [ ] No changes weaken Day 21's default-off live-LLM, tracing, role/confidentiality, pending-approval, or rate-limit behavior.

### Actual container gates

When Docker is available:

- [ ] `docker build` succeeds from a clean repo checkout and the exact command/tag is recorded.
- [ ] Image inspection records image id/tag, size, base/platform, default user, exposed port, and command without printing environment secret values.
- [ ] `docker run` starts with no provider key and with live LLM/tracing explicitly off.
- [ ] The container reaches `healthy` or the runbook records the exact reason it cannot.
- [ ] `GET /health` returns the Day 21 typed health response.
- [ ] A deterministic `POST /query` succeeds with no paid provider.
- [ ] A Q091/Q092-shaped request still returns `pending_approval` when no decision is supplied.
- [ ] One blocked/off-topic request proves the API boundary still works inside the image.
- [ ] The run uses host-loopback port publication and the container is removed afterward.
- [ ] Logs contain no raw key, `.env` content, or unexpected traceback.
- [ ] The selected model strategy is tested: offline steady-state if claimed, or exact startup-network dependency if not.

### Repo gates

- [ ] `pytest`, `compileall`, Ruff, and retrieval regression remain green with LangSmith tracing explicitly off.
- [ ] `git diff --check` is clean.
- [ ] `git status --short` shows only intentional Day 22 artifacts.
- [ ] The learning-log evidence contains real command output, not “should work” prose.

## Recommended 6-hour split

### Block 0 — Reactivate the service baseline and write the container contract, 30–45m

Run the deterministic gates with SaaS tracing disabled:

```bash
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false \
  ./.venv/bin/python src/regression_suite.py --verify-retrieval
```

Then write a one-page contract before the Dockerfile:

| Decision | Chosen value | Why | Proof command |
|---|---|---|---|
| Base image | _TODO_ | _TODO_ | `docker image inspect ...` |
| Python version | _TODO_ | project requires `>=3.11` | `python --version` in image |
| uv version/source | _TODO_ | locked/reproducible install | `uv --version` in image |
| Dependency mode | runtime only, no dev by default | smaller production artifact | inspect installed env |
| App command | _TODO_ | exec form; one worker; `0.0.0.0` | image inspect + logs |
| Container port | _TODO_ | Day 23 contract | `/health` smoke |
| Runtime user | _TODO_ | avoid root if practical | `id` in container |
| Model strategy | bake / named cache / explicit download fallback | _TODO_ | offline/startup probe |
| Health check | _TODO_ | startup-aware | `docker inspect` health |

### Block 1 — Read the exact container sources, 75–90m

Read the named FastAPI, uv, Docker build-context, Dockerfile, and freeCodeCamp sections. Write five short answers:

1. Why not copy `.venv`?
2. Which files should be copied before source code to improve layer reuse?
3. Why can `.gitignore` be correct while the Docker build context is still unsafe?
4. What changes between `127.0.0.1` on the host and `0.0.0.0` inside the container?
5. Where will the two retrieval models come from in a fresh container?

Do not copy a generic FastAPI Dockerfile without mapping it to ProcureRAG's flat `src` imports, `--app-dir src`, locked uv environment, corpus path, model cache, and startup time.

### Block 2 — Design the artifact and runbook, 45–60m

Decide the minimum artifacts:

- required: `Dockerfile`;
- required: `.dockerignore`;
- required: runbook evidence in `docs/learning-log.md` or `docs/docker-runbook.md`;
- optional: safe `.env.example` containing names/safe defaults only;
- optional: compose file if it clarifies ports, cache volume, health check, and runtime variables.

Define the exact smoke matrix before implementation:

| Probe | Expected result | Paid/network behavior |
|---|---|---|
| `/health` | `status=ok`, `live_llm=false` | no provider call |
| deterministic Q001 or another labeled control | `not_generated` with sources | local retrieval only |
| Q091/Q092 without decision | `pending_approval`, no `run_id` | no retrieval/model call by Day 21 contract |
| off-topic input | `blocked` | no retrieval/model call |
| optional live smoke | bounded `answered`/documented provider result | paid and explicitly opt-in |

### Block 3A — Primary route: Juan-owned Docker artifact, 120–150m

Juan implements the image and ignore/runbook artifacts.

Recommended constraints, not a substitute implementation:

- use an official Python base image;
- preserve `pyproject.toml` + `uv.lock` and use a locked sync;
- install runtime dependencies without silently resolving new versions;
- copy only the source, corpus, and runtime files the service needs;
- do not copy host `.venv`, `.env`, git history, tests/caches, or local traces into the runtime image unless a recorded reason requires one of them;
- use a non-root runtime user if practical;
- use one Uvicorn process;
- use exec-form startup with `api:app --app-dir src --host 0.0.0.0`;
- make the health check tolerant of model startup time;
- leave live LLM and LangSmith tracing off by default;
- make model-cache behavior explicit and measurable.

When Docker is available, record actual build and run commands. A safe local shape is:

```bash
docker build --tag procurerag-api:day22 .

docker run --rm --name procurerag-day22 \
  --publish 127.0.0.1:8000:8000 \
  --env PROCURERAG_LIVE_LLM=0 \
  --env LANGSMITH_TRACING=false \
  --env LANGSMITH_TRACING_V2=false \
  procurerag-api:day22
```

Adjust for the chosen model-cache strategy. Do not pass the real `.env` for the default smoke.

### Block 3B — Fallback when Docker is unavailable, 60–90m

The Hermes VM currently has no `docker` command. If Juan's available machine also lacks a functioning Docker daemon:

1. Create the Dockerfile, `.dockerignore`, and runbook as Juan-owned artifacts.
2. Run all non-Docker repo gates.
3. Record the exact output of:

```bash
docker --version
docker info
```

4. If only the daemon is unavailable, distinguish that from “CLI not installed.”
5. Optionally perform static checks that are locally available, but do not describe them as a successful Docker build.
6. Name the next machine/CI route that will perform the actual build/run.

This fallback is acceptable for session progress but **does not satisfy the Week 5 `Docker build works` gate**. HER-290 remains open until real build/run evidence exists.

### Block 4 — Smoke, measurements, evidence, and interview drill, 60–75m

Record on eval-report.md:

- cold build time and warm cached rebuild time if practical;
- image size;
- startup-to-healthy time;
- `/health` output;
- deterministic query status/source summary;
- pending-approval result;
- chosen model strategy and offline/startup-network proof;
- container logs/exit/cleanup result;
- all repo gate outputs;
- any exact blocker.

Then answer the interview drill below without notes.

## Interview drill

1. **Why should you not copy the host `.venv` into the image?**

   **Expected answer shape:** The host environment is platform- and path-specific and can contain wrong-architecture wheels, caches, editable paths, and dev state. The image should recreate dependencies from the lockfile for its own OS/architecture.

2. **What is the difference between `.gitignore` and `.dockerignore` for secret safety?**

   **Expected answer shape:** `.gitignore` controls what Git tracks. `.dockerignore` controls what Docker sends as build context. A secret can be untracked and still be sent to the Docker builder or copied into a layer unless `.dockerignore` excludes it.

3. **Why bind Uvicorn to `0.0.0.0` in the container but publish to `127.0.0.1` on the host?**

   **Expected answer shape:** Docker must reach the process through the container network, so the process listens on all container interfaces. Host loopback publication keeps this unauthenticated prototype local instead of exposing it to the LAN.

4. **Why is one Uvicorn worker the honest choice today?**

   **Expected answer shape:** Every worker would load its own models and have its own in-memory rate limiter. That multiplies memory and effective request allowance. The service has no distributed limiter or shared state yet.

5. **Where do the sentence-transformer/cross-encoder models come from in a fresh image?**

   **Expected answer shape:** Name the chosen strategy: baked/prefetched cache, a warmed persistent cache volume, or startup download. State which step needs network, where files live, and whether an offline steady-state run was proved.

6. **What does `/health` prove, and what does it not prove?**

   **Expected answer shape:** It proves the containerized app started and can answer the health route; depending on app startup, it can imply local models/service construction completed. It does not prove retrieval quality, citation correctness, live provider health, authentication, or production readiness.

7. **How do Docker layers and the uv lockfile solve different reproducibility problems?**

   **Expected answer shape:** The lockfile pins the resolved dependency graph. Docker layers package the filesystem/build steps and allow cache reuse. Layer cache can be stale or invalidated independently; a cached layer is not a dependency specification.

8. **How should OpenRouter/LangSmith secrets enter a deployed container?**

   **Expected answer shape:** At runtime through the platform's secret/environment mechanism, never through Dockerfile `ARG`/`ENV`, copied `.env`, source control, logs, or image history. The deterministic default needs no provider key.

9. **What measurements would you take before choosing an Azure Container Apps CPU/memory profile?**

   **Expected answer shape:** Image size, cold start to healthy, model memory, warm request latency, concurrent behavior, model download/cache behavior, optional LLM latency, and whether one worker is required. p95/load evidence is still future work.

## Hermes review protocol

When Juan has a serious Day 22 pass ready, ask Hermes:

> Day 22 Docker packaging done. Review HER-290: the exact FastAPI/uv/Docker/freeCodeCamp source sections, Dockerfile and `.dockerignore`, uv lock/install and layer-cache strategy, non-root/one-worker/startup command, model artifact/cache decision, health check, runtime config/secrets boundary, actual Docker build/run evidence, image size and cold-start/query measurements, `/health`, deterministic query, pending-approval and blocked-input smoke, learning-log evidence, and all pytest/compile/Ruff/regression outputs. Verify no `.env` or secret entered the build context/image/logs. If Docker evidence is blocked, confirm the exact CLI/daemon error and do not mark the Docker criterion complete. Do not write or rewrite the implementation for me; return precise findings and quiz me on the interview drill.

Hermes should review the artifacts, run every locally possible gate, inspect image/container metadata when Docker is available, verify acceptance criteria, quiz Juan, and either close HER-290 or return precise remaining tasks. Hermes must not replace Juan's implementation.

## Stop condition

Day 22 is complete only when:

1. The exact source sections are completed or summarized in the learning log.
2. Juan can explain every Dockerfile instruction and every `.dockerignore` category.
3. The image installs from the locked project dependency contract and does not copy the host `.venv`.
4. No `.env`, API key, token, or secret-like value is present in the build context, image layers/config, runtime command, or logs.
5. The model artifact/cache strategy is explicit, measured, and tested as far as claimed.
6. One-worker Uvicorn binds `0.0.0.0` in the container; the local host mapping is documented and defaults to loopback.
7. An actual Docker build succeeds and a real container reaches healthy state on a Docker-capable machine.
8. `/health`, a deterministic no-key query, a pending-approval case, and a blocked-input case are recorded from the running container.
9. `pytest`, `compileall`, Ruff, retrieval regression, and `git diff --check` pass.
10. `docs/learning-log.md` contains real commands/results, measurements, trade-offs, and remaining risks with no TODO placeholders for completed work.
11. Juan can answer the interview drill without notes.

A well-written Dockerfile with `docker: command not found` evidence is useful fallback progress, but it is **not** completion of HER-290 or the Week 5 Docker gate. Actual build/run evidence remains required.
