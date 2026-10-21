import re
from pathlib import Path

import config


def _workspace() -> Path:
    return Path(config.WORKSPACE_PATH).resolve()


def create_python_file(file_name: str, code_content: str) -> str:
    """Membuat file Python (.py) baru di folder kerja Carl (bukan di path sembarang).
    Gunakan tool ini saat user meminta untuk menyimpan atau membuat script/tool Python.
    """
    try:
        name = Path(str(file_name).replace("\\", "/")).name          # buang semua komponen direktori
        if not name.endswith(".py"):
            name += ".py"
        if not re.fullmatch(r"[\w\-. ]{1,80}\.py", name):
            return "Gagal membuat file Python: nama berkas tidak valid."

        cleaned_code = code_content.strip()
        if cleaned_code.startswith("```python"):
            cleaned_code = cleaned_code[9:]
        if cleaned_code.startswith("```"):
            cleaned_code = cleaned_code[3:]
        if cleaned_code.endswith("```"):
            cleaned_code = cleaned_code[:-3]
        cleaned_code = cleaned_code.strip()

        workspace = _workspace()
        workspace.mkdir(parents=True, exist_ok=True)
        target = (workspace / name).resolve()
        if workspace not in target.parents:
            return "Gagal membuat file Python: path di luar folder kerja."
        if target.exists():
            return f"File '{name}' sudah ada di folder kerja; gunakan nama lain agar tidak menimpa."

        target.write_text(cleaned_code, encoding="utf-8")
        return f"Berhasil membuat file Python di '{target}'."
    except Exception as e:
        return f"Gagal membuat file Python: {str(e)}"
