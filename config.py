from __future__ import annotations

import json
import uuid as _uuid_mod
from pathlib import Path

from db import db_log, get_db, get_setting, safe_col

DEFAULT_FAIRWAYFORT_ASSETS = [
    {
        "id": "va-state-matrix",
        "name": "50-State Street-Legal Compliance Matrix",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/50-state-golf-cart-street-legal-matrix.webp",
        "target_url": "https://fairwayfort.com/pages/tools",
        "intent_keywords": ["state", "law", "legal", "dmv", "street", "fl", "florida", "ca", "california", "tx", "texas", "sc", "nc", "az", "arizona", "ga", "georgia", "speed", "road", "public", "highway", "title", "plate", "registration"],
        "citation_source": "Source: NHTSA 49 CFR § 571.500 & State DOT Statutory Frameworks (Fairway Fort Dataset)",
        "caption": "Complete 50-State Golf Cart vs. Low-Speed Vehicle (LSV) Equipment & Speed Limit Matrix."
    },
    {
        "id": "va-vin-decoder",
        "name": "Golf Cart / LSV VIN & Serial Decoder Chart",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/golf-cart-serial-number-location-guide.webp",
        "target_url": "https://fairwayfort.com/pages/tools",
        "intent_keywords": ["vin", "serial", "year", "model", "identify", "find", "decoder", "chassis", "club car", "ezgo", "yamaha", "icon", "precedent", "ds", "txt", "rxv", "drive", "g29"],
        "citation_source": "Source: Manufacturer Technical Service Bulletins & Fairway Fort Lookup System",
        "caption": "OEM Serial & 17-digit VIN Placement & Model Year Cross-Reference Chart."
    },
    {
        "id": "va-windshield-spec",
        "name": "FMVSS 205 Windshield & Safety Equipment Spec Sheet",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/dot-approved-windshield-compliance-specs.webp",
        "target_url": "https://fairwayfort.com/pages/tools",
        "intent_keywords": ["windshield", "dot", "as4", "as5", "acrylic", "glass", "polycarbonate", "wiper", "fold down", "split windshield", "tinted"],
        "citation_source": "Source: DOT FMVSS 205 / ANSI Z26.1 Compliance Standard",
        "caption": "AS4/AS5 Certified Windshield vs Acrylic Fold-Down Street Compliance Comparison."
    },
    {
        "id": "va-battery-conversion",
        "name": "36V to 48V Lithium Conversion & Wiring Schematic",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/golf-cart-36v-48v-lithium-conversion-wiring.webp",
        "target_url": "https://fairwayfort.com/pages/tools",
        "intent_keywords": ["battery", "lithium", "lifepo4", "36v", "48v", "voltage", "charge", "charger", "solenoid", "convert", "conversion", "trojan", "lead acid", "bms", "wire", "wiring", "series", "parallel", "amp", "ah"],
        "citation_source": "Source: SAE J1798 Battery Safety Standard & Fairway Fort Technical Bulletins",
        "caption": "OEM Battery Bank Series/Parallel vs. Drop-in LiFePO4 Voltage & Solenoid Wiring Diagram."
    },
    {
        "id": "va-controller-pinout",
        "name": "Curtis / Navitas / Alltrax Motor Controller Pinout Guide",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/curtis-navitas-controller-pinout-guide.webp",
        "target_url": "https://fairwayfort.com/pages/tools",
        "intent_keywords": ["controller", "curtis", "navitas", "alltrax", "motor", "pinout", "throttle", "its", "solenoid", "clicking", "wont run", "no move", "beeping", "diagnostic", "regen", "speed code", "shunts"],
        "citation_source": "Source: OEM Motor Controller Technical Reference Guide (Fairway Fort Dataset)",
        "caption": "High-Current Motor Controller Throttle Input (ITS/0-5kΩ) & Diagnostic Blink Code Matrix."
    },
    {
        "id": "va-liftkit-tire-fitment",
        "name": "Lift Kit & Tire Clearance Fitment Matrix",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/golf-cart-lift-kit-tire-fitment-chart.webp",
        "target_url": "https://fairwayfort.com/pages/tools",
        "intent_keywords": ["lift", "lift kit", "tire", "tires", "wheel", "wheels", "rubbing", "clearance", "spindle", "a-arm", "all terrain", "14 inch", "12 inch", "10 inch", "offset", "camber", "toe in"],
        "citation_source": "Source: SEMA LSV Suspension Geometry Guidelines & Fairway Fort Fitment Chart",
        "caption": "Drop Spindle vs A-Arm Lift Height (3\" to 6\") & Max Tire Size Offset Clearance Guide."
    },
    {
        "id": "va-street-equipment-checklist",
        "name": "Federal DOT Street-Legal Equipment Checklist",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/golf-cart-street-legal-equipment-checklist.webp",
        "target_url": "https://fairwayfort.com/pages/tools",
        "intent_keywords": ["checklist", "equipment", "turn signal", "horn", "seat belt", "mirror", "dot tires", "brake lights", "inspection", "sheriff", "police", "ticket", "street legal kit", "light kit"],
        "citation_source": "Source: Federal Motor Vehicle Safety Standards (NHTSA 49 CFR Part 571 Subpart B)",
        "caption": "Mandatory Equipment Checklist: DOT Tires, Seat Belts, Turn Signals, Mirrors, Horn & Backup Alarm."
    },
    {
        "id": "va-canopy-sizing",
        "name": "Golf Cart Extended Canopy & Cover Sizing Matrix",
        "image_url": "https://fairwayfort.com/cdn/shop/t/9/assets/cartarmor-category-storage-cover-1200.webp",
        "target_url": "https://fairwayfort.com/pages/golf-cart-roof-cover-calculator",
        "intent_keywords": ["cover", "roof", "canopy", "storage cover", "dimension", "dimensions", "4 passenger", "4-passenger", "d5", "evolution", "nomad", "denago", "icon", "precedent", "tear", "ripped", "waterproof", "skirt drop", "footrest"],
        "citation_source": "Source: Fairway Fort LSV Canopy Fitment & Roof Clearance Dataset",
        "caption": "OEM vs. Extended (54\" to 88\" Canopy Crown) & 4-Passenger Footrest Clearance Sizing Guide."
    }
]

