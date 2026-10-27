"""Tests for `scripts/chat_smoke.py`'s judgement, with no network and no cost.

The script's value is in `check_view`: it must pass an honest answer and
catch each way an answer can be dishonest or wrong. These tests feed it
hand-made BrowserViews, the shape the BFF returns.
"""

import importlib.util
from pathlib import Path


def _load_chat_smoke_module():
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "chat_smoke.py"
    spec = importlib.util.spec_from_file_location("chat_smoke", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


chat_smoke = _load_chat_smoke_module()
LABELED = chat_smoke.load_labeled_queries()
ITEMS = {item["name"]: item for item in chat_smoke.SMOKE_SET}
UNCHECKED = "no query_id was given ... Treat this result as unchecked."


def view(state="answered", text=None, sources=(), caveats=(), guards=()):
    return {
        "state": state,
        "message": "fixed message",
        "text": text,
        "sources": list(sources),
        "caveats": list(caveats),
        "guards": list(guards),
        "retry_after_seconds": None,
    }


def source(source_id, doc_id, cited):
    return {"source_id": source_id, "doc_id": doc_id, "chunk_id": f"{doc_id}::chunk-1", "cited": cited}


GOOD_Q001 = view(
    text="EUR 60,000 is Band 3: VP Procurement approval with a documented Finance review [1].",
    sources=[source(1, "POL-001", True), source(2, "FAQ-001", False)],
)


def test_the_smoke_set_is_adr_section_10_plus_every_preset():
    sent = [chat_smoke.question_text(item, LABELED) for item in chat_smoke.SMOKE_SET]
    assert [item.get("query_id") for item in chat_smoke.SMOKE_SET if chat_smoke.is_preset(item)] == [
        "Q001",
        "Q005",
        "Q021",
        "Q090",
    ]
    assert "Who needs to approve a purchase order worth EUR 60,000?" in sent
    assert "What is the policy for buying company cars for executives?" in sent
    # Q091 is sent with its exact labeled text, but never as a preset.
    assert LABELED["Q091"]["query"] in sent
    assert not chat_smoke.is_preset(ITEMS["Q091 typed as free text (known failure)"])


def test_an_honest_cited_preset_answer_passes():
    assert chat_smoke.check_view(ITEMS["Q001 preset"], GOOD_Q001, LABELED) == []


def test_each_wrong_or_dishonest_answer_is_caught():
    q001 = ITEMS["Q001 preset"]
    sources = GOOD_Q001["sources"]
    cases = {
        "a marker for a source that was not returned": view(text="VP Procurement and Finance [3].", sources=sources),
        "a marker for a source not marked cited": view(text="VP Procurement and Finance [2].", sources=sources),
        "no citation at all": view(text="VP Procurement and Finance.", sources=sources),
        "a missing key fact": view(text="The Budget Owner approves it [1].", sources=sources),
        "no gold document cited": view(text="VP Procurement and Finance [1].", sources=[source(1, "SOP-003", True)]),
        "a preset with the free-text caveat": view(
            text=GOOD_Q001["text"], sources=sources, caveats=[UNCHECKED]
        ),
        "the wrong state": view(state="model_declined", text="The sources do not say."),
    }
    for label, bad in cases.items():
        assert chat_smoke.check_view(q001, bad, LABELED), label


def test_free_text_needs_its_caveat_and_a_block_needs_its_guard():
    paraphrase = ITEMS["Q001 paraphrase (free text)"]
    answer = view(text="VP Procurement approval [1].", sources=[source(1, "POL-001", True)])
    assert chat_smoke.check_view(paraphrase, answer, LABELED) == ["free text without the 'unchecked' caveat"]
    assert chat_smoke.check_view(paraphrase, {**answer, "caveats": [UNCHECKED]}, LABELED) == []

    injection = ITEMS["prompt injection"]
    assert chat_smoke.check_view(injection, view(state="blocked", guards=["prompt_injection"]), LABELED) == []
    assert chat_smoke.check_view(injection, view(state="blocked", guards=["off_topic"]), LABELED) == [
        "the 'prompt_injection' guard did not fire"
    ]


def test_q090_passes_only_as_its_honest_gap():
    q090 = ITEMS["Q090 preset (honest gap)"]
    gap = view(state="gap_report", text="Not answered: ... missing primary document(s) ['SOP-002'] ...")
    assert chat_smoke.check_view(q090, gap, LABELED) == []
    # An answer would mean retrieval changed: the smoke must say so.
    answered = view(text="Goods received not invoiced [1].", sources=[source(1, "GLOSSARY-001", True)])
    assert chat_smoke.check_view(q090, answered, LABELED) == ["state 'answered', expected one of ['gap_report']"]


def test_an_unanswerable_question_passes_only_as_a_refusal():
    cars = ITEMS["in scope but unanswerable (free text)"]
    declined = view(state="model_declined", text="The sources do not cover company cars.", caveats=[UNCHECKED])
    assert chat_smoke.check_view(cars, declined, LABELED) == []
    invented = view(text="Executives may lease cars up to EUR 900/month [1].", sources=[source(1, "POL-002", True)])
    assert chat_smoke.check_view(cars, {**invented, "caveats": [UNCHECKED]}, LABELED)
