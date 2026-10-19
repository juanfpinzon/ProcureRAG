# Day 23 — Azure Container Apps Deployment or Evidence-Backed Fallback

Date: 2026-10-17 kickoff.

Linear: HER-291 — Day 23 loop: Azure Container Apps or documented deployment fallback.

Related gate: HER-270 — Week 5 gate: serving, Azure, CI/CD, MCP.

Project rule: Juan owns every deployment/configuration artifact and any change to the `Dockerfile`, application code, tests, or cloud resources. Hermes may scaffold this route, review evidence, quiz, and help debug after a serious attempt; Hermes does not replace Juan's implementation.

## Course target for today

**No new Boot.dev chapter today.** Day 23 is a cloud-deployment bridge day. It carries Day 22's real container into Azure Container Apps, or produces an exact, reproducible fallback if account, subscription, CLI, quota, registry, or deployment setup blocks the cloud route.

Use these exact source pages and sections.

### Primary Microsoft Learn sources

1. **Microsoft Learn — `Deploy a Flask or FastAPI web app as a container in Azure Container Apps`** - All read.

   <https://learn.microsoft.com/en-us/azure/developer/python/tutorial-containerize-simple-web-app>
   - `Prerequisites`.
   - `Add Dockerfile and .dockerignore files` — compare with ProcureRAG's completed Day 22 artifact; do not replace it with the tutorial sample.
   - `Build and run the image locally` — reactivate only.
   - `Deploy web app to Azure`.
   - `Make updates and redeploy`.
   - `Clean up`.

2. **Microsoft Learn — `Deploy Azure Container Apps with the az containerapp up Command`** - All read.

   <https://learn.microsoft.com/en-us/azure/container-apps/containerapp-up>
   - `Set up the Azure CLI`.
   - `Deploy an existing image`.
   - `Deploy from local source code`.
   - `Configure container app settings`.
   - `Redeploy a container app`.

3. **Microsoft Learn — `Quickstart: Deploy your first container app with containerapp up`** - All read.

   <https://learn.microsoft.com/en-us/azure/container-apps/get-started>
   - `Prerequisites`.
   - `Setup`.
   - `Create and deploy the container app`.
   - `Verify deployment`.
   - `Clean up resources`.

4. **Microsoft Learn — `Configure Ingress for your app in Azure Container Apps`** - All read.

   <https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to>
   - `Ingress settings`.
   - `Automatic port detection`.
   - `Enable ingress`.
   - Understand `external`, `targetPort`, HTTPS termination, and why the app still listens on `0.0.0.0:8000` inside the container.

5. **Microsoft Learn — `Health probes in Azure Container Apps`** - All read.

   <https://learn.microsoft.com/en-us/azure/container-apps/health-probes>
   - `HTTP probes`.
   - `TCP probes`.
   - `Restrictions`.
   - `Default configuration`.
   - Distinguish Container Apps startup/readiness/liveness probes from the Dockerfile's local `HEALTHCHECK`; do not assume Azure imported the Docker health-check timing.

6. **Microsoft Learn — `Manage environment variables on Azure Container Apps` and `Manage secrets in Azure Container Apps`** - All read.

   <https://learn.microsoft.com/en-us/azure/container-apps/environment-variables>

   <https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets>
   - `Configure environment variables`.
   - Secret references through `secretref:<name>`.
   - Revision behavior when environment variables change.
   - Application-scoped secret behavior and the restart/new-revision implications.
   - Day 23's deterministic deployment must need **no provider secret**. Read the secret path so Juan can explain it; do not add or print a dummy key.

7. **Microsoft Learn — `View log streams in Azure Container Apps`** - All read.

   <https://learn.microsoft.com/en-us/azure/container-apps/log-streaming>
   - `View log streams via the Azure CLI`.
   - System logs versus container console logs.
   - Revision, replica, and container selection when diagnosing a failed deployment.

### Companion sections to reactivate

- **Microsoft Learn — `Set scaling rules in Azure Container Apps`** - Read.

  <https://learn.microsoft.com/en-us/azure/container-apps/scale-app>
  - `Scale definition`.
  - HTTP scaling, especially `minReplicas`, `maxReplicas`, scale-to-zero, and the cold-start trade-off.

