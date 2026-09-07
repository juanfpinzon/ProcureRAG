# Corpus v0 — Synthetic Procurement KB Mini-Corpus

Date: 2026-09-07  
Linear: HER-262  
Status: selected for Day 1 preprocessing work

## Decision

Use a synthetic procurement knowledge-base mini-corpus for ProcureRAG v0.

This is intentionally small, inspectable, and non-confidential. The goal is not data realism yet; the goal is to create a stable toy corpus where preprocessing, TF-IDF, BM25, semantic search, and evaluation behavior can be understood from first principles.

## Files

- Corpus: `data/corpus_v0/procurement_kb.jsonl`
- Example queries: `data/corpus_v0/example_queries.jsonl`

## Corpus shape

Each JSONL row is one retrievable document/snippet.

Fields:

- `id` — stable document identifier, e.g. `POL-001`
- `title` — human-readable title
- `doc_type` — policy, SOP, FAQ, guide, contract-summary
- `category` — procurement domain/category
- `region` — applicable region
- `supplier` — supplier name when supplier-specific, otherwise `null`
- `owner` — internal document owner
- `effective_date` — ISO date string
- `risk_tags` — retrieval/evaluation labels
- `text` — main retrievable content

## Included documents

| ID | Title | Retrieval purpose |
|---|---|---|
| POL-001 | Purchase order approval thresholds | currency amounts, approval thresholds, emergency purchases |
| POL-002 | Supplier onboarding due diligence | KYC, sanctions, legal suffixes, high-risk suppliers |
| POL-003 | Information security requirements for SaaS suppliers | ISO 27001, SOC 2, GDPR, DPA, breach notification |
| GUIDE-001 | RFP scoring guide for logistics providers | logistics scoring, SLA, carbon reporting, category guidance |
| CONTRACT-001 | MSA summary — Acme Logistics S.L. | supplier-specific contract lookup, SLA, renewal date |
| CONTRACT-002 | DPA summary — Northstar Analytics Ltd. | data processing, model-training restriction, sub-processors |
| SOP-001 | Three-bid requirement exceptions | competitive sourcing exceptions and audit trail |
| SOP-002 | Invoice mismatch handling | three-way match, price variance, payment blocking |
| FAQ-001 | Can a supplier begin work before PO approval? | FAQ wording, PO approval, emergency work |
| FAQ-002 | Which terms should be preserved in procurement search? | explicit preprocessing design traps |

## Preprocessing traps intentionally present

Your preprocessing script should make deliberate choices around these, not accidentally destroy them:

- Currency and thresholds: `€5,000`, `€50,000`, `€25,000`, `3%`
- Legal suffixes: `S.L.`, `GmbH`, `Ltd.`, `Inc.`
- Acronyms: `PO`, `RFP`, `SLA`, `KPI`, `KYC`, `MSA`, `DPA`, `GDPR`
- Standards: `ISO 27001`, `SOC 2 Type II`
- Dates: `2027-05-12`, `45 days`, `90 days`, `72 hours`
- Supplier names: `Acme Logistics S.L.`, `Northstar Analytics Ltd.`
- Hyphenated/domain terms: `three-way-match`, `sole-source`, `temperature-controlled`, `sub-processors`

## Day 1 preprocessing questions

Before writing code, decide:

1. Will the normalized output preserve both raw text and tokens?
2. Will you lowercase everything, or preserve acronyms/supplier names separately?
3. How will you handle punctuation in `S.L.`, `SOC 2`, and `€50,000`?
4. Which stop words are safe to remove, and which are risky in policy questions?
5. Will you stem/lemmatize now, or postpone until TF-IDF/BM25 behavior is visible?

## Suggested first success criterion

A Day 1 script/test is good enough if it can load one corpus row and show a before/after representation without losing obvious procurement-critical tokens such as `GDPR`, `DPA`, `ISO 27001`, `SOC 2`, `€50,000`, or `Acme Logistics S.L.`.

Do not make the first preprocessing implementation perfect. Make it inspectable.
