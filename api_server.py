# api_server.py
"""
Frontier A: Local API Server & Direct Obsidian Sidecar UI.
Menyediakan server API lokal berbasis FastAPI + Web Chat UI modern Dark Mode.
Carl dapat diakses langsung via browser (http://localhost:8000) atau
disematkan sebagai tab panel samping (sidecar) di dalam jendela Obsidian.
"""

import os
import sys
import math
import glob
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from config import VAULT_PATH, MODEL_WRITER, MODEL_REASONER, MODEL_CODER, OLLAMA_HOST
from memory_indexer import MemoryManager
from memory.vault_scanner import is_indexable_note
from agents import AITeam, AgentRouter
from agents.gemini_browser import request_stop_tutoring
from scheduler import start_background_scheduler, stop_background_scheduler

# Singleton global state
_memory_manager: Optional[MemoryManager] = None
_team: Optional[AITeam] = None
_router: Optional[AgentRouter] = None
SYSTEM_UNAVAILABLE_MESSAGE = "Sistem belum siap."
logger = logging.getLogger(__name__)


def unavailable_response() -> JSONResponse:
    """Menyediakan payload standar saat komponen AI belum siap."""
    return JSONResponse(
        status_code=503,
        content={
            "reply": SYSTEM_UNAVAILABLE_MESSAGE,
            "status": "error",
            "detail": SYSTEM_UNAVAILABLE_MESSAGE,
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Siklus hidup aplikasi: Inisialisasi memori, router, dan background scheduler."""
    global _memory_manager, _team, _router
    print("\n🚀 [Carl API Server] Memulai inisialisasi sistem...")
    try:
        _memory_manager = MemoryManager()
        _memory_manager.index_vault(silent=True)
    except Exception as e:
        print(f"[Warning] Gagal inisialisasi memory manager, menggunakan mode fallback: {e}")
        _memory_manager = None

    _team = AITeam(_memory_manager, user_name="Pengguna")
    _router = AgentRouter(_team)

    # Jalankan denyut waktu background scheduler (Frontier B)
    start_background_scheduler()
    print("✨ [Carl API Server] Sistem siap melayani di http://127.0.0.1:8000")

    yield

    # Shutdown
    print("\n🛑 [Carl API Server] Menghentikan background service...")
    stop_background_scheduler()


app = FastAPI(
    title="Carl - Obsidian Second Brain Cognitive API",
    version="5.0.0",
    lifespan=lifespan
)

# Izinkan CORS penuh agar dapat diakses dari Obsidian plugin (Custom Frames/Webview)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str


class CanvasRequest(BaseModel):
    topic: str


class QuickMemoRequest(BaseModel):
    content: str
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = "Mobile Bridge"


@app.get("/", response_class=FileResponse)
async def serve_ui():
    """Menyajikan Web Chat UI Dark Mode untuk Obsidian Sidecar."""
    html_path = PROJECT_ROOT / "web" / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return HTMLResponse("<h2>UI index.html belum ditemukan di folder web/.</h2>")


@app.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """Mengembalikan status kesehatan sistem dan memori."""
    vault = Path(VAULT_PATH)
    notes_count = await asyncio.to_thread(
        lambda: len(list(vault.rglob("*.md"))) if vault.exists() else 0
    )
    if _memory_manager is None:
        memory_status = "unavailable"
    elif not _memory_manager.store.client or not _memory_manager.store.vector_db:
        memory_status = "degraded"
    else:
        memory_status = "ready"
    return {
        "status": "online",
        "system": "Carl Level 5 Cognitive OS",
        "components": {
            "memory": memory_status,
            "router": "ready" if _router is not None else "unavailable",
        },
        "models": {
            "writer": MODEL_WRITER,
            "reasoner": MODEL_REASONER,
            "coder": MODEL_CODER
        },
        "vault_path": str(vault),
        "total_notes": notes_count,
        "ollama_host": OLLAMA_HOST
    }


@app.post(
    "/api/chat",
    responses={
        400: {"description": "Query tidak boleh kosong."},
        503: {"description": "Sistem router AI belum siap."},
        500: {"description": "Terjadi kesalahan internal saat memproses permintaan."},
    },
)
async def handle_chat(req: ChatRequest) -> Dict[str, Any]:
    """Endpoint percakapan utama yang memproses input melalui AgentRouter cerdas."""
    global _router
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query tidak boleh kosong.")

    q = req.query.strip()
    if q.lower() in ["/stop", "stop", "/batal", "batal", "berhenti", "/berhenti"]:
        request_stop_tutoring()
        return {
            "reply": "🛑 **Sinyal Berhenti Terkirim!** Sesi les Carl dan Gemini segera dihentikan dan seluruh materi yang diperoleh sedang dirapikan ke Obsidian...",
            "status": "ok"
        }

    if _router is None:
        raise HTTPException(status_code=503, detail="Sistem router AI belum siap.")

    try:
        reply = await asyncio.to_thread(_router.route_and_execute, q)
        return {
            "reply": reply,
            "status": "ok"
        }
    except Exception:
        logger.exception("Chat request failed.")
        message = "❌ Terjadi kesalahan internal saat memproses permintaan."
        return JSONResponse(
            status_code=500,
            content={"reply": message, "status": "error", "detail": message},
        )


@app.post("/api/tutoring/stop")
async def handle_stop_tutoring() -> Dict[str, Any]:
    """Endpoint langsung untuk menghentikan sesi les Carl & Gemini secara manual."""
    request_stop_tutoring()
    return {
        "status": "ok",
        "message": "Sinyal berhenti manual berhasil dikirim ke Carl."
    }


@app.post("/api/reset")
async def handle_reset() -> Dict[str, Any]:
    """Reset sesi obrolan aktif."""
    global _team
    if _team:
        reply = _team.reset_session()
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/briefing")
async def handle_briefing() -> Dict[str, Any]:
    """Trigger manual Morning Strategic Briefing."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_briefing)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/sentinel")
async def handle_sentinel() -> Dict[str, Any]:
    """Trigger audit kesehatan Vault."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_sentinel)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/backup")
async def handle_backup() -> Dict[str, Any]:
    """Trigger pencadangan 1-klik Vault."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_backup)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post(
    "/api/heal",
    responses={
        400: {"description": "Permintaan heal tidak dapat diproses."},
        500: {"description": "Terjadi kesalahan saat memperbaiki Vault."},
    },
)
async def handle_heal() -> Dict[str, Any]:
    """Trigger auto-heal seluruh temuan Sentinel."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_heal)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post(
    "/api/canvas",
    responses={
        400: {"description": "Topik canvas tidak valid."},
        500: {"description": "Gagal membuat canvas."},
    },
)
async def handle_canvas(req: CanvasRequest) -> Dict[str, Any]:
    """Trigger generator Obsidian Visual Canvas."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_canvas, req.topic)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.get(
    "/api/tts",
    responses={
        400: {"description": "Teks kosong."},
        500: {"description": "Gagal menghasilkan audio TTS."},
    },
)
async def handle_tts(text: str) -> FileResponse:
    """Mengonversi teks ke audio mp3 untuk diputar langsung di browser/Obsidian."""
    from tools.tool_voice import clean_markdown_for_speech, generate_edge_tts_audio_async, DEFAULT_VOICE
    clean = clean_markdown_for_speech(text)
    if not clean:
        raise HTTPException(status_code=400, detail="Teks kosong.")
    if len(clean) > 600:
        clean = clean[:597] + "..."

    cache_dir = PROJECT_ROOT / "web" / "audio_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    audio_file = cache_dir / "carl_voice.mp3"

    ok = await generate_edge_tts_audio_async(clean, str(audio_file), DEFAULT_VOICE)
    if ok and audio_file.exists() and audio_file.stat().st_size > 0:
        return FileResponse(str(audio_file), media_type="audio/mpeg")
    raise HTTPException(status_code=500, detail="Gagal menghasilkan audio TTS")


