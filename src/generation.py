"""Day 10: turn retrieved chunks into a source-cited, natural-language answer.

Up through Day 8/9 (`reranking.py`, `eval_metrics.py`) ProcureRAG can find and
score the *right context* for a query. It still cannot answer the buyer's
actual question in words. This module is the missing last step: retrieve ->
augment a prompt with that context -> generate an answer -> make sure every
claim in the answer can be traced back to a real retrieved chunk.

**The context/citation contract.** The single design decision that matters
most here (see `docs/day-10-augmented-generation-week2-gate.md`, "Block 2")
is that the generator never sees an anonymous blob of text. `build_sources`
below turns a ranked chunk list (from `reranking.two_stage_rerank`, or any
other ranked chunk list shaped the same way) into small numbered dicts -
source 1, source 2, ... - each still carrying its `doc_id`, `chunk_id`,
`title`, and rank/score. The prompt shows the model those numbers
(`[1]`, `[2]`, ...) and tells it to cite them; `validate_citations` then
checks the model's citations against that same numbered list, so a citation
is either traceable to a real chunk or flagged as an "orphan" - never just a
decorative bracket. This is what makes citations auditable instead of
cosmetic (see the module doc's "Citations must be source-backed" section).

**Grounding, not fluency.** If nothing was retrieved, `generate_answer`
returns a fixed "not enough evidence" answer and never calls the model at
all - an empty context has nothing true to say, and calling an LLM anyway
just invites it to answer from its own memory instead of the corpus, which
is exactly the hallucination failure mode this project's citation bar exists
to prevent.

**Test boundary.** `generate_answer(query, sources, client)` takes `client`
as a plain callable, `client(prompt) -> answer_text`. Tests pass a fake
function that returns a canned string - no network, no API key, fully
deterministic (`tests/test_generation.py`). `make_openrouter_client` below
builds a *real* one of these callables for the optional live smoke run in
`main()`; it is never imported by the test suite.

**What this deliberately does not do.** No contradiction-detection model, no
RAGAS/DeepEval integration, no agent framework, no FastAPI serving. Conflict
handling is a prompt rule ("if sources disagree or apply to different
scopes, name the difference and cite each separately"), not a separate
system - see `docs/day-10-augmented-generation-week2-gate.md` for why that
is the right amount of scope for today.
"""

import os
import re

# ---------------------------------------------------------------------------
# The context contract: ranked chunks -> numbered, citable sources
# ---------------------------------------------------------------------------


def build_sources(ranked_chunks, max_sources=None):
    """Turn a ranked chunk-result list into numbered source dicts for a prompt.

    `ranked_chunks` is expected to already be sorted best-first - exactly
    what `reranking.two_stage_rerank`/`rerank_with_cross_encoder` or
    `reranking.build_chunk_shortlist` return. This function does not re-rank
    or re-score anything; it only relabels each chunk with the one thing the
    prompt/citation contract actually needs: a small, stable `source_id`
    (1, 2, 3, ... in the given order) that both the prompt and the answer's
    `[1]`-style citations refer to.

    `.get(...)` is used for the rank/score fields because a first-stage-only
    shortlist (before reranking) uses `first_stage_rank`/`first_stage_score`,
    while a reranked shortlist uses `final_rank`/`reranker_score` - this
    function accepts either shape rather than forcing every caller through
    the reranker.

    `max_sources` caps how many of the ranked chunks are shown to the model
    at all (independent of how many the retrieval step already produced) -
    passing fewer, stronger sources keeps the prompt short and keeps a weak
    tail candidate from tempting the model into citing it.
    """
    if max_sources is not None:
        ranked_chunks = ranked_chunks[:max_sources]

    sources = []
    for source_id, chunk in enumerate(ranked_chunks, start=1):
        sources.append(
            {
                "source_id": source_id,
                "doc_id": chunk["document_id"],
                "title": chunk["title"],
                "chunk_id": chunk.get("chunk_id"),
                "text": chunk["text"],
                "rank": chunk.get("final_rank", chunk.get("first_stage_rank")),
                "score": chunk.get("reranker_score", chunk.get("first_stage_score")),
            }
        )
    return sources


