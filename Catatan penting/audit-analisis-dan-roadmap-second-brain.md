# Audit Awal dan Roadmap Perbaikan
## Multi-Agent AI Second Brain

> **Status dokumen:** Audit kode, perubahan, dan hasil validasi regresi terpilih  
> **Tujuan:** Menilai kesesuaian implementasi terhadap alur algoritma yang dirancang, mencatat temuan yang dapat dibuktikan dari kode, dan menyusun urutan validasi/perbaikan.  
> **Batasan:** Dokumen ini bukan sertifikasi bahwa seluruh aplikasi bebas bug. Audit menyeluruh memerlukan pemeriksaan semua modul, eksekusi test, dan validasi runtime pada environment aplikasi.

---

## 1. Ringkasan Eksekutif

Sistem sudah memiliki kerangka **Multi-Agent Second Brain** yang masuk akal: request diterima melalui API atau CLI, diarahkan oleh router, diproses agent yang sesuai, lalu dapat menggunakan memori dan tools untuk menjawab atau melakukan aksi. Perbaikan retrieval, routing, session memory, kontrak API, dan benchmark jawaban sudah diterapkan dengan regression tests terpilih.

Namun, **keberadaan arsitektur belum membuktikan seluruh alur bekerja benar**. Audit awal menemukan hasil query expansion tidak dimasukkan ke hasil akhir serta import `Optional` yang hilang. Keduanya telah diperbaiki; test regresi yang ditambahkan lulus. Evaluator juga kini secara eksplisit mengukur retrieval sintetis, bukan akurasi jawaban LLM, dan tidak menghasilkan skor sempurna saat sampel kosong.

### Penilaian awal

| Area | Penilaian awal | Catatan |
|---|---|---|
| Arsitektur umum | Cukup baik | Pemisahan API, router, agent, memory, dan tools terlihat jelas. |
| Routing | Berlapis dan teruji sebagian | Slash command, heuristic, dan classifier memiliki regression tests; belum seluruh intent/urutan konflik diuji. |
| Retrieval memori | Perbaikan inti diterapkan | Query expansion ikut difusikan; relevansi end-to-end pada Vault representatif belum tervalidasi. |
| Session memory | Perbaikan ketahanan diterapkan | Kegagalan ringkasan/persistensi/reset tidak memangkas atau mengosongkan state aktif; test terpilih lulus. |
| Ketahanan runtime | Sebagian tervalidasi | Kontrak error API dan fallback retrieval memiliki test; dependency eksternal dan startup bersih belum diverifikasi. |
| Kualitas validasi | Regression terpilih | 30 test terpilih lulus; dataset benchmark jawaban masih kosong sehingga belum ada skor akurasi. |

**Kesimpulan:** Algoritma utama sudah diterapkan secara struktural dan beberapa risiko yang teridentifikasi telah diperbaiki. Cakupan validasi saat ini bukan bukti bahwa seluruh fitur bekerja benar atau bebas bug. Prioritas tersisa adalah benchmark berbasis Vault yang ditinjau manusia dan validasi runtime terkontrol.

### Perubahan dan validasi setelah audit awal

- `memory/hybrid_search.py`: menambahkan import `Optional`, merger beberapa ranking dengan RRF, dan metadata sumber untuk dokumen graph.
- `memory/manager.py`: hasil pencarian dari variasi query sekarang digabungkan dan dideduplikasi sebelum hybrid ranking.
- `memory/evaluator.py`: menghitung ranking dari marker sumber eksplisit; kondisi tanpa sampel tidak mengembalikan skor 1.0; laporan menyatakan batasan benchmark dan tidak lagi menyebutnya akurasi jawaban.
- `test_memory_quality.py`, `test_router_and_session.py`, dan `test_api_contract.py`: **30 test lulus** menggunakan Python 3.14.7. Cakupan mencakup retrieval/fallback, routing, persistensi session memory, kontrak error API, dependency failure mock, dan galaxy builder pada Vault sementara.
- Smoke import `api_server`, `agents.router`, `memory.manager`, dan `memory.answer_evaluator` lulus; Pylance melaporkan tidak ada diagnostic pada file inti yang diperiksa.
- `evaluate_answers.py` menangani dataset kosong dengan warning dan metrik `null`, bukan skor sempurna. Akurasi jawaban Carl belum dapat dinilai sebelum dataset gold yang ditinjau manusia diisi.
- Belum dijalankan: startup proses server baru terhadap dependency aktual, benchmark ke Vault aktif, dan validasi end-to-end yang melibatkan layanan eksternal. Server aktif tidak direstart agar proses pengguna tidak terganggu.

---

## 2. Cakupan dan Dasar Analisa

Analisa awal ini didasarkan pada pemeriksaan kode berikut:

