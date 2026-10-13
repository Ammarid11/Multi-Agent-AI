"""Run the human-reviewed answer checklist benchmark against Carl."""

import argparse
import json
from pathlib import Path

from agents.bot_writer import run_bot_writer
from memory.answer_evaluator import evaluate_answer_benchmark
from memory_indexer import MemoryManager

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "answer_benchmark.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to a human-reviewed answer benchmark JSON file.",
    )
    args = parser.parse_args()

    report = evaluate_answer_benchmark(
        answer_fn=lambda _query: "",
        dataset_path=str(args.dataset),
    )
    if report["status"] == "warning":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    memory = MemoryManager()
    memory.index_vault(silent=True)

    report = evaluate_answer_benchmark(
        answer_fn=lambda query: run_bot_writer(
            query,
            memory_manager=memory,
            chat_history=[],
            user_name="Pengguna",
        ),
        dataset_path=str(args.dataset),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"success", "warning"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
