# Catatan Pemulihan Tahap 5 — Keep-Alive

Tanggal pemeriksaan: 14 Oktober 2026

## Tujuan

Catatan ini merekam keadaan konfigurasi Tahap 5 sebelum uji cold/warm singkat
agar keadaan awal jelas dan dapat dipulihkan jika ada perubahan konfigurasi di
kemudian hari.

## Keadaan sebelum uji

File konfigurasi aplikasi: `config.py`

- `MODEL_WRITER = "qwen2.5:7b"`
- `MODEL_REASONER = "deepseek-r1:8b"`
- `KEEP_ALIVE_DEFAULT = "2m"`
- `KEEP_ALIVE_SPECIALIST = "30s"`
- `OPTIONS_REASONER = {"temperature": 0.6}`

Snapshot runtime baca-saja sebelum uji:

- GPU: NVIDIA GeForce RTX 4060, total 8.188 MiB.
- VRAM bebas: 5.584 MiB.
- RAM bebas: sekitar 5,69 GiB.
- Ollama `/api/ps`: tidak ada model yang aktif pada saat pemeriksaan.
- `deepseek-r1:8b` terpasang dalam quantization `Q4_K_M`, ukuran model yang
  dilaporkan Ollama 5.225.376.047 byte.

## Perubahan persisten

**Tidak ada perubahan pada kode aplikasi atau `config.py`.**

Uji yang disetujui menggunakan request Ollama sementara dengan
`keep_alive: "30s"`, `num_ctx: 2048`, temperature `0.6`, dan batas output
pendek. Opsi `num_ctx` dan batas output tersebut hanya berlaku pada request uji;
tidak ditulis ke konfigurasi aplikasi. Ollama dapat memuat model selama
pengujian dan melepasnya sesuai keep-alive yang diminta.

## Cara memulihkan konfigurasi aplikasi

Karena konfigurasi aplikasi tidak diubah, tidak perlu rollback kode. Jika ada
perubahan manual di kemudian hari dan ingin kembali ke baseline Tahap 5, pastikan
nilai berikut di `config.py`:

```python
KEEP_ALIVE_DEFAULT = "2m"
KEEP_ALIVE_SPECIALIST = "30s"
OPTIONS_REASONER = {"temperature": 0.6}
```

Setelah mengubah nilai konfigurasi secara manual, restart server Carl agar
proses membaca konfigurasi kembali.

## Hasil uji

Uji minimum dijalankan tanpa mengubah file aplikasi:

- Dua request berurutan memakai `keep_alive: "30s"`, `num_ctx: 2048`,
  temperature `0.6`, dan `num_predict: 48`.
- Cold request: 17.405 ms waktu client; Ollama melaporkan `total_duration`
  15.322,62 ms, 21 token prompt dan 48 token output. `message.content` kosong
  karena batas output pendek terpakai pada penalaran.
- Warm request dengan parameter sama: 1.422 ms waktu client; Ollama
  melaporkan `total_duration` 1.421,38 ms, 21 token prompt dan 48 token
  output. `message.content` juga kosong.
- Uji warm tambahan memakai `num_predict: 512`: 12.492 ms waktu client;
  Ollama melaporkan `total_duration` 10.438,2 ms dengan 363 token output.
  Balasan menyebut Tokyo, tetapi juga menyertakan detail sejarah yang tidak
  akurat/tidak diperlukan. Ini bukan hasil kualitas yang lulus.
- Saat model aktif, `/api/ps` melaporkan `size_vram` 5.274.117.078 byte dan
  context 2.048. Snapshot `nvidia-smi` terendah yang teramati menunjukkan
  537 MiB VRAM bebas; tidak ada error/OOM pada request uji.
- Setelah menunggu 35 detik dari request terakhir, `/api/ps` kembali kosong
  dan VRAM bebas 5.562 MiB. RAM bebas terukur 5,69 GiB sebelum uji, 4,87 GiB
  setelah inference, dan 4,36 GiB setelah masa tunggu; nilainya tidak pulih
  pada snapshot akhir, dan penyebab perubahan RAM tidak dapat dipastikan dari
  pengukuran ini.

Kesimpulan: model berhasil menjalankan request singkat lalu auto-unload dengan
keep-alive baseline 30 detik. Headroom VRAM sangat tipis pada kondisi uji;
uji ini tidak membuktikan stabilitas untuk prompt/context produksi, sesi
panjang, atau keep-alive lebih lama.

## Jaminan tidak ada penerapan

- `config.py` tidak diedit; baseline `KEEP_ALIVE_DEFAULT = "2m"` dan
  `KEEP_ALIVE_SPECIALIST = "30s"` tetap berlaku.
- Tidak ada nilai keep-alive yang dinaikkan atau perubahan model yang
  diterapkan.
- Dokumen ini hanya mencatat baseline dan hasil uji agar konfigurasi awal
  dapat dipulihkan jika ada eksperimen berikutnya.