DEFAULT_GOLF_PERSONAS = [
    {
        "key": "mechanic",
        "label": "🔧 驻厂老技师",
        "name": "Senior Master Cart Tech & Diagnostic Guru",
        "tone": "Direct, hands-on, zero fluff. Diagnoses root causes with technical specifics (voltages, pinouts, solenoid clicks, OBC bypasses, motor winding resistance). Speaks from 15+ years in cart repair bays.",
        "match_keywords": ["wiring", "solenoid", "controller", "pinout", "curtis", "alltrax", "lithium", "battery", "batteries", "36v", "48v", "charger", "obc", "fuse", "clicking", "wont run", "won't run", "motor", "smoke", "spark", "resistor", "diode", "throttle", "its", "shunts", "voltage drop", "bms", "diagnostic"]
    },
    {
        "key": "modder",
        "label": "⚡ 极客改装先锋",
        "name": "Performance Builder & Suspension Modder",
        "tone": "Performance enthusiast passionate about speed codes, Navitas 600A OTF on-the-fly programmers, lithium high-discharge C-rates, drop spindle vs A-arm suspension geometry, and tire rubbing clearance offsets. Energetic, tech-savvy, hands-on.",
        "match_keywords": ["lift", "lift kit", "tire", "tires", "wheel", "wheels", "rubbing", "spindle", "a-arm", "navitas", "speed", "mph", "fast", "all-terrain", "offset", "camber", "controller tuning", "otf", "high speed", "gears", "motor swap"]
    },
    {
        "key": "cruiser",
        "label": "⛳ 车友会老司机",
        "name": "Neighborhood Cart Veteran & Community Cruiser",
        "tone": "Friendly, seasoned golf cart community regular who cruises daily in golf cart-friendly towns (The Villages, Peachtree City, Sun City, Florida coastal towns). Empathic, practical, expert in daily community use, DOT equipment like mirrors, turn signals, seat belts, and child safety.",
        "match_keywords": ["neighborhood", "village", "cruiser", "kids", "seat belt", "mirror", "horn", "light kit", "accessories", "enclosure", "sound bar", "speaker", "cover", "which cart", "recommendation", "buying", "club car vs ezgo", "family", "golf course", "daily", "commute"]
    },
    {
        "key": "compliance",
        "label": "📜 合规与法规专家",
        "name": "Statutory & DMV LSV Compliance Specialist",
        "tone": "Clear, meticulous, well-versed in NHTSA 49 CFR § 571.500, state statutory codes, DMV inspection requirements, FMVSS 205 AS4/AS5 windshield standards vs fold-down acrylic, and 17-digit VIN vs manufacturer serials. Objective, direct, reassuring.",
        "match_keywords": ["law", "legal", "dmv", "police", "sheriff", "ticket", "street legal", "statute", "inspection", "title", "plate", "registration", "fmvss", "as4", "as5", "vin", "serial", "speed limit", "road", "public", "ordinance"]
    }
]

