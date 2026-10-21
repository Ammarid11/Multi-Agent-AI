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
import argparse
import hashlib
import glob
import re
import asyncio
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
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

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

import config
from config import VAULT_PATH, MODEL_WRITER, MODEL_REASONER, MODEL_CODER, OLLAMA_HOST
from bridge_server import get_local_ip, is_authorized
from core.logging_setup import setup_logging
from core.netguard import host_allowed, origin_allowed
from memory_indexer import MemoryManager
from memory.vault_scanner import is_indexable_note
from agents import AITeam, AgentRouter
from agents.gemini_browser import request_stop_tutoring
from agents.streaming import reset_stream_callback, set_stream_callback
from scheduler import start_background_scheduler, stop_background_scheduler
from observability import log_stage

# Singleton global state
_memory_manager: Optional[MemoryManager] = None
_team: Optional[AITeam] = None
_router: Optional[AgentRouter] = None
SYSTEM_UNAVAILABLE_MESSAGE = "Sistem belum siap."
logger = logging.getLogger(__name__)
_remote_sessions: Dict[str, Any] = {}
_remote_sessions_lock = threading.Lock()
_REMOTE_SESSION_LIMIT = 20
_rate_hits: Dict[str, List[float]] = {}
_chat_job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="carl-chat")
_chat_jobs: Dict[str, Dict[str, Any]] = {}
_chat_jobs_lock = threading.Lock()
_CHAT_JOB_TTL_SECONDS = 60 * 60
_CHAT_JOB_LIMIT = 100


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
    setup_logging()
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

# CORS SENGAJA tidak diaktifkan: UI disajikan dari origin yang sama (termasuk di Obsidian Custom Frames).
# CORS wildcard + credentials sebelumnya memungkinkan situs web mana pun memanggil API ini.
LOCAL_CLIENTS = ("127.0.0.1", "::1", "localhost")
# Perangkat non-lokal hanya boleh tanya-jawab, memo, dan suara (dengan token). Semua endpoint lain ditolak.
REMOTE_ALLOW_PREFIXES = ("/api/chat", "/api/status", "/api/quick-memo", "/api/tts", "/api/reset")
_lan_ip_cache: Dict[str, Any] = {"ip": "", "at": 0.0}


def _client_host(request: Request) -> str:
    return request.client.host if request.client else ""


def _is_remote(request: Request) -> bool:
    return _client_host(request) not in LOCAL_CLIENTS


def _request_token(request: Request) -> Optional[str]:
    return (
        request.cookies.get("carl_t")
        or request.headers.get("x-carl-token")
        or request.query_params.get("t")
    )


def _allowed_hosts() -> set:
    port = config.WEB_PORT
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    if config.LAN_ENABLED:
        now = time.time()
        if now - _lan_ip_cache["at"] > 60:
            _lan_ip_cache.update(ip=get_local_ip(), at=now)
        hosts.add(f"{_lan_ip_cache['ip']}:{port}")
    return hosts


@app.middleware("http")
async def security_guard(request: Request, call_next):
    """Anti DNS-rebinding (Host), anti drive-by lintas situs (Origin), token + allowlist untuk perangkat remote."""
    host = request.headers.get("host", "")
    if not host_allowed(host, _allowed_hosts()):
        return JSONResponse(status_code=400, content={"detail": "Host tidak dikenal."})
    if not origin_allowed(request.headers.get("origin"), host):
        return JSONResponse(status_code=403, content={"detail": "Origin ditolak."})

    client = _client_host(request)
    remote = _is_remote(request)
    path = request.url.path
    if remote and path.startswith("/api/"):
        if not is_authorized(client, _request_token(request)):
            return JSONResponse(status_code=401, content={"detail": "Token diperlukan."})
        if not path.startswith(REMOTE_ALLOW_PREFIXES):
            return JSONResponse(status_code=403, content={"detail": "Endpoint ini tidak tersedia dari perangkat remote."})

    response = await call_next(request)
    token = request.query_params.get("t")
    if remote and token and is_authorized(client, token):
        response.set_cookie("carl_t", token, httponly=True, samesite="strict", max_age=int(config.BRIDGE_TOKEN_TTL_HOURS * 3600))
    return response


