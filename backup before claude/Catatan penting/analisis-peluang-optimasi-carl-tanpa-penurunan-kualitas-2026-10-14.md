# Analisis Peluang Optimasi Carl Tanpa Menurunkan Kualitas

**Tanggal:** 14 Oktober 2026  
**Status:** Analisis kandidat dan catatan hasil penerapan terpilih. Penerapan
dibatasi pada instrumentasi, streaming respons, dan lembar evaluasi manusia;
cache lexical serta perubahan Graph RAG tetap ditunda.

## Ringkasan

Masih ada peluang optimasi Carl, terutama dengan mengurangi pekerjaan
berulang pada retrieval dan mengukur dengan lebih rinci bagian mana yang
benar-benar memakan waktu. Belum ada bukti cukup untuk menyimpulkan bahwa satu
komponen tertentu adalah bottleneck end-to-end.

Optimasi tidak boleh dinyatakan aman hanya karena tes regresi lulus atau
latensi turun. Setiap perubahan perlu dibandingkan dengan baseline yang setara
dan diuji terpisah untuk ketepatan, grounding ke Vault, kelengkapan, dan mutu
penalaran. Jika kualitas ambigu atau menurun, perubahan tidak diterima.

## Kondisi dan bukti saat ini

- Tes regresi Tahap 1, 2, 3, 4, 6, dan 7 yang dijalankan lulus. Tes ini
  mengonfirmasi perilaku yang dicakup, tetapi bukan bukti performa atau kualitas
  end-to-end dalam penggunaan produksi.
- Cache peta Vault pernah diukur pada Vault sintetis 500 catatan. Hasil
  tersebut bukan pengukuran seluruh jalur jawaban Carl atau Vault produksi.
- API melaporkan `queue_wait_ms` dan `execution_ms`; `execution_ms` masih
  mencakup routing, retrieval, prompt, inference, serta pekerjaan lain di
  handler. Belum cukup untuk menentukan sub-tahap yang paling lambat.
- Pencarian keyword mengekstrak dan menghitung token konten chunk setiap kali
  pencarian dilakukan. Ini kandidat untuk dikurangi kerja berulang, tetapi
  belum terbukti dominan tanpa profiling.
- Writer menyertakan peta Vault, konteks hasil retrieval, dan bagian riwayat
  percakapan dalam prompt. Biaya token/prefill dari bagian-bagian tersebut
  belum diukur terpisah.
- Graph retrieval mengikuti wikilink dan membaca catatan terkait. Biaya
  pencarian berkas dan pembacaan konten belum diprofilkan sebagai tahap
  tersendiri.
- Reasoner mempunyai jalur model dan instruksi khusus. Memotong prompt,
  retrieval, history, atau anggaran token tanpa evaluasi berisiko mengubah
  mutu penalaran.
- Pada uji Tahap 5 yang terbatas, `deepseek-r1:8b` cold memerlukan 17.405 ms
  waktu client dan warm 1.422 ms ketika output dibatasi 48 token, tetapi
  keduanya tidak menghasilkan teks pada `message.content`. Uji tambahan
  menghasilkan jawaban, namun menyertakan detail sejarah tidak akurat/tidak
  diperlukan. Karena itu hasil tersebut bukan benchmark kualitas lulus.
- Pada uji Tahap 5, VRAM bebas turun sampai 537 MiB saat Reasoner aktif.
  Pengukuran ini tidak membuktikan stabilitas keep-alive lebih panjang,
  context produksi, atau sesi panjang.
- Konfigurasi model/keep-alive tetap sebagaimana baseline. Lihat
  [config.py](../config.py) dan
  [catatan pemulihan Tahap 5](./backup-tahap-5-keep-alive-2026-10-14.md).

## Kandidat optimasi

