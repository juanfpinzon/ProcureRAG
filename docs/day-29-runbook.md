# Day 29 runbook: hosting the portfolio demo (Blocks 0–6)

The commands to run, in order, for `docs/day-29-hosted-portfolio-demo.md`. The plan says **what** must be true. This file says **how** to make it true and what to record. The code it relies on:

| Repo / branch | What changed |
|---|---|
| portfolio `day-29-hosting` | `lib/chat/admission.ts` (policy, keys, UTC day, client HMAC), `lib/chat/upstash-admission.ts` (the two Lua scripts, REST client), `lib/chat/bff.ts` (kill switch, admission, lease release rules), `lib/chat/status.ts` + `app/api/chat/status/route.ts` (warm-up check), `lib/chat/server-config.ts` (all server-only settings), `components/ChatPanel.tsx` (warm on intent), `vercel.json` (`dub1`), tests |
| ProcureRAG `day-29` | `deploy/azure/containerapp-template.yaml` (secret refs, model, cap, `__LIVE_LLM__`), `.github/workflows/deploy.yml` (`live_llm` input, secret-name check, token for the URL smoke, readback), `scripts/container_smoke.py` (refusal probes on both routes, `--expect-live-llm`), `scripts/deployed_proof.py` (free deployed proof), `src/generation.py` (`max_retries=0`) |

**Rules for every command below:**

- A secret is read with `read -rs NAME` (nothing echoes) or piped from the command that makes it. It is never typed into a command line, never `echo`ed, never pasted into this repo, a log or a screenshot.
- Record names, states, counts, timings and prices. Never record tokens, keys, the Redis URL or token, the Azure URL, subscription/tenant/client ids, raw IPs, questions or answers from unreviewed logs.
- Placeholders: `<domain>` is your budget domain (e.g. `or-demo-2026-10`), and `<day>` is today's UTC date (`date -u +%F`).

## The settings and where each one lives

| Name | Lives in | What it is |
|---|---|---|
| `procurerag-service-token` | Azure app secret | the API's Bearer token (`PROCURERAG_SERVICE_TOKEN` inside the container, by `secretRef`) |
| `openrouter-api-key` | Azure app secret | the **dedicated** demo key (`OPENROUTER_API_KEY` inside the container, by `secretRef`) |
| `PROCURERAG_SERVICE_TOKEN` | Vercel **Production** + GitHub environment `production` (secret) | the same value as the Azure secret: the BFF sends it, the deploy smoke uses it |
| `PROCURERAG_API_URL` | Vercel Production | `https://<Azure app fqdn>` |
| `PROCURERAG_CLIENT_HASH_SECRET` | Vercel Production | the HMAC key for client digests (64 hex characters) |
| `PROCURERAG_BUDGET_DOMAIN` | Vercel Production | the namespace of every Redis key. One per OpenRouter key |
| `UPSTASH_REDIS_REST_URL` / `_TOKEN` (or `KV_REST_API_URL` / `_TOKEN`) | Vercel Production, injected by the Marketplace | the quota store (the code accepts either pair) |

Nothing is set for Vercel **Preview** or **Development**. A preview deployment therefore has no configuration and answers `unavailable`: there is one enabled path only (plan, invariant 11).

**Rotation of the service token** (three places, together): `az containerapp secret set` → `az containerapp revision restart` (a secret change does not restart a running revision) → `vercel env rm` + `vercel env add` and redeploy Vercel → `gh secret set` for the deploy smoke.

---

## Block 0: account and economics gate (you, before provisioning)

### 0.1 Vercel

