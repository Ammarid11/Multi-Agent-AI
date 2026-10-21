# Diagram Algoritma Sistem Multi-Agent AI Second Brain

## 1. Diagram Alur Sistem

```mermaid
flowchart TD
    A[User Input] --> B{Valid Query?}
    B -- No --> X[Reject 400]
    B -- Yes --> C[Route by Slash Command or Intent]

    C --> D{Command Match?}
    D -- Yes --> E[Execute Direct Handler]
    D -- No --> F[Select Specialized Agent]

    F --> G[Load Context]
    G --> H[Vault Retrieval + Session Summary + Rules + Profile]
    H --> I[Agent Generates Response]
    I --> J{Need Tool Action?}
    J -- Yes --> K[Call Tool: read/write/delete/move/search]
    J -- No --> L[Return Response]
    K --> M[Update History + Memory + Rules]
    M --> L
```

---

## 2. Diagram Arsitektur Komponen

```mermaid
flowchart LR
    U[User] --> API[api_server.py]
    API --> ROUTER[AgentRouter]
    ROUTER --> WRITER[bot_writer]
    ROUTER --> THINK[bot_reasoner]
    ROUTER --> CODE[bot_coder]
    ROUTER --> FILE[bot_file_manager]
    ROUTER --> CURATOR[bot_curator]
    ROUTER --> WEB[bot_web]

    WRITER --> MEM[Memory + Vector Retrieval]
    THINK --> MEM
    CODE --> MEM
    WEB --> MEM
    FILE --> TOOLS[tools/]
    CURATOR --> TOOLS

    MEM --> QDRANT[Qdrant DB]
    MEM --> VAULT[Obsidian Vault]
    MEM --> HIST[Session History / Profile / Rules]
```

---

## 3. Diagram Indexing Vault

```mermaid
flowchart TD
    A[Scan Vault Folder] --> B[Read Markdown Files]
    B --> C[Normalize content]
    C --> D[Split into chunks]
    D --> E[Generate embeddings]
    E --> F[Store to Qdrant]
    F --> G[Save metadata + path mapping]
    G --> H[Ready for retrieval]
```

---

## 4. Diagram Retrieval Query

```mermaid
flowchart TD
    A[User Question] --> B[Keyword Search]
    A --> C[Vector Similarity Search]
    B --> D[Merge Results]
    C --> D
    D --> E[Rank Relevance]
    E --> F[Inject into Prompt Context]
    F --> G[Agent Answer]
```

---

## 5. Diagram Logika Agent Selection

```mermaid
flowchart TD
    A[Input Query] --> B{Starts with / ?}
    B -- Yes --> C[Command Handler]
    B -- No --> D{Intent Detected?}
    D -- Yes --> E[Use Specialized Agent]
    D -- No --> F[Use Default Agent: Writer]
    C --> G[Return Output]
    E --> G
    F --> G
```

---

## 6. Ringkasan Sederhana

```text
Ambil input
  ↓
Validasi
  ↓
Routing
  ↓
Konteks + memory retrieval
  ↓
Agent per task
  ↓
Tool jika dibutuhkan
  ↓
Update memory history
  ↓
Respons final
```

---

## 7. Interpretasi Inti

Sistem ini bekerja seperti orkestrasi kognitif: input masuk, dipilah, dihubungkan ke memori, dipetakan ke agent yang tepat, dan menghasilkan jawaban atau aksi. Struktur ini membuat system lebih mirip "assistant yang punya memory + tools + task routing" dibanding hanya model statis.
