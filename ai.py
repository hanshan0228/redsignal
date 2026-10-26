from __future__ import annotations

import json
import os
import re


def run_ai_prompt(prompt: str, credential: dict, max_tokens: int = 300) -> str:
    ctype = credential.get("type", "anthropic")

    # Fast-path for unit tests with mock credentials
    if str(credential.get("api_key", "")).startswith("mock") or os.getenv("REDSIGNAL_MOCK_AI") == "1":
        if "BBCode" in prompt or "forum" in prompt.lower():
            return "Have you checked the solenoid resistor and diode orientation? Here is the reference diagram:\n[URL=\"https://fairwayfort.com\"]FairwayFort Wiring Guide[/URL]"
        elif "profile bio" in prompt.lower() or "stealth" in prompt.lower():
            return "Check the main wiring harness and verify battery pack voltage across all 6 cells under load. I saved the complete wiring matrix in my profile bio for easy reference."
        return "Step 1: Check your primary circuit voltage. Verify all terminal connections are torqued properly. You can search online for the complete model spec table."

    timeout_sec = float(credential.get("timeout") or 35.0)

    if ctype in ("anthropic", "claude"):
        import anthropic  # type: ignore
        model  = credential.get("model") or "claude-haiku-4-5-20251001"
        client = anthropic.Anthropic(api_key=credential["api_key"], timeout=timeout_sec)
        msg    = client.messages.create(model=model, max_tokens=max_tokens,
                                        messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text.strip()

    if ctype in ("openai", "ollama"):
        from openai import OpenAI  # type: ignore
        if ctype == "ollama":
            base   = (credential.get("base_url") or "http://localhost:11434").rstrip("/")
            client = OpenAI(api_key="ollama", base_url=f"{base}/v1/", timeout=timeout_sec)
            model  = credential.get("model") or "llama3.2"
        else:
            base   = credential.get("base_url") or os.getenv("OPENAI_BASE_URL") or "http://localhost:8317/v1"
            client = OpenAI(api_key=credential["api_key"], base_url=base, timeout=timeout_sec)
            model  = credential.get("model") or "gemini-3.8-flash-high"
        resp = client.chat.completions.create(model=model, max_tokens=max_tokens,
                                              messages=[{"role": "user", "content": prompt}])
        return resp.choices[0].message.content.strip()

    raise ValueError(f"Unknown credential type: {ctype}")


def classify_funnel_tier(
    title: str,
    text: str,
    custom_keywords: list[str] | None = None
) -> tuple[int, str]:
    """Classify lead intent into Promotion Warrior's 3-Tier funnel using domain-adaptive heuristics."""
    content = f"{title} {text}".lower()
    # Tier 1: Direct / Hot Intent (Solution Seeking, Purchase Intent, Lookup/Calculator queries)
    t1_patterns = [
        r"\b(where to buy|where can i (?:buy|get|find)|which should i buy|recommendations?|recommend a|best brand|looking for a|need a tool|how to buy|price check|coupon|discount|deal|quote|cost of|purchase|order|calculator|decoder|lookup|selector|fitment guide|spec sheet|checklist)\b",
        r"\b(ready to buy|who makes the best|top rated|what do you recommend|which tool do you recommend|any good alternatives to buy)\b",
        r"\b(agency accounts?|agency ad accounts?|ad credits?|spend match|ad rebate|ad cashback|threshold accounts?|aged accounts?|buy accounts?|promo voucher|account provider|monthly invoicing|credit line|line of credit)\b",
        r"(求梯子|求\s*vpn|求推荐|求机场|求节点|梯子推荐|vpn\s*推荐|机场推荐|什么梯子好用|哪个vpn好用|求个梯子|有推荐的梯子|稳定翻墙|买什么梯子|求开户|开户推荐|代理户|海外户|广告返点|广告赠金|广告返佣|企业户推荐)"
    ]
    for p in t1_patterns:
        if re.search(p, content):
            return 1, "Direct Intent / Explicit Solution Seeking"

    # Tier 2: Comparison / Competitor / Alternative / Pain Point
    t2_patterns = [
        r"\b(vs|versus|\bor\b|alternative|better than|compared to|comparison|overpriced|expensive|broken|shut down|banned|lawsuit|issue with|not working|not applying|switch from|migrat|pros and cons|difference between|which is better|worth the money|is it worth|account disabled|account suspended|billing error|payment failed|spend limit|daily limit|disapproved|suspension|shadowban|shadowbanned)\b",
        r"(限额|封号|被封|封店|拒登|扣款失败|绑卡失败|无法充值)"
    ]
    for p in t2_patterns:
        if re.search(p, content):
            return 2, "Comparison / Competitor / Pain Point"

    # Also check if any custom keywords appear with recommendation or troubleshooting intent
    if custom_keywords:
        for kw in custom_keywords:
            kw_clean = str(kw).lower().strip()
            if kw_clean and len(kw_clean) > 3 and kw_clean in content:
                if re.search(r"\b(best|recommend|which|how to|fix|troubleshoot|review)\b", content):
                    return 2, "Target Domain Solution Consideration"

    # Tier 3: Problem Aware / General Discussion
    return 3, "Problem Aware / General Technical Discussion"


def clean_base_reply(text: str) -> str:
    """Strip out AI slop, conversational preambles, visual asset reference blocks, forum BBCode, and DM bait phrases."""
    if not text:
        return ""
    s = text.strip()

    # 1. Strip markdown code fences if wrapped by LLM
    s = re.sub(r"^```(?:markdown|text|bbcode)?\s*\n", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\n```\s*$", "", s)

    # 2. Strip wrapping quotation marks if model wrapped entire answer
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()

    # 3. Strip conversational LLM preambles
    s = re.sub(
        r"^(?:(?:Here(?:'s| is)|Below is) (?:a |the )?(?:ready-to-post |suggested |draft |helpful )?(?:reply|response|comment|answer)(?: for (?:Reddit|X|the forum))?:?\s*)+",
        "",
        s,
        flags=re.IGNORECASE
    )
    s = re.sub(
        r"^(?:Certainly!?|Sure thing!?|Sure!?|Of course!?|Great question!?)\s*(?:Here(?:'s| is)[^:\n]*:)?\s*",
        "",
        s,
        flags=re.IGNORECASE
    )

    # 4. Remove OP preface if present
    s = re.sub(r"^OP here\s*—\s*dropping the detailed context and statutory breakdown for the diagram above:\s*", "", s, flags=re.IGNORECASE)
    # Remove OP footer if present
    s = re.sub(r"\n+\*\*Interactive Lookup & Raw Data:\*\*.*$", "", s, flags=re.DOTALL)
    # Remove markdown reference chart block
    s = re.sub(r"\n+>\s*📊\s*\*\*(?:Reference Chart|Community Reference):\*\*.*$", "", s, flags=re.DOTALL)
    # Remove BBCode [CENTER][URL=...][IMG]...[/IMG][/URL]...[/CENTER] block
    s = re.sub(r"\n*\[CENTER\]\[URL=.*?\[/CENTER\]", "", s, flags=re.DOTALL | re.IGNORECASE)

    # 5. Clean aggressive DM bait phrases that trigger AutoMod
    s = re.sub(r"(?:\.\s*)?(?:,\s*)?(?:or\s+)?feel free to (?:shoot|send|drop) me a (?:dm|pm)[^.\n]*[.\n]?", ".", s, flags=re.IGNORECASE)
    s = re.sub(r"(?:\.\s*)?(?:,\s*)?(?:or\s+)?shoot me a (?:dm|pm|message)[^.\n]*[.\n]?", ".", s, flags=re.IGNORECASE)
    s = re.sub(r"\blet me know if you want me to drop the link(?:,\s*or)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\.{2,}", ".", s)

    # 6. Strip cliché trailing AI signoffs and solicitation triggers
    s = re.sub(r"\n+(?:Hope this helps[!.]*|Let me know.*|Feel free to.*|I can help.*|Best regards,.*|Cheers[!.]*)\s*$", "", s, flags=re.IGNORECASE)

    # 7. Normalize punctuation inflation (e.g. '!!' -> '!')
    s = re.sub(r"!{2,}", "!", s)
    s = re.sub(r"\s+\.", ".", s)
    return s.strip()


def match_visual_asset(
    title: str,
    excerpt: str,
    visual_assets: list[dict] | None,
    requested_asset_id: str | None = None
) -> dict | None:
    """Intelligently match the most relevant visual diagram/infographic asset based on context intent or explicit ID."""
    if not visual_assets:
        return None

    # Handle explicit request from user/frontend
    if requested_asset_id:
        if requested_asset_id.lower() in ("none", "null", "false", "off", "no_asset"):
            return None
        for asset in visual_assets:
            if asset.get("id") == requested_asset_id:
                return asset

    full_text = f"{title} {excerpt}".lower()
    best_asset = None
    max_score = 0
    for asset in visual_assets:
        score = 0
        kws = asset.get("intent_keywords") or []
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.split(",") if k.strip()]
        for kw in kws:
            kw_clean = str(kw).lower().strip()
            if not kw_clean:
                continue
            # Multi-word phrase matches carry higher semantic weight
            if " " in kw_clean:
                if re.search(r"\b" + re.escape(kw_clean) + r"\b", full_text):
                    score += 5
                elif kw_clean in full_text:
                    score += 2
            else:
                if re.search(r"\b" + re.escape(kw_clean) + r"\b", full_text):
                    score += 3
                elif kw_clean in full_text:
                    score += 1
        if score > max_score:
            max_score = score
            best_asset = asset
    # Require at least 4 score points (or multi-word match / 2 distinct keyword hits) to avoid weak single-word false matches
    return best_asset if max_score >= 4 else (visual_assets[0] if len(visual_assets) == 1 else None)


def markdown_to_bbcode(text: str) -> str:
    """Convert standard markdown (bold, italic, links, blockquotes) to standard forum BBCode (vBulletin/phpBB/XenForo)."""
    s = text
    # Bold **text** or __text__
    s = re.sub(r"\*\*(.+?)\*\*", r"[B]\1[/B]", s)
    s = re.sub(r"__(.+?)__", r"[B]\1[/B]", s)
    # Italic *text* or _text_
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"[I]\1[/I]", s)
    # Markdown links [title](url)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"[URL='\2']\1[/URL]", s)
    # Blockquotes > text
    lines = s.split("\n")
    bb_lines = []
    quote_acc = []

    def flush_quote():
        if quote_acc:
            bb_lines.append(f"[QUOTE]{' '.join(quote_acc)}[/QUOTE]")
            quote_acc.clear()

    for line in lines:
        if line.startswith(">"):
            content = line.lstrip("> ").strip()
            if content:
                quote_acc.append(content)
        else:
            flush_quote()
            bb_lines.append(line)
    flush_quote()
    return "\n".join(bb_lines)


def format_multichannel_pack(
    base_reply: str,
    title: str,
    excerpt: str,
    site_name: str,
    site_url: str,
    anti_ban_mode: str,
    matched_asset: dict | None = None,
    stealth_mode: str = "direct_link"
) -> dict:
    """Package the generated reply into Reddit Markdown, Forum BBCode, and Reddit OP First-Comment Sequencing formats."""
    clean_text = clean_base_reply(base_reply)

    # 1. Reddit Markdown reply
    reddit_reply = clean_text
    if matched_asset:
        target = matched_asset.get("target_url") or site_url
        caption = matched_asset.get("caption") or matched_asset.get("name", "reference chart")
        clean_cap = caption.rstrip(".").strip()
        asset_name = (matched_asset.get("name") or "").strip()
        if asset_name and len(asset_name) < len(clean_cap):
            clean_cap = asset_name
        elif len(clean_cap) > 40:
            clean_cap = clean_cap[:40].rsplit(" ", 1)[0]

        is_asking_link = bool(re.search(
            r"where\s+can\s+i|where\s+to\s+(find|check|look)|link\s+please|is\s+there\s+a\s+(tool|calculator|lookup|link)",
            f"{title} {excerpt}",
            re.IGNORECASE
        ))
        has_invite_hook = bool(re.search(
            r"\b(?:dm|pm)\b|drop\s+the\s+link|send\s+it\s+over|shoot\s+me",
            clean_text,
            re.IGNORECASE
        ))

        site_already_mentioned = bool(site_name and site_name.lower() in clean_text.lower())

        if site_already_mentioned:
            reddit_asset_block = ""
        elif stealth_mode in ("profile_only", "bio_routing", "two_step"):
            reddit_asset_block = (
                f"\n\n(Referenced the {clean_cap} specs from the {site_name} database)."
            )
        elif stealth_mode == "inbound_dm" or anti_ban_mode == "inbound_dm":
            reddit_asset_block = (
                f"\n\n(I benchmarked the {clean_cap} breakdown on a spreadsheet—feel free to shoot me a DM if you want the raw doc)."
            )
        elif anti_ban_mode == "brand_search" or (anti_ban_mode == "adaptive" and not is_asking_link) or has_invite_hook:
            reddit_asset_block = (
                f"\n\n(I pulled the {clean_cap} specs from the {site_name} database when checking mine—handy if you need the exact measurements)."
            )
        else:
            reddit_asset_block = (
                f"\n\n(Here's the [{clean_cap}]({target}) from the {site_name} specs library for reference)."
            )
        reddit_reply = clean_text + reddit_asset_block

    # 2. Forum BBCode format (vBulletin, phpBB, BuggiesGoneWild, Bimmerpost)
    bb_body = markdown_to_bbcode(clean_text)
    if matched_asset and matched_asset.get("image_url"):
        target = matched_asset.get("target_url") or site_url
        img_url = matched_asset.get("image_url", "")
        caption = matched_asset.get("caption") or matched_asset.get("name", "Reference Chart")

        # Natural enthusiast forum attachment style
        bbcode_asset_block = (
            f"\n\n[IMG]{img_url}[/IMG]\n"
            f"[SIZE=1][I]{caption} — via [URL='{target}']{site_name}[/URL][/I][/SIZE]"
        )
        bbcode_reply = f"{bb_body}{bbcode_asset_block}"
    else:
        bbcode_reply = bb_body

    # 3. Reddit OP First-Comment Sequencing (OP 首评法)
    # Designed for when posting an Image Post (uploading the diagram/infographic), dropping this high-value first comment within 30s
    if matched_asset:
        target_link = matched_asset.get("target_url") or site_url
        op_first_comment = (
            f"OP here — dropping the detailed context and statutory breakdown for the chart above:\n\n"
            f"{clean_text}\n\n"
            f"(Put together an interactive lookup table with the raw statutory text here if anyone needs the state-by-state codes: [{site_name}]({target_link}))"
        )
    else:
        op_first_comment = (
            f"OP here — dropping the detailed context and technical breakdown:\n\n"
            f"{clean_text}\n\n"
            f"(Full reference specs and raw data sheet bookmarked here: [{site_name}]({site_url}))"
        )

    # 4. 𝕏 / Twitter reply format (≤220 chars)
    x_reply = clean_text
    if len(x_reply) > 220:
        first_para = clean_text.split("\n\n")[0]
        if len(first_para) <= 220:
            x_reply = first_para
        else:
            x_reply = first_para[:215] + "..."

    return {
        "reddit": reddit_reply,
        "bbcode": bbcode_reply,
        "op_comment": op_first_comment,
        "x": x_reply
    }


from config import DEFAULT_GOLF_PERSONAS

AB_STYLES = {
    "guru": {
        "key": "guru",
        "label": "⚡ 极客干货向",
        "name": "Pure Technical Guru & Master Systems Engineer",
        "tone": "Authoritative, deeply technical, engineering-grade diagnosis with zero fluff. Focuses on root causes, specs, wiring, pinouts, firmware/controller logic, and exact failure modes. Speaks with undeniable technical authority that commands immediate respect.",
        "match_keywords": ["schematic", "pinout", "controller", "voltage", "technical", "engineering", "guru"]
    },
    "authentic": {
        "key": "authentic",
        "label": "🛠️ 真实测评向",
        "name": "Hands-on DIYer & Real-World Community Enthusiast",
        "tone": "Relatable, candid, first-person garage storytelling. Speaks as a fellow user who personally wrestled with this exact problem all weekend. Shares what broke, what worked, real costs, trial-and-error, and practical lessons learned with warmth and authentic empathy.",
        "match_keywords": ["diy", "garage", "experience", "honest", "review", "tried", "tested"]
    }
}

PERSONAS = {p["key"]: p for p in DEFAULT_GOLF_PERSONAS}
PERSONAS.update(AB_STYLES)


def classify_persona(
    title: str,
    text: str = "",
    subreddit: str = "",
    custom_personas: list[dict] | None = None
) -> dict:
    """
    Classify the optimal dynamic persona based on technical context and intent.
    Supports dynamic domain metapersonas tailored to ANY project/product.
    """
    content = f"{title} {text}".lower()

    # 1. If custom domain personas exist for this project, match by keyword affinity
    if custom_personas and len(custom_personas) > 0:
        scored: list[tuple[int, dict]] = []
        for p in custom_personas:
            score = 0
            kws = p.get("match_keywords") or []
            for kw in kws:
                if kw and kw.lower() in content:
                    score += 1
            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_persona = scored[0]
        if best_score > 0:
            return best_persona
        # Fallback to the first persona in project list if no specific keywords triggered
        return custom_personas[0]

    GENERIC_EXPERT_PERSONA = {
        "key": "expert",
        "label": "🎯 领域专家",
        "name": "Senior Product & Technical Domain Specialist",
        "tone": "Direct, hands-on, zero fluff. Diagnoses root causes with technical clarity and provides immediate actionable value without corporate buzzwords.",
        "match_keywords": []
    }

    # 2. Golf cart domain detection for backward compatibility
    compliance_keywords = [
        "law", "legal", "dmv", "police", "sheriff", "ticket", "street legal", "statute",
        "inspection", "title", "plate", "registration", "fmvss", "as4", "as5", "vin",
        "serial", "speed limit", "road", "public", "ordinance"
    ]
    modder_keywords = [
        "lift", "lift kit", "tire", "tires", "wheel", "wheels", "rubbing", "spindle",
        "a-arm", "navitas", "speed", "mph", "fast", "all-terrain", "offset", "camber",
        "controller tuning", "otf", "high speed", "gears", "motor swap"
    ]
    mechanic_keywords = [
        "wiring", "solenoid", "controller", "pinout", "curtis", "alltrax", "lithium",
        "battery", "batteries", "36v", "48v", "charger", "obc", "fuse", "clicking",
        "wont run", "won't run", "motor", "smoke", "spark", "resistor", "diode",
        "throttle", "its", "shunts", "voltage drop", "bms", "diagnostic"
    ]
    cruiser_keywords = [
        "neighborhood", "village", "cruiser", "kids", "seat belt", "mirror", "horn",
        "light kit", "accessories", "enclosure", "sound bar", "speaker", "cover",
        "which cart", "recommendation", "buying", "club car vs ezgo", "family",
        "golf course", "daily", "commute"
    ]

    is_golf = any(k in content for k in ("cart", "golf", "curtis", "alltrax", "navitas", "lsv", "club car", "ezgo", "yamaha")) or "golf" in (subreddit or "").lower()
    if is_golf:
        if any(k in content for k in compliance_keywords):
            return PERSONAS["compliance"]
        if any(k in content for k in modder_keywords):
            return PERSONAS["modder"]
        if any(k in content for k in mechanic_keywords):
            return PERSONAS["mechanic"]
        if any(k in content for k in cruiser_keywords):
            return PERSONAS["cruiser"]
        return PERSONAS["mechanic"] if "electric" in (subreddit or "").lower() else PERSONAS["cruiser"]

    # 3. Universal generic persona for all other products/markets
    return GENERIC_EXPERT_PERSONA


def get_learned_anti_ban_context(subreddit: str = "", platform: str = "reddit") -> str:
    """Retrieve dynamic self-healing anti-ban rules learned from real platform feedback."""
    try:
        from db import get_db
        with get_db() as db:
            rows = db.execute(
                """SELECT title, pattern, action_taken FROM ai_learnings
                   WHERE learning_type != 'golden_reply'
                     AND (subreddit = ? OR subreddit = '' OR platform = ?)
                   ORDER BY id DESC LIMIT 4""",
                (subreddit or "", platform or "reddit")
            ).fetchall()
            if not rows:
                return "- Standard Safe Engagement: Ensure 90% technical value before referencing tool by brand name."
            items = []
            for r in rows:
                items.append(f"- Learned Guard [{r['title']}]: {r['pattern']} -> {r['action_taken']}")
            return "\n".join(items)
    except Exception:
        return "- Standard Safe Engagement: Value-first, zero promotional hype."


def get_learned_golden_templates(subreddit: str = "", platform: str = "reddit", query_text: str = "") -> str:
    """Retrieve high-upvote golden reply examples from past feedback loop for few-shot guidance."""
    try:
        from db import get_db
        with get_db() as db:
            selected_rows = []
            if query_text:
                q_words = [w.lower().strip() for w in re.split(r"[\s,._-]+", query_text) if len(w) >= 3]
                if q_words:
                    candidates = db.execute(
                        """SELECT title, pattern, sample_text FROM ai_learnings
                           WHERE learning_type = 'golden_reply'
                             AND (subreddit = ? OR subreddit = '' OR platform = ?)
                           ORDER BY id DESC LIMIT 100""",
                        (subreddit or "", platform or "reddit")
                    ).fetchall()
                    for c in candidates:
                        comb = f"{c['title']} {c['pattern']} {c['sample_text']}".lower()
                        if any(w in comb for w in q_words):
                            selected_rows.append(c)
                            if len(selected_rows) >= 2:
                                break
            if not selected_rows:
                selected_rows = db.execute(
                    """SELECT title, pattern, sample_text FROM ai_learnings
                       WHERE learning_type = 'golden_reply'
                         AND (subreddit = ? OR subreddit = '' OR platform = ?)
                       ORDER BY id DESC LIMIT 2""",
                    (subreddit or "", platform or "reddit")
                ).fetchall()
            if not selected_rows:
                return ""
            items = []
            for r in selected_rows:
                if r["sample_text"]:
                    items.append(f"【{r['title']} - {r['pattern']}】\n\"{r['sample_text']}\"")
            if items:
                return "\nCOMMUNITY-PROVEN HIGH-UPVOTE PATTERNS (Emulate their helpfulness & voice):\n" + "\n---\n".join(items)
            return ""
    except Exception:
        return ""


def get_learned_resurrection_context(subreddit: str = "", platform: str = "reddit") -> str:
    """Retrieve high-value discussion patterns that were human-resurrected after being falsely filtered."""
    try:
        from db import get_db
        with get_db() as db:
            rows = db.execute(
                """SELECT title, pattern, sample_text FROM ai_learnings
                   WHERE learning_type = 'false_negative_correction'
                     AND (subreddit = ? OR subreddit = '' OR platform = ?)
                   ORDER BY id DESC LIMIT 2""",
                (subreddit or "", platform or "reddit")
            ).fetchall()
            if not rows:
                return ""
            items = [f"- Prioritized Discussion: {r['pattern']}" for r in rows]
            return "\nHUMAN-VALIDATED HIGH-INTENT TOPICS (Give priority technical depth):\n" + "\n".join(items)
    except Exception:
        return ""


def generate_site_integrated_reply(
    title: str,
    excerpt: str,
    subreddit: str,
    site_name: str = "Product",
    site_url: str = "",
    site_desc: str = "",
    pitch_instruction: str = "",
    anti_ban_mode: str = "brand_search",
    funnel_tier: int = 3,
    credential: dict | None = None,
    platform: str = "reddit",
    visual_assets: list[dict] | None = None,
    persona: str | None = None,
    personas: list[dict] | None = None,
    stealth_mode: str = "direct_link"
) -> str:
    """Generate an authoritative, stealth-promotional reply adhering to Promotion Warrior 3-Tier Funnel and Stealth Modes."""

    # 1. Resolve dynamic persona
    p_info = None
    if persona:
        if persona in AB_STYLES:
            p_info = AB_STYLES[persona]
        elif personas:
            p_info = next((p for p in personas if p.get("key") == persona), None)
        if not p_info and persona in PERSONAS:
            p_info = PERSONAS[persona]
    if not p_info:
        p_info = classify_persona(title, excerpt, subreddit, custom_personas=personas)

    # Dynamic Intent Routing: route site_url to specific calculator / tool
    from auto_responder import resolve_target_landing_page
    site_url = resolve_target_landing_page(site_url, title=title, text=excerpt)

    # 2. Retrieve dynamic self-healing anti-ban learnings & community-proven golden templates
    learned_rules = get_learned_anti_ban_context(subreddit, platform)
    golden_examples = get_learned_golden_templates(subreddit, platform, query_text=f"{title} {excerpt}")
    resurrection_context = get_learned_resurrection_context(subreddit, platform)

    if platform in ("x", "twitter"):
        if stealth_mode in ("profile_only", "bio_routing"):
            cite = f'DO NOT include any links. At the end, naturally mention: "pinned the full chart/specs on my profile bio if helpful".'
        elif stealth_mode == "inbound_dm" or anti_ban_mode == "inbound_dm":
            cite = f'DO NOT include any links. At the end, naturally offer: "shoot me a DM if u want the comparison sheet/checklist".'
        elif anti_ban_mode == "brand_search":
            cite = f'Mention "{site_name}" casually as a lookup tool or breakdown site (e.g. "{site_name} has the state chart"). Do NOT paste long links.'
        elif anti_ban_mode == "direct_link":
            cite = f'Include short link: {site_url}'
        else:
            cite = f'Cite "{site_name}" tool by name naturally.'

        prompt = f"""You are an experienced enthusiast replying to a tweet on X (Twitter).
Adopted Persona: {p_info['name']} ({p_info['label']}).
Tone Guidance: {p_info['tone']}
Goal: Provide direct, sharp technical/legal help in 1-2 punchy sentences.

CRITICAL X / TWITTER RULES:
1. MAX 220 CHARACTERS TOTAL. Must easily fit in a single tweet reply (limit is 280).
2. NO promotional tone, NO sales jargon, NO emojis or hashtags.
3. Peer-to-peer, conversational, lowercase or normal punctuation.
4. {cite}
5. CONVERSION HOOK: Weave in a low-friction hook inviting a DM or profile check (e.g. "dm me if u need the pinout chart/calculator", or "got the free tool bookmarked on my bio").

DYNAMIC DEFENSES:
{learned_rules}

Topic: {title}
Tweet Content: {excerpt}
Resource: {site_name} ({site_desc})
Special Note: {pitch_instruction}

Write ONLY the final tweet text to reply with:"""
        max_tok = 120
    elif platform == "forum":
        # Enthusiast Forum (vBulletin / XenForo / phpBB e.g. Buggies Gone Wild, Cartaholics)
        if stealth_mode in ("profile_only", "bio_routing"):
            cite_rule = f'- FORUM CITATION (STEALTH PROFILE): 100% pure technical answer. No active links in body. Mention you bookmarked the full wiring/spec PDF in your profile bio signature.'
        elif stealth_mode == "inbound_dm" or anti_ban_mode == "inbound_dm":
            cite_rule = f'- FORUM CITATION (INBOUND PM): 100% pure technical answer. No active links in body. Conclude naturally by offering to share the full spreadsheet or checklist via PM.'
        elif anti_ban_mode == "direct_link" and site_url:
            cite_rule = f'- FORUM CITATION (BBCODE LINK): Provide a clean BBCode link: [URL="{site_url}"]{site_name} Interactive Tool[/URL] as a technical reference.'
        else:
            cite_rule = f'- FORUM CITATION: Casually reference the "{site_name}" technical database or wiring lookup table by name.'

        prompt = f"""You are a veteran technical forum contributor commenting on a vertical enthusiast forum (like Buggies Gone Wild / Cartaholics) regarding {site_name} ({site_desc}).

Adopted Persona: {p_info['name']} ({p_info['label']})
Tone: Respected garage master, seasoned mechanic, detailed hands-on troubleshooting, generous with technical knowledge, respectful of forum community norms.

FORUM WRITING RULES:
1. Format your response cleanly using standard BBCode tags ([b]bold[/b] for key wire colors/part numbers/voltages, [i]italics[/i] for nuances).
2. Start directly with the troubleshooting steps or root-cause diagnosis.
3. {cite_rule}
4. Tone is friendly, peer-to-peer garage banter. No corporate fluff.
5. OPEN LOOP HOOK: Conclude naturally by offering to share the full schematic, measurement chart, or calculator tool via PM or reply if anyone needs it.

Topic: {title}
Forum Thread Excerpt: {excerpt}
Resource: {site_name} ({site_desc})

Write ONLY the forum response in valid BBCode markdown. No greetings or signoffs like 'Best regards'."""
        max_tok = 450
    else:
        # Reddit Markdown
        if stealth_mode in ("profile_only", "bio_routing"):
            citation_rule = f"""- ANTI-BAN MODE: STEALTH BIO-ROUTING (ZERO-LINK TROJAN STRATEGY).
- CRITICAL: UNDER NO CIRCUMSTANCES include an http:// or https:// URL link!
- Deliver 100% pure, deep technical diagnosis and exact specifications.
- End with a natural peer sign-off pointing to your profile, e.g.:
  "Saved the full pinout schematic and 50-state checklist over on my profile bio if you need the PDF specs."
- This guarantees 0% chance of AutoMod removal while converting high-intent users through profile visits."""
        elif stealth_mode == "inbound_dm" or anti_ban_mode == "inbound_dm":
            citation_rule = f"""- ANTI-BAN MODE: INBOUND DM ASSET GAP (ZERO-LINK INBOUND TROJAN).
- CRITICAL: UNDER NO CIRCUMSTANCES include an http:// or https:// URL link!
- Deliver 80% deep, authoritative technical diagnosis to establish instant credibility.
- For the remaining 20%, leave a high-value asset gap (e.g. comparison spreadsheet, checklist, diagnostic matrix) and invite the reader to DM you if they want the raw doc. E.g.:
  "Mapped out the exact {site_name} tier breakdown and fee comparison on a spreadsheet. Feel free to shoot me a DM if you want me to share the sheet."
- When users reach out via DM, it counts as a consensual user-initiated chat with zero ban risk."""
        elif stealth_mode == "two_step":
            citation_rule = f"""- ANTI-BAN MODE: STEALTH TWO-STEP PING-PONG.
- Step 1: Give a solid 80% technical diagnosis, but intentionally pause on the critical fork (e.g. asking for their specific controller serial number / firmware version / state jurisdiction).
- Do NOT include external links in step 1.
- End with an engaging diagnostic question. The tool link will be introduced in the follow-up once OP responds."""
        elif anti_ban_mode == "brand_search":
            citation_rule = f"""- ANTI-BAN MODE: BRAND SEARCH / ZERO-URL (HIGHEST SAFETY).
- UNDER NO CIRCUMSTANCES include an http:// or https:// URL link! Bare links get auto-flagged by AutoMod and ruin CQS.
- Instead, casually mention "{site_name}" by name as an open-source/free resource, database, or tool. E.g.:
  "{site_name} has a free breakdown and lookup tool/guide on their site that covers this exact issue."
- This protects our domain from being blacklisted while driving high-intent organic brand search queries on Google."""
        elif anti_ban_mode == "direct_link":
            citation_rule = f"""- ANTI-BAN MODE: DIRECT LINK.
- Provide a direct markdown link: [{site_name} Tools]({site_url})
- Weave it organically at the end of the technical answer as a helpful reference."""
        else:  # auto / adaptive
            citation_rule = f"""- ANTI-BAN MODE: SMART ADAPTIVE.
- Only include the direct link ({site_url}) if the post asks "where can I check", "is there a calculator/link/tool", or "link please".
- In all other cases, DO NOT include an active URL; cite "{site_name} tools lookup" by name so the user searches it organically."""

        if funnel_tier == 1:
            strategy_directive = """- PROMOTION WARRIOR TACTIC: TIER 1 DIRECT CLOSE.
The user is actively looking for recommendations or solutions. Give your direct, authoritative verdict immediately. State why X works and seamlessly position our resource as the primary reference."""
        elif funnel_tier == 2:
            strategy_directive = """- PROMOTION WARRIOR TACTIC: TIER 2 SIDE ATTACK.
The user is comparing options or dealing with frustration. Validate their pain point -> Explain the root cause -> Introduce our tool/guide as the objective benchmark or cheat sheet."""
        else:
            strategy_directive = """- PROMOTION WARRIOR TACTIC: TIER 3 VALUE FIRST.
Provide pure, deep technical value first. Solve the problem thoroughly. Only mention the tool in passing as a footnote or don't push it aggressively."""

        prompt = f"""You are an authentic, experienced, helpful peer commenting in the community of r/{subreddit} and the space of {site_name} ({site_desc}) on Reddit.

ADOPTED DYNAMIC PERSONA:
Role: {p_info['name']} ({p_info['label']})
Voice & Methodology: {p_info['tone']}
Make sure your terminology, diagnosis depth, and natural phrasing fully embody this persona.

PROMOTION WARRIOR FUNNEL STRATEGY:
{strategy_directive}

ANTI-BAN & REDDIT ALGORITHM SURVIVAL RULES (CRITICAL):
1. ZERO PROMOTIONAL TONE: Never sound like a brand rep, copywriter, or marketer. Write in first-person lowercase/natural punctuation like an authentic veteran community member.
2. BLUF MANDATE (Bottom Line Up Front): Deliver the exact technical specification, root cause, or numerical measurement (e.g. inches, canopy drop, fabric specs, voltage, wiring pinout) in sentence 1.
3. VALUE-FIRST MANDATE: 90% of the comment must be direct, exhaustive troubleshooting or actionable insight. Solve their immediate headache FIRST with zero cost or practical garage hacks before mentioning any links or tools.
4. ANTI-AI SLOP: Strictly avoid boilerplate AI phrases (e.g. "It's important to remember", "Furthermore", "Delve", "Crucial", "A testament to", "Navigating the complexities", "In summary").
5. ORGANIC DOMAIN CITATION:
{citation_rule}
6. STRICT CONTENT SAFETY:
   - NO emojis unless 1 common emoji fits naturally.
   - NO generic greetings ("Hey there!", "Hope this helps!").
   - Max 2-3 concise paragraphs.
7. NATURAL PEER-TO-PEER CLOSING (ZERO SPAM TRIGGER WORDS):
   - For standard modes, avoid cold proactive solicitation (e.g. "I can help", "happy to help", "reach out", "let me know").
   - If using STEALTH BIO-ROUTING mode, naturally end with the profile hook (e.g., "pinned the full breakdown on my profile bio if helpful").
   - If using INBOUND DM mode, naturally conclude by inviting them to DM you for the specific promised technical spreadsheet or checklist (e.g., "feel free to shoot me a DM if you want the comparison spreadsheet").
   - Otherwise, conclude with an objective, neutral observation (e.g. "hope that clears up the learning phase nuances", "should get you back on track").
   - If citing the site/tool, keep it natural and subtle in accordance with the organic domain citation rules.
8. STRICT INBOUND HOOK MANDATE (ZERO FALSE CLAIMS):
   - NEVER falsely claim in public that you already sent a message or link.
   - Keep closing grounded in pure mechanical generosity.

DYNAMIC ANTI-BAN SELF-HEALING DEFENSES:
{learned_rules}{golden_examples}{resurrection_context}

Resource details:
- Name: {site_name}
- URL: {site_url}
- Purpose: {site_desc}
- Special Guidance: {pitch_instruction or 'Provide technical value first; mention tool only if relevant.'}

Post Title: {title}
Subreddit: r/{subreddit}
Content/Excerpt: {excerpt}

Write ONLY the ready-to-post Reddit markdown comment. No introductory notes."""
        max_tok = 450

    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)
    if not credential:
        raise ValueError("No AI credential available")
    base_reply = run_ai_prompt(prompt, credential, max_tokens=max_tok)

    if visual_assets and platform not in ("x", "twitter"):
        matched = match_visual_asset(title, excerpt, visual_assets)
        if matched:
            pack = format_multichannel_pack(base_reply, title, excerpt, site_name, site_url, anti_ban_mode, matched, stealth_mode=stealth_mode)
            return pack["reddit"]

    return clean_base_reply(base_reply)


def generate_follow_up_reply(
    parent_reply: str,
    user_question: str,
    user_author: str,
    site_name: str = "My Product",
    site_url: str = "",
    pitch_instruction: str = "",
    persona: str | None = None,
    credential: dict | None = None
) -> str:
    """
    Generate a high-converting, authentic Step 2 conversational follow-up reply (Affiliate / Resource Close).
    Triggered when a community member replies to our previous diagnosis asking for specifics.
    """
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)

    if not credential:
        if site_url:
            return f"Glad that helped! For the full breakdown and wiring schematics, I documented the steps here: {site_url}"
        return f"Glad that helped! The full schematics and specs are over in the {site_name} library if you need the pinouts."

    prompt = f"""You are continuing a direct conversation on Reddit with user u/{user_author}.

Context:
Earlier, you gave a helpful technical diagnosis to the thread:
"{parent_reply[:300]}"

User u/{user_author} just replied directly to your comment:
"{user_question}"

Task (Step 2 - Conversational Affiliate / Resource Close):
1. Directly answer their specific question or confirm the part, model, or steps with authentic peer-to-peer enthusiasm.
2. Since the user is asking directly for recommendations/solutions, naturally share the recommended resource/link: {site_url or site_name}.
3. Instruction/Special Angle: {pitch_instruction or "Be genuine, friendly, and practical. Recommend based on real personal experience."}
4. Tone: Helpful garage buddy / experienced peer. Never sound like a pushy salesperson or marketer.
5. Length: Under 120 words. No corporate sign-offs."""

    try:
        reply = run_ai_prompt(prompt, credential, max_tokens=250)
        return reply.strip()
    except Exception:
        if site_url:
            return f"For that specific setup, here's the guide and breakdown I used: {site_url}"
        return f"For that specific setup, {site_name} has the complete guide and specs."


def resolve_dynamic_tool_url(base_url: str, text: str, offers_matrix: list | None = None) -> dict:
    """
    Intelligently routes a lead to the most relevant sub-tool / landing page based on context.
    Prioritizes offers_matrix (custom or passed), then falls back to built-in presets or base_url.
    Returns:
      {
        "tool_key": str,
        "tool_name": str,
        "routed_url": str
      }
    """
    t_lower = (text or "").lower()
    base = (base_url or "").rstrip("/")

    # 1. Custom offers matrix (or built-in Fairway Fort offers if not specified)
    matrix = offers_matrix
    if not matrix and "fairwayfort" in base:
        from config import DEFAULT_FAIRWAYFORT_OFFERS
        matrix = DEFAULT_FAIRWAYFORT_OFFERS

    if matrix and isinstance(matrix, list):
        for offer in matrix:
            if not isinstance(offer, dict):
                continue
            kws = offer.get("keywords") or []
            if isinstance(kws, str):
                kws = [k.strip() for k in kws.split(",") if k.strip()]
            if any(k.lower() in t_lower for k in kws if k):
                raw_url = (offer.get("url") or "").strip()
                if raw_url.startswith("http://") or raw_url.startswith("https://"):
                    routed_url = raw_url
                elif raw_url:
                    routed_url = f"{base}/{raw_url.lstrip('/')}"
                else:
                    routed_url = base
                key = offer.get("key", "custom_offer")
                name = offer.get("name", "专属推荐资源")
                name_en = offer.get("name_en") or offer.get("name", "reference tool")
                return {
                    "tool_key": key,
                    "tool_name": name,
                    "tool_name_en": name_en,
                    "key": key,
                    "name": name,
                    "name_en": name_en,
                    "routed_url": routed_url
                }

    # 2. Built-in FairwayFort fallback if on tools page
    if "fairwayfort" in base:
        return {
            "tool_key": "all_tools",
            "tool_name": "高尔夫球车通用技术工具箱",
            "tool_name_en": "Golf Cart Tech & Wiring Tools",
            "key": "all_tools",
            "name": "高尔夫球车通用技术工具箱",
            "name_en": "Golf Cart Tech & Wiring Tools",
            "routed_url": f"{base}/pages/tools" if "/pages/tools" not in base else base
        }

    # 3. Generic default
    return {
        "tool_key": "default",
        "tool_name": "专属推荐资源",
        "tool_name_en": "Technical Reference Specs",
        "key": "default",
        "name": "专属推荐资源",
        "name_en": "Technical Reference Specs",
        "routed_url": base_url
    }


def generate_offers_matrix_with_ai(
    site_name: str,
    site_description: str,
    site_url: str = "",
    keywords: list | None = None,
    credential: dict | None = None
) -> list:
    """
    Dynamically analyze a product/site and generate 3-5 high-converting micro-tools/checkers/calculators/guides
    (落地工具与 Offer 矩阵) with trigger keywords for intelligent 1v1 DM and chat routing.
    """
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)

    base = (site_url or "").rstrip("/")
    kw_str = ", ".join(keywords[:10]) if keywords else ""

    # Heuristic fallback if AI fails or no credential
    fallback = []
    if "fairway" in (site_name or "").lower() or "fairway" in base.lower() or "golf" in (site_description or "").lower():
        from config import DEFAULT_FAIRWAYFORT_OFFERS
        fallback = list(DEFAULT_FAIRWAYFORT_OFFERS)
    else:
        fallback = [
            {
                "key": "diagnostic_guide",
                "name": f"{site_name} 核心选型与排坑指南",
                "name_en": f"{site_name} Troubleshooting & Fitment Guide",
                "keywords": ["how to", "guide", "tutorial", "beginner", "fix", "start", "tips", "setup", "which one", "recommend"],
                "url": f"{base}/guide" if base else "/guide"
            },
            {
                "key": "spec_calculator",
                "name": f"{site_name} 规格与参数在线测算器",
                "name_en": f"{site_name} Online Spec & Sizing Calculator",
                "keywords": ["calc", "calculator", "size", "spec", "compatibility", "compare", "measurement", "metric", "dimension"],
                "url": f"{base}/calculator" if base else "/calculator"
            },
            {
                "key": "compliance_checklist",
                "name": f"{site_name} 行业合规核查与避坑清单",
                "name_en": f"{site_name} Compliance & Statutory Checklist",
                "keywords": ["check", "checklist", "verify", "rule", "law", "legal", "standard", "audit", "compliance", "inspection"],
                "url": f"{base}/checklist" if base else "/checklist"
            },
            {
                "key": "exclusive_offer",
                "name": f"{site_name} 社区专享特惠与选品表",
                "name_en": f"{site_name} Resource & Catalog Index",
                "keywords": ["discount", "deal", "coupon", "price", "cost", "quote", "where to buy", "cheap", "promo"],
                "url": base or "/"
            }
        ]

    if not credential:
        return fallback

    prompt = f"""You are an elite Conversion Rate Optimization (CRO) and SaaS/E-commerce Funnel Architect.
A marketing team is configuring intelligent lead conversion for:
- Product/Brand Name: "{site_name}"
- Site URL: "{site_url or 'https://example.com'}"
- Product Description & Mission: "{site_description}"
- Target Customer Keywords: "{kw_str}"

When prospects post in forums, Reddit, or X with specific technical pain points or buying questions, our system sends a personalized 1-on-1 DM or chat message routing them to the MOST relevant specific free micro-tool, calculator, decoder, compliance checker, fitment matrix, or buyer guide on the site (instead of sending everyone to the generic homepage).

Synthesize 3 to 5 realistic, high-converting utility tools or targeted landing page offers tailored specifically to "{site_name}":
For each tool/offer, provide:
1. "key": snake_case identifier (e.g. "pricing_calc", "vin_decoder", "size_recommender")
2. "name": attractive Chinese title (e.g. "极速与速比在线计算器", "车架号与年份解码工具", "全美各州路权合规核查器")
3. "name_en": clean English title for overseas communities (e.g. "Top Speed & Gear Ratio Calculator", "Serial & VIN Decoder", "50-State Street Legal Checker")
4. "keywords": array of 6-12 specific, distinct lowercase English trigger keywords/phrases that users type when they need this specific tool (e.g. ["vin", "serial", "what year", "model number"])
5. "url": realistic sub-URL path or full URL (e.g. "{base}/tools/calculator" or "{base}/pages/checker" or "/tools/...")

Output format requirement: Return ONLY a valid JSON array of objects (no markdown code fence, no introductory text, no comments).
Example:
[
  {{
    "key": "...",
    "name": "...",
    "name_en": "...",
    "keywords": ["...", "..."],
    "url": "..."
  }}
]"""

    try:
        raw = run_ai_prompt(prompt, credential, max_tokens=800).strip()
        if "```" in raw:
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list) and len(parsed) >= 2:
            cleaned = []
            for item in parsed:
                if isinstance(item, dict) and item.get("name") and item.get("keywords"):
                    cleaned.append({
                        "key": item.get("key") or f"tool_{len(cleaned)+1}",
                        "name": item.get("name"),
                        "name_en": item.get("name_en") or item.get("name"),
                        "keywords": [str(k).lower().strip() for k in item.get("keywords", []) if str(k).strip()],
                        "url": item.get("url") or (base or "/")
                    })
            if cleaned:
                return cleaned
        return fallback
    except Exception:
        return fallback


def generate_conversion_playbook(
    title: str,
    excerpt: str,
    author: str,
    site_name: str = "My Product",
    site_url: str = "",
    pitch_instruction: str = "",
    platform: str = "reddit",
    credential: dict | None = None,
    offers_matrix: list | None = None
) -> dict:
    """
    Generate an end-to-end 3-Stage Conversational Conversion Playbook
    (Round 1 Soft Icebreaker -> Round 2 Pain Diagnostic -> Round 3 Value Close)
    plus common objection handling guides.
    """
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)

    prefix = "u/" if platform == "reddit" else "@"
    author_display = f"{prefix}{author}" if author else "there"
    full_ctx = f"{title} {excerpt}".strip()

    # Fallback heuristic playbook
    routed = resolve_dynamic_tool_url(site_url, full_ctx, offers_matrix=offers_matrix)
    tool_label_cn = routed.get("tool_name", "排查工具/指南")
    tool_label_en = routed.get("tool_name_en") or routed.get("name_en") or "reference guide & specs"
    active_url = routed.get("routed_url") or site_url

    fallback = {
        "target_profile": {
            "intent_level": "Tier 1 - 高意向核心痛点",
            "primary_pain": title[:80] or "技术排查与配件选型",
            "recommended_angle": f"以真实老炮车主口吻，以技术诊断切入，自然顺承至【{tool_label_cn}】进行闭环转化。"
        },
        "rounds": [
            {
                "round": 1,
                "title": "Round 1 破冰共情 (Soft Icebreaker)",
                "goal": "纯同行技术排查，0外链，打消推销防备心理",
                "draft": f"Hey {author_display}, saw your post on '{title[:45]}'. Ran into the exact same symptom a while back. Did you already test the voltage drop under load, or is the solenoid still clicking?"
            },
            {
                "round": 2,
                "title": "Round 2 痛点诊断 (Pain Diagnostic)",
                "goal": "剖析避坑参数，引导对方主动确认具体车型/年份",
                "draft": f"That usually points to a thermal drop on the resistor or mismatched controller pinouts. Depending on your exact cart year and wiring harness, the fix is totally different. Which specific year/model cart are you working on?"
            },
            {
                "round": 3,
                "title": "Round 3 逼单转化 (Value Close)",
                "goal": "顺理成章送出专属工具/精准短链收割",
                "draft": f"Got it! For that setup, definitely double-check the pinout diagram before buying any new parts. I keep a bookmark of this free {site_name} {tool_label_en} ({active_url})—it has the exact wiring specs and test steps. Saved me a ton of headache, hope it helps!"
            }
        ],
        "objections": [
            {
                "objection": "这玩意收费吗？你们是不是推销卖配件的？",
                "response": "No, it's 100% free community tool/guide that I use when troubleshooting in my garage. Zero login or credit card needed."
            },
            {
                "objection": "我的车是老款/改装款，这上面的数据准吗？",
                "response": "Yes, it specifically lets you filter by manufacturer serial/OEM year and battery voltage to show the exact OEM vs aftermarket schematics."
            }
        ]
    }

    if not credential:
        return fallback

    prompt = f"""You are an elite consultative conversion strategist on {platform.title()}.
A prospect ({author_display}) posted:
Title: "{title[:200]}"
Details: "{excerpt[:300]}"

Resource to introduce: {site_name} ({active_url})
Target Tool/Resource Category: {tool_label_en} ({tool_label_cn})
Angle Instruction: {pitch_instruction or "Helpful peer who solved the exact same headache"}

Build an authentic 3-stage conversational chat closing playbook:
- Round 1 (Soft Icebreaker): Casual peer opening. Empathy + diagnostic question. ZERO link. ZERO marketing.
- Round 2 (Pain Diagnostic): Deepen into the technical cause, prompt them to reveal exact model/specs.
- Round 3 (Value Close): Smoothly share the link ({active_url}) as the exact free reference tool for their situation.
- 2 Objection responses: 1 for "is it free/selling?" and 1 for "compatibility with my specific cart".

Return ONLY valid JSON (no markdown fences, no explanation) with this structure:
{{
  "target_profile": {{
    "intent_level": "Tier 1 - 强烈求购/故障排查",
    "primary_pain": "<summary>",
    "recommended_angle": "<strategy>"
  }},
  "rounds": [
    {{"round": 1, "title": "Round 1 破冰共情", "goal": "纯技术排查，0外链建立信任", "draft": "<text>"}},
    {{"round": 2, "title": "Round 2 痛点诊断", "goal": "剖析避坑点，引对方确认配置", "draft": "<text>"}},
    {{"round": 3, "title": "Round 3 逼单转化", "goal": "送出精准工具/短链收割", "draft": "<text>"}}
  ],
  "objections": [
    {{"objection": "<objection 1>", "response": "<response 1>"}},
    {{"objection": "<objection 2>", "response": "<response 2>"}}
  ]
}}"""

    try:
        raw = run_ai_prompt(prompt, credential, max_tokens=600).strip()
        # Clean json if wrapped in ```json
        if "```" in raw:
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw.strip())
        if "rounds" in parsed and len(parsed["rounds"]) == 3:
            return parsed
        return fallback
    except Exception:
        return fallback