- `api_server.py` — lifecycle aplikasi dan endpoint HTTP
- `agents/router.py` — slash command, heuristic routing, dan routing hasil classifier
- `agents/bot_router_llm.py` — classifier intent berbasis Ollama
- `agents/__init__.py` — orkestrasi agent dan pembaruan history
- `memory/manager.py` — sinkronisasi vault serta pencarian konteks
- `memory/vector_store.py` — koneksi dan operasi Qdrant
- `memory/hybrid_search.py` — keyword search dan Reciprocal Rank Fusion
- `memory/session_memory.py` — ringkasan serta persistensi session memory

Pemeriksaan ini **belum** membuktikan bahwa semua agent, semua endpoint, semua tool, dan semua skenario pengguna berfungsi. Area yang belum divalidasi dengan test/runtime dicatat sebagai pekerjaan lanjutan, bukan dianggap sebagai bug terkonfirmasi.

---

## 3. Alur Algoritma yang Diharapkan

```text
Input pengguna
    ↓
Validasi dan normalisasi
    ↓
Routing:
  1. slash command
  2. heuristic intent
  3. LLM intent classifier
  4. default agent
    ↓
Ambil konteks yang relevan
  - hasil retrieval vault
  - riwayat dan ringkasan sesi
  - profil pengguna
  - aturan operasional
    ↓
Jalankan agent terpilih
    ↓
Panggil tool jika diperlukan
    ↓
Perbarui history/memory yang relevan
    ↓
Kembalikan respons
```

Secara desain, alur ini sesuai dengan pola umum sistem retrieval-augmented dan tool-using agent. Setiap panah tetap perlu dibuktikan melalui test integrasi, khususnya bahwa hasil retrieval benar-benar diteruskan ke agent dan bahwa aksi tool hanya berjalan untuk intent yang tepat.

---

## 4. Temuan Detail

### 4.1 Kekuatan yang terlihat

1. **Komponen dipisahkan berdasarkan tanggung jawab.** API, router, orkestrator agent, memory, dan tools berada pada modul berbeda. Ini memudahkan pengujian dan perubahan terarah.
2. **Routing memiliki fallback bertingkat.** Slash command dapat diproses tanpa classifier; heuristic menangani ungkapan yang jelas; classifier LLM menangani input yang lebih bebas.
3. **Pencarian memori menggabungkan beberapa sinyal.** Kode menggabungkan vector results, keyword results, serta dokumen yang ditemukan dari traversal wikilink.
4. **Ada upaya membatasi konteks percakapan.** Session memory meringkas percakapan dan menyimpan ringkasan dengan masa berlaku.
5. **Operasi vault didelegasikan ke tools.** Agent file manager dan curator meminta model menentukan aksi, lalu memanggil fungsi tool khusus.

Kekuatan di atas adalah penilaian struktur/desain, bukan jaminan bahwa seluruh implementasi bebas kegagalan.

### 4.2 Temuan prioritas tinggi: `Optional` berpotensi belum terdefinisi

Pada `memory/hybrid_search.py`, fungsi `combine_search_results` menggunakan anotasi `Optional[List[Document]]`. Import yang terlihat hanya mencakup `List`, `Set`, `Tuple`, dan `Dict`; `Optional` tidak terlihat diimpor, dan file tersebut tidak terlihat menggunakan `from __future__ import annotations`.

Pada versi Python yang mengevaluasi anotasi saat definisi fungsi dimuat, kondisi ini dapat menghasilkan `NameError` ketika `memory.hybrid_search` di-import. Karena `memory/manager.py` mengimpor modul ini, kegagalan tersebut berpotensi menjalar ke inisialisasi MemoryManager dan startup aplikasi.

**Status:** Sudah diperbaiki dengan import `Optional`; smoke import modul inti dan regression tests lulus.

### 4.3 Bug logika: query expansion tidak memengaruhi hasil akhir

Di `memory/manager.py`, saat hasil vector dan keyword awal sedikit:

1. Sistem memanggil `expand_query(query)`.
2. Sistem menjalankan pencarian vector untuk query alternatif.
3. Dokumen alternatif hanya diperiksa/dimasukkan ke set `seen`.
4. Hasil alternatif tersebut tidak ditambahkan ke daftar yang digunakan untuk `combine_search_results`.

Akibatnya, query expansion menambah pekerjaan pencarian tetapi tidak memperluas konteks final. Ini adalah bug logika yang terlihat langsung dari alur data.

**Status:** Sudah diperbaiki dengan fusi RRF dan deduplikasi stabil; regression test membuktikan hasil yang hanya ditemukan query alternatif masuk ke konteks.

### 4.4 Fallback retrieval dapat menyamarkan kegagalan

`VectorStoreManager.similarity_search` menangkap exception dan mengembalikan list kosong. Ini mencegah sebagian kegagalan merambat, tetapi pemanggil dapat sulit membedakan:

