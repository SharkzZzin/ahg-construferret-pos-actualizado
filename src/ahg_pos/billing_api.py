from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import settings


class IMECFError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True)
class IMECFResult:
    data: dict[str, Any]
    request_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class FiscalCompanyConfig:
    id: int | None
    workspace_name: str
    issuer_name: str
    issuer_rnc: str
    company_id: str
    base_url: str
    portal_url: str
    environment: str
    api_key: str
    enabled: bool
    active: bool

    @property
    def dashboard_url(self) -> str:
        if not self.portal_url:
            return ""
        if not self.company_id:
            return self.portal_url
        return f"{self.portal_url.rstrip('/')}/c/{self.company_id}/dashboard"

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "FiscalCompanyConfig":
        return cls(
            id=int(row["id"]) if row.get("id") is not None else None,
            workspace_name=str(row.get("workspace_name") or ""),
            issuer_name=str(row.get("issuer_name") or ""),
            issuer_rnc=str(row.get("issuer_rnc") or ""),
            company_id=str(row.get("company_id") or ""),
            base_url=str(row.get("base_url") or "").rstrip("/"),
            portal_url=str(row.get("portal_url") or "").rstrip("/"),
            environment=str(row.get("environment") or "test"),
            api_key=str(row.get("api_key") or ""),
            enabled=bool(row.get("enabled")),
            active=bool(row.get("active")),
        )

    @classmethod
    def from_settings(cls) -> "FiscalCompanyConfig":
        return cls(
            id=None,
            workspace_name=settings.imecf_workspace_name,
            issuer_name=settings.imecf_expected_issuer_name or settings.company_name,
            issuer_rnc=settings.company_rnc,
            company_id=settings.imecf_company_id,
            base_url=settings.imecf_base_url,
            portal_url=settings.imecf_portal_base_url,
            environment=settings.fiscal_environment,
            api_key=settings.imecf_api_key,
            enabled=settings.imecf_enabled,
            active=True,
        )


class IMECFClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
        company: FiscalCompanyConfig | None = None,
    ) -> None:
        self.company = company or FiscalCompanyConfig.from_settings()
        self.base_url = (base_url or self.company.base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else self.company.api_key
        self.timeout = timeout or settings.imecf_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    @property
    def active(self) -> bool:
        return self.company.enabled and self.company.active and self.configured

    @property
    def mode(self) -> str:
        return "real" if self.active else "local"

    def test_connection(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "ok": False,
                "provider": "IMECF Platform",
                "mode": self.mode,
                "message": "Falta IMECF_API_KEY.",
            }
        try:
            response = self.list_documents({"page": 1, "limit": 1})
            return {
                "ok": True,
                "provider": "IMECF Platform",
                "mode": self.mode,
                "message": "Conexión IMECF verificada sin emitir comprobantes.",
                "response": response,
            }
        except IMECFError as exc:
            return {
                "ok": False,
                "provider": "IMECF Platform",
                "mode": self.mode,
                "message": str(exc),
                "status_code": exc.status_code,
            }

    def send_invoice(self, invoice: dict[str, Any]) -> IMECFResult:
        if not self.active:
            raise IMECFError("La empresa fiscal activa no está habilitada para emitir.")
        issuer = self.validate_issuer()
        if not issuer["valid"]:
            raise IMECFError(issuer["message"])
        payload = build_send_payload(invoice)
        data = self._request("POST", "/api/v1/ecf/send", payload=payload)
        return IMECFResult(data=data, request_payload=payload)

    def send_credit_note(self, credit_note: dict[str, Any]) -> IMECFResult:
        if not self.active:
            raise IMECFError("La empresa fiscal activa no está habilitada para emitir.")
        issuer = self.validate_issuer()
        if not issuer["valid"]:
            raise IMECFError(issuer["message"])
        payload = build_credit_note_payload(credit_note)
        data = self._request("POST", "/api/v1/ecf/send", payload=payload)
        return IMECFResult(data=data, request_payload=payload)

    def document_status(self, document_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/ecf/{document_id}/status")

    def track_document(self, document_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/ecf/{document_id}/track")

    def document_by_encf(self, encf: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/ecf/by-encf/{encf}")

    def list_documents(self, filters: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "tipoEcf",
            "estado",
            "search",
            "fechaDesde",
            "fechaHasta",
            "page",
            "limit",
            "ambiente",
        }
        query = {key: value for key, value in filters.items() if key in allowed and value not in (None, "")}
        suffix = f"?{urlencode(query)}" if query else ""
        return self._request("GET", f"/api/v1/ecf{suffix}")

    def lookup_taxpayer(self, value: str) -> dict[str, Any]:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) not in {9, 11}:
            raise IMECFError("El RNC o cédula debe contener 9 u 11 dígitos.")
        return self._request("GET", f"/api/v1/dgii/rnc?{urlencode({'value': digits})}")

    def validate_citizen(self, cedula: str) -> dict[str, Any]:
        digits = "".join(ch for ch in cedula if ch.isdigit())
        if len(digits) != 11:
            raise IMECFError("La consulta JCE requiere una cédula de 11 dígitos.")
        return self._request("GET", f"/api/v1/dgii/jce?{urlencode({'cedula': digits})}")

    def validate_issuer(self) -> dict[str, Any]:
        taxpayer = self.lookup_taxpayer(self.company.issuer_rnc)
        actual_name = str(_find_value(
            taxpayer,
            ("nombre", "nombreComercial", "razonSocial", "razon_social", "name", "legalName"),
        ) or "").strip()
        expected = self.company.issuer_name.upper().strip()
        actual_upper = actual_name.upper()
        valid = bool(actual_name) and (expected in actual_upper or actual_upper in expected)
        if not actual_name:
            valid = True
            message = "DGII no devolvio el nombre del emisor; se continuara con el emisor configurado."
        elif valid:
            message = "Emisor fiscal validado correctamente."
        else:
            message = (
                f"Advertencia: el perfil esperaba '{self.company.issuer_name}', "
                f"pero DGII devolvio '{actual_name}'. IMECF confirmara la emision."
            )
        return {
            "valid": valid,
            "rnc": self.company.issuer_rnc,
            "expected_name": self.company.issuer_name,
            "actual_name": actual_name,
            "status": taxpayer.get("estado"),
            "message": message,
        }

    def signed_xml(self, document_id: str) -> bytes:
        return self._request_bytes("GET", f"/api/v1/ecf/{document_id}/xml")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = self._headers()
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            details = _read_error_body(exc)
            raise IMECFError(_error_message(details, exc.reason), exc.code, details) from exc
        except TimeoutError as exc:
            raise IMECFError("IMECF no respondio a tiempo. El comprobante quedo registrado localmente para reintento.") from exc
        except URLError as exc:
            raise IMECFError(f"No se pudo conectar con IMECF: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise IMECFError("IMECF devolvio una respuesta JSON no valida.") from exc

    def _request_bytes(self, method: str, path: str) -> bytes:
        request = Request(f"{self.base_url}{path}", headers=self._headers(), method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except HTTPError as exc:
            details = _read_error_body(exc)
            raise IMECFError(_error_message(details, exc.reason), exc.code, details) from exc
        except TimeoutError as exc:
            raise IMECFError("IMECF no respondio a tiempo. Intenta descargar el XML nuevamente.") from exc
        except URLError as exc:
            raise IMECFError(f"No se pudo conectar con IMECF: {exc.reason}") from exc

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise IMECFError("IMECF no esta configurado. Define IMECF_API_KEY.")
        return {
            "Accept": "application/json, application/xml",
            "X-API-Key": self.api_key,
            "User-Agent": "AHG-CONSTRUFERRET-POS/0.2",
        }


def build_send_payload(invoice: dict[str, Any]) -> dict[str, Any]:
    ecf_type = str(invoice["ecf_type"])
    buyer_rnc = str(invoice.get("rnc_cedula") or "").strip()
    buyer_name = str(invoice.get("client_name") or "Consumidor Final").strip()
    subtotal = float(invoice["subtotal"])
    tax = float(invoice["tax"])
    total = float(invoice["total"])
    discount_total = float(invoice.get("discount_total") or 0)
    general_discount = float(invoice.get("general_discount") or 0)
    payment_method = str(invoice.get("payment_method") or "efectivo").strip().lower()
    is_credit = payment_method == "credito"
    id_doc: dict[str, Any] = {
        "TipoeCF": ecf_type,
        "IndicadorEnvioDiferido": "1",
        "IndicadorMontoGravado": "0",
        "IndicadorServicioTodoIncluido": "1",
        "TipoIngresos": "01",
        "TipoPago": "2" if is_credit else "1",
    }
    if is_credit:
        id_doc["FechaLimitePago"] = format_api_date(invoice.get("due_date") or invoice.get("issued_at"))
    else:
        id_doc["TablaFormasPago"] = {
            "FormaDePago": [
                {
                    "FormaPago": payment_method_code(payment_method),
                    "MontoPago": money(total),
                }
            ]
        }
    header: dict[str, Any] = {
        "Version": "1.0",
        "IdDoc": id_doc,
        "Totales": {
            "MontoGravadoTotal": money(subtotal),
            "MontoGravadoI1": money(subtotal),
            "MontoExento": "0",
            **({"MontoDescuento": money(discount_total)} if discount_total > 0 and ecf_type != "31" else {}),
            "ITBIS1": "18",
            "TotalITBIS": money(tax),
            "TotalITBIS1": money(tax),
            "MontoTotal": money(total),
            "MontoNoFacturable": "0",
        },
    }
    if buyer_rnc:
        header["Comprador"] = {
            "RNCComprador": buyer_rnc,
            "RazonSocialComprador": buyer_name,
        }
    elif ecf_type == "31":
        raise IMECFError("El e-CF 31 requiere RNC o cedula del comprador.")
    elif ecf_type == "32" and total >= 250000:
        raise IMECFError("El e-CF 32 igual o mayor a RD$250,000 requiere RNC o cédula del comprador.")
    items = [build_item(item, index) for index, item in enumerate(invoice.get("items") or [], start=1)]
    if not items:
        raise IMECFError("La factura necesita al menos un detalle para enviarse a IMECF.")
    item_payload: dict[str, Any] | list[dict[str, Any]] = items[0] if len(items) == 1 else items
    ecf: dict[str, Any] = {
        "Encabezado": header,
        "DetallesItems": {"Item": item_payload},
    }
    if general_discount > 0:
        ecf["DescuentosORecargos"] = {
            "DescuentoORecargo": {
                "NumeroLinea": "1",
                "TipoAjuste": "D",
                "DescripcionDescuentooRecargo": "Descuento general",
                "TipoValor": "$",
                "ValorDescuentooRecargo": money(general_discount),
                "MontoDescuentooRecargo": money(general_discount),
                "IndicadorFacturacionDescuentooRecargo": "1",
            }
        }
    return {
        "ECF": ecf
    }


def build_item(item: dict[str, Any], line_number: int) -> dict[str, Any]:
    discount_amount = float(item.get("discount_amount") or 0)
    payload = {
        "NumeroLinea": str(line_number),
        "IndicadorFacturacion": "1",
        "NombreItem": str(item.get("name") or item.get("product_id") or "Articulo")[:80],
        "IndicadorBienoServicio": "1",
        "CantidadItem": quantity(item.get("quantity", 1)),
        "UnidadMedida": str(item.get("unit_code") or "43"),
        "PrecioUnitarioItem": money(item.get("unit_price", 0)),
        "MontoItem": money(item.get("line_subtotal", 0)),
    }
    if discount_amount > 0:
        payload["DescuentoMonto"] = money(discount_amount)
        payload["TablaSubDescuento"] = {
            "SubDescuento": {
                "TipoSubDescuento": "$",
                "MontoSubDescuento": money(discount_amount),
            }
        }
    return payload


def build_credit_note_payload(note: dict[str, Any]) -> dict[str, Any]:
    buyer_rnc = str(note.get("rnc_cedula") or "").strip()
    source_type = str(note.get("source_ecf_type") or "")
    total = float(note["total"])
    if source_type == "32" and total >= 250000 and not buyer_rnc:
        raise IMECFError("La nota E34 de un E32 igual o mayor a RD$250,000 requiere identificar al comprador.")
    header: dict[str, Any] = {
        "Version": "1.0",
        "IdDoc": {
            "TipoeCF": "34",
            "IndicadorNotaCredito": credit_note_indicator(note.get("source_issued_at"), note.get("issued_at")),
            "IndicadorMontoGravado": "0",
            "TipoIngresos": "01",
            "TipoPago": "1",
        },
        "Totales": {
            "MontoGravadoTotal": money(note["subtotal"]),
            "MontoGravadoI1": money(note["subtotal"]),
            "MontoExento": "0",
            "ITBIS1": "18",
            "TotalITBIS": money(note["tax"]),
            "TotalITBIS1": money(note["tax"]),
            "MontoTotal": money(note["total"]),
            "MontoNoFacturable": "0",
        },
    }
    if buyer_rnc:
        header["Comprador"] = {
            "RNCComprador": buyer_rnc,
            "RazonSocialComprador": str(note.get("client_name") or "Cliente"),
        }
    items = [build_item(item, index) for index, item in enumerate(note.get("items") or [], start=1)]
    return {
        "ECF": {
            "Encabezado": header,
            "DetallesItems": {"Item": items[0] if len(items) == 1 else items},
            "InformacionReferencia": {
                "NCFModificado": str(note["source_encf"]),
                "FechaNCFModificado": format_api_date(note["source_issued_at"]),
                "CodigoModificacion": str(note["modification_code"]),
                "RazonModificacion": str(note["reason"])[:90],
            },
        }
    }


def payment_method_code(method: Any) -> int:
    normalized = str(method or "").strip().lower()
    return {
        "efectivo": 1,
        "cheque": 2,
        "transferencia": 2,
        "tarjeta": 3,
        "paypal": 8,
    }.get(normalized, 1)


def credit_note_indicator(source_issued_at: Any, note_issued_at: Any = None) -> str:
    source_date = parse_api_date(source_issued_at)
    note_date = parse_api_date(note_issued_at) if note_issued_at else datetime.now()
    return "1" if (note_date.date() - source_date.date()).days > 30 else "0"


def parse_api_date(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now()
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.now()


def money(value: Any) -> str:
    return f"{float(value):.2f}"


def quantity(value: Any) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}"


def format_api_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now().strftime("%d-%m-%Y")
    try:
        return datetime.fromisoformat(text).strftime("%d-%m-%Y")
    except ValueError:
        return text


def extract_document_metadata(data: dict[str, Any]) -> dict[str, str]:
    return {
        "provider_document_id": str(_find_value(data, ("id", "documentId", "document_id")) or ""),
        "track_id": str(_find_value(data, ("trackId", "track_id")) or ""),
        "encf": str(_find_value(data, ("eNCF", "encf", "numeroEcf")) or ""),
        "api_status": str(_find_value(data, ("estado", "status", "state")) or "Enviado"),
        "security_code": str(_find_value(data, ("codigoSeguridad", "securityCode")) or ""),
        "dgii_url": str(_find_value(data, ("dgiiUrl", "dgii_url")) or ""),
        "xml_url": str(_find_value(data, ("xmlUrl", "xml_url")) or ""),
    }


def _find_value(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, ""):
                return value[key]
        for child in value.values():
            found = _find_value(child, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_value(child, keys)
            if found not in (None, ""):
                return found
    return None


def _read_error_body(exc: HTTPError) -> Any:
    raw = exc.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return raw


def _error_message(details: Any, fallback: Any) -> str:
    if isinstance(details, dict):
        value = _find_value(details, ("message", "error", "detail"))
        if value:
            return f"IMECF: {value}"
    if isinstance(details, str) and details.strip():
        return f"IMECF: {details.strip()}"
    return f"IMECF: {fallback}"
