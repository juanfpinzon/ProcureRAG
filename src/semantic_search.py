"""Small, explainable dense-retrieval example for the Day 4 checkpoint.

The lexical retrievers in ``retrieval.py`` look for shared tokens. This module
adds a separate dense-retrieval path: a Sentence Transformer converts text to
vectors, and cosine similarity ranks documents by the direction of those
vectors. Keeping the paths separate makes the trade-off visible instead of
silently replacing an explainable lexical baseline.
"""

import numpy as np

from preprocessing import load_data, preprocess_data

# This compact model is trained for semantic search and returns 384-dimensional
# normalized embeddings. The model card documents the model's intended use,
# dimensions, normalization, and cosine-compatible scores:
# https://huggingface.co/sentence-transformers/multi-qa-MiniLM-L6-cos-v1
MODEL_NAME = "sentence-transformers/multi-qa-MiniLM-L6-cos-v1"

COMPARISON_CASES = [
    {
        "query": "What checks are needed before onboarding a new high-risk supplier?",
        "expected_id": "POL-002",
        "expected_answer": (
            "Complete KYC, sanctions screening, tax validation, and bank-account "
            "verification; high-risk suppliers also require enhanced due diligence "
            "and Legal approval."
        ),
    },
    {
        "query": "What vendor vetting is required before working with a risky supplier?",
        "expected_id": "POL-002",
        "expected_answer": (
            "Complete supplier due diligence before issuing a PO; a high-risk "
            "supplier requires enhanced due diligence and Legal approval."
        ),
    },
    {
        "query": "Can Northstar use company data for model training?",
        "expected_id": "CONTRACT-002",
        "expected_answer": "No, not without written approval under the DPA.",
    },
    {
        "query": "Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?",
        "expected_id": "POL-003",
        "expected_answer": (
            "SaaS suppliers handling company data must provide ISO 27001 "
            "certification or SOC 2 Type II evidence."
        ),
    },
    {
        "query": "What happens when invoice price variance is over 3%?",
        "expected_id": "SOP-002",
        "expected_answer": (
            "A price variance over 3% requires buyer review, and payment waits "
            "until mismatch resolution is documented."
        ),
    },
]


def load_embedding_model(model_name=MODEL_NAME):
    """Load the embedding model only when a real semantic run needs it.

    The import is intentionally inside this function. That keeps the pure
    cosine helper and model-free unit tests usable without downloading a model
    merely because this module was imported.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def cosine_similarity(vector_a, vector_b):
    """Return the cosine similarity between two numeric vectors.

    Cosine similarity is the dot product divided by both vector magnitudes:

        cos(a, b) = (a · b) / (||a|| * ||b||)

    In plain language, it compares the direction the vectors point in rather
    than their raw size. Identical directions score ``1``; perpendicular
    directions score ``0``. A zero vector has no direction, so this teaching
    implementation returns ``0`` instead of attempting to divide by zero.
    """
    # NumPy performs the dot product and norm calculations in optimized vector
    # operations instead of a Python loop over all 384 embedding dimensions.
    vector_a = np.asarray(vector_a, dtype=float)
    vector_b = np.asarray(vector_b, dtype=float)

    if vector_a.ndim != 1 or vector_b.ndim != 1:
        raise ValueError("Vectors must be one-dimensional")

    if vector_a.shape != vector_b.shape:
        raise ValueError("Vectors must have the same dimension")

    dot_product = np.dot(vector_a, vector_b)
    magnitude_a = np.linalg.norm(vector_a)
    magnitude_b = np.linalg.norm(vector_b)

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return float(dot_product / (magnitude_a * magnitude_b))


def _encode(model, texts):
    """Encode text with the shared settings used for documents and queries."""
    # ``normalize_embeddings=True`` puts vectors on a common unit scale. The
    # explicit cosine helper is still used below so the ranking math remains
    # inspectable, even though cosine and dot product are equivalent for unit
    # vectors.
    return model.encode(
        list(texts),
        normalize_embeddings=True,
        show_progress_bar=False,
    )


def build_semantic_index(data, model):
    """Build an in-memory document-to-embedding index.

    The existing preprocessing combines each title and body and applies the
    repository's normalization rules. We keep that same readable text for
    embedding so the dense retriever represents the same document content that
    the lexical retrievers see.

    ``model`` is passed in rather than created here. That keeps model loading a
    visible boundary, lets the command-line demo load it once, and allows unit
    tests to use deterministic fake vectors without network access.
    """
    documents = {document["id"]: document for document in preprocess_data(data)}
    document_ids = list(documents)

    if not document_ids:
        return {"documents": {}, "embeddings": {}}

    document_texts = [documents[document_id]["normalized_text"] for document_id in document_ids]
    document_embeddings = _encode(model, document_texts)

    if len(document_embeddings) != len(document_ids):
        raise ValueError("The embedding model returned the wrong number of vectors")

    return {
        "documents": documents,
        "embeddings": dict(zip(document_ids, document_embeddings)),
    }


def score_query_semantic(index, query, model):
    """Return cosine scores for every indexed document for a non-empty query."""
    if not query.strip():
        return {}

    documents = index.get("documents", {})
    embeddings = index.get("embeddings", {})
    if not documents:
        return {}

    # Encode one query as a one-item batch so the fake model used by tests and
    # the real Sentence Transformer follow the same simple interface.
    query_embedding = _encode(model, [query])[0]

    # Dense retrieval produces a score for every document, even when no exact
    # query token appears. That is the key contrast with TF-IDF/BM25: semantic
    # similarity can bridge paraphrases, but it can also blur exact numbers,
    # acronyms, identifiers, or legal names that lexical search preserves.
    return {
        document_id: cosine_similarity(query_embedding, embeddings[document_id])
        for document_id in documents
    }


def search_semantic(index, query, model, top_k=3):
    """Return the highest-scoring semantic matches in lexical-search shape."""
    if top_k <= 0:
        return []

    ranked_scores = sorted(
        score_query_semantic(index, query, model).items(),
        key=lambda item: (-item[1], item[0]),
    )
    return [
        {"id": document_id, "score": score}
        for document_id, score in ranked_scores[:top_k]
    ]


def _print_results(results):
    """Print the shared result shape with readable score precision."""
    for result in results:
        print(f"{result['id']}: {result['score']:.4f}")


def main() -> None:
    """Compare lexical and dense rankings for the Day 4 examples."""
    # Load the model once. Reusing it for all five queries avoids repeatedly
    # loading model weights while keeping this demo small and easy to follow.
    model = load_embedding_model()
    data = load_data()

    # Import the existing lexical paths only for comparison. Their behavior is
    # unchanged; the point of this demo is to inspect where each approach wins.
    from retrieval import build_index, search, search_bm25

    lexical_index = build_index(data)
    semantic_index = build_semantic_index(data, model)
    print(f"Semantic model: {MODEL_NAME}")
    for case in COMPARISON_CASES:
        query = case["query"]
        print(f"\nQuery: {query}")
        print(f"Expected document: {case['expected_id']}")
        print(f"Right answer: {case['expected_answer']}")
        print("**## TF-IDF:")
        _print_results(search(lexical_index, query))
        print("**## BM25:")
        _print_results(search_bm25(lexical_index, query))
        print("**## Semantic:")
        _print_results(search_semantic(semantic_index, query, model))


if __name__ == "__main__":
    main()