- **freeCodeCamp — `Production RAG with LangChain & Vector Databases`** - Fully done.

  <https://www.freecodecamp.org/news/production-rag-with-langchain-vector-databases/>
  - Reactivate `Production Hosting`.
  - Reactivate `Three Pillars of Production Visibility`.
  - Do not rewatch/rebuild the whole course today.

## Day 23 objective

Deploy the real ProcureRAG FastAPI container through a production-shaped Azure Container Apps path and collect enough evidence to answer:

> “Which artifact was deployed, how did it reach the registry and revision, what configuration was injected at runtime, how did ingress reach port 8000, how did the platform decide the replica was ready, where did the Hugging Face models come from on a fresh host, what did the logs show, how was cost/exposure bounded, and what exactly was cleaned up?”

A successful day is not `az containerapp up` returning without an error. It is a verified deployment handle plus deterministic API behavior, sanitized operational evidence, an explicit model/cold-start contract, and cleanup or an intentional retention decision. If Azure is blocked, the fallback must preserve the exact failed command/error and a bounded retry path; vague “Azure setup issue” prose does not pass.

## Starting state

### Day 22 artifact baseline

Day 22 is closed and gives Day 23 a real artifact rather than a tutorial sample:

- `Dockerfile` packages `src/api.py` with one Uvicorn worker, `0.0.0.0:8000`, a non-root user, locked uv dependencies, CPU-only PyTorch on Linux, safe no-key defaults, and a local Docker `HEALTHCHECK`.
- `.dockerignore` is a fail-closed allow-list; `.env`, host `.venv`, git history, tests, docs, and local caches do not enter the build context.
- `docs/docker-runbook.md` contains the reproducible local build/run contract.
- Day 22 proved both `linux/arm64` and `linux/amd64` build/run paths.
- The deployed service must preserve `/health`, `/query`, `/query/stream`, `pending_approval`, blocked-input handling, role/confidentiality filtering, and live-LLM default-off behavior.
- Current measured `linux/amd64` evidence: about 51 seconds offline startup to healthy and about 682 MiB after smoke on the Hermes VM. Treat those as one machine's measurements, not universal architecture constants.

### The model-cache decision blocks a blind deployment

The Day 22 local image deliberately defaults to:

```text
HF_HOME=/home/procurerag/.cache/huggingface
HF_HUB_OFFLINE=1
```

Locally, a pre-warmed named volume supplies two models (about 106 MB total). A fresh Azure Container Apps replica will not automatically have that Docker named volume. Deploying the current image unchanged with no cache should fail at startup. Therefore **model delivery is the first design decision, before paid cloud deployment**.

Choose and record one route:

| Route | Cloud behavior | Day 23 verdict |
|---|---|---|
| Bake/prefetch the exact model artifacts into the image | Larger image, but every revision has the models and can start offline | **Recommended primary route** for today's bounded portfolio deployment; 106 MB is small compared with the existing image, and this avoids a runtime Hub dependency | *- Chosen Option -*
| Download at startup with `HF_HUB_OFFLINE=0` | Simplest experiment, but every cold host/replica may need the Hub; startup and rate limits are less predictable | Acceptable as an explicitly labeled deployment experiment/fallback, not an offline/reproducible production claim |
| Mount Azure Files and warm/persist the model cache | Durable shared cache, but adds storage provisioning, mount permissions, lifecycle, and cost complexity | Valid advanced route only if Juan wants that complexity; do not let it consume the whole day by default |

If models are baked, record exact model ids, revisions/digests where practical, cache path, image-size delta, and whether the deployed revision starts without Hub access. If startup download is used, record the exact network dependency, cold-start time, retry/failure behavior, and why it is a fallback.

### Kickoff verification — 2026-10-17

Repo baseline on `main`, commit `509854d`, before the Day 23 route/log scaffold:

```text
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/pytest -q
357 passed in 6.93s

./.venv/bin/python -m compileall -q src tests
clean, no output

./.venv/bin/python -m ruff check src tests
All checks passed!

LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false \
  ./.venv/bin/python src/regression_suite.py --verify-retrieval
All frozen cases matched their expected state.
The current retrieval pipeline matched every case's expectation.

git diff --check
clean, no output

git status --short
clean, no output
```

