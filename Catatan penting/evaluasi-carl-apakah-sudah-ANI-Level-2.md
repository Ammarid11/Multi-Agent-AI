## 9. Evaluasi: Apakah Carl sudah ANI Level 2 Limited Memory?

**Tanggal evaluasi:** 14 Oktober 2026  
**Cakupan:** Pemeriksaan konfigurasi, alur agent, memori, API, tes yang tersedia,
dan laporan benchmark lokal pada repository. Ini evaluasi arsitektur dan bukti
yang tersedia, bukan sertifikasi AI atau audit keamanan formal.

### Kesimpulan singkat

**Belum ada dasar untuk menyebut Carl “ANI Level 2 Limited Memory yang
sempurna”.** “ANI” dan “limited memory” merupakan label konseptual, bukan
tingkat sertifikasi universal dengan kriteria kelulusan tunggal. Deskripsi
terukur yang lebih tepat untuk implementasi sekarang adalah:

> Carl adalah aplikasi asisten Second Brain berbasis model bahasa lokal, dengan
> retrieval catatan Vault (RAG), riwayat percakapan yang diringkas, serta
> penyimpanan profil dan aturan eksternal. Kemampuan ini membuatnya memiliki
> mekanisme memori terbatas dalam arti operasional, tetapi tidak membuktikan
> kemampuan, akurasi, atau reliabilitas yang sempurna.

Pemisahan agent, pemanggilan tool, atau banner “Level 4/5” tidak dengan
sendirinya menunjukkan tingkat kecerdasan formal yang lebih tinggi. Demikian
pula, menyimpan profil, aturan, dan catatan Vault adalah penggunaan memori
eksternal; itu bukan bukti bahwa model mengubah bobotnya atau belajar secara
mandiri dari percakapan.

### Bukti yang mendukung adanya memori terbatas

| Mekanisme | Implementasi yang terlihat | Batas/interpretasi |
|---|---|---|
| Memori percakapan aktif | AITeam mempertahankan `chat_history`, dan prompt memakai riwayat terbaru. | Konteks aktif bukan transkrip lengkap yang dijamin selalu dipertahankan. |
| Ringkasan sesi persisten | Ringkasan percakapan disimpan dengan timestamp; pemuatan menyaring umur lebih dari 48 jam dan membatasi jumlah ringkasan. | Ringkasan dapat kehilangan detail atau atribusi. Perilaku ini bukan memori fakta yang sempurna. |
| Retrieval Vault | File Markdown dipotong menjadi chunk, diindeks ke Qdrant, lalu dicari dengan retrieval vektor, kata kunci, ekspansi query kondisional, dan wikilink. | Retrieval bersifat kandidat: hasil kosong atau parsial tidak membuktikan informasi tidak ada di seluruh Vault. |
| Profil pengguna | Profil eksternal dapat memuat nama, minat, proyek, gaya jawaban, dan fakta penting. | Profil bertahan di disk; bukan bagian dari ringkasan 48 jam, dan kebijakan retensi/penghapusan menyeluruh belum dibuktikan. |
| Aturan/SOP | Aturan eksplisit dapat disimpan dan disisipkan ke konteks prompt. | Aturan persisten dapat usang atau saling bertentangan; memori tersebut bukan pembaruan parameter model. |

Referensi implementasi: `agents/__init__.py`, `memory/session_memory.py`,
`memory/manager.py`, `memory/document_loader.py`, `memory/user_profile.py`,
dan `memory/rules_engine.py`.

### Hasil evaluasi dan apa yang boleh disimpulkan

Laporan `evaluation/reports/pilot-2026-10-14.json` mencatat pilot **10
pertanyaan dari dua catatan**:

- Akurasi checklist keseluruhan: **2/10 (20%)**.
- Kasus dapat dijawab yang lulus syarat fakta sekaligus sumber: **0/8 (0%)**.
- Kecocokan fakta wajib literal untuk kasus dapat dijawab: **8/8 (100%)**.
- Citation rate: **0/8 (0%)**.
- Abstention untuk kasus yang tidak dapat dijawab: **2/2 (100%)**.

