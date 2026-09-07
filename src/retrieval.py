import math
from collections import Counter

from preprocessing import load_data, preprocess_data, preprocess_text


def build_index(data):
    """Build a small inverted index from raw corpus rows.

    The existing preprocessing function is deliberately called here instead
    of duplicated. Documents and queries must use the same token rules or a
    term that looks identical to a reader could fail to match.
    """
    documents = {}
    inverted_index = {}

    for document in preprocess_data(data):
        document_id = document["id"]
        documents[document_id] = document

        term_counts = Counter(document["tokens"])
        for token, term_count in term_counts.items():
            postings = inverted_index.setdefault(token, {})
            postings[document_id] = term_count

    # Document frequency is the number of documents containing a term, not
    # the total number of times that term appears. That distinction is what
    # lets IDF recognize a term as common or rare across the corpus.
    document_frequency = {
        token: len(postings) for token, postings in inverted_index.items()
    }

    return {
        "documents": documents,
        "inverted_index": inverted_index,
        "document_frequency": document_frequency,
        "document_count": len(documents),
    }


def score_query(index, query):
    """Return document scores for a query using raw TF-IDF.

    This is the intentionally small teaching version of TF-IDF:

        score += query_tf * document_tf * log(document_count / document_frequency)

    A common term has a low IDF contribution, while a term appearing in fewer
    documents contributes more. There is no document-length normalization;
    BM25 can address that limitation in a later retrieval block.
    """
    query_terms = Counter(preprocess_text(query)["tokens"])
    scores = {}
    document_count = index["document_count"]

    if not query_terms or document_count == 0:
        return scores

    for token, query_term_frequency in query_terms.items():
        postings = index["inverted_index"].get(token)
        if not postings:
            continue

        document_frequency = index["document_frequency"][token]
        inverse_document_frequency = math.log(document_count / document_frequency)

        # A term present in every document has IDF=0, so it contributes no
        # ranking information. Do not return zero-score documents for it.
        if inverse_document_frequency == 0:
            continue

        for document_id, document_term_frequency in postings.items():
            scores[document_id] = scores.get(document_id, 0.0) + (
                query_term_frequency
                * document_term_frequency
                * inverse_document_frequency
            )

    return scores


def search(index, query, top_k=3):
    """Return the highest-scoring matching documents for a query."""
    if top_k <= 0:
        return []

    ranked_scores = sorted(
        score_query(index, query).items(),
        key=lambda item: (-item[1], item[0]),
    )
    return [
        {"id": document_id, "score": score}
        for document_id, score in ranked_scores[:top_k]
    ]


def main() -> None:
    index = build_index(load_data())
    queries = [
        "When can we skip the three-bid requirement?",
        "Which SaaS suppliers need SOC 2 Type II or ISO 27001 evidence?",
        "What approval is required for a €60,000 purchase order?"
    ]

    for query in queries:
        print(f"Query: {query}")
        for result in search(index, query):
            print(f"{result['id']}: {result['score']:.4f}")


if __name__ == "__main__":
    main()
