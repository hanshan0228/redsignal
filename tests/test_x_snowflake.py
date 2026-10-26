import unittest
from monitor import extract_snowflake_timestamp


class TestXSnowflake(unittest.TestCase):
    def test_valid_snowflake_timestamp(self):
        # Known tweet: ID 1769411989417832560 -> 1710695667.019s (March 17, 2024 17:14:27 UTC)
        tid = "1769411989417832560"
        ts = extract_snowflake_timestamp(tid)
        self.assertIsNotNone(ts)
        self.assertAlmostEqual(ts, 1710695667.019, places=2)

    def test_invalid_or_short_tweet_ids(self):
        self.assertIsNone(extract_snowflake_timestamp(""))
        self.assertIsNone(extract_snowflake_timestamp(None))
        self.assertIsNone(extract_snowflake_timestamp("abc12345"))
        self.assertIsNone(extract_snowflake_timestamp("123"))  # too short
        self.assertIsNone(extract_snowflake_timestamp("0"))
        # Pre-snowflake legacy IDs (< 15 digits) should be rejected
        self.assertIsNone(extract_snowflake_timestamp("10000000"))
        self.assertIsNone(extract_snowflake_timestamp("12345678901234"))

    def test_future_overflow_ids(self):
        # 19 digits with massive timestamp far past 2049
        huge_id = str((1500000000000 << 22) + 1288834974657)
        self.assertIsNone(extract_snowflake_timestamp(huge_id))
