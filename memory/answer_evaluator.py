"""Evaluate Carl answers against a manually reviewed, explicit fact checklist."""

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

ABSTENTION_MARKERS = (
    "tidak ditemukan",
    "belum tercatat",
    "tidak ada informasi",
    "tidak memiliki informasi",
    "tidak dapat memastikan",
)


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold(), flags=re.UNICODE))


def _validate_string_list(case_id: str, value: Any, field_name: str) -> List[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"Benchmark case {case_id} has invalid '{field_name}'.")
    return value


def _validate_case(case: Any, index: int, seen_ids: set[str]) -> Dict[str, Any]:
    if not isinstance(case, dict):
        raise ValueError(f"Benchmark case {index} must be an object.")
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
        raise ValueError(f"Benchmark case {index} must have a unique, non-empty id.")
    seen_ids.add(case_id)
    if not isinstance(case.get("query"), str) or not case["query"].strip():
        raise ValueError(f"Benchmark case {case_id} must have a non-empty query.")
    if not isinstance(case.get("answerable"), bool):
        raise ValueError(f"Benchmark case {case_id} must define boolean 'answerable'.")

    required_facts = _validate_string_list(
        case_id, case.get("required_facts", []), "required_facts"
    )
    expected_sources = _validate_string_list(
        case_id, case.get("expected_sources", []), "expected_sources"
    )
    if case["answerable"] and (not required_facts or not expected_sources):
        raise ValueError(
            f"Answerable case {case_id} needs required_facts and expected_sources."
        )
    if not case["answerable"] and (required_facts or expected_sources):
        raise ValueError(
            f"Unanswerable case {case_id} must have empty facts and sources."
        )
    return case


def load_answer_benchmark(dataset_path: str) -> List[Dict[str, Any]]:
    """Load and validate cases from a human-reviewed JSON benchmark."""
    path = Path(dataset_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Benchmark must contain a 'cases' list.")

    seen_ids: set[str] = set()
    return [
        _validate_case(case, index, seen_ids)
        for index, case in enumerate(cases)
    ]


def evaluate_answer_benchmark(
    answer_fn: Callable[[str], str],
    dataset_path: str,
) -> Dict[str, Any]:
    """Score answer facts, citations, and abstentions against reviewed cases.

    Fact and citation checks are literal normalized phrase checks. This is a
    transparent checklist metric, not a semantic judge or a universal accuracy
    score; benchmark cases must be authored and reviewed by a human.
    """
    cases = load_answer_benchmark(dataset_path)
    if not cases:
        return {
            "status": "warning",
            "message": "Dataset benchmark jawaban kosong; belum ada skor yang dapat dihitung.",
            "samples_tested": 0,
            "answer_accuracy": None,
            "fact_coverage": None,
            "citation_rate": None,
            "abstention_rate": None,
        }

    fact_checks = 0
    fact_matches = 0
    citation_checks = 0
    citation_matches = 0
    unanswerable_checks = 0
    correct_abstentions = 0
    case_passes = 0
    case_results = []

    for case in cases:
        answer = answer_fn(case["query"])
        normalized_answer = _normalize(answer)
        abstained = any(_normalize(marker) in normalized_answer for marker in ABSTENTION_MARKERS)

        missing_facts = []
        missing_sources = []
        if case["answerable"]:
            matched_facts = [
                fact for fact in case["required_facts"]
                if _normalize(fact) in normalized_answer
            ]
            missing_facts = [
                fact for fact in case["required_facts"]
                if _normalize(fact) not in normalized_answer
            ]
            fact_checks += len(case["required_facts"])
            fact_matches += len(matched_facts)

            expected_sources = [_normalize(source) for source in case["expected_sources"]]
            cited = any(source in normalized_answer for source in expected_sources)
            citation_checks += 1
            citation_matches += int(cited)
            if not cited:
                missing_sources = case["expected_sources"]
            passed = not abstained and not missing_facts and cited
        else:
            unanswerable_checks += 1
            correct_abstentions += int(abstained)
            passed = abstained

        case_passes += int(passed)
        case_results.append({
            "id": case["id"],
            "passed": passed,
            "abstained": abstained,
            "missing_facts": missing_facts,
            "missing_sources": missing_sources,
        })

    return {
        "status": "success",
        "metric_scope": "human_reviewed_answer_checklist",
        "samples_tested": len(cases),
        "answer_accuracy": round(case_passes / len(cases), 3),
        "fact_coverage": round(fact_matches / fact_checks, 3) if fact_checks else None,
        "citation_rate": (
            round(citation_matches / citation_checks, 3) if citation_checks else None
        ),
        "abstention_rate": (
            round(correct_abstentions / unanswerable_checks, 3)
            if unanswerable_checks else None
        ),
        "cases": case_results,
        "evaluation_note": (
            "Checklist literal terhadap fakta dan sumber yang ditinjau manusia; "
            "bukan semantic judge dan hasilnya bergantung pada cakupan dataset."
        ),
    }
