import time
import unittest

from ai import (
    calculate_opportunity_score,
    classify_funnel_tier,
    classify_persona,
    clean_base_reply,
    format_multichannel_pack,
)
from auto_responder import calculate_smart_chrono_dispatch
from config import load_config


class TestAiPipeline(unittest.TestCase):
    def test_chrono_dispatch_timezone_adaptability(self):
        # Test EDT, JST, UTC across peak and night
        for tz in ["America/New_York", "Asia/Tokyo", "Europe/London", "UTC"]:
            res = calculate_smart_chrono_dispatch(
                post_ts=time.time(),
                opportunity_score=85,
                schedule_timezone=tz,
                schedule_start=7,
                schedule_end=22
            )
            self.assertIn("delay_seconds", res)
            self.assertIn("delay_minutes", res)
            self.assertIn("chrono_reason", res)
            self.assertIn("is_peak", res)
            self.assertGreater(res["delay_seconds"], 0)

    def test_funnel_tier_classification(self):
        # Tier 1: Hot Intent
        t1, _ = classify_funnel_tier(
            title="Looking for recommendations on the best diagnostic scanner",
            text="Where can I buy one or which tool do you recommend?"
        )
        self.assertEqual(t1, 1)

        # Tier 1: Media Buying / Agency Ad Account & Credit Intent
        t1_agency, _ = classify_funnel_tier(
            title="Looking for reliable TikTok agency accounts with ad credits",
            text="Need verified account provider"
        )
        self.assertEqual(t1_agency, 1)

        # Tier 2: Comparison & Pain point
        t2, _ = classify_funnel_tier(
            title="Comparison: Tool A vs Tool B",
            text="I hate how slow Tool A is, is there an alternative that doesn't break?"
        )
        self.assertEqual(t2, 2)

        # Tier 2: Account ban / spend limit pain point
        t2_ban, _ = classify_funnel_tier(
            title="Personal ad account suspended with $50 daily limit",
            text="Need alternative solution"
        )
        self.assertEqual(t2_ban, 2)

        # Tier 3: General Question
        t3, _ = classify_funnel_tier(
            title="How does voltage regulation work in battery cells?",
            text="Trying to understand the underlying electrical theory."
        )
        self.assertEqual(t3, 3)

    def test_opportunity_score_calculation(self):
        res = calculate_opportunity_score(
            title="Where to find the official wiring schematic?",
            text="Looking for recommendation and link",
            ts=time.time() - 300,
            funnel_tier=1
        )
        self.assertGreaterEqual(res["score"], 65)
        self.assertIn(res["priority"], ["P1_GOLDEN", "P2_SILVER", "P3_BRONZE", "P4_COLD"])

    def test_persona_matching_decoupled(self):
        # 1. Custom personas should take top precedence
        custom_personas = [
            {
                "key": "barista",
                "label": "☕ 咖啡萃取师",
                "name": "Barista & Roast Master",
                "tone": "Direct, passion for grind size and water temperature.",
                "match_keywords": ["espresso", "grinder", "extraction", "crema"]
            },
            {
                "key": "roaster",
                "label": "🔥 烘焙先锋",
                "name": "Roast Geek",
                "tone": "Focus on roast curves and first crack.",
                "match_keywords": ["roast", "crack", "green bean"]
            }
        ]
        matched = classify_persona(
            title="How to improve espresso crema?",
            text="My grinder is set fine but extraction is bitter.",
            subreddit="espresso",
            custom_personas=custom_personas
        )
        self.assertEqual(matched["key"], "barista")
        self.assertEqual(matched["label"], "☕ 咖啡萃取师")

        # 2. Universal fallback for non-golf content when no custom personas
        generic = classify_persona(
            title="How to deploy Next.js with Docker?",
            text="Facing issues with environment variables during build.",
            subreddit="nextjs",
            custom_personas=[]
        )
        self.assertEqual(generic["key"], "expert")
        self.assertEqual(generic["label"], "🎯 领域专家")

    def test_multichannel_formatting(self):
        asset = {
            "name": "Pinout Matrix",
            "image_url": "https://example.com/pinout.webp",
            "target_url": "https://voltfixer.example.com",
            "citation_source": "Source: VoltFixer Engineering",
            "caption": "Diagnostic Pinout Matrix"
        }
        pack = format_multichannel_pack(
            base_reply="Here is the step-by-step diagnostic breakdown for your controller.",
            title="Controller not powering up",
            excerpt="Checked the wiring but no LED indicator.",
            site_name="VoltFixer",
            site_url="https://voltfixer.example.com",
            anti_ban_mode="brand_search",
            matched_asset=asset
        )
        self.assertIn("reddit", pack)
        self.assertIn("bbcode", pack)
        self.assertIn("op_comment", pack)
        self.assertIn("x", pack)
        self.assertLessEqual(len(pack["x"]), 220)
        self.assertIn("VoltFixer", pack["reddit"])
        self.assertIn("VoltFixer", pack["op_comment"])
        self.assertIn("[URL='https://voltfixer.example.com']", pack["bbcode"])

    def test_load_config_neutral_defaults(self):
        cfg = load_config()
        self.assertIn("listeners", cfg)
        self.assertIn("credentials", cfg)
        for lst in cfg.get("listeners", []):
            self.assertTrue(lst.get("site_name"))

    def test_clean_base_reply_anti_slop(self):
        raw_ai = (
            '```markdown\n"Here is a suggested reply for Reddit:\n\n'
            'The 48V Solenoid should click immediately when key is in ON position. Check pin 3.\n\n'
            'Feel free to shoot me a DM if you get stuck.\n'
            'Hope this helps!!"\n```'
        )
        cleaned = clean_base_reply(raw_ai)
        self.assertNotIn("Here is a suggested reply", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertNotIn("Hope this helps", cleaned)
        self.assertNotIn("shoot me a DM", cleaned)
        self.assertIn("The 48V Solenoid should click immediately", cleaned)
        self.assertFalse(cleaned.startswith('"'))
        self.assertFalse(cleaned.endswith('"'))
        self.assertNotIn("!!", cleaned)

    def test_generate_listener_profile_hardening(self):
        from unittest.mock import patch
        from ai import generate_listener_profile

        fake_cred = {"type": "mock"}
        # Case 1: AI returned raw generic/unhardened fields
        raw_llm_output = (
            '{\n'
            '  "name": "TikTok Agency Radar",\n'
            '  "subreddits": "tiktokads ppc adops dropship",\n'
            '  "keywords": ["tiktok agency account", "tiktok ad credit", "spend limit", "daily cap"],\n'
            '  "negative_keywords": ["creator fund", "dance", "meme"],\n'
            '  "filter_prompt": "Does this content discuss topics directly relevant to TikTok Ads?",\n'
            '  "pitch_instruction": "Casually introduce our agency accounts with $500 match."\n'
            '}'
        )
        with patch("ai.run_ai_prompt", return_value=raw_llm_output):
            profile = generate_listener_profile(
                site_name="Adgrowth-Lab",
                site_description="Official agency ad accounts with spend match",
                site_url="https://adgrowth-lab.github.io",
                platform="reddit",
                credential=fake_cred
            )
            # Must override generic filter_prompt with buyer-intent gatekeeper
            self.assertIn("Adgrowth-Lab", profile["filter_prompt"])
            self.assertIn("commercial problem", profile["filter_prompt"])
            self.assertIn("Reply YES", profile["filter_prompt"])
            self.assertIn("Reply NO", profile["filter_prompt"])

            # Must harden pitch_instruction with anti-ban directives
            self.assertIn("salesperson", profile["pitch_instruction"].lower())
            self.assertIn("dollar", profile["pitch_instruction"].lower())
            self.assertIn("3rd person", profile["pitch_instruction"].lower())

    def test_generate_listener_profile_x_platform_hardening(self):
        from unittest.mock import patch
        from ai import generate_listener_profile

        fake_cred = {"type": "mock"}
        # Case: AI generated keywords including forbidden buy/coupon words on X
        raw_llm_output = (
            '{\n'
            '  "name": "TikTok Agency Radar",\n'
            '  "subreddits": "",\n'
            '  "keywords": ["tiktok agency account", "buy tiktok ad account", "tiktok ads coupon", "ad spend limit"],\n'
            '  "negative_keywords": ["creator fund", "dance"],\n'
            '  "filter_prompt": "Commercial intent gatekeeper prompt",\n'
            '  "pitch_instruction": "Long winded sales pitch over 200 chars that will trigger bans and fail platform guidelines."\n'
            '}'
        )
        with patch("ai.run_ai_prompt", return_value=raw_llm_output):
            profile = generate_listener_profile(
                site_name="Adgrowth-Lab",
                site_description="Official agency ad accounts with spend match",
                site_url="https://adgrowth-lab.github.io",
                platform="x",
                credential=fake_cred
            )
            # Forbidden keywords must be scrubbed on X
            self.assertIn("tiktok agency account", profile["keywords"])
            self.assertIn("ad spend limit", profile["keywords"])
            self.assertNotIn("buy tiktok ad account", profile["keywords"])
            self.assertNotIn("tiktok ads coupon", profile["keywords"])

            # X bot negative keywords must be auto-injected
            self.assertIn("whatsapp", profile["negative_keywords"])
            self.assertIn("dm me", profile["negative_keywords"])
            self.assertIn("crypto", profile["negative_keywords"])

            # Pitch instruction must enforce bio checklist and character bounds
            self.assertIn("bio", profile["pitch_instruction"].lower())
            self.assertLessEqual(len(profile["pitch_instruction"]), 190)

    def test_extract_metadata_from_url_rich_extraction(self):
        from unittest.mock import patch, MagicMock
        from ai import extract_metadata_from_url

        mock_html = """
        <html>
        <head>
            <title>TikTok Offers Hub &middot; Official Ad Credit Registry</title>
            <meta name="description" content="Official TikTok ad credits matched across 4 verified advertiser tiers.">
            <meta property="og:site_name" content="Adgrowth Lab">
        </head>
        <body>
            <h1>Agency Accounts with Zero Spend Limits</h1>
            <h2>Instant Whitelisting and Cashback</h2>
            <p>Scale paid ads on TikTok without random bans or billing holds.</p>
        </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html

        with patch("curl_cffi.requests.get", return_value=mock_resp):
            res = extract_metadata_from_url("https://adgrowth-lab.github.io")
            self.assertEqual(res["brand_name"], "Adgrowth Lab")
            self.assertIn("Agency Accounts with Zero Spend Limits", res["headings"])
            self.assertIn("Official TikTok ad credits", res["description"])
            self.assertIn("Zero Spend Limits", res["description"])

    def test_multichannel_formatting_bio_routing_and_inbound_dm(self):
        asset = {
            "name": "TikTok Agency Tier Matrix",
            "image_url": "https://adgrowth-lab.github.io/assets/tier-matrix.webp",
            "target_url": "https://adgrowth-lab.github.io/",
            "caption": "TikTok Agency Whitelist & Spend Match Matrix"
        }
        # Bio routing mode
        pack_bio = format_multichannel_pack(
            base_reply="Personal accounts hit $50/day spend holds due to new risk scoring.",
            title="TikTok ads daily budget capped",
            excerpt="Account stuck at 50/day limit on new BM.",
            site_name="Adgrowth-Lab",
            site_url="https://adgrowth-lab.github.io/",
            anti_ban_mode="safe",
            matched_asset=asset,
            stealth_mode="bio_routing"
        )
        self.assertNotIn("https://adgrowth-lab.github.io/", pack_bio["reddit"])
        self.assertIn("Adgrowth-Lab database", pack_bio["reddit"])

        # Inbound DM mode
        pack_dm = format_multichannel_pack(
            base_reply="Personal accounts hit $50/day spend holds due to new risk scoring.",
            title="TikTok ads daily budget capped",
            excerpt="Account stuck at 50/day limit on new BM.",
            site_name="Adgrowth-Lab",
            site_url="https://adgrowth-lab.github.io/",
            anti_ban_mode="safe",
            matched_asset=asset,
            stealth_mode="inbound_dm"
        )
        self.assertNotIn("https://adgrowth-lab.github.io/", pack_dm["reddit"])
        self.assertIn("shoot me a DM", pack_dm["reddit"])

    def test_dm_agent_tiktok_agency_drafting(self):
        from dm_agent import draft_automated_reply
        from unittest.mock import patch

        # Fallback test (when AI prompt throws) for Round 1, 2, 3
        with patch("dm_agent.run_ai_prompt", side_effect=RuntimeError("AI Offline")):
            r1 = draft_automated_reply(
                partner_handle="ecom_scaler",
                inbound_text="Hey saw your comment, can you send the breakdown?",
                target_round=1,
                campaign_name="Adgrowth-Lab",
                affiliate_url="https://adgrowth-lab.github.io/",
                ai_credential=None,
                platform="reddit"
            )
            self.assertIn("adgrowth-lab.github.io", r1)
            self.assertIn("breakdown sheet", r1)

            r2 = draft_automated_reply(
                partner_handle="ecom_scaler",
                inbound_text="We are running dropshipping and keep getting hit with billing limits.",
                target_round=2,
                campaign_name="Adgrowth-Lab",
                affiliate_url="https://adgrowth-lab.github.io/",
                ai_credential=None,
                platform="reddit"
            )
            self.assertIn("$50/day", r2)
            self.assertIn("agency lines", r2)

            r3 = draft_automated_reply(
                partner_handle="ecom_scaler",
                inbound_text="Where can I apply for the whitelisted agency account?",
                target_round=3,
                campaign_name="Adgrowth-Lab",
                affiliate_url="https://adgrowth-lab.github.io/",
                ai_credential=None,
                platform="reddit"
            )
            self.assertIn("adgrowth-lab.github.io", r3)
            self.assertIn("t.me/adgrowth_lab", r3)
            self.assertIn("$6,000", r3)


if __name__ == "__main__":
    unittest.main()
