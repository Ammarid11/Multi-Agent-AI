# Fase 0 — Catatan Penerapan

Dasar: roadmap v2 (Fase 0.A–0.F). Isi paket:

- `files/` : semua file yang berubah atau baru, dengan struktur folder proyek (`agents/`, `tools/`, `memory/`, `core/`, `tests/`, root). Salin menimpa proyekmu.
- `fase0.patch` : diff yang sama (`git apply fase0.patch` dari root proyek, bila proyekmu repo git dengan struktur identik).
- `files/tests/test_fase0.py` : 44 tes.

**Folder baru wajib:** `core/` (berisi `__init__.py` kosong; buat bila belum ada setelah menyalin).

## Cara menerapkan
1. Backup proyek dan Vault (`/backup` atau salin manual).
2. Salin isi `files/` ke root proyek.
3. (Opsional) set variabel lingkungan: `CARL_VAULT_PATH`, `CARL_DB_PATH`, `CARL_STATE_PATH`, `CARL_LOG_PATH`, `CARL_WORKSPACE_PATH`, `CARL_INPUT_DIRS` (daftar folder tambahan untuk `/vision`, dipisah `;`), `CARL_LAN=1`, `CARL_NUM_CTX`.
4. Jalankan tes dari root proyek: `python -m unittest tests.test_fase0 -v`.
5. Jalankan seperti biasa. Server web: `python api_server.py` (hanya 127.0.0.1) atau `python api_server.py --lan` (HP, wajib token).
6. Ketik `/new` sekali untuk membersihkan riwayat sesi lama (bisa memuat ringkasan berisi rahasia). Berkas `.session_history.json` lokasi lama juga dihapus otomatis saat start.

## Status per butir Fase 0

