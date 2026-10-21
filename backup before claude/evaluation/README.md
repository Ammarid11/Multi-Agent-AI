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
For a non-destructive run using only the source files listed in the dataset,
pass `--isolated-vault`; embeddings and the temporary Qdrant index require the
configured local Ollama service.

## Case format

Each answerable case requires:

- `id`: unique, stable identifier
- `query`: the exact prompt sent to Carl
- `answerable`: `true`
- `required_facts`: short, distinctive facts that must appear in Carl's answer
- `expected_sources`: one or more source filenames; at least one must be cited

An unanswerable case uses `answerable: false` and empty `required_facts` and
`expected_sources`. Carl is expected to explicitly abstain. Optionally assign
each case a `category` such as `factuality`, `retrieval`, `abstention`,
`reasoning`, `tool_use`, or `consistency`. Use category labels consistently to
get useful subgroup scores.

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "project-owner",
      "query": "Siapa pemilik proyek yang tercatat?",
      "answerable": true,
      "category": "factuality",
      "required_facts": ["Nama pemilik yang benar"],
      "expected_sources": ["Data Proyek.md"]
    },
    {
      "id": "unknown-fact",
      "query": "Apa nomor paspor yang tercatat?",
      "answerable": false,
      "category": "abstention",
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

- `answer_accuracy`: share of all cases passing the checklist; unanswerable
  cases pass only when Carl explicitly abstains.
- `answerable_accuracy`: share of answerable cases with all required phrases
  and at least one expected source filename present.
- `answerable_fact_accuracy`: share of answerable cases with all required
  phrases present, regardless of whether a citation was included.
- `fact_coverage`: share of required fact phrases found literally in answers.
- `citation_rate`: share of answerable cases that cite at least one expected
  source filename.
- `abstention_rate`: share of unanswerable cases with an explicit abstention.
- `category_results`: pass rate and number of samples for each category.
- `answer_accuracy_ci95`, `answerable_accuracy_ci95`, and
  `answerable_fact_accuracy_ci95`: two-sided 95% Wilson intervals for the
  per-case pass rates.
- `run_configuration`: configured writer/embedding model names and writer
  options for reproducing a completed run. These are configured values, not a
  verification of the model actually loaded by the local runtime.
  `index_mode` distinguishes use of the configured Vault from an isolated
  temporary Vault containing only `source_notes`.

Matching is literal after Unicode-aware case folding and whitespace/token
normalization. It is intentionally transparent, but can miss paraphrases and
can be fooled by incidental phrase mentions. The result is a checklist score,
not a semantic judge or a guarantee of factual correctness. Manually review
answers and keep benchmark cases representative. Wilson intervals assume
independent binomial samples; they are only indicative for small or
intentionally selected datasets.

## Building a meaningful test set

The checked-in dataset is a reviewed 17-case pilot, not a representative
accuracy benchmark. Do not add invented facts or private Vault content that has
not been approved and reviewed. Before treating a score as an accuracy estimate:

1. Add independently reviewed answerable and unanswerable cases covering the
   intended categories and realistic question difficulty. Include expected
   source filenames and concise fact phrases for answerable cases.
2. Keep a held-out set that is not used to tune prompts or retrieval. Avoid
   duplicate or near-duplicate questions across development and held-out sets.
3. Run the same model, prompt, and tool configuration for comparisons, and
   record those settings alongside each report.
4. Manually review answers for paraphrases, unsupported claims, and incorrect
   citations; the literal checklist cannot reliably detect these.
5. Report every category with its sample count. Treat Wilson intervals as
   indicative for small or intentionally selected test sets, not as a
   population guarantee.

Scores describe this dataset and configuration only, not universal
intelligence. Retrieval smoke tests and latency should be reported separately
from answer correctness.

The benchmark dataset may include `source_notes` for isolated runs. The current
pilot covers two general-topic Vault notes and evaluates source-grounded
retrieval, factual response, and abstention; it does not evaluate reasoning,
tool execution, or overall model intelligence. The first reviewed pilot report
is saved in `reports/pilot-2026-10-14.json`.

## Full QA case runner

`run_qa_benchmark.py` reads the QA cases in
`Catatan penting/benchmark-pertanyaan-akurasi-carl-ai.md`, including areas A–G
and sections 7.1–7.8. It is a separate runner from `evaluate_answers.py`:

```powershell
python run_qa_benchmark.py
python run_qa_benchmark.py --scaffold evaluation/qa_scenarios.json
```

The scaffold is intentionally **not ready to run**. Review each case's expected
behavior, replace prompt placeholders, add synthetic `fixture_notes` when a
case needs Vault content, and add explicit per-turn checks. Set its `status` to
`ready` only after that review. Deterministic checks can inspect required or
forbidden phrases, citations, abstention markers, regular expressions, response
length, fixture file contents, expected changed paths, and selected intents.
Use `manual_review` checks for semantic expectations; they remain
`NEEDS_REVIEW`, not automatic passes.

Inspect a manifest without running Carl:

```powershell
python run_qa_benchmark.py --manifest evaluation/qa_scenarios.json
```

After review, authorize model inference explicitly:

```powershell
python run_qa_benchmark.py --manifest evaluation/qa_scenarios.json `
  --run --confirm-local-model --output evaluation/reports/full-qa.json
```

Live chat cases use a temporary Vault and Qdrant database, and restore the
project's configured paths after the run. Fixture changes are discarded. The
runner does not access a production Vault. Network cases are blocked unless
`--allow-network` is explicitly passed. API/UI cases are reported as `BLOCKED`
until a dedicated API/UI adapter is added; latency is recorded, but resource
load checks are not currently collected. Literal assertions cannot establish
semantic correctness, source support, or overall intelligence; review those
results manually. Do not include private Vault data in manifests unless the
local environment is approved for it.
