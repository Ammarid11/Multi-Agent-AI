# Rencana Bertahap Mempercepat Respons Carl

## Tujuan

Mengurangi waktu tunggu Carl secara bertahap tanpa sengaja mengurangi kualitas
jawaban, kemampuan retrieval, atau penalaran. Setiap tahap mengubah **satu hal
saja**, kemudian diuji sebelum memulai tahap berikutnya.

Tidak ada janji bahwa respons dapat selalu dibuat lebih cepat tanpa trade-off.
Perubahan hanya dipertahankan jika hasil pengukuran menunjukkan manfaat dan
tes kualitas terkait tetap lulus.

## Aturan Pelaksanaan

1. Catat baseline sebelum setiap perubahan.
2. Ubah satu komponen atau satu perilaku dalam satu tahap.
3. Jalankan pengukuran kecepatan dengan input dan kondisi yang sama sebelum dan
   sesudah perubahan.
4. Pisahkan waktu pemuatan model pertama (cold) dari panggilan berikutnya
   (warm).
5. Uji setidaknya pertanyaan faktual sederhana, pertanyaan berbasis Vault,
   pertanyaan kompleks yang diarahkan ke Reasoner, dan jalur tool yang relevan
   dengan perubahan.
6. Jalankan tes regresi dan benchmark kualitas yang sesuai. Jangan menerima
   percepatan yang berasal dari melewati retrieval, menurunkan model, memotong
   konteks penting, atau memangkas jawaban.
7. Catat perubahan, hasil, konfigurasi, dan keterbatasan sebelum melanjutkan.
8. Jika kualitas turun, hasil ukur tidak konsisten, atau timbul efek samping,
   hentikan tahap tersebut dan perbaiki atau batalkan hanya perubahan tahap
   itu. Pertahankan pekerjaan lokal lain.

## Baseline Awal

### Pengukuran lokal awal yang tersedia

- Server lokal yang diuji: `http://127.0.0.1:8000`
- Pertanyaan: `Apa ibu kota Jepang? Jawab singkat.`
- Total waktu terukur melalui API job hingga hasil diterima: **19.443 ms**
- Jawaban tersebut dialihkan keliru ke jalur pencarian web, sehingga ini bukan
  pembanding kualitas yang setara dengan jalur pertanyaan umum.

### Pengukuran router setelah Tahap 1

Pengukuran lokal langsung melalui router, dengan classifier dilarang berjalan
dan peta Vault dimock kosong:

- Putaran 1: **577 ms**
- Putaran 2: **246 ms**
- Putaran 3: **264 ms**
- Jawaban: `Ibu kota Jepang adalah Tokyo.`

**Batas perbandingan:** dua pengukuran tersebut memakai jalur yang berbeda.
Angka 19.443 ms mencakup server/API dan salah routing ke web; angka 577/246/264
ms mengukur router langsung, tanpa retrieval/peta Vault. Karena itu angka ini
menunjukkan jalur cepat bekerja, tetapi tidak membuktikan besarnya penghematan
end-to-end pada server penuh. Baseline ulang yang setara perlu direkam untuk
tahap optimasi berikutnya.

## Tahapan

### Tahap 1 — Hindari classifier LLM untuk pertanyaan umum

**Status:** Selesai dan diterapkan.

- Pertanyaan informasi biasa yang diawali kata tanya diarahkan langsung ke
  Writer jika tidak mengandung petunjuk aksi khusus.
- Slash command, pencarian web yang jelas, serta permintaan tindakan khusus
  tetap diproses oleh jalur khusus/classifier yang sesuai.
- Permintaan analisis kompleks tetap dapat memakai Reasoner; rangkuman catatan
  tetap memakai alur rangkuman khusus.

**Validasi:**

- Run terfokus terbaru: 25 tes `TestRouter` lulus (0,030 detik, exit code 0).
- Cakupan tes membuktikan pertanyaan faktual umum melewati classifier, web
  eksplisit tetap ke jalur web, tindakan spesialis tetap dapat memakai
  classifier, dan pertanyaan kompleks masih dieskalasi ke Reasoner.
