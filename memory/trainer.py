# memory/trainer.py
"""
Frontier N: Local Knowledge Distillation & LoRA Self-Fine-Tuning Pipeline
Mengekstrak pengetahuan terbaik dari Vault Obsidian, mengonversinya menjadi
dataset instruksi Q&A format Alpaca, dan menyiapkan adapter LoRA untuk fine-tuning lokal.
Command: /train_adapter [refresh]
"""
import os
import re
import json
import glob
from datetime import datetime
from typing import List, Dict
import config
from memory.vault_scanner import is_indexable_note

TRAINING_OUTPUT_DIR = os.path.join(config.VAULT_PATH, "07-Settings", "training")
DATASET_FILE = os.path.join(TRAINING_OUTPUT_DIR, "vault_training_dataset.jsonl")
META_FILE = os.path.join(TRAINING_OUTPUT_DIR, "training_meta.json")


def _extract_best_notes(max_notes: int = 25) -> List[Dict]:
    """Ekstrak catatan terbaik dari Vault berdasarkan panjang & kualitas konten."""
    notes = []
    for filepath in glob.glob(os.path.join(config.VAULT_PATH, "**", "*.md"), recursive=True):
        if not is_indexable_note(filepath, config.VAULT_PATH):
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            # Bersihkan frontmatter YAML
            clean = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL).strip()
            # Hanya catatan substansial (> 150 karakter konten bersih)
            if len(clean) > 150:
                notes.append({
                    "path": filepath,
                    "title": os.path.splitext(os.path.basename(filepath))[0],
                    "content": clean[:1800],  # Batasi panjang untuk prompt
                    "length": len(clean)
                })
        except Exception:
            continue

    # Urutkan berdasarkan panjang konten (lebih panjang = lebih kaya pengetahuan)
    notes.sort(key=lambda x: x["length"], reverse=True)
    return notes[:max_notes]