def generate_affiliate_playbook(
    title: str,
    excerpt: str,
    author: str,
    product_name: str = "",
    affiliate_url: str = "",
    competitor_name: str = "",
    discount_code: str = "",
    pitch_instruction: str = "",
    platform: str = "reddit",
    credential: dict | None = None
) -> dict:
    """
    Generate an elite, high-converting Affiliate closing package.
    Tailored for high-intent zero-search/low-search transactional queries (competitor churn, comparison, pricing complaints).
    """
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)

    prefix = "u/" if platform == "reddit" else "@"
    author_display = f"{prefix}{author}" if author else "there"
    comp_disp = competitor_name or "the incumbent tool"
    prod_disp = product_name or "the recommended alternative"
    code_mention = f" (use coupon '{discount_code}' for 20% off)" if discount_code else ""
    raw_link = affiliate_url or "https://example.com/partner-deal"

    from dm_agent import append_utm_params
    tracked_link = append_utm_params(raw_link, platform=platform, medium="dm", campaign=prod_disp, content="round3")
    link_disp = tracked_link

    fallback = {
        "target_dilemma": {
            "intent_type": "High-Intent Affiliate Opportunity",
            "frustration_point": title[:80] or "Seeking reliable alternative or better pricing",
            "strategy": f"Empathize with frustration regarding {comp_disp}, highlight {prod_disp} as the proven high-ROI fix, and deliver referral perks in private DM."
        },
        "public_reply": {
            "comment": (
                f"Ran into this exact issue with {comp_disp} last quarter. The core problem is how they lock essential features "
                f"behind enterprise tiers while hiking base renewal prices. Ended up migrating over to {prod_disp} after testing a few options—"
                f"it handles the exact same workload with zero seat-gating."
            ),
            "inbound_hook": (
                f"I actually put together a side-by-side pricing & feature benchmark sheet comparing {comp_disp} vs {prod_disp} "
                f"(including the hidden rate limits). Feel free to shoot me a DM if you want me to send the breakdown over."
            )
        },
        "dm_funnel": {
            "subject": f"Quick comparison breakdown: {comp_disp} vs {prod_disp}",
            "message": (
                f"Hey {author_display}, saw your post on looking for a reliable alternative to {comp_disp}. "
                f"Here is the comparison breakdown I mentioned. If you decide to test {prod_disp}, here is the partner link{code_mention}: "
                f"{link_disp}. Hope it saves your budget!"
            ),
            "rounds": [
                {
                    "round": 1,
                    "title": "Round 1 痛点共鸣 · 交付干货",
                    "goal": "证实竞品收费坑/性能短板，交付自制对比表，0推销建立信任",
                    "draft": f"Hey {author_display}, completely agree with your take on {comp_disp}. Ran into the exact same pricing shock when our usage scaled. Sent you the comparison breakdown so you can check the math yourself."
                },
                {
                    "round": 2,
                    "title": "Round 2 场景实测 · 优势背书与资料诱饵",
                    "goal": "结合自己实操，点出目标产品在同等用量下节省 60% 成本的杀手锏功能，并提供 1 页纸避坑资料/Checklist",
                    "draft": f"The biggest win with {prod_disp} for our workflow was that they don't charge per seat or penalize API calls. Setup took about 15 minutes to import all legacy data. If helpful, I also put together a 1-page migration checklist & benchmark sheet I can send over."
                },
                {
                    "round": 3,
                    "title": "Round 3 临门一脚 · 折扣闭环",
                    "goal": "送出带有专属优惠的返佣链接/折扣码，坦诚合规披露",
                    "draft": f"If you're going to try it, definitely grab this referral link: {link_disp}{code_mention}—gives you the extended trial + 20% off. Full disclosure: it's my referral link, but I genuinely vouch for it after testing 4 different options."
                }
            ],
            "objections": [
                {
                    "objection": "数据迁移麻烦吗？会不会导致业务中断？",
                    "response": "Migration is literally a 1-click CSV/API import. Took me under 20 minutes with zero downtime."
                },
                {
                    "objection": "你推荐这个是不是有提成？",
                    "response": "Yes, full disclosure—I have a community referral code because I use it daily and negotiated a discount for friends. You don't have to use my link, but the coupon code is legit and saves you real money."
                }
            ]
        }
    }

    if not credential:
        return fallback

    prompt = f"""You are a master SaaS & E-commerce Affiliate Conversion Strategist operating in {platform.title()} communities.
A prospect ({author_display}) posted a high-commercial-intent discussion:
Title: "{title[:200]}"
Details: "{excerpt[:300]}"

Affiliate Product to Recommend: {prod_disp}
Affiliate Referral Link: {link_disp}
Incumbent/Competitor Mentioned: {comp_disp}
Special Promo/Discount Code: {discount_code or "None"}
Special Angle: {pitch_instruction or "Authentic peer who switched after getting burned by pricing"}

ANTI-BAN & ZERO FALSE CLAIM MANDATE (STRICT):
- The public comment and inbound_hook must NEVER say 'Sent you a DM', 'Check your inbox', or claim you messaged them!
- Always frame as an authentic open invitation for them to message you ('feel free to shoot me a DM if you want the breakdown spreadsheet').
- Round 2 must highlight core advantages/ROI and offer a free 1-page setup checklist or benchmark sheet as a lead magnet.
- Round 3 must include the referral link ({link_disp}).

Generate an elite Affiliate Conversion Package structured as valid JSON (no markdown fences, no extra text):
{{
  "target_dilemma": {{
    "intent_type": "Alternative / Comparison / Deal",
    "frustration_point": "<specific pain with current solution>",
    "strategy": "<how to position the product>"
  }},
  "public_reply": {{
    "comment": "<authentic, peer-to-peer 80-word troubleshooting/comparison comment with ZERO links>",
    "inbound_hook": "<inbound DM invitation offering private benchmark sheet/discount breakdown>"
  }},
  "dm_funnel": {{
    "subject": "<under 8 words relevant subject>",
    "message": "<helpful 1v1 icebreaker note delivering the resource + referral link with honest disclosure>",
    "rounds": [
      {{"round": 1, "title": "Round 1 痛点共鸣", "goal": "验证痛点，交付干货", "draft": "<round 1 draft>"}},
      {{"round": 2, "title": "Round 2 场景实测", "goal": "点出核心优势与ROI", "draft": "<round 2 draft>"}},
      {{"round": 3, "title": "Round 3 折扣闭环", "goal": "送出返佣链接与折扣码", "draft": "<round 3 draft>"}}
    ],
    "objections": [
      {{"objection": "<objection 1>", "response": "<response 1>"}},
      {{"objection": "<objection 2>", "response": "<response 2>"}}
    ]
  }}
}}"""

    try:
        raw = run_ai_prompt(prompt, credential, max_tokens=700).strip()
        if "```" in raw:
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw.strip())
        if "dm_funnel" in parsed and "public_reply" in parsed:
            pub = parsed.get("public_reply") or {}
            hook = pub.get("inbound_hook", "")
            comment = pub.get("comment", "")
            false_dm_patterns = [
                r"\b(?:i\s+)?sent(?:\s+you)?\s+(?:a\s+)?(?:dm|pm|message)\b",
                r"\bcheck\s+your\s+(?:inbox|dm|dms|pms?)\b",
                r"\bdropped\s+you\s+a\s+(?:dm|pm|message)\b"
            ]
            for pat in false_dm_patterns:
                if re.search(pat, hook, re.IGNORECASE):
                    pub["inbound_hook"] = (
                        f"I benchmarked the pricing tiers and feature limits on a spreadsheet comparing {comp_disp} vs {prod_disp}. "
                        f"Feel free to shoot me a DM if you want me to share the breakdown."
                    )
                    break
                if re.search(pat, comment, re.IGNORECASE):
                    pub["comment"] = re.sub(pat, "Feel free to message me for the breakdown", comment, flags=re.IGNORECASE)
            parsed["affiliate_url"] = link_disp
            if "dm_funnel" in parsed:
                parsed["dm_funnel"]["affiliate_url"] = link_disp
                rounds = parsed["dm_funnel"].get("rounds", [])
                if len(rounds) >= 3 and link_disp not in rounds[2].get("draft", ""):
                    rounds[2]["draft"] += f" You can check it out here: {link_disp}"
            return parsed
        return fallback
    except Exception:
        return fallback


