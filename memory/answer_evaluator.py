"""Evaluate Carl answers against a manually reviewed, explicit fact checklist."""

import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

ABSTENTION_MARKERS = (
    "tidak ditemukan",
    "tidak tersedia",
    "tidak disebutkan",
    "tidak tercantum",
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
    category = case.get("category", "uncategorized")
    if not isinstance(category, str) or not category.strip():
        raise ValueError(f"Benchmark case {case_id} has invalid 'category'.")

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
    case["category"] = category.strip()
    return case


def load_answer_benchmark(dataset_path: str) -> List[Dict[str, Any]]:
    """Load and validate cases from a human-reviewed JSON benchmark."""
    path = Path(dataset_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Benchmark root must be an object.")
    if data.get("schema_version") != 1:
        raise ValueError("Benchmark must use schema_version 1.")
    review_status = data.get("review_status")
    if review_status not in (None, "approved"):
        raise ValueError(
            "Benchmark is not approved for scoring; review the draft cases first."
        )
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Benchmark must contain a 'cases' list.")

    seen_ids: set[str] = set()
    return [
        _validate_case(case, index, seen_ids)
        for index, case in enumerate(cases)
    ]


def _wilson_interval(successes: int, trials: int) -> List[float] | None:
    """Return a two-sided 95% Wilson interval for a binomial proportion."""
    if trials == 0:
        return None

    z = 1.96
    proportion = successes / trials
    denominator = 1 + z**2 / trials
    center = (proportion + z**2 / (2 * trials)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / trials
            + z**2 / (4 * trials**2)
        )
        / denominator
    )
    return [round(max(0.0, center - margin), 3), round(min(1.0, center + margin), 3)]


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
            "answer_accuracy_ci95": None,
            "answerable_accuracy": None,
            "answerable_accuracy_ci95": None,
            "answerable_fact_accuracy": None,
            "answerable_fact_accuracy_ci95": None,
            "category_results": {},
        }

    fact_checks = 0
    fact_matches = 0
    citation_checks = 0
    citation_matches = 0
    unanswerable_checks = 0
    correct_abstentions = 0
    answerable_passes = 0
    answerable_fact_passes = 0
    case_passes = 0
    case_results = []
    category_counts: Dict[str, Dict[str, int]] = {}

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
            facts_passed = not abstained and not missing_facts
            answerable_fact_passes += int(facts_passed)
            passed = facts_passed and cited
            answerable_passes += int(passed)
        else:
            unanswerable_checks += 1
            correct_abstentions += int(abstained)
            facts_passed = None
            passed = abstained

        case_passes += int(passed)
        category = case["category"]
        counts = category_counts.setdefault(category, {"passed": 0, "total": 0})
        counts["passed"] += int(passed)
        counts["total"] += 1
        case_results.append({
            "id": case["id"],
            "category": category,
            "passed": passed,
            "abstained": abstained,
            "facts_passed": facts_passed,
            "missing_facts": missing_facts,
            "missing_sources": missing_sources,
        })

    answer_accuracy = case_passes / len(cases)
    category_results = {
        category: {
            "samples_tested": counts["total"],
            "passed": counts["passed"],
            "answer_accuracy": round(counts["passed"] / counts["total"], 3),
            "answer_accuracy_ci95": _wilson_interval(
                counts["passed"], counts["total"]
            ),
        }
        for category, counts in sorted(category_counts.items())
    }

    return {
        "status": "success",
        "metric_scope": "human_reviewed_answer_checklist",
        "samples_tested": len(cases),
        "answer_accuracy": round(answer_accuracy, 3),
        "answer_accuracy_ci95": _wilson_interval(case_passes, len(cases)),
        "answerable_samples_tested": len(cases) - unanswerable_checks,
        "answerable_accuracy": (
            round(answerable_passes / (len(cases) - unanswerable_checks), 3)
            if len(cases) > unanswerable_checks else None
        ),
        "answerable_accuracy_ci95": _wilson_interval(
            answerable_passes, len(cases) - unanswerable_checks
        ),
        "answerable_fact_accuracy": (
            round(answerable_fact_passes / (len(cases) - unanswerable_checks), 3)
            if len(cases) > unanswerable_checks else None
        ),
        "answerable_fact_accuracy_ci95": _wilson_interval(
            answerable_fact_passes, len(cases) - unanswerable_checks
        ),
        "unanswerable_samples_tested": unanswerable_checks,
        "fact_coverage": round(fact_matches / fact_checks, 3) if fact_checks else None,
        "citation_rate": (
            round(citation_matches / citation_checks, 3) if citation_checks else None
        ),
        "abstention_rate": (
            round(correct_abstentions / unanswerable_checks, 3)
            if unanswerable_checks else None
        ),
        "category_results": category_results,
        "cases": case_results,
        "evaluation_note": (
            "Checklist literal terhadap fakta dan sumber yang ditinjau manusia; "
            "bukan semantic judge dan hasilnya bergantung pada cakupan dataset. "
            "Interval Wilson 95% mengasumsikan sampel binomial yang independen; "
            "pada dataset kecil atau terpilih, interval hanya indikatif."
        ),
    }
