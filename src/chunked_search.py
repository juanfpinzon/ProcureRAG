"""Day 5: compare whole-document semantic search against chunk-level semantic search.

`semantic_search.py` (Day 4) embeds each whole document and ranks documents by
cosine similarity to the query. That is the retrieval unit this module
changes: instead of embedding one vector per *document*, it embeds one vector
per *chunk* (a few sentences, produced by `chunking.chunk_corpus`) and ranks
chunks instead.

Everything else - the embedding model, `cosine_similarity`, the result shape -
is reused unchanged from `semantic_search.py`. Keeping those identical is what
makes the whole-document vs chunk-level comparison in `main()` meaningful: the
only variable that changes between the two searches is the retrieval unit.
"""

from chunking import chunk_corpus
from semantic_search import cosine_similarity

MAX_SENTENCES = 3
OVERLAP = 1


def _encode(model, texts):
    """Encode text with the same settings `semantic_search._encode` uses.

    Duplicated here (it's three lines) rather than imported, so this module
    reads standalone without a reader needing to jump into
    `semantic_search.py` to see what "encode" means. `normalize_embeddings`
    puts every vector on a common unit scale so cosine similarity behaves the
    same way for chunks as it does for whole documents.
    """
    return model.encode(
        list(texts),
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def build_chunk_semantic_index(chunks, model):
    """Build an in-memory chunk-to-embedding index.

    This mirrors `semantic_search.build_semantic_index`, but keyed by
    `chunk_id` instead of `document_id`. Each chunk record is kept in full
    (not just its embedding) so a search result can report which document a
    matching chunk came from, and show the chunk text itself.
    """
    if not chunks:
        return {"chunks": {}, "embeddings": {}}

    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    chunk_texts = [chunk["text"] for chunk in chunks]
    chunk_embeddings = _encode(model, chunk_texts)

    if len(chunk_embeddings) != len(chunk_ids):
        raise ValueError("The embedding model returned the wrong number of vectors")

    return {
        "chunks": {chunk["chunk_id"]: chunk for chunk in chunks},
        "embeddings": dict(zip(chunk_ids, chunk_embeddings)),
    }


def score_query_semantic_chunks(index, query, model):
    """Return cosine scores for every indexed chunk for a non-empty query."""
    if not query.strip():
        return {}

    chunks = index.get("chunks", {})
    embeddings = index.get("embeddings", {})
    if not chunks:
        return {}

    query_embedding = _encode(model, [query])[0]

    return {
        chunk_id: cosine_similarity(query_embedding, embeddings[chunk_id])
        for chunk_id in chunks
    }


def search_semantic_chunks(index, query, model, top_k=3):
    """Return the highest-scoring chunks for a query.

    Unlike `semantic_search.search_semantic` (which returns just an `id` and
    `score` for a whole document), each result here also carries the chunk's
    `document_id` and `text` - the retrieved unit is small enough that seeing
    its text directly, rather than looking it up separately, is the point.
    """
    if top_k <= 0:
        return []

    ranked_scores = sorted(
        score_query_semantic_chunks(index, query, model).items(),
        key=lambda item: (-item[1], item[0]),
    )
    return [
        {
            "chunk_id": chunk_id,
            "document_id": index["chunks"][chunk_id]["document_id"],
            "text": index["chunks"][chunk_id]["text"],
            "score": score,
        }
        for chunk_id, score in ranked_scores[:top_k]
    ]


# Two procurement questions whose answer sits in one specific sentence inside
# a longer document - exactly the case where whole-document retrieval hands
# an LLM more text than it needs, and chunk-level retrieval hands it (close
# to) just the sentence that answers the question.
COMPARISON_QUERIES = [
    {
        "query": "What happens when invoice price variance is over 3%?",
        "expected_document_id": "SOP-002",
    },
    {
        "query": "When can we skip the three-bid requirement?",
        "expected_document_id": "SOP-001",
    },
]


def main() -> None:
    """Print whole-document vs chunk-level semantic search side by side."""
    from preprocessing import load_data
    from semantic_search import (
        build_semantic_index,
        load_embedding_model,
        search_semantic,
    )

    # Load the model once and reuse it for both indexes and every query, the
    # same way semantic_search.py's own demo does.
    model = load_embedding_model()
    data = load_data()

    whole_document_index = build_semantic_index(data, model)
    chunk_index = build_chunk_semantic_index(
        chunk_corpus(data, max_sentences=MAX_SENTENCES, overlap=OVERLAP), model
    )

    for case in COMPARISON_QUERIES:
        query = case["query"]
        print(f"\nQuery: {query}")
        print(f"Expected document: {case['expected_document_id']}")

        print("\nWhole-document semantic search (top 1):")
        for result in search_semantic(whole_document_index, query, model, top_k=1):
            document_text = whole_document_index["documents"][result["id"]][
                "normalized_text"
            ]
            print(f"  {result['id']} (score={result['score']:.4f})")
            print(f"  Full document text passed as context:\n    {document_text}")

        print("\nChunk-level semantic search (top 1):")
        for result in search_semantic_chunks(chunk_index, query, model, top_k=1):
            print(
                f"  {result['chunk_id']} from {result['document_id']} "
                f"(score={result['score']:.4f})"
            )
            print(f"  Chunk text passed as context:\n    {result['text']}")


if __name__ == "__main__":
    main()
