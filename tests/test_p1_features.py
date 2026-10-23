import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from app import app
from db import get_db, init_db, migrate_schema
from auto_responder import create_attributed_short_link, fetch_reddit_comment_stats, record_ai_learning
from ai import get_learned_golden_templates
from telegram_bot import handle_telegram_callback


class TestP1IndustrializationFeatures(unittest.TestCase):
    def setUp(self):
        init_db()
        migrate_schema()
        self.client = TestClient(app)
        with get_db() as db:
            db.execute("DELETE FROM short_links WHERE queue_id IN (99, 101) OR hit_id LIKE 'test_%' OR hit_id LIKE 'hit_%' OR hit_id LIKE 'tg_%'")
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'test_%' OR hit_id LIKE 'tg_%' OR post_id = 't3_123456'")
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'test_%' OR hit_id LIKE 'tg_%' OR title LIKE '%golf cart enclosures%'")
            db.execute("DELETE FROM ai_learnings WHERE sample_text LIKE '%solved my slice%'")

    def tearDown(self):
        with get_db() as db:
            db.execute("DELETE FROM short_links WHERE queue_id IN (99, 101) OR hit_id LIKE 'test_%' OR hit_id LIKE 'hit_%' OR hit_id LIKE 'tg_%'")
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'test_%' OR hit_id LIKE 'tg_%' OR post_id = 't3_123456'")
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'test_%' OR hit_id LIKE 'tg_%' OR title LIKE '%golf cart enclosures%'")
            db.execute("DELETE FROM ai_learnings WHERE sample_text LIKE '%solved my slice%'")

    def test_create_attributed_short_link(self):
        """Test UTM parameter injection and short link generation."""
        res = create_attributed_short_link(
            target_url="https://fairwayfort.com/products/case",
            hit_id="test_hit_123",
            queue_id=99,
            listener_id="lst_golf",
            persona="veteran_caddie",
            platform="reddit",
            campaign="golf_discussion"
        )
        self.assertIn("code", res)
        self.assertIn("short_url", res)
        self.assertIn("final_url", res)
        self.assertTrue(res["final_url"].startswith("https://fairwayfort.com/products/case?"))
        self.assertIn("utm_source=reddit", res["final_url"])
        self.assertIn("utm_medium=social_comment", res["final_url"])
        self.assertIn("utm_campaign=golf_discussion", res["final_url"])
        self.assertIn("utm_content=veteran_caddie", res["final_url"])
        self.assertIn("utm_term=test_hit_123", res["final_url"])

        # Check DB entry
        with get_db() as db:
            row = db.execute("SELECT * FROM short_links WHERE code=?", (res["code"],)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["hit_id"], "test_hit_123")
            self.assertEqual(row["clicks"], 0)

    def test_short_link_redirect_and_uv_dedup(self):
        """Test /r/{code} 302 redirect, PV counting, and SHA-256 IP UV deduplication."""
        import uuid
        test_hit = f"hit_pvuv_{uuid.uuid4().hex[:6]}"
        link_info = create_attributed_short_link(
            target_url="https://fairwayfort.com/tool",
            hit_id=test_hit,
            queue_id=None,
            listener_id="lst_test",
            persona="expert",
            platform="reddit"
        )
        code = link_info["code"]

        # Request 1 from IP 1.2.3.4
        resp1 = self.client.get(f"/r/{code}", headers={"x-forwarded-for": "1.2.3.4"}, follow_redirects=False)
        self.assertEqual(resp1.status_code, 302)
        self.assertEqual(resp1.headers["location"], link_info["final_url"])

        # Request 2 from same IP 1.2.3.4 (should increment PV to 2, but UV stays 1)
        resp2 = self.client.get(f"/r/{code}", headers={"x-forwarded-for": "1.2.3.4"}, follow_redirects=False)
        self.assertEqual(resp2.status_code, 302)

        # Request 3 from new IP 5.6.7.8 (should increment PV to 3, UV to 2)
        resp3 = self.client.get(f"/r/{code}", headers={"x-forwarded-for": "5.6.7.8"}, follow_redirects=False)
        self.assertEqual(resp3.status_code, 302)

        # Verify in /api/analytics/links
        analytics_resp = self.client.get("/api/analytics/links")
        self.assertEqual(analytics_resp.status_code, 200)
        data = analytics_resp.json()
        self.assertTrue(data.get("ok"))
        found = next((l for l in data.get("links", []) if l["code"] == code), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["clicks"], 3)  # PV = 3
        self.assertEqual(found["uv"], 2)      # UV = 2

    def test_reddit_comment_stats_and_golden_template(self):
        """Test upvote scraping logic and golden reply template recording."""
        import json

        # 1. Test fetch_reddit_comment_stats with mock
        mock_reddit_json = [
            {"data": {"children": []}},
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "cmt_999",
                                "score": 7,
                                "replies": {
                                    "data": {
                                        "children": [
                                            {"kind": "t1"},
                                            {"kind": "t1"}
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
            upvotes, replies = fetch_reddit_comment_stats("cmt_999", "post_888", "golf")
            self.assertEqual(upvotes, 7)
            self.assertEqual(replies, 2)

        # 2. Test recording golden reply and fetching it
        record_ai_learning(
            platform="reddit",
            subreddit="golf",
            learning_type="golden_reply",
            title="🌟 高赞黄金回复样本 (+7 赞)",
            pattern="实战数据分析结合用户提问点对点解答",
            action_taken="自动沉淀为【🎯 领域专家】高转化范式",
            sample_text="This setup solved my slice issue within two range sessions."
        )

        golden_tpls_str = get_learned_golden_templates(subreddit="golf", platform="reddit")
        self.assertIn("COMMUNITY-PROVEN HIGH-UPVOTE PATTERNS", golden_tpls_str)
        self.assertIn("This setup solved my slice", golden_tpls_str)

    def test_telegram_callback_actions(self):
        """Test Telegram interactive inline keyboard callback handlers (approve, schedule, reject)."""
        test_hit_id = "tg_hit_test_001"
        with get_db() as db:
            db.execute(
                """INSERT OR REPLACE INTO hits (hit_id, listener_id, subreddit, title, excerpt, reply_draft, filter_passed)
                   VALUES (?, 'lst_tg', 'tech', 'Best lightweight stack', 'What is best?', 'FastAPI is great.', 1)""",
                (test_hit_id,)
            )

        # 1. Test schedule callback ('sc:tg_hit_test_001')
        callback_sc = {
            "id": "cb_001",
            "data": f"sc:{test_hit_id}",
            "from": {"first_name": "Developer"},
            "message": {
                "message_id": 12345,
                "chat": {"id": 987654321},
                "text": "New lead detected"
            }
        }

        with patch("telegram_bot.telegram_api_call") as mock_tg_api:
            mock_tg_api.return_value = {"ok": True}
            res_sc = handle_telegram_callback("mock_token_123", callback_sc)
            self.assertTrue(res_sc.get("ok"))
            self.assertEqual(res_sc.get("status"), "scheduled")

        # Verify queue was populated
        with get_db() as db:
            q_row = db.execute("SELECT * FROM reply_queue WHERE hit_id=?", (test_hit_id,)).fetchone()
            self.assertIsNotNone(q_row)
            self.assertIn(q_row["status"], ["scheduled", "needs_review"])

        # 2. Test reject callback ('rj:tg_hit_test_002')
        test_hit_id_2 = "tg_hit_test_002"
        with get_db() as db:
            db.execute(
                """INSERT OR REPLACE INTO hits (hit_id, listener_id, subreddit, title, excerpt, filter_passed)
                   VALUES (?, 'lst_tg', 'tech', 'Another post', 'Spam question', 1)""",
                (test_hit_id_2,)
            )

        callback_rj = {
            "id": "cb_002",
            "data": f"rj:{test_hit_id_2}",
            "from": {"first_name": "Admin"},
            "message": {
                "message_id": 12346,
                "chat": {"id": 987654321},
                "text": "Lead notification"
            }
        }

        with patch("telegram_bot.telegram_api_call") as mock_tg_api:
            mock_tg_api.return_value = {"ok": True}
            res_rj = handle_telegram_callback("mock_token_123", callback_rj)
            self.assertTrue(res_rj.get("ok"))
            self.assertEqual(res_rj.get("status"), "ignored")

        with get_db() as db:
            h_row = db.execute("SELECT status FROM hits WHERE hit_id=?", (test_hit_id_2,)).fetchone()
            self.assertEqual(h_row["status"], "ignored")

    def test_hit_timestamps_and_thread_endpoint(self):
        """Test timestamp accuracy, created_at inclusion, and /api/reddit/thread timestamp propagation."""
        test_hit_id = "test_hit_ts_001"
        test_ts = 1790472417.27
        with get_db() as db:
            db.execute(
                """INSERT OR REPLACE INTO hits (hit_id, listener_id, subreddit, title, excerpt, ts, filter_passed, platform)
                   VALUES (?, 'lst_ts', 'tech', 'Test Post for Timestamps', 'Excerpt here', ?, 1, 'reddit')""",
                (test_hit_id, test_ts)
            )

        # 1. Fetch via /api/hits
        resp = self.client.get("/api/hits?q=Test+Post+for+Timestamps")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        matching = [h for h in data.get("hits", []) if h["id"] == test_hit_id]
        self.assertTrue(len(matching) > 0)
        hit = matching[0]
        self.assertAlmostEqual(hit["ts"], test_ts, places=1)
        self.assertIn("created_at", hit)
        self.assertTrue(len(hit["created_at"]) >= 10)

        # 2. Fetch via /api/reddit/thread
        thread_resp = self.client.get(f"/api/reddit/thread?post_id={test_hit_id}")
        self.assertEqual(thread_resp.status_code, 200)
        t_data = thread_resp.json()
        self.assertEqual(t_data.get("post_id"), test_hit_id)
        self.assertAlmostEqual(t_data.get("ts"), test_ts, places=1)
        self.assertIn("created_at", t_data)

    def test_dynamic_intent_landing_page_routing(self):
        """Test intelligent landing page routing and golden template retrieval based on lead intent."""
        from auto_responder import resolve_target_landing_page

        # 1. Routing test: cover / roof -> calculator
        calc_url = resolve_target_landing_page(
            "https://fairwayfort.com/pages/tools",
            title="Looking for an Evolution D5 winter storage cover",
            text="Anyone know the roof dimensions?"
        )
        self.assertEqual(calc_url, "https://fairwayfort.com/pages/golf-cart-roof-cover-calculator")

        # 2. Routing test: vin / legal -> tools
        tools_url = resolve_target_landing_page(
            "https://fairwayfort.com/pages/golf-cart-roof-cover-calculator",
            title="Need to find my Club Car serial number and VIN",
            text="How do I get DMV title for street legal cart?"
        )
        self.assertEqual(tools_url, "https://fairwayfort.com/pages/tools")

        # 3. Short link creation with dynamic routing
        link_res = create_attributed_short_link(
            target_url="https://fairwayfort.com/pages/tools",
            hit_id="hit_d5_cover",
            title="Evolution D5 Ranger 4 passenger cover fitment",
            text="Need to prevent tearing at rear footrest",
            listener_name="Fairway Fort"
        )
        self.assertIn("golf-cart-roof-cover-calculator", link_res["final_url"])

        # 4. Golden template query-based match
        golden_str = get_learned_golden_templates(subreddit="golfcarts", query_text="Evolution D5 canopy")
        self.assertIn("Evolution D5", golden_str)

    def test_auto_queue_timestamps_and_post_attribution(self):
        """Test queue lifecycle timestamps (updated_at, failed_at), original post attribution, and status counts."""
        import time
        from auto_responder import enqueue_reply

        hit_id = f"test_q_hit_{int(time.time())}"
        post_title = "Need recommendations for durable all-weather golf cart enclosures"
        post_url = "https://reddit.com/r/golfcarts/comments/123456/need_recommendations"
        post_ts = 1790472400.0

        with get_db() as db:
            db.execute(
                """INSERT OR REPLACE INTO hits (hit_id, listener_id, subreddit, title, excerpt, url, ts, filter_passed, platform)
                   VALUES (?, 'lst_queue_test', 'golfcarts', ?, 'Excerpt text here', ?, ?, 1, 'reddit')""",
                (hit_id, post_title, post_url, post_ts)
            )

        qid = enqueue_reply(
            hit_id=hit_id,
            listener_id="lst_queue_test",
            listener_name="Fairway Fort",
            subreddit="golfcarts",
            post_id="t3_123456",
            target_id="t3_123456",
            author="golf_enthusiast",
            reply_text="We tested several enclosures and found heavy-duty vinyl holds up best in freezing temps.",
            target_url=post_url,
            platform="reddit",
            scheduled_delay_seconds=600,
            status="scheduled"
        )
        self.assertIsNotNone(qid)

        # 1. Fetch via /api/queue and verify joined original post info + updated_at + status_counts
        resp = self.client.get("/api/queue")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status_counts", data)
        self.assertIn("all", data["status_counts"])
        self.assertIn("scheduled", data["status_counts"])
        self.assertIn("submitted", data["status_counts"])
        self.assertIn("failed", data["status_counts"])
        self.assertGreaterEqual(data["status_counts"]["scheduled"], 1)

        items = data.get("items", [])
        queued_items = [it for it in items if it["id"] == qid]
        self.assertTrue(len(queued_items) > 0)
        q_item = queued_items[0]
        self.assertEqual(q_item["post_title"], post_title)
        self.assertEqual(q_item["hit_url"], post_url)
        self.assertAlmostEqual(q_item["post_ts"], post_ts, places=1)
        self.assertIsNotNone(q_item.get("updated_at"))
        self.assertGreater(q_item["updated_at"], 0)

        # 2. Test cancel item updates updated_at and status
        cancel_resp = self.client.post(f"/api/queue/{qid}/cancel")
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertTrue(cancel_resp.json().get("ok"))

        with get_db() as db:
            row = db.execute("SELECT status, updated_at FROM reply_queue WHERE id=?", (qid,)).fetchone()
            self.assertEqual(row["status"], "cancelled")
            cancelled_updated_at = row["updated_at"]
            self.assertIsNotNone(cancelled_updated_at)

        # 3. Test retry item updates status to scheduled, scheduled_at, and updated_at
        time.sleep(0.01)
        retry_resp = self.client.post(f"/api/queue/{qid}/retry")
        self.assertEqual(retry_resp.status_code, 200)
        self.assertTrue(retry_resp.json().get("ok"))

        with get_db() as db:
            row = db.execute("SELECT status, updated_at, scheduled_at FROM reply_queue WHERE id=?", (qid,)).fetchone()
            self.assertEqual(row["status"], "scheduled")
            self.assertGreaterEqual(row["updated_at"], cancelled_updated_at)
            self.assertGreater(row["scheduled_at"], time.time() - 10)

    def test_reddit_api_error_parsing_and_archival_guard(self):
        """Test parsing of Reddit structured errors (TOO_OLD, RATELIMIT) and archival retry blocking."""
        from auto_responder import parse_reddit_api_errors

        # 1. Test TOO_OLD parse
        errors_old = [['TOO_OLD', "that's a piece of history now; it's too late to reply to it", 'parent']]
        res_old = parse_reddit_api_errors(errors_old)
        self.assertTrue(res_old["is_archived"])
        self.assertFalse(res_old["is_rate_limited"])
        self.assertIn("原帖已被 Reddit 归档", res_old["error_message"])

        # 2. Test RATELIMIT parse with minutes extraction
        errors_rl = [['RATELIMIT', "Looks like you've been doing that a lot. Take a break for 8 minutes before trying again.", 'ratelimit']]
        res_rl = parse_reddit_api_errors(errors_rl)
        self.assertFalse(res_rl["is_archived"])
        self.assertTrue(res_rl["is_rate_limited"])
        self.assertGreaterEqual(res_rl["wait_seconds"], 480)
        self.assertIn("触发 Reddit 官方频控保护", res_rl["error_message"])

        # 3. Test combined TOO_OLD + RATELIMIT
        errors_combined = errors_old + errors_rl
        res_combined = parse_reddit_api_errors(errors_combined)
        self.assertTrue(res_combined["is_archived"])
        self.assertTrue(res_combined["is_rate_limited"])
        self.assertIn("原帖已被 Reddit 归档", res_combined["error_message"])
        self.assertIn("触发 Reddit 官方频控保护", res_combined["error_message"])

        # 4. Test archival guard on /api/queue/{id}/retry
        with get_db() as db:
            cur = db.execute(
                """INSERT INTO reply_queue (hit_id, listener_id, status, is_archived, error_message, reply_text)
                   VALUES ('test_archived_guard', 'lst_test', 'failed', 1, 'TOO_OLD', 'Test reply')"""
            )
            archived_qid = cur.lastrowid

        retry_resp = self.client.post(f"/api/queue/{archived_qid}/retry")
        self.assertEqual(retry_resp.status_code, 200)
        self.assertFalse(retry_resp.json().get("ok"))
        self.assertIn("已被官方归档或锁定", retry_resp.json().get("error", ""))


if __name__ == "__main__":
    unittest.main()
