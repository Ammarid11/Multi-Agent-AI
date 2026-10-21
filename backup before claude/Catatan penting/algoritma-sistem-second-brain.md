# Algoritma Sistem Multi-Agent AI Second Brain

## 1. Ringkasan Proyek

Proyek ini adalah sistem AI personal berbasis Obsidian Vault yang berfungsi seperti "Second Brain". Inti sistemnya adalah:

- membaca, mengindeks, dan menelusuri catatan Markdown di vault
- menyimpan representasi semantik ke vector database (Qdrant)
- memetakan pertanyaan user ke agent yang tepat
- menjalankan operasi file, pencarian web, penalaran, kode, dan sintesis ide
- menyimpan memori sesi dan aturan operasional agar output lebih konsisten

Sistem utama menggabungkan beberapa komponen:

- `api_server.py` sebagai layer HTTP/FastAPI untuk UI browser/Obsidian sidecar
- `agents/router.py` sebagai router perintah dan intent detection
- `agents/__init__.py` sebagai orkestrator tim agent
- `memory/` untuk pembacaan vault, indexing, retrieval, dan konteks sesi
- `tools/` untuk CRUD file, relokasi, clean, search, dll.
- `config.py` untuk konfig model, vault path, dan opsi runtime

---

## 2. Analisis Arsitektur Secara Menyeluruh

### 2.1 Layer Input dan UI

- `api_server.py` menyediakan endpoint seperti:
  - `/api/chat` untuk percakapan utama
  - `/api/status` untuk monitoring sistem
  - `/api/briefing`, `/api/sentinel`, `/api/backup`, `/api/vision`, `/api/research`, dll.
- Aplikasi menerima request dari browser atau Obsidian custom sidecar.
- FastAPI menyiapkan middleware CORS agar bisa diakses dari Obsidian/Webview.

### 2.2 Layer Routing

`AgentRouter` bekerja dengan pendekatan 2 tahap:

1. Stage 1: pattern matching terhadap slash command seperti `/web`, `/think`, `/coder`, `/read`, `/write`, `/move`, `/clean`
2. Stage 2: jika input tidak masuk command, sistem memakai classifier LLM untuk menentukan intent secara lebih fleksibel

Fungsinya adalah menghindari buatan yang terlalu umum dan memastikan tugas diarahkan ke agent yang tepat.

### 2.3 Layer Agent

`AITeam` menampung agent spesialis berikut:

- `bot_writer`: agent utama untuk percakapan umum
- `bot_reasoner`: penalaran kritis
- `bot_coder`: coding and script generation
- `bot_web`: riset web
- `bot_synthesizer`: sintesis ide / knowledge graph
- `bot_curator`: kurasi dan relokasi materi
- `bot_file_manager`: manajemen file Obsidian
- `bot_cleaner`: pembersihan struktur note
- `bot_goal`, `bot_council`, `bot_simulator`, `bot_trainer`, `bot_gemini`, dst.: fitur lanjutan / frontier

### 2.4 Layer Memory

Memory system berfungsi sebagai "otak terdistribusi":

- membaca semua file `.md` di vault
- mengekstrak isi catatan dan metadata
- menyimpan embedding vector ke Qdrant
- menggabungkan retrieval vector + pencarian kata kunci
- mengelola profil pengguna, aturan operasional, dan ringkasan sesi

Semua ini dibuat untuk menjaga konteks saat user bertanya mengenai topik tertentu, tanpa harus membaca seluruh vault tiap kali.

### 2.5 Layer Tools

Tools bertanggung jawab atas aksi konkret di system:

- membuat file
- menambah isi catatan
- membaca file
- menghapus file
- memindahkan konten antar note
- membersihkan struktur folder / format note
- melakukan pencarian web
- menjalankan sandbox Python

Dengan pola seperti ini, agent tidak langsung menulis ke disk secara sembarangan. Ia memanggil tool yang terdefinisi dan aman.

---

## 3. Algoritma Utama Sistem

### 3.1 Flow 1: Booting Sistem

```text
START
  load config
  init project root
  init FastAPI app
  init MemoryManager
  index vault (scan .md files)
  init AITeam
  init AgentRouter
  start background scheduler
  server ready at localhost:8000
END
```

### 3.2 Flow 2: Proses Chat Normal

```text
INPUT: user query

IF query empty:
    reject with 400

IF router not initialized:
    reject with 503

CALL router.route_and_execute(query)

IF query matches slash command:
    execute direct command handler
ELSE:
    detect intent via keyword/LLM classifier
    select appropriate agent

SELECT context:
    - session summary
    - profile user
    - active rules
    - recent chat history
    - vault memory retrieval

CALL agent with context

agent generates response
append user + assistant records to history
update memory profile and rules
return final response to user
```

### 3.3 Flow 3: Routing dan Agent Selection

```text
FUNCTION route_and_execute(query):
    normalized = normalize(query)

    IF normalized starts with slash command:
        dispatch to exact handler
        return result

    IF command keywords detected:
        dispatch to specialized agent
        return result

    SELECT default agent = bot_writer
    return bot_writer(prompt, memory, history, context)
END
```

### 3.4 Flow 4: Agent Execution

```text
FUNCTION agent_exec(prompt, memory, history, context):
    retrieval = memory.search(prompt)
    prompt_with_context = inject(retrieval + history + profile + rules)
    response = LLM(prompt_with_context)
    return response
END
```

### 3.5 Flow 5: Memory Indexing