def _session_for(request: Request):
    """Sesi (team, router): lokal memakai instans utama; tiap perangkat remote mendapat sesi terpisah tanpa persistensi disk."""
    if not _is_remote(request):
        return _team, _router
    key = _request_token(request) or _client_host(request)
    with _remote_sessions_lock:
        session = _remote_sessions.get(key)
        if session is None:
            if len(_remote_sessions) >= _REMOTE_SESSION_LIMIT:
                _remote_sessions.pop(next(iter(_remote_sessions)))
            team = AITeam(_memory_manager, user_name="Pengguna", persist_history=False)
            session = (team, AgentRouter(team))
            _remote_sessions[key] = session
        return session


def _rate_ok(key: str, limit: int = 10, window: float = 60.0) -> bool:
    now = time.time()
    hits = [t for t in _rate_hits.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _rate_hits[key] = hits
        return False
    hits.append(now)
    _rate_hits[key] = hits
    return True


class ChatRequest(BaseModel):
    query: str = Field(max_length=20_000)


class CanvasRequest(BaseModel):
    topic: str


class QuickMemoRequest(BaseModel):
    content: str = Field(max_length=config.MEMO_MAX_CHARS)
    title: Optional[str] = Field(default=None, max_length=120)
    tags: Optional[List[str]] = Field(default=None, max_length=10)
    source: Optional[str] = Field(default="Mobile Bridge", max_length=60)


class TTSRequest(BaseModel):
    text: str = Field(max_length=4000)


@app.get("/", response_class=FileResponse)
async def serve_ui():
    """Menyajikan Web Chat UI Dark Mode untuk Obsidian Sidecar."""
    html_path = PROJECT_ROOT / "web" / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return HTMLResponse("<h2>UI index.html belum ditemukan di folder web/.</h2>")


@app.get("/api/status")
async def get_status(request: Request) -> Dict[str, Any]:
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
    if _is_remote(request):
        return {"status": "online", "components": {"memory": memory_status, "router": "ready" if _router is not None else "unavailable"}}
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
async def handle_chat(req: ChatRequest, request: Request) -> Dict[str, Any]:
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

    _, session_router = _session_for(request)
    try:
        reply = await asyncio.to_thread(session_router.route_and_execute, q, _is_remote(request))
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


def _run_chat_job(job_id: str, query: str, router: AgentRouter, remote: bool = False) -> None:
    """Run a chat request independently of the browser/Vercel request lifetime."""
    started_monotonic = time.perf_counter()
    with _chat_jobs_lock:
        job = _chat_jobs.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        job["started_monotonic"] = started_monotonic
        queue_wait_ms = round(
            (started_monotonic - job["queued_monotonic"]) * 1000,
            2,
        )
        job["queue_wait_ms"] = queue_wait_ms
        job["updated_at"] = time.time()

    last_stream_update = 0.0

    def publish_partial_reply(partial_reply: str) -> None:
        nonlocal last_stream_update
        now_monotonic = time.perf_counter()
        with _chat_jobs_lock:
            job = _chat_jobs.get(job_id)
            if job is not None and job["status"] == "running":
                stream_parts = job.setdefault("stream_parts", [])
                stream_parts.append(partial_reply)
                if now_monotonic - last_stream_update >= 0.04:
                    last_stream_update = now_monotonic
                    job["partial_reply"] = "".join(stream_parts)
                    job["updated_at"] = time.time()

    stream_token = set_stream_callback(publish_partial_reply)
    try:
        reply = router.route_and_execute(query, remote)
    except Exception:
        reset_stream_callback(stream_token)
        logger.exception("Background chat job %s failed.", job_id)
        finished_monotonic = time.perf_counter()
        with _chat_jobs_lock:
            job = _chat_jobs.get(job_id)
            if job is not None:
                job.update(
                    status="failed",
                    detail="Terjadi kesalahan internal saat memproses permintaan.",
                    execution_ms=round(
                        (finished_monotonic - started_monotonic) * 1000,
                        2,
                    ),
                    updated_at=time.time(),
                )
        log_stage(
            logger,
            "api",
            "chat_job",
            started_monotonic,
            queue_wait_ms=queue_wait_ms,
            status="failed",
        )
        return

    reset_stream_callback(stream_token)
    finished_monotonic = time.perf_counter()
    with _chat_jobs_lock:
        job = _chat_jobs.get(job_id)
        if job is not None:
            job.update(
                status="completed",
                reply=reply,
                execution_ms=round(
                    (finished_monotonic - started_monotonic) * 1000,
                    2,
                ),
                updated_at=time.time(),
            )
    log_stage(
        logger,
        "api",
        "chat_job",
        started_monotonic,
        queue_wait_ms=queue_wait_ms,
        status="completed",
    )


def _prune_chat_jobs(now: float) -> None:
    expired = [
        job_id
        for job_id, job in _chat_jobs.items()
        if job["status"] in {"completed", "failed"}
        and now - job["updated_at"] > _CHAT_JOB_TTL_SECONDS
    ]
    for job_id in expired:
        del _chat_jobs[job_id]

    if len(_chat_jobs) < _CHAT_JOB_LIMIT:
        return

    finished_jobs = sorted(
        (
            (job["updated_at"], job_id)
            for job_id, job in _chat_jobs.items()
            if job["status"] in {"completed", "failed"}
        )
    )
    while len(_chat_jobs) >= _CHAT_JOB_LIMIT and finished_jobs:
        _, job_id = finished_jobs.pop(0)
        del _chat_jobs[job_id]


@app.post("/api/chat-jobs", status_code=202)
@app.post("/api/chat/jobs", status_code=202)
async def start_chat_job(req: ChatRequest, request: Request) -> Dict[str, str]:
    """Start chat work on Carl and return immediately with a pollable job ID."""
    global _router
    query = req.query.strip() if req.query else ""
    if not query:
        raise HTTPException(status_code=400, detail="Query tidak boleh kosong.")

    if _router is None:
        raise HTTPException(status_code=503, detail=SYSTEM_UNAVAILABLE_MESSAGE)

    job_id = uuid.uuid4().hex
    now = time.time()
    with _chat_jobs_lock:
        _prune_chat_jobs(now)
        if len(_chat_jobs) >= _CHAT_JOB_LIMIT:
            raise HTTPException(
                status_code=503,
                detail="Antrean chat penuh. Tunggu tugas sebelumnya selesai.",
            )
        _chat_jobs[job_id] = {
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "queued_monotonic": time.perf_counter(),
        }

    try:
        _, session_router = _session_for(request)
        _chat_job_executor.submit(_run_chat_job, job_id, query, session_router, _is_remote(request))
    except RuntimeError as exc:
        logger.exception("Unable to enqueue chat job %s.", job_id)
        with _chat_jobs_lock:
            _chat_jobs.pop(job_id, None)
        raise HTTPException(
            status_code=503,
            detail="Server tidak dapat memulai tugas chat saat ini.",
        ) from exc

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/chat/jobs/{job_id}")
async def get_chat_job(job_id: str) -> Dict[str, Any]:
    """Return the current state or result of a background chat job."""
    with _chat_jobs_lock:
        job = _chat_jobs.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Tugas chat tidak ditemukan atau sudah kedaluwarsa.",
            )
        result = {"job_id": job_id, "status": job["status"]}
        if job["status"] == "queued":
            result["queue_wait_ms"] = round(
                (time.perf_counter() - job["queued_monotonic"]) * 1000,
                2,
            )
        elif job["status"] in {"running", "completed", "failed"}:
            result["queue_wait_ms"] = job.get("queue_wait_ms", 0)
            if job["status"] == "running":
                result["execution_ms"] = round(
                    (time.perf_counter() - job["started_monotonic"]) * 1000,
                    2,
                )
            else:
                result["execution_ms"] = job.get("execution_ms", 0)
        if job["status"] == "running" and job.get("stream_parts"):
            result["partial_reply"] = "".join(job["stream_parts"])
        if job["status"] == "completed":
            result["reply"] = job["reply"]
        elif job["status"] == "failed":
            result["detail"] = job["detail"]
        return result