DEFAULT_FAIRWAYFORT_OFFERS = [
    {
        "key": "serial_decoder",
        "name": "车架号与年份解码工具",
        "name_en": "Serial & VIN Decoder",
        "keywords": ["vin", "serial", "serial number", "year", "what year", "model number", "what model", "which model"],
        "url": "https://fairwayfort.com/pages/tools?tool=serial-decoder"
    },
    {
        "key": "street_legal",
        "name": "全美各州路权合规核查器",
        "name_en": "50-State Street Legal LSV Checker",
        "keywords": ["street legal", "lsv", "dmv", "law", "legal", "road", "public road", "plate", "license", "inspection", "title", "statute", "fmvss", "as4", "as5"],
        "url": "https://fairwayfort.com/pages/tools?tool=street-legal-checker"
    },
    {
        "key": "speed_calc",
        "name": "极速与速比在线计算器",
        "name_en": "Top Speed & Gear Ratio Calculator",
        "keywords": ["speed", "mph", "fast", "speed code", "navitas", "controller", "gear", "rpm", "speedometer", "top speed"],
        "url": "https://fairwayfort.com/pages/tools?tool=speed-calculator"
    },
    {
        "key": "battery_guide",
        "name": "锂电换装选型与续航表",
        "name_en": "Lithium Battery Conversion & Range Matrix",
        "keywords": ["lithium", "battery", "batteries", "36v", "48v", "lead acid", "drop in", "trojan", "charger", "bms", "range"],
        "url": "https://fairwayfort.com/pages/tools?tool=battery-comparison"
    }
]


