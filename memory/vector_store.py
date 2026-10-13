# memory/vector_store.py
import os
import uuid
import logging
from typing import List, Optional
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, Filter, FieldCondition, MatchValue
import config

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """Mengelola koneksi, pembersihan sinkron, dan operasi pencarian vektor di Qdrant DB."""
    def __init__(self, embeddings):
        self.embeddings = embeddings
        self.client: Optional[QdrantClient] = None
        self.vector_db: Optional[QdrantVectorStore] = None
        self._init_client()
        self.load_db()

    def _init_client(self) -> None:
        """Inisialisasi klien Qdrant dengan penanganan gracefully jika folder terkunci."""
        try:
            self.client = QdrantClient(path=config.DB_PATH)
        except Exception as e:
            if "already accessed by another instance" in str(e).lower() or "lock" in str(e).lower():
                logger.warning("Qdrant path is locked by another process: %s", config.DB_PATH)
            else:
                logger.exception("Unable to initialize Qdrant client at %s", config.DB_PATH)
            self.client = None

    def load_db(self) -> None:
        """Memuat Vector DB Qdrant jika client aktif."""
        if not self.client:
            return
        try:
            collections = [c.name for c in self.client.get_collections().collections]
            if config.COLLECTION_NAME in collections:
                self.vector_db = QdrantVectorStore(
                    client=self.client,
                    collection_name=config.COLLECTION_NAME,
                    embedding=self.embeddings
                )
        except Exception:
            logger.exception("Unable to load Qdrant collection %s", config.COLLECTION_NAME)
            self.vector_db = None

    def init_fresh_collection(self) -> None:
        """Membuat koleksi baru yang bersih."""
        if not self.client:
            return
        os.makedirs(config.DB_PATH, exist_ok=True)
        sample = self.embeddings.embed_query("test")
        self.client.recreate_collection(
            collection_name=config.COLLECTION_NAME,
            vectors_config=VectorParams(size=len(sample), distance=Distance.COSINE)
        )
        self.vector_db = QdrantVectorStore(
            client=self.client,
            collection_name=config.COLLECTION_NAME,
            embedding=self.embeddings
        )

    def delete_documents_by_sources(self, source_paths: List[str]) -> None:
        """
        ANTI-ZOMBIE CHUNKS:
        Menghapus seluruh point/vektor yang terafiliasi dengan file yang diedit atau dihapus.
        """
        if not source_paths or not self.client or not self.vector_db:
            return

        for src in source_paths:
            norm_src = os.path.normpath(src)
            try:
                # Coba hapus point di mana metadata.source cocok dengan path file
                self.client.delete(
                    collection_name=config.COLLECTION_NAME,
                    points_selector=Filter(
                        should=[
                            FieldCondition(key="metadata.source", match=MatchValue(value=norm_src)),
                            FieldCondition(key="metadata.source", match=MatchValue(value=src)),
                            FieldCondition(key="source", match=MatchValue(value=norm_src)),
                        ]
                    )
                )
            except Exception:
                logger.exception("Failed deleting indexed chunks for source %s", norm_src)

    def add_documents_with_unique_ids(self, chunks: List[Document]) -> None:
        """Menambahkan dokumen ke database dengan ID unik anti-duplikasi."""
        if not chunks or not self.vector_db:
            return
        ids = [
            str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{c.metadata.get('source', '')}::{c.page_content[:120]}"))
            for c in chunks
        ]
        self.vector_db.add_documents(chunks, ids=ids)

    def similarity_search(self, query: str, k: int = 6) -> List[Document]:
        """Pencarian vektor terdekat."""
        if not self.vector_db:
            self.load_db()
        if not self.vector_db:
            raise RuntimeError("Qdrant vector collection is unavailable.")
        try:
            return self.vector_db.similarity_search(query, k=max(1, k))
        except Exception:
            logger.exception("Vector search failed for query")
            raise
