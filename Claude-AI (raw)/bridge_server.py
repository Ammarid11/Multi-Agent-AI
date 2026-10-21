# bridge_server.py
"""
Frontier H: Local Multi-Device Mobile Bridge
Menghubungkan smartphone / tablet pada jaringan Wi-Fi lokal ke Carl Second Brain
melalui deteksi otomatis IP LAN, pembuatan QR Code pairing, dan Quick Mobile Memo Capture.
"""

import os
import socket
import io
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import qrcode
import config
from tools.tool_append import find_file_in_vault


def get_local_ip() -> str:
    """Mendeteksi IP LAN lokal (misal 192.168.x.x) dari mesin host secara aman, termasuk mode router offline."""
    # 1. Coba UDP probe keluar (jika ada rute default)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # 2. Fallback offline: Dapatkan hostname IP
    try:
        host_name = socket.gethostname()
        host_ip = socket.gethostbyname(host_name)
        if host_ip and not host_ip.startswith("127."):
            return host_ip
    except Exception:
        pass

    # 3. Fallback scan antarmuka getaddrinfo
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = info[4][0]
            if candidate and not candidate.startswith("127."):
                return candidate
    except Exception:
        pass

    return "127.0.0.1"


def generate_qr_ascii(url: str) -> str:
    """Menghasilkan representasi ASCII QR Code untuk terminal."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)

    f = io.StringIO()
    qr.print_ascii(out=f, invert=True)
    return f.getvalue()


def get_bridge_info(port: int = 8000) -> Dict[str, Any]:
    """Mengembalikan informasi jembatan koneksi mobile."""
    local_ip = get_local_ip()
    mobile_url = f"http://{local_ip}:{port}"
    localhost_url = f"http://127.0.0.1:{port}"
    
    return {
        "status": "active",
        "local_ip": local_ip,
        "port": port,
        "mobile_url": mobile_url,
        "localhost_url": localhost_url,
        "instructions": "Pastikan smartphone Anda terhubung ke jaringan Wi-Fi yang sama dengan PC ini, lalu scan QR code atau buka URL di browser HP."
    }


def save_quick_memo(
    content: str,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source: str = "Mobile Bridge"
) -> Dict[str, Any]:
    """
    Menyimpan memo kilat dari smartphone langsung ke 00-Inbox di Obsidian Vault.
    Lengkap dengan timestamp dan tag penanda.
    """
    if not content or not content.strip():
        return {"success": False, "error": "Konten memo tidak boleh kosong."}

    now = datetime.datetime.now()
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    date_code = now.strftime("%Y%m%d_%H%M%S")

    # Tentukan judul catatan
    if not title or not title.strip():
        # Ambil 5 kata pertama sebagai judul
        words = content.strip().split()
        short_title = " ".join(words[:5])
        clean_title = "".join(c for c in short_title if c.isalnum() or c in (" ", "-", "_")).strip()
        title = f"Memo {clean_title}" if clean_title else f"Quick Memo {date_code}"

    # Target folder: 00-Inbox
    vault = Path(config.VAULT_PATH)
    inbox_dir = vault / "00-Inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() + ".md"
    file_path = inbox_dir / safe_filename

    # Jika file sudah ada, tambahkan penanda waktu
    if file_path.exists():
        file_path = inbox_dir / f"{file_path.stem}_{date_code}.md"

    # Siapkan tag
    all_tags = ["quick-memo", "mobile-capture", "inbox"]
    if tags:
        for t in tags:
            clean_tag = t.strip("#").strip()
            if clean_tag and clean_tag not in all_tags:
                all_tags.append(clean_tag)
    tag_str = ", ".join(f'"{t}"' for t in all_tags)

    note_body = f"""---
title: "{title}"
created: {timestamp_str}
source: "{source}"
tags: [{tag_str}]
status: inbox
---

# 📱 {title}
> ⏱️ *Ditangkap via {source} pada {timestamp_str}*

{content.strip()}

---
## 🎯 Tindak Lanjut
- [ ] Tinjau dan proses memo ini ke folder proyek / area terkait.
"""

    try:
        file_path.write_text(note_body, encoding="utf-8")
        return {
            "success": True,
            "title": file_path.stem,
            "file_path": str(file_path),
            "filename": file_path.name,
            "created": timestamp_str
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_bridge_command(port: int = 8000) -> str:
    """Menampilkan informasi Mobile Bridge dan QR Code di chat/CLI."""
    info = get_bridge_info(port=port)
    ascii_qr = generate_qr_ascii(info["mobile_url"])

    lines = [
        "📱 **[Frontier H: Local Multi-Device Mobile Bridge]**",
        "Jembatan nirkabel lokal Carl Second Brain aktif!\n",
        f"🔗 **URL Akses Smartphone:** `{info['mobile_url']}`",
        f"💻 **URL Komputer Lokal:** `{info['localhost_url']}`",
        f"🌐 **IP Host PC:** `{info['local_ip']}`\n",
        "**Langkah Penggunaan:**",
        "1. Pastikan HP/Tablet Anda terhubung ke Wi-Fi yang sama dengan PC.",
        f"2. Buka browser HP dan ketik: **{info['mobile_url']}** atau scan QR Code di bawah:",
        "\n```text\n" + ascii_qr + "\n```\n",
        "💡 *Fitur Mobile Siap Pakai: Chat Suara/Teks, Audio Playback 🔊, dan tombol 'Memo Kilat' langsung ke 00-Inbox Vault!*"
    ]
    return "\n".join(lines)

