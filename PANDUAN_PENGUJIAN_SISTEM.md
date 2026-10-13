# 🧪 Panduan Lengkap Pengujian Sistem Carl AI (Multi-Agent Second Brain)

Dokumen ini berisi panduan pengujian menyeluruh (End-to-End Test Guide) untuk seluruh fitur dan agen pada sistem **Carl Multi-Agent AI**. Setiap pengujian dilengkapi dengan **tujuan**, **langkah-langkah**, **teks persis yang harus diketik ke AI**, serta **ekspektasi hasil** dan **cara verifikasinya**.

---

## 📋 Daftar Isi
1. [Persiapan Lingkungan (Pre-requisites)](#1-persiapan-lingkungan-pre-requisites)
2. [Skenario 1: Les Privat Carl & Guru Gemini (Frontier Q)](#2-skenario-1-les-privat-carl--guru-gemini-frontier-q)
   - [1A: Mode Unlimited & Live Incremental Save](#1a-mode-unlimited--live-incremental-save)
   - [1B: Mode Putaran Dibatasi (Limited Turns)](#1b-mode-putaran-dibatasi-limited-turns)
   - [1C: Respon Kuis / Pertanyaan Gemini](#1c-respon-kuis--pertanyaan-gemini)
   - [1D: Graceful Exit (Tutup Tab Browser Tanpa Error)](#1d-graceful-exit-tutup-tab-browser-tanpa-error)
3. [Skenario 2: Google Gemini Browser Bridge (Frontier P)](#3-skenario-2-google-gemini-browser-bridge-frontier-p)
4. [Skenario 3: Tanya Jawab Memori Second Brain (RAG Vault & Qdrant)](#4-skenario-3-tanya-jawab-memori-second-brain-rag-vault--qdrant)
5. [Skenario 4: Autonomous Goal & Council of Experts](#5-skenario-4-autonomous-goal--council-of-experts)
6. [Skenario 5: Manajemen Vault, Canvas, & Sentinel](#6-skenario-5-manajemen-vault-canvas--sentinel)
7. [Skenario 6: Riset Web & Autonomous Browser](#7-skenario-6-riset-web--autonomous-browser)
8. [Skenario 7: Python Code Sandbox & Self-Debug](#8-skenario-7-python-code-sandbox--self-debug)
9. [Skenario 8: Visualisasi Galaksi Pengetahuan 3D (Frontier O)](#9-skenario-8-visualisasi-galaksi-pengetahuan-3d-frontier-o)
10. [Skenario 9: Evaluator & Anti-Halusinasi](#10-skenario-9-evaluator--anti-halusinasi)
11. [Skenario 10: Pengujian Otomatis via Terminal (Unit Tests)](#11-skenario-10-pengujian-otomatis-via-terminal-unit-tests)
12. [Tabel Ringkasan Cheat Sheet Perintah](#12-tabel-ringkasan-cheat-sheet-perintah)

---

## 1. Persiapan Lingkungan (Pre-requisites)

Sebelum memulai pengujian, pastikan service berikut aktif:

1. **Ollama Service**:
   Pastikan model lokal tersedia:
   ```powershell
   ollama list
   ```
   *(Pastikan minimal `qwen2.5:7b` atau model yang diatur di `config.py` sudah terpasang).*

2. **Obsidian Vault**:
   Buka aplikasi **Obsidian** dan arahkan ke folder vault:
   `E:\Project AI 2026\Obsidian\Brain AI Memory`

3. **Jalankan Server AI**:
   Buka terminal di folder proyek (`e:\Project AI 2026\Multi-Agent AI`) dan jalankan:
   ```powershell
   .\server.bat
   ```
   Tunggu hingga muncul pesan server siap menerima request di Telegram Bot atau Web Chat.

---

## 2. Skenario 1: Les Privat Carl & Guru Gemini (Frontier Q)

Fitur ini membuat Carl bertindak sebagai murid manusia yang penasaran, belajar langsung dari Google Gemini di browser Microsoft Edge, dan menyerap ilmunya langsung ke Obsidian.

---

### 1A: Mode Unlimited & Live Incremental Save
* **Tujuan**: Memastikan Carl terus menggali ilmu tanpa henti, bertanya maksimal 1-2 kalimat alami, dan menyimpan catatan ke Obsidian setiap kali Gemini menjawab secara realtime.
* **Langkah-langkah**:
  1. Buka chat dengan AI (Telegram atau Web UI).
  2. Ketik perintah di bawah dan kirim.
  3. Perhatikan browser Edge yang terbuka otomatis membuka `gemini.google.com`.
  4. Buka folder `03-Resources` di Obsidian.
* **Teks yang diketik ke AI**:
  ```text
  /les Fisika Termodinamika
  ```
* **Ekspektasi Hasil**:
  - Di terminal: Muncul log `[Babak 0] Carl membuka sesi les...` disusul `[Putaran 1] Carl bertanya...`.
  - Di Obsidian: File `03-Resources/Materi Les Carl - Fisika Termodinamika.md` langsung dibuat dan bertambah panjang setiap putaran tanpa menunggu sesi ditutup.
  - Teks Carl ke Gemini: Pendek (maks 1-2 kalimat), tidak ada kata "AI", "sistem", atau "bot".

---

### 1B: Mode Putaran Dibatasi (Limited Turns)
* **Tujuan**: Memastikan Carl berhenti dan pamit secara sopan setelah jumlah putaran tertentu tercapai.
* **Langkah-langkah**:
  1. Ketik perintah dengan menyertakan angka putaran di belakang.
* **Teks yang diketik ke AI**:
  ```text
  /les Algoritma Dijkstra 3
  ```
* **Ekspektasi Hasil**:
  - Carl berinteraksi sebanyak Babak 0 (pembuka) + 3 putaran tanya jawab.
  - Pada putaran ke-3, Carl pamit: *"Terima kasih banyak! Penjelasan tadi sangat membantu. Sampai ketemu lagi ya!"*.
  - Catatan di Obsidian dirapikan (*Merge & Refine*) dan diindeks ke memori vektor Carl.

---

### 1C: Respon Kuis / Pertanyaan Gemini
* **Tujuan**: Memastikan Carl mendeteksi jika Gemini memberikan soal atau kuis, lalu Carl menjawab langkah-langkahnya (bukan malah bertanya balik).
* **Langkah-langkah**:
  1. Mulai sesi dengan topik kuis dasar matematika/logika.
* **Teks yang diketik ke AI**:
  ```text
  /les Latihan Soal Aljabar Dasar 2
  ```
* **Ekspektasi Hasil**:
  - Jika Gemini memberi soal (misal: *"Coba cari nilai x dari 2x + 4 = 10"*), Carl akan menghitung: *"2x = 6, maka x = 3. Apakah jawaban saya benar, Guru?"*.
  - Jawaban nyambung lurus dengan topik dan soal yang diajukan.

---

### 1D: Graceful Exit (Tutup Tab Browser Tanpa Error)
* **Tujuan**: Memastikan jika pengguna sengaja atau tidak sengaja menutup tab browser Gemini saat sesi les sedang berjalan, sistem tidak crash atau melempar error `Locator.fill`, melainkan tetap menyimpan apa yang sudah didapat secara rapi ke Obsidian.
* **Langkah-langkah**:
  1. Jalankan sesi les:
     ```text
     /les Arsitektur Komputer
     ```
  2. Tunggu sampai Putaran 1 atau Putaran 2 selesai di terminal.
  3. Klik tombol **Close (X)** pada tab browser Edge Gemini yang sedang dibuka otomatis.
* **Ekspektasi Hasil**:
  - Terminal menampilkan: `⚠️ [Carl Academy] Browser ditutup / dihentikan manual. Menyimpan N putaran materi...`
  - Pesan balasan ramah: `⚠️ Sesi les selesai karena browser ditutup / dihentikan — seluruh materi tetap tersimpan aman!` (tanpa tanda silang merah `❌` dan tanpa error `Locator.fill`).
  - Catatan putaran 1-2 yang sudah terkumpul tetap tersimpan rapi di Obsidian.

---

### 1E: Penghentian Manual Sesi Les (Tombol Stop UI atau Perintah /stop)
* **Tujuan**: Memastikan pengguna bisa menghentikan Carl kapan saja saat sesi les sedang berlangsung tanpa perlu menutup browser secara paksa.
* **Langkah-langkah Opsi 1 (Via Web Chat UI)**:
  1. Jalankan sesi les di Web Chat:
     ```text
     /les Teori Relativitas Einstein
     ```
  2. Perhatikan tombol merah **`🛑 Berhenti`** yang otomatis muncul di samping tombol kirim (atau klik tombol **`🛑 Stop Les`** di Quick Action bar).
  3. Klik tombol tersebut saat Carl sedang mengobrol dengan Gemini.
* **Langkah-langkah Opsi 2 (Via Perintah Chat)**:
  1. Ketik perintah:
     ```text
     /stop
     ```
     *(atau ketik `batal`)*
* **Ekspektasi Hasil**:
  - Sesi langsung berhenti di putaran berjalan.
  - Seluruh materi yang sudah sempat diajarkan Gemini dirapikan (*Merge & Refine*) ke Obsidian.
  - AI membalas dengan rangkuman materi yang berhasil didapat dan konfirmasi penyimpanan aman.

---

## 3. Skenario 2: Google Gemini Browser Bridge (Frontier P)

Fitur untuk meminta penjelasan sekali kirim (*one-off*) atau dialog langsung antara Carl dan Gemini.

### 2A: Tanya Gemini Sekali Kirim
* **Tujuan**: Menanyakan pertanyaan spesifik ke Gemini via browser automation dan mendapatkan jawaban langsung di chat.
* **Teks yang diketik ke AI**:
  ```text
  /gemini Apa perbedaan mendasar antara Quantum Computing dan Komputer Klasik dalam 3 poin singkat?
  ```
* **Ekspektasi Hasil**:
  - AI membuka browser, mengirim prompt ke Gemini, mengambil jawabannya, dan menampilkan langsung di pesan balasan chat.

---

### 2B: Dialog Kolaborasi Carl & Gemini
* **Tujuan**: Diskusi 3 arah seputar topik tertentu di mana Carl dan Gemini saling melempar argumen, lalu disimpan ke `Diskusi Carl & Gemini - [Topik].md`.
* **Teks yang diketik ke AI**:
  ```text
  /gemini_dialog Masa Depan Kecerdasan Buatan 2030
  ```
* **Ekspektasi Hasil**:
  - Carl dan Gemini saling menanggapi selama 3 putaran.
  - Transkrip percakapan tersimpan di Obsidian folder `03-Resources`.

---

## 4. Skenario 3: Tanya Jawab Memori Second Brain (RAG Vault & Qdrant)

Fitur inti Carl sebagai Second Brain pribadi yang mengingat seluruh catatan di Obsidian.

### 3A: Menguji Pengetahuan yang Baru Saja Dipelajari dari Les
* **Tujuan**: Memastikan Carl sudah menyerap materi yang baru saja dipelajari pada Skenario 1.
* **Teks yang diketik ke AI**:
  ```text
  Carl, apa yang baru saja kamu pelajari dari Guru Gemini tentang Termodinamika? Coba jelaskan kembali intinya kepadaku.
  ```
* **Ekspektasi Hasil**:
  - Carl menjawab dengan mengutip dan menyarikan catatan yang baru tersimpan di Obsidian.

---

### 3B: Menguji Pencarian Catatan Internal
* **Tujuan**: Menguji RAG semantik dari catatan-catatan lama di Vault.
* **Teks yang diketik ke AI**:
  ```text
  Apa saja catatan penting yang tersimpan di Second Brain saya tentang arsitektur atau proyek sistem?
  ```
* **Ekspektasi Hasil**:
  - Carl menyebutkan nama file dan konteks catatan yang relevan dari Vault.

---

## 5. Skenario 4: Autonomous Goal & Council of Experts

### 4A: Autonomous Goal Engine (ReAct Loop)
* **Tujuan**: AI memecah tujuan besar menjadi langkah-langkah nyata, mengeksekusinya secara otonom, dan mendokumentasikan hasilnya.
* **Teks yang diketik ke AI**:
  ```text
  /goal Buat analisis perbandingan arsitektur Monolith vs Microservices beserta studi kasusnya dan buatkan catatan baru di vault
  ```
* **Ekspektasi Hasil**:
  - AI menampilkan langkah-langkah berpikir (*Thinking / Action / Observation*).
  - Berkas catatan baru dibuat di Vault Obsidian.

---

### 4B: Council of Experts (Debat 3 Sudut Pandang)
* **Tujuan**: Menghadirkan debat internal antara Coder, Devil's Advocate (pengkritik), dan Carl Synthesizer sebelum mengambil keputusan arsitektur.
* **Teks yang diketik ke AI**:
  ```text
  /council Apakah kita harus menggunakan arsitektur Event-Driven untuk aplikasi IoT skala kecil?
  ```
* **Ekspektasi Hasil**:
  - Menampilkan 3 perspektif berbeda:
    1. **Coder**: Sudut pandang implementasi teknis.
    2. **Devil's Advocate**: Sudut pandang risiko dan kompleksitas berlebih.
    3. **Carl Consensus**: Kesimpulan dan jalan tengah terbaik.

---

## 6. Skenario 5: Manajemen Vault, Canvas, & Sentinel

### 6A: Generate Obsidian Visual Canvas (.canvas)
* **Tujuan**: Membuat diagram visual peta pikiran interaktif yang dapat langsung dibuka di Obsidian Canvas.
* **Teks yang diketik ke AI**:
  ```text
  /canvas Peta Konsep Machine Learning Modern
  ```
* **Ekspektasi Hasil**:
  - File `.canvas` terbuat di folder `03-Resources` atau root Vault.
  - Buka file tersebut di Obsidian untuk melihat node dan panah relasi konsep secara visual.

---

### 6B: Morning Briefing & Deadline Scan
* **Tujuan**: Memindai to-do list, catatan harian, dan agenda di Vault.
* **Teks yang diketik ke AI**:
  ```text
  /briefing
  ```
* **Ekspektasi Hasil**:
  - Menampilkan ringkasan agenda hari ini, tugas yang belum selesai, dan catatan yang perlu ditinjau.

---

### 6C: Vault Sentinel Audit & Auto-Heal
* **Tujuan**: Memeriksa kesehatan tautan rusak (*broken links*) atau catatan yatim (*orphan notes*) di Obsidian, lalu memperbaikinya.
* **Langkah-langkah**:
  1. Audit kesehatan vault:
     ```text
     /sentinel
     ```
  2. Perbaiki otomatis masalah yang ditemukan:
     ```text
     /heal
     ```
* **Ekspektasi Hasil**:
  - Menampilkan laporan status kesehatan file markdown di Vault dan status perbaikannya.

---

### 6D: 1-Click Vault Backup
* **Tujuan**: Mencadangkan seluruh isi Obsidian Vault menjadi arsip `.zip` bertanda waktu.
* **Teks yang diketik ke AI**:
  ```text
  /backup
  ```
* **Ekspektasi Hasil**:
  - File backup `.zip` terbuat di folder backup yang telah dikonfigurasi.

---

## 7. Skenario 6: Riset Web & Autonomous Browser

### 7A: Autonomous Web Browser (Playwright)
* **Tujuan**: Mengunjungi URL web, mengekstrak teks penting, dan merangkumnya.
* **Teks yang diketik ke AI**:
  ```text
  /browser https://news.ycombinator.com
  ```
* **Ekspektasi Hasil**:
  - AI membuka halaman web via browser headless, membaca konten berita teknologi terpopuler, dan merangkumnya untuk pengguna.

---

### 7B: Academic Paper Ingestion (arXiv)
* **Tujuan**: Mencari paper penelitian ilmiah terkini dan mengekstrak abstraknya.
* **Teks yang diketik ke AI**:
  ```text
  /research Direct Preference Optimization LLM
  ```
* **Ekspektasi Hasil**:
  - Menampilkan judul paper, penulis, dan intisari penelitian terkini dari arXiv.

---

## 8. Skenario 7: Python Code Sandbox & Self-Debug

* **Tujuan**: Menjalankan potongan kode Python di lingkungan terisolasi dengan kemampuan memperbaiki kodenya sendiri jika terjadi error (*self-debug*).
* **Teks yang diketik ke AI**:
  ```text
  /sandbox
  ```
  *(Atau ketik prompt instruksi kode):*
  ```text
  Tolong jalankan skrip Python untuk menghitung 10 bilangan Fibonacci pertama dan tampilkan hasilnya.
  ```
* **Ekspektasi Hasil**:
  - AI mengeksekusi kode di sandbox aman dan menampilkan output: `[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]`.

---

## 9. Skenario 8: Visualisasi Galaksi Pengetahuan 3D (Frontier O)

* **Tujuan**: Membuka antarmuka 3D interaktif visualisasi seluruh jaringan ide di Second Brain.
* **Teks yang diketik ke AI**:
  ```text
  /galaxy
  ```
* **Ekspektasi Hasil**:
  - AI memberikan link antarmuka: `http://localhost:8000/galaxy`.
  - Buka di browser: Tampil visualisasi bintang-bintang 3D yang dapat di-rotate, zoom, dan diklik untuk melihat relasi antar dokumen di Vault.

---

## 10. Skenario 9: Evaluator & Anti-Halusinasi

* **Tujuan**: Mengukur retrieval dokumen target dengan sampel sintetis dari judul/heading Vault. Ini bukan evaluasi akurasi jawaban Carl.
* **Teks yang diketik ke AI**:
  ```text
  /eval
  ```
* **Ekspektasi Hasil**:
  - Menampilkan Hit Rate@1, Hit Rate@3, MRR, latensi, dan jumlah sampel.
  - Laporan menyebutkan bahwa metrik ini hanya smoke benchmark retrieval, bukan akurasi jawaban atau skor halusinasi Carl.

---

## 11. Skenario 10: Pengujian Otomatis via Terminal (Unit Tests)

Pengujian ini dijalankan langsung di PowerShell untuk memverifikasi seluruh komponen tanpa perlu mengetik di chat satu per satu.

### 11A: Uji Modul Gemini Browser Bridge
```powershell
python test_gemini_browser.py
```
* **Ekspektasi Hasil**:
  ```text
  Ran 8 tests in ~0.10s
  OK
  ```
  *(Memverifikasi: anti-refusal, anti-detection, kuis answering, infinite loop, dynamic topic detection, incremental vault save, dll).*

### 11B: Uji Evaluasi Anti-Halusinasi
```powershell
python test_antihalu.py
```
* **Ekspektasi Hasil**: Seluruh regression tests guardrail yang tersedia passing. Ini bukan skor faktualitas jawaban Carl.

### 11C: Uji Regresi Retrieval dan Evaluator
```powershell
python -m unittest test_memory_quality -v
```
* **Ekspektasi Hasil**: Test memverifikasi merger query expansion, deduplikasi dokumen, ranking sumber eksplisit, dataset kosong, error vector retrieval, dan checklist jawaban.

### 11D: Benchmark Checklist Jawaban Carl
Isi dataset dengan fakta dan sumber yang sudah diverifikasi manusia, kemudian jalankan:
```powershell
.\.venv\Scripts\python.exe evaluate_answers.py
```
Detail format, metrik, dan batasan ada di `evaluation/README.md`. Dataset template yang masih kosong tidak menghasilkan skor dan tidak akan menjalankan model.

### 11E: Uji Batch Regresi Sistem
Jalankan pengujian batch sesuai kebutuhan:
```powershell
python test_batch1.py
python test_batch2.py
python test_batch3.py
python test_batch4.py
python test_batch5.py
```

---

## 12. Tabel Ringkasan Cheat Sheet Perintah

| Perintah | Contoh Teks Lengkap | Fungsi Utama |
| :--- | :--- | :--- |
| `/les <topik>` | `/les Jaringan Saraf Tiruan` | Sesi les privat Carl & Gemini tanpa henti + live Obsidian save |
| `/les <topik> <N>` | `/les Fisika Nuklir 4` | Sesi les privat dibatasi $N$ putaran |
| `/gemini <prompt>` | `/gemini Ringkas Hukum Kepler` | Tanya langsung ke Google Gemini via browser |
| `/gemini_dialog <topik>` | `/gemini_dialog Eksplorasi Mars` | Diskusi 3 putaran Carl & Gemini |
| `/goal <tujuan>` | `/goal Rancang skema database e-commerce` | ReAct Autonomous Engine menyelesaikan tugas kompleks |
| `/council <topik>` | `/council Pilih PostgreSQL atau MongoDB` | Debat 3 pakar (Coder, Devil's Advocate, Carl) |
| `/canvas <topik>` | `/canvas Konsep Deep Learning` | Buat diagram visual `.canvas` di Obsidian |
| `/briefing` | `/briefing` | Laporan harian to-do & agenda dari catatan Vault |
| `/sentinel` | `/sentinel` | Audit kesehatan tautan & berkas di Vault |
| `/heal` | `/heal` | Otomatis perbaiki masalah tautan di Vault |
| `/backup` | `/backup` | Backup 1-klik seluruh Vault ke format `.zip` |
| `/browser <url>` | `/browser https://news.ycombinator.com` | Jelajahi web dan ekstrak data secara otonom |
| `/research <query>` | `/research LoRA Fine-Tuning LLM` | Riset paper ilmiah dari arXiv |
| `/sandbox` | `/sandbox` | Eksekusi skrip Python aman dengan self-debug |
| `/galaxy` | `/galaxy` | Buka visualisasi konstelasi pengetahuan 3D |
| `/evaluator` | `/evaluator` | Evaluasi skor anti-halusinasi & akurasi memori |

---

> 💡 **Tips Pengujian:**
> Jika Anda baru saja mengedit kode Python, selalu restart `server.bat` (tekan `Ctrl+C` lalu ketik `.\server.bat`) sebelum menjalankan pengujian di atas agar perubahan langsung diterapkan.
