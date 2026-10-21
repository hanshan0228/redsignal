from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
import typing
from pathlib import Path

import requests as _http
from fastapi import APIRouter
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from starlette.requests import Request

from ai import resolve_ai_cred, run_ai_prompt
from auto_responder import create_attributed_short_link
from config import load_config, save_config
from db import db_log, get_db, get_setting, set_setting
from hits import _hit_history, db_update_filter, row_to_hit
from monitor import (
    listener_statuses,
    start_listener,
    stop_all_listeners,
    stop_listener,
)
from webhooks import queue_and_deliver

router = APIRouter()
_BOOT_TIME = time.time()


# ── Config ────────────────────────────────────────────────────────────────────
def _update_env_file(key_values: dict[str, str]) -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in key_values:
                new_lines.append(f"{k}={key_values[k]}")
                updated_keys.add(k)
                continue
        new_lines.append(line)
    for k, v in key_values.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@router.get("/api/auth/profile")
def api_get_auth_profile() -> dict:
    username = (get_setting("app_user") or os.getenv("APP_USER", "")).strip()
    return {
        "ok": True,
        "username": username or "admin",
        "has_auth": bool(username)
    }


@router.post("/api/auth/update")
def api_update_auth(payload: dict) -> dict:
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()
    if not username:
        return {"ok": False, "message": "用户名不能为空"}
    if not password:
        return {"ok": False, "message": "密码不能为空"}
    if len(password) < 6:
        return {"ok": False, "message": "密码长度不能少于 6 位"}

    # Update SQLite settings table
    set_setting("app_user", username)
    set_setting("app_password", password)

    # Update running environment in-memory
    os.environ["APP_USER"] = username
    os.environ["APP_PASSWORD"] = password

    # Update .env file so restarts persist
    try:
        _update_env_file({"APP_USER": username, "APP_PASSWORD": password})
    except Exception as e:
        db_log("warn", "system", f"Failed to persist .env file: {e}")

    db_log("info", "system", f"管理员账号凭据已更新 (用户名: {username})")
    return {"ok": True, "username": username, "message": "用户名和密码已成功更新！"}


@router.get("/api/config")
def api_get_config() -> dict:
    return load_config()


@router.post("/api/config")
def api_save_config(payload: dict) -> dict:
    cfg = load_config()
    cfg.update(payload)
    save_config(cfg)
    return {"ok": True}


# ── Monitor ───────────────────────────────────────────────────────────────────
@router.get("/api/listeners/status")
def api_listeners_status() -> dict:
    return listener_statuses()


@router.post("/api/listeners/{listener_id}/start")
def api_start_listener(listener_id: str) -> dict:
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == listener_id), None)
    if not lst:
        return {"ok": False, "message": "Listener not found"}
    lst["enabled"] = True
    save_config(cfg)
    start_listener(lst, cfg.get("credentials", []))
    return {"ok": True}


@router.post("/api/listeners/{listener_id}/stop")
def api_stop_listener(listener_id: str) -> dict:
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == listener_id), None)
    if lst:
        lst["enabled"] = False
        save_config(cfg)
    stop_listener(listener_id)
    return {"ok": True}


@router.post("/api/monitor/start")
def api_start_all() -> dict:
    cfg   = load_config()
    creds = cfg.get("credentials", [])
    started = [l.get("name", l["id"])
               for l in cfg.get("listeners", [])
               if l.get("enabled", True) and start_listener(l, creds)]
    return {"ok": True, "started": started}


@router.post("/api/monitor/stop")
def api_stop_all() -> dict:
    stop_all_listeners()
    return {"ok": True}


# ── Hits ──────────────────────────────────────────────────────────────────────
@router.get("/api/hits")
def api_get_hits(listener_id: str = "", kind: str = "", subreddit: str = "",
                 q: str = "", status: str = "", project: str = "", platform: str = "", limit: int = 50, offset: int = 0) -> dict:
    conds: list[str] = []
    params: list     = []
    if project and project != "all":
        cfg = load_config()
        matching_lids = [l["id"] for l in cfg.get("listeners", []) if (l.get("site_name") or l.get("name")) == project]
        if matching_lids:
            placeholders = ",".join(["?"] * len(matching_lids))
            conds.append(f"(listener_id IN ({placeholders}) OR listener_name = ?)")
            params.extend(matching_lids)
            params.append(project)
        else:
            conds.append("listener_name = ?")
            params.append(project)
    if listener_id: conds.append("listener_id=?");           params.append(listener_id)
    if platform:    conds.append("platform=?");              params.append(platform)
    if kind:        conds.append("kind=?");                  params.append(kind)
    if subreddit:   conds.append("subreddit LIKE ?");        params.append(f"%{subreddit}%")
    if status:      conds.append("status=?");                params.append(status)
    if q:
        conds.append("(title LIKE ? OR excerpt LIKE ? OR match_text LIKE ? OR author LIKE ?)")
        params.extend([f"%{q}%"] * 4)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM hits {where}", params).fetchone()[0]
        rows  = db.execute(f"SELECT * FROM hits {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
                            params + [limit, offset]).fetchall()
    return {"hits": [row_to_hit(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.patch("/api/hits/{hit_id}/status")
def api_hit_status(hit_id: str, payload: dict) -> dict:
    status = payload.get("status", "new")
    lid    = payload.get("listener_id")
    with get_db() as db:
        if lid:
            db.execute("UPDATE hits SET status=? WHERE hit_id=? AND listener_id=?", (status, hit_id, lid))
        else:
            db.execute("UPDATE hits SET status=? WHERE hit_id=?", (status, hit_id))
    return {"ok": True}


@router.patch("/api/hits/{hit_id}/reply")
def api_hit_reply(hit_id: str, payload: dict) -> dict:
    reply = payload.get("reply", "")
    lid   = payload.get("listener_id")
    with get_db() as db:
        if lid:
            db.execute("UPDATE hits SET reply_draft=?,status='replied' WHERE hit_id=? AND listener_id=?",
                       (reply, hit_id, lid))
        else:
            db.execute("UPDATE hits SET reply_draft=?,status='replied' WHERE hit_id=?", (reply, hit_id))
    return {"ok": True}


# ── Auto-Reply & Queue Control ────────────────────────────────────────────────
@router.get("/api/queue")
def api_get_queue(status: str = "", project: str = "", limit: int = 50) -> dict:
    conds = []
    params = []
    matching_lids: list[str] = []
    if project and project != "all":
        cfg = load_config()
        matching_lids = [l["id"] for l in cfg.get("listeners", []) if (l.get("site_name") or l.get("name")) == project]
        if matching_lids:
            placeholders = ",".join(["?"] * len(matching_lids))
            conds.append(f"(q.listener_id IN ({placeholders}) OR q.listener_name = ?)")
            params.extend(matching_lids)
            params.append(project)
        else:
            conds.append("q.listener_name = ?")
            params.append(project)

    if status:
        conds.append("q.status=?")
        params.append(status)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    order_clause = (
        "ORDER BY q.scheduled_at ASC, q.id ASC"
        if status == "scheduled"
        else "ORDER BY COALESCE(q.submitted_at, q.failed_at, q.updated_at, q.scheduled_at, CAST(strftime('%s', q.created_at) AS REAL)) DESC, q.id DESC"
    )

    with get_db() as db:
        rows = db.execute(
            f"""SELECT q.*,
                       h.title AS post_title,
                       h.excerpt AS post_excerpt,
                       h.ts AS post_ts,
                       h.created_at AS post_created_at,
                       h.url AS hit_url
                FROM reply_queue q
                LEFT JOIN hits h ON q.hit_id = h.hit_id
                {where}
                {order_clause}
                LIMIT ?""",
            params + [limit]
        ).fetchall()
        # Today count
        today = time.strftime("%Y-%m-%d")
        daily_used = db.execute(
            "SELECT SUM(reply_count) FROM account_quota WHERE date_str=?", (today,)
        ).fetchone()[0] or 0

        # Status counts breakdown for filter tabs
        filter_scope_where = ""
        filter_scope_params = []
        if matching_lids:
            placeholders = ",".join(["?"] * len(matching_lids))
            filter_scope_where = f"WHERE (listener_id IN ({placeholders}) OR listener_name = ?)"
            filter_scope_params = matching_lids + [project]

        counts_rows = db.execute(
            f"""SELECT status, COUNT(*) as cnt
                FROM reply_queue
                {filter_scope_where}
                GROUP BY status""",
            filter_scope_params
        ).fetchall()
        status_counts = {"all": 0, "scheduled": 0, "submitted": 0, "failed": 0, "cancelled": 0, "needs_review": 0}
        for cr in counts_rows:
            st = cr["status"]
            cnt = cr["cnt"]
            status_counts["all"] += cnt
            if st in status_counts:
                status_counts[st] = cnt

        # Scoped or global stats
        if matching_lids:
            placeholders = ",".join(["?"] * len(matching_lids))
            pending_count = db.execute(
                f"SELECT COUNT(*) FROM reply_queue WHERE status IN ('scheduled', 'pending') AND listener_id IN ({placeholders})",
                matching_lids
            ).fetchone()[0] or 0
            total_upvotes = db.execute(
                f"SELECT SUM(upvotes) FROM reply_queue WHERE status='submitted' AND listener_id IN ({placeholders})",
                matching_lids
            ).fetchone()[0] or 0
            total_clicks = db.execute(
                f"SELECT SUM(clicks) FROM short_links WHERE listener_id IN ({placeholders})",
                matching_lids
            ).fetchone()[0] or 0
            total_winners = db.execute(
                f"SELECT COUNT(*) FROM reply_queue WHERE is_winner=1 AND listener_id IN ({placeholders})",
                matching_lids
            ).fetchone()[0] or 0
        else:
            pending_count = db.execute(
                "SELECT COUNT(*) FROM reply_queue WHERE status IN ('scheduled', 'pending')"
            ).fetchone()[0] or 0
            total_upvotes = db.execute(
                "SELECT SUM(upvotes) FROM reply_queue WHERE status='submitted'"
            ).fetchone()[0] or 0
            total_clicks = db.execute(
                "SELECT SUM(clicks) FROM short_links"
            ).fetchone()[0] or 0
            total_winners = db.execute(
                "SELECT COUNT(*) FROM reply_queue WHERE is_winner=1"
            ).fetchone()[0] or 0

    items = [dict(r) for r in rows]
    return {
        "items": items,
        "daily_used": daily_used,
        "pending_count": pending_count,
        "total_upvotes": total_upvotes,
        "total_clicks": total_clicks,
        "total_winners": total_winners,
        "status_counts": status_counts,
        "now": time.time()
    }


class _EnqueueReq(BaseModel):
    hit_id: str
    listener_id: str
    subreddit: str
    post_id: str
    target_id: str
    target_url: str
    author: str
    reply_text: str
    funnel_tier: int = 3
    delay_seconds: int = 0
    immediate: bool = False
    platform: str = "reddit"
    opportunity_score: int = 50
    safety_verdict: str = "PASSED"
    persona: str = "expert"
    persona_label: str = "🎯 领域专家"
    chrono_reason: str = ""


@router.post("/api/queue/enqueue")
def api_enqueue_reply(req: _EnqueueReq) -> dict:
    import importlib, auto_responder
    importlib.reload(auto_responder)
    from auto_responder import (
        enqueue_reply,
        submit_reddit_reply,
        submit_x_reply,
        submit_forum_reply,
        record_successful_reply
    )
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == req.listener_id), None)
    platform = req.platform or (lst.get("platform") if lst else "reddit") or "reddit"

    # If immediate execution requested
    if req.immediate:
        item = {
            "reply_text": req.reply_text,
            "target_id": req.target_id or req.post_id,
            "post_id": req.post_id,
            "subreddit": req.subreddit,
            "target_url": req.target_url,
            "platform": platform
        }
        if platform in ("x", "twitter"):
            cred_id = lst.get("x_credential_id") if lst else None
            x_cred = next((c for c in cfg.get("credentials", []) if c["id"] == cred_id), None) if cred_id else None
            if not x_cred:
                x_cred = next((c for c in cfg.get("credentials", []) if c.get("type") in ("x", "twitter")), None)
            account_name = x_cred.get("name", "X Account") if x_cred else "X"
            cred_key = cred_id or (x_cred["id"] if x_cred else "x_default")
            is_cookie = bool(x_cred and x_cred.get("auth_token") and not x_cred.get("api_key"))
            cooldown_min = max(lst.get("reply_cooldown_minutes", 15), 45) if (lst and is_cookie) else (45 if is_cookie else 15)
            daily_lim = min(lst.get("daily_reply_limit", 25), 5) if (lst and is_cookie) else (5 if is_cookie else 25)
        elif platform in ("forum", "vbulletin", "phpbb", "xenforo"):
            cred_id = lst.get("forum_credential_id") if lst else None
            forum_cred = next((c for c in cfg.get("credentials", []) if c["id"] == cred_id), None) if cred_id else None
            if not forum_cred:
                forum_cred = next((c for c in cfg.get("credentials", []) if c.get("type") in ("forum", "vbulletin", "phpbb", "xenforo")), None)
            account_name = forum_cred.get("name", "Forum Account") if forum_cred else "Forum"
            cred_key = cred_id or (forum_cred["id"] if forum_cred else "forum_default")
            cooldown_min = lst.get("reply_cooldown_minutes", 15) if lst else 15
            daily_lim = lst.get("daily_reply_limit", 15) if lst else 15
        else:
            cred_id = lst.get("reddit_credential_id") if lst else None
            reddit_cred = next((c for c in cfg.get("credentials", []) if c["id"] == cred_id), None) if cred_id else None
            if not reddit_cred:
                reddit_cred = next((c for c in cfg.get("credentials", []) if c.get("type") == "reddit"), None)
            account_name = reddit_cred.get("name", "Reddit") if reddit_cred else "Reddit"
            cred_key = cred_id or (reddit_cred["id"] if reddit_cred else "reddit_default")
            cooldown_min = lst.get("reply_cooldown_minutes", 45) if lst else 45
            daily_lim = lst.get("daily_reply_limit", 8) if lst else 8

        # Rate limit & safety quarantine check before immediate execution
        from auto_responder import check_rate_limits
        allowed, reason = check_rate_limits(cred_key, cooldown_minutes=cooldown_min, daily_limit=daily_lim)
        if not allowed:
            return {
                "ok": False,
                "submitted": False,
                "rate_limited": True,
                "error": f"无法立即提交: 账号处于安全保护中 ({reason})。为防止平台风控封禁，请等待保护期结束。"
            }

        if platform in ("x", "twitter"):
            res = submit_x_reply(item, x_cred)
        elif platform in ("forum", "vbulletin", "phpbb", "xenforo"):
            res = submit_forum_reply(item, forum_cred)
        else:
            res = submit_reddit_reply(item, reddit_cred)

        now = time.time()
        if res["success"]:
            cid = res["comment_id"]
            curl = res["comment_url"]
            qid = enqueue_reply(
                hit_id=req.hit_id,
                listener_id=req.listener_id,
                listener_name=lst.get("name", req.listener_id) if lst else req.listener_id,
                subreddit=req.subreddit,
                post_id=req.post_id,
                target_id=req.target_id,
                target_url=req.target_url,
                author=req.author,
                reply_text=req.reply_text,
                funnel_tier=req.funnel_tier,
                scheduled_delay_seconds=0,
                status="submitted",
                platform=platform
            )
            with get_db() as db:
                db.execute(
                    "UPDATE reply_queue SET submitted_at=?, updated_at=?, comment_id=?, comment_url=?, error_message=NULL, credential_id=? WHERE id=?",
                    (now, now, cid, curl, cred_key, qid)
                )
                db.execute("UPDATE hits SET status='replied' WHERE hit_id=?", (req.hit_id,))
            record_successful_reply(cred_key, account_name)
            return {"ok": True, "submitted": True, "comment_url": curl, "comment_id": cid}
        else:
            err = res.get("error") or "Unknown error"
            if platform in ("x", "twitter") and any(k in str(err).lower() for k in ("344", "226", "daily limit", "automated", "429", "rate limit")):
                from auto_responder import record_rate_limit_cooldown
                record_rate_limit_cooldown(cred_key, 24 * 3600, account_name)
            elif res.get("is_rate_limited") and res.get("wait_seconds", 0) > 0:
                from auto_responder import record_rate_limit_cooldown
                record_rate_limit_cooldown(cred_key, res["wait_seconds"], account_name)
            return {"ok": False, "submitted": False, "error": err}

    # Enqueue for scheduled throttle
    qid = enqueue_reply(
        hit_id=req.hit_id,
        listener_id=req.listener_id,
        listener_name=lst.get("name", req.listener_id) if lst else req.listener_id,
        subreddit=req.subreddit,
        post_id=req.post_id,
        target_id=req.target_id,
        target_url=req.target_url,
        author=req.author,
        reply_text=req.reply_text,
        funnel_tier=req.funnel_tier,
        scheduled_delay_seconds=req.delay_seconds,
        status="scheduled",
        platform=platform,
        opportunity_score=req.opportunity_score,
        safety_verdict=req.safety_verdict,
        persona=req.persona,
        persona_label=req.persona_label,
        chrono_reason=req.chrono_reason
    )
    return {"ok": True, "queued": True, "queue_id": qid}


@router.post("/api/queue/{item_id}/submit_now")
def api_queue_submit_now(item_id: int) -> dict:
    import importlib, auto_responder
    importlib.reload(auto_responder)
    from auto_responder import submit_reddit_reply, submit_x_reply, submit_forum_reply, record_successful_reply
    with get_db() as db:
        row = db.execute("SELECT * FROM reply_queue WHERE id=?", (item_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "Queue item not found"}
        item = dict(row)

    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == item.get("listener_id")), None)
    platform = item.get("platform") or (lst.get("platform") if lst else "reddit") or "reddit"

    if platform in ("x", "twitter"):
        cred_id = lst.get("x_credential_id") if lst else None
        x_cred = next((c for c in cfg.get("credentials", []) if c["id"] == cred_id), None) if cred_id else None
        if not x_cred:
            x_cred = next((c for c in cfg.get("credentials", []) if c.get("type") in ("x", "twitter")), None)
        cred_key = cred_id or (x_cred["id"] if x_cred else "x_default")
        account_name = x_cred.get("name", "X Account") if x_cred else "X"
        is_cookie = bool(x_cred and x_cred.get("auth_token") and not x_cred.get("api_key"))
        cooldown_min = max(lst.get("reply_cooldown_minutes", 15), 45) if (lst and is_cookie) else (45 if is_cookie else 15)
        daily_lim = min(lst.get("daily_reply_limit", 25), 5) if (lst and is_cookie) else (5 if is_cookie else 25)
    elif platform in ("forum", "vbulletin", "phpbb", "xenforo"):
        cred_id = lst.get("forum_credential_id") if lst else None
        forum_cred = next((c for c in cfg.get("credentials", []) if c["id"] == cred_id), None) if cred_id else None
        if not forum_cred:
            forum_cred = next((c for c in cfg.get("credentials", []) if c.get("type") in ("forum", "vbulletin", "phpbb", "xenforo")), None)
        cred_key = cred_id or (forum_cred["id"] if forum_cred else "forum_default")
        account_name = forum_cred.get("name", "Forum Account") if forum_cred else "Forum"
        cooldown_min = lst.get("reply_cooldown_minutes", 15) if lst else 15
        daily_lim = lst.get("daily_reply_limit", 15) if lst else 15
    else:
        cred_id = lst.get("reddit_credential_id") if lst else None
        reddit_cred = next((c for c in cfg.get("credentials", []) if c["id"] == cred_id), None) if cred_id else None
        if not reddit_cred:
            reddit_cred = next((c for c in cfg.get("credentials", []) if c.get("type") == "reddit"), None)
        cred_key = cred_id or (reddit_cred["id"] if reddit_cred else "reddit_default")
        account_name = reddit_cred.get("name", "Reddit") if reddit_cred else "Reddit"
        cooldown_min = lst.get("reply_cooldown_minutes", 45) if lst else 45
        daily_lim = lst.get("daily_reply_limit", 8) if lst else 8

    from auto_responder import check_rate_limits
    allowed, reason = check_rate_limits(cred_key, cooldown_minutes=cooldown_min, daily_limit=daily_lim)
    if not allowed:
        return {
            "ok": False,
            "rate_limited": True,
            "error": f"无法立即提交: 账号处于安全保护中 ({reason})。为防止平台风控封禁，请等待保护期结束由系统自动提交。"
        }

    if platform in ("x", "twitter"):
        res = submit_x_reply(item, x_cred)
    elif platform in ("forum", "vbulletin", "phpbb", "xenforo"):
        res = submit_forum_reply(item, forum_cred)
    else:
        res = submit_reddit_reply(item, reddit_cred)

    now = time.time()
    if res["success"]:
        cid = res["comment_id"]
        curl = res["comment_url"]
        with get_db() as db:
            db.execute(
                """UPDATE reply_queue
                   SET status='submitted', submitted_at=?, updated_at=?, comment_id=?, comment_url=?, error_message=NULL, credential_id=?
                   WHERE id=?""",
                (now, now, cid, curl, cred_key, item_id)
            )
            db.execute("UPDATE hits SET status='replied' WHERE hit_id=?", (item["hit_id"],))
        record_successful_reply(cred_key, account_name)
        return {"ok": True, "comment_url": curl, "comment_id": cid}
    else:
        err = res.get("error") or "Unknown error"
        is_archived = res.get("is_archived", False)
        is_rate_limited = res.get("is_rate_limited", False)
        wait_seconds = res.get("wait_seconds", 0)

        if is_rate_limited and wait_seconds > 0:
            from auto_responder import record_rate_limit_cooldown
            record_rate_limit_cooldown(cred_key, wait_seconds, account_name)

        if is_rate_limited and not is_archived:
            resched_at = now + wait_seconds
            wait_min = max(1, round(wait_seconds / 60))
            with get_db() as db:
                db.execute(
                    """UPDATE reply_queue
                       SET status='scheduled', scheduled_at=?, error_message=?, updated_at=?, chrono_reason=?, credential_id=?
                       WHERE id=?""",
                    (resched_at, err, now, f"触发 Reddit 官方频控保护 (RATELIMIT)，已智能延期至 ~{wait_min} 分钟后重新尝试提交", cred_key, item_id)
                )
            return {
                "ok": False,
                "rate_limited": True,
                "wait_seconds": wait_seconds,
                "error": f"{err}。系统已为您自动排期至 {wait_min} 分钟后发射，无需重复手动点击。"
            }
        elif is_archived:
            with get_db() as db:
                db.execute(
                    "UPDATE reply_queue SET status='failed', is_archived=1, error_message=?, failed_at=?, updated_at=?, credential_id=? WHERE id=?",
                    (err, now, now, cred_key, item_id)
                )
            return {"ok": False, "is_archived": True, "error": err}
        else:
            if platform in ("x", "twitter") and any(k in str(err).lower() for k in ("344", "226", "daily limit", "automated", "429", "rate limit")):
                from auto_responder import record_rate_limit_cooldown
                record_rate_limit_cooldown(cred_key, 24 * 3600, account_name)

            with get_db() as db:
                db.execute(
                    "UPDATE reply_queue SET status='failed', error_message=?, failed_at=?, updated_at=?, credential_id=? WHERE id=?",
                    (err, now, now, cred_key, item_id)
                )
            return {"ok": False, "error": err}


