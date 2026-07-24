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
    from .invoicing import build_ecf_xml, invoice_public_model
    from .paypal_api import PayPalClient
    from .recommender import recommend_products, suggest_ai_guidance
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ahg_pos.auth import clear_session_cookie, parse_cookie_token, session_cookie
    from ahg_pos.billing_api import FiscalCompanyConfig, IMECFClient, IMECFError, extract_document_metadata
    from ahg_pos.config import settings
    from ahg_pos.database import Database, DatabaseError
    from ahg_pos.invoicing import build_ecf_xml, invoice_public_model
    from ahg_pos.paypal_api import PayPalClient
    from ahg_pos.recommender import recommend_products, suggest_ai_guidance


WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
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

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/login":
                if self.current_user():
                    self.send_redirect("/")
                else:
                    self.send_file(WEB_DIR / "login.html")
            elif path in {"/static/login.css", "/static/login.js"}:
                self.send_file(STATIC_DIR / path.removeprefix("/static/"))
            elif path == "/api/auth/session":
                user = self.current_user()
                self.send_json({"authenticated": bool(user), "user": user.public() if user else None})
            elif not self.current_user():
                if path.startswith("/api/"):
                    self.send_error_json(401, "Debes iniciar sesión.")
                else:
                    self.send_redirect("/login")
            elif path == "/":
                self.send_file(WEB_DIR / "index.html")
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
                        "database": DB.kind,
                        "fiscal_environment": company.environment,
                        "imecf_configured": imecf.configured,
                        "imecf_enabled": company.enabled,
                        "imecf_active": imecf.active,
                        "fiscal_issuer": {
                            "name": company.issuer_name,
                            "rnc": company.issuer_rnc,
                            "address": settings.company_address,
                            "environment": company.environment,
                            "company_id": company.company_id,
                            "workspace_name": company.workspace_name,
                        },
                        "user": self.current_user().public(),
                        "paypal": PayPalClient().public_config(),
                    }
                )
            elif path == "/api/products":
                self.send_json({"products": DB.list_products()})
            elif path == "/api/categories":
                self.send_json({"categories": DB.list_categories()})
            elif path == "/api/clients":
                self.send_json({"clients": DB.list_clients()})
            elif path == "/api/suppliers":
                self.send_json({"suppliers": DB.list_suppliers()})
            elif path == "/api/preinvoices":
                self.send_json({"preinvoices": DB.list_preinvoices()})
            elif path.startswith("/api/preinvoices/"):
                preinvoice_id = int(path.removeprefix("/api/preinvoices/"))
                self.send_json({"preinvoice": DB.get_preinvoice(preinvoice_id)})
            elif path == "/api/credit-notes":
                self.send_json({"credit_notes": DB.list_credit_notes()})
            elif path == "/api/alerts":
                self.send_json({"alerts": DB.low_stock()})
            elif path == "/api/invoices":
                limit = int(parse_qs(parsed.query).get("limit", ["25"])[0])
                self.send_json({"invoices": DB.recent_invoices(limit=limit), "summary": DB.daily_summary()})
            elif path.startswith("/api/invoices/") and path.count("/") == 3:
                invoice_id = int(path.split("/")[3])
                self.send_json({"invoice": invoice_public_model(DB.get_invoice(invoice_id))})
            elif path == "/api/fiscal/dashboard":
                imecf = imecf_client()
                company = imecf.company
                dashboard = DB.fiscal_dashboard()
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
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
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
                self.send_json(
                    {"ok": True, "user": user.public()},
                    headers={"Set-Cookie": session_cookie(token, settings.auth_secure_cookie)},
                )
            elif path == "/api/auth/logout":
                token = self.session_token()
                DB.revoke_session(token)
                self.send_json(
                    {"ok": True},
                    headers={"Set-Cookie": clear_session_cookie(settings.auth_secure_cookie)},
                )
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
                self.send_json({"product": product}, status=201)
            elif path == "/api/clients":
                self.require_sales_user()
                client = DB.save_client(payload)
                self.send_json({"client": client}, status=201)
            elif path == "/api/suppliers":
                self.require_product_editor()
                supplier = DB.save_supplier(payload)
                self.send_json({"supplier": supplier}, status=201)
            elif path == "/api/preinvoices":
                user = self.require_sales_user()
                draft = DB.save_preinvoice(payload, user.id)
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
                        "payment_method": draft["payment_method"],
                        "general_discount": draft.get("general_discount", 0),
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
                self.require_sales_user()
                self.send_json(self.emit_invoice(payload), status=201)
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def do_PUT(self) -> None:
        try:
            path = urlparse(self.path).path
            if not self.current_user():
                self.send_error_json(401, "Debes iniciar sesión.")
                return
            if path.startswith("/api/products/"):
                self.require_product_editor()
                product_id = unquote(path.removeprefix("/api/products/"))
                product = DB.save_product(self.read_json(), product_id=product_id)
                self.send_json({"product": product})
            elif path.startswith("/api/clients/"):
                self.require_sales_user()
                client_id = int(path.removeprefix("/api/clients/"))
                client = DB.save_client(self.read_json(), client_id=client_id)
                self.send_json({"client": client})
            elif path.startswith("/api/suppliers/"):
                self.require_product_editor()
                supplier_id = int(path.removeprefix("/api/suppliers/"))
                supplier = DB.save_supplier(self.read_json(), supplier_id=supplier_id)
                self.send_json({"supplier": supplier})
            elif path.startswith("/api/preinvoices/"):
                user = self.require_sales_user()
                preinvoice_id = int(path.removeprefix("/api/preinvoices/"))
                draft = DB.save_preinvoice(self.read_json(), user.id, preinvoice_id=preinvoice_id)
                self.send_json({"preinvoice": draft})
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def do_DELETE(self) -> None:
        try:
            path = urlparse(self.path).path
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
            else:
                self.send_error_json(404, "Ruta no encontrada.")
        except Exception as exc:
            self.handle_exception(exc)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
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
        invoice = DB.get_invoice(int(invoice["id"]))
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

    def send_bytes(self, body: bytes, status: int = 200, content_type: str = "application/octet-stream") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
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
