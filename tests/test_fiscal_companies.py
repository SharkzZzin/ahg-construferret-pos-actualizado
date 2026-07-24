from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ahg_pos.billing_api import FiscalCompanyConfig, IMECFClient
from ahg_pos.credentials import decrypt_secret, encrypt_secret
from ahg_pos.database import Database, DatabaseError


class FiscalCompanyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        path = Path(self.temp_dir.name) / "fiscal.db"
        self.db = Database(f"sqlite:///{path.as_posix()}").connect()
        self.admin_id = int(self.db.fetch_one("SELECT id FROM users WHERE role = 'admin'")["id"])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_encrypts_credentials(self) -> None:
        encrypted = encrypt_secret("ecf_live_test_secret")
        self.assertNotIn("ecf_live_test_secret", encrypted)
        self.assertEqual(decrypt_secret(encrypted), "ecf_live_test_secret")

    def test_profile_requires_validation_and_test_before_activation(self) -> None:
        company = self.db.save_fiscal_company(
            {
                "workspace_name": "Empresa Demo",
                "issuer_name": "EMPRESA DEMO SRL",
                "issuer_rnc": "101010101",
                "company_id": "demo-company",
                "base_url": "https://example.test",
                "portal_url": "https://portal.example.test",
                "environment": "test",
                "api_key": "ecf_live_demo",
                "enabled": True,
            },
            user_id=self.admin_id,
        )
        with self.assertRaises(DatabaseError):
            self.db.activate_fiscal_company(int(company["id"]), self.admin_id)

        self.db.record_fiscal_validation(int(company["id"]), True, "Emisor válido.")
        self.db.record_fiscal_connection_test(int(company["id"]), True, "Conexión válida.")
        active = self.db.activate_fiscal_company(int(company["id"]), self.admin_id)
        self.assertTrue(active["active"])

        client = IMECFClient(company=FiscalCompanyConfig.from_row(active))
        self.assertTrue(client.active)
        self.assertEqual(client.company.issuer_rnc, "101010101")


if __name__ == "__main__":
    unittest.main()