- Uji terukur langsung menghasilkan jawaban yang benar dalam 577/246/264 ms.
- Server lokal harus direstart agar proses aktif memakai kode baru.
- Validasi terfokus ini menguji routing dengan handler/mock terkontrol; bukan
  pengukuran Ollama live atau validasi kualitas/retrieval end-to-end. Rincian
  dan batasan run terbaru tercatat di
  [validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md).

**Dampak perubahan:**

- Pertanyaan biasa tidak lagi menunggu classifier LLM sebelum masuk ke Writer.
- Pada uji router langsung, classifier dipastikan tidak dipanggil dan jawaban
  faktual tetap benar.
- Baseline server lama 19.443 ms salah dialihkan ke web, sedangkan uji baru
  dilakukan langsung melalui router dengan peta Vault dimock. Jadi belum ada
  pengukuran end-to-end yang setara untuk menyatakan penghematan latensi
  server secara pasti.
- Heuristik pertanyaan umum berisiko mengarahkan pertanyaan berbentuk tanya
  yang sebenarnya meminta aksi khusus ke Writer.

**Cara mengurangi dampak/risiko:**

- Jalankan slash command, intent cepat, dan deteksi petunjuk aksi khusus
  sebelum aturan pertanyaan umum; permintaan web/canvas/tool tetap memakai
  jalur yang sesuai.
- Pertahankan fallback classifier untuk bentuk kalimat yang ambigu atau tidak
  dikenali.
- Tambahkan tes regresi untuk kata tanya yang meminta aksi, serta uji ulang
  endpoint server penuh sebelum mengklaim angka percepatan end-to-end.

### Tahap 2 — Cache peta Vault yang dibuat untuk setiap jawaban

**Status:** Selesai dan diterapkan.

- Peta disimpan di cache proses dan dipakai ulang selama metadata direktori
  yang masuk indeks tidak berubah. Perubahan struktur memicu pemindaian ulang;
  pemeriksaan cache normal cukup memeriksa metadata direktori.
- `Master_Index.md` hanya ditulis jika konten hasil pemindaian berbeda.
- Penambahan, rename, dan penghapusan catatan tercakup oleh tes invalidasi.

**Validasi:**

- Seluruh 27 tes di `test_grounding_reliability` lulus.
- Run regresi ulang 14 Oktober 2026: seluruh 28 tes di
  `test_grounding_reliability` lulus (0,188 detik, exit code 0). Dua tes
  terfokus untuk cache/invalidasi struktur dan pengecualian direktori juga
  lulus (0,013 detik).
- Tes cache memastikan pemanggilan berulang pada struktur tetap tidak
  memanggil `scandir`, tidak mengubah waktu modifikasi `Master_Index.md`, dan
  hasil mengikuti penambahan, rename, serta penghapusan.
- Benchmark sintetis dengan 500 catatan: sebelum perubahan, lima panggilan
  penuh menghasilkan median 14,54 ms (rentang 14,34–16,04 ms); setelah
  pemanggilan awal, lima panggilan cache menghasilkan median 0,758 ms
  (rentang 0,721–1,405 ms).
- Benchmark ini mengukur fungsi peta pada Vault sementara, bukan latensi
  end-to-end Carl atau Vault produksi.
- Run ulang terbaru memverifikasi regresi dengan Vault sementara; tidak
  mengulang benchmark 500 catatan maupun mengukur latensi end-to-end. Detail
  perintah dan batas hasil ada di
  [validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md).

**Dampak terukur dan mitigasi:**

- Panggilan berulang saat struktur stabil menghindari enumerasi catatan dan
  penulisan indeks; hasil benchmark sintetis menunjukkan penurunan median
  sekitar 94,8% pada jalur cache.
- Risiko peta basi dikurangi dengan memeriksa timestamp perubahan direktori,
  lalu membangun ulang peta saat metadata berubah. Tes membuktikan skenario
  tambah/rename/hapus; perubahan isi catatan tanpa perubahan nama tidak perlu
  mengubah peta nama berkas.