@app.post("/api/voice")
async def handle_voice(req: ChatRequest) -> Dict[str, Any]:
    """Memproses input audio/suara."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_voice, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/vision")
async def handle_vision(req: ChatRequest) -> Dict[str, Any]:
    """Memproses ekstraksi PDF atau analisis gambar."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_vision, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.get(
    "/api/bridge",
    responses={400: {"description": "Informasi koneksi bridge tidak tersedia."}},
)
async def handle_bridge() -> Dict[str, Any]:
    """Mengembalikan info koneksi jembatan mobile lokal dan URL QR Code."""
    from bridge_server import get_bridge_info, generate_qr_ascii
    info = await asyncio.to_thread(get_bridge_info, port=8000)
    info["qr_ascii"] = generate_qr_ascii(info["mobile_url"])
    return info


@app.post(
    "/api/quick-memo",
    responses={400: {"description": "Memo tidak dapat disimpan."}},
)
async def handle_quick_memo(req: QuickMemoRequest) -> Dict[str, Any]:
    """Menyimpan memo kilat dari smartphone langsung ke 00-Inbox Vault."""
    from bridge_server import save_quick_memo
    res = await asyncio.to_thread(
        save_quick_memo,
        content=req.content,
        title=req.title,
        tags=req.tags,
        source=req.source or "Mobile Bridge",
    )
    if res["success"]:
        return {"status": "ok", "memo": res, "reply": f"✅ Memo kilat berhasil disimpan ke `00-Inbox/{res['filename']}`!"}
    raise HTTPException(status_code=400, detail=res.get("error", "Gagal menyimpan memo."))


