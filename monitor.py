from __future__ import annotations

import datetime as _dt
import email.utils as _eu
import html as _html
import re
import threading
import time

import requests

from db import db_log, get_db
from webhooks import queue_and_deliver
from ws import _hit_queue

_monitors:    dict[str, threading.Thread] = {}
_stop_events: dict[str, threading.Event]  = {}

_author_cache: dict[str, dict] = {}


def _passes_author_quality(author, min_karma: int, min_age_days: int) -> bool:
    if author is None:
        return False
    name   = str(author)
    now    = time.time()
    cached = _author_cache.get(name)
    if cached and now - cached["t"] < 3600:
        data = cached
    else:
        try:
            karma   = (getattr(author, "comment_karma", 0) or 0) + (getattr(author, "link_karma", 0) or 0)
            created = getattr(author, "created_utc", now)
            data    = {"karma": karma, "created": created, "t": now}
            _author_cache[name] = data
        except Exception:
            return True
    if min_karma > 0 and data["karma"] < min_karma:
        return False
    if min_age_days > 0 and (now - data["created"]) / 86400 < min_age_days:
        return False
    return True


def _in_schedule(listener: dict) -> bool:
    if not listener.get("schedule_enabled"):
        return True
    try:
        import zoneinfo, datetime  # type: ignore
        tz   = zoneinfo.ZoneInfo(listener.get("schedule_timezone") or "UTC")
        now  = datetime.datetime.now(tz)
        days = listener.get("schedule_days", list(range(7)))
        if now.weekday() not in days:
            return False
        start = int(listener.get("schedule_start", 0))
        end   = int(listener.get("schedule_end", 24))
        return start <= now.hour < end
    except Exception:
        return True  # bad timezone → don't block monitoring


def should_dark_fleet_auto_dispatch(
    listener: dict,
    funnel_tier: int,
    opportunity_score: int,
    safety_verdict: str,
    safety_score: int
) -> bool:
    """Determine if a candidate hit meets the high-confidence Dark Fleet autonomous patrol threshold."""
    try:
        with get_db() as db:
            s_row = db.execute("SELECT value FROM settings WHERE key='dark_fleet_mode'").fetchone()
            if s_row and s_row["value"] == "0":
                return False
    except Exception:
        pass

    if not listener.get("dark_fleet_enabled", 1) and not listener.get("auto_submit_enabled"):
        return False

    min_safety = listener.get("dark_fleet_min_safety", 8)
    if min_safety > 10:
        min_safety = min_safety / 10.0
    min_opp = listener.get("dark_fleet_min_opp", 70)
    if safety_verdict != "PASSED" or (safety_score is not None and safety_score < min_safety):
        return False
    if opportunity_score < min_opp:
        return False
    if funnel_tier not in (1, 2):
        return False

    return True


def extract_snowflake_timestamp(tweet_id: str | int | None) -> float | None:
    """Extract unix timestamp (seconds) from Twitter/X Snowflake ID.

    Returns None if invalid or out of realistic epoch range (Nov 2010 to 2049).
    """
    if not tweet_id:
        return None
    s = str(tweet_id).strip()
    # Twitter Snowflake IDs are 64-bit integers with >= 15 digits
    if not s.isdigit() or len(s) < 15:
        return None
    try:
        ms = (int(s) >> 22) + 1288834974657
        # 1288834974657 is Twitter epoch (Nov 4, 2010), 2500000000000 is year 2049
        if 1288834974657 < ms < 2500000000000:
            return ms / 1000.0
    except Exception:
        pass
    return None


