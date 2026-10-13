# 🧠 Plan: Upgrade Multi-Agent AI — Lebih Pintar & Logika Lebih Baik

## 🎯 Tujuan
Membuat sistem AI lebih cerdas dalam memahami intent, memberikan jawaban lebih relevan, dan mengelola percakapan dengan lebih kontekstual — **tanpa menambah model baru**, murni perbaikan arsitektur & logika.

---

## 📋 5 Area Peningkatan

---

### ✅ Area 1 — Smart LLM Router (Ganti keyword matching → AI intent detection)

**Masalah sekarang:**
Router pakai `if "coding" in prompt` — rapuh dan mudah miss-route.

**Solusi:**
Tambah `bot_router_llm.py` — agent kecil yang pakai LLM untuk klasifikasi intent sebelum routing.

```
User: "tolong cariin info soal deepseek r1 terbaru"
→ Router LLM: { "intent": "web_search" }   ✅ (bukan default writer)

User: "buatin fungsi python buat sorting"
→ Router LLM: { "intent": "coder" }         ✅
```

**Flow baru:**
```
Input → [1] Slash Command? → Yes: langsung eksekusi
                           → No: [2] LLM Intent Classifier
                                     → route ke agent yang tepat
```

**File:** `agents/bot_router_llm.py` (baru)  
**Edit:** `agents/router.py`

---

### ✅ Area 2 — Memory Upgrade (Query Expansion + Re-ranking)

**Masalah sekarang:**
- Query langsung dicari ke vector DB → bisa miss jika user pakai kata berbeda
- Hasil keyword + vector digabung tanpa re-ranking berdasarkan relevansi

**Solusi A — Query Expansion:**
Sebelum search, expand query user jadi 2-3 variasi sinonim pakai LLM ringan.

```
User: "apa hobi dini?"
→ Expanded: ["hobi dini", "aktivitas dini", "kesukaan dini", "kegiatan dini"]
→ Search dengan semua variasi → hasil lebih lengkap
```

**Solusi B — Re-ranking dengan skor gabungan:**
Tambahkan skor posisi + skor frekuensi keyword ke hybrid search.

**File:** `memory/hybrid_search.py` (edit)  
**File:** `memory/query_expander.py` (baru)

---

### ✅ Area 3 — Improved System Prompts per Agent

**Masalah sekarang:**
System prompt tiap agent terlalu generik dan tidak ada panduan format output.

**Peningkatan per agent:**

| Agent | Peningkatan |
|:---|:---|
| **bot_writer (Carl)** | Tambah instruksi: bedakan "tahu dari catatan" vs "tidak tahu", wajib sebut sumber file |
| **bot_reasoner** | Tambah struktur: Problem → Root Cause → Solution → Action Items |
| **bot_coder** | Tambah: selalu sertakan docstring, contoh penggunaan, dan handle error |
| **bot_web** | Tambah: selalu sertakan credibility check sumber, tanggal informasi |
| **bot_synthesizer** | Tambah: output wajib ada "🔗 Koneksi Ide" dan "💡 Insight Baru" |

---

### ✅ Area 4 — Conversation Memory Management (Session Summarizer)

**Masalah sekarang:**
`chat_history` list tumbuh tanpa batas. Dipotong kasar di 3-4 pesan terakhir → AI lupa konteks penting di awal sesi.

**Solusi — Rolling Summary:**
Setiap 10 pesan, ringkas riwayat jadi summary singkat pakai LLM. Summary ini disimpan dan diinjeksi ke system prompt sebagai "memori sesi".

```
[Setelah 10 pesan]
Summary: "Ammar membahas proyek AI, minta info tentang Dini (teman, suka sudoku),
          dan menambahkan catatan tentang buku Clean Code."

[Pesan ke-11+]
System: "... RINGKASAN SESI: {summary} ... PESAN TERAKHIR: {last_4_messages}"
```

**File:** `memory/session_memory.py` (baru)  
**Edit:** `agents/__init__.py`, semua agent yang pakai `chat_history`

---

### ✅ Area 5 — Agent Collaboration (Chaining)

**Masalah sekarang:**
Agent berdiri sendiri-sendiri, tidak bisa saling bantu.

**Solusi — 2 chain sederhana:**

**Chain 1: Web → Reasoner**
```
/web <query>
→ bot_web ambil hasil internet
→ bot_reasoner analisis & buat kesimpulan mendalam
→ Output: jawaban lebih analitis, bukan sekadar rangkuman
```

**Chain 2: Writer → Reasoner (Fallback)**
```
bot_writer tidak menemukan konteks relevan di vault
→ Otomatis escalate ke bot_reasoner untuk reasoning dari pengetahuan umum
→ Tetap beritahu user: "Tidak ditemukan di catatan, menjawab dari pengetahuan umum..."
```

**Edit:** `agents/bot_web.py`, `agents/bot_writer.py`

---

## 📐 Arsitektur Baru (Flow)

```
User Input
    │
    ▼
[Slash Command?] ──Yes──→ Direct Execute
    │ No
    ▼
[LLM Intent Classifier]  ← BARU (Area 1)
    │
    ├─ web      → bot_web → [bot_reasoner chain]  ← BARU (Area 5)
    ├─ think    → bot_reasoner
    ├─ code     → bot_coder
    ├─ sintesis → bot_synthesizer
    ├─ file     → bot_file_manager
    └─ default  → bot_writer
                      │
                      ├─ Konteks ditemukan? → Jawab + sebutkan sumber
                      └─ Tidak ditemukan?  → Escalate ke reasoner  ← BARU (Area 5)

Memory Flow (BARU):
    Query → [Query Expander] → Hybrid Search → [Re-ranker] → Context
    Chat  → [Rolling Summarizer setiap 10 msg] → Session Memory
```

---

## 🗓️ Urutan Pengerjaan

| # | Area | File | Prioritas |
|---|---|---|---|
| 1 | Smart LLM Router | `agents/bot_router_llm.py` + `router.py` | 🔴 Tinggi |
| 2 | Improved Prompts | Semua `agents/bot_*.py` | 🔴 Tinggi |
| 3 | Session Memory | `memory/session_memory.py` + agent | 🟡 Sedang |
| 4 | Query Expansion | `memory/query_expander.py` + `hybrid_search.py` | 🟡 Sedang |
| 5 | Agent Chaining | `bot_web.py` + `bot_writer.py` | 🟢 Bonus |

---

> [!IMPORTANT]
> Semua perubahan **backward-compatible** — tidak ada perubahan interface publik, tidak perlu reset Qdrant lagi.
> 
> Kalau setuju dengan plan ini, ketik **Proceed** dan saya langsung kerjakan semua area sekaligus.
