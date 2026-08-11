from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
            "Necesita materiales para una reparación",
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
        self.assertEqual(saved["items"][0]["quantity"], 2)


if __name__ == "__main__":
    unittest.main()