def format_sources_block(sources):
    """Render numbered sources as the evidence block shown inside the prompt.

    Each source becomes one `[n] doc_id — title` header line followed by its
    quoted chunk text, so the model reads the citation number right next to
    the exact evidence it names - the same "which sentence, from which
    document" pairing a human reviewer would need to check the citation.
    """
    if not sources:
        return "(no sources retrieved)"

    lines = []
    for source in sources:
        lines.append(f"[{source['source_id']}] {source['doc_id']} — {source['title']}")
        lines.append(f'"{source["text"]}"')
        lines.append("")  # blank line between sources, for readability
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# The prompt contract: how the model is told to use those sources
# ---------------------------------------------------------------------------

# These four rules are Block 2's prompt contract, written out literally
# rather than left as an idea in the docs: answer only from the sources,
# cite specific ones, do not merge conflicting evidence, and refuse rather
# than guess. Keeping the rules this short and explicit (instead of a long
# persona/style prompt) matches the "grounded generation, not fluent
# summarization" goal - the prompt's job is to constrain the model, not to
# make it sound impressive.
PROMPT_INSTRUCTIONS = """You are a procurement policy assistant. Answer the buyer's question using ONLY the numbered sources below - do not use outside knowledge.

Rules:
1. Every specific claim (a euro amount, threshold, percentage, supplier name, date, or approval role) must be followed by the citation of the source it came from, like [1].
2. If sources disagree, or apply to different suppliers/contracts/scopes, do not merge them into one answer. Name the difference explicitly and cite each source separately.
3. If the sources do not contain enough information to answer, say so plainly instead of guessing.
4. Never cite a source number that is not listed below."""


def build_prompt(query, sources):
    """Assemble the full prompt text: instructions, numbered sources, question.

    This is the whole "augmentation" step in Retrieval-Augmented Generation,
    made literal: the query is *augmented* with retrieved context before it
    ever reaches the model. Returning one plain string (rather than, say, a
    structured chat-messages list) keeps this compatible with any
    `client(prompt) -> text` callable, fake or live, without committing to
    one provider's message-object shape.
    """
    return (
        f"{PROMPT_INSTRUCTIONS}\n\n"
        f"Sources:\n{format_sources_block(sources)}\n\n"
        f"Question: {query}\n"
        f"Answer:"
    )


# ---------------------------------------------------------------------------
# The citation contract: checking the model's [n] markers against real sources
# ---------------------------------------------------------------------------

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def extract_cited_source_ids(answer_text):
    """Return the sorted, de-duplicated source numbers an answer text cites.

    A plain regex over `[digits]` is all Day 10's scope calls for - see the
    module docstring's "what this deliberately does not do". It is also
    exactly what lets `validate_citations` below check a citation without
    ever needing to understand the sentence it is attached to.
    """
    return sorted({int(match) for match in CITATION_PATTERN.findall(answer_text)})


def validate_citations(answer_text, sources):
    """Check an answer's `[n]` citations against the sources it was given.

    Returns a small report a test (or a human) can assert on directly,
    instead of eyeballing printed text:

    - `cited_ids`: every source number the answer text cites at all.
    - `valid_ids`: cited numbers that map to a real source - a citation that
      can actually be traced back to retrieved evidence.
    - `orphan_ids`: cited numbers that do NOT map to any real source - a
      hallucinated citation. Per the contract in
      `docs/day-10-augmented-generation-week2-gate.md` ("no orphan
      citations"), this is a bug to catch, not a stylistic nitpick.
    - `uncited_ids`: real sources that were retrieved but never cited. Not
      necessarily wrong (a source can sit in context without being needed),
      but useful when debugging why an answer feels incomplete.
    """
    valid_id_set = {source["source_id"] for source in sources}
    cited_ids = extract_cited_source_ids(answer_text)

    return {
        "cited_ids": cited_ids,
        "valid_ids": [cited_id for cited_id in cited_ids if cited_id in valid_id_set],
        "orphan_ids": [cited_id for cited_id in cited_ids if cited_id not in valid_id_set],
        "uncited_ids": sorted(valid_id_set - set(cited_ids)),
    }