def _run_x_listener(listener: dict, credentials: list[dict]) -> None:
    """Real-time monitoring worker for X (Twitter) platform with API v2 and public verified discovery engines."""
    import html as _html
    import urllib.parse as _urllib_parse
    import requests

    lid = listener["id"]
    lname = listener.get("name", lid)
    stop = _stop_events.get(lid, threading.Event())
    was_paused = False

    def _err(msg: str) -> None:
        _hit_queue.put({"type": "error", "listener_id": lid, "listener_name": lname, "message": msg})
        db_log("error", "monitor", msg, lid, lname)

    def _status(msg: str) -> None:
        _hit_queue.put({"type": "status", "listener_id": lid, "listener_name": lname, "message": msg})
        db_log("info", "monitor", msg, lid, lname)

    kws = [k for k in listener.get("keywords", []) if k.strip()]
    if not kws:
        _err(f"[{lname}] 未配置监控关键词")
        return

    try:
        pattern = re.compile(
            r"(?<![A-Za-z0-9])(?:" + "|".join(kws) + r")(?![A-Za-z0-9])",
            re.IGNORECASE)
    except re.error as exc:
        _err(f"[{lname}] 正则表达式错误: {exc}")
        return

    neg_pattern: re.Pattern | None = None
    neg_kws = [k for k in listener.get("negative_keywords", []) if k.strip()]
    if neg_kws:
        try:
            neg_pattern = re.compile("|".join(neg_kws), re.IGNORECASE)
        except re.error as exc:
            _err(f"[{lname}] 排除词正则错误: {exc}")
            return

    webhook = (listener.get("webhook") or "").strip()
    slack_url = (listener.get("slack_webhook") or "").strip()
    tg_token = (listener.get("telegram_bot_token") or "").strip()
    tg_chat_id = (listener.get("telegram_chat_id") or "").strip()

    x_cred = next(
        (c for c in credentials if c.get("id") == listener.get("x_credential_id")
         and c.get("type") in ("x", "twitter")), None)
    if not x_cred:
        x_cred = next((c for c in credentials if c.get("type") in ("x", "twitter")), None)

    has_api = bool(x_cred and (x_cred.get("bearer_token") or (x_cred.get("api_key") and x_cred.get("api_secret"))))
    mode_name = "官方 API v2 搜索流" if has_api else "免 API 公开推文发现引擎"
    _status(f"[{lname}] 𝕏 (Twitter) 监听引擎启动: {mode_name}，关键词: {', '.join(kws)}")

    seen_tweet_ids = set()

    def _emit_tweet(tweet_id: str, author_name: str, tweet_text: str, permalink: str = "", post_ts: float | None = None):
        # Strictly reject invalid/synthetic tweet IDs (must be snowflake digits >= 8 chars)
        if not tweet_id or not str(tweet_id).isdigit() or len(str(tweet_id)) < 8:
            return
        clean_author = author_name.lstrip("@").strip()
        if not clean_author or clean_author.lower() in ("x_user", "unknown", "status", "i", "intent", "search", "share", "home"):
            return
        if tweet_id in seen_tweet_ids:
            return
        seen_tweet_ids.add(tweet_id)
        if len(seen_tweet_ids) > 10000:
            seen_tweet_ids.pop()

        m = pattern.search(tweet_text or "")
        if not m:
            return
        if neg_pattern and neg_pattern.search(tweet_text or ""):
            return

        # Calculate exact creation timestamp: API created_at or Twitter snowflake calculation
        actual_ts = post_ts
        if actual_ts is None:
            actual_ts = extract_snowflake_timestamp(tweet_id)
        if actual_ts is None:
            actual_ts = time.time()

        # Recency gate for Real-Time Radar: reject posts older than 7 days (or listener's max_post_age_days)
        # to eliminate necro-posting, algorithmic de-amplification, and wasted AI quota
        max_age_days = float(listener.get("max_post_age_days") or 7.0)
        if (time.time() - actual_ts) > (max_age_days * 86400):
            return

        url = permalink or f"https://x.com/{clean_author}/status/{tweet_id}"
        title = (tweet_text or "")[:80].replace("\n", " ").strip()
        excerpt = (tweet_text or "")[:300].replace("\n", " ")

        from ai import classify_funnel_tier, calculate_opportunity_score, evaluate_reply_safety
        funnel_tier, funnel_reason = classify_funnel_tier(title, tweet_text or "", custom_keywords=listener.get("keywords"))
        opp_eval = calculate_opportunity_score(
            title, tweet_text or "", ts=actual_ts, funnel_tier=funnel_tier,
            listener_keywords=listener.get("keywords")
        )
        opportunity_score = opp_eval["score"]

        reply_draft = None
        safety_verdict = None
        safety_score = None
        if listener.get("auto_reply_enabled", True):
            try:
                from ai import generate_site_integrated_reply, resolve_ai_cred
                from config import load_config
                cfg = load_config()
                cred = resolve_ai_cred(cfg, listener.get("ai_credential_id"))
                if cred:
                    reply_draft = generate_site_integrated_reply(
                        title=title,
                        excerpt=excerpt,
                        subreddit=f"@{clean_author}",
                        site_name=listener.get("site_name") or lname,
                        site_url=listener.get("site_url") or "",
                        site_desc=listener.get("site_description") or "",
                        pitch_instruction=listener.get("pitch_instruction", ""),
                        anti_ban_mode=listener.get("anti_ban_mode", "brand_search"),
                        funnel_tier=funnel_tier,
                        credential=cred,
                        platform="x",
                        personas=listener.get("personas")
                    )

                    if reply_draft:
                        safety_res = evaluate_reply_safety(
                            reply_text=reply_draft,
                            title=title,
                            excerpt=excerpt,
                            platform="x",
                            site_name=listener.get("site_name") or lname,
                            site_url=listener.get("site_url") or "",
                            credential=cred
                        )
                        safety_verdict = safety_res.get("verdict", "PASSED")
                        safety_score = safety_res.get("safety_score", 8)

                    first_p = (listener.get("personas") or [{}])[0] if listener.get("personas") else {}
                    persona = first_p.get("key") or "expert"
                    persona_label = first_p.get("label") or "🎯 领域专家"

                    has_x_auth = bool(
                        x_cred and (
                            (x_cred.get("api_key") and x_cred.get("access_token")) or
                            (x_cred.get("auth_token") and x_cred.get("ct0"))
                        )
                    )
                    is_df = should_dark_fleet_auto_dispatch(listener, funnel_tier, opportunity_score, safety_verdict, safety_score)
                    if reply_draft and is_df and has_x_auth:
                        from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
                        chrono = calculate_smart_chrono_dispatch(
                            post_ts=actual_ts,
                            opportunity_score=opportunity_score,
                            schedule_timezone=listener.get("schedule_timezone"),
                            schedule_start=listener.get("schedule_start"),
                            schedule_end=listener.get("schedule_end")
                        )
                        jitter = chrono["delay_seconds"]
                        chrono_reason = chrono["chrono_reason"]
                        enqueue_reply(
                            hit_id=tweet_id,
                            listener_id=lid,
                            listener_name=lname,
                            subreddit=f"@{clean_author}",
                            post_id=tweet_id,
                            target_id=tweet_id,
                            target_url=url,
                            author=clean_author,
                            reply_text=reply_draft,
                            funnel_tier=funnel_tier,
                            scheduled_delay_seconds=jitter,
                            status="scheduled",
                            platform="x",
                            opportunity_score=opportunity_score,
                            safety_verdict="PASSED",
                            persona=persona,
                            persona_label=persona_label,
                            chrono_reason=chrono_reason,
                            dispatch_mode="dark_fleet",
                            stealth_mode=listener.get("stealth_mode", "direct_link")
                        )
                        db_log("info", "dark_fleet", f"🛸 [Dark Fleet 自动巡航] 𝕏 高分推文已自动排期入队 (~{chrono['delay_minutes']}m 后发射): @{clean_author}", lid, lname)
                    elif reply_draft and listener.get("auto_submit_enabled") and has_x_auth:
                        from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
                        chrono = calculate_smart_chrono_dispatch(
                            post_ts=actual_ts,
                            opportunity_score=opportunity_score,
                            schedule_timezone=listener.get("schedule_timezone"),
                            schedule_start=listener.get("schedule_start"),
                            schedule_end=listener.get("schedule_end")
                        )
                        jitter = chrono["delay_seconds"]
                        chrono_reason = chrono["chrono_reason"]

                        if safety_verdict == "PASSED":
                            enqueue_reply(
                                hit_id=tweet_id,
                                listener_id=lid,
                                listener_name=lname,
                                subreddit=f"@{clean_author}",
                                post_id=tweet_id,
                                target_id=tweet_id,
                                target_url=url,
                                author=clean_author,
                                reply_text=reply_draft,
                                funnel_tier=funnel_tier,
                                scheduled_delay_seconds=jitter,
                                status="scheduled",
                                platform="x",
                                opportunity_score=opportunity_score,
                                safety_verdict="PASSED",
                                persona=persona,
                                persona_label=persona_label,
                                chrono_reason=chrono_reason,
                                dispatch_mode="auto_submit",
                                stealth_mode=listener.get("stealth_mode", "direct_link")
                            )
                            db_log("info", "ai_safety", f"𝕏 Gatekeeper PASSED ({safety_score}/10) for {tweet_id}: enqueued ({chrono_reason})", lid, lname)
                        else:
                            enqueue_reply(
                                hit_id=tweet_id,
                                listener_id=lid,
                                listener_name=lname,
                                subreddit=f"@{clean_author}",
                                post_id=tweet_id,
                                target_id=tweet_id,
                                target_url=url,
                                author=clean_author,
                                reply_text=reply_draft,
                                funnel_tier=funnel_tier,
                                scheduled_delay_seconds=0,
                                status="needs_review",
                                platform="x",
                                opportunity_score=opportunity_score,
                                safety_verdict="FLAGGED",
                                persona=persona,
                                persona_label=persona_label,
                                chrono_reason=chrono_reason,
                                dispatch_mode="manual",
                                stealth_mode=listener.get("stealth_mode", "direct_link")
                            )
                            db_log("warn", "ai_safety", f"𝕏 Gatekeeper FLAGGED ({safety_score}/10, {safety_res.get('reason')}) for {tweet_id}. Transferred to manual review.", lid, lname)
                    elif reply_draft:
                        from auto_responder import enqueue_reply
                        enqueue_reply(
                            hit_id=tweet_id,
                            listener_id=lid,
                            listener_name=lname,
                            subreddit=f"@{clean_author}",
                            post_id=tweet_id,
                            target_id=tweet_id,
                            target_url=url,
                            author=clean_author,
                            reply_text=reply_draft,
                            funnel_tier=funnel_tier,
                            scheduled_delay_seconds=0,
                            status="needs_review",
                            platform="x",
                            opportunity_score=opportunity_score,
                            safety_verdict=safety_verdict or "PASSED",
                            persona=persona,
                            persona_label=persona_label,
                            chrono_reason="未绑定 X 授权发帖凭据，已转入人工待审队列",
                            dispatch_mode="manual",
                            stealth_mode=listener.get("stealth_mode", "direct_link")
                        )
                        db_log("info", "ai_safety", f"𝕏 推文已生成草稿，因未配置发帖凭据已归入人工待审: @{clean_author}", lid, lname)
            except Exception as e:
                db_log("warn", "ai_draft", f"Auto-draft error for tweet {tweet_id}: {e}", lid, lname)

        hit = {
            "type":          "hit",
            "listener_id":   lid,
            "listener_name": lname,
            "kind":          "tweet",
            "subreddit":     f"@{clean_author}",
            "id":            tweet_id,
            "author":        clean_author,
            "match":         m.group(0),
            "title":         title,
            "url":           url,
            "excerpt":       excerpt,
            "post_id":       tweet_id,
            "reply_draft":   reply_draft,
            "funnel_tier":   funnel_tier,
            "funnel_reason": funnel_reason,
            "opportunity_score": opportunity_score,
            "safety_verdict": safety_verdict,
            "safety_score":   safety_score,
            "persona":        persona,
            "persona_label":  persona_label,
            "platform":      "x",
            "ts":            actual_ts,
            "created_at":    _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        _hit_queue.put(hit)

        if webhook:
            hit_with_draft = dict(hit)
            if reply_draft:
                hit_with_draft["reply_draft"] = reply_draft
            queue_and_deliver(webhook, hit_with_draft, lid, lname, "generic")

        if slack_url:
            queue_and_deliver(slack_url, {"blocks": [
                {"type": "header", "text": {"type": "plain_text",
                    "text": f"𝕏 {lname} — @{clean_author}"}},
                {"type": "section", "text": {"type": "mrkdwn",
                    "text": f"*{title}*\nby @{clean_author}  ·  keyword: `{m.group(0)}`"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"_{excerpt[:280]}_"}},
                {"type": "actions", "elements": [{"type": "button", "style": "primary",
                    "text": {"type": "plain_text", "text": "👀 View on 𝕏"}, "url": url}]},
            ]}, lid, lname, "slack")

        if tg_token and tg_chat_id:
            if 'is_df' in locals() and is_df:
                rem_m = chrono.get("delay_minutes", 10) if 'chrono' in locals() else 10
                c_reason = chrono.get("chrono_reason", "") if 'chrono' in locals() else ""
                tg_payload = {
                    "chat_id": tg_chat_id,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                    "text": (f"🛸 *[Dark Fleet 自动巡航拦截]*\n\n"
                             f"𝕏 *{lname}* — @{clean_author}\n\n"
                             f"🐦 *{title}*\nby @{clean_author}\n\n"
                             f"Keyword: `{m.group(0)}`  ·  Score: `{opportunity_score}` (Tier {funnel_tier})\n"
                             f"⏱️ 错峰发射: 约 ~{rem_m} 分钟后\n_{c_reason}_\n\n"
                             + (f"💡 *全自动排期草稿*:\n> {reply_draft[:180]}…\n\n" if reply_draft else "")
                             + f"[Open on 𝕏]({url})"),
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {"text": "⚡ 提前立即发布", "callback_data": f"ap:{tweet_id}"},
                                {"text": "❌ 撤销/拦截", "callback_data": f"rj:{tweet_id}"}
                            ],
                            [
                                {"text": "🛠️ 换 Authentic 测评风格", "callback_data": f"st_auth:{tweet_id}"}
                            ]
                        ]
                    }
                }
            else:
                tg_payload = {
                    "chat_id": tg_chat_id,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                    "text": (f"𝕏 *{lname}* — @{clean_author} (待审)\n\n"
                             f"🐦 *{title}*\nby @{clean_author}\n\n"
                             f"Keyword: `{m.group(0)}`  ·  Score: `{opportunity_score}` (Tier {funnel_tier})\n_{excerpt[:240]}_\n"
                             + (f"\n💡 *AI拟定草稿*:\n> {reply_draft[:180]}…\n" if reply_draft else "")
                             + f"\n[Open on 𝕏]({url})"),
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {"text": "🚀 立即发布", "callback_data": f"ap:{tweet_id}"},
                                {"text": "⏱️ 错峰排期", "callback_data": f"sc:{tweet_id}"},
                                {"text": "❌ 忽略", "callback_data": f"rj:{tweet_id}"}
                            ],
                            [
                                {"text": "🔬 换 Guru 风格", "callback_data": f"st_guru:{tweet_id}"},
                                {"text": "🛠️ 换 Authentic 风格", "callback_data": f"st_auth:{tweet_id}"}
                            ]
                        ]
                    }
                }
            queue_and_deliver(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                tg_payload,
                lid, lname, "telegram")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        session.get("https://search.yahoo.com/", timeout=10)
    except Exception:
        pass

    # Polling Loop
    while not stop.is_set():
        if not _in_schedule(listener):
            if not was_paused:
                _status(f"[{lname}] Outside schedule window — pausing")
                was_paused = True
            time.sleep(60)
            continue
        if was_paused:
            _status(f"[{lname}] Entering schedule window — resuming")
            was_paused = False

        for kw in kws:
            if stop.is_set():
                return
            # Path 1: Official X API v2 Search (if credentials provided)
            polled_via_api = False
            if has_api and x_cred:
                bearer = x_cred.get("bearer_token")
                if not bearer and x_cred.get("api_key") and x_cred.get("api_secret"):
                    try:
                        import base64
                        key_secret = f"{x_cred['api_key']}:{x_cred['api_secret']}"
                        b64 = base64.b64encode(key_secret.encode()).decode()
                        tok_resp = session.post(
                            "https://api.twitter.com/oauth2/token",
                            headers={"Authorization": f"Basic {b64}", "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                            data={"grant_type": "client_credentials"},
                            timeout=10
                        )
                        if tok_resp.status_code == 200:
                            bearer = tok_resp.json().get("access_token")
                            x_cred["bearer_token"] = bearer
                    except Exception:
                        pass

                if bearer:
                    try:
                        api_url = f"https://api.twitter.com/2/tweets/search/recent?query={_urllib_parse.quote(kw)}&max_results=15&tweet.fields=created_at,author_id&expansions=author_id&user.fields=username,name"
                        r = session.get(api_url, headers={"Authorization": f"Bearer {bearer}"}, timeout=12)
                        if r.status_code == 200:
                            data = r.json()
                            users_map = {u["id"]: u.get("username", "") for u in data.get("includes", {}).get("users", [])}
                            tweets = data.get("data", [])
                            for t in tweets:
                                tid = str(t.get("id"))
                                uid = t.get("author_id")
                                author = users_map.get(uid, "")
                                if not author or author.lower() == "x_user":
                                    continue
                                text = t.get("text", "")
                                c_at = t.get("created_at")
                                p_ts = None
                                if c_at:
                                    try:
                                        p_ts = _dt.datetime.fromisoformat(c_at.replace("Z", "+00:00")).timestamp()
                                    except Exception:
                                        pass
                                _emit_tweet(tid, author, text, post_ts=p_ts)
                            polled_via_api = True
                        elif r.status_code == 429:
                            _status(f"[{lname}] 𝕏 API 触发限频，正在使用公开推文流平滑接管...")
                    except Exception as e:
                        db_log("warn", "monitor", f"X API error: {e}", lid, lname)

            # Path 2: Public Zero-API Real-time Tweet Discovery Engine (Dual Provider: Yahoo + DuckDuckGo HTML Fallback)
            if not polled_via_api:
                try:
                    q = f"site:x.com {kw}"
                    candidates = []

                    # Provider A: Yahoo Search
                    try:
                        url = "https://search.yahoo.com/search?p=" + _urllib_parse.quote(q)
                        r = session.get(url, timeout=10)
                        if r.status_code == 200:
                            for m_ru in re.finditer(r"/RU=([^/\"\x27]+)/RK=", r.text):
                                raw = _urllib_parse.unquote(m_ru.group(1))
                                tm = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)/status/(\d+)", raw)
                                if tm:
                                    cand_author, cand_tid = tm.group(1), tm.group(2)
                                    if cand_author.lower() not in ("i", "intent", "search", "share", "home", "status", "explore", "x_user"):
                                        if cand_tid not in seen_tweet_ids:
                                            candidates.append((cand_author, cand_tid))
                    except Exception:
                        pass

                    # Provider B: DuckDuckGo HTML Search (Instant fallback when Yahoo rate-limits)
                    if not candidates:
                        try:
                            ddg_r = session.post(
                                "https://html.duckduckgo.com/html/",
                                data={"q": q},
                                timeout=10
                            )
                            if ddg_r.status_code == 200:
                                for a, tid in re.findall(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)/status/(\d+)", ddg_r.text):
                                    if a.lower() not in ("i", "intent", "search", "share", "home", "status", "explore", "x_user"):
                                        if tid not in seen_tweet_ids:
                                            candidates.append((a, tid))
                        except Exception:
                            pass

                    unique_candidates = list(dict.fromkeys(candidates))

                    # Pre-filter by Twitter snowflake timestamp to avoid fetching dead historical tweets
                    now_sec = time.time()
                    max_age_sec = float(listener.get("max_post_age_days") or 7.0) * 86400
                    recent_candidates = []
                    for cand_author, cand_tid in unique_candidates:
                        cand_ts = extract_snowflake_timestamp(cand_tid)
                        if cand_ts and (now_sec - cand_ts) > max_age_sec:
                            seen_tweet_ids.add(cand_tid)
                            continue
                        recent_candidates.append((cand_author, cand_tid))

                    # Verify via Twitter official oembed: guarantees 100% real live tweet
                    for cand_author, cand_tid in recent_candidates[:6]:
                        if stop.is_set():
                            return
                        if cand_tid in seen_tweet_ids:
                            continue
                        try:
                            t_url = f"https://x.com/{cand_author}/status/{cand_tid}"
                            vr = session.get(f"https://publish.x.com/oembed?url={t_url}&omit_script=true", timeout=6)
                            if vr.status_code == 200:
                                data = vr.json()
                                o_html = data.get("html", "")
                                pm = re.search(r"<p[^>]*>(.*?)</p>", o_html)
                                raw_text = pm.group(1) if pm else o_html
                                clean_text = _html.unescape(re.sub(r"<[^>]+>", " ", raw_text))
                                clean_text = re.sub(r"\s+", " ", clean_text).strip()

                                a_url = data.get("author_url", "")
                                real_author = a_url.rstrip("/").split("/")[-1] if a_url else cand_author
                                if real_author and real_author.lower() != "x_user":
                                    cand_ts = extract_snowflake_timestamp(cand_tid)
                                    _emit_tweet(
                                        cand_tid,
                                        real_author,
                                        clean_text,
                                        permalink=f"https://x.com/{real_author}/status/{cand_tid}",
                                        post_ts=cand_ts
                                    )
                        except Exception:
                            pass
                except Exception as e:
                    db_log("warn", "monitor", f"X discovery error for kw '{kw}': {e}", lid, lname)

            time.sleep(3)

        time.sleep(25)

    db_log("info", "monitor", f"[{lname}] Stopped", lid, lname)


