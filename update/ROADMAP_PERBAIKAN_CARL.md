# 🧠 Roadmap Perbaikan Carl → AI Otonom (v3, setelah Fase 0 diterapkan)

Tujuan akhir tetap sama: Carl bisa **berpikir** (agent loop), **berbicara** (voice dua arah), **menyimpan memori sendiri** (terkurasi), dan **belajar sendiri** (refleksi + evaluasi + konsolidasi).
Prinsip tetap: **otonomi naik bertahap, setiap tingkat punya pengaman.**

**Basis analisis:** seluruh file yang diunggah, dibaca statis. **Fase 0 sudah diterapkan** (paket `carl_fase0`: 46 file, 44 tes otomatis + uji middleware API lolos di lingkungan ber-stub; jalur yang memanggil model sungguhan belum diuji).
**Tidak ada di unggahan:** `web/index.html`, `web/spatial_graph.html`, `setup_vault_folder.py`, `requirements.txt`, `tests/`, `evaluation/answer_benchmark.json`, dan isi asli `memory/__init__.py` (lihat #51).

Legenda status: ✅ selesai · 🟡 sebagian · ❌ terbuka · 🆕 temuan baru di v2 · ⏳ dijadwalkan.
Kode Lampiran C/E/H.2 dari **v1 tetap berlaku** kecuali yang dikoreksi di Bagian 7. Simpan v1 sebagai `ROADMAP_PERBAIKAN_CARL_v1.md` untuk rujukan snippet.

## 📑 Daftar Isi
1. [Ringkasan](#1-ringkasan) · 2. [Yang sudah membaik](#2-yang-sudah-membaik) · 3. [Temuan baru #47–#58](#3-temuan-baru-4758)
4. [Fase 0–7 (direvisi)](#4-fase-07-direvisi) · 5. [Urutan eksekusi](#5-urutan-eksekusi) · 6. [Quick wins ≤ 1 jam](#6-quick-wins--1-jam)
7. [Patch kode baru / koreksi v1](#7-patch-kode-baru--koreksi-v1) · 8. [Matriks status #1–#58](#8-matriks-status-158) · 9. [Definisi selesai & risiko](#9-definisi-selesai--risiko)

---

## 1. Ringkasan (setelah Fase 0)

Dari 58 temuan: **✅ 14 selesai · 🟡 14 sebagian · ❌ 30 terbuka.**

**Sudah tertutup oleh Fase 0:** API tidak lagi bisa dikendalikan situs web mana pun (CORS wildcard dihapus, bind `127.0.0.1`, Host/Origin guard, token + allowlist untuk remote); rahasia tidak masuk riwayat/ringkasan; kripto v2 (scrypt + AES-256-GCM + verifier + auto-lock); semua tulis Vault lewat `core/vault_io.py` (tanpa fuzzy, atomik, snapshot, `/undo`); hapus dua langkah ke `.trash`; `/clean all` dry-run + backup; kurikulum les tidak lagi terpangkas; `create_python_file` dikurung; anti-SSRF di browser/web search; `/vision` dibatasi; `OLLAMA_MODEL`, `num_ctx`, `STATE_PATH`, logging berkas.

**Sisa paling mendesak (Fase 1):**
1. **`/coder` masih rusak** (#1, `tools=` → TypeError). Sekarang aman diperbaiki karena #48 sudah selesai.
2. **`/arxiv` rusak** (#14, impor `tools.tool_research`) dan arXiv fallback masih menulis "paper" palsu (#55).
3. **`memory/__init__.py`** belum diverifikasi (#51); impor di `watcher.py` sudah diperbaiki.
4. **`<think>` tidak di-strip** (#22) dan **streaming menembus validator grounding** (#47).
5. **Dua titik masuk** (`main.py` dan `api_server.py`) memegang Qdrant dan scheduler sendiri-sendiri (#39, #50).

**Tindak lanjut Fase 0 yang tersisa:** lihat daftar "Sisa Fase 0" di Bagian 4.

## 2. Yang sudah membaik

Tidak mengubah status temuan lama, tetapi fondasinya sudah ada dan sebaiknya dipertahankan:

- `tool_read`, `tool_delete`, `clean_markdown._resolve_markdown_file`: path eksak, guard di luar Vault, duplikat nama ditolak.
- `clean_markdown`: dokumen >8000 karakter diproses deterministik tanpa LLM; `_write_and_verify`; guard hasil terpotong.
- `bot_file_manager`: simpan-rangkuman terverifikasi; `delete` dari tafsiran LLM diblokir; baca ambigu minta path penuh.
- `manager.index_vault`: menolak `recreate` koleksi yang gagal dimuat; retrieval turun ke keyword/graph dengan peringatan eksplisit.
- `vault_indexer`: peta Vault di-cache dengan tanda tangan direktori.
- `autonomous_agent`: validasi rencana, hitungan berhasil/gagal, laporan jujur.
- `scheduler`: briefing harian persisten + lock.
- `api_server`: antrean job dengan polling, satu worker (aman untuk VRAM), streaming parsial.
- `answer_evaluator` + `evaluate_answers.py`: benchmark jawaban dengan mode vault terisolasi dan lembar review manusia.
- `grounding.py`: validator sitasi, kebijakan fakta vs inferensi.
- `observability.py`: modul log ada (belum aktif, #36).

## 3. Temuan Baru (#47–#58)

### 🔴 Kritis
**#47 Streaming menembus validator grounding.** `api_server._run_chat_job` mengisi `partial_reply` dari token mentah. Untuk jalur Vault-evidence, `bot_writer`/`bot_reasoner` memvalidasi sitasi *setelah* generasi dan bisa me-*repair*. Pengguna melihat draf yang belum divalidasi, dan draf + repair tersambung di `stream_parts`. Jawaban terverifikasi hanya muncul di akhir. Blok `<think>` (#22) juga ikut ter-stream.

**#48 `create_python_file` menulis ke path bebas.** `open(file_name, "w")` menerima path absolut atau relatif apa pun (CWD). Hari ini aman karena `/coder` crash (#1). Begitu `tools=` diperbaiki, model bisa menimpa file sembarang. Jangan perbaiki #1 sebelum fungsi ini dikurung.

**#51 `memory/__init__.py` mencurigakan (perlu konfirmasi).** `__init-memory__.py` identik dengan `__init-tools__.py` (header `# tools/__init__.py`, daftar impor tools). Jika itu isi `memory/__init__.py`, maka `watcher.py` (`from memory import MemoryManager`) gagal dan `main.py` crash saat `from watcher import start_auto_sync`. Perbaikan paling murah: `from memory.manager import MemoryManager` di `watcher.py`, dan kosongkan/benarkan `memory/__init__.py`.

### 🟠 Penting
**#49 State global lintas klien.** Satu `AITeam` global dipakai semua klien: riwayat chat, ringkasan sesi, profil, dan status `/unlock` (`_active_passphrase`) bercampur antara PC dan HP. Setelah pemilik `/unlock`, perangkat mana pun di Wi-Fi bisa `/reveal`. `/api/tts` memakai GET dengan teks di URL (masuk access log) dan satu berkas bersama `carl_voice.mp3` (balapan antar permintaan).

**#50 Dua titik masuk, server tanpa watcher.** `main.py` (CLI) dan `api_server.py` masing-masing membuat `MemoryManager` + scheduler, padahal Qdrant lokal hanya boleh satu proses (#39 dikonfirmasi). `api_server` juga tidak memanggil `start_auto_sync`, jadi catatan yang diubah setelah server menyala tidak ter-indeks sampai restart. `main.py` menampilkan banner "Sidecar di :8000" tetapi tidak menjalankannya.

**#52 Konten eksternal terindeks sebagai bukti Vault tanpa label trust.** `03-Resources/Web`, `Riset` (arXiv), `Materi Les Carl - …` (Gemini), PDF, memo HP, semuanya masuk indeks. Validator sitasi hanya memeriksa bahwa `[Sumber: …]` ada, jadi klaim dari web/LLM tampil seperti fakta Vault terverifikasi.

**#53 Operasi destruktif tanpa jaring pengaman.**
- `delete_file` memakai `os.remove` permanen (tidak ada snapshot/trash, `/undo` tidak bisa membantu); `/hapus` dan `/delete` langsung mengeksekusi tanpa konfirmasi.
- `bot_curator` menjalankan `relocate_content` langsung dari JSON model, dengan resolusi file fuzzy.
- `/clean all` → `merge_and_clean_folders` meratakan subfolder ke folder PARA (tabrakan nama di-rename `_1`) tanpa dry-run, sehingga wikilink berbasis path ikut rusak.

**#54 Pembacaan path/URL internal lewat tool.** `tool_vision._find_file_path` menerima path absolut mana pun (dan menyalinnya ke Vault); `tool_browser.fetch_and_clean_webpage` menerima URL apa pun, termasuk `http://localhost:8000/...` dan IP privat, tanpa batas ukuran `response.read()`. Dikombinasikan dengan #34, perangkat lain bisa memakainya lewat `/api/vision` dan `/api/browse`.

**#55 Catatan fabrikasi dan bug kalender.**
- `search_arxiv_papers` saat jaringan gagal mengembalikan "paper" palsu (`Riset Sintetis: …`, `local-fallback`) yang lalu **ditulis ke Vault** sebagai Literature Note. Seharusnya error.
- `scan_vault_deadlines`: pola ke-3 (`📅 tanggal`) mengenai baris tugas lebih dulu, jadi pola ke-4 (`- [ ] teks 📅 tanggal`) tidak pernah tercapai dan ringkasan tugas hilang.
- ICS: `DTEND` sama dengan `DTSTART` untuk event sehari penuh (standar meminta hari berikutnya); `;` dan `\` tidak di-escape; tanpa line folding.

### 🟡 Minor
**#56 Dependensi tidak sinkron.** `api_server` mengimpor `agents.gemini_browser` (Playwright) saat start, sehingga server mati bila Playwright tidak ada. `check_environment` hanya memeriksa 8 paket (tidak ada fastapi, uvicorn, playwright, bs4, requests, qrcode, edge-tts, cryptography, pypdf, pillow, speechrecognition, psutil). `requirements.txt` belum bisa diverifikasi. `check_environment` mencari `duckduckgo_search` sementara kode memilih `ddgs`. f-string berisi backslash di `tool_vision`/`gemini_browser` mensyaratkan Python ≥ 3.12.

**#57 Evaluasi belum tersambung.**
- `evaluate_answers.py` hanya CLI dan hanya menguji `run_bot_writer`, bukan jalur router (reasoner, web, dll.). `/eval` masih hanya `memory/evaluator.py` (retrieval sintetis).
- `answer_fn` yang melempar exception menghentikan seluruh benchmark.
- Opsi model di benchmark = `OPTIONS_WRITER` (temperature 0.3), tidak deterministik (#45).
- `memory/evaluator.py` tidak memakai `is_indexable_note`, jadi bisa memilih target yang memang tidak diindeks.

**#58 `swarm_simulator` menyajikan "Estimasi Probabilitas Sukses: X%"** dari model 7B tanpa dasar data, plus 10 panggilan LLM berurutan. Ganti dengan label "simulasi perspektif, bukan prediksi", hapus angka probabilitas.

---

## 4. Fase 0–7 (direvisi)

### Fase 0 — Fondasi Aman ✅ (diterapkan; sisa tindak lanjut di bawah)

**0.A Amankan API & jaringan (#34, #49, #54)** ✅
- [x] `CORSMiddleware` wildcard dihapus; bind default `127.0.0.1`; LAN hanya lewat `--lan`/`CARL_LAN=1` + token ber-TTL (S2).
- [x] Middleware: validasi `Host` (anti DNS-rebinding) dan `Origin` (anti drive-by lintas-situs).
- [x] Klien non-lokal: token + allowlist endpoint (`/api/chat*`, `status`, `quick-memo`, `tts`, `reset`); sisanya 403.
- [x] Router `remote=True`: hanya intent `default/think/web/sintesis` dan slash command baca/riset.
- [x] Sesi remote terpisah (`AITeam(persist_history=False)`): riwayat/profil/aturan tidak ditulis ke disk bersama. Brankas: auto-lock 10 menit; `/api/crypto` dan perintah brankas ditolak untuk remote.
- [x] `tool_vision`: hanya Vault, folder kerja, `CARL_INPUT_DIRS`; `tool_browser` dan deep-read web: `safe_fetch` (anti-SSRF, validasi tiap redirect, batas ukuran).
- [x] `/api/tts`: POST + berkas per-hash (GET lama dipertahankan, access log disaring); rate limit dan batas ukuran memo.

**0.B Rahasia (#3, #4)** ✅
- [x] `core/privacy.is_sensitive` di router dan `AITeam` (termasuk intent natural "brankas/rahasia"); berkas riwayat lama dibersihkan saat start.
- [x] Kripto v2: scrypt, salt acak per berkas, AES-256-GCM, verifier passphrase; format v1 tetap terbaca; passphrase baru ≥ 8 karakter.
- [x] `04-secure` dikecualikan dari indeks, grounding (explicit/recency), ringkasan, sentinel, trainer, serendipity, kalender, temporal, vision, dan `read_file`.

**0.C Satu pintu akses file (#2, #31, #48)** ✅
- [x] `core/vault_io.py`: `safe_path`, `resolve_write_path` (tanpa fuzzy; ambigu ditolak), `atomic_write`. Dipakai `create_file`, `append_file`, `relocate`, `delete`, `clean_*`, sentinel heal, browser, kalender, vision, canvas, weekly review.
- [x] `find_file_in_vault` (baca-lunak) tidak lagi mengembalikan path di luar Vault.
- [x] `create_python_file` dikurung ke `CARL_WORKSPACE_PATH` (S4).
- [x] `is_indexable_note` (scanner) dipakai temporal, trainer, serendipity, kalender, evaluator. 🟡 Belum: sentinel (hanya blokir `04-secure`, sengaja karena butuh target link), weekly review, resolver ringkasan.

**0.D Penulisan aman + jaring pengaman (#5, #6, #53)** ✅
- [x] Atomik + snapshot 20 versi + `/undo`; hapus dua langkah (`/confirm`) ke `.trash`; `bot_curator` membuat rencana lalu menunggu `/confirm`.
- [x] `/clean all`: dry-run + backup otomatis + struktur subfolder dipertahankan.
- [x] `relocate_content`: simpan → verifikasi → ubah sumber. Kurikulum les: transkrip utuh + ringkasan map-reduce, berkas sementara tidak dihapus sebelum hasil final tersimpan (S5).
- [x] `clean_markdown` (≤ 8000 karakter): guard 70% + cek wikilink/blok kode/angka.

**0.E Sandbox (#12)** 🟡
- [x] `python -I -B`, cwd sementara, env minimal, pemeriksaan AST, batas output; batas memori/CPU di POSIX.
- [ ] Container/pengguna terbatas tanpa jaringan dan tanpa akses Vault (di Windows jaringan dan berkas pengguna belum bisa diblokir penuh oleh Python saja).

**0.F Konfigurasi & observabilitas (#33, #35, #36, #43)** ✅/🟡
- [x] `config.py`: `OLLAMA_MODEL`, `NUM_CTX` di semua `OPTIONS_*`, `EVAL_OPTIONS`, `STATE_PATH`/`LOG_PATH`/`WORKSPACE_PATH`, override env, `validate_startup()`. `.vault_mtimes.json` **sengaja tetap di `DB_PATH`** (harus sepasang dengan Qdrant; benchmark terisolasi memakai DB sementara).
- [x] `setup_logging()` aktif di `main.py` dan `api_server` (berkas berotasi + request id). 🟡 Status `error` per tahap baru di router.

**Sisa Fase 0 (tindak lanjut)**
- [ ] UI web (`web/index.html`): pindah ke `POST /api/tts`; buka lewat `?t=<token>` untuk HP. Kirim file UI agar bisa disesuaikan.
- [ ] Isolasi sandbox penuh (0.E).
- [ ] Penulisan inkremental/berkas baru yang belum lewat `atomic_write`: `_quick_append_lesson`, `_save_previous_response`, memo, `generate_training_dataset`.
- [ ] `with stage(...)` dipasang di writer, reasoner, retrieval agar kegagalan tahap tercatat.
- [ ] `safe_fetch`: kunci koneksi ke IP hasil resolve (tutup celah TOCTOU kecil).
- [ ] `is_indexable_note` tunggal untuk weekly review dan resolver ringkasan.
- [ ] Verifikasi `memory/__init__.py` (#51).

### Fase 1 — Bug Kritis (agen harus benar-benar jalan)
- [ ] **#1** `/coder`: #48 sudah selesai, jadi tool-calling (C.1 v1 + S3 `tools=`) kini aman diaktifkan. Opsi tercepat: hapus `tools=` dan `coder_tools` dulu.
- [ ] **#14** `bot_research`: `from tools.tool_calendar import run_research_command`. **#55**: arXiv gagal → error, bukan paper palsu.
- [x] **#51** `watcher.py` memakai `from memory.manager import MemoryManager` (selesai, plus membaca `dest_path` untuk tulis atomik). [ ] Masih: verifikasi isi `memory/__init__.py`.
- [x] **#33** alias `OLLAMA_MODEL` (selesai). [ ] Masih: jangan telan `AttributeError` per persona di swarm.
- [ ] **#50/#39** Satu proses utama: `api_server` memulai memori + watcher + scheduler lewat lifespan; `main.py` jadi klien tipis (`/api/chat-jobs`) atau memakai kunci instans tunggal (`STATE_PATH/carl.lock`).
- [ ] **#47** Gerbang streaming (S3): jalur tervalidasi tidak di-stream; `partial_reply` hanya dari jalur bebas.
- [ ] **#22** `strip_think` terpusat (C.9 v1) di writer, reasoner, synthesizer, web, council. Cek versi Ollama (`message.thinking` vs `<think>` inline); tetap strip defensif.
- [ ] **#7** Sentinel: resolusi link berbasis path **dan** nama dasar; master index diseragamkan ke `07-Settings/Master_Index.md`; hapus `[[00-Index|…]]` (clean_markdown), `[[Rencana Bisnis 2026]]` (tool_calendar), `[[Master Index - Brain AI Memory]]` (heal); skor jangan di-floor 50.
- [ ] **#8–#11, #16, #27, #28** seperti v1. Tambahan #16: reindex yang dipicu watcher jangan jalan di jalur query (debounce + thread latar); #10: `chat_history = chat_history[len(snapshot):]` dan `prepare_for_prompt` jangan memblokir (`done()`).
- [ ] **#9** hapus `"bicara"` dari pola `voice`.
- [ ] **#25** `tool_web_search`: `date=""` bila kosong.

**Uji penerimaan:** `tests/` minimal (Lampiran E v1) + uji baru: Origin asing ditolak, `/run` dari klien remote ditolak, `create_python_file("../../x.py")` ditolak, `/secure` tidak masuk `chat_history` maupun `.session_history.json`, curriculum 30 putaran tidak kehilangan isi.

### Fase 2 — Retrieval yang Andal
Seperti v1 (#15 ambang skor, #17 graf, #18 chunking, #19 BM25, #23 anggaran konteks), dengan penyesuaian:
- [ ] **#18** `split_markdown_file` jangan menelan exception: log file yang gagal. ID chunk memuat indeks chunk (dua chunk dengan 120 karakter awal sama dalam satu berkas saat ini saling menimpa di Qdrant).
- [ ] **#52 Trust per folder (S6):** `03-Resources/Web` → `external_web`, `03-Resources/Riset` → `external_paper`, `Materi Les Carl - *` → `external_ai`, memo mobile → `user_mobile`, lainnya → `user`. Simpan sebagai metadata chunk. `grounding` menambah catatan "sumber eksternal, belum diverifikasi" bila sitasi mengarah ke trust ≠ `user`.
- [ ] Hapus `'ammar'` dari `STOPWORDS`.
- [ ] Baseline: jalankan `evaluate_answers.py --isolated-vault` dengan `EVAL_OPTIONS` sebelum menyentuh Fase 3.

### Fase 3 — Memori Otonom
Tidak berubah (lihat v1 §3 dan C.10), dengan penegasan dari kode saat ini:
- `user_profile.update_profile_from_interaction` dan `rules_engine.detect_and_register_rule` masih berbasis regex dan **langsung aktif**; ganti dengan staging + konfirmasi.
- `.session_history.json`, `.user_profile.json`, `.system_rules.json` perlu pindah ke `STATE_PATH` dan terpisah per klien.
- Memori otonom wajib lewat filter sensitif (0.B), kutipan asli pengguna, dan label trust (Fase 2).

### Fase 4 — Berpikir Otonom
- [ ] **#24 (🟡)** `AutonomousGoalEngine` sudah memvalidasi rencana dan melaporkan jujur. Yang masih kurang: replan saat langkah gagal; **blokir `write_file` bila tidak ada langkah riset berhasil** (saat ini jalan dengan konteks kosong karena `memory.get_summary` tidak ada dan `accumulated_context` kosong); anggaran konteks per langkah menggantikan `[:1800]`; batas langkah/waktu (rencana "2–4 langkah" tidak ditegakkan); verifikasi tujuan; `_tool_reported_success` jangan menganggap "✅ … perapihan belum tuntas" sebagai sukses penuh.
- [ ] Registry tool + `risk` (C.11 v1). `/stop` saat ini hanya menghentikan sesi les (`request_stop_tutoring`); perluas ke kill switch global `STOP_ALL`.
- [ ] Critic memakai `grounding.py`. `quality_gate.py` bukan critic (hanya merapikan fence/tag/heading); ganti namanya agar tidak menyesatkan.
- [ ] **#20 (bertambah)** Pindahkan ke fixture tes: `_build_explicit_erd_note_answer`, `nasa_official_requested`, "Ammar" (`bot_council`, stopwords), "Dini" (`bot_file_manager`), `_verify_displayed_arithmetic` dan `_GENERAL_CALCULATION_CUES` (ganti dengan tool kalkulator, bukan perbaikan regex pada keluaran), `format_vault_recency_fallback` (terikat format satu catatan), hack `"ilai"/"ama"/"omor"` di `fix_unfenced_code_blocks`.
- [ ] **#21** skor kompleksitas menggantikan regex ("terbaru", "rencana", "dan/dengan" bukan sinyal penalaran).
- [ ] **#58** simulasi swarm: hapus angka probabilitas, sebut "perspektif", urutan panggilan paralel/ringkas.

### Fase 5 — Belajar Sendiri
- [ ] **#57** Sambungkan `evaluate_answers` ke `/eval answers`; uji jalur router (bukan hanya writer); catat error per kasus; kasus *unanswerable* juga cek klaim karangan; `EVAL_OPTIONS` (temperature 0, seed); riwayat skor `07-Settings/eval_history.jsonl`; `memory/evaluator.py` pakai `is_indexable_note`.
- [ ] Gerbang evaluasi (H.2-F v1): set uji ≥ 30 kasus buatan manusia, 3 kali jalan, CI tidak turun.
- [ ] Materi les Gemini bertanda `external_ai`. Ganti Playwright (menyamarkan `navigator.webdriver`) dengan Gemini API resmi. `/les <topik> 3` ambigu (angka di akhir selalu dibaca jumlah putaran, mis. "Windows 10"); pakai flag `--turns`.
- [ ] `trainer.py` (#29): parser JSON, `num_predict`, filter `trust: user`, kecualikan `04-Secure`, `.trash`, templates.

### Fase 6 — Berbicara
Seperti v1 (C.14). Tambahan: `/api/tts` per permintaan dan POST (0.A); jangan ucapkan balasan `/reveal`; perintah sensitif lewat suara dinonaktifkan.

### Fase 7 — Tingkat Otonomi, Izin, Audit
Seperti v1 + butir yang kini konkret:
- [ ] Matriks izin per klien (lokal vs remote) = allowlist di 0.A.
- [ ] Log audit tidak boleh memuat argumen rahasia; masker `/unlock`, `/secure`.
- [ ] `tool_browser`: SSRF guard (0.A) dan simpan dengan nama unik (saat ini `Web - <judul>.md` ditimpa diam-diam).
- [ ] Rate limit `/api/quick-memo` dan batas `MAX_MEMO_CHARS`; frontmatter memo pakai `json.dumps`.

---

## 5. Urutan Eksekusi

**Selesai: Fase 0** (0.A–0.D, 0.F; 0.E sebagian). Jalankan `python -m unittest tests.test_fase0 -v` setiap selesai menerapkan perubahan.

**Berikutnya — Hari 1 (quick wins sisa, Bagian 6):** QW2 (`/coder`), QW3 (`/arxiv`), QW6, QW7, QW8, QW9, QW10, lalu verifikasi `memory/__init__.py`.

**Minggu 1 — Fase 1**
1. `#22` `strip_think` terpusat; `#47` gerbang streaming (S3); `#1` tool-calling dengan registry yang sudah aman.
2. `#50/#39` satu proses utama (server memulai memori + watcher + scheduler; `main.py` jadi klien tipis atau memakai kunci instans tunggal).
3. `#7`, `#8`–`#11`, `#16`, `#27`, `#28`, `#25`, `#55`.
4. Sisa Fase 0: UI `tts`, `with stage(...)`, penulisan inkremental lewat `atomic_write`.

**Minggu 2 — Stabil:** tes tambahan untuk butir Fase 1, baseline `/eval` + `evaluate_answers` dengan `EVAL_OPTIONS` (hubungkan `EVAL_OPTIONS` ke `evaluate_answers.py`).
**Minggu 3 — Retrieval + trust** → Fase 2 (baca `trust` di indexer, S6).
**Minggu 4–5 — Memori otonom** → Fase 3.
**Minggu 6–7 — Berpikir** → Fase 4.
**Minggu 8+ — Belajar & bicara** → Fase 5–6; Fase 7 paralel.

Aturan lama berlaku: jangan lompat ke Fase 5 sebelum Fase 0–3 stabil.

## 6. Quick Wins ≤ 1 jam

Status: QW1, QW4, QW5 ✅ sudah diterapkan di Fase 0. QW2, QW3, QW6–QW10 masih terbuka.

```python
# QW1 ✅ SELESAI di Fase 0 — config.py (memperbaiki /simulate dan /train_adapter)
OLLAMA_MODEL = MODEL_WRITER

# QW2 agents/bot_coder.py: hapus tools=coder_tools dan coder_tools sementara (/coder kembali jalan)

# QW3 agents/__init__.py bot_research
from tools.tool_calendar import run_research_command

# QW4 ✅ SELESAI di Fase 0 — watcher.py
from memory.manager import MemoryManager

# QW5 ✅ SELESAI di Fase 0 — api_server.py: bind 127.0.0.1, CORS dihapus, guard Host/Origin (S2)

# QW6 router.py FAST_INTENT_PATTERNS["voice"]: buang "bicara", sisakan frasa imperatif eksplisit

# QW7 manager.search_context: sinkronisasi tidak boleh menjatuhkan query
if self.needs_sync:
    try:
        self.index_vault(silent=True)
    except Exception:
        logger.exception("Sinkronisasi indeks gagal; query tetap dilanjutkan.")
    finally:
        self.needs_sync = False   # percobaan ulang lewat perubahan berkas berikutnya

# QW8 tool_calendar.scan_vault_deadlines: pindahkan pola tugas ke urutan pertama
date_patterns = [
    r"- \[[ xX]\]\s*(.+?)\s*📅\s*(\d{4}-\d{2}-\d{2})",   # harus sebelum pola 📅 polos
    r"(?:deadline|tenggat|due|target)[\s:]+(\d{4}-\d{2}-\d{2})",
    r"#deadline\s+(\d{4}-\d{2}-\d{2})",
    r"📅\s*(\d{4}-\d{2}-\d{2})",
]

# QW9 tool_calendar.search_arxiv_papers: ganti blok except fallback palsu
    except Exception:
        return []        # ingest_research_paper sudah menangani "tidak ditemukan"

# QW10 bot_router_llm.classify_intent: bersihkan tanda baca label
intent = re.sub(r"[^a-z_]", "", words[0]) if words else "default"
```

---

## 7. Patch Kode Baru / Koreksi v1

### S2. Pengamanan `api_server.py` ✅ diterapkan (Fase 0; menggantikan H.2-D v1 pada bagian server)

```python
# api_server.py: hapus app.add_middleware(CORSMiddleware, ...) lalu tambahkan:
from fastapi import Request
from bridge_server import get_local_ip, is_authorized     # H.2-D v1: token + kedaluwarsa

REMOTE_ALLOW = ("/api/chat", "/api/status", "/api/quick-memo", "/api/tts", "/api/reset")

def _allowed_hosts() -> set[str]:
    return {f"127.0.0.1:{WEB_PORT}", f"localhost:{WEB_PORT}", f"{get_local_ip()}:{WEB_PORT}"}

def _is_remote(request: Request) -> bool:
    return (request.client.host if request.client else "") not in ("127.0.0.1", "::1")

@app.middleware("http")
async def security_guard(request: Request, call_next):
    host = request.headers.get("host", "")
    if host not in _allowed_hosts():                                   # anti DNS-rebinding
        return JSONResponse(status_code=400, content={"detail": "Host tidak dikenal."})
    origin = request.headers.get("origin")
    if origin and origin.split("://", 1)[-1] != host:                  # anti drive-by lintas-situs
        return JSONResponse(status_code=403, content={"detail": "Origin ditolak."})
    path = request.url.path
    if _is_remote(request) and path.startswith("/api/"):
        token = (request.cookies.get("carl_t") or request.headers.get("x-carl-token")
                 or request.query_params.get("t"))
        if not is_authorized(request.client.host, token):
            return JSONResponse(status_code=401, content={"detail": "Token diperlukan."})
        if not path.startswith(REMOTE_ALLOW):
            return JSONResponse(status_code=403, content={"detail": "Perintah tidak diizinkan dari perangkat ini."})
    response = await call_next(request)
    t = request.query_params.get("t")
    if t and is_authorized(request.client.host if request.client else "", t):
        response.set_cookie("carl_t", t, httponly=True, samesite="strict")
    return response
```
Di `handle_chat` dan `start_chat_job`, teruskan `remote=_is_remote(request)` ke `route_and_execute`. Router menolak intent berisiko dan slash command di luar allowlist untuk `remote=True`:
```python
RISKY_INTENTS = {"file", "clean", "crypto", "backup", "heal", "trainer", "browser", "vision", "simulate"}
# _route_by_intent(intent, raw, remote=False): if remote and intent in RISKY_INTENTS: return "⚠️ Ditolak dari perangkat remote."
# _check_command: if remote and not command_allowed_for_remote(raw): return "⚠️ Perintah tidak diizinkan dari perangkat remote."
```
Catatan: untuk klien lokal, perlindungan datang dari pemeriksaan `Host` + `Origin`. Bila ingin lebih ketat, wajibkan token juga di localhost dan kirim lewat cookie yang diset saat `/` dimuat.

### S3. Streaming tidak boleh menembus validator (#47) ⏳ Fase 1

```python
# streaming.py
def chat_with_optional_stream(*, model, messages, options, keep_alive,
                              tools=None, stream_to_ui: bool = True):
    kwargs = dict(model=model, messages=messages, options=options, keep_alive=keep_alive)
    if tools:                                    # tool-calling: tanpa streaming agar tool_calls utuh
        return ollama.chat(**kwargs, tools=tools)
    callback = _stream_callback.get() if stream_to_ui else None
    if callback is None:
        return ollama.chat(**kwargs)
    ...  # sisanya sama; jangan teruskan blok <think> ke callback
```
```python
# bot_writer / bot_reasoner: jalur yang divalidasi tidak di-stream
validated_path = vault_evidence_request or explicit_note_request or vault_lookup_request
res = chat_with_optional_stream(..., stream_to_ui=not validated_path)
# repair_messages: selalu stream_to_ui=False
```
`api_server` mengirim `partial_reply` hanya bila ada; UI menampilkan "memverifikasi sumber…" untuk jalur tervalidasi.

### S4. `create_python_file` dikurung (#48) ✅ diterapkan (Fase 0)

```python
# tools/tool_create_py.py
import re
from pathlib import Path
import config

WORKSPACE_DIR = Path(getattr(config, "WORKSPACE_PATH", Path(config.VAULT_PATH).parent / "carl_workspace")).resolve()

def create_python_file(file_name: str, code_content: str) -> str:
    """Membuat file Python di folder kerja Carl (bukan di Vault dan bukan di path sembarang)."""
    name = Path(file_name).name                         # buang semua komponen direktori
    if not name.endswith(".py"):
        name += ".py"
    if not re.fullmatch(r"[\w\-. ]{1,80}\.py", name):
        return "❌ Nama berkas tidak valid."
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    target = (WORKSPACE_DIR / name).resolve()
    if WORKSPACE_DIR not in target.parents:
        return "❌ Path di luar folder kerja."
    if target.exists():
        return f"⚠️ '{name}' sudah ada; pilih nama lain agar tidak menimpa."
    target.write_text(_strip_fences(code_content), encoding="utf-8")
    return f"Berhasil membuat file Python di '{target}'."
```

### S5. Kurikulum les: tanpa pemotongan, tanpa hapus-dulu (#5) ✅ diterapkan (Fase 0)

```python
# gemini_browser.save_or_update_curriculum_note(...)
# 1) Jangan LLM-merge isi mentah. Transkrip tetap utuh; LLM hanya menulis ringkasan.
existing = Path(filepath).read_text(encoding="utf-8") if os.path.exists(filepath) else ""
body_old = _strip_frontmatter(existing)
body_new = current_session_content if not body_old else ""          # file inkremental sudah memuat semuanya
transcript = body_old or body_new
summary = _summarize_map_reduce(transcript, chunk_chars=6000)        # per potongan, lalu gabung
if not summary or len(summary) < 200:
    summary = "> ⚠️ Ringkasan otomatis gagal; transkrip lengkap di bawah."
new_text = _frontmatter(created=orig_created, updated=now_str, topic=clean_topic, trust="external_ai") \
           + f"# 🎓 …\n\n## 🧾 Ringkasan\n{summary}\n\n## 📜 Transkrip Lengkap\n{transcript}\n"
atomic_write(Path(filepath), new_text)                               # snapshot otomatis (C.2 v1)

# 2) run_carl_tutoring_session: bila topik aktual berbeda, tulis file baru DULU,
#    verifikasi, baru hapus file sementara (bukan sebaliknya).
```

### S6. Trust per folder (#52) ⏳ Fase 2 (frontmatter `trust:` sudah ditulis; indexer belum membacanya)

```python
# memory/document_loader.py
TRUST_RULES = (
    ("03-resources/web/", "external_web"),
    ("03-resources/riset/", "external_paper"),
    ("03-resources/materi les carl", "external_ai"),
    ("00-inbox/memo", "user_mobile"),
)
def trust_for(path: str, vault_path: str) -> str:
    rel = os.path.relpath(path, vault_path).replace("\\", "/").casefold()
    return next((label for prefix, label in TRUST_RULES if rel.startswith(prefix)), "user")
# split_markdown_file: s.metadata["trust"] = trust_for(norm_path, config.VAULT_PATH)
# combine_search_results: awali blok "📄 [Sumber: x] [trust: external_ai]" bila trust != user
```
Selaraskan `tool_browser`/`tool_calendar`/`gemini_browser` agar juga menulis `trust:` di frontmatter.

### S7. Koreksi snippet v1

| Snippet v1 | Koreksi |
|---|---|
| C.1 `run_with_tools` | Pakai `create_python_file` versi S4; `registry` tidak boleh berisi tool tulis ke Vault tanpa `safe_path`. |
| C.2 `resolve_unique` | Tambah `04-secure` di `EXCLUDED` (sudah) dan pakai juga di `vault_scanner` (satu daftar, bukan dua). |
| C.3 `is_sensitive` | Panggil di `router.route_and_execute` sebelum `record_untracked_response`; tambah `/confirm`. |
| H.2-D (bridge) | Digantikan S2 untuk bagian server; fungsi token/IP/memo di `bridge_server.py` tetap dipakai. |
| H.2-F `accept_change` | Hapus baris `margin * 0` (tidak berfungsi); jalankan dengan `EVAL_OPTIONS`. |

---

## 8. Matriks Status #1–#58

| # | Status | Kondisi di kode saat ini | Fase |
|---|---|---|---|
| 1 | ❌ | `bot_coder` kirim `tools=`; `chat_with_optional_stream` tak menerimanya → TypeError tertangkap, `/coder` selalu gagal | 1 (setelah #48) |
| 2 | ✅ | jalur tulis eksak (`resolve_write_path`), guard `..`/absolut; `find_file_in_vault` (baca-lunak) tidak lagi mengembalikan path di luar Vault | 0 ✔ |
| 3 | ✅ | `is_sensitive` di router dan `AITeam`; riwayat lama dibersihkan; sesi remote tidak menulis ke disk | 0 ✔ |
| 4 | ✅ | scrypt + salt acak + AES-256-GCM + verifier + auto-lock; `04-secure` dikecualikan di indeks/grounding/sentinel/dll. | 0 ✔ |
| 5 | ✅ | transkrip utuh + ringkasan map-reduce; berkas sementara tidak dihapus sebelum hasil final tersimpan | 0 ✔ |
| 6 | ✅ | simpan → verifikasi → ubah sumber; `bot_curator` memakai `/confirm` | 0 ✔ |
| 7 | ❌ | link path-style dianggap rusak; master index tidak seragam; link hardcode | 1 |
| 8 | ❌ | `_find_section_index` substring; `_merge_field_value` buang ":" | 1 |
| 9 | ❌ | `"bicara"` masih di pola voice | 1 |
| 10 | 🟡 | lock + Future ada; `[-KEEP_RECENT:]` dan `.result()` memblokir tetap | 1 |
| 11 | ❌ | `delete_rule` substring, ID `len+1` | 1 |
| 12 | 🟡 | `-I`, cwd sementara, env minimal, AST check, batas output/memori (POSIX); belum container/jaringan mati | 0.E |
| 13 | ❌ | pemutar PowerShell; `/api/tts` berkas bersama | 6 |
| 14 | ❌ | `/arxiv` gagal: impor `tools.tool_research` tidak ada | 1 |
| 15 | ❌ | tanpa skor/ambang | 2 |
| 16 | ❌ | `index_vault` tanpa try/except di jalur query | 1 |
| 17 | ❌ | seed graf bukan dari RRF; `max_hops` tak dipakai; embed ikut | 2 |
| 18 | ❌ | frontmatter di chunk; exception loader ditelan; ID chunk bisa bertabrakan | 2 |
| 19 | ❌ | tokenisasi ulang tiap query; `'ammar'` di stopwords | 2 |
| 20 | ❌ | bertambah: ERD, NASA, Ammar, Dini, arithmetic fixer, recency fallback, hack "ilai" | 4 |
| 21 | ❌ | regex pemicu R1 terlalu luas | 4 |
| 22 | ❌ | tanpa strip `<think>` (validator menolak jawaban, council meneruskan think, stream bocor) | 1 |
| 23 | 🟡 | `num_ctx` diset di semua `OPTIONS_*`; anggaran konteks belum | 2 |
| 24 | 🟡 | validasi + pelaporan jujur ada; replan, blokir write, anggaran, batas, verifikasi belum | 4 |
| 25 | ❌ | label tanggal kontradiktif | 1 |
| 26 | 🟡 | >8000 karakter deterministik; ≤8000 tetap ditulis ulang LLM | 0 |
| 27 | ❌ | regex dedup tanpa jangkar akhir baris | 1 |
| 28 | ❌ | `clean_markdown` → `agents.gemini_browser` (Playwright) | 1 |
| 29 | ❌ | `trainer`: `OLLAMA_MODEL`, regex `\[.*?\]`, `num_predict` kecil | 5 |
| 30 | ❌ | skor >100%, domain via substring | A |
| 31 | 🟡 | dipakai temporal/trainer/serendipity/kalender/evaluator; sentinel (hanya blokir `04-secure`), weekly review, resolver ringkasan masih aturan sendiri | 0 sisa |
| 32 | ❌ | `vault_temporal` punya regex sendiri, tanggal tak di-parse | A |
| 33 | ✅ | `OLLAMA_MODEL` ada; swarm masih menelan `AttributeError` per persona | 0 ✔ |
| 34 | ✅ | CORS dihapus, bind `127.0.0.1`, Host/Origin guard, token + allowlist (UI perlu penyesuaian, #46) | 0 ✔ |
| 35 | ✅ | `num_ctx` diset di semua `OPTIONS_*` | 0 ✔ |
| 36 | 🟡 | `setup_logging` aktif di `main`/`api_server`; status `error` baru di router | 0 sisa |
| 37 | 🟡 | briefing persisten; review kini ber-snapshot saat menimpa; briefing gagal tetap menandai selesai; review/backup belum persisten | 3 |
| 38 | 🟡 | `WRITE_LOCK` pada `atomic_write` dan read-modify-write `append_file`; backup belum memakai lock | 3 |
| 39 | ❌ | dikonfirmasi: `main.py` dan `api_server` sama-sama membuat memori + scheduler | 1 |
| 40 | ✅ | batas ukuran, nama berkas valid, frontmatter `json.dumps`, `trust: user_mobile`, rate limit di API | 0 ✔ |
| 41 | ❌ | `get_local_ip` bisa memilih adaptor virtual | A |
| 42 | 🟡 | `main.py` try/finally + `escape`; nama pengguna masih ditanya tiap start; `api_server` `user_name="Pengguna"` | A |
| 43 | ✅ | override env, `STATE_PATH`/`LOG_PATH`, `validate_startup`; `.vault_mtimes.json` sengaja tetap di `DB_PATH` | 0 ✔ |
| 44 | ❌ | swap model; antrean 1 worker di API membantu | A |
| 45 | 🟡 | `EVAL_OPTIONS` ada; belum dipakai `evaluate_answers.py` | 5 |
| 46 | 🟡 | `api_server.py` sudah ada; `web/index.html` dan `spatial_graph.html` belum | — |
| 47 | 🆕❌ | stream menampilkan draf sebelum validasi/repair | 1 |
| 48 | 🆕✅ | `create_python_file` hanya menulis ke `CARL_WORKSPACE_PATH` | 0 ✔ |
| 49 | 🆕✅ | sesi remote terpisah tanpa persist; unlock global tetapi perintah brankas ditolak untuk remote; TTS POST + berkas per-hash | 0 ✔ |
| 50 | 🆕❌ | server tanpa watcher; dua entry-point | 1 |
| 51 | 🆕🟡 | `watcher` memakai `memory.manager`; isi asli `memory/__init__.py` belum diverifikasi | 1 |
| 52 | 🆕🟡 | frontmatter `trust:` ditulis (browser, les, memo); indexer belum membacanya | 2 |
| 53 | 🆕✅ | delete → `.trash` + `/confirm`; curator rencana + `/confirm`; `/clean all` dry-run + backup + struktur dipertahankan | 0 ✔ |
| 54 | 🆕✅ | `/vision` dibatasi allowlist; `safe_fetch` (anti-SSRF) di browser dan deep-read web | 0 ✔ |
| 55 | 🆕❌ | arXiv fallback palsu ditulis ke Vault; pola/ICS kalender | 1 |
| 56 | 🆕❌ | dependensi/`check_environment` tidak sinkron; Playwright diimpor eager | A |
| 57 | 🆕❌ | `evaluate_answers` belum tersambung, hanya jalur writer, tak deterministik | 5 |
| 58 | 🆕❌ | probabilitas sukses fiktif di swarm | 4 |

Lampiran A (kebersihan, kerjakan saat sempat): hapus `agents.py` di root (dikalahkan paket `agents/`, file mati); escape YAML (`json.dumps`) di `tool_browser`, `tool_calendar`, `bridge_server`; `tool_browser`/`tool_web_search` paralelkan deep read (5 fetch × 4 detik berurutan) dan batasi ukuran respons; `vault_backup`: filter per segmen path, `testzip` sebelum rotasi, kecualikan `07-Settings/snapshots`; `tool_canvas`: validasi skema JSON LLM; `vector_store`: ganti `recreate_collection`; satu helper tanggal Indonesia; `user_profile`: word boundary, jangan `.capitalize()` nama; `main.py`: `rich.markup.escape(user_name)`, simpan nama pengguna; sinkronkan `requirements.txt` dan `check_environment` (#56).

---

## 9. Definisi "Selesai" & Risiko

| Kemampuan | Dianggap berhasil jika |
|---|---|
| Aman (jaringan) ✅ sisi server | Halaman web asing dan perangkat remote tidak bisa memanggil `/run`, `/delete`, `/write`, `/unlock`, `/reveal`, `/vision`, `/browse` (diuji dengan stub; tinggal sesuaikan UI) |
| Aman (data) | Tidak ada tulis di luar Vault dan folder kerja, tidak ada rahasia di riwayat/ringkasan/log, delete masuk trash, semua aksi otonom terlog dan bisa di-undo |
| Menyimpan memori sendiri | Memori baru punya kutipan sumber, label trust, tidak duplikat, bisa dilihat/dihapus |
| Berpikir | Goal multi-langkah selesai atau gagal-aman, tanpa karangan saat bukti kosong |
| Jujur pada sumber | Jawaban Vault hanya tampil setelah validasi; sumber eksternal diberi label |
| Belajar sendiri | Perubahan otonom diterima hanya bila skor set uji (≥ 30 kasus, deterministik) tidak turun |
| Berbicara | Dua arah dengan barge-in, STT offline, tanpa berkas audio bersama |

**Risiko tambahan dari v2**

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Memperbaiki `/coder` sebelum `create_python_file` dikurung | Model bisa menimpa file sembarang | ✅ Mitigasi selesai (S4); tool-calling kini boleh diaktifkan |
| Mengikat server ke LAN tanpa token | Eksekusi kode oleh perangkat lain | ✅ Default 127.0.0.1; LAN hanya `--lan` + token ber-TTL; HTTP polos, gunakan jaringan tepercaya/VPN |
| Status brankas global | Perangkat lain membaca rahasia saat pemilik unlock | ✅ Perintah brankas ditolak untuk remote + auto-lock 10 menit |
| Dua proses memegang Qdrant | Retrieval turun diam-diam ke keyword/graph | Satu proses utama + kunci instans tunggal |
| Sitasi `[Sumber: …]` pada materi eksternal | Klaim web/LLM tampak terverifikasi | Trust per folder + catatan di jawaban |
| `/clean all` tanpa dry-run | Struktur dan wikilink berubah massal | ✅ Dry-run + backup + struktur dipertahankan |

---

## Catatan Penutup
- Fase 0 diuji di lingkungan ber-stub (tanpa Ollama/LangChain/Qdrant/FastAPI); jalankan `python -m unittest tests.test_fase0 -v` di mesinmu, lalu uji manual jalur yang memanggil model (ringkasan les, perapihan LLM). Butir #51 (isi `memory/__init__.py`) dan #46 (file web UI) perlu dicek langsung.
- Kirim `web/index.html`, `requirements.txt`, dan `setup_vault_folder.py` bila ingin cakupan #34/#47/#56 dipastikan (misalnya: apakah UI menyimpan riwayat chat atau passphrase di `localStorage`).
- Kemampuan model lokal membatasi keandalan agent loop; uji beberapa model pada set uji emas sebelum memilih Planner dan Critic.