@app.post("/api/serendipity")
async def handle_serendipity(req: Optional[ChatRequest] = None) -> Dict[str, Any]:
    """Memicu mesin penemu koneksi ide tersembunyi lintas domain (Frontier G)."""
    global _team
    if _team:
        query = req.query if req else ""
        reply = await asyncio.to_thread(_team.bot_serendipity, query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/calendar")
async def handle_calendar() -> Dict[str, Any]:
    """Mengekspor jadwal deadline Vault ke berkas .ics (Frontier I)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_calendar, "export")
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/research")
async def handle_research(req: ChatRequest) -> Dict[str, Any]:
    """Mencari dan mengarsipkan paper riset ilmiah dari arXiv ke Vault (Frontier I)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_research, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/browse")
async def handle_browse(req: ChatRequest) -> Dict[str, Any]:
    """Menjelajah web dan mengarsipkan tabel/halaman ke Vault (Frontier J)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_browser, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/eval")
async def handle_eval() -> Dict[str, Any]:
    """Menjalankan smoke benchmark retrieval memori (Frontier K)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_evaluator)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/crypto")
async def handle_crypto(req: ChatRequest) -> Dict[str, Any]:
    """Mengelola brankas catatan rahasia terenkripsi AES-256 (Frontier L)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_crypto, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.get("/galaxy", response_class=FileResponse)
async def serve_galaxy():
    """Menyajikan antarmuka visualisasi 3D Galaksi Pengetahuan (Frontier O)."""
    spatial_path = PROJECT_ROOT / "web" / "spatial_graph.html"
    if spatial_path.exists():
        return FileResponse(str(spatial_path))
    return HTMLResponse("<h2>Visualisasi Galaksi spatial_graph.html belum ditemukan.</h2>")


@app.get("/api/galaxy")
async def get_galaxy_data() -> Dict[str, Any]:
    """Ekstrak node dan relasi edge 3D dari Vault untuk visualisasi galaksi (Frontier O)."""
    return await asyncio.to_thread(_build_galaxy_data)


def _build_galaxy_data() -> Dict[str, Any]:
    vault = Path(VAULT_PATH)
    if not vault.exists():
        return {"nodes": [], "edges": []}

    all_files = _eligible_galaxy_files(vault)
    folder_colors = {
        "00": "#60a5fa",
        "01": "#a78bfa",
        "02": "#f59e0b",
        "03": "#34d399",
        "04": "#fb7185",
        "05": "#e879f9",
        "default": "#f97316",
    }
    file_map = {Path(path).stem.casefold(): index for index, path in enumerate(all_files)}
    nodes = [
        _build_galaxy_node(index, path, vault, len(all_files), folder_colors)
        for index, path in enumerate(all_files)
    ]
    edges = _add_galaxy_edges(all_files, file_map, nodes)
    return {"nodes": nodes, "edges": edges}


def _eligible_galaxy_files(vault: Path) -> List[str]:
    files = []
    for fpath in glob.glob(os.path.join(str(vault), "**", "*.md"), recursive=True):
        if not is_indexable_note(fpath, str(vault)):
            continue
        files.append(fpath)
    return files


def _galaxy_folder_color(top_folder: str, folder_colors: Dict[str, str]) -> str:
    for prefix, color in folder_colors.items():
        if prefix != "default" and prefix in top_folder.casefold():
            return color
    return folder_colors["default"]


def _build_galaxy_node(
    index: int,
    fpath: str,
    vault: Path,
    total: int,
    folder_colors: Dict[str, str],
) -> Dict[str, Any]:
    stem = Path(fpath).stem
    rel_dir = os.path.relpath(os.path.dirname(fpath), str(vault)).replace("\\", "/")
    top_folder = rel_dir.split("/")[0] if rel_dir != "." else "Root"
    phi = math.acos(1 - 2 * (index + 0.5) / max(total, 1))
    theta = math.pi * (1 + 5**0.5) * index
    radius = 180 + (index % 7) * 25
    return {
        "id": index,
        "title": stem,
        "folder": top_folder,
        "color": _galaxy_folder_color(top_folder, folder_colors),
        "size": 5,
        "links": 0,
        "x": round(radius * math.sin(phi) * math.cos(theta), 1),
        "y": round(radius * math.sin(phi) * math.sin(theta) * 0.7, 1),
        "z": round(radius * math.cos(phi), 1),
    }


def _add_galaxy_edges(
    all_files: List[str],
    file_map: Dict[str, int],
    nodes: List[Dict[str, Any]],
) -> List[Dict[str, int]]:
    edges = []
    for index, fpath in enumerate(all_files):
        try:
            with open(fpath, "r", encoding="utf-8") as note_file:
                content = note_file.read()
        except (OSError, UnicodeError):
            logger.exception("Failed reading note while building the galaxy graph: %s", fpath)
            continue
        for raw_link in re.findall(r"\[\[(.*?)\]\]", content):
            target = raw_link.split("|")[0].split("#")[0].strip().casefold()
            if target not in file_map or file_map[target] == index:
                continue
            target_id = file_map[target]
            edges.append({"source": index, "target": target_id})
            nodes[target_id]["links"] += 1
            nodes[target_id]["size"] = min(12, nodes[target_id]["size"] + 0.5)
    return edges


@app.post("/api/simulate")
async def handle_simulate(req: ChatRequest) -> Dict[str, Any]:
    """Menjalankan simulasi swarm 10 persona otonom (Frontier M)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_simulator, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/trainer")