Tooling on the Hermes VM at kickoff:

```text
az version
bash: az: command not found

docker client: 29.1.3, linux/amd64
Docker daemon: available through `sg docker -c ...` because the long-lived Hermes process has not refreshed its supplementary `docker` group
local image `procurerag-api:day22`: not currently present
```

This means the Hermes VM can rebuild/test the Docker artifact, but it cannot attempt Azure deployment until Azure CLI is installed and an interactive Azure account/subscription is available. Juan may use his Mac, Azure Cloud Shell, or install the CLI deliberately. Do not turn credential setup into credential thrash, and never paste subscription secrets or tokens into the repo/log.

## Key concepts to nail today

### 1. Source-to-cloud is a chain of independently verifiable artifacts

For `az containerapp up --source .`, the chain is:

1. local source and Docker build context;
2. a remote image build;
3. an image pushed to Azure Container Registry;
4. a Container App revision configured to pull that image;
5. one or more replicas started from the revision;
6. ingress forwarding HTTPS traffic to container port 8000.

A green command at step 2 does not prove step 5 became healthy. Record the resource group, registry/image/tag or digest, environment, app, active revision, replica state, FQDN, and target port separately.

### 2. Container Apps probes are not the Dockerfile `HEALTHCHECK`

Day 22's Docker health check is local Docker evidence. Azure Container Apps has its own startup, readiness, and liveness probes. With ingress enabled, the platform can add defaults when custom probes are absent. Inspect what the deployed revision actually has; do not write “the Docker health check protects Azure” unless the platform configuration proves an equivalent probe exists.

The current `linux/amd64` evidence includes a 51-second startup. A too-aggressive startup/readiness configuration can create a restart loop even though the app is correct. If custom probes are used, route them to `/health` on port 8000 and give model loading enough startup grace. `/health` becomes available only after ProcureRAG's lifespan startup loads the models and constructs the service.

### 3. Ingress terminates public HTTPS and forwards to target port 8000

The service still listens on `0.0.0.0:8000` inside the container. Container Apps exposes an HTTPS FQDN and sends traffic to `targetPort=8000`. Keep insecure HTTP disabled; external ingress is only needed for the temporary smoke.

ProcureRAG has no authentication and the role is caller-asserted. Therefore the recommended Day 23 deployment is a **short-lived, deterministic, no-provider-key smoke deployment in a dedicated disposable resource group**, followed by resource-group deletion or explicit ingress shutdown. Do not leave an unauthenticated prototype publicly exposed by accident.

### 4. Runtime configuration and secrets are different

Safe, non-secret environment configuration for the deterministic path:

```text
PROCURERAG_LIVE_LLM=0
LANGSMITH_TRACING=false
LANGSMITH_TRACING_V2=false
```

`HF_HUB_OFFLINE` and `HF_HOME` depend on the selected model-delivery strategy. `OPENROUTER_API_KEY` is not needed and should be absent. If Juan performs a separate bounded live smoke later, the key must enter through a Container Apps secret and `secretref`, never a command transcript, environment dump, Dockerfile, `.env`, image history, or Linear/log comment.

Changing environment variables creates a new revision. Updating an application-scoped secret alone has different lifecycle behavior; Juan should be able to explain when a revision or restart is required.

### 5. Scale-to-zero trades cost for cold starts

For a short-lived portfolio smoke, `minReplicas=0` and `maxReplicas=1` is a reasonable cost boundary **only if the app can recover from a true cold start**. A startup-download model route pays the model-download latency again on a fresh replica and may fail under Hub availability/rate limits. A baked-model image removes that dependency but still pays image-pull and model-load time.

Record first-request/cold-start behavior separately from warm `/health` and warm `/query`. Do not present a 39 ms warm local query as cloud cold-start latency.

### 6. Logs must prove the deployment without leaking values

Collect both:

- **system logs** for image pull, revision provisioning, scaling, and platform errors;
- **console logs** for Uvicorn startup, application exceptions, and HTTP access lines.

Record only sanitized output. Never run commands that print all environment values or list secret values into the learning log. A clean log means no unexpected traceback and no secret-like content; it does not prove answer quality.

### 7. Revisions make rollback explicit

