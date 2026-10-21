# Algoritma Sistem Multi-Agent AI Second Brain (Versi Ringkas)

## 1. Tujuan Sistem

Sistem ini dirancang sebagai personal second brain yang menggabungkan:

- Obsidian Vault sebagai basis pengetahuan
- Qdrant sebagai database vektor
- AI agent spesialis untuk routing dan eksekusi tugas
- tool layer untuk manipulasi file, pencarian, dan aksi sistem

Tujuan utamanya: mengubah input user menjadi respons yang relevan, terstruktur, dan terhubung ke konteks vault yang tersimpan.

---

## 2. Pipeline Utama

```text
User Input
   ↓
Validasi Query
   ↓
Routing (slash command / intent detection)
   ↓
Ambil konteks relevan
   - session summary
   - user profile
   - rules SOP
   - vault retrieval
   ↓
Pilih agent spesialis
   ↓
Eksekusi agent
   ↓
Jika perlu, jalankan tool
   ↓
Update memory dan history
   ↓
Return output ke user
```

---

## 3. Algoritma Booting Sistem

```text
START
  load configuration
  init FastAPI app
  init MemoryManager
  scan Obsidian Vault
  index semua file .md ke vector DB
  create AITeam
  create AgentRouter
  start scheduler background
  server siap di localhost:8000
END
```

---

## 4. Algoritma Routing

```python
def route_and_execute(query):
    normalized = normalize(query)

    if is_slash_command(normalized):
        return execute_match_command(normalized)

    if keyword_matches_intent(normalized):
        return run_specialized_agent(normalized)

    return bot_writer(normalized)
```

### Prioritas routing:
1. Slash command (`/web`, `/think`, `/coder`, `/read`, dll.)
2. Keyword/intent detection
3. Default ke `bot_writer`

---

## 5. Algoritma Memory & Retrieval

```text
FOR every note in vault:
    read file
    normalize content
    split into chunks
    embed chunk
    store to vector database
END

WHEN user asks a question:
    retrieve top similar chunks from vector DB
    combine with keyword search
    inject into prompt as context
    send to selected agent
```

### Hasil dari retrieval:
- contextual memory
- topik relevan dari vault
- ringkasan sesi sebelumnya
- profil pengguna
- aturan operasional aktif

---

## 6. Algoritma Agent Execution

```python
def agent_execute(prompt, context):
    relevant_context = memory_search(prompt)
    full_prompt = combine(
        prompt,
        relevant_context,
        session_summary,
        user_profile,
        rules_context,
        chat_history,
    )
    response = llm_generate(full_prompt)
    return response
```

### Agent spesialis utama:
- `bot_writer` → percakapan umum / personal assistant
- `bot_reasoner` → analisis kritis
- `bot_coder` → development dan scripting
- `bot_web` → riset web
- `bot_file_manager` → create/read/update/delete file
- `bot_curator` → kurasi dan relokasi materi
- `bot_synthesizer` → sintesis ide

---

## 7. Algoritma File Management

```text
INPUT: prompt + chat history
  ↓
Build system prompt with vault map
  ↓
Ask model to return JSON
  ↓
Parse JSON result
  ↓
IF action == create: create_file
IF action == append: append_file
IF action == read: read_file
IF action == delete: delete_file
ELSE: return invalid action
```

Fungsi ini memberi sistem kontrol yang lebih aman dibandingkan direct file editing.

---

## 8. Algoritma Update Memory Setelah Respons

```python
def after_response(prompt, reply):
    chat_history.append({"role": "user", "content": prompt})
    chat_history.append({"role": "assistant", "content": reply})

    update_profile_from_interaction(prompt)
    detect_and_register_rule(prompt)

    chat_history, summaries = manage_history(
        chat_history,
        session_summaries,
        user_name
    )
```

Tujuannya:
- menjaga konteks sesi tetap relevan
- menyimpan preferensi pengguna
- meningkatkan kualitas interaksi selanjutnya

---

## 9. Kesimpulan Algoritmik

Model kerja sistem ini dapat diringkas menjadi:

```text
INPUT -> VALIDASI -> ROUTING -> RETRIEVAL -> AGENT -> TOOL -> MEMORY UPDATE -> OUTPUT
```

Artinya, sistem bukan hanya menjawab pertanyaan, tapi juga:

- mengingat konteks sebelumnya
- menghubungkan ke vault
- memilih agent yang tepat
- menjalankan aksi sesuai kebutuhan
- menjaga kualitas konsistensi via rules dan profile

---

## 10. Catatan Perbaikan Potensial

- pindahkan secret ke environment variable
- batasi panjang `chat_history`
- tambahkan logging per request
- perkuat validasi JSON output dari model
- tambah unit test untuk router dan memory retriever
