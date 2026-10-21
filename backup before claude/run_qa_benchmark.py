"""Safely plan or run Carl QA cases against a temporary, isolated Vault."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_PLAN = PROJECT_ROOT / "Catatan penting" / "benchmark-pertanyaan-akurasi-carl-ai.md"
DEFAULT_MANIFEST = PROJECT_ROOT / "evaluation" / "qa_scenarios.json"
ABSTENTION_MARKERS = (
    "tidak ditemukan",
    "tidak tersedia",
    "tidak disebutkan",
    "tidak tercantum",
    "belum tercatat",
    "tidak ada informasi",
    "tidak dapat memastikan",
    "belum bisa menjawab",
)
PLACEHOLDER_PATTERN = re.compile(r"\[[^\]]+\]")
CASE_ID_PATTERN = re.compile(r"(?:[A-G]\d+|R\d+|L\d+|M\d+|S\d+|T\d+|FMT\d+|API\d+|PERF\d+)")


def _plain_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return text.strip()


def parse_qa_catalog(markdown_path: Path = DEFAULT_PLAN) -> list[dict[str, str]]:
    """Read case IDs, prompts, and criteria from the existing QA document."""
    cases: list[dict[str, str]] = []
    area = "uncategorized"
    heading_pattern = re.compile(r"^###\s+(.+)$")

    for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
        heading = heading_pattern.match(raw_line)
        if heading:
            text = heading.group(1).strip()
            section = re.match(r"([A-G])\s*[.—-]", text)
            subsection = re.match(r"(7\.\d+)\b", text)
            if section:
                area = section.group(1)
            elif subsection:
                area = subsection.group(1)
            continue

        if not raw_line.lstrip().startswith("|"):
            continue
        columns = [cell.strip() for cell in raw_line.strip().strip("|").split("|")]
        if len(columns) < 3 or not CASE_ID_PATTERN.fullmatch(columns[0]):
            continue
        cases.append({
            "id": columns[0],
            "area": area,
            "prompt": _plain_markdown(columns[1]),
            "criteria": _plain_markdown(columns[2]),
        })
    return cases


def make_scaffold(catalog: list[dict[str, str]]) -> dict[str, Any]:
    """Create a manifest requiring reviewed fixtures and explicit assertions."""
    return {
        "schema_version": 1,
        "description": (
            "Fill fixture_notes and per-turn checks only after reviewing the "
            "expected facts/behavior. Use synthetic data, not the production Vault."
        ),
        "cases": [
            {
                **case,
                "status": "needs_oracle",
                "fixture_notes": {},
                "turns": [{"query": case["prompt"], "checks": []}],
                "file_checks": [],
                "requires_network": False,
            }
            for case in catalog
        ],
    }


def _safe_fixture_path(root: Path, relative: str) -> Path:
    """Resolve a fixture path while rejecting absolute paths and traversal."""
    candidate = PurePosixPath(relative.replace("\\", "/"))
    windows_candidate = PureWindowsPath(relative)
    if (
        candidate.is_absolute()
        or windows_candidate.is_absolute()
        or windows_candidate.drive
        or not candidate.parts
        or ".." in candidate.parts
    ):
        raise ValueError(f"Unsafe fixture-relative path: {relative!r}")
    root_resolved = root.resolve()
    target = (root_resolved / Path(*candidate.parts)).resolve()
    if not target.is_relative_to(root_resolved):
        raise ValueError(f"Fixture path escapes its root: {relative!r}")
    return target


def validate_manifest(
    manifest: Any,
    catalog: list[dict[str, str]],
) -> list[str]:
    """Return actionable manifest validation errors without running any models."""
    errors: list[str] = []
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return ["Manifest root must be an object with schema_version=1."]
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        return ["Manifest must contain a cases list."]

    known_ids = {case["id"] for case in catalog}
    seen: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            errors.append("Every manifest case must be an object.")
            continue
        case_id = item.get("id")
        if not isinstance(case_id, str) or case_id not in known_ids:
            errors.append(f"Unknown QA case id: {case_id!r}.")
            continue
        if case_id in seen:
            errors.append(f"Duplicate QA case id: {case_id}.")
        seen.add(case_id)
        turns = item.get("turns")
        if not isinstance(turns, list) or not turns:
            errors.append(f"{case_id}: turns must be a non-empty list.")
            continue
        for index, turn in enumerate(turns, 1):
            if not isinstance(turn, dict) or not isinstance(turn.get("query"), str):
                errors.append(f"{case_id}: turn {index} needs a query string.")
                continue
            if not turn["query"].strip():
                errors.append(f"{case_id}: turn {index} query is empty.")
            if item.get("status", "ready") == "ready" and PLACEHOLDER_PATTERN.search(turn["query"]):
                errors.append(f"{case_id}: turn {index} still contains a placeholder.")
            checks = turn.get("checks")
            if isinstance(checks, dict):
                if not checks and item.get("status") != "needs_oracle":
                    errors.append(f"{case_id}: turn {index} needs explicit checks.")
                elif any(not isinstance(name, str) for name in checks):
                    errors.append(f"{case_id}: turn {index} check names must be strings.")
            elif isinstance(checks, list):
                if not checks and item.get("status") != "needs_oracle":
                    errors.append(f"{case_id}: turn {index} needs explicit checks.")
                elif any(not isinstance(check, dict) for check in checks):
                    errors.append(f"{case_id}: turn {index} checks must be objects.")
            else:
                errors.append(f"{case_id}: turn {index} checks must be an object or list.")
        notes = item.get("fixture_notes", {})
        if not isinstance(notes, dict):
            errors.append(f"{case_id}: fixture_notes must map relative paths to text.")
        else:
            for path, content in notes.items():
                if not isinstance(path, str) or not isinstance(content, str):
                    errors.append(f"{case_id}: fixture note paths/content must be strings.")
                else:
                    try:
                        _safe_fixture_path(Path(tempfile.gettempdir()) / "qa-validation", path)
                    except ValueError as error:
                        errors.append(f"{case_id}: {error}")
        if item.get("requires_network") is not None and not isinstance(item.get("requires_network"), bool):
            errors.append(f"{case_id}: requires_network must be boolean.")
        if not isinstance(item.get("requires_vault", False), bool):
            errors.append(f"{case_id}: requires_vault must be boolean.")
        file_checks = item.get("file_checks", [])
        if not isinstance(file_checks, list) or any(not isinstance(check, dict) for check in file_checks):
            errors.append(f"{case_id}: file_checks must be a list of objects.")
        else:
            for check in file_checks:
                if not isinstance(check.get("path"), str):
                    errors.append(f"{case_id}: every file check needs a relative path.")
                    continue
                try:
                    _safe_fixture_path(Path(tempfile.gettempdir()) / "qa-validation", check["path"])
                except ValueError as error:
                    errors.append(f"{case_id}: {error}")
                if not isinstance(check.get("exists", True), bool):
                    errors.append(f"{case_id}: file check exists must be boolean.")
                for key in ("equals", "contains", "not_contains"):
                    if key in check and not isinstance(check[key], str):
                        errors.append(f"{case_id}: file check {key} must be a string.")
        changed_paths = item.get("expected_changed_paths")
        if changed_paths is not None and (
            not isinstance(changed_paths, list)
            or any(not isinstance(path, str) for path in changed_paths)
        ):
            errors.append(f"{case_id}: expected_changed_paths must be a list of relative paths.")
        expected_intents = item.get("expected_intents")
        if expected_intents is not None and (
            not isinstance(expected_intents, list)
            or any(not isinstance(intent, str) for intent in expected_intents)
        ):
            errors.append(f"{case_id}: expected_intents must be a list of strings.")
        if item.get("execution", "chat") not in {"chat", "api"}:
            errors.append(f"{case_id}: execution must be 'chat' or 'api'.")
        if item.get("status", "ready") not in {"ready", "needs_oracle"}:
            errors.append(f"{case_id}: status must be 'ready' or 'needs_oracle'.")
        if item.get("status", "ready") == "needs_oracle" and any(
            turn.get("checks") for turn in turns if isinstance(turn, dict)
        ):
            errors.append(f"{case_id}: remove draft checks or mark the case ready after review.")
    return errors


def evaluate_text_checks(answer: str, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate deterministic answer checks; semantic review remains separate."""
    results: list[dict[str, Any]] = []
    folded = answer.casefold()
    for check in checks:
        kind = check.get("type")
        values = check.get("values", [])
        if kind in {"contains_all", "contains_any", "contains_none", "citations"}:
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                results.append({"type": kind, "passed": False, "detail": "values must be strings"})
                continue
            matches = [value for value in values if value.casefold() in folded]
            if kind == "contains_all":
                passed = len(matches) == len(values)
            elif kind == "contains_any":
                passed = bool(matches)
            elif kind == "contains_none":
                passed = not matches
            else:
                cited = {
                    Path(value).name.casefold()
                    for value in re.findall(r"\[Sumber:\s*([^\]]+)\]", answer, re.IGNORECASE)
                }
                expected = {Path(value).name.casefold() for value in values}
                matches = sorted(cited.intersection(expected))
                passed = bool(matches)
            results.append({
                "type": kind,
                "passed": passed,
                "matched": matches,
                "expected": values,
            })
        elif kind == "abstains":
            expected = check.get("value", True)
            actual = any(marker in folded for marker in ABSTENTION_MARKERS)
            results.append({
                "type": kind,
                "passed": actual is expected,
                "expected": expected,
                "actual": actual,
            })
        elif kind == "source_citation_present":
            matches = re.findall(r"\[Sumber:\s*([^\]]+)\]", answer, re.IGNORECASE)
            results.append({
                "type": kind,
                "passed": bool(matches),
                "matched": matches,
            })
        elif kind == "number_present":
            expected = re.sub(r"\D", "", str(check.get("value", "")))
            actual = [
                re.sub(r"\D", "", value)
                for value in re.findall(r"\d[\d.,]*", answer)
            ]
            results.append({
                "type": kind,
                "passed": bool(expected) and expected in actual,
                "expected": str(check.get("value", "")),
                "matched": actual,
            })
        elif kind in {"markdown_table", "fenced_code", "exact_bullets", "max_bullets", "single_sentence"}:
            if kind == "markdown_table":
                actual = bool(re.search(r"(?m)^\s*\|.*\|\s*$", answer))
                expected: Any = True
            elif kind == "fenced_code":
                actual = answer.count("```") >= 2
                expected = True
            elif kind in {"exact_bullets", "max_bullets"}:
                count = len(re.findall(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", answer))
                limit = check.get("value")
                actual = count == limit if kind == "exact_bullets" else count <= limit
                expected = limit
            else:
                sentences = [
                    part for part in re.split(r"(?<=[.!?])\s+", answer.strip())
                    if part.strip()
                ]
                actual = len(sentences) <= 1
                expected = 1
            results.append({
                "type": kind,
                "passed": actual,
                "expected": expected,
                "actual": count if kind in {"exact_bullets", "max_bullets"} else actual,
            })
        elif kind in {"regex_all", "regex_none"}:
            patterns = check.get("values", [])
            try:
                matches = [pattern for pattern in patterns if re.search(pattern, answer, re.IGNORECASE)]
            except (re.error, TypeError) as error:
                results.append({"type": kind, "passed": False, "detail": str(error)})
                continue
            passed = len(matches) == len(patterns) if kind == "regex_all" else not matches
            results.append({
                "type": kind,
                "passed": passed,
                "matched": matches,
                "expected": patterns,
            })
        elif kind == "max_words":
            limit = check.get("value")
            count = len(re.findall(r"\S+", answer))
            passed = isinstance(limit, int) and count <= limit
            results.append({"type": kind, "passed": passed, "words": count, "limit": limit})
        elif kind == "max_bullets":
            limit = check.get("value")
            count = len(re.findall(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", answer))
            passed = isinstance(limit, int) and count <= limit
            results.append({"type": kind, "passed": passed, "bullets": count, "limit": limit})
        elif kind == "manual_review":
            results.append({
                "type": kind,
                "passed": None,
                "reason": str(check.get("reason", "Requires human semantic review.")),
            })
        else:
            results.append({"type": str(kind), "passed": False, "detail": "unknown check type"})
    return results


def normalize_manifest_checks(checks: Any) -> list[dict[str, Any]]:
    """Translate named QA expectations into objective checks or human review."""
    if isinstance(checks, list):
        return checks
    if not isinstance(checks, dict):
        return []

    normalized: list[dict[str, Any]] = []
    for name, expected in checks.items():
        if name == "expected_keywords" and isinstance(expected, list):
            normalized.append({"type": "contains_all", "values": expected})
        elif name == "contains_source_citation" and expected is True:
            normalized.append({"type": "source_citation_present"})
        elif name in {"correct_calculation", "correct_math_result"} and isinstance(expected, (str, int, float)):
            normalized.append({"type": "number_present", "value": expected})
        elif name in {"contains_markdown_table", "correct_table_columns"} and expected is True:
            normalized.append({"type": "markdown_table"})
        elif name in {"contains_fenced_code_block", "fenced_code_block_present"} and expected is True:
            normalized.append({"type": "fenced_code"})
        elif name == "exact_three_bullet_points" and expected is True:
            normalized.append({"type": "exact_bullets", "value": 3})
        elif name == "max_five_bullet_points" and expected is True:
            normalized.append({"type": "max_bullets", "value": 5})
        elif name == "single_sentence_response" and expected is True:
            normalized.append({"type": "single_sentence"})
        else:
            normalized.append({
                "type": "manual_review",
                "reason": f"Review assertion '{name}' against its expected value {expected!r}.",
            })
    return normalized


def _case_requires_unavailable_adapter(case: dict[str, Any]) -> str | None:
    """Keep API/UI and resource assertions from being misrun as ordinary chat."""
    check_names = {
        name
        for turn in case.get("turns", [])
        for name in (
            turn.get("checks", {}).keys()
            if isinstance(turn.get("checks"), dict)
            else (
                check.get("type")
                for check in turn.get("checks", [])
                if isinstance(check, dict)
            )
        )
    }
    if check_names.intersection({
        "job_completed_successfully",
        "streaming_response_intact",
        "consistent_failure_status_no_leak",
        "session_isolation_verified",
    }):
        return "API/UI assertion requires the API and streaming test adapter."
    if any(name.startswith("perf_") for name in check_names):
        return "Resource/performance assertion requires the dedicated measurement adapter."
    return None


def evaluate_file_checks(root: Path, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check post-run fixture files without allowing paths outside the fixture."""
    results = []
    for check in checks:
        relative = check.get("path")
        try:
            if not isinstance(relative, str):
                raise ValueError("path must be a string")
            path = _safe_fixture_path(root, relative)
            exists = path.is_file()
            expected_exists = check.get("exists", True)
            passed = exists is expected_exists
            content = path.read_text(encoding="utf-8") if exists else ""
            if exists and "equals" in check:
                passed = passed and content == check["equals"]
            if exists and "contains" in check:
                passed = passed and check["contains"] in content
            if exists and "not_contains" in check:
                passed = passed and check["not_contains"] not in content
            results.append({"path": relative, "passed": passed, "exists": exists})
        except (OSError, ValueError) as error:
            results.append({"path": str(relative), "passed": False, "detail": str(error)})
    return results


def _write_fixture_notes(root: Path, notes: dict[str, str]) -> None:
    for relative, content in notes.items():
        path = _safe_fixture_path(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _fixture_snapshot(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def run_live_manifest(manifest: dict[str, Any], catalog: list[dict[str, str]], allow_network: bool) -> dict[str, Any]:
    """Run reviewed cases with local models using only temporary Vault/DB state."""
    catalog_by_id = {case["id"]: case for case in catalog}
    not_ready = [
        case for case in manifest["cases"]
        if case.get("status", "ready") != "ready"
        or case.get("execution", "chat") != "chat"
        or (case.get("requires_network") and not allow_network)
        or (case.get("requires_vault", False) and not case.get("fixture_notes"))
        or _case_requires_unavailable_adapter(case) is not None
    ]
    if len(not_ready) == len(manifest["cases"]):
        blocked_cases = []
        for case in manifest["cases"]:
            entry = catalog_by_id[case["id"]]
            if case.get("status", "ready") != "ready":
                reason = "Reviewed expected facts/behavior and explicit checks are not filled in."
            elif case.get("execution", "chat") != "chat":
                reason = "API/UI execution requires the separate local API test adapter."
            elif case.get("requires_network") and not allow_network:
                reason = "network access not enabled"
            elif _case_requires_unavailable_adapter(case):
                reason = _case_requires_unavailable_adapter(case)
            else:
                reason = "Vault case needs isolated fixture notes"
            blocked_cases.append({
                "id": case["id"],
                "area": entry["area"],
                "status": "BLOCKED",
                "reason": reason,
            })
        return {
            "status": "completed",
            "cases": blocked_cases,
            "summary": _summarize(blocked_cases),
            "limitations": ["No model was loaded because there were no runnable cases."],
        }

    original_vault: str | None = None
    original_db: str | None = None
    original_history: str | None = None
    original_profile: str | None = None
    original_rules: str | None = None
    case_results: list[dict[str, Any]] = []

    try:
        import config
        from agents import AITeam, AgentRouter
        from memory.manager import MemoryManager
        import memory.session_memory as session_memory
        import memory.user_profile as user_profile
        import memory.rules_engine as rules_engine

        original_vault, original_db = config.VAULT_PATH, config.DB_PATH
        original_history = session_memory.HISTORY_FILE
        original_profile = user_profile.PROFILE_FILE
        original_rules = rules_engine.RULES_FILE
        with tempfile.TemporaryDirectory(prefix="carl-qa-isolated-") as temp:
            root = Path(temp)
            for case in manifest["cases"]:
                case_id = case["id"]
                catalog_entry = catalog_by_id[case_id]
                if case.get("status", "ready") != "ready":
                    case_results.append({
                        "id": case_id,
                        "area": catalog_entry["area"],
                        "status": "BLOCKED",
                        "reason": "Reviewed expected facts/behavior and explicit checks are not filled in.",
                    })
                    continue
                if case.get("execution", "chat") != "chat":
                    case_results.append({
                        "id": case_id,
                        "area": catalog_entry["area"],
                        "status": "BLOCKED",
                        "reason": "API/UI execution requires the separate local API test adapter.",
                    })
                    continue
                if case.get("requires_network") and not allow_network:
                    case_results.append({"id": case_id, "status": "BLOCKED", "reason": "network access not enabled"})
                    continue
                unavailable_adapter = _case_requires_unavailable_adapter(case)
                if unavailable_adapter:
                    case_results.append({
                        "id": case_id,
                        "area": catalog_entry["area"],
                        "status": "BLOCKED",
                        "reason": unavailable_adapter,
                    })
                    continue
                if not case.get("fixture_notes") and case.get("requires_vault", False):
                    case_results.append({"id": case_id, "status": "BLOCKED", "reason": "Vault case needs isolated fixture notes"})
                    continue

                case_root = root / "cases" / case_id
                vault, db = case_root / "vault", case_root / "qdrant"
                vault.mkdir(parents=True)
                db.mkdir(parents=True)
                config.VAULT_PATH, config.DB_PATH = str(vault), str(db)
                session_memory.HISTORY_FILE = str(case_root / "session_history.json")
                user_profile.PROFILE_FILE = str(db / "profile.json")
                rules_engine.RULES_FILE = str(db / "rules.json")
                _write_fixture_notes(vault, case.get("fixture_notes", {}))
                memory = None
                if case.get("fixture_notes"):
                    memory = MemoryManager()
                    memory.index_vault(silent=True)
                team = AITeam(memory, user_name="QA")
                router = AgentRouter(team)
                selected_intents: list[str] = []
                original_route = router._route_by_intent

                def record_route(intent: str, raw: str, _route=original_route, _selected=selected_intents):
                    _selected.append(intent)
                    return _route(intent, raw)

                router._route_by_intent = record_route

                turns_result = []
                case_started = time.perf_counter()
                files_before = _fixture_snapshot(vault)
                for turn in case["turns"]:
                    start = time.perf_counter()
                    answer = router.route_and_execute(turn["query"])
                    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                    checks = evaluate_text_checks(
                        answer,
                        normalize_manifest_checks(turn["checks"]),
                    )
                    turns_result.append({
                        "checks": checks,
                        "status": _checks_status(checks),
                        "latency_ms": elapsed_ms,
                        **({"answer": answer} if manifest.get("include_answers") else {}),
                    })
                file_results = evaluate_file_checks(vault, case.get("file_checks", []))
                changed_paths = sorted(_fixture_snapshot(vault) ^ files_before)
                if "expected_changed_paths" in case:
                    expected = sorted(case["expected_changed_paths"])
                    file_results.append({
                        "type": "changed_paths",
                        "passed": changed_paths == expected,
                        "actual": changed_paths,
                        "expected": expected,
                    })
                expected_intents = case.get("expected_intents")
                if expected_intents is not None:
                    file_results.append({
                        "type": "selected_intents",
                        "passed": selected_intents == expected_intents,
                        "actual": selected_intents,
                        "expected": expected_intents,
                    })
                overall = _checks_status([
                    result
                    for turn in turns_result
                    for result in turn["checks"]
                ] + file_results)
                case_results.append({
                    "id": case_id,
                    "area": catalog_entry["area"],
                    "status": overall,
                    "turns": turns_result,
                    "file_checks": file_results,
                    "changed_paths": changed_paths,
                    "selected_intents": selected_intents.copy(),
                    "elapsed_ms": round((time.perf_counter() - case_started) * 1000, 2),
                })
                if memory and memory.store.client:
                    memory.store.client.close()
    except Exception as error:
        return {
            "status": "ERROR",
            "error": f"{type(error).__name__}: {error}",
            "cases": case_results,
        }
    finally:
        if original_vault is not None and original_db is not None:
            config.VAULT_PATH, config.DB_PATH = original_vault, original_db
        if original_history is not None:
            session_memory.HISTORY_FILE = original_history
        if original_profile is not None:
            user_profile.PROFILE_FILE = original_profile
        if original_rules is not None:
            rules_engine.RULES_FILE = original_rules

    return {
        "status": "completed",
        "cases": case_results,
        "summary": _summarize(case_results),
        "limitations": [
            "Literal and structural assertions do not establish semantic correctness.",
            "Cases with manual_review checks require human review.",
            "Each run uses a temporary Vault and Qdrant directory; fixture changes are discarded.",
        ],
    }


def _checks_status(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "BLOCKED"
    if any(check.get("passed") is False for check in checks):
        return "FAIL"
    if any(check.get("passed") is None for check in checks):
        return "NEEDS_REVIEW"
    return "PASS"


def _summarize(cases: list[dict[str, Any]]) -> dict[str, int]:
    statuses = ("PASS", "FAIL", "NEEDS_REVIEW", "BLOCKED")
    return {
        "total": len(cases),
        **{status.lower(): sum(case.get("status") == status for case in cases) for status in statuses},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN, help="QA Markdown source document.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Reviewed JSON test manifest.")
    parser.add_argument("--scaffold", type=Path, help="Write an editable manifest for every documented case.")
    parser.add_argument("--run", action="store_true", help="Run cases using local models in an isolated temporary Vault.")
    parser.add_argument("--confirm-local-model", action="store_true", help="Explicitly authorize local model inference.")
    parser.add_argument("--allow-network", action="store_true", help="Allow manifest cases marked requires_network.")
    parser.add_argument("--output", type=Path, help="Write the report JSON to this path.")
    parser.add_argument("--include-answers", action="store_true", help="Include model responses in the report; responses may contain private fixture data.")
    args = parser.parse_args(argv)

    try:
        catalog = parse_qa_catalog(args.plan)
    except (OSError, UnicodeError) as error:
        print(f"Cannot read QA plan: {error}", file=sys.stderr)
        return 2
    if not catalog:
        print("No QA cases were found in the source document.", file=sys.stderr)
        return 2

    if args.scaffold:
        scaffold = make_scaffold(catalog)
        args.scaffold.parent.mkdir(parents=True, exist_ok=True)
        args.scaffold.write_text(json.dumps(scaffold, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(catalog)} case scaffold entries to {args.scaffold}")
        return 0

    if not args.manifest.exists():
        scaffold = make_scaffold(catalog)
        print(json.dumps({
            "status": "PLAN_ONLY",
            "catalog_cases": len(catalog),
            "areas": _area_counts(catalog),
            "manifest_missing": str(args.manifest),
            "next_step": "Create a reviewed manifest with --scaffold; no models or Vault were accessed.",
        }, ensure_ascii=False, indent=2))
        return 0

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Cannot read manifest: {error}", file=sys.stderr)
        return 2
    errors = validate_manifest(manifest, catalog)
    if errors:
        print(json.dumps({"status": "INVALID_MANIFEST", "errors": errors}, ensure_ascii=False, indent=2))
        return 2

    if not args.run:
        print(json.dumps({
            "status": "PLAN_ONLY",
            "catalog_cases": len(catalog),
            "manifest_cases": len(manifest["cases"]),
            "areas": _area_counts(catalog),
                "ready": sum(case.get("status", "ready") == "ready" for case in manifest["cases"]),
            "message": "No models, network, or Vault were accessed. Pass --run and --confirm-local-model to execute.",
        }, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_local_model:
        print("Live run refused: add --confirm-local-model to authorize local inference.", file=sys.stderr)
        return 2

    manifest["include_answers"] = args.include_answers
    report = run_live_manifest(manifest, catalog, args.allow_network)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Report written to {args.output}")
        print(json.dumps(
            {"status": report["status"], "summary": report.get("summary")},
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(rendered)
    return 1 if report["status"] == "ERROR" or report.get("summary", {}).get("fail", 0) else 0


def _area_counts(catalog: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in catalog:
        counts[case["area"]] = counts.get(case["area"], 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