@app.get("/api/chat-job")
async def get_chat_job_compat(id: str) -> Dict[str, Any]:
    """Support the single-segment polling URL used by the shared browser UI."""
    return await get_chat_job(id)


@app.post("/api/chat-stop")
@app.post("/api/tutoring/stop")
async def handle_stop_tutoring() -> Dict[str, Any]:
    """Endpoint langsung untuk menghentikan sesi les Carl & Gemini secara manual."""
    request_stop_tutoring()
    return {
        "status": "ok",
        "message": "Proses penghentian sesi les Carl & Gemini telah dimulai. \n"
        "Mohon tunggu beberapa saat hingga seluruh materi yang diperoleh dirapikan ke Second Brain.",
    }


@app.post("/api/reset")
async def handle_reset(request: Request) -> Dict[str, Any]:
    """Reset sesi obrolan aktif (milik klien yang meminta)."""
    team, _ = _session_for(request)
    if team:
        reply = team.reset_session()
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


_AUDIO_KEEP = 50
_AUDIO_MAX_AGE = 3600


def _prune_audio_cache(cache_dir: Path) -> None:
    try:
        files = sorted(cache_dir.glob("tts_*.mp3"), key=lambda f: f.stat().st_mtime, reverse=True)
        now = time.time()
        for index, f in enumerate(files):
            if index >= _AUDIO_KEEP or now - f.stat().st_mtime > _AUDIO_MAX_AGE:
                f.unlink(missing_ok=True)
    except OSError:
        pass


