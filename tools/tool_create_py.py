import os


def create_python_file(file_name: str, code_content: str) -> str:
    """Membuat atau menulis file Python (.py) baru dengan isi kode yang diberikan.
    Gunakan tool ini saat user meminta untuk menyimpan atau membuat script/tool Python.
    """
    try:
        # 1. Pastikan nama file berakhiran .py
        if not file_name.endswith('.py'):
            file_name += '.py'
            
        # 2. Bersihkan tag markdown ```python ... ``` jika AI tidak sengaja menyertakannya
        cleaned_code = code_content.strip()
        if cleaned_code.startswith("```python"):
            cleaned_code = cleaned_code[9:]
        if cleaned_code.startswith("```"):
            cleaned_code = cleaned_code[3:]
        if cleaned_code.endswith("```"):
            cleaned_code = cleaned_code[:-3]
        cleaned_code = cleaned_code.strip()

        # 3. Tulis kode ke file
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(cleaned_code)

        return f"Berhasil membuat file Python di '{file_name}'."
    except Exception as e:
        return f"Gagal membuat file Python: {str(e)}"