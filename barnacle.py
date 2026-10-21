"""
Barnacle SEO (藤壶 SEO) Engine for RedSignal.
Detects Google Page 1 / Top SERP discussion threads (Reddit, Quora, Forums),
inspects their archival/reply status, and crafts definitive evergreen solutions
to capture high-intent organic search traffic.
"""

import re
import time
import json
import html as _html
import urllib.request
import urllib.parse

from db import get_db, db_log


def get_reddit_cookie() -> str:
    """Retrieve active Reddit session cookie from credentials store if available."""
    try:
        with get_db() as db:
            row = db.execute("SELECT data FROM credentials WHERE type='reddit' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                d = json.loads(row["data"] if isinstance(row, dict) else row[0])
                return d.get("cookie") or d.get("reddit_session") or ""
    except Exception:
        pass
    return ""


def clean_reddit_url(url: str) -> str:
    """Normalize Reddit URL to canonical https://www.reddit.com/r/{sub}/comments/{id}/{slug}/ format."""
    if not url:
        return ""
    # Standard format: reddit.com/r/.../comments/...
    m = re.search(r"(?:https?://)?(?:www\.|old\.|np\.)?reddit\.com(/r/[^/]+/comments/[a-z0-9]+(?:/[^/?#&]+)?)", url, re.I)
    if m:
        return f"https://www.reddit.com{m.group(1)}"
    # Short link format: redd.it/<id>
    m_short = re.search(r"(?:https?://)?redd\.it/([a-z0-9]+)", url, re.I)
    if m_short:
        return f"https://www.reddit.com/comments/{m_short.group(1)}"
    # Comments without subreddit: reddit.com/comments/<id>
    m_comm = re.search(r"(?:https?://)?(?:www\.|old\.)?reddit\.com/comments/([a-z0-9]+)", url, re.I)
    if m_comm:
        return f"https://www.reddit.com/comments/{m_comm.group(1)}"
    return url.split("?")[0].split("#")[0]


def inspect_target_health(url: str) -> dict:
    """
    Check if a target discussion post is active, locked, or archived (> 180 days).
    Uses Reddit session authentication if available, with resilient oEmbed fallback.
    Returns telemetry: is_archived, author, title, upvotes, comments_count, post_created_at.
    """
    canon_url = clean_reddit_url(url)
    res = {
        "canonical_url": canon_url,
        "is_archived": False,
        "is_locked": False,
        "is_removed": False,
        "status_label": "UNKNOWN",
        "author": "",
        "title": "",
        "upvotes": 0,
        "comments_count": 0,
        "post_created_at": 0.0,
        "platform": "reddit" if "reddit.com" in canon_url or "redd.it" in canon_url else ("quora" if "quora.com" in canon_url else "forum"),
        "error": None
    }

    if res["platform"] == "reddit":
        # Extract base36 post ID
        m_id = re.search(r"/comments/([a-z0-9]+)", canon_url, re.I)
        post_id = m_id.group(1) if m_id else ""
        cookie = get_reddit_cookie()
        fetched_successfully = False

        # 1. Primary inspection: /by_id/t3_{id}.json (with cookie if available)
        if post_id:
            by_id_url = f"https://www.reddit.com/by_id/t3_{post_id}.json"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "application/json"
            }
            if cookie:
                headers["Cookie"] = f"reddit_session={cookie}"

            req = urllib.request.Request(by_id_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        children = data.get("data", {}).get("children", [])
                    elif isinstance(data, list) and len(data) > 0:
                        children = data[0].get("data", {}).get("children", [])
                    else:
                        children = []

                    if children:
                        p_data = children[0].get("data", {})
                        res["title"] = p_data.get("title", "")
                        res["author"] = p_data.get("author", "")
                        res["upvotes"] = int(p_data.get("score") or 0)
                        res["comments_count"] = int(p_data.get("num_comments") or 0)
                        res["post_created_at"] = float(p_data.get("created_utc") or 0)

                        archived = bool(p_data.get("archived", False))
                        locked = bool(p_data.get("locked", False))
                        removed = bool(p_data.get("removed_by_category")) or p_data.get("selftext") == "[removed]" or p_data.get("author") in ("[deleted]", "[removed]")
                        age_days = (time.time() - res["post_created_at"]) / 86400.0 if res["post_created_at"] > 0 else 0
                        if archived or locked or age_days > 180:
                            res["is_archived"] = True
                        res["is_locked"] = locked
                        res["is_removed"] = removed

                        if removed:
                            res["status_label"] = "REMOVED"
                        elif locked:
                            res["status_label"] = "LOCKED"
                        elif res["is_archived"]:
                            res["status_label"] = "ARCHIVED"
                        else:
                            res["status_label"] = "LIVE"
                        fetched_successfully = True
            except Exception as e:
                res["error"] = f"by_id error: {e}"

        # 2. Resilient Fallback: Reddit oEmbed (requires no login/cookies)
        if not fetched_successfully:
            try:
                oembed_url = f"https://www.reddit.com/oembed?url={urllib.parse.quote(canon_url)}"
                req = urllib.request.Request(
                    oembed_url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    if resp.status == 200:
                        o_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        if not res["title"]:
                            res["title"] = o_data.get("title", "")
                        if not res["author"]:
                            res["author"] = o_data.get("author_name", "")
                        res["error"] = None
            except Exception as e:
                if not res["error"]:
                    res["error"] = f"oembed error: {e}"

    elif res["platform"] == "forum":
        try:
            req = urllib.request.Request(
                canon_url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status == 200:
                    html = resp.read().decode("utf-8", errors="ignore")
                    m_title = re.search(r"<title>(.*?)</title>", html, re.I)
                    if m_title:
                        res["title"] = _html.unescape(m_title.group(1)).strip()
        except Exception as e:
            res["error"] = f"forum fetch error: {e}"

    return res


def clean_forum_url(url: str) -> str:
    """Normalize forum URLs, keeping necessary query params like ?t=..., ?p=... while stripping tracking."""
    if not url:
        return ""
    url = urllib.parse.unquote(_html.unescape(url)).strip()
    u = urllib.parse.urlparse(url)
    if not u.query:
        return url.split("#")[0].rstrip("/")
    qs = urllib.parse.parse_qs(u.query)
    keep_keys = {"t", "p", "f", "id", "threadid", "page"}
    filtered_qs = {k: v for k, v in qs.items() if k.lower() in keep_keys}
    new_query = urllib.parse.urlencode(filtered_qs, doseq=True) if filtered_qs else ""
    return urllib.parse.urlunparse(u._replace(query=new_query, fragment="")).rstrip("/")


def scrape_serp_playwright(query: str, max_results: int = 10) -> list[dict]:
    """
    Local browser-automated SERP discussion scraper using Playwright/Chromium (Option B).
    Launches headless Chrome with real browser headers and extracts genuine Page 1 SERP rankings.
    """
    url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}&n={max_results * 2}&ei=UTF-8"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-US"
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=12000)
            page.wait_for_timeout(1000)
            raw_items = page.eval_on_selector_all("div.algo, li div.algo", """elements => {
                return elements.map(el => {
                    const a = el.querySelector('h3 a') || el.querySelector('a');
                    const h3 = el.querySelector('h3');
                    const snip = el.querySelector('.compText') || el.querySelector('p');
                    return {
                        href: a ? a.href : '',
                        title: h3 ? h3.innerText.trim() : (a ? a.innerText.trim() : ''),
                        snippet: snip ? snip.innerText.trim() : ''
                    };
                });
            }""")
            browser.close()

            results = []
            seen = set()
            rank = 1
            for it in raw_items:
                raw_href = it.get("href", "")
                if "/RU=" in raw_href:
                    m_ru = re.search(r"/RU=([^/]+)/", raw_href)
                    if m_ru:
                        raw_href = urllib.parse.unquote(m_ru.group(1))

                is_reddit = "reddit.com/r/" in raw_href and "/comments/" in raw_href
                is_forum = any(d in raw_href for d in ("buggiesgonewild.com", "cartaholics.com", "golfcartforum.com"))
                if not (is_reddit or is_forum):
                    continue

                clean_url = clean_reddit_url(raw_href) if is_reddit else clean_forum_url(raw_href)
                if not clean_url or clean_url in seen:
                    continue
                seen.add(clean_url)

                title = it.get("title", "")
                title = re.sub(r"^(?:Reddit|Buggies Gone Wild)https?://\S+\s*", "", title, flags=re.I).strip()
                if not title or len(title) < 5 or title.startswith("http"):
                    title = clean_url.split("/")[-1].replace("_", " ").replace("-", " ").title()

                results.append({
                    "rank": rank,
                    "title": title,
                    "url": clean_url,
                    "snippet": it.get("snippet", "")[:280] or f"Organic SERP Top Discussion (Rank #{rank})",
                    "platform": "reddit" if is_reddit else "forum"
                })
                rank += 1
                if len(results) >= max_results:
                    break
            return results
    except Exception as e:
        db_log("warn", "barnacle", f"Playwright browser SERP scrape notice: {e}")
        return []


def scrape_serp_fast(query: str, max_results: int = 10) -> list[dict]:
    """
    Fast Chrome-fingerprinted HTTP SERP scraper using curl_cffi.
    Mimics Chrome TLS handshakes for sub-second Page 1 extraction without browser startup overhead.
    """
    url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}&n={max_results * 2}&ei=UTF-8"
    try:
        from curl_cffi import requests as cffi_requests
        r = cffi_requests.get(url, impersonate="chrome124", timeout=8)
        if r.status_code != 200:
            return []
        page_html = r.text
    except Exception:
        return []

    results = []
    seen = set()
    rank = 1

    blocks = re.findall(r'<div\s+class="[^"]*algo[^"]*"[^>]*>(.*?)</li>', page_html, re.I | re.S)
    for b in blocks:
        m_url = re.search(r'href="[^"]*/RU=([^/]+)/', b)
        if not m_url:
            continue
        raw_target = urllib.parse.unquote(m_url.group(1))

        is_reddit = "reddit.com/r/" in raw_target and "/comments/" in raw_target
        is_forum = any(d in raw_target for d in ("buggiesgonewild.com", "cartaholics.com", "golfcartforum.com"))
        if not (is_reddit or is_forum):
            continue

        clean_url = clean_reddit_url(raw_target) if is_reddit else clean_forum_url(raw_target)
        if not clean_url or clean_url in seen:
            continue
        seen.add(clean_url)

        m_title = re.search(r'<h3[^>]*>(.*?)</h3>', b, re.I | re.S)
        raw_title = m_title.group(1) if m_title else ""
        clean_title = _html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        clean_title = re.sub(r"^(?:Reddit|Buggies Gone Wild)https?://\S+\s*", "", clean_title, flags=re.I).strip()
        if not clean_title or len(clean_title) < 5 or clean_title.startswith("http"):
            clean_title = clean_url.split("/")[-1].replace("_", " ").replace("-", " ").title()

        m_snip = re.search(r'<div\s+class="[^"]*compText[^"]*"[^>]*>(.*?)</div>', b, re.I | re.S)
        clean_snip = _html.unescape(re.sub(r"<[^>]+>", "", m_snip.group(1))).strip() if m_snip else f"Organic SERP Top Discussion (Rank #{rank})"

        results.append({
            "rank": rank,
            "title": clean_title,
            "url": clean_url,
            "snippet": clean_snip[:280],
            "platform": "reddit" if is_reddit else "forum",
        })
        rank += 1
        if len(results) >= max_results:
            break

    return results


