# tools/vault_sentinel.py
"""
Autonomous Vault Sentinel (Pilar 8 Level 4 AI):
Dokter perawat kesehatan Vault Obsidian:
Mendeteksi broken links, orphan notes (catatan terisolasi), dan integritas struktur.
"""
import os
import re
import glob
from typing import Dict, List, Set
import config
from core import vault_io


def audit_vault_health() -> str:
    """Melakukan audit kesehatan lengkap terhadap seluruh catatan di Vault."""
    if not os.path.exists(config.VAULT_PATH):
        return "❌ Folder Vault tidak ditemukan."

    all_files: Dict[str, str] = {}  # base_name_lower -> full_path
    outgoing_links: Dict[str, List[str]] = {}
    incoming_links: Dict[str, int] = {}
    missing_frontmatter: List[str] = []
    broken_links: List[Dict[str, str]] = []

    ATTACHMENT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".pdf", ".canvas", ".mp3", ".wav", ".mp4", ".zip"}
    all_physical_files: Set[str] = set()

    # 1. Kumpulkan seluruh file di vault
    for filepath in glob.glob(os.path.join(config.VAULT_PATH, "**", "*"), recursive=True):
        if not os.path.isfile(filepath):
            continue
        fname_lower = os.path.basename(filepath).lower()
        all_physical_files.add(fname_lower)
        norm = filepath.replace("\\", "/").lower()
        if "07-settings" in norm or fname_lower.startswith((".", "_")) or vault_io.is_blocked_path(filepath):
            continue
        if fname_lower.endswith(".md"):
            base = os.path.splitext(fname_lower)[0]
            all_files[base] = filepath
            incoming_links[base] = 0

    # 2. Pindai isi file dan ekstrak wikilinks
    for base, fpath in all_files.items():
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.startswith("---"):
                missing_frontmatter.append(os.path.basename(fpath))

            # Ekstrak wikilinks (termasuk deteksi embed ![[...]])
            links = re.findall(r'(!?\[\[(.*?)\]\])', content)
            file_links = []
            for full_tag, raw_link in links:
                raw_clean = raw_link.strip()
                # Abaikan internal heading anchor dalam catatan yang sama (misal [[#Ringkasan]])
                if raw_clean.startswith("#"):
                    continue

                target = raw_clean.split('|')[0].split('#')[0].strip().lower()
                if not target:
                    continue

                # Periksa apakah ini lampiran media/canvas/pdf
                ext = os.path.splitext(target)[1]
                if ext in ATTACHMENT_EXTS:
                    if target in all_physical_files:
                        continue  # File lampiran ada secara fisik, bukan tautan rusak
                    else:
                        broken_links.append({
                            "source": os.path.basename(fpath),
                            "missing_target": raw_link
                        })
                        continue

                file_links.append(target)
                if target in all_files:
                    incoming_links[target] = incoming_links.get(target, 0) + 1
                else:
                    # Broken Link (target tidak ditemukan di vault)
                    broken_links.append({
                        "source": os.path.basename(fpath),
                        "missing_target": raw_link
                    })
            outgoing_links[base] = file_links
        except Exception:
            continue

    # 3. Hitung Orphan Notes (tidak ada incoming link dan tidak ada outgoing link)
    orphan_notes = [
        os.path.basename(all_files[b])
        for b in all_files
        if incoming_links.get(b, 0) == 0 and len(outgoing_links.get(b, [])) == 0
    ]

    total_notes = len(all_files)
    # Hitung Skor Kesehatan (0-100)
    penalties = (len(broken_links) * 2) + (len(orphan_notes) * 1) + (len(missing_frontmatter) * 0.5)
    health_score = max(50, int(100 - penalties)) if total_notes > 0 else 100

    report = [
        "### 🩺 Laporan Kesehatan Vault (Autonomous Vault Sentinel)\n",
        f"📊 **Skor Kesehatan Vault:** `{health_score}/100` ({'Sangat Sehat 🟢' if health_score >= 85 else 'Perlu Perawatan 🟡'})",
        f"📁 **Total Catatan Aktif:** {total_notes} berkas\n"
    ]

    # Broken Links
    report.append("🔗 **Tautan Rusak (Broken Links Terdeteksi):**")
    if broken_links:
        for bl in broken_links[:5]:
            report.append(f"- ⚠️ Di `{bl['source']}`: Tautan `[[{bl['missing_target']}]]` tidak memiliki berkas fisik.")
        if len(broken_links) > 5:
            report.append(f"  *(dan {len(broken_links) - 5} tautan rusak lainnya)*")
    else:
        report.append("- ✅ *Semua tautan [[...]] memiliki berkas target yang valid.*")

    report.append("")

    # Orphan Notes
    report.append("🏝️ **Catatan Terisolasi (Orphan Notes):**")
    if orphan_notes:
        for on in orphan_notes[:5]:
            report.append(f"- 📌 `{on}` (belum terhubung ke catatan mana pun)")
        if len(orphan_notes) > 5:
            report.append(f"  *(dan {len(orphan_notes) - 5} catatan terisolasi lainnya)*")
    else:
        report.append("- ✅ *Seluruh catatan saling terhubung dengan baik ke jejaring ide.*")

    report.append("")

    # Frontmatter
    report.append("📋 **Kepatuhan Format Frontmatter YAML:**")
    if missing_frontmatter:
        report.append(f"- ⚠️ {len(missing_frontmatter)} berkas belum memiliki Frontmatter YAML. (Contoh: `{missing_frontmatter[0]}`)")
        report.append("  *(Gunakan perintah `/clean <nama_file>` untuk melengkapi otomatis)*")

    if broken_links or orphan_notes or missing_frontmatter:
        report.append("")
        report.append("---")
        report.append("💡 **Tindakan Otomatis 1-Klik:**")
        report.append("[🩺 Sembuhkan & Bersihkan Semua Masalah Sekarang](/heal)")

    return "\n".join(report)


