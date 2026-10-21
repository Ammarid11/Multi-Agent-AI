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

- Dataset jawaban awal yang ditelaah memiliki 10 kasus: 8 dapat dijawab dan 2 menguji
  abstention. Ini awal yang berguna, tetapi belum cukup untuk menyimpulkan
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

## Status penerapan

Peningkatan kualitas prompt dan benchmark berikut telah diterapkan:

1. Instruksi Writer kini meminta rekomendasi proaktif secara kondisional,
   bukan pada akhir setiap jawaban.
2. Instruksi Reasoner kini menyesuaikan format dengan pertanyaan sederhana,
   analisis/solusi, perbandingan, hitungan, atau permintaan multi-bagian tanpa
   memaksakan template yang sama.
3. Benchmark jawaban lokal diperluas dari 10 menjadi 17 kasus yang disusun dan
   dicocokkan dengan dua catatan sumbernya; variasinya mencakup parafrasa,
   pertanyaan multi-bagian, dan informasi yang tidak tersedia.

Dalam lingkup optimasi yang kompatibel dengan RTX 4060 8 GB, Ryzen 5 5600, dan
RAM 32 GB, hanya tiga peningkatan berikut diterapkan:

1. **Instrumentasi:** log durasi antrean/eksekusi, routing, retrieval
   (vektor, keyword, ekspansi, graf, dan format), persiapan prompt, inference,
   serta total untuk jalur yang diinstrumentasi. Log ini tidak menyimpan isi
   prompt atau jawaban; panjang prompt dicatat sebagai jumlah karakter, bukan
   jumlah token.
2. **Streaming respons:** polling job API menampilkan teks parsial dari
   Writer/Coder tanpa mengubah kontrak job yang ada. Jalur Reasoner, Web, dan
   Synthesizer tetap non-streaming agar teks penalaran internal tidak dikirim
   sebagai potongan mentah.
3. **Evaluasi yang dapat ditinjau manusia:** `evaluate_answers.py` menerima
   `--review-output` opsional untuk membuat lembar JSON berisi jawaban dan
   kolom penilaian kosong. Pembuatan file harus diminta eksplisit karena
   isinya dapat memuat materi turunan Vault.

Cache lexical dan perubahan Graph RAG tidak diterapkan. Model, parameter
inferensi, konteks, keep-alive, dan jumlah worker juga tidak diubah. Benchmark
yang lebih luas dan observabilitas memperbaiki sarana evaluasi/diagnostik,
tetapi tidak dengan sendirinya membuktikan peningkatan akurasi atau latensi.
