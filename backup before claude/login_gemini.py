"""
login_gemini.py:
Skrip utilitas 1-klik untuk melakukan Login ke Akun Google sekali saja.
Sesi login akan disimpan secara permanen di db/gemini_browser_profile/
sehingga setiap kali Carl membuka browser Gemini di kemudian hari,
akun Google Anda sudah langsung aktif dan terhubung otomatis.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from agents.gemini_browser import GeminiBrowserSession, PROFILE_DIR


def main():
    print("=" * 60)
    print("🔑 SETUP LOGIN AKUN GOOGLE UNTUK CARL & GEMINI (HANYA 1X)")
    print("=" * 60)
    print(f"📁 Lokasi Penyimpanan Profil: {PROFILE_DIR}")
    print("\n⏳ Sedang membuka jendela browser Microsoft Edge...")

    session = GeminiBrowserSession(headless=False)
    try:
        session.start()
        print("\n✅ Jendela browser telah terbuka di layar Anda!")

        if session.check_login_status():
            print("\n🎉 Akun Google Anda sudah terdeteksi LOGIN dan aktif!")
            print("Anda sudah siap menggunakan Carl Les Privat & Diskusi Gemini.")
            input("\nTekan [ENTER] untuk menutup browser...")
            return

        print("\n👉 Silakan klik tombol 'Sign in' / 'Masuk' pada jendela browser tersebut,")
        print("   lalu login dengan email dan password Google Anda.")
        print("\n⏳ Menunggu Anda menyelesaikan login...")

        # Pantau status login secara otomatis
        logged_in = False
        for _ in range(120):  # Pantau hingga 4 menit
            time.sleep(2)
            if session.check_login_status():
                logged_in = True
                break

        if logged_in:
            print("\n🎉 SELAMAT! Akun Google Anda berhasil terhubung dan tersimpan permanen!")
            print("Sekarang Anda bisa menjalankan '/les' kapan saja tanpa perlu login lagi.")
        else:
            print("\nℹ️ Jika Anda sudah selesai login di browser, tekan [ENTER] di bawah ini:")
            input()
            print("✅ Sesi profil browser telah disimpan!")

    except Exception as e:
        print(f"\n❌ Terjadi kesalahan: {e}")
    finally:
        session.close()
        print("\n👋 Jendela browser ditutup. Sesi login telah diamankan.")


if __name__ == "__main__":
    main()