async def handle_trainer(req: ChatRequest) -> Dict[str, Any]:
    """Distilasi pengetahuan Vault & pembuatan dataset LoRA Q&A (Frontier N)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_trainer, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/gemini")
async def handle_gemini(req: ChatRequest) -> Dict[str, Any]:
    """Mengirim pertanyaan langsung ke Google Gemini di browser (Frontier P)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_gemini, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/gemini_dialog")
async def handle_gemini_dialog(req: ChatRequest) -> Dict[str, Any]:
    """Kolaborasi dialog multi-turn Carl & Google Gemini di browser (Frontier P)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_gemini_dialog, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


@app.post("/api/tutoring")
async def handle_tutoring(req: ChatRequest) -> Dict[str, Any]:
    """Sesi Les Privat Carl bersama Guru Gemini & Distilasi ke Obsidian Vault (Frontier Q)."""
    global _team
    if _team:
        reply = await asyncio.to_thread(_team.bot_tutoring, req.query)
        return {"reply": reply, "status": "ok"}
    return unavailable_response()


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Menjalankan server FastAPI lokal dengan dukungan multi-device LAN."""
    from bridge_server import get_local_ip
    local_ip = get_local_ip()
    print("==================================================")
    print("🔌 Carl Level 5 Cognitive Sidecar & Mobile Server")
    print(f"💻 Akses Komputer Lokal : http://127.0.0.1:{port}")
    print(f"📱 Akses Smartphone (Wi-Fi): http://{local_ip}:{port}")
    print("==================================================")
    uvicorn.run("api_server:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    run_server()
