import unittest
import uuid
import time
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from app import app
from db import get_db, init_db, migrate_schema
from ai import get_learned_resurrection_context
from auto_responder import record_ai_learning


class TestP2IndustrializationFeatures(unittest.TestCase):
    def setUp(self):
        init_db()
        migrate_schema()
        self.client = TestClient(app)
        with get_db() as db:
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'hit_rejected_%' OR title IN ('Title A', 'Title B', 'Overly filtered discussion')")
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'hit_rejected_%' OR hit_id LIKE 'hit_%'")

    def tearDown(self):
        with get_db() as db:
            db.execute("DELETE FROM hits WHERE hit_id LIKE 'hit_rejected_%' OR title IN ('Title A', 'Title B', 'Overly filtered discussion')")
            db.execute("DELETE FROM reply_queue WHERE hit_id LIKE 'hit_rejected_%' OR hit_id LIKE 'hit_%'")

    def test_get_projects_workspace_hub(self):
        """Test GET /api/projects aggregates workspaces correctly from listeners."""
        resp = self.client.get("/api/projects")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("projects", data)
        self.assertIsInstance(data["projects"], list)

        # Check project fields if any listener is configured
        if data["projects"]:
            p = data["projects"][0]
            self.assertIn("name", p)
            self.assertIn("listener_count", p)
            self.assertIn("today_hits", p)
            self.assertIn("today_replies", p)
            self.assertIn("total_clicks", p)
            self.assertIn("subreddits", p)
            self.assertIn("platforms", p)

    def test_workspace_isolation_hits_filtering(self):
        """Test /api/hits with project parameter filters hits strictly to the workspace."""
        proj_a = f"ProjectAlpha_{uuid.uuid4().hex[:6]}"
        proj_b = f"ProjectBeta_{uuid.uuid4().hex[:6]}"
        hid_a = f"hit_{uuid.uuid4().hex[:8]}"
        hid_b = f"hit_{uuid.uuid4().hex[:8]}"
        lst_a = f"lst_{uuid.uuid4().hex[:6]}"
        lst_b = f"lst_{uuid.uuid4().hex[:6]}"

        now = time.time()
        with get_db() as db:
            # Create two hits
            db.execute(
                """INSERT INTO hits (hit_id, listener_id, listener_name, kind, author, subreddit, title, excerpt, match_text, ts, filter_passed)
                   VALUES (?, ?, ?, 'post', 'author_a', 'golf', 'Title A', 'Excerpt A', 'keyword_a', ?, 1)""",
                (hid_a, lst_a, proj_a, now)
            )
            db.execute(
                """INSERT INTO hits (hit_id, listener_id, listener_name, kind, author, subreddit, title, excerpt, match_text, ts, filter_passed)
                   VALUES (?, ?, ?, 'post', 'author_b', 'ecommerce', 'Title B', 'Excerpt B', 'keyword_b', ?, 1)""",
                (hid_b, lst_b, proj_b, now)
            )

        # Query project A
        resp_a = self.client.get(f"/api/hits?project={proj_a}")
        self.assertEqual(resp_a.status_code, 200)
        hits_a = resp_a.json().get("hits", [])
        ids_a = [h["id"] for h in hits_a]
        self.assertIn(hid_a, ids_a)
        self.assertNotIn(hid_b, ids_a)

        # Query project B
        resp_b = self.client.get(f"/api/hits?project={proj_b}")
        self.assertEqual(resp_b.status_code, 200)
        hits_b = resp_b.json().get("hits", [])
        ids_b = [h["id"] for h in hits_b]
        self.assertIn(hid_b, ids_b)
        self.assertNotIn(hid_a, ids_b)

    @patch("routes.api_hit_one_click_engage")
    def test_false_negative_resurrection_and_ai_learning(self, mock_engage):
        """Test POST /api/hits/{hit_id}/resurrect recovers lead, enqueues draft, and learns from correction."""
        mock_engage.return_value = {
            "ok": True,
            "reply_draft": "Resurrected professional technical recommendation.",
            "funnel_tier": 2,
            "opportunity_score": 85,
            "safety_verdict": "PASSED",
            "status": "scheduled",
            "delay_minutes": 6,
            "chrono_reason": "Morning prime dispatch"
        }

        unique_sub = f"sub_{uuid.uuid4().hex[:6]}"
        unique_hid = f"hit_rejected_{uuid.uuid4().hex[:8]}"

        # Insert a rejected hit (filter_passed = 0)
        with get_db() as db:
            db.execute(
                """INSERT INTO hits (hit_id, listener_id, kind, author, subreddit, title, excerpt, match_text, ts, filter_passed)
                   VALUES (?, 'lst_1', 'post', 'dev_user', ?, 'Overly filtered discussion', 'Deep technical problem description', 'problem', ?, 0)""",
                (unique_hid, unique_sub, time.time())
            )

        # Invoke resurrection
        resp = self.client.post(f"/api/hits/{unique_hid}/resurrect")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("resurrected"))

        # Verify DB hit status updated
        with get_db() as db:
            hit = db.execute("SELECT * FROM hits WHERE hit_id=?", (unique_hid,)).fetchone()
            self.assertIsNotNone(hit)
            self.assertEqual(hit["filter_passed"], 1)

            # Verify AI Learning was persisted
            learning = db.execute(
                "SELECT * FROM ai_learnings WHERE learning_type='false_negative_correction' AND subreddit=?",
                (unique_sub,)
            ).fetchone()
            self.assertIsNotNone(learning)
            self.assertIn("人工纠偏复活", learning["title"])

        # Verify get_learned_resurrection_context outputs few-shot context
        ctx = get_learned_resurrection_context(subreddit=unique_sub, platform="reddit")
        self.assertIn("HUMAN-VALIDATED HIGH-INTENT TOPICS", ctx)
        self.assertIn("过度拦截", ctx)

    def test_account_health_quota_matrix(self):
        """Test GET /api/accounts/health returns quota usage, limits, and cooldown status."""
        resp = self.client.get("/api/accounts/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("accounts", data)
        self.assertIn("today", data)

        for acc in data.get("accounts", []):
            self.assertIn("id", acc)
            self.assertIn("name", acc)
            self.assertIn("type", acc)
            self.assertIn("today_used", acc)
            self.assertIn("daily_limit", acc)
            self.assertIn("usage_pct", acc)
            self.assertIn("status", acc)
            self.assertIn(acc["status"], ["ready", "cooling", "limit_reached", "unconfigured", "rate_limited", "quarantined"])


if __name__ == "__main__":
    unittest.main()
