from __future__ import annotations

import unittest
from pathlib import Path

from ahg_pos.billing_api import FiscalCompanyConfig, credit_note_indicator
from ahg_pos.config import settings
from ahg_pos.database import Database, POSTGRES_SCHEMA_LOCK_ID
from ahg_pos.paypal_api import PayPalClient


ROOT = Path(__file__).resolve().parents[1]


class _FakeConnection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _CurrentPostgresDatabase(Database):
    def __init__(self) -> None:
        super().__init__("postgresql://academic.test/database")
        self.conn = _FakeConnection()
        self.statements: list[tuple[str, tuple]] = []
        self.schema_applied = False

    def execute(self, sql: str, params: tuple = ()):
        self.statements.append((sql, params))
        return None

    def postgres_schema_is_current(self) -> bool:
        return True

    def apply_schema(self) -> None:
        self.schema_applied = True


class _ExistingAuditPostgresDatabase(_CurrentPostgresDatabase):
    def scalar(self, sql: str, params: tuple = ()):
        self.statements.append((sql, params))
        return True


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

    def test_postgres_schema_setup_is_serialized_and_skips_current_version(self) -> None:
        database = _CurrentPostgresDatabase()

        database.ensure_schema()

        self.assertFalse(database.schema_applied)
        self.assertEqual(database.statements[0], ("SELECT pg_advisory_lock(?)", (POSTGRES_SCHEMA_LOCK_ID,)))
        self.assertEqual(database.statements[-1], ("SELECT pg_advisory_unlock(?)", (POSTGRES_SCHEMA_LOCK_ID,)))
        self.assertEqual(database.conn.commits, 2)

    def test_existing_postgres_audit_objects_are_not_recreated(self) -> None:
        database = _ExistingAuditPostgresDatabase()

        database.ensure_audit_triggers()

        executed_sql = "\n".join(sql for sql, _ in database.statements)
        self.assertNotIn("CREATE FUNCTION", executed_sql)
        self.assertNotIn("CREATE TRIGGER", executed_sql)
        self.assertNotIn("DROP TRIGGER", executed_sql)


if __name__ == "__main__":
    unittest.main()
