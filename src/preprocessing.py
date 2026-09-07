import json
import os
import re

PROJECT_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ProcureRAG")
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "corpus_v0", "procurement_kb.jsonl")
TOKEN_PATTERN = re.compile(
    r"€\d[\d,.]*|(?:[^\W_]\.){2,}|[^\W_]+(?:-[^\W_]+)*|[^\w\s]",
    re.UNICODE,
)


def load_data():
    data = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def preprocess_text(text):
    normalized_text = " ".join(text.lower().split())
    return {
        "normalized_text": normalized_text,
        "tokens": TOKEN_PATTERN.findall(normalized_text),
    }


def preprocess_data(data):
    preprocessed_data = []
    for item in data:
        title = str(item.get("title") or "").strip()
        text = str(item.get("text") or "").strip()
        preprocessed_item = {"id": item.get("id"), **preprocess_text(f"{title} {text}".strip())}
        preprocessed_data.append(preprocessed_item)
    return preprocessed_data


def main() -> None:
    data = load_data()
    preprocessed_data = preprocess_data(data)
    for i, (raw_item, item) in enumerate(zip(data, preprocessed_data)):
        raw_text = f"{raw_item.get('title', '')} {raw_item.get('text', '')}".strip()
        print(f"Item {i} before: {raw_text}")
        print(f"Item {i} after:  {item['normalized_text']}")
        print(f"Item {i} tokens: {item['tokens']}")


if __name__ == "__main__":
    main()