- memang tidak ada hasil relevan; dan
- pencarian gagal karena DB, embedding, atau masalah runtime.

Hal ini dapat membuat jawaban tanpa konteks tampak seperti pencarian berhasil tetapi tidak menemukan catatan. Untuk menjaga fallback tetap berguna tanpa menyembunyikan masalah, kegagalan perlu dicatat secara terstruktur dan status retrieval perlu dapat dibedakan dari hasil kosong yang sah.

**Status:** Logging dan fallback retrieval eksplisit telah ditambahkan; regression test memastikan error vector tidak dianggap sebagai hasil kosong yang sah. Qdrant runtime belum diuji.

### 4.5 Intent classifier hanya mengenal sebagian intent

`agents/bot_router_llm.py` mendefinisikan label classifier berikut: `web`, `think`, `coder`, `sintesis`, `file`, `clean`, dan `default`. Sementara itu, `AgentRouter._route_by_intent` memiliki handler untuk lebih banyak intent, misalnya `canvas`, `backup`, `heal`, `vision`, `research`, dan lainnya.

Konsekuensinya, classifier LLM tidak dapat memilih sebagian besar label fitur tersebut: output yang tidak berada di `INTENT_LABELS` akan diubah menjadi `default`. Sebagian fitur tetap bisa dipanggil melalui slash command atau heuristic, tetapi tidak semuanya dapat ditemukan melalui jalur classifier natural language.

**Status:** Batasan implementasi yang tampak langsung dari daftar label. Dampak produk bergantung pada fitur yang diharapkan tersedia melalui bahasa natural.  
**Rencana:** Putuskan daftar intent yang memang perlu didukung classifier. Samakan label, deskripsi, handler, dan test pemetaan; jangan menambah label tanpa pengujian handler yang bersangkutan.

### 4.6 Heuristic routing menggunakan pencocokan substring

`_fast_intent_check` memeriksa frasa dengan ekspresi seperti `w in p`. Pencocokan substring dapat memicu intent meski frasa hanya menjadi bagian dari kata atau konteks yang tidak dimaksudkan. Heuristic juga harus diuji untuk urutan prioritas ketika satu input memuat lebih dari satu intent.

**Status:** Pencocokan frasa kini memakai batas kata dan menangani beberapa negasi umum; test kapitalisasi, substring, dan negasi tersedia. Konstruksi natural language dan konflik beberapa intent belum tercakup penuh.

### 4.7 Ranking keyword disebut BM25-style, tetapi bukan implementasi BM25 penuh

`get_ranked_keyword_results` memberi skor berdasarkan jumlah kata kunci yang cocok, bonus frasa, dan bonus nama sumber. Ini dapat berguna sebagai heuristic sederhana, tetapi tidak menghitung faktor BM25 lazim seperti frekuensi kata yang dinormalisasi terhadap panjang dokumen dan statistik korpus.

**Status:** Dokumentasi telah mengklarifikasi bahwa algoritma ini lexical heuristic, bukan BM25 penuh. Evaluasi dengan hasil acuan manusia masih terbuka.

### 4.8 Beberapa jalur error membutuhkan kebijakan konsisten

Pemeriksaan awal menemukan pola penanganan exception yang berbeda-beda: ada jalur yang mengembalikan fallback, ada yang membentuk pesan error, dan ada endpoint yang menyajikan status melalui payload. Tanpa kontrak respons yang seragam, client dapat kesulitan membedakan sukses, kegagalan agent, kegagalan dependency, dan hasil kosong.

Selain itu, `api_server.py` memanggil beberapa operasi agent melalui `asyncio.to_thread`, sedangkan pola endpoint lain perlu diperiksa satu per satu. Operasi sinkron/blocking yang dijalankan langsung dalam endpoint `async` dapat menghambat event loop.

**Status:** Jalur pemanggilan agent yang diperiksa memakai `asyncio.to_thread`; readiness mengembalikan 503, error internal chat 500, dan kontrak terkait diuji. Standardisasi seluruh endpoint/dependency belum selesai.

### 4.9 Dokumentasi arsitektur perlu diselaraskan dengan konfigurasi aktual

Dokumen lama `Catatan penting/analisa-project.md` menyebut stack OpenAI, sedangkan `config.py` yang ditinjau mengatur model Ollama lokal. Ini menunjukkan adanya drift dokumentasi yang dapat membingungkan setup, debugging, dan keputusan pengembangan.

**Status:** Dokumen arsitektur yang diperiksa telah diselaraskan dengan stack Ollama yang aktif; dokumen lama lainnya belum diaudit satu per satu.

### 4.10 Kualitas session memory dan aturan belum tervalidasi secara perilaku

Kode menyediakan ringkasan sesi, penyimpanan ringkasan, profile update, dan rule detection. Namun, perlu test untuk membuktikan:

- ringkasan tidak dibuat berulang tanpa perlu;
- percakapan terbaru tetap tersedia setelah pemotongan history;
- ringkasan kedaluwarsa disaring dengan benar;
- reset mengosongkan history dan data persisten sesuai ekspektasi;
- kegagalan model atau file tidak diam-diam menghasilkan state yang menyesatkan.

**Status:** Test mencakup kegagalan ringkasan/persistensi, pemotongan history saat sukses, masa berlaku, dan mempertahankan state ketika reset persisten gagal. Reset sukses dan semua batas threshold belum seluruhnya diuji.

---

## 5. Apakah Algoritma Sudah Dijalankan dengan Benar?

Jawaban berdasarkan kode dan validasi terpilih saat ini:

- **Secara arsitektur:** Ya, pola utama sudah terlihat dalam kode.
- **Secara implementasi penuh:** Belum dapat dinyatakan benar untuk semua alur.
- **Bug yang ditemukan dan telah diperbaiki:** Hasil query expansion tidak masuk ke hasil akhir; `Optional` belum diimpor pada hybrid search.
- **Risiko yang telah ditangani dan diuji sebagian:** kegagalan vector retrieval, koleksi Qdrant yang gagal dimuat, pemotongan session history saat ringkasan gagal, dan kontrak error API.
- **Bebas bug:** Tidak dapat diklaim tanpa test otomatis dan uji runtime yang memadai.

Dengan demikian, status yang disarankan adalah **prototype fungsional dengan beberapa gap implementasi dan validasi**, bukan sistem yang sudah terverifikasi production-ready.

---

## 6. Roadmap Perbaikan yang Diusulkan

### Fase 0 — Baseline dan verifikasi awal

**Tujuan:** Mengetahui status aplikasi saat ini sebelum perubahan.

- [x] Konfirmasi interpreter proyek: venv Python 3.14.7.
- [x] Jalankan smoke import untuk modul inti dan entry point API.
- [x] Jalankan test regresi terpilih sesudah perubahan.
- [x] Catat bahwa baseline kegagalan sebelum perubahan tidak tersedia dan tidak dapat direkonstruksi sesudah perubahan.
- [x] Konfirmasi Ollama dapat diakses dan model yang dikonfigurasi terdaftar melalui endpoint read-only `/api/tags`.
- [ ] Konfirmasi koleksi Qdrant bisa dimuat dan tidak terkunci; direktori database ada, tetapi tidak dibuka agar tidak berkonflik dengan proses aktif.

**Status:** Ollama merespons dan model writer/reasoner/coder/embedding terdaftar. Qdrant lokal tidak diinisialisasi ulang atau dibuka saat aplikasi mungkin sedang memakai lock. Tidak ada operasi destruktif pada Vault/database.

### Fase 1 — Pulihkan import dan startup

**Prioritas:** P0 — penghalang eksekusi jika terkonfirmasi.

- [x] Perbaiki referensi `Optional` pada `memory/hybrid_search.py`.
- [x] Tambahkan test yang mengimpor modul memory melalui suite test.
- [x] Jalankan smoke import entry point API tanpa melakukan reset/recreate collection.
- [x] Uji lifecycle startup/shutdown FastAPI dengan MemoryManager dan scheduler dimock, tanpa reset/recreate collection.
- [ ] Jalankan startup proses server nyata setelah mengoordinasikan port serta akses database yang sedang dipakai.

**Status:** Wiring lifecycle lulus dalam test terisolasi. Status server yang diamati melalui `GET /api/status` menyatakan `online`, menampilkan model writer/reasoner/coder dan 113 catatan, tetapi tidak memuat `components` yang kini dikeluarkan source. Server tidak direstart, jadi belum dapat dipastikan menjalankan source terbaru atau retrieval siap.

### Fase 2 — Perbaiki dan buktikan retrieval

**Prioritas:** P1 — kualitas jawaban berbasis vault.

- [x] Dokumentasikan kontrak hasil retrieval: hasil vektor, keyword, query alternatif, dan graph.
- [x] Gabungkan hasil query expansion ke kumpulan hasil yang benar menggunakan RRF antarranking.
- [x] Deduplikasi hasil antarkueri dengan identitas sumber dan konten chunk.
- [x] Pastikan hasil graph menyertakan marker sumber dan tetap dibatasi oleh batas traversal yang ada.
- [x] Tambahkan regression test untuk hasil expansion, deduplikasi, marker sumber, dan dataset kosong.
- [x] Tambahkan test retrieval untuk error vector backend.
- [ ] Validasi hasil aktual di Vault yang representatif.

**Status:** Fusi query, fallback retrieval, dan regression tests selesai; benchmark Vault representatif masih terbuka.

### Fase 3 — Validasi routing dan kontrak agent