# ---------------------------------------------------------------------------
# The generation boundary: fake-client-friendly, empty-context-safe
# ---------------------------------------------------------------------------

# The exact, fixed answer returned when there is no retrieved evidence at
# all. It is a constant, not model output, on purpose - see `generate_answer`
# below for why an empty context never reaches the model in the first place.
INSUFFICIENT_EVIDENCE_ANSWER = (
    "I don't have enough retrieved evidence to answer this question - no "
    "relevant procurement documents were found for this query."
)


def generate_answer(query, sources, client):
    """Turn retrieved `sources` into a cited answer, using `client` to generate.

    `client` is the entire live/fake boundary the Day 10 design doc calls
    for: any callable `client(prompt_text) -> answer_text`. In tests this is
    a small fake function returning a canned string (no network, fully
    deterministic); for the live demo in `main()` it is
    `make_openrouter_client(...)`, a real OpenRouter chat-completion call.
    `generate_answer` itself does not know or care which one it was handed.

    Empty-context short-circuit: if `sources` is empty, this returns
    `INSUFFICIENT_EVIDENCE_ANSWER` immediately and never calls `client` at
    all. There is nothing retrieved to prompt the model with, so calling it
    anyway would only invite it to answer from its own parametric memory -
    the opposite of grounded generation. Tests assert on this by handing a
    `client` that raises if it is ever called (see
    `tests/test_generation.py`).
    """
    if not sources:
        return {
            "query": query,
            "answer": INSUFFICIENT_EVIDENCE_ANSWER,
            "sources": [],
            "citations": {"cited_ids": [], "valid_ids": [], "orphan_ids": [], "uncited_ids": []},
        }

    prompt = build_prompt(query, sources)
    answer_text = client(prompt)

    return {
        "query": query,
        "answer": answer_text,
        "sources": sources,
        "citations": validate_citations(answer_text, sources),
    }


# ---------------------------------------------------------------------------
# Optional live client: OpenRouter (OpenAI-compatible), smoke-test only
#
# Nothing above this line imports this section, and `tests/test_generation.py`
# never calls `make_openrouter_client` in a way that reaches the network -
# per the Day 10 test boundary, live calls are demo/smoke-only, never part
# of the deterministic test gate. Loading the API key (`python-dotenv`) and
# making the call (the official `openai` SDK, pointed at OpenRouter's base
# URL) are both real `pyproject.toml` dependencies now, used only here.
# ---------------------------------------------------------------------------

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Checked live against https://openrouter.ai/api/v1/models on 2026-09-14:
# a real, free (prompt+completion cost $0), text-to-text chat model. Free
# models on OpenRouter rotate over time, so if this one is ever retired,
# override it without touching code by setting OPENROUTER_MODEL in `.env` -
# see https://openrouter.ai/models?max_price=0 for the current free list.
#
# This particular model is a *reasoning* model: by default it thinks out
# loud for thousands of tokens before answering, and without the
# `reasoning: {"exclude": True}` request option below, that entire
# chain-of-thought comes back as `message.content` instead of a clean
# answer - confirmed live on 2026-09-14 (a first run, before that option
# was added, printed several paragraphs of the model narrating which
# source to cite before trailing off into truncated, garbled text once it
# ran out of budget). If you swap in a different free model and see the
# same thing, this is why.
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3.5-lightning:free"


def make_openrouter_client(model=None, api_key=None):
    """Build a live `client(prompt) -> answer_text` callable backed by OpenRouter.

    OpenRouter exposes an OpenAI-compatible `/chat/completions` endpoint, so
    the official `openai` Python SDK works against it unmodified - the only
    difference from talking to OpenAI itself is pointing `base_url` at
    OpenRouter and using an OpenRouter key. The returned closure has the
    exact same shape as the fake clients in `tests/test_generation.py`
    (`client(prompt) -> answer_text`), which is what lets `generate_answer`
    above use either one without any special-casing.

    Raises `RuntimeError` immediately - before the `openai` client is even
    constructed - if no API key is available, so a missing key fails loudly
    and fast rather than as a confusing 401 deep inside a request.
    """
    from openai import OpenAI

    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Put it in .env (OPENROUTER_API_KEY=...) "
            "or export it before calling make_openrouter_client()."
        )
    model = model or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)

    openai_client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)

    def client(prompt):
        response = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            # `reasoning` is an OpenRouter extension, not a standard OpenAI
            # API field, so it has to be passed through `extra_body` rather
            # than as a normal keyword argument. `exclude: True` keeps a
            # reasoning model's internal chain-of-thought out of the
            # response entirely - see `DEFAULT_OPENROUTER_MODEL`'s comment
            # above for the actual broken output this fixes.
            extra_body={"reasoning": {"exclude": True}},
        )
        return response.choices[0].message.content

    return client


