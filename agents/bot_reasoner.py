# agents/bot_reasoner.py
"""Reasoner Agent — penalaran kritis dan problem solving via DeepSeek-R1."""
import re
import logging
import time
from typing import List, Dict
import config
from agents.streaming import chat_with_optional_stream
from agents.grounding import (
    VAULT_GROUNDING_POLICY,
    VAULT_FACT_CHECK_POLICY,
    VAULT_FACT_CHECK_FALLBACK,
    VAULT_RECENCY_POLICY,
    VAULT_SYNTHESIS_POLICY,
    UNGROUNDED_VAULT_ANSWER,
    add_explicit_vault_sources,
    build_vault_recency_context,
    add_citation_verification_notice,
    format_vault_recency_fallback,
    is_vault_comparison_request,
    is_vault_fact_check_request,
    is_vault_recency_request,
    is_vault_synthesis_request,
    missing_comparison_subjects,
    missing_vault_recency_requirements,
    should_verify_vault_citations,
    validate_vault_answer,
    vault_context_sources,
)
from observability import log_stage

logger = logging.getLogger(__name__)

_DEEP_REASONING_CUES = re.compile(
    r"\b(?:"
    r"analisis|analisa|bandingkan|perbandingan|trade[\s-]?off|pro[\s-]?kontra|"
    r"dampak|konsekuensi|sebab[\s-]?akibat|strategi|prioritaskan|prioritas|"
    r"optimalkan|pemecahan masalah|pecahkan masalah|langkah demi langkah|"
    r"logika|buktikan|evaluasi kritis|pilih yang terbaik|rencana|"
    r"terbaru|paling\s+baru|terkini|paling\s+mutakhir|"
    r"hitung|perhitungan|selesaikan persamaan"
    r")\b",
    re.IGNORECASE,
)
_CONDITIONAL_REASONING_CUES = re.compile(
    r"\b(?:jika|apabila|andaikan|dengan syarat|berdasarkan)\b",
    re.IGNORECASE,
)
_MULTI_PART_CUES = re.compile(
    r"\b(?:dan|lalu|kemudian|sementara|dibandingkan|dengan|serta)\b",
    re.IGNORECASE,
)


def should_use_deep_reasoning(prompt: str) -> bool:
    """Escalate explicit analytical, comparative, planning, or calculation requests."""
    normalized = prompt.strip()
    if not normalized:
        return False
    if _DEEP_REASONING_CUES.search(normalized):
        return True
    return bool(
        _CONDITIONAL_REASONING_CUES.search(normalized)
        and _MULTI_PART_CUES.search(normalized)
    )


