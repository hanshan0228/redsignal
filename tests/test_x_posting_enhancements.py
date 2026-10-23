import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from app import app
from db import get_db, init_db, migrate_schema
from auto_responder import (
    calc_tweet_weighted_length,
    truncate_tweet_text,
    submit_x_reply,
    check_rolling_link_ratio,
    fetch_latest_x_create_tweet_query_id
)


class TestXPostingEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        migrate_schema()
        cls.client = TestClient(app)

    def setUp(self):
        with get_db() as db:
            db.execute("DELETE FROM reply_queue WHERE credential_id LIKE 'test_x_post_%'")

    def tearDown(self):
        with get_db() as db:
            db.execute("DELETE FROM reply_queue WHERE credential_id LIKE 'test_x_post_%'")

    def test_calc_tweet_weighted_length(self):
        """Test Twitter character weighting according to official spec."""
        # 1. Plain ASCII: 1 weight per char
        text_ascii = "Hello world!"
        self.assertEqual(calc_tweet_weighted_length(text_ascii), 12)

        # 2. CJK / Chinese: 2 weight per char
        text_cjk = "高尔夫球车"
        self.assertEqual(calc_tweet_weighted_length(text_cjk), 10)

        # 3. URL: Always 23 weight regardless of raw string length
        long_url = "https://fairwayfort.com/tools/very/long/deep/linked/path/with/parameters?tracking=utm_source_123"
        self.assertEqual(calc_tweet_weighted_length(long_url), 23)

        # 4. Mixed: 9 CJK (18) + 1 space (1) + URL (23) = 42 weight
        mixed = "高尔夫球车电瓶指南 " + long_url
        self.assertEqual(calc_tweet_weighted_length(mixed), 18 + 1 + 23)

        # 5. Empty
        self.assertEqual(calc_tweet_weighted_length(""), 0)

    def test_truncate_tweet_text(self):
        """Test smart truncation ensuring result fits within max weight."""
        # 1. Under limit: unaffected
        short_text = "Standard concise troubleshooting reply."
        self.assertEqual(truncate_tweet_text(short_text, max_weight=280), short_text)

        # 2. Over limit: truncated safely
        huge_text = "word " * 100  # 500 characters
        truncated = truncate_tweet_text(huge_text, max_weight=280)
        self.assertTrue(truncated.endswith("..."))
        self.assertLessEqual(calc_tweet_weighted_length(truncated), 280)

        # 3. Long Chinese text over limit
        huge_cjk = "这是高尔夫球车深度维修排查指南针对电机与控制器电路故障的完整解析" * 15
        truncated_cjk = truncate_tweet_text(huge_cjk, max_weight=280)
        self.assertTrue(truncated_cjk.endswith("..."))
        self.assertLessEqual(calc_tweet_weighted_length(truncated_cjk), 280)

    def test_x_rolling_link_ratio_downgrade(self):
        """Test X posting automatically downgrades links to profile bio referral when link ratio > 20%."""
        cred_id = "test_x_post_rlr_cred"
        # Seed 1 post with link and 2 posts without link -> 1/3 = 33% (> 20%)
        with get_db() as db:
            db.execute(
                "INSERT INTO reply_queue (hit_id, credential_id, reply_text, status) VALUES ('hit1', ?, 'https://link.com', 'submitted')",
                (cred_id,)
            )
            db.execute(
                "INSERT INTO reply_queue (hit_id, credential_id, reply_text, status) VALUES ('hit2', ?, 'Pure text advice', 'submitted')",
                (cred_id,)
            )
            db.execute(
                "INSERT INTO reply_queue (hit_id, credential_id, reply_text, status) VALUES ('hit3', ?, 'Another text advice', 'submitted')",
                (cred_id,)
            )

        mock_cred = {
            "id": cred_id,
            "type": "x",
            "api_key": "k",
            "api_secret": "s",
            "access_token": "a",
            "access_token_secret": "as"
        }
        reply_item = {
            "reply_text": "Check out the tool at https://fairwayfort.com/tools/battery for details.",
            "target_id": "189283746592837465",
            "site_name": "Fairway Fort"
        }

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"data": {"id": "1234567890"}}
            mock_post.return_value = mock_resp

            res = submit_x_reply(reply_item, mock_cred)
            self.assertTrue(res["success"])

            # Verify the text posted through API had URL stripped and bio referral added
            sent_payload = mock_post.call_args[1]["json"]
            sent_text = sent_payload["text"]
            self.assertNotIn("https://", sent_text)
            self.assertIn("bio", sent_text.lower())

    def test_x_quote_tweet_dispatch_oauth(self):
        """Test Quote Tweet dispatch under OAuth 1.0a sends quote_tweet_id."""
        mock_cred = {
            "id": "test_x_post_quote_cred",
            "type": "x",
            "api_key": "k",
            "api_secret": "s",
            "access_token": "a",
            "access_token_secret": "as"
        }
        reply_item = {
            "reply_text": "Adding key context to this discussion.",
            "target_id": "999888777666",
            "is_quote_tweet": True
        }

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"data": {"id": "111222333444"}}
            mock_post.return_value = mock_resp

            res = submit_x_reply(reply_item, mock_cred)
            self.assertTrue(res["success"])

            sent_payload = mock_post.call_args[1]["json"]
            self.assertEqual(sent_payload.get("quote_tweet_id"), "999888777666")
            self.assertNotIn("reply", sent_payload)

    def test_x_quote_tweet_dispatch_web_graphql(self):
        """Test Quote Tweet dispatch under Web GraphQL sets attachment_url."""
        mock_cred = {
            "id": "test_x_post_quote_web",
            "type": "x",
            "auth_token": "mock_auth",
            "ct0": "mock_ct0",
            "query_id": "MockQid123"
        }
        reply_item = {
            "reply_text": "Adding key context via Web GraphQL.",
            "target_id": "888777666555",
            "is_quote_tweet": True
        }

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "data": {
                    "create_tweet": {
                        "tweet_results": {
                            "result": {
                                "rest_id": "555666777"
                            }
                        }
                    }
                }
            }
            mock_post.return_value = mock_resp

            res = submit_x_reply(reply_item, mock_cred)
            self.assertTrue(res["success"])

            sent_payload = mock_post.call_args[1]["json"]
            variables = sent_payload["variables"]
            self.assertEqual(variables.get("attachment_url"), "https://x.com/i/status/888777666555")
            self.assertNotIn("reply", variables)

    def test_x_2_tweet_thread_dispatch(self):
        """Test 2-Tweet Thread posting chains the 2nd tweet to the 1st tweet."""
        mock_cred = {
            "id": "test_x_post_thread_cred",
            "type": "x",
            "api_key": "k",
            "api_secret": "s",
            "access_token": "a",
            "access_token_secret": "as"
        }
        reply_item = {
            "reply_text": "Tweet 1: Pure technical troubleshooting analysis.",
            "thread_reply_text": "Tweet 2: Grab the wiring diagram tool here: https://fairwayfort.com/chart",
            "target_id": "1234567890"
        }

        resp_tweet1 = MagicMock()
        resp_tweet1.status_code = 201
        resp_tweet1.json.return_value = {"data": {"id": "100000000001"}}

        resp_tweet2 = MagicMock()
        resp_tweet2.status_code = 201
        resp_tweet2.json.return_value = {"data": {"id": "100000000002"}}

        with patch("requests.post", side_effect=[resp_tweet1, resp_tweet2]) as mock_post:
            res = submit_x_reply(reply_item, mock_cred)
            self.assertTrue(res["success"])
            self.assertEqual(res["comment_id"], "100000000001")
            self.assertEqual(res["thread_comment_id"], "100000000002")
            self.assertEqual(mock_post.call_count, 2)

            # Check 2nd tweet was posted in reply to 1st tweet
            second_call_payload = mock_post.call_args_list[1][1]["json"]
            self.assertEqual(second_call_payload["reply"]["in_reply_to_tweet_id"], "100000000001")
            self.assertIn("https://fairwayfort.com/chart", second_call_payload["text"])

    def test_x_web_graphql_rate_limit_cooldown(self):
        """Test that X 344/226 rate limit error triggers official rate limit cooldown in check_rate_limits."""
        from auto_responder import record_rate_limit_cooldown, check_rate_limits
        cred_id = "test_x_post_cooldown_cred"
        try:
            # Record 3600s cooldown
            record_rate_limit_cooldown(cred_id, 3600, "Test X Cooldown")
            allowed, reason = check_rate_limits(cred_id)
            self.assertFalse(allowed)
            self.assertIn("平台官方频控保护", reason)
        finally:
            with get_db() as db:
                db.execute("DELETE FROM account_quota WHERE credential_id=?", (cred_id,))

    def test_x_web_graphql_browser_headers(self):
        """Test that X Web GraphQL submission sends full realistic browser headers."""
        mock_cred = {
            "id": "test_x_post_headers_cred",
            "type": "x",
            "auth_token": "mock_token",
            "ct0": "mock_ct0"
        }
        reply_item = {
            "reply_text": "Troubleshooting packet drops on peering links.",
            "target_id": "1999888777"
        }
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "data": {"create_tweet": {"tweet_results": {"result": {"rest_id": "123456"}}}}
            }
            mock_post.return_value = mock_resp

            res = submit_x_reply(reply_item, mock_cred)
            self.assertTrue(res["success"])

            headers = mock_post.call_args[1]["headers"]
            self.assertEqual(headers.get("origin"), "https://x.com")
            self.assertEqual(headers.get("referer"), "https://x.com/i/status/1999888777")
            self.assertEqual(headers.get("sec-fetch-site"), "same-origin")
            self.assertIn("Chrome/131", headers.get("user-agent"))

    def test_x_web_consecutive_link_guard(self):
        """Test that Web Cookie X session auto-downgrades if previous tweet already contained an external link."""
        cred_id = "test_x_post_consec_cred"
        with get_db() as db:
            db.execute(
                "INSERT INTO reply_queue (hit_id, credential_id, platform, reply_text, status) VALUES ('hit_prev', ?, 'x', 'Check guide: https://prev-link.com', 'submitted')",
                (cred_id,)
            )

        mock_cred = {
            "id": cred_id,
            "type": "x",
            "auth_token": "mock_token",
            "ct0": "mock_ct0"
        }
        reply_item = {
            "reply_text": "BGP SLA is required. Full guide at: https://github.com/my-tool/guide",
            "target_id": "111222333"
        }

        try:
            with patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "data": {"create_tweet": {"tweet_results": {"result": {"rest_id": "999888"}}}}
                }
                mock_post.return_value = mock_resp

                res = submit_x_reply(reply_item, mock_cred)
                self.assertTrue(res["success"])

                # Verify URL was stripped and bio pinned referral added
                sent_text = mock_post.call_args[1]["json"]["variables"]["tweet_text"]
                self.assertNotIn("https://", sent_text)
                self.assertIn("bio", sent_text.lower())
        finally:
            with get_db() as db:
                db.execute("DELETE FROM reply_queue WHERE credential_id=?", (cred_id,))

    def test_delayed_visibility_check_credential_isolation(self):
        """Test that shadowban quarantine in _delayed_visibility_check is strictly isolated to the posting account."""
        import asyncio
        from auto_responder import _delayed_visibility_check
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        cred_a = "test_cred_isolate_a"
        cred_b = "test_cred_isolate_b"
        qid = 999988

        with get_db() as db:
            db.execute("INSERT OR REPLACE INTO account_quota (credential_id, account_name, date_str, consecutive_shadowbans, is_quarantined) VALUES (?, 'A', ?, 1, 0)", (cred_a, today))
            db.execute("INSERT OR REPLACE INTO account_quota (credential_id, account_name, date_str, consecutive_shadowbans, is_quarantined) VALUES (?, 'B', ?, 0, 0)", (cred_b, today))
            db.execute("INSERT OR REPLACE INTO reply_queue (id, hit_id, credential_id, reply_text, status) VALUES (?, 'hit_iso', ?, 'Test text', 'submitted')", (qid, cred_a))

        try:
            with patch("auto_responder.check_comment_visibility", return_value=False), \
                 patch("auto_responder.record_ai_learning") as mock_learn, \
                 patch("asyncio.sleep", return_value=None):
                asyncio.run(_delayed_visibility_check(qid, "https://old.reddit.com/r/test/comments/1/x/c1", "c1"))

            with get_db() as db:
                row_a = db.execute("SELECT consecutive_shadowbans, is_quarantined FROM account_quota WHERE credential_id=?", (cred_a,)).fetchone()
                row_b = db.execute("SELECT consecutive_shadowbans, is_quarantined FROM account_quota WHERE credential_id=?", (cred_b,)).fetchone()

                # Account A should have consecutive_shadowbans incremented to 2 and quarantined
                self.assertEqual(row_a["consecutive_shadowbans"], 2)
                self.assertEqual(row_a["is_quarantined"], 1)

                # Account B should be completely unaffected!
                self.assertEqual(row_b["consecutive_shadowbans"], 0)
                self.assertEqual(row_b["is_quarantined"], 0)
        finally:
            with get_db() as db:
                db.execute("DELETE FROM account_quota WHERE credential_id IN (?, ?)", (cred_a, cred_b))
                db.execute("DELETE FROM reply_queue WHERE id=?", (qid,))
                db.execute("DELETE FROM ai_learnings WHERE sample_text LIKE 'Test text%'")

    def test_reddit_http_429_rate_limiting(self):
        """Test that submit_reddit_reply recognizes HTTP 429 as rate limited with retry cooldown."""
        from auto_responder import submit_reddit_reply
        mock_cred = {
            "id": "test_reddit_429_cred",
            "type": "reddit",
            "cookie": "reddit_session=mock_sess;"
        }
        reply_item = {
            "reply_text": "Good technical comparison between golf cart models.",
            "target_id": "t3_post123"
        }

        with patch("requests.Session.get") as mock_get, patch("requests.Session.post") as mock_post:
            me_resp = MagicMock()
            me_resp.status_code = 200
            me_resp.json.return_value = {"data": {"modhash": "mock_modhash"}}
            mock_get.return_value = me_resp

            post_resp = MagicMock()
            post_resp.status_code = 429
            post_resp.text = "Too Many Requests"
            post_resp.headers = {"Retry-After": "480"}
            mock_post.return_value = post_resp

            res = submit_reddit_reply(reply_item, mock_cred)
            self.assertFalse(res["success"])
            self.assertTrue(res["is_rate_limited"])
            self.assertEqual(res["wait_seconds"], 480)
            self.assertIn("429 Too Many Requests", res["error"])

    def test_submit_now_rate_limit_blocking(self):
        """Test that /api/queue/{item_id}/submit_now blocks submission when credential has active rate limit cooldown."""
        from starlette.testclient import TestClient
        from app import app
        from auto_responder import record_rate_limit_cooldown
        client = TestClient(app)

        cred_id = "test_submit_now_blocked_cred"
        qid = 999977

        with get_db() as db:
            db.execute("INSERT OR REPLACE INTO reply_queue (id, hit_id, credential_id, platform, reply_text, status) VALUES (?, 'hit_sn_test', ?, 'x', 'Test draft', 'scheduled')", (qid, cred_id))

        try:
            record_rate_limit_cooldown(cred_id, 3600, "Blocked Account")

            with patch("config.load_config") as mock_cfg:
                mock_cfg.return_value = {
                    "listeners": [{"id": "lst1", "platform": "x", "x_credential_id": cred_id}],
                    "credentials": [{"id": cred_id, "type": "x", "auth_token": "tok", "ct0": "ct"}]
                }
                resp = client.post(f"/api/queue/{qid}/submit_now")
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertFalse(data["ok"])
                self.assertTrue(data.get("rate_limited"))
                self.assertIn("安全保护中", data["error"])
        finally:
            with get_db() as db:
                db.execute("DELETE FROM account_quota WHERE credential_id=?", (cred_id,))
                db.execute("DELETE FROM reply_queue WHERE id=?", (qid,))
