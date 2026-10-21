from __future__ import annotations

import asyncio
import json
import logging
import time
import requests
from typing import Any

from config import load_config
from db import db_log, get_db

logger = logging.getLogger("redsignal.telegram")


def telegram_api_call(token: str, method: str, payload: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    """Execute raw Telegram Bot API HTTP POST call."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
        data = resp.json()
        return data
    except Exception as e:
        logger.warning(f"Telegram API call {method} failed: {e}")
        return {"ok": False, "error": str(e)}


def answer_callback_query(token: str, callback_query_id: str, text: str = "", show_alert: bool = False) -> None:
    """Acknowledge Telegram callback query to dismiss loading state on button."""
    telegram_api_call(token, "answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert
    })


def update_telegram_message_status(token: str, chat_id: int | str, message_id: int, action_label: str) -> None:
    """Update button on Telegram message after user clicks it to prevent duplicate clicks."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": {
            "inline_keyboard": [
                [{"text": action_label, "callback_data": "noop"}]
            ]
        }
    }
    telegram_api_call(token, "editMessageReplyMarkup", payload)


def edit_telegram_message_text(token: str, chat_id: int | str, message_id: int, text: str, reply_markup: dict | None = None) -> None:
    """Edit both content and keyboard of an existing Telegram message in-place."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_api_call(token, "editMessageText", payload)


def handle_telegram_message(token: str, message: dict[str, Any]) -> None:
    """Handle incoming text commands like /status, /queue, /darkfleet from Telegram chat."""
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not text or not chat_id:
        return

    cmd = text.split()[0].lower()
    if cmd in ("/status", "/start"):
        with get_db() as db:
            pending_q = db.execute("SELECT COUNT(*) FROM reply_queue WHERE status='scheduled'").fetchone()[0]
            today_sub = db.execute("SELECT COUNT(*) FROM reply_queue WHERE status='submitted' AND date(datetime(submitted_at, 'unixepoch')) = date('now')").fetchone()[0]
            hits_today = db.execute("SELECT COUNT(*) FROM hits WHERE date(created_at) = date('now')").fetchone()[0]
            leads_cnt = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            dark_fleet_setting = db.execute("SELECT value FROM settings WHERE key='dark_fleet_mode'").fetchone()
            dark_fleet_on = (dark_fleet_setting["value"] == "1") if dark_fleet_setting else True

        cfg = load_config()
        active_listeners = [l.get("name") for l in cfg.get("listeners", []) if l.get("enabled", True)]

        reply_msg = (
            f"⚡ *RedSignal 巡航中枢状态*\n\n"
            f"🛸 *Dark Fleet 自动巡航*: {'🟢 已开启 (高置信度全自动发射)' if dark_fleet_on else '🟡 手动审批模式'}\n"
            f"📡 *运行中监听器*: {len(active_listeners)} 个 ({', '.join(active_listeners[:3])})\n"
            f"🎯 *今日捕获线索*: {hits_today} 条\n"
            f"⏱️ *当前排期队列*: {pending_q} 条待发射\n"
            f"🚀 *今日成功发射*: {today_sub} 条\n"
            f"📬 *零方线索邮箱*: {leads_cnt} 个潜客沉淀\n\n"
            f"💡 *快捷指令*:\n"
            f"/queue - 查看待发射排期队列\n"
            f"/darkfleet on - 开启全自动无人值守\n"
            f"/darkfleet off - 切换为手机手动审批"
        )
        telegram_api_call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": reply_msg,
            "parse_mode": "Markdown"
        })
    elif cmd == "/queue":
        with get_db() as db:
            rows = db.execute(
                """SELECT id, subreddit, platform, opportunity_score, scheduled_at, reply_text
                   FROM reply_queue WHERE status='scheduled' ORDER BY scheduled_at ASC LIMIT 5"""
            ).fetchall()
        if not rows:
            telegram_api_call(token, "sendMessage", {
                "chat_id": chat_id,
                "text": "⏱️ 当前安全排期队列为空，所有线索已发射完毕或等待新线索。"
            })
            return
        lines = ["⏱️ *待发射队列 (Top 5)*:\n"]
        for r in rows:
            rem_m = max(0, round((r["scheduled_at"] - time.time()) / 60))
            sub_name = r["subreddit"] or "feed"
            lines.append(f"• [#{r['id']}] {r['platform']} ({sub_name}) - 约 ~{rem_m}m 后发射 (分值: {r['opportunity_score']})\n  _{r['reply_text'][:70]}…_\n")
        telegram_api_call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "Markdown"
        })
    elif cmd.startswith("/darkfleet"):
        parts = text.split()
        with get_db() as db:
            if len(parts) > 1 and parts[1].lower() in ("off", "0", "stop"):
                db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('dark_fleet_mode', '0')")
                status_str = "🟡 已关闭全自动无人值守（切换为手机 Telegram 手动审批模式）"
            else:
                db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('dark_fleet_mode', '1')")
                status_str = "🟢 已开启 Dark Fleet 全自动巡航（高置信度线索将自动计算时差并排期发射）"
        telegram_api_call(token, "sendMessage", {
            "chat_id": chat_id,
            "text": f"🛸 *Dark Fleet 巡航模式设置变更*\n\n{status_str}",
            "parse_mode": "Markdown"
        })


def handle_telegram_callback(token: str, callback_query: dict[str, Any]) -> dict[str, Any]:
    """
    Handle Telegram button press (callback_query).
    Formats supported:
      - ap:{hit_id} -> 🚀 一键批准并立即发布
      - sc:{hit_id} -> ⏱️ 一键加入智能错峰排期
      - rj:{hit_id} -> ❌ 一键忽略/标记放弃
    """
    cq_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    msg = callback_query.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    msg_id = msg.get("message_id")
    from_user = callback_query.get("from") or {}
    user_name = from_user.get("first_name") or from_user.get("username") or "User"

    if data == "noop":
        answer_callback_query(token, cq_id, "该线索此前已被处理！")
        return {"ok": True, "action": "noop"}

    if ":" not in data:
        answer_callback_query(token, cq_id, "未知指令")
        return {"ok": False, "error": "Invalid callback format"}

    action, hit_id = data.split(":", 1)
    hit_id = hit_id.strip()

    with get_db() as db:
        r = db.execute(
            "SELECT * FROM hits WHERE hit_id=? OR post_id=? ORDER BY id DESC LIMIT 1",
            (hit_id, hit_id)
        ).fetchone()
        if not r:
            answer_callback_query(token, cq_id, f"线索未在数据库中找到: {hit_id}", show_alert=True)
            return {"ok": False, "error": "Hit not found"}
        hit = dict(r)

    # Resolve listener info
    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]
    lname = lst.get("name") if lst else (hit.get("listener_name") or "Listener")

    if action == "ap":
        # 🚀 立即发布 Approve Immediate
        from routes import api_hit_one_click_engage, api_queue_submit_now
        engage_res = api_hit_one_click_engage(hit["hit_id"])
        qid = engage_res.get("queue_id")

        if qid:
            # Trigger immediate dispatch
            submit_res = api_queue_submit_now(qid)
            if submit_res.get("ok"):
                curl = submit_res.get("comment_url") or ""
                note = f"🚀 发布成功！" + (f"链接: {curl}" if curl else "")
                answer_callback_query(token, cq_id, note, show_alert=False)
                if chat_id and msg_id:
                    update_telegram_message_status(token, chat_id, msg_id, f"✅ 已于 Telegram 批准发布 (by {user_name}) 🚀")
                db_log("info", "telegram_bot", f"Telegram 手机端批准发布成功 [Hit: {hit_id}, Queue: #{qid}]", hit.get("listener_id"), lname)
                return {"ok": True, "status": "submitted", "queue_id": qid}
            else:
                err = submit_res.get("error") or "发布失败"
                answer_callback_query(token, cq_id, f"⚠️ 立即发射失败: {err[:60]}", show_alert=True)
                if chat_id and msg_id:
                    update_telegram_message_status(token, chat_id, msg_id, f"⚠️ 发布异常 (已转入排期队列)")
                return {"ok": False, "error": err}
        else:
            answer_callback_query(token, cq_id, f"⚠️ 草稿生成/排期失败: {engage_res.get('error', '未知错误')}", show_alert=True)
            return {"ok": False, "error": engage_res.get("error")}

    elif action == "sc":
        # ⏱️ 智能错峰排期 Smart Chrono Schedule
        from routes import api_hit_one_click_engage
        engage_res = api_hit_one_click_engage(hit["hit_id"])
        qid = engage_res.get("queue_id")
        delay_min = engage_res.get("delay_minutes", 10)
        c_reason = engage_res.get("chrono_reason") or f"预计 ~{delay_min} 分钟后发射"

        answer_callback_query(token, cq_id, f"⏱️ 错峰排期成功！{c_reason}", show_alert=False)
        if chat_id and msg_id:
            update_telegram_message_status(token, chat_id, msg_id, f"⏱️ 已加入错峰安全队列 (约 ~{delay_min}m 后发射)")
        db_log("info", "telegram_bot", f"Telegram 手机端设置错峰排期 [Hit: {hit_id}, Queue: #{qid}, 延迟: ~{delay_min}m]", hit.get("listener_id"), lname)
        return {"ok": True, "status": "scheduled", "delay_minutes": delay_min}

    elif action == "rj":
        # ❌ 放弃线索 Reject / Ignore
        with get_db() as db:
            now_ts = time.time()
            db.execute("UPDATE hits SET status='ignored' WHERE hit_id=?", (hit["hit_id"],))
            db.execute("UPDATE reply_queue SET status='cancelled', updated_at=? WHERE hit_id=?", (now_ts, hit["hit_id"]))

        answer_callback_query(token, cq_id, "❌ 已忽略该线索并取消排期", show_alert=False)
        if chat_id and msg_id:
            update_telegram_message_status(token, chat_id, msg_id, f"❌ 已忽略 (by {user_name})")
        db_log("info", "telegram_bot", f"Telegram 手机端标记忽略线索 [Hit: {hit_id}]", hit.get("listener_id"), lname)
        return {"ok": True, "status": "ignored"}

    elif action in ("st_guru", "st_auth"):
        style = "guru" if action == "st_guru" else "authentic"
        style_label = "⚡ 极客干货向 (Guru)" if style == "guru" else "🛠️ 真实测评向 (Authentic)"
        from routes import api_hit_switch_style
        res = api_hit_switch_style(hit["hit_id"], style)
        if res.get("ok"):
            new_draft = res.get("reply_draft", "")
            answer_callback_query(token, cq_id, f"✅ 已成功切换为 {style_label}！", show_alert=False)
            if chat_id and msg_id:
                sub_label = hit.get("subreddit") or ""
                p_icon = "𝕏" if hit.get("platform") == "x" else ("🌐" if hit.get("platform") == "forum" else "🔴")
                opp_score = hit.get("opportunity_score", 50)
                tier = hit.get("funnel_tier", 3)
                updated_text = (
                    f"{p_icon} *{lname}* — {sub_label}\n\n"
                    f"*{hit.get('title') or '(Thread)'}*\nby u/{hit.get('author') or 'user'}\n\n"
                    f"Score: `{opp_score}` (Tier {tier}) | 风格: *{style_label}*\n"
                    f"_{hit.get('excerpt', '')[:200]}_\n\n"
                    f"💡 *AI新生成草稿 ({style})*:\n> {new_draft[:240]}…\n\n"
                    f"[Open Source Link]({hit.get('url', '')})"
                )
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "🚀 立即发布", "callback_data": f"ap:{hit['hit_id']}"},
                            {"text": "⏱️ 错峰排期", "callback_data": f"sc:{hit['hit_id']}"},
                            {"text": "❌ 忽略", "callback_data": f"rj:{hit['hit_id']}"}
                        ],
                        [
                            {"text": "🛠️ 换 Authentic 测评风格" if style == "guru" else "⚡ 换 Guru 极客风格",
                             "callback_data": f"st_auth:{hit['hit_id']}" if style == "guru" else f"st_guru:{hit['hit_id']}"}
                        ]
                    ]
                }
                edit_telegram_message_text(token, chat_id, msg_id, updated_text, keyboard)
            return {"ok": True, "style": style}
        else:
            answer_callback_query(token, cq_id, f"切换风格失败: {res.get('error', '未知错误')}", show_alert=True)
            return {"ok": False, "error": res.get("error")}

    else:
        answer_callback_query(token, cq_id, f"未知动作: {action}")
        return {"ok": False, "error": f"Unknown action {action}"}


async def telegram_polling_loop() -> None:
    """
    Background asynchronous loop that polls Telegram updates for interactive inline button presses.
    Requires ZERO external domain or webhook setup (works natively behind NAT, local dev, Docker).
    """
    await asyncio.sleep(6)  # Wait for startup
    token_offsets: dict[str, int] = {}
    invalid_tokens: set[str] = set()

    while True:
        try:
            cfg = load_config()
            listeners = cfg.get("listeners", [])
            # Collect unique active Telegram bot tokens
            active_tokens = set()
            for lst in listeners:
                if lst.get("enabled", True):
                    tok = (lst.get("telegram_bot_token") or "").strip()
                    if tok and tok not in invalid_tokens:
                        active_tokens.add(tok)

            if not active_tokens:
                await asyncio.sleep(15)
                continue

            for token in active_tokens:
                offset = token_offsets.get(token, 0)
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                payload = {
                    "offset": offset,
                    "timeout": 12,
                    "limit": 20,
                    "allowed_updates": ["callback_query", "message"]
                }
                try:
                    # Run blocking requests.post in default thread pool to avoid blocking asyncio event loop
                    loop = asyncio.get_running_loop()
                    resp_data = await loop.run_in_executor(
                        None,
                        lambda: telegram_api_call(token, "getUpdates", payload, timeout=15.0)
                    )

                    if not resp_data.get("ok"):
                        err_code = resp_data.get("error_code")
                        if err_code in (401, 404):
                            invalid_tokens.add(token)
                            db_log("warn", "telegram_bot", f"Telegram Bot Token 无效 ({err_code})，已暂停该 Token 轮询")
                        continue

                    updates = resp_data.get("result", [])
                    for u in updates:
                        up_id = u["update_id"]
                        token_offsets[token] = max(token_offsets.get(token, 0), up_id + 1)

                        if "callback_query" in u:
                            cq = u["callback_query"]
                            handle_telegram_callback(token, cq)
                        elif "message" in u:
                            msg_obj = u["message"]
                            handle_telegram_message(token, msg_obj)

                except Exception as ex:
                    logger.debug(f"Telegram polling exception for token: {ex}")

        except Exception as e:
            db_log("warn", "telegram_bot", f"Telegram polling loop error: {e}")

        await asyncio.sleep(2)
