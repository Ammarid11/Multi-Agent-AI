# agents/router.py
import re
import logging
import time
from typing import Callable, List, Optional, Sequence, Tuple
from tools import read_file, create_file, append_file, delete_file, relocate_content, clean_target, web_search
from agents.bot_file_manager import is_contextual_save_request
from agents.bot_writer import is_named_note_summary_request
from agents.bot_router_llm import classify_intent
from agents.grounding import has_explicit_markdown_reference

from memory.rules_engine import add_rule, delete_rule, format_rules_summary
from observability import log_stage

logger = logging.getLogger(__name__)

HELP_MENU = r"""### 📖 Panduan Perintah (Slash Commands) Multi-Agent AI (Level 4 System)

| Perintah | Fungsi & Keterangan |
| :--- | :--- |
| `/new` atau `/reset` | Mulai sesi baru & bersihkan ingatan obrolan sementara |
| `/goal <tujuan>` | **Level 4:** Eksekusi tujuan mandiri bertahap (ReAct Goal Loop) |
| `/council <topik>` | **Level 4:** Sidang debat internal (Devil's Advocate vs Coder vs Carl) |
| `/briefing` | **Level 4:** Morning strategic briefing, tenggat waktu & tugas aktif |
| `/sentinel` | **Level 4:** Audit kesehatan Vault (deteksi broken links & orphan notes) |
| `/heal` | **Level 5:** Sembuhkan & bersihkan otomatis seluruh temuan Sentinel |
| `/run <kode_py>` | **Level 4:** Jalankan & uji kode Python di sandbox lokal (Self-Debug) |
| `/rule <aturan>` | **Level 4:** Ajari AI aturan operasional baru (SOP Learning) |
| `/rules` | **Level 4:** Lihat seluruh aturan operasional SOP yang aktif |
| `/web <pencarian>` | Cari Info & Riset Terkini dari Web / Internet |
| `/think <analisa>` | Penalaran Kritis & Problem Solving (DeepSeek-R1); chat biasa otomatis diarahkan ke sini bila permintaannya kompleks |
| `/coder <soal>` | Spesialis Pemrograman & Skrip Python |
| `/sintesis [topik]` | Hubungkan Ide & Knowledge Graph Catatan |
| `/canvas <topik>` | **Level 5:** Visual Canvas & Mind Map Generator interaktif (.canvas) |
| `/backup` | **Level 5:** Pencadangan arsip 1-klik (.zip berstempel waktu) & Desktop Toast |
| `/voice [teks]` | **Level 5:** Antarmuka Suara Carl (Microphone STT & Natural TTS) |
| `/vision <file>` | **Level 5:** Ekstraksi Dokumen PDF & Analisis Gambar/Screenshot |
| `/browse <url>` | **Level 5:** Autonomous Browser Agent (Scrape & arsip tabel web) |
| `/eval` | **Level 5:** Smoke benchmark retrieval memori (bukan akurasi jawaban) |
| `/unlock <pass>` | **Level 5:** Buka Brankas Rahasia AES-256 (Zero-Knowledge) |
| `/secure <judul> \| <isi>` | **Level 5:** Simpan catatan rahasia terenkripsi AES-256 |
| `/reveal <judul>` | **Level 5:** Buka & baca catatan rahasia dari Brankas AES-256 |
| `/simulate <skenario>` | **Level 5:** Multi-Agent Swarm Simulation (10 Persona Pasar) |
| `/train_adapter` | **Level 5:** Distilasi Pengetahuan Vault & Dataset LoRA Q&A |
| `/galaxy` | **Level 5:** Spatial 3D Knowledge Constellation (Galaxy View) |
| `/gemini <tanya>` | **Frontier P:** Kirim pertanyaan langsung ke Google Gemini di browser |
| `/gemini_dialog <topik>` | **Frontier P:** Dialog interaktif Carl & Google Gemini di browser |
| `/les <topik>` | **Frontier Q:** Les Privat Carl & Guru Gemini (Live Browser + Auto-Vault Sync) |
| `/read <file>` | Baca isi lengkap catatan di Vault |
| `/write <file> \| <isi>` | Buat file catatan baru di Vault |
| `/append <file/orang> \| <isi>` | Tambah / perbarui isi catatan di Vault |
| `/delete <file>` | Hapus file catatan dari Vault |
| `/move <asal> -> <tujuan>` | Pindahkan materi antar catatan |
| `/clean [file/folder]` | Audit, perbaiki format & struktur folder (bisa juga diminta dengan bahasa biasa) |

*Tips: Anda juga bisa langsung mengobrol tanpa perintah. Pertanyaan sederhana memakai jalur cepat; permintaan analisis, perbandingan, perencanaan, hitungan, atau masalah bersyarat memakai penalaran mendalam.*
"""

