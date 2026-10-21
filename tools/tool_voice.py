# tools/tool_voice.py
"""
Frontier C: Real-Time Voice Interface (Telinga & Suara Carl).
Menyediakan Text-to-Speech (TTS) natural Bahasa Indonesia (Edge-TTS & Windows SAPI5)
serta Speech-to-Text (STT) lokal via microphone.
"""

import os
import sys
import re
import asyncio
import tempfile
import threading
from pathlib import Path
from typing import Optional, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Suara default: id-ID-ArdiNeural (Pria ramah dan profesional)
DEFAULT_VOICE = "id-ID-ArdiNeural"
ALT_VOICE = "id-ID-GadisNeural"


def clean_markdown_for_speech(text: str) -> str:
    """Membersihkan simbol markdown, kode, dan tautan agar terdengar alami saat diucapkan."""
    # Hapus blok kode
    clean = re.sub(r'```[\s\S]*?```', ' kode pemrograman dilewati ', text)
    # Hapus inline code
    clean = re.sub(r'`([^`]+)`', r'\1', clean)
    # Ubah wikilinks [[Target|Alias]] -> Alias atau [[Target]] -> Target
    clean = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', clean)
    # Hapus markdown link [Text](url) -> Text
    clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean)
    # Hapus header '#'
    clean = re.sub(r'#+\s*', '', clean)
    # Hapus tanda bintang formatting '**' atau '*'
    clean = re.sub(r'\*+([^*]+)\*+', r'\1', clean)
    # Hapus tanda checklist '- [ ]'
    clean = re.sub(r'-\s*\[[ xX]\]\s*', '', clean)
    # Hapus bullet points
    clean = re.sub(r'^\s*[-*+]\s+', '', clean, flags=re.MULTILINE)
    # Bersihkan baris berlebih
    clean = re.sub(r'\n+', '. ', clean)
    return clean.strip()


async def generate_edge_tts_audio_async(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> bool:
    """Mengonversi teks ke audio mp3 menggunakan edge-tts secara asinkron."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return True
    except Exception as e:
        print(f"[Voice Warning] Edge-TTS gagal: {e}")
        return False


def _play_audio_windows(audio_path: str):
    """Memutar berkas audio mp3/wav di background Windows menggunakan PowerShell."""
    try:
        ps_cmd = f"(New-Object Media.SoundPlayer '{audio_path}').PlaySync()"
        if audio_path.endswith('.mp3'):
            ps_cmd = f"""
            Add-Type -AssemblyName presentationCore
            $player = New-Object System.Windows.Media.MediaPlayer
            $player.Open([System.Uri]'{audio_path}')
            $player.Play()
            Start-Sleep -Seconds 4
            """
        os.system(f'powershell -NoProfile -Command "{ps_cmd}" > nul 2>&1')
    except Exception:
        pass


def speak_text(text: str, voice: str = DEFAULT_VOICE, play_sound: bool = True) -> Dict[str, Any]:
    """
    Mengucapkan teks dalam suara Bahasa Indonesia.
    Menggunakan Edge-TTS natural berkualitas tinggi, dengan fallback ke Windows SAPI5 jika offline.
    Aman dipanggil baik di thread biasa maupun di dalam event loop.
    """
    clean_text = clean_markdown_for_speech(text)
    if not clean_text:
        return {"success": False, "error": "Tidak ada teks untuk diucapkan."}

    # Batasi panjang ucapan jika terlalu panjang untuk performa
    if len(clean_text) > 600:
        clean_text = clean_text[:597] + "..."

    # Buat direktori cache audio
    cache_dir = PROJECT_ROOT / "web" / "audio_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_file = cache_dir / "carl_voice_local.mp3"

    success = False

    # Jalankan coroutine edge-tts di thread terpisah agar aman dari 'event loop already running'
    def _run_tts():
        nonlocal success
        try:
            success = asyncio.run(generate_edge_tts_audio_async(clean_text, str(audio_file), voice))
        except Exception as err:
            print(f"[Voice] Thread Edge-TTS error: {err}")

    t = threading.Thread(target=_run_tts)
    t.start()
    t.join(timeout=15)

    if audio_file.exists() and audio_file.stat().st_size > 0:
        success = True

    # Fallback offline Windows SAPI5 jika Edge-TTS gagal
    if not success:
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            if play_sound:
                threading.Thread(target=speaker.Speak, args=(clean_text,), daemon=True).start()
            return {
                "success": True,
                "engine": "Windows SAPI5 (Offline)",
                "spoken_text": clean_text
            }
        except Exception as e:
            return {"success": False, "error": f"Gagal menghasilkan suara: {e}"}

    if play_sound:
        threading.Thread(target=_play_audio_windows, args=(str(audio_file),), daemon=True).start()

    return {
        "success": True,
        "engine": "Edge-TTS Natural Indonesian",
        "audio_path": str(audio_file),
        "spoken_text": clean_text
    }


def listen_microphone(timeout: int = 5) -> Dict[str, Any]:
    """
    Mendengarkan ucapan pengguna melalui mikrofon lokal dan mengonversinya ke teks Bahasa Indonesia.
    """
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            print(f"\n🎙️ [Voice Input] Menyesuaikan kebisingan ruangan...")
            recognizer.adjust_for_ambient_noise(source, duration=0.8)
            print("🎙️ [Voice Input] Silakan berbicara (Bahasa Indonesia)...")
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=15)

        print("🧠 [Voice Input] Mengonversi suara ke teks...")
        text = recognizer.recognize_google(audio, language="id-ID")
        return {
            "success": True,
            "transcription": text
        }
    except Exception as e:
        err_msg = str(e)
        if "timed out" in err_msg.lower():
            err_msg = "Waktu habis: Tidak ada suara terdeteksi."
        elif "could not understand" in err_msg.lower() or "unknown" in err_msg.lower():
            err_msg = "Suara tidak terdengar jelas."
        return {
            "success": False,
            "error": err_msg
        }


def run_voice_command(prompt: str = "") -> str:
    """Wrapper untuk dieksekusi via slash command /voice atau /speak."""
    if prompt.strip():
        # Ucapkan teks yang diminta
        res = speak_text(prompt.strip())
        if res["success"]:
            return f"🔊 **Carl Berbicara:** \"{res['spoken_text']}\""
        return f"❌ Gagal memutar suara: {res.get('error')}"
    else:
        # Aktifkan mode mendengarkan mikrofon
        res = listen_microphone()
        if res["success"]:
            return f"🎙️ **Suara Terdeteksi:** \"{res['transcription']}\"\n\n*(Ketik atau kirim teks ini untuk bertanya pada Carl)*"
        return f"🎙️ ⚠️ {res.get('error', 'Gagal mendengarkan mikrofon')}"


if __name__ == "__main__":
    print("Menguji modul Suara Carl (Edge-TTS & SAPI5)...")
    res = speak_text("Halo! Saya Carl, asisten Second Brain Multi-Agent Anda. Suara saya sekarang aktif.", play_sound=False)
    print("Hasil TTS:", res)
