# memory/hybrid_search.py
"""Hybrid ranking with Reciprocal Rank Fusion and a lightweight lexical heuristic."""
import os
import re
from typing import List, Set, Tuple, Dict, Optional
from langchain_core.documents import Document

STOPWORDS = {
    'aku', 'saya', 'kamu', 'anda', 'ammar', 'tau', 'tahu', 'apa', 'siapa',
    'bagaimana', 'kenapa', 'mengapa', 'adalah', 'yang', 'dan', 'di', 'ke',
    'dari', 'ini', 'itu', 'dong', 'sih', 'kan', 'nya', 'juga', 'atau',
    'dengan', 'untuk', 'pada', 'dalam', 'oleh', 'akan', 'telah', 'sudah',
    'bisa', 'tidak', 'ada', 'itu', 'ini', 'jika', 'maka', 'tapi', 'namun'
}

RRF_K = 60  # Standar konstanta RRF (Cormack et al.)


def _document_key(doc: Document) -> Tuple[str, str]:
    return str(doc.metadata.get('source', '')), doc.page_content


def merge_ranked_results(
    result_lists: List[List[Document]],
    max_total: Optional[int] = None
) -> List[Document]:
    """Gabungkan beberapa ranking dengan RRF dan pertahankan satu entri per chunk."""
    rrf_scores: Dict[Tuple[str, str], float] = {}
    doc_map: Dict[Tuple[str, str], Document] = {}

    for ranked_docs in result_lists:
        for rank, doc in enumerate(ranked_docs, 1):
            key = _document_key(doc)
            doc_map[key] = doc
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (RRF_K + rank))

    sorted_keys = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
    if max_total is not None:
        sorted_keys = sorted_keys[:max_total]
    return [doc_map[key] for key in sorted_keys]


def _extract_keywords(query: str) -> List[str]:
    """Ekstrak kata kunci bermakna dari query."""
    return [
        word
        for word in re.findall(r"\w+", query.casefold(), flags=re.UNICODE)
        if len(word) > 2 and word not in STOPWORDS
    ]


def get_ranked_keyword_results(
    all_chunks: List[Document],
    query: str
) -> List[Document]:
    """
    Urutkan dokumen berdasarkan kecocokan kata kunci (heuristic, bukan BM25 penuh).
    Return: list Document terurut dari yang paling relevan.
    """
    keywords = _extract_keywords(query)
    if not all_chunks or not keywords:
        return []

    query_tokens = _extract_keywords(query)
    query_lower = " ".join(query_tokens)
    scored: List[Tuple[float, Document]] = []

    for chunk in all_chunks:
        text_tokens = set(
            re.findall(r"\w+", chunk.page_content.casefold(), flags=re.UNICODE)
        )
        kw_matches = sum(1 for kw in keywords if kw in text_tokens)
        if kw_matches == 0:
            continue

        normalized_text = " ".join(
            re.findall(r"\w+", chunk.page_content.casefold(), flags=re.UNICODE)
        )
        phrase_bonus = 2.0 if query_lower and query_lower in normalized_text else 0.0
        source_tokens = set(
            re.findall(
                r"\w+",
                os.path.basename(str(chunk.metadata.get('source', ''))).casefold(),
                flags=re.UNICODE,
            )
        )
        title_bonus = sum(1.0 for kw in keywords if kw in source_tokens)

        total_score = kw_matches + phrase_bonus + title_bonus
        scored.append((total_score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored]


def reciprocal_rank_fusion(
    vector_results: List[Document],
    keyword_results: List[Document],
    max_total: int = 8
) -> List[Document]:
    """
    Algoritma RRF (Reciprocal Rank Fusion):
    Score(d) = sum(1 / (RRF_K + rank))
    Menghilangkan dominasi skor absolut dan menghasilkan peringkat gabungan yang adil.
    """
    rrf_scores: Dict[Tuple[str, str], float] = {}
    doc_map: Dict[Tuple[str, str], Document] = {}

    # 1. Hitung skor rank dari Vector Search
    for rank, doc in enumerate(vector_results, 1):
        key = _document_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (RRF_K + rank))

    # 2. Hitung skor rank dari Keyword Search
    for rank, doc in enumerate(keyword_results, 1):
        key = _document_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (RRF_K + rank))

    # 3. Urutkan berdasarkan total skor RRF tertinggi
    sorted_keys = sorted(rrf_scores, key=rrf_scores.get, reverse=True)

    final_docs = [doc_map[k] for k in sorted_keys[:max_total]]
    return final_docs


def combine_search_results(
    vector_results: List[Document],
    keyword_results: List[Document],
    graph_results: Optional[List[Document]] = None,
    max_total: int = 8
) -> str:
    """Format hasil RRF dan asosiasi Graph RAG menjadi konteks catatan siap baca untuk AI."""
    final_docs = reciprocal_rank_fusion(vector_results, keyword_results, max_total=max_total)
    if not final_docs and not graph_results:
        return ""

    formatted = []
    for doc in final_docs:
        source = os.path.basename(str(doc.metadata.get('source', 'Catatan')))
        formatted.append(f"📄 [Sumber: {source}]\n{doc.page_content}")

    if graph_results:
        for g_doc in graph_results:
            source = os.path.basename(str(g_doc.metadata.get('source', 'Catatan Terhubung')))
            formatted.append(f"📄 [Sumber: {source}]\n{g_doc.page_content}")

    return "\n\n---\n\n".join(formatted)
