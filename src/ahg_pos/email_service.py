from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.request import Request, urlopen


class EmailDeliveryError(RuntimeError):
    pass


def send_prefactura_confirmation(request: dict) -> dict:
    recipient = str(request.get("email", "")).strip().lower()
    if not recipient or "@" not in recipient:
        return {"sent": False, "configured": False, "message": "El cliente no proporcionó un correo válido."}
    subject = f"Prefactura AHG CONSTRUFERRET #{request.get('id', '')}"
    text = (
        f"Hola {request.get('customer_name', 'cliente')},\n\n"
        f"Recibimos tu prefactura #{request.get('id', '')} por un total estimado de RD$ {float(request.get('total') or 0):,.2f}.\n"
        "Nuestro equipo revisará disponibilidad y precio antes de confirmar la venta.\n\n"
        "AHG CONSTRUFERRET"
    )
    resend_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_key:
        sender = os.getenv("EMAIL_FROM", "AHG CONSTRUFERRET <onboarding@resend.dev>").strip()
        body = {"from": sender, "to": [recipient], "subject": subject, "text": text}
        try:
            req = Request("https://api.resend.com/emails", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
            return {"sent": True, "configured": True, "provider": "resend", "id": result.get("id", "")}
        except Exception as exc:
            raise EmailDeliveryError(f"No se pudo enviar el correo por Resend: {exc}") from exc
    host = os.getenv("SMTP_HOST", "").strip()
    if host:
        port = int(os.getenv("SMTP_PORT", "587"))
        username = os.getenv("SMTP_USERNAME", "").strip()
        password = os.getenv("SMTP_PASSWORD", "")
        sender = os.getenv("EMAIL_FROM", username or "no-reply@ahg-construferret.local")
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = sender, recipient, subject
        message.set_content(text)
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls(context=context)
            if username:
                server.login(username, password)
            server.send_message(message)
        return {"sent": True, "configured": True, "provider": "smtp"}
    return {"sent": False, "configured": False, "message": "Correo no configurado: define RESEND_API_KEY o SMTP_HOST."}