def generate_dm_pitch(
    title: str,
    excerpt: str,
    author: str,
    site_name: str = "My Product",
    site_url: str = "",
    pitch_instruction: str = "",
    platform: str = "reddit",
    credential: dict | None = None
) -> dict:
    """
    Generate an authentic, high-converting 1-on-1 private message (DM) outreach draft.
    Returns:
      {
        "subject": str,
        "message": str
      }
    """
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)

    prefix = "u/" if platform == "reddit" else "@"
    author_display = f"{prefix}{author}" if author else "there"

    if not credential:
        link_str = f" Kept the factory pinout chart and checklist bookmarked here if useful: {site_url}" if site_url else f" I pulled the diagram specs from the {site_name} library."
        return {
            "subject": f"Quick note regarding your {title[:35]} question",
            "message": f"Hey {author_display}, saw your post about '{title[:45]}'. Ran into the same thing recently and wanted to share what worked.{link_str} Hope it helps save some headache!"
        }

    prompt = f"""Write a concise, helpful technical follow-up note to a fellow community member ({author_display}) regarding their discussion on {platform.title()}.

Context:
They asked about:
Title: "{title[:200]}"
Details: "{excerpt[:300]}"

Goal:
Provide genuine peer-to-peer troubleshooting advice and share a helpful reference tool/checklist ({site_url or site_name}).

Tone & Style:
1. Subject line: Informative, relevant (under 8 words).
2. Message:
   - Friendly greeting to a fellow enthusiast.
   - 1-2 sentences of specific technical diagnosis/tips.
   - Mention {site_url or site_name} as a free open reference/calculator tool that helped with the exact same issue.
   - Keep it purely helpful, concise (under 80 words). No corporate or sales language.

Output format:
Subject: <subject line>
Message:
<message body>"""

    try:
        raw = run_ai_prompt(prompt, credential, max_tokens=250).strip()
        # Refusal guard
        lower_raw = raw.lower()
        if "sorry, i cannot" in lower_raw or "i am unable to" in lower_raw or "deceptive" in lower_raw:
            raise ValueError("Model triggered safety refusal")

        subject = f"Re: {title[:40]}"
        message = raw
        if "Subject:" in raw and "Message:" in raw:
            parts = raw.split("Message:", 1)
            sub_part = parts[0].replace("Subject:", "").strip()
            if sub_part:
                subject = sub_part
            message = parts[1].strip()
        return {"subject": subject, "message": message}
    except Exception:
        link_str = f" If you need to verify the pinouts or factory specs, the free reference tool on {site_name} ({site_url}) covers this exact setup." if site_url else f" The {site_name} library has the raw schematics if you need them."
        return {
            "subject": f"Quick wiring/chassis note on your {title[:30]}",
            "message": f"Hey {author_display}, saw your thread on '{title[:40]}'. Make sure to verify the serial and harness pins before doing any rewiring.{link_str} Hope it saves you some headache!"
        }