**Prioritas:** P1 — mencegah tugas masuk ke agent yang salah.

- [x] Dokumentasikan tabel intent classifier → handler → input.
- [x] Samakan daftar label classifier dengan pemetaan handler yang tersedia untuk natural language.
- [x] Uji slash command, heuristic, label classifier valid, pemetaan handler, dan sebagian kasus false positive/negasi.
- [x] Uji output classifier tidak dikenal dan exception model; keduanya jatuh ke `default`.
- [x] Uji prioritas slash command atas classifier serta urutan heuristic saat ada beberapa trigger; `web` menang atas `coder` pada contoh uji.
- [x] Uji variasi kapitalisasi, substring, dan contoh negasi; konstruksi natural language yang lebih luas masih terbuka.
- [ ] Pastikan setiap route mengirim argumen yang benar dan mengembalikan kontrak hasil yang konsisten.

| Label classifier | Handler | Input yang diteruskan |
|---|---|---|
| `web` | `bot_web` | Prompt asli |
| `think` | `bot_reasoner` | Prompt asli |
| `coder` | `bot_coder` | Prompt asli |
| `sintesis` | `bot_synthesizer` | Prompt asli |
| `file` | `bot_file_manager` | Prompt asli |
| `clean` | `bot_cleaner` | Prompt asli |
| `default` | `bot_writer` | Prompt asli; fallback label tidak dikenal atau classifier gagal |

Regression tests memastikan pemetaan handler dan argumen untuk label di atas. Semua slash command dan jalur heuristic belum diperiksa satu per satu.

**Kriteria selesai:** Setiap intent yang didukung memiliki test pemetaan; intent yang tidak didukung jatuh ke default secara eksplisit dan tercatat.

### Fase 4 — Ketahanan API dan dependency

**Prioritas:** P2 — stabilitas penggunaan.

- [x] Inventarisasi semua endpoint API dan pola operasi blocking.
- [ ] Standarkan bentuk respons dan kode HTTP untuk sukses, validasi gagal, komponen belum siap, serta kegagalan internal.
- [x] Tambahkan logging untuk kegagalan retrieval dan error chat tanpa mengirim detail exception sebagai payload.
- [x] Simulasikan Ollama/model tidak tersedia, Qdrant terkunci, dan Vault hilang dengan test terisolasi/mocks.
- [x] Pastikan fallback retrieval dan komponen belum siap menunjukkan status yang jujur kepada pemanggil.

**Status:** Inventaris seluruh endpoint telah dicatat. Sebagian besar pemanggilan agent memakai `asyncio.to_thread`; operasi reset/stop, QR, dan cache TTS masih sinkron. Kontrak readiness/chat serta deklarasi error TTS/quick-memo sudah diperjelas, tetapi standardisasi menyeluruh masih terbuka. Test mensimulasikan dependency yang tidak tersedia; kegagalan eksternal yang aktual belum dipicu.

Inventaris endpoint: `GET /`, `/api/status`, `/api/tts`, `/api/bridge`, `/galaxy`, `/api/galaxy`; `POST /api/chat`, `/api/tutoring/stop`, `/api/reset`, `/api/briefing`, `/api/sentinel`, `/api/backup`, `/api/heal`, `/api/canvas`, `/api/voice`, `/api/vision`, `/api/quick-memo`, `/api/serendipity`, `/api/calendar`, `/api/research`, `/api/browse`, `/api/eval`, `/api/crypto`, `/api/simulate`, `/api/trainer`, `/api/gemini`, `/api/gemini_dialog`, `/api/tutoring`. Pemanggilan agent dan scan Vault utama didelegasikan melalui `asyncio.to_thread`; operasi ringan seperti stop/reset, pembuatan QR, dan filesystem cache TTS masih sinkron pada handler `async`.

**Kriteria selesai:** Kegagalan dependency bisa dibedakan dari hasil sukses kosong dan tidak menyebabkan event loop/API terblokir oleh operasi sinkron yang panjang.

### Fase 5 — Session memory dan konsistensi dokumentasi

**Prioritas:** P2 — kualitas konteks dan pemeliharaan.

- [x] Uji pemotongan history saat ringkasan sukses/gagal, masa berlaku, dan kegagalan reset persisten.
- [x] Tentukan kebijakan saat pembuatan atau penyimpanan ringkasan gagal: jangan potong history.
- [x] Selaraskan dokumen arsitektur yang diperiksa dengan konfigurasi Ollama yang aktif.
- [x] Perjelas lexical ranking sebagai heuristic sederhana, bukan BM25.

**Kriteria selesai:** Perilaku memory sesi terdokumentasi dan diuji; dokumentasi setup tidak mengarahkan pengguna ke stack yang berbeda dari konfigurasi aktif.

### Fase 6 — Validasi end-to-end dan kesiapan rilis