- Cache bersifat per proses; setelah restart Carl membangun ulang peta sekali.
- Angka latensi masih sintetis dan belum membuktikan peningkatan end-to-end;
  ukur kembali pada server lokal sebelum mengklaim dampak ke waktu balasan.

### Tahap 3 — Peringkasan riwayat percakapan di luar waktu tunggu balasan

**Status:** Perubahan diterapkan; validasi latensi end-to-end belum lengkap.

- Pemeriksaan kode mengonfirmasi `manage_history()` sebelumnya memanggil model
  Ollama dan menulis ringkasan secara sinkron setelah jawaban dihasilkan,
  sehingga penyelesaian jawaban tertahan ketika ambang tercapai.
- Peringkasan kini dijadwalkan di worker background dengan snapshot history.
  Balasan saat ambang tercapai dapat dikembalikan tanpa menunggu model ringkasan.
- Sebelum prompt berikutnya memakai history, router menyelesaikan Future dan
  menerapkan ringkasan yang berhasil dipersist; history terbaru tetap
  dipertahankan. Perintah reset juga menunggu pekerjaan tertunda sebelum
  menghapus berkas ringkasan agar hasil background tidak muncul kembali setelah
  reset.
- Jika pembuatan atau persistensi ringkasan gagal, history tidak dipotong.

**Validasi:**

- 33 tes router/session memory lulus, termasuk tes Future yang belum selesai:
  handler setelah jawaban tidak menunggu, sedangkan persiapan prompt berikutnya
  menunggu hasil dan baru kemudian menerapkan ringkasan.
- Run regresi ulang 14 Oktober 2026: seluruh 35 tes dalam
  `test_router_and_session` lulus (0,158 detik, exit code 0), termasuk snapshot,
  ringkasan asinkron, penerapan sebelum prompt selanjutnya, kegagalan generasi
  atau persistensi, dan reset yang menunggu Future.
- Tes lama untuk kegagalan ringkasan, kegagalan persistensi, ringkasan berhasil,
  dan reset tetap lulus; tes tambahan memastikan reset menunggu worker tertunda
  sebelum membersihkan ringkasan persisten.
- Belum dilakukan benchmark end-to-end dengan Ollama hidup, jadi durasi dan
  penghematan aktual belum terukur.
- Run terbaru tetap memakai mock/Future dan tidak mengukur latensi Ollama live;
  detail serta batasnya dicatat di
  [validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md).

**Dampak dan mitigasi:**

- Dampak yang diharapkan: respons pada giliran yang mencapai ambang tidak
  menunggu panggilan ringkasan.
- Biaya ringkasan tidak dihilangkan; bila masih berjalan saat pengguna mengirim
  prompt berikutnya, prompt berikutnya menunggu agar konteks tidak terpotong
  atau tertukar.
- Snapshot menghindari pembacaan history yang berubah; penerapan dan reset
  menunggu Future. Jika summary/persist gagal, history penuh tetap tersimpan
  sebagai konteks.
- Setelah proses dihentikan paksa sebelum worker menyimpan ringkasan, ringkasan
  yang masih berjalan dapat hilang. History hidup di memori proses juga tidak
  dipersist oleh mekanisme ini.

### Tahap 4 — Kurangi jeda polling browser setelah job selesai

**Status:** Selesai dan diterapkan.

- Browser mulai mengecek status setelah 500 ms, lalu menaikkan interval secara
  bertahap hingga maksimum 900 ms ketika status job tidak berubah.
- Saat status berubah (misalnya `queued` ke `running`), interval kembali ke
  500 ms. Job selesai/gagal tetap menghentikan polling segera.
- Backoff untuk gangguan jaringan/server tetap ada dan terpisah dari polling
  normal.

**Validasi dan batas pengukuran:**

- Pemeriksaan kode memastikan interval normal berada pada rentang 500–900 ms
  (sebelumnya tetap 1.200 ms), sehingga batas jeda setelah job selesai turun
  25% pada status yang stabil.
- Validasi dinamis 14 Oktober 2026 pada `pollChatJob` memastikan jeda naik
  500 → 750 → 900 ms dan tidak melebihi plafon; perubahan status mereset ke
  500 ms, status terminal menghentikan polling, dan HTTP 503 memakai retry
  backoff terpisah 1.000 ms.
