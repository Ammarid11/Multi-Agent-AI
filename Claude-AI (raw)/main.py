# main.py
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.table import Table

from memory_indexer import MemoryManager
from agents import AITeam, AgentRouter
from watcher import start_auto_sync
from setup_vault_folder import setup_folders
from scheduler import start_background_scheduler, stop_background_scheduler

console = Console()


def print_banner() -> None:
    """Menampilkan Banner Sambutan Modern dengan Kolom Sejajar Rapi (Rich Grid)."""
    # 1. Tabel Perintah Otonom Level 5
    grid_level5 = Table.grid(padding=(0, 1))
    grid_level5.add_column(style="bold magenta", min_width=32)
    grid_level5.add_column(style="dim", justify="center")
    grid_level5.add_column(style="white")

    grid_level5.add_row(" • /goal <tujuan>", ":", "Eksekusi Rangkaian Tugas Mandiri (ReAct Loop)")
    grid_level5.add_row(" • /council <topik>", ":", "Sidang Debat DeepSeek-R1 vs Coder vs Carl")
    grid_level5.add_row(" • /serendipity [topik]", ":", "Cross-Domain Discovery & Resonansi Ide (Eureka)")
    grid_level5.add_row(" • /bridge", ":", "Local Mobile Bridge (Wi-Fi QR Pairing dari HP)")
    grid_level5.add_row(" • /calendar [export|list]", ":", "Sinkronisasi Deadline & Ekspor Kalender .ics")
    grid_level5.add_row(" • /arxiv <topik>", ":", "Kurasi Makalah Ilmiah & Literature Notes Otomatis")
    grid_level5.add_row(" • /simulate <skenario>", ":", "Simulasi 10 Persona Pasar & Dampak Strategi (M)")
    grid_level5.add_row(" • /train_adapter", ":", "Distilasi Pengetahuan Vault & Dataset LoRA Q&A (N)")
    grid_level5.add_row(" • /galaxy", ":", "Galaksi Pengetahuan 3D (WebGL / Canvas View) (O)")
    grid_level5.add_row(" • /browse <url|kata-kunci>", ":", "Browser Agent: Jelajah & Arsipkan Halaman Web")
    grid_level5.add_row(" • /eval", ":", "Uji Akurasi Memori & Kalibrasi Anti-Drift (K)")
    grid_level5.add_row(" • /unlock <pass>", ":", "Buka Brankas Rahasia AES-256 (Zero-Knowledge)")
    grid_level5.add_row(" • /secure <judul> | <isi>", ":", "Simpan Catatan Rahasia Terenkripsi AES-256")
    grid_level5.add_row(" • /reveal <judul>", ":", "Dekripsi & Baca Catatan Rahasia dari Brankas")
    grid_level5.add_row(" • /canvas <topik>", ":", "Obsidian Visual Canvas & Mind Map Generator (.canvas)")
    grid_level5.add_row(" • /voice [teks]", ":", "Real-Time Natural Voice (Edge-TTS Indonesia)")
    grid_level5.add_row(" • /vision <file>", ":", "Multi-Modal Vision & Ekstraksi Dokumen PDF")
    grid_level5.add_row(" • /backup", ":", "Pencadangan Arsip 1-Klik & Windows Toast Notification")
    grid_level5.add_row(" • /briefing", ":", "Morning Strategic Briefing & Scan Deadline")
    grid_level5.add_row(" • /sentinel", ":", "Audit Kesehatan Vault (Orphan & Broken Links)")
    grid_level5.add_row(" • /rule <aturan> | /rules", ":", "Ajari AI SOP / Aturan Kerja Prosedural")
    grid_level5.add_row(" • /run <kode_python>", ":", "Sandbox Python Lokal & Self-Debugging")

    # 2. Tabel Perintah Agen Spesialis
    grid_agents = Table.grid(padding=(0, 1))
    grid_agents.add_column(style="bold yellow", min_width=32)
    grid_agents.add_column(style="dim", justify="center")
    grid_agents.add_column(style="white")

    grid_agents.add_row(" • /web <pencarian>", ":", "Cari Info & Riset Web Mendalam (Deep Reader)")
    grid_agents.add_row(" • /think <analisa>", ":", "Penalaran Kritis Berlapis (DeepSeek-R1)")
    grid_agents.add_row(" • /coder <soal>", ":", "Spesialis Pemrograman & Skrip Python")
    grid_agents.add_row(" • /sintesis [topik]", ":", "Hubungkan Ide & Knowledge Graph Catatan")

    # 3. Tabel Perintah Alat (Tools)
    grid_tools = Table.grid(padding=(0, 1))
    grid_tools.add_column(style="bold cyan", min_width=32)
    grid_tools.add_column(style="dim", justify="center")
    grid_tools.add_column(style="white")

    grid_tools.add_row(" • /read <file>", ":", "Baca isi catatan di Vault")
    grid_tools.add_row(" • /write <file> | <isi>", ":", "Buat file catatan baru di Vault")
    grid_tools.add_row(" • /append <target> | <isi>", ":", "Tambah / perbarui isi catatan di Vault")
    grid_tools.add_row(" • /clean [file/folder]", ":", "Audit, perbaiki format & struktur folder")

    # 4. Gabungkan dalam Layout Utama
    main_layout = Table.grid(padding=(1, 0))
    main_layout.add_row("[bold cyan]🧠 SECOND BRAIN AI (LEVEL 5 COGNITIVE OPERATING SYSTEM)[/bold cyan]\n[dim]Sidecar Web UI at http://localhost:8000 | Heartbeat Scheduler Active[/dim]")
    main_layout.add_row("[bold magenta]🚀 Fitur Otonom Level 5 & Kognitif:[/bold magenta]")
    main_layout.add_row(grid_level5)
    main_layout.add_row("[bold green]🤖 Agen Spesialis & Pengetahuan:[/bold green]")
    main_layout.add_row(grid_agents)
    main_layout.add_row("[bold green]🛠️ Perintah Alat (Tools):[/bold green]")
    main_layout.add_row(grid_tools)
    main_layout.add_row("[dim]• Ketik '/help' untuk panduan lengkap | Ketik 'exit' atau 'quit' untuk keluar.[/dim]")

    console.print(Panel(main_layout, border_style="bright_blue", title="⚡ [bold white]Level 5 Omniscient Ready[/bold white]", title_align="left"))


