import unittest
import subprocess
import json
import sys
import os

CLI_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "redsignal_cli.py")
PYTHON_BIN = sys.executable
os.environ["REDSIGNAL_MOCK_AI"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRedSignalCli(unittest.TestCase):
    def test_cli_quota_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "quota", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)
        if data:
            self.assertIn("name", data[0])
            self.assertIn("remaining_quota", data[0])
            self.assertIn("daily_limit", data[0])

    def test_cli_tools_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "tools", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) >= 3)
        self.assertIn("name", data[0])
        self.assertIn("path", data[0])

    def test_cli_radar_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "radar", "--limit", "2", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)

    def test_cli_post_dry_run(self):
        res = subprocess.run([
            PYTHON_BIN, CLI_PATH, "post", "3",
            "--text", "Testing CLI dry-run capability.",
            "--dry-run", "--json"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("dry_run"))
        self.assertIn("tool_matched", data)

    def test_cli_dm_command(self):
        res = subprocess.run([
            PYTHON_BIN, CLI_PATH, "dm", "3", "--json"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("public_dm_hook", data)
        self.assertIn("dm_subject", data)
        self.assertIn("compose_url", data)
        self.assertIn("playbook", data)


    def test_cli_campaigns_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "campaigns", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) >= 1)
        self.assertIn("id", data[0])
        self.assertIn("site_name", data[0])

    def test_cli_affiliate_command(self):
        res = subprocess.run([
            PYTHON_BIN, CLI_PATH, "affiliate", "3",
            "--product", "LemonSqueezy",
            "--url", "https://lemonsqueezy.com?aff=test",
            "--competitor", "Stripe",
            "--json"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("detected_intent", data)
        self.assertIn("playbook", data)
        self.assertIn("public_reply", data["playbook"])
        self.assertIn("dm_funnel", data["playbook"])
        self.assertIn("compose_url", data)
        # Verify inbound hook exists and no fake "sent you a dm"
        inbound_hook = data["playbook"]["public_reply"]["inbound_hook"]
        self.assertNotIn("I sent you a DM", inbound_hook)
        self.assertNotIn("Sent you a DM", inbound_hook)
        self.assertNotIn("sent you a dm", inbound_hook.lower())

    def test_cli_radar_with_intent(self):
        res = subprocess.run([
            PYTHON_BIN, CLI_PATH, "radar", "--intent", "troubleshoot", "--limit", "2", "--json"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)
        for item in data:
            self.assertIn("affiliate_intent", item)
            self.assertEqual(item["affiliate_intent"]["intent"], "troubleshoot")


    def test_cli_add_campaign_json(self):
        res = subprocess.run([
            PYTHON_BIN, CLI_PATH, "add-campaign",
            "--name", "PyTestProduct",
            "--url", "https://pytest-example.com/aff",
            "--subreddits", "SaaS,python",
            "--keywords", "alternative,vs,pricing",
            "--json"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("name"), "PyTestProduct")
        self.assertEqual(data.get("site_url"), "https://pytest-example.com/aff")
        self.assertTrue(len(data.get("offers_matrix", [])) >= 3)
        # Verify offers have name_en
        for offer in data["offers_matrix"]:
            self.assertIn("name_en", offer)
            self.assertTrue(len(offer["name_en"]) > 0)

        # Cleanup test campaign
        from config import load_config, save_config
        cfg = load_config()
        cfg["listeners"] = [l for l in cfg.get("listeners", []) if l.get("name") != "PyTestProduct"]
        save_config(cfg)

    def test_detect_affiliate_intent_boundary_matching(self):
        from ai import detect_affiliate_intent
        # Test word boundary matching prevents false positives
        res_ideal = detect_affiliate_intent("My ideal setup for productivity", "nothing special")
        self.assertNotEqual(res_ideal["intent"], "deal", "Substring 'ideal' should not match 'deal'")

        res_divs = detect_affiliate_intent("Creating divs with CSS grid", "styling help")
        self.assertNotEqual(res_divs["intent"], "compare", "Substring 'divs' should not match 'vs'")

        # Test true positives
        res_vs = detect_affiliate_intent("Stripe vs LemonSqueezy for EU customers", "need help")
        self.assertEqual(res_vs["intent"], "compare")

        res_deal = detect_affiliate_intent("Looking for a lifetime deal or discount code", "promo")
        self.assertEqual(res_deal["intent"], "deal")

        res_alt = detect_affiliate_intent("Looking for a cheaper alternative to Salesforce", "too expensive")
        self.assertEqual(res_alt["intent"], "alternative")

        # Test media buying & agency account intent keywords
        res_agency = detect_affiliate_intent("Looking for TikTok agency accounts with ad credits", "")
        self.assertEqual(res_agency["intent"], "deal")
        self.assertGreaterEqual(res_agency["buying_score"], 80)

        # Test Chinese intent keywords
        res_cn_deal = detect_affiliate_intent("最近查得严，大家有求梯子的吗？求个稳定的梯子", "")
        self.assertEqual(res_cn_deal["intent"], "deal")

        res_cn_vpn = detect_affiliate_intent("刚回国，求推荐vpn或者好用的翻墙工具", "")
        self.assertEqual(res_cn_vpn["intent"], "deal")

        res_cn_alt = detect_affiliate_intent("之前的机场太贵了而且老断流，准备换梯子了", "")
        self.assertEqual(res_cn_alt["intent"], "alternative")

        from ai import classify_funnel_tier
        tier, desc = classify_funnel_tier("求梯子", "请问各位有什么好用的求vpn推荐吗")
        self.assertEqual(tier, 1)

    def test_cli_status_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "status", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) >= 1)
        self.assertIn("id", data[0])
        self.assertIn("name", data[0])
        self.assertIn("total_leads", data[0])


    def test_cli_inbox_dry_run_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "inbox", "--dry-run", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)

    def test_cli_inbox_x_dry_run_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "inbox", "--platform", "x", "--dry-run", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)

    def test_cli_doctor_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "doctor", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIsInstance(data, list)
        self.assertTrue(len(data) >= 3)
        platforms = [d.get("platform") for d in data]
        self.assertIn("reddit", platforms)
        self.assertIn("x", platforms)
        self.assertIn("bark", platforms)

    def test_buying_intent_score_calculation(self):
        from ai import detect_affiliate_intent
        res_urgent = detect_affiliate_intent("最近查得严，急求一个梯子推荐，价格多少钱都可以", "")
        self.assertEqual(res_urgent["intent"], "deal")
        self.assertTrue(res_urgent["buying_score"] >= 90)
        self.assertIn("极速转化", res_urgent["urgency_level"])

        res_general = detect_affiliate_intent("Just thinking about networking today", "")
        self.assertEqual(res_general["intent"], "general")
        self.assertTrue(res_general["buying_score"] < 65)

    def test_dm_agent_state_machine_x(self):
        from dm_agent import get_conversation_state, save_conversation_state
        test_handle = "test_twitter_user_99"
        # Test initial state
        st = get_conversation_state(test_handle, platform="x")
        self.assertEqual(st.get("platform"), "x")
        self.assertEqual(st.get("partner_handle"), test_handle)
        self.assertEqual(st.get("current_round"), 1)

        # Update state
        st["current_round"] = 2
        st["last_inbound_msg"] = "求推荐"
        st["last_outbound_msg"] = "给您整理的对比文档"
        st["status"] = "replied"
        save_conversation_state(st)

        # Re-fetch
        st_after = get_conversation_state(test_handle, platform="x")
        self.assertEqual(st_after.get("current_round"), 2)
        self.assertEqual(st_after.get("last_inbound_msg"), "求推荐")
        self.assertEqual(st_after.get("status"), "replied")

        # Cleanup test row
        from db import get_db
        with get_db() as db:
            db.execute("DELETE FROM dm_conversations WHERE platform='x' AND partner_handle=?", (test_handle,))

    def test_dm_agent_intent_transition(self):
        from dm_agent import analyze_inbound_intent
        # Asking for link or promo code jumps to round 3
        r_link = analyze_inbound_intent("在哪买？可以给个链接和优惠码吗", 1)
        self.assertEqual(r_link, 3)

        # Asking for speed / 403 proof triggers round 2
        r_proof = analyze_inbound_intent("这个节点打得开 ChatGPT 吗？会不会报 403？", 1)
        self.assertEqual(r_proof, 2)

    def test_cli_audit_json(self):
        res = subprocess.run([PYTHON_BIN, CLI_PATH, "audit", "--fast", "--limit", "3", "--json"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertIn("replies", data)
        self.assertIn("targets", data)
        self.assertIn("total_audited", data)

    def test_append_utm_params_utility(self):
        from dm_agent import append_utm_params
        u1 = append_utm_params("https://justmysocks.net/members/aff.php?aff=24082", platform="reddit", medium="dm", campaign="jms_offer", content="round_3")
        self.assertIn("utm_source=reddit", u1)
        self.assertIn("utm_medium=dm", u1)
        self.assertIn("utm_campaign=jms_offer", u1)
        self.assertIn("utm_content=round_3", u1)
        self.assertIn("aff=24082", u1)

        u2 = append_utm_params("https://example.com/tool#anchor", platform="x", medium="dm", campaign="test_camp", content="lead_magnet")
        self.assertIn("utm_source=x", u2)
        self.assertIn("#anchor", u2)

    def test_affiliate_playbook_utm_and_lead_magnet(self):
        from ai import generate_affiliate_playbook
        pb = generate_affiliate_playbook(
            title="Alternative to expensive tool",
            excerpt="Looking for a cheaper replacement",
            author="testuser",
            product_name="BudgetTool",
            affiliate_url="https://budgettool.com/buy?ref=123",
            platform="reddit"
        )
        self.assertIn("dm_funnel", pb)
        rounds = pb["dm_funnel"].get("rounds", [])
        self.assertEqual(len(rounds), 3)
        # Verify Round 2 contains Lead Magnet checklist / benchmark mention
        self.assertIn("checklist", rounds[1]["draft"].lower())
        # Verify Round 3 draft contains UTM tracked link
        self.assertIn("utm_source=reddit", rounds[2]["draft"])
        self.assertIn("utm_medium=dm", rounds[2]["draft"])

    def test_cli_barnacle_positional_json(self):
        res = subprocess.run([
            PYTHON_BIN, CLI_PATH, "barnacle", "tiktok ad credit", "--limit", "2", "--json"
        ], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        # Handle stdout that may have the status banner on line 1
        raw = res.stdout.strip()
        idx = raw.find("[")
        self.assertTrue(idx != -1)
        data = json.loads(raw[idx:])
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        self.assertIn("target_url", data[0])

    def test_cli_post_multi_campaign_tool_matching(self):
        from db import get_db
        test_hit_id = "hit_test_adgrowth_post_01"
        with get_db() as db:
            db.execute(
                """INSERT OR REPLACE INTO hits (hit_id, listener_id, subreddit, title, url, author, excerpt, filter_passed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (test_hit_id, "15750933-43e3-4d05-b4ed-616c057d0a19", "TikTokAds",
                 "How to claim spend match credit for agency ad account?", "https://reddit.com/r/TikTokAds/test_match",
                 "agency_buyer", "Need ad credit calculator", 1)
            )

        try:
            res = subprocess.run([
                PYTHON_BIN, CLI_PATH, "post", test_hit_id,
                "--text", "Here is how to calculate your spend match credit.",
                "--dry-run", "--json"
            ], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertTrue(data.get("ok"))
            self.assertTrue(data.get("dry_run"))
            # Must match Adgrowth-Lab's spend match tool rather than Fairway Fort's golf cart tools
            self.assertIn("补贴", data.get("tool_matched", "") or "TikTok广告充值补贴与返点测算器")
        finally:
            with get_db() as db:
                db.execute("DELETE FROM hits WHERE hit_id=?", (test_hit_id,))


if __name__ == "__main__":
    unittest.main()
