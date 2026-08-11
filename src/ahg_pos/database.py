from __future__ import annotations

import sqlite3
import json
import secrets
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .auth import (
    AuthUser,
    hash_password,
    initial_admin_credentials,
    new_session_token,
    normalize_user_modules,
    session_expiration,
    token_hash,
    verify_password,
)
from .config import SCHEMA_DIR, settings
from .credentials import decrypt_secret, encrypt_secret, mask_secret


class DatabaseError(RuntimeError):
    pass


def normalize_party_payload(payload: dict[str, Any], label: str) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip().upper()
    fiscal_id = "".join(ch for ch in str(payload.get("rnc_cedula", "")) if ch.isdigit())
    phone = "".join(ch for ch in str(payload.get("phone", "")) if ch.isdigit())
    email = str(payload.get("email", "")).strip().lower()
    address = str(payload.get("address", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    taxpayer_activity = str(payload.get("taxpayer_activity", "")).strip().upper()
    dgii_locked = bool(payload.get("dgii_locked", False))
    active = bool(payload.get("active", True))
    if len(name) < 2:
        raise DatabaseError(f"El nombre de {label} debe tener al menos 2 caracteres.")
    if len(fiscal_id) not in {9, 11}:
        raise DatabaseError(f"El RNC o cedula de {label} debe tener 9 u 11 digitos.")
    if len(phone) != 10:
        raise DatabaseError(f"El telefono de {label} debe tener 10 digitos.")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise DatabaseError(f"El correo de {label} debe ser valido e incluir @.")
    if not address:
        raise DatabaseError(f"La direccion de {label} es obligatoria.")
    return {
        "name": name,
        "fiscal_id": fiscal_id,
        "phone": phone,
        "email": email,
        "address": address,
        "notes": notes,
        "taxpayer_activity": taxpayer_activity,
        "dgii_locked": dgii_locked,
        "active": active,
    }


def clean_discount_amount(payload: dict[str, Any], max_amount: float, amount_key: str = "discount_amount") -> float:
    max_amount = max(0.0, round(float(max_amount or 0), 2))
    raw_amount = payload.get(amount_key)
    percent_key = f"{amount_key}_percent" if amount_key != "discount_amount" else "discount_percent"
    raw_percent = payload.get(percent_key)
    amount = 0.0
    if raw_percent not in (None, ""):
        percent = max(0.0, min(float(raw_percent), 100.0))
        amount = max_amount * percent / 100
    elif raw_amount not in (None, ""):
        amount = float(raw_amount)
    amount = round(max(0.0, amount), 2)
    if amount > max_amount:
        raise DatabaseError("El descuento no puede superar el monto de la linea o factura.")
    return amount


def normalize_invoice_payments(
    payments: list[dict[str, Any]] | None,
    fallback_method: str,
    amount_due: float,
) -> list[dict[str, Any]]:
    allowed = {"efectivo", "tarjeta", "transferencia", "paypal"}
    amount_due = round(float(amount_due or 0), 2)
    if fallback_method == "credito":
        if payments:
            raise DatabaseError("Una venta a crÃ©dito no puede combinarse con pagos inmediatos.")
        return [{"payment_method": "credito", "amount": amount_due}] if amount_due > 0 else []
    raw_rows = payments or ([{"payment_method": fallback_method, "amount": amount_due}] if amount_due > 0 else [])
    if len(raw_rows) > 7:
        raise DatabaseError("La DGII permite hasta siete formas de pago por comprobante.")
    combined: dict[str, float] = {}
    for row in raw_rows:
        method = str(row.get("payment_method") or row.get("method") or "").strip().lower()
        if method not in allowed:
            raise DatabaseError("Forma de pago no vÃ¡lida para una venta de contado.")
        try:
            amount = round(float(row.get("amount") or 0), 2)
        except (TypeError, ValueError) as exc:
            raise DatabaseError("Cada monto de pago debe ser numÃ©rico.") from exc
        if amount <= 0:
            raise DatabaseError("Cada forma de pago debe tener un monto mayor que cero.")
        combined[method] = round(combined.get(method, 0) + amount, 2)
    normalized = [{"payment_method": method, "amount": amount} for method, amount in combined.items()]
    paid = round(sum(row["amount"] for row in normalized), 2)
    if abs(paid - amount_due) > 0.01:
        raise DatabaseError(f"Los pagos suman RD${paid:,.2f} y deben cubrir RD${amount_due:,.2f}.")
    return normalized


def compute_invoice_totals(lines: list[dict[str, Any]], general_discount: float = 0.0) -> dict[str, float]:
    taxable_base = 0.0
    item_discount_total = 0.0
    for line in lines:
        line_base = round(float(line["line_gross"]) - float(line.get("discount_amount") or 0), 2)
        line["line_subtotal"] = line_base
        item_discount_total += float(line.get("discount_amount") or 0)
        taxable_base += line_base
    general_discount = round(float(general_discount or 0), 2)
    if general_discount > round(taxable_base, 2):
        raise DatabaseError("El descuento general no puede superar el subtotal.")
    subtotal = round(taxable_base - general_discount, 2)
    tax = 0.0
    for line in lines:
        base = float(line["line_subtotal"])
        allocated_discount = round((base / taxable_base) * general_discount, 2) if taxable_base else 0.0
        taxable_line = max(0.0, base - allocated_discount)
        line["global_discount_share"] = allocated_discount
        line["line_tax"] = round(taxable_line * float(line["tax_rate"]), 2)
        line["line_total"] = round(taxable_line + line["line_tax"], 2)
        tax += line["line_tax"]
    tax = round(tax, 2)
    return {
        "subtotal": subtotal,
        "tax": tax,
        "total": round(subtotal + tax, 2),
        "discount_total": round(item_discount_total + general_discount, 2),
        "general_discount": general_discount,
    }


POSTGRES_SCHEMA_LOCK_ID = 2026081001
POSTGRES_SCHEMA_VERSION = "2026-08-11-user-modules-v3"


class Database:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or settings.database_url
        self.kind = "postgres" if self.database_url.startswith(("postgres://", "postgresql://")) else "sqlite"
        self.conn: Any = None

    def connect(self) -> "Database":
        if self.conn is not None:
            return self

        if self.kind == "postgres":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ModuleNotFoundError as exc:
                raise DatabaseError(
                    "Para usar PostgreSQL instala psycopg: pip install -r requirements.txt"
                ) from exc
            self.conn = psycopg.connect(self.database_url, row_factory=dict_row)
        else:
            db_path = self._sqlite_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")

        self.ensure_schema()
        return self

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def ensure_schema(self) -> None:
        schema_lock_acquired = False
        if self.kind == "postgres":
            self.execute("SELECT pg_advisory_lock(?)", (POSTGRES_SCHEMA_LOCK_ID,))
            self.conn.commit()
            schema_lock_acquired = True
        try:
            if self.kind == "postgres" and self.postgres_schema_is_current():
                return
            self.apply_schema()
            if self.kind == "postgres":
                self.mark_postgres_schema_current()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            if schema_lock_acquired:
                self.execute("SELECT pg_advisory_unlock(?)", (POSTGRES_SCHEMA_LOCK_ID,))
                self.conn.commit()

    def apply_schema(self) -> None:
        schema_name = "postgres.sql" if self.kind == "postgres" else "sqlite.sql"
        schema = (SCHEMA_DIR / schema_name).read_text(encoding="utf-8")
        if self.kind == "sqlite":
            self.conn.executescript(schema)
        else:
            for statement in [part.strip() for part in schema.split(";") if part.strip()]:
                self.conn.execute(statement)
        self.conn.commit()
        self.ensure_product_columns()
        self.ensure_billing_columns()
        self.ensure_tracking_table()
        self.ensure_public_quote_request_table()
        self.ensure_user_columns()
        self.ensure_audit_table()
        self.ensure_audit_triggers()
        if self.scalar("SELECT COUNT(*) FROM products") == 0:
            self.seed_demo_data()
        self.ensure_reference_data()
        self.ensure_initial_admin()
        self.ensure_initial_fiscal_company()

    def postgres_schema_is_current(self) -> bool:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS ahg_schema_state (
                name TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        self.conn.commit()
        return self.scalar(
            "SELECT version FROM ahg_schema_state WHERE name = ?",
            ("application",),
        ) == POSTGRES_SCHEMA_VERSION

    def mark_postgres_schema_current(self) -> None:
        self.execute(
            """
            INSERT INTO ahg_schema_state(name, version, updated_at)
            VALUES (?, ?, NOW())
            ON CONFLICT(name) DO UPDATE
            SET version = EXCLUDED.version, updated_at = EXCLUDED.updated_at
            """,
            ("application", POSTGRES_SCHEMA_VERSION),
        )
        self.conn.commit()

    def ensure_tracking_table(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS invoice_tracking_tokens (
                invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_used_at TEXT
            )
            """
        )
        self.conn.commit()

    def ensure_public_quote_request_table(self) -> None:
        if self.kind == "sqlite":
            self.execute(
                """
                CREATE TABLE IF NOT EXISTS public_quote_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    problem TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    subtotal REAL NOT NULL DEFAULT 0,
                    tax REAL NOT NULL DEFAULT 0,
                    total REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pendiente',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        else:
            self.execute(
                """
                CREATE TABLE IF NOT EXISTS public_quote_requests (
                    id SERIAL PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    problem TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    subtotal NUMERIC(12,2) NOT NULL DEFAULT 0,
                    tax NUMERIC(12,2) NOT NULL DEFAULT 0,
                    total NUMERIC(12,2) NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pendiente',
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        existing = self._column_names("public_quote_requests")
        columns = {
            "ecf_type": "TEXT NOT NULL DEFAULT '32'",
            "rnc_cedula": "TEXT NOT NULL DEFAULT ''",
            "address": "TEXT NOT NULL DEFAULT ''",
            "taxpayer_name": "TEXT NOT NULL DEFAULT ''",
            "taxpayer_activity": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in columns.items():
            if name not in existing:
                self.execute(f"ALTER TABLE public_quote_requests ADD COLUMN {name} {definition}")
        self.conn.commit()

    def ensure_audit_table(self) -> None:
        if self.kind == "sqlite":
            self.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id),
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_id TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
        else:
            self.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT '',
                    entity_id TEXT NOT NULL DEFAULT '',
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        self.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)")
        self.conn.commit()

    def ensure_audit_triggers(self) -> None:
        if self.kind == "sqlite":
            statements = [
                """CREATE TRIGGER IF NOT EXISTS audit_products_insert AFTER INSERT ON products BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER INSERT', 'producto', NEW.id, json_object('name', NEW.name, 'sku', NEW.sku), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_products_update AFTER UPDATE ON products BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER UPDATE', 'producto', NEW.id, json_object('name', NEW.name, 'sku', NEW.sku), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_products_delete AFTER DELETE ON products BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER DELETE', 'producto', OLD.id, json_object('name', OLD.name, 'sku', OLD.sku), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_clients_insert AFTER INSERT ON clients BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER INSERT', 'cliente', NEW.id, json_object('name', NEW.name), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_clients_update AFTER UPDATE ON clients BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER UPDATE', 'cliente', NEW.id, json_object('name', NEW.name), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_invoices_insert AFTER INSERT ON invoices BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER INSERT', 'factura', NEW.id, json_object('encf', NEW.en_ncf, 'total', NEW.total), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_preinvoices_insert AFTER INSERT ON preinvoices BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER INSERT', 'pre-factura', NEW.id, json_object('total', NEW.total, 'status', NEW.status), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_users_insert AFTER INSERT ON users BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER INSERT', 'usuario', NEW.id, json_object('email', NEW.email, 'role', NEW.role), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_users_update AFTER UPDATE ON users BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER UPDATE', 'usuario', NEW.id, json_object('email', NEW.email, 'role', NEW.role, 'active', NEW.active), datetime('now')); END""",
                """CREATE TRIGGER IF NOT EXISTS audit_public_quote_insert AFTER INSERT ON public_quote_requests BEGIN INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at) VALUES (NULL, 'TRIGGER INSERT', 'pre-factura pública', NEW.id, json_object('customer_name', NEW.customer_name, 'email', NEW.email, 'total', NEW.total), datetime('now')); END""",
            ]
        else:
            function_exists = bool(
                self.scalar(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_proc procedure
                        JOIN pg_namespace namespace ON namespace.oid = procedure.pronamespace
                        WHERE procedure.proname = ? AND namespace.nspname = current_schema()
                    )
                    """,
                    ("audit_row_change",),
                )
            )
            if not function_exists:
                self.execute(
                    """
                    CREATE FUNCTION audit_row_change() RETURNS trigger AS $$
                    BEGIN
                        INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at)
                        VALUES (NULL, 'TRIGGER ' || TG_OP, TG_TABLE_NAME, COALESCE((CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END)::text, ''), '{}'::text, NOW());
                        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
                    END; $$ LANGUAGE plpgsql;
                    """
                )
            for table in ("products", "clients", "invoices", "preinvoices", "users", "public_quote_requests"):
                trigger_name = f"audit_{table}_change"
                trigger_exists = bool(
                    self.scalar(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM pg_trigger
                            WHERE tgname = ? AND tgrelid = to_regclass(?) AND NOT tgisinternal
                        )
                        """,
                        (trigger_name, table),
                    )
                )
                if not trigger_exists:
                    self.execute(
                        f"CREATE TRIGGER {trigger_name} AFTER INSERT OR UPDATE OR DELETE ON {table} "
                        "FOR EACH ROW EXECUTE FUNCTION audit_row_change()"
                    )
        self.conn.commit()

    def ensure_user_columns(self) -> None:
        existing = self._column_names("users")
        if "module_permissions_json" not in existing:
            self.execute("ALTER TABLE users ADD COLUMN module_permissions_json TEXT")
            self.conn.commit()

    def ensure_product_columns(self) -> None:
        columns = {
            "barcode": "TEXT NOT NULL DEFAULT ''",
            "brand": "TEXT NOT NULL DEFAULT ''",
            "unit_name": "TEXT NOT NULL DEFAULT 'unidad'",
            "location": "TEXT NOT NULL DEFAULT ''",
            "supplier": "TEXT NOT NULL DEFAULT ''",
            "cost": "REAL NOT NULL DEFAULT 0" if self.kind == "sqlite" else "NUMERIC(12, 2) NOT NULL DEFAULT 0",
            "active": "INTEGER NOT NULL DEFAULT 1" if self.kind == "sqlite" else "BOOLEAN NOT NULL DEFAULT TRUE",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        if self.kind == "sqlite":
            existing = {row["name"] for row in self.fetch_all("PRAGMA table_info(products)")}
        else:
            existing = {
                row["column_name"]
                for row in self.fetch_all(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'products'"
                )
            }
        for name, definition in columns.items():
            if name not in existing:
                self.execute(f"ALTER TABLE products ADD COLUMN {name} {definition}")
        self.conn.commit()
        self.ensure_client_columns()

    def ensure_client_columns(self) -> None:
        columns = {
            "fiscal_id": "TEXT",
            "address": "TEXT NOT NULL DEFAULT ''",
            "taxpayer_activity": "TEXT NOT NULL DEFAULT ''",
            "dgii_locked": "INTEGER NOT NULL DEFAULT 0" if self.kind == "sqlite" else "BOOLEAN NOT NULL DEFAULT FALSE",
            "notes": "TEXT NOT NULL DEFAULT ''",
            "active": "INTEGER NOT NULL DEFAULT 1" if self.kind == "sqlite" else "BOOLEAN NOT NULL DEFAULT TRUE",
        }
        if self.kind == "sqlite":
            existing = {row["name"] for row in self.fetch_all("PRAGMA table_info(clients)")}
        else:
            existing = {
                row["column_name"]
                for row in self.fetch_all(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 'clients'"
                )
            }
        for name, definition in columns.items():
            if name not in existing:
                self.execute(f"ALTER TABLE clients ADD COLUMN {name} {definition}")
        self.execute("UPDATE clients SET fiscal_id = rnc_cedula WHERE fiscal_id IS NULL AND rnc_cedula <> ''")
        self.conn.commit()
        self.ensure_supplier_columns()

    def ensure_supplier_columns(self) -> None:
        bool_type = "INTEGER NOT NULL DEFAULT 1" if self.kind == "sqlite" else "BOOLEAN NOT NULL DEFAULT TRUE"
        text_required = "TEXT NOT NULL DEFAULT ''"
        columns = {
            "rnc_cedula": "TEXT NOT NULL DEFAULT ''" if self.kind == "sqlite" else "VARCHAR(11) NOT NULL DEFAULT ''",
            "name": text_required,
            "phone": text_required,
            "email": text_required,
            "address": text_required,
            "contact_person": text_required,
            "taxpayer_activity": text_required,
            "dgii_locked": bool_type,
            "notes": text_required,
            "active": bool_type,
            "created_at": text_required,
            "updated_at": text_required,
        }
        existing = self._column_names("suppliers")
        for name, definition in columns.items():
            if name not in existing:
                self.execute(f"ALTER TABLE suppliers ADD COLUMN {name} {definition}")
        self.conn.commit()

    def ensure_billing_columns(self) -> None:
        numeric = "REAL NOT NULL DEFAULT 0" if self.kind == "sqlite" else "NUMERIC(12, 2) NOT NULL DEFAULT 0"
        table_columns = {
            "invoices": {
                "discount_total": numeric,
                "general_discount": numeric,
                "credit_applied": numeric,
            },
            "invoice_items": {
                "discount_amount": numeric,
            },
            "preinvoices": {
                "discount_total": numeric,
                "general_discount": numeric,
            },
            "preinvoice_items": {
                "discount_amount": numeric,
            },
            "credit_notes": {
                "expires_at": "TEXT NOT NULL DEFAULT ''",
            },
        }
        for table, columns in table_columns.items():
            existing = self._column_names(table)
            for name, definition in columns.items():
                if name not in existing:
                    self.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        self.conn.commit()
        self.ensure_credit_application_table()
        self.ensure_payment_and_cash_tables()

    def ensure_payment_and_cash_tables(self) -> None:
        numeric = "REAL" if self.kind == "sqlite" else "NUMERIC(12, 2)"
        identity = "INTEGER PRIMARY KEY AUTOINCREMENT" if self.kind == "sqlite" else "SERIAL PRIMARY KEY"
        timestamp = "TEXT" if self.kind == "sqlite" else "TIMESTAMPTZ"
        self.execute(
            f"""
            CREATE TABLE IF NOT EXISTS cash_sessions (
                id {identity}, opened_by INTEGER REFERENCES users(id), opened_at {timestamp} NOT NULL,
                opening_amount {numeric} NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'abierta', closed_by INTEGER REFERENCES users(id),
                closed_at {timestamp}, expected_cash {numeric}, counted_cash {numeric},
                difference {numeric}, notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.execute(
            f"""
            CREATE TABLE IF NOT EXISTS cash_movements (
                id {identity}, cash_session_id INTEGER NOT NULL REFERENCES cash_sessions(id) ON DELETE CASCADE,
                movement_type TEXT NOT NULL, amount {numeric} NOT NULL, description TEXT NOT NULL,
                created_by INTEGER REFERENCES users(id), created_at {timestamp} NOT NULL
            )
            """
        )
        self.execute(
            f"""
            CREATE TABLE IF NOT EXISTS invoice_payments (
                id {identity}, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
                cash_session_id INTEGER REFERENCES cash_sessions(id), payment_method TEXT NOT NULL,
                amount {numeric} NOT NULL, created_at {timestamp} NOT NULL
            )
            """
        )
        self.execute("CREATE INDEX IF NOT EXISTS idx_invoice_payments_invoice ON invoice_payments(invoice_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_invoice_payments_session ON invoice_payments(cash_session_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_cash_movements_session ON cash_movements(cash_session_id)")
        self.conn.commit()
        for row in self.fetch_all("SELECT id, issued_at FROM credit_notes WHERE COALESCE(expires_at, '') = ''"):
            issued = self._parse_datetime(row.get("issued_at"))
            self.execute(
                "UPDATE credit_notes SET expires_at = ? WHERE id = ?",
                ((issued + timedelta(days=90)).date().isoformat(), row["id"]),
            )
        self.conn.commit()

    def ensure_credit_application_table(self) -> None:
        if self.kind == "sqlite":
            self.execute(
                """
                CREATE TABLE IF NOT EXISTS credit_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    credit_note_id INTEGER NOT NULL REFERENCES credit_notes(id),
                    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                    client_id INTEGER NOT NULL REFERENCES clients(id),
                    amount REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
        else:
            self.execute(
                """
                CREATE TABLE IF NOT EXISTS credit_applications (
                    id SERIAL PRIMARY KEY,
                    credit_note_id INTEGER NOT NULL REFERENCES credit_notes(id),
                    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
                    client_id INTEGER NOT NULL REFERENCES clients(id),
                    amount NUMERIC(12, 2) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
        self.conn.commit()

    def _column_names(self, table: str) -> set[str]:
        if self.kind == "sqlite":
            return {row["name"] for row in self.fetch_all(f"PRAGMA table_info({table})")}
        return {
            row["column_name"]
            for row in self.fetch_all(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (table,),
            )
        }

    def seed_demo_data(self) -> None:
        categories = [
            "Cemento y agregados",
            "Tuberias y plomeria",
            "Electricidad",
            "Herramientas",
            "Pintura y acabados",
            "Fijacion y seguridad",
        ]
        products = [
            {
                "id": "7460001000011",
                "sku": "CEM-GRIS-42",
                "category": "Cemento y agregados",
                "name": "Cemento gris 42.5 kg",
                "technical_description": "Saco de cemento Portland gris para columnas, zapatas, bloques y mezclas generales de construccion.",
                "price": 435.00,
                "tax_rate": 0.18,
                "stock": 84,
                "min_stock": 20,
                "tags": "cemento mezcla construccion columna zapata blocks obra gris",
            },
            {
                "id": "7460001000028",
                "sku": "VAR-3-8-20",
                "category": "Cemento y agregados",
                "name": "Varilla corrugada 3/8 x 20 pies",
                "technical_description": "Varilla de acero corrugado para refuerzo estructural en losas, columnas y vigas ligeras.",
                "price": 315.00,
                "tax_rate": 0.18,
                "stock": 38,
                "min_stock": 15,
                "tags": "varilla acero corrugada columna losa viga refuerzo estructura",
            },
            {
                "id": "7460001000035",
                "sku": "CPVC-12-HT",
                "category": "Tuberias y plomeria",
                "name": "Tubo CPVC alta temperatura 1/2 pulgada",
                "technical_description": "Tuberia CPVC de media pulgada para agua caliente, reparaciones empotradas y conduccion sanitaria.",
                "price": 168.00,
                "tax_rate": 0.18,
                "stock": 52,
                "min_stock": 12,
                "tags": "cpvc tubo tuberia agua caliente plomeria empotrada fuga grieta reparacion",
            },
            {
                "id": "7460001000042",
                "sku": "PEG-CPVC-118",
                "category": "Tuberias y plomeria",
                "name": "Pegamento CPVC 118 ml",
                "technical_description": "Adhesivo solvente para uniones de CPVC en agua caliente y reparaciones de tuberias.",
                "price": 235.00,
                "tax_rate": 0.18,
                "stock": 27,
                "min_stock": 8,
                "tags": "pegamento cpvc solvente tuberia agua caliente union fuga sellar",
            },
            {
                "id": "7460001000059",
                "sku": "PVC-34-SCH40",
                "category": "Tuberias y plomeria",
                "name": "Tubo PVC sanitario 3/4 SCH40",
                "technical_description": "Tubo PVC resistente para agua fria, drenaje liviano y conducciones domesticas.",
                "price": 142.00,
                "tax_rate": 0.18,
                "stock": 46,
                "min_stock": 10,
                "tags": "pvc tubo agua fria sanitario drenaje plomeria tuberia",
            },
            {
                "id": "7460001000066",
                "sku": "SEL-POLI-300",
                "category": "Pintura y acabados",
                "name": "Sellador poliuretano anti-filtracion 300 ml",
                "technical_description": "Sellador flexible para grietas, filtraciones, juntas, techos, canaletas y areas expuestas a humedad.",
                "price": 389.00,
                "tax_rate": 0.18,
                "stock": 19,
                "min_stock": 6,
                "tags": "sellador filtracion grieta humedad techo canaleta silicona junta fuga",
            },
            {
                "id": "7460001000073",
                "sku": "PINT-ACR-BLA",
                "category": "Pintura y acabados",
                "name": "Pintura acrilica blanca galon",
                "technical_description": "Pintura acrilica interior y exterior de alta cobertura para paredes y terminaciones limpias.",
                "price": 895.00,
                "tax_rate": 0.18,
                "stock": 12,
                "min_stock": 8,
                "tags": "pintura acrilica blanca pared exterior interior acabado humedad",
            },
            {
                "id": "7460001000080",
                "sku": "BRK-20A-1P",
                "category": "Electricidad",
                "name": "Breaker 20A monopolar",
                "technical_description": "Interruptor termomagnetico de 20 amperes para circuitos residenciales de tomacorrientes o cargas ligeras.",
                "price": 285.00,
                "tax_rate": 0.18,
                "stock": 31,
                "min_stock": 10,
                "tags": "breaker interruptor electrico 20 amperes circuito tomacorriente proteccion",
            },
            {
                "id": "7460001000097",
                "sku": "CAB-12-THHN",
                "category": "Electricidad",
                "name": "Cable THHN calibre 12 por metro",
                "technical_description": "Cable electrico THHN calibre 12 para instalaciones residenciales, tomacorrientes y alimentacion de circuitos.",
                "price": 42.00,
                "tax_rate": 0.18,
                "stock": 180,
                "min_stock": 40,
                "tags": "cable thhn calibre 12 electricidad tomacorriente instalacion circuito",
            },
            {
                "id": "7460001000103",
                "sku": "TAL-550W",
                "category": "Herramientas",
                "name": "Taladro percutor 550W",
                "technical_description": "Taladro percutor electrico para perforar concreto ligero, madera y metal con brocas compatibles.",
                "price": 2750.00,
                "tax_rate": 0.18,
                "stock": 7,
                "min_stock": 5,
                "tags": "taladro percutor herramienta perforar concreto madera metal broca",
            },
            {
                "id": "7460001000110",
                "sku": "TOR-HEX-2",
                "category": "Fijacion y seguridad",
                "name": "Tornillo hexagonal 2 pulgadas caja 100",
                "technical_description": "Tornillo hexagonal galvanizado para fijacion de estructuras metalicas, madera y soportes.",
                "price": 310.00,
                "tax_rate": 0.18,
                "stock": 5,
                "min_stock": 10,
                "tags": "tornillo hexagonal galvanizado fijacion soporte metal madera",
            },
            {
                "id": "7460001000127",
                "sku": "DIS-COR-MET",
                "category": "Herramientas",
                "name": "Disco de corte metal 4.5 pulgadas",
                "technical_description": "Disco abrasivo para corte de metal, varillas, perfiles y piezas de acero.",
                "price": 95.00,
                "tax_rate": 0.18,
                "stock": 64,
                "min_stock": 18,
                "tags": "disco corte metal varilla perfil acero esmeril herramienta",
            },
        ]

        try:
            self.conn.execute("BEGIN")
            for name in categories:
                self.execute("INSERT INTO categories(name) VALUES (?) ON CONFLICT(name) DO NOTHING", (name,))

            for product in products:
                category_id = self.fetch_one("SELECT id FROM categories WHERE name = ?", (product["category"],))["id"]
                self.execute(
                    """
                    INSERT INTO products(
                        id, sku, category_id, name, technical_description,
                        price, tax_rate, stock, min_stock, tags
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        product["id"],
                        product["sku"],
                        category_id,
                        product["name"],
                        product["technical_description"],
                        product["price"],
                        product["tax_rate"],
                        product["stock"],
                        product["min_stock"],
                        product["tags"],
                    ),
                )

            sequences = [
                ("31", "Factura de Credito Fiscal Electronica", "E31", 1, 9999999999, "2026-12-31", 1),
                ("32", "Factura de Consumo Electronica", "E32", 1, 9999999999, "2026-12-31", 1),
            ]
            for row in sequences:
                # SQLite acepta 0/1, pero PostgreSQL requiere booleanos.
                sequence_row = (*row[:-1], True if self.kind == "postgres" else row[-1])
                self.execute(
                    """
                    INSERT INTO fiscal_sequences(
                        type_code, description, prefix, current_number,
                        end_number, expires_at, authorized
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(type_code) DO NOTHING
                    """,
                    sequence_row,
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def ensure_initial_admin(self) -> None:
        if self.scalar("SELECT COUNT(*) FROM users") > 0:
            return
        name, email, phone, password = initial_admin_credentials()
        self.execute(
            """
            INSERT INTO users(name, email, phone, password_hash, role, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, email, phone, hash_password(password), "admin", True if self.kind == "postgres" else 1, self.now()),
        )
        self.conn.commit()

    def ensure_initial_fiscal_company(self) -> None:
        if self.scalar("SELECT COUNT(*) FROM fiscal_companies") > 0 or not settings.imecf_api_key:
            return
        now = self.now()
        self.execute(
            """
            INSERT INTO fiscal_companies(
                workspace_name, issuer_name, issuer_rnc, company_id, base_url,
                portal_url, environment, encrypted_api_key, enabled, active,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                settings.imecf_workspace_name,
                settings.imecf_expected_issuer_name or settings.company_name,
                settings.company_rnc,
                settings.imecf_company_id,
                settings.imecf_base_url,
                settings.imecf_portal_base_url,
                settings.fiscal_environment,
                encrypt_secret(settings.imecf_api_key),
                settings.imecf_enabled if self.kind == "postgres" else int(settings.imecf_enabled),
                True if self.kind == "postgres" else 1,
                now,
                now,
            ),
        )
        self.conn.commit()

    def verify_user_password(self, user_id: int, password: str) -> bool:
        row = self.fetch_one("SELECT password_hash FROM users WHERE id = ? AND active = ?", (
            user_id,
            True if self.kind == "postgres" else 1,
        ))
        return bool(row and verify_password(password, row["password_hash"]))

    def list_fiscal_companies(self) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT id, workspace_name, issuer_name, issuer_rnc, company_id,
                   base_url, portal_url, environment, encrypted_api_key,
                   enabled, active, validated_at, last_test_at, last_test_ok,
                   last_test_message, created_at, updated_at
            FROM fiscal_companies
            ORDER BY active DESC, workspace_name
            """
        )
        for row in rows:
            key = decrypt_secret(str(row.pop("encrypted_api_key", "")))
            row["api_key_masked"] = mask_secret(key)
            row["has_api_key"] = bool(key)
        return rows

    def get_fiscal_company(self, company_id: int | None = None, active: bool = False) -> dict[str, Any] | None:
        if active:
            row = self.fetch_one("SELECT * FROM fiscal_companies WHERE active = ? LIMIT 1", (
                True if self.kind == "postgres" else 1,
            ))
        else:
            row = self.fetch_one("SELECT * FROM fiscal_companies WHERE id = ?", (company_id,))
        if not row:
            return None
        row["api_key"] = decrypt_secret(str(row.pop("encrypted_api_key", "")))
        return row

    def save_fiscal_company(
        self,
        payload: dict[str, Any],
        user_id: int,
        company_id: int | None = None,
    ) -> dict[str, Any]:
        workspace_name = str(payload.get("workspace_name", "")).strip()
        issuer_name = str(payload.get("issuer_name", "")).strip()
        issuer_rnc = "".join(ch for ch in str(payload.get("issuer_rnc", "")) if ch.isdigit())
        remote_company_id = str(payload.get("company_id", "")).strip()
        base_url = str(payload.get("base_url", "")).strip().rstrip("/")
        portal_url = str(payload.get("portal_url", "")).strip().rstrip("/")
        environment = str(payload.get("environment", "test")).strip().lower()
        if settings.academic_mode:
            environment = "test"
        api_key = str(payload.get("api_key", "")).strip()
        enabled = bool(payload.get("enabled", False))
        if not workspace_name or not issuer_name:
            raise DatabaseError("El espacio IMECF y el nombre fiscal son obligatorios.")
        if len(issuer_rnc) not in {9, 11}:
            raise DatabaseError("El RNC o cédula del emisor debe tener 9 u 11 dígitos.")
        if not base_url.startswith("https://"):
            raise DatabaseError("La URL de la API IMECF debe usar HTTPS.")
        if portal_url and not portal_url.startswith("https://"):
            raise DatabaseError("La URL del portal debe usar HTTPS.")
        if environment not in {"test", "production"}:
            raise DatabaseError("El ambiente debe ser test o production.")
        existing = self.fetch_one("SELECT * FROM fiscal_companies WHERE id = ?", (company_id,)) if company_id else None
        if company_id and not existing:
            raise DatabaseError("Configuración fiscal no encontrada.")
        if not api_key and existing:
            encrypted_key = existing["encrypted_api_key"]
        elif api_key:
            encrypted_key = encrypt_secret(api_key)
        else:
            raise DatabaseError("La API Key es obligatoria para una nueva empresa.")
        now = self.now()
        enabled_value = enabled if self.kind == "postgres" else int(enabled)
        if existing:
            self.execute(
                """
                UPDATE fiscal_companies
                SET workspace_name = ?, issuer_name = ?, issuer_rnc = ?,
                    company_id = ?, base_url = ?, portal_url = ?, environment = ?,
                    encrypted_api_key = ?, enabled = ?, active = ?, validated_at = NULL,
                    last_test_ok = NULL, last_test_message = '', updated_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    workspace_name, issuer_name, issuer_rnc, remote_company_id,
                    base_url, portal_url, environment, encrypted_key, enabled_value,
                    False if self.kind == "postgres" else 0, user_id, now, company_id,
                ),
            )
            saved_id = company_id
        else:
            saved_id = self.insert_and_get_id(
                """
                INSERT INTO fiscal_companies(
                    workspace_name, issuer_name, issuer_rnc, company_id, base_url,
                    portal_url, environment, encrypted_api_key, enabled, active,
                    created_by, updated_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_name, issuer_name, issuer_rnc, remote_company_id,
                    base_url, portal_url, environment, encrypted_key, enabled_value,
                    False if self.kind == "postgres" else 0,
                    user_id, user_id, now, now,
                ),
            )
        self.conn.commit()
        return next(row for row in self.list_fiscal_companies() if int(row["id"]) == int(saved_id))

    def activate_fiscal_company(self, company_id: int, user_id: int) -> dict[str, Any]:
        row = self.fetch_one("SELECT * FROM fiscal_companies WHERE id = ?", (company_id,))
        if not row:
            raise DatabaseError("Configuración fiscal no encontrada.")
        if settings.academic_mode and str(row.get("environment") or "test").lower() != "test":
            raise DatabaseError("El proyecto académico solo permite perfiles fiscales de prueba.")
        if not bool(row["enabled"]) or not bool(row["last_test_ok"]) or not row["validated_at"]:
            raise DatabaseError("Primero habilita, valida y prueba la conexión de esta empresa.")
        now = self.now()
        false_value = False if self.kind == "postgres" else 0
        true_value = True if self.kind == "postgres" else 1
        self.execute("UPDATE fiscal_companies SET active = ?", (false_value,))
        self.execute(
            "UPDATE fiscal_companies SET active = ?, updated_by = ?, updated_at = ? WHERE id = ?",
            (true_value, user_id, now, company_id),
        )
        self.conn.commit()
        return self.get_fiscal_company(company_id)

    def record_fiscal_validation(self, company_id: int, valid: bool, message: str) -> None:
        now = self.now()
        self.execute(
            """
            UPDATE fiscal_companies
            SET validated_at = ?, last_test_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (now if valid else None, message[:1000], now, company_id),
        )
        self.conn.commit()

    def record_fiscal_connection_test(self, company_id: int, ok: bool, message: str) -> None:
        now = self.now()
        self.execute(
            """
            UPDATE fiscal_companies
            SET last_test_at = ?, last_test_ok = ?, last_test_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, ok if self.kind == "postgres" else int(ok), message[:1000], now, company_id),
        )
        self.conn.commit()

    def authenticate_user(self, identifier: str, password: str) -> tuple[AuthUser, str] | None:
        normalized = identifier.strip().lower()
        digits = "".join(ch for ch in normalized if ch.isdigit())
        user = self.fetch_one(
            """
            SELECT id, name, email, phone, password_hash, role, module_permissions_json, active
            FROM users
            WHERE LOWER(email) = ? OR phone = ?
            LIMIT 1
            """,
            (normalized, digits),
        )
        if not user or not bool(user["active"]) or not verify_password(password, user["password_hash"]):
            return None
        auth_user = AuthUser(
            id=int(user["id"]),
            name=str(user["name"]),
            email=str(user["email"]),
            phone=str(user["phone"]),
            role=str(user["role"]),
            modules=normalize_user_modules(user.get("module_permissions_json"), str(user["role"])),
        )
        token = new_session_token()
        now = self.now()
        self.execute(
            """
            INSERT INTO user_sessions(id, user_id, token_hash, expires_at, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (secrets.token_hex(16), auth_user.id, token_hash(token), session_expiration(), now, now),
        )
        self.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, auth_user.id))
        self.conn.commit()
        return auth_user, token

    def session_user(self, token: str) -> AuthUser | None:
        if not token:
            return None
        now = self.now()
        row = self.fetch_one(
            """
            SELECT u.id, u.name, u.email, u.phone, u.role, u.module_permissions_json, u.active, s.id AS session_id
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?
            LIMIT 1
            """,
            (token_hash(token), now),
        )
        if not row or not bool(row["active"]):
            return None
        self.execute("UPDATE user_sessions SET last_seen_at = ? WHERE id = ?", (now, row["session_id"]))
        self.conn.commit()
        return AuthUser(
            id=int(row["id"]),
            name=str(row["name"]),
            email=str(row["email"]),
            phone=str(row["phone"]),
            role=str(row["role"]),
            modules=normalize_user_modules(row.get("module_permissions_json"), str(row["role"])),
        )

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        self.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_hash(token),))
        self.conn.commit()

    def ensure_reference_data(self) -> None:
        self.ensure_demo_clients()
        self.ensure_demo_suppliers()
        self.ensure_extra_products()

    def ensure_demo_clients(self) -> None:
        clients = [
            ("101850556", "CONSTRUCTORA CIBAO NORTE SRL", "8095812301", "compras@cibaonorte.com", "AV. ESTRELLA SADHALA 45, SANTIAGO"),
            ("130447568", "FERRETERIA LOS ALPES SRL", "8092764410", "contabilidad@ferrealpes.com", "CALLE DUARTE 88, LA VEGA"),
            ("131226941", "INVERSIONES MADERA REAL SRL", "8099712045", "admin@maderareal.com", "CARRETERA LICEY 12, SANTIAGO"),
            ("132907401", "UTESA", "8095827156", "compras@utesa.edu", "AV. ESTRELLA SADHALA, SANTIAGO"),
            ("124018792", "SERVICIOS TECNICOS DEL NORTE SRL", "8294550198", "operaciones@tecnicosnorte.com", "CALLE RESTAURACION 22, MOCA"),
            ("101742315", "GRUPO ELECTRICO DOMINICANO SRL", "8493601122", "facturas@ged.com", "AV. 27 DE FEBRERO 104, SANTO DOMINGO"),
            ("130994218", "PROYECTOS HIDRAULICOS DEL CARIBE SRL", "8095600911", "ventas@hidrocaribe.com", "ZONA INDUSTRIAL, SANTIAGO"),
            ("131508643", "SOLUCIONES DE PINTURA RIVERA SRL", "8296407711", "info@pinturarivera.com", "CALLE MEXICO 18, SAN FRANCISCO"),
            ("122739884", "DISTRIBUIDORA ACERO FUERTE SRL", "8492229080", "pedidos@acerofuerte.com", "AV. CIRCUNVALACION 300, SANTIAGO"),
            ("101336092", "COMERCIAL EL BLOQUE SRL", "8097243310", "ventas@elbloque.com", "CARRETERA JACAGUA KM 4, SANTIAGO"),
            ("40214069177", "RAUL TORIBIO", "8093600026", "raul.toribio@example.com", "RESIDENCIAL LOS PRADOS, SANTIAGO"),
            ("00113918205", "ALINZON MENDOZA", "8292827556", "alinzon.mendoza@example.com", "CALLE PRINCIPAL 15, SANTIAGO"),
            ("03104567291", "MARIA FERNANDA LOPEZ", "8493331200", "maria.lopez@example.com", "URB. CERROS DE GURABO 9, SANTIAGO"),
            ("05400821936", "JOSE ANTONIO PEREZ", "8094129801", "jose.perez@example.com", "CALLE LAS CARRERAS 77, LA VEGA"),
            ("04711239084", "KARLA PATRICIA GOMEZ", "8295017722", "karla.gomez@example.com", "AV. HISPANOAMERICANA 21, SANTIAGO"),
            ("22300491872", "LUIS ENRIQUE SANTANA", "8496104005", "luis.santana@example.com", "CALLE EL SOL 140, SANTIAGO"),
            ("40223982170", "ANA CRISTINA ROSARIO", "8095551133", "ana.rosario@example.com", "LOS JARDINES METROPOLITANOS, SANTIAGO"),
            ("00117864095", "MIGUEL ANGEL RAMIREZ", "8297704200", "miguel.ramirez@example.com", "CALLE PADRE LAS CASAS 44, MOCA"),
            ("03198745621", "SANDRA MILAGROS NUÑEZ", "8492093344", "sandra.nunez@example.com", "ENSANCHE LIBERTAD 30, SANTIAGO"),
            ("05476543218", "CARLOS EDUARDO MARTINEZ", "8096042209", "carlos.martinez@example.com", "AV. REPUBLICA DE ARGENTINA 16, SANTIAGO"),
        ]
        for fiscal_id, name, phone, email, address in clients:
            existing = self.fetch_one("SELECT id FROM clients WHERE fiscal_id = ?", (fiscal_id,))
            payload = {"rnc_cedula": fiscal_id, "name": name, "phone": phone, "email": email, "address": address}
            self.save_client(payload, client_id=int(existing["id"]) if existing else None)

    def ensure_demo_suppliers(self) -> None:
        suppliers = [
            ("101112221", "CEMENTOS DEL CIBAO SRL", "8095550101", "ventas@cementoscibao.com", "ZONA INDUSTRIAL LA VEGA", "EQUIPO DE VENTAS"),
            ("101112239", "TUBERIAS DOMINICANAS SRL", "8095550102", "pedidos@tubodominicana.com", "AV. CIRCUNVALACION, SANTIAGO", "MARIA VARGAS"),
            ("101112247", "ELECTRO NORTE SUPPLY SRL", "8095550103", "compras@electronorte.com", "LOS JARDINES, SANTIAGO", "JUAN PERALTA"),
            ("101112255", "PINTURAS PROFESIONALES SRL", "8095550104", "servicio@pinturaspro.com", "AV. DUARTE, SANTO DOMINGO", "CARLA MEJIA"),
            ("101112263", "HERRAMIENTAS Y FIJACIONES SRL", "8095550105", "ventas@hyf.com", "CARRETERA LICEY, SANTIAGO", "RAFAEL CRUZ"),
        ]
        for fiscal_id, name, phone, email, address, contact in suppliers:
            existing = self.fetch_one("SELECT id FROM suppliers WHERE rnc_cedula = ?", (fiscal_id,))
            self.save_supplier({
                "rnc_cedula": fiscal_id,
                "name": name,
                "phone": phone,
                "email": email,
                "address": address,
                "contact_person": contact,
            }, supplier_id=int(existing["id"]) if existing else None)

    def ensure_extra_products(self) -> None:
        families = [
            ("Cemento y agregados", "CYA", ["CEMENTO BLANCO 25 KG", "ARENA LAVADA SACO", "GRAVA 3/4 SACO", "MORTERO LISTO 40 KG", "CAL HIDRATADA 20 KG", "BLOCK 6 PULGADAS", "BLOCK 8 PULGADAS", "ADITIVO IMPERMEABILIZANTE", "MALLA ELECTROSOLDADA", "VARILLA 1/2 X 20 PIES"]),
            ("Tuberias y plomeria", "PLM", ["TUBO PVC 1/2", "TUBO PVC 3/4", "TUBO PVC 1", "CODO PVC 90 1/2", "TEE PVC 3/4", "PEGAMENTO PVC 1/4", "LLAVE DE PASO 1/2", "SIFON LAVAMANOS", "CINTA TEFLON", "MANGUERA FLEXIBLE"]),
            ("Electricidad", "ELE", ["CABLE THHN #12", "CABLE THHN #10", "BREAKER 20A", "TOMACORRIENTE DOBLE", "INTERRUPTOR SENCILLO", "CAJA 2X4 METALICA", "TUBO EMT 1/2", "CONECTOR EMT 1/2", "PANEL 8 CIRCUITOS", "BOMBILLO LED 12W"]),
            ("Herramientas", "HER", ["MARTILLO 16 OZ", "ALICATE UNIVERSAL", "DESTORNILLADOR PHILLIPS", "LLAVE AJUSTABLE 10", "SERRUCHO 20", "CINTA METRICA 5M", "NIVEL 24", "TALADRO 1/2", "DISCO CORTE METAL", "BROCA CONCRETO 1/4"]),
            ("Pintura y acabados", "PIN", ["PINTURA ACRILICA BLANCA", "SELLADOR ACRILICO", "BROCHA 3 PULGADAS", "RODILLO 9 PULGADAS", "BANDEJA PARA PINTURA", "MASILLA ACRILICA", "LIJA #120", "THINNER GALON", "ESMALTE NEGRO", "IMPERMEABILIZANTE TECHO"]),
            ("Fijacion y seguridad", "FIJ", ["TORNILLO DRYWALL 1", "TORNILLO HEXAGONAL 2", "TARUGO PLASTICO", "CLAVO ACERO 2", "CANDADO 50MM", "BISAGRA 3", "PASADOR PUERTA", "CADENA GALVANIZADA", "GUANTE DE NITRILO", "LENTE SEGURIDAD"]),
            ("Ceramica y banos", "CER", ["CERAMICA PISO GRIS", "PORCELANATO BLANCO", "PEGAMENTO CERAMICO", "FRAGUA BLANCA", "INODORO ELONGADO", "LAVAMANOS PEDESTAL", "MEZCLADORA LAVAMANOS", "REGADERA CROMADA", "DESAGUE PISO", "ESPEJO BANO"]),
            ("Jardineria", "JAR", ["MANGUERA JARDIN 50FT", "PISTOLA RIEGO", "PALA PUNTA", "RASTRILLO METALICO", "TIJERA PODAR", "ABONO ORGANICO", "MACETA PLASTICA", "SEMILLA CESPED", "GUANTE JARDIN", "REGADERA PLASTICA"]),
            ("Madera y carpinteria", "MAD", ["PLYWOOD 3/4", "PLYWOOD 1/2", "LISTON PINO 2X4", "COLA BLANCA", "BARNIZ TRANSPARENTE", "CLAVO SIN CABEZA", "LIJA MADERA #80", "BISAGRA GABINETE", "TIRADOR GABINETE", "SELLADOR MADERA"]),
            ("Soldadura y metal", "SOL", ["ELECTRODO 6013", "ELECTRODO 7018", "CARETA SOLDAR", "GUANTE SOLDADOR", "ANGULAR 1X1", "PLATINA 1", "TUBO CUADRADO 1", "DISCO DESBASTE", "ANTIOXIDO ROJO", "CEPILLO ALAMBRE"]),
            ("Climatizacion y ventilacion", "CLI", ["AIRE ACONDICIONADO INVERTER 12000 BTU", "VENTILADOR DE TECHO 52 PULGADAS", "EXTRACTOR DE AIRE 8 PULGADAS", "TUBERIA COBRE 1/4", "TUBERIA COBRE 1/2", "AISLANTE PARA TUBERIA 1/2", "CINTA PARA AIRE ACONDICIONADO", "CAPACITOR 35 MFD", "TERMOSTATO DIGITAL", "FILTRO DE AIRE LAVABLE"]),
            ("Techos y drenaje", "TEC", ["ZINC ACANALADO CALIBRE 26", "CANALETA PVC BLANCA", "BAJANTE PLUVIAL 3 PULGADAS", "MANTO ASFALTICO 3 MM", "SELLADOR PARA TECHO GALON", "TORNILLO PARA ZINC CON ARANDELA", "CUMBRERA GALVANIZADA", "GOTERO GALVANIZADO", "MEMBRANA IMPERMEABLE", "REJILLA PARA DESAGUE PLUVIAL"]),
            ("Puertas y cerraduras", "PUE", ["CERRADURA DE POMO CON LLAVE", "CERRADURA DE PALANCA", "CERROJO DE SEGURIDAD", "CIERRAPUERTA HIDRAULICO", "BISAGRA REFORZADA 4 PULGADAS", "TOPE DE PUERTA", "MANIJA PARA GABINETE", "RIEL PARA PUERTA CORREDIZA", "BURLETE PARA PUERTA", "MIRILLA PARA PUERTA"]),
            ("Limpieza y mantenimiento", "LIM", ["DESENGRASANTE INDUSTRIAL GALON", "CLORO CONCENTRADO GALON", "ESCOBA INDUSTRIAL", "TRAPEADOR DE MICROFIBRA", "CEPILLO DE PISO", "CUBETA PLASTICA 5 GALONES", "ESPONJA ABRASIVA", "LIMPIADOR DE CONTACTOS ELECTRICOS", "LUBRICANTE MULTIUSO", "PAQUETE DE PANOS DE MICROFIBRA"]),
            ("Automotriz", "AUT", ["ACEITE MOTOR 10W40 GALON", "LIQUIDO DE FRENOS DOT 4", "REFRIGERANTE PARA RADIADOR GALON", "CABLE PARA BATERIA", "PINZA PARA BATERIA", "GATO HIDRAULICO 2 TONELADAS", "LLAVE DE RUEDA EN CRUZ", "MEDIDOR DE PRESION DE NEUMATICOS", "CARGADOR DE BATERIA 12V", "GRASA MULTIPROPOSITO"]),
            ("Proteccion personal", "EPP", ["CASCO DE SEGURIDAD", "CHALECO REFLECTIVO", "GUANTE DE CUERO", "MASCARILLA PARA POLVO", "RESPIRADOR CON FILTRO", "PROTECTOR AUDITIVO", "BOTAS DE SEGURIDAD", "ARNES DE SEGURIDAD", "CARETA FACIAL TRANSPARENTE", "RODILLERA DE TRABAJO"]),
        ]
        index = 1
        for category, prefix, names in families:
            for name in names:
                product_id = f"7460002{index:06d}"
                if self.fetch_one("SELECT id FROM products WHERE id = ?", (product_id,)):
                    index += 1
                    continue
                price = 75 + (index % 17) * 38 + (index // 10) * 12
                self.save_product({
                    "id": product_id,
                    "sku": f"{prefix}-{index:03d}",
                    "barcode": product_id,
                    "brand": "AHG SELECT",
                    "unit_name": "unidad",
                    "location": f"P{(index % 8) + 1}-E{(index % 5) + 1}",
                    "supplier": "CEMENTOS DEL CIBAO SRL" if category == "Cemento y agregados" else "HERRAMIENTAS Y FIJACIONES SRL",
                    "category": category,
                    "name": name,
                    "technical_description": f"{name} para venta de ferreteria, obra, mantenimiento y reparacion.",
                    "cost": round(price * 0.68, 2),
                    "price": round(price, 2),
                    "tax_rate": 18,
                    "stock": 20 + (index % 60),
                    "min_stock": 5 + (index % 12),
                    "tags": f"{category} {name} ferreteria construccion reparacion mantenimiento".lower(),
                    "active": True,
                })
                index += 1

    def list_products(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT
                p.id, p.sku, p.name, p.technical_description, p.price,
                p.barcode, p.brand, p.unit_name, p.location, p.supplier,
                p.cost, p.tax_rate, p.stock, p.min_stock, p.tags,
                p.active, p.created_at, p.updated_at, c.id AS category_id,
                c.name AS category
            FROM products p
            JOIN categories c ON c.id = p.category_id
            ORDER BY c.name, p.name
            """
        )

    def list_products_page(self, query: str = "", page: int = 1, limit: int = 25) -> dict[str, Any]:
        page, limit = self.normalize_page(page, limit)
        terms = [term.strip().lower() for term in str(query or "").split() if term.strip()]
        clauses = ["1 = 1"]
        params: list[Any] = []
        for term in terms:
            clauses.append(
                "LOWER(p.id || ' ' || p.sku || ' ' || p.barcode || ' ' || p.brand || ' ' || p.name || ' ' || p.technical_description || ' ' || p.tags) LIKE ?"
            )
            params.append(f"%{term}%")
        where = " AND ".join(clauses)
        total = int(self.scalar(f"SELECT COUNT(*) FROM products p WHERE {where}", tuple(params)) or 0)
        rows = self.fetch_all(
            f"""
            SELECT p.id, p.sku, p.name, p.technical_description, p.price,
                   p.barcode, p.brand, p.unit_name, p.location, p.supplier,
                   p.cost, p.tax_rate, p.stock, p.min_stock, p.tags,
                   p.active, p.created_at, p.updated_at, c.id AS category_id,
                   c.name AS category
            FROM products p
            JOIN categories c ON c.id = p.category_id
            WHERE {where}
            ORDER BY c.name, p.name
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, (page - 1) * limit]),
        )
        return self.page_result(rows, total, page, limit)

    def list_categories(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT c.id, c.name, COUNT(p.id) AS product_count
            FROM categories c
            LEFT JOIN products p ON p.category_id = c.id
            GROUP BY c.id, c.name
            ORDER BY c.name
            """
        )

    def save_product(self, payload: dict[str, Any], product_id: str | None = None) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        sku = str(payload.get("sku", "")).strip().upper()
        barcode = str(payload.get("barcode", "")).strip()
        brand = str(payload.get("brand", "")).strip()
        unit_name = str(payload.get("unit_name", "unidad")).strip() or "unidad"
        location = str(payload.get("location", "")).strip()
        supplier = str(payload.get("supplier", "")).strip()
        description = str(payload.get("technical_description", "")).strip()
        tags = str(payload.get("tags", "")).strip()
        category_name = str(payload.get("category", "")).strip()
        if len(name) < 2:
            raise DatabaseError("El nombre del artículo debe tener al menos 2 caracteres.")
        if not sku:
            raise DatabaseError("La referencia o SKU es obligatoria.")
        if not category_name:
            raise DatabaseError("La categoría es obligatoria.")
        price = self._non_negative(payload.get("price"), "precio")
        cost = self._non_negative(payload.get("cost", 0), "costo")
        stock = self._non_negative(payload.get("stock", 0), "stock")
        min_stock = self._non_negative(payload.get("min_stock", 0), "stock mínimo")
        try:
            tax_input = float(payload.get("tax_rate", 18) or 0)
        except (TypeError, ValueError) as exc:
            raise DatabaseError("El ITBIS debe ser numérico.") from exc
        tax_rate = tax_input / 100 if tax_input > 1 else tax_input
        if tax_rate < 0 or tax_rate > 1:
            raise DatabaseError("El ITBIS debe estar entre 0 y 100%.")
        active = bool(payload.get("active", True))
        identifier = str(product_id or payload.get("id") or barcode).strip()
        if not identifier:
            identifier = f"ART{int(self.scalar('SELECT COUNT(*) FROM products')) + 1:010d}"
        if len(identifier) > 40:
            raise DatabaseError("El código del artículo no puede superar 40 caracteres.")

        try:
            category = self.fetch_one("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (category_name,))
            if category:
                category_id = int(category["id"])
            else:
                category_id = self.insert_and_get_id("INSERT INTO categories(name) VALUES (?)", (category_name,))
            now = self.now()
            existing = self.fetch_one("SELECT id, stock FROM products WHERE id = ?", (identifier,))
            if product_id and not existing:
                raise DatabaseError("Artículo no encontrado.")
            duplicate = self.fetch_one("SELECT id FROM products WHERE sku = ? AND id <> ?", (sku, identifier))
            if duplicate:
                raise DatabaseError("Ya existe otro artículo con ese SKU.")
            if barcode:
                duplicate_barcode = self.fetch_one(
                    "SELECT id FROM products WHERE barcode = ? AND id <> ?",
                    (barcode, identifier),
                )
                if duplicate_barcode:
                    raise DatabaseError("Ya existe otro artículo con ese código de barras.")
            active_value = active if self.kind == "postgres" else int(active)
            if existing:
                previous_stock = float(existing["stock"])
                self.execute(
                    """
                    UPDATE products
                    SET sku = ?, category_id = ?, name = ?, technical_description = ?,
                        barcode = ?, brand = ?, unit_name = ?, location = ?, supplier = ?,
                        cost = ?, price = ?, tax_rate = ?, stock = ?,
                        min_stock = ?, tags = ?, active = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        sku, category_id, name, description, barcode, brand,
                        unit_name, location, supplier, cost, price,
                        tax_rate, stock, min_stock, tags, active_value, now, identifier,
                    ),
                )
                difference = round(stock - previous_stock, 3)
                if difference:
                    self.execute(
                        """
                        INSERT INTO inventory_movements(product_id, movement_type, quantity, reference, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (identifier, "ajuste", difference, "Maestro de artículos", now),
                    )
            else:
                self.execute(
                    """
                    INSERT INTO products(
                        id, sku, category_id, name, technical_description, barcode,
                        brand, unit_name, location, supplier,
                        cost, price, tax_rate, stock, min_stock, tags, active,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identifier, sku, category_id, name, description, barcode,
                        brand, unit_name, location, supplier,
                        cost, price, tax_rate, stock, min_stock, tags, active_value,
                        now, now,
                    ),
                )
                if stock:
                    self.execute(
                        """
                        INSERT INTO inventory_movements(product_id, movement_type, quantity, reference, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (identifier, "inicial", stock, "Maestro de artículos", now),
                    )
            self.conn.commit()
            return self.get_product(identifier)
        except Exception:
            self.conn.rollback()
            raise

    def get_product(self, product_id: str) -> dict[str, Any]:
        product = self.fetch_one(
            """
            SELECT p.*, c.name AS category
            FROM products p
            JOIN categories c ON c.id = p.category_id
            WHERE p.id = ?
            """,
            (product_id,),
        )
        if not product:
            raise DatabaseError("Artículo no encontrado.")
        return product

    def list_clients(self) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT id, name, COALESCE(fiscal_id, '') AS rnc_cedula, phone, email,
                   address, taxpayer_activity, dgii_locked, notes, active, created_at,
                   0 AS credit_balance
            FROM clients
            WHERE active = 1
            ORDER BY name
            """
        )
        for client in rows:
            client["credit_balance"] = self.client_credit_balance(int(client["id"]))
        return rows

    def list_clients_page(self, query: str = "", page: int = 1, limit: int = 25) -> dict[str, Any]:
        page, limit = self.normalize_page(page, limit)
        term = str(query or "").strip().lower()
        active_value = True if self.kind == "postgres" else 1
        params: tuple[Any, ...] = (active_value,)
        where = "active = ?"
        if term:
            where += " AND LOWER(name || ' ' || COALESCE(fiscal_id, '') || ' ' || phone || ' ' || email) LIKE ?"
            params += (f"%{term}%",)
        total = int(self.scalar(f"SELECT COUNT(*) FROM clients WHERE {where}", params) or 0)
        rows = self.fetch_all(
            f"""
            SELECT id, name, COALESCE(fiscal_id, '') AS rnc_cedula, phone, email,
                   address, taxpayer_activity, dgii_locked, notes, active, created_at,
                   0 AS credit_balance
            FROM clients WHERE {where} ORDER BY name LIMIT ? OFFSET ?
            """,
            params + (limit, (page - 1) * limit),
        )
        for client in rows:
            client["credit_balance"] = self.client_credit_balance(int(client["id"]))
        return self.page_result(rows, total, page, limit)

    def save_client(self, payload: dict[str, Any], client_id: int | None = None) -> dict[str, Any]:
        party = normalize_party_payload(payload, "cliente")
        existing = self.fetch_one("SELECT * FROM clients WHERE id = ?", (client_id,)) if client_id else None
        if client_id and not existing:
            raise DatabaseError("Cliente no encontrado.")
        duplicate = self.fetch_one(
            "SELECT id FROM clients WHERE fiscal_id = ? AND id <> ?",
            (party["fiscal_id"], client_id or 0),
        )
        if duplicate:
            raise DatabaseError("Ya existe un cliente con ese RNC o cedula.")
        active_value = party["active"] if self.kind == "postgres" else int(party["active"])
        now = self.now()
        if existing:
            internal_key = existing["rnc_cedula"]
            self.execute(
                """
                UPDATE clients
                SET name = ?, fiscal_id = ?, phone = ?, email = ?, address = ?,
                    taxpayer_activity = ?, dgii_locked = ?, notes = ?, active = ?
                WHERE id = ?
                """,
                (
                    party["name"], party["fiscal_id"], party["phone"], party["email"],
                    party["address"], party["taxpayer_activity"],
                    party["dgii_locked"] if self.kind == "postgres" else int(party["dgii_locked"]),
                    party["notes"], active_value, client_id,
                ),
            )
            saved_id = int(client_id)
        else:
            internal_key = party["fiscal_id"]
            saved_id = self.insert_and_get_id(
                """
                INSERT INTO clients(
                    rnc_cedula, fiscal_id, name, phone, email, address,
                    taxpayer_activity, dgii_locked, notes, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    internal_key, party["fiscal_id"], party["name"], party["phone"],
                    party["email"], party["address"], party["taxpayer_activity"],
                    party["dgii_locked"] if self.kind == "postgres" else int(party["dgii_locked"]),
                    party["notes"], active_value, now,
                ),
            )
        self.conn.commit()
        return self.get_client(saved_id)

    def get_client(self, client_id: int) -> dict[str, Any]:
        client = self.fetch_one(
            """
            SELECT id, name, COALESCE(fiscal_id, '') AS rnc_cedula, phone, email,
                   address, taxpayer_activity, dgii_locked, notes, active, created_at
            FROM clients
            WHERE id = ?
            """,
            (client_id,),
        )
        if not client:
            raise DatabaseError("Cliente no encontrado.")
        client["credit_balance"] = self.client_credit_balance(int(client["id"]))
        return client

    def client_credit_balance(self, client_id: int) -> float:
        return round(sum(float(note["available_amount"]) for note in self.available_credit_notes(client_id)), 2)

    def available_credit_notes(self, client_id: int | None, note_code: str = "") -> list[dict[str, Any]]:
        code = str(note_code or "").strip().upper()
        where = "1 = 1"
        params: tuple[Any, ...] = ()
        if client_id and code:
            where = "(i.client_id = ? OR i.client_id IS NULL) AND UPPER(COALESCE(NULLIF(cn.provider_encf, ''), cn.en_ncf)) = ?"
            params = (client_id, code)
        elif client_id:
            where = "i.client_id = ?"
            params = (client_id,)
        elif code:
            where = "UPPER(COALESCE(NULLIF(cn.provider_encf, ''), cn.en_ncf)) = ?"
            params = (code,)
        rows = self.fetch_all(
            f"""
            SELECT cn.id, cn.en_ncf, cn.provider_encf, cn.total, cn.reason, cn.issued_at, cn.expires_at,
                   i.client_id AS source_client_id,
                   COALESCE(c.name, 'Consumidor Final') AS source_client_name,
                   COALESCE((SELECT SUM(ca.amount) FROM credit_applications ca WHERE ca.credit_note_id = cn.id), 0) AS applied
            FROM credit_notes cn
            JOIN invoices i ON i.id = cn.source_invoice_id
            LEFT JOIN clients c ON c.id = i.client_id
            WHERE {where}
              AND COALESCE(cn.api_error, '') = ''
              AND LOWER(COALESCE(cn.api_status, '')) LIKE '%acept%'
              AND (COALESCE(cn.expires_at, '') = '' OR cn.expires_at >= ?)
            ORDER BY cn.id
            """,
            params + (date.today().isoformat(),),
        )
        available: list[dict[str, Any]] = []
        for row in rows:
            row["display_encf"] = row.get("provider_encf") or row.get("en_ncf") or ""
            row["available_amount"] = round(max(0.0, float(row["total"]) - float(row["applied"] or 0)), 2)
            row["credit_status"] = "vigente"
            if row["available_amount"] > 0:
                available.append(row)
        return available

    def apply_client_credit(
        self,
        client_id: int | None,
        invoice_id: int,
        amount: float,
        note_code: str = "",
    ) -> float:
        if not client_id or amount <= 0:
            return 0.0
        remaining = round(float(amount), 2)
        applied_total = 0.0
        notes = self.available_credit_notes(client_id, note_code)
        for note in notes:
            available = float(note["available_amount"])
            if available <= 0:
                continue
            applied = min(available, remaining)
            self.execute(
                """
                INSERT INTO credit_applications(credit_note_id, invoice_id, client_id, amount, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (note["id"], invoice_id, client_id, applied, self.now()),
            )
            applied_total = round(applied_total + applied, 2)
            remaining = round(remaining - applied, 2)
            if remaining <= 0:
                break
        return applied_total

    def delete_client(self, client_id: int, password: str) -> None:
        if password != "0000":
            raise PermissionError("Contraseña de seguridad incorrecta.")
        self.execute("UPDATE clients SET active = 0 WHERE id = ?", (client_id,))
        self.conn.commit()

    def list_suppliers(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT id, name, rnc_cedula, phone, email, address, contact_person,
                   taxpayer_activity, dgii_locked, notes, active, created_at, updated_at
            FROM suppliers
            WHERE active = 1
            ORDER BY name
            """
        )

    def list_suppliers_page(self, query: str = "", page: int = 1, limit: int = 25) -> dict[str, Any]:
        page, limit = self.normalize_page(page, limit)
        term = str(query or "").strip().lower()
        active_value = True if self.kind == "postgres" else 1
        params: tuple[Any, ...] = (active_value,)
        where = "active = ?"
        if term:
            where += " AND LOWER(name || ' ' || rnc_cedula || ' ' || phone || ' ' || email) LIKE ?"
            params += (f"%{term}%",)
        total = int(self.scalar(f"SELECT COUNT(*) FROM suppliers WHERE {where}", params) or 0)
        rows = self.fetch_all(
            f"""
            SELECT id, name, rnc_cedula, phone, email, address, contact_person,
                   taxpayer_activity, dgii_locked, notes, active, created_at, updated_at
            FROM suppliers WHERE {where} ORDER BY name LIMIT ? OFFSET ?
            """,
            params + (limit, (page - 1) * limit),
        )
        return self.page_result(rows, total, page, limit)

    def save_supplier(self, payload: dict[str, Any], supplier_id: int | None = None) -> dict[str, Any]:
        party = normalize_party_payload(payload, "proveedor")
        contact_person = "".join(ch for ch in str(payload.get("contact_person", "")) if ch.isdigit())
        if contact_person and len(contact_person) != 10:
            raise DatabaseError("El contacto del proveedor debe tener 10 digitos.")
        existing = self.fetch_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)) if supplier_id else None
        if supplier_id and not existing:
            raise DatabaseError("Proveedor no encontrado.")
        duplicate = self.fetch_one(
            "SELECT id FROM suppliers WHERE rnc_cedula = ? AND id <> ?",
            (party["fiscal_id"], supplier_id or 0),
        )
        if duplicate:
            raise DatabaseError("Ya existe un proveedor con ese RNC o cedula.")
        active_value = party["active"] if self.kind == "postgres" else int(party["active"])
        now = self.now()
        if existing:
            self.execute(
                """
                UPDATE suppliers
                SET rnc_cedula = ?, name = ?, phone = ?, email = ?, address = ?,
                    contact_person = ?, taxpayer_activity = ?, dgii_locked = ?,
                    notes = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    party["fiscal_id"], party["name"], party["phone"], party["email"],
                    party["address"], contact_person, party["taxpayer_activity"],
                    party["dgii_locked"] if self.kind == "postgres" else int(party["dgii_locked"]),
                    party["notes"], active_value, now, supplier_id,
                ),
            )
            saved_id = int(supplier_id)
        else:
            saved_id = self.insert_and_get_id(
                """
                INSERT INTO suppliers(
                    rnc_cedula, name, phone, email, address, contact_person,
                    taxpayer_activity, dgii_locked, notes, active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    party["fiscal_id"], party["name"], party["phone"], party["email"],
                    party["address"], contact_person, party["taxpayer_activity"],
                    party["dgii_locked"] if self.kind == "postgres" else int(party["dgii_locked"]),
                    party["notes"], active_value, now, now,
                ),
            )
        self.conn.commit()
        return self.get_supplier(saved_id)

    def get_supplier(self, supplier_id: int) -> dict[str, Any]:
        supplier = self.fetch_one(
            """
            SELECT id, name, rnc_cedula, phone, email, address, contact_person,
                   taxpayer_activity, dgii_locked, notes, active, created_at, updated_at
            FROM suppliers
            WHERE id = ?
            """,
            (supplier_id,),
        )
        if not supplier:
            raise DatabaseError("Proveedor no encontrado.")
        return supplier

    def delete_supplier(self, supplier_id: int, password: str) -> None:
        if password != "0000":
            raise PermissionError("Contraseña de seguridad incorrecta.")
        self.execute("UPDATE suppliers SET active = 0, updated_at = ? WHERE id = ?", (self.now(), supplier_id))
        self.conn.commit()

    def save_public_quote_request(
        self,
        customer_name: str,
        phone: str,
        email: str,
        problem: str,
        quote: dict[str, Any],
        fiscal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fiscal = fiscal or {}
        now = self.now()
        request_id = self.insert_and_get_id(
            """
            INSERT INTO public_quote_requests(
                customer_name, phone, email, problem, items_json,
                subtotal, tax, total, status, created_at, updated_at,
                ecf_type, rnc_cedula, address, taxpayer_name, taxpayer_activity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_name.strip(), phone.strip(), email.strip().lower(), problem.strip(),
                json.dumps(quote.get("lines", []), ensure_ascii=False),
                quote.get("subtotal", 0), quote.get("tax", 0), quote.get("total", 0), now, now,
                str(fiscal.get("ecf_type", "32")), str(fiscal.get("rnc_cedula", "")),
                str(fiscal.get("address", "")), str(fiscal.get("taxpayer_name", "")),
                str(fiscal.get("taxpayer_activity", "")),
            ),
        )
        self.conn.commit()
        return self.get_public_quote_request(request_id)

    def list_users(self) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT id, name, email, phone, role, module_permissions_json, active, last_login_at, created_at
            FROM users ORDER BY name, id
            """
        )
        return [self.user_public_record(row) for row in rows]

    @staticmethod
    def user_public_record(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        role = str(result.get("role") or "cajero")
        result["modules"] = list(normalize_user_modules(result.pop("module_permissions_json", None), role))
        return result

    def save_user(self, payload: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
        phone = "".join(ch for ch in str(payload.get("phone", "")) if ch.isdigit())
        role = str(payload.get("role", "cajero")).strip().lower()
        password = str(payload.get("password", ""))
        active = bool(payload.get("active", True))
        if len(name) < 2 or "@" not in email or len(email) < 5:
            raise DatabaseError("Nombre y correo de usuario son obligatorios.")
        if role not in {"admin", "gerente", "cajero", "vendedor", "almacen"}:
            raise DatabaseError("Rol de usuario no válido.")
        if user_id is None and len(password) < 8:
            raise DatabaseError("La contraseña inicial debe tener al menos 8 caracteres.")
        active_value = active if self.kind == "postgres" else int(active)
        now = self.now()
        try:
            if user_id is not None:
                existing = self.fetch_one("SELECT id, module_permissions_json FROM users WHERE id = ?", (int(user_id),))
                if not existing:
                    raise DatabaseError("Usuario no encontrado.")
                raw_modules = payload.get("modules") if "modules" in payload else existing.get("module_permissions_json")
                modules_json = json.dumps(normalize_user_modules(raw_modules, role), ensure_ascii=False)
                if password:
                    self.execute("UPDATE users SET name = ?, email = ?, phone = ?, role = ?, module_permissions_json = ?, active = ?, password_hash = ? WHERE id = ?", (name, email, phone, role, modules_json, active_value, hash_password(password), int(user_id)))
                else:
                    self.execute("UPDATE users SET name = ?, email = ?, phone = ?, role = ?, module_permissions_json = ?, active = ? WHERE id = ?", (name, email, phone, role, modules_json, active_value, int(user_id)))
                saved_id = int(user_id)
            else:
                modules_json = json.dumps(normalize_user_modules(payload.get("modules"), role), ensure_ascii=False)
                saved_id = self.insert_and_get_id("INSERT INTO users(name, email, phone, password_hash, role, module_permissions_json, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (name, email, phone, hash_password(password), role, modules_json, active_value, now))
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise DatabaseError("Ya existe un usuario con ese correo.") from exc
            raise
        saved = self.fetch_one("SELECT id, name, email, phone, role, module_permissions_json, active, last_login_at, created_at FROM users WHERE id = ?", (saved_id,)) or {}
        return self.user_public_record(saved) if saved else {}

    def export_backup(self) -> dict[str, Any]:
        if self.kind == "sqlite":
            tables = [row["name"] for row in self.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        else:
            tables = [row["table_name"] for row in self.fetch_all("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name")]
        data: dict[str, Any] = {}
        for table in tables:
            data[table] = self.fetch_all(f'SELECT * FROM "{table}"')
        return {"format": "ahg-pos-backup-v1", "database": self.kind, "generated_at": self.now(), "tables": data}

    def get_public_quote_request(self, request_id: int) -> dict[str, Any]:
        row = self.fetch_one("SELECT * FROM public_quote_requests WHERE id = ?", (request_id,))
        if not row:
            raise DatabaseError("Solicitud de cotización no encontrada.")
        result = dict(row)
        result["items"] = json.loads(result.pop("items_json") or "[]")
        return result

    def list_public_quote_requests(self) -> list[dict[str, Any]]:
        rows = self.fetch_all("SELECT * FROM public_quote_requests ORDER BY id DESC LIMIT 100")
        result = []
        for row in rows:
            item = dict(row)
            item["items"] = json.loads(item.pop("items_json") or "[]")
            result.append(item)
        return result

    def delete_public_quote_request(self, request_id: int) -> dict[str, Any]:
        request = self.get_public_quote_request(request_id)
        self.execute("DELETE FROM public_quote_requests WHERE id = ?", (request_id,))
        self.conn.commit()
        return request

    def list_preinvoices(self) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT p.*, COALESCE(c.name, 'Sin cliente') AS client_name,
                   COALESCE(c.fiscal_id, '') AS rnc_cedula,
                   COALESCE(c.phone, '') AS phone,
                   COALESCE(c.email, '') AS email,
                   COALESCE(c.address, '') AS address
            FROM preinvoices p
            LEFT JOIN clients c ON c.id = p.client_id
            ORDER BY p.id DESC
            """
        )
        return rows

    def list_preinvoices_page(self, page: int = 1, limit: int = 25) -> dict[str, Any]:
        page, limit = self.normalize_page(page, limit)
        total = int(self.scalar("SELECT COUNT(*) FROM preinvoices") or 0)
        rows = self.fetch_all(
            """
            SELECT p.*, COALESCE(c.name, 'Sin cliente') AS client_name,
                   COALESCE(c.fiscal_id, '') AS rnc_cedula,
                   COALESCE(c.phone, '') AS phone, COALESCE(c.email, '') AS email,
                   COALESCE(c.address, '') AS address
            FROM preinvoices p LEFT JOIN clients c ON c.id = p.client_id
            ORDER BY p.id DESC LIMIT ? OFFSET ?
            """,
            (limit, (page - 1) * limit),
        )
        return self.page_result(rows, total, page, limit)

    def get_preinvoice(self, preinvoice_id: int) -> dict[str, Any]:
        draft = self.fetch_one(
            """
            SELECT p.*, COALESCE(c.name, '') AS client_name,
                   COALESCE(c.fiscal_id, '') AS rnc_cedula,
                   COALESCE(c.phone, '') AS phone,
                   COALESCE(c.email, '') AS email,
                   COALESCE(c.address, '') AS address
            FROM preinvoices p
            LEFT JOIN clients c ON c.id = p.client_id
            WHERE p.id = ?
            """,
            (preinvoice_id,),
        )
        if not draft:
            raise DatabaseError("Pre-Factura no encontrada.")
        draft["items"] = self.fetch_all(
            """
            SELECT pi.product_id, p.name, p.sku, pi.quantity, pi.unit_price,
                   COALESCE(pi.discount_amount, 0) AS discount_amount,
                   pi.tax_rate, p.stock
            FROM preinvoice_items pi
            JOIN products p ON p.id = pi.product_id
            WHERE pi.preinvoice_id = ?
            ORDER BY pi.id
            """,
            (preinvoice_id,),
        )
        return draft

    def save_preinvoice(
        self,
        payload: dict[str, Any],
        user_id: int,
        preinvoice_id: int | None = None,
    ) -> dict[str, Any]:
        ecf_type = str(payload.get("ecf_type", "32"))
        payment_method = str(payload.get("payment_method", "efectivo"))
        notes = str(payload.get("notes", "")).strip()
        if ecf_type not in {"31", "32"}:
            raise DatabaseError("La pre-factura solo admite e-CF 31 o 32.")
        if payment_method not in {"efectivo", "tarjeta", "transferencia", "credito", "paypal"}:
            raise DatabaseError("Método de pago no válido.")
        client = payload.get("client") or {}
        client_id = int(client.get("id") or 0) or None
        if not client_id and str(client.get("name", "")).strip():
            client_id = int(self.save_client(client)["id"])
        existing = self.fetch_one("SELECT * FROM preinvoices WHERE id = ?", (preinvoice_id,)) if preinvoice_id else None
        if preinvoice_id and not existing:
            raise DatabaseError("Pre-Factura no encontrada.")
        if existing and existing["status"] != "borrador":
            raise DatabaseError("Esta pre-factura ya fue emitida.")

        lines: list[dict[str, Any]] = []
        for item in payload.get("items") or []:
            product_id = str(item.get("product_id", "")).strip()
            product = self.fetch_one("SELECT * FROM products WHERE id = ?", (product_id,))
            if not product:
                raise DatabaseError(f"Producto no encontrado: {product_id}")
            quantity = float(item.get("quantity", 0))
            unit_price = float(item.get("unit_price", product["price"]) or 0)
            if quantity <= 0 or unit_price < 0:
                raise DatabaseError("Cantidad y precio de pre-factura no válidos.")
            tax_rate = float(product["tax_rate"])
            line_gross = round(quantity * unit_price, 2)
            discount_amount = clean_discount_amount(item, line_gross)
            lines.append(
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "discount_amount": discount_amount,
                    "tax_rate": tax_rate,
                    "line_gross": line_gross,
                }
            )
        base_after_line_discounts = sum(line["line_gross"] - line["discount_amount"] for line in lines)
        totals = compute_invoice_totals(
            lines,
            clean_discount_amount(payload, base_after_line_discounts, "general_discount"),
        )
        subtotal = totals["subtotal"]
        tax = totals["tax"]
        total = totals["total"]
        discount_total = totals["discount_total"]
        general_discount = totals["general_discount"]
        now = self.now()
        try:
            self.conn.execute("BEGIN")
            if existing:
                self.execute(
                    """
                    UPDATE preinvoices
                    SET client_id = ?, ecf_type = ?, payment_method = ?, notes = ?,
                        subtotal = ?, discount_total = ?, general_discount = ?, tax = ?, total = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        client_id, ecf_type, payment_method, notes, subtotal,
                        discount_total, general_discount, tax, total, now, preinvoice_id,
                    ),
                )
                self.execute("DELETE FROM preinvoice_items WHERE preinvoice_id = ?", (preinvoice_id,))
                saved_id = int(preinvoice_id)
            else:
                saved_id = self.insert_and_get_id(
                    """
                    INSERT INTO preinvoices(
                        client_id, ecf_type, payment_method, notes, subtotal,
                        discount_total, general_discount, tax, total, status, created_by, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_id, ecf_type, payment_method, notes, subtotal,
                        discount_total, general_discount, tax, total, "borrador", user_id, now, now,
                    ),
                )
            for line in lines:
                self.execute(
                    """
                    INSERT INTO preinvoice_items(
                        preinvoice_id, product_id, quantity, unit_price, discount_amount, tax_rate
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        saved_id, line["product_id"], line["quantity"],
                        line["unit_price"], line["discount_amount"], line["tax_rate"],
                    ),
                )
            self.conn.commit()
            return self.get_preinvoice(saved_id)
        except Exception:
            self.conn.rollback()
            raise

    def mark_preinvoice_emitted(self, preinvoice_id: int, invoice_id: int) -> None:
        self.execute(
            """
            UPDATE preinvoices
            SET status = 'emitida', emitted_invoice_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (invoice_id, self.now(), preinvoice_id),
        )
        self.conn.commit()

    def create_credit_note(
        self,
        source_invoice_id: int,
        modification_code: str,
        reason: str,
        fiscal_environment: str,
        expires_at: str = "",
    ) -> dict[str, Any]:
        if modification_code not in {"1", "2", "3"}:
            raise DatabaseError("El código de modificación E34 debe ser 1, 2 o 3.")
        reason = reason.strip()
        if len(reason) < 5:
            raise DatabaseError("Indica el motivo de la nota de crédito.")
        source = self.get_invoice(source_invoice_id)
        if not source.get("provider_encf"):
            raise DatabaseError("El E34 requiere una factura electrónica previamente enviada a IMECF.")
        existing = self.fetch_one(
            "SELECT id FROM credit_notes WHERE source_invoice_id = ? AND api_status NOT LIKE '%Rechaz%'",
            (source_invoice_id,),
        )
        if existing:
            raise DatabaseError("Esta factura ya tiene una nota de crédito E34 registrada.")
        try:
            self.conn.execute("BEGIN")
            sequence = self.fetch_one("SELECT current_number FROM credit_note_sequences WHERE id = 1")
            number = int(sequence["current_number"])
            en_ncf = f"E34{number:010d}"
            self.execute("UPDATE credit_note_sequences SET current_number = ? WHERE id = 1", (number + 1,))
            now = self.now()
            issued_date = self._parse_datetime(now).date()
            try:
                expiry_date = date.fromisoformat(str(expires_at or "").strip()) if expires_at else issued_date + timedelta(days=90)
            except ValueError as exc:
                raise DatabaseError("La fecha de expiraciÃ³n del saldo no es vÃ¡lida.") from exc
            if expiry_date < issued_date:
                raise DatabaseError("La vigencia comercial no puede vencer antes de emitirse la nota.")
            note_id = self.insert_and_get_id(
                """
                INSERT INTO credit_notes(
                    source_invoice_id, en_ncf, modification_code, reason,
                    subtotal, tax, total, status, issued_at, expires_at, fiscal_environment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_invoice_id, en_ncf, modification_code, reason,
                    source["subtotal"], source["tax"], source["total"],
                    "emitida", now, expiry_date.isoformat(), fiscal_environment,
                ),
            )
            self.conn.commit()
            return self.get_credit_note(note_id)
        except Exception:
            self.conn.rollback()
            raise

    def get_credit_note(self, note_id: int) -> dict[str, Any]:
        note = self.fetch_one(
            """
            SELECT cn.*, i.issued_at AS source_issued_at,
                   COALESCE(api.encf, i.en_ncf) AS source_encf,
                   i.ecf_type AS source_ecf_type,
                   COALESCE(c.fiscal_id, '') AS rnc_cedula,
                   COALESCE(c.name, 'Consumidor Final') AS client_name
            FROM credit_notes cn
            JOIN invoices i ON i.id = cn.source_invoice_id
            LEFT JOIN clients c ON c.id = i.client_id
            LEFT JOIN ecf_api_records api ON api.invoice_id = i.id
            WHERE cn.id = ?
            """,
            (note_id,),
        )
        if not note:
            raise DatabaseError("Nota de crédito no encontrada.")
        note["items"] = self.fetch_all(
            """
            SELECT ii.product_id, p.name, ii.quantity, ii.unit_price,
                   ii.tax_rate, ii.line_subtotal, ii.line_tax, ii.line_total
            FROM invoice_items ii
            JOIN products p ON p.id = ii.product_id
            WHERE ii.invoice_id = ?
            ORDER BY ii.id
            """,
            (note["source_invoice_id"],),
        )
        note["applied_amount"] = float(self.scalar(
            "SELECT COALESCE(SUM(amount), 0) FROM credit_applications WHERE credit_note_id = ?",
            (note_id,),
        ) or 0)
        note["available_amount"] = round(max(0.0, float(note["total"]) - note["applied_amount"]), 2)
        self._decorate_credit_note(note)
        return note

    def list_credit_notes(self) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT cn.id, cn.source_invoice_id, cn.en_ncf, cn.provider_encf,
                   cn.modification_code, cn.reason, cn.total, cn.status,
                   cn.api_status, cn.api_error, cn.track_id, cn.provider_document_id, cn.issued_at, cn.expires_at,
                   COALESCE(api.encf, i.en_ncf) AS source_encf,
                   COALESCE(c.name, 'Consumidor Final') AS source_client_name,
                   COALESCE((SELECT SUM(ca.amount) FROM credit_applications ca WHERE ca.credit_note_id = cn.id), 0) AS applied_amount
            FROM credit_notes cn
            JOIN invoices i ON i.id = cn.source_invoice_id
            LEFT JOIN clients c ON c.id = i.client_id
            LEFT JOIN ecf_api_records api ON api.invoice_id = i.id
            ORDER BY cn.id DESC
            """
        )
        for row in rows:
            row["available_amount"] = round(max(0.0, float(row["total"]) - float(row.get("applied_amount") or 0)), 2)
            self._decorate_credit_note(row)
        return rows

    def list_credit_notes_page(self, page: int = 1, limit: int = 25) -> dict[str, Any]:
        page, limit = self.normalize_page(page, limit)
        total = int(self.scalar("SELECT COUNT(*) FROM credit_notes") or 0)
        rows = self.fetch_all(
            """
            SELECT cn.id, cn.source_invoice_id, cn.en_ncf, cn.provider_encf,
                   cn.modification_code, cn.reason, cn.total, cn.status,
                   cn.api_status, cn.api_error, cn.track_id, cn.provider_document_id, cn.issued_at, cn.expires_at,
                   COALESCE(api.encf, i.en_ncf) AS source_encf,
                   COALESCE(c.name, 'Consumidor Final') AS source_client_name,
                   COALESCE((SELECT SUM(ca.amount) FROM credit_applications ca WHERE ca.credit_note_id = cn.id), 0) AS applied_amount
            FROM credit_notes cn JOIN invoices i ON i.id = cn.source_invoice_id
            LEFT JOIN clients c ON c.id = i.client_id
            LEFT JOIN ecf_api_records api ON api.invoice_id = i.id
            ORDER BY cn.id DESC LIMIT ? OFFSET ?
            """,
            (limit, (page - 1) * limit),
        )
        for row in rows:
            row["available_amount"] = round(max(0.0, float(row["total"]) - float(row.get("applied_amount") or 0)), 2)
            self._decorate_credit_note(row)
        return self.page_result(rows, total, page, limit)

    def _decorate_credit_note(self, note: dict[str, Any]) -> None:
        status = str(note.get("api_status") or note.get("status") or "").lower()
        if note.get("api_error") or "rechaz" in status:
            note["credit_status"] = "rechazada"
        elif "acept" not in status:
            note["credit_status"] = "pendiente"
        elif note.get("expires_at") and str(note["expires_at"]) < date.today().isoformat():
            note["credit_status"] = "vencida"
        elif float(note.get("available_amount") or 0) <= 0:
            note["credit_status"] = "agotada"
        else:
            note["credit_status"] = "vigente"

    def save_credit_note_api_result(
        self,
        note_id: int,
        metadata: dict[str, Any],
        request_payload: dict[str, Any] | None,
        response_payload: dict[str, Any] | None,
        error: str = "",
    ) -> None:
        self.execute(
            """
            UPDATE credit_notes
            SET provider_document_id = ?, track_id = ?, provider_encf = ?,
                api_status = ?, request_json = ?, response_json = ?,
                api_error = ?, status = ?
            WHERE id = ?
            """,
            (
                metadata.get("provider_document_id", ""),
                metadata.get("track_id", ""),
                metadata.get("encf", ""),
                metadata.get("api_status", ""),
                json.dumps(request_payload or {}, ensure_ascii=False),
                json.dumps(response_payload or {}, ensure_ascii=False),
                error[:2000],
                metadata.get("api_status") or ("error_api" if error else "enviada"),
                note_id,
            ),
        )
        self.conn.commit()

    def get_open_cash_session(self) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM cash_sessions WHERE status = 'abierta' ORDER BY id DESC LIMIT 1"
        )

    def open_cash_session(self, user_id: int, opening_amount: float, notes: str = "") -> dict[str, Any]:
        if self.get_open_cash_session():
            raise DatabaseError("Ya existe una caja abierta. Debes cerrarla antes de iniciar otra.")
        amount = round(float(opening_amount or 0), 2)
        if amount < 0:
            raise DatabaseError("El fondo inicial no puede ser negativo.")
        session_id = self.insert_and_get_id(
            """
            INSERT INTO cash_sessions(opened_by, opened_at, opening_amount, status, notes)
            VALUES (?, ?, ?, 'abierta', ?)
            """,
            (user_id, self.now(), amount, str(notes or "").strip()[:500]),
        )
        self.conn.commit()
        return self.cash_session_detail(session_id)

    def add_cash_movement(
        self, user_id: int, movement_type: str, amount: float, description: str
    ) -> dict[str, Any]:
        session = self.get_open_cash_session()
        if not session:
            raise DatabaseError("Abre la caja antes de registrar movimientos.")
        movement_type = str(movement_type or "").strip().lower()
        if movement_type not in {"entrada", "salida"}:
            raise DatabaseError("El movimiento debe ser una entrada o una salida.")
        value = round(float(amount or 0), 2)
        description = str(description or "").strip()
        if value <= 0:
            raise DatabaseError("El monto del movimiento debe ser mayor que cero.")
        if len(description) < 3:
            raise DatabaseError("Describe el motivo del movimiento de caja.")
        self.execute(
            """
            INSERT INTO cash_movements(cash_session_id, movement_type, amount, description, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session["id"], movement_type, value, description[:300], user_id, self.now()),
        )
        self.conn.commit()
        return self.cash_session_detail(int(session["id"]))

    def cash_session_detail(self, session_id: int | None = None) -> dict[str, Any]:
        if session_id is None:
            session = self.get_open_cash_session() or self.fetch_one(
                "SELECT * FROM cash_sessions ORDER BY id DESC LIMIT 1"
            )
        else:
            session = self.fetch_one("SELECT * FROM cash_sessions WHERE id = ?", (session_id,))
        if not session:
            return {"status": "sin_apertura", "payments": [], "movements": [], "expected_cash": 0.0}
        payment_rows = self.fetch_all(
            """
            SELECT payment_method, COALESCE(SUM(amount), 0) AS amount
            FROM invoice_payments WHERE cash_session_id = ?
            GROUP BY payment_method ORDER BY payment_method
            """,
            (session["id"],),
        )
        movements = self.fetch_all(
            """
            SELECT cm.*, COALESCE(u.name, 'Sistema') AS user_name
            FROM cash_movements cm LEFT JOIN users u ON u.id = cm.created_by
            WHERE cm.cash_session_id = ? ORDER BY cm.id DESC
            """,
            (session["id"],),
        )
        cash_sales = sum(float(row["amount"]) for row in payment_rows if row["payment_method"] == "efectivo")
        entries = sum(float(row["amount"]) for row in movements if row["movement_type"] == "entrada")
        exits = sum(float(row["amount"]) for row in movements if row["movement_type"] == "salida")
        expected = round(float(session.get("opening_amount") or 0) + cash_sales + entries - exits, 2)
        session["payments"] = payment_rows
        session["movements"] = movements
        session["cash_sales"] = round(cash_sales, 2)
        session["cash_entries"] = round(entries, 2)
        session["cash_exits"] = round(exits, 2)
        session["expected_cash"] = round(float(session.get("expected_cash") if session.get("expected_cash") is not None else expected), 2)
        session["invoice_count"] = int(self.scalar(
            "SELECT COUNT(DISTINCT invoice_id) FROM invoice_payments WHERE cash_session_id = ?",
            (session["id"],),
        ) or 0)
        return session

    def close_cash_session(self, user_id: int, counted_cash: float, notes: str = "") -> dict[str, Any]:
        session = self.get_open_cash_session()
        if not session:
            raise DatabaseError("No hay una caja abierta para cerrar.")
        counted = round(float(counted_cash or 0), 2)
        if counted < 0:
            raise DatabaseError("El efectivo contado no puede ser negativo.")
        detail = self.cash_session_detail(int(session["id"]))
        expected = round(float(detail["expected_cash"]), 2)
        difference = round(counted - expected, 2)
        merged_notes = " | ".join(part for part in (str(session.get("notes") or "").strip(), str(notes or "").strip()) if part)[:500]
        self.execute(
            """
            UPDATE cash_sessions SET status = 'cerrada', closed_by = ?, closed_at = ?,
                expected_cash = ?, counted_cash = ?, difference = ?, notes = ? WHERE id = ?
            """,
            (user_id, self.now(), expected, counted, difference, merged_notes, session["id"]),
        )
        self.conn.commit()
        return self.cash_session_detail(int(session["id"]))

    def list_cash_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.fetch_all("SELECT * FROM cash_sessions ORDER BY id DESC LIMIT ?", (min(100, max(1, int(limit))),))
        for row in rows:
            if row["status"] == "abierta":
                current = self.cash_session_detail(int(row["id"]))
                row.update({key: current.get(key) for key in ("expected_cash", "cash_sales", "invoice_count")})
        return rows

    @staticmethod
    def _non_negative(value: Any, label: str) -> float:
        try:
            number = float(value or 0)
        except (TypeError, ValueError) as exc:
            raise DatabaseError(f"El {label} debe ser numérico.") from exc
        if number < 0:
            raise DatabaseError(f"El {label} no puede ser negativo.")
        return round(number, 3)

    def low_stock(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT p.id, p.sku, p.name, p.stock, p.min_stock, c.name AS category
            FROM products p
            JOIN categories c ON c.id = p.category_id
            WHERE p.stock <= p.min_stock AND p.active = ?
            ORDER BY p.stock ASC, p.name ASC
            """,
            (True if self.kind == "postgres" else 1,),
        )

    def recent_invoices(self, limit: int = 25) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT
                i.id, i.en_ncf, i.ecf_type, i.subtotal, i.discount_total, i.credit_applied, i.tax, i.total,
                i.status, i.payment_method, i.issued_at,
                COALESCE(c.name, 'Consumidor Final') AS client_name,
                COALESCE(c.fiscal_id, '') AS rnc_cedula,
                COALESCE(api.provider_document_id, '') AS provider_document_id,
                COALESCE(api.track_id, '') AS track_id,
                COALESCE(api.encf, '') AS provider_encf,
                COALESCE(api.api_status, '') AS api_status,
                COALESCE(api.last_error, '') AS api_error,
                COALESCE(api.response_json, '') AS provider_response_json,
                COALESCE((SELECT CAST(fs.expires_at AS TEXT) FROM fiscal_sequences fs WHERE fs.type_code = i.ecf_type LIMIT 1), '') AS sequence_expires_at
            FROM invoices i
            LEFT JOIN clients c ON c.id = i.client_id
            LEFT JOIN ecf_api_records api ON api.invoice_id = i.id
            ORDER BY i.id DESC
            LIMIT ?
            """,
            (limit,),
        )

    def recent_invoices_page(self, query: str = "", page: int = 1, limit: int = 25) -> dict[str, Any]:
        page, limit = self.normalize_page(page, limit)
        term = str(query or "").strip().lower()
        params: tuple[Any, ...] = ()
        where = "1 = 1"
        if term:
            where += " AND LOWER(i.en_ncf || ' ' || COALESCE(c.name, '') || ' ' || COALESCE(c.fiscal_id, '')) LIKE ?"
            params = (f"%{term}%",)
        total = int(self.scalar(
            f"SELECT COUNT(*) FROM invoices i LEFT JOIN clients c ON c.id = i.client_id WHERE {where}", params
        ) or 0)
        rows = self.fetch_all(
            f"""
            SELECT i.id, i.en_ncf, i.ecf_type, i.subtotal, i.discount_total, i.credit_applied, i.tax, i.total,
                   i.status, i.payment_method, i.issued_at,
                   COALESCE(c.name, 'Consumidor Final') AS client_name,
                   COALESCE(c.fiscal_id, '') AS rnc_cedula,
                   COALESCE(api.provider_document_id, '') AS provider_document_id,
                   COALESCE(api.track_id, '') AS track_id, COALESCE(api.encf, '') AS provider_encf,
                   COALESCE(api.api_status, '') AS api_status, COALESCE(api.last_error, '') AS api_error,
                   COALESCE(api.response_json, '') AS provider_response_json,
                   COALESCE((SELECT CAST(fs.expires_at AS TEXT) FROM fiscal_sequences fs WHERE fs.type_code = i.ecf_type LIMIT 1), '') AS sequence_expires_at
            FROM invoices i LEFT JOIN clients c ON c.id = i.client_id
            LEFT JOIN ecf_api_records api ON api.invoice_id = i.id
            WHERE {where} ORDER BY i.id DESC LIMIT ? OFFSET ?
            """,
            params + (limit, (page - 1) * limit),
        )
        return self.page_result(rows, total, page, limit)

    def daily_summary(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT ecf_type, COUNT(*) AS invoice_count, COALESCE(SUM(total), 0) AS total
            FROM invoices
            GROUP BY ecf_type
            ORDER BY ecf_type
            """
        )

    def fiscal_dashboard(self) -> dict[str, Any]:
        documents = self.recent_invoices(limit=100)
        sequences = self.fetch_all(
            """
            SELECT type_code, description, prefix, current_number, end_number,
                   expires_at, authorized
            FROM fiscal_sequences
            ORDER BY type_code
            """
        )
        status_counts: dict[str, int] = {}
        for document in documents:
            status = str(document.get("api_status") or ("ERROR" if document.get("api_error") else "LOCAL"))
            status_counts[status] = status_counts.get(status, 0) + 1
        sequence_rows = []
        for sequence in sequences:
            current = int(sequence["current_number"])
            end = int(sequence["end_number"])
            available = max(0, end - current + 1)
            sequence_rows.append(
                {
                    **sequence,
                    "available": available,
                    "used": max(0, current - 1),
                    "state": "Activa" if bool(sequence["authorized"]) and available > 0 else "Agotada",
                }
            )
        return {
            "documents": documents,
            "sequences": sequence_rows,
            "counts": status_counts,
            "totals": {
                "documents": len(documents),
                "accepted": sum(value for key, value in status_counts.items() if "acept" in key.lower()),
                "errors": sum(value for key, value in status_counts.items() if "error" in key.lower()),
                "local": status_counts.get("LOCAL", 0),
                "available_sequences": sum(row["available"] for row in sequence_rows),
            },
        }

    def log_ai_query(self, query: str, result_count: int) -> None:
        self.execute(
            "INSERT INTO ai_search_logs(query, result_count, created_at) VALUES (?, ?, ?)",
            (query[:500], result_count, self.now()),
        )
        self.conn.commit()

    def log_audit(
        self,
        user_id: int | None,
        action: str,
        entity_type: str = "",
        entity_id: str | int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.execute(
            """
            INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                str(action)[:120],
                str(entity_type)[:80],
                str(entity_id or "")[:80],
                json.dumps(details or {}, ensure_ascii=False, default=str)[:4000],
                self.now(),
            ),
        )
        self.conn.commit()

    def list_audit_logs(self, page: int = 1, limit: int = 50, query: str = "") -> dict[str, Any]:
        page = max(1, int(page or 1))
        limit = min(100, max(1, int(limit or 50)))
        query = str(query or "").strip()
        clauses = ["a.user_id IS NOT NULL", "UPPER(a.action) NOT LIKE 'TRIGGER %'"]
        params: list[Any] = []
        if query:
            clauses.append("LOWER(a.action || ' ' || a.entity_type || ' ' || a.entity_id || ' ' || COALESCE(u.name, '')) LIKE ?")
            params.append(f"%{query.lower()}%")
        where = "WHERE " + " AND ".join(clauses)
        total = int(self.scalar(f"SELECT COUNT(*) FROM audit_logs a LEFT JOIN users u ON u.id = a.user_id {where}", tuple(params)) or 0)
        offset = (page - 1) * limit
        rows = self.fetch_all(
            f"""
            SELECT a.id, a.user_id, COALESCE(u.name, 'Sistema') AS user_name,
                   a.action, a.entity_type, a.entity_id, a.details_json, a.created_at
            FROM audit_logs a
            LEFT JOIN users u ON u.id = a.user_id
            {where}
            ORDER BY a.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        )
        for row in rows:
            try:
                row["details"] = json.loads(row.get("details_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                row["details"] = {}
            row.pop("details_json", None)
        pages = max(1, (total + limit - 1) // limit)
        return {"items": rows, "page": page, "limit": limit, "total": total, "pages": pages, "has_next": page < pages, "has_previous": page > 1}

    def create_invoice(
        self,
        ecf_type: str,
        client: dict[str, Any] | None,
        items: list[dict[str, Any]],
        payment_method: str = "efectivo",
        fiscal_environment: str | None = None,
        general_discount: float = 0.0,
        general_discount_percent: float = 0.0,
        credit_amount: float = 0.0,
        credit_note_code: str = "",
        payments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if ecf_type not in {"31", "32"}:
            raise DatabaseError("Solo se permiten e-CF tipo 31 o 32 en esta fase.")
        if not items:
            raise DatabaseError("La factura necesita al menos un producto.")
        if payment_method not in {"efectivo", "tarjeta", "transferencia", "credito", "paypal"}:
            raise DatabaseError("Método de pago no válido.")

        try:
            self.conn.execute("BEGIN")
            invoice_items: list[dict[str, Any]] = []

            for item in items:
                product_id = str(item.get("product_id", "")).strip()
                quantity = float(item.get("quantity", 0))
                if quantity <= 0:
                    raise DatabaseError("La cantidad debe ser mayor que cero.")
                product = self.fetch_one("SELECT * FROM products WHERE id = ?", (product_id,))
                if not product:
                    raise DatabaseError(f"Producto no encontrado: {product_id}")
                if not bool(product.get("active", True)):
                    raise DatabaseError(f"El artículo {product['name']} está inactivo.")
                if float(product["stock"]) < quantity:
                    raise DatabaseError(
                        f"Stock insuficiente para {product['name']}. Disponible: {product['stock']}."
                    )

                unit_price = float(item["unit_price"]) if item.get("unit_price") not in (None, "") else float(product["price"])
                if unit_price < 0:
                    raise DatabaseError("El precio unitario no puede ser negativo.")
                tax_rate = float(product["tax_rate"])
                line_gross = round(unit_price * quantity, 2)
                discount_amount = clean_discount_amount(item, line_gross)
                invoice_items.append(
                    {
                        "product_id": product_id,
                        "name": product["name"],
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "discount_amount": discount_amount,
                        "tax_rate": tax_rate,
                        "line_gross": line_gross,
                    }
                )

            base_after_line_discounts = sum(line["line_gross"] - line["discount_amount"] for line in invoice_items)
            totals = compute_invoice_totals(
                invoice_items,
                clean_discount_amount(
                    {
                        "general_discount": general_discount,
                        "general_discount_percent": general_discount_percent,
                    },
                    base_after_line_discounts,
                    "general_discount",
                ),
            )
            subtotal = totals["subtotal"]
            tax = totals["tax"]
            total = totals["total"]
            discount_total = totals["discount_total"]
            general_discount = totals["general_discount"]
            if total <= 0:
                raise DatabaseError("La factura fiscal debe tener un total mayor que cero.")
            client_id = self._ensure_client(client or {}, ecf_type, total)
            requested_credit = round(float(credit_amount or 0), 2)
            if requested_credit < 0:
                raise DatabaseError("El monto de la nota de crédito no puede ser negativo.")
            if requested_credit > 0 and not client_id:
                raise DatabaseError("Selecciona un cliente registrado para aplicar la nota de crédito.")
            if requested_credit > 0 and payment_method == "credito" and requested_credit < total:
                raise DatabaseError("No se puede combinar una nota de crédito con una venta pendiente a crédito.")
            available_notes = self.available_credit_notes(client_id, credit_note_code) if requested_credit > 0 else []
            available_credit = round(sum(float(note["available_amount"]) for note in available_notes), 2)
            if requested_credit > available_credit:
                raise DatabaseError(f"Crédito insuficiente. Disponible: RD${available_credit:,.2f}.")
            if requested_credit > total:
                raise DatabaseError("El crédito aplicado no puede superar el total de la venta.")
            credit_applied = requested_credit
            payable_total = round(total - credit_applied, 2)
            tender_rows = normalize_invoice_payments(payments, payment_method, payable_total)
            fiscal_payment_rows = ([{"payment_method": "nota_credito", "amount": credit_applied}] if credit_applied > 0 else []) + tender_rows
            if len(fiscal_payment_rows) > 7:
                raise DatabaseError("La nota de crÃ©dito y los demÃ¡s pagos superan las siete formas permitidas por DGII.")
            if payable_total <= 0:
                stored_payment_method = "nota_credito"
            elif payment_method != "credito":
                methods = [row["payment_method"] for row in tender_rows]
                stored_payment_method = "mixto" if credit_applied > 0 or len(methods) > 1 else (methods[0] if methods else "nota_credito")
            else:
                stored_payment_method = "credito"
            sequence = self._next_sequence(ecf_type)
            issued_at = self.now()
            invoice_id = self.insert_and_get_id(
                """
                INSERT INTO invoices(
                    en_ncf, ecf_type, client_id, subtotal, discount_total, general_discount, credit_applied, tax, total,
                    status, payment_method, issued_at, fiscal_environment
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence,
                    ecf_type,
                    client_id,
                    subtotal,
                    discount_total,
                    general_discount,
                    credit_applied,
                    tax,
                    total,
                    "emitida",
                    stored_payment_method,
                    issued_at,
                    fiscal_environment or settings.fiscal_environment,
                ),
            )
            if credit_applied > 0:
                applied = self.apply_client_credit(client_id, invoice_id, credit_applied, credit_note_code)
                if applied != credit_applied:
                    raise DatabaseError("No se pudo reservar el saldo completo de la nota de crédito.")

            for line in invoice_items:
                self.execute(
                    """
                    INSERT INTO invoice_items(
                        invoice_id, product_id, quantity, unit_price,
                        discount_amount, tax_rate, line_subtotal, line_tax, line_total
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice_id,
                        line["product_id"],
                        line["quantity"],
                        line["unit_price"],
                        line["discount_amount"],
                        line["tax_rate"],
                        line["line_subtotal"],
                        line["line_tax"],
                        line["line_total"],
                    ),
                )
                self.execute(
                    "UPDATE products SET stock = stock - ? WHERE id = ?",
                    (line["quantity"], line["product_id"]),
                )
                self.execute(
                    """
                    INSERT INTO inventory_movements(product_id, movement_type, quantity, reference, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (line["product_id"], "venta", -line["quantity"], sequence, issued_at),
                )

            cash_session = self.get_open_cash_session()
            cash_session_id = int(cash_session["id"]) if cash_session else None
            for row in fiscal_payment_rows:
                self.execute(
                    """
                    INSERT INTO invoice_payments(invoice_id, cash_session_id, payment_method, amount, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (invoice_id, cash_session_id, row["payment_method"], row["amount"], issued_at),
                )
            for row in tender_rows:
                self.execute(
                    "INSERT INTO daily_transactions(invoice_id, amount, payment_method, created_at) VALUES (?, ?, ?, ?)",
                    (invoice_id, row["amount"], row["payment_method"], issued_at),
                )
            self.conn.commit()
            tracking_token = secrets.token_urlsafe(32)
            self.execute(
                "INSERT INTO invoice_tracking_tokens(invoice_id, token_hash, created_at) VALUES (?, ?, ?)",
                (invoice_id, token_hash(tracking_token), issued_at),
            )
            self.conn.commit()
            invoice = self.get_invoice(invoice_id)
            invoice["tracking_token"] = tracking_token
            return invoice
        except Exception:
            self.conn.rollback()
            raise

    def get_invoice(self, invoice_id: int) -> dict[str, Any]:
        invoice = self.fetch_one(
            """
            SELECT
                i.*, COALESCE(c.fiscal_id, '') AS rnc_cedula,
                c.name AS client_name, c.phone, c.email, COALESCE(c.address, '') AS address,
                COALESCE(api.provider_document_id, '') AS provider_document_id,
                COALESCE(api.track_id, '') AS track_id,
                COALESCE(api.encf, '') AS provider_encf,
                COALESCE(api.api_status, '') AS api_status,
                COALESCE(api.last_error, '') AS api_error,
                COALESCE(api.response_json, '') AS provider_response_json,
                COALESCE((SELECT CAST(fs.expires_at AS TEXT) FROM fiscal_sequences fs WHERE fs.type_code = i.ecf_type LIMIT 1), '') AS sequence_expires_at
            FROM invoices i
            LEFT JOIN clients c ON c.id = i.client_id
            LEFT JOIN ecf_api_records api ON api.invoice_id = i.id
            WHERE i.id = ?
            """,
            (invoice_id,),
        )
        if not invoice:
            raise DatabaseError("Factura no encontrada.")
        invoice["items"] = self.fetch_all(
            """
            SELECT
                ii.product_id, p.sku, p.name, ii.quantity, ii.unit_price,
                COALESCE(ii.discount_amount, 0) AS discount_amount,
                ii.tax_rate, ii.line_subtotal, ii.line_tax, ii.line_total
            FROM invoice_items ii
            JOIN products p ON p.id = ii.product_id
            WHERE ii.invoice_id = ?
            ORDER BY ii.id
            """,
            (invoice_id,),
        )
        invoice["payments"] = self.fetch_all(
            """
            SELECT payment_method, amount, cash_session_id, created_at
            FROM invoice_payments WHERE invoice_id = ? ORDER BY id
            """,
            (invoice_id,),
        )
        return invoice

    def track_invoice_by_token(self, token: str) -> dict[str, Any]:
        token = str(token or "").strip()
        if len(token) < 20:
            raise DatabaseError("Token de seguimiento inválido.")
        row = self.fetch_one(
            """
            SELECT i.id, i.en_ncf, i.ecf_type, i.total, i.status, i.issued_at,
                   COALESCE(api.provider_encf, '') AS provider_encf,
                   COALESCE(api.track_id, '') AS track_id,
                   COALESCE(api.api_status, '') AS api_status,
                   COALESCE(api.last_error, '') AS api_error
            FROM invoice_tracking_tokens t
            JOIN invoices i ON i.id = t.invoice_id
            LEFT JOIN ecf_api_records api ON api.invoice_id = i.id
            WHERE t.token_hash = ?
            """,
            (token_hash(token),),
        )
        if not row:
            raise DatabaseError("Token de seguimiento no encontrado.")
        self.execute(
            "UPDATE invoice_tracking_tokens SET last_used_at = ? WHERE token_hash = ?",
            (self.now(), token_hash(token)),
        )
        self.conn.commit()
        return row

    def update_invoice_xml(self, invoice_id: int, xml_text: str) -> None:
        self.execute("UPDATE invoices SET xml_text = ? WHERE id = ?", (xml_text, invoice_id))
        self.conn.commit()

    def save_ecf_api_record(
        self,
        invoice_id: int,
        metadata: dict[str, Any] | None = None,
        request_payload: dict[str, Any] | None = None,
        response_payload: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        metadata = metadata or {}
        existing = self.fetch_one(
            "SELECT * FROM ecf_api_records WHERE invoice_id = ?",
            (invoice_id,),
        )
        if existing:
            for key in ("provider_document_id", "track_id", "encf", "api_status"):
                if not metadata.get(key):
                    metadata[key] = existing.get(key, "")
            if request_payload is None and existing.get("request_json"):
                with suppress(json.JSONDecodeError):
                    request_payload = json.loads(existing["request_json"])
        now = self.now()
        values = (
            str(metadata.get("provider_document_id", "")),
            str(metadata.get("track_id", "")),
            str(metadata.get("encf", "")),
            str(metadata.get("api_status", "")),
            json.dumps(request_payload or {}, ensure_ascii=False),
            json.dumps(response_payload or {}, ensure_ascii=False),
            error[:2000],
            now,
        )
        if existing:
            self.execute(
                """
                UPDATE ecf_api_records
                SET provider_document_id = ?, track_id = ?, encf = ?, api_status = ?,
                    request_json = ?, response_json = ?, last_error = ?, updated_at = ?
                WHERE invoice_id = ?
                """,
                (*values, invoice_id),
            )
        else:
            self.execute(
                """
                INSERT INTO ecf_api_records(
                    provider_document_id, track_id, encf, api_status,
                    request_json, response_json, last_error, updated_at,
                    invoice_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values, invoice_id, now),
            )
        status = metadata.get("api_status") or ("error_api" if error else "pendiente_api")
        self.execute("UPDATE invoices SET status = ? WHERE id = ?", (str(status), invoice_id))
        self.conn.commit()

    def update_ecf_api_response(
        self,
        invoice_id: int,
        response_payload: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        current = self.fetch_one(
            "SELECT * FROM ecf_api_records WHERE invoice_id = ?",
            (invoice_id,),
        )
        request_payload: dict[str, Any] = {}
        if current and current.get("request_json"):
            with suppress(json.JSONDecodeError):
                request_payload = json.loads(current["request_json"])
        if current:
            for key in ("provider_document_id", "track_id", "encf", "api_status"):
                if not metadata.get(key):
                    metadata[key] = current.get(key, "")
        self.save_ecf_api_record(
            invoice_id,
            metadata=metadata,
            request_payload=request_payload,
            response_payload=response_payload,
        )

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return self._clean_row(row)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cursor = self.execute(sql, params)
        return [self._clean_row(row) for row in cursor.fetchall()]

    @staticmethod
    def normalize_page(page: int | str = 1, limit: int | str = 25) -> tuple[int, int]:
        try:
            page_value = max(1, int(page))
        except (TypeError, ValueError):
            page_value = 1
        try:
            limit_value = min(100, max(1, int(limit)))
        except (TypeError, ValueError):
            limit_value = 25
        return page_value, limit_value

    @staticmethod
    def page_result(rows: list[dict[str, Any]], total: int, page: int, limit: int) -> dict[str, Any]:
        return {
            "items": rows,
            "page": page,
            "limit": limit,
            "total": total,
            "pages": max(1, (total + limit - 1) // limit),
            "has_next": page * limit < total,
            "has_previous": page > 1,
        }

    def scalar(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return next(iter(row.values()))
        return row[0]

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        return self.conn.execute(self._sql(sql), params)

    def insert_and_get_id(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Return the id produced by this insert without consulting session-wide sequence state."""
        if self.kind == "postgres":
            statement = sql.rstrip().rstrip(";")
            cursor = self.execute(f"{statement} RETURNING id", params)
            row = cursor.fetchone()
            if row is None:
                raise DatabaseError("La insercion no devolvio un identificador.")
            return int(row["id"] if isinstance(row, dict) else row[0])
        cursor = self.execute(sql, params)
        if cursor.lastrowid is None:
            raise DatabaseError("La insercion no devolvio un identificador.")
        return int(cursor.lastrowid)

    def now(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        text = str(value or "").strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc)

    def _ensure_client(self, client: dict[str, Any], ecf_type: str, total: float = 0) -> int | None:
        selected_id = int(client.get("id") or 0)
        rnc = "".join(ch for ch in str(client.get("rnc_cedula", "")).strip() if ch.isdigit())
        if selected_id:
            selected = self.get_client(selected_id)
            if ecf_type == "31" and not selected["rnc_cedula"]:
                raise DatabaseError("La factura e-CF 31 requiere RNC o cedula del cliente.")
            if ecf_type == "32" and total >= 250000 and not selected["rnc_cedula"]:
                raise DatabaseError("El e-CF 32 con monto igual o mayor a RD$250,000 requiere RNC o cedula.")
            return selected_id
        if ecf_type == "31" and not rnc:
            raise DatabaseError("La factura e-CF 31 requiere RNC o cedula del cliente.")
        if ecf_type == "32" and total >= 250000 and not rnc:
            raise DatabaseError("El e-CF 32 con monto igual o mayor a RD$250,000 requiere RNC o cedula.")
        if not rnc:
            return None
        existing = self.fetch_one("SELECT id FROM clients WHERE fiscal_id = ?", (rnc,))
        if existing:
            return int(existing["id"])
        return int(self.save_client(client)["id"])

    def _next_sequence(self, ecf_type: str) -> str:
        sql = "SELECT * FROM fiscal_sequences WHERE type_code = ? AND authorized = 1"
        if self.kind == "postgres":
            sql += " FOR UPDATE"
        sequence = self.fetch_one(sql, (ecf_type,))
        if not sequence:
            raise DatabaseError(f"No existe rango autorizado para e-CF {ecf_type}.")
        current = int(sequence["current_number"])
        end_number = int(sequence["end_number"])
        if current > end_number:
            raise DatabaseError(f"Rango agotado para e-CF {ecf_type}.")
        en_ncf = f"{sequence['prefix']}{current:010d}"
        self.execute(
            "UPDATE fiscal_sequences SET current_number = ? WHERE type_code = ?",
            (current + 1, ecf_type),
        )
        return en_ncf

    def _sqlite_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            path = urlparse(self.database_url).path
            if len(path) > 3 and path[0] == "/" and path[2] == ":":
                path = path[1:]
            return Path(path)
        return Path(self.database_url)

    def _sql(self, sql: str) -> str:
        if self.kind == "postgres":
            # Psycopg interpreta '%' como marcador de parámetros. Escapar los
            # porcentajes literales de LIKE antes de convertir los placeholders
            # estilo SQLite evita errores como "got %R" en PostgreSQL.
            return sql.replace("%", "%%").replace("?", "%s").replace("authorized = 1", "authorized = TRUE")
        return sql

    def _clean_row(self, row: Any) -> dict[str, Any]:
        data = dict(row)
        for key, value in list(data.items()):
            if isinstance(value, Decimal):
                data[key] = float(value)
            elif hasattr(value, "isoformat"):
                with suppress(Exception):
                    data[key] = value.isoformat()
        return data