**Prioritas:** P3 — dilakukan setelah fase sebelumnya stabil.

- [ ] Uji alur chat umum sampai agent default dan jawaban berbasis vault.
- [x] Uji pembangun galaxy dengan fixture Vault sementara; tidak membaca/menulis Vault produksi.
- [ ] Uji fitur eksternal/opsional secara terisolasi dengan mock atau environment pengujian.
- [x] Jalankan diagnostics Pylance untuk file inti yang diubah; tidak ada error.
- [x] Dokumentasikan batasan dan pekerjaan validasi yang masih tersisa.

**Kriteria selesai:** Skenario utama lulus di environment terkontrol; tidak ada klaim “bebas bug”, tetapi risiko residual dan hasil test diketahui.

---

## 7. Prioritas Eksekusi yang Direkomendasikan

Urutan paling aman dan bernilai berikut mencerminkan pekerjaan yang masih terbuka:

1. **Buat dataset benchmark dari Vault yang ditinjau manusia** — tetapkan query, fakta wajib, sumber, dan kasus tidak terjawab.
2. **Evaluasi jawaban Carl** — setelah dataset gold diisi, ukur dukungan sumber/fakta dan abstention serta lakukan review manual.
3. **Jalankan startup dan smoke test dependency dalam environment terkontrol** tanpa mengubah data produksi.
4. **Lengkapi test classifier/API** serta skenario end-to-end yang masih terbuka.
5. **Uji operasi tulis hanya di Vault sementara** dan catat batasan yang tersisa.

Perubahan sebaiknya dilakukan per fase, dengan test sebelum dan sesudah setiap fase. Jangan menguji operasi file yang menghapus atau menimpa data pada vault pengguna; gunakan direktori fixture sementara.

---

## 8. Definisi “Siap” yang Disarankan

Sistem dapat dianggap cukup tervalidasi untuk penggunaan internal apabila:

- semua modul inti dapat di-import dan aplikasi dapat startup;
- test routing dan retrieval yang relevan lulus;
- query expansion terbukti memengaruhi hasil akhir;
- error dependency dilaporkan secara jelas dan tidak menyamar sebagai jawaban normal;
- endpoint penting diuji dengan request sukses dan gagal;
- operasi tulis/hapus diuji hanya di vault sementara;
- dokumentasi sesuai dengan stack konfigurasi aktif;
- batasan dan kegagalan yang belum diperbaiki dicatat.

Kriteria tersebut meningkatkan keyakinan, tetapi tetap bukan bukti matematis bahwa semua bug telah dihilangkan.

---

## 9. Keputusan dan Langkah Berikutnya

Perbaikan import, retrieval, routing dasar, API chat, dan ketahanan session memory telah diterapkan dengan validasi regresi terpilih. Langkah berikutnya adalah benchmark acuan manusia dan validasi runtime terisolasi. Test yang belum dijalankan tidak boleh dianggap lulus; hindari operasi tulis/hapus pada Vault pengguna.

Dokumen ini mencatat analisa, perubahan, dan bukti validasi yang tersedia. Checkbox menandai pekerjaan yang benar-benar diterapkan dan diuji; pekerjaan yang menunggu dataset atau akses environment tetap belum selesai.

---

## Addendum: Pengurangan Risiko Halusinasi dan Validasi Lanjutan

Perubahan lanjutan memperkuat grounding dan pelaporan tanpa menganggap bahwa pemeriksaan otomatis dapat menjamin kebenaran semantik:

- Agent penjawab dan peringkas menerima kebijakan bersama untuk membedakan fakta bersumber, inferensi, pengetahuan umum, serta informasi yang belum terverifikasi.
- Pemeriksaan sitasi memastikan nama sumber yang disebut jawaban muncul pada konteks yang diberikan. Ini **bukan** pemeriksaan bahwa isi sumber benar-benar mendukung setiap klaim.
- Peta Vault kini menggunakan pengecualian folder yang sama dengan pemindaian retrieval. Folder hidden, arsip, trash, template, settings, dan system tidak dimasukkan sebagai catatan yang dapat dicari.
- Pelaporan aksi otonom memvalidasi rencana dan membedakan langkah berhasil, gagal, dan tidak dijalankan. Penghapusan file mengharuskan path yang tepat jika basename ambigu; validasinya memakai Vault sementara.
- Parser hasil web mengutamakan URL tujuan sumber, bukan URL perantara mesin pencari. Timestamp bertanggal hanya dikonversi ke WIB bila input memiliki zona waktu; zona WIB tetap digunakan tanpa database zona waktu Windows.
- Profil pengguna tidak lagi mengisi minat atau proyek default yang belum dikonfirmasi.