def heal_vault() -> str:
    """
    Auto-Heal: Menyembuhkan secara tepat seluruh masalah yang terdeteksi pada Sentinel:
    1. Melengkapi Frontmatter YAML pada berkas yang belum memilikinya.
    2. Menghubungkan seluruh Orphan Notes ke Master Index & menambahkan backlink.
    3. Memperbaiki broken links (membersihkan tautan mati di Master Index dan catatan lainnya).
    """
    if not os.path.exists(config.VAULT_PATH):
        return "❌ Folder Vault tidak ditemukan."

    from datetime import datetime

    all_files: Dict[str, str] = {}
    missing_frontmatter: List[str] = []
    broken_links: List[Dict[str, str]] = []
    outgoing_links: Dict[str, List[str]] = {}
    incoming_links: Dict[str, int] = {}

    ATTACHMENT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".pdf", ".canvas", ".mp3", ".wav", ".mp4", ".zip"}
    all_physical_files: Set[str] = set()

    for filepath in glob.glob(os.path.join(config.VAULT_PATH, "**", "*"), recursive=True):
        if not os.path.isfile(filepath):
            continue
        fname_lower = os.path.basename(filepath).lower()
        all_physical_files.add(fname_lower)
        norm = filepath.replace("\\", "/").lower()
        if "07-settings" in norm or fname_lower.startswith((".", "_")) or vault_io.is_blocked_path(filepath):
            continue
        if fname_lower.endswith(".md"):
            base = os.path.splitext(fname_lower)[0]
            all_files[base] = filepath
            incoming_links[base] = 0

    for base, fpath in all_files.items():
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.startswith("---"):
                missing_frontmatter.append(fpath)

            links = re.findall(r'(!?\[\[(.*?)\]\])', content)
            file_links = []
            for full_tag, raw_link in links:
                raw_clean = raw_link.strip()
                if raw_clean.startswith("#"):
                    continue

                target = raw_clean.split('|')[0].split('#')[0].strip().lower()
                if not target:
                    continue

                ext = os.path.splitext(target)[1]
                if ext in ATTACHMENT_EXTS:
                    if target in all_physical_files:
                        continue
                    else:
                        broken_links.append({
                            "file_path": fpath,
                            "raw_link": raw_link,
                            "target": target
                        })
                        continue

                file_links.append(target)
                if target in all_files:
                    incoming_links[target] = incoming_links.get(target, 0) + 1
                else:
                    broken_links.append({
                        "file_path": fpath,
                        "raw_link": raw_link,
                        "target": target
                    })
            outgoing_links[base] = file_links
        except Exception:
            continue

    orphan_notes = [
        all_files[b]
        for b in all_files
        if incoming_links.get(b, 0) == 0 and len(outgoing_links.get(b, [])) == 0
    ]

    # --- 1. Sembuhkan Frontmatter YAML ---
    healed_frontmatter_count = 0
    for fpath in missing_frontmatter:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                c = f.read()
            mtime = os.path.getmtime(fpath)
            created_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            rel_folder = os.path.relpath(os.path.dirname(fpath), config.VAULT_PATH).lower()
            tag = "catatan"
            if "project" in rel_folder: tag = "proyek"
            elif "area" in rel_folder: tag = "area"
            elif "resource" in rel_folder: tag = "referensi"
            elif "pemrograman" in rel_folder: tag = "coding"
            elif "daily" in rel_folder: tag = "daily"

            new_c = f"---\ncreated: {created_str}\ntype: note\ntags:\n  - {tag}\n---\n\n" + c
            vault_io.atomic_write(fpath, new_c)
            healed_frontmatter_count += 1
        except Exception:
            pass

    # --- 2. Sembuhkan Orphan Notes ---
    healed_orphan_count = 0
    master_index_path = os.path.join(config.VAULT_PATH, "Master Index - Brain AI Memory.md")
    master_links_to_add = []

    for fpath in orphan_notes:
        try:
            fname = os.path.basename(fpath)
            note_title = os.path.splitext(fname)[0]
            with open(fpath, 'r', encoding='utf-8') as f:
                c = f.read()

            if "[[Master Index" not in c:
                c += f"\n\n## 🔗 Referensi Indeks\n- Terhubung ke [[Master Index - Brain AI Memory]]\n"
                vault_io.atomic_write(fpath, c)

            master_links_to_add.append(f"- [[{note_title}]]")
            healed_orphan_count += 1
        except Exception:
            pass

    # Tambahkan orphan links ke Master Index
    if master_links_to_add and os.path.exists(master_index_path):
        try:
            with open(master_index_path, 'r', encoding='utf-8') as f:
                mi_content = f.read()
            if "## 📌 Indeks Catatan Terintegrasi" not in mi_content:
                mi_content += "\n\n## 📌 Indeks Catatan Terintegrasi\n"
            for link in master_links_to_add:
                if link not in mi_content:
                    mi_content += f"{link}\n"
            vault_io.atomic_write(master_index_path, mi_content)
        except Exception:
            pass

    # --- 3. Sembuhkan Broken Links ---
    # Netralkan broken links: ubah [[non_existent|alias]] -> alias dan [[non_existent]] -> non_existent
    healed_links_count = 0
    files_to_heal = set(item["file_path"] for item in broken_links)
    for fpath in files_to_heal:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                c = f.read()

            def _clean_link(match):
                nonlocal healed_links_count
                full_tag = match.group(1)
                raw = match.group(2)
                raw_clean = raw.strip()
                if raw_clean.startswith("#"):
                    return full_tag  # Heading anchor internal

                target = raw_clean.split('|')[0].split('#')[0].strip().lower()
                # Jika target adalah catatan .md atau file fisik lampiran, pertahankan
                if target in all_files or target in all_physical_files:
                    return full_tag

                # Jika embed gambar/media, pertahankan agar tidak merusak format markdown
                if full_tag.startswith("!"):
                    return full_tag

                healed_links_count += 1
                # Jika ada alias [[target|alias]], pakai alias
                if '|' in raw:
                    return raw.split('|', 1)[1].strip()
                return raw.strip()

            new_c = re.sub(r'(!?\[\[(.*?)\]\])', _clean_link, c)
            if new_c != c:
                vault_io.atomic_write(fpath, new_c)
        except Exception:
            pass

    return (
        f"🩺 **Auto-Heal Sentinel Selesai! Seluruh Masalah Berhasil Dirapikan:**\n\n"
        f"- 📋 **Frontmatter YAML:** {healed_frontmatter_count} berkas berhasil dilengkapi metadata baku.\n"
        f"- 🏝️ **Catatan Terisolasi (Orphans):** {healed_orphan_count} catatan berhasil disambungkan ke Master Index.\n"
        f"- 🔗 **Tautan Rusak (Broken Links):** {healed_links_count} tautan mati berhasil dinetralkan menjadi teks bersih.\n\n"
        f"*Ketik `/sentinel` kembali untuk melihat skor kesehatan Vault Anda yang baru!*"
    )


