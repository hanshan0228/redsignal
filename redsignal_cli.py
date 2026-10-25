#!/usr/bin/env python3
"""
RedSignal Agentic CLI Tool
Unified command-line interface for the RedSignal Agentic Skill:
- radar / leads: Real-time scan, multi-subreddit aggregation & search
- quota: Safe cadence & daily limit monitor (8-reply guardrail & cooldown)
- post: Human-in-the-loop verified dispatch with Web session / API
- playbook: 3-stage conversational strategy & dynamic tool routing
- tools: Available high-converting landing tools catalog
"""

import sys
import os
import re
import argparse
import json
import time
import datetime
import urllib.request as _urllib_req
import xml.etree.ElementTree as _ET
import subprocess

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_db
from config import load_config, save_config
from ai import (
    resolve_ai_cred,
    resolve_dynamic_tool_url,
    generate_dm_pitch,
    generate_conversion_playbook,
    classify_funnel_tier,
    calculate_opportunity_score
)
from auto_responder import (
    check_rate_limits,
    submit_reddit_reply,
    submit_x_reply,
    record_successful_reply,
    create_attributed_short_link,
    check_rolling_link_ratio,
    downgrade_reply_links_to_brand_search,
    get_account_maturity_tier
)


def _sync_reddit_rss(limit=25, campaign=""):
    """Fetch latest Reddit posts via Authenticated Multireddit RSS and insert new hits."""
    cfg = load_config()
    reddit_lst = None
    if campaign:
        for l in cfg.get("listeners", []):
            if l.get("platform") == "reddit" and (
                l.get("id") == campaign
                or campaign.lower() in (l.get("site_name", "") or "").lower()
                or campaign.lower() in (l.get("name", "") or "").lower()
            ):
                reddit_lst = l
                break
    if not reddit_lst:
        reddit_lst = next((l for l in cfg.get("listeners", []) if l.get("platform") == "reddit"), None)
    if not reddit_lst:
        return 0, "未配置 Reddit 监听器"

    subs = (reddit_lst.get("subreddits") or "golfcarts ClubCar").split()
    if not subs:
        return 0, "未配置监控版块"

    # Resolve cookie
    cookie = ""
    cred_id = reddit_lst.get("reddit_credential_id")
    if cred_id:
        c = next((item for item in cfg.get("credentials", []) if item.get("id") == cred_id), None)
        if c:
            cookie = c.get("cookie") or c.get("reddit_session") or ""
    if not cookie:
        try:
            from barnacle import get_reddit_cookie
            cookie = get_reddit_cookie()
        except Exception:
            pass

    sub_query = "+".join(subs[:8])
    url = f"https://www.reddit.com/r/{sub_query}/new.rss"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
    }
    if cookie:
        headers["Cookie"] = f"reddit_session={cookie}" if "reddit_session=" not in cookie else cookie

    new_count = 0
    try:
        req = _urllib_req.Request(url, headers=headers)
        with _urllib_req.urlopen(req, timeout=12) as resp:
            tree = _ET.fromstring(resp.read().decode("utf-8", errors="ignore"))
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = tree.findall("atom:entry", ns)

            with get_db() as db:
                for entry in entries:
                    id_el = entry.find("atom:id", ns)
                    raw_id = id_el.text if id_el is not None else ""
                    if not raw_id:
                        continue

                    # Extract clean Reddit post ID (e.g. t3_1wn7oqp)
                    hit_id = raw_id.split("/")[-1] if "/" in raw_id else raw_id
                    if not hit_id.startswith("t3_") and "_" in raw_id:
                        hit_id = "t3_" + raw_id.split("_")[-1]

                    # Check exists
                    exists = db.execute("SELECT id FROM hits WHERE hit_id=?", (hit_id,)).fetchone()
                    if exists:
                        continue

                    title_el = entry.find("atom:title", ns)
                    title = title_el.text if title_el is not None else ""

                    link_el = entry.find("atom:link", ns)
                    target_url = link_el.attrib.get("href", "") if link_el is not None else ""

                    author_el = entry.find("atom:author/atom:name", ns)
                    author = author_el.text.replace("/u/", "") if author_el is not None and author_el.text else "unknown"

                    cat_el = entry.find("atom:category", ns)
                    sub_name = (cat_el.attrib.get("term", "") if cat_el is not None else "") or "golfcarts"

                    content_el = entry.find("atom:content", ns)
                    content_raw = content_el.text if content_el is not None else ""
                    # Simple HTML strip
                    import re
                    excerpt = re.sub(r"<[^>]+>", " ", content_raw).strip()[:400]
                    full_text = f"{title} {excerpt}"

                    # Match listener keywords & negative keywords if configured
                    kws = [k for k in (reddit_lst.get("keywords") or []) if k.strip()]
                    if kws:
                        try:
                            pat = re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(kws) + r")(?![A-Za-z0-9])", re.IGNORECASE)
                            if not pat.search(full_text):
                                continue
                        except Exception:
                            pass

                    neg_kws = [k for k in (reddit_lst.get("negative_keywords") or []) if k.strip()]
                    if neg_kws:
                        try:
                            neg_pat = re.compile("|".join(neg_kws), re.IGNORECASE)
                            if neg_pat.search(full_text):
                                continue
                        except Exception:
                            pass

                    pub_el = entry.find("atom:published", ns)
                    if pub_el is None:
                        pub_el = entry.find("atom:updated", ns)
                    pub_str = pub_el.text.strip() if pub_el is not None and pub_el.text else datetime.datetime.utcnow().isoformat() + "Z"

                    # Classify intent & score
                    tier, reason = classify_funnel_tier(title, excerpt, custom_keywords=reddit_lst.get("keywords"))
                    opp = calculate_opportunity_score(title, excerpt, funnel_tier=tier, listener_keywords=reddit_lst.get("keywords"))

                    db.execute(
                        """INSERT INTO hits (
                            hit_id, listener_id, listener_name, platform, subreddit, author, title,
                            excerpt, url, created_at, filter_passed,
                            funnel_tier, funnel_reason, opportunity_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                        (
                            hit_id, reddit_lst.get("id"), reddit_lst.get("name") or "", "reddit", sub_name, author, title,
                            excerpt, target_url, pub_str,
                            tier, reason, opp.get("score", 70)
                        )
                    )
                    new_count += 1
            return new_count, f"成功同步抓取 {len(entries)} 条贴文，新收录入库 {new_count} 条线索。"
    except Exception as e:
        return 0, f"RSS 同步拉取异常: {e}"


def cmd_radar(args):
    """Radar & Leads discovery."""
    campaign = (getattr(args, "campaign", "") or "").strip()
    if getattr(args, "sync", False):
        new_c, msg = _sync_reddit_rss(limit=25, campaign=campaign)
        if not getattr(args, "json", False):
            print(f"🔄 [Radar Sync] {msg}")

    limit = args.limit or 10
    platform = (args.platform or "all").lower()
    sub = (args.sub or "").strip()
    keyword = (args.keyword or "").strip()
    campaign = (getattr(args, "campaign", "") or "").strip()
    intent = (getattr(args, "intent", "") or "").strip().lower()

    where_clauses = ["(filter_passed=1 OR filter_passed IS NULL)"]
    params = []

    if platform != "all":
        where_clauses.append("platform=?")
        params.append(platform)

    if sub:
        where_clauses.append("LOWER(subreddit) LIKE ?")
        params.append(f"%{sub.lower()}%")

    if keyword:
        where_clauses.append("(LOWER(title) LIKE ? OR LOWER(excerpt) LIKE ?)")
        params.extend([f"%{keyword.lower()}%", f"%{keyword.lower()}%"])

    if campaign:
        where_clauses.append("(listener_id=? OR LOWER(listener_name) LIKE ?)")
        params.extend([campaign, f"%{campaign.lower()}%"])

    fetch_limit = limit * 4 if intent else limit
    query = f"""
        SELECT id, hit_id, platform, subreddit, author, title, excerpt, url,
               created_at, funnel_tier, opportunity_score, listener_id, listener_name
        FROM hits
        WHERE {' AND '.join(where_clauses)}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(fetch_limit)

    with get_db() as db:
        rows = [dict(r) for r in db.execute(query, params).fetchall()]

    from ai import detect_affiliate_intent
    for r in rows:
        aff = detect_affiliate_intent(r.get("title", ""), r.get("excerpt", ""), created_at=r.get("created_at"))
        r["affiliate_intent"] = aff

    if intent:
        if intent == "affiliate":
            rows = [r for r in rows if r["affiliate_intent"]["intent"] in ("alternative", "compare", "deal", "review")]
        else:
            rows = [r for r in rows if r["affiliate_intent"]["intent"] == intent]
        rows = rows[:limit]

    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if not rows:
        print("🔍 暂未检索到符合条件的有效商机线索 (No matching leads found)")
        return

    print(f"\n🎯 【RedSignal 社媒截流雷达 (Top {len(rows)})】\n" + "=" * 76)
    for r in rows:
        hid = r["hit_id"] or str(r["id"])
        plat = (r["platform"] or "reddit").upper()
        author = r["author"] or "anon"
        subreddit = r["subreddit"] or "web"
        tier = f"Tier {r['funnel_tier']}" if str(r.get("funnel_tier", "")).isdigit() else (r.get("funnel_tier") or "Tier 2")
        score = r.get("opportunity_score") or 70
        title = r["title"] or ""
        created = (r.get("created_at") or "")[:16].replace("T", " ")
        badge = r["affiliate_intent"].get("badge", "💬 通用讨论")
        buying_score = r["affiliate_intent"].get("buying_score", 50)
        urgency = r["affiliate_intent"].get("urgency_level", "")

        print(f"[{plat}] ID: {hid:<16} | r/{subreddit:<14} | @{author:<15} [{badge} | 买家意向: {buying_score}分 | {urgency}]")
        print(f"  📝 标题: {title[:75]}")
        print(f"  🔗 链接: {r.get('url') or 'N/A'} ({created})")
        print("-" * 76)
    print("👉 提示:")
    print("  • 联盟高转化攻坚: `python3 redsignal_cli.py affiliate <hit_id> [--product <name>] [--url <link>]`")
    print("  • 自营转化心智流: `python3 redsignal_cli.py playbook <hit_id>`")
    print("  • 发送回复(演练): `python3 redsignal_cli.py post <hit_id> --text '...' --dry-run`\n")


def cmd_quota(args):
    """Inspect safe cadence, daily limits, cooldown countdown and account health."""
    cfg = load_config()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    now = time.time()
    accounts_status = []
    with get_db() as db:
        for cred in cfg.get("credentials", []):
            cid = cred.get("id")
            cname = cred.get("name") or "Unnamed"
            ctype = cred.get("type") or "unknown"
            if not ctype or ctype in ("anthropic", "openai", "groq", "deepseek"):
                continue

            is_reddit = (ctype == "reddit")
            is_forum = ctype in ("forum", "vbulletin", "phpbb", "xenforo")
            is_cookie_x = (not is_reddit and not is_forum and bool(cred.get("auth_token") and not cred.get("api_key")))

            if is_reddit:
                daily_limit = 8
                cooldown_seconds = 45 * 60
            elif is_cookie_x:
                daily_limit = 5
                cooldown_seconds = 45 * 60
            elif is_forum:
                daily_limit = 15
                cooldown_seconds = 15 * 60
            else:
                daily_limit = 25
                cooldown_seconds = 15 * 60

            row = db.execute(
                "SELECT reply_count, last_reply_ts, is_quarantined, quarantine_until, rate_limit_until FROM account_quota WHERE credential_id=? AND date_str=?",
                (cid, today)
            ).fetchone()

            prev = db.execute(
                "SELECT is_quarantined, quarantine_until, rate_limit_until FROM account_quota WHERE credential_id=? ORDER BY id DESC LIMIT 1",
                (cid,)
            ).fetchone()

            used = row["reply_count"] if row else 0
            last_ts = row["last_reply_ts"] if row else 0.0

            quar_until = max(row["quarantine_until"] if row else 0, prev["quarantine_until"] if prev else 0)
            is_quarantined = bool(((row and row["is_quarantined"]) or (prev and prev["is_quarantined"])) and quar_until > now)

            rl_until = max(
                row["rate_limit_until"] if (row and "rate_limit_until" in row.keys() and row["rate_limit_until"]) else 0,
                prev["rate_limit_until"] if (prev and "rate_limit_until" in prev.keys() and prev["rate_limit_until"]) else 0
            )
            rate_limit_active = bool(rl_until > now)

            elapsed = now - last_ts if last_ts > 0 else 999999
            remaining_cooldown = max(0, int(cooldown_seconds - elapsed))
            remaining_quota = max(0, daily_limit - used)

            # Rolling Link Ratio & Maturity check
            rlr_allowed, rlr_ratio, rlr_link_cnt, rlr_total = check_rolling_link_ratio(cid, max_link_ratio=0.20, window_size=10)
            raw_karma = int(cred.get("karma") or 100)
            maturity = get_account_maturity_tier(karma=raw_karma)

            accounts_status.append({
                "credential_id": cid,
                "name": cname,
                "type": ctype,
                "daily_limit": daily_limit,
                "used_today": used,
                "remaining_quota": remaining_quota,
                "cooldown_remaining_seconds": remaining_cooldown,
                "cooldown_ready": remaining_cooldown == 0 and not is_quarantined and not rate_limit_active,
                "is_quarantined": is_quarantined,
                "rate_limit_active": rate_limit_active,
                "rate_limit_until": rl_until,
                "last_reply_time": datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S") if last_ts > 0 else "None",
                "rolling_link_ratio": rlr_ratio,
                "rolling_link_count": rlr_link_cnt,
                "rolling_total_count": rlr_total,
                "rolling_link_safe": rlr_allowed,
                "maturity_tier": maturity["tier"],
                "maturity_name": maturity["name"]
            })

    if getattr(args, "json", False):
        print(json.dumps(accounts_status, ensure_ascii=False, indent=2))
        return

    print(f"\n🛡️ 【RedSignal 账号频控与防封配额雷达 (今日: {today})】\n" + "=" * 74)
    for acc in accounts_status:
        status_icon = "🟢 可安全发帖" if (acc["cooldown_ready"] and acc["remaining_quota"] > 0 and not acc["is_quarantined"]) else "🟡 冷却中"
        if acc["remaining_quota"] <= 0:
            status_icon = "🔴 今日配额已耗尽 (8/8)"
        if acc["is_quarantined"]:
            status_icon = "⛔ 账号风控隔离中"

        link_status = "🟢 留链安全" if acc["rolling_link_safe"] else "🟡 建议纯干货洗号 (已近20%红线)"
        print(f"账号: {acc['name']} ({acc['type'].upper()}) [{status_icon}]")
        print(f"  • 账号成熟度: {acc['maturity_name']}")
        print(f"  • 今日发帖: {acc['used_today']} / {acc['daily_limit']} 篇 (剩余配额: {acc['remaining_quota']})")
        print(f"  • 外链安全率: {round(acc['rolling_link_ratio'] * 100)}% ({acc['rolling_link_count']}/{acc['rolling_total_count']} 篇带链 - {link_status})")
        if acc["cooldown_remaining_seconds"] > 0:
            mins = acc["cooldown_remaining_seconds"] // 60
            secs = acc["cooldown_remaining_seconds"] % 60
            print(f"  • 冷却倒计时: 还需等待 {mins}分{secs}秒 (安全间歇: 45分钟)")
        else:
            print(f"  • 冷却状态: 冷却完毕，随时可安全触达")
        print(f"  • 上次发帖: {acc['last_reply_time']}")
        print("-" * 74)
    print("💡 哥飞洗号法则建议: 严守 80/20 安全比 (80% 纯技术解惑干货，20% 软植入工具品牌搜索词)。\n")


def cmd_post(args):
    """Execute verified reply dispatch with full rate limit enforcement."""
    hit_id = str(args.hit_id).strip()
    reply_text = (args.text or "").strip()
    mode = getattr(args, "mode", "brand_search")
    is_dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    if not reply_text:
        print("❌ 错误: 回复文本不能为空 (--text)")
        sys.exit(1)

    with get_db() as db:
        hit = db.execute("SELECT * FROM hits WHERE hit_id=? OR id=?", (hit_id, hit_id)).fetchone()
        if not hit:
            print(f"❌ 找不到线索: {hit_id}")
            sys.exit(1)
        hit = dict(hit)

    cfg = load_config()
    platform = hit.get("platform") or "reddit"

    # Resolve platform credential
    cred = None
    if getattr(args, "account", None):
        cred = next((c for c in cfg.get("credentials", []) if c.get("id") == args.account), None)
    if not cred:
        cred = next((c for c in cfg.get("credentials", []) if c.get("type") == platform or platform in str(c.get("name", "")).lower()), None)

    if not cred and not is_dry_run:
        print(f"❌ 错误: 未在 Vault 凭据库中找到适用于平台 [{platform}] 的发帖账号凭据")
        sys.exit(1)

    cred_id = cred.get("id") if cred else "dry_run_cred"

    # Rate limit guard
    is_cookie_x = (platform in ("x", "twitter") and bool(cred and cred.get("auth_token") and not cred.get("api_key")))
    cd_min = 45 if (platform == "reddit" or is_cookie_x) else 15
    d_lim = 8 if platform == "reddit" else (5 if is_cookie_x else 25)
    allowed, reason = check_rate_limits(cred_id, cooldown_minutes=cd_min, daily_limit=d_lim)
    if not allowed and not force and not is_dry_run:
        print(f"🚫 【发帖拦截】频控保护触发: {reason}")
        print("👉 如确需紧急绕过冷却限制请加 `--force` (仍受每日硬风控限制)")
        sys.exit(1)

    # Dynamic tool & link attribution
    lst = next((l for l in cfg.get("listeners", []) if l.get("id") == hit.get("listener_id")), None)
    site_name = (lst.get("site_name") or lst.get("name") or hit.get("listener_name") or "Fairway Fort") if lst else (hit.get("listener_name") or "Fairway Fort")
    site_url = (lst.get("site_url") or "https://fairwayfort.com") if lst else "https://fairwayfort.com"
    offers_matrix = lst.get("offers_matrix") if lst else None
    routed = resolve_dynamic_tool_url(site_url, f"{hit.get('title', '')} {hit.get('excerpt', '')}", offers_matrix=offers_matrix)
    destination_url = routed.get("routed_url") or site_url

    # Respect user/AI generated text directly.
    # NEVER blindly append robotic parentheses, fake citations, or untrusted dynamic DNS links.
    final_text = reply_text
    short_url = destination_url

    # Rolling link ratio guard & safe degradation
    has_url = bool(re.search(r"https?://", reply_text))
    force_link = getattr(args, "force_link", False)
    if has_url and not force_link and cred_id and cred_id != "dry_run_cred":
        allowed, ratio, lcnt, tcnt = check_rolling_link_ratio(cred_id, max_link_ratio=0.20, window_size=10)
        if not allowed:
            downgraded = downgrade_reply_links_to_brand_search(reply_text, site_name)
            print(f"⚠️ 【Rolling Link Ratio 提醒】最近发帖带链比已达 {round(ratio*100)}% ({lcnt}/{tcnt})，触发 20% 外链门禁！")
            if not is_dry_run:
                print(f"🛡️ 自动安全降级为品牌搜索模式，确保账号声誉安全。")
                final_text = downgraded
            else:
                print(f"🛡️ [Dry Run] 降级后文本预览: {downgraded[:100]}... (如需强行带链请加 `--force-link`)")

    is_quote = getattr(args, "quote", False)
    thread_text = getattr(args, "thread_text", "")

    reply_item = {
        "reply_text": final_text,
        "force_link": force_link,
        "is_quote_tweet": is_quote,
        "thread_reply_text": thread_text,
        "target_id": hit.get("hit_id") or hit_id,
        "post_id": hit.get("hit_id") or hit_id,
        "target_url": hit.get("url") or "",
        "hit_id": hit.get("hit_id") or hit_id,
        "subreddit": hit.get("subreddit") or "",
        "site_name": site_name
    }

    if is_dry_run:
        result = {
            "ok": True,
            "dry_run": True,
            "target": hit.get("title"),
            "url": hit.get("url"),
            "account": cred.get("name") if cred else "Mock Account",
            "reply_text": final_text,
            "mode": mode,
            "is_quote": is_quote,
            "has_thread": bool(thread_text),
            "tool_matched": routed.get("tool_name"),
            "status": "Verified & Ready for live dispatch"
        }
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            tool_disp = f"{routed.get('tool_name')} ({routed.get('tool_name_en')})" if routed.get('tool_name_en') and routed.get('tool_name_en') != routed.get('tool_name') else (routed.get('tool_name') or "General Specs")
            post_type_label = "引用推文 (Quote Tweet)" if is_quote else "评论回复 (Reply)"
            print("\n🧪 【RedSignal 发帖预演完成 (Dry Run Passed)】\n" + "=" * 70)
            print(f"📌 目标贴子: {hit.get('title')}")
            print(f"🔗 目标原链: {hit.get('url')}")
            print(f"🎯 交互类型: {post_type_label}")
            print(f"🛠 匹配落地: {tool_disp}")
            print(f"👤 发帖账号: {cred.get('name') if cred else 'Mock Account'}")
            print(f"📝 发帖内容:\n{final_text}")
            if thread_text:
                print(f"🧵 2-Tweet Thread 次推内容:\n{thread_text}")
            print("=" * 70)
            print("👉 若确认无误，去掉 `--dry-run` 即可真正发布到目标社区。\n")
        return

    # Live dispatch
    print(f"🚀 正在通过 [{cred.get('name')}] 会话安全发射回复至 {hit.get('url')}...")
    if platform == "reddit":
        res = submit_reddit_reply(reply_item, cred)
    elif platform in ("x", "twitter"):
        res = submit_x_reply(reply_item, cred)
    else:
        print(f"❌ 暂不支持向平台 [{platform}] 自动回帖")
        sys.exit(1)

    if res.get("success"):
        comment_url = res.get("comment_url") or hit.get("url")
        cid = res.get("comment_id") or ""
        record_successful_reply(cred["id"], cred.get("name") or "Account")
        now_ts = time.time()
        with get_db() as db:
            db.execute(
                """INSERT INTO reply_queue (
                    hit_id, listener_id, subreddit, author, post_id, target_id, target_url,
                    reply_text, status, comment_id, comment_url, credential_id, submitted_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?, ?, ?, ?)""",
                (
                    hit.get("hit_id"), hit.get("listener_id"), hit.get("subreddit"),
                    hit.get("author"), hit.get("hit_id"), hit.get("hit_id"), hit.get("url"),
                    final_text, cid, comment_url, cred["id"], now_ts, now_ts
                )
            )
            db.execute("UPDATE hits SET status='replied' WHERE hit_id=?", (hit.get("hit_id"),))

        print("\n🎉 【发帖成功！】")
        print(f"  • 直达链接: {comment_url}")
        if res.get("thread_comment_url"):
            print(f"  • 2-Tweet Thread 串推链接: {res.get('thread_comment_url')}")
        print(f"  • 账号配额: 已扣减 1 篇，已自动开启安全冷却计时\n")
    else:
        err = res.get("error") or ""
        if platform in ("x", "twitter") and any(k in str(err).lower() for k in ("344", "226", "daily limit", "automated", "429", "rate limit")):
            from auto_responder import record_rate_limit_cooldown
            record_rate_limit_cooldown(cred["id"], 24 * 3600, cred.get("name") or "Account")
        print(f"\n❌ 【发帖失败】: {err}\n")
        sys.exit(1)


def cmd_tools(args):
    """List dynamic landing page tools."""
    cfg = load_config()
    catalog = [
        {"name": "Golf Cart VIN Decoder", "path": "/tools/vin-decoder", "desc": "车架号型号/年份免费解码器，用于求购配件及年份鉴别帖子"},
        {"name": "Lithium Battery Range Calculator", "path": "/tools/battery-calculator", "desc": "高尔夫球车铅酸改锂电续航与电压选型计算器"},
        {"name": "LSV Street Legal Checker", "path": "/tools/street-legal-guide", "desc": "各州低速车/高尔夫球车上路合规排查指南"},
        {"name": "Precedent vs DS Comparison Chart", "path": "/tools/club-car-chart", "desc": "Club Car 核心架构底盘配件兼容对照表"},
    ]
    seen_paths = {t["path"] for t in catalog}
    for lst in cfg.get("listeners", []):
        for offer in (lst.get("offers_matrix") or []):
            url_path = offer.get("url", "")
            if url_path and url_path not in seen_paths:
                seen_paths.add(url_path)
                catalog.append({
                    "name": f"{offer.get('name', 'Tool')} [{lst.get('name', 'Campaign')}]",
                    "path": url_path,
                    "desc": f"针对关键词 {', '.join(offer.get('keywords', [])[:4])} 的专属转化落地承接页"
                })

    if getattr(args, "json", False):
        print(json.dumps(catalog, ensure_ascii=False, indent=2))
        return

    print("\n🛠️ 【RedSignal 动态高转化落地工具库】\n" + "=" * 70)
    for t in catalog:
        print(f"• {t['name']}")
        print(f"  路径: {t['path']}")
        print(f"  定位: {t['desc']}")
        print("-" * 70)
    print()


def cmd_dm(args):
    """Generate high-converting 1v1 DM outreach, official compose link, public DM hooks, and objection handlers."""
    hit_id = str(args.hit_id).strip()
    with get_db() as db:
        row = db.execute("SELECT * FROM hits WHERE hit_id=? OR id=?", (hit_id, hit_id)).fetchone()
        if not row:
            print(f"❌ 找不到线索: {hit_id}")
            sys.exit(1)
        hit = dict(row)

    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]

    cred = resolve_ai_cred(cfg, lst.get("ai_credential_id") if lst else None)
    site_name = (lst.get("site_name") or lst.get("name") or "Fairway Fort") if lst else "Fairway Fort"
    site_url  = (lst.get("site_url") or "https://fairwayfort.com") if lst else "https://fairwayfort.com"
    pitch_ins = lst.get("pitch_instruction", "") if lst else ""
    platform  = hit.get("platform") or "reddit"
    author    = hit.get("author") or "friend"
    title     = hit.get("title") or ""
    excerpt   = hit.get("excerpt") or ""

    # Dynamic Tool Routing
    routed = resolve_dynamic_tool_url(site_url, f"{title} {excerpt}")
    destination_url = routed.get("routed_url") or site_url

    # Attribution short link
    short_url = destination_url
    try:
        from auto_responder import create_attributed_short_link
        link_info = create_attributed_short_link(
            target_url=destination_url,
            hit_id=hit.get("hit_id", hit_id),
            listener_id=hit.get("listener_id", ""),
            platform=platform,
            title=title,
            text=excerpt,
            listener_name=site_name,
            campaign="cli_dm_funnel"
        )
        short_url = link_info.get("short_url") or destination_url
    except Exception:
        short_url = destination_url

    # Generate DM pitch & 3-stage playbook
    dm = generate_dm_pitch(
        title=title,
        excerpt=excerpt,
        author=author,
        site_name=site_name,
        site_url=short_url,
        pitch_instruction=pitch_ins,
        platform=platform,
        credential=cred
    )

    playbook = generate_conversion_playbook(
        title=title,
        excerpt=excerpt,
        author=author,
        site_name=site_name,
        site_url=short_url,
        pitch_instruction=pitch_ins,
        platform=platform,
        credential=cred
    )

    import urllib.parse
    subject = dm.get("subject") or "Quick troubleshooting tip regarding your cart"
    message = dm.get("message") or ""

    if platform == "reddit":
        query_params = urllib.parse.urlencode({
            "to": author,
            "subject": subject,
            "message": message
        })
        compose_url = f"https://www.reddit.com/message/compose?{query_params}"
    elif platform in ("x", "twitter"):
        compose_url = f"https://twitter.com/messages/compose?text={urllib.parse.quote(message)}"
    else:
        compose_url = ""

    # Craft high-converting Inbound DM Hook (Never falsely claim "I sent a DM")
    # Rule: Invite the user to reach out, ensuring 100% compliant, zero-spam inbound intent
    tool_key = routed.get("tool_key") or routed.get("key") or ""
    if tool_key in ("tiktok_spend_match_calculator", "ad_credit_calculator"):
        dm_hook = "I benchmarked the agency pricing tiers and spend match requirements on a spreadsheet. Feel free to shoot me a DM and I'll send it over."
    elif tool_key in ("tier_eligibility_checker", "agency_account_matcher"):
        dm_hook = "Put together a quick 1-page checklist on how to qualify for Ads Manager whitelist lines without spending limits. Drop me a DM if you want the breakdown doc."
    elif tool_key == "coupon_stack_validator":
        dm_hook = "Mapped out the official TikTok ad voucher verification flow and coupon stacking rules on a sheet. Shoot me a message if you want the checklist."
    elif tool_key in ("scaling_roas_simulator", "roas_budget_planner"):
        dm_hook = "Ran the numbers on effective CPA reduction with the tiered ad spend match. Drop me a DM if you want the break-even calculator spreadsheet."
    elif tool_key in ("ai_ip_unlock_checker", "ip_failover_status_monitor"):
        dm_hook = "Tested the clean IP node pools and automatic IP failover logs across carriers. Feel free to shoot me a DM if you want the verification sheet."
    elif tool_key == "serial_decoder":
        dm_hook = "I've got the OEM serial breakdown charts on my bench. If you're not sure which digit is the build year, feel free to shoot me a DM with the serial number and I'll look it up for you."
    elif tool_key == "street_legal":
        dm_hook = "I keep a reference sheet of the county DMV inspection requirements and FMVSS 500 checklists. If your local police department is giving you conflicting answers, feel free to shoot me a DM and I can share the state statute breakdown."
    elif tool_key == "battery_guide":
        dm_hook = "I've got the real-world AH to mileage discharge curve and BMS voltage cutoffs on my bench. If you're calculating pack weight or continuous amp draw, feel free to shoot me a DM and I'll send the comparison matrix over."
    elif tool_key == "speed_calc":
        dm_hook = "I've got the tire diameter to gear ratio RPM chart for high-speed controllers. If you're trying to figure out motor heat vs top-end speed, feel free to shoot me a DM and I can run the numbers for your setup."
    else:
        dm_hook = "I've got the comparison matrix and troubleshooting notes on my desk. If you want the raw doc, feel free to shoot me a DM and I'll share it."

    tool_disp = f"{routed.get('tool_name')} ({routed.get('tool_name_en')})" if routed.get('tool_name_en') and routed.get('tool_name_en') != routed.get('tool_name') else (routed.get('tool_name') or "General Technical Specs")

    out = {
        "hit_id": hit_id,
        "author": author,
        "platform": platform,
        "target_url": hit.get("url"),
        "routed_tool": routed,
        "short_url": short_url,
        "public_dm_hook": dm_hook,
        "dm_subject": subject,
        "dm_message": message,
        "compose_url": compose_url,
        "playbook": playbook
    }

    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"\n=======================================================================")
    print(f"🎯 【RedSignal 1v1 私信攻坚与双轨转化漏斗】 - {hit_id}")
    print(f"👤 目标发帖人: @{author} ({platform.upper()})")
    print(f"📌 帖子标题: {title}")
    print(f"🛠 智能匹配落地工具: {tool_disp} ({short_url})")
    print(f"=======================================================================\n")

    print(f"【Track 1: 公开回复私信钩子 (Public DM Hook)】")
    print(f"  👉 将此句拼在公开回帖末尾，点燃好奇并顺承转入私信:")
    print(f"  💡 \"{dm_hook}\"\n")

    print(f"【Track 2: 1v1 私信直达破冰 (Direct Message Outreach)】")
    print(f"  • 私信标题: {subject}")
    print(f"  • 私信正文:\n    \"{message}\"")
    if compose_url:
        print(f"\n  🚀 官方一键预填发信直达链接:")
        print(f"    {compose_url}")
        print(f"    (点击即可在浏览器中一键打开带好标题正文的发信窗口，0封号风险)\n")

    print(f"【三轮心智攻坚心法 (3-Stage Playbook)】")
    for r in playbook.get("rounds", []):
        print(f"  ▶ [{r.get('title')}] - 目标: {r.get('goal')}")
        print(f"    话术: \"{r.get('draft')}\"\n")

    print(f"【异议抗拒与跟进化解库】")
    for obj in playbook.get("objections", []):
        print(f"  ❓ 客户顾虑: {obj.get('objection')}")
        print(f"  🛡️ 老炮化解: \"{obj.get('response')}\"")
    print()


