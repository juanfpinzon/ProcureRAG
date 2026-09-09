import importlib.util
import sys
from pathlib import Path

import pytest


def _load_chunking_module():
    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"

    # chunking.py's main() imports the sibling preprocessing module. Add src
    # to the import path only while loading it, matching the import approach
    # used by the existing retrieval and semantic_search tests.
    sys.path.insert(0, str(src_path))
    try:
        module_path = src_path / "chunking.py"
        spec = importlib.util.spec_from_file_location("chunking", module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


# --- split_into_sentences -----------------------------------------------


def test_split_into_sentences_splits_on_sentence_boundaries():
    chunking = _load_chunking_module()

    sentences = chunking.split_into_sentences(
        "Invoices are matched against purchase order, goods receipt, and "
        "contracted pricing. A price variance over 3% requires buyer review. "
        "Suppliers should not be paid until mismatch resolution is documented."
    )

    assert sentences == [
        "Invoices are matched against purchase order, goods receipt, and "
        "contracted pricing.",
        "A price variance over 3% requires buyer review.",
        "Suppliers should not be paid until mismatch resolution is documented.",
    ]


def test_split_into_sentences_does_not_split_mid_abbreviation():
    chunking = _load_chunking_module()

    # "Ltd." here is followed by a lowercase continuation word ("may"), not a
    # new capitalized sentence, so it must not be treated as a sentence end.
    sentences = chunking.split_into_sentences(
        "Northstar Analytics Ltd. may process sales data for dashboard "
        "reporting. The DPA prohibits use of company data for model training."
    )

    assert sentences == [
        "Northstar Analytics Ltd. may process sales data for dashboard "
        "reporting.",
        "The DPA prohibits use of company data for model training.",
    ]


def test_split_into_sentences_handles_empty_and_whitespace_only_text():
    chunking = _load_chunking_module()

    assert chunking.split_into_sentences("") == []
    assert chunking.split_into_sentences("   \n  ") == []


def test_split_into_sentences_strips_whitespace_from_input_and_each_sentence():
    chunking = _load_chunking_module()

    # Stray leading/trailing whitespace around the whole text, and extra
    # internal spacing between sentences, must not leak into the output.
    sentences = chunking.split_into_sentences(
        "  \n First sentence.   Second sentence.  \n  "
    )

    assert sentences == ["First sentence.", "Second sentence."]
    assert all(sentence == sentence.strip() for sentence in sentences)
    assert all(sentence for sentence in sentences)


def test_split_into_sentences_keeps_unpunctuated_text_as_a_single_sentence():
    chunking = _load_chunking_module()

    # A document title or short heading often has no sentence-ending
    # punctuation at all. The boundary regex has nothing to match on, so this
    # must come back as one whole sentence rather than an empty list or a
    # sentence missing its last character.
    assert chunking.split_into_sentences("Draft note pending review") == [
        "Draft note pending review"
    ]
    assert chunking.split_into_sentences("Approved") == ["Approved"]


# --- chunk_sentences (the sliding-window algorithm) ----------------------


def test_chunk_sentences_with_no_overlap_tiles_the_sentence_list():
    chunking = _load_chunking_module()
    sentences = ["S0.", "S1.", "S2.", "S3.", "S4.", "S5."]

    windows = chunking.chunk_sentences(sentences, max_sentences=2, overlap=0)

    assert windows == [
        ["S0.", "S1."],
        ["S2.", "S3."],
        ["S4.", "S5."],
    ]


def test_chunk_sentences_with_overlap_repeats_trailing_sentences():
    chunking = _load_chunking_module()
    sentences = ["S0.", "S1.", "S2.", "S3.", "S4."]

    windows = chunking.chunk_sentences(sentences, max_sentences=3, overlap=1)

    # step = max_sentences - overlap = 2, so window 2 starts at sentence
    # index 2 - the last sentence ("S2.") of window 1 reappears as the first
    # sentence of window 2.
    assert windows == [
        ["S0.", "S1.", "S2."],
        ["S2.", "S3.", "S4."],
    ]


def test_chunk_sentences_stops_once_a_window_reaches_the_end():
    chunking = _load_chunking_module()
    # Exactly max_sentences long: one window already covers everything, so a
    # second, fully-redundant window must not be produced.
    sentences = ["S0.", "S1.", "S2."]

    windows = chunking.chunk_sentences(sentences, max_sentences=3, overlap=1)

    assert windows == [["S0.", "S1.", "S2."]]


def test_chunk_sentences_short_list_produces_exactly_one_chunk():
    chunking = _load_chunking_module()
    sentences = ["Only one sentence."]

    windows = chunking.chunk_sentences(sentences, max_sentences=3, overlap=1)

    assert windows == [["Only one sentence."]]


def test_chunk_sentences_handles_empty_list():
    chunking = _load_chunking_module()

    assert chunking.chunk_sentences([], max_sentences=3, overlap=1) == []


def test_chunk_sentences_rejects_overlap_greater_than_or_equal_to_max_sentences():
    chunking = _load_chunking_module()

    with pytest.raises(ValueError, match="overlap must be smaller"):
        chunking.chunk_sentences(["S0.", "S1."], max_sentences=2, overlap=2)


def test_chunk_sentences_rejects_non_positive_max_sentences():
    chunking = _load_chunking_module()

    with pytest.raises(ValueError, match="max_sentences must be a positive integer"):
        chunking.chunk_sentences(["S0."], max_sentences=0, overlap=0)


def test_chunk_sentences_rejects_negative_overlap():
    chunking = _load_chunking_module()

    with pytest.raises(ValueError, match="overlap cannot be negative"):
        chunking.chunk_sentences(["S0."], max_sentences=2, overlap=-1)


# --- chunk_text (sentence split + windowing, joined back to strings) -----


def test_chunk_text_end_to_end_with_overlap():
    chunking = _load_chunking_module()
    text = (
        "New suppliers must complete KYC before receiving a purchase order. "
        "High-risk suppliers require enhanced due diligence and Legal "
        "approval. Supplier names must match registration documents exactly."
    )

    chunks = chunking.chunk_text(text, max_sentences=2, overlap=1)

    assert chunks == [
        "New suppliers must complete KYC before receiving a purchase order. "
        "High-risk suppliers require enhanced due diligence and Legal "
        "approval.",
        "High-risk suppliers require enhanced due diligence and Legal "
        "approval. Supplier names must match registration documents exactly.",
    ]


def test_chunk_text_with_no_overlap():
    chunking = _load_chunking_module()
    text = "Sentence one. Sentence two. Sentence three. Sentence four."

    chunks = chunking.chunk_text(text, max_sentences=2, overlap=0)

    assert chunks == [
        "Sentence one. Sentence two.",
        "Sentence three. Sentence four.",
    ]


def test_chunk_text_handles_short_text_as_a_single_chunk():
    chunking = _load_chunking_module()

    chunks = chunking.chunk_text("Just one sentence here.", max_sentences=3, overlap=1)

    assert chunks == ["Just one sentence here."]


def test_chunk_text_handles_empty_text():
    chunking = _load_chunking_module()

    assert chunking.chunk_text("", max_sentences=3, overlap=1) == []
    assert chunking.chunk_text("   ", max_sentences=3, overlap=1) == []


# --- chunk_document / chunk_corpus (attaching document metadata) ---------


def test_chunk_document_attaches_deterministic_ids_and_metadata():
    chunking = _load_chunking_module()
    document = {
        "id": "SOP-002",
        "title": "Invoice mismatch handling",
        "text": "Sentence one. Sentence two. Sentence three. Sentence four.",
    }

    chunks = chunking.chunk_document(document, max_sentences=2, overlap=0)

    assert chunks == [
        {
            "chunk_id": "SOP-002::chunk-0",
            "document_id": "SOP-002",
            "chunk_index": 0,
            "text": "Sentence one. Sentence two.",
            "title": "Invoice mismatch handling",
        },
        {
            "chunk_id": "SOP-002::chunk-1",
            "document_id": "SOP-002",
            "chunk_index": 1,
            "text": "Sentence three. Sentence four.",
            "title": "Invoice mismatch handling",
        },
    ]


def test_chunk_document_ids_are_deterministic_across_repeated_calls():
    chunking = _load_chunking_module()
    document = {
        "id": "POL-001",
        "title": "Purchase order approval thresholds",
        "text": "Sentence one. Sentence two. Sentence three.",
    }

    first_run = chunking.chunk_document(document)
    second_run = chunking.chunk_document(document)

    assert [chunk["chunk_id"] for chunk in first_run] == [
        chunk["chunk_id"] for chunk in second_run
    ]


def test_chunk_document_handles_a_document_with_empty_text():
    chunking = _load_chunking_module()

    assert chunking.chunk_document({"id": "EMPTY-001", "title": "", "text": ""}) == []


def test_chunk_corpus_flattens_chunks_from_every_document():
    chunking = _load_chunking_module()
    data = [
        {"id": "DOC-1", "title": "", "text": "One sentence only."},
        {
            "id": "DOC-2",
            "title": "",
            "text": "Sentence one. Sentence two. Sentence three.",
        },
    ]

    chunks = chunking.chunk_corpus(data, max_sentences=2, overlap=0)

    assert [chunk["chunk_id"] for chunk in chunks] == [
        "DOC-1::chunk-0",
        "DOC-2::chunk-0",
        "DOC-2::chunk-1",
    ]


def test_chunk_corpus_over_the_real_procurement_corpus_produces_more_chunks_than_documents():
    chunking = _load_chunking_module()

    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"
    sys.path.insert(0, str(src_path))
    try:
        from preprocessing import load_data

        data = load_data()
    finally:
        sys.path.pop(0)

    chunks = chunking.chunk_corpus(data)

    # Every document in this corpus has multiple sentences, so chunking must
    # produce at least as many chunks as documents - this is the concrete
    # "whole-document retrieval is too coarse" evidence for Day 5.
    assert len(chunks) >= len(data)
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
