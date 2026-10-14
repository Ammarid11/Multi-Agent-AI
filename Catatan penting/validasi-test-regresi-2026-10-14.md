# Validasi Tes Regresi — 14 Oktober 2026

## Ringkasan

Suite tes regresi yang diminta berhasil dijalankan:

- **Hasil:** lulus, `96 tests`, `OK`
- **Durasi:** 0,547 detik
- **Exit code:** 0
- **Python:** `.venv` — Python 3.14.7

## Perintah

Dijalankan dari root proyek:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_router_and_session test_grounding_reliability test_memory_quality test_api_contract test_scheduler
```

## Interpretasi log

Output memuat beberapa warning dan traceback, tetapi proses tetap berakhir
dengan `Ran 96 tests ... OK`. Contohnya mencakup:

- `RuntimeError: model unavailable` pada pengujian fallback classifier.
- Kegagalan pencarian semantik pada jalur yang menguji fallback lexical/graph.
- Error backend pada tes kontrak API untuk memastikan kegagalan ditangani.
- `UnicodeDecodeError` saat tes memproses catatan dengan encoding tidak valid.
- Pesan bahwa database Qdrant terkunci atau koleksi yang ada tidak dapat
  dimuat.

Traceback yang sengaja dipicu dalam tes digunakan untuk memeriksa penanganan
kegagalan dan tidak menyebabkan suite gagal. Walau begitu, pesan Qdrant berarti
database vektor tidak tersedia secara normal selama output run ini; hasil
`OK` membuktikan tes-tes suite lulus, tetapi **bukan** validasi operasional
Qdrant live atau pengujian retrieval end-to-end terhadap koleksi produksi.

Jangan menghapus file lock atau database untuk mengatasi pesan tersebut.
Untuk validasi Qdrant live, hentikan server Carl secara normal terlebih dahulu
agar tidak ada proses lain yang memakai database yang sama, lalu jalankan tes
retrieval yang relevan dan periksa ringkasan akhirnya.

## Cakupan yang dijalankan

- `test_router_and_session`
- `test_grounding_reliability`
- `test_memory_quality`
- `test_api_contract`
- `test_scheduler`

Tes dijalankan tanpa mengubah kode atau data proyek.

## Validasi Tahap 1 — Router pertanyaan umum

Perintah terfokus:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_router_and_session.TestRouter
```

Hasil: **25 tes lulus** dalam 0,030 detik (`OK`, exit code 0).

Tes mencakup perilaku batas utama Tahap 1:

- Pertanyaan faktual umum seperti `Apa ibu kota Jepang?` diarahkan ke Writer
  tanpa memanggil classifier.
- Pertanyaan berbentuk tanya yang meminta aksi spesialis tetap menggunakan
  classifier.
- Pertanyaan web yang eksplisit tetap masuk jalur web cepat tanpa classifier.
- Permintaan kompleks diarahkan ke Reasoner, sedangkan pertanyaan faktual
  sederhana tidak dieskalasi.
- Rangkuman catatan bernama tetap diarahkan ke Writer agar jalur pemeriksaan
  sumber penuh tidak dilewati.
- Slash command dan fast intent lainnya tetap diuji terhadap prioritas routing.

Satu traceback `RuntimeError: model unavailable` tampil karena tes fallback
classifier sengaja membuat mock melempar error; tes tetap lulus dan mengharapkan
fallback ke intent `default`.

**Batas validasi:** pengujian ini berfokus pada pemilihan jalur router dengan
handler/mock terkontrol. Ia tidak mengukur latensi Ollama live, tidak
membuktikan kualitas jawaban produksi, dan tidak menguji retrieval Vault
end-to-end. Pengukuran 577/246/264 ms yang tercatat di rencana adalah hasil
sebelumnya, bukan pengukuran ulang pada run ini. Karena itu Tahap 1 lolos
validasi regresi routing, sedangkan validasi performa dan mutu end-to-end tetap
terbuka.

## Validasi Tahap 2 — Cache peta Vault

Tes terfokus yang memeriksa cache, perubahan struktur, dan pengecualian
direktori:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_grounding_reliability.TestGroundingAndRetrieval.test_vault_map_cache_skips_rescan_and_invalidates_structure_changes test_grounding_reliability.TestGroundingAndRetrieval.test_vault_map_uses_the_same_indexing_exclusions
```

Hasil: **2 tes lulus** dalam 0,013 detik (`OK`, exit code 0).

Seluruh modul regresi terkait kemudian dijalankan:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_grounding_reliability
```

Hasil: **28 tes lulus** dalam 0,188 detik (`OK`, exit code 0).

Tes cache memastikan:

- Panggilan kedua pada struktur Vault yang tidak berubah memakai cache dan
  tidak menjalankan `os.scandir`.
- Konten peta yang dikembalikan tetap sama dan `Master_Index.md` tidak ditulis
  ulang (mtime nanodetik tidak berubah).
- Penambahan catatan masuk ke peta; rename dan penghapusan tercermin setelah
  cache diinvalidasi.
