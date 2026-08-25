from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ahg_pos.email_service import email_delivery_status, is_valid_email, send_prefactura_confirmation


class EmailServiceTests(unittest.TestCase):
    def test_validates_customer_email(self) -> None:
        self.assertTrue(is_valid_email("cliente@example.com"))
        self.assertFalse(is_valid_email("cliente@"))
        self.assertFalse(is_valid_email("Cliente <cliente@example.com>"))

    @patch.dict(os.environ, {}, clear=True)
    def test_reports_unconfigured_delivery(self) -> None:
        self.assertEqual(email_delivery_status(), {"configured": False, "provider": None})
        result = send_prefactura_confirmation({"email": "cliente@example.com"})
        self.assertFalse(result["sent"])
        self.assertFalse(result["configured"])

    @patch.dict(
        os.environ,
        {"RESEND_API_KEY": "re_test", "EMAIL_FROM": "AHG <ventas@example.com>"},
        clear=True,
    )
    @patch("ahg_pos.email_service.urlopen")
    def test_resend_confirmation_contains_reference_items_and_idempotency(self, mocked_urlopen) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id":"email_123"}'
        mocked_urlopen.return_value = response

        result = send_prefactura_confirmation(
            {
                "id": 42,
                "customer_name": "Ana Pérez",
                "email": "ana@example.com",
                "total": 118.0,
                "items": [{"name": "Cemento gris", "quantity": 2}],
            }
        )

        self.assertTrue(result["sent"])
        self.assertEqual(result["id"], "email_123")
        api_request = mocked_urlopen.call_args.args[0]
        payload = json.loads(api_request.data.decode("utf-8"))
        self.assertIn("Prefactura recibida", payload["html"])
        self.assertIn("Cemento gris", payload["html"])
        self.assertIn("#42", payload["text"])
        self.assertEqual(api_request.get_header("Idempotency-key"), "ahg-prefactura-42")


if __name__ == "__main__":
    unittest.main()