def cmd_playbook(args):
    """Generate 3-stage conversion playbook for a specific lead."""
    hit_id = args.hit_id
    with get_db() as db:
        row = db.execute("SELECT * FROM hits WHERE hit_id=? OR id=?", (hit_id, hit_id)).fetchone()
        if not row:
            print(f"❌ 找不到线索: {hit_id}")
            return
        hit = dict(row)

    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]

    cred = resolve_ai_cred(cfg, lst.get("ai_credential_id") if lst else None)
    site_name = (lst.get("site_name") or lst.get("name") or "My Product") if lst else "My Product"
    site_url  = (lst.get("site_url") or "") if lst else ""
    pitch_ins = lst.get("pitch_instruction", "") if lst else ""
    platform  = hit.get("platform") or "reddit"
    author    = hit.get("author") or "friend"

    # Match dynamic tool
    routed = resolve_dynamic_tool_url(site_url, f"{hit.get('title', '')} {hit.get('excerpt', '')}")
    destination_url = routed.get("routed_url") or site_url

    short_url = destination_url
    if destination_url:
        try:
            link_info = create_attributed_short_link(
                target_url=destination_url,
                hit_id=hit.get("hit_id", hit_id),
                listener_id=hit.get("listener_id", ""),
                platform=platform,
                title=hit.get("title", ""),
                text=hit.get("excerpt", ""),
                listener_name=site_name,
                campaign="cli_playbook"
            )
            short_url = link_info.get("short_url") or destination_url
        except Exception:
            short_url = destination_url

    playbook = generate_conversion_playbook(
        title=hit.get("title") or "",
        excerpt=hit.get("excerpt") or "",
        author=author,
        site_name=site_name,
        site_url=short_url,
        pitch_instruction=pitch_ins,
        platform=platform,
        credential=cred
    )

    dm = generate_dm_pitch(
        title=hit.get("title") or "",
        excerpt=hit.get("excerpt") or "",
        author=author,
        site_name=site_name,
        site_url=short_url,
        pitch_instruction=pitch_ins,
        platform=platform,
        credential=cred
    )

    if getattr(args, "json", False):
        out = {
            "hit_id": hit_id,
            "target": hit.get("title"),
            "author": author,
            "platform": platform,
            "tool": routed,
            "playbook": playbook,
            "dm": dm
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    tool_disp = f"{routed.get('tool_name')} ({routed.get('tool_name_en')})" if routed.get('tool_name_en') and routed.get('tool_name_en') != routed.get('tool_name') else (routed.get('tool_name') or "General Specs")
    print(f"\n=======================================================")
    print(f"🎯 【RedSignal 聊单转化攻坚锦囊】 - {hit_id}")
    print(f"👤 目标发帖人: {author} ({platform.title()})")
    print(f"📌 帖子标题: {hit.get('title', '')}")
    print(f"🛠 智能匹配落地工具: {tool_disp} ({short_url})")
    print(f"=======================================================\n")

    profile = playbook.get("target_profile", {})
    print(f"【客户画像与痛点】")
    print(f"  • 意向等级: {profile.get('intent_level', 'Tier 1')}")
    print(f"  • 核心痛点: {profile.get('primary_pain', '')}")
    print(f"  • 攻坚角度: {profile.get('recommended_angle', '')}\n")

    print(f"【三轮递进聊单心智流】")
    for r in playbook.get("rounds", []):
        print(f"\n▶ [{r.get('title')}] - 目标: {r.get('goal')}")
        print(f"  💬 话术: \"{r.get('draft')}\"")

    print(f"\n【常见异议速查与化解】")
    for obj in playbook.get("objections", []):
        print(f"  ❓ 问: {obj.get('objection')}")
        print(f"  💡 答: \"{obj.get('response')}\"")

    print(f"\n【⚡ 极速 1v1 私信备料】")
    print(f"  Subject: {dm.get('subject')}")
    print(f"  Message: {dm.get('message')}\n")


def cmd_queue(args):
    """List queue items."""
    with get_db() as db:
        rows = [dict(r) for r in db.execute(
            """SELECT id, hit_id, subreddit, author, status, reply_text, scheduled_at, short_url
               FROM reply_queue
               ORDER BY id DESC
               LIMIT 10"""
        ).fetchall()]

    if getattr(args, "json", False):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    if not rows:
        print("📭 当前队列为空 (Queue is empty)")
        return

    print("\n📦 【RedSignal 当前回复队列 (Top 10)】\n" + "=" * 70)
    for r in rows:
        print(f"Queue #{r['id']} [{r['status'].upper()}] - To @{r['author']} in r/{r['subreddit']}")
        print(f"  文本: {r['reply_text'][:65]}...")
        if r['short_url']:
            print(f"  短链: {r['short_url']}")
        print("-" * 70)
    print()


def cmd_campaigns(args):
    """List all configured marketing campaigns, affiliate offers, and listener configurations."""
    cfg = load_config()
    listeners = cfg.get("listeners", [])
    if getattr(args, "json", False):
        print(json.dumps(listeners, ensure_ascii=False, indent=2))
        return

    print(f"\n🚀 【RedSignal 全局营销与联盟项目矩阵 (Campaigns: {len(listeners)})】\n" + "=" * 76)
    if not listeners:
        print("暂无已配置的项目。可通过 `python3 redsignal_cli.py add-campaign` 快速创建。")
        return

    for l in listeners:
        lid = l.get("id")
        name = l.get("name") or "Unnamed"
        site_name = l.get("site_name") or name
        site_url = l.get("site_url") or "N/A"
        subs = l.get("subreddits") or []
        subs_str = ", ".join(subs[:4]) if isinstance(subs, list) else str(subs)
        kws = l.get("keywords") or []
        kws_str = ", ".join(kws[:5]) if isinstance(kws, list) else str(kws)
        offers = l.get("offers_matrix") or []
        enabled = "🟢 运行中" if l.get("enabled", True) else "⚪ 已停用"

        print(f"项目 ID: {lid:<18} [{enabled}]")
        print(f"  • 产品/品牌: {site_name} ({site_url})")
        print(f"  • 监控版块: {subs_str}")
        print(f"  • 核心词根: {kws_str}")
        print(f"  • 落地工具/Offer: {len(offers)} 个已激活承接点")
        print("-" * 76)
    print("👉 提示:")
    print("  • 针对特定项目雷达扫描: `python3 redsignal_cli.py radar --campaign <id>`")
    print("  • 添加新联盟项目: `python3 redsignal_cli.py add-campaign --name <name> --url <url>`\n")


def cmd_add_campaign(args):
    """Quickly register a new affiliate product, SaaS, or marketing campaign."""
    name = (args.name or "").strip()
    url = (args.url or "").strip()
    subreddits = (args.subreddits or "SaaS,Entrepreneur,startups").split(",")
    keywords = (args.keywords or "alternative,vs,recommend,pricing,discount").split(",")
    desc = getattr(args, "desc", "") or f"{name} promotional & affiliate campaign"
    pitch = getattr(args, "pitch", "") or "Provide authentic peer-to-peer technical help first; recommend tool as the high-ROI solution."

    if not name or not url:
        print("❌ 错误: 必须指定 --name 和 --url。")
        return

    cfg = load_config()
    cred = resolve_ai_cred(cfg, None)

    import uuid
    camp_id = f"camp_{uuid.uuid4().hex[:8]}"

    from ai import generate_offers_matrix_with_ai
    offers = generate_offers_matrix_with_ai(
        site_name=name,
        site_description=desc,
        site_url=url,
        keywords=keywords,
        credential=cred
    )

    clean_subs = [s.strip() for s in subreddits if s.strip()]
    clean_kws = [k.strip().lower() for k in keywords if k.strip()]

    new_listener = {
        "id": camp_id,
        "name": name,
        "enabled": True,
        "subreddits": " ".join(clean_subs),
        "webhook": "",
        "whitelist": [],
        "keywords": clean_kws,
        "filters": [],
        "negative_keywords": [],
        "min_karma": 0,
        "min_account_age_days": 0,
        "auto_reply_enabled": True,
        "site_name": name,
        "site_url": url,
        "site_description": desc,
        "pitch_instruction": pitch,
        "anti_ban_mode": "brand_search",
        "auto_submit_enabled": False,
        "reply_cooldown_minutes": 45,
        "daily_reply_limit": 8,
        "platform": "reddit",
        "stealth_mode": "direct_link",
        "dark_fleet_enabled": True,
        "dark_fleet_min_safety": 85,
        "dark_fleet_min_opp": 70,
        "visual_assets": [],
        "personas": [],
        "offers_matrix": offers,
        "reddit_credential_id": "",
        "ai_credential_id": ""
    }

    cfg.setdefault("listeners", []).append(new_listener)
    save_config(cfg)

    if getattr(args, "json", False):
        print(json.dumps(new_listener, ensure_ascii=False, indent=2))
        return

    print(f"\n✅ 成功注册新营销/联盟项目: [{name}] (ID: {camp_id})")
    print(f"  • 目标网址: {url}")
    print(f"  • 监听版块: {', '.join(clean_subs)}")
    print(f"  • 触发词根: {', '.join(clean_kws)}")
    print(f"  • 智能生成转化工具/矩阵: {len(offers)} 个承接页")
    for o in offers:
        print(f"    - {o.get('name')} ({o.get('name_en') or ''}): {o.get('url')}")
    print(f"\n👉 现在你可以直接使用: `python3 redsignal_cli.py radar --campaign {camp_id}` 扫描专属线索。\n")


def cmd_affiliate(args):
    """Generate targeted Affiliate conversion playbook, comparison bridge comment, inbound hook, and DM closing funnel."""
    hit_id = str(args.hit_id).strip()
    with get_db() as db:
        row = db.execute("SELECT * FROM hits WHERE hit_id=? OR id=?", (hit_id, hit_id)).fetchone()
        if not row:
            if getattr(args, "json", False):
                print(json.dumps({"ok": False, "error": f"Hit {hit_id} not found"}, ensure_ascii=False))
            else:
                print(f"❌ 找不到线索: {hit_id}")
            sys.exit(1)
        hit = dict(row)

    cfg = load_config()
    lst = next((l for l in cfg.get("listeners", []) if l["id"] == hit.get("listener_id")), None)
    if not lst and cfg.get("listeners"):
        lst = cfg["listeners"][0]

    cred = resolve_ai_cred(cfg, lst.get("ai_credential_id") if lst else None)
    product_name = (getattr(args, "product", "") or "").strip() or (lst.get("site_name") if lst else "Recommended Product")
    affiliate_url = (getattr(args, "url", "") or "").strip() or (lst.get("site_url") if lst else "https://example.com/partner")
    competitor_name = (getattr(args, "competitor", "") or "").strip()
    discount_code = (getattr(args, "code", "") or "").strip()
    pitch_ins = lst.get("pitch_instruction", "") if lst else ""
    platform = hit.get("platform") or "reddit"
    author = hit.get("author") or "friend"
    title = hit.get("title") or ""
    excerpt = hit.get("excerpt") or ""

    from ai import generate_affiliate_playbook, detect_affiliate_intent
    intent_info = detect_affiliate_intent(title, excerpt)

    playbook = generate_affiliate_playbook(
        title=title,
        excerpt=excerpt,
        author=author,
        product_name=product_name,
        affiliate_url=affiliate_url,
        competitor_name=competitor_name,
        discount_code=discount_code,
        pitch_instruction=pitch_ins,
        platform=platform,
        credential=cred
    )

    import urllib.parse
    dm_subject = playbook.get("dm_funnel", {}).get("subject") or "Quick comparison breakdown regarding your post"
    dm_message = playbook.get("dm_funnel", {}).get("message") or ""

    if platform == "reddit":
        query_params = urllib.parse.urlencode({
            "to": author,
            "subject": dm_subject,
            "message": dm_message
        })
        compose_url = f"https://www.reddit.com/message/compose?{query_params}"
    elif platform in ("x", "twitter"):
        compose_url = f"https://twitter.com/messages/compose?text={urllib.parse.quote(dm_message)}"
    else:
        compose_url = ""

    out = {
        "hit_id": hit_id,
        "author": author,
        "platform": platform,
        "detected_intent": intent_info,
        "product_name": product_name,
        "affiliate_url": affiliate_url,
        "compose_url": compose_url,
        "playbook": playbook
    }

    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    dilemma = playbook.get("target_dilemma", {})
    pub = playbook.get("public_reply", {})
    funnel = playbook.get("dm_funnel", {})

    print(f"\n=======================================================================")
    print(f"💰 【RedSignal 联盟营销与高客单转化攻坚包】 - {hit_id}")
    print(f"👤 目标发帖人: @{author} ({platform.upper()}) [{intent_info.get('badge')}]")
    print(f"📌 帖子标题: {title}")
    print(f"🎯 推荐联盟品: {product_name} ({affiliate_url})")
    print(f"=======================================================================\n")

    print(f"【商机研判与截流切入点】")
    print(f"  • 意向类型: {intent_info.get('label')}")
    print(f"  • 核心困惑/痛点: {dilemma.get('frustration_point')}")
    print(f"  • 截流策略: {dilemma.get('strategy')}\n")

    print(f"【Track 1: 公开藤壶占坑回帖 (Public Barnacle Comment · 0外链高权重)】")
    print(f"  👉 贴在目标帖子下，提供客观对比解惑，末尾附带逆向私信钩子:")
    print(f"  💬 \"{pub.get('comment')}\"")
    print(f"  💡 逆向私信钩子: \"{pub.get('inbound_hook')}\"\n")

    print(f"【Track 2: 1v1 私信闭环攻坚 (Direct Message Close)】")
    print(f"  • 私信标题: {dm_subject}")
    print(f"  • 私信正文:\n    \"{dm_message}\"")
    if compose_url:
        print(f"\n  🚀 官方一键预填直达链接 (0封号风险):")
        print(f"    {compose_url}\n")

    print(f"【三轮心智攻坚心法 (3-Stage Affiliate Closing Playbook)】")
    for r in funnel.get("rounds", []):
        print(f"  ▶ [{r.get('title')}] - 目标: {r.get('goal')}")
        print(f"    话术: \"{r.get('draft')}\"\n")

    print(f"【高频异议与利益披露化解】")
    for obj in funnel.get("objections", []):
        print(f"  ❓ 客户顾虑: {obj.get('objection')}")
        print(f"  🛡️ 真诚化解: \"{obj.get('response')}\"")
    print()


def cmd_status(args):
    """Inspect unified long-term asset health, cron schedules, mirror connectivity, and campaign radar performance."""
    cfg = load_config()
    camp_filter = getattr(args, "campaign", "") or ""
    listeners = cfg.get("listeners", [])
    if camp_filter:
        listeners = [
            l for l in listeners
            if camp_filter.lower() in l.get("id", "").lower() or camp_filter.lower() in l.get("name", "").lower()
        ]

    # Check system crontab
    cron_jobs = []
    try:
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if "justmysocks" in line or "redsignal" in line:
                    cron_jobs.append(line.strip())
    except Exception:
        pass

    import socket
    def probe_domain(domain, port=443, timeout=2.0):
        t0 = time.time()
        try:
            s = socket.create_connection((domain, port), timeout=timeout)
            lat = round((time.time() - t0) * 1000, 1)
            s.close()
            return True, lat
        except Exception:
            return False, -1.0

    report = []
    with get_db() as db:
        for l in listeners:
            cid = l.get("id")
            cname = l.get("name") or l.get("site_name")
            target_url = l.get("site_url") or ""
            offers = l.get("offers_matrix") or []

            # Hits count for this campaign
            count_total = db.execute("SELECT COUNT(*) FROM hits WHERE listener_id=?", (cid,)).fetchone()[0]

            # Domain / Mirror probe
            domain_probe = None
            if target_url:
                import urllib.parse
                parsed = urllib.parse.urlparse(target_url)
                netloc = parsed.netloc or target_url.split("/")[0]
                if netloc:
                    ok, lat = probe_domain(netloc)
                    domain_probe = {"domain": netloc, "reachable": ok, "latency_ms": lat}

            # Check if there is an associated local repository or autopilot log
            local_repo_info = None
            if "justmysocks" in cid.lower() or "justmysocks" in cname.lower():
                local_dir = "/Users/han/justmysocks"
                if os.path.exists(local_dir):
                    log_file = os.path.join(local_dir, "autopilot.log")
                    last_log_line = ""
                    if os.path.exists(log_file):
                        try:
                            with open(log_file, "r", encoding="utf-8") as lf:
                                lines = [ln.strip() for ln in lf.readlines() if ln.strip()]
                                if lines:
                                    last_log_line = lines[-1]
                        except Exception:
                            pass

                    last_git = ""
                    try:
                        g_res = subprocess.run(
                            ["git", "-C", local_dir, "log", "-1", "--format=%cd (%cr) - %s"],
                            capture_output=True, text=True
                        )
                        if g_res.returncode == 0:
                            last_git = g_res.stdout.strip()
                    except Exception:
                        pass

                    local_repo_info = {
                        "path": local_dir,
                        "github_url": "https://github.com/justmysocks-guide/justmysocks",
                        "last_commit": last_git,
                        "last_autopilot_log": last_log_line,
                        "cron_active": len(cron_jobs) > 0,
                        "cron_jobs": cron_jobs
                    }

            report.append({
                "id": cid,
                "name": cname,
                "site_url": target_url,
                "keywords_count": len(l.get("keywords") or []),
                "offers_count": len(offers),
                "total_leads": count_total,
                "domain_probe": domain_probe,
                "local_repo": local_repo_info
            })

    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("\n=======================================================================")
    print("📊 【RedSignal 营销与资产长线中枢大盘 (Long-Term Assets Dashboard)】")
    print("=======================================================================\n")
    if not report:
        print("暂无运行中的营销项目或未匹配到指定 Campaign。")
        return

    for item in report:
        print(f"📦 项目名称: [{item['name']}] (ID: {item['id']})")
        print(f"   • 目标主链: {item['site_url']}")
        if item.get("domain_probe"):
            dp = item["domain_probe"]
            st_text = f"🟢 连通正常 ({dp['latency_ms']}ms)" if dp["reachable"] else "🔴 无法连通/超时"
            print(f"   • 域名/镜像探针: {dp['domain']} -> {st_text}")
        print(f"   • 核心词库数: {item['keywords_count']} 个词根 | 承接工具/页面数: {item['offers_count']} 个")
        print(f"   • 历史截流线索库: {item['total_leads']} 条商机")

        if item.get("local_repo"):
            lr = item["local_repo"]
            print(f"   • 🏛️ 关联代码仓库: {lr['github_url']}")
            print(f"     - 本地路径: {lr['path']}")
            if lr.get("last_commit"):
                print(f"     - 最近提交: {lr['last_commit']}")
            cron_st = "🟢 已挂载运行中" if lr.get("cron_active") else "⚪ 未配置"
            print(f"     - 系统底层定时器 (Crontab): {cron_st}")
            if lr.get("cron_jobs"):
                for cj in lr["cron_jobs"]:
                    print(f"       ⏱️  `{cj}`")
            if lr.get("last_autopilot_log"):
                print(f"     - 自动化巡检日志: {lr['last_autopilot_log']}")
        print()


def cmd_inbox(args):
    """Poll unread messages in Reddit / X inboxes, draft and auto-dispatch multi-round AI replies."""
    from dm_agent import poll_and_respond_all_inboxes
    dry_run = getattr(args, "dry_run", False)
    is_json = getattr(args, "json", False)
    platform = getattr(args, "platform", "all")
    if not is_json:
        print(f"[*] Checking inboxes (platform={platform}, dry_run={dry_run})...")
    res = poll_and_respond_all_inboxes(dry_run=dry_run, platform=platform, verbose=not is_json)
    if is_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    if not res:
        print(f"[+] Inbox check finished: 0 new messages to process on {platform.upper()}.")
    else:
        reddit_cnt = sum(1 for r in res if r.get("platform") == "reddit")
        x_cnt = sum(1 for r in res if r.get("platform") in ("x", "twitter"))
        print(f"[+] Processed {len(res)} inbound conversations (Reddit: {reddit_cnt}, X: {x_cnt}).")


def cmd_doctor(args):
    """Proactively inspect health of Reddit, X (Twitter), Bark, and AI credentials (inspired by twikit/openmagpie)."""
    from dm_agent import check_session_health
    is_json = getattr(args, "json", False)
    diags = check_session_health()
    if is_json:
        print(json.dumps(diags, ensure_ascii=False, indent=2))
        return

    print("\n🩺 【RedSignal 会话凭据与服务健康体检 (Session Keeper Doctor)】")
    print("=" * 76)
    for d in diags:
        st = d.get("status")
        icon = "🟢" if st == "healthy" else ("🟡" if st == "warning" else "🔴")
        plat = d.get("name")
        acc = d.get("account")
        det = d.get("details")
        print(f"{icon} {plat:<26} [{acc}] -> {st.upper()} ({det})")
    print("=" * 76)
    all_healthy = all(d.get("status") == "healthy" for d in diags)
    if all_healthy:
        print("✅ 所有核心通信会话、手机推送通道及 AI 大脑均处于健康可用状态！\n")
    else:
        print("⚠️ 检测到异常或过期凭据，请根据上述提示在 redsignal 中更新对应 Cookie 或 API Key。\n")


def cmd_audit(args):
    """Audit visibility, lock status, and SERP health of sent replies and barnacle targets."""
    from barnacle import audit_sent_replies, audit_barnacle_targets
    limit = getattr(args, "limit", 10)
    audit_type = getattr(args, "type", "replies")
    is_fast = getattr(args, "fast", False)
    is_json = getattr(args, "json", False)

    if audit_type in ("replies", "all"):
        replies = audit_sent_replies(limit=limit, skip_network=is_fast)
    else:
        replies = []

    if audit_type in ("targets", "all"):
        targets = audit_barnacle_targets(limit=limit, skip_network=is_fast)
    else:
        targets = []

    out = {
        "replies": replies,
        "targets": targets,
        "total_audited": len(replies) + len(targets)
    }

    if is_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print("\n🔍 【RedSignal 藤壶回帖存活与占坑健康巡检 (Barnacle Audit)】")
    print("=" * 78)

    if replies:
        print(f"📡 【公域已发回帖存活状态巡检 (Outbound Replies: {len(replies)} 条)】")
        for r in replies:
            st = r.get("status", "LIVE")
            icon = "🟢" if st == "LIVE" else ("🟡" if st == "LOCKED" else ("⚪" if st == "ARCHIVED" else "🔴"))
            print(f"{icon} [ID: {r['id']}] r/{r.get('subreddit') or 'social'} | 作者: {r.get('author') or 'N/A'}")
            print(f"   • 目标链接: {r.get('target_url')}")
            print(f"   • 存活状态: {st:<8} | 点赞数: {r.get('upvotes', 0)} | 互动评论: {r.get('comments_count', 0)}")
            print(f"   • 巡检诊断: {r.get('recommendation')}")
            print("-" * 78)

    if targets:
        print(f"\n🎯 【藤壶 SERP 核心搜索占坑帖巡检 (Barnacle Targets: {len(targets)} 条)】")
        for t in targets:
            st = t.get("status", "discovered")
            icon = "🟢" if not t.get("is_archived") else "⚪"
            print(f"{icon} [ID: {t['id']}] 关键词: \"{t.get('keyword')}\" (Google Rank: #{t.get('google_rank', '-')})")
            print(f"   • 目标链接: {t.get('target_url')}")
            print(f"   • 状态: {st} | 机会评分: {t.get('opportunity_score', 0)}")
            print(f"   • 建议: {t.get('recommendation')}")
            print("-" * 78)

    if not replies and not targets:
        print("暂无已发送回帖或藤壶目标数据。可使用 `redsignal_cli.py post` 或 `radar` 开展截流作业。")
    print()


def cmd_barnacle(args):
    """Hunt Google Page 1 discussion threads for high-intent keywords and craft evergreen replies."""
    from barnacle import hunt_and_auto_draft_barnacle
    keyword = (getattr(args, "keyword", "") or getattr(args, "keyword_pos", "") or "").strip()
    if not keyword:
        print("❌ 错误: 请指定目标商业/长尾搜索关键词 (--keyword 或直接在命令后传参)")
        sys.exit(1)

    limit = getattr(args, "limit", 8)
    auto_draft = getattr(args, "auto_draft", False)
    is_json = getattr(args, "json", False)

    print(f"\n🔍 【RedSignal 藤壶 SEO 猎金雷达】正在 Google 检索首页讨论帖: \"{keyword}\" ...")
    targets = hunt_and_auto_draft_barnacle(keyword, max_results=limit, auto_draft=auto_draft)

    if is_json:
        print(json.dumps(targets, ensure_ascii=False, indent=2))
        return

    print(f"🎯 共捕获 {len(targets)} 个排名前列的讨论坑位:\n" + "=" * 76)
    for idx, t in enumerate(targets, 1):
        st_icon = "🟢 活帖可回" if not t.get("is_archived") else "⚪ 已归档/锁帖"
        print(f"#{t.get('google_rank', idx)} [{st_icon}] {t.get('post_title')} (得分: {t.get('opportunity_score', 0)})")
        print(f"   🔗 原帖: {t.get('target_url')}")
        if t.get("author"):
            print(f"   👤 楼主: u/{t.get('author')}")
        if t.get("evergreen_draft"):
            print(f"   📝 常青解答草稿已生成:\n{t.get('evergreen_draft')[:180]}...")
        print("-" * 76)
    print("💡 建议: 优先挑选 Google Rank 靠前且状态为 🟢 的帖子进行专业回帖，借 Google 搜索流量长期被动引流。\n")


def main():
    parser = argparse.ArgumentParser(description="RedSignal Agentic CLI Tool")
    subparsers = parser.add_subparsers(dest="command")

    # radar (with alias leads)
    p_radar = subparsers.add_parser("radar", aliases=["leads"], help="Scan high opportunity leads & sync RSS")
    p_radar.add_argument("--limit", type=int, default=10, help="Number of leads to fetch")
    p_radar.add_argument("--platform", type=str, default="all", help="Platform filter (reddit/x/forum/all)")
    p_radar.add_argument("--sub", type=str, default="", help="Subreddit keyword filter")
    p_radar.add_argument("--keyword", type=str, default="", help="Keyword search in title/content")
    p_radar.add_argument("--campaign", type=str, default="", help="Filter leads by campaign / listener ID or name")
    p_radar.add_argument("--intent", choices=["affiliate", "alternative", "compare", "deal", "review", "troubleshoot"], default="", help="Filter by commercial intent archetype")
    p_radar.add_argument("--sync", action="store_true", help="Perform immediate authenticated RSS pull")
    p_radar.add_argument("--json", action="store_true", help="Output raw JSON format")

    # campaigns (with alias camps)
    p_camps = subparsers.add_parser("campaigns", aliases=["camps"], help="List all configured marketing & affiliate campaigns")
    p_camps.add_argument("--json", action="store_true", help="Output raw JSON format")

    # add-campaign
    p_add_camp = subparsers.add_parser("add-campaign", help="Quickly register a new affiliate product, SaaS, or marketing campaign")
    p_add_camp.add_argument("--name", required=True, help="Product or campaign brand name")
    p_add_camp.add_argument("--url", required=True, help="Target landing or affiliate partner link")
    p_add_camp.add_argument("--subreddits", default="SaaS,Entrepreneur,startups", help="Target subreddits (comma separated)")
    p_add_camp.add_argument("--keywords", default="alternative,vs,pricing,discount,switch", help="Trigger keyword roots (comma separated)")
    p_add_camp.add_argument("--desc", default="", help="Product description and core value prop")
    p_add_camp.add_argument("--pitch", default="", help="Pitch instruction for AI playbooks")
    p_add_camp.add_argument("--json", action="store_true", help="Output raw JSON format")

    # affiliate (with alias aff)
    p_aff = subparsers.add_parser("affiliate", aliases=["aff"], help="Generate targeted Affiliate conversion playbook, inbound hook & closing funnel")
    p_aff.add_argument("hit_id", help="Hit ID or integer row ID")
    p_aff.add_argument("--product", default="", help="Override affiliate product/brand name")
    p_aff.add_argument("--url", default="", help="Override affiliate/referral URL")
    p_aff.add_argument("--competitor", default="", help="Competitor being churned/compared")
    p_aff.add_argument("--code", default="", help="Optional exclusive discount code")
    p_aff.add_argument("--json", action="store_true", help="Output raw JSON format")

    # quota
    p_quota = subparsers.add_parser("quota", help="Inspect rate limits, cooldown countdown & quota")
    p_quota.add_argument("--json", action="store_true", help="Output raw JSON format")

    # post
    p_post = subparsers.add_parser("post", help="Verified dispatch to target community post")
    p_post.add_argument("hit_id", help="Target hit ID or integer row ID")
    p_post.add_argument("--text", required=True, help="Reply text content")
    p_post.add_argument("--mode", choices=["brand_search", "link", "direct"], default="brand_search", help="Anti-ban link mode")
    p_post.add_argument("--dry-run", action="store_true", help="Dry run verification without sending real network request")
    p_post.add_argument("--force", action="store_true", help="Bypass 45m cooldown countdown (still bounded by 8/day hard limit)")
    p_post.add_argument("--force-link", action="store_true", help="Force active link inclusion even if rolling link ratio exceeds 20%%")
    p_post.add_argument("--quote", action="store_true", help="Post as a Quote Tweet (引用推文) on X to maximize personal timeline reach")
    p_post.add_argument("--thread-text", type=str, default="", help="Optional 2nd tweet content for 2-Tweet Thread link drop")
    p_post.add_argument("--account", type=str, default="", help="Optional specific credential ID")
    p_post.add_argument("--json", action="store_true", help="Output raw JSON format")

    # barnacle / hunt (Google SERP Discussion Hunter)
    p_bar = subparsers.add_parser("barnacle", aliases=["hunt"], help="Hunt Google Page 1 discussion threads for target keyword")
    p_bar.add_argument("keyword_pos", nargs="?", default="", help="Target keyword or search query (positional)")
    p_bar.add_argument("-k", "--keyword", default="", help="Target keyword or search query")
    p_bar.add_argument("--limit", type=int, default=8, help="Max discussion threads to hunt (default: 8)")
    p_bar.add_argument("--auto-draft", action="store_true", help="Automatically generate evergreen authoritative AI reply for active threads")
    p_bar.add_argument("--json", action="store_true", help="Output raw JSON format")

    # tools
    p_tools = subparsers.add_parser("tools", help="List available high-converting landing tools")
    p_tools.add_argument("--json", action="store_true", help="Output raw JSON format")

    # dm / chat
    p_dm = subparsers.add_parser("dm", aliases=["chat"], help="Generate 1v1 private DM pitch & dual-track conversion funnel")
    p_dm.add_argument("hit_id", help="Hit ID or integer row ID")
    p_dm.add_argument("--json", action="store_true", help="Output raw JSON format")

    # playbook
    p_play = subparsers.add_parser("playbook", help="Generate 3-stage chat playbook for a lead")
    p_play.add_argument("hit_id", help="Hit ID or integer row ID")
    p_play.add_argument("--json", action="store_true", help="Output raw JSON format")

    # queue
    p_queue = subparsers.add_parser("queue", help="List recent reply queue items")
    p_queue.add_argument("--json", action="store_true", help="Output raw JSON format")

    # status (with alias st)
    p_status = subparsers.add_parser("status", aliases=["st"], help="Inspect unified long-term asset health, cron schedules & mirror probes")
    p_status.add_argument("--campaign", type=str, default="", help="Filter by specific campaign ID or name")
    p_status.add_argument("--json", action="store_true", help="Output raw JSON format")

    # inbox
    p_inbox = subparsers.add_parser("inbox", help="Poll unread Reddit / X DMs, generate multi-round AI closing replies & auto-dispatch")
    p_inbox.add_argument("--platform", choices=["all", "reddit", "x", "twitter"], default="all", help="Target platform to check (all/reddit/x)")
    p_inbox.add_argument("--dry-run", action="store_true", help="Draft replies and send Bark preview without posting to network")
    p_inbox.add_argument("--json", action="store_true", help="Output raw JSON format")

    # doctor / check (inspired by twikit session keeper)
    p_doc = subparsers.add_parser("doctor", aliases=["check"], help="Check live health and authentication of Reddit, X, Bark, and AI sessions")
    p_doc.add_argument("--json", action="store_true", help="Output raw JSON format")

    # audit (Barnacle SEO & Sent Reply Health Tracker)
    p_audit = subparsers.add_parser("audit", help="Audit visibility, lock status, and SERP health of sent replies and barnacle targets")
    p_audit.add_argument("--limit", type=int, default=10, help="Number of records to inspect (default: 10)")
    p_audit.add_argument("--type", choices=["replies", "targets", "all"], default="replies", help="Audit sent replies or barnacle SERP targets (default: replies)")
    p_audit.add_argument("--fast", action="store_true", help="Fast audit without outbound network inspection")
    p_audit.add_argument("--json", action="store_true", help="Output raw JSON format")

    args = parser.parse_args()
    if args.command in ("radar", "leads"):
        cmd_radar(args)
    elif args.command in ("doctor", "check"):
        cmd_doctor(args)
    elif args.command in ("barnacle", "hunt"):
        cmd_barnacle(args)
    elif args.command == "audit":
        cmd_audit(args)
    elif args.command in ("status", "st"):
        cmd_status(args)
    elif args.command == "inbox":
        cmd_inbox(args)
    elif args.command in ("campaigns", "camps"):
        cmd_campaigns(args)
    elif args.command == "add-campaign":
        cmd_add_campaign(args)
    elif args.command in ("affiliate", "aff"):
        cmd_affiliate(args)
    elif args.command == "quota":
        cmd_quota(args)
    elif args.command == "post":
        cmd_post(args)
    elif args.command == "tools":
        cmd_tools(args)
    elif args.command in ("dm", "chat"):
        cmd_dm(args)
    elif args.command == "playbook":
        cmd_playbook(args)
    elif args.command == "queue":
        cmd_queue(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
