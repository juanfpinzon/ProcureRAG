# ProcureRAG Docker runbook

How to build, run, and check the ProcureRAG API (Day 21's `src/api.py`) as a local container, from a clean checkout.

Day 22 (HER-290). The commands below were executed as written on 2026-10-15. Their measured output is in [`eval-report.md`](eval-report.md), section "Day 22".

**What you get:** one container running one Uvicorn process, reachable at `http://127.0.0.1:8000` from this machine only. It answers with local retrieval only: no LLM call, no LangSmith trace, no API key.

**What you do not get:** authentication, a production rate limit, answer-quality evaluation, or a cloud deployment (see "Honest limits").

## Prerequisites

- Docker Engine or Docker Desktop, with BuildKit (the default builder since Docker 23). Measured on Docker 29.7.2: Docker Desktop on Apple Silicon, so the daemon runs `linux/aarch64`. The image was also built and exercised as `linux/amd64` on the Hermes VM (reported 2026-10-17). That machine is much slower, so its timings differ (see "Day 23 handoff").
- About 2 GB free in Docker's disk for the image (1.87 GB measured), plus about 110 MB for the model cache volume.
- Network access for two steps only: the build (base images, Python packages from PyPI, and `torch` from PyTorch's CPU-only index) and the one-time model warm-up (Hugging Face Hub). Every run after that works with no network at all.
- Run every command from the repository root.
- No `.env` file is needed. Do not pass your real `.env` to Docker: it holds keys this run must not have.

## The image contract

| Decision | Value | Why |
|---|---|---|
| Base image | `python:3.11.17-slim-trixie` (official image, Debian 13). Digest on 2026-10-15: `sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce` | `.python-version` is 3.11. "slim" means fewer OS packages to patch. FastAPI's docs mark `tiangolo/uvicorn-gunicorn-fastapi` as deprecated |
| Installer | `uv 0.12.2`, one binary copied from `ghcr.io/astral-sh/uv:0.12.2` | The uv version that wrote `uv.lock` |
| Dependencies | `uv sync --locked --no-dev --no-install-project --no-cache` into `/app/.venv` | Exactly the lockfile's versions, built fresh for Linux, never copied from the host `.venv`. The dev group is omitted, although some of its packages also arrive through runtime dependencies (pytest through `deepeval`; httpx through `huggingface-hub`, `langchain-core`, and others). Only ruff is absent |
| PyTorch build | `torch 2.14.0+cpu` from `https://download.pytorch.org/whl/cpu` on Linux (`[tool.uv.sources]` in `pyproject.toml`); macOS keeps PyPI's `torch 2.14.0` | The service runs on CPU only. PyPI's Linux wheel is the CUDA build, which made the first image 6.58 GB |
| Files copied in | `pyproject.toml`, `uv.lock`, `src/`, `data/corpus_v1/` (24 files, 1.8 MB) | `.dockerignore` is an allow-list: everything else stays out |
| Runtime user | `procurerag` (uid 1000), no login shell. Code and packages are owned by root | Not root, and it cannot modify its own code |
| Process | `python -m uvicorn api:app --app-dir src --host 0.0.0.0 --port 8000 --workers 1`, exec form | One process: the models and the rate limiter both live in process memory |
| Port | Container `8000`, published on host `127.0.0.1:8000` | Reachable from this machine only |
| Health check | `GET /health` with Python's `urllib`. 60 s start period, a probe every 2 s while starting, then every 30 s | Startup loads two models before the server answers |
| Models | Named volume `procurerag-hf-cache`, mounted at `HF_HOME=/home/procurerag/.cache/huggingface`, warmed once. `HF_HUB_OFFLINE=1` by default | See step 3 |
| Image tag | `procurerag-api:day22` | The name Day 23 starts from |

The [`Dockerfile`](../Dockerfile) explains each instruction in its comments, and [`.dockerignore`](../.dockerignore) explains each category it keeps out.

## Runtime configuration

| Variable | Image default | Secret? | When to change it | How to set it |
|---|---|---|---|---|
| `PROCURERAG_LIVE_LLM` | `0` | No | `1` only for an explicit, paid live-LLM run | `docker run --env PROCURERAG_LIVE_LLM=1` |
| `LANGSMITH_TRACING` | `false` | No | Keep `false` for every run in this runbook | `--env` |
| `LANGSMITH_TRACING_V2` | `false` | No | Same. LangSmith reads this name first | `--env` |
| `OPENROUTER_API_KEY` | not set | **Yes** | Only together with `PROCURERAG_LIVE_LLM=1` | At run time only (see "Optional: a paid live-LLM run"). Never in `ARG`, `ENV`, a copied `.env`, or a committed file |
| `HF_HOME` | `/home/procurerag/.cache/huggingface` | No | Never: the cache volume is mounted at this path | n/a |
| `HF_HUB_OFFLINE` | `1` | No | `0` for the warm-up run only | `--env HF_HUB_OFFLINE=0` |

The app can also read `PROCURERAG_LIVE_LLM` and `OPENROUTER_API_KEY` from a `.env` file (`read_setting` in `src/api.py`). The image contains no `.env` file, so environment variables are its only configuration.

The commands below pass the three safe defaults (`PROCURERAG_LIVE_LLM=0` and both `LANGSMITH_*=false`) explicitly, even though the image already sets them. That way, the command itself shows the run's configuration, without opening the Dockerfile.

## 1. Check what Docker will receive (optional)

`docker build .` sends the build context (this folder, minus what `.dockerignore` excludes) to the builder before any Dockerfile line runs. This throwaway build lists exactly what was sent. It reads its Dockerfile from the heredoc (`-f -`), so no file is created:

```bash
docker build --no-cache --progress=plain -f - . <<'EOF'
FROM busybox
COPY . /context
RUN find /context -type f | sort
EOF
```

Expected: 24 files, which are `pyproject.toml`, `uv.lock`, the 20 `src/*.py` modules, and the two `data/corpus_v1/*.jsonl` files. There must be no `.env`, `.venv`, `.git`, `tests/`, `docs/`, or cache folder.

## 2. Build the image

```bash
docker build --tag procurerag-api:day22 .
```

With the base images already pulled, a build that installs every dependency takes about 15 s (measured), most of it downloading about 320 MB of Python packages. A rebuild with nothing changed takes about 1 s. A rebuild after a change in `src/` re-runs only the last `COPY`.

Inspect what was built:

```bash
docker image inspect procurerag-api:day22 --format 'id={{.Id}}
size={{.Size}} bytes  platform={{.Os}}/{{.Architecture}}  user={{.Config.User}}
ports={{json .Config.ExposedPorts}}
cmd={{json .Config.Cmd}}'

# The NAMES of the environment variables baked into the image (names only: a habit worth keeping)
docker image inspect procurerag-api:day22 --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1

# No build step mentions a secret. Expect 0
docker history --no-trunc procurerag-api:day22 --format '{{.CreatedBy}}' | grep -ciE 'api_key|token|secret|password'
```

## 3. Warm the model cache (once per machine, needs network)

The retrieval pipeline needs two models from the Hugging Face Hub:

| Model | Used for | Size in the cache |
|---|---|---|
| `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` | Embeddings (`semantic_search.load_embedding_model`) | 88 MB |
| `cross-encoder/ms-marco-TinyBERT-L2-v2` | Reranking (`reranking.load_cross_encoder`) | 18 MB |

They are not in the image. They live in a named Docker volume, which is filled once and then mounted into every container:

```bash
docker volume create procurerag-hf-cache

docker run --rm --name procurerag-warmup \
  --env HF_HUB_OFFLINE=0 \
  --volume procurerag-hf-cache:/home/procurerag/.cache/huggingface \
  procurerag-api:day22 \
  python -c "import sys; sys.path.insert(0, 'src'); from semantic_search import load_embedding_model; from reranking import load_cross_encoder; load_embedding_model(); load_cross_encoder(); print('both models cached')"
```

What this does:

- `--env HF_HUB_OFFLINE=0` lifts the image's "never contact the Hub" default for this one run.
- `--volume NAME:PATH` mounts the named volume at `HF_HOME`, so the downloads land in the volume, not in the container's own filesystem (which `--rm` deletes).
- The command calls the same two loader functions that server startup calls (`load_live_pipeline` in `src/api.py`), with the same default arguments, so it caches exactly the files startup needs. `sys.path.insert(0, 'src')` does what `--app-dir src` does for Uvicorn.
- Expected last line: `both models cached` (14-19 s measured). Expect a warning about "unauthenticated requests to the HF Hub" as well. These models are public, so no Hugging Face token is needed, and none should be passed.

**Why a volume?** The image stays code plus dependencies. The models are downloaded once per machine, and they survive container restarts and image rebuilds. The price is one extra step. A fresh machine, CI runner, or cloud host must warm its own cache, or use a different strategy (see "Day 23 handoff").

**What happens if you skip this step?** The container stops within seconds (exit code 3, measured) with `LocalEntryNotFoundError: Cannot find the requested files in the disk cache and outgoing traffic has been disabled`, followed by `Application startup failed. Exiting.` That is deliberate: a missing cache fails loudly, instead of downloading silently in every new container.

**Model versions are not pinned.** The code asks for each model's `main` branch, so a warm-up on a later day could download different weights. The 2026-10-15 warm-up cached snapshot `b207367332321f8e44f96e224ef15bc607f4dbf0` (MiniLM) and `81d1926f67cb8eee2c2be17ca9f793c7c3bd20cc` (TinyBERT), the same snapshots as the host's own cache.

## 4. Run the service (no key, host loopback only)

```bash
docker run --detach --rm --name procurerag-day22 \
  --publish 127.0.0.1:8000:8000 \
  --env PROCURERAG_LIVE_LLM=0 \
  --env LANGSMITH_TRACING=false \
  --env LANGSMITH_TRACING_V2=false \
  --volume procurerag-hf-cache:/home/procurerag/.cache/huggingface:ro \
  procurerag-api:day22
```

- `--detach` runs it in the background. `--rm` deletes the container when it stops.
- `--publish 127.0.0.1:8000:8000` reads as `HOST_IP:HOST_PORT:CONTAINER_PORT`. Inside the container, Uvicorn listens on `0.0.0.0:8000` (every container interface), because Docker's forwarded traffic arrives on the container's network interface, not on its loopback. On the host, the port opens on `127.0.0.1` only, so other machines on the LAN cannot reach this unauthenticated service. A bare `--publish 8000:8000` would open it on every host interface.
- `:ro` mounts the model cache read-only. The running service only reads the models, so it cannot modify a cache that other containers share.

Wait until Docker reports the health check result:

```bash
start=$(date +%s)
until [ "$(docker inspect --format '{{.State.Health.Status}}' procurerag-day22 2>/dev/null)" != "starting" ]; do sleep 1; done
echo "$(docker inspect --format '{{.State.Health.Status}}' procurerag-day22 2>/dev/null) after $(( $(date +%s) - start )) s"
```

Expected: `healthy after 9 s` or so. If it prints only ` after N s` with no status, the container has already exited and `--rm` removed it (see "Troubleshooting").

## 5. Smoke test

| # | Probe | Expected result | What runs |
|---|---|---|---|
| 1 | `GET /health` | HTTP 200, `"status":"ok"`, `"live_llm":false` | Nothing: liveness only |
| 2 | Q001, labeled, `buyer` | `"status":"not_generated"`, 5 sources, a `run_id` | Local retrieval only; the live LLM is off |
| 3 | Q091, labeled, no `decision` | `"status":"pending_approval"`, `"run_id":null`, no sources, an `approval_request` | Nothing: the approval boundary stops it before retrieval |
| 4 | Off-topic free text | `"status":"blocked"`, an `off_topic` finding, `"run_id":null` | Nothing: the scope guard stops it before retrieval |

```bash
# 1. Liveness
curl -sS -w '\nHTTP %{http_code} in %{time_total} s\n' http://127.0.0.1:8000/health

# 2. A labeled question, local retrieval only
curl -sS -w '\nHTTP %{http_code} in %{time_total} s\n' -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "What approval is required for a EUR 60,000 purchase order?", "role": "buyer", "query_id": "Q001"}'

# 3. A question that may need the approval-gated second pass, sent without a decision
curl -sS -w '\nHTTP %{http_code} in %{time_total} s\n' -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "What approvals and security evidence do I need for a EUR 120,000 SaaS renewal?", "role": "buyer", "query_id": "Q091"}'

# 4. An off-topic question
curl -sS -w '\nHTTP %{http_code} in %{time_total} s\n' -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "What is the capital of France?", "role": "buyer"}'
```

A passing `/health` and a passing smoke test still say nothing about answer quality. They prove that the packaged service starts, enforces its Day 21 contract, and runs local retrieval. Answer quality remains a separate evaluation.

## 6. Check the logs

```bash
docker logs procurerag-day22 2>&1 | grep -c Traceback                                  # expect 0
docker logs procurerag-day22 2>&1 | grep -ciE 'api_key|token|secret|sk-or|lsv2_'      # expect 0
docker logs procurerag-day22 2>&1 | tail -8
```

The access log shows every request from the host arriving from one address, the Docker bridge gateway (`172.17.0.1` measured). Health probes come from `127.0.0.1`, because Docker runs them inside the container.

## 7. Stop and clean up

```bash
docker stop procurerag-day22                    # SIGTERM -> Uvicorn shuts down cleanly; --rm then deletes the container
docker ps --all --filter name=procurerag        # expect only the header line: no container is left
```

The image and the warmed volume are kept for the next run. To delete them as well:

```bash
docker volume rm procurerag-hf-cache            # the next run must warm the cache again (step 3)
docker image rm procurerag-api:day22
```

## Optional: prove the offline steady state

With the cache warmed, the service needs no network at all. `--network none` gives the container no network interface except its own loopback:

```bash
docker run --detach --rm --name procurerag-offline \
  --network none \
  --env PROCURERAG_LIVE_LLM=0 \
  --env LANGSMITH_TRACING=false \
  --env LANGSMITH_TRACING_V2=false \
  --volume procurerag-hf-cache:/home/procurerag/.cache/huggingface:ro \
  procurerag-api:day22

start=$(date +%s)
until [ "$(docker inspect --format '{{.State.Health.Status}}' procurerag-offline 2>/dev/null)" != "starting" ]; do sleep 1; done
echo "$(docker inspect --format '{{.State.Health.Status}}' procurerag-offline 2>/dev/null) after $(( $(date +%s) - start )) s"

# With no network, the host cannot reach the container, so the query is sent from INSIDE it
docker exec procurerag-offline python -c "import json, urllib.request; req = urllib.request.Request('http://127.0.0.1:8000/query', data=json.dumps({'query': 'What approval is required for a EUR 60,000 purchase order?', 'role': 'buyer', 'query_id': 'Q001'}).encode(), headers={'Content-Type': 'application/json'}); r = json.load(urllib.request.urlopen(req)); print(r['status'], [s['chunk_id'] for s in r['sources']])"

# And the container really has no way out
docker exec procurerag-offline python -c "import urllib.request; urllib.request.urlopen('https://huggingface.co', timeout=3)"   # expect: URLError ... name resolution

docker stop procurerag-offline
```

The health check still works here because Docker runs it inside the container.

## Optional: a paid live-LLM run (not run on Day 22)

The deterministic path above needs no key. If a bounded live-LLM run is ever needed, the key must arrive at run time only:

```bash
# Read the key into this shell only. -s hides the typing; nothing goes into shell history.
read -rs OPENROUTER_API_KEY && export OPENROUTER_API_KEY

# `--env NAME` with no `=value` copies the value from this shell, so the key never appears in the command
docker run --detach --rm --name procurerag-live \
  --publish 127.0.0.1:8000:8000 \
  --env PROCURERAG_LIVE_LLM=1 \
  --env OPENROUTER_API_KEY \
  --env LANGSMITH_TRACING=false \
  --env LANGSMITH_TRACING_V2=false \
  --volume procurerag-hf-cache:/home/procurerag/.cache/huggingface:ro \
  procurerag-api:day22
```

- Every in-scope request with complete evidence is then one paid OpenRouter call, capped by the rate limit (30 per minute).
- `/health` then reports `"live_llm":true`.
- While this container exists, the key is stored in its configuration: `docker inspect procurerag-live` shows it to anyone who can use Docker on this machine. Never paste that output anywhere. `--rm` deletes it with the container. A deployed service gets the key from the platform's secret store instead (Day 23).
- `--env-file .env` is not an option: the real `.env` also holds LangSmith and Tavily keys, which this service does not need.

## Troubleshooting

- **The health loop prints no status.** The container exited and `--rm` deleted it, along with its logs. Run the same `docker run` without `--detach` to see the error in the terminal (stop it with Ctrl+C).
- **`LocalEntryNotFoundError ... outgoing traffic has been disabled`, then `Application startup failed`.** The model cache is empty, or it is not mounted at exactly `/home/procurerag/.cache/huggingface`. Run step 3, then check the `--volume` path.
- **`Bind for 127.0.0.1:8000 failed: port is already allocated`.** Something else uses host port 8000: a local Uvicorn, or another container. Stop it, or publish a different host port (`--publish 127.0.0.1:8001:8000`). The container side stays 8000.
- **`unhealthy`.** Read the probe history: `docker inspect --format '{{json .State.Health}}' procurerag-day22`.

## Day 23 handoff

What Day 23 can rely on:

- Image `procurerag-api:day22`; container port `8000`; `GET /health` returns HTTP 200 once startup is complete. With a warm cache, that took 9-10 s on the Mac and 51 s (offline) on the Hermes VM.
- The environment contract in "Runtime configuration". The deterministic path needs no secret.
- A start command that needs no shell: the image's `CMD`.

What Day 23 must decide:

- **CPU architecture.** The image built on the Mac is `linux/arm64`. Azure Container Apps runs `linux/amd64`. That image has now been built and exercised successfully on the Hermes VM (reported 2026-10-17):
  - image id `sha256:b9f88b8abc7c…`;
  - a truly cold build (image pulls, dependency downloads, bytecode compiling) in 332.57 s;
  - offline startup to healthy in 51 s;
  - about 682 MiB after the smoke.

  These numbers belong to that VM. It is a much slower machine than the Mac (10 s startup, 572 MiB), so they do not show what Azure will do. Its reported size, 590,293,766 bytes, is most likely a compressed size: the x86_64 `torch` wheel alone unpacks to 712 MiB. So it cannot be compared with the Mac's 1.87 GB on-disk figure.
- **Where the models come from.** A local named volume has no direct cloud equivalent. The options are a cloud file share warmed once (Azure Files), models baked into the image, or a download at every start (`HF_HUB_OFFLINE=0`). Each one moves the cold-start cost somewhere else. Baking the 106 MB of models in is now cheap compared with the 1.87 GB image.
- **Image size.** 1.87 GB on disk for `linux/arm64` with CPU-only `torch` (it was 6.58 GB with the CUDA build). The `linux/amd64` on-disk size is not recorded yet. Every cold start on a new host still pulls it, so it remains a cold-start cost to measure on Azure.
- **Health probes.** Kubernetes-based platforms such as Azure Container Apps do not run the Dockerfile `HEALTHCHECK`. The same `/health` route has to be configured as the platform's own probe. Its startup grace period must cover the slow case: 51 s on the Hermes VM, already close to the Dockerfile's 60 s start period.

## Honest limits

- Every Day 21 limit still applies inside the container: the role is caller-asserted (no authentication); approval is a stateless re-submission; free-text evidence is unchecked; trace rows are not persisted.
- The rate limit lives in the one Uvicorn process. It resets whenever the container restarts. Behind Docker's port forwarding, every client on the host arrives from the same gateway address, so they all share one 30-requests-per-minute budget.
- Trace rows built inside the container have no code version: `git describe` finds no `git` and no `.git` in the image, and the code records `None`, as designed. The image tag is not yet recorded anywhere in the trace.
- `linux/arm64` was built and run on the Mac, and `linux/amd64` on the Hermes VM. The two machines differ a lot, so their timings measure the machines as much as the architectures. No vulnerability scan of the image was run.
- `--no-dev` leaves out the dev group, but the evaluation stack is still a runtime dependency. `deepeval` brings pytest into the serving image.