| Prioritas | Kandidat yang belum diterapkan | Alasan untuk menyelidiki | Pengaman kualitas |
|---|---|---|---|
| 1 | Cache tokenisasi atau indeks lexical per chunk | [Pencarian keyword](../memory/hybrid_search.py) menghitung token konten chunk saat pencarian. Cache mungkin mengurangi pekerjaan berulang pada Vault besar. | Ranking dan hasil harus identik terhadap algoritma baseline pada query acuan; verifikasi invalidasi untuk perubahan isi, tambah, rename, dan hapus catatan. |
| 2 | Ukur/optimalkan biaya prompt Writer | Peta Vault, hasil retrieval, dan history disusun sebelum panggilan model. Prompt panjang dapat menambah prefill, namun dampak aktual belum diukur. | Jangan membuang peta atau memangkas history secara umum. Jika diuji, pastikan cakupan sumber, konteks percakapan, dan kualitas jawaban tidak berkurang. |
| 3 | Profiling dan optimasi Graph RAG | Penelusuran wikilink melakukan pencarian file dan membaca catatan terkait. Overhead atau I/O berulang mungkin bisa dioptimalkan. | Perubahan cache harus diinvalidasi ketika isi/link berubah; bandingkan sumber graph yang ditemukan dan jawaban sebelum/sesudah. |

Kandidat yang belum diterapkan di atas tetap hipotesis. Implementasi hanya
dilakukan setelah pengukuran dan evaluasi menunjukkan manfaat serta tidak
menurunkan kualitas.

## Peningkatan kompatibel yang telah diterapkan

- **Instrumentasi:** mencatat durasi tahap API/job, routing, retrieval vektor,
  keyword, ekspansi query, graph, format hasil, persiapan prompt, dan inference
  pada jalur yang telah diinstrumentasi. Log tidak mencatat prompt atau jawaban;
  panjang prompt dinyatakan dalam karakter, bukan token.
- **Streaming respons:** potongan Writer/Coder dikirim melalui polling job yang
  sudah ada. Jalur Reasoner/Web/Synthesizer tidak mengirim potongan model mentah,
  dan model, parameter inferensi, serta jumlah worker tidak berubah.
- **Evaluasi manusia:** `evaluate_answers.py --review-output <file.json>`
  membuat keluaran review opsional berisi jawaban model serta kolom
  keputusan/catatan kosong. File tersebut dapat mengandung konten Vault dan
  karena itu hanya dibuat atas permintaan eksplisit.

## Perubahan yang belum disarankan

Sebelum tersedia evaluasi kualitas dan pengukuran yang memadai, jangan:

- mengganti model dengan model lebih kecil atau menurunkan quantization;
- memangkas `num_ctx`, riwayat, prompt Reasoner, atau hasil retrieval;
- mengurangi batas output global; uji Tahap 5 menunjukkan batas 48 token dapat
  habis sebelum teks jawaban muncul;
- mematikan query expansion, grounding, pemeriksaan sitasi, atau jalur
  fallback untuk mengejar latensi;
- menaikkan jumlah worker; API berbagi router dan state sesi yang mutable,
  sementara inferensi memakai GPU yang sama;
- memperpanjang keep-alive atau mempertahankan beberapa model di GPU sebelum
  uji beban aman menunjukkan headroom yang cukup.

## Protokol validasi end-to-end

### 1. Pastikan baseline bersih

- Restart Carl secara normal sebelum benchmark.
- Pastikan hanya satu proses Carl memakai direktori embedded Qdrant yang sama.
  Jangan menghapus lock atau database untuk mengatasi konflik.
- Periksa endpoint `/api/status`: router tersedia, memory menunjukkan kondisi
  yang diharapkan, dan jumlah catatan Vault tercatat.
- Periksa Ollama `/api/ps`, model aktif, model yang terpasang, RAM bebas,
  VRAM bebas, temperatur, dan proses GPU.
- Catat tanggal, versi kode, model/quantization, konfigurasi, jumlah catatan,
  dan kondisi cold/warm.

### 2. Tetapkan kumpulan permintaan tetap

Gunakan prompt yang sama sebelum dan sesudah perubahan. Sertakan sekurangnya:

1. Pertanyaan faktual sederhana yang tidak memerlukan Vault.
2. Pertanyaan yang jawabannya memang ada pada catatan Vault tertentu.
3. Pertanyaan Vault yang perlu menghubungkan dua atau lebih catatan.
4. Permintaan analisis kompleks yang harus diarahkan ke Reasoner.
5. Rangkuman sumber bernama dan satu permintaan tool yang relevan.