- Seluruh 15 tes `test_api_contract` lulus (0,263 detik, exit code 0),
  termasuk pembuatan job dan endpoint pemeriksaan status yang digunakan UI.
- Polling normal untuk job panjang dapat meningkat dari sekitar 0,83 menjadi
  maksimum 1,11 request per detik per tab (hingga sekitar 33% lebih banyak).
- Belum ada pengukuran browser nyata, jaringan nyata, atau beban multi-client;
  validasi tiruan memastikan logika polling dan kontrak API, bukan manfaat
  latensi atau beban produksi. Detail ada di
  [validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md).

**Dampak dan mitigasi:**

- Respons yang selesai di antara dua pemeriksaan dapat tampil lebih cepat;
  latensi tunggu maksimum turun dari 1.200 ke 900 ms saat job berstatus sama.
- Risiko bertambahnya request dibatasi dengan interval adaptif dan plafon
  900 ms, mempertahankan backoff saat error, serta menghentikan polling pada
  status terminal. Pantau log jumlah request dan kembalikan interval awal jika
  beban server/perangkat meningkat tanpa manfaat nyata.

### Tahap 5 — Uji durasi model tetap aktif (keep-alive)

**Status:** Uji baseline cold/warm terbatas dilakukan tanpa menerapkan perubahan;
keep-alive tetap `30s`. Stabilitas produksi dan keep-alive lebih lama belum
tervalidasi.

**Hipotesis:** model Reasoner yang hanya ditahan selama 30 detik mungkin
memerlukan pemuatan ulang untuk permintaan kompleks berikutnya.

**Rencana perubahan:** ukur cold start dan warm call setiap model yang
digunakan. Jika pemuatan ulang terbukti dominan, uji durasi keep-alive lebih
lama secara terukur.

**Validasi sesudah perubahan:**

- Ukur cold/warm latency sebelum dan sesudah.
- Pantau RAM/VRAM, waktu muat model lain, dan stabilitas sesi panjang.
- Pastikan jawaban Reasoner tetap diuji pada benchmark penalaran.

**Keputusan:** pertahankan hanya jika peningkatan warm response sepadan dengan
penggunaan memori dan tidak mengganggu model lain.

**Dampak yang mungkin dan cara menguranginya:**

- Dampak positif yang diharapkan: panggilan berikutnya menghindari sebagian
  waktu muat model jika model tetap berada di memori.
- Risiko: penggunaan RAM/VRAM meningkat dan dapat membuat model lain lambat,
  dievikt, atau gagal dimuat. Mitigasi: ukur konsumsi memori dan latensi model
  lain, naikkan keep-alive secara bertahap, lalu kembalikan ke nilai awal jika
  tekanan memori atau waktu respons total memburuk.

**Pemeriksaan saat ini:**

- Snapshot terbaru sebelum uji (14 Oktober 2026): RTX 4060 8.188 MiB dengan
  5.584 MiB VRAM bebas, RAM 31,93 GiB dengan 5,69 GiB bebas, dan tidak ada
  model aktif di Ollama.
- Dengan persetujuan pengguna, dua request direct ke `deepseek-r1:8b`
  dijalankan pada `keep_alive: 30s`, `num_ctx: 2048`. Request cold memerlukan
  17.405 ms waktu client; request warm 1.422 ms. Batas 48 token menghasilkan
  content kosong pada keduanya, sehingga ditambahkan satu request warm dengan
  batas 512 token (12.492 ms client, 363 token) untuk memastikan ada jawaban.
- Jawaban tambahan menyebut Tokyo tetapi juga memuat detail sejarah yang tidak
  akurat/tidak diperlukan. Saat model aktif VRAM bebas turun hingga 537 MiB.
  Tidak terjadi OOM pada uji singkat.
- Setelah 35 detik, model tidak lagi tampil pada `/api/ps` dan VRAM bebas
  pulih ke 5.562 MiB. RAM bebas tercatat 4,36 GiB pada snapshot akhir dan
  belum pulih ke baseline; penyebabnya tidak dapat dipastikan.