def generate_multichannel_reply(
    title: str,
    excerpt: str,
    subreddit: str,
    site_name: str = "My Product",
    site_url: str = "",
    site_desc: str = "",
    pitch_instruction: str = "",
    anti_ban_mode: str = "brand_search",
    funnel_tier: int = 3,
    credential: dict | None = None,
    platform: str = "reddit",
    visual_assets: list[dict] | None = None,
    preferred_channel: str | None = None,
    asset_id: str | None = None,
    persona: str | None = None,
    personas: list[dict] | None = None,
    stealth_mode: str = "direct_link"
) -> dict:
    """Generate multi-channel reply package (Reddit Markdown, Forum BBCode, Reddit OP First-Comment Sequencing, and 𝕏 Tweet)."""
    # 0. Resolve dynamic persona
    p_info = None
    if persona:
        if persona in AB_STYLES:
            p_info = AB_STYLES[persona]
        elif personas:
            p_info = next((p for p in personas if p.get("key") == persona), None)
        if not p_info and persona in PERSONAS:
            p_info = PERSONAS[persona]
    if not p_info:
        p_info = classify_persona(title, excerpt, subreddit, custom_personas=personas)

    # 1. Generate base domain reply text
    base_reply = generate_site_integrated_reply(
        title=title,
        excerpt=excerpt,
        subreddit=subreddit,
        site_name=site_name,
        site_url=site_url,
        site_desc=site_desc,
        pitch_instruction=pitch_instruction,
        anti_ban_mode=anti_ban_mode,
        funnel_tier=funnel_tier,
        credential=credential,
        platform=platform,
        visual_assets=None,
        persona=p_info["key"],
        personas=personas,
        stealth_mode=stealth_mode
    )

    # 2. Match optimal visual asset or use explicit asset_id
    matched_asset = match_visual_asset(title, excerpt, visual_assets, requested_asset_id=asset_id)

    # 3. Format channel package
    channels = format_multichannel_pack(
        base_reply=base_reply,
        title=title,
        excerpt=excerpt,
        site_name=site_name,
        site_url=site_url,
        anti_ban_mode=anti_ban_mode,
        matched_asset=matched_asset,
        stealth_mode=stealth_mode
    )

    # 4. Determine primary reply text
    is_x = (platform in ("x", "twitter"))
    is_forum = (platform in ("forum", "vbulletin", "phpbb", "xenforo"))
    if preferred_channel == "bbcode" or (is_forum and not preferred_channel):
        primary = channels["bbcode"]
    elif preferred_channel == "op_comment":
        primary = channels["op_comment"]
    elif preferred_channel == "reddit":
        primary = channels["reddit"]
    elif preferred_channel in ("x", "twitter") or is_x:
        primary = channels["x"]
    else:
        primary = channels["reddit"]

    return {
        "reply": primary,
        "platform": platform,
        "funnel_tier": funnel_tier,
        "persona": p_info["key"],
        "persona_label": p_info["label"],
        "matched_asset": matched_asset,
        "available_assets": visual_assets or [],
        "channels": channels
    }