**Validasi terbaru:** 40 test pada suite grounding, kontrak API, router/session, dan kualitas memori lulus. Test menguji penghapusan pada direktori sementara; Vault pengguna dan database Qdrant aktif tidak disentuh. Pemeriksaan Pylance pada file yang baru diubah tidak menemukan masalah selain import opsional `ddgs` yang belum terpasang/terdeteksi pada konfigurasi editor.

**Batasan dan pekerjaan terbuka:** validasi nama sitasi bukan validasi dukungan semantik; benchmark akurasi jawaban berbasis dataset gold yang ditinjau manusia belum tersedia. Belum ada smoke test terhadap server baru atau seluruh dependency eksternal, dan perubahan filter indexing perlu disinkronkan pada runtime terkoordinasi agar indeks lama sesuai kebijakan baru. Hasil test terpilih tidak membuktikan seluruh aplikasi bebas bug.

### Temuan: laporan sukses perapihan Markdown dokumen les

Tangkapan layar menunjukkan respons yang dihasilkan langsung oleh jalur dokumen besar pada `tools/clean_markdown.py`. Untuk file di atas 8.000 karakter, implementasi sebelumnya sengaja tidak meminta LLM menulis ulang isi, tetapi hanya menjalankan beberapa normalisasi tetap. Meski begitu, ia selalu mengklaim struktur telah dirapikan dan seluruh materi utuh. Resolver file juga dapat memilih salah satu catatan duplikat berdasarkan waktu modifikasi, sehingga file yang dimaksud belum tentu yang diproses.

Perbaikan yang diterapkan:

- Target perapihan kini harus cocok dengan path tepat; nama duplikat meminta path Vault lengkap dan path di luar Vault ditolak.
- Setelah penulisan, isi file dibaca ulang dan dibandingkan dengan hasil yang diharapkan sebelum respons sukses diberikan.
- Respons dokumen besar menyebut perubahan yang benar-benar dilakukan. Jika body materi tidak mengalami normalisasi format, respons memperingatkan bahwa isi mungkin masih perlu dirapikan manual; tidak ada lagi klaim bahwa struktur sudah dirapikan atau data 100% utuh.
- Perapihan folder/Vault membedakan file berhasil, peringatan, dan gagal. Pembuatan catatan juga tidak lagi menyembunyikan kegagalan auto-format.

**Validasi:** 45 test pada suite grounding, cleanup, kontrak API, router/session, dan kualitas memori lulus. Test menggunakan file duplikat dan file besar dalam direktori sementara; tidak menyentuh catatan Vault pengguna.

### Follow-up: menyimpan jawaban/rangkuman sebelumnya

Kasus percakapan “jawab topik → pengguna meminta catat rangkuman yang di atas” kini ditangani sebagai operasi kontekstual yang eksplisit:

- Permintaan natural-language seperti “catat di catatan baru”, “simpan jawaban tadi”, dan “catat rangkuman yang di atas” diprioritaskan ke file manager tanpa bergantung pada klasifikasi LLM.
- Isi yang disimpan adalah jawaban assistant terakhir apa adanya; file baru dibuat di `00-Inbox`, nama topik diambil secara konservatif dari konteks eksplisit, dan nama generik dipakai jika topik tidak dapat dikenali.
- File dibuka dengan mode eksklusif agar catatan lama tidak tertimpa. Hasil disimpan lalu dibaca ulang untuk verifikasi; jika tidak ada jawaban sebelumnya atau penulisan gagal, operasi tidak melaporkan sukses.
- Permintaan membuat catatan baru tentang topik (misalnya “buat catatan baru tentang pariwisata”) tidak disalahartikan sebagai perintah menyimpan jawaban sebelumnya.

**Validasi follow-up:** test mencakup isi rangkuman persis tersimpan, ketiadaan jawaban sebelumnya, penghindaran overwrite pada penyimpanan berulang, deteksi intent, dan routing natural-language yang dinegasikan. File uji dibuat di direktori sementara.

### Koreksi: riwayat jawaban dari sebagian route tidak tercatat

Pengujian lanjutan dengan UI menunjukkan kasus simpan tetap dapat menjawab “Belum ada jawaban sebelumnya”. Penyebabnya berada sebelum fungsi simpan: pencatatan riwayat sebelumnya hanya dilakukan oleh sebagian method agent (`bot_writer`, `bot_reasoner`, `bot_file_manager`, dan lainnya), sedangkan route seperti synthesizer dan perintah langsung tidak mencatat balasan ke `AITeam.chat_history`. Handler simpan memang berjalan, tetapi tidak punya pesan assistant untuk disalin. Test awal yang memberi riwayat sintetis langsung ke handler tidak mencakup jalur penuh dari router.

**Perbaikan:** router kini memastikan setiap jawaban route tercatat pada team yang mendukung history. Balasan yang sudah dicatat agent tidak diduplikasi; perintah reset tetap mengosongkan sesi tanpa memasukkan respons reset ke riwayat. Dengan demikian, jawaban dari synthesizer dan handler langsung juga dapat dirujuk oleh permintaan lanjutan seperti “simpan rangkuman”.

