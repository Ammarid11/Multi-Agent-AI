# agents/autonomous_agent.py
"""
Autonomous Multi-Step Goal Engine & Self-Healing (Pilar 1 & 6 Level 4 AI):
Mengeksekusi tujuan bertahap secara mandiri dengan alur ReAct (Planner -> Executor -> Self-Healer).
"""
import os
import re
import json
import logging
from typing import List, Dict, Any, Optional
import ollama
import config
from tools.tool_web_search import web_search_structured
from tools.tool_read import read_file
from tools.tool_create import create_file
from tools.tool_append import append_file
from tools.tool_append import find_file_in_vault

logger = logging.getLogger(__name__)
_PLAN_FIELDS = {
    "web_search": ("query",),
    "read_file": ("filename",),
    "write_file": ("filename", "summary"),
    "append_file": ("filename", "content"),
}


def _extract_plan_json(raw: str) -> List[Dict[str, Any]]:
    """Mengekstrak list sub-tugas JSON dari keluaran model."""
    if not raw:
        return []
        
    clean = raw.strip()
    # Memperbaiki pola agar grup yang berisi array tertangkap dengan benar di group(1)
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", clean)
    if match:
        clean = match.group(1).strip()
    else:
        match_arr = re.search(r"\[[\s\S]*\]", clean)
        if match_arr:
            clean = match_arr.group(0).strip()
            
    try:
        data = json.loads(clean, strict=False)
        return (
            [step for step in data if isinstance(step, dict)]
            if isinstance(data, list)
            else []
        )
    except Exception:
        return []


