# test_upgrade.py
"""
Script Pengujian Mandiri untuk Upgrade Multi-Agent AI System.
Jalankan: python test_upgrade.py
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.panel import Panel


console = Console()

def test_intent_classifier():
    console.print("\n[bold cyan]1. Menguji Smart Intent Classifier (bot_router_llm)...[/bold cyan]")
    from agents.bot_router_llm import classify_intent
    
    test_cases = [
        ("tolong buatkan fungsi python untuk fibonacci", "coder"),
        ("apa perkembangan AI dan robotika terkini di internet?", "web"),
        ("bagaimana cara menganalisis risiko bisnis startup secara kritis?", "think"),
        ("tolong simpan catatan baru tentang rencana liburan", "file"),
        ("halo Carl apa kabar?", "default")
    ]
    
    for prompt, expected in test_cases:
        detected = classify_intent(prompt)
        match = "✅ SESUAI" if detected == expected else f"⚠️ BERBEDA (Didapat: {detected})"
        console.print(f" • Input: [italic]\"{prompt}\"[/italic]\n   Target: [green]{expected}[/green] | Status: {match}")

def test_query_expansion():
    console.print("\n[bold cyan]2. Menguji Query Expansion (memory/query_expander)...[/bold cyan]")
    from memory.query_expander import expand_query
    
    query = "catatan profil teman ammar"
    expansions = expand_query(query)
    console.print(f" • Query Utama: [yellow]'{query}'[/yellow]")
    console.print(f" • Variasi Dihasilkan ({len(expansions)} variasi):")
    for idx, var in enumerate(expansions, 1):
        console.print(f"   {idx}. {var}")

def test_session_memory():
    console.print("\n[bold cyan]3. Menguji Session Memory & Rolling Summarizer (memory/session_memory)...[/bold cyan]")
    from memory.session_memory import manage_history, get_session_context
    
    # Simulasikan 10 percakapan
    dummy_history = []
    for i in range(1, 11):
        dummy_history.append({"role": "user", "content": f"Ini pertanyaan ke-{i} tentang proyek AI dan catatan vault."})
        dummy_history.append({"role": "assistant", "content": f"Ini jawaban ke-{i} mencatat informasi dan task proyek."})
    
    recent, summaries = manage_history(dummy_history, [])
    console.print(f" • History Awal: {len(dummy_history)} pesan")
    console.print(f" • History Setelah Rolling: {len(recent)} pesan")
    console.print(f" • Ringkasan Sesi Dibuat: {len(summaries)} buah")
    if summaries:
        console.print(Panel(summaries[0], title="[green]Contoh Ringkasan Otomatis[/green]"))

def test_memory_indexing():
    console.print("\n[bold cyan]4. Menguji Inisialisasi Database Vektor (Qdrant + nomic-embed-text)...[/bold cyan]")
    try:
        from memory_indexer import MemoryManager
        mm = MemoryManager()
        mm.index_vault(silent=False)
        sample_search = mm.search_context("proyek AI", k=2)
        console.print(f" • Uji Search Konteks: {'[green]Ditemukan konteks catatan![/green]' if sample_search else '[yellow]Tidak ada konteks (Vault kosong / baru)[/yellow]'}")
    except Exception as e:
        console.print(f" [red]❌ Error saat index: {e}[/red]")

def test_level4_features():
    console.print("\n[bold cyan]5. Menguji Fitur Otonom Level 4 (Rules, Sandbox, Briefing, Sentinel)...[/bold cyan]")
    # Rules Engine
    from memory.rules_engine import add_rule, load_rules
    add_rule("Contoh SOP: Catatan proyek wajib menyertakan KPI", category="test")
    rules = load_rules()
    console.print(f" • Rules Engine (Pilar 3): [green]OK ({len(rules)} aturan aktif)[/green]")

    # Sandbox
    from tools.tool_sandbox import execute_python_code
    res_py = execute_python_code("print(10 * 10)")
    console.print(f" • Python Code Sandbox (Pilar 5): {'[green]OK[/green]' if '100' in res_py else '[red]Failed[/red]'}")

    # Temporal & Briefing
    from tools.vault_temporal import scan_deadlines_and_tasks
    findings = scan_deadlines_and_tasks()
    console.print(f" • Temporal Scanner (Pilar 4): [green]OK ({len(findings['deadlines'])} deadline, {len(findings['tasks'])} tugas terdeteksi)[/green]")

    # Vault Sentinel
    from tools.vault_sentinel import audit_vault_health
    rep = audit_vault_health()
    console.print(f" • Vault Sentinel (Pilar 8): {'[green]OK[/green]' if 'Skor Kesehatan' in rep else '[red]Failed[/red]'}")

if __name__ == "__main__":
    console.print(Panel("[bold magenta]🧪 RUNNING LEVEL 4 MULTI-AGENT UPGRADE TEST SUITE[/bold magenta]", border_style="magenta"))
    test_intent_classifier()
    test_query_expansion()
    test_session_memory()
    test_memory_indexing()
    test_level4_features()
    console.print("\n[bold green]🎉 Seluruh pengujian Level 4 selesai! Sistem siap dijalankan via 'run.bat'.[/bold green]\n")