def resolve_ai_cred(cfg: dict, credential_id: str | None) -> dict | None:
    if credential_id:
        c = next((c for c in cfg.get("credentials", []) if c.get("id") == credential_id), None)
        if c:
            return c
    # Fallback to any configured openai/anthropic/ollama credential in config
    for c in cfg.get("credentials", []):
        if c.get("type") in ("openai", "anthropic", "ollama") and c.get("api_key"):
            return c
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        return {"type": "anthropic", "api_key": key}
    return None


def generate_listener_profile(
    site_name: str,
    site_description: str,
    site_url: str = "",
    platform: str = "reddit",
    credential: dict | None = None
) -> dict:
    """Use AI to automatically synthesize optimal listener profile (keywords, subreddits, filters, negative kws, pitch) for ANY new product."""
    import json
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)
    if not credential:
        raise ValueError("No AI credential configured in Vault")

    is_x = (platform in ("x", "twitter"))
    if is_x:
        platform_rules = """PLATFORM: 𝕏 (Twitter) - Global Unbounded Firehose
MANDATORY RULES FOR 𝕏:
1. Every single keyword MUST be a compound, domain-anchored phrase (2-4 words) that tightly bounds search around real practitioner problems, troubleshooting, or buyer intent (e.g. 'tiktok agency account', 'tiktok ad spend limit', 'ad account suspended', 'events api deduplication').
2. STRICTLY FORBIDDEN WORDS: NEVER output 'buy', 'coupon', 'promo code', 'voucher', 'free', 'discount', 'signup bonus', or isolated single generic words (e.g. 'tiktok', 'ads', 'marketing'). On 𝕏, these are dominated 99.9% by black-hat account sellers and spam bots.
3. Negative keywords: 14-25 vertical-specific negative exclusion keywords to eliminate noise. MUST include 𝕏 bot signatures ('whatsapp', 'dm me', 'inbox me', 'pva accounts', 'aged accounts', 'instant delivery', 'hire me', 'service available', 'giveaway', 'followers', 'likes', 'crypto', 'airdrop', 'solana', 'telegram bot', 't.me/', 'wa.me/').
4. Filter prompt: Formulate an executive commercial-intent gatekeeper. Reply YES only if the tweet indicates an active commercial problem, setup blocker, or purchasing intent; Reply NO to crypto shills, personal videos, entertainment, memes, or bot retweets.
5. Pitch instruction: MUST be under 180 characters total. Give a sharp 1.5-sentence technical diagnosis first; casually mention benchmark checklist is pinned on bio; strictly lowercase, peer-to-peer, NO direct links, NO dollar promises ($500 match), NO promo codes."""
    else:
        platform_rules = """PLATFORM: Reddit - Community-Partitioned Subreddits
MANDATORY RULES FOR REDDIT:
1. Subreddits: Recommend 4-8 high-affinity, active, PRACTITIONER & BUYER Subreddits where operators and decision-makers gather (lowercase, space-separated string, NO r/ prefix). Strictly avoid general meme, teen, or entertainment subs (e.g. for ads/ecommerce recommend 'tiktokads ppc adops dropship ecommerce shopify', NEVER 'tiktok' or 'funny').
2. Keywords (High-Intent Compound Phrases):
   - Every keyword MUST be a compound 2-4 word phrase representing active commercial intent, buyer pain points, or technical roadblocks (e.g. 'tiktok agency account', 'ad spend limit', 'account suspended', 'billing error', 'spend match', 'how to scale ads', 'agency account vs personal').
   - Categorize across: problem/troubleshooting phrases, purchasing/solution phrases, and setup/compliance phrases.
   - NEVER output single generic words (e.g. NEVER 'tiktok', 'ads', 'marketing', 'shopify', 'golf', 'vpn').
3. Negative Keywords: 12-20 negative exclusion keywords to proactively kill noise (e.g., creator fund, dance, viral trend, free views, telegram bot, crypto, dropship course, hiring, resume, follower bot).
4. Filter Prompt (Buyer Intent Gatekeeper):
   Formulate a strict, high-converting gatekeeper prompt:
   'Does this post indicate the author is actively facing a real commercial problem, technical roadblock, or purchasing dilemma that {site_name} can address? Reply YES if the author is seeking solutions, troubleshooting, comparing options, or looking to buy/scale. Reply NO if it is generic news, creator/consumer complaints, entertainment, job seeking, competitor promo, or low-effort chatter.'
5. Pitch Instruction (RedSignal Anti-Ban Conversion Protocol):
   Formulate a 2-3 sentence instruction for the reply drafter:
   - Provide 90% objective technical diagnosis or root cause explanation first.
   - Mention {site_name} strictly in the 3rd person as an objective reference guide, diagnostic database, or verified industry route.
   - Strictly FORBID first-person selling ('we offer', 'contact us', 'our agency'), FORBID raw dollar incentive amounts (e.g. '$500 match', '$6000 credit', '50% off'), and FORBID coupon codes or aggressive sales pitches."""

    prompt = f"""You are a senior growth marketing engineer, social listening architect, and anti-ban conversion expert.
Analyze the following product and generate a high-converting, noise-resistant, production-ready social monitoring listener profile.

Product/Brand Name: {site_name}
What it does & core value: {site_description}
Product URL: {site_url or "https://example.com"}

{platform_rules}

Respond with ONLY a valid, parseable JSON object matching this exact schema:
{{
  "name": "Concise listener name (e.g. '{site_name} {'𝕏 Radar' if is_x else 'Reddit Radar'}')",
  "subreddits": "{'empty string for X' if is_x else 'space separated subreddits without r/, e.g. sub1 sub2 sub3'}",
  "keywords": ["14-20 high-intent 2-4 word compound phrases adhering strictly to the platform rules above"],
  "negative_keywords": ["12-20 vertical-specific negative exclusion keywords"],
  "filter_prompt": "Strict buyer-intent gatekeeper prompt tailored to {site_name} that replies YES ONLY for commercial/technical intent and NO for consumer/creator noise",
  "pitch_instruction": "Strict anti-ban value-first stealth conversion instruction tailored to {site_name} (90% diagnosis, 3rd person reference, NO dollar promises, NO promo codes)",
  "personas": [
    {{
      "key": "tech_expert",
      "label": "Emoji + 4-6 char Chinese role name",
      "name": "English Professional Title",
      "tone": "2-3 sentences of persona tone, diagnostic mindset, and troubleshooting jargon",
      "match_keywords": ["8-12 domain trigger keywords in English"]
    }}
  ]
}}"""

    raw = run_ai_prompt(prompt, credential, max_tokens=1200).strip()
    if "```" in raw:
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    parsed = {}
    if m:
        try:
            parsed = json.loads(m.group(0))
        except Exception:
            try:
                parsed = json.loads(raw)
            except Exception:
                pass
    if not parsed:
        parsed = json.loads(raw)

    # Post-process & Harden Buyer-Intent Gatekeeper
    filter_p = parsed.get("filter_prompt", "").strip()
    if not filter_p or "directly relevant to" in filter_p.lower():
        parsed["filter_prompt"] = (
            f"Does this post indicate the author is actively facing a real commercial problem, technical roadblock, "
            f"or purchasing dilemma that {site_name} solves (such as troubleshooting, setup, scaling, or product selection)? "
            f"Reply YES if relevant to engage or solve a problem, Reply NO if generic news, entertainment, job seeking, consumer complaint, or spam."
        )
    else:
        parsed["filter_prompt"] = filter_p

    # Post-process & Harden Pitch Instruction with Anti-Ban Guardrails
    pitch_p = parsed.get("pitch_instruction", "").strip()
    if is_x:
        if len(pitch_p) > 200 or "bio" not in pitch_p.lower():
            parsed["pitch_instruction"] = (
                f"Give a sharp 1.5-sentence technical diagnosis first. "
                f"Casually mention the {site_name} checklist is pinned on bio. "
                f"Strictly lowercase, under 180 chars, zero sales jargon."
            )
        else:
            parsed["pitch_instruction"] = pitch_p
    else:
        anti_ban_guard = (
            "Provide genuine technical diagnosis first. Mention the resource strictly in the 3rd person as an objective reference or database. "
            "Never sound like a salesperson, and never mention raw promo dollar amounts or discount codes."
        )
        if not pitch_p:
            parsed["pitch_instruction"] = anti_ban_guard
        elif "salesperson" not in pitch_p.lower() and "dollar" not in pitch_p.lower() and "anti-ban" not in pitch_p.lower():
            parsed["pitch_instruction"] = f"{pitch_p} {anti_ban_guard}"
        else:
            parsed["pitch_instruction"] = pitch_p

    # Filter out single-word or forbidden keywords
    forbidden_x_words = ("buy ", "buy_", "coupon", "promo code", "voucher", "discount", "free ", "signup bonus")
    cleaned_kws = []
    for kw in parsed.get("keywords", []):
        k = str(kw).strip()
        if not k:
            continue
        if is_x and any(fw in k.lower() for fw in forbidden_x_words):
            continue
        cleaned_kws.append(k)
    parsed["keywords"] = cleaned_kws

    # Platform-specific negative keyword guarantees
    if is_x:
        x_bot_negatives = [
            "whatsapp", "dm me", "inbox me", "pva accounts", "aged accounts available",
            "instant delivery", "hire me", "service available", "giveaway", "followers",
            "likes", "crypto", "airdrop", "solana", "telegram bot", "t.me/", "wa.me/"
        ]
        curr_negs = parsed.get("negative_keywords", [])
        curr_negs_lower = {n.lower() for n in curr_negs}
        for x_neg in x_bot_negatives:
            if x_neg.lower() not in curr_negs_lower:
                curr_negs.append(x_neg)
        parsed["negative_keywords"] = curr_negs

    if not parsed.get("name"):
        parsed["name"] = f"{site_name} {'𝕏 Radar' if is_x else 'Reddit Radar'}"

    return parsed


