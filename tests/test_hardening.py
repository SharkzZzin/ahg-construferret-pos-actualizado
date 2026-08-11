from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ahg_pos.database import Database, DatabaseError
from ahg_pos.http_security import request_is_same_origin


class HardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        path = Path(self.temp_dir.name) / "hardening.db"
        self.db = Database(f"sqlite:///{path.as_posix()}").connect()

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_login_is_temporarily_locked_after_five_failures(self) -> None:
        for _ in range(5):
            self.assertIsNone(self.db.authenticate_user("missing@example.com", "incorrecta", "127.0.0.1"))
        with self.assertRaises(DatabaseError):
            self.db.authenticate_user("missing@example.com", "incorrecta", "127.0.0.1")

    def test_delete_requires_the_authenticated_users_password(self) -> None:
        client = self.db.list_clients()[0]
        with self.assertRaises(PermissionError):
            self.db.delete_client(int(client["id"]), 1, "0000")
        self.db.delete_client(int(client["id"]), 1, "Cambiar123!")
        self.assertFalse(bool(self.db.get_client(int(client["id"]))["active"]))

    def test_each_user_has_an_independent_cash_session(self) -> None:
        second = self.db.save_user({
            "name": "Segundo cajero", "email": "cajero2@example.com", "phone": "8095551111",
            "role": "cajero", "password": "Segura123!", "active": True,
        })
        first_session = self.db.open_cash_session(1, 100, terminal_name="Caja 1")
        second_session = self.db.open_cash_session(int(second["id"]), 200, terminal_name="Caja 2")
        self.assertNotEqual(first_session["id"], second_session["id"])
        self.assertEqual(self.db.get_open_cash_session(1)["terminal_name"], "Caja 1")
        self.assertEqual(self.db.get_open_cash_session(int(second["id"]))["terminal_name"], "Caja 2")

    def test_retry_queue_and_management_report_are_available(self) -> None:
        retry_id = self.db.enqueue_integration_retry("email", "prefactura", 9, {"request_id": 9}, "temporal")
        self.assertEqual(self.db.pending_integration_retries()[0]["id"], retry_id)
        self.db.finish_integration_retry(retry_id)
        self.assertEqual(self.db.pending_integration_retries(), [])
        report = self.db.management_report("2026-01-01", "2026-12-31")
        self.assertIn("estimated_margin", report["totals"])

    def test_same_origin_validation_rejects_cross_site_browser_request(self) -> None:
        self.assertTrue(request_is_same_origin({"Origin": "https://pos.example", "Host": "pos.example"}))
        self.assertFalse(request_is_same_origin({"Origin": "https://evil.example", "Host": "pos.example"}))


if __name__ == "__main__":
    unittest.main()
