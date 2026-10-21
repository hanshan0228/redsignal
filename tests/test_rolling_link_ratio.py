import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from app import app
from db import get_db, init_db, migrate_schema
from auto_responder import (
    check_rolling_link_ratio,
    downgrade_reply_links_to_brand_search,
    get_account_maturity_tier
)
from barnacle import search_google_serp, hunt_and_auto_draft_barnacle


class TestRollingLinkRatioAndBarnacleHunt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        migrate_schema()
        cls.client = TestClient(app)

    def setUp(self):
        with get_db() as db:
            db.execute("DELETE FROM reply_queue WHERE credential_id LIKE 'test_rlr_%'")
            db.execute("DELETE FROM barnacle_targets WHERE keyword LIKE 'test_hunt_%'")

    def tearDown(self):
        with get_db() as db:
            db.execute("DELETE FROM reply_queue WHERE credential_id LIKE 'test_rlr_%'")
            db.execute("DELETE FROM barnacle_targets WHERE keyword LIKE 'test_hunt_%'")

    def test_rolling_link_ratio_calculation(self):
        """Test rolling link ratio calculation across last 10 posted items."""
        cred_id = "test_rlr_cred_1"

        # 1. Zero history -> allowed
        allowed, ratio, link_cnt, total = check_rolling_link_ratio(cred_id, max_link_ratio=0.20, window_size=10)
        self.assertTrue(allowed)
        self.assertEqual(ratio, 0.0)
        self.assertEqual(link_cnt, 0)
        self.assertEqual(total, 0)

        # 2. Insert 4 pure value posts (no link) and 1 post with a link
        with get_db() as db:
            for i in range(4):
                db.execute(
                    "INSERT INTO reply_queue (hit_id, credential_id, reply_text, status) VALUES (?, ?, ?, 'submitted')",
                    (f"test_hit_{i}", cred_id, f"Pure helpful technical comment #{i}")
                )
            db.execute(
                "INSERT INTO reply_queue (hit_id, credential_id, reply_text, status) VALUES (?, ?, ?, 'submitted')",
                ("test_hit_link", cred_id, "Check out the specs at https://example.com/specs")
            )

        # Current state: 1 link out of 5 posts = 20%
        # If adding another link: (1+1)/(5+1) = 2/6 = 33.3% > 20% -> should disallow adding another link
        allowed, ratio, link_cnt, total = check_rolling_link_ratio(cred_id, max_link_ratio=0.20, window_size=10)
        self.assertFalse(allowed)
        self.assertEqual(link_cnt, 1)
        self.assertEqual(total, 5)
        self.assertAlmostEqual(ratio, 0.20, places=2)

        # 3. Insert 5 more pure technical comments -> total 10, link_cnt 1 (10%)
        with get_db() as db:
            for i in range(5):
                db.execute(
                    "INSERT INTO reply_queue (hit_id, credential_id, reply_text, status) VALUES (?, ?, ?, 'submitted')",
                    (f"test_hit_clean_{i}", cred_id, f"Another clean solution #{i}")
                )

        # Now: 1 link out of 10 posts = 10%. Adding 1 link -> 2/11 = 18.18% <= 20% -> allowed!
        allowed, ratio, link_cnt, total = check_rolling_link_ratio(cred_id, max_link_ratio=0.20, window_size=10)
        self.assertTrue(allowed)
        self.assertEqual(link_cnt, 1)
        self.assertEqual(total, 10)
        self.assertAlmostEqual(ratio, 0.10, places=2)

    def test_downgrade_reply_links_to_brand_search(self):
        """Test markdown link and bare URL safe degradation to protect accounts."""
        # 1. Markdown link with custom brand
        raw_text_md = "You should definitely look at the [Fairway Roof Calculator](https://fairwayfort.com/tools/roof) for measurements."
        downgraded_md = downgrade_reply_links_to_brand_search(raw_text_md, site_name="Fairway Fort")
        self.assertNotIn("https://", downgraded_md)
        self.assertIn("search for 'Fairway Fort' online", downgraded_md)

        # 2. Bare URL with no site_name
        raw_bare = "I found the diagram at https://diagrams.example.com/schematic-36v. Hope this helps!"
        downgraded_bare = downgrade_reply_links_to_brand_search(raw_bare)
        self.assertNotIn("https://", downgraded_bare)
        self.assertIn("search for 'the tool' on Google", downgraded_bare)

        # 3. Clean text with no links remains unchanged
        clean_text = "Check the solenoid resistor coil behind the batteries."
        self.assertEqual(downgrade_reply_links_to_brand_search(clean_text), clean_text)

        # 4. Empty or None text
        self.assertEqual(downgrade_reply_links_to_brand_search(""), "")

    def test_account_maturity_tiering(self):
        """Test account karma and warmup maturity classification."""
        # COLD / Nursery (< 10 karma)
        cold = get_account_maturity_tier(karma=5)
        self.assertEqual(cold["tier"], "COLD")
        self.assertFalse(cold["can_post_links"])
        self.assertEqual(cold["max_link_ratio"], 0.0)

        # WARMING (10 - 99 karma)
        warming = get_account_maturity_tier(karma=45)
        self.assertEqual(warming["tier"], "WARMING")
        self.assertTrue(warming["can_post_links"])
        self.assertEqual(warming["max_link_ratio"], 0.10)

        # MATURE (>= 100 karma)
        mature = get_account_maturity_tier(karma=350)
        self.assertEqual(mature["tier"], "MATURE")
        self.assertTrue(mature["can_post_links"])
        self.assertEqual(mature["max_link_ratio"], 0.20)

    @patch("urllib.request.urlopen")
    def test_search_google_serp(self, mock_urlopen):
        """Test Google SERP HTML parser extracting high-ranking Reddit discussion threads."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"""
        <!DOCTYPE html>
        <html>
        <body>
            <a href="https://www.reddit.com/r/golfcarts/comments/abc123/best_solenoid_for_ezgo/">
                <h3>Best Solenoid for EZGO TXT 36V?</h3>
            </a>
            <a href="/url?q=https://www.reddit.com/r/ClubCar/comments/def456/precedent_lift_kit/&sa=U">
                <h3>Club Car Precedent Lift Kit Recommendations</h3>
            </a>
            <a href="https://other-site.com/irrelevant">
                <h3>Irrelevant</h3>
            </a>
        </body>
        </html>
        """
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        results = search_google_serp("ezgo solenoid", max_results=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["target_url"], "https://www.reddit.com/r/golfcarts/comments/abc123/best_solenoid_for_ezgo")
        self.assertEqual(results[0]["post_title"], "Best Solenoid for EZGO TXT 36V?")
        self.assertEqual(results[0]["google_rank"], 1)

        self.assertEqual(results[1]["target_url"], "https://www.reddit.com/r/ClubCar/comments/def456/precedent_lift_kit")
        self.assertEqual(results[1]["google_rank"], 2)

    @patch("barnacle.search_serp_targets")
    @patch("barnacle.generate_evergreen_barnacle_reply")
    def test_hunt_and_auto_draft_barnacle(self, mock_gen_draft, mock_search):
        """Test end-to-end barnacle hunt and auto-draft flow."""
        mock_search.return_value = [
            {
                "id": 991,
                "keyword": "test_hunt_cart",
                "target_url": "https://www.reddit.com/r/test/comments/111",
                "post_title": "Top Cart Thread",
                "is_archived": 0,
                "evergreen_draft": ""
            },
            {
                "id": 992,
                "keyword": "test_hunt_cart",
                "target_url": "https://www.reddit.com/r/test/comments/222",
                "post_title": "Old Archived Thread",
                "is_archived": 1,
                "evergreen_draft": ""
            }
        ]
        mock_gen_draft.return_value = "### Definitive Guide\nDetailed troubleshooting steps."

        hunted = hunt_and_auto_draft_barnacle("test_hunt_cart", max_results=2, auto_draft=True)
        self.assertEqual(len(hunted), 2)
        # Active target got auto-drafted
        self.assertEqual(hunted[0]["evergreen_draft"], "### Definitive Guide\nDetailed troubleshooting steps.")
        self.assertEqual(hunted[0]["status"], "drafted")
        # Archived target did NOT get drafted
        self.assertEqual(hunted[1]["evergreen_draft"], "")

    def test_api_barnacle_hunt_endpoint(self):
        """Test POST /api/barnacle/hunt endpoint."""
        with patch("barnacle.hunt_and_auto_draft_barnacle") as mock_hunt:
            mock_hunt.return_value = [
                {
                    "id": 101,
                    "keyword": "test_hunt_api",
                    "target_url": "https://reddit.com/r/test/comments/999",
                    "post_title": "API Test Hunt",
                    "google_rank": 1,
                    "is_archived": 0
                }
            ]
            resp = self.client.post("/api/barnacle/hunt", json={"keyword": "test_hunt_api", "max_results": 5})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["targets"][0]["post_title"], "API Test Hunt")
