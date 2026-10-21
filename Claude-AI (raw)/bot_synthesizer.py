# agents/bot_synthesizer.py
import ollama
import config
from agents.grounding import (
    VAULT_GROUNDING_POLICY,
    VAULT_SYNTHESIS_POLICY,
    validate_vault_answer,
    vault_context_sources,
)


def run_bot_synthesizer(prompt: str, memory_manager) -> str:
    """Sintesis ide dan penemuan pola tersembunyi antar-catatan di Vault."""
    print(f"\n💡 [Idea Synthesizer ({config.MODEL_REASONER})] Menghubungkan ide & wawasan...")

    clean = prompt.replace("/sintesis", "").replace("/connect", "").strip()
    query = clean if clean else "proyek konsep catatan aktivitas rencana"
    context = memory_manager.search_context(query, k=8) if memory_manager else ""
    if not context.strip() or not vault_context_sources(context):
        return (
            "Belum bisa membuat sintesis berbasis Vault: hasil pencarian tidak memuat "
            "sumber catatan yang dapat dikutip. Saya tidak akan mengisi kekosongan "
            "dengan dugaan atau pengetahuan umum."
        )

    sys_prompt = (
        "Anda adalah asisten sintesis ide & Knowledge Graph Second Brain.\n"
        "Analisis hubungan lintas catatan hanya sejauh bukti mendukungnya. Jangan "
        "menyimpulkan bahwa isi pertanyaan/hipotesis dalam catatan adalah fakta.\n"
        f"{VAULT_GROUNDING_POLICY}\n"
        f"{VAULT_SYNTHESIS_POLICY}\n"
        "Jangan menambahkan profil/riwayat percakapan, dugaan psikologis, atau "
        "rekomendasi aksi yang tidak diminta.\n\n"
        f"--- KONTEKS CATATAN OBSIDIAN ---\n{context if context else 'Belum ada cukup catatan.'}"
    )

    res = ollama.chat(
        model=config.MODEL_REASONER,
        messages=[
            {'role': 'system', 'content': sys_prompt},
            {'role': 'user', 'content': clean if clean else "Tolong buatkan sintesis ide dari catatan saya."},
        ],
        options=config.OPTIONS_REASONER,
        keep_alive=config.KEEP_ALIVE_SPECIALIST,
    )
    return validate_vault_answer(
        res.message.content,
        context,
        min_cited_sources=2 if len(vault_context_sources(context)) > 1 else 1,
    )