def search_google_serp(keyword: str, max_results: int = 10) -> list[dict]:
    """
    Active Google/Organic SERP Discussion Hunter (Option B Engine).
    Surfaces the authentic discussion threads (Reddit & authority forums) that rank on Page 1.
    1. First attempts direct Google Search via standard request (and honors unit test mocks).
    2. If Google issues an automated traffic challenge (IP-level datacenter block),
       seamlessly queries the Organic SERP index (Yahoo/Bing Page 1 discussion index)
       via fast TLS fingerprinting or Playwright Chromium to guarantee authentic Page 1 discussion ranking.
    """
    clean_kw = re.sub(r"\bsite:(?:reddit\.com|buggiesgonewild\.com)\b", "", keyword, flags=re.I).strip()
    clean_kw = re.sub(r"\s+", " ", clean_kw).strip()
    if not clean_kw:
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    # 1. Try Google Search directly (honors proxies and unit test urlopen mocks)
    try:
        encoded_q = urllib.parse.quote(f"{clean_kw} site:reddit.com")
        g_url = f"https://www.google.com/search?q={encoded_q}&num={max_results * 2}&hl=en&gl=us"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        req = urllib.request.Request(g_url, headers=headers)
        with urllib.request.urlopen(req, timeout=7) as resp:
            if resp.status == 200:
                html_text = resp.read().decode("utf-8", errors="ignore")
                if not any(blk in html_text for blk in ("unusual traffic", "/sorry/", "enablejs", "recaptcha")):
                    matches = re.finditer(r'<a[^>]+href="([^">]+)"[^>]*>(.*?)</a>', html_text, re.I | re.S)
                    rank = 1
                    for m in matches:
                        raw_href = m.group(1)
                        inner_html = m.group(2) or ""
                        if "/url?q=" in raw_href:
                            m_url = re.search(r'/url\?q=([^&]+)', raw_href)
                            if m_url:
                                raw_href = urllib.parse.unquote(m_url.group(1))

                        if "reddit.com/r/" in raw_href and "/comments/" in raw_href:
                            canon_url = clean_reddit_url(raw_href)
                            if not canon_url or canon_url in seen_urls:
                                continue
                            seen_urls.add(canon_url)

                            m_h3 = re.search(r'<h3[^>]*>(.*?)</h3>', inner_html, re.I | re.S)
                            raw_title = m_h3.group(1) if m_h3 else inner_html
                            clean_title = _html.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip() or f"Discussion: {clean_kw}"

                            results.append({
                                "keyword": clean_kw,
                                "target_url": canon_url,
                                "platform": "reddit",
                                "post_title": clean_title,
                                "google_rank": rank,
                                "search_snippet": f"Google Page 1 Top Discussion (Rank #{rank})",
                                "author": "",
                                "post_created_at": 0.0,
                                "is_archived": 0,
                            })
                            rank += 1
                            if len(results) >= max_results:
                                break
                    if results:
                        return results
    except Exception:
        pass

    # 2. Organic SERP Hunter (Fast TLS -> Playwright Chromium fallback)
    serp_query = f"{clean_kw} (site:reddit.com OR site:buggiesgonewild.com)"
    serp_items = scrape_serp_fast(serp_query, max_results=max_results)
    if not serp_items:
        serp_items = scrape_serp_playwright(serp_query, max_results=max_results)

    for item in serp_items:
        canon_url = clean_reddit_url(item["url"]) if item["platform"] == "reddit" else item["url"]
        if not canon_url or canon_url in seen_urls:
            continue
        seen_urls.add(canon_url)
        results.append({
            "keyword": clean_kw,
            "target_url": canon_url,
            "platform": item["platform"],
            "post_title": item["title"],
            "google_rank": item["rank"],
            "search_snippet": item["snippet"] or f"Organic SERP Page 1 Top Discussion (Rank #{item['rank']})",
            "author": "",
            "post_created_at": 0.0,
            "is_archived": 0,
        })
        if len(results) >= max_results:
            break

    return results