@router.post("/api/queue/{item_id}/cancel")
def api_queue_cancel(item_id: int) -> dict:
    now = time.time()
    with get_db() as db:
        db.execute("UPDATE reply_queue SET status='cancelled', updated_at=? WHERE id=?", (now, item_id))
    return {"ok": True}


@router.post("/api/queue/{item_id}/retry")
def api_queue_retry(item_id: int) -> dict:
    now = time.time()
    with get_db() as db:
        row = db.execute("SELECT is_archived, error_message FROM reply_queue WHERE id=?", (item_id,)).fetchone()
        if row and (row["is_archived"] or (row["error_message"] and ("TOO_OLD" in row["error_message"] or "归档" in row["error_message"]))):
            return {"ok": False, "error": "该帖在 Reddit 上已被官方归档或锁定，禁止任何新回复，无法重试。建议点击清理移除该任务。"}
        db.execute(
            "UPDATE reply_queue SET status='scheduled', scheduled_at=?, updated_at=?, error_message=NULL WHERE id=?",
            (now, now, item_id)
        )
    return {"ok": True}


@router.post("/api/queue/{item_id}/follow_up")
def api_queue_follow_up(item_id: int) -> dict:
    """Generate Step 2 follow-up close reply for an already submitted comment and enqueue it."""
    with get_db() as db:
        row = db.execute("SELECT * FROM reply_queue WHERE id=?", (item_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Queue item {item_id} not found"}
        item = dict(row)

    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == item.get("listener_id")), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]

    cred = resolve_ai_cred(cfg, lst.get("ai_credential_id") if lst else None)
    site_name = (lst.get("site_name") or lst.get("name") or "My Product") if lst else "My Product"
    site_url  = (lst.get("site_url") or "") if lst else ""
    pitch_ins = lst.get("pitch_instruction", "") if lst else ""
    platform  = item.get("platform") or "reddit"

    # Generate attributed short link for follow-up
    short_link_url = ""
    if site_url:
        try:
            from auto_responder import create_attributed_short_link
            link_info = create_attributed_short_link(
                target_url=site_url,
                hit_id=item.get("hit_id", ""),
                listener_id=item.get("listener_id", ""),
                platform=platform,
                title=f"Follow-up to {item.get('author', 'user')}",
                text=item.get("reply_text", ""),
                listener_name=site_name,
                campaign="step2_followup"
            )
            short_link_url = link_info.get("short_url") or site_url
        except Exception:
            short_link_url = site_url

    from ai import generate_follow_up_reply
    follow_up_text = generate_follow_up_reply(
        parent_reply=item.get("reply_text") or "",
        user_question="Could you share the specific link, model recommendation, or guide you used?",
        user_author=item.get("author") or "friend",
        site_name=site_name,
        site_url=short_link_url or site_url,
        pitch_instruction=pitch_ins,
        credential=cred
    )

    comment_id = item.get("comment_id")
    if not comment_id:
        target_id = item.get("target_id") or item.get("post_id")
    else:
        if platform == "reddit":
            target_id = f"t1_{comment_id}" if not str(comment_id).startswith("t1_") else str(comment_id)
        else:
            target_id = str(comment_id)

    from auto_responder import enqueue_reply
    new_qid = enqueue_reply(
        hit_id=f"{item.get('hit_id')}_fu_{int(time.time())}",
        listener_id=item.get("listener_id") or "",
        listener_name=item.get("listener_name") or site_name,
        subreddit=item.get("subreddit") or "",
        post_id=item.get("post_id") or "",
        target_id=target_id,
        author=item.get("author") or "user",
        reply_text=follow_up_text,
        target_url=item.get("comment_url") or item.get("target_url") or "",
        platform=platform,
        funnel_tier=1,
        opportunity_score=95,
        safety_verdict="PASSED",
        persona=item.get("persona") or "authentic",
        persona_label="💬 二轮闭环追评",
        chrono_reason=f"人工触发针对已提交回复 ({comment_id or 'parent'}) 的 Step 2 转化追评",
        status="scheduled"
    )

    return {
        "ok": True,
        "follow_up_id": new_qid,
        "reply_text": follow_up_text,
        "target_id": target_id
    }


@router.patch("/api/hits/{hit_id}")
def api_update_hit(hit_id: str, payload: dict) -> dict:
    db_update_filter(hit_id, payload.get("listener_id"), payload.get("passed", False), payload.get("results", []))
    return {"ok": True}


@router.delete("/api/hits")
def api_clear_hits() -> dict:
    with get_db() as db:
        db.execute("DELETE FROM hits")
    _hit_history.clear()
    return {"ok": True}


@router.post("/api/hits/clean_test_mocks")
def api_clean_test_mocks() -> dict:
    """Clean up mock test hits generated during unit tests (where url is null and title matches test mocks)."""
    titles = [
        'Title A', 'Title B', 'Spam post', 'Where to buy',
        'Battery swap', 'Controller Issue', 'Overly filtered discussion',
        'Another post', 'Best lightweight stack'
    ]
    with get_db() as db:
        res = db.execute(f"DELETE FROM hits WHERE title IN ({','.join('?' for _ in titles)}) OR (url IS NULL AND title LIKE 'Project%')", titles)
        count = res.rowcount
    return {"ok": True, "deleted_count": count}


@router.get("/api/hits/stats")
def api_hits_stats() -> dict:
    with get_db() as db:
        total  = db.execute("SELECT COUNT(*) FROM hits").fetchone()[0]
        today  = db.execute("SELECT COUNT(*) FROM hits WHERE created_at >= date('now')").fetchone()[0]
        passed = db.execute("SELECT COUNT(*) FROM hits WHERE filter_passed=1").fetchone()[0]
        by_lst = db.execute("SELECT listener_name,COUNT(*) as cnt FROM hits GROUP BY listener_id ORDER BY cnt DESC LIMIT 10").fetchall()
        by_sub = db.execute("SELECT subreddit,COUNT(*) as cnt FROM hits GROUP BY subreddit ORDER BY cnt DESC LIMIT 10").fetchall()
    return {"total": total, "today": today, "passed": passed,
            "by_listener":  [{"name": r["listener_name"], "count": r["cnt"]} for r in by_lst],
            "by_subreddit": [{"subreddit": r["subreddit"], "count": r["cnt"]} for r in by_sub]}


