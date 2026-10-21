# tools/confirm_actions.py
"""Eksekusi aksi tertunda setelah pengguna mengetik /confirm <kode>."""
from core.confirm import consume


def execute_confirmed(code: str) -> str:
    code = (code or "").strip()
    if not code:
        return "❌ Format: `/confirm <kode>`."
    action = consume(code)
    if not action:
        return "❌ Kode konfirmasi tidak dikenal atau sudah kedaluwarsa. Ulangi perintah awalnya."
    kind, payload = action["kind"], action["payload"]
    if kind == "delete":
        from tools.tool_delete import delete_file_confirmed
        return delete_file_confirmed(payload["rel"])
    if kind == "relocate":
        from tools.tool_relocate import relocate_content
        return relocate_content(**payload)
    if kind == "clean_all":
        from tools.tool_clean import clean_all_vault_files
        return clean_all_vault_files(apply=True)
    return f"❌ Jenis aksi tidak dikenal: {kind}"
