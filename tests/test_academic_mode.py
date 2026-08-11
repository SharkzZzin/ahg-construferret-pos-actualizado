from __future__ import annotations

import unittest
from pathlib import Path

from ahg_pos.billing_api import FiscalCompanyConfig, credit_note_indicator
from ahg_pos.config import settings
from ahg_pos.paypal_api import PayPalClient


ROOT = Path(__file__).resolve().parents[1]


class AcademicModeTests(unittest.TestCase):
    def test_academic_mode_forces_test_integrations(self) -> None:
        self.assertTrue(settings.academic_mode)
        self.assertEqual(settings.fiscal_environment, "test")
        self.assertEqual(settings.paypal_environment, "sandbox")
        self.assertTrue(settings.paypal_no_charge)
        self.assertEqual(PayPalClient().public_config()["environment"], "sandbox")

    def test_saved_fiscal_profile_is_read_as_test_in_academic_mode(self) -> None:
        company = FiscalCompanyConfig.from_row(
            {
                "id": 1,
                "workspace_name": "UTESA",
                "issuer_name": "AHG",
                "issuer_rnc": "132907401",
                "company_id": "academic",
                "base_url": "https://example.test",
                "portal_url": "https://example.test",
                "environment": "production",
                "api_key": "test",
                "enabled": True,
                "active": True,
            }
        )
        self.assertEqual(company.environment, "test")

    def test_credit_note_indicator_is_deterministic(self) -> None:
        self.assertEqual(
            credit_note_indicator("2026-06-19T10:00:00-04:00", "2026-06-19T10:00:00-04:00"),
            "0",
        )

    def test_login_does_not_publish_default_credentials(self) -> None:
        login = (ROOT / "src" / "ahg_pos" / "web" / "login.html").read_text(encoding="utf-8")
        self.assertNotIn("Cambiar123!", login)
        self.assertNotIn("admin@ahg.local", login)
        self.assertIn("Proyecto Integrador UTESA", login)

    def test_academic_notice_exists_on_all_public_surfaces(self) -> None:
        login = (ROOT / "src" / "ahg_pos" / "web" / "login.html").read_text(encoding="utf-8")
        pos = (ROOT / "src" / "ahg_pos" / "web" / "index.html").read_text(encoding="utf-8")
        catalog = (ROOT / "src" / "ahg_pos" / "web" / "customer.html").read_text(encoding="utf-8")
        self.assertIn("académic", login.lower())
        self.assertIn("academic-banner", pos)
        self.assertIn("academic-public-notice", catalog)


if __name__ == "__main__":
    unittest.main()