Gunakan prompt dan kriteria penilaian yang sama untuk baseline dan kandidat.
Hindari data pribadi atau catatan sensitif dalam log benchmark.

### 3. Jalankan pengulangan yang sebanding

- Ukur cold terpisah dari warm.
- Gunakan batas output yang cukup untuk jawaban lengkap; jangan membandingkan
  jawaban kosong/terpotong dengan jawaban penuh.
- Jalankan sekurangnya lima pengulangan untuk tiap kondisi. Catat semua sampel,
  bukan hanya hasil tercepat.
- Jangan menjalankan permintaan secara paralel pada baseline satu worker.
- Untuk eksperimen keep-alive, uji satu perubahan sementara pada satu waktu,
  pantau resource, dan pulihkan ke baseline segera bila tekanan memori atau
  gangguan muncul.

### 4. Rekam latensi dan mutu secara terpisah

Catat:

- waktu total pengguna dari pengiriman sampai jawaban tampil;
- waktu antre, routing, retrieval, graph, persiapan prompt, inference, dan
  polling bila instrumentation tersedia;
- token prompt dan output, status retrieval, cold/warm, serta penggunaan
  RAM/VRAM;
- median dan p95 untuk waktu total dan tahap internal;
- jawaban lengkap, sitasi/sumber yang dipakai, fakta yang didukung, fakta yang
  salah, bagian permintaan yang terlewat, dan mutu reasoning.

Jangan menyimpulkan kualitas tetap hanya dari tes kecepatan. Bandingkan hasil
jawaban dengan rubrik atau acuan yang ditetapkan sebelum benchmark.

### 5. Kriteria menerima atau menolak optimasi

Terima perubahan hanya jika:

- perbandingan baseline dan kandidat memakai kondisi serta input yang setara;
- manfaat latensi terlihat konsisten, bukan hanya satu run tercepat;
- tidak ada penurunan yang teramati pada ketepatan, grounding, kelengkapan,
  atau reasoning;
- RAM/VRAM, kestabilan layanan, dan perilaku model lain tetap dapat diterima;
- tes regresi dan pengujian kualitas yang relevan lulus.

Jika hasil kualitas ambigu, resource terlalu dekat batas, atau performa tidak
konsisten, jangan terapkan perubahan secara permanen. Kembalikan konfigurasi
dan kode terkait ke baseline eksperimen.

## Urutan tindakan yang disarankan

1. Jalankan baseline end-to-end pada server lokal dengan Qdrant sehat dan
   simpan metrik mentah serta jawaban.
2. Tambahkan instrumentation per tahap tanpa mengubah perilaku model.
3. Ulangi baseline untuk mengonfirmasi bahwa instrumentation tidak mengubah
   hasil secara berarti.
4. Profilkan query keyword dan prompt token terlebih dahulu.
5. Pilih hanya satu bottleneck yang terbukti, buat perubahan kecil, lalu
   jalankan ulang kumpulan uji yang sama.
6. Bandingkan p50/p95, jawaban, grounding, reasoning, dan penggunaan resource.
7. Pertahankan hanya perubahan yang memberi manfaat tanpa penurunan kualitas;
   dokumentasikan rollback dan batas eksperimennya.

## Formulir pencatatan eksperimen

```text
Nama eksperimen:
Tanggal dan versi kode:
Perubahan sementara:
Model dan quantization:
Kondisi cold/warm:
Jumlah catatan Vault:
Kondisi GPU/RAM:
Prompt uji dan jumlah pengulangan:
Latensi mentah:
Median/p95 end-to-end:
Median/p95 tiap tahap:
Token prompt/output:
Mutu jawaban, grounding, dan reasoning:
Error atau efek samping:
Keputusan: pertahankan / revisi / rollback
```

## Kesimpulan

Optimasi paling aman berikutnya bukan mengurangi kemampuan model, melainkan
mengukur bottleneck end-to-end dan menghindari pekerjaan berulang yang
terbukti dominan. Cache token/index keyword, efisiensi prompt, dan Graph RAG
layak diselidiki setelah profiling; belum ada bukti untuk menyatakan ketiganya
akan mempercepat Carl dalam kondisi produksi.

