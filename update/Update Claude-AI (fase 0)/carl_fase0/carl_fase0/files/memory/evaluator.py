# memory/evaluator.py
"""Smoke benchmark retrieval terhadap catatan target dari Vault."""

import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import config
from memory.vault_scanner import is_indexable_note

def generate_synthetic_eval_dataset(vault_path: str = config.VAULT_PATH, max_samples: int = 5) -> List[Dict[str, Any]]:
    """
    Menghasilkan pasangan (Pertanyaan Sintetis, Dokumen Target) dari catatan Vault
    untuk menguji daya ingat dan presisi pencarian sistem.
    """
    vault = Path(vault_path)
    if not vault.exists():
        return []

    dataset = []
    # Pilih catatan yang memiliki konten substantif
    for md_file in sorted(vault.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        rel_str = str(md_file.relative_to(vault)).replace("\\", "/")
        if not is_indexable_note(str(md_file), str(vault)):
            continue

        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        if len(content) < 80:
            continue

        # Ekstrak judul dan heading
        headings = re.findall(r"^#+\s+(.+)$", content, flags=re.MULTILINE)
        stem = md_file.stem

        # Buat query evaluasi realistis berdasarkan judul dan heading
        query = f"Apa isi dan poin utama dari catatan {stem}?"
        if headings:
            query = f"{headings[0]} terkait {stem}"

        dataset.append({
            "query": query,
            "target_stem": stem.lower(),
            "target_filename": md_file.name.lower(),
            "target_path": str(md_file)
        })

        if len(dataset) >= max_samples:
            break

    return dataset


def evaluate_memory_accuracy(memory_manager=None, max_samples: int = 5) -> Dict[str, Any]:
    """
    Mengukur retrieval dokumen target dengan query sintetis dari Vault.

    Ini bukan evaluasi akurasi jawaban LLM. Dataset yang dihasilkan dari judul
    catatan hanya cocok sebagai smoke benchmark retrieval, bukan benchmark
    relevansi independen.
    """
    if max_samples <= 0:
        raise ValueError("max_samples harus lebih besar dari nol.")

    if memory_manager is None:
        from memory_indexer import MemoryManager
        memory_manager = MemoryManager()
        memory_manager.index_vault(silent=True)

    dataset = generate_synthetic_eval_dataset(config.VAULT_PATH, max_samples=max_samples)
    if not dataset:
        return {
            "status": "warning",
            "message": "Belum ada catatan yang cukup untuk dievaluasi di Vault.",
            "metric_scope": "synthetic_retrieval",
            "hit_rate_at_1": None,
            "hit_rate_at_3": None,
            "mrr": None,
            "avg_latency_ms": None,
            "composite_score": None,
            "samples_tested": 0,
        }

    hits_at_1 = 0
    hits_at_3 = 0
    rr_scores = []
    latencies = []

    for item in dataset:
        start_t = time.perf_counter()
        result_text = memory_manager.search_context(item["query"], k=5)
        elapsed_ms = (time.perf_counter() - start_t) * 1000
        latencies.append(elapsed_ms)

        # Rank by explicit source markers, not incidental mentions in chunk text.
        source_names = re.findall(r"\[Sumber:\s*([^\]]+)\]", result_text)
        target_filename = item["target_filename"].casefold()
        found_rank = 0
        for r_idx, source_name in enumerate(source_names, 1):
            if Path(source_name.strip()).name.casefold() == target_filename:
                found_rank = r_idx
                break

        if found_rank == 1:
            hits_at_1 += 1
            hits_at_3 += 1
            rr_scores.append(1.0)
        elif 1 < found_rank <= 3:
            hits_at_3 += 1
            rr_scores.append(1.0 / found_rank)
        elif found_rank > 3:
            rr_scores.append(1.0 / found_rank)
        else:
            rr_scores.append(0.0)

    total = len(dataset)
    hit_rate_1 = hits_at_1 / total
    hit_rate_3 = hits_at_3 / total
    mrr = sum(rr_scores) / total if total > 0 else 0.0
    avg_latency = sum(latencies) / total if total > 0 else 0.0

    # Penilaian kesehatan memori (0 - 100)
    composite_score = int((hit_rate_3 * 60) + (mrr * 40))

    if composite_score >= 85:
        grade = "A+ (Retrieval kuat pada sampel sintetis)"
    elif composite_score >= 70:
        grade = "B (Retrieval cukup pada sampel sintetis)"
    else:
        grade = "C (Retrieval perlu ditinjau)"

    return {
        "status": "success",
        "metric_scope": "synthetic_retrieval",
        "composite_score": composite_score,
        "grade": grade,
        "hit_rate_at_1": round(hit_rate_1, 2),
        "hit_rate_at_3": round(hit_rate_3, 2),
        "mrr": round(mrr, 3),
        "avg_latency_ms": round(avg_latency, 1),
        "samples_tested": total,
        "total_chunks_indexed": len(memory_manager.all_chunks),
        "evaluation_note": (
            "Skor ini mengukur retrieval catatan target pada query sintetis; "
            "bukan akurasi, kelengkapan, atau groundedness jawaban LLM."
        ),
        "recommendation": (
            "Retrieval target memadai pada sampel sintetis ini; validasi dengan pertanyaan "
            "dan jawaban acuan buatan manusia sebelum menyimpulkan kualitas produksi."
            if composite_score >= 75
            else "Periksa sinkronisasi/index dan relevansi retrieval; gunakan dataset acuan "
                 "yang ditinjau manusia untuk mengukur kualitas secara lebih representatif."
        )
    }


def run_evaluation_command(memory_manager=None) -> str:
    """Menangani perintah /eval atau /calibrate di CLI dan Web chat."""
    report = evaluate_memory_accuracy(memory_manager=memory_manager, max_samples=5)

    if report.get("status") == "warning":
        return f"⚠️ {report.get('message')}"

    lines = [
        "🧪 **[Evaluasi Retrieval Memori Vault]**",
        "Benchmark sintetis berbasis judul dan heading catatan:\n",
        f"- **Skor Retrieval Komposit:** `{report['composite_score']}/100` — **{report['grade']}**",
        f"- **Hit Rate@3:** `{int(report['hit_rate_at_3'] * 100)}%`",
        f"- **MRR (Mean Reciprocal Rank):** `{report['mrr']}` (Skala 0.0 - 1.0)",
        f"- **Rata-rata Latensi Retrieval:** `{report['avg_latency_ms']} ms`",
        f"- **Sampel Uji Sintetis:** `{report['samples_tested']} berkas catatan`",
        f"- **Total Indeks Memori:** `{report['total_chunks_indexed']} pecahan semantik`\n",
        f"ℹ️ **Batasan:** {report['evaluation_note']}\n",
        f"💡 **Rekomendasi Adaptif:** {report['recommendation']}\n",
        "---",
        "*Catatan: evaluasi ini tidak menilai kebenaran jawaban yang dihasilkan Carl.*"
    ]
    return "\n".join(lines)