FAST_INTENT_PATTERNS = (
    ("web", ("cari di internet", "cari di google", "cari di web", "berita tentang", "berita hari ini", "kabar hari ini", "apa berita", "info terkini", "browsing tentang", "kabar terbaru", "cari perkembangan terbaru", "perkembangan terbaru tentang", "perkembangan terkini tentang")),
    ("coder", ("buatkan kode", "buat kode", "tulis kode", "script python", "fungsi python", "kodingan", "coding python", "bikin script", "debug kode")),
    ("think", ("analisis mendalam", "evaluasi kritis", "solusi strategis", "problem solving", "dilema antara")),
    ("file", ("buat catatan baru", "simpan ke catatan", "simpan di catatan baru", "catat di catatan baru", "simpan rangkuman", "catat rangkuman", "tulis file baru", "bikin catatan", "hapus catatan")),
    ("clean", ("rapikan vault", "audit folder", "bersihkan catatan", "rapikan folder")),
    ("canvas", ("buat canvas", "buatkan canvas", "bikin canvas", "mindmap untuk", "peta konsep")),
    ("backup", ("backup vault", "cadangkan vault", "backup catatan", "arsip vault")),
    ("heal", ("clean semuanya yang rusak", "clean semua yang rusak", "bersihkan semua yang rusak", "perbaiki semua yang rusak", "heal vault", "sembuhkan vault", "perbaiki broken links", "perbaiki tautan rusak", "perbaiki catatan terisolasi", "clean broken")),
    ("voice", ("ucapkan", "bicara", "baca dengan suara", "nyalakan suara", "mode suara")),
    ("vision", ("baca pdf", "ekstrak pdf", "analisis gambar", "baca gambar", "lihat gambar")),
    ("serendipity", ("temukan koneksi", "ide tersembunyi", "eureka", "cross domain", "serendipity")),
    ("bridge", ("akses dari hp", "koneksi hp", "scan qr", "mobile bridge", "sambungkan hp")),
    ("calendar", ("ekspor kalender", "jadwal kalender", "sinkron kalender", "jadwal deadline", "export kalender")),
    ("research", ("cari paper", "riset paper", "cari di arxiv", "paper arxiv", "makalah ilmiah")),
    ("browser", ("buka web", "buka url", "browse web", "jelajah web")),
    ("eval", ("evaluasi memori", "uji akurasi memori", "kalibrasi memori", "cek akurasi")),
    ("crypto", ("kunci brankas", "buka brankas", "simpan rahasia", "catatan rahasia", "enkripsi catatan")),
    ("simulate", ("simulasi pasar", "simulasi skenario", "ramalkan dampak", "simulasi bisnis", "swarm simulator", "simulasikan")),
    ("trainer", ("latih model", "fine tune", "fine-tuning", "train adapter", "buat dataset training", "distilasi pengetahuan")),
    ("galaxy", ("galaksi 3d", "konstelasi ide", "galaxy view", "tampilan 3d", "galaksi pengetahuan")),
)