| Butir | Status | Yang dikerjakan |
|---|---|---|
| 0.A API & jaringan (#34, #49, #54) | ✅ | CORS wildcard dihapus; bind default `127.0.0.1`; middleware cek `Host` (anti DNS-rebinding) dan `Origin` (anti drive-by); perangkat remote wajib token ber-TTL + allowlist endpoint (`/api/chat*`, `status`, `quick-memo`, `tts`, `reset`); router `remote=True` hanya mengizinkan intent `default/think/web/sintesis` dan slash command baca/riset; sesi remote terpisah dan tidak menulis ke disk; auto-lock brankas; `/vision` dibatasi ke Vault/folder kerja/`CARL_INPUT_DIRS`; `tool_browser` dan deep-read web memakai `safe_fetch` (anti-SSRF, validasi tiap redirect, batas ukuran); `/api/tts` POST + berkas per-hash (GET lama tetap jalan, access log disaring); rate limit dan batas ukuran memo |
| 0.B Rahasia (#3, #4) | ✅ | `/unlock /lock /secure /reveal /brankas` (dan intent natural "brankas/rahasia") tidak masuk `chat_history`, ringkasan, profil; kripto v2: scrypt + salt acak per berkas + AES-256-GCM + verifier passphrase; berkas v1 tetap terbaca; `04-secure` dikecualikan dari indeks, grounding, ringkasan, sentinel, trainer, serendipity, kalender, temporal, vision, read |
| 0.C Satu pintu file (#2, #31, #48) | ✅ | `core/vault_io.py` (`safe_path`, `resolve_write_path` tanpa fuzzy, `atomic_write`); `create_file`, `append_file`, `relocate`, `delete`, `clean_*`, sentinel heal, browser, kalender, vision, canvas, weekly review memakainya; `find_file_in_vault` tidak lagi mengembalikan path di luar Vault; `create_python_file` dikurung ke `CARL_WORKSPACE_PATH`; satu `is_indexable_note` (scanner) dipakai temporal/trainer/serendipity/kalender/evaluator |
| 0.D Tulis aman (#5, #6, #53) | ✅ | tulis atomik + snapshot 20 versi + `/undo`; hapus dua langkah (`/confirm`) ke `.trash`; `bot_curator` hanya membuat rencana lalu menunggu `/confirm`; `/clean all` dry-run + backup otomatis + struktur subfolder dipertahankan; relokasi simpan→verifikasi→ubah sumber; kurikulum les: transkrip utuh + ringkasan map-reduce, berkas sementara tidak dihapus sebelum hasil final tersimpan; guard perapihan LLM 70% + cek wikilink/blok kode/angka |
| 0.E Sandbox (#12) | 🟡 | `python -I -B`, cwd sementara, env minimal, output dibatasi, batas memori/CPU di POSIX, pemeriksaan AST (subprocess, socket, os.system, rmtree, eval, dll.) |
| 0.F Config & log (#33, #35, #36, #43) | ✅ | `OLLAMA_MODEL`, `NUM_CTX` di semua `OPTIONS_*`, `EVAL_OPTIONS`, `STATE_PATH`/`LOG_PATH`/`WORKSPACE_PATH`, `validate_startup()`, `setup_logging()` (berkas berotasi + request id) di `main.py` dan `api_server`, `main.py` shutdown aman |

## Perubahan perilaku yang perlu kamu tahu
- `/delete` hanya meminta konfirmasi; ketik `/confirm <kode>`. File masuk `.trash`; `/undo <nama>` memulihkan.
- `/write` dan `/append` memakai nama yang **persis**. Nama pendek yang sebelumnya "ditebak" ke catatan mirip kini membuat catatan baru di root Vault, atau menolak bila ada beberapa nama sama (sebutkan path penuh).
- `/clean all` menampilkan rencana dulu; eksekusi lewat `/confirm`, dengan backup `.zip` otomatis.
- Passphrase **baru** minimal 8 karakter; passphrase lama (≥1 karakter) tetap bisa membuka brankas lama. `/unlock` pertama membuat `04-Secure/.carl_verifier.json`. Catatan baru memakai format v2; catatan lama terbaca dan ditandai untuk disimpan ulang. Brankas terkunci otomatis setelah 10 menit idle.
- Sandbox menolak impor `subprocess/socket/urllib/http/requests/ctypes/importlib` dan panggilan `eval/exec/os.system/shutil.rmtree`.
- Script Python buatan Carl disimpan di folder kerja (`CARL_WORKSPACE_PATH`), bukan di direktori kerja proses.
- Berkas state (`.user_profile.json`, `.system_rules.json`, `.scheduler_state.json`) dipindah ke `STATE_PATH` (disalin otomatis dari `DB_PATH`). `.vault_mtimes.json` **sengaja tetap di `DB_PATH`** karena harus sepasang dengan database Qdrant (benchmark terisolasi memakai DB sementara).
- Catatan les Gemini kini berbentuk: frontmatter (`trust: external_ai`) + **Ringkasan** + **Transkrip Lengkap**.
- `watcher.py` kini membaca `dest_path` (tulis atomik = rename `.tmp` → `.md`); impor diperbaiki ke `memory.manager`.

## Belum tercakup / perlu tindak lanjut
- **UI web (`web/index.html`) tidak ikut diunggah.** Agar sepenuhnya memakai fitur baru: ganti panggilan `GET /api/tts?text=` menjadi `POST /api/tts` (body `{"text": ...}`). GET lama masih bekerja. Perangkat remote membuka UI lewat URL berisi `?t=<token>` (cookie diset otomatis).
- `/coder` masih rusak (#1, Fase 1). `create_python_file` sudah aman, jadi perbaikan tool-calling kini boleh dilakukan.
- Isi asli `memory/__init__.py` (#51) belum diverifikasi. Pastikan bukan salinan `tools/__init__.py`.
- Sandbox belum seisolasi container: di Windows jaringan dan akses berkas pengguna tidak bisa diblokir penuh oleh Python saja. Untuk isolasi penuh gunakan container/pengguna terbatas.
- `safe_fetch` memvalidasi DNS saat permintaan dan tiap redirect, tetapi belum mengunci koneksi ke IP hasil resolve (celah TOCTOU kecil).
- Log tahap yang mencatat kegagalan (`status=error`) baru dipasang di router; agen lain masih memakai `log_stage` jalur sukses (bagian Fase 1).
- Penulisan inkremental `_quick_append_lesson` dan berkas baru satu-kali (memo, rangkuman) belum lewat `atomic_write`; berkas hasil timpa sudah.
- Mode LAN memakai HTTP polos; gunakan hanya di jaringan tepercaya atau lewat VPN (Tailscale/WireGuard). Host LAN harus berupa IP (nama host `.local` ditolak).

## Catatan pengujian
Tes dijalankan di lingkungan tanpa Ollama/LangChain/Qdrant/FastAPI/rich (diganti stub), jadi yang teruji adalah logika Fase 0 itu sendiri: path, snapshot, undo, trash, konfirmasi, kripto, sandbox, SSRF, kebijakan remote, router, kurikulum, watcher, dan middleware API (diuji dengan stub FastAPI). Jalur yang memanggil model sungguhan (ringkasan map-reduce, perapihan LLM) hanya diuji sampai batas kegagalan/penjagaan; jalankan sekali secara manual setelah menerapkan. Tes kurikulum memakai Ollama yang gagal (stub); bila Ollama aktif di mesinmu, ringkasan akan benar-benar dibuat dan tes tetap valid.
