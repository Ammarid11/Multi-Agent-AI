# tools/tool_browser.py
"""
Frontier J: Autonomous Web Browser Agent
Mengekstrak dan menjelajah halaman web dinamis, membersihkan noise/iklan,
mengonversi tabel HTML ke tabel Markdown resmi, dan mengarsipkan halaman web
menjadi catatan kaya wawasan di 03-Resources/Web/ di Obsidian Vault.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any
from bs4 import BeautifulSoup, Tag
import config
from core import vault_io
from core.netguard import safe_fetch, UnsafeURL
from tools.tool_web_search import web_search_structured


def _html_table_to_markdown(table: Tag) -> str:
    """Mengonversi tag HTML <table> menjadi tabel Markdown rapi."""
    rows = table.find_all("tr")
    if not rows:
        return ""

    md_lines = []
    headers = []
    
    # Periksa th di baris pertama atau thead
    th_elements = rows[0].find_all(["th", "td"])
    headers = [re.sub(r"\s+", " ", cell.get_text().strip()) for cell in th_elements]
    if not headers or all(h == "" for h in headers):
        headers = [f"Kolom {i+1}" for i in range(len(th_elements))]

    md_lines.append("| " + " | ".join(headers) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    # Baris isi
    start_idx = 1 if rows[0].find("th") or len(rows) > 1 else 0
    for r in rows[start_idx:]:
        cells = r.find_all(["td", "th"])
        cell_texts = [re.sub(r"\s+", " ", c.get_text().strip()).replace("|", "\\|") for c in cells]
        # Pad jika panjang tidak sama
        while len(cell_texts) < len(headers):
            cell_texts.append("")
        cell_texts = cell_texts[:len(headers)]
        if any(cell_texts):
            md_lines.append("| " + " | ".join(cell_texts) + " |")

    return "\n".join(md_lines) + "\n\n"


def fetch_and_clean_webpage(url: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Mengambil konten halaman web via headless engine dan mengekstrak teks bersih,
    tabel Markdown, heading, dan metadata.
    """
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        body, final_url = safe_fetch(url, timeout=timeout, max_bytes=2_000_000, headers=headers)
        html = body.decode("utf-8", errors="replace")
        url = final_url
    except UnsafeURL as e:
        return {"success": False, "error": f"URL ditolak demi keamanan ({e})", "url": url}
    except Exception as e:
        return {"success": False, "error": f"Gagal mengakses URL ({str(e)})", "url": url}

    soup = BeautifulSoup(html, "html.parser")

    # Ambil judul
    title = soup.title.string.strip() if soup.title and soup.title.string else "Web Snapshot"
    title = re.sub(r"\s+", " ", title)

    # Ambil meta description
    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag.get("content").strip()

    # Bersihkan elemen noise
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside", "svg", "button", "iframe"]):
        tag.decompose()

    # Ekstraksi tabel sebelum diuraikan
    tables_md = []
    for t in soup.find_all("table"):
        t_md = _html_table_to_markdown(t)
        if t_md:
            tables_md.append(t_md)
        t.decompose()

    # Ekstraksi teks utama dari elemen artikel / main / body
    content_root = soup.find("article") or soup.find("main") or soup.find("body") or soup
    raw_text = content_root.get_text(separator="\n")

    # Rapikan baris kosong berturut-turut
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]
    clean_lines = [l for l in lines if l]
    body_text = "\n\n".join(clean_lines[:120])[:16000]  # Batasi 120 paragraf / 16.000 karakter terbaik

    return {
        "success": True,
        "url": url,
        "title": title,
        "description": meta_desc,
        "body_text": body_text,
        "tables_md": tables_md
    }


def archive_web_page_to_vault(url: str, vault_path: str = config.VAULT_PATH) -> Dict[str, Any]:
    """Menjelajah web dan mengarsipkannya ke 03-Resources/Web/ di Obsidian Vault."""
    data = fetch_and_clean_webpage(url)
    if not data["success"]:
        return data

    clean_title = "".join(c for c in data["title"] if c.isalnum() or c in (" ", "-", "_")).strip()
    clean_title = " ".join(clean_title.split()[:8]) or "Web Note"

    vault = Path(vault_path)
    web_dir = vault / "03-Resources" / "Web"
    web_dir.mkdir(parents=True, exist_ok=True)

    filename = f"Web - {clean_title}.md"
    file_path = web_dir / filename

    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tables_section = ""
    if data["tables_md"]:
        tables_section = "## 📊 Data Tabel Halaman\n\n" + "\n".join(data["tables_md"]) + "\n---\n\n"

    desc_section = f"> **Ringkasan:** {data['description']}\n\n" if data["description"] else ""

    note_body = f"""---
title: {json.dumps(data['title'], ensure_ascii=False)}
url: {json.dumps(data['url'])}
captured: "{now_str}"
tags: ["web-capture", "browser-agent", "resources"]
trust: external_web
status: archived
---

# 🌐 {data['title']}
> **Sumber URL:** [{data['url']}]({data['url']})  
> **Ditangkap pada:** {now_str}

{desc_section}---

{tables_section}## 📄 Konten Halaman Web
{data['body_text']}

---
*Dianalisis dan diarsipkan otomatis oleh Carl Frontier J (Autonomous Web Browser Agent)*
"""

    try:
        vault_io.atomic_write(file_path, note_body)
        return {
            "success": True,
            "title": data["title"],
            "filename": filename,
            "file_path": str(file_path),
            "url": data["url"],
            "preview": data["body_text"][:300] + "..."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_browser_command(target: str) -> str:
    """Menangani perintah /browse di CLI dan Web chat."""
    target = target.strip()
    if not target:
        return "⚠️ Harap masukkan URL atau kata kunci pencarian. Contoh: `/browse https://kompas.com` atau `/browse perkembangan AI 2026`"

    # Jika bukan URL langsung, cari via DuckDuckGo
    url = target
    if not target.startswith("http://") and not target.startswith("https://") and "." not in target.split()[0]:
        _, search_results = web_search_structured(target, deep_read=False)
        if not search_results:
            return f"❌ Tidak dapat menemukan halaman web untuk '{target}'"
        url = search_results[0].get("url", "")
        if not url:
            return f"❌ Hasil pencarian untuk '{target}' tidak memiliki URL yang valid."

    res = archive_web_page_to_vault(url)
    if not res["success"]:
        return f"❌ Gagal menjelajah halaman web: {res.get('error')}"

    return (
        f"🌐 **[Frontier J: Autonomous Web Browser Agent]**\n"
        f"Halaman web berhasil dianalisis dan diarsipkan ke Vault!\n\n"
        f"- **Judul:** {res['title']}\n"
        f"- **URL:** {res['url']}\n"
        f"- **Arsip Obsidian:** `03-Resources/Web/{res['filename']}`\n\n"
        f"**Pratinjau Konten:**\n"
        f"{res['preview']}\n\n"
        f"📌 *Tabel data & teks utuh kini tersimpan rapi dan dapat ditautkan via `[[{res['filename'].replace('.md', '')}]]`.*"
    )