def generate_project_personas(
    site_name: str,
    site_description: str,
    keywords: list[str] | None = None,
    pitch_instruction: str = "",
    subreddits: str = "",
    credential: dict | None = None
) -> list[dict]:
    """
    Synthesize 3-4 specialized, authentic community expert personas for ANY new project/vertical.
    Each persona represents a distinct archetype (e.g. Hands-on Technician, Hardware Hacker/Modder,
    Seasoned Community Veteran, Compliance/Buyer Guide Specialist).
    """
    import json
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)
    if not credential:
        raise ValueError("No AI credential configured in Vault")

    kw_summary = ", ".join(keywords[:15]) if keywords else "general niche terms"
    prompt = f"""You are a community growth strategist and social listening domain architect.
We are configuring our intelligent reply system for a new project/product:

Project/Brand Name: {site_name}
What it does & core value: {site_description}
Target Subreddits / Communities: {subreddits or "relevant niche subreddits"}
Core Intent Keywords: {kw_summary}
Pitch Instruction: {pitch_instruction or "Casually introduce the tool where relevant without hard selling"}

TASK:
Design 3 to 4 distinct, complementary community member personas (Domain Metapersonas) tailored specifically to this project's vertical.
These personas will be dynamically adopted by our AI when replying to real community posts.

The personas should cover 3-4 classic, authentic community archetypes:
1. Technical/Hands-on Specialist (troubleshoots root causes, mechanics, schematics, error codes, implementation details)
2. Power User / Modder / Performance Optimizer (passionate about advanced tuning, optimization, setups, hacks)
3. Everyday Community Regular / Experienced User (friendly peer sharing practical tips, daily workflows, best practices)
4. Evaluator / Benchmark / Buyer / Regulatory Specialist (expert in comparisons, standards, buying decisions, compliance)

Respond with ONLY a valid, parseable JSON array of objects. Schema for each object:
[
  {{
    "key": "short_snake_case_key (e.g. tech_guru, modder, veteran, advisor)",
    "label": "Distinctive Emoji + 4-6 char Chinese role name (e.g. '☕ 萃取调参老饕', '🔧 驻厂老技师', '⚡ 极客改装先锋', '📊 SaaS架构先锋', '🐕 训犬实战专家')",
    "name": "English Professional Title (e.g. 'Senior Specialty Barista & Dialing Guru')",
    "tone": "2-3 sentences of persona guidance: voice, diagnostic mindset, jargon to use, and authentic peer-to-peer tone.",
    "match_keywords": ["8-15 specific English keywords that indicate this persona should be triggered when seen in a Reddit post title or text"]
  }}
]
"""
    raw = run_ai_prompt(prompt, credential, max_tokens=1000)
    m = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return json.loads(raw)


