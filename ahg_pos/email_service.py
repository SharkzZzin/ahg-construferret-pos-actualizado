from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmailDeliveryError(RuntimeError):
    pass


def is_valid_email(value: str) -> bool:
    recipient = str(value or "").strip().lower()
    parsed = parseaddr(recipient)[1]
    return parsed == recipient and bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", recipient))


def email_delivery_status() -> dict:
    if os.getenv("RESEND_API_KEY", "").strip():
        return {"configured": True, "provider": "resend"}
    if os.getenv("SMTP_HOST", "").strip():
        return {"configured": True, "provider": "smtp"}
    return {"configured": False, "provider": None}


def _confirmation_content(request: dict) -> tuple[str, str, str]:
    request_id = str(request.get("id", "")).strip()
    customer_name = str(request.get("customer_name") or "cliente").strip()
    total = float(request.get("total") or 0)
    items = request.get("items") or []
    subject = f"Recibimos tu prefactura #{request_id} | AHG CONSTRUFERRET"
    item_lines = []
    item_rows = []
    for item in items[:50]:
        name = str(item.get("name") or "Producto").strip()
        quantity = float(item.get("quantity") or 0)
        item_lines.append(f"- {name} x {quantity:g}")
        item_rows.append(
            "<tr>"
            f"<td style='padding:8px;border-bottom:1px solid #e8ecea'>{escape(name)}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #e8ecea;text-align:right'>{quantity:g}</td>"
            "</tr>"
        )
    details_text = "\n".join(item_lines) or "- Productos indicados en la solicitud"
    text = (
        f"Hola {customer_name},\n\n"
        f"Tu prefactura #{request_id} fue recibida correctamente por AHG CONSTRUFERRET.\n"
        f"Total estimado: RD$ {total:,.2f}\n\n"
        f"Productos:\n{details_text}\n\n"
        "Nuestro equipo revisará disponibilidad y precio antes de confirmar la venta. "
        "Conserva este número como referencia.\n\n"
        "AHG CONSTRUFERRET"
    )
    html = f"""<!doctype html>
<html lang="es"><body style="margin:0;background:#f4f7f5;font-family:Arial,sans-serif;color:#17342c">
<div style="max-width:620px;margin:0 auto;padding:32px 18px">
  <div style="background:#fff;border-radius:16px;padding:28px;border:1px solid #dce7e1">
    <p style="margin:0 0 8px;color:#168451;font-weight:700">AHG CONSTRUFERRET</p>
    <h1 style="font-size:24px;margin:0 0 18px">Prefactura recibida</h1>
    <p>Hola {escape(customer_name)}, recibimos correctamente tu solicitud <strong>#{escape(request_id)}</strong>.</p>
    <table style="width:100%;border-collapse:collapse;margin:18px 0">
      <thead><tr><th style="padding:8px;text-align:left;background:#eef7f2">Producto</th><th style="padding:8px;text-align:right;background:#eef7f2">Cantidad</th></tr></thead>
      <tbody>{''.join(item_rows)}</tbody>
    </table>
    <p style="font-size:18px"><strong>Total estimado: RD$ {total:,.2f}</strong></p>
    <p>Revisaremos disponibilidad y precio antes de confirmar la venta. Conserva el número de prefactura como referencia.</p>
  </div>
</div></body></html>"""
    return subject, text, html


def send_prefactura_confirmation(request: dict) -> dict:
    recipient = str(request.get("email", "")).strip().lower()
    if not recipient:
        return {"sent": False, "configured": email_delivery_status()["configured"], "message": "El cliente no proporcionó correo."}
    if not is_valid_email(recipient):
        return {"sent": False, "configured": email_delivery_status()["configured"], "message": "El correo proporcionado no es válido."}

    subject, text, html = _confirmation_content(request)
    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_key:
        sender = os.getenv("EMAIL_FROM", "AHG CONSTRUFERRET <onboarding@resend.dev>").strip()
        body = {"from": sender, "to": [recipient], "subject": subject, "text": text, "html": html}
        request_id = str(request.get("id", "unknown")).strip() or "unknown"
        try:
            api_request = Request(
                "https://api.resend.com/emails",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": f"ahg-prefactura-{request_id}",
                },
                method="POST",
            )
            with urlopen(api_request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
            return {"sent": True, "configured": True, "provider": "resend", "id": result.get("id", "")}
        except HTTPError as exc:
            raise EmailDeliveryError(f"El proveedor de correo rechazó el envío (HTTP {exc.code}).") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise EmailDeliveryError("El proveedor de correo no respondió correctamente.") from exc

    host = os.getenv("SMTP_HOST", "").strip()
    if host:
        port = int(os.getenv("SMTP_PORT", "587"))
        username = os.getenv("SMTP_USERNAME", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        sender = os.getenv("EMAIL_FROM", username or "no-reply@ahg-construferret.local").strip()
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = sender, recipient, subject
        message.set_content(text)
        message.add_alternative(html, subtype="html")
        context = ssl.create_default_context()
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as server:
                    if username:
                        server.login(username, password)
                    server.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    if os.getenv("SMTP_USE_TLS", "1") != "0":
                        server.starttls(context=context)
                    if username:
                        server.login(username, password)
                    server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailDeliveryError("No se pudo completar el envío por SMTP.") from exc
        return {"sent": True, "configured": True, "provider": "smtp"}

    return {
        "sent": False,
        "configured": False,
        "message": "El servicio de correo aún no está configurado.",
    }
