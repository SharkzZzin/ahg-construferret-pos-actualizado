from __future__ import annotations

import unittest

from ahg_pos.invoicing import invoice_public_model, make_dgii_qr_svg, trusted_dgii_url


class InvoiceRepresentationTests(unittest.TestCase):
    def test_accepts_official_dgii_test_url(self) -> None:
        url = "https://fc.dgii.gov.do/testecf/consultatimbrefc?rncemisor=132907401&encf=E3201"
        self.assertEqual(trusted_dgii_url(url), url)
        svg = make_dgii_qr_svg(url)
        self.assertIn(b"<svg", svg)
        self.assertGreater(len(svg), 500)

    def test_rejects_non_dgii_or_production_url_in_academic_mode(self) -> None:
        self.assertEqual(trusted_dgii_url("https://example.com/testecf/consulta"), "")
        self.assertEqual(trusted_dgii_url("https://ecf.dgii.gov.do/ecf/ConsultaTimbre"), "")

    def test_accepts_official_testecf_subdomain(self) -> None:
        url = "https://testecf.dgii.gov.do/ecf/ConsultaTimbre?ENCF=E310000000001"
        self.assertEqual(trusted_dgii_url(url), url)

    def test_local_invoice_does_not_claim_an_official_security_code(self) -> None:
        model = invoice_public_model(
            {
                "en_ncf": "E320000000001",
                "ecf_type": "32",
                "total": 118,
                "issued_at": "2026-08-10T10:00:00-04:00",
            }
        )
        self.assertEqual(model["security_code"], "")
        self.assertEqual(len(model["academic_reference_code"]), 6)
        self.assertFalse(model["dgii_qr_available"])

    def test_public_model_uses_provider_qr_data(self) -> None:
        url = "https://fc.dgii.gov.do/testecf/consultatimbrefc?encf=E3201"
        model = invoice_public_model(
            {
                "en_ncf": "E320000000001",
                "ecf_type": "32",
                "total": 118,
                "issued_at": "2026-08-10T10:00:00-04:00",
                "provider_encf": "E320000001234",
                "provider_response_json": (
                    '{"codigoSeguridad":"ABC123","dgiiUrl":"' + url
                    + '","requestJson":{"ECF":{"FechaHoraFirma":"10-08-2026 10:00:01",'
                    '"Encabezado":{"Emisor":{"RazonSocialEmisor":"UTESA","RNCEmisor":"132907401"}}}}}'
                ),
            }
        )
        self.assertEqual(model["display_encf"], "E320000001234")
        self.assertEqual(model["security_code"], "ABC123")
        self.assertEqual(model["dgii_url"], url)
        self.assertTrue(model["dgii_qr_available"])
        self.assertEqual(model["signed_at"], "10-08-2026 10:00:01")
        self.assertEqual(model["provider_issuer_name"], "UTESA")
        self.assertEqual(model["provider_issuer_rnc"], "132907401")


if __name__ == "__main__":
    unittest.main()