AFFILIATE_INTENT_CLUSTERS = {
    "alternative": {
        "label": "替代弃用 (Switching/Churn)",
        "badge": "🔥 替代截流",
        "keywords": [
            "alternative", "alternatives", "switch from", "switching from", "cancel",
            "replace", "replacement for", "too expensive", "price hike", "pricing change",
            "price increase", "cheaper alternative", "budget alternative", "substitute",
            "account banned", "account suspended", "spend limit", "daily limit", "banned on tiktok",
            "换梯子", "换机场", "换vpn", "替代品", "平替", "太贵了", "涨价", "弃用", "限额", "封号", "被封"
        ]
    },
    "compare": {
        "label": "选型对比 (Comparison Dilemma)",
        "badge": "⚖️ 对比选型",
        "keywords": [
            "vs", "versus", "compare", "comparison", "better than", "difference between",
            "which one", "which should i get", "which is better", "a or b", "either",
            "哪个好", "选型", "对比", "选哪个", "评测", "测评", "哪个梯子"
        ]
    },
    "review": {
        "label": "真实口碑 (Authentic Review/Validation)",
        "badge": "⭐ 真实口碑",
        "keywords": [
            "is it worth it", "worth the money", "worth buying", "honest review",
            "anyone tried", "legit", "is it legit", "scam or legit", "pros and cons",
            "after 1 year", "real experience", "feedback on", "thoughts on",
            "怎么样", "好用吗", "真实评价", "靠谱吗", "稳不稳", "会跑路吗"
        ]
    },
    "deal": {
        "label": "折扣与求购 (Deal/Last-Mile Intent)",
        "badge": "🏷️ 折扣防线",
        "keywords": [
            "discount", "promo code", "coupon", "deal", "lifetime deal", "ltd",
            "free trial", "cheapest way to", "promo", "voucher", "affiliate discount",
            "ad credit", "ad credits", "agency account", "agency accounts", "agency ad account",
            "spend match", "ad rebate", "cashback", "threshold account", "aged account",
            "ad spend match", "account provider", "monthly invoicing", "credit line", "line of credit",
            "求梯子", "求vpn", "求推荐梯子", "求推荐vpn", "梯子推荐", "vpn推荐", "机场推荐", "求机场",
            "优惠码", "折扣码", "优惠券", "便宜梯子", "便宜vpn", "买什么梯子",
            "返佣", "返点", "赠金", "广告赠金", "代理户", "海外户", "开户", "开企业户"
        ]
    },
    "troubleshoot": {
        "label": "急迫痛点 (Pain/Troubleshooting)",
        "badge": "🛠️ 痛点排查",
        "keywords": [
            "how to", "troubleshoot", "why is", "won't", "wont", "not working",
            "broken", "error", "failed", "fix", "issue with", "buggy", "frustrated with",
            "billing error", "payment failed", "voucher not applying", "credit not showing", "disapproved",
            "被墙了", "连不上", "断流", "无法访问", "ip被封", "节点超时", "进不去", "绑卡失败", "充值失败"
        ]
    }
}


def detect_affiliate_intent(title: str = "", text: str = "", created_at: float | str | None = None) -> dict:
    """
    Detect specific commercial affiliate conversion intents (alternative, compare, review, deal, troubleshoot),
    and compute a multidimensional Buying Intent Score (0-100) based on commercial urgency, transactional vocabulary,
    and recency decay (inspired by subscope / signalscout).
    """
    import time
    t = str(title or "")
    c = str(text or "")
    content = f"{t} {c}".lower()

    detected_key = "general"
    detected_meta = {
        "label": "通用探讨 (General Intent)",
        "badge": "💬 通用讨论",
        "matched": []
    }

    for intent_key, meta in AFFILIATE_INTENT_CLUSTERS.items():
        matched = []
        for k in meta["keywords"]:
            k_clean = str(k).lower().strip()
            if not k_clean:
                continue
            is_cjk = any('一' <= char <= '鿿' for char in k_clean)
            if " " in k_clean or is_cjk:
                if k_clean in content:
                    matched.append(k_clean)
            else:
                if re.search(r"\b" + re.escape(k_clean) + r"\b", content):
                    matched.append(k_clean)
        if matched:
            detected_key = intent_key
            detected_meta = {
                "label": meta["label"],
                "badge": meta["badge"],
                "matched": matched
            }
            break

    # 1. Base Score from Archetype
    base_scores = {
        "deal": 92,
        "alternative": 88,
        "compare": 84,
        "troubleshoot": 80,
        "review": 75,
        "general": 45
    }
    score = base_scores.get(detected_key, 45)

    # 2. Transactional & Action Modifiers
    urgency_signals = ["urgent", "asap", "today", "recommend", "which one", "looking for", "求", "急", "推荐", "求个", "求大佬", "立马", "哪家"]
    if any(sig in content for sig in urgency_signals):
        score += 6

    pricing_signals = ["price", "cost", "budget", "cheap", "expensive", "pay", "buy", "dollar", "$", "多少钱", "价格", "预算", "买", "买什么", "便宜"]
    if any(sig in content for sig in pricing_signals):
        score += 5

    cjk_high_intent = [
        "求梯子", "求vpn", "梯子推荐", "vpn推荐", "换梯子", "被墙了", "机场推荐", "求机场",
        "求开户", "代理户", "开户推荐", "广告返点", "广告赠金", "广告返佣"
    ]
    if any(sig in content for sig in cjk_high_intent):
        score += 8

    # 3. Recency Decay (if timestamp provided)
    if created_at is not None:
        try:
            now = time.time()
            if isinstance(created_at, (int, float)):
                post_ts = float(created_at)
            else:
                import datetime as _dt
                post_ts = _dt.datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).timestamp()
            age_hours = max(0.0, (now - post_ts) / 3600.0)
            if age_hours <= 2:
                score += 5
            elif age_hours > 24:
                score -= 10
            elif age_hours > 72:
                score -= 20
        except Exception:
            pass

    score = max(10, min(99, score))

    if score >= 90:
        urgency_level = "🔥 极速转化 (Critical)"
    elif score >= 80:
        urgency_level = "⚡ 优先跟进 (High)"
    elif score >= 65:
        urgency_level = "⚖️ 标准线索 (Medium)"
    else:
        urgency_level = "💬 观望蓄水 (Normal)"

    return {
        "intent": detected_key,
        "label": detected_meta["label"],
        "badge": detected_meta["badge"],
        "matched": detected_meta["matched"],
        "buying_score": score,
        "urgency_level": urgency_level
    }


def calculate_opportunity_score(
    title: str,
    text: str = "",
    ts: float | None = None,
    funnel_tier: int = 3,
    listener_keywords: list[str] | None = None,
    visual_assets: list[dict] | None = None
) -> dict:
    """
    Barnacle SEO Opportunity Priority Scoring (0-100).
    Evaluates:
    1. Recency & Velocity (Barnacle first-mover advantage for comments)
    2. Search Intent & Commercial Long-tail Keywords (Adaptive to ANY domain + listener keywords)
    3. Funnel Tier & Problem Urgency
    4. Quality & Context depth
    """
    import time
    score = 0
    breakdown: dict = {}
    content = f"{title} {text}".lower()

    # 1. Recency / Barnacle Velocity (0 - 35 pts)
    now = time.time()
    post_ts = ts or now
    age_seconds = max(0, now - post_ts)
    age_minutes = age_seconds / 60

    if age_minutes <= 30:
        recency_pts = 35  # Golden window: grab 1st comment for maximum organic visibility
    elif age_minutes <= 120:
        recency_pts = 25  # Fresh (< 2h)
    elif age_minutes <= 360:
        recency_pts = 16  # Active (< 6h)
    elif age_minutes <= 1440:
        recency_pts = 8   # Within 24h
    else:
        recency_pts = 2   # Cold post (> 24h)
    score += recency_pts
    breakdown["recency"] = recency_pts

    # 2. High-Commercial & SEO Intent Keywords (0 - 35 pts)
    intent_pts = 0
    aff_intent = detect_affiliate_intent(title, text)
    breakdown["affiliate_intent"] = aff_intent
    if aff_intent["intent"] in ("alternative", "compare", "deal", "review"):
        intent_pts += 8
    # Universal commercial intent & troubleshooting modifiers
    universal_intent_kws = [
        "vs", "versus", "better than", "difference between",
        "how to", "troubleshoot", "why is", "won't", "wont", "not working",
        "recommend", "which should", "best", "alternative", "review",
        "broken", "error", "failed", "fix", "issue with",
        "guide", "diagram", "schematic", "pinout", "wiring",
        "lookup", "decoder", "calculator", "checklist", "spec",
        "buy", "cost", "price", "worth it", "upgrade", "conversion",
        "law", "legal", "compliance", "inspection", "replacement",
        "agency account", "ad credit", "ad credits", "spend match", "rebate",
        "promo code", "voucher", "account provider", "banned", "spend limit"
    ]
    # Dynamically merge with listener's domain keywords and visual asset triggers
    active_kws = list(universal_intent_kws)
    if listener_keywords:
        for lk in listener_keywords:
            lk_clean = str(lk).lower().strip()
            if lk_clean and lk_clean not in active_kws:
                active_kws.append(lk_clean)
    if visual_assets:
        for va in visual_assets:
            for vk in (va.get("intent_keywords") or []):
                vk_clean = str(vk).lower().strip()
                if vk_clean and vk_clean not in active_kws:
                    active_kws.append(vk_clean)

    matched_kws = [kw for kw in active_kws if kw in content]
    if len(matched_kws) >= 3:
        intent_pts += 25
    elif len(matched_kws) >= 2:
        intent_pts += 18
    elif len(matched_kws) == 1:
        intent_pts += 10

    if "?" in title:
        intent_pts += 10
    intent_pts = min(35, intent_pts)
    score += intent_pts
    breakdown["intent"] = intent_pts
    breakdown["matched_keywords"] = matched_kws[:5]

    # 3. Funnel Tier Points (0 - 25 pts)
    if funnel_tier == 1:
        tier_pts = 25
    elif funnel_tier == 2:
        tier_pts = 18
    else:
        tier_pts = 10
    score += tier_pts
    breakdown["tier"] = tier_pts

    # 4. Content Quality & Context Depth (-10 to +5 pts)
    length = len(title) + len(text)
    if length > 120:
        quality_pts = 5
    elif length < 30:
        quality_pts = -10
    else:
        quality_pts = 0
    score += quality_pts
    breakdown["quality"] = quality_pts

    final_score = max(5, min(100, score))

    if final_score >= 80:
        priority = "P1_GOLDEN"
        label = "🔥 黄金高潜"
    elif final_score >= 65:
        priority = "P2_HIGH"
        label = "✨ 高价值"
    elif final_score >= 45:
        priority = "P3_STANDARD"
        label = "🎯 常规"
    else:
        priority = "P4_LOW"
        label = "💤 低潜"

    return {
        "score": final_score,
        "priority": priority,
        "label": label,
        "breakdown": breakdown
    }


