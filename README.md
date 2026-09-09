# ProcureRAG

A retrieval-augmented-generation system for procurement knowledge, built from
primitives rather than a framework, over a synthetic (non-confidential)
procurement knowledge base. This is a learning project: each retrieval method
is written by hand — no LangChain/LlamaIndex — so the trade-offs between
lexical and dense retrieval are visible in the code, not hidden behind a
library call.

## What's here

| Module | What it does |
|---|---|
| `src/preprocessing.py` | Loads the JSONL corpus, normalizes text, tokenizes for retrieval |
| `src/retrieval.py` | TF-IDF and BM25 keyword search over an inverted index |
| `src/semantic_search.py` | Dense retrieval via sentence-transformer embeddings + cosine similarity |
| `src/chunking.py` | Splits documents into overlapping sentence-window chunks |
| `src/chunked_search.py` | Dense retrieval at chunk granularity, compared against whole-document retrieval |

Each module is runnable on its own (`python src/retrieval.py`, etc.) and prints
its own worked example against the corpus.

## Corpus

Two versions live under `data/`:

- **`data/corpus_v0/`** — 10 tiny documents, ~60 words each. Used while writing
  preprocessing/TF-IDF/BM25/semantic search from scratch. See
  [`docs/corpus-v0.md`](docs/corpus-v0.md).
- **`data/corpus_v1/`** — 34 realistic documents (725–913 words each) with a
  93-query golden set (`example_queries.jsonl`, with graded relevance and
  verbatim evidence quotes). Built once v0 stopped producing meaningful
  benchmark scores. See [`docs/corpus-v1.md`](docs/corpus-v1.md) for corpus
  shape, baseline numbers (TF-IDF/BM25/dense, document- vs chunk-level), and
  design rationale.

`src/preprocessing.py` currently points at `corpus_v1`.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Running things

```bash
# Run the test suite
uv run pytest

# See TF-IDF/BM25 search results for a few example queries
uv run python src/retrieval.py

# See dense (semantic) search results
uv run python src/semantic_search.py

# Compare whole-document vs chunk-level dense retrieval
uv run python src/chunked_search.py
```

## Docs

`docs/` has a day-by-day build log (`day-01-*.md` through `day-05-*.md`), plus
`learning-log.md` for what was learned each session. Start with
[`docs/corpus-v1.md`](docs/corpus-v1.md) for the current retrieval baselines.

## Status

Week 1 (retrieval from primitives) is complete: preprocessing, TF-IDF, BM25,
semantic search, and chunking all exist with tests. Hybrid search (RRF),
reranking, and retrieval evals are next.
