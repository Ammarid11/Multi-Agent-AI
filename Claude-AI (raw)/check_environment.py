# check_environment.py
"""
Pengecekan otomatis dependensi Python dan Model AI Ollama.
Jika sudah ada, proses langsung dilewati (skip).
Jika belum ada, otomatis di-install/download.
"""
import sys
import subprocess
import urllib.request
import json

# Pastikan console Windows mendukung output UTF-8 / Emoji tanpa crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config



def check_python_packages():
    """Periksa apakah paket di requirements.txt sudah terinstall."""
    print("🔍 [1/3] Memeriksa dependensi Python...")
    required_packages = [
        "ollama", "qdrant_client", "langchain", "langchain_qdrant",
        "langchain_ollama", "rich", "watchdog", "duckduckgo_search"
    ]
    missing = []
    for pkg in required_packages:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"⚠️ Ditemukan paket yang belum terpasang: {', '.join(missing)}")
        print("⏳ Sedang menginstal dependensi dari requirements.txt...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print("✅ Dependensi Python selesai dipasang!")
    else:
        print("✅ Semua dependensi Python sudah terpasang. (Skipped)")


def check_ollama_service():
    """Periksa apakah server Ollama sedang berjalan."""
    print("🔍 [2/3] Memeriksa layanan Ollama...")
    try:
        with urllib.request.urlopen(f"{config.OLLAMA_HOST}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return [m.get("name") for m in data.get("models", [])]
    except Exception:
        print("❌ Layanan Ollama tidak terdeteksi aktif di localhost:11434!")
        print("💡 Silakan buka aplikasi Ollama terlebih dahulu.")
        return None


def check_and_pull_models(installed_models):
    """Periksa model di config.py, download hanya jika belum ada."""
    print("🔍 [3/3] Memeriksa ketersediaan model AI...")
    required_models = [
        config.MODEL_EMBEDDING,
        config.MODEL_WRITER,
        config.MODEL_REASONER,
        config.MODEL_CODER,
    ]

    # Bersihkan tag ':latest' untuk perbandingan yang akurat
    installed_normalized = set()
    for m in installed_models:
        installed_normalized.add(m)
        if ":" in m:
            base_name, tag = m.split(":", 1)
            if tag == "latest":
                installed_normalized.add(base_name)
        else:
            installed_normalized.add(f"{m}:latest")

    for model in required_models:
        # Cek apakah model ada di daftar
        is_installed = False
        for inst in installed_normalized:
            if model == inst or model.startswith(inst) or inst.startswith(model):
                is_installed = True
                break

        if is_installed:
            print(f" • Model '{model}': [Sudah Ada] ✅")
        else:
            print(f" • Model '{model}': [Belum Ada] ⏳ Sedang mendownload (ollama pull {model})...")
            try:
                subprocess.run(["ollama", "pull", model], check=True)
                print(f"   ✅ Selesai mengunduh model '{model}'!")
            except Exception as e:
                print(f"   ❌ Gagal mendownload model '{model}': {e}")


def main():
    check_python_packages()
    installed = check_ollama_service()
    if installed is not None:
        check_and_pull_models(installed)
    # Tandai bahwa setup awal sudah berhasil diselesaikan
    try:
        with open(".setup_done", "w", encoding="utf-8") as f:
            f.write("SETUP_COMPLETED")
    except Exception:
        pass

    print("\n🚀 Persiapan selesai! Memulai sistem Second Brain...\n" + "="*50 + "\n")


if __name__ == "__main__":
    main()