def _run_forum_listener(listener: dict, credentials: list[dict]) -> None:
    """Vertical forum radar engine (vBulletin, phpBB, XenForo RSS2 / Atom)."""
    lid   = listener["id"]
    lname = listener.get("name", lid)

    def _err(msg: str) -> None:
        _hit_queue.put({"type": "error", "listener_id": lid, "listener_name": lname, "message": msg})
        db_log("error", "monitor", msg, lid, lname)

    def _status(msg: str) -> None:
        _hit_queue.put({"type": "status", "listener_id": lid, "listener_name": lname, "message": msg})
        db_log("info", "monitor", msg, lid, lname)

    kws = [k for k in listener.get("keywords", []) if k.strip()]
    if not kws:
        _err(f"[{lname}] 未配置论坛监控关键词")
        return

    try:
        pattern = re.compile(
            r"(?<![A-Za-z0-9])(?:" + "|".join(kws) + r")(?![A-Za-z0-9])",
            re.IGNORECASE)
    except re.error as exc:
        _err(f"[{lname}] 论坛关键词正则错误: {exc}"); return

    neg_pattern: re.Pattern | None = None
    neg_kws = [k for k in listener.get("negative_keywords", []) if k.strip()]
    if neg_kws:
        try:
            neg_pattern = re.compile("|".join(neg_kws), re.IGNORECASE)
        except re.error as exc:
            _err(f"[{lname}] 论坛负向词正则错误: {exc}"); return

    webhook    = (listener.get("webhook")            or "").strip()
    slack_url  = (listener.get("slack_webhook")      or "").strip()
    tg_token   = (listener.get("telegram_bot_token") or "").strip()
    tg_chat_id = (listener.get("telegram_chat_id")   or "").strip()

    rss_url = (listener.get("forum_rss_url") or listener.get("subreddits") or "").strip()
    if not rss_url or not (rss_url.startswith("http://") or rss_url.startswith("https://")):
        rss_url = "https://www.buggiesgonewild.com/external.php?type=RSS2"

    import xml.etree.ElementTree as _ET
    import html as _html
    import hashlib

    stop = _stop_events.get(lid, threading.Event())
    seen_ids = set()
    _status(f"[{lname}] 垂直技术论坛生态雷达已启动: {rss_url}")

    forum_cred = next(
        (c for c in credentials if c.get("id") == listener.get("forum_credential_id")
         and c.get("type") in ("forum", "vbulletin", "phpbb", "xenforo")), None)
    if not forum_cred:
        forum_cred = next((c for c in credentials if c.get("type") in ("forum", "vbulletin", "phpbb", "xenforo")), None)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
    })
    if forum_cred and (forum_cred.get("cookie") or forum_cred.get("session_cookie")):
        c_str = (forum_cred.get("cookie") or forum_cred.get("session_cookie")).strip()
        if c_str:
            session.headers["Cookie"] = c_str

    while not stop.is_set():
        if not _in_schedule(listener):
            time.sleep(60)
            continue

        try:
            resp = session.get(rss_url, timeout=15)
            if resp.status_code == 200:
                root = _ET.fromstring(resp.content)
                # Determine RSS vs Atom
                items = root.findall(".//item")
                if not items:
                    items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

                for it in items:
                    if stop.is_set():
                        return
                    # Extract fields
                    title_elem = it.find("title") or it.find("{http://www.w3.org/2005/Atom}title")
                    title = title_elem.text if title_elem is not None and title_elem.text else ""

                    link_elem = it.find("link") or it.find("{http://www.w3.org/2005/Atom}link")
                    if link_elem is not None:
                        url = link_elem.get("href") or link_elem.text or ""
                    else:
                        url = ""

                    guid_elem = it.find("guid") or it.find("id") or it.find("{http://www.w3.org/2005/Atom}id")
                    item_id = guid_elem.text if guid_elem is not None and guid_elem.text else ""
                    if not item_id:
                        item_id = hashlib.md5((url or title).encode()).hexdigest()[:16]

                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                    desc_elem = it.find("description") or it.find("{http://www.w3.org/2005/Atom}content") or it.find("{http://www.w3.org/2005/Atom}summary")
                    raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
                    clean_desc = _html.unescape(re.sub(r'<[^>]+>', ' ', raw_desc))
                    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

                    full_text = f"{title}\n{clean_desc}"
                    m = pattern.search(full_text)
                    if not m:
                        continue
                    if neg_pattern and neg_pattern.search(full_text):
                        continue

                    # Extract author
                    author_elem = it.find("dc:creator", {"dc": "http://purl.org/dc/elements/1.1/"}) or it.find("author") or it.find("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
                    author = author_elem.text if author_elem is not None and author_elem.text else "ForumMember"

                    # Extract published/post timestamp
                    pub_elem = it.find("pubDate") or it.find("dc:date", {"dc": "http://purl.org/dc/elements/1.1/"}) or it.find("{http://www.w3.org/2005/Atom}published") or it.find("{http://www.w3.org/2005/Atom}updated")
                    post_ts = None
                    if pub_elem is not None and pub_elem.text:
                        pub_str = pub_elem.text.strip()
                        try:
                            post_ts = _eu.parsedate_to_datetime(pub_str).timestamp()
                        except Exception:
                            try:
                                post_ts = _dt.datetime.fromisoformat(pub_str.replace("Z", "+00:00")).timestamp()
                            except Exception:
                                pass
                    if not post_ts:
                        post_ts = time.time()

                    # Recency gate for Real-Time Radar: reject forum posts older than 7 days
                    max_age_days = float(listener.get("max_post_age_days") or 7.0)
                    if (time.time() - post_ts) > (max_age_days * 86400):
                        continue

                    from ai import classify_funnel_tier, calculate_opportunity_score, evaluate_reply_safety, generate_site_integrated_reply, resolve_ai_cred
                    from config import load_config
                    funnel_tier, funnel_reason = classify_funnel_tier(title, clean_desc, custom_keywords=listener.get("keywords"))
                    opp_eval = calculate_opportunity_score(
                        title, clean_desc, ts=post_ts, funnel_tier=funnel_tier,
                        listener_keywords=listener.get("keywords"),
                        visual_assets=listener.get("visual_assets")
                    )
                    opportunity_score = opp_eval["score"]

                    reply_draft = None
                    safety_verdict = None
                    safety_score = None
                    persona = "expert"
                    persona_label = "🎯 领域专家"

                    if listener.get("auto_reply_enabled", True):
                        try:
                            cfg = load_config()
                            cred = resolve_ai_cred(cfg, listener.get("ai_credential_id"))
                            if cred:
                                first_p = (listener.get("personas") or [{}])[0] if listener.get("personas") else {}
                                persona = first_p.get("key") or "expert"
                                persona_label = first_p.get("label") or "🎯 领域专家"
                                reply_draft = generate_site_integrated_reply(
                                    title=title,
                                    excerpt=clean_desc[:300],
                                    subreddit="Forum",
                                    site_name=listener.get("site_name") or lname,
                                    site_url=listener.get("site_url") or "",
                                    site_desc=listener.get("site_description") or "",
                                    pitch_instruction=listener.get("pitch_instruction", ""),
                                    anti_ban_mode=listener.get("anti_ban_mode", "brand_search"),
                                    funnel_tier=funnel_tier,
                                    credential=cred,
                                    platform="forum",
                                    visual_assets=listener.get("visual_assets"),
                                    personas=listener.get("personas"),
                                    stealth_mode=listener.get("stealth_mode", "direct_link")
                                )

                                if reply_draft:
                                    safety_res = evaluate_reply_safety(
                                        reply_text=reply_draft,
                                        title=title,
                                        excerpt=clean_desc[:300],
                                        platform="forum",
                                        site_name=listener.get("site_name") or lname,
                                        site_url=listener.get("site_url") or "",
                                        credential=cred
                                    )
                                    safety_verdict = safety_res.get("verdict", "PASSED")
                                    safety_score = safety_res.get("safety_score", 8)

                                is_df = should_dark_fleet_auto_dispatch(listener, funnel_tier, opportunity_score, safety_verdict, safety_score)
                                has_forum_auth = bool(forum_cred and (forum_cred.get("cookie") or forum_cred.get("session_cookie")))
                                if reply_draft and is_df and has_forum_auth:
                                    from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
                                    chrono = calculate_smart_chrono_dispatch(
                                        post_ts=post_ts,
                                        opportunity_score=opportunity_score,
                                        schedule_timezone=listener.get("schedule_timezone"),
                                        schedule_start=listener.get("schedule_start"),
                                        schedule_end=listener.get("schedule_end")
                                    )
                                    enqueue_reply(
                                        hit_id=item_id,
                                        listener_id=lid,
                                        listener_name=lname,
                                        subreddit="forum",
                                        post_id=item_id,
                                        target_id=item_id,
                                        target_url=url,
                                        author=author,
                                        reply_text=reply_draft,
                                        funnel_tier=funnel_tier,
                                        scheduled_delay_seconds=chrono["delay_seconds"],
                                        status="scheduled",
                                        platform="forum",
                                        opportunity_score=opportunity_score,
                                        safety_verdict="PASSED",
                                        persona=persona,
                                        persona_label=persona_label,
                                        chrono_reason=chrono["chrono_reason"],
                                        dispatch_mode="dark_fleet",
                                        stealth_mode=listener.get("stealth_mode", "direct_link")
                                    )
                                    db_log("info", "dark_fleet", f"🛸 [Dark Fleet 自动巡航] 垂直论坛高分帖子已排期入队 (~{chrono['delay_minutes']}m 后发射): {title[:30]} by {author}", lid, lname)
                                elif reply_draft and listener.get("auto_submit_enabled") and has_forum_auth:
                                    from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
                                    chrono = calculate_smart_chrono_dispatch(
                                        post_ts=post_ts,
                                        opportunity_score=opportunity_score,
                                        schedule_timezone=listener.get("schedule_timezone"),
                                        schedule_start=listener.get("schedule_start"),
                                        schedule_end=listener.get("schedule_end")
                                    )
                                    enqueue_reply(
                                        hit_id=item_id,
                                        listener_id=lid,
                                        listener_name=lname,
                                        subreddit="forum",
                                        post_id=item_id,
                                        target_id=item_id,
                                        target_url=url,
                                        author=author,
                                        reply_text=reply_draft,
                                        funnel_tier=funnel_tier,
                                        scheduled_delay_seconds=chrono["delay_seconds"] if safety_verdict == "PASSED" else 0,
                                        status="scheduled" if safety_verdict == "PASSED" else "needs_review",
                                        platform="forum",
                                        opportunity_score=opportunity_score,
                                        safety_verdict=safety_verdict,
                                        persona=persona,
                                        persona_label=persona_label,
                                        chrono_reason=chrono["chrono_reason"],
                                        dispatch_mode="auto_submit",
                                        stealth_mode=listener.get("stealth_mode", "direct_link")
                                    )
                                elif reply_draft:
                                    from auto_responder import enqueue_reply
                                    enqueue_reply(
                                        hit_id=item_id,
                                        listener_id=lid,
                                        listener_name=lname,
                                        subreddit="forum",
                                        post_id=item_id,
                                        target_id=item_id,
                                        target_url=url,
                                        author=author,
                                        reply_text=reply_draft,
                                        funnel_tier=funnel_tier,
                                        scheduled_delay_seconds=0,
                                        status="needs_review",
                                        platform="forum",
                                        opportunity_score=opportunity_score,
                                        safety_verdict=safety_verdict or "PASSED",
                                        persona=persona,
                                        persona_label=persona_label,
                                        chrono_reason="未绑定论坛发帖 Cookie，已转为人工待审草稿",
                                        dispatch_mode="manual",
                                        stealth_mode=listener.get("stealth_mode", "direct_link")
                                    )
                                    db_log("info", "forum_dispatch", f"垂直论坛帖子已生成 BBCode 专业草稿，已归入人工待审: {title[:30]}", lid, lname)
                        except Exception as ex:
                            db_log("warn", "ai_draft", f"Forum auto-draft error for {item_id}: {ex}", lid, lname)

                    hit = {
                        "type":          "hit",
                        "listener_id":   lid,
                        "listener_name": lname,
                        "kind":          "post",
                        "subreddit":     "forum",
                        "id":            item_id,
                        "author":        author,
                        "match":         m.group(0),
                        "title":         title,
                        "url":           url,
                        "excerpt":       clean_desc[:300],
                        "post_id":       item_id,
                        "reply_draft":   reply_draft,
                        "funnel_tier":   funnel_tier,
                        "funnel_reason": funnel_reason,
                        "opportunity_score": opportunity_score,
                        "safety_verdict": safety_verdict,
                        "safety_score":   safety_score,
                        "persona":        persona,
                        "persona_label":  persona_label,
                        "platform":      "forum",
                        "ts":            post_ts,
                        "created_at":    _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    }
                    _hit_queue.put(hit)

                    if webhook:
                        hit_with_draft = dict(hit)
                        if reply_draft:
                            hit_with_draft["reply_draft"] = reply_draft
                        queue_and_deliver(webhook, hit_with_draft, lid, lname, "generic")

                    if slack_url:
                        queue_and_deliver(slack_url, {"blocks": [
                            {"type": "header", "text": {"type": "plain_text", "text": f"🌐 {lname} — 垂直论坛"}},
                            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\nby {author} · keyword: `{m.group(0)}`"}},
                            {"type": "section", "text": {"type": "mrkdwn", "text": f"_{clean_desc[:260]}_"}},
                            {"type": "actions", "elements": [{"type": "button", "style": "primary", "text": {"type": "plain_text", "text": "👀 打开论坛原帖"}, "url": url}]},
                        ]}, lid, lname, "slack")

                    if tg_token and tg_chat_id:
                        if 'is_df' in locals() and is_df:
                            rem_m = chrono.get("delay_minutes", 10) if 'chrono' in locals() else 10
                            c_reason = chrono.get("chrono_reason", "") if 'chrono' in locals() else ""
                            tg_payload = {
                                "chat_id": tg_chat_id,
                                "parse_mode": "Markdown",
                                "disable_web_page_preview": True,
                                "text": (f"🛸 *[Dark Fleet 自动巡航拦截]*\n\n"
                                         f"🌐 *{lname}* — 垂直论坛\n\n"
                                         f"📌 *{title}*\nby {author}\n\n"
                                         f"Keyword: `{m.group(0)}`  ·  Score: `{opportunity_score}` (Tier {funnel_tier})\n"
                                         f"⏱️ 错峰发射: 约 ~{rem_m} 分钟后\n_{c_reason}_\n\n"
                                         + (f"💡 *BBCode 全自动草稿*:\n> {reply_draft[:180]}…\n\n" if reply_draft else "")
                                         + f"[打开论坛原帖]({url})"),
                                "reply_markup": {
                                    "inline_keyboard": [
                                        [
                                            {"text": "⚡ 提前立即发布", "callback_data": f"ap:{item_id}"},
                                            {"text": "❌ 撤销/拦截", "callback_data": f"rj:{item_id}"}
                                        ],
                                        [
                                            {"text": "🛠️ 换 Authentic 测评风格", "callback_data": f"st_auth:{item_id}"}
                                        ]
                                    ]
                                }
                            }
                        else:
                            tg_payload = {
                                "chat_id": tg_chat_id,
                                "parse_mode": "Markdown",
                                "disable_web_page_preview": True,
                                "text": (f"🌐 *{lname}* — 垂直论坛 (待审)\n\n"
                                         f"📌 *{title}*\nby {author}\n\n"
                                         f"Keyword: `{m.group(0)}`  ·  Score: `{opportunity_score}` (Tier {funnel_tier})\n_{clean_desc[:240]}_\n"
                                         + (f"\n💡 *BBCode 原生草稿*:\n> {reply_draft[:180]}…\n" if reply_draft else "")
                                         + f"\n[打开论坛原帖]({url})"),
                                "reply_markup": {
                                    "inline_keyboard": [
                                        [
                                            {"text": "🚀 立即发布", "callback_data": f"ap:{item_id}"},
                                            {"text": "⏱️ 错峰排期", "callback_data": f"sc:{item_id}"},
                                            {"text": "❌ 忽略", "callback_data": f"rj:{item_id}"}
                                        ],
                                        [
                                            {"text": "🔬 换 Guru 风格", "callback_data": f"st_guru:{item_id}"},
                                            {"text": "🛠️ 换 Authentic 风格", "callback_data": f"st_auth:{item_id}"}
                                        ]
                                    ]
                                }
                            }
                        queue_and_deliver(
                            f"https://api.telegram.org/bot{tg_token}/sendMessage",
                            tg_payload,
                            lid, lname, "telegram")
            elif resp.status_code == 403 or "cf-mitigated" in resp.headers or "Just a moment" in resp.text:
                db_log("warn", "forum_radar", f"[{lname}] 论坛被 Cloudflare 拦截 (HTTP 403 Challenge)。若需自动抓取，建议在 Vault 论坛凭据中配置带 cf_clearance 的 Cookie；已进入智能节流冷却 (120s)", lid, lname)
                time.sleep(120)
                continue
            else:
                db_log("warn", "forum_radar", f"[{lname}] 论坛 RSS 抓取未确认成功 (HTTP {resp.status_code})", lid, lname)
                time.sleep(60)
                continue
        except Exception as e:
            db_log("warn", "forum_radar", f"Forum RSS parse error: {e}", lid, lname)

        time.sleep(30)

    db_log("info", "monitor", f"[{lname}] 论坛雷达停止", lid, lname)


def _run_listener(listener: dict, credentials: list[dict]) -> None:
    lid   = listener["id"]
    lname = listener.get("name", lid)

    platform = listener.get("platform") or "reddit"
    if platform in ("x", "twitter"):
        _run_x_listener(listener, credentials)
        return
    elif platform in ("forum", "vbulletin", "phpbb", "xenforo"):
        _run_forum_listener(listener, credentials)
        return

    def _err(msg: str) -> None:
        _hit_queue.put({"type": "error", "listener_id": lid, "listener_name": lname, "message": msg})
        db_log("error", "monitor", msg, lid, lname)

    def _status(msg: str) -> None:
        _hit_queue.put({"type": "status", "listener_id": lid, "listener_name": lname, "message": msg})
        db_log("info", "monitor", msg, lid, lname)

    reddit_cred = next(
        (c for c in credentials if c.get("id") == listener.get("reddit_credential_id")
         and c.get("type") == "reddit"), None)
    _status(f"[{lname}] 免 API 公开流/RSS 轮询引擎已就绪")

    kws = [k for k in listener.get("keywords", []) if k.strip()]
    if not kws:
        _err(f"[{lname}] No keywords configured")
        return

    try:
        pattern = re.compile(
            r"(?<![A-Za-z0-9])(?:" + "|".join(kws) + r")(?![A-Za-z0-9])",
            re.IGNORECASE)
    except re.error as exc:
        _err(f"[{lname}] Invalid regex: {exc}"); return

    neg_pattern: re.Pattern | None = None
    neg_kws = [k for k in listener.get("negative_keywords", []) if k.strip()]
    if neg_kws:
        try:
            neg_pattern = re.compile("|".join(neg_kws), re.IGNORECASE)
        except re.error as exc:
            _err(f"[{lname}] Invalid negative keyword regex: {exc}"); return

    whitelist      = {s.strip().lower() for s in listener.get("whitelist", []) if s.strip()}
    subreddits_str = listener.get("subreddits") or "all"
    webhook        = (listener.get("webhook")            or "").strip()
    slack_url      = (listener.get("slack_webhook")      or "").strip()
    tg_token       = (listener.get("telegram_bot_token") or "").strip()
    tg_chat_id     = (listener.get("telegram_chat_id")   or "").strip()
    min_karma      = int(listener.get("min_karma", 0) or 0)
    min_age_days   = int(listener.get("min_account_age_days", 0) or 0)
    check_author   = min_karma > 0 or min_age_days > 0

    stop       = _stop_events.get(lid, threading.Event())
    was_paused = False

    def _emit(kind: str, item_id: str, author_name: str, permalink: str, text: str, title: str, post_id: str, sub_name: str, author_obj=None, post_ts: float | None = None) -> None:
        m = pattern.search(text or "")
        if not m:
            return
        if neg_pattern and neg_pattern.search(text or ""):
            return
        if whitelist and sub_name.lower() not in whitelist:
            return
        if check_author and not _passes_author_quality(author_obj, min_karma, min_age_days):
            return

        actual_ts = post_ts if post_ts is not None and post_ts > 0 else time.time()

        # Recency gate for Real-Time Radar: reject posts older than 7 days (or max_post_age_days)
        max_age_days = float(listener.get("max_post_age_days") or 7.0)
        if (time.time() - actual_ts) > (max_age_days * 86400):
            return

        if permalink.startswith("http://") or permalink.startswith("https://"):
            url = permalink
        else:
            url = f"https://reddit.com{permalink}" if permalink else ""
        excerpt = (text or "")[:300].replace("\n", " ")

        from ai import classify_funnel_tier, calculate_opportunity_score, evaluate_reply_safety
        funnel_tier, funnel_reason = classify_funnel_tier(title, text or "", custom_keywords=listener.get("keywords"))
        opp_eval = calculate_opportunity_score(
            title, text or "", ts=actual_ts, funnel_tier=funnel_tier,
            listener_keywords=listener.get("keywords"),
            visual_assets=listener.get("visual_assets")
        )
        opportunity_score = opp_eval["score"]

        reply_draft = None
        safety_verdict = None
        safety_score = None
        # 若开启了自动生成独立站融合回复 (auto_reply_enabled)
        if listener.get("auto_reply_enabled", True):
            try:
                from ai import generate_site_integrated_reply, resolve_ai_cred
                from config import load_config
                cfg = load_config()
                cred = resolve_ai_cred(cfg, listener.get("ai_credential_id"))
                if cred:
                    first_p = (listener.get("personas") or [{}])[0] if listener.get("personas") else {}
                    persona = first_p.get("key") or "expert"
                    persona_label = first_p.get("label") or "🎯 领域专家"

                    reply_draft = generate_site_integrated_reply(
                        title=title,
                        excerpt=excerpt,
                        subreddit=sub_name,
                        site_name=listener.get("site_name") or lname,
                        site_url=listener.get("site_url") or "",
                        site_desc=listener.get("site_description") or "",
                        pitch_instruction=listener.get("pitch_instruction", ""),
                        anti_ban_mode=listener.get("anti_ban_mode", "brand_search"),
                        funnel_tier=funnel_tier,
                        credential=cred,
                        platform="reddit",
                        visual_assets=listener.get("visual_assets"),
                        personas=listener.get("personas"),
                        stealth_mode=listener.get("stealth_mode", "direct_link")
                    )

                    # AI 预审员防封门禁（LLM-as-a-Judge Pre-Flight Safety Gatekeeper）
                    if reply_draft:
                        safety_res = evaluate_reply_safety(
                            reply_text=reply_draft,
                            title=title,
                            excerpt=excerpt,
                            platform="reddit",
                            site_name=listener.get("site_name") or lname,
                            site_url=listener.get("site_url") or "",
                            credential=cred
                        )
                        safety_verdict = safety_res.get("verdict", "PASSED")
                        safety_score = safety_res.get("safety_score", 8)

                    is_df = should_dark_fleet_auto_dispatch(listener, funnel_tier, opportunity_score, safety_verdict, safety_score)
                    # Protect against Reddit TOO_OLD: Reddit permanently archives posts > 180 days old
                    if actual_ts < time.time() - 180 * 86400:
                        is_df = False
                        db_log("info", "monitor", f"[{lname}] 自动忽略 Reddit 历史归档帖 (帖龄 > 180天，避免 TOO_OLD 封禁): {title[:40]}...")

                    if reply_draft and is_df:
                        from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
                        chrono = calculate_smart_chrono_dispatch(
                            post_ts=actual_ts,
                            opportunity_score=opportunity_score,
                            schedule_timezone=listener.get("schedule_timezone"),
                            schedule_start=listener.get("schedule_start"),
                            schedule_end=listener.get("schedule_end")
                        )
                        jitter = chrono["delay_seconds"]
                        chrono_reason = chrono["chrono_reason"]
                        enqueue_reply(
                            hit_id=item_id,
                            listener_id=lid,
                            listener_name=lname,
                            subreddit=sub_name,
                            post_id=post_id,
                            target_id=item_id,
                            target_url=url,
                            author=author_name or "",
                            reply_text=reply_draft,
                            funnel_tier=funnel_tier,
                            scheduled_delay_seconds=jitter,
                            status="scheduled",
                            platform="reddit",
                            opportunity_score=opportunity_score,
                            safety_verdict="PASSED",
                            persona=persona,
                            persona_label=persona_label,
                            chrono_reason=chrono_reason,
                            dispatch_mode="dark_fleet",
                            stealth_mode=listener.get("stealth_mode", "direct_link")
                        )
                        db_log("info", "dark_fleet", f"🛸 [Dark Fleet 自动巡航] Reddit 高分线索已自动排期入队 (~{chrono['delay_minutes']}m 后发射): r/{sub_name} by u/{author_name}", lid, lname)
                    elif reply_draft and listener.get("auto_submit_enabled"):
                        from auto_responder import calculate_smart_chrono_dispatch, enqueue_reply
                        chrono = calculate_smart_chrono_dispatch(
                            post_ts=actual_ts,
                            opportunity_score=opportunity_score,
                            schedule_timezone=listener.get("schedule_timezone"),
                            schedule_start=listener.get("schedule_start"),
                            schedule_end=listener.get("schedule_end")
                        )
                        jitter = chrono["delay_seconds"]
                        chrono_reason = chrono["chrono_reason"]

                        if safety_verdict == "PASSED":
                            enqueue_reply(
                                hit_id=item_id,
                                listener_id=lid,
                                listener_name=lname,
                                subreddit=sub_name,
                                post_id=post_id,
                                target_id=item_id,
                                target_url=url,
                                author=author_name or "",
                                reply_text=reply_draft,
                                funnel_tier=funnel_tier,
                                scheduled_delay_seconds=jitter,
                                status="scheduled",
                                platform="reddit",
                                opportunity_score=opportunity_score,
                                safety_verdict="PASSED",
                                persona=persona,
                                persona_label=persona_label,
                                chrono_reason=chrono_reason,
                                dispatch_mode="auto_submit",
                                stealth_mode=listener.get("stealth_mode", "direct_link")
                            )
                            db_log("info", "ai_safety", f"AI Gatekeeper PASSED ({safety_score}/10) for {item_id}: enqueued ({chrono_reason})", lid, lname)
                        else:
                            enqueue_reply(
                                hit_id=item_id,
                                listener_id=lid,
                                listener_name=lname,
                                subreddit=sub_name,
                                post_id=post_id,
                                target_id=item_id,
                                target_url=url,
                                author=author_name or "",
                                reply_text=reply_draft,
                                funnel_tier=funnel_tier,
                                scheduled_delay_seconds=0,
                                status="needs_review",
                                platform="reddit",
                                opportunity_score=opportunity_score,
                                safety_verdict="FLAGGED",
                                persona=persona,
                                persona_label=persona_label,
                                chrono_reason=chrono_reason,
                                dispatch_mode="manual",
                                stealth_mode=listener.get("stealth_mode", "direct_link")
                            )
                            db_log("warn", "ai_safety", f"AI Gatekeeper FLAGGED ({safety_score}/10, Reason: {safety_res.get('reason')}) for {item_id}. Auto-submission withheld for manual review.", lid, lname)
            except Exception as e:
                db_log("warn", "ai_draft", f"Auto-draft error for {item_id}: {e}", lid, lname)

        hit = {
            "type":          "hit",
            "listener_id":   lid,
            "listener_name": lname,
            "kind":          kind,
            "subreddit":     sub_name,
            "id":            item_id,
            "author":        author_name or "",
            "match":         m.group(0),
            "title":         title,
            "url":           url,
            "excerpt":       excerpt,
            "post_id":       post_id,
            "reply_draft":   reply_draft,
            "funnel_tier":   funnel_tier,
            "funnel_reason": funnel_reason,
            "opportunity_score": opportunity_score,
            "safety_verdict": safety_verdict,
            "safety_score":   safety_score,
            "persona":        persona,
            "persona_label":  persona_label,
            "platform":      "reddit",
            "ts":            actual_ts,
            "created_at":    _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        _hit_queue.put(hit)

        if webhook:
            # 强化 Bark Webhook: 将 AI 回复草稿也一并下发
            hit_with_draft = dict(hit)
            if reply_draft:
                hit_with_draft["reply_draft"] = reply_draft
            queue_and_deliver(webhook, hit_with_draft, lid, lname, "generic")

        if slack_url:
            queue_and_deliver(slack_url, {"blocks": [
                {"type": "header", "text": {"type": "plain_text",
                    "text": f"🔴 {lname} — r/{sub_name}"}},
                {"type": "section", "text": {"type": "mrkdwn",
                    "text": f"*{title or '(comment)'}*\nby u/{hit['author']}  ·  keyword: `{m.group(0)}`"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"_{excerpt[:280]}_"}},
                {"type": "actions", "elements": [{"type": "button", "style": "primary",
                    "text": {"type": "plain_text", "text": "👀 View on Reddit"}, "url": url}]},
            ]}, lid, lname, "slack")

        if tg_token and tg_chat_id:
            icon = "📝" if kind == "post" else "💬"
            if 'is_df' in locals() and is_df:
                rem_m = chrono.get("delay_minutes", 10) if 'chrono' in locals() else 10
                c_reason = chrono.get("chrono_reason", "") if 'chrono' in locals() else ""
                tg_payload = {
                    "chat_id": tg_chat_id,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                    "text": (f"🛸 *[Dark Fleet 自动巡航拦截]*\n\n"
                             f"🔴 *{lname}* — r/{sub_name}\n\n"
                             f"{icon} *{title or '(comment)'}*\nby u/{hit['author']}\n\n"
                             f"Keyword: `{m.group(0)}`  ·  Score: `{opportunity_score}` (Tier {funnel_tier})\n"
                             f"⏱️ 错峰发射: 约 ~{rem_m} 分钟后\n_{c_reason}_\n\n"
                             + (f"💡 *全自动排期草稿*:\n> {reply_draft[:180]}…\n\n" if reply_draft else "")
                             + f"[Open on Reddit]({url})"),
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {"text": "⚡ 提前立即发布", "callback_data": f"ap:{item_id}"},
                                {"text": "❌ 撤销/拦截", "callback_data": f"rj:{item_id}"}
                            ],
                            [
                                {"text": "🛠️ 换 Authentic 测评风格", "callback_data": f"st_auth:{item_id}"}
                            ]
                        ]
                    }
                }
            else:
                tg_payload = {
                    "chat_id": tg_chat_id,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                    "text": (f"🔴 *{lname}* — r/{sub_name} (待审)\n\n"
                             f"{icon} *{title or '(comment)'}*\nby u/{hit['author']}\n\n"
                             f"Keyword: `{m.group(0)}`  ·  Score: `{opportunity_score}` (Tier {funnel_tier})\n_{excerpt[:260]}_\n"
                             + (f"\n💡 *AI拟定草稿*:\n> {reply_draft[:180]}…\n" if reply_draft else "")
                             + f"\n[Open on Reddit]({url})"),
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {"text": "🚀 立即发布", "callback_data": f"ap:{item_id}"},
                                {"text": "⏱️ 错峰排期", "callback_data": f"sc:{item_id}"},
                                {"text": "❌ 忽略", "callback_data": f"rj:{item_id}"}
                            ],
                            [
                                {"text": "🔬 换 Guru 风格", "callback_data": f"st_guru:{item_id}"},
                                {"text": "🛠️ 换 Authentic 风格", "callback_data": f"st_auth:{item_id}"}
                            ]
                        ]
                    }
                }
            queue_and_deliver(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                tg_payload,
                lid, lname, "telegram")

    _status(f"[{lname}] Monitoring r/{subreddits_str}…")

    # ── 免 API 公开流/RSS 轮询引擎 (稳定避开 Reddit 401/403 封禁) ──────────────
    import urllib.request as _urllib_req
    import xml.etree.ElementTree as _ET
    import html as _html
    import re as _re
    seen_ids = set()
    invalid_subs = set()
    subs_list = [s.strip() for s in subreddits_str.replace("+", " ").split() if s.strip()]
    if not subs_list:
        subs_list = ["all"]

    # 从凭据库中挂接有效的 Reddit Session Cookie，避开未鉴权公共 IP 频控 (429)
    reddit_cookie = ""
    if reddit_cred:
        reddit_cookie = reddit_cred.get("cookie") or reddit_cred.get("reddit_session") or ""
    if not reddit_cookie:
        try:
            from barnacle import get_reddit_cookie
            reddit_cookie = get_reddit_cookie()
        except Exception:
            pass

    rss_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
    }
    if reddit_cookie:
        rss_headers["Cookie"] = f"reddit_session={reddit_cookie}" if "reddit_session=" not in reddit_cookie else reddit_cookie

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    auth_state = "已挂接 Web Cookie" if reddit_cookie else "未鉴权匿名模式"
    _status(f"[{lname}] Reddit 轮询引擎就绪 ({auth_state})，巡检板块: {', '.join(subs_list)}")

    def _clean_html(raw_html: str) -> str:
        if not raw_html: return ""
        clean = re.sub(r'<[^>]+>', ' ', _html.unescape(raw_html))
        return re.sub(r'\s+', ' ', clean).strip()

    while not stop.is_set():
        if not _in_schedule(listener):
            if not was_paused:
                _status(f"[{lname}] Outside schedule window — pausing")
                was_paused = True
            time.sleep(60)
            continue
        if was_paused:
            _status(f"[{lname}] Entering schedule window — resuming")
            was_paused = False

        # 优先使用 Reddit 原生 Multireddit (+ 连接) 聚合请求，每组最多 4 个板块，防止大流量板块挤占前 25 条 RSS 容量，同时极速低频杜绝 429
        active_subs = [s for s in subs_list if s not in invalid_subs]
        chunk_size = 4
        batches = []
        for i in range(0, len(active_subs), chunk_size):
            chunk = active_subs[i:i + chunk_size]
            batches.append(("+".join(chunk), len(chunk) > 1))

        for target_sub, is_multireddit in batches:
            if stop.is_set(): return
            ep_url = f"https://www.reddit.com/r/{target_sub}/new.rss"
            try:
                req = _urllib_req.Request(ep_url, headers=rss_headers)
                with _urllib_req.urlopen(req, timeout=20) as resp:
                    tree = _ET.fromstring(resp.read().decode("utf-8", errors="ignore"))
                    for entry in tree.findall("atom:entry", ns):
                        id_el = entry.find("atom:id", ns)
                        item_id = id_el.text if id_el is not None else ""
                        if not item_id or item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)
                        if len(seen_ids) > 20000:
                            seen_ids.pop()

                        title_el = entry.find("atom:title", ns)
                        p_title = title_el.text if title_el is not None else ""

                        link_el = entry.find("atom:link", ns)
                        permalink = link_el.attrib.get("href", "") if link_el is not None else ""
                        if permalink.startswith("https://www.reddit.com"):
                            permalink = permalink.replace("https://www.reddit.com", "")
                        elif permalink.startswith("https://reddit.com"):
                            permalink = permalink.replace("https://reddit.com", "")

                        author_el = entry.find("atom:author/atom:name", ns)
                        author = author_el.text.replace("/u/", "") if author_el is not None and author_el.text else "unknown"

                        content_el = entry.find("atom:content", ns)
                        content_raw = content_el.text if content_el is not None else ""
                        body_text = _clean_html(content_raw)
                        full_body = (p_title + " " + body_text).strip()

                        # 多板块聚合时从 category 获取具体的 Subreddit 名称
                        cat_el = entry.find("atom:category", ns)
                        actual_sub = (cat_el.attrib.get("term", "") if cat_el is not None else "") or target_sub

                        # Extract exact post timestamp from atom entry: <published> or <updated>
                        post_ts = None
                        published_el = entry.find("atom:published", ns) or entry.find("atom:updated", ns)
                        if published_el is not None and published_el.text:
                            try:
                                pub_text = published_el.text.strip().replace("Z", "+00:00")
                                post_ts = _dt.datetime.fromisoformat(pub_text).timestamp()
                            except Exception:
                                pass

                        _emit("post", item_id, author, permalink, full_body, p_title, item_id, actual_sub, post_ts=post_ts)
            except Exception as e:
                err_msg = str(e)
                if "404" in err_msg or "Not Found" in err_msg:
                    if not is_multireddit:
                        invalid_subs.add(target_sub)
                        db_log("warn", "monitor", f"[{lname}] 版块 r/{target_sub} 不存在 (404)，已移出巡检池", lid, lname)
                elif "429" in err_msg:
                    _status(f"[{lname}] 触发频率限制，智能冷却 60 秒...")
                    time.sleep(60)
                else:
                    db_log("warn", "monitor", f"Fetch {target_sub} error: {e}", lid, lname)
                    # 聚合请求若遭遇网络超时或 SSL 抖动，降级单拉首要核心版块，确保核心流不中断
                    if is_multireddit and ("timed out" in err_msg or "EOF" in err_msg):
                        primary_sub = target_sub.split("+")[0]
                        try:
                            fallback_url = f"https://www.reddit.com/r/{primary_sub}/new.rss"
                            fb_req = _urllib_req.Request(fallback_url, headers=rss_headers)
                            with _urllib_req.urlopen(fb_req, timeout=12) as fb_resp:
                                fb_tree = _ET.fromstring(fb_resp.read().decode("utf-8", errors="ignore"))
                                for entry in fb_tree.findall("atom:entry", ns):
                                    id_el = entry.find("atom:id", ns)
                                    item_id = id_el.text if id_el is not None else ""
                                    if not item_id or item_id in seen_ids:
                                        continue
                                    seen_ids.add(item_id)
                                    p_title = (entry.find("atom:title", ns).text or "") if entry.find("atom:title", ns) is not None else ""
                                    link_el = entry.find("atom:link", ns)
                                    permalink = link_el.attrib.get("href", "") if link_el is not None else ""
                                    if permalink.startswith("https://www.reddit.com"): permalink = permalink.replace("https://www.reddit.com", "")
                                    author_el = entry.find("atom:author/atom:name", ns)
                                    author = author_el.text.replace("/u/", "") if author_el is not None and author_el.text else "unknown"
                                    content_raw = (entry.find("atom:content", ns).text or "") if entry.find("atom:content", ns) is not None else ""
                                    body_text = _clean_html(content_raw)
                                    full_body = (p_title + " " + body_text).strip()
                                    _emit("post", item_id, author, permalink, full_body, p_title, item_id, primary_sub)
                        except Exception:
                            pass

        # 巡检间隔平稳休眠 35 秒
        time.sleep(35)
    db_log("info", "monitor", f"[{lname}] Stopped", lid, lname)
    return


def start_listener(listener: dict, credentials: list[dict]) -> bool:
    lid = listener["id"]
    if lid in _monitors and _monitors[lid].is_alive():
        return False
    stop = threading.Event()
    _stop_events[lid] = stop
    t = threading.Thread(target=_run_listener, args=(listener, credentials),
                         daemon=True, name=f"rs-{lid[:8]}")
    _monitors[lid] = t
    t.start()
    return True


def stop_listener(listener_id: str) -> None:
    if listener_id in _stop_events:
        _stop_events[listener_id].set()


def stop_all_listeners() -> None:
    for ev in _stop_events.values():
        ev.set()


def listener_statuses() -> dict[str, bool]:
    return {lid: t.is_alive() for lid, t in _monitors.items()}