- Peta dan pemindaian indeks mengabaikan direktori sistem/archive/template
  sesuai aturan pengecualian.

**Batas validasi:** tes perubahan struktur memakai Vault sementara, bukan
Vault produksi. Run ini mengonfirmasi perilaku dan regresi cache, tetapi tidak
mengulang benchmark 500 catatan, tidak mengukur latensi end-to-end, dan tidak
menguji invalidasi akibat perilaku filesystem khusus pada Vault pengguna.
Benchmark sintetis yang tercatat di rencana adalah hasil sebelumnya, bukan
pengukuran ulang pada run ini.

## Validasi Tahap 3 — Ringkasan history di background

Modul router dan session memory dijalankan:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_router_and_session
```

Hasil: **35 tes lulus** dalam 0,158 detik (`OK`, exit code 0).

Cakupan relevan yang diverifikasi oleh tes:

- Ringkasan dijadwalkan menggunakan snapshot; perubahan pada history sumber
  setelah submit tidak mengubah snapshot yang diproses.
- Setelah respons mencapai ambang ringkasan, handler tidak menunggu Future
  yang belum selesai.
- Persiapan prompt selanjutnya menunggu ringkasan tertunda, kemudian
  menerapkan ringkasan dan memangkas hanya history lama.
- Kegagalan generasi atau persistensi ringkasan tidak memangkas history.
- Ringkasan yang berhasil dipersist dan mempertahankan pesan terbaru.
- Reset menunggu Future sebelum menghapus penyimpanan persisten dan
  membersihkan state sesi.

Output juga memuat log Qdrant terkunci dan traceback `model unavailable`;
yang terakhir berasal dari tes fallback classifier yang sengaja memicu
exception. Rangkaian berakhir dengan `OK`.

**Batas validasi:** tes ringkasan/background menggunakan Future, mock, dan
penyimpanan sementara terkontrol; tidak menjalankan ringkasan Ollama live dan
tidak mengukur pengurangan latensi end-to-end. Run ini memverifikasi perilaku
dan regresi sinkronisasi, bukan ketahanan terhadap penghentian proses paksa
atau performa di bawah beban nyata.

## Validasi Tahap 4 — Polling status chat job di browser

Fungsi `pollChatJob` di `web/index.html` diuji langsung memakai Node.js dengan
respons `fetch` dan timer tiruan; tidak ada file test atau kode aplikasi yang
diubah.

Perilaku polling normal yang diverifikasi:

- Status yang stabil menaikkan jeda dari 500 ms ke 750 ms lalu mencapai plafon
  900 ms; pemeriksaan berulang tetap pada 900 ms.
- Perubahan status mereset jeda ke 500 ms.
- Status `completed` mengembalikan balasan tanpa melakukan polling tambahan;
  status `failed` langsung menghasilkan error.
- HTTP 503 memakai retry backoff 1.000 ms secara terpisah dari jeda polling
  normal, lalu polling normal dimulai kembali dari 500 ms.

Tes kontrak backend juga dijalankan:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_api_contract
```

Hasil: **15 tes lulus** dalam 0,263 detik (`OK`, exit code 0), termasuk
pembuatan chat job dan pemeriksaan status melalui endpoint yang digunakan UI.
Traceback error backend dan pembacaan UTF-8 yang tampil merupakan skenario
kegagalan yang diuji; suite berakhir `OK`.

**Batas validasi:** polling diuji dengan timer dan respons tiruan, sedangkan
tes API memakai executor/router mock. Belum dilakukan pengukuran pada browser
nyata, jaringan nyata, atau beban banyak tab/klien; jadi hasil membuktikan
logika interval, penghentian terminal, retry, dan kontrak API, bukan manfaat
latensi atau dampak beban di produksi.

## Validasi Tahap 6 — Metrik antrean chat job

Seluruh tes kontrak API dijalankan dengan interpreter proyek:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_api_contract
```

Hasil: **15 tes lulus** dalam 0,255 detik (`OK`, exit code 0).

Tes serial `test_serial_chat_jobs_report_queue_and_execution_durations`
menjalankan executor terkontrol dengan satu worker, menahan job pertama
sekurangnya 50 ms, lalu memasukkan job kedua. Tes memastikan job kedua masih
berstatus `queued` sebelum worker tersedia, kedua job kemudian selesai
berurutan, serta respons status memberikan `queue_wait_ms` dan
`execution_ms`. Waktu tunggu job kedua harus sekurangnya 10 ms; nilai
`execution_ms` juga diverifikasi sebagai angka nonnegatif.

Source API mempertahankan `ThreadPoolExecutor(max_workers=1)`. Metrik memakai
`time.perf_counter()` dan endpoint status melaporkan waktu tunggu ketika job
queued serta waktu tunggu/eksekusi setelah job mulai.

**Batas validasi:** ini menguji correctness metrik dan serialisasi dengan
router tiruan, bukan beban Ollama nyata, throughput, p50/p95, atau dampak
perangkat. Tes tidak mengukur apakah penambahan worker bermanfaat; jumlah
worker sengaja tidak dinaikkan. Traceback kegagalan backend serta UTF-8 dalam
output adalah skenario yang dites, dan keseluruhan modul berakhir `OK`.

## Validasi Tahap 7 — Retrieval adaptif

Modul tes kualitas retrieval dijalankan:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest test_memory_quality
```

