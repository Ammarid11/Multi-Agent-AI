"""Tes Fase 0. Jalankan: python -m unittest tests.test_fase0 -v  (dari root proyek)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="carl_test_")
for key, sub in (("CARL_VAULT_PATH", "vault"), ("CARL_DB_PATH", "db"), ("CARL_STATE_PATH", "state"),
                 ("CARL_LOG_PATH", "logs"), ("CARL_WORKSPACE_PATH", "workspace")):
    os.environ[key] = os.path.join(_TMP, sub)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from core import vault_io, confirm  # noqa: E402
from core.privacy import is_sensitive, command_allowed_for_remote, intent_allowed_for_remote  # noqa: E402
from core import netguard  # noqa: E402


def fresh_vault():
    import shutil
    shutil.rmtree(config.VAULT_PATH, ignore_errors=True)
    os.makedirs(config.VAULT_PATH)
    return Path(config.VAULT_PATH)


class TestVaultIO(unittest.TestCase):
    def setUp(self):
        self.vault = fresh_vault()

    def test_safe_path_blocks_traversal_and_absolute(self):
        for bad in ("../../x.md", "..\\..\\x.md", "/etc/passwd", "C:/Windows/x.md"):
            with self.assertRaises(ValueError):
                vault_io.safe_path(bad)
        self.assertTrue(str(vault_io.safe_path("00-Inbox/a.md")).startswith(str(self.vault.resolve())))

    def test_atomic_write_snapshot_and_undo(self):
        p = self.vault / "00-Inbox" / "a.md"
        vault_io.atomic_write(p, "v1")
        vault_io.atomic_write(p, "v2")
        vault_io.atomic_write(p, "v3")
        self.assertEqual(p.read_text(), "v3")
        self.assertEqual(len(vault_io.list_snapshots(p)), 2)
        self.assertIn("dikembalikan", vault_io.undo_last("00-Inbox/a.md"))
        self.assertEqual(p.read_text(), "v2")
        vault_io.undo_last("00-Inbox/a.md")
        self.assertEqual(p.read_text(), "v1")
        self.assertFalse(list(p.parent.glob("*.tmp")))

    def test_snapshot_rotation(self):
        p = self.vault / "r.md"
        for i in range(vault_io.KEEP_SNAPSHOTS + 6):
            vault_io.atomic_write(p, f"v{i}")
            time.sleep(0.002)
        self.assertLessEqual(len(vault_io.list_snapshots(p)), vault_io.KEEP_SNAPSHOTS)

    def test_same_stem_in_different_folders_do_not_share_snapshots(self):
        a, b = self.vault / "A" / "n.md", self.vault / "B" / "n.md"
        for p in (a, b):
            vault_io.atomic_write(p, "1"); vault_io.atomic_write(p, "2")
        self.assertEqual(len(vault_io.list_snapshots(a)), 1)
        self.assertEqual(len(vault_io.list_snapshots(b)), 1)

    def test_resolve_write_path_rules(self):
        (self.vault / "A").mkdir(); (self.vault / "B").mkdir()
        (self.vault / "A" / "dup.md").write_text("x"); (self.vault / "B" / "dup.md").write_text("y")
        path, err = vault_io.resolve_write_path("dup")
        self.assertIsNone(path); self.assertIn("beberapa", err)
        path, err = vault_io.resolve_write_path("A/dup.md")
        self.assertIsNone(err)
        path, err = vault_io.resolve_write_path("baru")
        self.assertIsNone(err); self.assertEqual(path.parent, self.vault.resolve())
        path, err = vault_io.resolve_write_path("04-Secure/x.md")
        self.assertIsNone(path); self.assertIn("04-Secure", err)
        path, err = vault_io.resolve_write_path("../keluar.md")
        self.assertIsNone(path)

    def test_trash_and_restore(self):
        p = self.vault / "Z" / "hapus.md"
        vault_io.atomic_write(p, "isi")
        vault_io.move_to_trash(p)
        self.assertFalse(p.exists())
        self.assertIn("dipulihkan", vault_io.undo_last("hapus"))
        self.assertEqual(p.read_text(), "isi")

    def test_trash_not_indexed(self):
        p = self.vault / "Z" / "t.md"
        vault_io.atomic_write(p, "isi")
        trashed = vault_io.move_to_trash(p)
        self.assertFalse(vault_io.is_indexable_note(trashed))
        self.assertFalse(vault_io.is_indexable_note(self.vault / "04-Secure" / "a.md"))
        self.assertTrue(vault_io.is_indexable_note(self.vault / "00-Inbox" / "a.md"))


class TestWriteTools(unittest.TestCase):
    def setUp(self):
        self.vault = fresh_vault()
        self.outside = Path(_TMP) / "evil.md"
        if self.outside.exists():
            self.outside.unlink()

    def test_create_and_append_reject_traversal(self):
        from tools.tool_create import create_file
        from tools.tool_append import append_file, find_file_in_vault
        for name in ("../evil.md", "..\\evil.md", "../../evil", str(self.outside)):
            self.assertTrue(create_file(name, "x").startswith("❌"), name)
            self.assertTrue(append_file(name, "x").startswith("❌"), name)
        self.assertFalse(self.outside.exists())
        self.assertFalse(os.path.exists(find_file_in_vault("../evil.md")))

    def test_append_creates_snapshot_and_no_fuzzy(self):
        from tools.tool_append import append_file
        (self.vault / "03-Resources").mkdir()
        (self.vault / "03-Resources" / "Rencana Bisnis 2026.md").write_text("---\ncreated: x\n---\nisi\n")
        # nama mirip tapi tidak persis: TIDAK boleh menimpa/menambah ke file lain
        res = append_file("Rencana Bisnis.md", "- baru")
        self.assertTrue((self.vault / "Rencana Bisnis.md").exists())
        self.assertNotIn("baru", (self.vault / "03-Resources" / "Rencana Bisnis 2026.md").read_text())
        append_file("03-Resources/Rencana Bisnis 2026.md", "- tambahan")
        self.assertEqual(len(vault_io.list_snapshots(self.vault / "03-Resources" / "Rencana Bisnis 2026.md")), 1)

    def test_secure_dir_blocked_for_writes_and_reads(self):
        from tools.tool_create import create_file
        from tools.tool_read import read_file
        self.assertTrue(create_file("04-Secure/x.md", "x").startswith("❌"))
        (self.vault / "04-Secure").mkdir()
        (self.vault / "04-Secure" / "r.enc.md").write_text("cipher")
        self.assertIn("04-Secure", read_file("04-Secure/r.enc.md"))

    def test_delete_is_two_step_to_trash(self):
        from tools.tool_delete import delete_file
        from tools.confirm_actions import execute_confirmed
        p = self.vault / "N" / "x.md"
        vault_io.atomic_write(p, "isi")
        res = delete_file("N/x.md")
        self.assertTrue(p.exists()); self.assertIn("/confirm", res)
        code = res.split("/confirm ")[1].split("`")[0]
        self.assertIn("dipindahkan ke .trash", execute_confirmed(code))
        self.assertFalse(p.exists())
        self.assertIn("kedaluwarsa", execute_confirmed(code))     # sekali pakai
        self.assertIn("dipulihkan", vault_io.undo_last("x"))
        self.assertTrue(p.exists())

    def test_relocate_saves_before_removing_and_rejects_ambiguity(self):
        from tools.tool_relocate import relocate_content
        src, dst = self.vault / "src.md", self.vault / "dst.md"
        src.write_text("awal\nPINDAH INI\nakhir\n"); dst.write_text("tujuan\n")
        res = relocate_content("src.md", "dst.md", "PINDAH INI")
        self.assertIn("Berhasil", res)
        self.assertIn("PINDAH INI", dst.read_text()); self.assertNotIn("PINDAH INI", src.read_text())
        self.assertTrue(vault_io.list_snapshots(src))
        src.write_text("dua\nX\nX\n")
        before = src.read_text()
        self.assertIn("tepat satu kali", relocate_content("src.md", "dst.md", "X"))
        self.assertEqual(src.read_text(), before)

    def test_clean_markdown_content_guard(self):
        from tools.clean_markdown import _content_preserved
        orig = "---\ncreated: 1\n---\n# T\nLihat [[Catatan A]] total 12500.\n```py\nx=1\n```\n"
        self.assertIsNone(_content_preserved(orig, orig))
        self.assertIn("wikilink", _content_preserved(orig, orig.replace("[[Catatan A]]", "Catatan A")))
        self.assertIn("kode", _content_preserved(orig, orig.replace("```", "")))
        self.assertIn("angka", _content_preserved(orig, orig.replace("12500", "banyak")))

    def test_clean_folder_plan_preserves_structure_and_applies(self):
        from tools.clean_folder import plan_folder_merges, merge_and_clean_folders
        src = self.vault / "Projects" / "Alpha"
        src.mkdir(parents=True); (src / "n.md").write_text("a")
        (self.vault / "Projects" / "top.md").write_text("b")
        plan = plan_folder_merges()
        dsts = {os.path.relpath(d, config.VAULT_PATH).replace("\\", "/") for _, d, _ in plan}
        self.assertEqual(dsts, {"01-Projects/Alpha/n.md", "01-Projects/top.md"})
        dry = merge_and_clean_folders()
        self.assertTrue((src / "n.md").exists())
        self.assertTrue(all(line.startswith("📋") for line in dry))
        merge_and_clean_folders(apply=True)
        self.assertTrue((self.vault / "01-Projects" / "Alpha" / "n.md").exists())
        self.assertFalse((self.vault / "Projects").exists())

    def test_clean_all_requires_confirmation(self):
        from tools.tool_clean import clean_all_vault_files
        (self.vault / "Projects").mkdir(); (self.vault / "Projects" / "n.md").write_text("a")
        res = clean_all_vault_files()
        self.assertIn("/confirm", res)
        self.assertTrue((self.vault / "Projects" / "n.md").exists())

    def test_create_python_file_confined(self):
        from tools.tool_create_py import create_python_file
        ws = Path(config.WORKSPACE_PATH)
        for name in ("../../x.py", "/tmp/x.py", "..\\y.py", "a/b/c.py"):
            create_python_file(name, "print(1)")
        self.assertFalse((Path(_TMP) / "x.py").exists())
        self.assertFalse(Path("/tmp/x.py").exists())
        self.assertTrue((ws / "x.py").exists() or (ws / "y.py").exists() or (ws / "c.py").exists())
        for f in ws.iterdir():
            self.assertEqual(f.resolve().parent, ws.resolve())
        self.assertIn("sudah ada", create_python_file("c.py", "print(2)"))
        self.assertIn("tidak valid", create_python_file("bad;name.py", "x"))


class TestCrypto(unittest.TestCase):
    def setUp(self):
        fresh_vault()
        from tools import vault_crypto as vc
        self.vc = vc
        vc.lock_session()

    def test_roundtrip_no_plaintext_and_wrong_passphrase(self):
        vc = self.vc
        self.assertFalse(vc.unlock_session("pendek")["success"])
        self.assertTrue(vc.unlock_session("kata-sandi-kuat-1")["success"])
        vc.lock_session()
        self.assertFalse(vc.unlock_session("kata-sandi-salah-2")["success"])
        self.assertFalse(vc.is_session_unlocked())
        vc.unlock_session("kata-sandi-kuat-1")
        res = vc.save_encrypted_note("Rahasia", "isi sangat rahasia 12345")
        self.assertTrue(res["success"])
        raw = Path(res["file_path"]).read_text()
        self.assertNotIn("sangat rahasia", raw); self.assertIn("AES-256-GCM", raw); self.assertIn("v2:", raw)
        out = vc.read_encrypted_note("Rahasia")
        self.assertEqual(out["plaintext"], "isi sangat rahasia 12345")
        self.assertFalse(out["legacy_format"])

    def test_salt_is_random_per_encryption(self):
        a = self.vc.encrypt_blob("p" * 10, b"data"); b = self.vc.encrypt_blob("p" * 10, b"data")
        self.assertNotEqual(a, b)
        self.assertEqual(self.vc.decrypt_blob("p" * 10, a), b"data")
        with self.assertRaises(Exception):
            self.vc.decrypt_blob("q" * 10, a)

    def test_idle_autolock(self):
        self.vc.unlock_session("kata-sandi-kuat-1")
        old = config.VAULT_UNLOCK_IDLE_SECONDS
        try:
            config.VAULT_UNLOCK_IDLE_SECONDS = 0
            time.sleep(0.02)
            self.assertFalse(self.vc.is_session_unlocked())
            self.assertIn("terkunci", self.vc.save_encrypted_note("x", "y")["error"].lower())
        finally:
            config.VAULT_UNLOCK_IDLE_SECONDS = old

    def test_legacy_v1_readable_and_validates_passphrase(self):
        import base64, json
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=self.vc.LEGACY_SALT, iterations=100_000)
        key = base64.urlsafe_b64encode(kdf.derive(b"passphrase-lama-1"))
        token = Fernet(key).encrypt("lama".encode()).decode()
        d = Path(config.VAULT_PATH) / "04-Secure"; d.mkdir()
        (d / "Lama.enc.md").write_text(f"x\n```encrypted-carl-vault\n{token}\n```\n")
        self.assertFalse(self.vc.unlock_session("passphrase-SALAH")["success"])   # tidak membuat verifier salah
        self.assertFalse((d / self.vc.VERIFIER_NAME).exists())
        self.assertTrue(self.vc.unlock_session("passphrase-lama-1")["success"])
        out = self.vc.read_encrypted_note("Lama")
        self.assertEqual(out["plaintext"], "lama"); self.assertTrue(out["legacy_format"])

    def test_short_legacy_passphrase_can_still_unlock_but_new_must_be_long(self):
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=self.vc.LEGACY_SALT, iterations=100_000)
        token = Fernet(base64.urlsafe_b64encode(kdf.derive(b"abcd"))).encrypt(b"x").decode()
        d = Path(config.VAULT_PATH) / "04-Secure"; d.mkdir()
        (d / "L.enc.md").write_text(f"```encrypted-carl-vault\n{token}\n```\n")
        self.assertTrue(self.vc.unlock_session("abcd")["success"])      # lama (4 karakter) tetap bisa dibuka
        import shutil; shutil.rmtree(config.VAULT_PATH); os.makedirs(config.VAULT_PATH)
        self.vc.lock_session()
        self.assertFalse(self.vc.unlock_session("abcd")["success"])     # brankas baru: wajib >= 8

    def test_secure_commands_are_sensitive(self):
        for c in ("/unlock abc", "/SECURE a | b", "  /reveal x", "/lock", "/brankas"):
            self.assertTrue(is_sensitive(c), c)
        self.assertFalse(is_sensitive("halo /unlock"))
        self.assertFalse(is_sensitive("jelaskan unlock"))


class TestPolicyAndNetwork(unittest.TestCase):
    def test_remote_policy(self):
        for ok in ("halo apa kabar", "/web berita", "/read catatan", "/new"):
            self.assertTrue(command_allowed_for_remote(ok), ok)
        for bad in ("/run print(1)", "/delete x", "/write a | b", "/unlock x", "/secure a|b", "/clean all",
                    "/goal x", "/vision a.pdf", "/browse http://x", "/backup", "/heal", "/confirm abc", "/undo x"):
            self.assertFalse(command_allowed_for_remote(bad), bad)
        self.assertTrue(intent_allowed_for_remote("default"))
        for bad in ("file", "clean", "crypto", "coder", "browser", "vision", "backup", "heal"):
            self.assertFalse(intent_allowed_for_remote(bad), bad)

    def test_ssrf_validation(self):
        for bad in ("http://127.0.0.1:8000/api/chat", "http://localhost/", "http://192.168.1.10/", "http://10.0.0.1/",
                    "http://169.254.169.254/latest/meta-data", "http://[::1]/", "ftp://example.com/", "file:///etc/passwd",
                    "http://user:pw@8.8.8.8/", "http://0.0.0.0/", "http://100.64.0.1/", "http://[::ffff:127.0.0.1]/"):
            with self.assertRaises(netguard.UnsafeURL, msg=bad):
                netguard.validate_public_url(bad)
        self.assertEqual(netguard.validate_public_url("http://8.8.8.8/"), "http://8.8.8.8/")

    def test_host_and_origin_checks(self):
        allowed = {"127.0.0.1:8000", "localhost:8000"}
        self.assertTrue(netguard.host_allowed("127.0.0.1:8000", allowed))
        self.assertFalse(netguard.host_allowed("evil.example:8000", allowed))       # DNS rebinding
        self.assertTrue(netguard.origin_allowed(None, "127.0.0.1:8000"))
        self.assertTrue(netguard.origin_allowed("http://127.0.0.1:8000", "127.0.0.1:8000"))
        self.assertFalse(netguard.origin_allowed("https://evil.example", "127.0.0.1:8000"))   # drive-by
        self.assertFalse(netguard.origin_allowed("null", "127.0.0.1:8000"))

    def test_bridge_token(self):
        import bridge_server as b
        self.assertTrue(b.is_authorized("127.0.0.1", None))
        self.assertFalse(b.is_authorized("192.168.1.5", "apa-saja"))
        t = b.new_bridge_token()
        self.assertTrue(b.is_authorized("192.168.1.5", t))
        self.assertFalse(b.is_authorized("192.168.1.5", t + "x"))
        b._BRIDGE_EXPIRES = time.time() - 1
        self.assertFalse(b.is_authorized("192.168.1.5", t))

    def test_quick_memo_hardening(self):
        import bridge_server as b
        fresh_vault()
        self.assertFalse(b.save_quick_memo("x" * (config.MEMO_MAX_CHARS + 1))["success"])
        res = b.save_quick_memo("isi", title="!!!", tags=['a"b'])
        self.assertTrue(res["success"])
        text = Path(res["file_path"]).read_text()
        self.assertNotEqual(res["filename"], ".md"); self.assertIn("trust: user_mobile", text)
        self.assertIn('\\"', text)         # tag ter-escape, YAML tidak rusak


class TestSandbox(unittest.TestCase):
    def test_ok_and_blocked(self):
        from tools.tool_sandbox import execute_python_code
        self.assertIn("Sukses", execute_python_code("print(6*7)"))
        for bad in ("import subprocess\nsubprocess.run(['ls'])", "import os\nos.system('echo hi')",
                    "import socket", "eval('1+1')", "__import__('os')", "import shutil\nshutil.rmtree('.')",
                    "from urllib.request import urlopen"):
            self.assertIn("tidak diizinkan", execute_python_code(bad), bad)

    def test_isolated_cwd_and_timeout_and_output_cap(self):
        from tools.tool_sandbox import execute_python_code
        out = execute_python_code("import os\nopen('jejak.txt','w').write('x')\nprint(os.getcwd())")
        self.assertIn("carl_sandbox_", out)
        self.assertFalse(os.path.exists("jejak.txt"))
        self.assertIn("batas waktu", execute_python_code("while True: pass", timeout=2))
        self.assertIn("dipotong", execute_python_code("print('a'*50000)"))
        self.assertIn("Error Runtime", execute_python_code("import os\nprint(os.environ['HOME_RAHASIA'])"))


class TestCurriculum(unittest.TestCase):
    def setUp(self):
        fresh_vault()
        import agents.gemini_browser as gb
        self.gb = gb

    def test_long_transcript_is_never_truncated(self):
        gb = self.gb
        topic = "Aljabar"
        target = Path(config.VAULT_PATH) / "03-Resources" / f"Materi Les Carl - {topic}.md"
        target.parent.mkdir(parents=True)
        blocks = "".join(f"\n### Putaran {i}\nPENJELASAN-{i} " + ("isi " * 200) + "\n" for i in range(30))
        target.write_text(
            "---\ncreated: 2026-10-01 10:00\n---\n\n# 🎓 Materi\n\n> **Mentor:** Gemini  \n\n---\n" + blocks, encoding="utf-8")
        lessons = [{"role": "Carl", "text": "q"}, {"role": "Gemini", "text": "a"}]
        name = gb.save_or_update_curriculum_note(topic, lessons)     # ollama stub gagal -> ringkasan fallback
        out = (Path(config.VAULT_PATH) / "03-Resources" / name).read_text(encoding="utf-8")
        for i in range(30):
            self.assertIn(f"PENJELASAN-{i} ", out)
        self.assertIn("created: 2026-10-01 10:00", out)
        self.assertIn("trust: external_ai", out)
        self.assertEqual(out.count("---\n\n# 🎓"), 1)
        # idempoten: simpan ulang tidak menggandakan transkrip
        gb.save_or_update_curriculum_note(topic, lessons)
        again = (Path(config.VAULT_PATH) / "03-Resources" / name).read_text(encoding="utf-8")
        self.assertEqual(again.count("PENJELASAN-7 "), 1)
        self.assertTrue(vault_io.list_snapshots(target))

    def test_topic_change_keeps_temp_file_and_merges_it(self):
        gb = self.gb
        temp = Path(config.VAULT_PATH) / "03-Resources" / "Materi Les Carl - Awal.md"
        temp.parent.mkdir(parents=True)
        temp.write_text("---\ncreated: 2026-10-02 09:00\n---\n\n# T\n\n---\nISI-SEMENTARA-PENTING\n", encoding="utf-8")
        name = gb.save_or_update_curriculum_note("Topik Akhir", [{"role": "Gemini", "text": "x"}], source_path=str(temp))
        self.assertTrue(temp.exists())                           # tidak dihapus oleh fungsi simpan
        self.assertIn("ISI-SEMENTARA-PENTING", (temp.parent / name).read_text(encoding="utf-8"))

    def test_split_chunks_loses_nothing(self):
        text = "\n\n".join(f"para-{i} " + "x" * 1500 for i in range(20)) + "\n\n" + "y" * 15000
        chunks = self.gb._split_chunks(text, 6000)
        joined = "".join(chunks)
        for i in range(20):
            self.assertIn(f"para-{i} ", joined)
        self.assertEqual(joined.count("y"), 15000)
        self.assertTrue(all(len(c) <= 6000 + 2 for c in chunks))


class TestRouterPrivacy(unittest.TestCase):
    class FakeTeam:
        def __init__(self):
            self.recorded = []; self.calls = []
        def record_untracked_response(self, p, r): self.recorded.append((p, r))
        def bot_crypto(self, raw): self.calls.append(("crypto", raw)); return "RAHASIA-PLAINTEXT"
        def bot_web(self, raw): self.calls.append(("web", raw)); return "web ok"
        def bot_writer(self, raw): self.calls.append(("writer", raw)); return "writer ok"
        def bot_sandbox(self, code): self.calls.append(("sandbox", code)); return "dijalankan"
        def bot_file_manager(self, raw): self.calls.append(("file", raw)); return "file ok"

    def setUp(self):
        from agents.router import AgentRouter, REMOTE_DENIED
        self.team = self.FakeTeam(); self.router = AgentRouter(self.team); self.denied = REMOTE_DENIED

    def test_sensitive_never_recorded(self):
        for cmd in ("/unlock kata-sandi-123", "/secure judul | isi rahasia", "/reveal judul", "/lock"):
            self.assertEqual(self.router.route_and_execute(cmd), "RAHASIA-PLAINTEXT")
        self.assertEqual(self.team.recorded, [])
        self.router.route_and_execute("/web berita hari ini")
        self.assertEqual(len(self.team.recorded), 1)

    def test_natural_language_crypto_not_recorded(self):
        self.router.route_and_execute("tolong simpan rahasia saya di brankas")
        self.assertEqual(self.team.recorded, [])

    def test_remote_is_restricted(self):
        for cmd in ("/run print(1)", "/secure a | b", "/unlock abc", "/delete x", "/confirm abc"):
            self.assertEqual(self.router.route_and_execute(cmd, remote=True), self.denied, cmd)
        self.assertEqual(self.router.route_and_execute("tolong simpan ke catatan baru isi ini", remote=True), self.denied)
        self.assertEqual(self.team.calls, [])
        self.assertEqual(self.router.route_and_execute("/web berita", remote=True), "web ok")
        self.assertEqual(self.router.route_and_execute("/run print(1)", remote=False), "dijalankan")


class TestTeamAndWatcher(unittest.TestCase):
    def test_team_skips_sensitive_and_remote_does_not_persist(self):
        from agents import AITeam
        team = AITeam(None, persist_history=False)
        team.record_untracked_response("/unlock abc", "ok")
        team._after_response("/secure a | b", "ok")
        self.assertEqual(team.chat_history, [])
        team.record_untracked_response("halo", "hai")
        self.assertEqual(len(team.chat_history), 2)
        self.assertEqual(team.session_summaries, [])

    def test_watcher_sees_atomic_replace(self):
        from types import SimpleNamespace
        import watcher
        class M: needs_sync = False
        m = M(); h = watcher.ObsidianVaultHandler(m)
        h.on_any_event(SimpleNamespace(src_path="/v/a.md.123.tmp", dest_path="/v/a.md"))
        self.assertTrue(m.needs_sync)
        m.needs_sync = False
        h.on_any_event(SimpleNamespace(src_path="/v/07-Settings/snapshots/x.bak", dest_path=""))
        h.on_any_event(SimpleNamespace(src_path="/v/a.md.123.tmp", dest_path=""))
        self.assertFalse(m.needs_sync)

    def test_state_file_migration_and_secret_history_not_migrated(self):
        os.makedirs(config.DB_PATH, exist_ok=True)
        Path(config.DB_PATH, ".user_profile.json").write_text('{"x":1}')
        target = config.state_file(".user_profile.json")
        self.assertEqual(Path(target).read_text(), '{"x":1}')
        self.assertTrue(target.startswith(config.STATE_PATH))
        import memory.session_memory as sm
        self.assertTrue(sm.HISTORY_FILE.startswith(config.STATE_PATH))

    def test_config_aliases(self):
        self.assertEqual(config.OLLAMA_MODEL, config.MODEL_WRITER)
        self.assertEqual(config.OPTIONS_WRITER["num_ctx"], config.NUM_CTX)
        self.assertEqual(config.EVAL_OPTIONS["temperature"], 0.0)
        self.assertFalse(config.LAN_ENABLED)


class TestIntegrationTools(unittest.TestCase):
    def setUp(self):
        self.vault = fresh_vault()

    def test_clean_markdown_large_doc_snapshot_and_llm_guard(self):
        import tools.clean_markdown as cm
        big = self.vault / "01-Projects" / "besar.md"
        vault_io.atomic_write(big, "Judul\n\n" + ("baris isi penting 12345\n" * 500))
        self.assertIn("✅", cm.clean_and_refactor_file(str(big)))
        self.assertTrue(vault_io.list_snapshots(big))
        self.assertIn("12345", big.read_text())

        small = self.vault / "01-Projects" / "kecil.md"
        original = "---\ncreated: 2026-10-01 10:00\n---\n# Kecil\n" + ("Total biaya 987654 untuk [[Catatan A]].\n" * 6)
        vault_io.atomic_write(small, original)

        class R:  # model nakal: menghapus angka & tautan
            class message:
                content = "---\ncreated: x\n---\n# Kecil\n" + ("Total biaya untuk Catatan A.\n" * 6) + ("tambahan " * 40)
        orig_chat = cm.ollama.chat
        cm.ollama.chat = lambda **k: R
        try:
            res = cm.clean_and_refactor_file(str(small))
        finally:
            cm.ollama.chat = orig_chat
        self.assertIn("Pembatalan aman", res)
        self.assertEqual(small.read_text(), original)

    def test_vision_input_allowlist(self):
        import tools.tool_vision as tv
        outside = Path(_TMP) / "luar.pdf"; outside.write_bytes(b"%PDF-1.4")
        inside = self.vault / "00-Inbox" / "dalam.pdf"; inside.parent.mkdir(parents=True); inside.write_bytes(b"%PDF-1.4")
        secure = self.vault / "04-Secure" / "s.pdf"; secure.parent.mkdir(); secure.write_bytes(b"%PDF-1.4")
        self.assertIsNone(tv._find_file_path(str(outside)))
        self.assertIsNone(tv._find_file_path("/etc/passwd"))
        self.assertIsNone(tv._find_file_path(str(secure)))
        self.assertEqual(tv._find_file_path("dalam.pdf").resolve(), inside.resolve())
        self.assertIn("diizinkan", tv.ingest_pdf(str(outside))["error"])
        old = config.INPUT_ALLOWED_DIRS
        try:
            config.INPUT_ALLOWED_DIRS = [str(Path(_TMP))]
            self.assertEqual(tv._find_file_path(str(outside)).resolve(), outside.resolve())
        finally:
            config.INPUT_ALLOWED_DIRS = old

    def test_browser_refuses_internal_urls(self):
        import threading, http.server, socketserver
        import tools.tool_browser as tb
        class H(http.server.BaseHTTPRequestHandler):
            hits = 0
            def do_GET(self):
                H.hits += 1; self.send_response(200); self.end_headers(); self.wfile.write(b"<html>rahasia</html>")
            def log_message(self, *a): pass
        srv = socketserver.TCPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            res = tb.fetch_and_clean_webpage(f"http://127.0.0.1:{srv.server_address[1]}/")
            self.assertFalse(res["success"]); self.assertIn("ditolak", res["error"])
            self.assertEqual(H.hits, 0)
            self.assertFalse(tb.archive_web_page_to_vault("http://localhost:1/")["success"])
        finally:
            srv.shutdown()

    def test_sentinel_heal_snapshots_and_skips_secure(self):
        import tools.vault_sentinel as vs
        note = self.vault / "01-Projects" / "tanpa_fm.md"
        vault_io.atomic_write(note, "isi tanpa frontmatter\n")
        sec = self.vault / "04-Secure" / "x.enc.md"; sec.parent.mkdir(); sec.write_text("```encrypted-carl-vault\nv2:abc\n```")
        before = sec.read_text()
        vs.heal_vault()
        self.assertTrue(note.read_text().startswith("---"))
        self.assertTrue(vault_io.list_snapshots(note))
        self.assertEqual(sec.read_text(), before)
        self.assertNotIn("x.enc.md", vs.audit_vault_health())

    def test_scanners_skip_secure_and_trash(self):
        import tools.vault_temporal as vt
        (self.vault / "04-Secure").mkdir(); (self.vault / "04-Secure" / "a.enc.md").write_text("deadline: 2026-12-01\n- [ ] tugas rahasia")
        (self.vault / "N").mkdir(); (self.vault / "N" / "b.md").write_text("deadline: 2026-12-02\n- [ ] tugas biasa")
        found = vt.scan_deadlines_and_tasks()
        self.assertEqual([t["task"] for t in found["tasks"]], ["tugas biasa"])
        from agents.grounding import load_explicit_vault_sources
        ctx, errors, _ = load_explicit_vault_sources("baca a.enc.md", self.vault)
        self.assertEqual(ctx, "")


if __name__ == "__main__":
    unittest.main()