def load_config() -> dict:
    with get_db() as db:
        creds = []
        for r in db.execute("SELECT id,type,name,data FROM credentials ORDER BY rowid"):
            c = {"id": r["id"], "type": r["type"], "name": r["name"]}
            c.update(json.loads(r["data"]))
            creds.append(c)

        listeners = []
        for r in db.execute("SELECT * FROM listeners ORDER BY sort_order, rowid"):
            listeners.append({
                "id":                   r["id"],
                "name":                 r["name"],
                "enabled":              bool(r["enabled"]),
                "subreddits":           r["subreddits"],
                "webhook":              r["webhook"],
                "whitelist":            json.loads(r["whitelist"]),
                "keywords":             json.loads(r["keywords"]),
                "filters":              json.loads(r["filters"]),
                "negative_keywords":    json.loads(safe_col(r, "negative_keywords") or "[]"),
                "min_karma":            int(safe_col(r, "min_karma") or 0),
                "min_account_age_days": int(safe_col(r, "min_account_age_days") or 0),
                "slack_webhook":        safe_col(r, "slack_webhook") or "",
                "telegram_bot_token":   safe_col(r, "telegram_bot_token") or "",
                "telegram_chat_id":     safe_col(r, "telegram_chat_id") or "",
                "schedule_enabled":     bool(safe_col(r, "schedule_enabled") or 0),
                "schedule_timezone":    safe_col(r, "schedule_timezone") or "UTC",
                "schedule_days":        json.loads(safe_col(r, "schedule_days") or "[0,1,2,3,4,5,6]"),
                "schedule_start":       int(safe_col(r, "schedule_start") or 0),
                "schedule_end":         int(safe_col(r, "schedule_end") or 24),
                "auto_reply_enabled":   bool(safe_col(r, "auto_reply_enabled", 1)),
                "site_name":            safe_col(r, "site_name") or "My Product",
                "site_url":             safe_col(r, "site_url") or "",
                "site_description":     safe_col(r, "site_description") or "",
                "pitch_instruction":    safe_col(r, "pitch_instruction") or "Provide genuine technical value first; mention tool only if directly relevant and helpful. Never sound like a salesperson.",
                "anti_ban_mode":        safe_col(r, "anti_ban_mode") or "brand_search",
                "auto_submit_enabled":  bool(safe_col(r, "auto_submit_enabled", 0)),
                "reply_cooldown_minutes": int(safe_col(r, "reply_cooldown_minutes", 45) or 45),
                "daily_reply_limit":    int(safe_col(r, "daily_reply_limit", 8) or 8),
                "platform":             safe_col(r, "platform") or "reddit",
                "forum_rss_url":         safe_col(r, "forum_rss_url") or "",
                "stealth_mode":           safe_col(r, "stealth_mode") or "direct_link",
                "dark_fleet_enabled":     bool(safe_col(r, "dark_fleet_enabled", 1)),
                "dark_fleet_min_safety":  int(safe_col(r, "dark_fleet_min_safety", 85) or 85),
                "dark_fleet_min_opp":     int(safe_col(r, "dark_fleet_min_opp", 70) or 70),
                "x_credential_id":      safe_col(r, "x_credential_id") or "",
                "forum_credential_id":  safe_col(r, "forum_credential_id") or "",
                "visual_assets":        json.loads(safe_col(r, "visual_assets") or "[]") or (DEFAULT_FAIRWAYFORT_ASSETS if "fairway" in (safe_col(r, "site_name") or "").lower() else []),
                "personas":             json.loads(safe_col(r, "personas") or "[]") or (DEFAULT_GOLF_PERSONAS if "fairway" in (safe_col(r, "site_name") or "").lower() else []),
                "offers_matrix":        json.loads(safe_col(r, "offers_matrix") or "[]") or (DEFAULT_FAIRWAYFORT_OFFERS if "fairway" in (safe_col(r, "site_name") or "").lower() else []),
                "reddit_credential_id": r["reddit_credential_id"],
                "ai_credential_id":     r["ai_credential_id"],
            })

    return {
        "credentials":     creds,
        "listeners":       listeners,
        "product_context": get_setting("product_context"),
    }