A new image or revision-scope configuration change creates a new immutable revision. Record the active revision name and image digest/tag. A defensible rollback statement names the previous revision/image and how traffic would return to it; “redeploy the old code” is weaker than identifying the immutable artifact.

## Target evidence by end of day

### Source and design evidence

- [ ] Every exact Microsoft Learn/freeCodeCamp section above is marked complete or summarized in `docs/learning-log.md`.
- [ ] A deployment contract is written before cloud mutation:
  - [ ] Azure subscription/account permission checked without logging credentials;
  - [ ] dedicated resource group, region, app name, environment name, registry/image path, and target port;
  - [ ] model-delivery choice with cold-start consequence;
  - [ ] external-ingress duration and cleanup plan;
  - [ ] safe environment variables and explicit absence of provider keys;
  - [ ] startup/readiness/liveness probe decision;
  - [ ] CPU/memory, min/max replicas, and cost boundary;
  - [ ] revision/rollback evidence plan.

### Azure artifact evidence — Juan-owned

Primary route:

- [ ] `az version`, `az account show`, Container Apps extension, and required provider registration states are recorded safely.
- [ ] `az containerapp up` or an equivalent explicit build/push/deploy path succeeds.
- [ ] The exact resource handles are recorded: resource group, Container Apps environment, registry/image tag or digest, app, active revision, and FQDN.
- [ ] The deployed revision has an explicit model-artifact path and starts on a fresh replica.
- [ ] External HTTPS ingress reaches container target port 8000.
- [ ] The deployed app runs with live LLM and LangSmith tracing off and without `OPENROUTER_API_KEY`.
- [ ] Scale and resource settings are recorded; cost exposure is bounded.

Evidence-backed fallback if Azure is blocked:

- [ ] Record the exact command and complete non-secret error category (CLI absent, login/account, no active subscription, RBAC, provider registration, quota, ACR build, image pull, startup/probe, or another named layer).
- [ ] State the last successful layer and the first failed layer in the source-to-cloud chain.
- [ ] Preserve Day 22's local Docker evidence and, when relevant, rebuild/run the cloud-target image locally.
- [ ] Name the fallback host/path chosen and the exact retry checklist; do not claim Azure or HER-291 complete.

### Cloud smoke evidence

- [ ] `GET https://<fqdn>/health` returns HTTP 200 and the typed health payload with `live_llm=false`.
- [ ] A deterministic no-key `POST /query` for Q001 returns the expected non-paid status and source metadata.
- [ ] Q091 or Q092 without a decision returns `pending_approval`, no run id, and no sources.
- [ ] One off-topic or injection-shaped request returns `blocked`.
- [ ] System and console logs are inspected and sanitized; no unexpected traceback or secret exposure appears.
- [ ] Warm latency and a true cold-start/startup measurement are recorded separately.
- [ ] The active revision/image and replica state are captured.
- [ ] Cleanup is executed and verified, or Juan records the intentional retention decision, ingress/auth risk, owner, budget/cost alert, and deletion date.

### Repo gates

- [ ] `pytest`, `compileall`, Ruff, retrieval regression, and `git diff --check` stay green.
- [ ] `git status --short` contains only intentional Day 23 artifacts.
- [ ] No real `.env`, key, token, subscription credential, or secret-bearing output enters Git, docs, logs, Linear, or chat.
- [ ] `docs/learning-log.md` contains real outputs/handles and no TODO placeholders for completed work.

## Recommended 6-hour split

### Block 0 — Reactivate the baseline and write the deployment contract, 30–45m

Run:

```bash
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false ./.venv/bin/pytest -q
./.venv/bin/python -m compileall -q src tests
./.venv/bin/python -m ruff check src tests
LANGSMITH_TRACING=false LANGSMITH_TRACING_V2=false \
  ./.venv/bin/python src/regression_suite.py --verify-retrieval
git diff --check
git status --short
```

Then fill this decision table before cloud mutation:

| Decision | Chosen value | Why | Proof command/evidence |
|---|---|---|---|
| Subscription/region | _TODO_ | permissions, proximity, service availability | `az account show`, provider state |
| Resource group | _TODO_ | dedicated + disposable | `az group show` |
| App/environment names | _TODO_ | lowercase/unique/reusable | `az containerapp show`, env query |
| Build path | `--source .` / existing registry image / other | _TODO_ | registry image + revision image |
| Model delivery | baked / startup download / Azure Files | _TODO_ | fresh-replica startup proof |
| Ingress/port | external HTTPS -> 8000 for smoke | temporary public verification | ingress query + `/health` |
| Runtime configuration | live LLM/tracing off | free deterministic path | app config names, `/health` |
| Probe strategy | default inspected / custom HTTP probes | current startup may be ~51 s | revision config + logs |
| Resources/scale | _TODO CPU/memory_; min 0 or 1; max 1 | memory/cost/cold-start trade-off | app revision config |
| Cleanup/retention | delete RG / disable ingress / retain until date | no accidental public/cost tail | final `az` verification |

**Gate before Block 3:** the fresh cloud replica must have a valid model path. Do not deploy the current offline/no-cache contract blindly.

### Block 1 — Read the exact sources, 75–90m

Complete the exact sections above and write concise answers to:

1. What does `az containerapp up --source .` create or reuse?
2. Where does the built image live, and which image does the active revision run?
3. What is the difference between external ingress, the public HTTPS endpoint, and target port 8000?
4. Why is the Dockerfile `HEALTHCHECK` not enough evidence for Azure's startup/readiness/liveness behavior?
5. Which settings create a new revision, and which secret changes require a restart or new revision?
6. What makes scale-to-zero safe or unsafe for this model-loading service?
7. Which logs diagnose image-pull/provisioning failures versus Python/Uvicorn failures?

### Block 2 — Design the Azure artifact contract, 45–60m

Choose the model route first. Recommended order:

1. **Primary:** make the cloud-target image self-contained by baking the two exact model artifacts into its cache, then keep runtime offline.
2. **Bounded fallback:** allow startup download for the first Azure experiment, explicitly label it as network-dependent, and measure a true fresh-replica cold start.
3. **Advanced only:** Azure Files cache with a documented warm-up and mount/permission lifecycle.

Then choose a dedicated disposable resource group and names. A safe shell shape is:

```bash
export LOCATION=<chosen-region>
export RESOURCE_GROUP=<dedicated-day23-rg>
export CONTAINERAPP_ENV=<unique-environment-name>
export CONTAINERAPP_NAME=<unique-lowercase-app-name>
```

Do not put credentials or keys in these variables or in the route/log.

### Block 3A — Primary route: Juan-owned Azure deployment, 120–150m

Prerequisite/discovery commands:

```bash
az version
az login
az account show --query '{name:name,id:id,state:state,user:user.name}' -o json
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider show --namespace Microsoft.App --query registrationState -o tsv
az provider show --namespace Microsoft.OperationalInsights --query registrationState -o tsv
```

Do not copy tokens or full credential output into docs. Record only the account/subscription handle needed for reproducibility, and redact anything sensitive.

After Juan's model-delivery decision is implemented and locally verified, the source-to-cloud deployment shape is:

```bash
az containerapp up \
  --name "$CONTAINERAPP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --environment "$CONTAINERAPP_ENV" \
  --source . \
  --ingress external \
  --target-port 8000
```

Then apply/verify only safe deterministic settings and the selected scale/resource contract using current `az containerapp update --help` syntax. At minimum the deployed configuration must resolve to:

```text
PROCURERAG_LIVE_LLM=0
LANGSMITH_TRACING=false
LANGSMITH_TRACING_V2=false
OPENROUTER_API_KEY absent
```

Use `HF_HUB_OFFLINE=1` only when the image or mounted storage really contains the models. Do not paper over a missing cache by setting contradictory values.

Collect handles without printing secret values:

```bash
az containerapp show \
  --name "$CONTAINERAPP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query '{fqdn:properties.configuration.ingress.fqdn,targetPort:properties.configuration.ingress.targetPort,latestRevision:properties.latestRevisionName,latestReadyRevision:properties.latestReadyRevisionName}' \
  -o json

az containerapp revision list \
  --name "$CONTAINERAPP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  -o table
```

Inspect the active revision's image, resources, scale, probes, and **environment-variable names/references**, not secret values. If the CLI output shape differs, use `az containerapp show -o json` interactively, then narrow the final documented query to safe fields.