def search_serp_targets(keyword: str, max_results: int = 15) -> list[dict]:
    """
    Search SERP engines and high-authority discussion networks to discover Reddit and Forum
    discussion threads that hold high organic authority and ranking for the given keyword.
    """
    clean_kw = keyword.strip()
    if not clean_kw:
        return []

    targets: list[dict] = []
    seen_urls: set[str] = set()
    cookie = get_reddit_cookie()

    # 1. Active Google/Organic SERP discovery first (Guaranteed authentic Page 1 rankings)
    serp_hits = search_google_serp(clean_kw, max_results=max_results)
    for sh in serp_hits:
        targets.append(sh)
        seen_urls.add(sh["target_url"])
        if len(targets) >= max_results:
            break

    # 2. Native Reddit Relevance Search with active session (Supplementary if SERP yields fewer items)
    if len(targets) < max_results:
        search_queries = [
            f'"{clean_kw}"',
            clean_kw
        ]

        for sq in search_queries:
            if len(targets) >= max_results:
                break
            try:
                r_url = f"https://www.reddit.com/search.json?q={urllib.parse.quote(sq)}&sort=relevance&limit={max_results}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
                if cookie:
                    headers["Cookie"] = f"reddit_session={cookie}"

                req = urllib.request.Request(r_url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                        children = data.get("data", {}).get("children", [])
                        for child in children:
                            d = child.get("data", {})
                            permalink = d.get("permalink", "")
                            if not permalink:
                                continue
                            canon_url = f"https://www.reddit.com{permalink}".split("?")[0].rstrip("/")
                            canon_url = clean_reddit_url(canon_url)
                            if canon_url in seen_urls:
                                continue
                            seen_urls.add(canon_url)

                            created_utc = float(d.get("created_utc") or 0)
                            archived = bool(d.get("archived", False))
                            locked = bool(d.get("locked", False))
                            age_days = (time.time() - created_utc) / 86400.0 if created_utc > 0 else 0
                            is_archived = 1 if (archived or locked or age_days > 180) else 0

                            targets.append({
                                "keyword": clean_kw,
                                "target_url": canon_url,
                                "platform": "reddit",
                                "post_title": d.get("title") or f"Discussion: {clean_kw}",
                                "google_rank": 0,  # 0 indicates internal search fallback, NOT SERP Page 1!
                                "search_snippet": d.get("selftext", "")[:280] or f"Subreddit: r/{d.get('subreddit')} (Reddit Internal Search)",
                                "author": d.get("author", ""),
                                "post_created_at": created_utc,
                                "is_archived": is_archived,
                                "upvotes": int(d.get("score") or 0),
                                "comments_count": int(d.get("num_comments") or 0)
                            })
                            if len(targets) >= max_results:
                                break
            except Exception as e:
                db_log("warn", "barnacle", f"Reddit relevance search error for '{sq}': {e}")

    # 3. Persist and calculate opportunity scores
    persisted: list[dict] = []
    with get_db() as db:
        now = time.time()
        for t in targets:
            # If metadata was missing (e.g. from SERP search), run health inspection
            if not t.get("author") or t.get("post_created_at", 0) == 0:
                health = inspect_target_health(t["target_url"])
                if health.get("title") and not t.get("post_title"):
                    t["post_title"] = health["title"]
                if health.get("author"):
                    t["author"] = health["author"]
                if health.get("post_created_at"):
                    t["post_created_at"] = health["post_created_at"]
                t["is_archived"] = 1 if health.get("is_archived") else t.get("is_archived", 0)

            rank = t.get("google_rank", 0)
            if rank and rank > 0:
                score = max(50, 100 - (rank - 1) * 5)
            else:
                score = 45  # Baseline score for non-SERP discussion
            if t.get("is_archived"):
                score = max(20, score - 30)
            t["opportunity_score"] = score

            db.execute(
                """INSERT INTO barnacle_targets
                   (keyword, target_url, platform, post_title, google_rank, search_snippet,
                    author, post_created_at, is_archived, opportunity_score, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(target_url) DO UPDATE SET
                       google_rank=excluded.google_rank,
                       post_title=COALESCE(NULLIF(excluded.post_title, ''), post_title),
                       is_archived=excluded.is_archived,
                       opportunity_score=excluded.opportunity_score,
                       updated_at=excluded.updated_at""",
                (
                    t["keyword"], t["target_url"], t["platform"], t["post_title"],
                    t["google_rank"], t.get("search_snippet", ""), t.get("author", ""),
                    t.get("post_created_at", 0), t["is_archived"], t["opportunity_score"], now
                )
            )
            row = db.execute("SELECT id FROM barnacle_targets WHERE target_url=?", (t["target_url"],)).fetchone()
            if row:
                t["id"] = row["id"]
            persisted.append(t)

    return persisted


def generate_evergreen_barnacle_reply(
    target_id: int,
    site_name: str = "Fairway Fort",
    site_url: str = "",
    site_desc: str = "",
    custom_instruction: str = ""
) -> str:
    """
    Generate an authoritative, evergreen, comprehensive reply specifically crafted
    for a high-ranking Google discussion thread to siphon long-term search traffic.
    """
    with get_db() as db:
        row = db.execute("SELECT * FROM barnacle_targets WHERE id=?", (target_id,)).fetchone()
        if not row:
            raise ValueError(f"Barnacle target {target_id} not found")
        target = dict(row)

    from ai import run_ai_prompt, resolve_ai_cred
    from config import load_config
    cfg = load_config()
    cred = resolve_ai_cred(cfg, None)
    if not cred:
        raise ValueError("No AI credential configured in settings/vault")

    prompt = f"""You are a master domain authority and veteran industry specialist crafting a definitive, permanent, evergreen reply for a discussion post that RANKS ON GOOGLE PAGE 1 for the keyword: "{target['keyword']}".

CONTEXT OF THIS THREAD:
- Thread Title: {target.get('post_title')}
- Target Platform: {target.get('platform', 'reddit').upper()}
- URL: {target.get('target_url')}
- Search Query Intent: {target.get('search_snippet')}

YOUR MISSION (BARNACLE SEO PERMANENCE):
Thousands of people search Google for "{target['keyword']}" every month and land directly on this exact thread.
Your comment must be so comprehensive, structured, objective, and authoritative that readers consider it the DEFINITIVE ANSWER on the entire page.

WRITING MANDATES:
1. PURE VALUE & STRUCTURE:
   - Use clear markdown headers or bullet points.
   - Address the root problem, common misconceptions, and exact measurements / specifications.
   - Contrast cheap band-aid solutions with professional, durable fixes.
2. OBJECTIVE PRODUCT / TOOL INTEGRATION:
   - Seamlessly mention {site_name} ({site_desc}) as a free reference, calculator, or specialized solution.
   - Target Link: {site_url or 'https://fairwayfort.com/pages/tools'}
   - If direct link is appropriate, weave it as an informational resource (e.g. "[{site_name} Roof Calculator]({site_url})").
3. HIGH-CONVERTING OPEN LOOP & PERMISSION HOOK:
   - Conclude by stating you put together a comprehensive checklist/calculator/fitment guide for anyone landing here from Google:
   - "If anyone is reading this down the road and needs the full fitment table/schematic, shoot me a DM or check the tool."
4. TONE:
   - Authoritative, warm, peer-to-peer veteran expert. Zero corporate fluff, no generic opening ("Great question!").
   - Max 3-4 structured, punchy paragraphs.

Special Instructions: {custom_instruction or 'Focus on long-term value, durability, and practical troubleshooting.'}

Write ONLY the ready-to-post markdown response:"""

    reply_text = run_ai_prompt(prompt, cred, max_tokens=650)

    # Save generated draft back to target record
    with get_db() as db:
        db.execute(
            "UPDATE barnacle_targets SET evergreen_draft=?, status='drafted', updated_at=? WHERE id=?",
            (reply_text, time.time(), target_id)
        )

    return reply_text


def audit_sent_replies(limit: int = 15, skip_network: bool = False) -> list[dict]:
    """
    Audit recent outbound replies from reply_queue to verify:
    1. Is the discussion post still alive, locked, archived, or removed by AutoMod?
    2. Real-time upvotes, comment engagement, and survival health.
    3. Update visibility_status in reply_queue.
    """
    results: list[dict] = []
    with get_db() as db:
        rows = db.execute(
            """SELECT id, hit_id, listener_name, subreddit, target_url, comment_url,
                      author, reply_text, status, visibility_status, upvotes,
                      replies_count, submitted_at, created_at
               FROM reply_queue
               ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()

    for r in rows:
        row_id = r["id"] if isinstance(r, dict) else r[0]
        listener_name = r["listener_name"] if isinstance(r, dict) else r[2]
        subreddit = r["subreddit"] if isinstance(r, dict) else r[3]
        target_url = r["target_url"] if isinstance(r, dict) else r[4]
        author = r["author"] if isinstance(r, dict) else r[6]
        raw_text = r["reply_text"] if isinstance(r, dict) else r[7]
        text_snippet = (raw_text[:70] + "...") if raw_text else ""
        vis_st = r["visibility_status"] if isinstance(r, dict) else r[9]
        upvotes = r["upvotes"] if isinstance(r, dict) else r[10]

        canon_url = clean_reddit_url(target_url or "")
        audit_item = {
            "id": row_id,
            "campaign": listener_name or "default",
            "subreddit": subreddit or "",
            "author": author or "",
            "target_url": canon_url or target_url or "",
            "snippet": text_snippet,
            "stored_visibility": vis_st or "unverified",
            "status": "LIVE",
            "is_archived": False,
            "is_locked": False,
            "is_removed": False,
            "upvotes": upvotes or 0,
            "comments_count": 0,
            "recommendation": "🟢 存活良好 (借船出海持续获客)"
        }

        if not skip_network and canon_url and "reddit.com" in canon_url:
            health = inspect_target_health(canon_url)
            audit_item["upvotes"] = health.get("upvotes", audit_item["upvotes"])
            audit_item["comments_count"] = health.get("comments_count", 0)
            audit_item["is_archived"] = health.get("is_archived", False)
            audit_item["is_locked"] = health.get("is_locked", False)
            audit_item["is_removed"] = health.get("is_removed", False)
            status_label = health.get("status_label") or ("ARCHIVED" if audit_item["is_archived"] else "LIVE")
            audit_item["status"] = status_label

            if status_label == "REMOVED":
                audit_item["recommendation"] = "🔴 帖子已被删/折叠 (停止跟进，建议从雷达剔除)"
                new_vis = "removed"
            elif status_label == "LOCKED":
                audit_item["recommendation"] = "🟡 帖子被版主锁定 (禁止新评论，历史内容仍保留搜索权重)"
                new_vis = "locked"
            elif status_label == "ARCHIVED":
                audit_item["recommendation"] = "⚪ 已归档超180天 (只读展示，持续吃Google长尾搜索)"
                new_vis = "archived"
            else:
                audit_item["recommendation"] = "🟢 存活良好 (公域权威建立中，建议跟进二次互动)"
                new_vis = "visible"

            try:
                with get_db() as db:
                    db.execute(
                        "UPDATE reply_queue SET visibility_status=?, upvotes=?, updated_at=? WHERE id=?",
                        (new_vis, audit_item["upvotes"], time.time(), row_id)
                    )
            except Exception:
                pass

        results.append(audit_item)
    return results


def audit_barnacle_targets(limit: int = 15, skip_network: bool = False) -> list[dict]:
    """Audit SERP keyword targets to check rank, health, and freshness."""
    results: list[dict] = []
    with get_db() as db:
        rows = db.execute(
            """SELECT id, keyword, target_url, platform, post_title, google_rank,
                      is_archived, opportunity_score, status, updated_at
               FROM barnacle_targets
               ORDER BY id DESC LIMIT ?""",
            (limit,)
        ).fetchall()

    for r in rows:
        target_url = r["target_url"] if isinstance(r, dict) else r[2]
        is_archived = bool(r["is_archived"] if isinstance(r, dict) else r[6])
        item = {
            "id": r["id"] if isinstance(r, dict) else r[0],
            "keyword": r["keyword"] if isinstance(r, dict) else r[1],
            "target_url": target_url,
            "google_rank": r["google_rank"] if isinstance(r, dict) else r[5],
            "status": r["status"] if isinstance(r, dict) else r[8],
            "opportunity_score": r["opportunity_score"] if isinstance(r, dict) else r[7],
            "is_archived": is_archived,
            "recommendation": "🎯 SERP 前列优质金矿帖，优先回帖建坑"
        }
        if not skip_network and target_url and "reddit.com" in target_url:
            health = inspect_target_health(target_url)
            if health.get("is_archived"):
                item["is_archived"] = True
                item["recommendation"] = "⚪ 目标帖已归档，无法回帖"
        results.append(item)
    return results


def hunt_and_auto_draft_barnacle(
    keyword: str,
    max_results: int = 5,
    auto_draft: bool = False,
    site_name: str = "",
    site_url: str = ""
) -> list[dict]:
    """
    End-to-end Active Google SERP Barnacle Hunter (Inspired by backlinkflow).
    1. Direct SERP discovery targeting Google Page 1 discussions
    2. Real-time post health and lock status inspection
    3. Persist targets with opportunity score
    4. Optional automatic evergreen authoritative reply generation
    """
    targets = search_serp_targets(keyword, max_results=max_results)
    if not auto_draft:
        return targets

    for t in targets:
        tid = t.get("id")
        if tid and not t.get("is_archived") and not t.get("evergreen_draft"):
            try:
                draft = generate_evergreen_barnacle_reply(
                    target_id=tid,
                    site_name=site_name or "Official Guide",
                    site_url=site_url or ""
                )
                t["evergreen_draft"] = draft
                t["status"] = "drafted"
            except Exception as e:
                db_log("warn", "barnacle", f"Auto-draft notice for target {tid}: {e}")

    return targets