def generate_training_dataset() -> str:
    """
    Generate dataset Q&A instruksi dari vault notes menggunakan Ollama secara lokal.
    Output: JSONL format Alpaca, siap untuk Unsloth / LLaMA-Factory / Axolotl.
    """
    import ollama

    os.makedirs(TRAINING_OUTPUT_DIR, exist_ok=True)
    notes = _extract_best_notes(max_notes=20)

    if not notes:
        return (
            "❌ **Tidak ada catatan Vault yang cukup substansial.**\n\n"
            "Pastikan folder Vault (`E:/Project AI 2026/Obsidian/Brain AI Memory/`) "
            "memiliki catatan dengan konten minimal 150 karakter."
        )

    dataset: List[Dict] = []
    processed = 0

    for note in notes:
        prompt = (
            f"Berdasarkan catatan berikut, buat **2 pasangan pertanyaan-jawaban** berkualitas tinggi "
            f"dalam format JSON array. Pertanyaan harus natural seperti yang ditanyakan pengguna kepada "
            f"asisten AI pribadi bernama Carl. Jawaban harus informatif dan relevan dengan isi catatan.\n\n"
            f"Format output (HANYA JSON, tanpa teks lain):\n"
            f"[{{\"instruction\": \"pertanyaan...\", \"input\": \"\", \"output\": \"jawaban...\"}}]\n\n"
            f"Catatan:\nJudul: {note['title']}\n\n{note['content']}"
        )
        try:
            resp = ollama.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 400, "temperature": 0.3}
            )
            text = resp["message"]["content"].strip()
            # Ekstrak JSON dari respons
            json_match = re.search(r'\[.*?\]', text, re.DOTALL)
            if json_match:
                pairs = json.loads(json_match.group())
                for pair in pairs:
                    if isinstance(pair, dict) and "instruction" in pair and "output" in pair:
                        if len(pair["instruction"]) > 10 and len(pair["output"]) > 20:
                            dataset.append({
                                "instruction": pair["instruction"].strip(),
                                "input": pair.get("input", "").strip(),
                                "output": pair["output"].strip(),
                                "source_note": note["title"]
                            })
            processed += 1
        except Exception:
            continue

    if not dataset:
        return "❌ Dataset kosong. Ollama gagal menghasilkan pasangan Q&A dari catatan Vault."

    # Simpan dataset ke JSONL
    with open(DATASET_FILE, 'w', encoding='utf-8') as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Simpan metadata
    meta = {
        "generated_at": datetime.now().isoformat(),
        "source_notes_processed": processed,
        "source_notes_total": len(notes),
        "qa_pairs": len(dataset),
        "dataset_file": DATASET_FILE,
        "format": "Alpaca JSONL",
        "model_used": config.OLLAMA_MODEL
    }
    with open(META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return (
        f"🧬 **Dataset Training LoRA Berhasil Dihasilkan dari Vault Anda!**\n\n"
        f"| Parameter | Nilai |\n"
        f"|---|---|\n"
        f"| 📚 Catatan Vault Diproses | {processed}/{len(notes)} |\n"
        f"| 🗂️ Pasangan Q&A Dihasilkan | **{len(dataset)} instruksi** |\n"
        f"| 💾 Format Output | Alpaca JSONL |\n"
        f"| 📂 Lokasi File | `07-Settings/training/vault_training_dataset.jsonl` |\n\n"
        f"**🚀 Langkah Selanjutnya — Pilih Metode Fine-Tuning:**\n\n"
        f"**Opsi A — Unsloth** *(GPU, VRAM ≥ 6GB, tercepat):*\n"
        f"```bash\n"
        f"pip install unsloth\n"
        f"# Gunakan dataset: {DATASET_FILE}\n"
        f"```\n\n"
        f"**Opsi B — LLaMA-Factory** *(CPU/GPU, paling kompatibel):*\n"
        f"```bash\n"
        f"pip install llamafactory\n"
        f"llamafactory-cli train --dataset {DATASET_FILE}\n"
        f"```\n\n"
        f"**Opsi C — Ollama Modelfile** *(100% lokal tanpa GPU):*\n"
        f"```\n"
        f"FROM qwen2.5:7b\n"
        f"SYSTEM \"Kamu adalah Carl, asisten Second Brain pribadi yang memiliki pengetahuan mendalam tentang catatan dan pemikiran pemilikmu.\"\n"
        f"```\n\n"
        f"*🧠 Vault pengetahuan Anda kini siap dijadikan intuisi neural AI pribadi!*"
    )


def get_training_status() -> str:
    """Cek status dataset training yang sudah ada."""
    if not os.path.exists(META_FILE):
        return (
            "🧬 **Status Training Adapter LoRA (Frontier N)**\n\n"
            "- ⚠️ **Belum ada dataset training yang dibuat.**\n"
            "- Ketik `/train_adapter` untuk memulai proses distilasi pengetahuan dari Vault.\n\n"
            "*Carl akan membaca semua catatan Vault dan mengubahnya menjadi dataset instruksi Q&A siap pakai untuk fine-tuning model lokal.*"
        )

    try:
        with open(META_FILE, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        return (
            f"🧬 **Status Dataset Training LoRA (Frontier N)**\n\n"
            f"- ✅ **Dataset Tersedia**\n"
            f"- 📅 Dibuat: `{meta.get('generated_at', 'N/A')[:19]}`\n"
            f"- 📚 Sumber: `{meta.get('source_notes_processed', 0)}` catatan Vault\n"
            f"- 🗂️ Q&A Pairs: **`{meta.get('qa_pairs', 0)}` instruksi**\n"
            f"- 💾 Format: `{meta.get('format', 'Alpaca JSONL')}`\n"
            f"- 📂 Lokasi: `07-Settings/training/vault_training_dataset.jsonl`\n\n"
            f"*Ketik `/train_adapter refresh` untuk regenerasi ulang dengan catatan terbaru.*"
        )
    except Exception:
        return "❌ File metadata training tidak dapat dibaca. Coba `/train_adapter refresh`."


def run_trainer_command(args: str = "") -> str:
    """Entry point utama untuk perintah /train_adapter."""
    if "status" in args.lower():
        return get_training_status()
    elif "refresh" in args.lower() or args.strip() == "":
        return generate_training_dataset()
    return get_training_status()

