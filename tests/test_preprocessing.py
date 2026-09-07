import importlib.util
from pathlib import Path


def _load_preprocessing_module():
    module_path = Path(__file__).resolve().parents[1] / "src" / "preprocessing.py"
    spec = importlib.util.spec_from_file_location("preprocessing", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_data_reads_jsonl_line_by_line(tmp_path, monkeypatch):
    data_file = tmp_path / "procurement_kb.jsonl"
    data_file.write_text('{"a": 1}\n\n{"b": 2}\n', encoding="utf-8")

    preprocessing = _load_preprocessing_module()
    monkeypatch.setattr(preprocessing, "DATA_PATH", str(data_file))

    assert preprocessing.load_data() == [{"a": 1}, {"b": 2}]


def test_preprocess_text_preserves_casing_in_text_and_lowercases_tokens():
    preprocessing = _load_preprocessing_module()

    result = preprocessing.preprocess_text(
        "  GDPR DPA ISO 27001 SOC 2 €50,000 Acme Logistics S.L. three-way-match  "
    )

    assert result["normalized_text"] == (
        "GDPR DPA ISO 27001 SOC 2 €50,000 Acme Logistics S.L. three-way-match"
    )
    assert {
        "gdpr",
        "dpa",
        "iso",
        "27001",
        "soc",
        "2",
        "€50,000",
        "acme",
        "logistics",
        "s.l.",
        "three-way-match",
    }.issubset(result["tokens"])


def test_preprocess_data_combines_title_and_text():
    preprocessing = _load_preprocessing_module()

    result = preprocessing.preprocess_data(
        [{"id": "DOC-1", "title": "Supplier DPA", "text": "GDPR, applies."}]
    )

    assert result == [
        {
            "id": "DOC-1",
            "normalized_text": "Supplier DPA GDPR, applies.",
            "tokens": ["supplier", "dpa", "gdpr", "applies"],
        }
    ]
