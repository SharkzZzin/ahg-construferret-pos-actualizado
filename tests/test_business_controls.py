from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ahg_pos.database import Database, DatabaseError, RateLimitError


class BusinessControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(f"sqlite:///{(Path(self.temp_dir.name) / 'business.db').as_posix()}").connect()
        self.product = self.db.save_product({
            "id": "CTRL-001", "sku": "CTRL-001", "name": "Producto controlado",
            "category": "Herramientas", "cost": 40, "price": 100, "stock": 10,
            "min_stock": 1, "tax_rate": 18,
        })

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_public_rate_limit_stops_abuse(self) -> None:
        self.db.consume_public_rate_limit("quote", "127.0.0.8", 2)
        self.db.consume_public_rate_limit("quote", "127.0.0.8", 2)
        with self.assertRaises(RateLimitError):
            self.db.consume_public_rate_limit("quote", "127.0.0.8", 2)

    def test_backup_excludes_credentials_and_sessions(self) -> None:
        backup = self.db.export_backup()
        self.assertNotIn("user_sessions", backup["tables"])
        self.assertNotIn("login_attempts", backup["tables"])
        self.assertNotIn("password_hash", backup["tables"]["users"][0])
        self.assertTrue(all("encrypted_api_key" not in row for row in backup["tables"]["fiscal_companies"]))

    def test_last_admin_cannot_be_demoted_or_deactivated(self) -> None:
        admin = self.db.fetch_one("SELECT * FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
        with self.assertRaises(DatabaseError):
            self.db.save_user({
                "name": admin["name"], "email": admin["email"], "phone": admin["phone"],
                "role": "gerente", "active": True,
            }, user_id=int(admin["id"]), actor_user_id=int(admin["id"]))

    def test_cash_session_is_required_for_immediate_sale(self) -> None:
        with self.assertRaises(DatabaseError):
            self.db.create_invoice("32", {}, [{"product_id": self.product["id"], "quantity": 1}], cash_user_id=1)
        self.db.open_cash_session(1, 100)
        invoice = self.db.create_invoice("32", {}, [{"product_id": self.product["id"], "quantity": 1}], cash_user_id=1)
        self.assertGreater(int(invoice["id"]), 0)

    def test_purchase_updates_weighted_cost_and_stock(self) -> None:
        supplier = self.db.list_suppliers()[0]
        purchase = self.db.receive_purchase({
            "supplier_id": supplier["id"], "supplier_invoice_number": "F-100",
            "items": [{"product_id": self.product["id"], "quantity": 10, "unit_cost": 60}],
        }, user_id=1)
        updated = self.db.get_product(self.product["id"])
        self.assertEqual(float(updated["stock"]), 20)
        self.assertEqual(float(updated["cost"]), 50)
        self.assertEqual(float(purchase["balance_due"]), 708)
        paid = self.db.record_supplier_payment(int(purchase["id"]), {"amount": 108, "payment_method": "transferencia"}, 1)
        self.assertEqual(float(paid["balance_due"]), 600)

    def test_credit_sale_creates_receivable_and_cash_collection(self) -> None:
        client = self.db.save_client({
            "name": "Cliente crédito", "rnc_cedula": "40255512345", "phone": "8095550000",
            "email": "credito@example.com", "address": "Santiago",
        })
        invoice = self.db.create_invoice(
            "32", {"id": client["id"]}, [{"product_id": self.product["id"], "quantity": 1}],
            payment_method="credito", due_date="2026-09-30",
        )
        receivable = self.db.list_receivables()[0]
        self.assertEqual(receivable["invoice_id"], invoice["id"])
        self.db.open_cash_session(1, 0)
        paid = self.db.record_customer_payment(int(receivable["id"]), {"amount": 118, "payment_method": "efectivo"}, 1)
        self.assertEqual(float(paid["balance"]), 0)
        self.assertEqual(float(self.db.cash_session_detail(user_id=1)["customer_collections"]), 118)

    def test_partial_credit_note_restocks_only_selected_quantity(self) -> None:
        source = self.db.create_invoice("32", {}, [{"product_id": self.product["id"], "quantity": 4}])
        self.db.save_ecf_api_record(int(source["id"]), {
            "provider_document_id": "source", "track_id": "track", "encf": "E320000000001", "api_status": "Aceptado",
        })
        note = self.db.create_credit_note(
            int(source["id"]), "1", "Devolución parcial", "test",
            items=[{"product_id": self.product["id"], "quantity": 2}], restock=True,
        )
        self.assertEqual(float(note["items"][0]["quantity"]), 2)
        self.assertEqual(float(self.db.get_product(self.product["id"])["stock"]), 8)
        with self.assertRaises(DatabaseError):
            self.db.create_credit_note(
                int(source["id"]), "1", "Cantidad excesiva", "test",
                items=[{"product_id": self.product["id"], "quantity": 3}],
            )

    def test_price_override_requires_manager(self) -> None:
        with self.assertRaises(DatabaseError):
            self.db.create_invoice("32", {}, [{"product_id": self.product["id"], "quantity": 1, "unit_price": 90}])
        admin = self.db.fetch_one("SELECT id, email FROM users WHERE role = 'admin' LIMIT 1")
        approval = self.db.verify_manager_credentials(admin["email"], "Cambiar123!")
        self.assertEqual(approval, admin["id"])
        invoice = self.db.create_invoice(
            "32", {}, [{"product_id": self.product["id"], "quantity": 1, "unit_price": 90}], approved_by_user_id=approval,
        )
        self.assertEqual(invoice["approved_by"], admin["id"])


if __name__ == "__main__":
    unittest.main()