```text
FUNCTION index_vault():
    scan all .md files in vault
    for each file:
        read content
        normalize text
        split into chunks
        embed each chunk
        store to vector DB
    save metadata and hash
END
```

### 3.6 Flow 6: File Management Agent

```text
FUNCTION run_bot_file_manager(prompt, chat_history):
    build system prompt with vault map and operational rules
    send last messages to LLM
    parse JSON result
    IF parse failed:
        return error

    action = parse(action)
    switch action:
        create -> create_file(filename, content)
        append -> append_file(filename, content, section)
        read -> read_file(filename)
        delete -> delete_file(filename)
        else -> return invalid action
END
```

### 3.7 Flow 7: Curator Agent

```text
FUNCTION run_bot_curator(prompt, chat_history):
    load vault map
    ask model to decide best target file and section
    parse JSON output
    IF invalid JSON:
        return failure message

    relocate_content(source, target, snippet, section)
    return result
END
```

---

## 4. Pseudocode Sistem Lengkap

```python
def main():
    app = FastAPI()
    memory = MemoryManager()
    memory.index_vault()

    team = AITeam(memory, user_name="Pengguna")
    router = AgentRouter(team)

    start_background_scheduler()

    @app.post("/api/chat")
    async def chat(req):
        if not req.query.strip():
            raise HTTPException(400)

        if router is None:
            raise HTTPException(503)

        reply = router.route_and_execute(req.query.strip())
        return {"reply": reply, "status": "ok"}

    uvicorn.run(app)
```

```python
class AgentRouter:
    def route_and_execute(self, query):
        if is_slash_command(query):
            return execute_command(query)

        intent = classify_intent(query)
        if intent == "web":
            return team.bot_web(query)
        if intent == "think":
            return team.bot_reasoner(query)
        if intent == "coder":
            return team.bot_coder(query)
        if intent == "write":
            return team.bot_file_manager(query)
        return team.bot_writer(query)
```

```python
class AITeam:
    def _after_response(self, prompt, reply):
        chat_history.append({"role": "user", "content": prompt})
        chat_history.append({"role": "assistant", "content": reply})
        update_profile_from_interaction(prompt)
        detect_and_register_rule(prompt)
        chat_history, summaries = manage_history(chat_history, summaries)
```

---

## 5. Komponen Kunci Berdasarkan File

### `api_server.py`
- entry point HTTP
- endpoint untuk chat, status, backup, TTS, voice, vision, canvas, dan fitur lanjutan
- mengatur lifecycle aplikasi dan scheduler

### `agents/router.py`
- router perintah dan intent
- menentukan kapan fitur khusus dipanggil
- menangani command `/read`, `/write`, `/append`, `/move`, dll.

### `agents/__init__.py`
- `AITeam` orchestrates all agents
- menyimpan chat_history, session summaries, user profile, rules engine
- memanggil `manage_history` untuk membatasi konteks penting

### `config.py`
- model: `qwen2.5:7b`, `deepseek-r1:8b`, `qwen2.5-coder:7b`
- path vault dan DB Qdrant
- parameter runtime seperti temperature

### `memory/`
- index vault, store vector embeddings, search semantik,build session context
- menjadikan sistem lebih "ingat" terhadap notes dan topik user

### `tools/`
- menyediakan tindakan yang aman dan eksplisit pada vault atau sistem
- menghilangkan kebutuhan agent untuk memanipulasi file secara langsung

---

## 6. Keunggulan Desain

- Modular: masing-masing agent berdiri sendiri
- Router cepat: slash command langsung diproses tanpa LLM
- Memory berbasis semantik: retrieval lebih relevan daripada sekadar keyword
- Multi-agent: beberapa departemen AI untuk fungsi yang berbeda
- Obsidian-integrated: sinkronisasi dengan notes dan knowledge base

---

## 7. Risiko dan Potensi Perbaikan

### 7.1 Risiko Teknis
- API key dan konfigurasi sensitif mungkin disimpan dalam file biasa
- beberapa fitur menggunakan proses async dan I/O file yang perlu pengelolaan error yang lebih kuat
- chat history bisa berkembang besar jika tidak dibatasi dengan baik
- fungsi lintas-agent perlu validasi lebih ketat untuk mencegah hasil tidak konsisten

### 7.2 Potensi Perbaikan
- pindahkan secret ke `.env` atau environment variables
- normalisasi semua input query sebelum diproses
- tambahkan logging / tracing untuk setiap langkah agent
- gunakan class response standard untuk semua agent
- tambahkan test unit untuk router, file manager, dan memory retrieval

---

## 8. Kesimpulan Algoritmik

Sistem ini bekerja seperti pipeline berikut:

1. Ambil input dari user
2. Validasi dan normalisasi query
3. Lakukan routing command/intent
4. Ambil konteks relevan dari memory, profil, rules, dan sesi
5. Pilih agent spesialis
6. Jalankan model untuk menghasilkan keputusan/teks
7. Jika ada tindakan, panggil tool khusus
8. Simpan hasil ke sesi dan update memory
9. Kembalikan respons final ke user

Secara singkat, algoritma sistem ini adalah:

```text
INPUT -> VALIDASI -> ROUTING -> RETRIEVAL KONTEX -> AGENT SELEKSI -> EXECUTION -> TOOL ACTION -> UPDATES -> OUTPUT
```

Ini adalah pola `cognitive orchestration` yang menggabungkan retrieval, planning, tool use, dan memory persistence menjadi satu loop kerja AI.