def _validate_plan_steps(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Memvalidasi daftar langkah rencana dari model dengan pengaman tambahan dan log."""
    validated = []
    for idx, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
            
        action = step.get("action")
        if not isinstance(action, str):
            continue
            
        normalized_action = action.casefold().strip()
        required_fields = _PLAN_FIELDS.get(normalized_action)
        
        if not required_fields:
            continue
            
        # Periksa kelengkapan field wajib
        failed = False
        for field in required_fields:
            val = step.get(field)
            # Memastikan field ada, berupa string, dan tidak kosong setelah strip
            if not isinstance(val, str) or not val.strip():
                failed = True
                break
                
        if failed:
            continue
            
        validated.append({**step, "action": normalized_action})
    return validated


def _tool_reported_success(result: str) -> bool:
    """Memeriksa apakah laporan hasil alat menunjukkan status sukses dengan lebih fleksibel."""
    if not result or not isinstance(result, str):
        return False
        
    normalized = result.strip().casefold()
    
    # Periksa simbol atau kata kunci umum yang menandakan keberhasilan
    success_indicators = [
        "✅", 
        "berhasil dibuat", 
        "sukses", 
        "success", 
        "berhasil disimpan"
    ]
    
    return any(indicator.casefold() in normalized for indicator in success_indicators)


class AutonomousGoalEngine:
    """Mesin Eksekusi Tujuan Mandiri Multi-Step dengan Self-Healing yang disempurnakan."""
    def __init__(self, memory_manager, user_name: str = "Pengguna"):
        self.memory = memory_manager
        self.user_name = user_name

    def plan_steps(self, goal: str) -> List[Dict[str, Any]]:
        """Menguraikan tujuan pengguna menjadi 2-4 sub-tugas terstruktur dengan mekanisme retry."""
        # Ambil konteks memori jika tersedia untuk memperkaya perencanaan
        context = ""
        if self.memory and hasattr(self.memory, "get_summary"):
            context = f"\nKonteks Percakapan Sebelumnya: {self.memory.get_summary()}\n"

        sys_prompt = (
            "Anda adalah AI Task Planner tingkat lanjut.\n"
            "TUGAS: Pecah tujuan pengguna berikut menjadi 2 hingga 4 sub-tugas berurutan.\n"
            "Pilihan aksi yang didukung:\n"
            "- 'web_search': {action: 'web_search', query: 'kata kunci'}\n"
            "- 'read_file': {action: 'read_file', filename: 'nama_file.md'}\n"
            "- 'write_file': {action: 'write_file', filename: 'folder/nama_file.md', summary: 'poin isi'}\n"
            "- 'append_file': {action: 'append_file', filename: 'nama_file.md', content: 'isi teks'}\n"
            "ATURAN:\n"
            "1. Kembalikan HANYA array JSON murni (tanpa teks penjelasan lain).\n"
            "2. Contoh format: [{\"action\": \"web_search\", \"query\": \"...\"}, {\"action\": \"write_file\", \"filename\": \"...\", \"summary\": \"...\"}]\n"
            + context
        )

        messages = [
            {'role': 'system', 'content': sys_prompt},
            {'role': 'user', 'content': f"Tujuan Pengguna: {goal}"}
        ]

        # Mekanisme Self-Healing: Coba hingga 2 kali jika validasi gagal
        for attempt in range(2):
            try:
                res = ollama.chat(
                    model=config.MODEL_WRITER,
                    messages=messages,
                    options={"temperature": 0.1},
                    keep_alive=config.KEEP_ALIVE_DEFAULT
                )
                steps = _validate_plan_steps(_extract_plan_json(res.message.content))
                if steps:
                    return steps
            except Exception:
                logger.exception(f"Percobaan ke-{attempt + 1} gagal membuat rencana. Mencoba ulang...")

        logger.error("Semua percobaan pembuatan rencana tugas gagal.")
        return []

    def execute_goal(self, goal: str) -> str:
        """Mengeksekusi rencana langkah demi langkah dengan pemulihan mandiri (Self-Healing)."""
        print(f"\n🚀 [Goal Engine] Merencanakan strategi eksekusi untuk: '{goal[:60]}...'")
        plan = self.plan_steps(goal)
        if not plan:
            return (
                "⚠️ Tujuan belum dieksekusi: sistem tidak mendapatkan rencana valid "
                "dengan aksi yang didukung. Tidak ada perubahan yang dilakukan."
            )

        execution_logs: List[str] = [f"### 🎯 Laporan Eksekusi Tujuan Mandiri (Level 4 Agent):\n**Tujuan:** *{goal}*\n"]
        accumulated_context = ""
        successful_steps = 0
        failed_steps = 0

        for idx, step in enumerate(plan, 1):
            action = step.get("action", "").lower()
            print(f"   ▶️ Menjalankan Langkah {idx}/{len(plan)}: [{action}]")

            try:
                if action == "web_search":
                    query = step.get("query", goal)
                    web_ctx, refs = web_search_structured(query)
                    if not refs or not any(
                        (item.get("deep_content") or item.get("snippet", "")).strip()
                        for item in refs
                    ):
                        failed_steps += 1
                        execution_logs.append(
                            f"⚠️ **Langkah {idx} (Riset Web) gagal:** tidak ada hasil "
                            "dengan konten dan sumber yang dapat digunakan."
                        )
                        continue
                    accumulated_context += f"\n\n[Hasil Riset Web: {query}]\n{web_ctx}"
                    source_names = ", ".join([r['source'] for r in refs[:2]]) or "Web"
                    execution_logs.append(f"✅ **Langkah {idx} (Riset Web):** Berhasil menelusuri `{query}` via {source_names}.")
                    successful_steps += 1

                elif action == "read_file":
                    fn = step.get("filename", "")
                    content = read_file(fn)
                    if not content or content.startswith("❌"):
                        failed_steps += 1
                        execution_logs.append(
                            f"⚠️ **Langkah {idx} (Baca Berkas) gagal:** "
                            f"{content or 'tidak ada isi yang dapat dibaca.'}"
                        )
                        continue
                    accumulated_context += f"\n\n[Isi Berkas: {fn}]\n{content}"
                    execution_logs.append(f"✅ **Langkah {idx} (Baca Berkas):** Berhasil membaca data dari `{fn}`.")
                    successful_steps += 1

                elif action == "write_file":
                    fn = step.get("filename", "")
                    summary = step.get("summary", "")
                    if not fn:
                        failed_steps += 1
                        execution_logs.append(f"⚠️ **Langkah {idx} (Buat Berkas) gagal:** nama berkas tidak valid.")
                        continue

                    # Sintesis isi file berdasarkan konteks yang terkumpul
                    file_prompt = (
                        f"Buat isi catatan rapi dalam format Markdown Obsidian untuk: {summary}.\n"
                        f"Gunakan data berikut jika relevan:\n{accumulated_context[:1800]}\n"
                        "Pisahkan fakta dari inferensi. Cantumkan nama sumber yang tersedia untuk fakta dari riset atau berkas.\n"
                        "Wajib sertakan Frontmatter YAML dan Heading # Emoji."
                    )
                    content_res = ollama.chat(
                        model=config.MODEL_WRITER,
                        messages=[{'role': 'user', 'content': file_prompt}],
                        options=config.OPTIONS_WRITER,
                        keep_alive=config.KEEP_ALIVE_DEFAULT
                    )
                    from agents.quality_gate import verify_and_polish_output
                    file_body = verify_and_polish_output(content_res.message.content.strip())

                    # SELF-HEALING: Jika penulisan gagal atau folder tidak ada, buat folder aman
                    save_res = create_file(fn, file_body)
                    if _tool_reported_success(save_res):
                        successful_steps += 1
                        execution_logs.append(f"✅ **Langkah {idx} (Buat Berkas):** {save_res}")
                    else:
                        failed_steps += 1
                        execution_logs.append(f"⚠️ **Langkah {idx} (Buat Berkas) gagal:** {save_res}")

                elif action == "append_file":
                    fn = step.get("filename", "")
                    content_to_add = step.get("content", f"\n- Catatan terkait: [[{goal}]]")
                    if not fn:
                        failed_steps += 1
                        execution_logs.append(f"⚠️ **Langkah {idx} (Hubungkan Berkas) gagal:** nama berkas tidak valid.")
                        continue
                        
                    append_res = append_file(fn, content_to_add)
                    if _tool_reported_success(append_res):
                        successful_steps += 1
                        execution_logs.append(f"✅ **Langkah {idx} (Hubungkan Berkas):** {append_res}")
                    else:
                        failed_steps += 1
                        execution_logs.append(f"⚠️ **Langkah {idx} (Hubungkan Berkas) gagal:** {append_res}")

                else:
                    failed_steps += 1
                    execution_logs.append(
                        f"⚠️ **Langkah {idx} dilewati:** aksi `{action}` tidak didukung."
                    )

            except Exception:
                logger.exception("Goal execution step %s failed.", idx)
                failed_steps += 1
                execution_logs.append(
                    f"⚠️ **Langkah {idx} gagal karena kesalahan internal.** "
                    "Langkah berikutnya tetap dicoba; periksa log untuk detail."
                )

        if failed_steps == 0 and successful_steps == len(plan):
            execution_logs.append(
                f"\n✅ **Semua {successful_steps} langkah terkonfirmasi berhasil.**"
            )
        elif successful_steps:
            execution_logs.append(
                f"\n⚠️ **Eksekusi sebagian:** {successful_steps} langkah berhasil "
                f"dan {failed_steps} langkah gagal/dilewati."
            )
        else:
            execution_logs.append(
                f"\n❌ **Tujuan belum berhasil:** tidak ada langkah berhasil "
                f"({failed_steps} gagal/dilewati)."
            )
        return "\n".join(execution_logs)
    