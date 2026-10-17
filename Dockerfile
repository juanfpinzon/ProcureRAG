# Dockerfile: the Day 21 FastAPI service (`src/api.py`) as a container image.
#
#   build:  docker build --tag procurerag-api:day22 .
#   run:    see docs/docker-runbook.md (the model cache volume is warmed first)
#
# Keep two moments apart while reading this file:
#
# - BUILD time (`docker build`): every instruction below runs once, on the
#   builder, and most of them leave a read-only, cached LAYER in the image.
#   Nothing at build time needs, or may see, a secret.
# - RUN time (`docker run`): only CMD and HEALTHCHECK execute, in every
#   container started from the image. Secrets and per-run settings arrive
#   here, as environment variables, and never earlier.
#
# The order of the instructions is deliberate: things that rarely change come
# first, and the code (which changes most often) comes last. Docker reuses a
# cached layer only if that instruction, every file it copies, and every
# layer BEFORE it are unchanged. So an edit to `src/api.py` rebuilds only the
# last layers, and never re-runs the multi-GB dependency install.

# ---------------------------------------------------------------------------
# Base image
#
# The official Python image, pinned to an exact patch release and Debian
# release (trixie = Debian 13). `.python-version` says 3.11, and uv.lock
# was resolved for `requires-python >= 3.11`.
#
# "slim" leaves out compilers, man pages, and most OS tools: a smaller image
# with fewer packages to patch. Nothing needs compiling here, because every
# package in uv.lock ships a prebuilt wheel for Linux.
#
# Not `tiangolo/uvicorn-gunicorn-fastapi`: FastAPI's own docs mark that base
# image as deprecated and recommend building from the official Python image.
# ---------------------------------------------------------------------------
FROM python:3.11.17-slim-trixie

# ---------------------------------------------------------------------------
# uv, the installer
#
# Copy the single `uv` binary out of Astral's official image. This is a
# one-file copy from another image, so it adds no Python packages and no
# installer script. The tag is pinned to the uv version that wrote uv.lock
# (0.12.2), so two builds of the same commit read the lockfile the same way.
# ---------------------------------------------------------------------------
COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /bin/uv

# Every relative path below (COPY destinations, CMD's `src`) is under /app.
# WORKDIR creates the folder if it does not exist.
WORKDIR /app

# ---------------------------------------------------------------------------
# Dependencies: their own layers, BEFORE the application code
#
# Only the two files that DEFINE the dependencies are copied here. The next
# RUN is the slowest step of the build (it downloads torch and the rest), and
# Docker re-runs it only when one of these two files changes.
# ---------------------------------------------------------------------------
COPY pyproject.toml uv.lock ./

# Compile every installed package to bytecode (.pyc files) during the build.
# The runtime user (created below) cannot write into /app/.venv. Without this
# line, Python could not save its compiled files there, and would recompile
# torch, transformers, and langchain in memory on EVERY container start.
ENV UV_COMPILE_BYTECODE=1

# Create /app/.venv from the lockfile:
#
# --locked              Install exactly what uv.lock pins. If uv.lock is out
#                       of date with pyproject.toml, FAIL instead of quietly
#                       resolving new versions. The lockfile chooses the
#                       versions; this step only builds a fresh environment
#                       for the image's own OS and CPU architecture (Linux).
#                       The host's .venv is never copied (see .dockerignore):
#                       its wheels were built for macOS. On Linux, the lock
#                       takes `torch` from PyTorch's CPU-only index, not PyPI
#                       (see `[tool.uv.sources]` in pyproject.toml), so no
#                       NVIDIA/CUDA library is installed.
# --no-dev              Skip the project's `dev` dependency group. The image
#                       serves requests; it does not run the tests. This
#                       omits the GROUP, not every package named in it: the
#                       runtime dependency `deepeval` pulls in pytest, and
#                       several runtime libraries pull in httpx, so both are
#                       still installed. Only ruff is really left out.
# --no-install-project  Install the dependencies only, not ProcureRAG itself.
#                       The code is not copied yet (this layer must not depend
#                       on it), and pyproject.toml has no [build-system]
#                       anyway: the code runs straight from src/ (see CMD).
# --no-cache            Download into a temporary folder that uv deletes when
#                       it finishes. Otherwise uv's download cache would stay in
#                       this layer, a second copy of every package. The cost:
#                       when uv.lock changes, the next build downloads
#                       everything again. (uv's Docker guide shows a BuildKit
#                       cache mount that keeps downloads between builds. That
#                       is an optimization for later, if rebuild time matters.)
RUN uv sync --locked --no-dev --no-install-project --no-cache

# Put the environment first on PATH, so `python` means /app/.venv/bin/python
# (the one with FastAPI, torch, and the rest installed) in CMD, in
# HEALTHCHECK, and in `docker exec`. This is uv's "Using the environment"
# pattern. `source .venv/bin/activate` would not work here: its effect only
# lasts for one shell, and each RUN gets a new one.
ENV PATH="/app/.venv/bin:$PATH"

