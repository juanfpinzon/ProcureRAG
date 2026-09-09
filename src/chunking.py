"""Day 5: split whole documents into smaller, retrievable chunks.

Day 1-4 built retrieval (TF-IDF, BM25, and dense/semantic search) over whole
*documents*. That is fine for this tiny 10-document corpus, but real policies
and contracts run for pages, and the answer to a question usually lives in one
paragraph or sentence, not the whole file. If we hand a whole 3-page contract
to an LLM as "context", we waste prompt budget and make it easier for the
model to miss or misquote the one clause that actually answers the question.

Chunking fixes this by changing the *retrieval unit* from "document" to
"chunk": a small, contiguous piece of a document (here, a short run of
sentences) that can be ranked and retrieved on its own, while still
remembering which document it came from.

This module has two separate jobs, kept separate on purpose (mirroring the
`preprocess_text` / `preprocess_data` split in `preprocessing.py`):

1. Turn raw text into a list of sentences (`split_into_sentences`), and group
   those sentences into overlapping windows (`chunk_sentences`). Neither
   function knows anything about "documents" - they only work with text and
   lists of sentences, which makes them easy to unit test in isolation.
2. Attach document metadata (`chunk_document`, `chunk_corpus`) so each chunk
   remembers which document it came from and where it sits inside it.
"""

import re

# A chunk boundary is placed after a sentence-ending punctuation mark ('.',
# '!', or '?') that is followed by whitespace and then a capital letter. The
# capital-letter lookahead is what keeps this from being a naive "split on
# every period" rule: an abbreviation like "Ltd." or "S.L." is almost always
# followed by a lowercase continuation word ("Ltd. may process...") or by a
# comma, while a real sentence boundary is followed by a new sentence that
# starts with a capital letter ("...approval. Supplier names must...").
#
# This heuristic is not perfect - a sentence that genuinely starts with an
# abbreviation followed by a capitalized proper noun (e.g. "Dr. Smith
# approved it.") would still be split incorrectly. That specific case is a
# real limitation of this regex; the edge cases handled explicitly below
# (whitespace-only input, sentences with no terminal punctuation, and stray
# empty fragments) are the other half of Boot.dev's "Chunked Edge Cases"
# lesson. For the procurement policy/contract text in this corpus, the rule
# below produces correct sentence boundaries - see `tests/test_chunking.py`
# for the exact cases checked.
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# A sentence "properly" ends with one of these. Used below to detect text
# that has no sentence-ending punctuation at all (a document title, a short
# heading, a one-line note) so it can be kept as a single sentence instead of
# being run through the boundary regex, which expects real sentence-final
# punctuation to do anything meaningful.
SENTENCE_END_CHARACTERS = (".", "!", "?")


def split_into_sentences(text):
    """Split text into a list of sentences, handling a few real edge cases.

    1. Leading/trailing whitespace on the whole input is stripped first, and
       whitespace-only input (after stripping) returns an empty list instead
       of a list containing one empty string.
    2. Internal whitespace (stray double spaces, newlines) is also collapsed,
       same normalization `preprocessing.py` already applies, so a paragraph
       with awkward line breaks doesn't produce sentences with ragged
       whitespace inside them.
    3. If, after splitting, there's only *one* piece and it doesn't end with
       sentence-ending punctuation (`.`, `!`, or `?`), the text is treated as
       one sentence as-is rather than something to split further. This
       matters for text with no sentence punctuation at all - a document
       title or a short heading - where running the boundary regex wouldn't
       have split anything anyway, but making that explicit avoids silently
       relying on the regex's behavior for a case it wasn't designed for.
    4. Each split piece is stripped of its own leading/trailing whitespace,
       and (5) any piece that turns out empty after stripping is dropped
       rather than kept as an empty "sentence" - defensive cleanup in case a
       future tweak to the boundary regex above ever produces a stray empty
       match.
    """
    stripped_text = text.strip()
    if not stripped_text:
        return []

    normalized_text = " ".join(stripped_text.split())

    sentences = []
    for raw_sentence in SENTENCE_BOUNDARY_PATTERN.split(normalized_text):
        sentence = raw_sentence.strip()
        if sentence:
            sentences.append(sentence)

    if len(sentences) == 1 and not sentences[0].endswith(SENTENCE_END_CHARACTERS):
        return [normalized_text]

    return sentences


