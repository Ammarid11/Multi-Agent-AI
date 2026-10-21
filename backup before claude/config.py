# config.py
import os

# Path Direktori Obsidian Vault & Database Vektor
VAULT_PATH = "E:/Project AI 2026/Obsidian/Brain AI Memory"
DB_PATH = "E:/Project AI 2026/Multi-Agent AI/db/qdrantstorage"
COLLECTION_NAME = "obsidian_vault"

# Model Ollama (Full Local)
MODEL_EMBEDDING = "nomic-embed-text"
MODEL_WRITER = "qwen2.5:7b"
MODEL_REASONER = "deepseek-r1:8b"
MODEL_CODER = "qwen2.5-coder:7b"

# Host & Efisiensi VRAM
OLLAMA_HOST = "http://localhost:11434"
KEEP_ALIVE_DEFAULT = "2m"
KEEP_ALIVE_SPECIALIST = "30s"

# Opsi Pemanggilan Model
OPTIONS_WRITER = {"temperature": 0.3}
OPTIONS_REASONER = {"temperature": 0.6}
OPTIONS_CODER = {"temperature": 0.2}
OPTIONS_CLEANER = {"temperature": 0.1}