- Tidak ada perubahan pada `config.py` atau kode aplikasi. `KEEP_ALIVE_DEFAULT`
  tetap `2m`, `KEEP_ALIVE_SPECIALIST` tetap `30s`. Tahap 5 masih belum
  tervalidasi untuk keep-alive lebih lama, context produksi, kualitas jawaban,
  atau sesi panjang. Rincian dan baseline pemulihan ada di
  [validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md)
  dan [backup-tahap-5-keep-alive-2026-10-14.md](./backup-tahap-5-keep-alive-2026-10-14.md).

### Tahap 6 — Antrean dan beban beberapa permintaan

**Status:** Instrumentasi antrean diterapkan; jumlah worker tetap satu.

- API kini mengukur `queue_wait_ms` dan `execution_ms` memakai jam monotonic.
  GET status job melaporkan waktu antre saat queued dan waktu antre/eksekusi
  ketika job berjalan atau selesai/gagal.
- Uji dengan dua job simulasi memastikan job kedua tetap queued saat job pertama
  ditahan, lalu keduanya selesai berurutan dan job kedua melaporkan waktu antre.
- Ini memberi observabilitas antrean, tetapi belum membuktikan perubahan
  throughput dengan model Ollama nyata; concurrency belum dinaikkan.

**Alasan mempertahankan satu worker:**

- Semua job memakai `_router`/`AITeam` bersama dan `chat_history` mutable.
  Paralelisasi dapat membuat giliran percakapan berinterleaving atau mengambil
  konteks yang berubah.
- Ollama memakai perangkat bersama. Uji perangkat terakhir mencatat VRAM bebas
  5.334 MiB dari 8.188 MiB dan RAM bebas sekitar 6,8 GB; belum ada uji model
  paralel yang membuktikan bahwa penambahan worker memperbaiki throughput tanpa
  menimbulkan kontensi.

**Validasi dan batas pengukuran:**

- 3 tes terarah siklus job lulus; seluruh kontrak API diuji setelah perubahan.
- Run regresi ulang 14 Oktober 2026: 15 tes `test_api_contract` lulus
  (0,255 detik, exit code 0). Tes serial mengonfirmasi job kedua menunggu
  worker tunggal, job selesai berurutan, dan status melaporkan
  `queue_wait_ms` serta `execution_ms`.
- Uji simulasi menahan job pertama sekurangnya 50 ms dan memverifikasi waktu
  antre job kedua sekurangnya 10 ms. Ini tes correctness metrik, bukan benchmark
  performa inferensi atau p50/p95 beban nyata.
- Metrik tersedia per job di endpoint status agar pengukuran terkontrol
  berikutnya dapat memisahkan antre dari waktu model.
- Run terbaru memakai router tiruan dan tidak mengukur throughput Ollama
  nyata; rinciannya ada di
  [validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md).

**Dampak dan mitigasi:**

- Dampak positif: penyebab lambat dapat dibedakan—antrean versus eksekusi—
  sebelum memilih optimasi yang benar.
- Dampak saat ini: tidak ada peningkatan paralelisme atau kecepatan inferensi;
  worker satu mempertahankan urutan dan mencegah job sesi yang sama overlap.
- Jika kelak diuji dengan banyak worker, terlebih dahulu serialisasi akses
  per sesi, gunakan batas konkurensi, ukur GPU/VRAM dan p50/p95, serta batalkan
  bila akurasi konteks atau throughput memburuk. Antrean penuh tetap
  mengembalikan HTTP 503, tidak menerima job diam-diam.

### Tahap 7 — Retrieval adaptif tanpa mematikan ekspansi yang berguna

**Status:** Fast path diterapkan; validasi recall benchmark nyata masih perlu.

- Jika hasil keyword menemukan catatan yang judulnya secara eksplisit disebut
  dalam query (setidaknya dua istilah judul bermakna), query-expander LLM
  dilewati.
- Ekspansi bersyarat yang sudah ada tetap aktif untuk pertanyaan tanpa judul
  eksplisit ketika hasil awal lemah (kurang dari 3 hasil vektor dan kurang dari
  2 hasil keyword).
