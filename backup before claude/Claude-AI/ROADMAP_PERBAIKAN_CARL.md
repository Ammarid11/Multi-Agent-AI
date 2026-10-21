# 🧠 Roadmap Perbaikan Carl → AI Otonom (v2, disinkronkan dengan kode per 20 Okt 2026)

Tujuan akhir tetap sama: Carl bisa **berpikir** (agent loop), **berbicara** (voice dua arah), **menyimpan memori sendiri** (terkurasi), dan **belajar sendiri** (refleksi + evaluasi + konsolidasi).
Prinsip tetap: **otonomi naik bertahap, setiap tingkat punya pengaman.**

**Basis analisis:** seluruh file yang diunggah (agents, tools, memory, root, `api_server.py`, `evaluate_answers.py`, dll.), dibaca statis, belum dijalankan.
**Tidak ada di unggahan:** `web/index.html`, `web/spatial_graph.html`, `setup_vault_folder.py`, `requirements.txt`, `tests/`, `evaluation/answer_benchmark.json`, dan isi asli `memory/__init__.py` (lihat #51).

Legenda status: ✅ selesai · 🟡 sebagian · ❌ terbuka · 🆕 temuan baru di v2.
Kode Lampiran C/E/H.2 dari **v1 tetap berlaku** kecuali yang dikoreksi di Bagian 7. Simpan v1 sebagai `ROADMAP_PERBAIKAN_CARL_v1.md` untuk rujukan snippet.

## 📑 Daftar Isi
1. [Ringkasan](#1-ringkasan) · 2. [Yang sudah membaik](#2-yang-sudah-membaik) · 3. [Temuan baru #47–#58](#3-temuan-baru-4758)
4. [Fase 0–7 (direvisi)](#4-fase-07-direvisi) · 5. [Urutan eksekusi](#5-urutan-eksekusi) · 6. [Quick wins ≤ 1 jam](#6-quick-wins--1-jam)
7. [Patch kode baru / koreksi v1](#7-patch-kode-baru--koreksi-v1) · 8. [Matriks status #1–#58](#8-matriks-status-158) · 9. [Definisi selesai & risiko](#9-definisi-selesai--risiko)

---

## 1. Ringkasan

Dari 46 temuan v1: **0 tuntas, 7 sebagian, 39 terbuka.** Ditambah **12 temuan baru** dari file yang sebelumnya belum terbaca (terutama `api_server.py`).

**Lima hal paling mendesak (kerjakan sebelum fitur apa pun):**

1. **API server bisa dikendalikan halaman web mana pun (RCE jarak jauh).** `api_server.py` memakai CORS `allow_origins=["*"]` + `allow_credentials=True`, bind `0.0.0.0`, tanpa autentikasi, dan `/api/chat` meneruskan `/run <kode_python>` ke sandbox berbasis blacklist. Situs apa pun yang kamu buka di browser bisa `fetch("http://127.0.0.1:8000/api/chat", ...)` dan menjalankan kode di PC-mu. (#34, diperberat)
2. **Rahasia bocor ke disk.** `/secure judul | isi` dan hasil `/reveal` ikut `record_untracked_response` → `chat_history` → ringkasan → `.session_history.json` (plaintext, 48 jam). (#3)
3. **Transkrip les Gemini terpangkas di jalur normal.** `save_or_update_curriculum_note` selalu me-LLM-merge dengan `existing[:2500]` + `new[:2500]`; sesi panjang kehilangan sebagian besar isinya. (#5, diperberat)
4. **Beberapa perintah rusak total:** `/coder` (#1, TypeError `tools=`), `/arxiv` (#14, impor `tools.tool_research` tidak ada), `/simulate` & `/train_adapter` (#33, `config.OLLAMA_MODEL` tidak ada).
5. **`main.py` kemungkinan crash saat start** karena `watcher.py` memakai `from memory import MemoryManager` sementara `__init-memory__.py` yang diunggah isinya salinan `tools/__init__.py` (#51, perlu konfirmasi).

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

### Fase 0 — Fondasi Aman (wajib sebelum otonom)
Urutan baru: **tutup pintu masuk dulu (0.A), baru integritas data.**

**0.A Amankan API & jaringan (#34, #49, #54)** 🆕 prioritas tertinggi
- [ ] Hapus `CORSMiddleware` wildcard (UI disajikan dari origin yang sama, CORS tidak perlu). Bind default `127.0.0.1`; LAN hanya lewat flag eksplisit + token (S2).
- [ ] Middleware: validasi header `Host` (anti DNS-rebinding) dan `Origin` (anti drive-by lintas-situs).
- [ ] Klien non-lokal: token + allowlist endpoint; `/api/crypto`, `/api/vision`, `/api/browse`, `/api/trainer`, `/api/heal`, `/api/backup` ditolak.
- [ ] Router menerima `remote=True` dan menolak intent berisiko (`file`, `clean`, `crypto`, `backup`, `heal`, `trainer`, `browser`, `vision`, `sandbox`) serta slash command di luar allowlist.
- [ ] Riwayat/profil/unlock **per klien** (session id), bukan global. Auto-lock brankas setelah idle (mis. 10 menit).
- [ ] `tool_vision`/`tool_browser`: path hanya di Vault/`00-Inbox`; URL tolak localhost, IP privat, link-local, skema non-http(s); batasi ukuran respons.
- [ ] `/api/tts`: POST (bukan GET), berkas unik per permintaan (hash teks), hapus berkala.

**0.B Rahasia (#3, #4)**
- [ ] `core/privacy.is_sensitive` dipasang di `router.route_and_execute` *sebelum* `record_untracked_response`, `AITeam._after_response`, summarizer, profil. Balasan `/reveal` juga tidak masuk `chat_history`. Hapus berkas `.session_history.json` lama setelah patch.
- [ ] Perbaikan kripto seperti v1 (salt acak per berkas, KDF kuat, verifier passphrase, AES-GCM atau ganti klaim "AES-256").
- [ ] Tambahkan `04-secure` ke `EXCLUDED_VAULT_DIRS` **dan** ke `grounding` (`load_explicit_vault_sources`, `add_explicit_vault_sources`, `build_vault_recency_context`), `bot_writer._resolve_summary_source`, sentinel, trainer, serendipity, calendar.

**0.C Satu pintu akses file (#2, #31, #48)**
- [ ] Buat `core/vault_io.py` (C.2 v1). `create_file`, `append_file`, `relocate_content`, `clean_*`, `trainer`, `serendipity`, `calendar`, `temporal`, `bot_curator`, `bot_file_manager` memakainya. Tulis tanpa fuzzy, tolak `..` dan path absolut. `os.path.join(VAULT_PATH, "../x")` saat ini lolos di `find_file_in_vault`.
- [ ] `create_python_file` dikurung ke `WORKSPACE_DIR` (S4).
- [ ] Satu `is_indexable_note` (pakai `vault_scanner`, tambah `04-secure`) untuk semua pemindai.

**0.D Penulisan aman + jaring pengaman (#5, #6, #53)**
- [ ] `atomic_write` + snapshot + `/undo` (C.2).
- [ ] `delete_file` → pindah ke `.trash/` (sudah dikecualikan indexer) + konfirmasi dua langkah (`/delete X` → `/confirm <kode>` ber-TTL).
- [ ] `bot_curator`: tampilkan rencana pemindahan dan tunggu konfirmasi.
- [ ] `merge_and_clean_folders`: mode dry-run default, tampilkan daftar pemindahan, snapshot dulu, jangan meratakan subfolder.
- [ ] `relocate_content`: simpan → verifikasi → baru ubah sumber (C.4 v1).
- [ ] `save_or_update_curriculum_note`: lihat S5 (tanpa pemotongan, tanpa `os.remove` sebelum hasil final tertulis).
- [ ] `clean_markdown` (≤8000 karakter): naikkan guard 40% → 70%, dan tolak hasil bila wikilink/blok kode/angka asli hilang.

**0.E Sandbox (#12)** — `python -I`, direktori sementara, batas memori, tanpa jaringan/akses Vault. Blacklist regex bukan pengaman utama.

**0.F Konfigurasi & observabilitas (#33, #35, #36, #43)**
- [ ] `config.py`: `OLLAMA_MODEL`, `NUM_CTX`, `STATE_PATH`, `LOG_PATH`, `EVAL_OPTIONS`, `validate_startup()` (H.2-A v1).
- [ ] `setup_logging()` dipanggil di `main.py` **dan** lifespan `api_server`; request id; `with stage(...)` agar tahap gagal tercatat (H.2-B v1).

### Fase 1 — Bug Kritis (agen harus benar-benar jalan)
- [ ] **#1** `/coder`: sementara hapus `tools=` dan `coder_tools`; aktifkan tool-calling (C.1 v1) **hanya setelah #48 selesai**.
- [ ] **#14** `bot_research`: `from tools.tool_calendar import run_research_command`. **#55**: arXiv gagal → error, bukan paper palsu.
- [ ] **#51** `watcher.py`: `from memory.manager import MemoryManager`; verifikasi isi `memory/__init__.py`.
- [ ] **#33** alias `OLLAMA_MODEL` (juga jangan telan `AttributeError` per persona di swarm).
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

**Hari 1 — Quick wins (Bagian 6) + 0.A**
1. QW1–QW10, lalu S2 (API aman), verifikasi `memory/__init__.py`.

**Minggu 1 — Fondasi**
2. 0.B (privasi/rahasia), 0.C (`vault_io`, `create_python_file` dikurung), 0.D (snapshot, trash, curriculum, relocate), 0.F (config + logging).

**Minggu 2 — Stabil**
3. Fase 1 sisanya (#1 dengan tool-calling, #47, #50, #22, #7–#11), tes dasar, baseline `/eval` + `evaluate_answers`.

**Minggu 3 — Retrieval + trust** → Fase 2.
**Minggu 4–5 — Memori otonom** → Fase 3.
**Minggu 6–7 — Berpikir** → Fase 4.
**Minggu 8+ — Belajar & bicara** → Fase 5–6, Fase 7 paralel sejak awal.

Aturan lama berlaku: jangan lompat ke Fase 5 sebelum Fase 0–3 stabil.

---

## 6. Quick Wins ≤ 1 jam

```python
# QW1 config.py (memperbaiki /simulate dan /train_adapter)
OLLAMA_MODEL = MODEL_WRITER

# QW2 agents/bot_coder.py: hapus tools=coder_tools dan coder_tools sementara (/coder kembali jalan)

# QW3 agents/__init__.py bot_research
from tools.tool_calendar import run_research_command

# QW4 watcher.py
from memory.manager import MemoryManager

# QW5 api_server.py: run_server(host="127.0.0.1") dan hapus CORSMiddleware (S2 lengkap di Bagian 7)

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

### S2. Pengamanan `api_server.py` (menggantikan H.2-D v1 pada bagian server)

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

### S3. Streaming tidak boleh menembus validator (#47)

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

### S4. `create_python_file` dikurung (#48)

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

### S5. Kurikulum les: tanpa pemotongan, tanpa hapus-dulu (#5)

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

### S6. Trust per folder (#52)

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
| 2 | 🟡 | read/delete/clean_markdown sudah eksak; create/append/relocate masih fuzzy dan tanpa guard `..` | 0 |
| 3 | ❌ | `/secure`, `/reveal` masuk chat_history → `.session_history.json` plaintext | 0 |
| 4 | ❌ | salt tetap, 100k iterasi, tanpa verifier, label "AES-256" salah; `04-secure` belum dikecualikan | 0 |
| 5 | ❌ | jalur normal selalu merge `[:2500]`; jalur topik beda `os.remove` dulu | 0 |
| 6 | ❌ | relocate menulis sumber dulu; juga dipicu `bot_curator` | 0 |
| 7 | ❌ | link path-style dianggap rusak; master index tidak seragam; link hardcode | 1 |
| 8 | ❌ | `_find_section_index` substring; `_merge_field_value` buang ":" | 1 |
| 9 | ❌ | `"bicara"` masih di pola voice | 1 |
| 10 | 🟡 | lock + Future ada; `[-KEEP_RECENT:]` dan `.result()` memblokir tetap | 1 |
| 11 | ❌ | `delete_rule` substring, ID `len+1` | 1 |
| 12 | ❌ | blacklist regex, tanpa `-I`/batas memori | 0 |
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
| 23 | ❌ | `num_ctx` dan anggaran konteks belum ada | 0/2 |
| 24 | 🟡 | validasi + pelaporan jujur ada; replan, blokir write, anggaran, batas, verifikasi belum | 4 |
| 25 | ❌ | label tanggal kontradiktif | 1 |
| 26 | 🟡 | >8000 karakter deterministik; ≤8000 tetap ditulis ulang LLM | 0 |
| 27 | ❌ | regex dedup tanpa jangkar akhir baris | 1 |
| 28 | ❌ | `clean_markdown` → `agents.gemini_browser` (Playwright) | 1 |
| 29 | ❌ | `trainer`: `OLLAMA_MODEL`, regex `\[.*?\]`, `num_predict` kecil | 5 |
| 30 | ❌ | skor >100%, domain via substring | A |
| 31 | 🟡 | `vault_scanner` dipakai indexer/graf/galaxy/peta; pemindai lain punya aturan sendiri | 0 |
| 32 | ❌ | `vault_temporal` punya regex sendiri, tanggal tak di-parse | A |
| 33 | ❌ | `config.OLLAMA_MODEL` tidak ada | 1 |
| 34 | ❌ | CORS `*` + credentials, bind `0.0.0.0`, tanpa auth → RCE via `/run` dari halaman web mana pun | 0.A |
| 35 | ❌ | `num_ctx` tak diset di semua `OPTIONS_*` | 0 |
| 36 | ❌ | logging tak dikonfigurasi di `main.py` maupun `api_server` | 0 |
| 37 | 🟡 | briefing persisten; review/backup tidak; review `"w"`; kegagalan briefing tetap menandai selesai | 3 |
| 38 | ❌ | scheduler dan chat menulis Vault tanpa lock | 3 |
| 39 | ❌ | dikonfirmasi: `main.py` dan `api_server` sama-sama membuat memori + scheduler | 1 |
| 40 | ❌ | memo: nama berkas kosong, YAML injection, tanpa batas/auth | 7 |
| 41 | ❌ | `get_local_ip` bisa memilih adaptor virtual | A |
| 42 | ❌ | `main.py` tanpa `finally`; `api_server` `user_name="Pengguna"` tetap | A |
| 43 | ❌ | path keras, `DB_PATH` bercampur file runtime | 0 |
| 44 | ❌ | swap model; antrean 1 worker di API membantu | A |
| 45 | ❌ | belum ada `EVAL_OPTIONS`; benchmark memakai temperature 0.3 | 5 |
| 46 | 🟡 | `api_server.py` sudah ada; `web/index.html` dan `spatial_graph.html` belum | — |
| 47 | 🆕❌ | stream menampilkan draf sebelum validasi/repair | 1 |
| 48 | 🆕❌ | `create_python_file` path bebas | 0/1 |
| 49 | 🆕❌ | `AITeam`, unlock, riwayat global lintas klien; TTS GET + berkas bersama | 0.A |
| 50 | 🆕❌ | server tanpa watcher; dua entry-point | 1 |
| 51 | 🆕❌ | `__init-memory__.py` = salinan tools init; `watcher` impor gagal (konfirmasi) | 1 |
| 52 | 🆕❌ | konten eksternal terindeks tanpa trust | 2 |
| 53 | 🆕❌ | delete permanen, curator LLM langsung, `/clean all` meratakan folder | 0 |
| 54 | 🆕❌ | vision baca path bebas; browser tanpa SSRF guard/batas ukuran | 0.A |
| 55 | 🆕❌ | arXiv fallback palsu ditulis ke Vault; pola/ICS kalender | 1 |
| 56 | 🆕❌ | dependensi/`check_environment` tidak sinkron; Playwright diimpor eager | A |
| 57 | 🆕❌ | `evaluate_answers` belum tersambung, hanya jalur writer, tak deterministik | 5 |
| 58 | 🆕❌ | probabilitas sukses fiktif di swarm | 4 |

Lampiran A (kebersihan, kerjakan saat sempat): hapus `agents.py` di root (dikalahkan paket `agents/`, file mati); escape YAML (`json.dumps`) di `tool_browser`, `tool_calendar`, `bridge_server`; `tool_browser`/`tool_web_search` paralelkan deep read (5 fetch × 4 detik berurutan) dan batasi ukuran respons; `vault_backup`: filter per segmen path, `testzip` sebelum rotasi, kecualikan `07-Settings/snapshots`; `tool_canvas`: validasi skema JSON LLM; `vector_store`: ganti `recreate_collection`; satu helper tanggal Indonesia; `user_profile`: word boundary, jangan `.capitalize()` nama; `main.py`: `rich.markup.escape(user_name)`, simpan nama pengguna; sinkronkan `requirements.txt` dan `check_environment` (#56).

---

## 9. Definisi "Selesai" & Risiko

| Kemampuan | Dianggap berhasil jika |
|---|---|
| Aman (jaringan) | Halaman web asing dan perangkat remote tidak bisa memanggil `/run`, `/delete`, `/write`, `/unlock`, `/reveal`, `/vision`, `/browse` |
| Aman (data) | Tidak ada tulis di luar Vault dan folder kerja, tidak ada rahasia di riwayat/ringkasan/log, delete masuk trash, semua aksi otonom terlog dan bisa di-undo |
| Menyimpan memori sendiri | Memori baru punya kutipan sumber, label trust, tidak duplikat, bisa dilihat/dihapus |
| Berpikir | Goal multi-langkah selesai atau gagal-aman, tanpa karangan saat bukti kosong |
| Jujur pada sumber | Jawaban Vault hanya tampil setelah validasi; sumber eksternal diberi label |
| Belajar sendiri | Perubahan otonom diterima hanya bila skor set uji (≥ 30 kasus, deterministik) tidak turun |
| Berbicara | Dua arah dengan barge-in, STT offline, tanpa berkas audio bersama |

**Risiko tambahan dari v2**

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Memperbaiki `/coder` sebelum `create_python_file` dikurung | Model bisa menimpa file sembarang | Urutan wajib: S4 → baru tool-calling |
| Mengikat server ke LAN tanpa token | Eksekusi kode oleh perangkat lain | Default 127.0.0.1; LAN hanya dengan token ber-TTL |
| Status brankas global | Perangkat lain membaca rahasia saat pemilik unlock | Unlock per sesi + auto-lock |
| Dua proses memegang Qdrant | Retrieval turun diam-diam ke keyword/graph | Satu proses utama + kunci instans tunggal |
| Sitasi `[Sumber: …]` pada materi eksternal | Klaim web/LLM tampak terverifikasi | Trust per folder + catatan di jawaban |
| `/clean all` tanpa dry-run | Struktur dan wikilink berubah massal | Dry-run + snapshot + jangan meratakan |

---

## Catatan Penutup
- Dokumen ini hasil pembacaan statis; belum ada kode yang dijalankan. Butir #51 (isi `memory/__init__.py`) dan #46 (file web UI) perlu dicek langsung.
- Kirim `web/index.html`, `requirements.txt`, dan `setup_vault_folder.py` bila ingin cakupan #34/#47/#56 dipastikan (misalnya: apakah UI menyimpan riwayat chat atau passphrase di `localStorage`).
- Kemampuan model lokal membatasi keandalan agent loop; uji beberapa model pada set uji emas sebelum memilih Planner dan Critic.
