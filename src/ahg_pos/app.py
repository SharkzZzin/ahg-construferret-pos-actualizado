from __future__ import annotations

import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    from .auth import clear_session_cookie, parse_cookie_token, session_cookie
    from .billing_api import FiscalCompanyConfig, IMECFClient, IMECFError, extract_document_metadata
    from .config import settings
    from .database import Database, DatabaseError
    from .email_service import EmailDeliveryError, email_delivery_status, is_valid_email, send_prefactura_confirmation
    from .invoicing import build_ecf_xml, invoice_public_model, make_dgii_qr_svg
    from .local_ai import LocalAIUnavailable, consult_local_model
    from .paypal_api import PayPalClient
    from .recommender import recommend_products, required_filter_questions, suggest_ai_guidance
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ahg_pos.auth import clear_session_cookie, parse_cookie_token, session_cookie
    from ahg_pos.billing_api import FiscalCompanyConfig, IMECFClient, IMECFError, extract_document_metadata
    from ahg_pos.config import settings
    from ahg_pos.database import Database, DatabaseError
    from ahg_pos.email_service import EmailDeliveryError, email_delivery_status, is_valid_email, send_prefactura_confirmation
    from ahg_pos.invoicing import build_ecf_xml, invoice_public_model, make_dgii_qr_svg
    from ahg_pos.local_ai import LocalAIUnavailable, consult_local_model
    from ahg_pos.paypal_api import PayPalClient
    from ahg_pos.recommender import recommend_products, required_filter_questions, suggest_ai_guidance


WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
ACADEMIC_LOGO_FALLBACK = (
    "https://raw.githubusercontent.com/SharkzZzin/ahg-construferret-pos-actualizado/"
    "699c29f30b7873f7567b6177b91236ffff878846/src/ahg_pos/web/static/logo-ahg.png"
)
DB = Database().connect()


def imecf_client(company_id: int | None = None) -> IMECFClient:
    row = DB.get_fiscal_company(company_id) if company_id is not None else DB.get_fiscal_company(active=True)
    if row is None and company_id is None:
        profiles = DB.list_fiscal_companies()
        if profiles:
            row = DB.get_fiscal_company(int(profiles[0]["id"]))
    if row:
        return IMECFClient(company=FiscalCompanyConfig.from_row(row))
    return IMECFClient()