1. Re-read the Hobby terms (personal, non-commercial use) and the Functions limits page. Record: plan, maximum duration (the code uses 100 s), the single-region rule, and that `dub1` can be chosen. Plan Hobby, Vercel Function maximum duration	300s (5 minutes), all else good.
2. Decide the account: your **personal** Vercel account. [vercel.com/juanfpinzon](https://vercel.com/marca-ia-s-projects)
3. Check the CLI: `vercel --version`. **The CLI installed on this machine reports 54.4.1, while the plan's kickoff recorded 65.4.0.** Check which one is on your PATH (`which -a vercel`) and record the real version. on this Mac I get 54.4.1 .

### 0.2 Azure subscription state (no identifiers)

```bash
az login
az account show --query '{name:name, state:state, isDefault:isDefault}' -o table
```

The offer, the remaining credit, the trial expiry and the spending limit are not reliably available from the CLI: read them in the portal (**Cost Management + Billing → Subscriptions → your subscription**). Record: offer name, state, spending limit On/Off, credit left, expiry date. Do not record the subscription id.

### 0.3 Cost worksheet (current calculator, `northeurope`, Consumption)

Rates read on **2026-10-28** from Azure's official Retail Prices API (`https://prices.azure.com/api/retail/prices`, region `northeurope`, USD, pay-as-you-go), checked against the Container Apps billing page (free grants per subscription per month: 180,000 vCPU-s, 360,000 GiB-s, 2 million requests). With `minReplicas: 0` the idle rate never applies: a running replica is always billed at the ACTIVE rate. The pricing calculator gave the same totals on 2026-10-29 (cross-check below).

| Line | Usage | Rate on 2026-10-28 | Monthly |
|---|---|---|---|
| Worst case: one 1 vCPU / 2 GiB replica, 720 h | 2,592,000 vCPU-s − 180,000 free = **2,412,000 vCPU-s** | US$0.000024 per vCPU-s (Standard vCPU Active Usage) | **US$57.89** |
| | 5,184,000 GiB-s − 360,000 free = **4,824,000 GiB-s** | US$0.000003 per GiB-s (Standard Memory Active Usage) | **US$14.47** |
| Requests | 2 million free; keeping one replica awake 24/7 needs about 8,640 requests a month | US$0.40 per million above the grant | ≈ US$0 |
| Container Registry (Basic) | 1 registry, every day of the month, whether the app runs or not | US$0.1666 per day | **US$5.00** |
| Log Analytics | first 5 GB a month ingested free (per billing account), 31 days of retention included; this app logs kilobytes a day | US$2.76 per GB above 5 GB | ≈ US$0 |
| **Worst-case total (24/7)** | | | **≈ US$77.36: about 7.7 times the US$10 ceiling** |
| BFF-bounded worst case | every paid question (54) and status check (15) spaced to wake a cold replica: 69 × 6.5 min a day ≈ 224 h a month, minus the 50 free hours | US$0.108 per replica-hour above the grant | ≈ US$18.82 + US$5.00 ACR = **≈ US$23.82** |
| **Normal: scale to zero** | a few wake-ups a day (5 × 6.5 min ≈ 16 h a month), inside the 50 free replica-hours | | compute US$0 + ACR US$5.00 = **≈ US$5.00** |

How to read it:

- **The registry alone costs about US$5 a month, half the ceiling.** That leaves about US$5 of compute, which is about 46 replica-hours beyond the free 50. In total that is roughly 96 hours awake a month, about 29 wake-ups a day.
- **The BFF's limits do NOT keep the cloud bill under US$10 on their own.** Even someone using only the public chat, spacing questions to find a cold replica each time, reaches about US$24. A direct caller of the public Azure URL reaches the 24/7 case: requests refused with 401 still wake the replica. So the US$10 ceiling is enforced by the alert plus your action below, as ADR §8.4 says.
- A cheaper lever exists but is not taken: a shorter scale-down `cooldownPeriod` (default 300 s) would cut each wake-up from about 6.5 to about 2.5 minutes. It would also defeat warm on intent, because the replica would fall asleep again while the visitor types.

**Pricing-calculator cross-check, done 2026-10-29: it matches the table.** The calculator has no "hours running" field. It works out active seconds as requests × execution time ÷ concurrent requests. So a replica awake all month is entered as traffic that multiplies out to 720 h = 2,592,000 s:

| Calculator item | Settings | Result |
|---|---|---|
| Azure Container Apps | North Europe, **Consumption** plan, 1 vCPU, 2 GiB; 1.296 million requests, 1 concurrent request per app, 2000 ms per request (1,296,000 × 2 s ÷ 1 = 2,592,000 s); Required Minimum Replicas **off** | vCPU 2,412,000 billable s = US$57.89; memory 4,824,000 billable GiB-s = US$14.47; requests 0 billable; **US$72.36** |
| Azure Container Registry | North Europe, **Basic**, 1 registry × 30 days × US$0.167; Extra Storage 0 GB; Container Build left at its default (1 CPU × 1 s, inside the 100 free minutes) | **US$5.00** |
| Azure Monitor (Log Analytics) | North Europe, Analytics Logs 0.1 GB a day × 30 days = 3 GB a month, inside the Pay-As-You-Go tier's free 5 GB per billing account; interactive retention 1 month (31 days free); long-term retention 0 | **US$0.00** |
| **Total** | | **US$77.36**, the worst case in the table above |

- With the calculator's default traffic (0.1 million requests, 100 ms each, 20 concurrent), Container Apps shows US$0. That is 500 active seconds a month: the normal, scale-to-zero month, inside the free grant.
- The browser shows decimals with a comma: "1,296" means 1.296 million and "0,1" means 0.1 GB.
- The registry item's default **Bandwidth** line (inter-region, North Europe → East Asia, 5 GB) does not describe this setup. The app pulls its image inside North Europe. That line shows US$0 either way.
- **Container Build** is ACR Tasks, which this repo does not use. Images are built with `docker` (on the laptop or in GitHub Actions) and pushed.
- **Extra Storage** stays 0 while the registry holds less than the 10 GB that Basic includes. Check after a few deploys: `az acr show-usage --name "$ACR_NAME" --resource-group "$RESOURCE_GROUP" -o table`.
- **Must NOT appear in the estimate:**
  - any "Management (hour)" line;
  - Dedicated plan;
  - private endpoint;
  - planned maintenance;
  - idle usage;
  - more than 1 replica.

**Check that your environment does not pay the new hourly environment meters.** Since 2026-09-01 the price list has three meters at **US$0.143 per hour** each (≈ US$103 a month each): Environment Management Hour, Environment Private Endpoint and Environment Planned Maintenance Hour. The pricing page says this "Management" charge applies to the Dedicated plan, private endpoints and planned maintenance, and that the charges add up when several are used. A Consumption-only environment with none of them should therefore pay none. That is a reading of the page, so verify it after Block 3 creates the environment:

```bash
# Expect ["Consumption"] (or null for a Consumption-only environment): no Dedicated profile.
az containerapp env show --name "$CONTAINERAPP_ENV" --resource-group "$RESOURCE_GROUP" \
  --query 'properties.workloadProfiles[].workloadProfileType' -o json
# Expect 0: no private endpoint.
az network private-endpoint list --resource-group "$RESOURCE_GROUP" --query 'length(@)'
# Expect an empty list: no planned-maintenance window (preview command).
az containerapp env maintenance-config list --environment "$CONTAINERAPP_ENV" --resource-group "$RESOURCE_GROUP"
```

Then, one or two days after creating the resources, open **Cost Management → Cost analysis**, group by **Meter**, and confirm that no "Environment … Hour" meter appears. If one does, the ceiling is broken by that fee alone: stop and delete the environment.

Write down the action that catches the over-ceiling cases, as ADR §8.4 requires:

- an **Azure budget** of US$10/month on the resource group, with alerts at **60% (US$6) and 100% of actual cost, and 100% of forecast**, emailed to you (portal: **Cost Management → Budgets → Add**).
  - Not 50%: the registry alone reaches about US$5 by the end of every normal month, so a 50% alert would fire every month for nothing.
  - A 24/7 runaway costs about US$2.58 a day, so the forecast alert should fire about one day after its cost data arrives;
- record, in these words: **a budget alerts on cost data that arrives with a delay of hours. It does not stop the app or its consumption.**
- the owner (you) and the action on an alert: kill switch off (Block 2), then Azure max replicas 0 or ingress off, then revoke the OpenRouter key.

### 0.4 The Redis store (Upstash via the Vercel Marketplace)

1. Vercel dashboard → **Storage → Create → Upstash for Redis**. Region **eu-west-1 (Ireland)**, next to `dub1`. Choose the free plan.
2. Connect it to the project for **Production only** (untick Preview and Development).
3. In the Upstash console, record: the plan, its price and free allowance (commands, data size, bandwidth), the region, **eviction: must be OFF**, persistence, and that `EVAL` (scripting) is listed as supported.
   - Why eviction must be off: under memory pressure an evicting Redis drops keys. A dropped kill-switch key fails closed (chat off), but a dropped counter would RESET today's quota: that would fail open on spend.
4. Check which variable names were injected, by name only: `vercel env ls production`.

  - Free Plan monthly commands allowed: 500,000
  - Resource name: upstash-kv-rose-forest
  - Commands (per second) - 10,000 
  - Request Size - 10 MB
  - Record Size - 100 MB
  - Data Size - 250 MB
  - Monthly Bandwidth - 10 GB

  - REDIS_URL, KV_URL, KV_REST_API_TOKEN, KV_REST_API_READ_ONLY_TOKEN, KV_REST_API_URL 

### 0.5 The dedicated OpenRouter key

1. openrouter.ai → **Keys → Create**: a name such as `procurerag-demo-2026-10`, credit limit **US$5**, reset **monthly**.
2. Verify the limit fields only (the key is read silently and never printed):

   ```bash
   read -rs OPENROUTER_DEMO_KEY   # paste the key, press Enter: nothing is shown
   curl -s https://openrouter.ai/api/v1/key -H "Authorization: Bearer $OPENROUTER_DEMO_KEY" \
     | python3 -c 'import json,sys; d=json.load(sys.stdin)["data"]; print({k: d.get(k) for k in ("limit","limit_remaining","limit_reset")})'
   ```

   Expect `limit 5`, `limit_reset 'monthly'`. Do not print `label` either: it can contain part of the key.
3. **Settings → Privacy**: prompt/input logging **off**.
4. Re-check Day 28's ZDR route: `curl -s https://openrouter.ai/api/v1/models/openai/gpt-4o-mini/endpoints` (public, no key). Confirm that a Zero Data Retention endpoint (Azure on Day 28) still serves the model and still lists `structured_outputs` / `response_format`. If that changed, stop: the disclosure text names it.

### 0.6 Generate the two portfolio secrets (outside both repos)

```bash
# In a terminal that you close afterwards. Values go straight into the variable, never on screen.
PROCURERAG_SERVICE_TOKEN=$(openssl rand -hex 32)
``` 
DONE.

The client-hash secret is generated in Block 4, piped straight into Vercel. Nothing else needs it.

**Stop (plan, Block 0):** if the store, the dedicated key, the cloud ceiling or the terms are not approved, keep going with local tests only. Do not deploy the paid chat, and do not claim the hosted gate.

ALL APPROVED.

---

## Blocks 1–2: admission, kill switch, warm-up check (code done; prove it)

### Local gates (portfolio, `day-29-hosting`)

```bash
npm ci && npm audit --omit=dev && npm run typecheck && npm run lint && npm run build && npm test && git diff --check
```

Expected at hand-over: `196 passed, 10 skipped`. The 10 skipped tests are the real-store proof below.

### The real-store proof (plan: "faking `eval()` alone is insufficient")

The Upstash REST URL and token come from the Upstash console (**your database → REST API**). They are read silently, and the test uses its own variable names, so an app shell never runs it by accident:

```bash
read -r ADMISSION_TEST_REDIS_REST_URL; read -rs ADMISSION_TEST_REDIS_REST_TOKEN
export ADMISSION_TEST_REDIS_REST_URL ADMISSION_TEST_REDIS_REST_TOKEN
npx playwright test tests/chat-admission-redis.spec.ts
unset ADMISSION_TEST_REDIS_REST_URL ADMISSION_TEST_REDIS_REST_TOKEN
```

Each test uses its own random namespace (`procurerag-demo:test-xxxxxxxx`) and deletes only the keys it touched. Expect 10 passed:

- the 55th question refused, with nothing changed by the refusal;
- the 11th from one client refused while another client gets in;
- **10 parallel admissions → exactly 2**;
- a release frees only its own lease, and a double or unknown release is harmless;
- an expired lease is pruned;
- the UTC-midnight reset;
- bounded TTLs;
- the status limits;
- the kill-switch values;
- a wrong token failing closed.

### Mutation checks (by hand, one at a time, then `git checkout -- <file>`)

| # | Change | Must turn red | Went red (2026-10-31) |
|---|---|---|---|
| M1 | `lib/chat/bff.ts`: in the timeout branch, `await releaseLease()` before returning | chat-bff "a timeout KEEPS the lease" | 1 failed: exactly that test |
| M2 | `lib/chat/bff.ts`: in the kill-switch `catch`, set `enabled = true` instead of returning | chat-bff "a store that cannot be read counts as OFF" | 1 failed: exactly that test |
| M3 | `lib/chat/bff.ts`: pass `deps.clientAddress` instead of `digest` as `clientDigest` | chat-bff "admission gets … an HMAC digest, never the address", and the log test | 1 failed: "admission gets … an HMAC digest, never the address". The log test stayed **green**, and that is correct: M3 changes what reaches the store, not the log, which holds neither the digest nor the address either way. The prediction was wrong, not the test |
| M4 | `lib/chat/upstash-admission.ts`: move the `ZADD`/`INCR` lines above the three `if … return {0 …}` lines (write before check) | chat-admission "every refusal returns BEFORE the first write", and the real-store global/race tests | Unit half: 1 failed, "every refusal returns BEFORE the first write". Real-store half: 5 of 10 failed. Two were predicted (global, race), and three more went red too (client, release, expired-lease prune). Each of the five checks the store's state after a refusal, and a refusal now writes before it refuses |
| M5 | Non-atomic: make `admitChat` send `ZCARD` and two `GET`s, decide in TypeScript, then send `ZADD`/`INCR` as separate commands | real-store "10 simultaneous admissions … EXACTLY 2" (run it several times: a race is probabilistic) | Unit half: 1 failed, "admitChat: one EVAL with 3 declared KEYS …". That catches the command **shape**, not the race. Real-store half, run 5 times: the race test failed **5 of 5**, so the real-store proof catches non-atomic admission on every run. The global test also failed 5 of 5, but **by timeout, not by an assertion** (confirmed: "Test timeout of 30000ms exceeded"). M5 makes 11 round trips per question instead of 2, about 600 sequential calls for 54 questions. That is a slowdown, not a logic catch, so it is not counted. The race test is the proof |
| M6 | `lib/chat/bff.ts`: on a non-200 upstream, call any extra store method (a "refund") | chat-bff "…: the lease is released once, and nothing is refunded" | 4 failed: the 401, 422, 429 and 500 rows of that test. The three 200 rows (valid, malformed, oversized) stayed green, as they must: the refund fires only on a non-200 |

Record which test went red for each, as Day 28 did for its M-series.

**How the 2026-10-31 run was made.** The `day-29-hosting` tree was still uncommitted, so `git checkout -- <file>` would have wiped the Day 29 edits too. Each file was restored from a copy instead, and checked by SHA-256 after every mutation (`bff.ts` `6d2e5c41b6ec…`, `upstash-admission.ts` `614834eee883…`). Per mutation, the run covered the three specs that import `lib/chat/*` directly: chat-bff, chat-admission and chat-status. Those test the mutated source with no rebuild. Baseline: 91 passed, and each mutation produced only the failures listed. The route specs were not re-run, because they test the built `.next`, which no mutation changed. M5 kept the prune and the expiries, so only atomicity differed. M6's "refund" was a second `releaseChat` on any non-200, because the store has no refund method, and any fourth store call is what the test counts.

---

## Block 3: Azure

### 3.1 Recreate the resources

Day 23/24 resources were deleted. Follow `docs/azure-container-apps-runbook.md` §1–4 (variables, prerequisites, image push, `az containerapp up` in **northeurope**), then §10b items 1–4 (identity, federated credential, `AcrPush` + `Contributor` on the app, GitHub environment `production`). Ingress stays external and HTTPS-only. DONE

### 3.2 Set the two app secrets ONCE (before any template apply)

```bash
read -rs OPENROUTER_DEMO_KEY   # if not still set from 0.5
az containerapp secret set --name "$CONTAINERAPP_NAME" --resource-group "$RESOURCE_GROUP" \
  --secrets "procurerag-service-token=$PROCURERAG_SERVICE_TOKEN" "openrouter-api-key=$OPENROUTER_DEMO_KEY" -o none
az containerapp secret list --name "$CONTAINERAPP_NAME" --resource-group "$RESOURCE_GROUP" --query '[].name' -o tsv
```

Expect two names. The values were briefly in the `az` process's arguments on your own laptop. They are not in a log, a file or GitHub. That is the residual of this one-time step.

**Permissions (recorded decision):** `az containerapp update --yaml` (deploy step 6) always calls `listSecrets` with values; this is verified in the Azure CLI 2.91.0 source. So the deploy identity can read these two values, through its existing `Contributor` on this one app. No new role is granted. The exposure is bounded by OIDC, which works only for this repository's `production` environment, which needs a reviewer. A tighter custom role would still need `listSecrets/action`.

### 3.3 The deploy smoke's token (GitHub)

```bash
printf %s "$PROCURERAG_SERVICE_TOKEN" | gh secret set PROCURERAG_SERVICE_TOKEN --env production --repo juanfpinzon/ProcureRAG
```

### 3.4 Deploy, LLM OFF first

After the ProcureRAG PR is merged and CI is green on `main`:

```bash
gh workflow run deploy.yml --ref main -f live_llm=false
```

Approve the `production` run. The job summary records:

- the digest;
- the previous revision and the rollback handle;
- `PROCURERAG_LIVE_LLM=0`;
- the URL smoke (both routes refuse no token and a wrong one);
- the readback: env **names**, secret **names**, scale 0/1, 1 vCPU / 2 GiB, `allowInsecure: false`.

The live revision comes later, in Block 5, with `-f live_llm=true`, only after you approve the paid smoke.

### 3.5 Read by hand what the workflow cannot

```bash
az monitor log-analytics workspace list --resource-group "$RESOURCE_GROUP" \
  --query '[].{name:name, retentionInDays:retentionInDays}' -o table      # expect the 30-day default
```

### 3.6 Easy Auth: rejected (record it)

Built-in authentication, applied to all requests, would also gate `/health`, which must stay anonymous for the platform's probes and the warm-up check. Its alternative, "allow unauthenticated", would add nothing to the existing check. The API already authenticates `/query` and `/query/stream` with the service token, in middleware, before the body is read (Day 28, and re-proven by the URL smoke). The token is service identity ("came through my BFF"), not enterprise identity: that is the limit, stated plainly.

**Residual compute risk:** any request to the public ingress, even one refused with 401, wakes the scaled-to-zero replica before the app can refuse it. The bounds are max 1 replica, the budget alert and the kill switch.

---

## Block 4: Vercel

```bash
cd ~/python_projects/juanfpinzon.github.io        # the reviewed day-29-hosting checkout, clean `git status`
vercel login
vercel link                                       # personal account; a new project (`.vercel/` is git-ignored)

# Server-only settings, Production only. Values come from pipes, never from the keyboard.
# Production variables are "sensitive" by default: not readable back, even in the dashboard.
az containerapp show --name "$CONTAINERAPP_NAME" --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv | sed 's|^|https://|' | tr -d '\n' \
  | vercel env add PROCURERAG_API_URL production
printf %s "$PROCURERAG_SERVICE_TOKEN" | vercel env add PROCURERAG_SERVICE_TOKEN production
openssl rand -hex 32 | tr -d '\n' | vercel env add PROCURERAG_CLIENT_HASH_SECRET production
printf %s "or-demo-2026-10" | vercel env add PROCURERAG_BUDGET_DOMAIN production
vercel env ls                                      # names and environments only: expect Production only

vercel deploy --prod
```

- **Region:** `vercel.json` sets `"regions": ["dub1"]` (in the repository, so it is reviewed). After the deploy, **Project → Settings → Functions** should show Dublin. `scripts/deployed_proof.py free` (Block 5) reads the region the function really ran in from `x-vercel-id`.
- **Functions:** the build log must list `/api/chat` and `/api/chat/status` as functions (ƒ), and every page as static (○).
- **Deployment Protection:** Hobby's default protects preview deployments, not the project's production domain. Use the production domain `https://<project>.vercel.app` for every test below.
- **The kill switch starts OFF:** the key does not exist yet, which means off. The chat answers "Demo offline" until Block 5 turns it on.
- `master` / GitHub Pages: untouched. No canonical URL or share-image work (Day 30).

---

## Block 5: deployed proof

`SITE=https://<project>.vercel.app`. **Kill-switch commands** go in the Upstash console (**your database → CLI**), so no token touches your shell:

```text
SET procurerag-demo:<domain>:chat:enabled true      # ON
SET procurerag-demo:<domain>:chat:enabled false     # OFF (or DEL the key)
```

### 5.1 Free proof, revision with LLM off

```bash
read -r PROCURERAG_API_URL; export PROCURERAG_API_URL      # https://<fqdn>, never printed by the script
python3 scripts/deployed_proof.py free --site "$SITE"      # 1st run: switch still OFF
```

With the switch OFF, expect:

- pages ok;
- "kill switch: off";
- `function region: dub1`;
- status route `unavailable` (the kill switch is read first);
- no leaks in browser-visible files;
- Azure `/health` 200 without credentials;
- four 401s (`/query` and `/query/stream`, no token and wrong token).

Then turn the switch ON, wait at least 5 minutes so the replica scales to zero, and run `free` again. The status route's latency is then the **cold start through the BFF**. Expect `ready` (or `waking` if it took over 90 s).

With the LLM off, a question is free (`not_generated`), so the full chain can be proven at no cost:

- **Admitted:** ask a preset in the browser → "Retrieval only". The Vercel log line shows `quota` counters and `lease: "released"`.
- **Global cap → busy, zero upstream:**

  ```text
  GET procurerag-demo:<domain>:chat:global:<day>                 # note the value (nil if none)
  SET procurerag-demo:<domain>:chat:global:<day> 54 EX 90000
  ```

  Ask → "Demo limit reached" with a countdown to 00:00 UTC. The Vercel log shows `reason: global_cap`; the Azure console log shows no new `POST /query`. Restore the noted value (`SET … <value> EX 90000`), or `DEL` the key if it was nil.
- **In-flight cap → busy, no countdown:**

  ```bash
  python3 -c 'import time; print(int(time.time() * 1000) + 300000)'   # an expiry 5 minutes ahead
  ```

  ```text
  ZADD procurerag-demo:<domain>:chat:in_flight <expiry> manual-proof-1 <expiry> manual-proof-2
  ```

  Ask → busy, no countdown. Then `ZREM procurerag-demo:<domain>:chat:in_flight manual-proof-1 manual-proof-2`.
- **Broken store → unavailable, zero upstream** (a real store error, safe to undo):

  ```text
  GET procurerag-demo:<domain>:chat:global:<day>       # note it
  DEL procurerag-demo:<domain>:chat:global:<day>
  HSET procurerag-demo:<domain>:chat:global:<day> broken 1
  ```

  Ask → "Demo offline". The Vercel log shows `reason: store_error, store_error: "store answered HTTP 400"` (WRONGTYPE inside the script). Azure: no `POST /query`. Then `DEL` the key and restore the noted value.
- **Missing configuration:** `vercel deploy` (no `--prod`) creates a preview with no variables. Open it (Vercel login) → "Demo offline". The log shows `missing_config`.

### 5.2 Kill-switch flip-to-effect

```bash
python3 scripts/deployed_proof.py watch-kill-switch --site "$SITE"
```

While it runs, set the switch OFF in the Upstash console. Note the UTC time when you press Enter (`date -u +%T` in another tab, right before). The script prints the last request that saw "on" and the first that saw "off". Record: the flip time, the first-off time, and the difference. The switch is read on every request with no cache, so expect about one probe interval (1 s). Flip it back the same way.

Record too: the switch stops NEW work. A question already admitted still finishes. The secondary stop is Azure ingress off / max replicas 0, and the tertiary is revoking the key.

### 5.3 Is the client address really Vercel's?

With the switch ON, on a day you have not used the status check yet:

```bash
python3 scripts/deployed_proof.py spoof-check --site "$SITE"
```

Expect `[ok] forged addresses were ignored: busy after 3 check(s) from one real client`.

### 5.4 Cold start and the lease TTL

Measure from admission to the end of upstream work, on a cold replica. Confirm it is cold first: `az containerapp replica list --name "$CONTAINERAPP_NAME" --resource-group "$RESOURCE_GROUP" --query 'length(@)'` should print 0.

| Segment | Where to read it |
|---|---|
| admission (t0) | the Vercel log line's `at` |
| Azure scale-from-zero, health ready | `az containerapp logs show … --type system --tail 50` (replica start), `--type console` (`Application startup complete`) |
| retrieval + provider (or provider timeout) | the console access line for `POST /query` (completion time); OpenRouter activity (generation time) |
| BFF response / timeout and cleanup | the Vercel log line: `latency_ms`, `state`, `lease` |

If a cold question exceeds 75 s, the BFF answers `timed_out` while Azure keeps working. The Azure `POST /query` line then shows when the work really ended: that is the **continuation after admission**.

Lease TTL rule: `LEASE_TTL_MS ≥ worst measured continuation + a written margin (≥ 20%)`. The analytic worst case, with `max_retries=0`, is about 72 s cold start + a few seconds of retrieval + 60 s provider timeout ≈ 140 s, inside 180 s. Keep 180 s only if the measurement agrees. Otherwise change `LEASE_TTL_MS`, its comment, the tests and ADR §8.3.1 together.

### 5.5 Paid launch smoke (only after you approve the spend)

1. Re-run 0.5 step 2: the key's `limit_remaining` and `limit_reset`.
2. `gh workflow run deploy.yml --ref main -f live_llm=true`, then approve. The URL smoke runs with `--expect-live-llm`, which skips the one paid probe.
3. `python3 scripts/chat_smoke.py "$SITE"`. It sends the 8 questions once each, in order, with no retry. That is 8 of your 10 per-client daily questions.
4. Record, per question:
   - the state, latency and cited IDs;
   - your manual verdict (Q001 partly right, Q090 `gap_report`, Q091 the known red);
   - from OpenRouter's activity page: provider and model routing, tokens, cost;
   - the key's usage before and after.

### 5.6 Logs and privacy

- **Vercel** (Project → Logs): one JSON line per request, with route, state, status, latency, preset id or `free_text`, `quota`, `lease` and `reason`. No question, answer, address, digest, token or URL.
- **Azure** console log: access lines (path and status) only. No LangSmith upload: tracing is off by env, and no project receives traces.
- **OpenRouter:** prompt logging off.
- Record each platform's log retention.

---

## Block 6: rollback rehearsal

Record the handles first (no secrets, mask private URLs):

- the previous and new Azure revision plus digest (deploy job summary);
- the current and previous Vercel deployment ids (`vercel ls`);
- the kill-switch state and the store namespace (`procurerag-demo:<domain>`);
- the OpenRouter key's name and its limit metadata.

Then, in this order:

1. **Chat off, portfolio up:** switch OFF (5.2 shows the timing). `deployed_proof.py free` → pages ok, kill switch off, status `unavailable`.
2. **Vercel rollback.** This needs a previous production deployment. If there is only one, run `vercel deploy --prod` again first.

   ```bash
   vercel rollback <previous-deployment-url-or-id>
   vercel rollback status
   ```

   Then smoke the content routes (`deployed_proof.py free`). After a rollback, Vercel stops assigning the production domain to new deployments until you promote one: `vercel promote <deployment>` restores it.
3. **Azure rollback** to the previous digest: `docs/azure-container-apps-runbook.md` §10b "6. Roll back" (with `LIVE_LLM=0`). Then smoke `/health` and authenticated retrieval-only behaviour: `PROCURERAG_SERVICE_TOKEN` in the environment (`read -rs`), then `python3 scripts/container_smoke.py --url https://<fqdn>`.
4. **Restore** the new revision only if you want it (same commands with its digest and the approved `LIVE_LLM`), then leave the kill switch in a recorded final state.

Do not rehearse by deleting resources, and do not touch `master` / Pages.