def save_config(cfg: dict) -> None:
    with get_db() as db:
        new_ids = {c["id"] for c in cfg.get("credentials", [])}
        old_ids = {r["id"] for r in db.execute("SELECT id FROM credentials")}
        for dead in old_ids - new_ids:
            db.execute("DELETE FROM credentials WHERE id=?", (dead,))
        for c in cfg.get("credentials", []):
            data = {k: v for k, v in c.items() if k not in ("id", "type", "name")}
            db.execute(
                "INSERT INTO credentials(id,type,name,data) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET type=excluded.type,name=excluded.name,data=excluded.data",
                (c["id"], c["type"], c["name"], json.dumps(data)),
            )

        new_ids = {l["id"] for l in cfg.get("listeners", [])}
        old_ids = {r["id"] for r in db.execute("SELECT id FROM listeners")}
        for dead in old_ids - new_ids:
            db.execute("DELETE FROM listeners WHERE id=?", (dead,))
        for i, l in enumerate(cfg.get("listeners", [])):
            db.execute(
                """INSERT INTO listeners
	                   (id,name,enabled,subreddits,webhook,whitelist,keywords,filters,
	                    negative_keywords,min_karma,min_account_age_days,
	                    slack_webhook,telegram_bot_token,telegram_chat_id,
	                    schedule_enabled,schedule_timezone,schedule_days,schedule_start,schedule_end,
	                    auto_reply_enabled,site_name,site_url,site_description,pitch_instruction,anti_ban_mode,
	                    auto_submit_enabled,reply_cooldown_minutes,daily_reply_limit,
	                    platform,forum_rss_url,stealth_mode,dark_fleet_enabled,dark_fleet_min_safety,dark_fleet_min_opp,x_credential_id,forum_credential_id,visual_assets,personas,offers_matrix,
	                    reddit_credential_id,ai_credential_id,sort_order)
	                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
	                   ON CONFLICT(id) DO UPDATE SET
	                     name=excluded.name,enabled=excluded.enabled,
	                     subreddits=excluded.subreddits,webhook=excluded.webhook,
	                     whitelist=excluded.whitelist,keywords=excluded.keywords,
	                     filters=excluded.filters,negative_keywords=excluded.negative_keywords,
	                     min_karma=excluded.min_karma,min_account_age_days=excluded.min_account_age_days,
	                     slack_webhook=excluded.slack_webhook,
	                     telegram_bot_token=excluded.telegram_bot_token,
	                     telegram_chat_id=excluded.telegram_chat_id,
	                     schedule_enabled=excluded.schedule_enabled,
	                     schedule_timezone=excluded.schedule_timezone,
	                     schedule_days=excluded.schedule_days,
	                     schedule_start=excluded.schedule_start,
	                     schedule_end=excluded.schedule_end,
	                     auto_reply_enabled=excluded.auto_reply_enabled,
	                     site_name=excluded.site_name,
	                     site_url=excluded.site_url,
	                     site_description=excluded.site_description,
	                     pitch_instruction=excluded.pitch_instruction,
	                     anti_ban_mode=excluded.anti_ban_mode,
	                     auto_submit_enabled=excluded.auto_submit_enabled,
	                     reply_cooldown_minutes=excluded.reply_cooldown_minutes,
	                     daily_reply_limit=excluded.daily_reply_limit,
	                     reddit_credential_id=excluded.reddit_credential_id,
	                     platform=excluded.platform,
	                     forum_rss_url=excluded.forum_rss_url,
	                     stealth_mode=excluded.stealth_mode,
	                     dark_fleet_enabled=excluded.dark_fleet_enabled,
	                     dark_fleet_min_safety=excluded.dark_fleet_min_safety,
	                     dark_fleet_min_opp=excluded.dark_fleet_min_opp,
	                     x_credential_id=excluded.x_credential_id,
	                     forum_credential_id=excluded.forum_credential_id,
	                     visual_assets=excluded.visual_assets,
	                     personas=excluded.personas,
	                     offers_matrix=excluded.offers_matrix,
	                     ai_credential_id=excluded.ai_credential_id,
	                     sort_order=excluded.sort_order""",
	                (l["id"], l["name"], 1 if l.get("enabled", True) else 0,
	                 " ".join(l["subreddits"]) if isinstance(l.get("subreddits"), list) else (l.get("subreddits") or "all"), l.get("webhook", ""),
	                 json.dumps(l.get("whitelist", [])), json.dumps(l.get("keywords", [])),
	                 json.dumps(l.get("filters", [])), json.dumps(l.get("negative_keywords", [])),
	                 int(l.get("min_karma", 0) or 0), int(l.get("min_account_age_days", 0) or 0),
	                 l.get("slack_webhook", ""), l.get("telegram_bot_token", ""), l.get("telegram_chat_id", ""),
	                 1 if l.get("schedule_enabled") else 0,
	                 l.get("schedule_timezone", "UTC"),
	                 json.dumps(l.get("schedule_days", list(range(7)))),
	                 int(l.get("schedule_start", 0)), int(l.get("schedule_end", 24)),
	                 1 if l.get("auto_reply_enabled", True) else 0,
	                 l.get("site_name", "My Product"),
	                 l.get("site_url", ""),
	                 l.get("site_description", ""),
	                 l.get("pitch_instruction", "Provide genuine technical value first; mention tool only if directly relevant and helpful. Never sound like a salesperson."),
	                 l.get("anti_ban_mode", "brand_search"),
	                 1 if l.get("auto_submit_enabled") else 0,
	                 int(l.get("reply_cooldown_minutes", 45) or 45),
	                 int(l.get("daily_reply_limit", 8) or 8),
	                 l.get("platform", "reddit"),
	                 l.get("forum_rss_url", ""),
	                 l.get("stealth_mode", "direct_link"),
	                 1 if l.get("dark_fleet_enabled", True) else 0,
	                 int(l.get("dark_fleet_min_safety", 85) or 85),
	                 int(l.get("dark_fleet_min_opp", 70) or 70),
	                 l.get("x_credential_id", ""),
	                 l.get("forum_credential_id", ""),
	                 json.dumps(l.get("visual_assets", [])),
	                 json.dumps(l.get("personas", [])),
	                 json.dumps(l.get("offers_matrix", [])),
	                 l.get("reddit_credential_id"), l.get("ai_credential_id"), i),
	            )
        if "product_context" in cfg:
            db.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("product_context", cfg["product_context"] or ""),
            )