# ---------------------------------------------------------------------------
# Demo: one easy query, one multi-document query, real retrieved context
# ---------------------------------------------------------------------------

# Q001 is a single-document threshold lookup (the easy case). Q091 is Day
# 9's flagged `multi_doc` weak slice - answering it correctly requires
# combining evidence from three different documents (POL-001, POL-003,
# GUIDE-002) rather than confidently quoting just one. Demoing only Q001
# would prove nothing about whether generation handles the harder,
# real-world case Day 10 exists to stress-test - see
# `docs/day-10-augmented-generation-week2-gate.md`.
DEMO_QUERY_IDS = ["Q001", "Q091"]


def _print_sources(sources):
    for source in sources:
        text = source["text"]
        preview = text if len(text) <= 160 else text[:157] + "..."
        print(f"    [{source['source_id']}] {source['doc_id']} — {source['title']}")
        print(f'        "{preview}"')


def main() -> None:
    """Retrieve real context for `DEMO_QUERY_IDS`, then generate a cited answer.

    Builds the same first-stage-plus-reranking pipeline `reranking.main()`
    and `eval_metrics.main()` already build (nothing new here - this module
    only adds what happens *after* a ranked chunk list exists). Whether the
    final generation step is live or not depends entirely on whether
    `OPENROUTER_API_KEY` is set (in `.env` or the shell): with no key, this
    still prints the retrieved sources and stops there, honestly, rather
    than faking a model answer.
    """
    from chunked_search import build_chunk_lexical_index, build_chunk_semantic_index
    from chunking import chunk_corpus
    from dotenv import load_dotenv
    from hybrid_search import load_example_queries
    from preprocessing import load_data
    from reranking import load_cross_encoder, two_stage_rerank
    from semantic_search import load_embedding_model

    # Reads `.env` (walking up from this file's directory, so it finds the
    # project-root `.env` from anywhere `main()` is run) and copies any
    # `KEY=VALUE` lines into `os.environ`, without overwriting a variable
    # already exported in the real shell environment.
    load_dotenv()

    data = load_data()
    chunks = chunk_corpus(data)
    embedding_model = load_embedding_model()
    chunk_lexical_index = build_chunk_lexical_index(chunks)
    chunk_semantic_index = build_chunk_semantic_index(chunks, embedding_model)
    cross_encoder_model = load_cross_encoder()

    queries_by_id = {query["query_id"]: query for query in load_example_queries()}

    client = make_openrouter_client() if os.environ.get("OPENROUTER_API_KEY") else None
    if client is None:
        print(
            "No OPENROUTER_API_KEY found (checked .env and the environment) - "
            "showing retrieved sources only and skipping the live call.\n"
            "Set OPENROUTER_API_KEY in .env to see a real generated answer.\n"
        )

    for query_id in DEMO_QUERY_IDS:
        query_row = queries_by_id[query_id]
        query = query_row["query"]

        reranked = two_stage_rerank(
            query,
            chunk_lexical_index,
            chunk_semantic_index,
            embedding_model,
            cross_encoder_model,
            top_k=5,
        )
        sources = build_sources(reranked)

        print(f"\n{query_id} ({query_row['query_type']}): {query}")
        print("  retrieved sources:")
        _print_sources(sources)

        if client is None:
            continue

        result = generate_answer(query, sources, client)
        print(f"\n  answer:\n    {result['answer']}")
        print(f"\n  citation check: {result['citations']}")


if __name__ == "__main__":
    main()