Pertahankan model, konteks, grounding, fallback, dan keep-alive pada konfigurasi
saat ini sampai eksperimen terkontrol menunjukkan peningkatan yang konsisten
tanpa penurunan mutu jawaban.

---

## Analisis kualitas kognitif Carl berdasarkan kode saat ini

Bagian ini melengkapi analisis performa di atas. Fokusnya adalah ketepatan
memahami maksud, pemilihan jalur berpikir, penggunaan bukti, kelengkapan, dan
kualitas respons—bukan klaim bahwa model sudah diuji langsung. Jejak utama yang
ditelaah adalah [router](../agents/router.py), [orkestrator AITeam](../agents/__init__.py),
[Writer Carl](../agents/bot_writer.py), [Reasoner](../agents/bot_reasoner.py),
[retrieval memori](../memory/manager.py), [kebijakan grounding](../agents/grounding.py),
dan [evaluator jawaban](../memory/answer_evaluator.py).

### Peta alur kognitif yang terimplementasi

| Tahap | Perilaku yang terlihat pada kode | Dampak terhadap kualitas |
|---|---|---|
| Memahami maksud | Slash command menang lebih dahulu; frasa tertentu memakai fast route; pertanyaan umum diarahkan ke Writer; input ambigu memakai LLM intent classifier. | Cepat pada pola yang dikenal, tetapi aturan frasa dan keluaran classifier tetap dapat salah mengklasifikasikan maksud. |
| Menentukan kedalaman | Writer memanggil `should_use_deep_reasoning`; sejumlah kata/struktur bahasa Indonesia mengalihkan permintaan ke Reasoner. | Ada jalur eksplisit untuk analisis, hitungan, perbandingan, dan rencana, tetapi deteksinya berbasis kata/regex, bukan pemahaman kompleksitas yang diukur. |
| Mengambil bukti | Memori menggabungkan vector search, pencocokan keyword, ekspansi query kondisional, dan wikilink; kegagalan semantik diberi penanda. | Ada redundansi retrieval dan fallback yang baik, namun bukti yang ditemukan belum tentu lengkap atau paling relevan untuk seluruh sub-pertanyaan. |
| Membentuk konteks | Writer menerima peta Vault, hasil retrieval, riwayat percakapan terbaru, serta konteks sesi yang mencakup profil/aturan/ringkasan; Reasoner menerima konteks sesi dan hasil retrieval. | Personalisasi dan konteks tersedia, tetapi sumber-sumber berbeda dapat bersaing untuk perhatian model dan panjang prompt belum dikontrol secara terukur. |
| Menghasilkan jawaban | Writer memakai Qwen; Reasoner memakai DeepSeek-R1; prompt keduanya melarang monolog internal dan meminta ketidakpastian bila bukti kurang. | Pemisahan peran mendukung tugas berbeda; keberhasilan kualitas tetap bergantung pada routing, konteks, dan instruksi model. |
| Memeriksa hasil | Pemeriksaan sitasi mencari nama file sumber yang cocok/tidak cocok; benchmark checklist mengukur fakta, sitasi, dan abstention secara literal. | Guardrail memberi sinyal berguna, tetapi belum membuktikan bahwa setiap klaim benar-benar didukung sumber atau bahwa penalarannya valid. |

### Hal yang sudah dirancang dengan baik

1. **Pemisahan fakta Vault, riwayat sesi, dan inferensi.** Prompt Writer dan
   Reasoner menjelaskan bahwa ringkasan sesi bukan bukti faktual, memerintahkan
   model untuk menyatakan asumsi/keterbatasan, dan melarang mengarang detail
   catatan. Kebijakan tersebut juga membingkai isi Vault sebagai data, bukan
   instruksi yang harus diikuti.
2. **Penalaran mendalam tidak dipaksakan ke setiap pertanyaan.** Ada jalur
   Reasoner yang berbeda, sedangkan pertanyaan informasi sederhana bisa
   langsung menuju Writer. Prompt Reasoner meminta alasan utama yang dapat
   diperiksa, bukan monolog rantai pemikiran.
