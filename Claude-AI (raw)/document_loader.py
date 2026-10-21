# memory/document_loader.py
import os
from typing import List
from langchain_core.documents import Document
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

HEADERS_TO_SPLIT = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]


def split_markdown_file(filepath: str) -> List[Document]:
    """Memuat dan memecah file markdown menjadi potongan (chunks) terstruktur."""
    try:
        norm_path = os.path.normpath(filepath)
        docs = TextLoader(norm_path, encoding='utf-8').load()
        if not docs:
            return []

        splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS_TO_SPLIT, strip_headers=False)
        all_splits: List[Document] = []
        for doc in docs:
            doc.metadata['source'] = norm_path
            for s in splitter.split_text(doc.page_content):
                s.metadata.update(doc.metadata)
                s.metadata['source'] = norm_path
                all_splits.append(s)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=60)
        return text_splitter.split_documents(all_splits)
    except Exception:
        return []