_NATURAL_CLEAN_TRIGGER = re.compile(
    r"^(?:(?:tolong|bantu|coba|bisa|boleh|please)\s+)*"
    r"(?:rapikan|rapihkan|rapihin|merapikan|merapihkan)\b",
    re.IGNORECASE,
)
_NATURAL_CLEAN_VERB = re.compile(
    r"\b(?:rapikan|rapihkan|rapihin|merapikan|merapihkan)\b",
    re.IGNORECASE,
)
_GENERAL_QUESTION_START = re.compile(
    r"^(?:apa(?:kah)?|siapa|bagaimana|kenapa|mengapa|kapan|dimana|berapa|"
    r"adakah|benarkah|di\s+(?:dalam\s+)?(?:catatan|vault)\b|"
    r"menurut\s+(?:catatan|vault)\b)",
    re.IGNORECASE,
)
_SPECIALIST_ACTION_CUE = re.compile(
    r"\b(?:buat(?:kan)?|membuat|bikin|cari(?:kan)?|telusuri|analisis|analisa|"
    r"bandingkan|rapikan|rapihkan|rapihin|bersihkan|simpan|catat|tambah(?:kan)?|"
    r"perbarui|update|hapus|baca|"
    r"rangkum|ringkas|tulis|jalankan|perbaiki|simulasikan|jadwalkan|hubungkan|"
    r"pindah(?:kan)?|ubah|edit|ekspor|terjemahkan|kodekan)\b",
    re.IGNORECASE,
)
_EXPLICIT_FILE_ACTION_START = re.compile(
    r"^\s*(?:(?:tolong|bisa|boleh|mohon|coba|bantu)\s+)*"
    r"(?:buat(?:kan)?|bikin|simpan|catat|tambah(?:kan)?|perbarui|update|"
    r"hapus|delete|baca|bacakan|tampilkan|pindah(?:kan)?|ubah|edit)\b",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(
    r"^\s*(?:apa(?:kah)?|siapa|bagaimana|kenapa|mengapa|kapan|dimana|berapa|"
    r"adakah|benarkah)\b",
    re.IGNORECASE,
)
_NOTE_FILE_ACTION = re.compile(
    r"^\s*(?:di|dalam)\s+(?:catatan|vault)\b.*?"
    r"\b(buat(?:kan)?|bikin|simpan|catat|tambah(?:kan)?|perbarui|update|"
    r"hapus|delete|baca|bacakan|tampilkan|pindah(?:kan)?|ubah|edit)\b",
    re.IGNORECASE,
)
_QUESTION_CUE = re.compile(
    r"\b(?:apa(?:kah)?|siapa|bagaimana|kenapa|mengapa|berapa|perlukah|haruskah)\b",
    re.IGNORECASE,
)


def _is_general_question(text: str) -> bool:
    """Keep ordinary information questions off the slower LLM intent-classifier path."""
    normalized = text.strip()
    return bool(
        _GENERAL_QUESTION_START.match(normalized)
        and not _SPECIALIST_ACTION_CUE.search(normalized)
    )


def _is_explicit_file_action(text: str) -> bool:
    """Avoid file writes/reads for messages merely asking about Vault content."""
    if _EXPLICIT_FILE_ACTION_START.match(text):
        return True
    action_match = _NOTE_FILE_ACTION.match(text)
    if not action_match or _QUESTION_START.match(text):
        return False
    return not _QUESTION_CUE.search(text[:action_match.start(1)])


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match a phrase on token boundaries to avoid accidental substring routes."""
    normalized_phrase = phrase.strip()
    return bool(
        normalized_phrase
        and re.search(
            rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)",
            text,
            flags=re.IGNORECASE,
        )
    )


def _matches_any_phrase(text: str, phrases: Sequence[str]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


def _is_negated_fast_trigger(text: str) -> bool:
    negation = re.compile(r"\b(?:jangan|tidak|tak|bukan|nggak|enggak|ga)\b")
    if is_contextual_save_request(text):
        action_match = re.search(
            r"\b(?:catat|simpan|rekam|masukkan|buat(?:kan)?)\b",
            text,
            flags=re.IGNORECASE,
        )
        if action_match:
            clause_start = max(
                text.rfind(mark, 0, action_match.start()) for mark in ".!?;\n"
            )
            prefix = text[clause_start + 1:action_match.start()]
            if negation.search(prefix) and len(prefix.split()) <= 6:
                return True

    clean_match = _NATURAL_CLEAN_VERB.search(text)
    if clean_match:
        clause_start = max(text.rfind(mark, 0, clean_match.start()) for mark in ".!?;\n")
        prefix = text[clause_start + 1:clean_match.start()]
        if negation.search(prefix) and len(prefix.split()) <= 6:
            return True

    for _, phrases in FAST_INTENT_PATTERNS:
        for phrase in phrases:
            match = re.search(
                rf"(?<!\w){re.escape(phrase.strip())}(?!\w)",
                text,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            clause_start = max(
                text.rfind(mark, 0, match.start()) for mark in ".!?;\n"
            )
            prefix = text[clause_start + 1:match.start()]
            if negation.search(prefix) and len(prefix.split()) <= 6:
                return True
    return False


def _handle_write_cmd(query: str, team) -> str:
    """Helper: Eksekusi command /write atau /create."""
    if "|" in query:
        filename, content = query.split("|", 1)
        return create_file(filename.strip(), content.strip())
    return team.bot_file_manager(query)


def _handle_append_cmd(query: str, team) -> str:
    """Helper: Eksekusi command /append atau /update."""
    if "|" in query:
        target, content = query.split("|", 1)
        target_clean = target.strip()
        if target_clean.endswith(".md") or "/" in target_clean or "\\" in target_clean:
            return append_file(target_clean, content.strip())
        return append_file("03-Resources/Data Profil Orang Lain.md", content.strip(), section=target_clean)
    return team.bot_file_manager(query)


def _handle_move_cmd(query: str, team) -> str:
    """Helper: Eksekusi command /move atau /pindah."""
    if "->" in query and "|" in query:
        paths, snippet = query.split("|", 1)
        src, dst = paths.split("->", 1)
        return relocate_content(src.strip(), dst.strip(), snippet.strip())
    return team.bot_curator(query)


def _match_command(
    prompt: str,
    raw: str,
    commands: List[Tuple[Sequence[str], Callable[[str], str]]],
) -> Optional[str]:
    for prefixes, handler in commands:
        for prefix in prefixes:
            if prompt == prefix or prompt.startswith(prefix + " "):
                return handler(raw[len(prefix):].strip())
    return None


class AgentRouter:
    """
    Hybrid Router:
    - Stage 1: Fast Deterministic Pattern Matching (0 milidetik - bebas lag)
    - Stage 2: Smart LLM Classifier jika kalimat samar/ambigu
    """
    def __init__(self, team):
        self.team = team

    def _check_command(self, p: str, raw: str) -> Optional[str]:
        """Layer 1: Perintah manual slash command."""
        commands = [
            (("/help", "/menu", "/bantuan"), lambda q: HELP_MENU),
            (("/new", "/reset", "/clear"), lambda q: self.team.reset_session()),
            (("/goal", "/tujuan", "/task"), lambda q: self.team.bot_goal(q)),
            (("/council", "/sidang", "/debat"), lambda q: self.team.bot_council(q)),
            (("/canvas", "/mindmap", "/peta"), lambda q: self.team.bot_canvas(q)),
            (("/backup", "/cadangkan", "/snapshot"), lambda q: self.team.bot_backup()),
            (("/briefing", "/morning", "/fokus"), lambda q: self.team.bot_briefing()),
            (("/sentinel", "/kesehatan"), lambda q: self.team.bot_sentinel()),
            (("/run", "/sandbox"), lambda q: self.team.bot_sandbox(q)),
            (("/rules", "/aturan-aktif"), lambda q: format_rules_summary()),
            (("/rule", "/aturan"), lambda q: add_rule(q)),
            (("/delrule", "/hapusaturan"), lambda q: delete_rule(q)),
            (("/web", "/search", "/browsing", "/googling"), lambda q: self.team.bot_web(raw)),
            (("/think", "/analisis", "/evaluasi"), lambda q: self.team.bot_reasoner(q)),
            (("/coder", "/code", "/koding"), lambda q: self.team.bot_coder(q)),
            (("/sintesis", "/connect"), lambda q: self.team.bot_synthesizer(q)),
            (("/read", "/baca"), lambda q: read_file(q)),
            (("/write", "/create", "/buat"), lambda q: _handle_write_cmd(q, self.team)),
            (("/append", "/update", "/tambah"), lambda q: _handle_append_cmd(q, self.team)),
            (("/delete", "/del", "/hapus"), lambda q: delete_file(q)),
            (("/move", "/pindah", "/relokasi"), lambda q: _handle_move_cmd(q, self.team)),
            (("/clean", "/audit", "/rapikan", "/rapihkan"), lambda q: clean_target(q)),
            (("/heal", "/sembuhkan", "/perbaiki"), lambda q: self.team.bot_heal()),
            (("/voice", "/suara", "/bicara", "/speak"), lambda q: self.team.bot_voice(q)),
            (("/vision", "/lihat", "/pdf", "/gambar"), lambda q: self.team.bot_vision(q)),
            (("/serendipity", "/eureka"), lambda q: self.team.bot_serendipity(q)),
            (("/bridge", "/mobile", "/hp", "/qrcode"), lambda q: self.team.bot_bridge()),
            (("/calendar", "/jadwal", "/agenda"), lambda q: self.team.bot_calendar(q)),
            (("/arxiv", "/paper", "/riset"), lambda q: self.team.bot_research(q)),
            (("/browse", "/browser", "/webpage"), lambda q: self.team.bot_browser(q)),
            (("/eval", "/calibrate", "/accuracy"), lambda q: self.team.bot_evaluator()),
            (("/unlock", "/lock", "/secure", "/reveal", "/brankas"), lambda q: self.team.bot_crypto(raw)),
            (("/simulate", "/swarm", "/simulasi"), lambda q: self.team.bot_simulator(q)),
            (("/train_adapter", "/lora", "/train"), lambda q: self.team.bot_trainer(q)),
            (("/galaxy", "/galaksi", "/3d"), lambda q: self.team.bot_galaxy()),
            (("/gemini_dialog", "/debat_gemini"), lambda q: self.team.bot_gemini_dialog(q)),
            (("/gemini", "/tanya_gemini"), lambda q: self.team.bot_gemini(q)),
            (("/les", "/tutoring", "/belajar"), lambda q: self.team.bot_tutoring(q)),
            (("/stop", "/batal", "/berhenti", "/stop_les"), lambda q: self.team.bot_stop_tutoring()),
        ]
        return _match_command(p, raw, commands)

    def _fast_intent_check(self, p: str) -> Optional[str]:
        """
        Stage 1 Fast Heuristic (0 ms):
        Mendeteksi kata kerja / intensi yang sangat jelas tanpa perlu memanggil LLM.
        """
        # 0. Manual Stop Tutoring Fast Catch
        if p in ['stop', 'berhenti', 'batal', 'stop les', 'berhenti les', 'batal les', 'stop belajar']:
            return "stop_tutoring"

        if _NATURAL_CLEAN_TRIGGER.match(p):
            return "clean"

        for intent, phrases in FAST_INTENT_PATTERNS:
            if _matches_any_phrase(p, phrases):
                return intent

        return None

    def _route_by_intent(self, intent: str, raw: str) -> str:
        """Eksekusi agen berdasarkan intent akhir."""
        intent_map = {
            "web":         lambda: self.team.bot_web(raw),
            "think":       lambda: self.team.bot_reasoner(raw),
            "coder":       lambda: self.team.bot_coder(raw),
            "sintesis":    lambda: self.team.bot_synthesizer(raw),
            "file":        lambda: self.team.bot_file_manager(raw),
            "clean":       lambda: self.team.bot_cleaner(raw),
            "canvas":      lambda: self.team.bot_canvas(raw),
            "backup":      lambda: self.team.bot_backup(),
            "heal":        lambda: self.team.bot_heal(),
            "voice":       lambda: self.team.bot_voice(raw),
            "vision":      lambda: self.team.bot_vision(raw),
            "serendipity": lambda: self.team.bot_serendipity(raw),
            "bridge":      lambda: self.team.bot_bridge(),
            "calendar":    lambda: self.team.bot_calendar(raw),
            "research":    lambda: self.team.bot_research(raw),
            "browser":     lambda: self.team.bot_browser(raw),
            "eval":        lambda: self.team.bot_evaluator(),
            "crypto":      lambda: self.team.bot_crypto(raw),
            "simulate":    lambda: self.team.bot_simulator(raw),
            "trainer":     lambda: self.team.bot_trainer(raw),
            "galaxy":      lambda: self.team.bot_galaxy(),
            "stop_tutoring": lambda: self.team.bot_stop_tutoring(),
            "default":     lambda: self.team.bot_writer(raw),
        }
        handler = intent_map.get(intent, intent_map["default"])
        handler_started = time.perf_counter()
        try:
            return handler()
        finally:
            log_stage(
                logger,
                "router",
                "agent_execution",
                handler_started,
                intent=intent,
            )

    def route_and_execute(self, user_prompt: str) -> str:
        """Pintu masuk routing eksekusi cerdas."""
        total_started = time.perf_counter()
        prepare_for_prompt = getattr(self.team, "prepare_for_prompt", None)
        if callable(prepare_for_prompt):
            prepare_for_prompt()
        p = user_prompt.strip().lower()

        # 1. Cek Slash Command
        reply = self._check_command(p, user_prompt)
        if reply is None:
            if _is_negated_fast_trigger(p):
                reply = self._route_by_intent("default", user_prompt)
            elif is_contextual_save_request(p):
                print("\n⚡ [Fast Router] Permintaan simpan konteks percakapan terdeteksi.")
                reply = self._route_by_intent("file", user_prompt)
            elif is_named_note_summary_request(user_prompt):
                print("\n⚡ [Fast Router] Permintaan rangkuman diarahkan ke pemeriksaan sumber penuh.")
                reply = self._route_by_intent("default", user_prompt)
            elif (
                has_explicit_markdown_reference(user_prompt)
                and not _is_explicit_file_action(user_prompt)
            ):
                print("\n⚡ [Fast Router] Pertanyaan dengan sumber Vault eksplisit diarahkan ke Carl.")
                reply = self._route_by_intent("default", user_prompt)
            else:
                # 2. Stage 1: Fast Check (0 ms)
                fast_intent = self._fast_intent_check(p)
                if fast_intent:
                    print(f"\n⚡ [Fast Router] Pola terdeteksi instan: [{fast_intent}]")
                    reply = self._route_by_intent(fast_intent, user_prompt)
                elif _is_general_question(user_prompt):
                    print("\n⚡ [Fast Router] Pertanyaan informasi umum diarahkan langsung ke Carl.")
                    reply = self._route_by_intent("default", user_prompt)
                else:
                    # 3. Stage 2: Smart LLM Classifier (Cadangan untuk kalimat ambigu/bahasa gaul)
                    print("\n🔀 [Router] Menganalisis kalimat via LLM Classifier...")
                    intent = classify_intent(user_prompt)
                    if intent == "file" and not _is_explicit_file_action(user_prompt):
                        intent = "default"
                    print(f"   → Intent terdeteksi: [{intent}]")
                    reply = self._route_by_intent(intent, user_prompt)

        record_response = getattr(self.team, "record_untracked_response", None)
        if callable(record_response):
            record_response(user_prompt, reply)
        log_stage(logger, "router", "total", total_started)
        return reply