**Validasi koreksi:** uji integrasi merutekan permintaan rangkum ke synthesizer, lalu menjalankan “simpan rangkuman” pada giliran berikutnya dan memeriksa file fixture berisi jawaban yang tepat. Uji deduplikasi dan handler-level ikut lulus. Validasi operasi ini menggunakan direktori sementara; tidak menulis ke Vault pengguna.

### Perapihan format catatan rangkuman untuk Obsidian

Catatan rangkuman kini menggunakan YAML frontmatter dengan `title`, `created` berformat ISO 8601, `category: "Rangkuman"`, dan tag YAML berupa daftar string: `rangkuman-percakapan` serta tag topik yang dinormalisasi. Judul utama Markdown tetap selaras dengan properti `title`, sementara jawaban assistant dipertahankan tanpa perubahan di bawahnya. Nilai frontmatter di-escape agar judul/topik dengan karakter khusus tidak merusak YAML.

**Validasi:** test simpan memeriksa properti metadata, tag kategori/topik, judul Markdown, dan isi rangkuman yang tetap utuh; alur router rangkum-lalu-simpan juga lulus di direktori sementara.

### Memastikan rangkuman mencakup seluruh catatan sumber

Kasus “rangkum Materi Les Carl - Pariwisata” menghasilkan ringkasan hanya dari potongan catatan yang retrieval pilih. Permintaan rangkuman bernama kini diarahkan langsung ke Bot Writer, yang menyelesaikan nama catatan di Vault dan membaca sumber, bukan hanya mengambil potongan retrieval. Prompt meminta seluruh konsep, klasifikasi, mekanisme, peran, contoh, kesimpulan, dan batasan unik; isi catatan diperlakukan sebagai data, bukan instruksi.

Pencocokan sumber tidak menggunakan fuzzy fallback yang memilih file sembarang: nama unik diproses, nama ambigu meminta path lebih spesifik, sedangkan catatan eksplisit yang tidak ditemukan menghasilkan pesan gagal dan tidak dirangkum dari hasil pencarian parsial. Hasil mencantumkan sumber untuk memudahkan verifikasi. Permintaan rangkuman tanpa referensi catatan yang dapat dikenali tetap memakai jalur tanya-jawab biasa.

**Validasi awal:** test memverifikasi isi sumber dan outline diberikan ke model, routing summary melewati classifier, sumber tidak ditemukan tidak menghasilkan ringkasan, serta nama ambigu meminta klarifikasi.

### Koreksi: sumber panjang dan contoh kode hilang dari rangkuman

Screenshot rangkuman “Materi Les Carl - Python Dasar” memperlihatkan contoh kode tidak ikut tampil. Catatan sumber itu sekitar 139 ribu karakter dengan 27 fenced code blocks; mengirim seluruh catatan dalam satu permintaan model tidak andal karena batas konteks dan mendorong model merangkum terlalu singkat.

**Perbaikan:** isi sumber kini dibagi ke potongan maksimal sekitar 12 ribu karakter tanpa memotong fenced code block. Setiap potongan dirangkum terpisah, lalu hasilnya disatukan menggunakan outline heading sebagai checklist cakupan. Ringkasan tiap bagian juga dipertahankan dalam output akhir di bawah `## Rangkuman Rinci per Bagian Sumber`, sehingga model sintesis akhir tidak dapat diam-diam membuang semua rincian bagian sebelumnya. Semua fenced code block sumber ditambahkan kembali secara verbatim pada bagian `## Kode dari Sumber`, sehingga kode tidak bergantung pada kemampuan model untuk mengingat atau menyalin contoh secara tepat. Kode diberi judul konteks dari heading terdekat dan sintaks fence aslinya dipertahankan.

Setiap chunk kini wajib menghasilkan ringkasan non-kosong; jika tidak, proses berhenti dengan pesan gagal alih-alih meneruskan hasil parsial seolah lengkap. Output memuat checklist deterministik `## Cakupan Pemrosesan Sumber` dengan satu item per chunk yang berhasil dirangkum. Checklist menjelaskan bahwa ia membuktikan pemrosesan, bukan pemahaman sempurna atas seluruh detail. Jika sintesis akhir kosong, rincian chunk tetap dikirim dengan peringatan yang jelas.

**Validasi:** tes memastikan catatan panjang menghasilkan beberapa permintaan model, detail ringkasan tiap bagian dan checklist tetap ada di output, blok kode tetap identik, serta ringkasan chunk kosong menghentikan proses. Pemeriksaan runtime pada catatan Python Dasar nyata menghasilkan 12 chunk, memproses 27 code block dan mempertahankan seluruh 27 pada lampiran kode.