def migrate_from_json() -> None:
    """One-time import of legacy config.json."""
    f = Path("config.json")
    if not f.exists():
        return
    try:
        raw = json.loads(f.read_text())
        if "keywords" in raw and "listeners" not in raw:
            raw["listeners"] = [{
                "id": str(_uuid_mod.uuid4()), "name": "Default", "enabled": True,
                "subreddits": raw.pop("subreddits", "all"), "webhook": raw.pop("webhook", ""),
                "whitelist":  raw.pop("whitelist", []),    "keywords": raw.pop("keywords", []),
                "filters":    raw.pop("filters", []),
            }]
        if ("client_id" in raw or "anthropic_key" in raw) and "credentials" not in raw:
            creds: list[dict] = []
            rc_id = ai_id = None
            if raw.get("client_id") or raw.get("client_secret"):
                rc_id = str(_uuid_mod.uuid4())
                creds.append({"id": rc_id, "name": "Default Reddit", "type": "reddit",
                               "client_id": raw.pop("client_id", ""),
                               "client_secret": raw.pop("client_secret", ""),
                               "user_agent": raw.pop("user_agent", "redsignal/1.0")})
            else:
                for k in ("client_id", "client_secret", "user_agent"): raw.pop(k, None)
            if raw.get("anthropic_key"):
                ai_id = str(_uuid_mod.uuid4())
                creds.append({"id": ai_id, "name": "Default Anthropic", "type": "anthropic",
                               "api_key": raw.pop("anthropic_key")})
            else:
                raw.pop("anthropic_key", None)
            raw["credentials"] = creds
            for lst in raw.get("listeners", []):
                if rc_id: lst.setdefault("reddit_credential_id", rc_id)
                if ai_id: lst.setdefault("ai_credential_id", ai_id)
        save_config(raw)
        f.rename("config.json.bak")
        db_log("info", "system", "Migrated config.json → redsignal.db")
    except Exception as exc:
        db_log("warn", "system", f"config.json migration warning: {exc}")