Interpretasinya harus presisi: fakta wajib yang ditentukan cocok pada jawaban
untuk delapan kasus tersebut, tetapi tidak ada satupun yang memenuhi syarat
sitasi benchmark. Jadi, hasil 0% pada kasus answerable **bukan bukti bahwa semua
isi jawaban salah**; hasil itu menunjukkan benchmark tidak meluluskan jawaban
tanpa sitasi yang diharapkan. Sebaliknya, kecocokan frasa fakta bukan bukti
bahwa semua klaim jawaban benar atau didukung sumber.

Pilot ini kecil, berasal dari catatan uji terisolasi, dan secara eksplisit tidak
mengukur penalaran, pemakaian tool, kebenaran semantik, atau kecerdasan
universal. Dataset aktif berisi 17 kasus, sehingga laporan 10 kasus tersebut
tidak boleh diperlakukan sebagai hasil untuk seluruh dataset. Hasil QA A–C yang
tercatat juga berisi kegagalan atau batas bukti; perubahan kode sesudahnya
belum membuktikan kasus-kasus tersebut lulus pada model dan Vault aktual.
Regresi dengan mock/fixture membuktikan kontrak kode yang diuji, bukan mutu
end-to-end.

### Kesenjangan yang masih menghalangi klaim matang/andal

1. **Akurasi jawaban live belum diukur secara representatif.** Belum ada
   rangkaian besar dan held-out yang mencakup fakta, retrieval, multi-hop,
   konflik sumber, abstention, parafrasa, dan variasi prompt. Metrik literal
   saat ini dapat melewatkan parafrasa yang benar atau memberi nilai pada
   kemunculan kata yang tidak membuktikan dukungan semantik.
2. **Sitasi belum sama dengan verifikasi dukungan klaim.** Pencocokan nama file
   memeriksa apakah sumber yang dikutip muncul dalam konteks; itu tidak
   membuktikan sumber tersebut mendukung setiap kalimat. Sitasi perlu ditinjau
   pada tingkat klaim terhadap bagian sumber.
3. **Kelengkapan dan kesehatan retrieval belum terlihat sebagai bukti
   terukur.** Potongan konteks dan top-k dapat melewatkan fakta penting.
   Beberapa jalur pemuatan catatan mengembalikan hasil kosong saat exception,
   sehingga kesalahan baca dapat menyerupai ketiadaan data. Catatan yang
   dikecualikan dari indeks memang tidak akan ditemukan oleh retrieval biasa.
4. **QA C2 masih menunggu pembuktian pada Vault aktif.** Tes pemeringkatan nama
   langka menggunakan fixture sintetis; belum membuktikan
   `Data Profil Orang Lain.md` terindeks atau isi catatan mendukung klaim
   tentang Alvi. Penyebutan nama tidak otomatis membuktikan gender.
5. **Kebijakan memori belum menjadi siklus hidup yang utuh.** Riwayat sesi punya
   batas umur, tetapi profil dan aturan tersimpan terpisah dan persisten.
   Perlu kebijakan yang dapat dijelaskan mengenai persetujuan, retensi,
   pemeriksaan, koreksi, dan penghapusan masing-masing jenis memori.
6. **Isolasi pengguna belum terbukti untuk penggunaan multi-user.** API
   menginisialisasi satu AITeam/router global, sedangkan profil dan aturan
   memakai berkas bersama. Ini perlu dibatasi/didokumentasikan sebagai
   single-user atau dirancang ulang sebelum melayani banyak pengguna dengan
   memori privat.
