# memory/serendipity.py
"""
Frontier G: Serendipity Engine & Cross-Domain Discovery
Menemukan korelasi dan resonansi ide tersembunyi lintas domain (terutama antara 03-Resources dan 01-Projects)
yang belum terhubung secara eksplisit via Wikilinks, memicu momen 'Eureka' untuk terobosan kreatif.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import config
from memory.vault_scanner import is_indexable_note
from tools.tool_append import find_file_in_vault
from memory.graph_retriever import extract_wikilinks


def _clean_markdown_text(content: str) -> str:
    """Membersihkan YAML frontmatter dan karakter khusus untuk analisis semantik."""
    # Hapus YAML frontmatter
    text = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    # Hapus format markdown berlebih
    text = re.sub(r"[#*`>_-]", " ", text)
    return " ".join(text.split())


def _extract_domain_notes(vault_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Mengelompokkan catatan di vault ke dalam domain fungsional:
    - projects: Catatan di 01-Projects atau berkas rencana/proyek
    - resources: Catatan di 03-Resources atau referensi/buku/literatur
    - areas: Catatan di 02-Areas
    - others: Catatan lainnya di vault
    """
    domains: Dict[str, List[Dict[str, Any]]] = {
        "projects": [],
        "resources": [],
        "areas": [],
        "others": []
    }

    vault = Path(vault_path)
    if not vault.exists():
        return domains

    for md_file in vault.rglob("*.md"):
        # Abaikan template dan trash
        rel_str = str(md_file.relative_to(vault)).replace("\\", "/")
        if not is_indexable_note(str(md_file), str(vault)):
            continue

        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        item = {
            "title": md_file.stem,
            "filename": md_file.name,
            "path": str(md_file),
            "rel_path": rel_str,
            "content": content,
            "clean_text": _clean_markdown_text(content),
            "links": set(extract_wikilinks(content))
        }

        if "01-Projects" in rel_str or "proyek" in rel_str.lower() or "project" in rel_str.lower():
            domains["projects"].append(item)
        elif "03-Resources" in rel_str or "resource" in rel_str.lower() or "referensi" in rel_str.lower() or "buku" in rel_str.lower():
            domains["resources"].append(item)
        elif "02-Areas" in rel_str or "area" in rel_str.lower():
            domains["areas"].append(item)
        else:
            domains["others"].append(item)

    return domains


def _compute_jaccard_semantic_resonance(text_a: str, text_b: str) -> float:
    """Menghitung skor resonansi leksikal & konsep antara dua catatan."""
    words_a = {
        w.lower() for w in re.findall(r"\b[a-zA-Z0-9_-]{4,}\b", text_a)
        if w.lower() not in {"dengan", "untuk", "dalam", "adalah", "yang", "pada", "oleh", "bisa", "akan", "dari", "yang", "atau", "juga"}
    }
    words_b = {
        w.lower() for w in re.findall(r"\b[a-zA-Z0-9_-]{4,}\b", text_b)
        if w.lower() not in {"dengan", "untuk", "dalam", "adalah", "yang", "pada", "oleh", "bisa", "akan", "dari", "yang", "atau", "juga"}
    }

    if not words_a or not words_b:
        return 0.0

    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)
    return len(intersection) / len(union)


