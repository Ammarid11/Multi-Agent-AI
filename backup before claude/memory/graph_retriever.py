# memory/graph_retriever.py
"""
Graph RAG Engine: Menelusuri jaringan pengetahuan Obsidian via Wikilinks [[...]].
Menghubungkan catatan terkait secara asosiatif layaknya neuron otak manusia.
"""
import os
import re
from typing import List, Set
from langchain_core.documents import Document
from tools.tool_append import find_file_in_vault
import config
from memory.vault_scanner import is_indexable_note


def extract_wikilinks(text: str) -> List[str]:
    """Mengekstrak seluruh tautan [[Catatan]] dari teks markdown."""
    if not text:
        return []
    raw_links = re.findall(r'\[\[(.*?)\]\]', text)
    cleaned_links = []
    for link in raw_links:
        # Tangani format alias [[Target|Tampilan]] atau anchor [[Target#Section]]
        target = link.split('|')[0].split('#')[0].strip()
        if target and target.lower() not in ['catatan terkait', 'index', '_index']:
            cleaned_links.append(target)
    return list(dict.fromkeys(cleaned_links))  # Hilangkan duplikat sambil jaga urutan


def traverse_graph_links(
    seed_docs: List[Document],
    max_hops: int = 1,
    max_linked_docs: int = 3
) -> List[Document]:
    """
    Melakukan penelusuran graf 1-hop dari dokumen awal (seed).
    Membaca catatan yang ditautkan di dalam wikilinks dan mengembalikannya sebagai Document.
    """
    if not seed_docs:
        return []

    # Kumpulkan seluruh path dokumen awal agar tidak menarik duplikat
    seen_sources: Set[str] = {
        os.path.normpath(str(d.metadata.get('source', ''))).lower()
        for d in seed_docs
    }

    linked_docs: List[Document] = []

    for doc in seed_docs:
        links = extract_wikilinks(doc.page_content)
        for link_title in links:
            if len(linked_docs) >= max_linked_docs:
                break

            target_filename = link_title if link_title.endswith('.md') else f"{link_title}.md"
            target_path = find_file_in_vault(target_filename)

            norm_target = os.path.normpath(target_path).lower()
            if (
                not os.path.exists(target_path)
                or not is_indexable_note(target_path, config.VAULT_PATH)
                or norm_target in seen_sources
            ):
                continue

            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()

                if not content:
                    continue

                seen_sources.add(norm_target)
                base_name = os.path.splitext(os.path.basename(target_path))[0]

                # Ambil cuplikan terpenting (maksimal 600 karakter)
                snippet = content[:600] + ("..." if len(content) > 600 else "")
                linked_doc = Document(
                    page_content=f"🔗 [Terhubung via Wikilink [[{base_name}]]]:\n{snippet}",
                    metadata={
                        "source": target_path,
                        "is_graph_linked": True,
                        "linked_from": doc.metadata.get('source', '')
                    }
                )
                linked_docs.append(linked_doc)
            except Exception:
                continue

        if len(linked_docs) >= max_linked_docs:
            break

    return linked_docs