3. **Fallback retrieval terlihat oleh pengguna.** Ketika pencarian vektor gagal,
   hasil memberi tanda bahwa pencarian semantik tidak tersedia; Writer juga
   membedakannya dari kondisi tidak ada catatan. Ini mengurangi risiko
   menyampaikan hasil parsial seolah-olah pencarian Vault lengkap.
4. **Tersedia uji kualitas jawaban terpisah dari uji retrieval.**
   [Benchmark jawaban](../evaluation/answer_benchmark.json) berisi kasus
   answerable dan unanswerable dengan fakta serta sumber acuan. Evaluator
   mengungkapkan bahwa pemeriksaannya literal, dan evaluasi `/eval` di
   [memory/evaluator.py](../memory/evaluator.py) juga mengungkap bahwa skor
   sintetisnya hanya menilai retrieval, bukan kebenaran jawaban.
5. **Sebagian keluaran operasional sudah diuji dengan mock/regresi.**
   Tes routing, citation notice, retrieval, dan kontrak API memberi perlindungan
   terhadap kelas regresi yang memang tercakup di tes tersebut. Itu tidak sama
   dengan validasi kualitas model end-to-end.

### Peluang peningkatan yang paling relevan untuk nalar dan akurasi

| Prioritas | Temuan berbasis kode | Risiko kualitas | Tindakan yang disarankan |
|---|---|---|---|
| P0 | `add_citation_verification_notice` memeriksa keberadaan nama file dalam konteks, bukan keterdukungan tiap klaim. | Model dapat memberi sitasi yang memang ada tetapi menempelkan klaim yang tidak didukungnya; sitasi valid secara nama bukan bukti valid secara semantik. | Pertahankan pemeriksaan deterministik sebagai pemeriksaan format, tetapi jangan menyebutnya verifikasi kebenaran. Tambahkan evaluasi grounding per klaim dengan pertanyaan acuan dan tinjauan manusia; bila kelak memakai model judge, kalibrasikan terhadap label manusia dan jangan jadikan satu-satunya gerbang. |
| P0 | Benchmark jawaban saat ini berisi 17 kasus dan metrik fakta/sitasi berbasis kecocokan frasa literal. | Sampel masih sempit untuk mewakili variasi bahasa, tugas, konflik sumber, atau tingkat kesulitan. Frasa wajib yang muncul secara kebetulan dapat dihitung lolos, sementara parafrasa yang benar bisa gagal. | Kembangkan suite versi-terkontrol yang ditinjau manusia: fakta Vault, multi-hop, beberapa bagian permintaan, konflik/versi catatan, informasi tidak tersedia, analisis berbasis bukti, logika/hitungan, instruksi format, serta prompt injection dari dokumen. Laporkan skor per kategori dan contoh kesalahan; jangan mengandalkan satu angka agregat. |
| P1 | Eskalasi ke Reasoner dipicu daftar kata/regex di `should_use_deep_reasoning`; tes yang ditelaah mencakup beberapa contoh eksplisit dan sederhana. | Permintaan kompleks yang diutarakan secara tidak langsung/gaul dapat tertinggal di Writer; kata pemicu pada konteks yang tidak membutuhkan analisis dapat mengeskalasi berlebihan. | Bangun kumpulan uji routing berlabel (intent dan tingkat kedalaman), termasuk parafrasa, negasi, multi-intent, bahasa campuran, dan kalimat panjang. Ukur false-negative dan false-positive. Perbaiki cue/aturan berdasarkan kasus gagal; jangan mengganti routing deterministik dengan panggilan LLM tambahan tanpa bukti manfaat dan dampak latensi. |
| P1 | Hybrid lexical search mencocokkan token secara eksak; query expansion dilakukan secara kondisional dan hasil ekspansinya menambah pencarian vektor. | Bentuk kata berimbuhan, sinonim domain, alias, atau istilah lintas bahasa dapat tidak cocok secara leksikal; perluasan query mungkin membantu recall tetapi menambah variasi yang tidak relevan. | Uji retrieval dengan query dan dokumen relevan yang ditandai manusia. Ukur hit/recall@k, MRR/nDCG, precision@k, dan kasus salah ambil; bandingkan baseline terhadap stemming Bahasa Indonesia/BM25 atau ekspansi yang dibatasi—satu perubahan per eksperimen. |
| P1 | Graph RAG menambahkan catatan terkait dari tautan wikilink dengan cuplikan awal maksimum 600 karakter dan tidak melakukan pemeringkatan relevansi bagian pada catatan tujuan. | Bukti penting yang berada di tengah/akhir catatan bisa tidak masuk konteks, sementara catatan tertaut yang kurang relevan ikut memengaruhi jawaban. | Uji kasus multi-hop dengan fakta target sengaja diletakkan di bagian berbeda. Pertimbangkan mengambil chunk relevan dari catatan tujuan, bukan selalu awalan berkas; ukur source recall dan precision serta pastikan file/path ambigu tidak menghasilkan sumber salah. |
| P1 | Konteks Writer menggabungkan peta Vault, hasil pencarian, riwayat, dan konteks personal/sesi; seluruh aturan yang tersimpan ikut dibentuk menjadi prompt. Tidak terlihat pengukuran token atau batas relevansi khusus untuk komponen-komponen itu. | Konteks yang panjang atau instruksi lama yang tidak relevan berpotensi menggeser bukti penting, menaikkan latensi, dan membuat jawaban terlalu terpersonalisasi. | Catat token per bagian prompt dan keterkaitan bagian konteks dengan jawaban benar. Buat kebijakan anggaran/urutan prioritas berbasis tugas setelah baseline ada; ringkas/pilih aturan hanya dengan cara yang tidak menghilangkan preferensi penting. Uji konflik antaraturan dan instruksi yang sudah kedaluwarsa. |
| P2 | Writer memfilter riwayat berdasarkan apakah `content` diawali `{`, sedangkan konteks sesi berasal dari ringkasan percakapan. | Filter format ini bukan pemeriksaan relevansi atau kebenaran; keluaran/tool data yang kebetulan berbentuk lain masih dapat masuk. Ringkasan juga dapat kehilangan batas atribusi walaupun prompt menganjurkan pemisahan. | Tambahkan uji kontrak riwayat dan atribusi: fakta dari pengguna, klaim Carl, keputusan, preferensi, dan hal yang belum pasti harus tetap dibedakan setelah peringkasan. Pertimbangkan representasi bertipe, bukan penyaringan dengan bentuk string, jika kasus nyata menunjukkan kebocoran konteks. |
| P2 | Konfigurasi sampling Writer/Reasoner ditetapkan secara terpusat, tetapi opsi selain temperature dan profil token/context khusus tidak dibuktikan sebagai optimal untuk setiap kelas tugas. | Mengubah temperature, ukuran konteks, atau model secara global dapat menaikkan variasi atau menurunkan kemampuan pada tugas lain. | Jangan mengubah nilai konfigurasi hanya berdasarkan intuisi. Bandingkan opsi per kelas tugas dengan prompt/data yang sama, pengulangan yang cukup, kualitas jawaban blind review, serta p50/p95 dan resource. Simpan konfigurasi terbaik per eksperimen dan siapkan rollback. |

