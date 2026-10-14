# memory/manager.py
import os
import re
import warnings
import logging
import time
from typing import List, Dict, Optional, Set, Tuple
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
import config

from memory.vector_store import VectorStoreManager
from memory.vault_scanner import (
    scan_vault_mtimes,
    detect_file_changes,
    extract_and_update_chunks,
    extract_all_chunks,
    load_saved_mtimes,
    save_mtimes
)
from memory.hybrid_search import (
    STOPWORDS,
    combine_search_results,
    get_ranked_keyword_results,
    merge_ranked_results,
)
from memory.query_expander import expand_query
from memory.graph_retriever import traverse_graph_links
from observability import log_stage

warnings.filterwarnings("ignore", category=UserWarning)
logger = logging.getLogger(__name__)


def _has_explicit_keyword_source_match(query: str, keyword_results: List[Document]) -> bool:
    query_terms = {
        term
        for term in re.findall(r"\w+", query.casefold(), flags=re.UNICODE)
        if len(term) > 2 and term not in STOPWORDS
    }
    if len(query_terms) < 2:
        return False

    for document in keyword_results[:3]:
        source_stem = os.path.splitext(os.path.basename(str(document.metadata.get("source", ""))))[0]
        source_terms = {
            term
            for term in re.findall(r"\w+", source_stem.casefold(), flags=re.UNICODE)
            if len(term) > 2 and term not in STOPWORDS
        }
        if len(source_terms) >= 2 and source_terms.issubset(query_terms):
            return True
    return False