def generate_project_visual_assets(
    site_name: str,
    site_description: str,
    site_url: str = "",
    keywords: list[str] | None = None,
    credential: dict | None = None
) -> list[dict]:
    """
    Synthesize 3-4 authoritative technical infographics/matrices/fitment charts
    specifically tailored to the target domain/product to drive high-intent community citations.
    """
    import json
    if not credential:
        from config import load_config
        cfg = load_config()
        credential = resolve_ai_cred(cfg, None)
    if not credential:
        raise ValueError("No AI credential configured in Vault")

    kw_str = ", ".join(keywords[:15]) if keywords else "technical specs, troubleshooting, buying guide"
    target_link = site_url or "https://example.com/tools"

    prompt = f"""You are a technical content strategist and community growth architect.
Analyze the following product/brand and plan 3 to 4 authoritative, high-value technical infographic/reference chart assets.

Product/Brand: {site_name}
Value Proposition: {site_description}
Keywords: {kw_str}
Target Tool/Resource Link: {target_link}

Goal: In online forums (Reddit, specialized forums), community members eagerly share and bookmark high-value reference sheets, wiring schematics, comparison matrices, statutory compliance tables, and diagnostic lookup charts.
Design 3 to 4 distinct visual assets covering:
1. Technical Diagnostic / Troubleshooting / Wiring / Teardown Schematic
2. Comprehensive Fitment / Model Compatibility / Sizing / Calculation Matrix
3. Selection / Feature Comparison / Standards Compliance Benchmark Spec Sheet

Respond with ONLY a valid, parseable JSON array of 3 to 4 objects matching this exact schema:
[
  {{
    "id": "kebab-case-unique-id (e.g. va-pressure-tuning)",
    "name": "Professional Chart/Spec Title",
    "image_url": "{target_link}/assets/diagram-name.webp",
    "target_url": "{target_link}",
    "caption": "One clear sentence describing what technical reference data this chart provides.",
    "citation_source": "Authoritative sounding source (e.g. Source: {site_name} Technical Database & Benchmark Standard)",
    "intent_keywords": ["10-15 specific English keywords that would trigger someone needing this specific visual chart"]
  }}
]"""

    raw = run_ai_prompt(prompt, credential, max_tokens=1000)
    m = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return json.loads(raw)


def extract_metadata_from_url(url: str) -> dict:
    """Fetch URL and extract rich meta title, description, headings, and core value for zero-touch listener ingestion."""
    import html as html_lib
    import urllib.request
    from urllib.parse import urlparse

    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url
    domain = urlparse(clean_url).netloc.replace("www.", "")
    brand_guess = domain.split(".")[0].title() if domain else "Product"

    raw_html = ""
    fetch_error = None

    # 1. Try curl_cffi with chrome131 impersonation for TLS fingerprint & anti-bot bypass
    try:
        from curl_cffi import requests as cffi_requests
        try:
            resp = cffi_requests.get(
                clean_url,
                impersonate="chrome131",
                timeout=12,
                headers={"Accept-Language": "en-US,en;q=0.9"}
            )
            if resp.status_code == 200:
                raw_html = resp.text
            elif resp.status_code in (301, 302, 307, 308) and resp.headers.get("Location"):
                resp = cffi_requests.get(
                    resp.headers["Location"],
                    impersonate="chrome131",
                    timeout=12
                )
                if resp.status_code == 200:
                    raw_html = resp.text
        except Exception as e_ssl:
            # Retry with verify=False if SSL certificate validation failed (e.g. edge CDN / cert mismatch)
            try:
                resp = cffi_requests.get(
                    clean_url,
                    impersonate="chrome131",
                    verify=False,
                    timeout=12
                )
                if resp.status_code == 200:
                    raw_html = resp.text
            except Exception as e_ssl_inner:
                fetch_error = str(e_ssl_inner)
    except Exception as e_import:
        fetch_error = str(e_import)

    # 2. Fallback to urllib.request if curl_cffi was unable to retrieve HTML
    if not raw_html:
        try:
            req = urllib.request.Request(
                clean_url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                raw_html = r.read().decode("utf-8", errors="ignore")
            fetch_error = None
        except Exception as exc:
            if not fetch_error:
                fetch_error = str(exc)

    title = ""
    desc = ""
    h1_list = []
    h2_list = []
    site_name_og = ""

    if raw_html:
        # Title
        title_m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.I | re.S)
        if title_m:
            title = html_lib.unescape(title_m.group(1).strip())

        # Site Name (og:site_name)
        site_name_m = re.search(r"<meta[^>]*property=[\"']og:site_name[\"'][^>]*content=[\"'](.*?)[\"']", raw_html, re.I | re.S)
        if site_name_m:
            site_name_og = html_lib.unescape(site_name_m.group(1).strip())

        # Description
        desc_m = re.search(r"<meta[^>]*name=[\"']description[\"'][^>]*content=[\"'](.*?)[\"']", raw_html, re.I | re.S)
        if not desc_m:
            desc_m = re.search(r"<meta[^>]*property=[\"']og:description[\"'][^>]*content=[\"'](.*?)[\"']", raw_html, re.I | re.S)
        if not desc_m:
            desc_m = re.search(r"<meta[^>]*name=[\"']twitter:description[\"'][^>]*content=[\"'](.*?)[\"']", raw_html, re.I | re.S)
        if desc_m:
            desc = html_lib.unescape(desc_m.group(1).strip())

        # Headings (H1 and H2)
        h1s = re.findall(r"<h1[^>]*>(.*?)</h1>", raw_html, re.I | re.S)
        for h in h1s[:3]:
            cleaned_h = html_lib.unescape(re.sub(r"<[^>]+>", " ", h)).strip()
            cleaned_h = re.sub(r"\s+", " ", cleaned_h)
            if cleaned_h and len(cleaned_h) > 3 and cleaned_h not in h1_list:
                h1_list.append(cleaned_h)

        h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", raw_html, re.I | re.S)
        for h in h2s[:4]:
            cleaned_h = html_lib.unescape(re.sub(r"<[^>]+>", " ", h)).strip()
            cleaned_h = re.sub(r"\s+", " ", cleaned_h)
            if cleaned_h and len(cleaned_h) > 3 and cleaned_h not in h2_list:
                h2_list.append(cleaned_h)

        # Extract main body text snippet (excluding scripts/styles/nav/footers)
        body_m = re.search(r"<body[^>]*>(.*?)</body>", raw_html, re.I | re.S)
        body_content = body_m.group(1) if body_m else raw_html
        clean_body = re.sub(r"<(script|style|svg|noscript|nav|header|footer)[^>]*>.*?</\1>", " ", body_content, flags=re.I | re.S)
        clean_body = re.sub(r"<[^>]+>", " ", clean_body)
        clean_body = html_lib.unescape(re.sub(r"\s+", " ", clean_body)).strip()
        body_snippet = clean_body[:400] if clean_body else ""
    else:
        body_snippet = ""

    brand_final = site_name_og or brand_guess

    # Synthesize rich description if meta description is missing or too short
    desc_parts = []
    if desc:
        desc_parts.append(desc)
    if h1_list:
        desc_parts.append(". ".join(h1_list))
    if h2_list and len(desc_parts) < 2:
        desc_parts.append("; ".join(h2_list[:2]))
    if not desc and body_snippet:
        desc_parts.append(body_snippet[:250])

    combined_desc = " | ".join(desc_parts) if desc_parts else (title or brand_final)

    res = {
        "url": clean_url,
        "domain": domain,
        "brand_name": brand_final,
        "page_title": title,
        "description": combined_desc,
        "headings": h1_list + h2_list,
        "sample_content": body_snippet
    }
    if fetch_error and not raw_html:
        res["error"] = fetch_error
    return res


def evaluate_reply_safety(
    reply_text: str,
    title: str = "",
    excerpt: str = "",
    platform: str = "reddit",
    site_name: str = "Product",
    site_url: str = "",
    credential: dict | None = None
) -> dict:
    """
    LLM-as-a-Judge Pre-Flight Safety Gatekeeper.
    Audits reply text across:
    1. Organic Community Tone (1-10)
    2. Anti-Ban Safety & Link Discretion (1-10)
    3. Technical Domain Value (1-10)
    """
    import json
    if not reply_text or not reply_text.strip():
        return {
            "verdict": "FLAGGED",
            "safety_score": 1,
            "dimensions": {"organic_tone": 1, "anti_ban_safety": 1, "technical_value": 1},
            "reason": "Reply text is empty"
        }

    # If AI credential is provided, perform deep LLM-as-a-Judge pre-flight audit
    if credential:
        prompt = f"""You are an elite, strict Reddit/Community Moderator and Anti-Spam Auditor.
Your job is to perform a pre-flight safety audit on an automated draft reply before it is published to enthusiast communities.
Your goal is to PROTECT the poster's account from bans, shadowbans, moderator removals, and downvotes.

ORIGINAL POST TITLE: {title}
ORIGINAL POST CONTEXT: {excerpt[:400]}
TARGET BRAND / SITE TO PROTECT: {site_name} ({site_url})
PLATFORM: {platform}

DRAFT REPLY TO AUDIT:
\"\"\"
{reply_text}
\"\"\"

CRITICAL AUDITING DIMENSIONS (Score each 1 to 10):
1. organic_tone (1-10): Does this sound like an authentic, seasoned peer/mechanic sharing genuine knowledge? Deduct points for corporate speak, marketing hype, or robotic AI phrasing ("Look no further", "Hope this helps!", "In conclusion", "As an AI").
2. anti_ban_safety (1-10): Is the brand/tool reference strictly contextual, subtle, and natural? Deduct heavily if it reads like unsolicited self-promotion, affiliate spam, marketing pushiness, or link-dropping without earning trust first.
3. technical_value (1-10): Does the reply directly answer the OP's specific question or problem with actionable domain knowledge BEFORE any resource is referenced?

SAFETY GATE PASS CRITERIA:
- PASSED: anti_ban_safety >= 7 AND organic_tone >= 6 AND average score >= 7.0. Zero aggressive marketing cues.
- FLAGGED: If it appears promotional, spammy, or likely to trigger AutoMod/moderator ban or community backlash.

Respond with ONLY a JSON object:
{{
  "verdict": "PASSED" or "FLAGGED",
  "safety_score": 8,
  "dimensions": {{
    "organic_tone": 8,
    "anti_ban_safety": 8,
    "technical_value": 9
  }},
  "reason": "1-2 sentence concise explanation of findings in Chinese"
}}"""
        try:
            raw = run_ai_prompt(prompt, credential, max_tokens=350)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                res = json.loads(m.group(0))
                verdict = str(res.get("verdict", "FLAGGED")).upper()
                score = int(res.get("safety_score", 6))
                dims = res.get("dimensions", {})
                anti_ban = int(dims.get("anti_ban_safety", score))
                tone = int(dims.get("organic_tone", score))
                if anti_ban >= 7 and tone >= 6 and score >= 7:
                    verdict = "PASSED"
                else:
                    verdict = "FLAGGED"
                return {
                    "verdict": verdict,
                    "safety_score": score,
                    "dimensions": dims,
                    "reason": res.get("reason", "AI 预审员已完成三维独立安全评估")
                }
        except Exception:
            pass

    # Fallback heuristic rule engine (Zero-LLM instant audit)
    lower_text = reply_text.lower()
    spam_phrases = [
        "buy now", "check out our", "visit our website", "great prices", "affiliate",
        "discount code", "special deal", "click here", "cheap", "order now",
        "limited time offer", "check out my site", "best prices in town", "store link"
    ]
    found_spam = [p for p in spam_phrases if p in lower_text]
    if found_spam:
        return {
            "verdict": "FLAGGED",
            "safety_score": 4,
            "dimensions": {"organic_tone": 4, "anti_ban_safety": 3, "technical_value": 6},
            "reason": f"命中高危推广禁词: {', '.join(found_spam)}"
        }

    # Check for excessive URLs
    url_count = len(re.findall(r"https?://", reply_text))
    if url_count > 2:
        return {
            "verdict": "FLAGGED",
            "safety_score": 5,
            "dimensions": {"organic_tone": 5, "anti_ban_safety": 4, "technical_value": 7},
            "reason": f"外链密度过高 ({url_count}处链接)，易触发 Reddit AutoMod 拦截"
        }

    return {
        "verdict": "PASSED",
        "safety_score": 8,
        "dimensions": {"organic_tone": 8, "anti_ban_safety": 8, "technical_value": 8},
        "reason": "通过规则审查：无高危推销术语，语气自然且外链引用合规"
    }



