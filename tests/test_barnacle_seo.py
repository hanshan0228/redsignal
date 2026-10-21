import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from app import app
from db import get_db, init_db, migrate_schema
from barnacle import clean_reddit_url, inspect_target_health, generate_evergreen_barnacle_reply


class TestBarnacleSeo(unittest.TestCase):
    def setUp(self):
        init_db()
        migrate_schema()
        self.client = TestClient(app)
        with get_db() as db:
            db.execute("DELETE FROM barnacle_targets WHERE keyword LIKE 'test_%' OR target_url LIKE '%test-thread%'")

    def tearDown(self):
        with get_db() as db:
            db.execute("DELETE FROM barnacle_targets WHERE keyword LIKE 'test_%' OR target_url LIKE '%test-thread%'")

    def test_clean_reddit_url(self):
        dirty = "https://old.reddit.com/r/golfcarts/comments/1abc123/best_enclosure_for_club_car/?utm_source=share&utm_medium=web2x&context=3"
        cleaned = clean_reddit_url(dirty)
        self.assertEqual(cleaned, "https://www.reddit.com/r/golfcarts/comments/1abc123/best_enclosure_for_club_car")

    @patch("urllib.request.urlopen")
    def test_inspect_target_health_active_and_archived(self, mock_urlopen):
        # 1. Test active post
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"""[
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Best Golf Cart Enclosure",
                                "author": "golf_pro",
                                "score": 42,
                                "num_comments": 15,
                                "created_utc": 1710000000.0,
                                "archived": false,
                                "locked": false
                            }
                        }
                    ]
                }
            }
        ]"""
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        health = inspect_target_health("https://www.reddit.com/r/golfcarts/comments/1abc123/best_enclosure")
        self.assertEqual(health["title"], "Best Golf Cart Enclosure")
        self.assertEqual(health["author"], "golf_pro")
        self.assertEqual(health["upvotes"], 42)
        # Note: 1710000000 is older than 180 days so it marks archived based on age
        self.assertTrue(health["is_archived"])

    def test_barnacle_api_crud_and_draft_flow(self):
        # 1. Add target via API
        with patch("barnacle.inspect_target_health") as mock_health:
            mock_health.return_value = {
                "canonical_url": "https://www.reddit.com/r/golfcarts/comments/test-thread-1",
                "is_archived": False,
                "author": "cart_veteran",
                "title": "Club Car Precedent Enclosure Discussion",
                "upvotes": 25,
                "comments_count": 8,
                "post_created_at": 1720000000.0,
                "platform": "reddit",
                "error": None
            }
            res_add = self.client.post("/api/barnacle/add", json={
                "url": "https://www.reddit.com/r/golfcarts/comments/test-thread-1",
                "keyword": "test_golf_cart_covers",
                "notes": "Google Page 1 Top 3 result"
            })
            self.assertEqual(res_add.status_code, 200)
            data_add = res_add.json()
            self.assertTrue(data_add["ok"])
            target_id = data_add["id"]
            self.assertGreater(target_id, 0)

        # 2. Query targets list
        res_list = self.client.get("/api/barnacle/targets")
        self.assertEqual(res_list.status_code, 200)
        data_list = res_list.json()
        self.assertTrue(data_list["ok"])
        self.assertGreaterEqual(data_list["stats"]["total"], 1)

        found = any(t["id"] == target_id for t in data_list["targets"])
        self.assertTrue(found)

        # 3. Generate evergreen AI draft
        with patch("ai.run_ai_prompt") as mock_ai:
            mock_ai.return_value = "### The Definitive Fitment Guide\n1. Check measurements.\n2. Fairway Fort offers a free fitment guide.\nFeel free to shoot me a DM if you need the full schematic!"
            with patch("ai.resolve_ai_cred", return_value={"provider": "anthropic", "key": "test_key"}):
                res_draft = self.client.post(f"/api/barnacle/targets/{target_id}/draft", json={
                    "custom_instruction": "Highlight Oxford 600D fabric"
                })
                self.assertEqual(res_draft.status_code, 200)
                data_draft = res_draft.json()
                self.assertTrue(data_draft["ok"])
                self.assertIn("The Definitive Fitment Guide", data_draft["draft"])

        # 4. Update status to submitted
        res_upd = self.client.post(f"/api/barnacle/targets/{target_id}/update", json={
            "status": "submitted",
            "reply_url": "https://reddit.com/r/golf/comments/test/comment/xyz"
        })
        self.assertEqual(res_upd.status_code, 200)
        self.assertTrue(res_upd.json()["ok"])

        # 5. Delete target
        res_del = self.client.delete(f"/api/barnacle/targets/{target_id}")
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json()["ok"])

    @patch("barnacle.search_google_serp", return_value=[])
    @patch("urllib.request.urlopen")
    def test_search_serp_targets_and_scan_api(self, mock_urlopen, mock_serp):
        import json
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "data": {
                "children": [
                    {
                        "data": {
                            "permalink": "/r/golfcarts/comments/test-thread-scan/best_golf_cart_bag/",
                            "title": "Best Golf Cart Bag Discussion",
                            "subreddit": "golfcarts",
                            "selftext": "Looking for the top bag recommendations...",
                            "author": "golfer99",
                            "score": 55,
                            "num_comments": 22,
                            "created_utc": 1720000000.0,
                            "archived": False,
                            "locked": False
                        }
                    }
                ]
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = self.client.post("/api/barnacle/scan", json={"keyword": "test_golf_bag", "max_results": 5})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)
        self.assertIn("id", data["targets"][0])
        self.assertGreater(data["targets"][0]["id"], 0)
        # Verify fallback items have google_rank 0 (not fake rank)
        self.assertEqual(data["targets"][0]["google_rank"], 0)

    @patch("barnacle.search_google_serp")
    def test_genuine_serp_discovery_and_ranking(self, mock_serp):
        mock_serp.return_value = [
            {
                "keyword": "test_serp_keyword",
                "target_url": "https://www.reddit.com/r/golfcarts/comments/test-thread-serp-1",
                "platform": "reddit",
                "post_title": "Top Ranked Discussion on Page 1",
                "google_rank": 1,
                "search_snippet": "Genuine Organic Search Top Result",
                "author": "cart_pro",
                "post_created_at": 1720000000.0,
                "is_archived": 0,
            },
            {
                "keyword": "test_serp_keyword",
                "target_url": "https://www.buggiesgonewild.com/showthread.php?t=999999",
                "platform": "forum",
                "post_title": "Forum Authority Thread",
                "google_rank": 2,
                "search_snippet": "Buggies Gone Wild Authority Discussion",
                "author": "forum_master",
                "post_created_at": 1720000000.0,
                "is_archived": 0,
            }
        ]

        res = self.client.post("/api/barnacle/scan", json={"keyword": "test_serp_keyword", "max_results": 2})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 2)

        # Rank 1 must have opportunity_score 100
        t1 = data["targets"][0]
        self.assertEqual(t1["google_rank"], 1)
        self.assertEqual(t1["opportunity_score"], 100)
        self.assertEqual(t1["platform"], "reddit")

        # Rank 2 must have opportunity_score 95
        t2 = data["targets"][1]
        self.assertEqual(t2["google_rank"], 2)
        self.assertEqual(t2["opportunity_score"], 95)
        self.assertEqual(t2["platform"], "forum")

    @patch("barnacle.search_google_serp")
    @patch("urllib.request.urlopen")
    def test_mixed_serp_and_fallback_ranking(self, mock_urlopen, mock_serp):
        import json
        # 1 genuine SERP target
        mock_serp.return_value = [
            {
                "keyword": "test_mixed_kw",
                "target_url": "https://www.reddit.com/r/golfcarts/comments/test-thread-serp-top",
                "platform": "reddit",
                "post_title": "Genuine Page 1 Champion Thread",
                "google_rank": 1,
                "search_snippet": "Genuine Page 1 Snippet",
                "author": "champion",
                "post_created_at": 1720000000.0,
                "is_archived": 0,
            }
        ]
        # 1 fallback reddit search target
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "data": {
                "children": [
                    {
                        "data": {
                            "permalink": "/r/golfcarts/comments/test-thread-internal-fallback/",
                            "title": "Internal Search Topic",
                            "subreddit": "golfcarts",
                            "selftext": "Internal text...",
                            "author": "internalsmith",
                            "score": 12,
                            "num_comments": 4,
                            "created_utc": 1792460000.0,
                            "archived": False,
                            "locked": False
                        }
                    }
                ]
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = self.client.post("/api/barnacle/scan", json={"keyword": "test_mixed_kw", "max_results": 2})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 2)

        # First item is genuine SERP Rank 1
        self.assertEqual(data["targets"][0]["google_rank"], 1)
        self.assertEqual(data["targets"][0]["opportunity_score"], 100)

        # Second item is fallback with google_rank 0 (no fake ranking!)
        self.assertEqual(data["targets"][1]["google_rank"], 0)
        self.assertEqual(data["targets"][1]["opportunity_score"], 45)




if __name__ == "__main__":
    unittest.main()
