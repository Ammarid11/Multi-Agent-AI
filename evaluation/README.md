# Answer Benchmark

This benchmark checks Carl's generated answers against a **human-reviewed fact
checklist**. It is separate from `/eval`, which measures retrieval only.

## Run

From the project root:

```powershell
.\.venv\Scripts\python.exe evaluate_answers.py
```

The default dataset is `evaluation/answer_benchmark.json`. A custom dataset may
be selected with `--dataset path\to\benchmark.json`.

## Case format

Each answerable case requires:

- `id`: unique, stable identifier
- `query`: the exact prompt sent to Carl
- `answerable`: `true`
- `required_facts`: short, distinctive facts that must appear in Carl's answer
- `expected_sources`: one or more source filenames; at least one must be cited

An unanswerable case uses `answerable: false` and empty `required_facts` and
`expected_sources`. Carl is expected to explicitly abstain.

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "project-owner",
      "query": "Siapa pemilik proyek yang tercatat?",
      "answerable": true,
      "required_facts": ["Nama pemilik yang benar"],
      "expected_sources": ["Data Proyek.md"]
    },
    {
      "id": "unknown-fact",
      "query": "Apa nomor paspor yang tercatat?",
      "answerable": false,
      "required_facts": [],
      "expected_sources": []
    }
  ]
}
```

Replace the example facts with reviewed facts from the Vault before using the
benchmark. Do not add private or highly sensitive data unless the local
environment is approved for it.

## Metrics and limits

- `answer_accuracy`: share of cases where all required phrases and a valid
  expected source are present, or an unanswerable case receives an abstention.
- `fact_coverage`: share of required fact phrases found literally in answers.
- `citation_rate`: share of answerable cases that cite at least one expected
  source filename.
- `abstention_rate`: share of unanswerable cases with an explicit abstention.

Matching is literal after Unicode-aware case folding and whitespace/token
normalization. It is intentionally transparent, but can miss paraphrases and
can be fooled by incidental phrase mentions. The result is a checklist score,
not a semantic judge or a guarantee of factual correctness. Manually review
answers and keep benchmark cases representative.
