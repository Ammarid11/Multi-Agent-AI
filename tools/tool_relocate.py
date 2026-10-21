# tools/tool_relocate.py
import os
from typing import Optional

from core import vault_io
from tools.tool_append import append_file


def relocate_content(source_file: str, target_file: str, content_snippet: str, target_section: Optional[str] = None) -> str:
    """Memindahkan cuplikan teks antar catatan: SIMPAN dulu -> VERIFIKASI -> baru ubah sumber."""
    src_path, error = vault_io.resolve_write_path(source_file)
    if error:
        return f"❌ File asal: {error}"
    if not src_path.exists():
        return f"❌ File asal '{source_file}' tidak ditemukan!"
    tgt_path, error = vault_io.resolve_write_path(target_file)
    if error:
        return f"❌ File tujuan: {error}"

    try:
        src_text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        snippet = content_snippet.strip().replace("\r\n", "\n")
        if not snippet:
            return "❌ Cuplikan kosong; tidak ada yang dipindahkan."
        if src_text.count(snippet) != 1:
            return "❌ Cuplikan harus muncul tepat satu kali di file asal; tidak ada yang diubah."

        before = tgt_path.read_text(encoding="utf-8") if tgt_path.exists() else None

        # 1) simpan di tujuan
        result = append_file(str(tgt_path.relative_to(vault_io.vault_root()).as_posix()), snippet, section=target_section)

        # 2) verifikasi tujuan benar-benar berubah/berisi cuplikan
        if not tgt_path.exists():
            return f"❌ Gagal menyimpan ke tujuan; file asal tidak diubah.\n{result}"
        after = tgt_path.read_text(encoding="utf-8")
        changed = (after != before)
        if not changed or (target_section is None and snippet not in after.replace("\r\n", "\n")):
            return f"❌ Verifikasi tujuan gagal; file asal tidak diubah.\n{result}"

        # 3) baru ubah sumber (atomik + snapshot, bisa /undo)
        target_name = os.path.splitext(os.path.basename(str(tgt_path)))[0]
        vault_io.atomic_write(src_path, src_text.replace(snippet, f"*(Dipindahkan ke [[{target_name}]])*"))
        return f"🚚 Berhasil memindahkan materi ke '{os.path.basename(str(tgt_path))}'!"
    except Exception as e:
        return f"❌ Gagal memindahkan teks: {str(e)}"