def run_bot_reasoner(
    prompt: str,
    memory_manager,
    chat_history: List[Dict[str, str]],
    session_context: str = "",
    user_name: str = "Pengguna"
) -> str:
    """Analisis mendalam dengan struktur penalaran yang jelas."""
    print(f"\n🧠 [Bot Reasoner ({config.MODEL_REASONER})] Memulai analisis mendalam...")

    total_started = time.perf_counter()
    retrieval_started = time.perf_counter()
    vault_comparison = is_vault_comparison_request(prompt)
    vault_synthesis = is_vault_synthesis_request(prompt)
    vault_recency = is_vault_recency_request(prompt)
    vault_fact_check = is_vault_fact_check_request(prompt)
    vault_lookup_request = should_verify_vault_citations(prompt)
    vault_evidence_request = (
        vault_comparison or vault_synthesis or vault_recency or vault_fact_check
    )
    if vault_recency:
        context, source_read_errors = build_vault_recency_context(
            prompt,
            config.VAULT_PATH,
        )
        if source_read_errors:
            logger.error("Unable to build complete dated Vault evidence: %s", source_read_errors)
            return (
                "Belum dapat memastikan informasi paling baru di Vault karena pencarian "
                "bukti bertanggal tidak dapat diselesaikan. Tidak ada klaim kebaruan "
                "yang akan dibuat."
            )
    else:
        context = memory_manager.search_context(prompt, k=6) if memory_manager else ""
    if vault_evidence_request:
        if not vault_recency:
            context, source_read_errors = add_explicit_vault_sources(
                prompt,
                context,
                config.VAULT_PATH,
            )
            if source_read_errors:
                logger.error("Unable to read explicitly named Vault sources: %s", source_read_errors)
                return (
                    "Belum dapat memverifikasi semua catatan yang disebut secara eksplisit. "
                    "Periksa akses ke sumber tersebut lalu ulangi pertanyaannya."
                )
    log_stage(logger, "reasoner", "retrieval", retrieval_started)
    if vault_evidence_request:
        if not context.strip() or not vault_context_sources(context):
            log_stage(logger, "reasoner", "total", total_started, outcome="insufficient_vault_evidence")
            if vault_fact_check:
                return VAULT_FACT_CHECK_FALLBACK
            return (
                "Belum bisa menjawab berdasarkan Vault: hasil pencarian tidak memuat "
                "sumber catatan yang dapat dikutip. Saya tidak akan mengisi kekosongan "
                "dengan dugaan atau pengetahuan umum."
            )
        missing_subjects = (
            missing_comparison_subjects(prompt, context) if vault_comparison else []
        )
        if missing_subjects:
            log_stage(logger, "reasoner", "total", total_started, outcome="missing_comparison_evidence")
            return (
                "Belum bisa membandingkan "
                f"{' dan '.join(missing_subjects)} berdasarkan Vault: hasil pencarian "
                "belum memuat bukti untuk bagian tersebut. Saya tidak akan menggantinya "
                "dengan pengetahuan umum. Sebutkan atau tambahkan catatan sumber yang relevan."
            )

    prompt_started = time.perf_counter()
    effective_session_context = "" if vault_evidence_request else session_context
    sys_prompt = (
        "═══ IDENTITAS & LAWAN BICARA ═══\n"
        f"Anda adalah pakar analisis dan pemecahan masalah kritis untuk {user_name}.\n"
        f"Lawan Bicara: Anda sedang berbicara LANGSUNG dengan {user_name}.\n"
        "Model: DeepSeek-R1 — unggul dalam reasoning bertahap.\n\n"
        "═══ METODE ANALISIS ═══\n"
        "Untuk menjawab, identifikasi tujuan dan batasan, pisahkan fakta dari asumsi, "
        "uraikan faktor yang relevan, bandingkan alternatif bila memang ada, lalu "
        "periksa bahwa kesimpulan menjawab semua bagian pertanyaan dan tidak "
        "bertentangan dengan bukti. Sesuaikan kedalaman dengan kompleksitas tugas; "
        "jangan memaksakan daftar panjang pada pertanyaan sederhana.\n"
        "Sampaikan jawaban akhir yang ringkas dan alasan utama yang dapat diperiksa. "
        "Jangan tampilkan monolog internal atau seluruh rantai pemikiran.\n\n"
        "═══ FORMAT JAWABAN ADAPTIF ═══\n"
        "Pilih struktur sesuai jenis permintaan, bukan satu template wajib:\n"
        "- Pertanyaan sederhana/faktual: jawab langsung dan ringkas; hindari heading "
        "analisis yang tidak diperlukan.\n"
        "- Analisis atau pemecahan masalah: mulai dengan kesimpulan/ringkasan, lalu "
        "uraikan fakta dan asumsi penting, alasan utama, serta risiko/batasan yang "
        "relevan. Tambahkan solusi atau tindakan hanya jika memang diminta atau berguna.\n"
        "- Perbandingan/keputusan: gunakan kriteria yang sesuai, jelaskan trade-off "
        "utama, lalu berikan rekomendasi bila pengguna meminta pilihan.\n"
        "- Hitungan: tampilkan rumus, nilai/asumsi yang digunakan, dan hasil yang "
        "dapat diverifikasi.\n"
        "- Permintaan multi-bagian: jawab setiap bagian secara eksplisit dengan "
        "heading atau daftar seperlunya.\n"
        "Jangan memaksakan bagian akar masalah bila tidak ada diagnosis, dan jangan "
        "mengarang asumsi, risiko, atau action item demi memenuhi format.\n\n"
        "═══ ATURAN PERBANDINGAN BERDASARKAN VAULT ═══\n"
        "Jika pengguna meminta perbandingan menurut/dari catatan Vault, gunakan "
        "hanya fakta yang benar-benar ada pada konteks catatan yang ditemukan. "
        "Untuk setiap sisi perbandingan, sebutkan sumbernya. Jika bukti untuk salah "
        "satu sisi tidak ditemukan, katakan bahwa catatan yang tersedia belum cukup "
        "dan jangan mengisi celah dengan pengetahuan umum. Jangan gunakan profil, "
        "ringkasan sesi, proyek pengguna, atau dugaan sebagai bukti Vault. Pisahkan "
        "inferensi secara jelas dan hilangkan jika tidak diperlukan. Jawab ringkas "
        "sesuai permintaan; jangan menambahkan saran menyimpan/mengubah catatan "
        "atau rekomendasi proaktif kecuali diminta.\n\n"
        f"{VAULT_SYNTHESIS_POLICY}\n\n"
        f"{VAULT_FACT_CHECK_POLICY if vault_fact_check else ''}\n\n"
        f"{VAULT_RECENCY_POLICY if vault_recency else ''}\n\n"
        "═══ PRINSIP PENALARAN DEEPSEEK-R1 ═══\n"
        "- Berpikir kritis, objektif, dan teliti mengaitkan konsep lintas catatan.\n"
        "- Jika data penting tidak ada, nyatakan asumsi atau minta klarifikasi; jangan mengisi kekosongan dengan tebakan.\n"
        "- Untuk hitungan, tunjukkan rumus, nilai yang dipakai, dan hasil agar dapat diverifikasi.\n"
        f"- Sesuaikan rekomendasi secara personal untuk {user_name} hanya jika diminta "
        "atau memang relevan; jangan tambahkan kode/anjuran verifikasi pada hitungan "
        "sederhana kecuali diminta.\n"
        "- Untuk fakta umum yang tidak meminta Vault, jangan menyiratkan bahwa jawaban "
        "bersumber dari Vault atau menampilkan peringatan sitasi yang tidak relevan.\n"
        f"- {VAULT_GROUNDING_POLICY}\n"
        "- Riwayat dan ringkasan sesi bukan bukti faktual; labeli sebagai informasi percakapan yang belum diverifikasi.\n"
        "- Jika konteks kosong atau tidak menjawab pertanyaan, nyatakan keterbatasan dan jangan mengarang.\n\n"
        f"═══ KONTEKS SESI (RIWAYAT, BUKAN SUMBER FAKTA TERVALIDASI) ═══\n{effective_session_context}\n"
        f"═══ CATATAN OBSIDIAN & ASOSIASI GRAF ═══\n{context if context else '(Tidak ada catatan terkait.)'}\n"
        "══════════════════════════════════"
    )

    messages = [{'role': 'system', 'content': sys_prompt}]
    if not vault_evidence_request:
        messages.extend(chat_history[-4:] if chat_history else [])
    messages.append({'role': 'user', 'content': prompt})

    prompt_chars = sum(len(message["content"]) for message in messages)
    log_stage(
        logger,
        "reasoner",
        "prompt_preparation",
        prompt_started,
        prompt_chars=prompt_chars,
        history_messages=0 if vault_evidence_request else min(len(chat_history), 4),
    )
    inference_started = time.perf_counter()
    res = chat_with_optional_stream(
        model=config.MODEL_REASONER,
        messages=messages,
        options=config.OPTIONS_REASONER,
        keep_alive=config.KEEP_ALIVE_SPECIALIST,
    )
    log_stage(logger, "reasoner", "inference", inference_started)
    if vault_evidence_request:
        min_cited_sources = (
            2 if vault_synthesis and len(vault_context_sources(context)) > 1 else 1
        )
        answer = validate_vault_answer(
            res.message.content,
            context,
            min_cited_sources=min_cited_sources,
        )
        recency_missing = (
            missing_vault_recency_requirements(answer, context, prompt)
            if vault_recency and answer != UNGROUNDED_VAULT_ANSWER
            else []
        )
        if answer == UNGROUNDED_VAULT_ANSWER or recency_missing:
            source_labels = vault_context_sources(context)
            repair_messages = [
                *messages,
                {"role": "assistant", "content": res.message.content},
                {
                    "role": "user",
                    "content": (
                        "Tulis ulang jawaban secara ringkas dan hanya berdasarkan fakta "
                        "yang secara langsung menjawab pertanyaan. Buang jawaban "
                        "sebelumnya, jangan menyalin detail sampingan, status, tautan, "
                        "hipotesis, atau rekomendasi yang tidak diminta. Hormati semua "
                        "batasan eksplisit pengguna dan jangan menyimpulkan hal yang "
                        "secara eksplisit diminta untuk tidak ditebak. Format wajib: "
                        "tanpa heading atau daftar; buat paragraf pendek, masing-masing "
                        "satu kalimat faktual, dan akhiri setiap kalimat dengan sitasi. "
                        "Jangan meletakkan sitasi hanya di awal kalimat. Gunakan label "
                        "persis dari konteks: "
                        f"{', '.join(f'[Sumber: {source}]' for source in source_labels)}. "
                        "Kutip setiap sumber yang mendukung kalimat tersebut. Hapus "
                        "asumsi, rekomendasi, dan klaim yang tidak diperlukan. Jangan "
                        "menambahkan fakta baru. "
                        + (
                            "Cocokkan ulang setiap tanggal publikasi dengan item berita "
                            "yang sama; jangan mengambil sumber atau tanggal dari item "
                            "lain, dan sebutkan keterbatasan bila catatan pembanding tidak "
                            f"cukup. Bagian yang belum terpenuhi: {'; '.join(recency_missing)}."
                            if vault_recency else ""
                        )
                    ),
                },
            ]
            repair_started = time.perf_counter()
            repaired = chat_with_optional_stream(
                model=config.MODEL_REASONER,
                messages=repair_messages,
                options=config.OPTIONS_REASONER,
                keep_alive=config.KEEP_ALIVE_SPECIALIST,
            )
            log_stage(logger, "reasoner", "citation_repair", repair_started)
            answer = validate_vault_answer(
                repaired.message.content,
                context,
                min_cited_sources=min_cited_sources,
            )
            if vault_fact_check and answer == UNGROUNDED_VAULT_ANSWER:
                logger.warning(
                    "Reasoner could not produce a citation-validated Vault fact-check answer."
                )
                answer = VAULT_FACT_CHECK_FALLBACK
            if answer != UNGROUNDED_VAULT_ANSWER and vault_recency:
                recency_missing = missing_vault_recency_requirements(
                    answer,
                    context,
                    prompt,
                )
                if recency_missing:
                    logger.warning(
                        "Reasoner recency answer omitted required evidence fields: %s",
                        recency_missing,
                    )
                    answer = (
                        "Belum dapat menyajikan jawaban kebaruan Vault yang lengkap dan "
                        "terverifikasi karena jawaban tidak mencantumkan: "
                        + "; ".join(recency_missing)
                        + "."
                    )
            if vault_recency and (
                answer == UNGROUNDED_VAULT_ANSWER
                or "Belum dapat menyajikan jawaban kebaruan Vault" in answer
            ):
                fallback_answer = format_vault_recency_fallback(context)
                if fallback_answer:
                    answer = fallback_answer
    else:
        answer = (
            add_citation_verification_notice(res.message.content, context)
            if vault_lookup_request
            else res.message.content.strip()
        )
    log_stage(logger, "reasoner", "total", total_started)
    return answer
