# agents/bot_council.py
"""
Council of Experts: Multi-Agent Internal Debate (Pilar 2 Level 4 AI):
Debat internal 3 arah antara DeepSeek-R1 (Devil's Advocate), Architect (Kelayakan),
dan Carl (Synthesizer) untuk menghasilkan solusi strategis yang tahan banting.
"""
from typing import List, Dict
import ollama
import config
from agents.grounding import VAULT_GROUNDING_POLICY, add_citation_verification_notice


def run_council_debate(topic: str, memory_manager, user_name: str = "Pengguna") -> str:
    """Menjalankan debat internal 3 babak antar model spesialis."""
    print(f"\n🏛️ [Council of Experts] Memulai sidang perdebatan strategi untuk: '{topic[:50]}...'")

    context = memory_manager.search_context(topic, k=4) if memory_manager else ""

    # BABAK 1: DeepSeek-R1 (The Inquisitor / Devil's Advocate)
    print("   🔴 Babak 1: DeepSeek-R1 membedah risiko & skenario terburuk...")
    r1_prompt = (
        f"Anda adalah Penguji Risiko Ekstrem (Devil's Advocate) untuk {user_name}.\n"
        f"Topik / Rencana: {topic}\n"
        f"Data Pendukung Obsidian:\n{context}\n\n"
        f"{VAULT_GROUNDING_POLICY}\n"
        "Jika konteks tidak memuat bukti, jangan menciptakan fakta tentang pengguna atau proyek.\n"
        "TUGAS: Jangan mudah setuju! Bedah secara kritis:\n"
        "1. Tiga risiko terbesar atau skenario kegagalan terburuk.\n"
        "2. Asumsi-asumsi keliru atau jebakan operasional/finansial yang mungkin terabaikan.\n"
        "Format ringkas, tajam, dan tidak berbasa-basi."
    )
    res_r1 = ollama.chat(
        model=config.MODEL_REASONER,
        messages=[{'role': 'user', 'content': r1_prompt}],
        options=config.OPTIONS_REASONER,
        keep_alive=config.KEEP_ALIVE_SPECIALIST
    )
    critique = res_r1.message.content.strip()

    # BABAK 2: The Pragmatist / Architect (Qwen)
    print("   🔵 Babak 2: Arsitek mengevaluasi kelayakan teknis & eksekusi...")
    arch_prompt = (
        f"Sebagai Arsitek Solusi dan Eksekutor Praktis untuk {user_name}:\n"
        f"Topik: {topic}\n"
        f"Kritik & Risiko dari Devil's Advocate:\n{critique}\n\n"
        "TUGAS: Berikan solusi teknis, alokasi sumber daya, dan mitigasi konkret untuk menjawab kritik tersebut."
    )
    res_arch = ollama.chat(
        model=config.MODEL_CODER,
        messages=[{'role': 'user', 'content': arch_prompt}],
        options=config.OPTIONS_CODER,
        keep_alive=config.KEEP_ALIVE_SPECIALIST
    )
    technical_plan = res_arch.message.content.strip()

    # BABAK 3: Carl (The Master Synthesizer)
    print("   🟢 Babak 3: Carl merumuskan konsensus dan rencana aksi final...")
    consensus_prompt = (
        f"Anda adalah Carl, asisten pemimpin Second Brain untuk {user_name}.\n"
        f"TOPIK: {topic}\n\n"
        f"Konteks sumber Vault:\n{context}\n"
        f"{VAULT_GROUNDING_POLICY}\n"
        "Tandai risiko/solusi sebagai hipotesis bila tidak didukung bukti.\n\n"
        f"HASIL UJI RISIKO (DeepSeek-R1):\n{critique}\n\n"
        f"RENCANA MITIGASI (Arsitek Teknis):\n{technical_plan}\n\n"
        "TUGAS:\n"
        "Sajikan laporan akhir sidang Council of Experts dalam format yang elegan, terstruktur, dan actionable:\n"
        "1. Ringkasan Dilema / Topik\n"
        "2. Poin Kritis Risiko yang Wajib Diwaspadai (Hasil Debat R1)\n"
        "3. Solusi Terpilih & Mitigasi Tahan Uji\n"
        "4. Tiga Langkah Eksekusi Prioritas Pertama untuk Ammar."
    )
    res_carl = ollama.chat(
        model=config.MODEL_WRITER,
        messages=[{'role': 'user', 'content': consensus_prompt}],
        options=config.OPTIONS_WRITER,
        keep_alive=config.KEEP_ALIVE_DEFAULT
    )
    final_consensus = res_carl.message.content.strip()

    report = (
        "### 🏛️ Sidang Perdebatan Multimodel (Council of Experts Report)\n\n"
        f"{final_consensus}\n\n"
        "---\n"
        "*(Sidang melibatkan penalaran bertahap DeepSeek-R1, Qwen Architecture, dan Sintesis Carl)*"
    )
    return add_citation_verification_notice(report, context)