Prioritas P0 berarti perlu diperjelas/diukur sebelum klaim kualitas Carl
ditingkatkan; bukan berarti sistem saat ini selalu menghasilkan jawaban salah.
Prioritas P1/P2 menunjukkan area eksperimen bertahap yang manfaatnya harus
dibuktikan.

### Keterbatasan evaluasi yang harus dinyatakan secara eksplisit

- Dataset jawaban saat ini memiliki 17 kasus yang mencakup kasus dapat dijawab
  dan abstention. Ini awal yang berguna, tetapi belum cukup untuk menyimpulkan
  kualitas umum atau perbandingan model dengan keyakinan tinggi.
- Pemeriksaan `required_facts` dan sumber di evaluator adalah pencocokan teks
  yang dinormalisasi, bukan penilaian ekuivalensi makna atau keterdukungan
  klaim. Interval kepercayaan tidak mengatasi bias pemilihan kasus atau
  keterbatasan metrik.
- Evaluasi `/eval` membentuk query dari judul/heading catatan dan mengambil
  sampel terbaru; ia berguna sebagai smoke test retrieval, bukan tes reasoning,
  factuality, atau variasi query pengguna.
- Tes routing dan anti-halusinasi yang ditelaah menguji perilaku yang dipilih,
  sering dengan mock; tes tersebut tidak mengukur mutu jawaban model nyata,
  p50/p95 produksi, maupun konsistensi antar-run.