### Block 3B — Fallback when Azure is blocked, 60–90m

Stop before credential or quota thrash. Preserve:

1. exact command;
2. non-secret error text/category;
3. CLI/extension version;
4. account/subscription state if safely available;
5. last successful layer and first failed layer;
6. resources created before failure;
7. whether they were cleaned up;
8. exact retry command/checklist.

Fallback priority:

1. Azure Cloud Shell with the same repo and source-to-cloud command, if only the local CLI is missing.
2. Juan's Mac with Azure CLI and Docker, if account/subscription access exists there.
3. A comparable container host only if Azure account/subscription/RBAC is genuinely unavailable; record why the semantics differ (build/registry, ingress, secrets, probes, logs, scaling, cleanup).
4. Local-only Day 22 evidence plus a complete Azure retry plan is progress, but does **not** close HER-291 or satisfy the HER-270 Azure/fallback criterion unless the documented fallback itself is executed and verified.

### Block 4 — Cloud smoke, logs, cleanup, and interview drill, 60–75m

After the FQDN is ready:

```bash
export BASE_URL="https://<fqdn>"

curl -fsS "$BASE_URL/health"

curl -fsS -X POST "$BASE_URL/query" \
  -H 'content-type: application/json' \
  --data '{"query":"What approval is required for a EUR 60,000 purchase order?","role":"buyer","query_id":"Q001"}'

curl -fsS -X POST "$BASE_URL/query" \
  -H 'content-type: application/json' \
  --data '{"query":"<exact Q091 or Q092 labeled question from the canonical query file>","role":"buyer","query_id":"Q091"}'

curl -fsS -X POST "$BASE_URL/query" \
  -H 'content-type: application/json' \
  --data '{"query":"What is the capital of France?","role":"buyer"}'
```

Use the exact canonical text when sending a labeled `query_id`; `src/api.py` rejects a label paired with another question. Do not substitute invented Q091/Q092 text.

Inspect logs:

```bash
az containerapp logs show \
  --name "$CONTAINERAPP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --type system --tail 50

az containerapp logs show \
  --name "$CONTAINERAPP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --type console --tail 50
```

Record sanitized summaries, not raw environment/secret dumps. Verify no unexpected traceback and identify the active revision/replica.

For a disposable resource group, cleanup is intentionally destructive and must target the dedicated Day 23 group only:

```bash
az group delete --name "$RESOURCE_GROUP" --yes --no-wait
az group exists --name "$RESOURCE_GROUP"
```

The second command may remain `true` while asynchronous deletion is in progress. Poll later and record when it becomes `false`. Never run resource-group deletion against a shared group.

## Interview drill

1. **What does `az containerapp up --source .` do beyond `docker run`?**

   **Expected answer shape:** It can create/reuse a resource group, registry, Container Apps environment and Log Analytics workspace; remotely build the Dockerfile, push the image, create a revision, configure ingress, and start replicas. Each layer has its own failure evidence.

2. **Why could the Day 22 image work locally but fail immediately on Azure?**

   **Expected answer shape:** Locally it mounts a pre-warmed named volume while `HF_HUB_OFFLINE=1`. A fresh Azure replica has no Docker named volume. The models must be baked, downloaded at startup, or supplied through mounted cloud storage.

3. **What is the difference between external ingress, target port, and the Uvicorn bind address?**

   **Expected answer shape:** External ingress creates the public HTTPS entry. `targetPort=8000` tells the platform where to forward inside the replica. Uvicorn must listen on `0.0.0.0:8000` so the container network can reach it; Azure handles the public 443 endpoint/TLS.

4. **Why is the Dockerfile health check not the same as Azure startup/readiness/liveness probes?**

   **Expected answer shape:** Docker metadata proves local Docker behavior. Container Apps owns replica lifecycle and routing through its platform probe configuration. Startup gates slow initialization; readiness gates traffic; liveness restarts a stuck process. The deployed revision must be inspected rather than inferred from the Dockerfile.