Hasil: **14 tes lulus** dalam 0,027 detik (`OK`, exit code 0).

Cakupan fast path dan fallback yang diverifikasi:

- Query yang menyebut judul catatan yang ditemukan oleh pencarian keyword
  melewati query expansion.
- Retrieval awal yang lemah tetap memanggil ekspansi dan dokumen yang ditemukan
  lewat query alternatif dapat masuk ke konteks.
- Kegagalan query alternatif tidak mengubah keberhasilan pencarian vektor awal
  menjadi status “semantic retrieval unavailable”.
- Kegagalan pencarian vektor awal ditandai secara eksplisit dan tidak
  menjalankan query expansion.
- Merge hasil antarquery menghilangkan duplikasi.

Output menampilkan exception `alternate query failed` dan `backend unavailable`
karena kedua keadaan tersebut sengaja disimulasikan oleh tes; rangkaian
berakhir `OK`.

**Batas validasi:** retrieval memakai dokumen/store tiruan yang hasilnya
dikendalikan tes. Belum ada benchmark recall/ranking pada Vault nyata, evaluasi
jawaban end-to-end, atau pengukuran p50/p95. Hasil ini membuktikan alur
fast-path/fallback dan penanganan error, bukan bahwa relevansi produksi tidak
berubah atau meningkat.

## Validasi Tahap 5 — Snapshot cold/warm keep-alive tanpa penerapan

Atas persetujuan pengguna, Ollama lokal diuji secara langsung dengan dua
request berurutan ke `deepseek-r1:8b`. Tidak ada perubahan source code atau
konfigurasi Carl. Request memakai baseline `keep_alive: "30s"`, context
terbatas `num_ctx: 2048`, temperature `0.6`, dan batas output pendek.

### Snapshot sebelum uji

- NVIDIA GeForce RTX 4060: 8.188 MiB total, 5.584 MiB VRAM bebas; GPU 3%,
  45°C.
- RAM: 31,93 GiB total, 5,69 GiB bebas.
- Ollama `/api/ps`: tidak ada model aktif.
- Reasoner terpasang sebagai `Q4_K_M`, ukuran inventaris 5.225.376.047 byte.

### Hasil inference

| Run | Batas output | Waktu client | `total_duration` Ollama | Token prompt/output | Hasil |
|---|---:|---:|---:|---:|---|
| Cold | 48 | 17.405 ms | 15.322,62 ms | 21 / 48 | Request selesai; content kosong karena batas token habis pada penalaran |
| Warm | 48 | 1.422 ms | 1.421,38 ms | 21 / 48 | Request selesai; content kosong karena batas token habis pada penalaran |
| Warm fungsional tambahan | 512 | 12.492 ms | 10.438,2 ms | 21 / 363 | Menjawab Tokyo, tetapi menambahkan detail sejarah tidak akurat/tidak diperlukan |

Saat model aktif, `/api/ps` melaporkan `size_vram` 5.274.117.078 byte dan
context 2.048. Snapshot GPU menunjukkan VRAM bebas turun hingga 537 MiB (GPU
terukur 51°C, penggunaan GPU 11%). Tidak ada exception/OOM; namun hasil jawaban
belum lulus pemeriksaan mutu sederhana.

### Auto-unload dan kondisi sesudah uji

Setelah menunggu 35 detik dari request terakhir dengan keep-alive 30 detik:

- Ollama `/api/ps` kembali menunjukkan tidak ada model aktif.
- VRAM bebas: 5.562 MiB dari 8.188 MiB; penggunaan GPU 0%, suhu 49°C.
- RAM bebas: 4,36 GiB pada snapshot akhir, dibanding 5,69 GiB sebelum uji.
  RAM tidak pulih ke baseline selama observasi; penyebab perbedaan tidak dapat
  dipastikan hanya dari snapshot ini.

**Kesimpulan terbatas:** cold/warm request dengan context 2.048 berhasil
dijalankan pada kondisi saat itu, warm request jauh lebih cepat, dan model
auto-unload setelah baseline 30 detik. Headroom VRAM sangat tipis (minimum
537 MiB), kualitas keluaran tidak konsisten, dan RAM bebas menurun pada
snapshot akhir. Karena itu ini **bukan** bukti bahwa keep-alive lebih lama,
context produksi, atau sesi panjang akan stabil.

**Keputusan:** tidak menerapkan perubahan. `KEEP_ALIVE_DEFAULT` tetap `2m`
dan `KEEP_ALIVE_SPECIALIST` tetap `30s`. Catatan baseline/pemulihan dan detail
run tersimpan di
[backup-tahap-5-keep-alive-2026-10-14.md](./backup-tahap-5-keep-alive-2026-10-14.md).