def chunk_sentences(sentences, max_sentences=3, overlap=1):
    """Group a list of sentences into overlapping windows.

    This is the actual "chunking algorithm": a sliding window over the
    sentence list. ``max_sentences`` is the window size, and ``overlap`` is
    how many trailing sentences from one window are repeated at the start of
    the next window. The window advances by ``step = max_sentences -
    overlap`` sentences each time.

    Example with 5 sentences, ``max_sentences=3``, ``overlap=1``
    (step = 3 - 1 = 2):

        sentences:  [S0, S1, S2, S3, S4]
        window 1:   [S0, S1, S2]          (start=0)
        window 2:       [S2, S3, S4]      (start=2, S2 repeats -> the overlap)

    Overlap exists so a sentence that sits right on a chunk boundary (like S2
    above) still shows up in full context in at least one chunk, instead of
    being split across two chunks that each only have half its neighbors.
    Too much overlap, though, means most of each chunk is a duplicate of the
    one before it - more chunks to embed and rank, without much new
    information in each one.

    The loop stops as soon as a window reaches the last sentence, rather than
    always advancing by a fixed step. Without that check, a short list (or
    the tail end of a long one) could get a final window that only repeats
    sentences already fully covered by the previous window - see the
    "short text produces exactly one chunk" test for the case this avoids.
    """
    if max_sentences <= 0:
        raise ValueError("max_sentences must be a positive integer")
    if overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= max_sentences:
        # If overlap were >= max_sentences, every window would fully contain
        # the next one and `start` would never move past it - the window
        # would never advance, and we could loop forever.
        raise ValueError("overlap must be smaller than max_sentences")

    if not sentences:
        return []

    step = max_sentences - overlap
    total_sentences = len(sentences)
    windows = []
    start = 0

    while start < total_sentences:
        end = min(start + max_sentences, total_sentences)
        windows.append(sentences[start:end])

        if end == total_sentences:
            # This window already reaches the last sentence - stop instead of
            # advancing again, which would only produce a trailing window
            # that repeats sentences already covered above.
            break

        start += step

    return windows


def chunk_text(text, max_sentences=3, overlap=1):
    """Split raw text into a list of overlapping, sentence-aligned chunk strings.

    This is the small end-to-end pipeline the Day 5 doc asks for: split the
    text into sentences, group those sentences into overlapping windows, then
    join each window back into a single chunk string. It has no idea which
    document (if any) the text came from - see `chunk_document` below for
    that.
    """
    sentences = split_into_sentences(text)
    sentence_windows = chunk_sentences(
        sentences, max_sentences=max_sentences, overlap=overlap
    )
    return [" ".join(window) for window in sentence_windows]


def chunk_document(document, max_sentences=3, overlap=1):
    """Chunk one corpus record and attach the metadata a retriever needs.

    Per the Day 5 design note, a chunk carries: a deterministic ``chunk_id``,
    the ``document_id`` it came from, its ``chunk_index`` within that
    document, the chunk ``text`` itself, and lightweight metadata copied from
    the source document (here, ``title``) so a retrieved chunk is still
    readable without a second lookup back into the corpus.

    Only the document's ``text`` field is chunked, not the title. A title
    isn't a sentence, and repeating it into every chunk would inflate chunk
    length without adding retrievable content - it's carried alongside each
    chunk as metadata instead.

    ``chunk_id`` is built from ``document_id`` and ``chunk_index`` rather than
    a random id (like ``uuid4()``). That makes it deterministic: chunking the
    same document twice produces identical chunk ids, which is what lets
    tests assert on exact ids instead of "some unique string".
    """
    document_id = document.get("id")
    title = str(document.get("title") or "").strip()
    text = str(document.get("text") or "").strip()

    chunks = chunk_text(text, max_sentences=max_sentences, overlap=overlap)

    return [
        {
            "chunk_id": f"{document_id}::chunk-{chunk_index}",
            "document_id": document_id,
            "chunk_index": chunk_index,
            "text": chunk_text_value,
            "title": title,
        }
        for chunk_index, chunk_text_value in enumerate(chunks)
    ]


def chunk_corpus(data, max_sentences=3, overlap=1):
    """Chunk every document in a corpus, mirroring `preprocess_data`'s shape.

    `data` is the raw list of corpus rows returned by `load_data()` - the same
    input `preprocess_data` takes in `preprocessing.py`. The result is a flat
    list of chunk records (not grouped by document), which is the shape a
    chunk-level retrieval index wants to build over.
    """
    all_chunks = []
    for document in data:
        all_chunks.extend(
            chunk_document(document, max_sentences=max_sentences, overlap=overlap)
        )
    return all_chunks


def main() -> None:
    """Smoke test: chunk the real corpus and print a readable before/after."""
    from preprocessing import load_data

    data = load_data()
    chunks = chunk_corpus(data)

    print(f"{len(data)} documents -> {len(chunks)} chunks (max_sentences=3, overlap=1)\n")
    for document in data:
        document_chunks = [c for c in chunks if c["document_id"] == document["id"]]
        print(f"{document['id']} ({len(document_chunks)} chunk(s)):")
        for chunk in document_chunks:
            print(f"  [{chunk['chunk_id']}] {chunk['text']}")
        print()


if __name__ == "__main__":
    main()
