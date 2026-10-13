# agents/__init__.py
from typing import List, Dict
from agents.bot_writer import run_bot_writer
from agents.bot_file_manager import run_bot_file_manager
from agents.bot_coder import run_bot_coder
from agents.bot_reasoner import run_bot_reasoner
from agents.bot_synthesizer import run_bot_synthesizer
from agents.bot_curator import run_bot_curator
from agents.bot_web import run_bot_web
from tools.tool_clean import clean_target
from agents.router import AgentRouter
from memory.session_memory import manage_history, get_session_context, load_initial_session_summaries, clear_session_history
from memory.user_profile import get_user_profile_context, update_profile_from_interaction
from memory.rules_engine import get_rules_prompt_context, detect_and_register_rule


class AITeam:
    """Orkestrator Tim Multi-Agent AI dengan Session Memory & Personalisasi Nama."""
    def __init__(self, memory_manager, user_name: str = "Pengguna"):
        self.memory = memory_manager
        self.user_name = user_name
        self.chat_history: List[Dict[str, str]] = []
        # Muat memori 48 jam terakhir dari disk jika tersedia
        self.session_summaries: List[str] = load_initial_session_summaries()

    def reset_session(self) -> str:
        """Kosongkan memori percakapan aktif untuk memulai topik baru."""
        clear_session_history()
        self.chat_history = []
        self.session_summaries = []
        return "🧹 **Sesi baru dimulai!** Riwayat obrolan sebelumnya telah dibersihkan."

    def _get_session_ctx(self) -> str:
        """Ambil context ringkasan sesi, profil pengguna, dan aturan operasional untuk diinjeksi ke prompt."""
        profile_ctx = get_user_profile_context(self.user_name)
        rules_ctx = get_rules_prompt_context()
        session_ctx = get_session_context(self.session_summaries)
        parts = [p for p in [profile_ctx, rules_ctx, session_ctx] if p.strip()]
        return "\n".join(parts)

    def _after_response(self, prompt: str, reply: str) -> None:
        """Catat ke chat_history, update profil adaptif, aturan prosedural, dan trigger summarize."""
        self.chat_history.append({'role': 'user', 'content': prompt})
        self.chat_history.append({'role': 'assistant', 'content': reply})

        # Update minat & fokus pengguna serta aturan prosedural secara dinamis
        update_profile_from_interaction(prompt, user_name=self.user_name)
        detect_and_register_rule(prompt)

        # Rolling summary otomatis dengan nama user
        self.chat_history, self.session_summaries = manage_history(
            self.chat_history, self.session_summaries, user_name=self.user_name
        )

    def record_untracked_response(self, prompt: str, reply: str) -> None:
        """Keep routed responses from handlers that do not manage conversational history."""
        if prompt.strip().casefold() in {"/new", "/reset", "/clear"}:
            return

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
        self.chat_history, self.session_summaries = manage_history(
            self.chat_history, self.session_summaries, user_name=self.user_name
        )


    def bot_writer(self, prompt: str) -> str:
        """Carl: Asisten Second Brain utama."""
        reply = run_bot_writer(
            prompt, self.memory, self.chat_history,
            session_context=self._get_session_ctx(),
            user_name=self.user_name
        )
        self._after_response(prompt, reply)
        return reply

    def bot_file_manager(self, prompt: str) -> str:
        """Tool Agent: Pembuat dan pengelola berkas di Vault."""
        reply = run_bot_file_manager(prompt, self.chat_history)
        self._after_response(prompt, reply)
        return reply

    def bot_coder(self, prompt: str) -> str:
        """Coder Agent: Spesialis skrip dan kode Python."""
        reply = run_bot_coder(prompt, self.chat_history)
        self._after_response(prompt, reply)
        return reply

    def bot_reasoner(self, prompt: str) -> str:
        """Reasoner Agent: Penalaran kritis via DeepSeek-R1."""
        reply = run_bot_reasoner(
            prompt, self.memory, self.chat_history,
            session_context=self._get_session_ctx(),
            user_name=self.user_name
        )
        self._after_response(prompt, reply)
        return reply

    def bot_synthesizer(self, prompt: str) -> str:
        """Synthesizer Agent: Sintesis ide & Knowledge Graph."""
        return run_bot_synthesizer(prompt, self.memory)

    def bot_curator(self, prompt: str) -> str:
        """Curator Agent: Kurasi & relokasi materi catatan."""
        reply = run_bot_curator(prompt, self.chat_history)
        self._after_response(prompt, reply)
        return reply

    def bot_web(self, prompt: str) -> str:
        """Web Explorer Agent: Riset web & penalaran informasi internet."""
        reply = run_bot_web(
            prompt, self.memory, self.chat_history,
            session_context=self._get_session_ctx(),
            user_name=self.user_name
        )
        self._after_response(prompt, reply)
        return reply

    def bot_cleaner(self, prompt: str) -> str:
        """Cleaner Agent: Perapihan catatan & struktur folder."""
        return clean_target(prompt.strip())

    def bot_council(self, prompt: str) -> str:
        """Council of Experts: Debat internal 3 arah (Devil's Advocate vs Coder vs Carl)."""
        from agents.bot_council import run_council_debate
        reply = run_council_debate(prompt, self.memory, user_name=self.user_name)
        self._after_response(prompt, reply)
        return reply

    def bot_goal(self, prompt: str) -> str:
        """Autonomous Goal Engine: Eksekusi tujuan mandiri bertahap (ReAct loop)."""
        from agents.autonomous_agent import AutonomousGoalEngine
        engine = AutonomousGoalEngine(self.memory, user_name=self.user_name)
        reply = engine.execute_goal(prompt)
        self._after_response(prompt, reply)
        return reply

    def bot_briefing(self) -> str:
        """Temporal Intelligence: Morning briefing dan scan deadline/tugas."""
        from tools.vault_temporal import generate_daily_briefing
        return generate_daily_briefing(user_name=self.user_name)

    def bot_sentinel(self) -> str:
        """Vault Sentinel: Audit kesehatan vault (broken links & orphan notes)."""
        from tools.vault_sentinel import audit_vault_health
        return audit_vault_health()

    def bot_sandbox(self, code: str) -> str:
        """Code Sandbox: Eksekusi Python lokal dengan proteksi & self-debug."""
        from tools.tool_sandbox import execute_and_self_debug
        return execute_and_self_debug(code)

    def bot_backup(self) -> str:
        """Frontier E: Pencadangan arsip 1-klik (.zip berstempel waktu)."""
        from tools.vault_backup import run_backup_command
        return run_backup_command()

    def bot_canvas(self, topic: str) -> str:
        """Frontier F: Generator file visual Obsidian .canvas interaktif."""
        from tools.tool_canvas import run_canvas_command
        return run_canvas_command(topic)

    def bot_heal(self) -> str:
        """Auto-Heal: Menyembuhkan seluruh masalah yang dideteksi oleh Sentinel."""
        from tools.vault_sentinel import heal_vault
        return heal_vault()

    def bot_voice(self, prompt: str) -> str:
        """Frontier C: Real-Time Voice Interface (TTS & STT)."""
        from tools.tool_voice import run_voice_command
        return run_voice_command(prompt)

    def bot_vision(self, query: str) -> str:
        """Frontier D: Multi-Modal Vision & PDF Ingestion."""
        from tools.tool_vision import run_vision_command
        return run_vision_command(query)

    def bot_serendipity(self, query: str = "") -> str:
        """Frontier G: Serendipity Engine & Cross-Domain Discovery."""
        from memory.serendipity import run_serendipity_command
        return run_serendipity_command(query, memory_manager=self.memory)

    def bot_bridge(self) -> str:
        """Frontier H: Local Multi-Device Mobile Bridge."""
        from bridge_server import run_bridge_command
        return run_bridge_command()

    def bot_calendar(self, action: str = "") -> str:
        """Frontier I: External Calendar Synchronizer (.ics)."""
        from tools.tool_calendar import run_calendar_command
        return run_calendar_command(action)

    def bot_research(self, query: str) -> str:
        """Frontier I: Research Action Ingestion (arXiv)."""
        from tools.tool_calendar import run_research_command
        return run_research_command(query)

    def bot_browser(self, target: str) -> str:
        """Frontier J: Autonomous Web Browser Agent."""
        from tools.tool_browser import run_browser_command
        return run_browser_command(target)

    def bot_evaluator(self) -> str:
        """Frontier K: Continuous Self-Evolution & Accuracy Guard."""
        from memory.evaluator import run_evaluation_command
        return run_evaluation_command(memory_manager=self.memory)

    def bot_crypto(self, command_str: str) -> str:
        """Frontier L: Zero-Knowledge Encrypted Vault Partition."""
        from tools.vault_crypto import run_crypto_command
        return run_crypto_command(command_str)

    def bot_simulator(self, scenario: str) -> str:
        """Frontier M: Multi-Agent Swarm Simulation & Scenario Forecasting."""
        from agents.swarm_simulator import simulate_swarm
        reply = simulate_swarm(scenario)
        self._after_response(scenario, reply)
        return reply

    def bot_trainer(self, args: str = "") -> str:
        """Frontier N: Local Knowledge Distillation & LoRA Self-Fine-Tuning."""
        from memory.trainer import run_trainer_command
        return run_trainer_command(args)

    def bot_galaxy(self) -> str:
        """Frontier O: Spatial 3D Knowledge Constellation (Galaxy View)."""
        return (
            "🌌 **Galaksi Pengetahuan 3D — Frontier O**\n\n"
            "Visualisasi konstelasi 3D seluruh ide dan catatan Vault Anda terbuka di tab baru.\n\n"
            "**[🚀 Buka Galaksi Pengetahuan 3D](/galaxy)](http://localhost:8000/galaxy)**\n\n"
            "*Putar dengan drag mouse · Zoom dengan scroll · Hover untuk melihat detail bintang ide*"
        )

    def bot_gemini(self, prompt: str) -> str:
        """Frontier P: Kirim pertanyaan langsung ke Google Gemini di browser."""
        from agents.gemini_browser import ask_gemini_once
        return ask_gemini_once(prompt)

    def bot_gemini_dialog(self, topic: str) -> str:
        """Frontier P: Kolaborasi dialog multi-turn interaktif Carl & Gemini di browser."""
        from agents.gemini_browser import run_carl_gemini_dialog
        return run_carl_gemini_dialog(topic, turns=3, memory_manager=self.memory)

    def bot_tutoring(self, topic: str) -> str:
        """Frontier Q: Sesi Les Privat Carl bersama Guru Gemini & Distilasi ke Obsidian Vault.
        
        Format: /les <topik>          → unlimited putaran (berhenti jika Gemini tidak merespons)
                /les <topik> <angka>  → maks <angka> putaran, lalu Carl pamit
        Contoh: /les Matematika Dasar
                /les Aljabar 5
        """
        import re
        from agents.gemini_browser import run_carl_tutoring_session

        # Cek apakah ada angka di akhir: "/les Matematika 5" → topic="Matematika", turns=5
        match = re.search(r'\s+(\d+)\s*$', topic)
        if match:
            custom_turns = int(match.group(1))
            clean_topic = topic[:match.start()].strip()
        else:
            custom_turns = 0   # 0 = unlimited
            clean_topic = topic.strip()

        return run_carl_tutoring_session(clean_topic, turns=custom_turns, memory_manager=self.memory)

    def bot_stop_tutoring(self) -> str:
        """Frontier Q: Memberhentikan sesi les privat Carl & Gemini secara manual & instan."""
        from agents.gemini_browser import request_stop_tutoring
        request_stop_tutoring()
        return "🛑 **Sesi Les Carl & Gemini telah dihentikan secara manual.**\n\nBrowser ditutup dan materi les yang terkumpul langsung diamankan ke Obsidian Vault."


__all__ = ["AITeam", "AgentRouter"]
