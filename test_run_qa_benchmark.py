import tempfile
import unittest
from pathlib import Path

import run_qa_benchmark as benchmark


class TestQaCatalog(unittest.TestCase):
    def test_catalog_includes_all_documented_areas(self):
        catalog = benchmark.parse_qa_catalog()
        areas = {case["area"] for case in catalog}
        self.assertEqual(areas, {
            "A", "B", "C", "D", "E", "F", "G",
            "7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8",
        })
        self.assertGreaterEqual(len(catalog), 60)

    def test_generated_scaffold_is_valid_but_not_runnable(self):
        catalog = benchmark.parse_qa_catalog()
        manifest = benchmark.make_scaffold(catalog)
        self.assertEqual(benchmark.validate_manifest(manifest, catalog), [])
        self.assertTrue(all(case["status"] == "needs_oracle" for case in manifest["cases"]))

    def test_ready_case_requires_explicit_checks_and_no_placeholder(self):
        catalog = [{"id": "A1", "area": "A", "prompt": "Q", "criteria": "C"}]
        manifest = {
            "schema_version": 1,
            "cases": [{
                "id": "A1",
                "status": "ready",
                "turns": [{"query": "Question [replace me]", "checks": []}],
            }],
        }
        errors = benchmark.validate_manifest(manifest, catalog)
        self.assertTrue(any("explicit checks" in error for error in errors))
        self.assertTrue(any("placeholder" in error for error in errors))


class TestFixtureSafety(unittest.TestCase):
    def test_fixture_paths_reject_traversal_and_allow_nested_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                benchmark._safe_fixture_path(root, "nested/note.md"),
                root.resolve() / "nested" / "note.md",
            )
            for unsafe in ("../outside.md", r"..\outside.md", "C:\\outside.md", "/outside.md"):
                with self.subTest(path=unsafe), self.assertRaises(ValueError):
                    benchmark._safe_fixture_path(root, unsafe)

    def test_file_checks_validate_content_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.md").write_text("approved fixture", encoding="utf-8")
            results = benchmark.evaluate_file_checks(root, [
                {"path": "note.md", "contains": "fixture"},
                {"path": "missing.md", "exists": False},
                {"path": "../escape.md"},
            ])
            self.assertEqual([result["passed"] for result in results], [True, True, False])


class TestAnswerChecks(unittest.TestCase):
    def test_named_assertions_keep_unimplemented_semantics_for_manual_review(self):
        checks = benchmark.normalize_manifest_checks({
            "contains_source_citation": True,
            "correct_calculation": "204000",
            "mention_conflict_and_both_sources": True,
        })
        results = benchmark.evaluate_text_checks(
            "Totalnya Rp204.000. [Sumber: hitung.md]",
            checks,
        )
        self.assertEqual([result["passed"] for result in results], [True, True, None])
        self.assertEqual(benchmark._checks_status(results), "NEEDS_REVIEW")

    def test_manifest_accepts_named_assertions_and_inline_fixture_notes(self):
        catalog = [{"id": "A1", "area": "A", "prompt": "Q", "criteria": "C"}]
        manifest = {
            "schema_version": 1,
            "cases": [{
                "id": "A1",
                "status": "ready",
                "fixture_notes": {"fixture.md": "Known test fact."},
                "turns": [{
                    "query": "What fact is in the fixture?",
                    "checks": {
                        "contains_source_citation": True,
                        "expected_keywords": ["fact"],
                    },
                }],
            }],
        }
        self.assertEqual(benchmark.validate_manifest(manifest, catalog), [])

    def test_text_checks_cover_citations_abstention_and_manual_review(self):
        results = benchmark.evaluate_text_checks(
            "Tidak tersedia. [Sumber: profil.md]",
            [
                {"type": "citations", "values": ["profil.md"]},
                {"type": "abstains", "value": True},
                {"type": "manual_review", "reason": "Check factual support"},
            ],
        )
        self.assertEqual([result["passed"] for result in results], [True, True, None])
        self.assertEqual(benchmark._checks_status(results), "NEEDS_REVIEW")

    def test_status_aggregation_does_not_turn_review_into_pass(self):
        self.assertEqual(benchmark._checks_status([]), "BLOCKED")
        self.assertEqual(benchmark._checks_status([{"passed": False}]), "FAIL")
        self.assertEqual(benchmark._checks_status([{"passed": None}]), "NEEDS_REVIEW")
        self.assertEqual(benchmark._checks_status([{"passed": True}]), "PASS")


class TestSafePlanning(unittest.TestCase):
    def test_unreviewed_cases_are_blocked_without_loading_carl(self):
        catalog = [{"id": "A1", "area": "A", "prompt": "Q", "criteria": "C"}]
        report = benchmark.run_live_manifest(benchmark.make_scaffold(catalog), catalog, False)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["summary"]["blocked"], 1)
        self.assertEqual(report["cases"][0]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
