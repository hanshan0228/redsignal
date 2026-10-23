import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

import db
from app import app
from db import init_db, migrate_schema


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch, tmp_path):
    test_db = tmp_path / "test_api_endpoints.db"
    monkeypatch.setattr("db.DB_PATH", test_db)
    monkeypatch.setenv("DB_PATH", str(test_db))
    init_db()
    migrate_schema()
    yield


class TestApiEndpoints(unittest.TestCase):
    def setUp(self):
        # Fallback isolation for direct unittest runner without pytest
        if not str(db.DB_PATH).endswith("test_api_endpoints.db"):
            self._temp_dir = tempfile.TemporaryDirectory()
            temp_db = Path(self._temp_dir.name) / "test_api_endpoints.db"
            orig_db = db.DB_PATH
            orig_env = os.environ.get("DB_PATH")
            db.DB_PATH = temp_db
            os.environ["DB_PATH"] = str(temp_db)
            init_db()
            migrate_schema()

            def cleanup():
                db.DB_PATH = orig_db
                if orig_env is None:
                    os.environ.pop("DB_PATH", None)
                else:
                    os.environ["DB_PATH"] = orig_env
                self._temp_dir.cleanup()

            self.addCleanup(cleanup)

        self.client = TestClient(app)

    def test_get_config(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("listeners", data)
        self.assertIn("credentials", data)

    def test_ai_health_analytics(self):
        resp = self.client.get("/api/analytics/ai_health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("chrono", data)
        chrono = data["chrono"]
        self.assertIn("timezone", chrono)
        self.assertIn("tz_abbr", chrono)
        self.assertIn("is_peak", chrono)
        self.assertIn("personas", data)
        self.assertIn("safety_audit", data)
        self.assertIn("automod_penetration", data)

    def test_queue_listing(self):
        resp = self.client.get("/api/queue")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("items", data)
        self.assertIn("daily_used", data)
        self.assertIn("pending_count", data)

    def test_format_channels(self):
        resp = self.client.post(
            "/api/reply/format_channels",
            json={
                "text": "Check the primary circuit pinout first.",
                "title": "Controller blinking red",
                "excerpt": "Looking for diagnostics",
                "anti_ban_mode": "brand_search"
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("channels", data)
        self.assertIn("reddit", data["channels"])
        self.assertIn("x", data["channels"])
        self.assertIn("op_comment", data["channels"])

    def test_auth_profile_and_update_api(self):
        """Test GET /api/auth/profile and POST /api/auth/update validation and persistence."""
        with patch("routes.get_setting", return_value="test-admin"), \
             patch("routes.set_setting") as mock_set_setting, \
             patch("routes._update_env_file") as mock_update_env, \
             patch("routes.db_log"), \
             patch.dict(os.environ, {"APP_USER": "test-admin"}, clear=False):

            # 1. Profile query
            resp = self.client.get("/api/auth/profile")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertIn("username", data)

            # 2. Validation failure: empty fields or short password
            resp_bad = self.client.post("/api/auth/update", json={"username": "", "password": ""})
            self.assertEqual(resp_bad.status_code, 200)
            self.assertFalse(resp_bad.json().get("ok"))

            resp_short = self.client.post("/api/auth/update", json={"username": "test-admin", "password": "123"})
            self.assertEqual(resp_short.status_code, 200)
            self.assertFalse(resp_short.json().get("ok"))
            self.assertIn("6 位", resp_short.json().get("message", ""))

            # 3. Successful update
            resp_good = self.client.post(
                "/api/auth/update",
                json={"username": "test-admin", "password": "test-dummy-password-xyz"}
            )
            self.assertEqual(resp_good.status_code, 200)
            self.assertTrue(resp_good.json().get("ok"))
            self.assertEqual(resp_good.json().get("username"), "test-admin")
            mock_set_setting.assert_any_call("app_user", "test-admin")
            mock_set_setting.assert_any_call("app_password", "test-dummy-password-xyz")
            mock_update_env.assert_called_once_with({"APP_USER": "test-admin", "APP_PASSWORD": "test-dummy-password-xyz"})
            self.assertEqual(os.environ.get("APP_USER"), "test-admin")
            self.assertEqual(os.environ.get("APP_PASSWORD"), "test-dummy-password-xyz")

    def test_cleanup_logs_api(self):
        mock_ret = {"deleted_system_logs": 5, "deleted_webhook_logs": 2, "vacuumed": True}
        with patch("db.cleanup_old_logs", return_value=mock_ret) as mock_cleanup:
            resp = self.client.post("/api/logs/cleanup", json={"days": 14, "max_records": 3000})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(data["deleted_system_logs"], 5)
            self.assertEqual(data["deleted_webhook_logs"], 2)
            self.assertTrue(data["vacuumed"])
            mock_cleanup.assert_called_once_with(days=14, max_records=3000)

    def test_system_status_and_restart_api(self):
        # 1. Test GET /api/system/status
        resp_status = self.client.get("/api/system/status")
        self.assertEqual(resp_status.status_code, 200)
        data_status = resp_status.json()
        self.assertTrue(data_status.get("ok"))
        self.assertIn("pid", data_status)
        self.assertIn("uptime_seconds", data_status)
        self.assertIn("uptime_human", data_status)
        self.assertIn("python_version", data_status)
        self.assertIn("reload_active", data_status)
        self.assertIn("port", data_status)

        # 2. Test POST /api/system/restart with mocked detached execution
        with patch("subprocess.Popen") as mock_popen, patch("time.sleep"):
            resp_restart = self.client.post("/api/system/restart")
            self.assertEqual(resp_restart.status_code, 200)
            data_restart = resp_restart.json()
            self.assertTrue(data_restart.get("ok"))
            self.assertIn("reconnect_wait_seconds", data_restart)
            self.assertEqual(data_restart["reconnect_wait_seconds"], 4)

    def test_health_endpoint_public_access(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("listeners", data)

    def test_listener_start_stop_syncs_enabled(self):
        from config import load_config

        orig_cfg = load_config()
        test_id = "test-sync-listener-id"
        mock_cfg = dict(orig_cfg)
        mock_cfg["listeners"] = list(orig_cfg.get("listeners", [])) + [
            {"id": test_id, "name": "Sync Test", "enabled": False}
        ]

        saved = []
        def fake_save(c):
            saved.append(c)

        with patch("routes.load_config", return_value=mock_cfg), \
             patch("routes.save_config", side_effect=fake_save), \
             patch("routes.start_listener", return_value=True) as mock_start, \
             patch("routes.stop_listener") as mock_stop:

            # 1. Start listener sets enabled=True
            resp_start = self.client.post(f"/api/listeners/{test_id}/start")
            self.assertEqual(resp_start.status_code, 200)
            self.assertTrue(resp_start.json().get("ok"))
            mock_start.assert_called_once()
            target_lst = next(l for l in mock_cfg["listeners"] if l["id"] == test_id)
            self.assertTrue(target_lst.get("enabled"))
            self.assertTrue(len(saved) >= 1)

            # 2. Stop listener sets enabled=False
            resp_stop = self.client.post(f"/api/listeners/{test_id}/stop")
            self.assertEqual(resp_stop.status_code, 200)
            self.assertTrue(resp_stop.json().get("ok"))
            mock_stop.assert_called_once_with(test_id)
            self.assertFalse(target_lst.get("enabled"))

            # 3. Nonexistent listener
            resp_nf = self.client.post("/api/listeners/nonexistent-id-999/start")
            self.assertEqual(resp_nf.status_code, 200)
            self.assertFalse(resp_nf.json().get("ok"))
            self.assertEqual(resp_nf.json().get("message"), "Listener not found")


if __name__ == "__main__":
    unittest.main()
