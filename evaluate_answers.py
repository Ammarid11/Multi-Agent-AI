"""Run the human-reviewed answer checklist benchmark against Carl."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import config
from agents.bot_writer import run_bot_writer
from memory.answer_evaluator import evaluate_answer_benchmark
from memory.answer_evaluator import load_answer_benchmark
from memory_indexer import MemoryManager

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "answer_benchmark.json"


def _copy_benchmark_sources(dataset_path: Path, target_vault: Path) -> None:
    """Copy only explicitly listed benchmark sources into a temporary vault."""
    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    source_notes = data.get("source_notes")
    if not isinstance(source_notes, list) or not source_notes:
        raise ValueError(
            "Isolated mode requires a non-empty 'source_notes' list in the dataset."
        )

    source_root = Path(config.VAULT_PATH).resolve()
    for note in source_notes:
        if not isinstance(note, str) or not note.strip():
            raise ValueError("Each benchmark source note must be a non-empty path.")
        relative_path = Path(note)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"Benchmark source path must be relative: {note}")
        source_path = (source_root / relative_path).resolve()
        if source_root not in source_path.parents or not source_path.is_file():
            raise ValueError(f"Benchmark source note does not exist in the Vault: {note}")

        destination = target_vault / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)


def _evaluate(memory: MemoryManager, dataset_path: Path, isolated: bool) -> dict:
    report = evaluate_answer_benchmark(
        answer_fn=lambda query: run_bot_writer(
            query,
            memory_manager=memory,
            chat_history=[],
            user_name="Pengguna",
        ),
        dataset_path=str(dataset_path),
    )
    report["run_configuration"] = {
        "writer_model_configured": config.MODEL_WRITER,
        "writer_options": config.OPTIONS_WRITER,
        "embedding_model_configured": config.MODEL_EMBEDDING,
        "index_mode": "isolated_benchmark_sources" if isolated else "configured_vault",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to a human-reviewed answer benchmark JSON file.",
    )
    parser.add_argument(
        "--isolated-vault",
        action="store_true",
        help="Index only the dataset's source_notes in a temporary Vault and Qdrant DB.",
    )
    args = parser.parse_args()

    try:
        cases = load_answer_benchmark(str(args.dataset))
    except (OSError, ValueError) as exc:
        print(json.dumps({
            "status": "error",
            "message": str(exc),
        }, ensure_ascii=False, indent=2))
        return 2

    if not cases:
        print(json.dumps({
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
        }, ensure_ascii=False, indent=2))
        return 0

    if args.isolated_vault:
        original_vault_path = config.VAULT_PATH
        original_db_path = config.DB_PATH
        with tempfile.TemporaryDirectory(prefix="carl-answer-benchmark-") as temp_dir:
            temp_root = Path(temp_dir)
            temp_vault = temp_root / "vault"
            try:
                _copy_benchmark_sources(args.dataset, temp_vault)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(json.dumps({
                    "status": "error",
                    "message": str(exc),
                }, ensure_ascii=False, indent=2))
                return 2

            config.VAULT_PATH = str(temp_vault)
            config.DB_PATH = str(temp_root / "qdrant")
            memory = None
            try:
                memory = MemoryManager()
                memory.index_vault(silent=True)
                report = _evaluate(memory, args.dataset, isolated=True)
            finally:
                try:
                    if memory and memory.store.client:
                        memory.store.client.close()
                finally:
                    config.VAULT_PATH = original_vault_path
                    config.DB_PATH = original_db_path
    else:
        memory = MemoryManager()
        memory.index_vault(silent=True)
        report = _evaluate(memory, args.dataset, isolated=False)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"success", "warning"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