- Belum dilakukan benchmark live terhadap Ollama/model terpasang atau Vault
  produksi dalam analisis ini. Karena itu tidak ada klaim skor akurasi,
  penurunan/kenaikan kualitas aktual, atau bottleneck performa yang telah
  dibuktikan oleh sesi ini.

### Rencana peningkatan bertahap yang disarankan

1. **Bekukan baseline kualitas.** Simpan versi kode, nama/kuantisasi model,
   konfigurasi, prompt, dataset, dan jawaban mentah; jalankan kasus yang sama
   beberapa kali untuk mengidentifikasi variasi.
2. **Perluas dataset sebelum mengubah prompt/model.** Tambah kasus berdasarkan
   kesalahan yang nyata dan label manusia. Sertakan jawaban ideal/rubrik,
   sumber yang diharapkan, fakta wajib, dan kondisi untuk menolak atau
   menyatakan ketidakpastian.
3. **Pisahkan skor per kapabilitas.** Minimal: akurasi fakta, kelengkapan
   multi-bagian, relevansi retrieval, validitas sitasi/grounding, abstention
   yang tepat, kualitas reasoning, kepatuhan instruksi/format, relevansi
   rekomendasi, serta latensi.
4. **Kumpulkan bukti per tahap tanpa menyimpan data sensitif.** Tambahkan
   pengukuran durasi/token untuk routing, tiap retrieval, pembentukan prompt,
   inference, dan respons; gunakan identitas kasus anonim serta hindari
   menyimpan isi Vault/percakapan mentah pada log performa secara default.
5. **Ubah satu faktor pada satu waktu.** Mulai dari relevansi prompt proaktif
   dan uji routing; berikutnya evaluasi chunk retrieval/graph dan anggaran
   konteks. Jangan sekaligus mengganti model, temperature, prompt, dan retrieval.
6. **Lakukan review jawaban blind.** Untuk kasus yang membutuhkan penalaran,
   penilai sebaiknya tidak mengetahui apakah jawaban berasal dari baseline atau
   kandidat. Catat kesalahan faktual, asumsi tersembunyi, bagian terlewat,
   kontradiksi, dan saran yang tidak diminta.
7. **Terapkan gerbang penerimaan.** Pertahankan kandidat hanya jika peningkatan
   kualitas pada kategori sasaran konsisten, kategori kritis lain tidak
   memburuk secara material, retrieval/sitasi dapat ditelusuri, dan stabilitas
   latensi/resource masih layak. Ambang numerik harus dipilih setelah ukuran
   dataset dan baseline tersedia, bukan ditetapkan dari satu run.

### Kesimpulan kualitas Carl

Fondasi penting untuk Carl sudah ada: router bertingkat, jalur Reasoner
terpisah, hybrid retrieval, pengakuan degradasi retrieval, kebijakan anti-halu,
serta evaluator jawaban awal. Peningkatan paling bernilai berikutnya bukan
memaksa model “berpikir lebih panjang”, melainkan memastikan jalur yang tepat
dipilih, bukti relevan benar-benar hadir, jawaban tidak menambahkan kewajiban
proaktif yang tidak perlu, dan kualitasnya dinilai dengan benchmark yang
representatif.

Urutan paling aman: (1) benchmark kualitas yang lebih kuat, (2) tuning
relevansi dan format respons, (3) perbaikan routing/retrieval berdasarkan
kasus gagal, kemudian (4) optimasi prompt dan performa. Pertahankan instruksi
agar model tidak menampilkan monolog internal; nilai penalaran dari alasan
utama yang dapat diverifikasi, ketepatan bukti, dan hasil—bukan panjang
“chain-of-thought”.