@router.get("/api/hits/export")
def api_export_hits(listener_id: str = "", kind: str = "", platform: str = "") -> StreamingResponse:
    conds: list[str] = []
    params: list     = []
    if listener_id: conds.append("listener_id=?"); params.append(listener_id)
    if kind:        conds.append("kind=?");         params.append(kind)
    if platform:    conds.append("platform=?");     params.append(platform)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_db() as db:
        rows = db.execute(f"SELECT * FROM hits {where} ORDER BY ts DESC", params).fetchall()

    def _gen():
        yield "ts,listener,kind,subreddit,author,match,title,url,excerpt,filter_passed,status\n"
        for r in rows:
            def q(v): return '"' + str(v or "").replace('"', '""') + '"'
            fp = "" if r["filter_passed"] is None else ("yes" if r["filter_passed"] else "no")
            yield ",".join([q(r["created_at"]), q(r["listener_name"]), q(r["kind"]),
                            q(r["subreddit"]), q(r["author"]), q(r["match_text"]),
                            q(r["title"]), q(r["url"]), q(r["excerpt"]), q(fp),
                            q(r["status"] if "status" in r.keys() else "new")]) + "\n"

    return StreamingResponse(_gen(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=redsignal_hits.csv"})


# ── AI filter ─────────────────────────────────────────────────────────────────
class _FilterReq(BaseModel):
    text:          str
    filters:       list[typing.Any] = []
    credential_id: str | None = None
    hit_id:        str | None = None
    listener_id:   str | None = None


@router.post("/api/filter/test")
def api_filter_test(req: _FilterReq) -> dict:
    cfg  = load_config()
    cred = resolve_ai_cred(cfg, req.credential_id)
    if not cred:
        return {"error": "No AI key configured — add one in Vault"}

    results: list[dict] = []
    passed  = True

    lst = next((l for l in cfg.get("listeners", []) if l["id"] == req.listener_id), None) if req.listener_id else None
    site_name = (lst.get("site_name") if lst else "") or "our product"
    site_desc = (lst.get("site_description") if lst else "") or ""
    site_url  = (lst.get("site_url") if lst else "") or ""

    # 规范化 filters 参数（支持字典对象或纯字符串提示词；未传时回退使用监听器配置的 filters）
    raw_filters = req.filters if req.filters else ((lst.get("filters") or []) if lst else [])
    normalized_filters = []
    for idx, f in enumerate(raw_filters):
        if isinstance(f, str):
            normalized_filters.append({"name": f"Step {idx+1}", "prompt": f, "enabled": True})
        elif isinstance(f, dict):
            normalized_filters.append(f)

    for step in normalized_filters:
        if not step.get("enabled", True):
            results.append({"step": step.get("name", "?"), "skipped": True})
            continue
        try:
            step_prompt = step["prompt"]
            step_prompt = step_prompt.replace("{{site_name}}", site_name)
            step_prompt = step_prompt.replace("{{site_description}}", site_desc)
            step_prompt = step_prompt.replace("{{site_url}}", site_url)
            response = run_ai_prompt(step_prompt + "\n\nContent:\n" + req.text, cred)
            clean_resp = (response or "").strip()
            first_token = re.split(r"[\s,.:;!?-]+", clean_resp)[0].upper() if clean_resp else ""
            if first_token in ("YES", "PASS", "PASSED", "TRUE", "MATCH"):
                is_pass = True
            elif first_token in ("NO", "REJECT", "REJECTED", "FALSE"):
                is_pass = False
            else:
                has_no = bool(re.search(r"\b(no|reject|rejected|false|irrelevant|unrelated)\b", clean_resp, re.IGNORECASE))
                has_yes = bool(re.search(r"\b(yes|pass|passed|true|relevant|matches)\b", clean_resp, re.IGNORECASE))
                if has_yes and not has_no:
                    is_pass = True
                elif has_no and not has_yes:
                    is_pass = False
                else:
                    first_line = clean_resp.split("\n")[0]
                    is_pass = bool(re.search(r"\b(yes|pass|passed|true)\b", first_line, re.IGNORECASE))
            results.append({"step": step.get("name", "?"), "response": response, "passed": is_pass})
            if not is_pass:
                passed = False; break
        except Exception as exc:
            db_log("error", "filter", str(exc), req.listener_id)
            results.append({"step": step.get("name", "?"), "error": str(exc), "passed": False})
            passed = False; break

    if req.hit_id:
        db_update_filter(req.hit_id, req.listener_id, passed, results)

    return {"results": results, "passed": passed}


# ── AI Auto-Profile Generator for Any Project ──────────────────────────────────
class _GenProfileReq(BaseModel):
    site_name: str
    site_description: str
    site_url: str = ""
    platform: str = "reddit"
    credential_id: str | None = None


@router.post("/api/listeners/ai_generate_profile")
def api_generate_listener_profile(req: _GenProfileReq) -> dict:
    from ai import generate_listener_profile, generate_offers_matrix_with_ai, resolve_ai_cred
    cfg = load_config()
    cred = resolve_ai_cred(cfg, req.credential_id)
    if not cred:
        return {"ok": False, "error": "未配置有效的 AI 密钥。请先在 Vault (凭据库) 中添加 Claude 或 OpenAI 密钥。"}
    try:
        data = generate_listener_profile(
            site_name=req.site_name,
            site_description=req.site_description,
            site_url=req.site_url,
            platform=req.platform,
            credential=cred
        )
        if not data.get("offers_matrix"):
            data["offers_matrix"] = generate_offers_matrix_with_ai(
                site_name=req.site_name,
                site_description=req.site_description,
                site_url=req.site_url,
                keywords=data.get("keywords", []),
                credential=cred
            )
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": f"AI 分析生成失败: {e}"}


class _GenPersonasReq(BaseModel):
    site_name: str
    site_description: str
    keywords: list[str] = []
    pitch_instruction: str = ""
    subreddits: str = ""
    credential_id: str | None = None


@router.post("/api/listeners/generate_personas")
def api_generate_personas(req: _GenPersonasReq) -> dict:
    """Dynamically deduce 3-4 specialized domain expert personas tailored to ANY new project."""
    from ai import generate_project_personas, resolve_ai_cred
    cfg = load_config()
    cred = resolve_ai_cred(cfg, req.credential_id)
    if not cred:
        return {"ok": False, "error": "未配置有效的 AI 密钥。请先在 Vault (凭据库) 中配置 Claude 或 OpenAI 密钥。"}
    try:
        personas = generate_project_personas(
            site_name=req.site_name,
            site_description=req.site_description,
            keywords=req.keywords,
            pitch_instruction=req.pitch_instruction,
            subreddits=req.subreddits,
            credential=cred
        )
        return {"ok": True, "personas": personas}
    except Exception as e:
        return {"ok": False, "error": f"AI 赛道人设推演失败: {e}"}


class _GenVisualAssetsReq(BaseModel):
    site_name: str
    site_description: str
    site_url: str = ""
    keywords: list[str] = []
    credential_id: str | None = None


@router.post("/api/listeners/generate_visual_assets")
def api_generate_visual_assets(req: _GenVisualAssetsReq) -> dict:
    """Dynamically synthesize 3-4 authoritative technical visual assets tailored to ANY new project."""
    from ai import generate_project_visual_assets, resolve_ai_cred
    cfg = load_config()
    cred = resolve_ai_cred(cfg, req.credential_id)
    if not cred:
        return {"ok": False, "error": "未配置有效的 AI 密钥。请先在 Vault (凭据库) 中配置。"}
    try:
        assets = generate_project_visual_assets(
            site_name=req.site_name,
            site_description=req.site_description,
            site_url=req.site_url,
            keywords=req.keywords,
            credential=cred
        )
        return {"ok": True, "visual_assets": assets}
    except Exception as e:
        return {"ok": False, "error": f"AI 资产规划推演失败: {e}"}


class _GenOffersReq(BaseModel):
    site_name: str
    site_description: str = ""
    site_url: str = ""
    keywords: list[str] = []
    credential_id: str | None = None


@router.post("/api/listeners/ai_generate_offers")
def api_generate_offers_matrix(req: _GenOffersReq) -> dict:
    """Dynamically analyze a product and synthesize 3-5 high-converting offers/micro-tools."""
    from ai import generate_offers_matrix_with_ai, resolve_ai_cred
    cfg = load_config()
    cred = resolve_ai_cred(cfg, req.credential_id)
    try:
        offers = generate_offers_matrix_with_ai(
            site_name=req.site_name,
            site_description=req.site_description,
            site_url=req.site_url,
            keywords=req.keywords,
            credential=cred
        )
        return {"ok": True, "offers_matrix": offers, "offers": offers}
    except Exception as e:
        return {"ok": False, "error": f"AI 工具矩阵推演失败: {e}"}


class _IngestUrlReq(BaseModel):
    url: str
    platform: str = "reddit"
    credential_id: str | None = None


@router.post("/api/listeners/ai_ingest_url")
def api_ingest_url(req: _IngestUrlReq) -> dict:
    """One-click Zero-touch listener generation by crawling and analyzing a site URL."""
    from ai import extract_metadata_from_url, generate_listener_profile, generate_project_personas, generate_project_visual_assets, generate_offers_matrix_with_ai, resolve_ai_cred
    cfg = load_config()
    cred = resolve_ai_cred(cfg, req.credential_id)
    if not cred:
        return {"ok": False, "error": "未配置有效的 AI 密钥。请先在 Vault (凭据库) 中配置。"}
    try:
        meta = extract_metadata_from_url(req.url)
        site_name = meta.get("brand_name") or "Product"
        site_desc = meta.get("description") or meta.get("page_title") or site_name
        site_url = meta.get("url")

        # 1. Generate full listener profile
        profile = generate_listener_profile(
            site_name=site_name,
            site_description=site_desc,
            site_url=site_url,
            platform=req.platform,
            credential=cred
        )

        # 2. Synthesize 4 domain personas if not included
        personas = profile.get("personas")
        if not personas or len(personas) < 2:
            personas = generate_project_personas(
                site_name=site_name,
                site_description=site_desc,
                keywords=profile.get("keywords", []),
                pitch_instruction=profile.get("pitch_instruction", ""),
                subreddits=profile.get("subreddits", ""),
                credential=cred
            )

        # 3. Synthesize 3-4 visual assets proposals
        visual_assets = generate_project_visual_assets(
            site_name=site_name,
            site_description=site_desc,
            site_url=site_url,
            keywords=profile.get("keywords", []),
            credential=cred
        )

        # 4. Synthesize 3-5 offers/tools matrix proposals
        offers_matrix = generate_offers_matrix_with_ai(
            site_name=site_name,
            site_description=site_desc,
            site_url=site_url,
            keywords=profile.get("keywords", []),
            credential=cred
        )

        return {
            "ok": True,
            "data": {
                "site_name": site_name,
                "site_description": site_desc,
                "site_url": site_url,
                "name": profile.get("name") or f"{site_name} Radar",
                "subreddits": profile.get("subreddits", ""),
                "keywords": profile.get("keywords", []),
                "negative_keywords": profile.get("negative_keywords", []),
                "pitch_instruction": profile.get("pitch_instruction", ""),
                "filter_prompt": profile.get("filter_prompt", ""),
                "personas": personas,
                "visual_assets": visual_assets,
                "offers_matrix": offers_matrix
            }
        }
    except Exception as e:
        return {"ok": False, "error": f"URL 智能建仓失败: {e}"}


# ── Reply drafting ────────────────────────────────────────────────────────────
class _DraftReq(BaseModel):
    title:           str = ""
    excerpt:         str = ""
    subreddit:       str = ""
    product_context: str = ""
    tone:            str = "helpful"
    style:           str = "auto"
    funnel_tier:     int = 3
    credential_id:   str | None = None
    listener_id:     str | None = None
    platform:        str = "reddit"
    preferred_channel: str | None = None
    asset_id:        str | None = None
    persona:         str | None = None


@router.post("/api/reply/draft")
def api_draft_reply(req: _DraftReq) -> dict:
    cfg  = load_config()
    cred = resolve_ai_cred(cfg, req.credential_id)
    if not cred:
        return {"error": "No AI key configured — add one in Vault"}

    lst = None
    if req.listener_id:
        lst = next((l for l in cfg.get("listeners", []) if l["id"] == req.listener_id), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]

    site_name = (lst.get("site_name") or lst.get("name") or "My Product") if lst else "My Product"
    site_url  = (lst.get("site_url") or "") if lst else ""
    site_desc = (lst.get("site_description") or "") if lst else ""
    pitch_ins = lst.get("pitch_instruction", "") if lst else ""
    anti_ban  = lst.get("anti_ban_mode", "brand_search") if lst else "brand_search"
    stealth   = lst.get("stealth_mode", "direct_link") if lst else "direct_link"
    platform  = req.platform or (lst.get("platform") if lst else "reddit") or "reddit"

    from ai import generate_multichannel_reply, classify_funnel_tier
    funnel_tier = req.funnel_tier
    if not funnel_tier or funnel_tier == 3:
        funnel_tier, _ = classify_funnel_tier(req.title, req.excerpt)

    resolved_persona = req.persona or (req.style if req.style in ("guru", "authentic") else None)

    try:
        pack = generate_multichannel_reply(
            title=req.title,
            excerpt=req.excerpt,
            subreddit=req.subreddit,
            site_name=site_name,
            site_url=site_url,
            site_desc=site_desc,
            pitch_instruction=pitch_ins,
            anti_ban_mode=anti_ban,
            funnel_tier=funnel_tier,
            credential=cred,
            platform=platform,
            visual_assets=lst.get("visual_assets") if lst else None,
            preferred_channel=req.preferred_channel,
            asset_id=req.asset_id,
            persona=resolved_persona,
            personas=lst.get("personas") if lst else None,
            stealth_mode=stealth
        )
        from ai import calculate_opportunity_score, evaluate_reply_safety
        opp_eval = calculate_opportunity_score(
            req.title, req.excerpt, ts=time.time(), funnel_tier=funnel_tier,
            listener_keywords=lst.get("keywords") if lst else None,
            visual_assets=lst.get("visual_assets") if lst else None
        )
        safety_eval = evaluate_reply_safety(
            reply_text=pack["reply"],
            title=req.title,
            excerpt=req.excerpt,
            platform=platform,
            site_name=site_name,
            site_url=site_url,
            credential=cred
        )
        default_persona_obj = lst.get("personas", [{}])[0] if (lst and lst.get("personas")) else {}
        return {
            "reply": pack["reply"],
            "funnel_tier": funnel_tier,
            "persona": pack.get("persona") or default_persona_obj.get("key") or "expert",
            "persona_label": pack.get("persona_label") or default_persona_obj.get("label") or "🎯 领域专家",
            "opportunity_score": opp_eval["score"],
            "opp_priority": opp_eval["priority"],
            "safety_verdict": safety_eval.get("verdict", "PASSED"),
            "safety_score": safety_eval.get("safety_score", 8),
            "safety_details": safety_eval,
            "channels": pack.get("channels", {}),
            "matched_asset": pack.get("matched_asset"),
            "available_assets": pack.get("available_assets", [])
        }
    except Exception as exc:
        return {"error": str(exc)}


class _FormatChannelReq(BaseModel):
    text:          str
    title:         str = ""
    excerpt:       str = ""
    listener_id:   str | None = None
    anti_ban_mode: str | None = None
    asset_id:      str | None = None


@router.post("/api/reply/format_channels")
def api_format_channels(req: _FormatChannelReq) -> dict:
    """Instantly convert existing reply markdown into Forum BBCode, Reddit OP comment, and Tweet."""
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == req.listener_id), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]
    site_name = (lst.get("site_name") or lst.get("name") or "My Product") if lst else "My Product"
    site_url = (lst.get("site_url") or "") if lst else ""
    anti_ban = req.anti_ban_mode or (lst.get("anti_ban_mode") if lst else "brand_search") or "brand_search"
    visual_assets = (lst.get("visual_assets") if lst else None) or []
    stealth = (lst.get("stealth_mode", "direct_link") if lst else "direct_link")

    from ai import match_visual_asset, format_multichannel_pack
    matched = match_visual_asset(req.title, req.excerpt or req.text, visual_assets, requested_asset_id=req.asset_id)
    channels = format_multichannel_pack(
        base_reply=req.text,
        title=req.title,
        excerpt=req.excerpt,
        site_name=site_name,
        site_url=site_url,
        anti_ban_mode=anti_ban,
        matched_asset=matched,
        stealth_mode=stealth
    )
    return {
        "channels": channels,
        "matched_asset": matched,
        "available_assets": visual_assets
    }


class _SafetyCheckReq(BaseModel):
    text:          str
    title:         str = ""
    excerpt:       str = ""
    platform:      str = "reddit"
    listener_id:   str | None = None
    credential_id: str | None = None


@router.post("/api/reply/evaluate_safety")
def api_evaluate_safety(req: _SafetyCheckReq) -> dict:
    """Run LLM-as-a-Judge pre-flight safety audit on any reply text on demand."""
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == req.listener_id), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]
    site_name = (lst.get("site_name") or lst.get("name") or "My Product") if lst else "My Product"
    site_url  = (lst.get("site_url") or "") if lst else ""
    cred = resolve_ai_cred(cfg, req.credential_id or (lst.get("ai_credential_id") if lst else None))

    from ai import evaluate_reply_safety
    return evaluate_reply_safety(
        reply_text=req.text,
        title=req.title,
        excerpt=req.excerpt,
        platform=req.platform,
        site_name=site_name,
        site_url=site_url,
        credential=cred
    )


@router.post("/api/listeners/{listener_id}/reset_assets")
def api_reset_listener_assets(listener_id: str) -> dict:
    """Reset listener visual assets to preset if golf-related, or empty."""
    from config import DEFAULT_FAIRWAYFORT_ASSETS, save_config
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == listener_id), None)
    if not lst:
        return {"ok": False, "error": f"Listener {listener_id} not found"}
    is_golf = "fairway" in (lst.get("site_name") or "").lower() or "golf" in (lst.get("subreddits") or "").lower()
    assets = DEFAULT_FAIRWAYFORT_ASSETS if is_golf else []
    lst["visual_assets"] = assets
    save_config(cfg)
    return {"ok": True, "visual_assets": assets}


