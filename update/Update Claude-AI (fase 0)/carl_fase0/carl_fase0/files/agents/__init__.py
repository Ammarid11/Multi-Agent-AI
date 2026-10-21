# agents/__init__.py
from concurrent.futures import Future
import logging
import threading
from typing import List, Dict
from agents.bot_writer import is_summary_request, run_bot_writer
from agents.bot_file_manager import run_bot_file_manager
from agents.bot_coder import run_bot_coder
from agents.bot_reasoner import run_bot_reasoner
from agents.bot_reasoner import should_use_deep_reasoning
from agents.bot_synthesizer import run_bot_synthesizer
from agents.bot_curator import run_bot_curator
from agents.bot_web import run_bot_web
from tools.tool_clean import clean_target
from agents.router import AgentRouter
from memory.session_memory import (
    KEEP_RECENT,
    SUMMARIZE_THRESHOLD,
    clear_session_history,
    get_session_context,
    load_initial_session_summaries,
    submit_history_summary,
)
from memory.user_profile import get_user_profile_context, update_profile_from_interaction
from memory.rules_engine import get_rules_prompt_context, detect_and_register_rule
from core.privacy import is_sensitive

logger = logging.getLogger(__name__)


class AITeam:
    """Orkestrator Tim Multi-Agent AI dengan Session Memory & Personalisasi Nama."""
    def __init__(self, memory_manager, user_name: str = "Pengguna", persist_history: bool = True):
        self.memory = memory_manager
        self.user_name = user_name
        # False untuk sesi perangkat remote: ringkasan/profil/aturan tidak ditulis ke disk bersama.
        self.persist_history = persist_history
        self.chat_history: List[Dict[str, str]] = []
        self._pending_history_summary: Future[str] | None = None
        self._pending_summary_snapshot: List[Dict[str, str]] = []
        
        # PERBAIKAN: Inisialisasi thread lock untuk keamanan operasi asinkron
        self._lock = threading.Lock()
        
        # PERBAIKAN: Tambahkan pengaman try-except saat memuat ringkasan dari disk
        try:
            self.session_summaries: List[str] = load_initial_session_summaries() if persist_history else []
        except Exception:
            logger.exception("Gagal memuat ringkasan sesi awal dari disk. Menggunakan list kosong.")
            self.session_summaries = []

    def _finish_pending_history_summary(self) -> None:
        """Apply a completed summary safely using a thread lock before the next turn."""
        with self._lock:
            pending = getattr(self, "_pending_history_summary", None)
            if pending is None:
                return

            snapshot = self._pending_summary_snapshot
            try:
                summary = pending.result()
            except Exception:
                logger.exception("Background session summary failed.")
                summary = ""
            finally:
                self._pending_history_summary = None
                self._pending_summary_snapshot = []

            if not summary:
                return

            if self.chat_history[:len(snapshot)] != snapshot:
                logger.warning("Chat history snapshot mismatch; skipping background summary update.")
                return

            self.session_summaries = (self.session_summaries + [summary])[-3:]
            self.chat_history = self.chat_history[-KEEP_RECENT:]

    def prepare_for_prompt(self) -> None:
        """Wait for prior history compaction before a new prompt uses that history safely."""
        try:
            # Memastikan ringkasan latar belakang selesai sebelum prompt baru masuk
            self._finish_pending_history_summary()
        except Exception:
            logger.exception("Terjadi kesalahan saat mempersiapkan riwayat sesi untuk prompt baru.")

    def _manage_history_after_response(self) -> None:
        """Mengelola dan memicu ringkasan riwayat obrolan secara asinkron setelah respons."""
        self._finish_pending_history_summary()
        
        with self._lock:
            if len(self.chat_history) < SUMMARIZE_THRESHOLD:
                return

            try:
                snapshot = self.chat_history[:-KEEP_RECENT]
                print(f"\n📝 [Session Memory] Meringkas {len(snapshot)} pesan di background...")
                self._pending_summary_snapshot = [message.copy() for message in snapshot]
                self._pending_history_summary = submit_history_summary(
                    self._pending_summary_snapshot,
                    user_name=self.user_name,
                    persist=self.persist_history,
                )
            except Exception:
                logger.exception("Gagal memicu ringkasan riwayat obrolan di background.")
                self._pending_history_summary = None
                self._pending_summary_snapshot = []

    def reset_session(self) -> str:
        """Kosongkan memori percakapan aktif untuk memulai topik baru."""
        self._finish_pending_history_summary()
        if self.persist_history:
            clear_session_history()
        self.chat_history = []
        self.session_summaries = []
        return "🧹 **Sesi baru dimulai!** Riwayat obrolan sebelumnya telah dibersihkan."

    def _get_session_ctx(self) -> str:
        """Ambil context ringkasan sesi, profil pengguna, dan aturan operasional secara aman untuk diinjeksi ke prompt."""
        try:
            with self._lock:
                profile_ctx = get_user_profile_context(self.user_name)
                rules_ctx = get_rules_prompt_context()
                session_ctx = get_session_context(self.session_summaries)
                
            parts = [p for p in [profile_ctx, rules_ctx, session_ctx] if p and p.strip()]
            return "\n".join(parts)
        except Exception:
            logger.exception("Gagal merangkum konteks sesi untuk prompt.")
            return ""

    def _after_response(self, prompt: str, reply: str) -> None:
        """Catat ke chat_history secara aman, update profil adaptif, aturan prosedural, dan trigger summarize."""
        if is_sensitive(prompt):
            return
        try:
            with self._lock:
                self.chat_history.append({'role': 'user', 'content': prompt})
                self.chat_history.append({'role': 'assistant', 'content': reply})

            # Update minat & fokus pengguna serta aturan prosedural secara dinamis
            if self.persist_history:
                update_profile_from_interaction(prompt, user_name=self.user_name)
                detect_and_register_rule(prompt)

            # Rolling summary otomatis dengan nama user
            self._manage_history_after_response()
        except Exception:
            logger.exception("Terjadi kesalahan saat memproses pasca-respons (_after_response).")

    def record_untracked_response(self, prompt: str, reply: str) -> None:
        """Keep routed responses from handlers that do not manage conversational history safely."""
        if not prompt or prompt.strip().casefold() in {"/new", "/reset", "/clear"} or is_sensitive(prompt):
            return

        try:
            with self._lock:
                if (
                    len(self.chat_history) >= 2
                    and self.chat_history[-2].get("role") == "user"
                    and self.chat_history[-2].get("content") == prompt
                    and self.chat_history[-1].get("role") == "assistant"
                    and self.chat_history[-1].get("content") == reply
                ):
                    return

                self.chat_history.extend([
                    {'role': 'user', 'content': prompt},
                    {'role': 'assistant', 'content': reply},
                ])
                
            self._manage_history_after_response()
        except Exception:
            logger.exception("Gagal merekam respons tidak terlacak (untracked response).")


    def bot_writer(self, prompt: str) -> str:
        """Carl: Asisten Second Brain utama dengan validasi input dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan teks atau instruksi yang valid untuk Carl."

        try:
            if not is_summary_request(prompt) and should_use_deep_reasoning(prompt):
                print("\n⚡ [Router] Permintaan kompleks diarahkan ke penalaran mendalam.")
                return self.bot_reasoner(prompt)

            reply = run_bot_writer(
                prompt, self.memory, self.chat_history,
                session_context=self._get_session_ctx(),
                user_name=self.user_name
            )
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_writer saat memproses prompt.")
            return "❌ **Terjadi kesalahan:** Carl gagal memproses permintaan Anda saat ini."

    def bot_file_manager(self, prompt: str) -> str:
        """Tool Agent: Pembuat dan pengelola berkas di Vault dengan validasi input dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan instruksi pengelolaan berkas yang valid untuk File Manager."

        try:
            reply = run_bot_file_manager(prompt, self.chat_history)
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_file_manager saat mengelola berkas.")
            return "❌ **Terjadi kesalahan:** File Manager gagal memproses permintaan berkas Anda."

    def bot_coder(self, prompt: str) -> str:
        """Coder Agent: Spesialis skrip dan kode Python dengan validasi input dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan instruksi pembuatan atau perbaikan kode yang valid untuk Coder Agent."

        try:
            reply = run_bot_coder(prompt, self.chat_history)
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_coder saat memproses kode.")
            return "❌ **Terjadi kesalahan:** Coder Agent gagal memproses permintaan kode Anda saat ini."

    def bot_reasoner(self, prompt: str) -> str:
        """Reasoner Agent: Penalaran kritis via DeepSeek-R1 dengan validasi input dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan pertanyaan atau topik penalaran yang valid untuk Reasoner Agent."

        try:
            reply = run_bot_reasoner(
                prompt, self.memory, self.chat_history,
                session_context=self._get_session_ctx(),
                user_name=self.user_name
            )
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_reasoner saat memproses penalaran.")
            return "❌ **Terjadi kesalahan:** Reasoner Agent gagal memproses permintaan penalaran Anda saat ini."

    def bot_synthesizer(self, prompt: str) -> str:
        """Synthesizer Agent: Sintesis ide & Knowledge Graph dengan validasi input dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan topik atau ide yang valid untuk Synthesizer Agent."

        try:
            reply = run_bot_synthesizer(prompt, self.memory)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_synthesizer saat melakukan sintesis.")
            return "❌ **Terjadi kesalahan:** Synthesizer Agent gagal memproses permintaan Anda saat ini."

    def bot_curator(self, prompt: str) -> str:
        """Curator Agent: Kurasi & relokasi materi catatan dengan validasi dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan instruksi kurasi materi catatan yang valid."
        try:
            reply = run_bot_curator(prompt, self.chat_history)
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_curator.")
            return "❌ **Terjadi kesalahan:** Curator Agent gagal memproses permintaan Anda."

    def bot_web(self, prompt: str) -> str:
        """Web Explorer Agent: Riset web & penalaran informasi internet dengan pengaman."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan kueri pencarian atau topik riset web yang valid."
        try:
            reply = run_bot_web(
                prompt, self.memory, self.chat_history,
                session_context=self._get_session_ctx(),
                user_name=self.user_name
            )
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_web.")
            return "❌ **Terjadi kesalahan:** Web Explorer Agent gagal mengakses atau memproses web."

    def bot_cleaner(self, prompt: str) -> str:
        """Cleaner Agent: Perapihan catatan & struktur folder dengan validasi."""
        cleaned_prompt = prompt.strip() if prompt else ""
        if not cleaned_prompt:
            return "❌ Masukkan target atau path folder yang valid untuk dibersihkan."
        try:
            return clean_target(cleaned_prompt)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_cleaner.")
            return "❌ **Terjadi kesalahan:** Cleaner Agent gagal membersihkan target."

    def bot_council(self, prompt: str) -> str:
        """Council of Experts: Debat internal 3 arah dengan validasi dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan topik atau masalah yang valid untuk didiskusikan oleh Council of Experts."
        try:
            from agents.bot_council import run_council_debate
            reply = run_council_debate(prompt, self.memory, user_name=self.user_name)
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_council.")
            return "❌ **Terjadi kesalahan:** Council of Experts gagal memproses debat."

    def bot_goal(self, prompt: str) -> str:
        """Autonomous Goal Engine: Eksekusi tujuan mandiri bertahap (ReAct loop) dengan validasi dan penanganan galat."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan tujuan atau target otonom yang valid untuk Goal Engine."

        try:
            from agents.autonomous_agent import AutonomousGoalEngine
            engine = AutonomousGoalEngine(self.memory, user_name=self.user_name)
            reply = engine.execute_goal(prompt)
            self._after_response(prompt, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_goal saat mengeksekusi Autonomous Goal Engine.")
            return "❌ **Terjadi kesalahan:** Autonomous Goal Engine gagal memproses tujuan Anda saat ini."

    def bot_briefing(self) -> str:
        """Temporal Intelligence: Morning briefing dan scan deadline/tugas dengan pengaman."""
        try:
            from tools.vault_temporal import generate_daily_briefing
            return generate_daily_briefing(user_name=self.user_name)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_briefing.")
            return "❌ **Terjadi kesalahan:** Gagal menghasilkan ringkasan briefing harian."

    def bot_sentinel(self) -> str:
        """Vault Sentinel: Audit kesehatan vault dengan pengaman galat."""
        try:
            from tools.vault_sentinel import audit_vault_health
            return audit_vault_health()
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_sentinel.")
            return "❌ **Terjadi kesalahan:** Audit kesehatan Vault gagal dijalankan."

    def bot_sandbox(self, code: str) -> str:
        """Code Sandbox: Eksekusi Python lokal dengan validasi dan pengaman."""
        if not code or not code.strip():
            return "❌ Masukkan skrip atau kode Python yang valid untuk dieksekusi di sandbox."
        try:
            from tools.tool_sandbox import execute_and_self_debug
            return execute_and_self_debug(code)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_sandbox.")
            return "❌ **Terjadi kesalahan:** Eksekusi kode sandbox mengalami kegagalan."

    def bot_backup(self) -> str:
        """Frontier E: Pencadangan arsip 1-klik dengan pengaman galat."""
        try:
            from tools.vault_backup import run_backup_command
            return run_backup_command()
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_backup.")
            return "❌ **Terjadi kesalahan:** Proses pencadangan Vault gagal dilakukan."

    def bot_canvas(self, topic: str) -> str:
        """Frontier F: Generator file visual Obsidian .canvas dengan validasi."""
        if not topic or not topic.strip():
            return "❌ Masukkan topik yang valid untuk pembuatan Canvas."
        try:
            from tools.tool_canvas import run_canvas_command
            return run_canvas_command(topic)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_canvas.")
            return "❌ **Terjadi kesalahan:** Gagal menghasilkan file canvas."

    def bot_heal(self) -> str:
        """Auto-Heal: Menyembuhkan masalah vault dengan pengaman galat."""
        try:
            from tools.vault_sentinel import heal_vault
            return heal_vault()
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_heal.")
            return "❌ **Terjadi kesalahan:** Proses Auto-Heal gagal memperbaiki vault."

    def bot_voice(self, prompt: str) -> str:
        """Frontier C: Real-Time Voice Interface dengan validasi."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan teks atau perintah suara yang valid."
        try:
            from tools.tool_voice import run_voice_command
            return run_voice_command(prompt)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_voice.")
            return "❌ **Terjadi kesalahan:** Antarmuka suara gagal diproses."

    def bot_vision(self, query: str) -> str:
        """Frontier D: Multi-Modal Vision & PDF Ingestion dengan validasi."""
        if not query or not query.strip():
            return "❌ Masukkan path atau kueri gambar/PDF yang valid untuk Vision."
        try:
            from tools.tool_vision import run_vision_command
            return run_vision_command(query)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_vision.")
            return "❌ **Terjadi kesalahan:** Gagal memproses data Vision/PDF."

    def bot_serendipity(self, query: str = "") -> str:
        """Frontier G: Serendipity Engine & Cross-Domain Discovery dengan pengaman."""
        try:
            from memory.serendipity import run_serendipity_command
            return run_serendipity_command(query, memory_manager=self.memory)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_serendipity.")
            return "❌ **Terjadi kesalahan:** Serendipity Engine gagal menemukan korelasi."

    def bot_bridge(self) -> str:
        """Frontier H: Local Multi-Device Mobile Bridge dengan pengaman galat."""
        try:
            from bridge_server import run_bridge_command
            return run_bridge_command()
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_bridge.")
            return "❌ **Terjadi kesalahan:** Gagal menghubungkan Local Mobile Bridge."

    def bot_calendar(self, action: str = "") -> str:
        """Frontier I: External Calendar Synchronizer (.ics) dengan pengaman galat."""
        try:
            from tools.tool_calendar import run_calendar_command
            return run_calendar_command(action)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_calendar.")
            return "❌ **Terjadi kesalahan:** Sinkronisasi kalender eksternal gagal."

    def bot_research(self, query: str) -> str:
        """Frontier I: Research Action Ingestion (arXiv) dengan validasi dan pengaman."""
        if not query or not query.strip():
            return "❌ Masukkan kueri atau topik riset arXiv yang valid."
        try:
            # Sesuaikan modul impor dengan modul riset yang benar jika diperlukan
            from tools.tool_research import run_research_command
            return run_research_command(query)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_research.")
            return "❌ **Terjadi kesalahan:** Pengambilan data riset arXiv gagal diproses."

    def bot_browser(self, target: str) -> str:
        """Frontier J: Autonomous Web Browser Agent dengan validasi dan pengaman."""
        if not target or not target.strip():
            return "❌ Masukkan target URL atau instruksi browsing yang valid."
        try:
            from tools.tool_browser import run_browser_command
            return run_browser_command(target)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_browser.")
            return "❌ **Terjadi kesalahan:** Autonomous Web Browser Agent gagal berjalan."

    def bot_evaluator(self) -> str:
        """Frontier K: Continuous Self-Evolution & Accuracy Guard dengan pengaman galat."""
        try:
            from memory.evaluator import run_evaluation_command
            return run_evaluation_command(memory_manager=self.memory)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_evaluator.")
            return "❌ **Terjadi kesalahan:** Evaluasi mandiri sistem gagal dijalankan."

    def bot_crypto(self, command_str: str) -> str:
        """Frontier L: Zero-Knowledge Encrypted Vault Partition dengan validasi dan pengaman."""
        if not command_str or not command_str.strip():
            return "❌ Masukkan perintah enkripsi atau dekripsi Vault yang valid."
        try:
            from tools.vault_crypto import run_crypto_command
            return run_crypto_command(command_str)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_crypto.")
            return "❌ **Terjadi kesalahan:** Operasi Zero-Knowledge Vault gagal diproses."

    def bot_simulator(self, scenario: str) -> str:
        """Frontier M: Multi-Agent Swarm Simulation & Scenario Forecasting dengan validasi dan pengaman."""
        if not scenario or not scenario.strip():
            return "❌ Masukkan skenario simulasi swarm yang valid."
        try:
            from agents.swarm_simulator import simulate_swarm
            reply = simulate_swarm(scenario)
            self._after_response(scenario, reply)
            return reply
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_simulator.")
            return "❌ **Terjadi kesalahan:** Multi-Agent Swarm Simulation gagal dijalankan."

    def bot_trainer(self, args: str = "") -> str:
        """Frontier N: Local Knowledge Distillation & LoRA Self-Fine-Tuning dengan pengaman galat."""
        try:
            from memory.trainer import run_trainer_command
            return run_trainer_command(args)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_trainer.")
            return "❌ **Terjadi kesalahan:** Proses pelatihan model dan distilasi lokal gagal."

    def bot_galaxy(self) -> str:
        """Frontier O: Spatial 3D Knowledge Constellation (Galaxy View) dengan pengaman galat."""
        try:
            return (
                "🌌 **Galaksi Pengetahuan 3D – Frontier O**\n\n"
                "Visualisasi konstelasi 3D seluruh ide dan catatan Vault Anda terbuka di tab baru.\n"
                "**[🚀 Buka Galaksi Pengetahuan 3D](http://localhost:8000/galaxy)**\n\n"
                "*Putar dengan drag mouse • Zoom dengan scroll • Hover untuk melihat detail bintang ide*"
            )
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_galaxy.")
            return "❌ **Terjadi kesalahan:** Gagal memuat tampilan Galaksi Pengetahuan 3D."

    def bot_gemini(self, prompt: str) -> str:
        """Frontier P: Kirim pertanyaan langsung ke Google Gemini di browser dengan validasi dan pengaman."""
        if not prompt or not prompt.strip():
            return "❌ Masukkan pertanyaan yang valid untuk dikirim ke Google Gemini."
        try:
            from agents.gemini_browser import ask_gemini_once
            return ask_gemini_once(prompt)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_gemini.")
            return "❌ **Terjadi kesalahan:** Gagal terhubung atau meminta respons dari Google Gemini."

    def bot_gemini_dialog(self, topic: str) -> str:
        """Frontier P: Kolaborasi dialog interaktif multi-turn Carl & Gemini di browser dengan validasi."""
        if not topic or not topic.strip():
            return "❌ Masukkan topik dialog interaktif yang valid untuk Carl & Gemini."
        try:
            from agents.gemini_browser import run_carl_gemini_dialog
            return run_carl_gemini_dialog(topic, turns=3, memory_manager=self.memory)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_gemini_dialog.")
            return "❌ **Terjadi kesalahan:** Kolaborasi dialog interaktif Carl & Gemini mengalami kegagalan."

    def bot_tutoring(self, topic: str) -> str:
        """Frontier Q: Sesi Les Privat Carl bersama Guru Gemini dengan validasi dan pengaman."""
        if not topic or not topic.strip():
            return "❌ Masukkan topik les yang valid, contoh: `/les Matematika Dasar` atau `/les Aljabar 5`."

        try:
            import re
            from agents.gemini_browser import run_carl_tutoring_session

            match = re.search(r'(\d+)\s*$', topic)
            if match:
                custom_turns = int(match.group(1))
                clean_topic = topic[:match.start()].strip()
            else:
                custom_turns = 0
                clean_topic = topic.strip()

            return run_carl_tutoring_session(clean_topic, turns=custom_turns, memory_manager=self.memory)
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_tutoring.")
            return "❌ **Terjadi kesalahan:** Sesi les privat Carl & Gemini gagal dijalankan."

    def bot_stop_tutoring(self) -> str:
        """Frontier Q: Memberhentikan sesi les privat Carl & Gemini secara manual & instan dengan pengaman."""
        try:
            from agents.gemini_browser import request_stop_tutoring
            request_stop_tutoring()
            return "🛑 **Sesi Les Carl & Gemini telah dihentikan secara manual.**\n\nBrowser ditutup dan materi les yang terkumpul langsung diamankan ke Obsidian Vault."
        except Exception:
            logger.exception("Terjadi kesalahan pada bot_stop_tutoring.")
            return "❌ **Terjadi kesalahan:** Gagal menghentikan sesi les secara paksa."


__all__ = ["AITeam", "AgentRouter"]
