from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import settings


class PayPalError(RuntimeError):
    pass


@dataclass
class PayPalClient:
    timeout: int = 30

    @property
    def configured(self) -> bool:
        return settings.paypal_configured

    def public_config(self) -> dict:
        return {
            "configured": self.configured,
            "environment": settings.paypal_environment,
            "client_id": settings.paypal_client_id if self.configured else "",
            "currency": settings.paypal_currency,
            "dop_per_usd": settings.paypal_dop_per_usd,
            "no_charge": settings.paypal_no_charge,
        }

    def create_order(self, amount_dop: float, description: str) -> dict:
        if amount_dop <= 0:
            raise ValueError("El monto a cobrar debe ser mayor que cero.")
        if settings.paypal_no_charge and settings.paypal_environment != "sandbox":
            raise PayPalError("El modo sin cargo solo puede usarse con PayPal Sandbox.")
        amount = self._convert_amount(amount_dop)
        return self._request(
            "POST",
            "/v2/checkout/orders",
            {
                "intent": "AUTHORIZE" if settings.paypal_no_charge else "CAPTURE",
                "purchase_units": [
                    {
                        "description": description[:127],
                        "amount": {
                            "currency_code": settings.paypal_currency,
                            "value": f"{amount:.2f}",
                        },
                    }
                ],
            },
        )

    def capture_order(self, order_id: str) -> dict:
        if not order_id or len(order_id) > 80:
            raise ValueError("Orden de PayPal no válida.")
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture", {})

    def authorize_order(self, order_id: str) -> dict:
        if not order_id or len(order_id) > 80:
            raise ValueError("Orden de PayPal no valida.")
        return self._request("POST", f"/v2/checkout/orders/{order_id}/authorize", {})

    def _convert_amount(self, amount_dop: float) -> Decimal:
        amount = Decimal(str(amount_dop))
        if settings.paypal_currency == "DOP":
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if settings.paypal_currency != "USD" or settings.paypal_dop_per_usd <= 0:
            raise PayPalError("Configura una moneda y tasa de conversión válidas.")
        return (amount / Decimal(str(settings.paypal_dop_per_usd))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def _access_token(self) -> str:
        if not self.configured:
            raise PayPalError("PayPal Sandbox no está configurado.")
        credentials = base64.b64encode(
            f"{settings.paypal_client_id}:{settings.paypal_client_secret}".encode("utf-8")
        ).decode("ascii")
        request = Request(
            f"{settings.paypal_api_base_url}/v1/oauth2/token",
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        data = self._open(request)
        token = str(data.get("access_token", ""))
        if not token:
            raise PayPalError("PayPal no devolvió un token de acceso.")
        return token

    def _request(self, method: str, path: str, payload: dict) -> dict:
        request = Request(
            f"{settings.paypal_api_base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": f"ahg-{path.rsplit('/', 1)[-1]}-{id(payload)}",
            },
            method=method,
        )
        return self._open(request)

    def _open(self, request: Request) -> dict:
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise PayPalError(f"PayPal rechazó la operación ({exc.code}): {details[:300]}") from exc
        except (URLError, TimeoutError) as exc:
            raise PayPalError(f"No fue posible conectar con PayPal: {exc}") from exc