@router.post("/api/hits/{hit_id}/auto_draft")
def api_hit_auto_draft(hit_id: str, style: str = "auto") -> dict:
    """Generate marketing contextual reply draft for a specific hit and save to DB."""
    with get_db() as db:
        row = db.execute("SELECT * FROM hits WHERE hit_id=? OR id=?", (hit_id, hit_id)).fetchone()
        if not row:
            return {"ok": False, "error": f"Hit {hit_id} not found"}
        hit = dict(row)

    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]

    cred = resolve_ai_cred(cfg, lst.get("ai_credential_id") if lst else None)
    if not cred:
        return {"ok": False, "error": "No AI key configured in Vault"}

    site_name = (lst.get("site_name") or lst.get("name") or "My Product") if lst else "My Product"
    site_url  = (lst.get("site_url") or "") if lst else ""
    site_desc = (lst.get("site_description") or "") if lst else ""
    pitch_ins = lst.get("pitch_instruction", "") if lst else ""
    anti_ban  = lst.get("anti_ban_mode", "brand_search") if lst else "brand_search"
    stealth   = lst.get("stealth_mode", "direct_link") if lst else "direct_link"
    platform  = hit.get("platform") or (lst.get("platform") if lst else "reddit") or "reddit"

    from ai import generate_multichannel_reply, classify_funnel_tier, calculate_opportunity_score, evaluate_reply_safety
    funnel_tier, funnel_reason = classify_funnel_tier(
        hit.get("title") or "", hit.get("excerpt") or "",
        custom_keywords=lst.get("keywords") if lst else None
    )
    opp_res = calculate_opportunity_score(
        hit.get("title") or "", hit.get("excerpt") or "", ts=hit.get("ts"), funnel_tier=funnel_tier,
        listener_keywords=lst.get("keywords") if lst else None,
        visual_assets=lst.get("visual_assets") if lst else None
    )
    opportunity_score = opp_res["score"]

    resolved_persona = style if style in ("guru", "authentic") else None

    try:
        pack = generate_multichannel_reply(
            title=hit.get("title") or "",
            excerpt=hit.get("excerpt") or "",
            subreddit=hit.get("subreddit") or "",
            site_name=site_name,
            site_url=site_url,
            site_desc=site_desc,
            pitch_instruction=pitch_ins,
            anti_ban_mode=anti_ban,
            funnel_tier=funnel_tier,
            credential=cred,
            platform=platform,
            visual_assets=lst.get("visual_assets") if lst else None,
            persona=resolved_persona,
            personas=lst.get("personas") if lst else None,
            stealth_mode=stealth
        )
        reply = pack["reply"]

        safety_res = evaluate_reply_safety(
            reply_text=reply,
            title=hit.get("title") or "",
            excerpt=hit.get("excerpt") or "",
            platform=platform,
            site_name=site_name,
            site_url=site_url,
            credential=cred
        )
        safety_verdict = safety_res.get("verdict", "PASSED")
        safety_score = safety_res.get("safety_score", 8)

        persona_key = pack.get("persona", "expert")
        persona_lbl = pack.get("persona_label", "🎯 领域专家")

        with get_db() as db:
            db.execute(
                """UPDATE hits
                   SET reply_draft=?, funnel_tier=?, funnel_reason=?,
                       opportunity_score=?, safety_verdict=?, safety_score=?,
                       persona=?, persona_label=?
                   WHERE hit_id=? OR id=?""",
                (reply, funnel_tier, funnel_reason, opportunity_score, safety_verdict, safety_score,
                 persona_key, persona_lbl, hit_id, hit_id)
            )
            # Sync to pending queue item if one already exists
            db.execute(
                """UPDATE reply_queue
                   SET reply_text=?, opportunity_score=?, safety_verdict=?,
                       persona=?, persona_label=?
                   WHERE hit_id=? AND status IN ('pending', 'needs_review')""",
                (reply, opportunity_score, safety_verdict, persona_key, persona_lbl, hit_id)
            )
        return {
            "ok": True,
            "reply_draft": reply,
            "funnel_tier": funnel_tier,
            "funnel_reason": funnel_reason,
            "persona": persona_key,
            "persona_label": persona_lbl,
            "opportunity_score": opportunity_score,
            "opp_priority": opp_res.get("priority"),
            "safety_verdict": safety_verdict,
            "safety_score": safety_score,
            "safety_details": safety_res,
            "channels": pack.get("channels", {}),
            "matched_asset": pack.get("matched_asset")
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/api/hits/{hit_id}/switch_style")
def api_hit_switch_style(hit_id: str, style: str = "guru") -> dict:
    """Instantly switch and regenerate draft between A/B styles ('guru' vs 'authentic')."""
    return api_hit_auto_draft(hit_id, style=style)


@router.post("/api/queue/{item_id}/switch_style")
def api_queue_switch_style(item_id: int, style: str = "guru") -> dict:
    """Regenerate queued reply in specified A/B style ('guru' vs 'authentic')."""
    with get_db() as db:
        row = db.execute("SELECT * FROM reply_queue WHERE id=?", (item_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Queue item {item_id} not found"}
        q = dict(row)

    res = api_hit_auto_draft(q["hit_id"], style=style)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error")}

    with get_db() as db:
        updated = db.execute("SELECT * FROM reply_queue WHERE id=?", (item_id,)).fetchone()
        return {"ok": True, "item": dict(updated) if updated else None, "draft": res}


@router.post("/api/hits/batch_auto_draft")
def api_batch_auto_draft(limit: int = 10) -> dict:
    """Batch generate drafts for hits that do not have reply_draft yet."""
    with get_db() as db:
        rows = db.execute(
            """SELECT hit_id FROM hits
               WHERE (reply_draft IS NULL OR reply_draft = '')
               ORDER BY (CASE WHEN filter_passed = 1 THEN 0 ELSE 1 END), rowid DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        hit_ids = [r["hit_id"] for r in rows]

    success_count = 0
    errors = []
    for hid in hit_ids:
        res = api_hit_auto_draft(hid)
        if res.get("ok"):
            success_count += 1
        else:
            errors.append(res.get("error"))

    return {"ok": True, "generated_count": success_count, "total_attempted": len(hit_ids), "errors": errors}


@router.post("/api/queue/enqueue_all_passed")
def api_queue_enqueue_all_passed() -> dict:
    """Enqueue all passed hits with reply drafts into the anti-ban safety queue with spaced delays."""
    cfg = load_config()
    listeners_map = {l["id"]: l for l in cfg.get("listeners", [])}

    with get_db() as db:
        rows = db.execute(
            """SELECT h.* FROM hits h
               LEFT JOIN reply_queue q ON h.hit_id = q.hit_id
               WHERE h.filter_passed = 1 AND h.reply_draft IS NOT NULL AND h.reply_draft != '' AND q.id IS NULL
               ORDER BY h.ts DESC LIMIT 20"""
        ).fetchall()
        eligible = [dict(r) for r in rows]

    if not eligible:
        return {"ok": True, "enqueued_count": 0, "message": "没有符合条件的待排期线索（需已通过 AI 筛选且已有草稿）"}

    from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
    enqueued = 0
    for idx, hit in enumerate(eligible):
        lst = listeners_map.get(hit.get("listener_id"), {})
        cooldown_min = lst.get("reply_cooldown_minutes", 45) or 45
        chrono = calculate_smart_chrono_dispatch(
            post_ts=hit.get("ts"),
            opportunity_score=hit.get("opportunity_score", 50),
            schedule_timezone=lst.get("schedule_timezone"),
            schedule_start=lst.get("schedule_start"),
            schedule_end=lst.get("schedule_end")
        )
        stagger = (idx * cooldown_min * 60) + chrono["delay_seconds"]
        default_persona_obj = lst.get("personas", [{}])[0] if lst.get("personas") else {}
        persona = hit.get("persona") or default_persona_obj.get("key") or "expert"
        persona_label = hit.get("persona_label") or default_persona_obj.get("label") or "🎯 领域专家"
        enqueue_reply(
            hit_id=hit["hit_id"],
            listener_id=hit.get("listener_id") or "",
            listener_name=hit.get("listener_name") or "",
            subreddit=hit.get("subreddit") or "",
            post_id=hit.get("post_id") or hit["hit_id"],
            target_id=hit["hit_id"],
            target_url=hit.get("url") or "",
            author=hit.get("author") or "",
            reply_text=hit["reply_draft"],
            funnel_tier=hit.get("funnel_tier", 3) or 3,
            scheduled_delay_seconds=stagger,
            status="scheduled",
            platform=hit.get("platform") or lst.get("platform", "reddit") or "reddit",
            opportunity_score=hit.get("opportunity_score", 50) or 50,
            safety_verdict=hit.get("safety_verdict", "PASSED") or "PASSED",
            persona=persona,
            persona_label=persona_label,
            chrono_reason=chrono["chrono_reason"]
        )
        enqueued += 1

    return {"ok": True, "enqueued_count": enqueued}


@router.post("/api/hits/{hit_id}/one_click_engage")
def api_hit_one_click_engage(hit_id: str) -> dict:
    """One-click AI Autopilot for a single hit: generate draft if needed, evaluate safety, and enqueue into safety queue."""
    with get_db() as db:
        r = db.execute("SELECT * FROM hits WHERE hit_id=?", (hit_id,)).fetchone()
        if not r:
            return {"ok": False, "error": "Hit not found"}
        hit = dict(r)

    reply_draft = hit.get("reply_draft")
    safety_verdict = hit.get("safety_verdict") or "PASSED"
    opp_score = hit.get("opportunity_score", 50) or 50
    funnel_tier = hit.get("funnel_tier", 3) or 3
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), None)
    first_p = (lst.get("personas") or [{}])[0] if lst and lst.get("personas") else {}
    persona = hit.get("persona") or first_p.get("key") or "expert"
    persona_label = hit.get("persona_label") or first_p.get("label") or "🎯 领域专家"

    # 1. If no draft, auto-generate with AI
    if not reply_draft:
        res = api_hit_auto_draft(hit_id)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error", "AI 草稿生成失败")}
        reply_draft = res.get("reply_draft")
        safety_verdict = res.get("safety_verdict", "PASSED")
        opp_score = res.get("opportunity_score", 50)
        funnel_tier = res.get("funnel_tier", 3)
        persona = res.get("persona") or persona
        persona_label = res.get("persona_label") or persona_label

    # 2. Check if already in queue
    with get_db() as db:
        existing = db.execute("SELECT id, status, chrono_reason, scheduled_at FROM reply_queue WHERE hit_id=?", (hit_id,)).fetchone()
        if existing:
            return {
                "ok": True,
                "already_queued": True,
                "queue_id": existing["id"],
                "status": existing["status"],
                "reply_draft": reply_draft,
                "opportunity_score": opp_score,
                "safety_verdict": safety_verdict,
                "persona": persona,
                "persona_label": persona_label,
                "chrono_reason": existing["chrono_reason"] or "",
                "message": "该线索已在防封队列中排期"
            }

    # 3. Enqueue into safety queue using Smart Chrono Peak Dispatcher
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), {})

    from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
    chrono = calculate_smart_chrono_dispatch(
        post_ts=hit.get("ts"),
        opportunity_score=opp_score,
        schedule_timezone=lst.get("schedule_timezone"),
        schedule_start=lst.get("schedule_start"),
        schedule_end=lst.get("schedule_end")
    )
    stagger = chrono["delay_seconds"]
    chrono_reason = chrono["chrono_reason"]
    is_peak = chrono["is_peak"]

    status = "scheduled" if safety_verdict == "PASSED" else "needs_review"

    qid = enqueue_reply(
        hit_id=hit_id,
        listener_id=hit.get("listener_id") or "",
        listener_name=hit.get("listener_name") or "",
        subreddit=hit.get("subreddit") or "",
        post_id=hit.get("post_id") or hit_id,
        target_id=hit_id,
        target_url=hit.get("url") or "",
        author=hit.get("author") or "",
        reply_text=reply_draft,
        funnel_tier=funnel_tier,
        scheduled_delay_seconds=stagger,
        status=status,
        platform=hit.get("platform") or lst.get("platform", "reddit") or "reddit",
        opportunity_score=opp_score,
        safety_verdict=safety_verdict,
        persona=persona,
        persona_label=persona_label,
        chrono_reason=chrono_reason
    )

    return {
        "ok": True,
        "queue_id": qid,
        "status": status,
        "reply_draft": reply_draft,
        "opportunity_score": opp_score,
        "safety_verdict": safety_verdict,
        "persona": persona,
        "persona_label": persona_label,
        "chrono_reason": chrono_reason,
        "is_peak": is_peak,
        "delay_minutes": chrono["delay_minutes"]
    }


@router.post("/api/hits/{hit_id}/resurrect")
def api_hit_resurrect(hit_id: str) -> dict:
    """
    AI Negative Feedback & False-Positive Resurrection:
    Recovers a falsely-filtered lead, marks it passed, auto-generates reply draft,
    enqueues it into the safety queue, and records human correction feedback into ai_learnings.
    """
    with get_db() as db:
        r = db.execute("SELECT * FROM hits WHERE hit_id=? OR post_id=? ORDER BY id DESC LIMIT 1", (hit_id, hit_id)).fetchone()
        if not r:
            return {"ok": False, "error": "Hit not found"}
        hit = dict(r)

        # Mark as passed and active
        db.execute(
            """UPDATE hits
               SET filter_passed=1, status='new'
               WHERE hit_id=?""",
            (hit["hit_id"],)
        )

    # 1. Record AI Learning (Human Correction Feedback)
    sub = hit.get("subreddit") or ""
    plat = hit.get("platform") or "reddit"
    title_snippet = (hit.get("title") or "线索")[:60]
    excerpt_snippet = (hit.get("excerpt") or hit.get("title") or "")[:200]

    from auto_responder import record_ai_learning
    record_ai_learning(
        platform=plat,
        subreddit=sub,
        learning_type="false_negative_correction",
        title=f"r/{sub} 意向线索人工纠偏复活",
        pattern=f"用户人工核准复活线索「{title_snippet}」，原判定存在过度拦截",
        action_taken=f"自愈引擎已强化意向召回：对 r/{sub} 同类痛点咨询与技术排查优先放行并积极解答",
        sample_text=excerpt_snippet
    )
    db_log("info", "ai_learning", f"🛡️ [AI自愈闭环] 成功复活误杀线索并沉淀纠偏知识: {title_snippet}")

    # 2. Trigger One-click Engage (Draft + Safety + Smart Chrono Enqueue)
    engage_res = api_hit_one_click_engage(hit["hit_id"])
    return {
        "ok": True,
        "resurrected": True,
        "hit_id": hit["hit_id"],
        "engage": engage_res
    }


@router.post("/api/hits/{hit_id}/dm_pitch")
def api_hit_dm_pitch(hit_id: str) -> dict:
    """Generate high-converting 1-on-1 private message (DM) outreach draft, dynamic tool routing, and 3-stage playbook."""
    with get_db() as db:
        row = db.execute("SELECT * FROM hits WHERE hit_id=? OR id=?", (hit_id, hit_id)).fetchone()
        if not row:
            return {"ok": False, "error": f"Hit {hit_id} not found"}
        hit = dict(row)

    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]

    cred = resolve_ai_cred(cfg, lst.get("ai_credential_id") if lst else None)
    site_name = (lst.get("site_name") or lst.get("name") or "My Product") if lst else "My Product"
    site_url  = (lst.get("site_url") or "") if lst else ""
    pitch_ins = lst.get("pitch_instruction", "") if lst else ""
    platform  = hit.get("platform") or (lst.get("platform") if lst else "reddit") or "reddit"
    author    = hit.get("author") or ""
    offers_matrix = lst.get("offers_matrix") if lst else None

    # Dynamic Tool Routing: match the best landing tool based on post keywords
    from ai import resolve_dynamic_tool_url, generate_dm_pitch, generate_conversion_playbook
    routed_tool = resolve_dynamic_tool_url(
        site_url,
        f"{hit.get('title', '')} {hit.get('excerpt', '')}",
        offers_matrix=offers_matrix
    )
    destination_url = routed_tool.get("routed_url") or site_url

    # Generate attributed short link with UTM for DM outreach pointing to the specific routed tool
    short_link_url = ""
    if destination_url:
        try:
            from auto_responder import create_attributed_short_link
            link_info = create_attributed_short_link(
                target_url=destination_url,
                hit_id=hit.get("hit_id", hit_id),
                listener_id=hit.get("listener_id", ""),
                platform=platform,
                title=hit.get("title", ""),
                text=hit.get("excerpt", ""),
                listener_name=site_name,
                campaign="dm_outreach"
            )
            short_link_url = link_info.get("short_url") or destination_url
        except Exception:
            short_link_url = destination_url

    dm_res = generate_dm_pitch(
        title=hit.get("title") or "",
        excerpt=hit.get("excerpt") or "",
        author=author,
        site_name=site_name,
        site_url=short_link_url or destination_url,
        pitch_instruction=pitch_ins,
        platform=platform,
        credential=cred
    )

    playbook = generate_conversion_playbook(
        title=hit.get("title") or "",
        excerpt=hit.get("excerpt") or "",
        author=author,
        site_name=site_name,
        site_url=short_link_url or destination_url,
        pitch_instruction=pitch_ins,
        platform=platform,
        credential=cred,
        offers_matrix=offers_matrix
    )

    subject = dm_res.get("subject", "Quick question / tip")
    message = dm_res.get("message", "")

    # Build official direct message compose URL
    import urllib.parse
    compose_url = ""
    if platform in ("x", "twitter"):
        clean_author = author.replace("@", "").strip()
        compose_url = f"https://x.com/{clean_author}" if clean_author and clean_author != "unknown" else "https://x.com/messages/compose"
    elif platform in ("forum", "vbulletin", "phpbb", "xenforo"):
        compose_url = hit.get("url") or ""
    else:
        clean_author = author.replace("u/", "").strip()
        encoded_sub = urllib.parse.quote(subject)
        encoded_msg = urllib.parse.quote(message)
        if clean_author and clean_author != "unknown":
            compose_url = f"https://www.reddit.com/message/compose?to={clean_author}&subject={encoded_sub}&message={encoded_msg}"
        else:
            compose_url = "https://www.reddit.com/message/compose"

    return {
        "ok": True,
        "author": author,
        "platform": platform,
        "subject": subject,
        "message": message,
        "short_url": short_link_url,
        "compose_url": compose_url,
        "routed_tool": routed_tool,
        "playbook": playbook
    }


@router.post("/api/queue/{item_id}/dm_pitch")
def api_queue_dm_pitch(item_id: int) -> dict:
    """Generate DM pitch and playbook directly from a queue item."""
    with get_db() as db:
        row = db.execute("SELECT * FROM reply_queue WHERE id=?", (item_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Queue item {item_id} not found"}
        item = dict(row)

    # Forward to api_hit_dm_pitch using the associated hit_id if available in hits table
    hit_id = item.get("hit_id")
    if hit_id:
        with get_db() as db:
            h_row = db.execute("SELECT id FROM hits WHERE hit_id=? OR id=?", (hit_id, hit_id)).fetchone()
            if h_row:
                return api_hit_dm_pitch(hit_id)

    # Fallback if no hit_id or hit not found in hits table
    cfg = load_config()
    cred = resolve_ai_cred(cfg, None)
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == item.get("listener_id")), None)
    offers_matrix = lst.get("offers_matrix") if lst else None

    from ai import generate_dm_pitch, generate_conversion_playbook, resolve_dynamic_tool_url
    base_dest = item.get("short_url") or (lst.get("site_url") if lst else "") or ""
    routed_tool = resolve_dynamic_tool_url(
        base_dest,
        f"{item.get('title', '')} {item.get('reply_text', '')}",
        offers_matrix=offers_matrix
    )
    destination_url = routed_tool.get("routed_url") or base_dest

    dm_res = generate_dm_pitch(
        title=f"Post {item.get('post_id', '')}",
        excerpt=item.get("reply_text", "")[:100],
        author=item.get("author", ""),
        site_name=item.get("listener_name", "My Product"),
        site_url=destination_url,
        platform=item.get("platform", "reddit"),
        credential=cred
    )
    playbook = generate_conversion_playbook(
        title=f"Post {item.get('post_id', '')}",
        excerpt=item.get("reply_text", "")[:100],
        author=item.get("author", ""),
        site_name=item.get("listener_name", "My Product"),
        site_url=destination_url,
        platform=item.get("platform", "reddit"),
        credential=cred,
        offers_matrix=offers_matrix
    )
    return {
        "ok": True,
        "author": item.get("author", ""),
        "platform": item.get("platform", "reddit"),
        "subject": dm_res.get("subject", ""),
        "message": dm_res.get("message", ""),
        "short_url": destination_url,
        "compose_url": f"https://www.reddit.com/message/compose?to={item.get('author', '')}",
        "routed_tool": routed_tool,
        "playbook": playbook
    }


@router.post("/api/hits/one_click_autopilot")
def api_one_click_autopilot(limit: int = 10) -> dict:
    """Batch one-click AI autopilot: generate drafts, filter safety, and enqueue eligible hits."""
    with get_db() as db:
        rows = db.execute(
            """SELECT h.hit_id FROM hits h
               LEFT JOIN reply_queue q ON h.hit_id = q.hit_id
               WHERE (h.filter_passed IS NULL OR h.filter_passed = 1) AND q.id IS NULL
               ORDER BY h.ts DESC LIMIT ?""",
            (limit,)
        ).fetchall()
        hit_ids = [r["hit_id"] for r in rows]

    processed = 0
    enqueued = 0
    needs_review = 0
    errors = []

    for hid in hit_ids:
        res = api_hit_one_click_engage(hid)
        if res.get("ok"):
            processed += 1
            if res.get("status") == "scheduled":
                enqueued += 1
            elif res.get("status") == "needs_review":
                needs_review += 1
        else:
            errors.append(res.get("error"))

    return {
        "ok": True,
        "processed_count": processed,
        "enqueued_count": enqueued,
        "needs_review_count": needs_review,
        "errors": errors
    }


class _AutopilotToggleReq(BaseModel):
    enabled: bool


@router.get("/api/config/autopilot")
def api_get_autopilot_status() -> dict:
    """Check if all enabled listeners have auto_submit_enabled."""
    cfg = load_config()
    listeners = [l for l in cfg.get("listeners", []) if l.get("enabled", True)]
    if not listeners:
        return {"enabled": False, "count": 0}
    is_all = all(l.get("auto_submit_enabled", False) for l in listeners)
    return {"enabled": is_all, "count": len(listeners)}


@router.post("/api/config/autopilot")
def api_toggle_autopilot(req: _AutopilotToggleReq) -> dict:
    """Turn autopilot on/off across all enabled listeners."""
    with get_db() as db:
        db.execute("UPDATE listeners SET auto_submit_enabled = ?, auto_reply_enabled = 1 WHERE enabled = 1", (1 if req.enabled else 0,))
    return {"ok": True, "enabled": req.enabled}


# ── Thread view ───────────────────────────────────────────────────────────────
@router.get("/api/reddit/thread")
def api_reddit_thread(post_id: str, listener_id: str = "") -> dict:
    cfg         = load_config()
    reddit_cred = None
    lst         = None
    if listener_id:
        lst = next((l for l in cfg.get("listeners", []) if l["id"] == listener_id), None)
        if lst:
            reddit_cred = next((c for c in cfg.get("credentials", [])
                                if c.get("id") == lst.get("reddit_credential_id")), None)
    if not reddit_cred:
        reddit_cred = next((c for c in cfg.get("credentials", []) if c.get("type") == "reddit"), None)

    # 优先从本地数据库获取该帖子/线索的基础信息作为兜底
    hit_info = None
    clean_id = post_id.replace("t3_", "").replace("t1_", "")
    t3_id = f"t3_{clean_id}"
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM hits WHERE post_id=? OR hit_id=? OR post_id=? OR hit_id=? ORDER BY id DESC LIMIT 1",
                (post_id, post_id, t3_id, clean_id)
            ).fetchone()
            if row:
                hit_info = dict(row)
    except Exception:
        pass

    # 若该线索属于 X (Twitter) 平台，直接格式化返回推文视图
    lst_platform = (lst.get("platform") or "") if lst else ""
    if hit_info:
        hit_platform = hit_info.get("platform") or ""
        hit_url = hit_info.get("url") or ""
        if hit_platform in ("x", "twitter") or "x.com" in hit_url or "twitter.com" in hit_url or lst_platform in ("x", "twitter"):
            return {
                "platform": "x",
                "post_id": post_id,
                "title": hit_info.get("title") or "𝕏 (Twitter) 推文",
                "selftext": hit_info.get("excerpt") or "",
                "author": hit_info.get("author") or "unknown",
                "subreddit": "x",
                "score": 1,
                "num_comments": 0,
                "url": hit_url or f"https://x.com/i/status/{clean_id}",
                "ts": hit_info.get("ts"),
                "created_at": hit_info.get("created_at"),
                "comments": [],
                "notice": "𝕏 平台推文线索。点击下方「Open on 𝕏」可直接在推特中查看并参与互动。"
            }
    elif lst_platform in ("x", "twitter") or (clean_id.isdigit() and len(clean_id) >= 15):
        return {
            "platform": "x",
            "post_id": post_id,
            "title": "𝕏 (Twitter) 推文",
            "selftext": "",
            "author": "tweet",
            "subreddit": "x",
            "score": 1,
            "num_comments": 0,
            "url": f"https://x.com/i/status/{clean_id}",
            "comments": [],
            "notice": "𝕏 平台推文线索。点击下方「Open on 𝕏」可直接在推特中查看并参与互动。"
        }

    if hit_info:
        return {
            "post_id": post_id,
            "title": hit_info.get("title") or "Reddit 讨论帖",
            "selftext": hit_info.get("excerpt") or "",
            "author": hit_info.get("author") or "unknown",
            "subreddit": hit_info.get("subreddit") or "",
            "score": 1,
            "num_comments": 0,
            "url": hit_info.get("url") or f"https://reddit.com/comments/{post_id}",
            "ts": hit_info.get("ts"),
            "created_at": hit_info.get("created_at"),
            "comments": [],
            "notice": "免 API 极速抓取模式。点击下方「Open on Reddit」可直接在原帖中查看与回复。"
        }
    return {
        "post_id": post_id,
        "title": "Reddit 讨论帖",
        "selftext": "",
        "author": "unknown",
        "subreddit": "",
        "score": 0,
        "num_comments": 0,
        "url": f"https://reddit.com/comments/{post_id}",
        "comments": [],
        "notice": "免 API 极速抓取模式。"
    }


# ── Notify ────────────────────────────────────────────────────────────────────
class _NotifyReq(BaseModel):
    listener_id:    str
    title:          str = ""
    url:            str = ""
    subreddit:      str = ""
    author:         str = ""
    match:          str = ""
    excerpt:        str = ""
    filter_results: list[dict] = []


@router.post("/api/notify")
def api_notify(req: _NotifyReq) -> dict:
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == req.listener_id), None)
    if not lst:
        return {"ok": False, "error": "Listener not found"}

    slack_url  = (lst.get("slack_webhook")      or "").strip()
    tg_token   = (lst.get("telegram_bot_token") or "").strip()
    tg_chat_id = (lst.get("telegram_chat_id")   or "").strip()
    sent: list[str] = []

    steps = "  ·  ".join(
        f"{'✅' if r.get('passed') else '❌'} {r['step']}"
        for r in req.filter_results if not r.get("skipped"))

    if slack_url:
        payload = {"blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"✅ Lead passed filter — r/{req.subreddit}"}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": f"*{req.title or '(comment)'}*\nby u/{req.author}  ·  keyword: `{req.match}`"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"_{req.excerpt[:280]}_"}},
            *([ {"type": "context", "elements": [{"type": "mrkdwn", "text": steps}]} ] if steps else []),
            {"type": "actions", "elements": [{"type": "button", "style": "primary",
                "text": {"type": "plain_text", "text": "👀 View on Reddit"}, "url": req.url}]},
        ]}
        queue_and_deliver(slack_url, payload, req.listener_id, lst.get("name", ""), "slack-ai")
        sent.append("slack")

    if tg_token and tg_chat_id:
        step_lines = "\n".join(f"{'✅' if r.get('passed') else '❌'} {r['step']}: {r.get('response','')[:60]}"
                                for r in req.filter_results if not r.get("skipped"))
        payload = {
            "chat_id": tg_chat_id, "parse_mode": "Markdown", "disable_web_page_preview": False,
            "text": (f"✅ *Lead passed filter — r/{req.subreddit}*\n\n"
                     f"*{req.title or '(comment)'}*\nby u/{req.author}\n\n"
                     f"Keyword: `{req.match}`\n_{req.excerpt[:280]}_"
                     + (f"\n\n{step_lines}" if step_lines else "")
                     + f"\n\n[Open on Reddit]({req.url})")
        }
        queue_and_deliver(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                          payload, req.listener_id, lst.get("name", ""), "telegram-ai")
        sent.append("telegram")

    return {"ok": True, "sent": sent}


# ── Health ────────────────────────────────────────────────────────────────────
@router.get("/api/health")
def api_health() -> dict:
    from monitor import _monitors
    now = time.time()
    with get_db() as db:
        rows = db.execute(
            "SELECT listener_id,listener_name,MAX(ts) as last_ts,"
            "SUM(CASE WHEN ts >= ? THEN 1 ELSE 0 END) as cnt_5m "
            "FROM hits GROUP BY listener_id", (now - 300,)).fetchall()
    stats: list[dict] = []
    seen:  set[str]   = set()
    for r in rows:
        lid = r["listener_id"] or ""
        seen.add(lid)
        stats.append({"listener_id": lid, "name": r["listener_name"] or lid[:8] or "?",
                       "running": lid in _monitors and _monitors[lid].is_alive(),
                       "last_ts": r["last_ts"], "per_min": round((r["cnt_5m"] or 0) / 5, 1)})
    cfg = load_config()
    for l in cfg.get("listeners", []):
        if l["id"] not in seen and l["id"] in _monitors and _monitors[l["id"]].is_alive():
            stats.append({"listener_id": l["id"], "name": l["name"],
                           "running": True, "last_ts": None, "per_min": 0.0})
    return {"listeners": stats, "now": now}


# ── Stats ─────────────────────────────────────────────────────────────────────
@router.get("/api/stats")
def api_stats(days: int = 30, project: str = "") -> dict:
    from datetime import datetime, timedelta, timezone
    cfg = load_config()
    listeners = cfg.get("listeners", [])

    hit_conds: list[str] = []
    hit_params: list     = []
    if days > 0:
        hit_conds.append(f"ts >= strftime('%s','now','-{days} days')")

    is_proj_filtered = bool(project and project != "all")
    proj_listener_ids = []
    if is_proj_filtered:
        proj_listener_ids = [
            l["id"] for l in listeners
            if (l.get("site_name") or l.get("name") or "").strip().lower() == project.strip().lower()
        ]
        if proj_listener_ids:
            ph = ",".join(["?"] * len(proj_listener_ids))
            hit_conds.append(f"(listener_id IN ({ph}) OR listener_name = ?)")
            hit_params.extend(list(proj_listener_ids) + [project])
        else:
            hit_conds.append("listener_name = ?")
            hit_params.append(project)

    def _where_clause(extra: str = "") -> str:
        c = list(hit_conds)
        if extra:
            c.append(extra)
        return ("WHERE " + " AND ".join(c)) if c else ""

    with get_db() as db:
        ov = db.execute(f"""SELECT COUNT(*) as total,
            SUM(CASE WHEN kind='post' THEN 1 ELSE 0 END) as posts,
            SUM(CASE WHEN kind='comment' THEN 1 ELSE 0 END) as comments,
            SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN filter_passed IS NOT NULL THEN 1 ELSE 0 END) as filtered,
            COUNT(DISTINCT subreddit) as unique_subs,
            COUNT(DISTINCT author) as unique_authors FROM hits {_where_clause()}""", hit_params).fetchone()

        tl_rows = db.execute(
            f"SELECT date(datetime(ts,'unixepoch')) as day,COUNT(*) as total,"
            f"SUM(CASE WHEN kind='post' THEN 1 ELSE 0 END) as posts,"
            f"SUM(CASE WHEN kind='comment' THEN 1 ELSE 0 END) as comments,"
            f"SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END) as passed "
            f"FROM hits {_where_clause()} GROUP BY day ORDER BY day", hit_params).fetchall()

        by_sub  = db.execute(f"SELECT subreddit,COUNT(*) as cnt,SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END) as passed FROM hits {_where_clause('subreddit IS NOT NULL AND subreddit != \'\'')} GROUP BY subreddit ORDER BY cnt DESC LIMIT 15", hit_params).fetchall()
        by_kw   = db.execute(f"SELECT LOWER(match_text) as kw,COUNT(*) as cnt FROM hits {_where_clause('match_text IS NOT NULL AND match_text != \'\'')} GROUP BY LOWER(match_text) ORDER BY cnt DESC LIMIT 15", hit_params).fetchall()
        by_lst  = db.execute(f"SELECT COALESCE(listener_name,'Unknown') as name,COUNT(*) as cnt,SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END) as passed,SUM(CASE WHEN filter_passed=0 THEN 1 ELSE 0 END) as rejected FROM hits {_where_clause()} GROUP BY listener_id ORDER BY cnt DESC", hit_params).fetchall()
        by_hour = db.execute(f"SELECT CAST(strftime('%H',datetime(ts,'unixepoch')) AS INTEGER) as hour,COUNT(*) as cnt FROM hits {_where_clause()} GROUP BY hour ORDER BY hour", hit_params).fetchall()
        by_dow  = db.execute(f"SELECT CAST(strftime('%w',datetime(ts,'unixepoch')) AS INTEGER) as dow,COUNT(*) as cnt FROM hits {_where_clause()} GROUP BY dow ORDER BY dow", hit_params).fetchall()
        by_month = db.execute("SELECT strftime('%Y-%m',datetime(ts,'unixepoch')) as month,COUNT(*) as total,SUM(CASE WHEN kind='post' THEN 1 ELSE 0 END) as posts,SUM(CASE WHEN kind='comment' THEN 1 ELSE 0 END) as comments,SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END) as passed FROM hits GROUP BY month ORDER BY month DESC LIMIT 24").fetchall()
        top_auth = db.execute(f"SELECT author,COUNT(*) as cnt,SUM(CASE WHEN kind='post' THEN 1 ELSE 0 END) as posts,SUM(CASE WHEN kind='comment' THEN 1 ELSE 0 END) as comments,SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END) as passed FROM hits {_where_clause('author IS NOT NULL AND author NOT IN (\'\',\'None\',\'[deleted]\')')} GROUP BY author ORDER BY cnt DESC LIMIT 10", hit_params).fetchall()
        sub_pass = db.execute(f"SELECT subreddit,COUNT(*) as cnt,ROUND(100.0*SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN filter_passed IS NOT NULL THEN 1 ELSE 0 END),0),1) as rate FROM hits {_where_clause('subreddit IS NOT NULL AND filter_passed IS NOT NULL')} GROUP BY subreddit HAVING cnt >= 3 ORDER BY rate DESC LIMIT 10", hit_params).fetchall()

        # ── Full Funnel & Attribution Analytics ──────────────────────────────
        q_conds: list[str] = []
        q_params: list     = []
        if is_proj_filtered:
            if proj_listener_ids:
                ph = ",".join(["?"] * len(proj_listener_ids))
                q_conds.append(f"(listener_id IN ({ph}) OR listener_name = ?)")
                q_params.extend(list(proj_listener_ids) + [project])
            else:
                q_conds.append("listener_name = ?")
                q_params.append(project)
        q_where = ("WHERE " + " AND ".join(q_conds)) if q_conds else ""

        l_conds: list[str] = []
        l_params: list     = []
        if is_proj_filtered:
            if proj_listener_ids:
                ph = ",".join(["?"] * len(proj_listener_ids))
                l_conds.append(f"(sl.listener_id IN ({ph}) OR rq.listener_name = ?)")
                l_params.extend(list(proj_listener_ids) + [project])
            else:
                l_conds.append("rq.listener_name = ?")
                l_params.append(project)
        l_where = ("WHERE " + " AND ".join(l_conds)) if l_conds else ""

        q_row = db.execute(f"""
            SELECT
                COUNT(*) as scheduled_total,
                COALESCE(SUM(CASE WHEN status IN ('submitted', 'sent', 'published') THEN 1 ELSE 0 END), 0) as published_total,
                COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END), 0) as pending_total,
                COALESCE(SUM(CASE WHEN status='needs_review' THEN 1 ELSE 0 END), 0) as review_total,
                COALESCE(SUM(CASE WHEN status IN ('submitted', 'sent', 'published') AND (upvotes >= 1 OR replies_count >= 1) THEN 1 ELSE 0 END), 0) as engaged_total,
                COALESCE(SUM(CASE WHEN is_winner=1 OR upvotes >= 3 THEN 1 ELSE 0 END), 0) as winners_total,
                COALESCE(SUM(CASE WHEN status IN ('submitted', 'sent', 'published') THEN upvotes ELSE 0 END), 0) as total_upvotes,
                COALESCE(SUM(CASE WHEN status IN ('submitted', 'sent', 'published') THEN replies_count ELSE 0 END), 0) as total_replies
            FROM reply_queue {q_where}
        """, q_params).fetchone()

        l_row = db.execute(f"""
            SELECT
                COUNT(sl.id) as total_links,
                COALESCE(SUM(sl.clicks), 0) as total_clicks
            FROM short_links sl
            LEFT JOIN reply_queue rq ON sl.queue_id = rq.id
            {l_where}
        """, l_params).fetchone()

        uv_row = db.execute(f"""
            SELECT COUNT(DISTINCT e.ip_hash) as total_uv
            FROM link_click_events e
            JOIN short_links sl ON sl.code = e.code
            LEFT JOIN reply_queue rq ON sl.queue_id = rq.id
            {l_where}
        """, l_params).fetchone()

        hits_captured = (ov["total"] or 0) if ov else 0
        ai_passed     = (ov["passed"] or 0) if ov else 0
        scheduled     = q_row["scheduled_total"] or 0 if q_row else 0
        published     = q_row["published_total"] or 0 if q_row else 0
        engaged       = q_row["engaged_total"] or 0 if q_row else 0
        winners       = q_row["winners_total"] or 0 if q_row else 0
        total_upvotes = q_row["total_upvotes"] or 0 if q_row else 0
        total_replies = q_row["total_replies"] or 0 if q_row else 0
        total_clicks  = l_row["total_clicks"] or 0 if l_row else 0
        total_uv      = uv_row["total_uv"] or 0 if uv_row else 0

        funnel = {
            "hits_captured": hits_captured,
            "ai_passed": ai_passed,
            "pass_rate": round(ai_passed / hits_captured * 100, 1) if hits_captured > 0 else 0.0,
            "scheduled": scheduled,
            "schedule_rate": round(scheduled / ai_passed * 100, 1) if ai_passed > 0 else 0.0,
            "published": published,
            "publish_rate": round(published / scheduled * 100, 1) if scheduled > 0 else 0.0,
            "engaged": engaged,
            "engagement_rate": round(engaged / published * 100, 1) if published > 0 else 0.0,
            "winners": winners,
            "total_upvotes": total_upvotes,
            "total_replies": total_replies,
            "total_clicks": total_clicks,
            "total_uv": total_uv,
            "ctr": round(total_clicks / published * 100, 1) if published > 0 else 0.0,
            "uv_rate": round(total_uv / total_clicks * 100, 1) if total_clicks > 0 else 0.0,
        }

        # ── Multi-project ROI Comparison Matrix ───────────────────────────────
        projects_dict: dict[str, dict] = {}
        for l in listeners:
            pname = (l.get("site_name") or l.get("name") or "Default Project").strip()
            if pname not in projects_dict:
                projects_dict[pname] = {
                    "name": pname,
                    "listener_ids": set(),
                    "platforms": set(),
                    "site_url": l.get("site_url", "")
                }
            projects_dict[pname]["listener_ids"].add(l["id"])
            projects_dict[pname]["platforms"].add(l.get("platform", "reddit"))

        extra_projs = db.execute("SELECT DISTINCT listener_name FROM hits WHERE listener_name IS NOT NULL AND listener_name != ''").fetchall()
        for ep in extra_projs:
            pname = ep["listener_name"].strip()
            if pname and pname not in projects_dict:
                projects_dict[pname] = {
                    "name": pname,
                    "listener_ids": set(),
                    "platforms": {"reddit"},
                    "site_url": ""
                }

        projects_roi = []
        for pname, pinfo in projects_dict.items():
            l_ids = list(pinfo["listener_ids"])
            if l_ids:
                p_ph = ",".join(["?"] * len(l_ids))
                p_h_w = f"WHERE (listener_id IN ({p_ph}) OR listener_name = ?)"
                p_params = l_ids + [pname]
                p_link_w = f"WHERE (sl.listener_id IN ({p_ph}) OR rq.listener_name = ?)"
            else:
                p_h_w = "WHERE listener_name = ?"
                p_params = [pname]
                p_link_w = "WHERE rq.listener_name = ?"

            p_h = db.execute(f"SELECT COUNT(*) as h_cnt, COALESCE(SUM(CASE WHEN filter_passed=1 THEN 1 ELSE 0 END), 0) as p_cnt FROM hits {p_h_w}", p_params).fetchone()
            p_q = db.execute(f"SELECT COUNT(*) as sch_cnt, COALESCE(SUM(CASE WHEN status IN ('submitted', 'sent', 'published') THEN 1 ELSE 0 END), 0) as sent_cnt, COALESCE(SUM(upvotes), 0) as up_cnt, COALESCE(SUM(CASE WHEN is_winner=1 OR upvotes >= 3 THEN 1 ELSE 0 END), 0) as win_cnt FROM reply_queue {p_h_w}", p_params).fetchone()
            p_l_clk = db.execute(f"SELECT COALESCE(SUM(sl.clicks), 0) as clk_cnt FROM short_links sl LEFT JOIN reply_queue rq ON sl.queue_id = rq.id {p_link_w}", p_params).fetchone()
            p_l_uv = db.execute(f"SELECT COUNT(DISTINCT e.ip_hash) as uv_cnt FROM link_click_events e JOIN short_links sl ON sl.code = e.code LEFT JOIN reply_queue rq ON sl.queue_id = rq.id {p_link_w}", p_params).fetchone()

            h_cnt = (p_h["h_cnt"] or 0) if p_h else 0
            pass_cnt = (p_h["p_cnt"] or 0) if p_h else 0
            sent_cnt = (p_q["sent_cnt"] or 0) if p_q else 0
            up_cnt = (p_q["up_cnt"] or 0) if p_q else 0
            win_cnt = (p_q["win_cnt"] or 0) if p_q else 0
            clk_cnt = (p_l_clk["clk_cnt"] or 0) if p_l_clk else 0
            uv_cnt = (p_l_uv["uv_cnt"] or 0) if p_l_uv else 0
            p_ctr = round(clk_cnt / sent_cnt * 100, 1) if (sent_cnt and sent_cnt > 0) else 0.0

            projects_roi.append({
                "name": pname,
                "hits": h_cnt,
                "passed": pass_cnt,
                "published": sent_cnt,
                "upvotes": up_cnt,
                "winners": win_cnt,
                "clicks": clk_cnt,
                "uv": uv_cnt,
                "ctr": p_ctr,
                "platforms": sorted(list(pinfo["platforms"])),
                "site_url": pinfo["site_url"]
            })

        projects_roi.sort(key=lambda x: (x["clicks"], x["upvotes"], x["hits"]), reverse=True)

        # ── Top Attributed Links ──────────────────────────────────────────────
        top_links_rows = db.execute(f"""
            SELECT sl.code, sl.target_url, sl.final_url, sl.clicks, sl.platform,
                   COUNT(DISTINCT e.ip_hash) as uv,
                   rq.upvotes, rq.is_winner, rq.subreddit, rq.comment_url, rq.author
            FROM short_links sl
            LEFT JOIN link_click_events e ON sl.code = e.code
            LEFT JOIN reply_queue rq ON sl.queue_id = rq.id
            {l_where}
            GROUP BY sl.id
            ORDER BY sl.clicks DESC, uv DESC
            LIMIT 10
        """, l_params).fetchall()
        top_links = [dict(r) for r in top_links_rows]

    tl_map   = {r["day"]: dict(r) for r in tl_rows}
    timeline = []
    if days > 0:
        start = datetime.now(timezone.utc) - timedelta(days=days - 1)
        for i in range(days):
            d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            timeline.append(tl_map.get(d, {"day": d, "total": 0, "posts": 0, "comments": 0, "passed": 0}))
    else:
        timeline = [dict(r) for r in tl_rows]

    h_map    = {r["hour"]: r["cnt"] for r in by_hour}
    d_map    = {r["dow"]:  r["cnt"] for r in by_dow}
    total    = ov["total"] or 0
    filtered = ov["filtered"] or 0
    passed_n = ov["passed"] or 0

    return {
        "overview": {"total": total, "posts": ov["posts"] or 0, "comments": ov["comments"] or 0,
                     "passed": passed_n, "filtered": filtered,
                     "pass_rate": round(passed_n / filtered * 100, 1) if filtered > 0 else None,
                     "unique_subs": ov["unique_subs"] or 0, "unique_authors": ov["unique_authors"] or 0},
        "funnel":       funnel,
        "projects_roi": projects_roi,
        "top_links":    top_links,
        "timeline":     timeline,
        "by_subreddit": [{"name": r["subreddit"], "count": r["cnt"], "passed": r["passed"] or 0} for r in by_sub],
        "by_keyword":   [{"keyword": r["kw"], "count": r["cnt"]} for r in by_kw],
        "by_listener":  [{"name": r["name"], "count": r["cnt"], "passed": r["passed"] or 0, "rejected": r["rejected"] or 0} for r in by_lst],
        "by_hour":      [{"hour": h, "count": h_map.get(h, 0)} for h in range(24)],
        "by_dow":       [{"dow": d, "count": d_map.get(d, 0)} for d in range(7)],
        "by_month":     [{"month": r["month"], "total": r["total"], "posts": r["posts"] or 0, "comments": r["comments"] or 0, "passed": r["passed"] or 0} for r in by_month],
        "top_authors":  [{"author": r["author"], "count": r["cnt"], "posts": r["posts"] or 0, "comments": r["comments"] or 0, "passed": r["passed"] or 0} for r in top_auth],
        "sub_pass":     [{"name": r["subreddit"], "rate": r["rate"], "count": r["cnt"]} for r in sub_pass],
    }


# ── Logs ──────────────────────────────────────────────────────────────────────
@router.get("/api/logs/system")
def api_system_logs(level: str = "", source: str = "", listener_id: str = "",
                    limit: int = 100, offset: int = 0) -> dict:
    conds: list[str] = []
    params: list     = []
    if level:       conds.append("level=?");       params.append(level)
    if source:      conds.append("source=?");      params.append(source)
    if listener_id: conds.append("listener_id=?"); params.append(listener_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM system_log {where}", params).fetchone()[0]
        rows  = db.execute(f"SELECT * FROM system_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                            params + [limit, offset]).fetchall()
    return {
        "logs": [{"id": r["id"], "level": r["level"], "source": r["source"],
                  "listener_id": r["listener_id"], "listener_name": r["listener_name"],
                  "message": r["message"], "created_at": r["created_at"]} for r in rows],
        "total": total,
    }


@router.get("/api/logs/webhooks")
def api_webhook_logs(status: str = "", listener_id: str = "",
                     limit: int = 100, offset: int = 0) -> dict:
    conds: list[str] = []
    params: list     = []
    if status:      conds.append("status=?");      params.append(status)
    if listener_id: conds.append("listener_id=?"); params.append(listener_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM webhook_log {where}", params).fetchone()[0]
        rows  = db.execute(f"SELECT * FROM webhook_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                            params + [limit, offset]).fetchall()
    return {
        "logs": [{"id": r["id"], "listener_id": r["listener_id"], "listener_name": r["listener_name"],
                  "wtype": r["wtype"],
                  "url": (r["url"] or "")[:60] + "…" if len(r["url"] or "") > 60 else r["url"],
                  "status": r["status"], "attempts": r["attempts"], "last_error": r["last_error"],
                  "created_at": r["created_at"], "delivered_at": r["delivered_at"]} for r in rows],
        "total": total,
    }


@router.post("/api/logs/webhooks/{log_id}/retry")
def api_retry_webhook(log_id: int) -> dict:
    with get_db() as db:
        row = db.execute("SELECT * FROM webhook_log WHERE id=?", (log_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "Not found"}
    try:
        r = _http.post(row["url"], data=row["payload"],
                       headers={"Content-Type": "application/json"}, timeout=10)
        r.raise_for_status()
        with get_db() as db:
            db.execute("UPDATE webhook_log SET status='success',attempts=attempts+1,"
                       "delivered_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (log_id,))
        db_log("info", "webhook", f"Manual retry succeeded [{row['wtype']}]",
               row["listener_id"], row["listener_name"])
        return {"ok": True}
    except Exception as exc:
        with get_db() as db:
            db.execute("UPDATE webhook_log SET attempts=attempts+1,last_error=? WHERE id=?",
                       (str(exc)[:500], log_id))
        return {"ok": False, "error": str(exc)}


class _CleanupLogsReq(BaseModel):
    days: int = 7
    max_records: int = 5000


@router.post("/api/logs/cleanup")
def api_cleanup_logs(req: _CleanupLogsReq | None = None) -> dict:
    days = req.days if req and req.days is not None else 7
    max_records = req.max_records if req and req.max_records is not None else 5000
    from db import cleanup_old_logs
    res = cleanup_old_logs(days=days, max_records=max_records)
    return {"ok": True, **res}



# ── Settings ──────────────────────────────────────────────────────────────────
@router.get("/api/settings/{key}")
def api_get_setting(key: str) -> dict:
    return {"value": get_setting(key)}


@router.put("/api/settings/{key}")
def api_set_setting(key: str, payload: dict) -> dict:
    set_setting(key, payload.get("value", ""))
    return {"ok": True}


# ── File logs ─────────────────────────────────────────────────────────────────
@router.get("/api/logs")
def api_file_logs(lines: int = 200) -> dict:
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    def _tail(f: Path) -> list[str]:
        if not f.exists(): return []
        return f.read_text(errors="replace").splitlines()[-lines:]
    return {"available": (log_dir / "out.log").exists() or (log_dir / "err.log").exists(),
            "stdout": _tail(log_dir / "out.log"), "stderr": _tail(log_dir / "err.log")}


# ── Barnacle SEO (藤壶 SEO 长效截流板块) ───────────────────────────────────────

class _BarnacleScanReq(BaseModel):
    keyword: str
    max_results: int = 15


class _BarnacleHuntReq(BaseModel):
    keyword: str
    max_results: int = 8
    auto_draft: bool = False


class _BarnacleAddReq(BaseModel):
    url: str
    keyword: str
    notes: str = ""


class _BarnacleDraftReq(BaseModel):
    custom_instruction: str = ""


class _BarnacleUpdateReq(BaseModel):
    status: str | None = None
    reply_url: str | None = None
    notes: str | None = None
    evergreen_draft: str | None = None


@router.get("/api/barnacle/targets")
def api_barnacle_targets() -> dict:
    with get_db() as db:
        rows = db.execute("SELECT * FROM barnacle_targets ORDER BY CASE WHEN google_rank > 0 THEN google_rank ELSE 9999 END ASC, opportunity_score DESC, id DESC").fetchall()
        targets = [dict(r) for r in rows]

        stats_row = db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_archived = 0 THEN 1 ELSE 0 END) as active_count,
                SUM(CASE WHEN is_archived = 1 THEN 1 ELSE 0 END) as archived_count,
                SUM(CASE WHEN status = 'drafted' THEN 1 ELSE 0 END) as drafted_count,
                SUM(CASE WHEN status = 'submitted' THEN 1 ELSE 0 END) as submitted_count
            FROM barnacle_targets
        """).fetchone()

        stats = {
            "total": stats_row["total"] or 0,
            "active": stats_row["active_count"] or 0,
            "archived": stats_row["archived_count"] or 0,
            "drafted": stats_row["drafted_count"] or 0,
            "submitted": stats_row["submitted_count"] or 0
        }

    return {"ok": True, "targets": targets, "stats": stats}


