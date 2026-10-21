from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import db


class DatabaseBootstrapTests(unittest.TestCase):
    def test_init_db_creates_missing_parent_directory(self) -> None:
        original = db.DB_PATH
        try:
            with TemporaryDirectory() as root:
                db.DB_PATH = Path(root) / "nested" / "redsignal.db"
                db.init_db()
                self.assertTrue(db.DB_PATH.is_file())
        finally:
            db.DB_PATH = original

    def test_cleanup_old_logs(self) -> None:
        original = db.DB_PATH
        try:
            with TemporaryDirectory() as root:
                db.DB_PATH = Path(root) / "test_cleanup.db"
                db.init_db()

                # Insert 3 expired logs and 8 fresh logs into system_log
                with db.get_db() as conn:
                    for i in range(3):
                        conn.execute(
                            "INSERT INTO system_log (level, source, message, created_at) VALUES ('info', 'test', ?, '2026-09-01T00:00:00Z')",
                            (f"old_{i}",)
                        )
                    for i in range(8):
                        conn.execute(
                            "INSERT INTO system_log (level, source, message) VALUES ('info', 'test', ?)",
                            (f"new_{i}",)
                        )
                    # Insert 2 expired logs and 3 fresh logs into webhook_log
                    for i in range(2):
                        conn.execute(
                            "INSERT INTO webhook_log (wtype, url, payload, created_at) VALUES ('slack', 'http://test', '{}', '2026-09-01T00:00:00Z')"
                        )
                    for i in range(3):
                        conn.execute(
                            "INSERT INTO webhook_log (wtype, url, payload) VALUES ('slack', 'http://test', '{}')"
                        )

                # Clean up: delete > 7 days old, cap max_records to 5
                res = db.cleanup_old_logs(days=7, max_records=5)
                self.assertTrue(res["vacuumed"])
                # 3 expired deleted + (8 - 5 = 3) excess deleted = 6 total system logs deleted
                self.assertEqual(res["deleted_system_logs"], 6)
                # 2 expired deleted, 3 remaining <= 5 cap, so 2 total webhook logs deleted
                self.assertEqual(res["deleted_webhook_logs"], 2)

                with db.get_db() as conn:
                    sys_count = conn.execute("SELECT COUNT(*) FROM system_log").fetchone()[0]
                    wh_count = conn.execute("SELECT COUNT(*) FROM webhook_log").fetchone()[0]
                    self.assertEqual(sys_count, 5)
                    self.assertEqual(wh_count, 3)

                # Test that days=0 and max_records=0 leaves remaining records intact
                res_zero = db.cleanup_old_logs(days=0, max_records=0)
                self.assertEqual(res_zero["deleted_system_logs"], 0)
                self.assertEqual(res_zero["deleted_webhook_logs"], 0)
                with db.get_db() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM system_log").fetchone()[0], 5)
        finally:
            db.DB_PATH = original



if __name__ == "__main__":
    unittest.main()