async def _tts_file_response(text: str) -> FileResponse:
    """Audio per teks (nama berkas = hash), ditulis ke berkas sementara lalu di-replace: aman dari balapan antar permintaan."""
    from tools.tool_voice import clean_markdown_for_speech, generate_edge_tts_audio_async, DEFAULT_VOICE
    clean = clean_markdown_for_speech(text)
    if not clean:
        raise HTTPException(status_code=400, detail="Teks kosong.")
    if len(clean) > 600:
        clean = clean[:597] + "..."

    cache_dir = PROJECT_ROOT / "web" / "audio_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{DEFAULT_VOICE}:{clean}".encode("utf-8")).hexdigest()[:24]
    audio_file = cache_dir / f"tts_{key}.mp3"
    if not (audio_file.exists() and audio_file.stat().st_size > 0):
        tmp_file = cache_dir / f"tts_{key}.{uuid.uuid4().hex[:8]}.part"
        ok = await generate_edge_tts_audio_async(clean, str(tmp_file), DEFAULT_VOICE)
        if not (ok and tmp_file.exists() and tmp_file.stat().st_size > 0):
            tmp_file.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="Gagal menghasilkan audio TTS")
        os.replace(tmp_file, audio_file)
    _prune_audio_cache(cache_dir)
    return FileResponse(str(audio_file), media_type="audio/mpeg")


@app.post("/api/tts", responses={400: {"description": "Teks kosong."}, 500: {"description": "Gagal menghasilkan audio TTS."}})
async def handle_tts_post(req: TTSRequest) -> FileResponse:
    """Mengonversi teks ke audio mp3. Teks dikirim di body (tidak masuk URL/access log)."""
    return await _tts_file_response(req.text)


@app.get("/api/tts", deprecated=True)
async def handle_tts(text: str = Query(..., max_length=4000)) -> FileResponse:
    """DEPRECATED: gunakan POST /api/tts. Dipertahankan agar UI lama tetap berjalan (access log disaring)."""
    return await _tts_file_response(text)


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
async def handle_quick_memo(req: QuickMemoRequest, request: Request) -> Dict[str, Any]:
    """Menyimpan memo kilat dari smartphone langsung ke 00-Inbox Vault (maks 10 memo/menit per klien)."""
    if not _rate_ok(f"memo:{_client_host(request)}"):
        raise HTTPException(status_code=429, detail="Terlalu banyak memo; coba lagi sebentar lagi.")
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


def run_server(host: Optional[str] = None, port: Optional[int] = None, lan: Optional[bool] = None):
    """Menjalankan server FastAPI. Default HANYA 127.0.0.1; mode LAN (--lan / CARL_LAN=1) memakai token."""
    from bridge_server import get_local_ip, current_bridge_token
    config.WEB_PORT = port or config.WEB_PORT
    config.LAN_ENABLED = config.LAN_ENABLED if lan is None else lan
    host = host or ("0.0.0.0" if config.LAN_ENABLED else "127.0.0.1")
    setup_logging()
    print("==================================================")
    print("🔌 Carl Level 5 Cognitive Sidecar")
    print(f"💻 Akses Komputer Lokal : http://127.0.0.1:{config.WEB_PORT}")
    if config.LAN_ENABLED:
        token = current_bridge_token()
        print(f"📱 Akses Smartphone (Wi-Fi): http://{get_local_ip()}:{config.WEB_PORT}/?t={token}")
        print(f"   (token berlaku {config.BRIDGE_TOKEN_TTL_HOURS:g} jam; perangkat remote hanya tanya-jawab/memo)")
    else:
        print("🔒 Mode LAN nonaktif. Jalankan dengan --lan untuk mengizinkan HP.")
    print("==================================================")
    uvicorn.run("api_server:app", host=host, port=config.WEB_PORT, reload=False, log_level="info")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carl API server")
    parser.add_argument("--lan", action="store_true", help="Izinkan perangkat lain di Wi-Fi (butuh token)")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    run_server(port=args.port, lan=True if args.lan else None)