class POSHandler(BaseHTTPRequestHandler):
    server_version = "AHGPos/0.1"

    def route_path(self) -> str:
        parsed = urlparse(self.path)
        if parsed.path in {"/api/index.py", "/api/index"}:
            forwarded = parse_qs(parsed.query).get("_route", [""])[0]
            if forwarded:
                return unquote(forwarded)
        return parsed.path

    def build_public_quote(self, items: list[dict]) -> dict:
        catalog = {str(row["id"]): row for row in DB.list_products()}
        lines = []
        subtotal = 0.0
        tax = 0.0
        for raw in items[:50]:
            product = catalog.get(str(raw.get("product_id", "")))
            if not product or not bool(product.get("active")):
                raise ValueError("Uno de los productos seleccionados ya no está disponible.")
            quantity = float(raw.get("quantity", 1) or 1)
            stock = float(product.get("stock") or 0)
            if quantity <= 0 or quantity > stock:
                raise ValueError(f"Cantidad no disponible para {product['name']}.")
            price = float(product.get("price") or 0)
            line_subtotal = round(quantity * price, 2)
            line_tax = round(line_subtotal * float(product.get("tax_rate") or 0) / 100, 2)
            subtotal += line_subtotal
            tax += line_tax
            lines.append({"product_id": product["id"], "name": product["name"], "sku": product.get("sku", ""), "quantity": quantity, "unit_price": price, "line_subtotal": line_subtotal, "line_tax": line_tax})
        if not lines:
            raise ValueError("Selecciona al menos un producto.")
        return {"lines": lines, "subtotal": round(subtotal, 2), "tax": round(tax, 2), "total": round(subtotal + tax, 2), "persisted": False}

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = self.route_path()
            if path == "/login":
                if self.current_user():
                    self.send_redirect("/")
                else:
                    self.send_file(WEB_DIR / "login.html")
            elif path == "/static/logo-ahg.png":
                self.send_logo()
            elif path in {"/static/login.css", "/static/login.js"}:
                self.send_file(STATIC_DIR / path.removeprefix("/static/"))
            elif path == "/api/auth/session":
                user = self.current_user()
                self.send_json({"authenticated": bool(user), "user": user.public() if user else None})
            elif path.startswith("/api/public/tracking/"):
                token = unquote(path.removeprefix("/api/public/tracking/"))
                tracking = DB.track_invoice_by_token(token)
                self.send_json({"tracking": tracking})
            elif path == "/catalog":
                self.send_file(WEB_DIR / "customer.html")
            elif path in {"/static/customer.css", "/static/customer.js", "/static/polish.css"}:
                self.send_file(STATIC_DIR / path.removeprefix("/static/"))
            elif path == "/api/public/products":
                query = parse_qs(parsed.query)
                result = DB.list_products_page(query.get("q", [""])[0], query.get("page", ["1"])[0], query.get("limit", ["12"])[0])
                available = [row for row in result["items"] if bool(row.get("active")) and float(row.get("stock") or 0) > 0]
                self.send_json({"products": available, "pagination": result})
            elif path == "/api/public/categories":
                self.send_json({"categories": DB.list_categories()})
            elif path == "/api/audit":
                self.require_audit_viewer()
                query = parse_qs(parsed.query)
                self.send_json({"logs": DB.list_audit_logs(query.get("page", ["1"])[0], query.get("limit", ["50"])[0], query.get("q", [""])[0])})
            elif path == "/api/users":
                self.require_fiscal_admin()
                self.send_json({"users": DB.list_users()})
            elif path == "/api/admin/backup":
                user = self.require_fiscal_admin()
                DB.log_audit(int(user.id), "Generar backup", "seguridad", "", {"database": DB.kind})
                body = json.dumps(DB.export_backup(), ensure_ascii=False, indent=2).encode("utf-8")
                self.send_bytes(body, content_type="application/json; charset=utf-8", headers={"Content-Disposition": "attachment; filename=ahg-pos-backup.json"})
            elif path == "/api/public/taxpayer":
                value = parse_qs(parsed.query).get("value", [""])[0]
                self.send_json(imecf_client().lookup_taxpayer(value))
            elif not self.current_user():
                if path.startswith("/api/"):
                    self.send_error_json(401, "Debes iniciar sesión.")
                else:
                    self.send_redirect("/login")
            elif path == "/":
                self.send_file(WEB_DIR / "index.html")
            elif path == "/api/public/quote-requests":
                self.send_json({"requests": DB.list_public_quote_requests()})
            elif path.startswith("/static/"):
                name = unquote(path.removeprefix("/static/"))
                self.send_file(STATIC_DIR / name)
            elif path == "/api/health":
                imecf = imecf_client()
                company = imecf.company
                self.send_json(
                    {
                        "ok": True,
                        "app": settings.app_name,
                        "academic_mode": settings.academic_mode,
                        "database": DB.kind,
                        "fiscal_environment": company.environment,
                        "imecf_configured": imecf.configured,
                        "imecf_enabled": company.enabled,
                        "imecf_active": imecf.active,
                        "fiscal_issuer": {
                            "name": company.issuer_name,
                            "rnc": company.issuer_rnc,
                            "address": settings.company_address,
                            "municipality": settings.company_municipality,
                            "province": settings.company_province,
                            "environment": company.environment,
                            "company_id": company.company_id,
                            "workspace_name": company.workspace_name,
                        },
                        "user": self.current_user().public(),
                        "paypal": PayPalClient().public_config(),
                        "email": email_delivery_status(),
                    }
                )
            elif path == "/api/products":
                query = parse_qs(parsed.query)
                page = query.get("page", ["1"])[0]
                limit = query.get("limit", ["25"])[0]
                search = query.get("q", [""])[0]
                result = DB.list_products_page(search, page, limit)
                self.send_json({"products": result["items"], "pagination": result})
            elif path == "/api/categories":
                self.send_json({"categories": DB.list_categories()})
            elif path == "/api/clients":
                query = parse_qs(parsed.query)
                result = DB.list_clients_page(query.get("q", [""])[0], query.get("page", ["1"])[0], query.get("limit", ["25"])[0])
                self.send_json({"clients": result["items"], "pagination": result})
            elif path == "/api/suppliers":
                query = parse_qs(parsed.query)
                result = DB.list_suppliers_page(query.get("q", [""])[0], query.get("page", ["1"])[0], query.get("limit", ["25"])[0])
                self.send_json({"suppliers": result["items"], "pagination": result})
            elif path == "/api/preinvoices":
                query = parse_qs(parsed.query)
                result = DB.list_preinvoices_page(query.get("page", ["1"])[0], query.get("limit", ["25"])[0])
                self.send_json({"preinvoices": result["items"], "pagination": result})
            elif path.startswith("/api/preinvoices/"):
                preinvoice_id = int(path.removeprefix("/api/preinvoices/"))
                self.send_json({"preinvoice": DB.get_preinvoice(preinvoice_id)})
            elif path == "/api/credit-notes":
                query = parse_qs(parsed.query)
                result = DB.list_credit_notes_page(query.get("page", ["1"])[0], query.get("limit", ["25"])[0])
                for note in result["items"]:
                    note["available_amount"] = round(max(0.0, float(note["total"]) - float(note.get("applied_amount") or 0)), 2)
                self.send_json({"credit_notes": result["items"], "pagination": result})
            elif path == "/api/credit-notes/available":
                query = parse_qs(parsed.query)
                client_id = int(query.get("client_id", ["0"])[0] or 0)
                code = query.get("code", [""])[0]
                notes = DB.available_credit_notes(client_id, code)
                self.send_json({
                    "credit_notes": notes,
                    "available_total": round(sum(float(note["available_amount"]) for note in notes), 2),
                })
            elif path.startswith("/api/credit-notes/"):
                note_id = int(path.removeprefix("/api/credit-notes/"))
                self.send_json({"credit_note": DB.get_credit_note(note_id)})
            elif path == "/api/cash-register":
                self.require_sales_user()
                self.send_json({
                    "session": DB.cash_session_detail(),
                    "history": DB.list_cash_sessions(),
                })
            elif path == "/api/alerts":
                self.send_json({"alerts": DB.low_stock()})
            elif path == "/api/invoices":
                query = parse_qs(parsed.query)
                result = DB.recent_invoices_page(
                    query.get("q", [""])[0], query.get("page", ["1"])[0], query.get("limit", ["25"])[0]
                )
                self.send_json({"invoices": [invoice_public_model(row) for row in result["items"]], "pagination": result, "summary": DB.daily_summary()})
            elif path.startswith("/api/invoices/") and path.count("/") == 3:
                invoice_id = int(path.split("/")[3])
                self.send_json({"invoice": invoice_public_model(DB.get_invoice(invoice_id))})
            elif path == "/api/fiscal/dashboard":
                imecf = imecf_client()
                company = imecf.company
                dashboard = DB.fiscal_dashboard()
                dashboard["documents"] = [invoice_public_model(row) for row in dashboard.get("documents", [])]
                dashboard["provider"] = {
                    "name": "IMECF Platform" if imecf.configured else "Proveedor local",
                    "mode": imecf.mode,
                    "configured": imecf.configured,
                    "active": imecf.active,
                    "environment": company.environment,
                    "base_url": company.base_url,
                    "company_id": company.company_id,
                    "dashboard_url": company.dashboard_url,
                    "issuer_name": company.issuer_name,
                    "issuer_rnc": company.issuer_rnc,
                    "workspace_name": company.workspace_name,
                }
                dashboard["can_manage_credentials"] = self.current_user().role == "admin"
                self.send_json(dashboard)
            elif path == "/api/fiscal/companies":
                self.require_fiscal_admin()
                self.send_json({"companies": DB.list_fiscal_companies()})
            elif path == "/api/imecf/documents":
                self.require_imecf_configured()
                filters = {key: values[0] for key, values in parse_qs(parsed.query).items()}
                self.send_json(imecf_client().list_documents(filters))
            elif path.startswith("/api/imecf/documents/") and path.endswith("/status"):
                self.require_imecf_configured()
                document_id = path.split("/")[4]
                self.send_json(imecf_client().document_status(document_id))
            elif path.startswith("/api/imecf/documents/") and path.endswith("/track"):
                self.require_imecf_configured()
                document_id = path.split("/")[4]
                self.send_json(imecf_client().track_document(document_id))
            elif path.startswith("/api/imecf/documents/") and path.endswith("/xml"):
                self.require_imecf_configured()
                document_id = path.split("/")[4]
                self.send_bytes(imecf_client().signed_xml(document_id), content_type="application/xml; charset=utf-8")
            elif path == "/api/imecf/connection":
                self.send_json(imecf_client().test_connection())
            elif path == "/api/dgii/taxpayer":
                self.require_imecf_configured()
                value = parse_qs(parsed.query).get("value", [""])[0]
                self.send_json(imecf_client().lookup_taxpayer(value))
            elif path == "/api/dgii/jce":
                self.require_imecf_configured()
                cedula = parse_qs(parsed.query).get("cedula", [""])[0]
                self.send_json(imecf_client().validate_citizen(cedula))
            elif path == "/api/fiscal/validate-issuer":
                self.require_imecf_configured()
                self.send_json(imecf_client().validate_issuer())
            elif path.startswith("/api/imecf/by-encf/"):
                self.require_imecf_configured()
                encf = unquote(path.removeprefix("/api/imecf/by-encf/"))
                self.send_json(imecf_client().document_by_encf(encf))
            elif path.startswith("/api/invoices/") and path.endswith("/status"):
                invoice_id = int(path.split("/")[3])
                invoice = DB.get_invoice(invoice_id)
                document_id = self.require_provider_document(invoice)
                response = imecf_client().document_status(document_id)
                DB.update_ecf_api_response(invoice_id, response, extract_document_metadata(response))
                self.send_json({"invoice": invoice_public_model(DB.get_invoice(invoice_id)), "imecf": response})
            elif path.startswith("/api/invoices/") and path.endswith("/track"):
                invoice_id = int(path.split("/")[3])
                invoice = DB.get_invoice(invoice_id)
                document_id = self.require_provider_document(invoice)
                response = imecf_client().track_document(document_id)
                DB.update_ecf_api_response(invoice_id, response, extract_document_metadata(response))
                self.send_json({"invoice": invoice_public_model(DB.get_invoice(invoice_id)), "imecf": response})
            elif path.startswith("/api/invoices/") and path.endswith("/xml"):
                invoice_id = int(path.split("/")[3])
                invoice = DB.get_invoice(invoice_id)
                imecf = imecf_client()
                if imecf.active and invoice.get("provider_document_id"):
                    xml_bytes = imecf.signed_xml(str(invoice["provider_document_id"]))
                    self.send_bytes(xml_bytes, content_type="application/xml; charset=utf-8")
                    return
                xml_text = invoice.get("xml_text") or build_ecf_xml(invoice, imecf.company)
                if not invoice.get("xml_text"):
                    DB.update_invoice_xml(invoice_id, xml_text)
                self.send_text(xml_text, content_type="application/xml; charset=utf-8")
            elif path.startswith("/api/invoices/") and path.endswith("/qr.svg"):
                invoice_id = int(path.split("/")[3])
                invoice = invoice_public_model(DB.get_invoice(invoice_id))
                self.send_bytes(
                    make_dgii_qr_svg(invoice.get("dgii_url")),
                    content_type="image/svg+xml; charset=utf-8",
                    headers={"Cache-Control": "private, no-store"},
                )
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def do_POST(self) -> None:
        try:
            path = self.route_path()
            payload = self.read_json()
            if path == "/api/auth/login":
                identifier = str(payload.get("identifier", "")).strip()
                password = str(payload.get("password", ""))
                if len(identifier) < 3 or len(password) < 6:
                    raise ValueError("Correo/teléfono o contraseña inválidos.")
                result = DB.authenticate_user(identifier, password)
                if not result:
                    self.send_error_json(401, "Credenciales incorrectas.")
                    return
                user, token = result
                DB.log_audit(int(user.id), "Inicio de sesión", "usuario", user.id, {"email": user.email})
                self.send_json(
                    {"ok": True, "user": user.public()},
                    headers={"Set-Cookie": session_cookie(token, settings.auth_secure_cookie)},
                )
            elif path == "/api/auth/logout":
                token = self.session_token()
                user = self.current_user()
                DB.revoke_session(token)
                if user:
                    DB.log_audit(int(user.id), "Cierre de sesión", "usuario", user.id)
                self.send_json(
                    {"ok": True},
                    headers={"Set-Cookie": clear_session_cookie(settings.auth_secure_cookie)},
                )
            elif path == "/api/users":
                user = self.require_fiscal_admin()
                created = DB.save_user(payload)
                DB.log_audit(int(user.id), "Crear usuario", "usuario", created.get("id"), {"email": created.get("email"), "role": created.get("role")})
                self.send_json({"user": created}, status=201)
            elif path == "/api/public/quote-requests":
                customer_name = str(payload.get("customer_name", "")).strip()
                phone = str(payload.get("phone", "")).strip()
                email = str(payload.get("email", "")).strip()
                problem = str(payload.get("problem", "")).strip()
                fiscal = payload.get("fiscal") or {}
                ecf_type = str(fiscal.get("ecf_type", "32")).strip()
                rnc_cedula = "".join(ch for ch in str(fiscal.get("rnc_cedula", "")) if ch.isdigit())
                if ecf_type not in {"31", "32"}:
                    raise ValueError("El tipo de comprobante debe ser e-CF 31 o e-CF 32.")
                if ecf_type == "31" and len(rnc_cedula) not in {9, 11}:
                    raise ValueError("Para e-CF 31 el RNC o cédula es obligatorio y debe ser válido.")
                if len(customer_name) < 2:
                    raise ValueError("Indica el nombre del cliente.")
                if len(phone) < 7:
                    raise ValueError("Indica un teléfono válido.")
                if email and not is_valid_email(email):
                    raise ValueError("Indica un correo electrónico válido para recibir la confirmación.")
                quote = self.build_public_quote(payload.get("items") or [])
                fiscal["ecf_type"] = ecf_type
                fiscal["rnc_cedula"] = rnc_cedula
                request = DB.save_public_quote_request(customer_name, phone, email, problem, quote, fiscal)
                email_result = {"sent": False, "configured": False, "message": "Correo no configurado."}
                try:
                    email_result = send_prefactura_confirmation(request)
                except EmailDeliveryError as exc:
                    email_result = {"sent": False, "configured": True, "message": str(exc)}
                DB.log_audit(None, "Recibir prefactura", "pre-factura pública", request.get("id"), {"email": email, "email_sent": email_result.get("sent", False)})
                self.send_json({"request": request, "email": email_result}, status=201)
            elif False and path == "/api/public/ai/agent":
                action = str(payload.get("action", "consult")).strip().lower()
                if action == "prepare_quote":
                    self.send_json({"quote": prepare_quote(DB, payload.get("items") or [])})
                    return
                if action not in {"consult", "recommend"}:
                    raise ValueError("Acción del agente no válida.")
                budget = payload.get("budget")
                result = consult_agent(
                    DB,
                    str(payload.get("query", "")).strip(),
                    history=payload.get("history") or [],
                    context=str(payload.get("context", "")).strip(),
                    budget=float(budget) if budget not in (None, "") else None,
                    limit=int(payload.get("limit", 6)),
                )
                self.send_json(result)
            elif path == "/api/public/ai/consult":
                query = str(payload.get("query", "")).strip()
                history = payload.get("history") or []
                context = str(payload.get("context", "")).strip()
                recent_context = " ".join(
                    str(item.get("content", "")) for item in history[-6:] if isinstance(item, dict)
                )
                autonomous_query = " ".join(part for part in (recent_context, context, query) if part).strip()
                budget = payload.get("budget")
                recommendations = recommend_products(
                    DB,
                    autonomous_query,
                    limit=min(8, max(1, int(payload.get("limit", 6)))),
                    budget=float(budget) if budget not in (None, "") else None,
                )
                guidance = suggest_ai_guidance(DB, autonomous_query, recommendations)
                questions: list[str] = []
                for recommendation in recommendations:
                    questions.extend(recommendation.get("questions", []))
                questions = list(dict.fromkeys(questions))[:3]
                if not autonomous_query:
                    reply = "Cuéntame qué problema quieres resolver, dónde lo usarás y si conoces la medida o presupuesto."
                elif recommendations:
                    top = recommendations[0]
                    reply = (
                        f"Por lo que describes, empezaría con {top['name']}. "
                        f"{top.get('advisor_summary', '')} {top.get('sales_tip', '')}"
                    )
                    if top.get("complements"):
                        reply += " También revisaría: " + ", ".join(top["complements"]) + "."
                else:
                    reply = guidance.get("follow_up_prompt") or "Necesito un poco más de contexto para recomendarte algo compatible."
                local_ai = None
                try:
                    local_ai = consult_local_model(query, history, recommendations)
                except LocalAIUnavailable:
                    # El flujo deterministico sigue funcionando si Ollama no esta disponible.
                    local_ai = None
                if local_ai:
                    reply = local_ai["reply"]
                    questions = local_ai["next_questions"] or questions
                # Estos filtros son obligatorios: el modelo puede redactar una
                # respuesta convincente, pero nunca debe inventar una medida.
                questions = list(dict.fromkeys(required_filter_questions(autonomous_query) + questions))[:4]
                DB.log_audit(self.current_user().id if self.current_user() else None, "Consulta IA", "ia", "", {"query": query[:300], "recommendations": len(recommendations)})
                self.send_json({
                    "reply": reply,
                    "recommendations": recommendations,
                    "guidance": guidance,
                    "next_questions": questions,
                    "autonomous": True,
                    "local_ai": bool(local_ai),
                    "local_ai_model": local_ai.get("model", "") if local_ai else "",
                })
            elif not self.current_user():
                self.send_error_json(401, "Debes iniciar sesión.")
            elif path == "/api/recommend":
                query = str(payload.get("query", "")).strip()
                limit = int(payload.get("limit", 6))
                budget = payload.get("budget")
                recommendations = recommend_products(DB, query, limit=limit, budget=float(budget) if budget else None)
                DB.log_ai_query(query, len(recommendations))
                self.send_json({
                    "recommendations": recommendations,
                    "guidance": suggest_ai_guidance(DB, query, recommendations),
                })
            elif path == "/api/payments/paypal/order":
                self.require_sales_user()
                amount = float(payload.get("amount_dop", 0))
                order = PayPalClient().create_order(amount, str(payload.get("description", "Venta AHG")))
                self.send_json({"order": order}, status=201)
            elif path.startswith("/api/payments/paypal/") and path.endswith("/capture"):
                self.require_sales_user()
                order_id = unquote(path.split("/")[4])
                capture = PayPalClient().capture_order(order_id)
                if str(capture.get("status", "")).upper() != "COMPLETED":
                    raise ValueError("PayPal no confirmó el pago.")
                self.send_json({"capture": capture})
            elif path.startswith("/api/payments/paypal/") and path.endswith("/authorize"):
                self.require_sales_user()
                order_id = unquote(path.split("/")[4])
                authorization = PayPalClient().authorize_order(order_id)
                if str(authorization.get("status", "")).upper() not in {"COMPLETED", "CREATED"}:
                    raise ValueError("PayPal no confirmo la autorizacion.")
                self.send_json({"authorization": authorization})
            elif path == "/api/products":
                self.require_product_editor()
                product = DB.save_product(payload)
                DB.log_audit(int(self.current_user().id), "Crear artículo", "producto", product.get("id"), {"sku": product.get("sku"), "name": product.get("name")})
                self.send_json({"product": product}, status=201)
            elif path == "/api/clients":
                self.require_sales_user()
                client = DB.save_client(payload)
                DB.log_audit(int(self.current_user().id), "Crear cliente", "cliente", client.get("id"), {"name": client.get("name")})
                self.send_json({"client": client}, status=201)
            elif path == "/api/suppliers":
                self.require_product_editor()
                supplier = DB.save_supplier(payload)
                DB.log_audit(int(self.current_user().id), "Crear proveedor", "proveedor", supplier.get("id"), {"name": supplier.get("name")})
                self.send_json({"supplier": supplier}, status=201)
            elif path == "/api/preinvoices":
                user = self.require_sales_user()
                draft = DB.save_preinvoice(payload, user.id)
                DB.log_audit(int(user.id), "Guardar pre-factura", "pre-factura", draft.get("id"), {"total": draft.get("total"), "status": draft.get("status")})
                self.send_json({"preinvoice": draft}, status=201)
            elif path.startswith("/api/preinvoices/") and path.endswith("/issue"):
                self.require_sales_user()
                preinvoice_id = int(path.split("/")[3])
                draft = DB.get_preinvoice(preinvoice_id)
                result = self.emit_invoice(
                    {
                        "ecf_type": draft["ecf_type"],
                        "client": {
                            "id": draft.get("client_id"),
                            "rnc_cedula": draft.get("rnc_cedula", ""),
                            "name": draft.get("client_name", ""),
                            "phone": draft.get("phone", ""),
                            "email": draft.get("email", ""),
                            "address": draft.get("address", ""),
                        },
                        "payment_method": str(payload.get("payment_method") or draft["payment_method"]),
                        "payments": payload.get("payments") or [],
                        "general_discount": draft.get("general_discount", 0),
                        "credit_amount": payload.get("credit_amount", 0),
                        "credit_note_code": payload.get("credit_note_code", ""),
                        "items": [
                            {
                                "product_id": item["product_id"],
                                "quantity": item["quantity"],
                                "unit_price": item["unit_price"],
                                "discount_amount": item.get("discount_amount", 0),
                            }
                            for item in draft["items"]
                        ],
                    }
                )
                DB.mark_preinvoice_emitted(preinvoice_id, int(result["invoice"]["id"]))
                result["preinvoice_id"] = preinvoice_id
                self.send_json(result, status=201)
            elif path == "/api/credit-notes":
                self.require_sales_user()
                imecf = imecf_client()
                note = DB.create_credit_note(
                    source_invoice_id=int(payload.get("source_invoice_id")),
                    modification_code=str(payload.get("modification_code", "1")),
                    reason=str(payload.get("reason", "")),
                    fiscal_environment=imecf.company.environment,
                    expires_at=str(payload.get("expires_at", "")),
                )
                warning = ""
                if imecf.active:
                    try:
                        result = imecf.send_credit_note(note)
                        DB.save_credit_note_api_result(
                            int(note["id"]),
                            extract_document_metadata(result.data),
                            result.request_payload,
                            result.data,
                        )
                    except IMECFError as exc:
                        warning = str(exc)
                        DB.save_credit_note_api_result(
                            int(note["id"]), {}, None,
                            exc.details if isinstance(exc.details, dict) else None,
                            warning,
                        )
                self.send_json(
                    {"credit_note": DB.get_credit_note(int(note["id"])), "imecf_warning": warning},
                    status=201,
                )
            elif path == "/api/cash-register/open":
                user = self.require_sales_user()
                session = DB.open_cash_session(
                    int(user.id), float(payload.get("opening_amount") or 0), str(payload.get("notes") or "")
                )
                DB.log_audit(int(user.id), "Abrir caja", "cuadre", session.get("id"), {"opening_amount": session.get("opening_amount")})
                self.send_json({"session": session}, status=201)
            elif path == "/api/cash-register/movement":
                user = self.require_sales_user()
                session = DB.add_cash_movement(
                    int(user.id), str(payload.get("movement_type") or ""),
                    float(payload.get("amount") or 0), str(payload.get("description") or ""),
                )
                DB.log_audit(int(user.id), "Movimiento de caja", "cuadre", session.get("id"), {"movement_type": payload.get("movement_type"), "amount": payload.get("amount")})
                self.send_json({"session": session}, status=201)
            elif path == "/api/cash-register/close":
                user = self.require_sales_user()
                session = DB.close_cash_session(
                    int(user.id), float(payload.get("counted_cash") or 0), str(payload.get("notes") or "")
                )
                DB.log_audit(int(user.id), "Cerrar caja", "cuadre", session.get("id"), {"expected": session.get("expected_cash"), "counted": session.get("counted_cash"), "difference": session.get("difference")})
                self.send_json({"session": session})
            elif path == "/api/fiscal/companies":
                user = self.require_fiscal_admin()
                password = str(payload.pop("current_password", ""))
                if not DB.verify_user_password(user.id, password):
                    raise PermissionError("La contraseña administrativa no es correcta.")
                company_id = payload.pop("id", None)
                company = DB.save_fiscal_company(
                    payload,
                    user_id=user.id,
                    company_id=int(company_id) if company_id else None,
                )
                self.send_json({"company": company}, status=201 if not company_id else 200)
            elif path.startswith("/api/fiscal/companies/"):
                user = self.require_fiscal_admin()
                parts = path.strip("/").split("/")
                if len(parts) != 5:
                    raise ValueError("Acción fiscal no válida.")
                company_id = int(parts[3])
                action = parts[4]
                client = imecf_client(company_id)
                if action == "validate":
                    result = client.validate_issuer()
                    DB.record_fiscal_validation(company_id, bool(result["valid"]), str(result["message"]))
                    self.send_json(result)
                elif action == "test":
                    result = client.test_connection()
                    DB.record_fiscal_connection_test(company_id, bool(result["ok"]), str(result["message"]))
                    self.send_json(result)
                elif action == "activate":
                    company = DB.activate_fiscal_company(company_id, user.id)
                    self.send_json({"ok": True, "company_id": company["id"]})
                else:
                    raise ValueError("Acción fiscal no válida.")
            elif path == "/api/invoices":
                user = self.require_sales_user()
                result = self.emit_invoice(payload)
                DB.log_audit(int(user.id), "Emitir factura", "factura", result.get("invoice", {}).get("id"), {"encf": result.get("invoice", {}).get("en_ncf"), "ecf_type": result.get("invoice", {}).get("ecf_type")})
                self.send_json(result, status=201)
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def do_PUT(self) -> None:
        try:
            path = self.route_path()
            if not self.current_user():
                self.send_error_json(401, "Debes iniciar sesión.")
                return
            if path.startswith("/api/users/"):
                user = self.require_fiscal_admin()
                user_id = int(path.removeprefix("/api/users/"))
                updated = DB.save_user(self.read_json(), user_id=user_id)
                DB.log_audit(int(user.id), "Actualizar usuario", "usuario", user_id, {"email": updated.get("email"), "role": updated.get("role"), "active": updated.get("active")})
                self.send_json({"user": updated})
            elif path.startswith("/api/products/"):
                self.require_product_editor()
                product_id = unquote(path.removeprefix("/api/products/"))
                product = DB.save_product(self.read_json(), product_id=product_id)
                DB.log_audit(int(self.current_user().id), "Actualizar artículo", "producto", product.get("id"), {"sku": product.get("sku"), "name": product.get("name")})
                self.send_json({"product": product})
            elif path.startswith("/api/clients/"):
                self.require_sales_user()
                client_id = int(path.removeprefix("/api/clients/"))
                client = DB.save_client(self.read_json(), client_id=client_id)
                DB.log_audit(int(self.current_user().id), "Actualizar cliente", "cliente", client.get("id"), {"name": client.get("name")})
                self.send_json({"client": client})
            elif path.startswith("/api/suppliers/"):
                self.require_product_editor()
                supplier_id = int(path.removeprefix("/api/suppliers/"))
                supplier = DB.save_supplier(self.read_json(), supplier_id=supplier_id)
                DB.log_audit(int(self.current_user().id), "Actualizar proveedor", "proveedor", supplier.get("id"), {"name": supplier.get("name")})
                self.send_json({"supplier": supplier})
            elif path.startswith("/api/preinvoices/"):
                user = self.require_sales_user()
                preinvoice_id = int(path.removeprefix("/api/preinvoices/"))
                draft = DB.save_preinvoice(self.read_json(), user.id, preinvoice_id=preinvoice_id)
                DB.log_audit(int(user.id), "Actualizar pre-factura", "pre-factura", draft.get("id"), {"total": draft.get("total"), "status": draft.get("status")})
                self.send_json({"preinvoice": draft})
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def do_DELETE(self) -> None:
        try:
            path = self.route_path()
            if not self.current_user():
                self.send_error_json(401, "Debes iniciar sesión.")
                return
            payload = self.read_json()
            if path.startswith("/api/clients/"):
                self.require_sales_user()
                client_id = int(path.removeprefix("/api/clients/"))
                DB.delete_client(client_id, str(payload.get("password", "")))
                self.send_json({"ok": True})
            elif path.startswith("/api/suppliers/"):
                self.require_product_editor()
                supplier_id = int(path.removeprefix("/api/suppliers/"))
                DB.delete_supplier(supplier_id, str(payload.get("password", "")))
                self.send_json({"ok": True})
            elif path.startswith("/api/public/quote-requests/"):
                user = self.require_sales_user()
                request_id = int(path.removeprefix("/api/public/quote-requests/"))
                deleted = DB.delete_public_quote_request(request_id)
                DB.log_audit(
                    int(user.id),
                    "Eliminar prefactura Customer",
                    "pre-factura pública",
                    request_id,
                    {"customer_name": deleted.get("customer_name"), "total": deleted.get("total")},
                )
                self.send_json({"ok": True, "id": request_id})
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        if length > 1_000_000:
            raise ValueError("La solicitud supera el tamaño permitido.")
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def require_product_editor(self) -> None:
        user = self.current_user()
        if not user or user.role not in {"admin", "gerente", "almacen"}:
            raise PermissionError("No tienes permiso para modificar artículos.")

    def require_sales_user(self):
        user = self.current_user()
        if not user or user.role not in {"admin", "gerente", "cajero", "vendedor"}:
            raise PermissionError("No tienes permiso para gestionar ventas o clientes.")
        return user

    def require_audit_viewer(self):
        user = self.current_user()
        if not user or user.role not in {"admin", "gerente"}:
            raise PermissionError("Solo un administrador o gerente puede consultar la auditoría.")
        return user

    def emit_invoice(self, payload: dict) -> dict:
        imecf = imecf_client()
        invoice = DB.create_invoice(
            ecf_type=str(payload.get("ecf_type", "32")),
            client=payload.get("client") or {},
            items=payload.get("items") or [],
            payment_method=str(payload.get("payment_method", "efectivo")),
            fiscal_environment=imecf.company.environment,
            general_discount=float(payload.get("general_discount") or 0),
            general_discount_percent=float(payload.get("general_discount_percent") or 0),
            credit_amount=float(payload.get("credit_amount") or 0),
            credit_note_code=str(payload.get("credit_note_code") or ""),
            payments=payload.get("payments") or None,
        )
        xml_text = build_ecf_xml(invoice, imecf.company)
        DB.update_invoice_xml(int(invoice["id"]), xml_text)
        imecf_warning = ""
        if imecf.active:
            try:
                result = imecf.send_invoice(invoice)
                DB.save_ecf_api_record(
                    int(invoice["id"]),
                    metadata=extract_document_metadata(result.data),
                    request_payload=result.request_payload,
                    response_payload=result.data,
                )
            except IMECFError as exc:
                imecf_warning = str(exc)
                DB.save_ecf_api_record(
                    int(invoice["id"]),
                    request_payload=None,
                    response_payload=exc.details if isinstance(exc.details, dict) else None,
                    error=imecf_warning,
                )
        tracking_token = invoice.get("tracking_token", "")
        invoice = DB.get_invoice(int(invoice["id"]))
        invoice["tracking_token"] = tracking_token
        return {
            "invoice": invoice_public_model(invoice),
            "imecf_active": imecf.active,
            "imecf_warning": imecf_warning,
        }

    def require_fiscal_admin(self):
        user = self.current_user()
        if not user or user.role != "admin":
            raise PermissionError("Solo un administrador puede gestionar credenciales fiscales.")
        return user

    def send_json(self, payload: dict, status: int = 200, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, status: int = 200, content_type: str = "application/octet-stream", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def session_token(self) -> str:
        return parse_cookie_token(self.headers.get("Cookie"))

    def current_user(self):
        if hasattr(self, "_current_user"):
            return self._current_user
        self._current_user = DB.session_user(self.session_token())
        return self._current_user

    def send_redirect(self, location: str, status: int = 302) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def require_imecf(self) -> None:
        if not imecf_client().active:
            raise IMECFError("No hay una empresa IMECF activa y habilitada.")

    def require_imecf_configured(self) -> None:
        if not imecf_client().configured:
            raise IMECFError("La empresa fiscal activa no tiene credenciales IMECF configuradas.")

    def require_provider_document(self, invoice: dict) -> str:
        self.require_imecf()
        document_id = str(invoice.get("provider_document_id") or "")
        if not document_id:
            raise IMECFError("Esta factura local todavia no tiene un ID de documento IMECF.")
        return document_id

    def send_file(self, path: Path) -> None:
        target = path.resolve()
        allowed = {WEB_DIR.resolve(), STATIC_DIR.resolve()}
        if not target.exists() or not any(parent in [target, *target.parents] for parent in allowed):
            self.send_error_json(404, "Archivo no encontrado.")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_logo(self) -> None:
        """Serve the bundled logo, with a pinned academic-release fallback for file-only deploys."""
        logo_path = STATIC_DIR / "logo-ahg.png"
        if logo_path.exists():
            self.send_file(logo_path)
        else:
            self.send_redirect(ACADEMIC_LOGO_FALLBACK)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def handle_exception(self, exc: Exception) -> None:
        if isinstance(exc, PermissionError):
            self.send_error_json(403, str(exc))
        elif isinstance(exc, (DatabaseError, IMECFError, ValueError, TypeError, json.JSONDecodeError)):
            self.send_error_json(400, str(exc))
        else:
            self.send_error_json(500, f"Error interno: {exc}")

    def log_message(self, format: str, *args) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))


def run() -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), POSHandler)
    print(f"{settings.app_name} listo en http://{settings.host}:{settings.port}")
    print(f"Base de datos: {DB.kind}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        DB.close()
        server.server_close()


if __name__ == "__main__":
    run()
    from ahg_pos.auth import clear_session_cookie, parse_cookie_token, session_cookie
