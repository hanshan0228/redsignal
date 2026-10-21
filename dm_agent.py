"""
dm_agent.py - RedSignal Fully Automated Inbound DM & Chat Conversion Agent
Handles:
- Periodic inbox polling for Reddit (and X)
- Conversation thread state tracking in SQLite (Round 1 -> Round 2 -> Round 3)
- AI-driven dynamic reply drafting tailored to user objections & intent
- Automated session-authenticated reply dispatch with anti-ban rate limiting
- Real-time Bark notification push to user mobile
"""

from __future__ import annotations

import datetime
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from typing import Optional

from ai import run_ai_prompt
from config import load_config
from db import db_log, get_db

BARK_WEBHOOK = os.getenv("BARK_WEBHOOK", "")
BOT_BLOCKLIST = {"automoderator", "reddit", "welcomebot", "redditcareresources"}


def send_bark_dm_alert(title: str, body: str, url: str = "https://www.reddit.com/message/messages/"):
    """Send immediate notification to user's iOS Bark client."""
    if not BARK_WEBHOOK:
        return
    try:
        payload = {
            "title": title,
            "body": body,
            "group": "RedSignal-DM",
            "icon": "https://raw.githubusercontent.com/justmysocks-guide/.github/main/assets/logo.png",
            "url": url,
            "sound": "anticipate"
        }
        req = urllib.request.Request(
            BARK_WEBHOOK,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "RedSignal/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception as e:
        db_log("warn", "dm_agent", f"Bark notification failed: {e}")


def get_conversation_state(partner_handle: str, platform: str = "reddit") -> dict:
    """Retrieve or initialize conversation state from SQLite."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM dm_conversations WHERE platform = ? AND partner_handle = ?",
            (platform, partner_handle)
        ).fetchone()
        if row:
            return dict(row)
        return {
            "thread_id": "",
            "platform": platform,
            "partner_handle": partner_handle,
            "current_round": 1,
            "campaign_id": "justmysocks",
            "subject": "",
            "last_inbound_msg": "",
            "last_outbound_msg": "",
            "status": "active"
        }


def save_conversation_state(state: dict):
    """Persist conversation round and messages in SQLite."""
    now = time.time()
    with get_db() as db:
        db.execute(
            """INSERT INTO dm_conversations
               (thread_id, platform, partner_handle, current_round, campaign_id, subject,
                last_inbound_msg, last_outbound_msg, status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(platform, partner_handle) DO UPDATE SET
               thread_id = excluded.thread_id,
               current_round = excluded.current_round,
               campaign_id = excluded.campaign_id,
               subject = excluded.subject,
               last_inbound_msg = excluded.last_inbound_msg,
               last_outbound_msg = excluded.last_outbound_msg,
               status = excluded.status,
               updated_at = excluded.updated_at""",
            (
                state.get("thread_id", ""),
                state.get("platform", "reddit"),
                state.get("partner_handle", ""),
                int(state.get("current_round", 1)),
                state.get("campaign_id", "justmysocks"),
                state.get("subject", ""),
                state.get("last_inbound_msg", ""),
                state.get("last_outbound_msg", ""),
                state.get("status", "active"),
                now
            )
        )


def analyze_inbound_intent(inbound_text: str, current_round: int) -> int:
    """
    Intelligently infer which round of the closing funnel to advance to.
    Round 1: Value first / Icebreaker
    Round 2: Technical proof & BandwagonHost advantage
    Round 3: Close with Affiliate Link & Promo Code
    """
    t = (inbound_text or "").lower()

    # If the user explicitly asks for purchase link, discount, or where to buy -> jump to Round 3 Close
    close_patterns = [
        "link", "where to buy", "coupon", "code", "promo", "affiliate", "how to get", "buy",
        "链接", "地址", "购买", "优惠码", "多少钱", "购买地址", "怎么买", "给个链接", "求链接"
    ]
    if any(p in t for p in close_patterns):
        return 3

    # If the user asks about reliability, speed, or IP bans -> answer with Round 2 Proof
    proof_patterns = [
        "speed", "403", "blocked", "ban", "safe", "stable", "openai", "claude",
        "速度", "卡不卡", "被封", "403", "跑路", "稳定吗", "好用吗", "丢包", "晚高峰"
    ]
    if any(p in t for p in proof_patterns):
        return 2

    return min(current_round, 3)


def append_utm_params(
    url: str,
    platform: str = "reddit",
    medium: str = "dm",
    campaign: str = "redsignal",
    content: str = ""
) -> str:
    """Safely append standard UTM tracking parameters to URL without breaking existing query params."""
    if not url:
        return ""
    try:
        import urllib.parse
        import re
        parsed = urllib.parse.urlparse(url)
        q_params = dict(urllib.parse.parse_qsl(parsed.query))
        q_params.setdefault("utm_source", platform or "reddit")
        q_params.setdefault("utm_medium", medium or "dm")
        clean_camp = re.sub(r"[^a-zA-Z0-9_-]+", "_", (campaign or "redsignal").strip()).strip("_").lower()
        q_params.setdefault("utm_campaign", clean_camp or "redsignal")
        if content:
            q_params.setdefault("utm_content", content)
        new_query = urllib.parse.urlencode(q_params)
        return urllib.parse.urlunparse((
            parsed.scheme or "https",
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
    except Exception:
        return url


def draft_automated_reply(
    partner_handle: str,
    inbound_text: str,
    target_round: int,
    campaign_name: str = "Just My Socks",
    affiliate_url: str = "https://justmysocks.net/members/aff.php?aff=24082",
    discount_code: str = "JMS9272283",
    ai_credential: Optional[dict] = None,
    platform: str = "reddit"
) -> str:
    """Draft an authentic, human-like peer reply tailored to the current round."""
    tracked_affiliate_url = append_utm_params(
        affiliate_url,
        platform=platform,
        medium="dm",
        campaign=campaign_name,
        content=f"round_{target_round}"
    )

    if not ai_credential:
        cfg = load_config()
        ai_credential = next((c for c in cfg.get("credentials", []) if c.get("type") in ("anthropic", "openai", "ollama")), None)

    prefix = "u/" if platform == "reddit" else "@"
    prompt = f"""You are an authentic, experienced developer and tech enthusiast having a private 1v1 message conversation on {platform.upper()} with {prefix}{partner_handle}.

Their incoming message to you:
"{inbound_text}"

Goal for this turn (Funnel Round {target_round} of 3):
- If Round 1: Deliver pure technical setup guidance or empathy. Zero aggressive selling. Friendly, peer-to-peer.
- If Round 2: Explain why you personally use {campaign_name} (BandwagonHost/IT7 Networks official, automatic background IP replacement if blocked by GFW or OpenAI, CN2 GIA/9929 premium backbone). Highlight high ROI and peace of mind. Also offer to send a free setup & speed test checklist if they need it.
- If Round 3: Send the tracked referral link ({tracked_affiliate_url}) and mention coupon code '{discount_code}' (5.2% perpetual recurring discount). Transparently include: "(透明说明：这是我的返佣推荐链接，但服务确实是我用了两年最稳的)".

COMMUNICATION RULES:
1. Natural conversational tone (Chinese or English matching the user's language).
2. Keep it under 140 words.
3. Absolutely NO robotic corporate marketing fluff ("Dear friend", "I hope this finds you well").
4. Authentic, honest, and helpful.

Write ONLY the direct message text to send:"""

    try:
        reply = run_ai_prompt(prompt, ai_credential, max_tokens=250)
        return reply.strip()
    except Exception as e:
        db_log("error", "dm_agent", f"AI draft failed: {e}")
        if target_round >= 3:
            return (
                f"购买地址可以直接走这个官方通道：{tracked_affiliate_url} "
                f"（透明说明：这是我的返佣链接，用了两年很稳）。结账记得填专属循环优惠码 【{discount_code}】，"
                f"立减 5.2% 且续费永久生效。有什么配置问题随时问我！"
            )
        elif target_round == 2:
            return (
                f"我之前也饱受 403 折磨。后来换成搬瓦工官方的 {campaign_name}，"
                f"核心优势是后台自动探活：一旦 IP 被防火墙或 OpenAI 阻断，系统自动秒换可用新 IP，走的也是 CN2 GIA 专线。"
                f"如果你需要的话，我也可以把之前的测速对比和配置避坑清单发你一份。"
            )
        else:
            return "老哥好！做开发和学术最烦中途断流。如果是用 Claude 和 ChatGPT，核心是出口 IP 纯净度和路由优先级。我这边整理了一份终端代理防泄露规则，你可以先参考下！"


def poll_and_respond_reddit_inbox(dry_run: bool = False, verbose: bool = True) -> list:
    """
    Poll Reddit unread inbox messages via authenticated cookie session,
    generate AI multi-round conversational replies, and dispatch automatically.
    """
    def log(msg: str):
        if verbose:
            print(msg)

    import requests

    cfg = load_config()
    reddit_cred = next((c for c in cfg.get("credentials", []) if c.get("type") == "reddit"), None)
    if not reddit_cred:
        log("[!] No Reddit credential configured.")
        return []

    cookie_str = reddit_cred.get("cookie") or reddit_cred.get("reddit_session") or ""
    if not cookie_str:
        log("[!] Reddit cookie/session is empty.")
        return []

    if "reddit_session=" not in cookie_str and "=" not in cookie_str:
        cookie_str = f"reddit_session={cookie_str}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": cookie_str,
        "Origin": "https://old.reddit.com",
        "Referer": "https://old.reddit.com/",
    }

    s = requests.Session()
    # 1. Fetch unread messages
    try:
        resp = s.get("https://old.reddit.com/message/unread.json?limit=10", headers=headers, timeout=12)
    except Exception as e:
        log(f"[!] Network error fetching unread messages: {e}")
        return []

    if resp.status_code != 200:
        log(f"[!] Failed to fetch Reddit inbox (HTTP {resp.status_code})")
        if resp.status_code in (401, 403):
            send_bark_dm_alert(
                "⚠️ Reddit 会话凭证已过期",
                f"Reddit 会话返回 HTTP {resp.status_code}，请重新获取 reddit_session Cookie！"
            )
        return []

    data = resp.json()
    items = data.get("data", {}).get("children", [])
    if not items:
        log("[*] No unread messages in Reddit inbox.")
        return []

    log(f"[+] Found {len(items)} unread inbox items.")

    # Extract modhash for POST requests
    modhash = ""
    try:
        me_resp = s.get("https://old.reddit.com/api/me.json", headers=headers, timeout=8)
        if me_resp.status_code == 200:
            modhash = me_resp.json().get("data", {}).get("modhash", "")
    except Exception:
        pass

    results = []

    for item in items:
        kind = item.get("kind")
        d = item.get("data", {})
        msg_id = d.get("name")
        author = (d.get("author") or "").strip()
        subject = d.get("subject", "")
        body = d.get("body", "").strip()

        # Skip bots or self
        if not author or author.lower() in BOT_BLOCKLIST or author.lower() == "last_ad_9446":
            continue

        log(f"[*] Processing inbound message from u/{author} (Kind: {kind}, Subject: {subject})")
        log(f"    Content: {body[:100]}...")

        # 2. Retrieve or compute conversation round
        state = get_conversation_state(author, platform="reddit")
        curr_round = state.get("current_round", 1)
        next_round = analyze_inbound_intent(body, curr_round)

        # 3. Draft AI response
        ai_reply = draft_automated_reply(
            partner_handle=author,
            inbound_text=body,
            target_round=next_round,
            platform="reddit"
        )

        log(f"    [AI Generated Round {next_round} Reply]:\n    {ai_reply}")

        # 4. Dispatch reply if not dry-run
        sent_successfully = False
        if not dry_run and modhash:
            # Add human-like typing jitter delay (10 - 25 seconds)
            jitter_sec = random.randint(10, 25)
            log(f"    Simulating human reading & typing delay ({jitter_sec}s)...")
            time.sleep(jitter_sec)

            # Reply via Reddit API
            # For messages (t4) or comment replies (t1), Reddit API accepts parent=msg_id on /api/comment
            post_data = {
                "api_type": "json",
                "thing_id": msg_id,
                "text": ai_reply,
                "uh": modhash
            }
            try:
                reply_resp = s.post("https://old.reddit.com/api/comment", data=post_data, headers=headers, timeout=15)
                if reply_resp.status_code == 200 and not reply_resp.json().get("json", {}).get("errors"):
                    sent_successfully = True
                    log(f"    [+] Successfully dispatched automated reply to u/{author}!")
                else:
                    log(f"    [!] Error sending comment reply: {reply_resp.text[:150]}")
            except Exception as e:
                log(f"    [!] Exception sending reply: {e}")

            # Mark message as read
            try:
                s.post("https://old.reddit.com/api/read_message", data={"id": msg_id, "uh": modhash}, headers=headers, timeout=8)
            except Exception:
                pass
        else:
            log("    [!] Dry-run mode: skipping network dispatch.")

        # 5. Update state in database
        state["thread_id"] = msg_id
        state["current_round"] = min(next_round + 1, 3)
        state["subject"] = subject
        state["last_inbound_msg"] = body
        state["last_outbound_msg"] = ai_reply
        state["status"] = "replied" if sent_successfully else "drafted"
        save_conversation_state(state)

        # 6. Push real-time Bark notification to user device
        send_bark_dm_alert(
            f"Reddit 私信自愈对齐: u/{author} (Round {next_round})",
            f"收到: \"{body[:60]}\"\nAI回复: \"{ai_reply[:80]}...\"",
            url=f"https://www.reddit.com/message/messages/"
        )

        results.append({
            "author": author,
            "platform": "reddit",
            "msg_id": msg_id,
            "round": next_round,
            "inbound": body,
            "reply": ai_reply,
            "sent": sent_successfully
        })

    return results


def poll_and_respond_x_inbox(dry_run: bool = False, verbose: bool = True) -> list:
    """
    Poll X (Twitter) unread DM conversations via authenticated Web Session,
    detect inbound partner messages, generate AI multi-round closing replies,
    dispatch via X web API, and notify via Bark.
    """
    def log(msg: str):
        if verbose:
            print(msg)

    import requests
    import uuid

    cfg = load_config()
    x_cred = next((c for c in cfg.get("credentials", []) if c.get("type") in ("x", "twitter")), None)
    if not x_cred:
        log("[!] No X (Twitter) credential configured.")
        return []

    auth_token = x_cred.get("auth_token")
    ct0 = x_cred.get("ct0")
    if not auth_token or not ct0:
        log("[!] X (Twitter) auth_token or ct0 is missing.")
        return []

    headers = {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-csrf-token": ct0,
        "cookie": f"auth_token={auth_token}; ct0={ct0}",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session"
    }

    s = requests.Session()
    try:
        resp = s.get("https://x.com/i/api/1.1/dm/inbox_initial_state.json", headers=headers, timeout=12)
    except Exception as e:
        log(f"[!] Network error fetching X DMs: {e}")
        return []

    if resp.status_code != 200:
        log(f"[!] Failed to fetch X DMs (HTTP {resp.status_code})")
        if resp.status_code in (401, 403):
            send_bark_dm_alert(
                "⚠️ X (Twitter) 会话凭证已过期",
                f"X 返回 HTTP {resp.status_code}，请重新获取 auth_token 和 ct0！"
            )
        return []

    st = resp.json().get("inbox_initial_state", {})
    convs = st.get("conversations", {})
    entries = st.get("entries", [])
    users = st.get("users", {})

    if not convs:
        log("[*] No DM conversations found on X.")
        return []

    # Identify our own account user_id from conversations
    my_user_id = None
    for cid, cdata in convs.items():
        parts = cdata.get("participants", [])
        for p in parts:
            if "last_read_event_id" in p:
                my_user_id = str(p.get("user_id"))
                break
        if my_user_id:
            break

    # Group entries by conversation_id
    conv_entries: dict[str, list] = {}
    for e in entries:
        msg = e.get("message", {})
        mdata = msg.get("message_data", {})
        cid = msg.get("conversation_id")
        if cid and mdata:
            conv_entries.setdefault(cid, []).append(mdata)

    results = []

    for cid, cdata in convs.items():
        # Find partner user_id
        parts = cdata.get("participants", [])
        partner_uid = None
        for p in parts:
            uid = str(p.get("user_id"))
            if uid != my_user_id:
                partner_uid = uid
                break

        if not partner_uid or partner_uid not in users:
            continue

        partner_info = users.get(partner_uid, {})
        screen_name = partner_info.get("screen_name") or f"user_{partner_uid}"
        partner_name = partner_info.get("name") or screen_name

        # Get latest message in this conversation
        c_msgs = conv_entries.get(cid, [])
        if not c_msgs:
            continue

        # Sort messages by time descending
        c_msgs.sort(key=lambda m: int(m.get("time") or 0), reverse=True)
        latest_msg = c_msgs[0]
        sender_id = str(latest_msg.get("sender_id"))
        msg_text = (latest_msg.get("text") or "").strip()
        msg_id = str(latest_msg.get("id"))

        # If latest message was sent by ourselves, partner hasn't replied yet
        if sender_id == my_user_id:
            continue

        # Check existing conversation state in database
        state = get_conversation_state(screen_name, platform="x")
        last_seen_msg = state.get("last_inbound_msg", "")

        # If this inbound message is already processed, skip
        if last_seen_msg == msg_text or state.get("thread_id") == msg_id:
            continue

        log(f"[*] Found new inbound X DM from @{screen_name} ({partner_name}):")
        log(f"    Message: {msg_text[:100]}...")

        # Analyze intent and select round
        curr_round = state.get("current_round", 1)
        next_round = analyze_inbound_intent(msg_text, curr_round)

        # Draft AI response
        ai_reply = draft_automated_reply(
            partner_handle=screen_name,
            inbound_text=msg_text,
            target_round=next_round,
            platform="x"
        )

        log(f"    [AI Generated Round {next_round} Reply for X]:\n    {ai_reply}")

        sent_successfully = False
        if not dry_run:
            jitter_sec = random.randint(10, 25)
            log(f"    Simulating human reading & typing delay ({jitter_sec}s)...")
            time.sleep(jitter_sec)

            post_headers = dict(headers)
            post_headers["content-type"] = "application/json"
            post_payload = {
                "conversation_id": cid,
                "recipient_ids": False,
                "request_id": str(uuid.uuid4()),
                "text": ai_reply
            }
            try:
                reply_resp = s.post("https://x.com/i/api/1.1/dm/new2.json", headers=post_headers, json=post_payload, timeout=15)
                if reply_resp.status_code in (200, 201):
                    sent_successfully = True
                    log(f"    [+] Successfully dispatched automated reply to @{screen_name} on X!")
                else:
                    log(f"    [!] Error sending X DM: {reply_resp.text[:150]}")
            except Exception as e:
                log(f"    [!] Exception sending X DM: {e}")
        else:
            log("    [!] Dry-run mode: skipping X network dispatch.")

        # Save state
        state["thread_id"] = msg_id
        state["current_round"] = min(next_round + 1, 3)
        state["subject"] = "X Direct Message"
        state["last_inbound_msg"] = msg_text
        state["last_outbound_msg"] = ai_reply
        state["status"] = "replied" if sent_successfully else "drafted"
        save_conversation_state(state)

        # Push Bark
        send_bark_dm_alert(
            f"X (Twitter) 私信对齐: @{screen_name} (Round {next_round})",
            f"收到: \"{msg_text[:60]}\"\nAI回复: \"{ai_reply[:80]}...\"",
            url=f"https://x.com/messages/{cid}"
        )

        results.append({
            "author": screen_name,
            "platform": "x",
            "msg_id": msg_id,
            "round": next_round,
            "inbound": msg_text,
            "reply": ai_reply,
            "sent": sent_successfully
        })

    return results


def poll_and_respond_all_inboxes(dry_run: bool = False, platform: str = "all", verbose: bool = True) -> list:
    """Unified runner to poll and respond across both Reddit and X."""
    all_results = []
    if platform in ("all", "reddit"):
        all_results.extend(poll_and_respond_reddit_inbox(dry_run=dry_run, verbose=verbose))
    if platform in ("all", "x", "twitter"):
        all_results.extend(poll_and_respond_x_inbox(dry_run=dry_run, verbose=verbose))
    return all_results


def check_session_health() -> list[dict]:
    """
    Session Keeper & Diagnostics Doctor (inspired by twikit / openmagpie).
    Actively checks Reddit, X (Twitter), Bark, and AI service health, returning diagnostic records.
    """
    import requests
    cfg = load_config()
    diagnostics = []

    # 1. Reddit Web Session Check
    r_cred = next((c for c in cfg.get("credentials", []) if c.get("type") == "reddit"), None)
    if r_cred:
        r_cookie = r_cred.get("session_cookie") or r_cred.get("reddit_session")
        if r_cookie:
            try:
                r_resp = requests.get(
                    "https://old.reddit.com/api/me.json",
                    headers={
                        "cookie": f"reddit_session={r_cookie}",
                        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    },
                    timeout=8
                )
                if r_resp.status_code == 200:
                    data = r_resp.json().get("data", {})
                    diagnostics.append({
                        "platform": "reddit",
                        "name": "Reddit Web Session",
                        "status": "healthy",
                        "account": f"u/{data.get('name')}",
                        "details": f"Karma: {data.get('link_karma', 0) + data.get('comment_karma', 0)}"
                    })
                else:
                    diagnostics.append({
                        "platform": "reddit",
                        "name": "Reddit Web Session",
                        "status": "expired",
                        "account": r_cred.get("name", "Reddit"),
                        "details": f"HTTP {r_resp.status_code} (Cookie expired or blocked)"
                    })
            except Exception as e:
                diagnostics.append({
                    "platform": "reddit",
                    "name": "Reddit Web Session",
                    "status": "unreachable",
                    "account": r_cred.get("name", "Reddit"),
                    "details": str(e)[:60]
                })

    # 2. X (Twitter) Web Session Check
    x_cred = next((c for c in cfg.get("credentials", []) if c.get("type") in ("x", "twitter")), None)
    if x_cred:
        auth_token = x_cred.get("auth_token")
        ct0 = x_cred.get("ct0")
        if auth_token and ct0:
            try:
                x_resp = requests.get(
                    "https://x.com/i/api/1.1/dm/inbox_initial_state.json",
                    headers={
                        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
                        "x-csrf-token": ct0,
                        "cookie": f"auth_token={auth_token}; ct0={ct0}",
                        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    },
                    timeout=8
                )
                if x_resp.status_code == 200:
                    st = x_resp.json().get("inbox_initial_state", {})
                    users = st.get("users", {})
                    my_handle = "hanshan0228"
                    for uid, u in users.items():
                        if u.get("screen_name") == "hanshan0228":
                            my_handle = u.get("screen_name")
                            break
                    diagnostics.append({
                        "platform": "x",
                        "name": "X (Twitter) Web Session",
                        "status": "healthy",
                        "account": f"@{my_handle}",
                        "details": "Authenticated & Live"
                    })
                else:
                    diagnostics.append({
                        "platform": "x",
                        "name": "X (Twitter) Web Session",
                        "status": "expired",
                        "account": x_cred.get("name", "X"),
                        "details": f"HTTP {x_resp.status_code} (auth_token/ct0 expired)"
                    })
            except Exception as e:
                diagnostics.append({
                    "platform": "x",
                    "name": "X (Twitter) Web Session",
                    "status": "unreachable",
                    "account": x_cred.get("name", "X"),
                    "details": str(e)[:60]
                })

    # 3. Bark Mobile Push Check
    if BARK_WEBHOOK:
        try:
            b_resp = requests.get(f"{BARK_WEBHOOK.rstrip('/')}/ping", timeout=5)
            if b_resp.status_code == 200 and b_resp.json().get("code") == 200:
                diagnostics.append({
                    "platform": "bark",
                    "name": "Bark Mobile Push",
                    "status": "healthy",
                    "account": "iPhone Device",
                    "details": "Endpoint reachable & responsive"
                })
            else:
                diagnostics.append({
                    "platform": "bark",
                    "name": "Bark Mobile Push",
                    "status": "warning",
                    "account": "iPhone Device",
                    "details": f"HTTP {b_resp.status_code}"
                })
        except Exception as e:
            diagnostics.append({
                "platform": "bark",
                "name": "Bark Mobile Push",
                "status": "unreachable",
                "account": "iPhone Device",
                "details": str(e)[:60]
            })

    # 4. AI Gateway Check
    from ai import resolve_ai_cred
    ai_cred = resolve_ai_cred(cfg, None)
    if ai_cred and ai_cred.get("api_key"):
        diagnostics.append({
            "platform": "ai",
            "name": f"AI Engine ({ai_cred.get('type', 'api').upper()})",
            "status": "healthy",
            "account": ai_cred.get("model", "default"),
            "details": f"API Key configured ({ai_cred.get('api_key')[:6]}...)"
        })
    else:
        diagnostics.append({
            "platform": "ai",
            "name": "AI Engine",
            "status": "missing",
            "account": "None",
            "details": "No AI API key found"
        })

    return diagnostics


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    plat = "all"
    for arg in sys.argv:
        if arg.startswith("--platform="):
            plat = arg.split("=")[-1]
    print(f"[*] Starting RedSignal Inbound DM & Chat Agent (platform={plat}, dry_run={dry})...")
    poll_and_respond_all_inboxes(dry_run=dry, platform=plat)