@router.post("/api/barnacle/scan")
def api_barnacle_scan(req: _BarnacleScanReq) -> dict:
    from barnacle import search_serp_targets
    try:
        results = search_serp_targets(req.keyword, max_results=req.max_results)
        return {"ok": True, "count": len(results), "targets": results}
    except Exception as e:
        return {"ok": False, "error": f"SERP 扫描失败: {e}"}


@router.post("/api/barnacle/hunt")
def api_barnacle_hunt(req: _BarnacleHuntReq) -> dict:
    from barnacle import hunt_and_auto_draft_barnacle
    try:
        results = hunt_and_auto_draft_barnacle(req.keyword, max_results=req.max_results, auto_draft=req.auto_draft)
        return {"ok": True, "count": len(results), "targets": results}
    except Exception as e:
        return {"ok": False, "error": f"Google SERP 讨论帖猎金失败: {e}"}


@router.post("/api/barnacle/add")
def api_barnacle_add(req: _BarnacleAddReq) -> dict:
    from barnacle import inspect_target_health, clean_reddit_url
    url = clean_reddit_url(req.url.strip())
    if not url:
        return {"ok": False, "error": "无效的目标帖子 URL"}

    try:
        health = inspect_target_health(url)
        title = health.get("title") or req.keyword
        author = health.get("author") or ""
        is_archived = 1 if health.get("is_archived") else 0
        created_at_utc = health.get("post_created_at") or 0
        platform = health.get("platform") or "reddit"
        score = 80 if not is_archived else 50
        now = time.time()

        with get_db() as db:
            cur = db.execute(
                """INSERT INTO barnacle_targets
                   (keyword, target_url, platform, post_title, google_rank, search_snippet,
                    author, post_created_at, is_archived, opportunity_score, notes, updated_at)
                   VALUES (?, ?, ?, ?, 1, '手动添加高价值目标', ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(target_url) DO UPDATE SET
                       keyword=excluded.keyword,
                       post_title=COALESCE(NULLIF(excluded.post_title, ''), post_title),
                       is_archived=excluded.is_archived,
                       notes=COALESCE(NULLIF(excluded.notes, ''), notes),
                       updated_at=excluded.updated_at""",
                (req.keyword, url, platform, title, author, created_at_utc, is_archived, score, req.notes, now)
            )
            existing = db.execute("SELECT id FROM barnacle_targets WHERE target_url=?", (url,)).fetchone()
            row_id = existing["id"] if existing else cur.lastrowid

        return {"ok": True, "id": row_id, "url": url, "is_archived": bool(is_archived)}
    except Exception as e:
        return {"ok": False, "error": f"添加目标失败: {e}"}


