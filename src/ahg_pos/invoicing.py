from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from .config import settings


ECF_TYPES = {
    "31": "Factura de Cr\u00e9dito Fiscal Electr\u00f3nica",
    "32": "Factura de Consumo Electr\u00f3nica",
}


def fiscal_warning(ecf_type: str, total: float) -> str:
    if ecf_type == "31":
        return "e-CF 31 requiere comprador identificado y rangos autorizados por DGII."
    if ecf_type == "32" and total < 250000:
        return "e-CF 32 menor a RD$250,000 puede entrar en resumen de consumo segun reglas DGII."
    return "e-CF 32 de consumo emitido para cliente final."


def make_security_code(en_ncf: str, total: float, issued_at: str) -> str:
    raw = f"{en_ncf}|{total:.2f}|{issued_at}|{settings.company_rnc}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6].upper()


def build_ecf_xml(invoice: dict[str, Any], fiscal_company: Any = None) -> str:
    issuer_rnc = getattr(fiscal_company, "issuer_rnc", settings.company_rnc)
    issuer_name = getattr(fiscal_company, "issuer_name", settings.company_name)
    environment = getattr(fiscal_company, "environment", settings.fiscal_environment)
    root = Element("ECF")
    root.set("version", "1.0")
    root.set("modo", environment)

    encabezado = SubElement(root, "Encabezado")
    id_doc = SubElement(encabezado, "IdDoc")
    add_text(id_doc, "TipoeCF", invoice["ecf_type"])
    add_text(id_doc, "eNCF", invoice["en_ncf"])
    add_text(id_doc, "FechaEmision", format_date(invoice["issued_at"]))

    emisor = SubElement(encabezado, "Emisor")
    add_text(emisor, "RNCEmisor", issuer_rnc)
    add_text(emisor, "RazonSocialEmisor", issuer_name)
    add_text(emisor, "DireccionEmisor", settings.company_address)

    comprador = SubElement(encabezado, "Comprador")
    add_text(comprador, "RNCComprador", invoice.get("rnc_cedula") or "")
    add_text(comprador, "RazonSocialComprador", invoice.get("client_name") or "Consumidor Final")

    totales = SubElement(encabezado, "Totales")
    add_money(totales, "MontoGravadoTotal", invoice["subtotal"])
    add_money(totales, "MontoDescuento", invoice.get("discount_total", 0))
    add_money(totales, "ITBIS18", invoice["tax"])
    add_money(totales, "MontoTotal", invoice["total"])

    detalles = SubElement(root, "DetallesItems")
    for index, item in enumerate(invoice["items"], start=1):
        detalle = SubElement(detalles, "Item")
        add_text(detalle, "NumeroLinea", index)
        add_text(detalle, "CodigoItem", item["product_id"])
        add_text(detalle, "NombreItem", item["name"])
        add_money(detalle, "CantidadItem", item["quantity"])
        add_money(detalle, "PrecioUnitarioItem", item["unit_price"])
        add_money(detalle, "DescuentoMonto", item.get("discount_amount", 0))
        add_money(detalle, "MontoItem", item["line_total"])

    referencia = SubElement(root, "ReferenciaSistema")
    add_text(referencia, "CodigoSeguridad", make_security_code(invoice["en_ncf"], float(invoice["total"]), invoice["issued_at"]))
    add_text(
        referencia,
        "Nota",
        "XML generado por el sistema local. La emision fiscal se valida contra el proveedor configurado.",
    )

    rough = tostring(root, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def invoice_public_model(invoice: dict[str, Any]) -> dict[str, Any]:
    provider_response: dict[str, Any] = {}
    raw_response = invoice.get("provider_response_json")
    if raw_response:
        try:
            provider_response = json.loads(raw_response)
        except (TypeError, json.JSONDecodeError):
            provider_response = {}
    provider_code = find_nested_value(provider_response, ("codigoSeguridad", "securityCode"))
    provider_dgii_url = find_nested_value(provider_response, ("dgiiUrl", "dgii_url"))
    provider_xml_url = find_nested_value(provider_response, ("xmlUrl", "xml_url"))
    code = provider_code or make_security_code(invoice["en_ncf"], float(invoice["total"]), invoice["issued_at"])
    return {
        **invoice,
        "display_encf": invoice.get("provider_encf") or invoice["en_ncf"],
        "ecf_label": ECF_TYPES.get(invoice["ecf_type"], invoice["ecf_type"]),
        "security_code": code,
        "dgii_url": provider_dgii_url or "",
        "xml_url": provider_xml_url or "",
        "fiscal_warning": fiscal_warning(invoice["ecf_type"], float(invoice["total"])),
    }


def find_nested_value(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) not in (None, ""):
                return value[key]
        for child in value.values():
            found = find_nested_value(child, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_nested_value(child, keys)
            if found not in (None, ""):
                return found
    return None


def add_text(parent: Element, name: str, value: Any) -> None:
    child = SubElement(parent, name)
    child.text = str(value)


def add_money(parent: Element, name: str, value: Any) -> None:
    child = SubElement(parent, name)
    child.text = f"{float(value):.2f}"


def format_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d-%m-%Y")
    except ValueError:
        return value[:10]