7. **Paparan jaringan perlu dikendalikan sebelum penggunaan LAN.** Server
   berjalan dengan host default `0.0.0.0` dan konfigurasi CORS wildcard.
   Keberadaan endpoint lokal tidak setara dengan autentikasi atau otorisasi;
   konfigurasi akses harus sesuai dengan model ancaman sebelum dibuka ke
   jaringan yang tidak sepenuhnya tepercaya.
8. **Reliabilitas, latensi, dan kualitas belum memiliki baseline rilis
   end-to-end yang lengkap.** Tes unit/regresi bukan pengukuran konsistensi
   model, p50/p95, perilaku saat service gagal, atau penggunaan resource pada
   konfigurasi produksi.

### Rencana penutupan gap tanpa mengulang pekerjaan yang sudah ada

Urutan ini membangun di atas benchmark, guard grounding, tes regresi, dan
retrieval yang sudah tersedia; tidak mengusulkan pembuatan ulang komponen
tersebut.

| Prioritas | Pekerjaan | Bukti selesai yang diperlukan |
|---|---|---|
| P0 | Jalankan ulang benchmark 17 kasus dengan versi kode/model/config yang dicatat; tambahkan kasus B1–B3 dan C1–C4 dengan sumber fixture terverifikasi. Untuk C1 gunakan detail spesifik yang terbukti tidak ada. | Jawaban mentah, sumber/chunk retrieval, status tiap kriteria, kegagalan yang tidak disembunyikan, dan tinjauan manusia per klaim. |
| P0 | Perbaiki dan ukur retrieval terhadap query manusia, termasuk nama orang, alias, bentuk kata, file relevan yang panjang, dan pertanyaan multi-bagian. | Recall/Hit@k, MRR atau nDCG, precision sumber, kasus gagal, serta tes bahwa kesalahan baca/indeks dilaporkan berbeda dari “tidak tercatat”. |
| P0 | Tetapkan lingkup deployment single-user atau multi-user. Jika multi-user/LAN, rancang identitas dan isolasi riwayat/profil/aturan serta autentikasi dan pembatasan CORS/host. | Tes bahwa pengguna berbeda tidak dapat membaca/mengubah konteks satu sama lain; konfigurasi jaringan dan akses terverifikasi. |
| P1 | Lengkapi manajemen memori: tampilkan apa yang disimpan, atribusi dan waktu, mekanisme koreksi, retensi terpisah, serta penghapusan yang terverifikasi. | Tes simpan/baca/koreksi/hapus untuk ringkasan, profil, dan aturan; definisi jelas tentang cakupan `/reset`. |
| P1 | Tingkatkan evaluasi grounding dari keberadaan nama sitasi menjadi pemeriksaan klaim-sumber. | Review manusia berlabel pada set pengembangan dan held-out; ukur klaim didukung, tidak didukung, kontradiksi, dan sitasi salah. Judge otomatis, bila ditambahkan, harus dibandingkan dengan label manusia. |
| P1 | Ukur kualitas dan operasi secara terpisah dengan konfigurasi tetap. | Pengulangan kasus untuk variasi output; metrik kategori, latensi p50/p95, error rate, dan resource. Kriteria lulus ditetapkan sebelum tuning. |
| P2 | Setelah baseline stabil, uji konflik aturan, batas konteks, retrieval graph, routing bahasa natural, dan kegagalan tool secara bertahap. | Satu perubahan per eksperimen, hasil terhadap set yang sama, serta tidak ada regresi pada held-out. |

### Kriteria klaim yang lebih aman

Sebelum gap P0 ditutup, gunakan deskripsi **“prototipe asisten Second Brain
dengan memori sesi terbatas dan retrieval Vault”**, bukan “ANI Level 2 sempurna”
atau “Level 4/5 terverifikasi”. Setelah evaluasi pun, laporkan kemampuan
berdasarkan benchmark, konfigurasi, tanggal, dan batas pengujian—hindari
klaim kesempurnaan. Tidak ada satu skor atau jumlah fitur yang membuktikan
kesempurnaan sistem AI.