@router.post("/api/barnacle/targets/{target_id}/draft")
def api_barnacle_generate_draft(target_id: int, req: _BarnacleDraftReq) -> dict:
    from barnacle import generate_evergreen_barnacle_reply
    cfg = load_config()
    first_lst = cfg.get("listeners", [{}])[0] if cfg.get("listeners") else {}
    site_name = first_lst.get("site_name") or first_lst.get("name") or "Fairway Fort"
    site_url = first_lst.get("site_url") or "https://fairwayfort.com/pages/tools"
    site_desc = first_lst.get("site_description") or "Specialized Tools & Equipment"

    try:
        draft = generate_evergreen_barnacle_reply(
            target_id=target_id,
            site_name=site_name,
            site_url=site_url,
            site_desc=site_desc,
            custom_instruction=req.custom_instruction
        )
        return {"ok": True, "draft": draft}
    except Exception as e:
        return {"ok": False, "error": f"生成常青树草稿失败: {e}"}


@router.post("/api/barnacle/targets/{target_id}/update")
def api_barnacle_update_target(target_id: int, req: _BarnacleUpdateReq) -> dict:
    fields = []
    params = []
    if req.status is not None:
        fields.append("status=?")
        params.append(req.status)
    if req.reply_url is not None:
        fields.append("reply_url=?")
        params.append(req.reply_url)
    if req.notes is not None:
        fields.append("notes=?")
        params.append(req.notes)
    if req.evergreen_draft is not None:
        fields.append("evergreen_draft=?")
        params.append(req.evergreen_draft)

    if not fields:
        return {"ok": True}

    fields.append("updated_at=?")
    params.append(time.time())
    params.append(target_id)

    with get_db() as db:
        db.execute(f"UPDATE barnacle_targets SET {', '.join(fields)} WHERE id=?", params)

    return {"ok": True}


