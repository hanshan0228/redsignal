import os
import sys
import time
import unittest
from starlette.testclient import TestClient

sys.path.insert(0, "/Users/han/redsignal")
from app import app
from db import get_db, init_db, migrate_schema, set_setting
from auto_responder import (
    create_attributed_short_link,
    check_rate_limits,
    _delayed_visibility_check,
    enqueue_reply
)
from monitor import should_dark_fleet_auto_dispatch
from telegram_bot import handle_telegram_message, handle_telegram_callback
from ai import generate_site_integrated_reply


class TestDarkFleetAndAutomation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        migrate_schema()
        cls.client = TestClient(app)

    def setUp(self):
        with get_db() as db:
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'hit_tg_test%' OR hit_id LIKE 'hit_aff_%' OR hit_id LIKE 'hit_reply_child%' OR hit_id LIKE 'hit_dm_test%' OR hit_id LIKE '%_fu_%'")
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'hit_tg_test%' OR hit_id LIKE 'hit_aff_%' OR hit_id LIKE 'hit_reply_child%' OR hit_id LIKE 'hit_dm_test%' OR hit_id LIKE '%_fu_%'")
            db.execute("DELETE FROM ai_learnings WHERE sample_text LIKE '%test resistor%'")
            db.execute("DELETE FROM account_quota WHERE credential_id LIKE 'test_%'")

    def tearDown(self):
        with get_db() as db:
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'hit_tg_test%' OR hit_id LIKE 'hit_aff_%' OR hit_id LIKE 'hit_reply_child%' OR hit_id LIKE 'hit_dm_test%' OR hit_id LIKE '%_fu_%'")
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'hit_tg_test%' OR hit_id LIKE 'hit_aff_%' OR hit_id LIKE 'hit_reply_child%' OR hit_id LIKE 'hit_dm_test%' OR hit_id LIKE '%_fu_%'")
            db.execute("DELETE FROM ai_learnings WHERE sample_text LIKE '%test resistor%'")
            db.execute("DELETE FROM account_quota WHERE credential_id LIKE 'test_%'")

    def test_dark_fleet_decision_logic(self):
        """Test Dark Fleet autonomous closed-loop dispatch conditions."""
        listener = {
            "dark_fleet_enabled": 1,
            "dark_fleet_min_safety": 80,  # 8/10
            "dark_fleet_min_opp": 70
        }

        # 1. Global dark fleet mode disabled
        set_setting("dark_fleet_mode", "0")
        self.assertFalse(should_dark_fleet_auto_dispatch(listener, 1, 85, "PASSED", 9))

        # 2. Global enabled
        set_setting("dark_fleet_mode", "1")
        # High confidence Tier 1, opp 85, passed safety 9/10 -> True
        self.assertTrue(should_dark_fleet_auto_dispatch(listener, 1, 85, "PASSED", 9))
        # High confidence Tier 2, opp 75, passed safety 8/10 -> True
        self.assertTrue(should_dark_fleet_auto_dispatch(listener, 2, 75, "PASSED", 8))

        # Flunk safety -> False
        self.assertFalse(should_dark_fleet_auto_dispatch(listener, 1, 85, "FLAGGED", 9))
        # Safety score too low (< 8/10) -> False
        self.assertFalse(should_dark_fleet_auto_dispatch(listener, 1, 85, "PASSED", 6))
        # Opp score too low (< 70) -> False
        self.assertFalse(should_dark_fleet_auto_dispatch(listener, 1, 65, "PASSED", 9))
        # Low intent Tier 3 -> False
        self.assertFalse(should_dark_fleet_auto_dispatch(listener, 3, 90, "PASSED", 9))

    def test_stealth_modes_and_forum_bbcode(self):
        """Test stealth mode prompt variations and forum BBCode generation."""
        mock_cred = {"type": "claude", "api_key": "mock_key"}

        # 1. Forum platform generates BBCode or technical references
        forum_draft = generate_site_integrated_reply(
            title="Precedent solenoid clicking but won't run",
            excerpt="Tested batteries at 48V. Solenoid clicks when pressing pedal.",
            subreddit="forum",
            site_name="FairwayFort",
            site_url="https://fairwayfort.com",
            site_desc="Golf cart technical diagrams and street legal guides",
            pitch_instruction="",
            anti_ban_mode="direct_link",
            funnel_tier=1,
            credential=mock_cred,
            platform="forum",
            stealth_mode="direct_link"
        )
        self.assertIsInstance(forum_draft, str)
        self.assertGreater(len(forum_draft), 40)

        # 2. Stealth profile_only mode strictly forbids active URL in text
        stealth_draft = generate_site_integrated_reply(
            title="Looking for Club Car DS wiring schematic",
            excerpt="Need 36V resistor cart diagram",
            subreddit="golfcarts",
            site_name="FairwayFort",
            site_url="https://fairwayfort.com",
            site_desc="Golf cart technical schematics",
            pitch_instruction="",
            anti_ban_mode="brand_search",
            funnel_tier=1,
            credential=mock_cred,
            platform="reddit",
            stealth_mode="profile_only"
        )
        self.assertIsInstance(stealth_draft, str)
        self.assertNotIn("https://", stealth_draft.lower())
        self.assertNotIn("http://", stealth_draft.lower())

    def test_account_quarantine_and_self_healing(self):
        """Test account pool quarantine after 2 shadowbans and auto-recovery."""
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        cred_id = "test_quarantine_cred"

        # Initialize quota row
        with get_db() as db:
            db.execute("INSERT OR REPLACE INTO account_quota (credential_id, account_name, date_str, reply_count, consecutive_shadowbans, is_quarantined, quarantine_until) VALUES (?, ?, ?, 0, 0, 0, 0)",
                       (cred_id, "BotAccount1", today))

        # First shadowban -> count=1, not quarantined yet
        with get_db() as db:
            db.execute("UPDATE account_quota SET consecutive_shadowbans=1 WHERE credential_id=?", (cred_id,))

        allowed, reason = check_rate_limits(cred_id, 8, 45)
        self.assertTrue(allowed)

        # Second shadowban -> quarantine triggered for 24h
        with get_db() as db:
            db.execute("UPDATE account_quota SET consecutive_shadowbans=2, is_quarantined=1, quarantine_until=? WHERE credential_id=?",
                       (time.time() + 86400, cred_id))

        allowed, reason = check_rate_limits(cred_id, 8, 45)
        self.assertFalse(allowed)
        self.assertIn("Shadowban 隔离保护期", reason)

        # Successful visibility resets quarantine
        with get_db() as db:
            db.execute("UPDATE account_quota SET consecutive_shadowbans=0, is_quarantined=0, quarantine_until=0 WHERE credential_id=?",
                       (cred_id,))
        allowed, reason = check_rate_limits(cred_id, 8, 45)
        self.assertTrue(allowed)

    def test_lead_capture_and_dynamic_forwarding(self):
        """Test zero-party lead capture API and short link dynamic parameter forwarding."""
        # 1. Create short link
        s_res = create_attributed_short_link(
            target_url="https://fairwayfort.com/tool",
            hit_id="hit_lead_1",
            queue_id=101,
            listener_id="lst_lead",
            persona="expert",
            platform="reddit",
            intent="street_legal",
            state="FL",
            cart_model="Precedent"
        )
        code = s_res["code"]
        self.assertTrue(code)

        # 2. Redirect with dynamic context forwarding
        resp = self.client.get(f"/r/{code}?state=FL&cart_model=Precedent", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        loc = resp.headers["location"]
        self.assertIn("state=FL", loc)
        self.assertIn("cart_model=Precedent", loc)

        # 3. Capture inbound lead
        payload = {
            "email": "test_buyer@gmail.com",
            "short_code": code,
            "source": "lead_magnet_widget",
            "intent": "street_legal_checklist",
            "state": "FL",
            "cart_model": "Precedent"
        }
        cap_resp = self.client.post("/api/leads/capture", json=payload)
        self.assertEqual(cap_resp.status_code, 200)
        data = cap_resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("lead_id", data)

        # 4. Query leads list
        list_resp = self.client.get("/api/leads")
        self.assertEqual(list_resp.status_code, 200)
        leads_data = list_resp.json()
        self.assertTrue(leads_data.get("ok"))
        matched = [l for l in leads_data.get("leads", []) if l["email"] == "test_buyer@gmail.com"]
        self.assertGreaterEqual(len(matched), 1)
        self.assertEqual(matched[0]["state"], "FL")
        self.assertEqual(matched[0]["cart_model"], "Precedent")

    def test_telegram_commands_and_callbacks(self):
        """Test Telegram text commands (/status, /queue, /darkfleet) and callback actions."""
        # 1. Test /darkfleet on & off
        handle_telegram_message("mock_token", {"chat": {"id": 12345}, "text": "/darkfleet off"})
        with get_db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='dark_fleet_mode'").fetchone()
            self.assertEqual(row["value"], "0")

        handle_telegram_message("mock_token", {"chat": {"id": 12345}, "text": "/darkfleet on"})
        with get_db() as db:
            row = db.execute("SELECT value FROM settings WHERE key='dark_fleet_mode'").fetchone()
            self.assertEqual(row["value"], "1")

        # 2. Insert mock hit for callback testing
        with get_db() as db:
            db.execute("INSERT OR REPLACE INTO hits (hit_id, listener_id, subreddit, title, url, excerpt, reply_draft, filter_passed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("hit_tg_test", "lst_test", "golfcarts", "Motor humming", "https://reddit.com/r/test", "excerpt", "Check brushes", 1))

        # 3. Test callback 'sc:hit_tg_test' (Smart Chrono Schedule)
        cb_res = handle_telegram_callback("mock_token", {
            "id": "cq_1",
            "data": "sc:hit_tg_test",
            "message": {"chat": {"id": 12345}, "message_id": 999},
            "from": {"first_name": "Admin"}
        })
        self.assertTrue(cb_res.get("ok"))
        self.assertEqual(cb_res.get("status"), "scheduled")

        # 4. Test callback 'rj:hit_tg_test' (Reject / Cancel)
        cb_rj = handle_telegram_callback("mock_token", {
            "id": "cq_2",
            "data": "rj:hit_tg_test",
            "message": {"chat": {"id": 12345}, "message_id": 999},
            "from": {"first_name": "Admin"}
        })
        self.assertTrue(cb_rj.get("ok"))
        self.assertEqual(cb_rj.get("status"), "ignored")

    def test_conversational_affiliate_follow_up_engine(self):
        """Test Step 2 Conversational Affiliate Engine: follow-up draft generation and reply radar."""
        import json
        import asyncio
        from unittest.mock import patch, MagicMock
        from ai import generate_follow_up_reply
        from auto_responder import fetch_reddit_comment_stats, performance_tracking_loop

        # 1. Unit Test generate_follow_up_reply fallback
        with patch("ai.resolve_ai_cred", return_value=None):
            fallback_reply = generate_follow_up_reply(
                parent_reply="Check the resistor coils under the rear seat.",
                user_question="Where did you get the replacement solenoid?",
                user_author="cart_fixer",
                site_name="FairwayFort",
                site_url="https://fairwayfort.com/parts",
                credential=None
            )
            self.assertIn("https://fairwayfort.com/parts", fallback_reply)

        # 2. Unit Test generate_follow_up_reply with AI mock
        mock_cred = {"type": "anthropic", "api_key": "test_key", "model": "claude-3-haiku-20240307"}
        with patch("ai.run_ai_prompt", return_value="I used the heavy-duty 400A solenoid from https://fairwayfort.com/parts, worked like a charm."):
            ai_reply = generate_follow_up_reply(
                parent_reply="Check the resistor coils.",
                user_question="Which solenoid did you buy?",
                user_author="cart_fixer",
                site_name="FairwayFort",
                site_url="https://fairwayfort.com/parts",
                credential=mock_cred
            )
            self.assertIn("https://fairwayfort.com/parts", ai_reply)
            self.assertIn("solenoid", ai_reply)

        # 3. Unit Test fetch_reddit_comment_stats with return_replies=True and False
        mock_reddit_json = [
            {"data": {"children": []}},
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "parent_cmt_1",
                                "score": 9,
                                "replies": {
                                    "data": {
                                        "children": [
                                            {
                                                "kind": "t1",
                                                "data": {
                                                    "id": "child_rep_88",
                                                    "author": "interested_user",
                                                    "body": "Which brake kit did you install?",
                                                    "created_utc": time.time(),
                                                    "permalink": "/r/golfcarts/comments/post_p1/_/child_rep_88"
                                                }
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                    ]
                }
            }
        ]
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(mock_reddit_json).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=mock_resp):
            score, count = fetch_reddit_comment_stats("parent_cmt_1", "post_p1", "golfcarts", return_replies=False)
            self.assertEqual(score, 9)
            self.assertEqual(count, 1)

            score_r, count_r, replies_list = fetch_reddit_comment_stats("parent_cmt_1", "post_p1", "golfcarts", return_replies=True)
            self.assertEqual(score_r, 9)
            self.assertEqual(count_r, 1)
            self.assertEqual(len(replies_list), 1)
            self.assertEqual(replies_list[0]["id"], "child_rep_88")
            self.assertEqual(replies_list[0]["author"], "interested_user")

        # 4. End-to-end Test performance_tracking_loop detecting child reply and enqueuing Step 2 close
        with get_db() as db:
            db.execute(
                """INSERT INTO reply_queue
                   (hit_id, listener_id, listener_name, subreddit, post_id, comment_id, target_id, author, reply_text, status, scheduled_at, submitted_at, is_winner)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("hit_aff_parent", "lst_test", "Golf Radar", "golfcarts", "post_p1", "parent_cmt_1", "t3_post_p1",
                 "cart_owner", "Diagnostic: test resistor", "submitted", time.time(), time.time(), 1)
            )

        sleep_calls = 0
        async def mock_sleep(secs):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 3:
                raise asyncio.CancelledError()

        with patch("urllib.request.urlopen", return_value=mock_resp), \
             patch("asyncio.sleep", side_effect=mock_sleep), \
             patch("ai.run_ai_prompt", return_value="For your cart, check the brake kit at https://fairwayfort.com/brakes"):
            try:
                asyncio.run(performance_tracking_loop())
            except (asyncio.CancelledError, Exception):
                pass

        # Verify that hit_reply_child_rep_88 was created in hits as kind='follow_up'
        with get_db() as db:
            hit_row = db.execute("SELECT * FROM hits WHERE hit_id='hit_reply_child_rep_88'").fetchone()
            self.assertIsNotNone(hit_row, "Step 2 follow-up hit should be captured in hits table")
            self.assertEqual(hit_row["kind"], "follow_up")
            self.assertEqual(hit_row["funnel_tier"], 1)
            self.assertEqual(hit_row["author"], "interested_user")
            self.assertIn("child_rep_88", hit_row["url"])

            # Verify that reply_queue enqueued the follow-up response with target_id=t1_child_rep_88
            q_row = db.execute("SELECT * FROM reply_queue WHERE hit_id='hit_reply_child_rep_88'").fetchone()
            self.assertIsNotNone(q_row, "Step 2 close reply should be enqueued in reply_queue")
            self.assertEqual(q_row["target_id"], "t1_child_rep_88")
            self.assertEqual(q_row["funnel_tier"], 1)
            self.assertIn("fairwayfort.com", q_row["reply_text"])

    def test_submit_x_reply_query_id_rotation(self):
        """Test X Web GraphQL submission with queryId auto-rotation fallback."""
        from auto_responder import submit_x_reply
        from unittest.mock import patch, MagicMock

        reply_item = {
            "reply_text": "Great insights on golf cart wiring!",
            "target_id": "189283746592837465"
        }
        mock_x_cred = {
            "auth_token": "mock_auth_token",
            "ct0": "mock_ct0_cookie",
            "query_id": "CustomQueryId123"
        }

        # 1. Simulate CustomQueryId returning 404 {"message":"Query not found"},
        # and next candidate (H-t2v_HvFR07ZBP9aOeKoA) succeeding with 200
        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_404.text = '{"message":"Query not found"}'

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "data": {
                "create_tweet": {
                    "tweet_results": {
                        "result": {
                            "rest_id": "1999888777666"
                        }
                    }
                }
            }
        }

        with patch("requests.post", side_effect=[resp_404, resp_200]) as mock_post:
            res = submit_x_reply(reply_item, mock_x_cred)
            self.assertTrue(res["success"])
            self.assertEqual(res["comment_id"], "1999888777666")
            self.assertEqual(res["comment_url"], "https://x.com/i/status/1999888777666")
            # Verify it retried with second candidate
            self.assertEqual(mock_post.call_count, 2)

    def test_dm_pitch_generation_and_queue_follow_up_endpoints(self):
        """Test 1v1 DM pitch generation, API endpoint, and manual follow-up reply enqueueing."""
        from unittest.mock import patch
        from ai import generate_dm_pitch

        # 1. Unit test generate_dm_pitch fallback when no credential available
        with patch("ai.resolve_ai_cred", return_value=None):
            fallback_dm = generate_dm_pitch(
                title="Club Car DS 48V solenoid clicking",
                excerpt="Tested batteries at 48V, need wiring diagram",
                author="cart_owner",
                site_name="FairwayFort",
                site_url="https://fairwayfort.com/tools",
                credential=None
            )
            self.assertIn("https://fairwayfort.com/tools", fallback_dm["message"])
            self.assertTrue(len(fallback_dm["subject"]) > 5)

        # 2. Unit test generate_dm_pitch with mocked AI
        with patch("ai.run_ai_prompt", return_value="Subject: Solenoid fix for Club Car\nMessage:\nHey u/cart_owner, saw your issue with the solenoid. Here is the schematic: https://fairwayfort.com/tools"):
            ai_dm = generate_dm_pitch(
                title="Club Car DS 48V solenoid",
                excerpt="Need diagram",
                author="cart_owner",
                site_name="FairwayFort",
                site_url="https://fairwayfort.com/tools",
                credential={"type": "anthropic", "api_key": "test_key"}
            )
            self.assertEqual(ai_dm["subject"], "Solenoid fix for Club Car")
            self.assertIn("https://fairwayfort.com/tools", ai_dm["message"])

        # 3. Test POST /api/hits/{hit_id}/dm_pitch
        with get_db() as db:
            db.execute(
                """INSERT OR REPLACE INTO hits (hit_id, listener_id, subreddit, title, url, author, excerpt, filter_passed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("hit_dm_test_01", "lst_test", "golfcarts", "Motor clicking issue", "https://reddit.com/r/golfcarts/test", "cart_guy", "Need help with 36v cart", 1)
            )

        with patch("ai.run_ai_prompt", return_value="Subject: Fix\nMessage: Check schematic: https://fairwayfort.com/tools"):
            dm_resp = self.client.post("/api/hits/hit_dm_test_01/dm_pitch")
        self.assertEqual(dm_resp.status_code, 200)
        dm_json = dm_resp.json()
        self.assertTrue(dm_json.get("ok"))
        self.assertEqual(dm_json.get("author"), "cart_guy")
        self.assertIn("reddit.com/message/compose", dm_json.get("compose_url", ""))
        self.assertIn("routed_tool", dm_json)
        self.assertIn("playbook", dm_json)
        self.assertEqual(len(dm_json["playbook"]["rounds"]), 3)

        # 4. Insert queue item for queue follow-up and queue DM tests
        with get_db() as db:
            cursor = db.execute(
                """INSERT INTO reply_queue
                   (hit_id, listener_id, listener_name, subreddit, post_id, comment_id, target_id, author, reply_text, status, scheduled_at, submitted_at, is_winner)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("hit_dm_test_02", "lst_test", "Golf Radar", "golfcarts", "post_fu_99", "cmt_submitted_99", "t3_post_fu_99",
                 "cart_owner", "Earlier diagnosis: test resistor", "submitted", time.time(), time.time(), 1)
            )
            item_id = cursor.lastrowid

        # 5. Test POST /api/queue/{item_id}/dm_pitch
        with patch("ai.run_ai_prompt", return_value="Subject: Fix\nMessage: Check schematic: https://fairwayfort.com/tools"):
            queue_dm_resp = self.client.post(f"/api/queue/{item_id}/dm_pitch")
        self.assertEqual(queue_dm_resp.status_code, 200)
        q_dm_json = queue_dm_resp.json()
        self.assertTrue(q_dm_json.get("ok"))
        self.assertIn("playbook", q_dm_json)
        self.assertEqual(len(q_dm_json["playbook"]["rounds"]), 3)

        # 6. Test POST /api/queue/{item_id}/follow_up
        with patch("ai.run_ai_prompt", return_value="Here is the follow up: https://fairwayfort.com/parts"):
            fu_resp = self.client.post(f"/api/queue/{item_id}/follow_up")
        self.assertEqual(fu_resp.status_code, 200)
        fu_json = fu_resp.json()
        self.assertTrue(fu_json.get("ok"))
        self.assertIn("follow_up_id", fu_json)

        # Check DB that the new follow-up item was enqueued under target_id=t1_cmt_submitted_99
        with get_db() as db:
            fu_row = db.execute("SELECT * FROM reply_queue WHERE id=?", (fu_json["follow_up_id"],)).fetchone()
            self.assertIsNotNone(fu_row)
            self.assertEqual(fu_row["target_id"], "t1_cmt_submitted_99")
            self.assertEqual(fu_row["funnel_tier"], 1)
            self.assertIn("二轮闭环追评", fu_row["persona_label"])

    def test_universal_offers_matrix_routing_and_ai_generation(self):
        """Test universal multi-project offers matrix routing, AI generation, and ingest integration."""
        from unittest.mock import patch
        from ai import resolve_dynamic_tool_url, generate_offers_matrix_with_ai

        # 1. Custom SaaS / e-commerce offers_matrix routing
        custom_matrix = [
            {
                "key": "roi_calc",
                "name": "SaaS ROI 计算器",
                "keywords": ["roi", "cost", "pricing", "expensive", "save money"],
                "url": "/tools/roi-calculator"
            },
            {
                "key": "migration_checklist",
                "name": "一键迁移自查清单",
                "keywords": ["migration", "switch", "transfer", "migrate"],
                "url": "https://docs.mysaas.com/migration"
            }
        ]

        # Case A: Matches relative URL -> joined with base_url
        res_roi = resolve_dynamic_tool_url(
            base_url="https://mysaas.com",
            text="How much does this cost? Is the pricing worth the ROI?",
            offers_matrix=custom_matrix
        )
        self.assertEqual(res_roi["key"], "roi_calc")
        self.assertEqual(res_roi["name"], "SaaS ROI 计算器")
        self.assertEqual(res_roi["routed_url"], "https://mysaas.com/tools/roi-calculator")

        # Case B: Matches absolute URL
        res_mig = resolve_dynamic_tool_url(
            base_url="https://mysaas.com",
            text="Looking to switch and migrate from our old tool",
            offers_matrix=custom_matrix
        )
        self.assertEqual(res_mig["key"], "migration_checklist")
        self.assertEqual(res_mig["routed_url"], "https://docs.mysaas.com/migration")

        # Case C: No keyword match -> fallbacks to base_url
        res_none = resolve_dynamic_tool_url(
            base_url="https://mysaas.com",
            text="Hello everyone in the community",
            offers_matrix=custom_matrix
        )
        self.assertEqual(res_none["key"], "default")
        self.assertEqual(res_none["routed_url"], "https://mysaas.com")

        # Case D: Backward compatibility for Fairway Fort when offers_matrix is empty/None
        res_ff = resolve_dynamic_tool_url(
            base_url="https://fairwayfort.com",
            text="What year is my Club Car? Where is the serial number located?",
            offers_matrix=None
        )
        self.assertEqual(res_ff["key"], "serial_decoder")
        self.assertIn("serial-decoder", res_ff["routed_url"])

        # 2. Test generate_offers_matrix_with_ai heuristic fallback
        with patch("ai.resolve_ai_cred", return_value=None):
            offers = generate_offers_matrix_with_ai(
                site_name="CoffeePro Tools",
                site_description="Espresso grind size and extraction ratio calculators",
                site_url="https://coffeepro.com",
                keywords=["espresso", "grinder", "extraction", "ratio"]
            )
            self.assertIsInstance(offers, list)
            self.assertGreaterEqual(len(offers), 3)
            for offer in offers:
                self.assertIn("key", offer)
                self.assertIn("name", offer)
                self.assertIn("keywords", offer)
                self.assertIn("url", offer)
                self.assertTrue(len(offer["keywords"]) > 0)

        # 3. Test API endpoint POST /api/listeners/ai_generate_offers
        mock_ai_json = """[
            {"key": "grind_calc", "name": "研磨刻度换算器", "keywords": ["grind", "size", "click", "coarse", "fine"], "url": "/tools/grind-calculator"},
            {"key": "ratio_guide", "name": "粉水比黄金公式指南", "keywords": ["ratio", "brew", "water", "dose"], "url": "/tools/ratio-guide"}
        ]"""
        mock_cred = {"type": "anthropic", "api_key": "test_key"}
        with patch("ai.resolve_ai_cred", return_value=mock_cred), \
             patch("ai.run_ai_prompt", return_value=mock_ai_json):
            resp = self.client.post("/api/listeners/ai_generate_offers", json={
                "site_name": "CoffeePro",
                "site_description": "Coffee brewing calculators",
                "site_url": "https://coffeepro.com",
                "keywords": ["coffee", "espresso"]
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(len(data.get("offers_matrix")), 2)
            self.assertEqual(data["offers_matrix"][0]["key"], "grind_calc")

        # 4. Test API endpoint POST /api/listeners/ai_ingest_url returns offers_matrix
        mock_meta = {
            "brand_name": "BeanToCup SaaS",
            "page_title": "Roaster inventory and temperature profiling",
            "description": "Roaster inventory and temperature profiling",
            "url": "https://beantocup.io",
            "sample_content": "Profile your coffee beans with ease."
        }

        def mock_ai_dispatcher(prompt, *args, **kwargs):
            if "Target Customer Keywords" in prompt or "offers" in prompt.lower() or "CRO" in prompt:
                return mock_ai_json
            if "personas" in prompt.lower():
                return '[{"key": "barista", "label": "☕ 资深咖啡师", "name": "Head Barista", "tone": "Expert", "match_keywords": ["espresso"]}]'
            if "visual assets" in prompt.lower() or "infographics" in prompt.lower():
                return '[{"id": "va1", "name": "Grind Chart", "image_url": "https://img.com/1", "target_url": "https://beantocup.io", "intent_keywords": ["grind"], "caption": "Chart"}]'
            return '{"name": "Coffee Radar", "keywords": ["espresso", "grind"], "negative_keywords": [], "subreddits": "espresso,Coffee", "pitch_instruction": "Helpful"}'

        with patch("ai.resolve_ai_cred", return_value=mock_cred), \
             patch("ai.extract_metadata_from_url", return_value=mock_meta), \
             patch("ai.run_ai_prompt", side_effect=mock_ai_dispatcher):
            ingest_resp = self.client.post("/api/listeners/ai_ingest_url", json={"url": "https://beantocup.io"})
            self.assertEqual(ingest_resp.status_code, 200)
            ingest_data = ingest_resp.json()
            self.assertTrue(ingest_data.get("ok"))
            self.assertIn("data", ingest_data)
            self.assertIn("offers_matrix", ingest_data["data"])
            self.assertIsInstance(ingest_data["data"]["offers_matrix"], list)
            self.assertGreaterEqual(len(ingest_data["data"]["offers_matrix"]), 1)
            self.assertEqual(ingest_data["data"]["offers_matrix"][0]["key"], "grind_calc")


if __name__ == "__main__":
    unittest.main()
