import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from memory.answer_evaluator import evaluate_answer_benchmark
from memory.evaluator import evaluate_memory_accuracy, run_evaluation_command
from memory.hybrid_search import merge_ranked_results
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
                    "required_facts": ["Result is 42"],
                    "expected_sources": ["result.md"],
                },
                {
                    "id": "unanswerable",
                    "query": "What is the private key?",
                    "answerable": False,
                    "required_facts": [],
                    "expected_sources": [],
                },
            ],
        }
        answers = {
            "What is the documented result?": "Result is 42. [Sumber: result.md]",
            "What is the private key?": "Informasi itu tidak ditemukan di Vault.",
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
