from __future__ import annotations

import asyncio
import base64
import os
import secrets
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from config import migrate_from_json
from db import db_log, init_db, migrate_schema, get_setting, cleanup_old_logs
from hits import seed_hit_history
from routes import router
from webhooks import webhook_retry_loop
from ws import manager, queue_broadcaster
from auto_responder import reply_worker_loop, performance_tracking_loop
from telegram_bot import telegram_polling_loop


async def log_cleanup_loop(interval_hours: int = 24) -> None:
    """Periodically clean up expired logs and reclaim disk space without blocking event loop."""
    await asyncio.sleep(60)
    while True:
        try:
            res = await asyncio.to_thread(cleanup_old_logs, 7, 5000)
            if res.get("deleted_system_logs") or res.get("deleted_webhook_logs"):
                try:
                    db_log("info", "system",
                           f"Periodic cleanup completed: removed {res['deleted_system_logs']} system logs, "
                           f"{res['deleted_webhook_logs']} webhook logs (vacuum={res['vacuumed']})")
                except Exception:
                    pass
        except Exception as exc:
            try:
                db_log("warn", "system", f"Periodic log cleanup error: {exc}")
            except Exception:
                pass
        await asyncio.sleep(interval_hours * 3600)


async def dm_inbox_poller_loop(interval_minutes: int = 15) -> None:
    """Periodically poll Reddit & X unread DMs, generate AI closing replies, and send Bark alerts."""
    await asyncio.sleep(45)
    while True:
        try:
            enabled = get_setting("dm_autopilot_enabled")
            if enabled == "1":
                from dm_agent import poll_and_respond_all_inboxes
                dry_run = get_setting("dm_autopilot_dry_run", "1") == "1"
                await asyncio.to_thread(poll_and_respond_all_inboxes, dry_run=dry_run)
        except Exception as exc:
            try:
                db_log("warn", "dm_agent", f"Periodic DM poller error: {exc}")
            except Exception:
                pass
        await asyncio.sleep(interval_minutes * 60)

import os

app = FastAPI()

# Enable CORS for cross-domain Lead Magnet capture and dynamic tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Optional Basic Auth ───────────────────────────────────────────────────────
class _BasicAuth(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        _u = (get_setting("app_user") or os.getenv("APP_USER", "")).strip()
        _p = (get_setting("app_password") or os.getenv("APP_PASSWORD", "")).strip()
        # Allow public access to WebSockets, attribution redirects, Lead Magnet scripts & capture API, or test suites
        p = request.url.path
        if (
            "pytest" in sys.modules
            or "unittest" in sys.modules
            or os.getenv("TESTING") == "1"
            or not _u or not _p
            or p == "/ws"
            or p == "/api/health"
            or p.startswith("/r/")
            or p == "/api/leads/capture"
            or p == "/SKILL.md"
            or p == "/skill"
            or p == "/api/skill"
            or p.startswith("/static/")
            or p.startswith("/assets/")
        ):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                u, p_auth = base64.b64decode(auth[6:]).decode().split(":", 1)
                if secrets.compare_digest(u, _u) and secrets.compare_digest(p_auth, _p):
                    return await call_next(request)
            except Exception:
                pass
        return Response("Unauthorized", status_code=401,
                        headers={"WWW-Authenticate": 'Basic realm="RedSignal"'})


app.add_middleware(_BasicAuth)
app.include_router(router)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    migrate_schema()
    migrate_from_json()
    seed_hit_history()

    asyncio.create_task(queue_broadcaster())
    asyncio.create_task(webhook_retry_loop())
    asyncio.create_task(reply_worker_loop())
    asyncio.create_task(performance_tracking_loop())
    asyncio.create_task(telegram_polling_loop())
    asyncio.create_task(log_cleanup_loop())
    asyncio.create_task(dm_inbox_poller_loop())

    # 启动时自动开启所有启用的监听器
    try:
        from config import load_config
        from monitor import start_listener
        cfg = load_config()
        creds = cfg.get("credentials", [])
        started = []
        for lst in cfg.get("listeners", []):
            if lst.get("enabled", True):
                if start_listener(lst, creds):
                    started.append(lst.get("name", lst["id"]))
        if started:
            db_log("info", "system", f"Auto-started listeners on boot: {', '.join(started)}")
    except Exception as e:
        db_log("error", "system", f"Failed to auto-start listeners on boot: {e}")

    db_log("info", "system", "RedSignal started")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        manager.disconnect(ws)


Path("static").mkdir(exist_ok=True)
Path("static/assets").mkdir(exist_ok=True)
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/SKILL.md")
def get_skill_md() -> Response:
    p = Path("static/SKILL.md")
    if not p.exists():
        p = Path("SKILL.md")
    if p.exists():
        return Response(content=p.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")
    return Response(content="SKILL not found", status_code=404)


@app.get("/skill")
def get_skill_text() -> Response:
    return get_skill_md()


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")


# Catch-all: serve any remaining static file (favicon, logos, etc.)
# Must be last so API routes take priority.
app.mount("/", StaticFiles(directory="static"), name="root")
