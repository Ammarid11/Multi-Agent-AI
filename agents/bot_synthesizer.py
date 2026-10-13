# agents/bot_synthesizer.py
import ollama
import config
from agents.grounding import (
    VAULT_GROUNDING_POLICY,
    add_citation_verification_notice,
)


def run_bot_synthesizer(prompt: str, memory_manager) -> str:
    """Sintesis ide dan penemuan pola tersembunyi antar-catatan di Vault."""
    print(f"\n💡 [Idea Synthesizer ({config.MODEL_REASONER})] Menghubungkan ide & wawasan...")

    clean = prompt.replace("/sintesis", "").replace("/connect", "").strip()
    query = clean if clean else "proyek konsep catatan aktivitas rencana"
    context = memory_manager.search_context(query, k=8) if memory_manager else ""

    sys_prompt = (
        "Anda adalah asisten sintesis ide & Knowledge Graph Second Brain.\n"
        "Analisis hubungan ide lintas catatan, berikan insight baru, dan rekomendasi aksi nyata.\n"
        f"{VAULT_GROUNDING_POLICY}\n"
        "Bedakan secara eksplisit fakta dari catatan dan hipotesis/inferensi baru. Jika bukti tidak cukup, katakan demikian.\n\n"
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
    return add_citation_verification_notice(res.message.content, context)