def discover_cross_domain_serendipity(
    target_query: Optional[str] = None,
    vault_path: str = config.VAULT_PATH,
    memory_manager=None,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Mendeteksi hubungan tersembunyi antara catatan Proyek dan Sumber Daya / Konsep lain.
    Memfilter pasangan yang SUDAH memiliki tautan langsung.
    """
    domain_map = _extract_domain_notes(vault_path)
    projects = domain_map["projects"]
    resources = domain_map["resources"] + domain_map["areas"] + domain_map["others"]

    if not projects:
        # Jika tidak ada folder 01-Projects, jadikan separuh catatan sebagai 'ide' dan separuh sebagai 'referensi'
        all_notes = []
        for lst in domain_map.values():
            all_notes.extend(lst)
        if len(all_notes) < 2:
            return []
        projects = all_notes[:len(all_notes)//2]
        resources = all_notes[len(all_notes)//2:]

    candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []

    # Filter target spesifik jika ada
    target_projects = projects
    if target_query and target_query.strip():
        q_lower = target_query.lower()
        matched = [p for p in projects if q_lower in p["title"].lower() or q_lower in p["clean_text"].lower()]
        if matched:
            target_projects = matched

    for proj in target_projects:
        proj_title = proj["title"]
        proj_links = proj["links"]

        for res in resources:
            res_title = res["title"]
            if proj_title == res_title:
                continue

            # Abaikan jika SUDAH terhubung (tidak serendipitous lagi)
            if res_title in proj_links or proj_title in res["links"]:
                continue

            # Hitung skor resonansi
            score = _compute_jaccard_semantic_resonance(proj["clean_text"], res["clean_text"])
            
            # Berikan bobot bonus jika ada kecocokan frase tema
            shared_tags = set(re.findall(r"#([a-zA-Z0-9_-]+)", proj["content"])).intersection(
                set(re.findall(r"#([a-zA-Z0-9_-]+)", res["content"]))
            )
            if shared_tags:
                score += 0.15 * len(shared_tags)

            if score > 0.02:  # Ambang batas relevansi minimum
                candidates.append((score, proj, res))

    # Urutkan berdasarkan skor tertinggi
    candidates.sort(key=lambda x: x[0], reverse=True)

    results = []
    seen_pairs = set()

    for score, proj, res in candidates[:top_k]:
        pair_key = tuple(sorted([proj["title"], res["title"]]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        results.append({
            "score": round(score, 3),
            "project_title": proj["title"],
            "project_path": proj["rel_path"],
            "resource_title": res["title"],
            "resource_path": res["rel_path"],
            "project_summary": proj["clean_text"][:220] + "..." if len(proj["clean_text"]) > 220 else proj["clean_text"],
            "resource_summary": res["clean_text"][:220] + "..." if len(res["clean_text"]) > 220 else res["clean_text"]
        })

    return results


def run_serendipity_command(query: str = "", memory_manager=None) -> str:
    """Menjalankan mesin Serendipity dan menghasilkan narasi penemuan ide kreatif."""
    results = discover_cross_domain_serendipity(
        target_query=query,
        vault_path=config.VAULT_PATH,
        memory_manager=memory_manager,
        top_k=3
    )

    if not results:
        return (
            "💡 **[Serendipity Engine]** Belum menemukan koneksi tersembunyi yang cukup kuat lintas folder.\n"
            "Pastikan Anda memiliki beberapa catatan di folder `01-Projects` dan referensi di `03-Resources`!"
        )

    lines = [
        "💡 **[Serendipity Engine & Cross-Domain Discovery]**",
        "Carl menganalisis topologi pengetahuan Vault Anda dan menemukan korelasi konsep tak terduga (*Eureka Moments*):\n"
    ]

    for idx, item in enumerate(results, 1):
        lines.append(f"### {idx}. Resonansi: [[{item['project_title']}]] ⚡ [[{item['resource_title']}]]")
        lines.append(f"- **Proyek Aktif:** `{item['project_path']}`")
        lines.append(f"- **Sumber Daya Terpendam:** `{item['resource_path']}`")
        lines.append(f"- **Tingkat Resonansi Konsep:** `{int(item['score'] * 100)}% Match`")
        lines.append(f"- **Konteks Proyek:** {item['project_summary']}")
        lines.append(f"- **Wawasan Referensi:** {item['resource_summary']}")
        lines.append(
            f"- **💡 Saran Terobosan:** Terapkan prinsip pada [[{item['resource_title']}]] "
            f"untuk mengoptimalkan strategi pada [[{item['project_title']}]].\n"
        )

    lines.append("---")
    lines.append("📌 *Tip: Klik tautan `[[Wikilinks]]` di atas untuk langsung menghubungkan kedua pemikiran ini di Obsidian!*")
    return "\n".join(lines)