class MemoryManager:
    """Manajer Memori: Sinkronisasi vault Obsidian, vector DB, dan hybrid search RRF."""
    def __init__(self):
        self.embeddings = OllamaEmbeddings(model=config.MODEL_EMBEDDING, base_url=config.OLLAMA_HOST)
        self.store = VectorStoreManager(self.embeddings)
        self.all_chunks: List[Document] = []
        self.cache_path = os.path.join(config.DB_PATH, ".vault_mtimes.json")
        self.file_mtimes: Dict[str, float] = load_saved_mtimes(self.cache_path)
        self.needs_sync: bool = False

    def index_vault(self, silent: bool = False) -> None:
        """Memindai dan menyinkronkan seluruh catatan di Obsidian Vault."""
        if not os.path.exists(config.VAULT_PATH):
            return

        if not self.store.client:
            if not silent:
                print("⚠️ [Memory Manager] Klien Qdrant tidak tersedia (kemungkinan folder terkunci oleh proses lain).")
            self._load_chunks_if_needed(force=True)
            return

        collections = self._get_collection_names()
        if collections is None:
            self._load_chunks_if_needed(force=True)
            return

        if config.COLLECTION_NAME in collections and self.store.vector_db is None:
            logger.error(
                "Qdrant collection %s exists but could not be loaded; refusing to recreate it.",
                config.COLLECTION_NAME,
            )
            self._load_chunks_if_needed(force=True)
            return

        is_fresh = config.COLLECTION_NAME not in collections
        if is_fresh:
            if not silent:
                print("\n🧹 [Memory Manager] Menginisialisasi database memori...")
            self.store.init_fresh_collection()
            self.file_mtimes = {}

        current_files = scan_vault_mtimes(config.VAULT_PATH)
        self._sync_vault_chunks(current_files, is_fresh, silent)

    def _load_chunks_if_needed(self, force: bool = False) -> None:
        if force or not self.all_chunks:
            current_files = scan_vault_mtimes(config.VAULT_PATH)
            self.all_chunks = extract_all_chunks(list(current_files.keys()))

    def _get_collection_names(self) -> Optional[Set[str]]:
        try:
            return {
                collection.name
                for collection in self.store.client.get_collections().collections
            }
        except Exception:
            logger.exception("Unable to inspect Qdrant collections; preserving existing data.")
            return None

    def _sync_vault_chunks(
        self,
        current_files: Dict[str, float],
        is_fresh: bool,
        silent: bool,
    ) -> None:
        changed, deleted = detect_file_changes(current_files, self.file_mtimes)

        if not is_fresh and not changed and not deleted:
            self._load_chunks_if_needed()
            if not silent:
                print(f"⚡ [Memory Manager] Memori siap (Cache sinkron): {len(self.all_chunks)} potongan catatan.")
            return

        new_chunks, self.all_chunks = extract_and_update_chunks(changed, deleted, self.all_chunks)

        if changed or deleted:
            self.store.delete_documents_by_sources(changed + deleted)

        if new_chunks:
            self.store.add_documents_with_unique_ids(new_chunks)

        self.file_mtimes = current_files
        save_mtimes(self.cache_path, self.file_mtimes)

        if not silent:
            print(f"✅ [Memory Manager] Memori aktif: {len(self.all_chunks)} potongan catatan.")

    def search_context(self, query: str, k: int = 6) -> str:
        """
        Pencarian cerdas dan hemat komputasi:
        1. Pencarian awal langsung via Semantic Vector + Keyword RRF (Cepat - 0 ms overhead).
        2. Adaptive Query Expansion: lewati ekspansi jika hasil keyword menemukan
           catatan yang disebut eksplisit; pertahankan ekspansi saat hasil awal lemah.
        """
        if not query or not query.strip():
            return ""

        total_started = time.perf_counter()
        if self.needs_sync:
            self.index_vault(silent=True)
            self.needs_sync = False

        vector_started = time.perf_counter()
        vector_results, vector_search_failed = self._search_vectors(query, k)
        log_stage(logger, "retrieval", "vector_search", vector_started)
        keyword_started = time.perf_counter()
        keyword_results = get_ranked_keyword_results(self.all_chunks, query)
        log_stage(
            logger,
            "retrieval",
            "keyword_search",
            keyword_started,
            chunks=len(self.all_chunks),
        )

        explicit_source_match = _has_explicit_keyword_source_match(query, keyword_results)
        if (
            not vector_search_failed
            and not explicit_source_match
            and len(vector_results) < 3
            and len(keyword_results) < 2
        ):
            expansion_started = time.perf_counter()
            vector_results = self._expand_vector_search(
                query,
                vector_results,
                k,
            )
            log_stage(logger, "retrieval", "query_expansion", expansion_started)
        elif explicit_source_match:
            logger.debug("Skipping query expansion because the query names a retrieved Vault note.")

        top_seed = vector_results[:3] + keyword_results[:2]
        graph_started = time.perf_counter()
        graph_results = traverse_graph_links(top_seed, max_hops=1, max_linked_docs=3)
        log_stage(
            logger,
            "retrieval",
            "graph_retrieval",
            graph_started,
            seed_documents=len(top_seed),
            linked_documents=len(graph_results),
        )
        formatting_started = time.perf_counter()
        context = combine_search_results(
            vector_results,
            keyword_results,
            graph_results=graph_results,
            max_total=8,
        )
        log_stage(
            logger,
            "retrieval",
            "result_formatting",
            formatting_started,
            context_chars=len(context),
        )
        log_stage(
            logger,
            "retrieval",
            "total",
            total_started,
            vector_results=len(vector_results),
            keyword_results=len(keyword_results),
        )
        if vector_search_failed:
            warning = (
                "⚠️ Semantic retrieval is unavailable for this request; "
                "results below, if any, use keyword/graph retrieval only."
            )
            return f"{warning}\n\n{context}" if context else warning
        return context

    def _search_vectors(self, query: str, k: int) -> Tuple[List[Document], bool]:
        try:
            return self.store.similarity_search(query, k=k), False
        except Exception:
            logger.exception("Semantic retrieval unavailable; continuing with lexical/graph search.")
            return [], True

    def _expand_vector_search(
        self,
        query: str,
        initial_results: List[Document],
        k: int,
    ) -> List[Document]:
        ranked_results = [initial_results]
        seen_queries = {query.casefold()}
        for alternate_query in expand_query(query)[1:]:
            normalized_query = alternate_query.strip()
            if not normalized_query or normalized_query.casefold() in seen_queries:
                continue
            seen_queries.add(normalized_query.casefold())
            try:
                ranked_results.append(self.store.similarity_search(alternate_query, k=3))
            except Exception:
                logger.exception("Expanded semantic retrieval failed.")
        return merge_ranked_results(ranked_results, max_total=k)