@router.delete("/api/barnacle/targets/{target_id}")
def api_barnacle_delete_target(target_id: int) -> dict:
    with get_db() as db:
        db.execute("DELETE FROM barnacle_targets WHERE id=?", (target_id,))
    return {"ok": True}


class _BarnacleAuditReq(BaseModel):
    type: str = "all"  # 'replies', 'targets', 'all'
    limit: int = 20
    fast: bool = False


@router.post("/api/barnacle/audit")
def api_barnacle_audit(req: _BarnacleAuditReq = None) -> dict:
    from barnacle import audit_sent_replies, audit_barnacle_targets
    req = req or _BarnacleAuditReq()
    limit = req.limit or 20
    audit_type = req.type or "all"
    skip_net = bool(req.fast)

    replies = []
    targets = []
    if audit_type in ("all", "replies"):
        replies = audit_sent_replies(limit=limit, skip_network=skip_net)
    if audit_type in ("all", "targets"):
        targets = audit_barnacle_targets(limit=limit, skip_network=skip_net)

    return {
        "ok": True,
        "replies": replies,
        "targets": targets,
        "total_audited": len(replies) + len(targets),
        "fast": skip_net,
    }


@router.get("/api/skill")
def api_get_skill() -> dict:
    skill_path = Path("/Users/han/redsignal/SKILL.md")
    if not skill_path.exists():
        skill_path = Path("/Users/han/.claude/skills/redsignal/SKILL.md")
    content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    return {
        "ok": True,
        "name": "redsignal",
        "description": "RedSignal 极简 Agentic 社媒截流雷达、全品类营销/联盟转化中枢与智能发帖控制台",
        "url": "https://s.hanzhe.dpdns.org/SKILL.md",
        "content": content,
        "updated_at": "2026-10-01",
    }


# ── DM Inbox & Multi-Round Conversational Monitor ────────────────────────────
class _InboxPollReq(BaseModel):
    platform: str = "all"  # 'all', 'reddit', 'x'
    dry_run: bool = True


class _InboxReplyReq(BaseModel):
    conversation_id: int
    custom_text: str | None = None
    dry_run: bool = False


class _InboxUpdateReq(BaseModel):
    status: str | None = None
    current_round: int | None = None
    last_outbound_msg: str | None = None


class _InboxConfigReq(BaseModel):
    autopilot_enabled: bool | None = None
    dry_run: bool | None = None


@router.get("/api/inbox/conversations")
def api_inbox_conversations(
    platform: str = "all",
    status: str = "all",
    limit: int = 50
) -> dict:
    with get_db() as db:
        where_clauses = []
        params = []
        if platform != "all":
            where_clauses.append("platform = ?")
            params.append(platform)
        if status != "all":
            where_clauses.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"SELECT * FROM dm_conversations {where_sql} ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(limit)

        rows = db.execute(query, params).fetchall()
        conversations = [dict(r) for r in rows]

        stats_row = db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status != 'closed' THEN 1 ELSE 0 END) as active_count,
                SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) as replied_count,
                SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_count,
                SUM(CASE WHEN platform = 'reddit' THEN 1 ELSE 0 END) as reddit_count,
                SUM(CASE WHEN platform = 'x' THEN 1 ELSE 0 END) as x_count
            FROM dm_conversations
        """).fetchone()

        stats = {
            "total": stats_row["total"] or 0,
            "active": stats_row["active_count"] or 0,
            "replied": stats_row["replied_count"] or 0,
            "closed": stats_row["closed_count"] or 0,
            "reddit": stats_row["reddit_count"] or 0,
            "x": stats_row["x_count"] or 0,
        }

    return {"ok": True, "conversations": conversations, "stats": stats}


@router.post("/api/inbox/poll")
def api_inbox_poll(req: _InboxPollReq = None) -> dict:
    from dm_agent import poll_and_respond_all_inboxes, poll_and_respond_reddit_inbox, poll_and_respond_x_inbox
    req = req or _InboxPollReq()
    try:
        if req.platform == "reddit":
            results = poll_and_respond_reddit_inbox(dry_run=req.dry_run)
        elif req.platform in ("x", "twitter"):
            results = poll_and_respond_x_inbox(dry_run=req.dry_run)
        else:
            results = poll_and_respond_all_inboxes(dry_run=req.dry_run)
        return {
            "ok": True,
            "results": results,
            "count": len(results),
            "dry_run": req.dry_run,
            "platform": req.platform
        }
    except Exception as e:
        return {"ok": False, "error": f"轮询私信失败: {e}"}


@router.post("/api/inbox/reply")
def api_inbox_reply(req: _InboxReplyReq) -> dict:
    import urllib.parse
    from dm_agent import draft_automated_reply, send_bark_dm_alert
    with get_db() as db:
        conv = db.execute("SELECT * FROM dm_conversations WHERE id = ?", (req.conversation_id,)).fetchone()
        if not conv:
            return {"ok": False, "error": "未找到对应的私信会话"}
        conv = dict(conv)

    handle = conv["partner_handle"]
    platform = conv["platform"]
    curr_round = conv.get("current_round", 1)
    inbound_text = conv.get("last_inbound_msg", "")

    # Draft reply
    reply_text = req.custom_text
    if not reply_text:
        reply_text = draft_automated_reply(
            partner_handle=handle,
            inbound_text=inbound_text,
            target_round=curr_round,
            platform=platform
        )

    # Compose official direct URL as safe fallback
    compose_url = ""
    if platform == "reddit":
        clean_user = handle.replace("u/", "").strip()
        sub = urllib.parse.quote_plus(conv.get("subject") or "Follow-up")
        msg = urllib.parse.quote_plus(reply_text)
        compose_url = f"https://www.reddit.com/message/compose?to={clean_user}&subject={sub}&message={msg}"
    else:
        clean_user = handle.replace("@", "").strip()
        compose_url = f"https://x.com/messages/compose?recipient_id={clean_user}" if clean_user else "https://x.com/messages"

    now = time.time()
    with get_db() as db:
        db.execute(
            """UPDATE dm_conversations
               SET last_outbound_msg = ?,
                   status = 'replied',
                   current_round = MIN(current_round + 1, 3),
                   updated_at = ?
               WHERE id = ?""",
            (reply_text, now, req.conversation_id)
        )

    # Send Bark alert
    send_bark_dm_alert(
        f"RedSignal Web 私信攻坚: {platform.upper()} {handle}",
        f"发送话术 (Round {curr_round}):\n{reply_text[:100]}..."
    )

    return {
        "ok": True,
        "reply_text": reply_text,
        "compose_url": compose_url,
        "dry_run": req.dry_run,
        "next_round": min(curr_round + 1, 3)
    }


@router.post("/api/inbox/conversations/{conv_id}/update")
def api_inbox_update_conversation(conv_id: int, req: _InboxUpdateReq) -> dict:
    fields = []
    params = []
    if req.status is not None:
        fields.append("status = ?")
        params.append(req.status)
    if req.current_round is not None:
        fields.append("current_round = ?")
        params.append(req.current_round)
    if req.last_outbound_msg is not None:
        fields.append("last_outbound_msg = ?")
        params.append(req.last_outbound_msg)

    if not fields:
        return {"ok": True}

    fields.append("updated_at = ?")
    params.append(time.time())
    params.append(conv_id)

    with get_db() as db:
        db.execute(f"UPDATE dm_conversations SET {', '.join(fields)} WHERE id = ?", params)

    return {"ok": True}


@router.delete("/api/inbox/conversations/{conv_id}")
def api_inbox_delete_conversation(conv_id: int) -> dict:
    with get_db() as db:
        db.execute("DELETE FROM dm_conversations WHERE id = ?", (conv_id,))
    return {"ok": True}


@router.get("/api/inbox/config")
def api_inbox_get_config() -> dict:
    return {
        "ok": True,
        "autopilot_enabled": get_setting("dm_autopilot_enabled") == "1",
        "dry_run": get_setting("dm_autopilot_dry_run", "1") == "1",
    }


@router.post("/api/inbox/config")
def api_inbox_set_config(req: _InboxConfigReq) -> dict:
    if req.autopilot_enabled is not None:
        set_setting("dm_autopilot_enabled", "1" if req.autopilot_enabled else "0")
    if req.dry_run is not None:
        set_setting("dm_autopilot_dry_run", "1" if req.dry_run else "0")
    return {"ok": True}


@router.get("/api/doctor")
def api_doctor() -> dict:
    from dm_agent import check_session_health
    try:
        diagnostics = check_session_health()
        all_healthy = all(d.get("status") == "healthy" for d in diagnostics)
        return {
            "ok": True,
            "diagnostics": diagnostics,
            "all_healthy": all_healthy
        }
    except Exception as e:
        return {"ok": False, "error": f"体检异常: {e}", "diagnostics": []}



# ── AI Health Analytics & Dynamic Self-Healing ─────────────────────────────────
@router.get("/api/analytics/ai_health")
def api_ai_health_analytics() -> dict:
    """Comprehensive AI engine health, dynamic persona distribution, and self-healing memory status."""
    import datetime, zoneinfo
    cfg = load_config()
    first_lst = (cfg.get("listeners") or [{}])[0]
    tz_str = first_lst.get("schedule_timezone") or "America/New_York"
    start_h = int(first_lst.get("schedule_start", 7))
    end_h = int(first_lst.get("schedule_end", 22))

    try:
        target_tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        target_tz = zoneinfo.ZoneInfo("America/New_York")
    now_tz = datetime.datetime.now(target_tz)
    hour = now_tz.hour
    minute = now_tz.minute
    tz_abbr = now_tz.strftime("%Z") or tz_str
    is_daytime = (hour > start_h or (hour == start_h and minute >= 30)) and hour < end_h

    with get_db() as db:
        # Persona counts
        persona_counts = {}
        for r in db.execute("SELECT persona_label, COUNT(*) as cnt FROM hits WHERE reply_draft IS NOT NULL GROUP BY persona_label"):
            persona_counts[r["persona_label"]] = r["cnt"]

        # Safety audit pass stats
        row_safety = db.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN safety_verdict='PASSED' THEN 1 ELSE 0 END) as passed FROM hits WHERE safety_verdict IS NOT NULL"
        ).fetchone()
        safety_total = row_safety["total"] if row_safety else 0
        safety_passed = row_safety["passed"] if (row_safety and row_safety["passed"]) else 0
        safety_rate = round((safety_passed / safety_total * 100), 1) if safety_total > 0 else 100.0

        # AutoMod visibility penetration stats
        row_vis = db.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN visibility_status='visible' THEN 1 ELSE 0 END) as vis FROM reply_queue WHERE status='submitted'"
        ).fetchone()
        vis_total = row_vis["total"] if row_vis else 0
        vis_passed = row_vis["vis"] if (row_vis and row_vis["vis"]) else 0
        vis_rate = round((vis_passed / vis_total * 100), 1) if vis_total > 0 else 100.0

        # Self-healing rules
        learnings_rows = db.execute("SELECT * FROM ai_learnings ORDER BY id DESC LIMIT 10").fetchall()
        learnings = [dict(r) for r in learnings_rows]

    return {
        "ok": True,
        "chrono": {
            "timezone": tz_str,
            "tz_abbr": tz_abbr,
            "current_est_time": now_tz.strftime(f"%H:%M {tz_abbr}"),
            "is_peak": is_daytime,
            "window_desc": f"🔥 {tz_abbr} 活跃黄金期 ({start_h:02d}:30 - {end_h:02d}:00 {tz_abbr})" if is_daytime else f"🌙 {tz_abbr} 深夜静音防封期 ({end_h:02d}:00 - {start_h:02d}:30 {tz_abbr})",
            "policy": "敏捷抢楼 (3~8分钟递送)" if is_daytime else f"智能顺延至早间 {start_h:02d}:45 晨峰发射"
        },
        "personas": persona_counts,
        "safety_audit": {
            "total_audited": safety_total,
            "passed_count": safety_passed,
            "pass_rate": safety_rate
        },
        "automod_penetration": {
            "total_submitted": vis_total,
            "visible_count": vis_passed,
            "penetration_rate": vis_rate
        },
        "self_healing_rules": learnings,
        "self_healing_rules_count": len(learnings)
    }


@router.get("/api/ai/learnings")
def api_get_ai_learnings(limit: int = 20) -> dict:
    """List dynamic self-healing anti-ban rules accumulated by AI."""
    with get_db() as db:
        rows = db.execute("SELECT * FROM ai_learnings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {"ok": True, "learnings": [dict(r) for r in rows]}


# ── Short Link Attribution & ROI Tracking ────────────────────────────────────
@router.get("/r/{code}")
@router.head("/r/{code}")
def api_resolve_short_link(code: str, request: Request):
    """302 Attribution Redirect with Click Counter & Unique IP Hashing."""
    with get_db() as db:
        row = db.execute("SELECT * FROM short_links WHERE code=?", (code,)).fetchone()
        if not row:
            return RedirectResponse(url="https://fairwayfort.com/pages/tools", status_code=302)

        # Increment total click counter
        db.execute(
            """UPDATE short_links
               SET clicks = clicks + 1,
                   last_clicked_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')
               WHERE code = ?""",
            (code,)
        )

        # Hash client IP for privacy-preserving deduplicated UV counting
        client_ip = (request.client.host if request.client else "") or "unknown"
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            client_ip = fwd.split(",")[0].strip()
        ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]
        user_agent = request.headers.get("user-agent", "")[:250]
        referer = request.headers.get("referer", "")[:250]

        db.execute(
            """INSERT INTO link_click_events (code, ip_hash, user_agent, referer)
               VALUES (?, ?, ?, ?)""",
            (code, ip_hash, user_agent, referer)
        )

        final_url = row["final_url"] or row["target_url"] or "/"

        # Dynamic Context Parameter Forwarding:
        # Merge any incoming request query params (e.g. ?intent=..., &state=...) into the destination URL
        if request.query_params:
            try:
                import urllib.parse as _up
                parsed = _up.urlparse(final_url)
                params = dict(_up.parse_qsl(parsed.query))
                for k, v in request.query_params.items():
                    params[k] = v
                new_query = _up.urlencode(params)
                final_url = _up.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
            except Exception:
                pass

        return RedirectResponse(url=final_url, status_code=302)


# ── Zero-Party Data Lead Magnet & Inbound Capture ───────────────────────────
class _CaptureLeadReq(BaseModel):
    email: str
    short_code: str | None = None
    source: str = "lead_magnet"
    intent: str | None = None
    state: str | None = None
    cart_model: str | None = None


@router.post("/api/leads/capture")
def api_capture_lead(req: _CaptureLeadReq, request: Request) -> dict:
    """Zero-party data lead capture endpoint for landing page lead magnets and tools."""
    email = req.email.strip()
    if not email or "@" not in email:
        return {"ok": False, "error": "Invalid email address"}

    client_ip = (request.client.host if request.client else "") or "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        client_ip = fwd.split(",")[0].strip()
    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]

    hit_id = None
    queue_id = None
    if req.short_code:
        with get_db() as db:
            sl = db.execute("SELECT hit_id, queue_id FROM short_links WHERE code=?", (req.short_code,)).fetchone()
            if sl:
                hit_id = sl["hit_id"]
                queue_id = sl["queue_id"]

    with get_db() as db:
        cur = db.execute(
            """INSERT INTO leads (email, source, hit_id, queue_id, short_code, intent, state, cart_model, ip_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email, req.source, hit_id, queue_id, req.short_code, req.intent, req.state, req.cart_model, ip_hash)
        )
        lead_id = cur.lastrowid

    db_log("info", "lead_magnet", f"🎯 零方数据捕获: 收到潜客邮箱 {email} [Code: {req.short_code or 'none'}, State: {req.state or 'any'}]")

    # Instant Telegram alert to admin about inbound lead
    try:
        cfg = load_config()
        first_listener = next((l for l in cfg.get("listeners", []) if l.get("telegram_bot_token") and l.get("telegram_chat_id")), None)
        if first_listener:
            from telegram_bot import telegram_api_call
            tok = first_listener["telegram_bot_token"]
            cid = first_listener["telegram_chat_id"]
            msg = (
                f"📬 *[新潜客线索捕获 Inbound Lead]*\n\n"
                f"📧 邮箱: `{email}`\n"
                f"🏷️ 来源: `{req.source}`\n"
                f"📍 州/地区: `{req.state or '未指定'}`\n"
                f"🏎️ 需求/型号: `{req.cart_model or req.intent or '未指定'}`\n"
                f"🔗 短链归因码: `{req.short_code or 'Direct'}`\n"
                f"⏱️ 捕获时间: `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            telegram_api_call(tok, "sendMessage", {
                "chat_id": cid,
                "text": msg,
                "parse_mode": "Markdown"
            })
    except Exception:
        pass

    return {
        "ok": True,
        "lead_id": lead_id,
        "message": "Lead captured successfully"
    }


