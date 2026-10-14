import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from memory.answer_evaluator import evaluate_answer_benchmark
from memory.evaluator import evaluate_memory_accuracy, run_evaluation_command
from memory.hybrid_search import get_ranked_keyword_results, merge_ranked_results
from memory.manager import MemoryManager


def _doc(source: str, content: str) -> Document:
    return Document(page_content=content, metadata={"source": source})


class TestMemoryQuality(unittest.TestCase):
    def test_merge_ranked_results_deduplicates_across_queries(self):
        shared = _doc("shared.md", "shared chunk")
        original_only = _doc("original.md", "original result")
        expanded_only = _doc("expanded.md", "expanded result")

        merged = merge_ranked_results([
            [shared, original_only],
            [shared, expanded_only],
        ])

        self.assertEqual(
            [(doc.metadata["source"], doc.page_content) for doc in merged],
            [
                ("shared.md", "shared chunk"),
                ("original.md", "original result"),
                ("expanded.md", "expanded result"),
            ],
        )

    def test_rare_name_match_ranks_above_common_claim_terms(self):
        target = _doc(
            "Data Profil Orang Lain.md",
            "Alvi disebut dalam profil.",
        )
        common_term_matches = [
            _doc(
                f"Umum {index}.md",
                "Catatan ini membahas perempuan dalam konteks umum.",
            )
            for index in range(8)
        ]

        results = get_ranked_keyword_results(
            [*common_term_matches, target],
            "catatan mana yang menyebut Alvi adalah perempuan?",
        )

        self.assertEqual(results[0].metadata["source"], "Data Profil Orang Lain.md")
        self.assertIn("Alvi", results[0].page_content)

    def test_query_expansion_results_reach_formatted_context(self):
        memory = MemoryManager.__new__(MemoryManager)
        memory.needs_sync = False
        memory.all_chunks = []
        expanded_doc = _doc("expanded-target.md", "Unique expanded retrieval content")
        memory.store = type(
            "FakeStore",
            (),
            {
                "similarity_search": lambda _self, query, k: (
                    [] if query == "original query" else [expanded_doc]
                )
            },
        )()

        with (
            patch("memory.manager.expand_query", return_value=["original query", "expanded wording"]),
            patch("memory.manager.get_ranked_keyword_results", return_value=[]),
            patch("memory.manager.traverse_graph_links", return_value=[]),
        ):
            context = memory.search_context("original query", k=5)

        self.assertIn("Unique expanded retrieval content", context)
        self.assertIn("expanded-target.md", context)

    def test_explicit_note_title_match_skips_query_expansion(self):
        memory = MemoryManager.__new__(MemoryManager)
        memory.needs_sync = False
        memory.all_chunks = []
        named_note = _doc(
            "03-Resources/Pengetahuan tentang Ikan.md",
            "Catatan tentang cara ikan mengambil oksigen.",
        )
        memory.store = type(
            "FakeStore",
            (),
            {"similarity_search": staticmethod(lambda query, k: [])},
        )()

        with (
            patch("memory.manager.expand_query") as expand_query,
            patch("memory.manager.get_ranked_keyword_results", return_value=[named_note]),
            patch("memory.manager.traverse_graph_links", return_value=[]),
        ):
            context = memory.search_context(
                "Menurut catatan Pengetahuan tentang Ikan bagaimana ikan mengambil oksigen",
                k=5,
            )

        self.assertIn("Pengetahuan tentang Ikan.md", context)
        expand_query.assert_not_called()

    def test_weak_initial_retrieval_keeps_query_expansion_fallback(self):
        memory = MemoryManager.__new__(MemoryManager)
        memory.needs_sync = False
        memory.all_chunks = []
        expanded_doc = _doc("expanded-target.md", "Recovered through query expansion")
        memory.store = type(
            "FakeStore",
            (),
            {
                "similarity_search": staticmethod(
                    lambda query, k: [] if query == "unclear project query" else [expanded_doc]
                )
            },
        )()

        with (
            patch(
                "memory.manager.expand_query",
                return_value=["unclear project query", "alternate project phrasing"],
            ) as expand_query,
            patch("memory.manager.get_ranked_keyword_results", return_value=[]),
            patch("memory.manager.traverse_graph_links", return_value=[]),
        ):
            context = memory.search_context("unclear project query", k=5)

        self.assertIn("Recovered through query expansion", context)
        expand_query.assert_called_once_with("unclear project query")

    def test_expansion_failure_does_not_misreport_initial_vector_search_failure(self):
        memory = MemoryManager.__new__(MemoryManager)
        memory.needs_sync = False
        memory.all_chunks = []
        initial_doc = _doc("initial.md", "Initial semantic result")
        call_count = 0

        def similarity_search(query, k):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [initial_doc]
            raise RuntimeError("alternate query failed")

        memory.store = type(
            "FakeStore",
            (),
            {"similarity_search": staticmethod(similarity_search)},
        )()

        with (
            patch(
                "memory.manager.expand_query",
                return_value=["unclear project query", "alternate project phrasing"],
            ),
            patch("memory.manager.get_ranked_keyword_results", return_value=[]),
            patch("memory.manager.traverse_graph_links", return_value=[]),
        ):
            context = memory.search_context("unclear project query", k=5)

        self.assertIn("Initial semantic result", context)
        self.assertNotIn("Semantic retrieval is unavailable", context)

    def test_vector_failure_is_explicit_and_does_not_run_query_expansion(self):
        memory = MemoryManager.__new__(MemoryManager)
        memory.needs_sync = False
        memory.all_chunks = []

        class FailedVectorStore:
            @staticmethod
            def similarity_search(query, k):
                raise RuntimeError("backend unavailable")

        memory.store = FailedVectorStore()
        with (
            patch("memory.manager.expand_query") as expand_query,
            patch("memory.manager.get_ranked_keyword_results", return_value=[]),
            patch("memory.manager.traverse_graph_links", return_value=[]),
        ):
            context = memory.search_context("query with enough characters", k=5)

        self.assertIn("Semantic retrieval is unavailable", context)
        expand_query.assert_not_called()

    def test_qdrant_fallback_reloads_lexical_chunks_instead_of_using_stale_cache(self):
        memory = MemoryManager.__new__(MemoryManager)
        memory.store = type("UnavailableStore", (), {"client": None})()
        stale_chunk = _doc("old.md", "stale indexed content")
        fresh_chunk = _doc("fresh.md", "current vault content")
        memory.all_chunks = [stale_chunk]

        with (
            patch("memory.manager.os.path.exists", return_value=True),
            patch("memory.manager.scan_vault_mtimes", return_value={"fresh.md": 1.0}),
            patch("memory.manager.extract_all_chunks", return_value=[fresh_chunk]) as extract,
        ):
            memory.index_vault(silent=True)

        extract.assert_called_once_with(["fresh.md"])
        self.assertEqual(memory.all_chunks, [fresh_chunk])

    def test_evaluator_ranks_explicit_source_markers_only(self):
        class FakeMemory:
            all_chunks = [object()]

            @staticmethod
            def search_context(_query, k):
                return (
                    "📄 [Sumber: unrelated.md]\n"
                    "This body mentions target.md but is not the target source.\n\n"
                    "---\n\n"
                    "📄 [Sumber: target.md]\nTarget content."
                )

        dataset = [{
            "query": "target query",
            "target_stem": "target",
            "target_filename": "target.md",
            "target_path": "target.md",
        }]

        with patch("memory.evaluator.generate_synthetic_eval_dataset", return_value=dataset):
            report = evaluate_memory_accuracy(FakeMemory())

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["metric_scope"], "synthetic_retrieval")
        self.assertEqual(report["hit_rate_at_1"], 0.0)
        self.assertEqual(report["hit_rate_at_3"], 1.0)
        self.assertEqual(report["mrr"], 0.5)
        self.assertIn("bukan akurasi", report["evaluation_note"])

    def test_empty_dataset_has_no_perfect_score(self):
        with (
            patch("memory.evaluator.generate_synthetic_eval_dataset", return_value=[]),
            patch("memory.evaluator.config.VAULT_PATH", "unused"),
        ):
            report = evaluate_memory_accuracy(memory_manager=object())
            message = run_evaluation_command(memory_manager=object())

        self.assertEqual(report["status"], "warning")
        self.assertIsNone(report["composite_score"])
        self.assertIsNone(report["hit_rate_at_3"])
        self.assertIn("Belum ada catatan", message)

    def test_non_positive_sample_count_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_memory_accuracy(memory_manager=object(), max_samples=0)

    def test_answer_benchmark_checks_facts_sources_and_abstention(self):
        import json
        import tempfile
        from pathlib import Path

        benchmark = {
            "schema_version": 1,
            "cases": [
                {
                    "id": "answerable",
                    "query": "What is the documented result?",
                    "answerable": True,
                    "category": "factuality",
                    "required_facts": ["Result is 42"],
                    "expected_sources": ["result.md"],
                },
                {
                    "id": "unanswerable",
                    "query": "What is the private key?",
                    "answerable": False,
                    "category": "abstention",
                    "required_facts": [],
                    "expected_sources": [],
                },
            ],
        }
        answers = {
            "What is the documented result?": "Result is 42. [Sumber: result.md]",
            "What is the private key?": "Informasi itu tidak tersedia dalam catatan.",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(json.dumps(benchmark), encoding="utf-8")
            report = evaluate_answer_benchmark(answers.__getitem__, str(path))

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["metric_scope"], "human_reviewed_answer_checklist")
        self.assertEqual(report["answer_accuracy"], 1.0)
        self.assertEqual(report["fact_coverage"], 1.0)
        self.assertEqual(report["citation_rate"], 1.0)
        self.assertEqual(report["abstention_rate"], 1.0)
        self.assertEqual(report["answer_accuracy_ci95"], [0.342, 1.0])
        self.assertEqual(report["answerable_accuracy"], 1.0)
        self.assertEqual(report["answerable_accuracy_ci95"], [0.207, 1.0])
        self.assertEqual(report["answerable_fact_accuracy"], 1.0)
        self.assertEqual(report["answerable_fact_accuracy_ci95"], [0.207, 1.0])
        self.assertEqual(report["answerable_samples_tested"], 1)
        self.assertEqual(report["unanswerable_samples_tested"], 1)
        self.assertEqual(report["category_results"]["factuality"]["samples_tested"], 1)
        self.assertEqual(report["category_results"]["abstention"]["passed"], 1)

    def test_answer_benchmark_rejects_unsupported_schema_version(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(
                json.dumps({"schema_version": 2, "cases": []}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "schema_version 1"):
                evaluate_answer_benchmark(lambda _query: "", str(path))

    def test_answer_benchmark_refuses_to_score_unreviewed_draft(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft.json"
            path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "review_status": "needs_review",
                    "cases": [],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "not approved for scoring"):
                evaluate_answer_benchmark(lambda _query: "", str(path))

    def test_answer_benchmark_separates_fact_accuracy_from_citation_rate(self):
        import json
        import tempfile
        from pathlib import Path

        benchmark = {
            "schema_version": 1,
            "cases": [{
                "id": "uncited-answer",
                "query": "What is the result?",
                "answerable": True,
                "category": "grounded_factuality",
                "required_facts": ["Result is 42"],
                "expected_sources": ["result.md"],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "benchmark.json"
            path.write_text(json.dumps(benchmark), encoding="utf-8")
            report = evaluate_answer_benchmark(
                lambda _query: "Result is 42.", str(path)
            )

        self.assertEqual(report["answerable_fact_accuracy"], 1.0)
        self.assertEqual(report["answerable_accuracy"], 0.0)
        self.assertEqual(report["citation_rate"], 0.0)
        self.assertTrue(report["cases"][0]["facts_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
