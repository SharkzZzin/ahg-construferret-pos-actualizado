from __future__ import annotations

import unittest

from ahg_pos.billing_api import (
    IMECFError,
    build_credit_note_payload,
    build_send_payload,
    extract_document_metadata,
    format_api_date,
)


class BillingPayloadTests(unittest.TestCase):
    def test_formats_utc_timestamp_in_dgii_gmt_minus_four(self) -> None:
        self.assertEqual(format_api_date("2026-08-11T03:55:00+00:00"), "10-08-2026")

    def test_builds_documented_credit_fiscal_payload(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "31",
                "payment_method": "efectivo",
                "rnc_cedula": "40223982170",
                "client_name": "CLIENTE SRL",
                "subtotal": 500,
                "tax": 90,
                "total": 590,
                "issued_at": "2026-06-13T10:00:00-04:00",
                "items": [
                    {
                        "name": "ZUKO PINA 25GR",
                        "quantity": 1,
                        "unit_price": 500,
                        "line_subtotal": 500,
                    }
                ],
            }
        )

        header = payload["ECF"]["Encabezado"]
        self.assertEqual(header["Version"], "1.0")
        self.assertEqual(header["IdDoc"]["TipoeCF"], "31")
        self.assertEqual(header["IdDoc"]["TipoPago"], "1")
        self.assertEqual(header["Comprador"]["RNCComprador"], "40223982170")
        self.assertEqual(header["Totales"]["MontoTotal"], "590.00")
        self.assertEqual(header["Totales"]["TotalITBIS"], "90.00")
        self.assertEqual(payload["ECF"]["DetallesItems"]["Item"]["NombreItem"], "ZUKO PINA 25GR")

    def test_consumption_invoice_can_omit_buyer(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "32",
                "payment_method": "tarjeta",
                "rnc_cedula": "",
                "client_name": "Consumidor Final",
                "subtotal": 168,
                "tax": 30.24,
                "total": 198.24,
                "issued_at": "2026-06-13T10:00:00-04:00",
                "items": [
                    {
                        "name": "Tubo CPVC",
                        "quantity": 1,
                        "unit_price": 168,
                        "line_subtotal": 168,
                    }
                ],
            }
        )

        header = payload["ECF"]["Encabezado"]
        self.assertNotIn("Comprador", header)
        self.assertEqual(header["IdDoc"]["TipoPago"], "1")
        self.assertEqual(header["IdDoc"]["TablaFormasPago"]["FormaDePago"][0]["FormaPago"], 3)

    def test_credit_payment_includes_due_date(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "31",
                "payment_method": "credito",
                "rnc_cedula": "40223982170",
                "client_name": "Alinzon Mendoza",
                "subtotal": 500,
                "tax": 90,
                "total": 590,
                "issued_at": "2026-06-13T10:00:00-04:00",
                "items": [
                    {
                        "name": "ZUKO PINA 25GR",
                        "quantity": 1,
                        "unit_price": 500,
                        "line_subtotal": 500,
                    }
                ],
            }
        )

        id_doc = payload["ECF"]["Encabezado"]["IdDoc"]
        self.assertEqual(id_doc["TipoPago"], "2")
        self.assertEqual(id_doc["FechaLimitePago"], "13-06-2026")
        self.assertNotIn("TablaFormasPago", id_doc)

    def test_extracts_nested_provider_metadata(self) -> None:
        metadata = extract_document_metadata(
            {
                "data": {
                    "id": "doc_123",
                    "trackId": "track_456",
                    "eNCF": "E310000000015",
                    "estado": "Aceptado",
                }
            }
        )

        self.assertEqual(metadata["provider_document_id"], "doc_123")
        self.assertEqual(metadata["track_id"], "track_456")
        self.assertEqual(metadata["encf"], "E310000000015")
        self.assertEqual(metadata["api_status"], "Aceptado")

    def test_large_consumption_invoice_requires_buyer(self) -> None:
        with self.assertRaises(IMECFError):
            build_send_payload(
                {
                    "ecf_type": "32",
                    "payment_method": "paypal",
                    "subtotal": 250000,
                    "tax": 45000,
                    "total": 295000,
                    "items": [{"name": "Venta grande", "quantity": 1, "unit_price": 250000, "line_subtotal": 250000}],
                }
            )

    def test_paypal_uses_other_payment_method(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "32",
                "payment_method": "paypal",
                "subtotal": 100,
                "tax": 18,
                "total": 118,
                "items": [{"name": "Artículo", "quantity": 1, "unit_price": 100, "line_subtotal": 100}],
            }
        )
        self.assertEqual(payload["ECF"]["Encabezado"]["IdDoc"]["TablaFormasPago"]["FormaDePago"][0]["FormaPago"], 8)

    def test_credit_note_is_reported_as_payment_without_reducing_fiscal_total(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "32",
                "payment_method": "efectivo",
                "subtotal": 100,
                "tax": 18,
                "total": 118,
                "credit_applied": 50,
                "items": [{"name": "Articulo", "quantity": 1, "unit_price": 100, "line_subtotal": 100}],
            }
        )
        header = payload["ECF"]["Encabezado"]
        self.assertEqual(header["Totales"]["MontoTotal"], "118.00")
        payments = header["IdDoc"]["TablaFormasPago"]["FormaDePago"]
        self.assertEqual(payments, [
            {"FormaPago": 7, "MontoPago": "50.00"},
            {"FormaPago": 1, "MontoPago": "68.00"},
        ])

    def test_mixed_cash_and_card_are_sent_as_separate_dgii_payments(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "32",
                "payment_method": "mixto",
                "subtotal": 100,
                "tax": 18,
                "total": 118,
                "payments": [
                    {"payment_method": "efectivo", "amount": 40},
                    {"payment_method": "tarjeta", "amount": 78},
                ],
                "items": [{"name": "Articulo", "quantity": 1, "unit_price": 100, "line_subtotal": 100}],
            }
        )
        self.assertEqual(
            payload["ECF"]["Encabezado"]["IdDoc"]["TablaFormasPago"]["FormaDePago"],
            [
                {"FormaPago": 1, "MontoPago": "40.00"},
                {"FormaPago": 3, "MontoPago": "78.00"},
            ],
        )

    def test_invoice_discount_payload(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "32",
                "payment_method": "efectivo",
                "subtotal": 425,
                "discount_total": 75,
                "general_discount": 25,
                "tax": 76.50,
                "total": 501.50,
                "items": [
                    {
                        "name": "Articulo con descuento",
                        "quantity": 1,
                        "unit_price": 500,
                        "discount_amount": 50,
                        "line_subtotal": 450,
                    }
                ],
            }
        )
        header = payload["ECF"]["Encabezado"]
        self.assertEqual(header["Totales"]["MontoDescuento"], "75.00")
        self.assertEqual(header["Totales"]["MontoTotal"], "501.50")
        item = payload["ECF"]["DetallesItems"]["Item"]
        self.assertEqual(item["DescuentoMonto"], "50.00")
        self.assertEqual(item["TablaSubDescuento"]["SubDescuento"]["MontoSubDescuento"], "50.00")
        adjustment = payload["ECF"]["DescuentosORecargos"]["DescuentoORecargo"]
        self.assertEqual(adjustment["TipoAjuste"], "D")
        self.assertEqual(adjustment["DescripcionDescuentooRecargo"], "Descuento general")
        self.assertNotIn("IndicadorFacturacionDescuentoORecargo", adjustment)
        self.assertEqual(adjustment["IndicadorFacturacionDescuentooRecargo"], "1")
        self.assertEqual(adjustment["ValorDescuentooRecargo"], "25.00")
        self.assertEqual(adjustment["MontoDescuentooRecargo"], "25.00")

    def test_e31_discount_keeps_item_discount_without_total_discount_field(self) -> None:
        payload = build_send_payload(
            {
                "ecf_type": "31",
                "payment_method": "efectivo",
                "rnc_cedula": "40223982170",
                "client_name": "Cliente",
                "subtotal": 480,
                "discount_total": 20,
                "general_discount": 0,
                "tax": 86.40,
                "total": 566.40,
                "items": [
                    {
                        "name": "Articulo con descuento",
                        "quantity": 1,
                        "unit_price": 500,
                        "discount_amount": 20,
                        "line_subtotal": 480,
                    }
                ],
            }
        )
        self.assertNotIn("MontoDescuento", payload["ECF"]["Encabezado"]["Totales"])
        self.assertEqual(payload["ECF"]["DetallesItems"]["Item"]["DescuentoMonto"], "20.00")

    def test_builds_e34_reference(self) -> None:
        payload = build_credit_note_payload(
            {
                "source_encf": "E310000000001",
                "source_ecf_type": "31",
                "source_issued_at": "2026-06-19T10:00:00-04:00",
                "modification_code": "1",
                "reason": "Anulación total",
                "subtotal": 100,
                "tax": 18,
                "total": 118,
                "rnc_cedula": "101010101",
                "client_name": "CLIENTE SRL",
                "items": [{"name": "Artículo", "quantity": 1, "unit_price": 100, "line_subtotal": 100}],
            }
        )
        self.assertEqual(payload["ECF"]["Encabezado"]["IdDoc"]["TipoeCF"], "34")
        self.assertEqual(payload["ECF"]["Encabezado"]["IdDoc"]["IndicadorNotaCredito"], "0")
        self.assertNotIn("IndicadorEnvioDiferido", payload["ECF"]["Encabezado"]["IdDoc"])
        self.assertEqual(payload["ECF"]["InformacionReferencia"]["NCFModificado"], "E310000000001")
        self.assertEqual(payload["ECF"]["InformacionReferencia"]["CodigoModificacion"], "1")

    def test_e34_reference_uses_dgii_local_date_for_utc_source(self) -> None:
        payload = build_credit_note_payload(
            {
                "source_encf": "E320000001231",
                "source_ecf_type": "32",
                "source_issued_at": "2026-08-11T03:55:00+00:00",
                "issued_at": "2026-08-11T03:56:00+00:00",
                "modification_code": "1",
                "reason": "Devolucion total",
                "subtotal": 623,
                "tax": 112.14,
                "total": 735.14,
                "items": [{"name": "Gato hidraulico", "quantity": 1, "unit_price": 623, "line_subtotal": 623}],
            }
        )
        self.assertEqual(payload["ECF"]["InformacionReferencia"]["FechaNCFModificado"], "10-08-2026")

    def test_e34_sets_late_credit_note_indicator_after_30_days(self) -> None:
        payload = build_credit_note_payload(
            {
                "source_encf": "E310000000001",
                "source_ecf_type": "31",
                "source_issued_at": "2026-05-01T10:00:00-04:00",
                "issued_at": "2026-06-15T10:00:00-04:00",
                "modification_code": "1",
                "reason": "Anulacion total",
                "subtotal": 100,
                "tax": 18,
                "total": 118,
                "rnc_cedula": "101010101",
                "client_name": "CLIENTE SRL",
                "items": [{"name": "Articulo", "quantity": 1, "unit_price": 100, "line_subtotal": 100}],
            }
        )
        self.assertEqual(payload["ECF"]["Encabezado"]["IdDoc"]["IndicadorNotaCredito"], "1")


if __name__ == "__main__":
    unittest.main()