def main() -> None:
    # 1. Setup Folder Vault
    setup_folders() 
    
    # 2. Inisialisasi Memori
    with console.status("[bold green]Menginisialisasi memori Obsidian...", spinner="dots"):
        memory_manager = MemoryManager()
        memory_manager.index_vault(silent=True)
    
    # 3. Jalankan Watcher & Heartbeat Scheduler Diam-Diam
    observer = start_auto_sync(memory_manager)
    start_background_scheduler()

    print_banner()

    # 4. Wajib Masukkan Nama Pengguna di Awal
    user_name = ""
    while not user_name.strip():
        user_name = Prompt.ask("\n[bold yellow]👤 Siapa nama Anda?[/bold yellow]")
    user_name = user_name.strip()

    console.print(f"[bold green]✨ Halo {user_name}! Carl dan tim Second Brain siap membantu Anda.[/bold green]")

    # 5. Inisialisasi Tim Agent & Router dengan Nama Pengguna
    ai_team = AITeam(memory_manager, user_name=user_name)
    router = AgentRouter(ai_team)

    try:
        while True:
            user_input = Prompt.ask(f"\n[bold cyan]{user_name}[/bold cyan]")
            
            if user_input.lower() in ['exit', 'quit']:
                console.print(f"\n[bold red]👋 Sampai jumpa, {user_name}! Mematikan sistem AI Second Brain...[/bold red]")
                observer.stop()
                stop_background_scheduler()
                break
                
            if not user_input.strip():
                continue

            with console.status("[bold yellow]🤖 Sedang memproses dan menghubungkan memori...[/bold yellow]", spinner="aesthetic"):
                jawaban = router.route_and_execute(user_input)

            console.print()
            console.print(Panel(
                Markdown(jawaban), 
                title="[bold green]🤖 Balasan AI[/bold green]", 
                border_style="bright_cyan",
                padding=(1, 2),
            ))
                
    except KeyboardInterrupt:
        console.print("\n[dim]Program dihentikan oleh pengguna.[/dim]")
        observer.stop()
        stop_background_scheduler()
    
    observer.join()


if __name__ == "__main__":
    main()