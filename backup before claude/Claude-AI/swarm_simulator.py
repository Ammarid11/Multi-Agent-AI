# agents/swarm_simulator.py
"""
Frontier M: Multi-Agent Swarm Simulation & Scenario Forecasting
Simulasi 10 persona otonom untuk meramalkan dampak keputusan bisnis/strategi.
Command: /simulate <rencana_atau_keputusan>
"""
import ollama
import config

# 10 persona otonom dengan karakter khas masing-masing
PERSONAS = [
    {"nama": "🔴 Kompetitor Agresif",     "peran": "Pesaing utama yang sedang menganalisis celah dan kelemahan rencana ini untuk memanfaatkannya"},
    {"nama": "😤 Konsumen Skeptis",        "peran": "Pelanggan potensial yang sangat kritis terhadap nilai, harga, dan klaim manfaat produk"},
    {"nama": "💰 Investor Konservatif",    "peran": "Investor yang mengevaluasi risiko finansial, ROI, dan viabilitas bisnis jangka panjang secara ketat"},
    {"nama": "📊 Analis Pasar",           "peran": "Analis data yang menilai potensi pasar, tren industri, dan proyeksi pertumbuhan berbasis data"},
    {"nama": "🚀 Early Adopter",          "peran": "Pengguna awal yang antusias, suka inovasi, dan memberikan umpan balik konstruktif tentang use case"},
    {"nama": "⚖️ Regulator/Hukum",        "peran": "Pejabat yang mengevaluasi aspek regulasi, izin usaha, kepatuhan hukum, dan risiko litigasi"},
    {"nama": "📰 Media/Jurnalis",          "peran": "Jurnalis yang mencari angle berita menarik, kontroversial, atau implikasi sosial dari rencana ini"},
    {"nama": "👷 Tim Internal",           "peran": "Karyawan senior yang menilai kelayakan eksekusi, beban kerja tim, dan risiko operasional internal"},
    {"nama": "🤝 Mitra Strategis",        "peran": "Calon mitra bisnis yang mengevaluasi peluang sinergi, kolaborasi, dan pembagian keuntungan"},
    {"nama": "😈 Devil's Advocate",       "peran": "Kritikus sistematis yang bertugas mencari semua skenario terburuk, asumsi yang salah, dan blind spot"},
]


def simulate_swarm(scenario: str) -> str:
    """
    Jalankan simulasi 10 persona terhadap skenario/keputusan yang diberikan.
    Setiap persona memberikan perspektif unik + 1 peluang + 1 risiko.
    """
    if not scenario.strip():
        return (
            "❌ **Format salah.** Masukkan skenario yang ingin disimulasikan.\n\n"
            "**Contoh:**\n"
            "- `/simulate Saya ingin meluncurkan aplikasi AI lokal berbasis langganan di 2026`\n"
            "- `/simulate Membuka toko online produk handmade dengan target ekspor Asia Tenggara`\n"
            "- `/simulate Merekrut 5 freelancer remote menggantikan 2 karyawan tetap`"
        )

    results = []
    results.append(f"### 👥 Laporan Simulasi Swarm Multi-Agen\n")
    results.append(f"**📋 Skenario:** _{scenario.strip()}_\n")
    results.append(f"**🤖 Agen Aktif:** {len(PERSONAS)} Persona Otonom\n")
    results.append("---\n")

    for i, persona in enumerate(PERSONAS, 1):
        prompt = (
            f"Kamu adalah seorang **{persona['nama']}**.\n"
            f"Peranmu: {persona['peran']}.\n\n"
            f"Seseorang baru saja mengajukan rencana berikut:\n"
            f"**\"{scenario.strip()}\"**\n\n"
            f"Berikan responmu yang singkat, jujur, dan langsung sebagai {persona['nama']} "
            f"dalam 2-3 kalimat Bahasa Indonesia. Wajib sertakan:\n"
            f"- 💡 Satu **peluang** dari sudut pandangmu\n"
            f"- ⚠️ Satu **risiko** atau kekhawatiran utamamu\n\n"
            f"Tulis langsung tanpa basa-basi."
        )
        try:
            resp = ollama.chat(
                model=config.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 150, "temperature": 0.75}
            )
            response_text = resp["message"]["content"].strip()
        except Exception as e:
            response_text = f"*(Agen tidak merespons: {e})*"

        results.append(f"**{i}. {persona['nama']}**")
        results.append(f"> {response_text}\n")

    # Executive Summary
    summary_prompt = (
        f"Kamu adalah fasilitator rapat strategis. Berdasarkan simulasi 10 persona "
        f"terhadap rencana: \"{scenario.strip()}\", "
        f"berikan **Ringkasan Eksekutif** dalam format ini:\n\n"
        f"**🎯 Peluang Terbesar:** (1 kalimat)\n"
        f"**🚨 Risiko Utama:** (1 kalimat)\n"
        f"**✅ Rekomendasi Strategis:** (2-3 kalimat actionable)\n"
        f"**📊 Estimasi Probabilitas Sukses:** (X% dengan alasan singkat)\n\n"
        f"Gunakan Bahasa Indonesia yang tegas dan langsung."
    )
    try:
        summary_resp = ollama.chat(
            model=config.OLLAMA_MODEL,
            messages=[{"role": "user", "content": summary_prompt}],
            options={"num_predict": 200, "temperature": 0.4}
        )
        summary = summary_resp["message"]["content"].strip()
    except Exception:
        summary = "*(Ringkasan eksekutif tidak tersedia)*"

    results.append("---")
    results.append("### 🎯 Ringkasan Eksekutif Simulasi\n")
    results.append(summary)
    results.append("\n---")
    results.append("*💡 Ketik `/simulate <skenario_baru>` untuk mensimulasikan strategi lainnya.*")

    return "\n".join(results)

