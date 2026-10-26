import unittest
import uuid
import time
from unittest.mock import patch
from starlette.testclient import TestClient

from app import app
from db import get_db, init_db, migrate_schema
from ai import AB_STYLES, PERSONAS


class TestRoiAndAbStyles(unittest.TestCase):
    def setUp(self):
        init_db()
        migrate_schema()
        self.client = TestClient(app)
        with get_db() as db:
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'hit_ab_%' OR hit_id LIKE 'hit_q_%' OR hit_id LIKE 'hit_roi_%'")
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'hit_ab_%' OR hit_id LIKE 'hit_q_%' OR hit_id LIKE 'hit_roi_%'")

    def tearDown(self):
        with get_db() as db:
            db.execute("DELETE FROM hits WHERE title IN ('Where to buy', 'Spam post', 'Battery swap', 'Controller Issue')")
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'hit_ab_%' OR hit_id LIKE 'hit_q_%' OR hit_id LIKE 'hit_roi_%'")
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'hit_ab_%' OR hit_id LIKE 'hit_q_%' OR hit_id LIKE 'hit_roi_%'")

    def test_ab_styles_configuration(self):
        """Test that AB_STYLES presets are properly registered in ai.py."""
        self.assertIn("guru", AB_STYLES)
        self.assertIn("authentic", AB_STYLES)
        self.assertEqual(AB_STYLES["guru"]["key"], "guru")
        self.assertEqual(AB_STYLES["authentic"]["key"], "authentic")
        self.assertIn("guru", PERSONAS)
        self.assertIn("authentic", PERSONAS)
        self.assertIn("tone", AB_STYLES["guru"])
        self.assertIn("tone", AB_STYLES["authentic"])

    @patch("routes.resolve_ai_cred")
    @patch("ai.generate_multichannel_reply")
    @patch("ai.evaluate_reply_safety")
    def test_hit_switch_style_api(self, mock_safety, mock_reply, mock_cred):
        """Test POST /api/hits/{hit_id}/switch_style regenerates draft in specified persona tone."""
        mock_cred.return_value = {"id": "c_test", "provider": "deepseek", "api_key": "sk-dummy"}
        mock_reply.return_value = {
            "reply": "Mocked guru technical diagnosis with zero fluff.",
            "persona": "guru",
            "persona_label": "⚡ 极客干货向",
            "channels": {"forum": "f", "op": "o", "tweet": "t"}
        }
        mock_safety.return_value = {"verdict": "PASSED", "safety_score": 9}

        hid = f"hit_ab_{uuid.uuid4().hex[:8]}"
        with get_db() as db:
            db.execute(
                """INSERT INTO hits (hit_id, listener_id, kind, author, subreddit, title, excerpt, match_text, ts, filter_passed)
                   VALUES (?, 'lst_ab', 'post', 'golf_user', 'golf', 'Controller Issue', 'My golf cart controller shuts down randomly', 'controller', ?, 1)""",
                (hid, time.time())
            )

        resp = self.client.post(f"/api/hits/{hid}/switch_style?style=guru")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("persona"), "guru")
        self.assertIn("guru", data.get("reply_draft", "").lower())

        # Check DB was updated with new draft
        with get_db() as db:
            row = db.execute("SELECT reply_draft, persona FROM hits WHERE hit_id=?", (hid,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["reply_draft"], "Mocked guru technical diagnosis with zero fluff.")
            self.assertEqual(row["persona"], "guru")

    @patch("routes.resolve_ai_cred")
    @patch("ai.generate_multichannel_reply")
    @patch("ai.evaluate_reply_safety")
    def test_queue_switch_style_api(self, mock_safety, mock_reply, mock_cred):
        """Test POST /api/queue/{item_id}/switch_style updates queue item and underlying hit."""
        mock_cred.return_value = {"id": "c_test", "provider": "deepseek", "api_key": "sk-dummy"}
        mock_reply.return_value = {
            "reply": "Mocked authentic hands-on garage review.",
            "persona": "authentic",
            "persona_label": "🛠️ 真实测评向",
            "channels": {"forum": "f", "op": "o", "tweet": "t"}
        }
        mock_safety.return_value = {"verdict": "PASSED", "safety_score": 9}

        hid = f"hit_q_{uuid.uuid4().hex[:8]}"
        now = time.time()
        with get_db() as db:
            db.execute(
                """INSERT INTO hits (hit_id, listener_id, kind, author, subreddit, title, excerpt, match_text, ts, filter_passed)
                   VALUES (?, 'lst_q', 'post', 'diy_user', 'diy', 'Battery swap', 'Looking for recommendations', 'battery', ?, 1)""",
                (hid, now)
            )
            cur = db.execute(
                """INSERT INTO reply_queue (hit_id, platform, target_id, author, subreddit, reply_text, status, scheduled_at, created_at)
                   VALUES (?, 'reddit', 't3_123', 'diy_user', 'diy', 'Old draft text', 'pending', ?, ?)""",
                (hid, now + 3600, now)
            )
            item_id = cur.lastrowid

        resp = self.client.post(f"/api/queue/{item_id}/switch_style?style=authentic")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("item", data)
        self.assertEqual(data["item"]["reply_text"], "Mocked authentic hands-on garage review.")
        self.assertEqual(data["item"]["persona"], "authentic")

        # Verify DB persisted
        with get_db() as db:
            q_row = db.execute("SELECT reply_text, persona FROM reply_queue WHERE id=?", (item_id,)).fetchone()
            self.assertEqual(q_row["reply_text"], "Mocked authentic hands-on garage review.")
            self.assertEqual(q_row["persona"], "authentic")

    def test_stats_full_funnel_attribution_and_project_roi(self):
        """Test GET /api/stats returns complete commercial funnel metrics and multi-project ROI breakdown."""
        site_name = f"TestSite_{uuid.uuid4().hex[:6]}"
        hid_pass = f"hit_roi_pass_{uuid.uuid4().hex[:8]}"
        hid_reject = f"hit_roi_rej_{uuid.uuid4().hex[:8]}"
        now = time.time()

        with get_db() as db:
            # 1. Insert 2 hits (1 passed, 1 rejected)
            db.execute(
                """INSERT INTO hits (hit_id, listener_id, listener_name, kind, author, subreddit, title, excerpt, match_text, ts, filter_passed)
                   VALUES (?, 'lst_roi', ?, 'post', 'buyer1', 'ecommerce', 'Where to buy', 'details', 'buy', ?, 1)""",
                (hid_pass, site_name, now)
            )
            db.execute(
                """INSERT INTO hits (hit_id, listener_id, listener_name, kind, author, subreddit, title, excerpt, match_text, ts, filter_passed)
                   VALUES (?, 'lst_roi', ?, 'post', 'buyer2', 'ecommerce', 'Spam post', 'spam', 'buy', ?, 0)""",
                (hid_reject, site_name, now)
            )

            # 2. Insert reply_queue row (scheduled & published with upvotes)
            cur = db.execute(
                """INSERT INTO reply_queue (hit_id, listener_name, platform, target_id, author, subreddit, reply_text, status, scheduled_at, submitted_at, upvotes, created_at)
                   VALUES (?, ?, 'reddit', 't3_roi', 'buyer1', 'ecommerce', 'Check this solution /r/testcode', 'published', ?, ?, 5, ?)""",
                (hid_pass, site_name, now - 100, now - 50, now - 200)
            )
            queue_id = cur.lastrowid

            # 3. Insert short link & click events
            code = f"roi{uuid.uuid4().hex[:4]}"
            db.execute(
                """INSERT INTO short_links (code, target_url, final_url, platform, queue_id, hit_id, clicks, created_at)
                   VALUES (?, 'https://example.com/product', 'https://example.com/product?utm_source=reddit', 'reddit', ?, ?, 2, datetime('now'))""",
                (code, queue_id, hid_pass)
            )
            db.execute(
                """INSERT INTO link_click_events (code, ip_hash, user_agent, referer, clicked_at)
                   VALUES (?, 'hash_ip_1', 'Mozilla/5.0', 'https://reddit.com', datetime('now'))""",
                (code,)
            )
            db.execute(
                """INSERT INTO link_click_events (code, ip_hash, user_agent, referer, clicked_at)
                   VALUES (?, 'hash_ip_2', 'Mozilla/5.0', 'https://reddit.com', datetime('now'))""",
                (code,)
            )

        # 4. Query stats endpoint with project parameter
        resp = self.client.get(f"/api/stats?days=30&project={site_name}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Funnel assertions
        self.assertIn("funnel", data)
        fn = data["funnel"]
        self.assertEqual(fn["hits_captured"], 2)
        self.assertEqual(fn["ai_passed"], 1)
        self.assertEqual(fn["pass_rate"], 50.0)
        self.assertEqual(fn["scheduled"], 1)
        self.assertEqual(fn["published"], 1)
        self.assertEqual(fn["publish_rate"], 100.0)
        self.assertEqual(fn["total_upvotes"], 5)
        self.assertEqual(fn["winners"], 1)  # upvotes >= 3
        self.assertEqual(fn["total_clicks"], 2)
        self.assertEqual(fn["total_uv"], 2)

        # Projects ROI assertions
        self.assertIn("projects_roi", data)
        self.assertIsInstance(data["projects_roi"], list)
        matching = [p for p in data["projects_roi"] if p["name"] == site_name]
        self.assertTrue(len(matching) > 0)
        proj_stat = matching[0]
        self.assertEqual(proj_stat["hits"], 2)
        self.assertEqual(proj_stat["passed"], 1)
        self.assertEqual(proj_stat["published"], 1)
        self.assertEqual(proj_stat["upvotes"], 5)
        self.assertEqual(proj_stat["clicks"], 2)
        self.assertEqual(proj_stat["uv"], 2)

        # Top links assertions
        self.assertIn("top_links", data)
        top_codes = [l["code"] for l in data["top_links"]]
        self.assertIn(code, top_codes)


if __name__ == "__main__":
    unittest.main()