@router.get("/api/leads")
def api_get_leads(limit: int = 50, offset: int = 0) -> dict:
    """Retrieve captured leads with attribution data."""
    with get_db() as db:
        rows = db.execute(
            """SELECT l.*, sl.platform, sl.target_url, sl.persona
               FROM leads l
               LEFT JOIN short_links sl ON l.short_code = sl.code
               ORDER BY l.id DESC
               LIMIT ? OFFSET ?""",
            (limit, offset)
        ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    return {
        "ok": True,
        "total": total,
        "leads": [dict(r) for r in rows]
    }


@router.get("/api/analytics/links")
def api_get_links_analytics(limit: int = 50) -> dict:
    """Attribution & Link Click Performance Analytics."""
    with get_db() as db:
        rows = db.execute(
            """SELECT sl.*,
                      COUNT(DISTINCT e.ip_hash) as uv,
                      rq.upvotes,
                      rq.is_winner,
                      rq.subreddit,
                      rq.status as queue_status,
                      rq.comment_url
               FROM short_links sl
               LEFT JOIN link_click_events e ON sl.code = e.code
               LEFT JOIN reply_queue rq ON sl.queue_id = rq.id
               GROUP BY sl.id
               ORDER BY sl.clicks DESC, sl.id DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()

        totals = db.execute(
            """SELECT COUNT(DISTINCT sl.id) as total_links,
                      COALESCE(SUM(sl.clicks), 0) as total_clicks,
                      COUNT(DISTINCT e.ip_hash) as total_uv
               FROM short_links sl
               LEFT JOIN link_click_events e ON sl.code = e.code"""
        ).fetchone()

    return {
        "ok": True,
        "total_links": totals["total_links"] if totals else 0,
        "total_clicks": totals["total_clicks"] if totals else 0,
        "total_uv": totals["total_uv"] if totals else 0,
        "links": [dict(r) for r in rows]
    }


class _CreateLinkReq(BaseModel):
    target_url: str
    hit_id: str = ""
    queue_id: int | None = None
    listener_id: str = ""
    persona: str = ""
    platform: str = "reddit"
    campaign: str = ""


@router.post("/api/links/create")
def api_create_short_link(req: _CreateLinkReq) -> dict:
    """Explicitly generate an attributed tracking short link for any target URL."""
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == req.listener_id), None)
    lname = lst.get("name", "") if lst else ""
    res = create_attributed_short_link(
        target_url=req.target_url,
        hit_id=req.hit_id,
        queue_id=req.queue_id,
        listener_id=req.listener_id,
        listener_name=lname,
        persona=req.persona,
        platform=req.platform,
        campaign=req.campaign
    )
    return {"ok": True, **res}


# ── Telegram Interactive Webhook ─────────────────────────────────────────────
@router.post("/api/telegram/webhook")
def api_telegram_webhook(payload: dict) -> dict:
    """Endpoint for Telegram Webhook mode to receive inline keyboard approvals."""
    if "callback_query" in payload:
        from telegram_bot import handle_telegram_callback
        cfg = load_config()
        first_tok = next((l.get("telegram_bot_token") for l in cfg.get("listeners", []) if l.get("telegram_bot_token")), "")
        res = handle_telegram_callback(first_tok, payload["callback_query"])
        return res
    return {"ok": True}


# ── Multi-Project Workspace Hub ───────────────────────────────────────────────
@router.get("/api/projects")
def api_get_projects() -> dict:
    """
    Multi-Project Workspace Hub:
    Aggregates distinct projects/products from listeners, along with lead counts,
    active queue items, short link clicks, and monitored channels.
    """
    cfg = load_config()
    listeners = cfg.get("listeners", [])

    project_map: dict[str, dict] = {}

    with get_db() as db:
        today_start = time.time() - 86400
        hit_counts = {}
        for row in db.execute("SELECT listener_id, COUNT(*) as cnt FROM hits WHERE ts >= ? GROUP BY listener_id", (today_start,)):
            hit_counts[row["listener_id"]] = row["cnt"]

        queue_counts = {}
        for row in db.execute("SELECT listener_id, COUNT(*) as cnt FROM reply_queue WHERE status='submitted' AND submitted_at >= ? GROUP BY listener_id", (today_start,)):
            queue_counts[row["listener_id"]] = row["cnt"]

        click_counts = {}
        for row in db.execute("SELECT listener_id, SUM(clicks) as cnt FROM short_links GROUP BY listener_id"):
            click_counts[row["listener_id"]] = row["cnt"] or 0

    for lst in listeners:
        p_name = (lst.get("site_name") or lst.get("name") or "默认项目").strip()
        if p_name not in project_map:
            project_map[p_name] = {
                "name": p_name,
                "site_url": lst.get("site_url") or "",
                "site_description": lst.get("site_description") or "",
                "listeners": [],
                "subreddits": set(),
                "platforms": set(),
                "today_hits": 0,
                "today_replies": 0,
                "total_clicks": 0,
                "personas_count": len(lst.get("personas") or []),
                "visual_assets_count": len(lst.get("visual_assets") or []),
            }
        p = project_map[p_name]
        p["listeners"].append({
            "id": lst["id"],
            "name": lst.get("name", lst["id"]),
            "enabled": lst.get("enabled", True),
            "platform": lst.get("platform", "reddit")
        })
        for s in (lst.get("subreddits") or "").split(","):
            if s.strip():
                p["subreddits"].add(s.strip())
        p["platforms"].add(lst.get("platform", "reddit"))
        p["today_hits"] += hit_counts.get(lst["id"], 0)
        p["today_replies"] += queue_counts.get(lst["id"], 0)
        p["total_clicks"] += click_counts.get(lst["id"], 0)

    result = []
    for p in project_map.values():
        p["subreddits"] = sorted(list(p["subreddits"]))
        p["platforms"] = sorted(list(p["platforms"]))
        p["listener_count"] = len(p["listeners"])
        result.append(p)

    return {"ok": True, "projects": result}


# ── Account Health & Multi-Account Quota Matrix ───────────────────────────────
@router.get("/api/accounts/health")
def api_get_accounts_health() -> dict:
    """
    Account Health & Multi-Account Quota Matrix:
    Monitors daily reply quotas, cooldown intervals, and ban prevention statuses
    for all configured Reddit and X/Twitter credentials.
    """
    import datetime
    cfg = load_config()
    creds = cfg.get("credentials", [])
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    now = time.time()

    with get_db() as db:
        rows = db.execute("SELECT * FROM account_quota WHERE date_str=?", (today,)).fetchall()
        quota_map = {r["credential_id"]: dict(r) for r in rows}
        # Also retrieve any active rate limits or quarantines from previous dates
        active_prev = db.execute(
            """SELECT credential_id, is_quarantined, quarantine_until, rate_limit_until 
               FROM account_quota 
               WHERE (quarantine_until > ? OR rate_limit_until > ?)
               ORDER BY id DESC""",
            (now, now)
        ).fetchall()
        for pr in active_prev:
            cid = pr["credential_id"]
            if cid in quota_map:
                if pr["is_quarantined"] and pr["quarantine_until"] > now:
                    quota_map[cid]["is_quarantined"] = 1
                    quota_map[cid]["quarantine_until"] = max(quota_map[cid].get("quarantine_until", 0), pr["quarantine_until"])
                if pr["rate_limit_until"] and pr["rate_limit_until"] > now:
                    quota_map[cid]["rate_limit_until"] = max(quota_map[cid].get("rate_limit_until", 0), pr["rate_limit_until"])
            else:
                quota_map[cid] = dict(pr)

    accounts = []
    for c in creds:
        c_type = c.get("type")
        if c_type not in ("reddit", "x", "twitter", "forum", "vbulletin", "phpbb", "xenforo"):
            continue

        cid = c["id"]
        q = quota_map.get(cid, {})
        used = q.get("reply_count", 0)
        last_ts = q.get("last_reply_ts", 0)

        is_reddit = (c_type == "reddit")
        is_forum = c_type in ("forum", "vbulletin", "phpbb", "xenforo")
        is_cookie_x = (not is_reddit and not is_forum and bool(c.get("auth_token") and not c.get("api_key")))

        if is_reddit:
            daily_limit = 8
            cooldown_sec = 45 * 60
        elif is_cookie_x:
            daily_limit = 5
            cooldown_sec = 45 * 60
        elif is_forum:
            daily_limit = 15
            cooldown_sec = 15 * 60
        else:
            daily_limit = 25
            cooldown_sec = 15 * 60

        elapsed = now - last_ts if last_ts > 0 else 999999
        remaining_sec = max(0, int(cooldown_sec - elapsed))

        has_auth = False
        auth_mode = "unknown"
        if is_reddit:
            if c.get("cookie") or c.get("reddit_session"):
                has_auth = True
                auth_mode = "cookie"
            elif c.get("client_id") and c.get("client_secret"):
                has_auth = True
                auth_mode = "oauth"
        elif is_forum:
            if c.get("cookie") or c.get("session_cookie"):
                has_auth = True
                auth_mode = "cookie"
        else:
            if c.get("api_key") and c.get("access_token"):
                has_auth = True
                auth_mode = "oauth_api"
            elif c.get("auth_token") and c.get("ct0"):
                has_auth = True
                auth_mode = "cookie"

        is_quarantined = bool(q.get("is_quarantined") and q.get("quarantine_until", 0) > now)
        rate_limit_active = bool(q.get("rate_limit_until", 0) > now)

        if not has_auth:
            status = "unconfigured"
            status_label = "未配置凭据"
        elif is_quarantined:
            rem_h = round((q["quarantine_until"] - now) / 3600, 1)
            status = "quarantined"
            status_label = f"隔离保护中 (~{rem_h}h)"
        elif rate_limit_active:
            rem_m = max(1, round((q["rate_limit_until"] - now) / 60))
            status = "rate_limited"
            status_label = f"官方频控保护中 (~{rem_m}m)"
        elif used >= daily_limit:
            status = "limit_reached"
            status_label = "已达单日风控上限"
        elif remaining_sec > 0:
            status = "cooling"
            status_label = f"风控冷却中 ({round(remaining_sec / 60)}m)"
        else:
            status = "ready"
            status_label = "安全就绪"

        from auto_responder import check_rolling_link_ratio, get_account_maturity_tier
        rlr_allowed, rlr_ratio, rlr_link_cnt, rlr_total = check_rolling_link_ratio(cid, max_link_ratio=0.20, window_size=10)
        maturity = get_account_maturity_tier(karma=int(c.get("karma") or 100))

        accounts.append({
            "id": cid,
            "name": c.get("name") or cid[:8],
            "type": c_type,
            "auth_mode": auth_mode,
            "has_auth": has_auth,
            "today_used": used,
            "daily_limit": daily_limit,
            "usage_pct": round(min(100.0, (used / daily_limit) * 100)),
            "last_reply_ts": last_ts,
            "last_reply_time": datetime.datetime.fromtimestamp(last_ts).strftime("%H:%M") if last_ts > 0 else "无记录",
            "cooldown_remaining_seconds": remaining_sec,
            "status": status,
            "status_label": status_label,
            "is_quarantined": is_quarantined,
            "quarantine_until": q.get("quarantine_until", 0),
            "rate_limit_active": rate_limit_active,
            "rate_limit_until": q.get("rate_limit_until", 0),
            "rolling_link_ratio": rlr_ratio,
            "rolling_link_count": rlr_link_cnt,
            "rolling_total_count": rlr_total,
            "rolling_link_safe": rlr_allowed,
            "maturity_tier": maturity["tier"],
            "maturity_name": maturity["name"]
        })

    return {"ok": True, "accounts": accounts, "today": today, "now": now}


@router.post("/api/credentials/{cred_id}/test")
def api_test_credential(cred_id: str) -> dict:
    """Test connectivity and session validity for a credential (forum, reddit, x, ai)."""
    cfg = load_config()
    cred = next((c for c in cfg.get("credentials", []) if c["id"] == cred_id), None)
    if not cred:
        return {"ok": False, "status": "not_found", "message": "未找到该凭据"}

    c_type = cred.get("type", "")
    if c_type in ("forum", "vbulletin", "xenforo", "phpbb"):
        from auto_responder import verify_forum_session
        return verify_forum_session(cred)
    elif c_type == "reddit":
        from auto_responder import get_reddit_instance
        try:
            r = get_reddit_instance(cred)
            if r:
                user = r.user.me()
                return {"ok": True, "status": "ready", "message": f"Reddit API 连接成功！登录用户: u/{user.name if user else 'API'}"}
            elif cred.get("cookie") or cred.get("reddit_session"):
                return {"ok": True, "status": "ready", "message": f"Reddit Web Cookie 凭据已就绪 (@{cred.get('username') or 'session'})"}
            return {"ok": False, "status": "unconfigured", "message": "未配置有效的 Reddit 认证凭据"}
        except Exception as e:
            return {"ok": False, "status": "error", "message": f"Reddit 鉴权失败: {e}"}
    elif c_type in ("x", "twitter"):
        if cred.get("auth_token"):
            return {"ok": True, "status": "ready", "message": f"𝕏 Web Cookie 已就绪 (@{cred.get('username') or 'session'})"}
        elif cred.get("api_key") and cred.get("access_token"):
            return {"ok": True, "status": "ready", "message": "𝕏 OAuth 1.0a 官方 API 凭据已就绪"}
        return {"ok": False, "status": "unconfigured", "message": "未配置完整的 𝕏 凭据"}
    elif c_type in ("anthropic", "openai", "ollama"):
        from ai import run_ai_prompt
        try:
            res = run_ai_prompt("Respond with OK only", "ping", cred=cred)
            if res:
                return {"ok": True, "status": "ready", "message": f"AI 服务响应正常 ({c_type})"}
            return {"ok": False, "status": "error", "message": "AI 未返回有效响应"}
        except Exception as e:
            return {"ok": False, "status": "error", "message": f"AI 连接测试失败: {e}"}

    return {"ok": True, "status": "ready", "message": "凭据基本格式校验通过"}


# ── System Control & Lifecycle ────────────────────────────────────────────────
@router.get("/api/system/status")
def api_system_status() -> dict:
    import sys
    uptime = time.time() - _BOOT_TIME
    hrs = int(uptime // 3600)
    mins = int((uptime % 3600) // 60)
    secs = int(uptime % 60)
    uptime_human = f"{hrs}h {mins}m {secs}s" if hrs > 0 else f"{mins}m {secs}s"
    reload_active = any("--reload" in a for a in sys.argv) or os.getenv("RELOAD") == "1"
    return {
        "ok": True,
        "pid": os.getpid(),
        "uptime_seconds": int(uptime),
        "uptime_human": uptime_human,
        "python_version": sys.version.split()[0],
        "reload_active": reload_active,
        "port": os.getenv("PORT", "8770")
    }


@router.post("/api/system/restart")
def api_system_restart() -> dict:
    import subprocess
    import threading
    db_log("info", "system", "Manual system restart triggered via Admin API")
    current_pid = os.getpid()
    port = os.getenv("PORT", "8770")
    project_dir = str(Path(__file__).resolve().parent)

    def _detached_restart():
        time.sleep(0.8)
        # Detached script executed via background bash
        script = f"""
        (
          # 1. Gracefully terminate current uvicorn process
          kill -TERM {current_pid} 2>/dev/null || true
          for i in {{1..20}}; do
            kill -0 {current_pid} 2>/dev/null || break
            sleep 0.2
          done
          kill -9 {current_pid} 2>/dev/null || true
          sleep 0.5

          # 2. If managed by launchd, kickstart the registered service
          if launchctl list com.han.redsignal >/dev/null 2>&1; then
            launchctl kickstart -k "gui/$(id -u)/com.han.redsignal" 2>/dev/null || true
          fi

          # 3. Verify health on target port; if not responding within 3s, relaunch start.sh directly
          sleep 1.5
          for j in {{1..6}}; do
            if curl -fsS "http://127.0.0.1:{port}/api/health" >/dev/null 2>&1; then
              exit 0
            fi
            sleep 0.5
          done

          cd "{project_dir}" && nohup ./start.sh >> logs/server.log 2>&1 &
        ) &
        """
        subprocess.Popen(["/bin/bash", "-c", script], start_new_session=True, close_fds=True)

    threading.Thread(target=_detached_restart, daemon=True).start()

    return {
        "ok": True,
        "message": "服务重启指令已下达，后台进程正在平滑重载...",
        "reconnect_wait_seconds": 4
    }