# ---------------------------------------------------------------------------
# Runtime defaults: safe, NOT secret, and each one can be overridden with
# `docker run --env NAME=value`.
#
# PROCURERAG_LIVE_LLM=0   No paid LLM call. A live run must ask for one
#                         (`--env PROCURERAG_LIVE_LLM=1`) and also pass an
#                         OPENROUTER_API_KEY at run time.
# LANGSMITH_TRACING=false Send no trace to LangSmith. Both names are set,
# LANGSMITH_TRACING_V2    because LangSmith reads the _V2 name first.
#   =false
# HF_HOME                 Where Hugging Face stores downloaded models. A fixed,
#                         known path, so the named cache volume can be mounted
#                         exactly here (see docs/docker-runbook.md).
# HF_HUB_OFFLINE=1        Never contact the Hugging Face Hub. The two models
#                         must already be in HF_HOME. With an empty cache,
#                         startup fails at once with a clear error, instead of
#                         quietly downloading the models again in every new
#                         container. Only the warm-up run sets this to 0.
#
# There is deliberately NO OPENROUTER_API_KEY here, and no ARG for it.
# ENV and ARG values are saved in the image's config and history: anyone who
# can pull the image can read them (`docker inspect`, `docker history`). The
# free path needs no key. A live run passes it at `docker run` time.
# ---------------------------------------------------------------------------
ENV PROCURERAG_LIVE_LLM=0 \
    LANGSMITH_TRACING=false \
    LANGSMITH_TRACING_V2=false \
    HF_HOME=/home/procurerag/.cache/huggingface \
    HF_HUB_OFFLINE=1

# ---------------------------------------------------------------------------
# A non-root runtime user
#
# Containers run as root unless told otherwise. If an attacker ever got this
# service to run their code, as root it could rewrite the app, its packages,
# and anything mounted into the container. The `procurerag` user owns only
# its home folder. It has no login shell, because nobody needs to log in.
# ---------------------------------------------------------------------------
RUN useradd --create-home --shell /usr/sbin/nologin procurerag
USER procurerag

# Create the model cache folder AS the runtime user, so that user owns it.
# This line is what makes the named volume work. When an EMPTY named volume is
# first mounted on a folder that exists in the image, Docker copies that
# folder's contents AND its owner into the volume. Without this line, Docker
# would create the mount point owned by root, and the model download would
# fail with "Permission denied".
RUN mkdir -p "$HF_HOME"

# ---------------------------------------------------------------------------
# The application: data first, then code (the code changes more often)
#
# Only what the service reads: the corpus and labeled queries it loads at
# startup, and the Python modules. COPY writes these files owned by root
# (USER does not change that; only `COPY --chown` would). So the runtime user
# can read its code and data, but cannot change them.
# ---------------------------------------------------------------------------
COPY data/corpus_v1 ./data/corpus_v1
COPY src ./src

# ---------------------------------------------------------------------------
# Network contract
#
# Documentation only: EXPOSE publishes nothing. It records "this image
# listens on 8000" in the image metadata. The actual host -> container
# mapping is made at run time, by `docker run --publish 127.0.0.1:8000:8000`.
# ---------------------------------------------------------------------------
EXPOSE 8000

# ---------------------------------------------------------------------------
# Health check
#
# Docker runs this command INSIDE the container, so it works even when the
# container has no network at all (`--network none`). Docker then reports the
# container as "starting", then "healthy" or "unhealthy".
#
# It calls /health with Python's standard library. The slim image has no
# curl, and adding an OS package only for a health check would grow the image.
# `urlopen` raises an error (exit code 1, a failed probe) on a refused
# connection, on a timeout, or on any HTTP error status.
#
# The timing allows for startup. Uvicorn only starts answering once
# `lifespan` in api.py has loaded both models and built the service.
#
#   --start-period=60s    failed probes in the first 60 s do not count
#   --start-interval=2s   probe every 2 s during those 60 s, so "healthy" is
#                         reported within about 2 s of the app being ready
#   --interval=30s        after that, probe every 30 s
#   --timeout=5s          a probe that takes longer than this counts as failed
#   --retries=3           three failed probes in a row -> "unhealthy"
#
# What "healthy" proves: the process started, loaded the models, built the
# service, and answers HTTP. It does NOT prove that answers are correct, or
# that OpenRouter is reachable. (`/health` never calls the pipeline or the
# provider; see `health` in src/api.py.)
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# ---------------------------------------------------------------------------
# The process
#
# Exec form (a JSON list): Docker starts Python directly as the container's
# main process (PID 1), with no `/bin/sh -c` in between. So the SIGTERM that
# `docker stop` sends reaches Uvicorn, which shuts down cleanly (exit code 0).
# In shell form, `sh` would be PID 1 instead (Debian's `sh` does not hand
# over to the command it runs). The shell does not pass SIGTERM on, so Docker
# would wait out its stop timeout and then kill everything (exit code 137),
# with no clean shutdown.
#
# --app-dir src   Put src/ on sys.path, as in the local Day 21 command, so
#                 `api` can import its sibling modules.
# --host 0.0.0.0  Listen on every network interface INSIDE the container.
#                 Docker forwards published ports to the container's own
#                 network interface, not to its loopback (127.0.0.1). With
#                 127.0.0.1 here, every request from outside would be
#                 refused. Whether the LAN can reach the service is decided
#                 on the HOST side, by `--publish 127.0.0.1:8000:8000`.
# --workers 1     One process. Each extra worker would load its own copy of
#                 both models, and keep its own in-memory rate-limit counter.
#                 With N workers, memory and the effective rate limit
#                 (30 requests per minute, per worker) would both be N times
#                 larger.
# ---------------------------------------------------------------------------
CMD ["python", "-m", "uvicorn", "api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
