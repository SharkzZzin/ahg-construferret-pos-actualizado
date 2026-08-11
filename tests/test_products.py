from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ahg_pos.billing_api import build_send_payload
from ahg_pos.database import Database
from ahg_pos.recommender import recommend_products, suggest_ai_guidance


class ProductMasterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        path = Path(self.temp_dir.name) / "catalog.db"
        self.db = Database(f"sqlite:///{path.as_posix()}").connect()

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_creates_and_updates_product_with_stock_movement(self) -> None:
        created = self.db.save_product(
            {
                "id": "TEST-001",
                "sku": "SKU-TEST-001",
                "name": "Llave ajustable profesional",
                "category": "Herramientas",
                "technical_description": "Llave para trabajos de plomería.",
                "tags": "llave plomeria ajuste tuerca",
                "cost": 200,
                "price": 350,
                "stock": 8,
                "min_stock": 2,
                "tax_rate": 18,
            }
        )
        self.assertEqual(created["name"], "Llave ajustable profesional")
        self.assertEqual(float(created["tax_rate"]), 0.18)

        updated = self.db.save_product(
            {
                **created,
                "category": "Herramientas",
                "price": 375,
                "stock": 11,
                "tax_rate": 18,
            },
            product_id="TEST-001",
        )
        self.assertEqual(float(updated["price"]), 375)
        self.assertEqual(float(updated["stock"]), 11)
        movement = self.db.fetch_one(
            "SELECT quantity FROM inventory_movements WHERE product_id = ? ORDER BY id DESC",
            ("TEST-001",),
        )
        self.assertEqual(float(movement["quantity"]), 3)

    def test_recommender_handles_typo_and_exact_sku(self) -> None:
        typo_results = recommend_products(self.db, "necesito reparar una tuberia de agua calinte", limit=5)
        self.assertTrue(any("CPVC" in row["name"] for row in typo_results))

        sku_results = recommend_products(self.db, "CAB-12-THHN", limit=3)
        self.assertEqual(sku_results[0]["sku"], "CAB-12-THHN")
        self.assertGreaterEqual(sku_results[0]["confidence"], 90)

    def test_user_module_permissions_are_persisted(self) -> None:
        created = self.db.save_user(
            {
                "name": "Usuario restringido",
                "email": "restringido@example.com",
                "phone": "8095550101",
                "role": "cajero",
                "password": "ClaveSegura123!",
                "modules": ["clients", "audit", "invalid"],
                "active": True,
            }
        )
        self.assertEqual(created["modules"], ["clients", "audit"])
        authenticated = self.db.authenticate_user("restringido@example.com", "ClaveSegura123!")
        self.assertIsNotNone(authenticated)
        auth_user, _ = authenticated
        self.assertEqual(auth_user.modules, ("clients", "audit"))

    def test_audit_list_only_returns_user_actions(self) -> None:
        admin = self.db.fetch_one("SELECT id FROM users ORDER BY id LIMIT 1")
        self.db.log_audit(int(admin["id"]), "Actualizar cliente", "cliente", "42", {"name": "Cliente"})
        self.db.log_audit(None, "TRIGGER UPDATE CLIENT", "cliente", "42", {})

        actions = [item["action"] for item in self.db.list_audit_logs(limit=100)["items"]]

        self.assertIn("Actualizar cliente", actions)
        self.assertNotIn("TRIGGER UPDATE CLIENT", actions)

    def test_recommender_guidance_for_empty_search(self) -> None:
        results = recommend_products(self.db, "pieza espacial imposible xyz", limit=5)
        guidance = suggest_ai_guidance(self.db, "pieza espacial imposible xyz")
        self.assertEqual(results, [])
        self.assertTrue(guidance["search_suggestions"])
        self.assertTrue(guidance["guided_questions"])

    def test_recommender_returns_short_factual_summary(self) -> None:
        results = recommend_products(self.db, "tuvberia para agua caliente", limit=4)
        guidance = suggest_ai_guidance(self.db, "tuvberia para agua caliente", results)
        self.assertTrue(results)
        self.assertEqual(
            guidance["result_summary"],
            "Estos fueron los resultados mas afinados conforme a tu inventario.",
        )
        self.assertLessEqual(guidance["result_summary"].count("."), 2)

    def test_valid_client_and_zero_preinvoice(self) -> None:
        client = self.db.save_client(
            {
                "name": "Cliente completo",
                "rnc_cedula": "40255512345",
                "phone": "8095550000",
                "email": "cliente@example.com",
                "address": "Santiago",
            }
        )
        self.assertEqual(client["rnc_cedula"], "40255512345")
        draft = self.db.save_preinvoice(
            {
                "ecf_type": "32",
                "client": {"id": client["id"]},
                "payment_method": "paypal",
                "items": [],
            },
            user_id=1,
        )
        self.assertEqual(float(draft["total"]), 0)
        self.assertEqual(draft["status"], "borrador")

    def test_public_quote_request_returns_saved_prefactura(self) -> None:
        saved = self.db.save_public_quote_request(
            "Cliente portal",
            "8095550199",
            "cliente@example.com",
            "",
            {
                "lines": [{"product_id": "TEST-EMAIL", "name": "Producto de prueba", "quantity": 2}],
                "subtotal": 100,
                "tax": 18,
                "total": 118,
            },
            {"ecf_type": "32"},
        )

        self.assertGreater(int(saved["id"]), 0)
        self.assertEqual(saved["email"], "cliente@example.com")
        self.assertEqual(saved["problem"], "")
        self.assertEqual(saved["items"][0]["quantity"], 2)

        deleted = self.db.delete_public_quote_request(int(saved["id"]))
        self.assertEqual(deleted["id"], saved["id"])
        self.assertFalse(any(row["id"] == saved["id"] for row in self.db.list_public_quote_requests()))

    def test_redeems_anonymous_e34_voucher_without_changing_new_invoice_total(self) -> None:
        product = self.db.save_product(
            {
                "id": "CREDIT-001",
                "sku": "CREDIT-001",
                "name": "Producto para canje",
                "category": "Herramientas",
                "cost": 50,
                "price": 100,
                "stock": 10,
                "min_stock": 1,
                "tax_rate": 18,
            }
        )
        source = self.db.create_invoice(
            "32", {},
            [{"product_id": product["id"], "quantity": 1, "unit_price": 100}],
            payment_method="efectivo",
        )
        self.db.save_ecf_api_record(
            int(source["id"]),
            {"provider_document_id": "invoice-source", "track_id": "track-source", "encf": "E320000009991", "api_status": "Aceptado"},
        )
        note = self.db.create_credit_note(int(source["id"]), "1", "Devolucion total", "test")
        self.db.save_credit_note_api_result(
            int(note["id"]),
            {"provider_document_id": "credit-source", "track_id": "track-credit", "encf": "E340000009991", "api_status": "Aceptado"},
            {},
            {},
        )
        all_valid_notes = self.db.available_credit_notes(None)
        self.assertIn("E340000009991", [row["display_encf"] for row in all_valid_notes])
        client = self.db.save_client(
            {
                "name": "Cliente que presenta el vale",
                "rnc_cedula": "40255512345",
                "phone": "8095550000",
                "email": "vale@example.com",
                "address": "Santiago",
            }
        )

        redeemed = self.db.create_invoice(
            "32",
            {"id": client["id"]},
            [{"product_id": product["id"], "quantity": 1, "unit_price": 100}],
            payment_method="efectivo",
            credit_amount=50,
            credit_note_code="E340000009991",
            payments=[{"payment_method": "tarjeta", "amount": 68}],
        )

        self.assertEqual(float(redeemed["total"]), 118)
        self.assertEqual(float(redeemed["credit_applied"]), 50)
        self.assertEqual(redeemed["payment_method"], "mixto")
        self.assertEqual(
            [(row["payment_method"], float(row["amount"])) for row in redeemed["payments"]],
            [("nota_credito", 50), ("tarjeta", 68)],
        )
        fiscal_payments = build_send_payload(redeemed)["ECF"]["Encabezado"]["IdDoc"]["TablaFormasPago"]["FormaDePago"]
        self.assertEqual(fiscal_payments, [{"FormaPago": 7, "MontoPago": "50.00"}, {"FormaPago": 3, "MontoPago": "68.00"}])
        transaction = self.db.fetch_one("SELECT amount FROM daily_transactions WHERE invoice_id = ?", (redeemed["id"],))
        self.assertEqual(float(transaction["amount"]), 68)
        available = self.db.available_credit_notes(int(client["id"]), "E340000009991")
        self.assertEqual(float(available[0]["available_amount"]), 68)

    def test_mixed_payment_is_persisted_and_included_in_cash_close(self) -> None:
        product = self.db.save_product(
            {"id": "MIX-001", "sku": "MIX-001", "name": "Producto mixto", "category": "Herramientas", "cost": 50, "price": 100, "stock": 5, "min_stock": 1, "tax_rate": 18}
        )
        session = self.db.open_cash_session(1, 500, "Inicio")
        invoice = self.db.create_invoice(
            "32", {}, [{"product_id": product["id"], "quantity": 1, "unit_price": 100}],
            payment_method="efectivo",
            payments=[{"payment_method": "efectivo", "amount": 40}, {"payment_method": "tarjeta", "amount": 78}],
        )
        self.assertEqual(invoice["payment_method"], "mixto")
        self.assertEqual([(row["payment_method"], float(row["amount"])) for row in invoice["payments"]], [("efectivo", 40), ("tarjeta", 78)])
        detail = self.db.cash_session_detail(int(session["id"]))
        self.assertEqual(float(detail["expected_cash"]), 540)
        closed = self.db.close_cash_session(1, 535, "Conteo")
        self.assertEqual(float(closed["difference"]), -5)

    def test_expired_credit_note_is_not_available(self) -> None:
        product = self.db.save_product(
            {"id": "EXP-001", "sku": "EXP-001", "name": "Producto crédito", "category": "Herramientas", "cost": 50, "price": 100, "stock": 5, "min_stock": 1, "tax_rate": 18}
        )
        source = self.db.create_invoice("32", {}, [{"product_id": product["id"], "quantity": 1, "unit_price": 100}])
        self.db.save_ecf_api_record(int(source["id"]), {"provider_document_id": "source", "encf": "E320000008881", "api_status": "Aceptado"})
        note = self.db.create_credit_note(int(source["id"]), "1", "Devolución total", "test")
        self.db.save_credit_note_api_result(int(note["id"]), {"provider_document_id": "note", "encf": "E340000008881", "api_status": "Aceptado"}, {}, {})
        self.db.execute("UPDATE credit_notes SET expires_at = '2020-01-01' WHERE id = ?", (note["id"],))
        self.db.conn.commit()
        self.assertEqual(self.db.get_credit_note(int(note["id"]))["credit_status"], "vencida")
        self.assertEqual(self.db.available_credit_notes(1, "E340000008881"), [])


if __name__ == "__main__":
    unittest.main()
