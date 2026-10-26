from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

_BASE_DIR = Path(__file__).resolve().parent
_env_path = os.getenv("DB_PATH")
if _env_path:
    _p = Path(_env_path)
    DB_PATH = _p if _p.is_absolute() else (_BASE_DIR / _p)
else:
    DB_PATH = _BASE_DIR / "data" / "redsignal.db"

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS credentials (
    id   TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS listeners (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL DEFAULT 'Listener',
    enabled              INTEGER NOT NULL DEFAULT 1,
    subreddits           TEXT NOT NULL DEFAULT 'all',
    webhook              TEXT NOT NULL DEFAULT '',
    whitelist            TEXT NOT NULL DEFAULT '[]',
    keywords             TEXT NOT NULL DEFAULT '[]',
    filters              TEXT NOT NULL DEFAULT '[]',
    negative_keywords    TEXT NOT NULL DEFAULT '[]',
    min_karma            INTEGER NOT NULL DEFAULT 0,
    min_account_age_days INTEGER NOT NULL DEFAULT 0,
    slack_webhook        TEXT NOT NULL DEFAULT '',
    telegram_bot_token   TEXT NOT NULL DEFAULT '',
    telegram_chat_id     TEXT NOT NULL DEFAULT '',
    schedule_enabled     INTEGER NOT NULL DEFAULT 0,
    schedule_timezone    TEXT NOT NULL DEFAULT 'UTC',
    schedule_days        TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
    schedule_start       INTEGER NOT NULL DEFAULT 0,
    schedule_end         INTEGER NOT NULL DEFAULT 24,
    reddit_credential_id TEXT,
    ai_credential_id     TEXT,
    visual_assets        TEXT NOT NULL DEFAULT '[]',
    personas             TEXT NOT NULL DEFAULT '[]',
    offers_matrix        TEXT NOT NULL DEFAULT '[]',
    sort_order           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS hits (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    hit_id         TEXT NOT NULL,
    listener_id    TEXT,
    listener_name  TEXT,
    kind           TEXT,
    subreddit      TEXT,
    author         TEXT,
    match_text     TEXT,
    title          TEXT,
    url            TEXT,
    excerpt        TEXT,
    post_id        TEXT,
    ts             REAL,
    filter_passed  INTEGER,
    filter_results TEXT,
    status         TEXT NOT NULL DEFAULT 'new',
    reply_draft    TEXT,
    opportunity_score INTEGER NOT NULL DEFAULT 50,
    safety_verdict TEXT,
    safety_score   INTEGER,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(hit_id, listener_id)
);

CREATE TABLE IF NOT EXISTS webhook_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    listener_id   TEXT,
    listener_name TEXT,
    wtype         TEXT,
    url           TEXT,
    payload       TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    delivered_at  TEXT
);

CREATE TABLE IF NOT EXISTS system_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    level         TEXT NOT NULL DEFAULT 'info',
    source        TEXT NOT NULL DEFAULT 'system',
    listener_id   TEXT,
    listener_name TEXT,
    message       TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS reply_queue (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    hit_id             TEXT NOT NULL,
    listener_id        TEXT,
    listener_name      TEXT,
    subreddit          TEXT,
    post_id            TEXT,
    target_id          TEXT,
    target_url         TEXT,
    author             TEXT,
    reply_text         TEXT NOT NULL,
    credential_id      TEXT NOT NULL DEFAULT '',
    funnel_tier        INTEGER NOT NULL DEFAULT 3,
    status             TEXT NOT NULL DEFAULT 'pending',
    error_message      TEXT,
    comment_id         TEXT,
    comment_url        TEXT,
    visibility_status  TEXT NOT NULL DEFAULT 'unverified',
    scheduled_at       REAL,
    submitted_at       REAL,
    opportunity_score  INTEGER NOT NULL DEFAULT 50,
    safety_verdict     TEXT DEFAULT 'PASSED',
    updated_at         REAL,
    failed_at          REAL,
    created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS account_quota (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    credential_id  TEXT NOT NULL,
    account_name   TEXT NOT NULL,
    date_str       TEXT NOT NULL,
    reply_count    INTEGER NOT NULL DEFAULT 0,
    last_reply_ts  REAL NOT NULL DEFAULT 0,
    UNIQUE(credential_id, date_str)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS ai_learnings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    platform       TEXT NOT NULL DEFAULT 'reddit',
    subreddit      TEXT NOT NULL DEFAULT '',
    learning_type  TEXT NOT NULL DEFAULT 'anti_ban_rule',
    title          TEXT NOT NULL,
    pattern        TEXT NOT NULL,
    action_taken   TEXT NOT NULL,
    sample_text    TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS short_links (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    code             TEXT UNIQUE NOT NULL,
    target_url       TEXT NOT NULL,
    final_url        TEXT NOT NULL,
    hit_id           TEXT,
    queue_id         INTEGER,
    listener_id      TEXT,
    persona          TEXT,
    platform         TEXT NOT NULL DEFAULT 'reddit',
    clicks           INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_clicked_at  TEXT
);

CREATE TABLE IF NOT EXISTS link_click_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL,
    ip_hash     TEXT NOT NULL,
    user_agent  TEXT,
    referer     TEXT,
    clicked_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS leads (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT NOT NULL,
    source         TEXT DEFAULT 'lead_magnet',
    hit_id         TEXT,
    queue_id       INTEGER,
    short_code     TEXT,
    intent         TEXT,
    state          TEXT,
    cart_model     TEXT,
    ip_hash        TEXT,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS barnacle_targets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword           TEXT NOT NULL,
    target_url        TEXT UNIQUE NOT NULL,
    platform          TEXT NOT NULL DEFAULT 'reddit',
    post_title        TEXT,
    google_rank       INTEGER DEFAULT 0,
    search_snippet    TEXT,
    author            TEXT,
    post_created_at   REAL DEFAULT 0,
    is_archived       INTEGER DEFAULT 0,
    opportunity_score INTEGER DEFAULT 85,
    evergreen_draft   TEXT,
    status            TEXT NOT NULL DEFAULT 'discovered',
    reply_url         TEXT,
    reply_upvotes     INTEGER DEFAULT 0,
    notes             TEXT,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at        REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dm_conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id         TEXT NOT NULL,
    platform          TEXT NOT NULL DEFAULT 'reddit',
    partner_handle    TEXT NOT NULL,
    current_round     INTEGER NOT NULL DEFAULT 1,
    campaign_id       TEXT,
    subject           TEXT,
    last_inbound_msg  TEXT,
    last_outbound_msg TEXT,
    status            TEXT NOT NULL DEFAULT 'active',
    updated_at        REAL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(platform, partner_handle)
);

CREATE INDEX IF NOT EXISTS hits_listener   ON hits(listener_id);
CREATE INDEX IF NOT EXISTS hits_ts         ON hits(ts DESC);
CREATE INDEX IF NOT EXISTS hits_sub        ON hits(subreddit);
CREATE INDEX IF NOT EXISTS syslog_ts       ON system_log(created_at DESC);
CREATE INDEX IF NOT EXISTS webhooklog_ts   ON webhook_log(created_at DESC);
CREATE INDEX IF NOT EXISTS rqueue_status   ON reply_queue(status, scheduled_at);
CREATE INDEX IF NOT EXISTS ai_learn_sub    ON ai_learnings(subreddit, platform);
CREATE INDEX IF NOT EXISTS short_link_code ON short_links(code);
CREATE INDEX IF NOT EXISTS click_evt_code  ON link_click_events(code, clicked_at DESC);
CREATE INDEX IF NOT EXISTS leads_email     ON leads(email);
CREATE INDEX IF NOT EXISTS leads_code      ON leads(short_code);
CREATE INDEX IF NOT EXISTS idx_barnacle_kw ON barnacle_targets(keyword);
CREATE INDEX IF NOT EXISTS idx_barnacle_st ON barnacle_targets(status);
CREATE INDEX IF NOT EXISTS idx_dm_partner  ON dm_conversations(platform, partner_handle);
"""


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    # ponytail: local installs do not have Docker's `mkdir data` layer.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(SCHEMA)


def migrate_schema() -> None:
    """Add columns introduced after initial release. Safe to run every startup."""
    cols = [
        ("hits",      "status         TEXT NOT NULL DEFAULT 'new'"),
        ("hits",      "reply_draft    TEXT"),
        ("listeners", "negative_keywords       TEXT NOT NULL DEFAULT '[]'"),
        ("listeners", "min_karma               INTEGER NOT NULL DEFAULT 0"),
        ("listeners", "min_account_age_days    INTEGER NOT NULL DEFAULT 0"),
        ("listeners", "slack_webhook           TEXT NOT NULL DEFAULT ''"),
        ("listeners", "telegram_bot_token      TEXT NOT NULL DEFAULT ''"),
        ("listeners", "telegram_chat_id        TEXT NOT NULL DEFAULT ''"),
        ("listeners", "schedule_enabled        INTEGER NOT NULL DEFAULT 0"),
        ("listeners", "schedule_timezone       TEXT NOT NULL DEFAULT 'UTC'"),
        ("listeners", "schedule_days           TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]'"),
        ("listeners", "schedule_start          INTEGER NOT NULL DEFAULT 0"),
        ("listeners", "schedule_end            INTEGER NOT NULL DEFAULT 24"),
        ("listeners", "auto_reply_enabled      INTEGER NOT NULL DEFAULT 1"),
        ("listeners", "site_name               TEXT NOT NULL DEFAULT 'My Product'"),
        ("listeners", "site_url                TEXT NOT NULL DEFAULT ''"),
        ("listeners", "site_description        TEXT NOT NULL DEFAULT ''"),
        ("listeners", "pitch_instruction       TEXT NOT NULL DEFAULT 'Provide genuine technical value first; mention tool only if directly relevant and helpful. Never sound like a salesperson.'"),
        ("listeners", "anti_ban_mode           TEXT NOT NULL DEFAULT 'brand_search'"),
        ("listeners", "auto_submit_enabled     INTEGER NOT NULL DEFAULT 0"),
        ("listeners", "reply_cooldown_minutes  INTEGER NOT NULL DEFAULT 45"),
        ("listeners", "daily_reply_limit       INTEGER NOT NULL DEFAULT 8"),
        ("listeners", "platform                TEXT NOT NULL DEFAULT 'reddit'"),
        ("listeners", "x_credential_id         TEXT NOT NULL DEFAULT ''"),
        ("listeners", "visual_assets           TEXT NOT NULL DEFAULT '[]'"),
        ("listeners", "personas                TEXT NOT NULL DEFAULT '[]'"),
        ("hits",      "platform                TEXT NOT NULL DEFAULT 'reddit'"),
        ("hits",      "funnel_tier             INTEGER NOT NULL DEFAULT 3"),
        ("hits",      "funnel_reason           TEXT NOT NULL DEFAULT ''"),
        ("hits",      "opportunity_score       INTEGER NOT NULL DEFAULT 50"),
        ("hits",      "safety_verdict          TEXT"),
        ("hits",      "safety_score            INTEGER"),
        ("reply_queue", "platform              TEXT NOT NULL DEFAULT 'reddit'"),
        ("reply_queue", "opportunity_score     INTEGER NOT NULL DEFAULT 50"),
        ("reply_queue", "safety_verdict        TEXT DEFAULT 'PASSED'"),
        ("hits",        "persona               TEXT NOT NULL DEFAULT 'expert'"),
        ("hits",        "persona_label         TEXT NOT NULL DEFAULT '🎯 领域专家'"),
        ("reply_queue", "persona               TEXT NOT NULL DEFAULT 'expert'"),
        ("reply_queue", "persona_label         TEXT NOT NULL DEFAULT '🎯 领域专家'"),
        ("reply_queue", "chrono_reason         TEXT NOT NULL DEFAULT ''"),
        ("reply_queue", "upvotes               INTEGER NOT NULL DEFAULT 0"),
        ("reply_queue", "replies_count         INTEGER NOT NULL DEFAULT 0"),
        ("reply_queue", "last_scraped_at       TEXT"),
        ("reply_queue", "is_winner             INTEGER NOT NULL DEFAULT 0"),
        ("reply_queue", "short_url             TEXT NOT NULL DEFAULT ''"),
        ("reply_queue", "dispatch_mode         TEXT NOT NULL DEFAULT 'manual'"),
        ("reply_queue", "stealth_mode          TEXT NOT NULL DEFAULT 'direct_link'"),
        ("hits",        "auto_dispatched       INTEGER NOT NULL DEFAULT 0"),
        ("listeners",   "dark_fleet_enabled    INTEGER NOT NULL DEFAULT 1"),
        ("listeners",   "dark_fleet_min_safety INTEGER NOT NULL DEFAULT 85"),
        ("listeners",   "dark_fleet_min_opp    INTEGER NOT NULL DEFAULT 70"),
        ("listeners",   "forum_rss_url         TEXT NOT NULL DEFAULT ''"),
        ("listeners",   "forum_credential_id   TEXT NOT NULL DEFAULT ''"),
        ("listeners",   "stealth_mode          TEXT NOT NULL DEFAULT 'direct_link'"),
        ("listeners",   "offers_matrix         TEXT NOT NULL DEFAULT '[]'"),
        ("account_quota", "consecutive_shadowbans INTEGER NOT NULL DEFAULT 0"),
        ("account_quota", "is_quarantined      INTEGER NOT NULL DEFAULT 0"),
        ("account_quota", "quarantine_until    REAL NOT NULL DEFAULT 0"),
        ("account_quota", "rate_limit_until    REAL NOT NULL DEFAULT 0"),
        ("reply_queue", "updated_at            REAL"),
        ("reply_queue", "failed_at             REAL"),
        ("reply_queue", "is_archived           INTEGER NOT NULL DEFAULT 0"),
        ("reply_queue", "credential_id         TEXT NOT NULL DEFAULT ''"),
    ]
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                email          TEXT NOT NULL,
                source         TEXT DEFAULT 'lead_magnet',
                hit_id         TEXT,
                queue_id       INTEGER,
                short_code     TEXT,
                intent         TEXT,
                state          TEXT,
                cart_model     TEXT,
                ip_hash        TEXT,
                created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS leads_email ON leads(email)")
        db.execute("CREATE INDEX IF NOT EXISTS leads_code  ON leads(short_code)")
        db.execute("""
            CREATE TABLE IF NOT EXISTS ai_learnings (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                platform       TEXT NOT NULL DEFAULT 'reddit',
                subreddit      TEXT NOT NULL DEFAULT '',
                learning_type  TEXT NOT NULL DEFAULT 'anti_ban_rule',
                title          TEXT NOT NULL,
                pattern        TEXT NOT NULL,
                action_taken   TEXT NOT NULL,
                sample_text    TEXT,
                created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS short_links (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                code             TEXT UNIQUE NOT NULL,
                target_url       TEXT NOT NULL,
                final_url        TEXT NOT NULL,
                hit_id           TEXT,
                queue_id         INTEGER,
                listener_id      TEXT,
                persona          TEXT,
                platform         TEXT NOT NULL DEFAULT 'reddit',
                clicks           INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                last_clicked_at  TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS link_click_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT NOT NULL,
                ip_hash     TEXT NOT NULL,
                user_agent  TEXT,
                referer     TEXT,
                clicked_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS short_link_code ON short_links(code)")
        db.execute("CREATE INDEX IF NOT EXISTS click_evt_code  ON link_click_events(code, clicked_at DESC)")
        db.execute("""
            CREATE TABLE IF NOT EXISTS barnacle_targets (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword           TEXT NOT NULL,
                target_url        TEXT UNIQUE NOT NULL,
                platform          TEXT NOT NULL DEFAULT 'reddit',
                post_title        TEXT,
                google_rank       INTEGER DEFAULT 0,
                search_snippet    TEXT,
                author            TEXT,
                post_created_at   REAL DEFAULT 0,
                is_archived       INTEGER DEFAULT 0,
                opportunity_score INTEGER DEFAULT 85,
                evergreen_draft   TEXT,
                status            TEXT NOT NULL DEFAULT 'discovered',
                reply_url         TEXT,
                reply_upvotes     INTEGER DEFAULT 0,
                notes             TEXT,
                created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at        REAL DEFAULT 0
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_barnacle_kw ON barnacle_targets(keyword)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_barnacle_st ON barnacle_targets(status)")
        for table, col_def in cols:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # already exists

        # Backfill existing queue rows with timestamps if updated_at or failed_at is null
        try:
            db.execute("""
                UPDATE reply_queue
                SET updated_at = COALESCE(submitted_at, scheduled_at, CAST(strftime('%s', created_at) AS REAL))
                WHERE updated_at IS NULL
            """)
            db.execute("""
                UPDATE reply_queue
                SET failed_at = COALESCE(scheduled_at, CAST(strftime('%s', created_at) AS REAL))
                WHERE status = 'failed' AND failed_at IS NULL
            """)
        except Exception:
            pass

        # Seed initial high-value anti-ban self-healing rules if empty
        row = db.execute("SELECT COUNT(*) as c FROM ai_learnings").fetchone()
        if row and row["c"] == 0:
            defaults = [
                ("reddit", "general", "anti_ban_rule", "高流量社区外链穿透自卫", "社区对直接暴露裸网址敏感，易触发 AutoMod 拦截", "自动采用 Brand Search 纯品牌检索法，指引用户在 Google 搜索品牌名获取公开工具", "I recommend searching for the open technical chart or lookup guide online."),
                ("reddit", "technical", "anti_ban_rule", "技术深度价值前置律", "高流量综合版块严厉打击推销开场白", "强制前两段必须纯技术问题排查与核心参数分析，后置附带工具参考", "Step 1: Diagnose the root cause by checking the primary circuit specs and baseline metrics first."),
                ("x", "", "platform_rule", "𝕏 平台单条推文硬约束", "长推文容易被折叠或因文字超长被 API 截断", "单条回复严格控制在 220 字符以内，保持口语交流感", "Check your primary settings and test the circuit for proper voltage. Search for the spec matrix online.")
            ]
            for p, s, t, tit, pat, act, sam in defaults:
                db.execute(
                    """INSERT INTO ai_learnings (platform, subreddit, learning_type, title, pattern, action_taken, sample_text)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (p, s, t, tit, pat, act, sam)
                )


def db_log(level: str, source: str, message: str,
           listener_id: str | None = None, listener_name: str | None = None) -> None:
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO system_log(level,source,listener_id,listener_name,message) VALUES(?,?,?,?,?)",
                (level, source, listener_id, listener_name, message[:2000]),
            )
    except Exception:
        pass


def get_setting(key: str, default: str = "") -> str:
    with get_db() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_db() as db:
        db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def safe_col(r: sqlite3.Row, key: str, default=None):
    """Safe row accessor for columns that may not exist on older DBs."""
    try:
        return r[key]
    except (IndexError, KeyError):
        return default


def cleanup_old_logs(days: int = 7, max_records: int = 5000) -> dict:
    """Clean up system_log and webhook_log older than `days` or beyond `max_records`, then VACUUM."""
    deleted_sys = 0
    deleted_wh = 0

    with get_db() as db:
        if days > 0:
            time_cutoff = f"-{days} days"
            cur = db.execute(
                "DELETE FROM system_log WHERE created_at < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
                (time_cutoff,)
            )
            deleted_sys += cur.rowcount

            cur = db.execute(
                "DELETE FROM webhook_log WHERE created_at < strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
                (time_cutoff,)
            )
            deleted_wh += cur.rowcount

        if max_records > 0:
            cur = db.execute(
                """DELETE FROM system_log WHERE id NOT IN (
                    SELECT id FROM system_log ORDER BY id DESC LIMIT ?
                )""",
                (max_records,)
            )
            deleted_sys += cur.rowcount

            cur = db.execute(
                """DELETE FROM webhook_log WHERE id NOT IN (
                    SELECT id FROM webhook_log ORDER BY id DESC LIMIT ?
                )""",
                (max_records,)
            )
            deleted_wh += cur.rowcount

    vacuumed = False
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.isolation_level = None
        conn.execute("VACUUM")
        vacuumed = True
    except Exception as exc:
        db_log("warn", "system", f"Database VACUUM skipped or failed: {exc}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    return {
        "deleted_system_logs": deleted_sys,
        "deleted_webhook_logs": deleted_wh,
        "vacuumed": vacuumed
    }