5. **Why might `minReplicas=0` be cheap but risky for ProcureRAG?**

   **Expected answer shape:** It can scale to zero, reducing idle cost, but the next request pays image pull, model load, and possibly model download. If model delivery depends on the Hub, a fresh replica can be slow or fail. Baked models make scale-to-zero more deterministic but do not eliminate cold start.

6. **How do environment variables and secrets differ in Container Apps?**

   **Expected answer shape:** Non-sensitive config can be plain runtime environment values; sensitive values are application-scoped secrets referenced from env vars. Environment changes create revisions. Secret rotation has its own restart/new-revision behavior. Deterministic Day 23 needs no provider secret.

7. **Which logs would you inspect for an image-pull failure versus a Python startup exception?**

   **Expected answer shape:** System logs for registry/image pull, revision provisioning, replica and probe/platform events; console logs for stdout/stderr from Uvicorn/Python, imports, model loading, and tracebacks.

8. **What makes the deployment reproducible and rollbackable?**

   **Expected answer shape:** Locked dependencies, known image tag/digest, recorded runtime config names, model artifact/version strategy, revision name, probe/scale/ingress configuration, smoke commands, and a previous immutable image/revision to restore or receive traffic.

9. **Why should today's public deployment be temporary?**

   **Expected answer shape:** The service has no authentication, trusts a caller-asserted role, keeps rate limits in process, and lacks durable approval/trace state. Deterministic no-key mode limits spend but not unauthorized access. Use a disposable group, short smoke window, and verified cleanup.

10. **What does `/health` prove in Azure, and what remains unproved?**

    **Expected answer shape:** It proves the active replica completed app startup and can answer HTTP through ingress; with this lifespan, models/service loaded. It does not prove answer quality, citations, auth, provider health, throughput, durable state, or correct multi-client rate limiting.

## Hermes review protocol

When Juan has a serious Day 23 pass ready, ask Hermes:

> Day 23 deployment path done. Review HER-291: exact Microsoft Learn/freeCodeCamp sections; Azure CLI/account/provider prerequisites; model-artifact strategy for a fresh replica; build/registry/image/revision handles; ingress/target port; Container Apps probes; runtime config and secret boundary; CPU/memory/scale and cost limits; public `/health`, deterministic Q001, pending-approval, and blocked-input smoke; system/console logs; cold-start and warm latency evidence; rollback and cleanup; learning-log evidence; and pytest/compile/Ruff/regression outputs. If Azure was blocked, verify the exact failed command/error, the last successful and first failed deployment layers, resources cleaned up, and the executable fallback/retry path. Do not write or rewrite the implementation for me; return precise findings and quiz me on the interview drill.

Hermes should re-read every changed artifact, run all locally possible gates, inspect cloud handles only when Juan provides access/context, verify no secret was printed or committed, and either close HER-291 or return exact remaining tasks. Hermes must not implement the deployment or application changes for Juan.

## Stop condition

Day 23 is complete only when:

1. The exact source sections are completed or summarized in the learning log.
2. Juan can explain the source-to-cloud chain, model delivery, ingress/port, probes, revisions, logs, scaling, secrets, and cleanup without notes.
3. A fresh replica has an explicit, tested model-artifact path; local named-volume assumptions are not silently carried into Azure.
4. Azure Container Apps has a recorded app/revision/image/FQDN and verified deterministic smokes, **or** an executed comparable fallback has the same level of evidence plus the exact Azure blocker and retry path.
5. `/health`, deterministic Q001, pending approval, and blocked input are proved through the deployed endpoint without a provider key.
6. System and console logs are inspected; no unexpected traceback or secret exposure remains.
7. Cold-start and warm behavior are labeled separately, and scale/cost settings are explicit.
8. The public unauthenticated deployment is deleted/disabled after evidence capture, or intentional retention has an owner, budget/cost guard, auth-risk note, and deletion date.
9. `pytest`, `compileall`, Ruff, retrieval regression, and `git diff --check` pass.
10. `docs/learning-log.md` contains real commands, sanitized results, resource handles, trade-offs, cleanup state, and no TODO placeholders for completed work.
11. Juan can answer the interview drill without notes.

A route doc, successful image build, or `az containerapp up` command alone is not completion. The closing evidence is a healthy, behaviorally verified deployment plus operational/cleanup proof—or a genuinely executed fallback with a precise Azure blocker and retry path.