- Kegagalan pencarian pada query alternatif dicatat, tetapi tidak lagi
  mengubah status sukses pencarian vektor utama menjadi peringatan
  “semantic retrieval unavailable”.

**Validasi:**

- Run validasi ulang 14 Oktober 2026: seluruh 14 tes `test_memory_quality`
  lulus (0,027 detik, exit code 0).
- Tes membuktikan query judul catatan seperti “Pengetahuan tentang Ikan”
  menghindari ekspansi; query lemah tanpa hasil awal tetap menjalankan ekspansi
  dan dapat menambahkan dokumen alternatif.
- Tes juga memastikan kegagalan query alternatif tidak menyamarkan hasil
  pencarian awal yang berhasil sebagai kegagalan retrieval.
- Belum ada pengukuran p50/p95 atau recall pada Vault nyata; benchmark uji ini
  memverifikasi alur dengan hasil retrieval terkontrol, bukan relevansi
  semantik produksi.
- Detail run dan batas validasi tercatat di
  [validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md).

**Dampak dan mitigasi:**

- Dampak positif: pencarian catatan yang diminta dengan nama eksplisit dapat
  menghindari panggilan query-expander LLM, mengurangi latensi dan beban model.
- Risiko: variasi nama/parafrasa mungkin tidak memenuhi deteksi judul sehingga
  tetap memakai ekspansi; ini mempertahankan recall dengan biaya latensi.
- Fast path dibatasi pada judul dengan minimal dua istilah bermakna yang
  semuanya hadir di query dan dokumen terambil lewat keyword. Semua query lain
  tetap memakai aturan fallback yang ada; ukur recall/ranking pada set acuan
  sebelum memperluas kriteria.

## Protokol Pengukuran Per Tahap

Hasil run regresi gabungan terbaru dicatat di
[validasi-test-regresi-2026-10-14.md](./validasi-test-regresi-2026-10-14.md).

Analisis peluang optimasi lanjutan tanpa menurunkan kualitas, termasuk
protokol benchmark end-to-end dan pengaman mutu, dicatat di
[analisis-peluang-optimasi-carl-tanpa-penurunan-kualitas-2026-10-14.md](./analisis-peluang-optimasi-carl-tanpa-penurunan-kualitas-2026-10-14.md).

Untuk setiap perubahan, gunakan protokol yang sama:

1. Catat versi kode, model, opsi, status model cold/warm, jumlah catatan, dan
   konfigurasi perangkat yang relevan.
2. Kirim set pertanyaan uji yang sama secara berurutan dan ukur masing-masing
   durasi; gunakan sekurangnya lima pengulangan untuk membedakan variasi biasa
   dari perubahan nyata.
3. Ukur waktu dari dua sudut pandang:
   - **Waktu end-to-end pengguna:** kirim sampai balasan tampil.
   - **Waktu internal tahap:** antre, retrieval, model, post-processing, dan
     polling jika tersedia.
4. Laporkan median dan p95, bukan hanya satu run tercepat.
5. Catat isi/status jawaban secara terpisah dari kecepatannya.
6. Jalankan tes regresi dan benchmark kualitas yang relevan sebelum menyatakan
   tahap lulus.
7. Laporkan angka mentah, jumlah sampel, perbedaan konfigurasi, dan batas
   eksperimen. Jangan menyimpulkan bahwa kemampuan tidak berubah hanya dari
   tes kecepatan.

## Hasil Akhir yang Diharapkan

Setiap tahap mempunyai catatan:

```text
Nama perubahan:
Commit/versi kode:
Model dan kondisi cold/warm:
Kumpulan permintaan:
Baseline p50/p95:
Hasil sesudah perubahan p50/p95:
Tes kualitas/regresi:
Perubahan mutu jawaban:
Efek samping:
Keputusan: pertahankan / revisi / batalkan
```

Rencana ini mengoptimalkan waktu tunggu yang terbukti tidak diperlukan.
Mengganti model dengan model lebih kecil, memangkas konteks, mematikan retrieval
atau mengurangi pemeriksaan kualitas bukan bagian dari rencana tanpa persetujuan
dan pengukuran khusus.
