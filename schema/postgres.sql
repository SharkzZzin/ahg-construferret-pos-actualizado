CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(40) PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name TEXT NOT NULL,
    technical_description TEXT NOT NULL,
    barcode TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    unit_name TEXT NOT NULL DEFAULT 'unidad',
    location TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    cost NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK(cost >= 0),
    price NUMERIC(12, 2) NOT NULL CHECK(price >= 0),
    tax_rate NUMERIC(5, 4) NOT NULL DEFAULT 0.18,
    stock NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK(stock >= 0),
    min_stock NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    rnc_cedula VARCHAR(11) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    fiscal_id TEXT,
    address TEXT NOT NULL DEFAULT '',
    taxpayer_activity TEXT NOT NULL DEFAULT '',
    dgii_locked BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    rnc_cedula VARCHAR(11) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    address TEXT NOT NULL,
    contact_person TEXT NOT NULL DEFAULT '',
    taxpayer_activity TEXT NOT NULL DEFAULT '',
    dgii_locked BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fiscal_sequences (
    type_code VARCHAR(2) PRIMARY KEY CHECK(type_code IN ('31', '32')),
    description TEXT NOT NULL,
    prefix VARCHAR(3) NOT NULL,
    current_number BIGINT NOT NULL,
    end_number BIGINT NOT NULL,
    expires_at DATE NOT NULL,
    authorized BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    en_ncf VARCHAR(13) NOT NULL UNIQUE,
    ecf_type VARCHAR(2) NOT NULL CHECK(ecf_type IN ('31', '32')),
    client_id INTEGER REFERENCES clients(id),
    subtotal NUMERIC(12, 2) NOT NULL,
    discount_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    general_discount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    credit_applied NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(12, 2) NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'emitida',
    payment_method TEXT NOT NULL DEFAULT 'efectivo',
    issued_at TIMESTAMPTZ NOT NULL,
    due_date TEXT NOT NULL DEFAULT '',
    approved_by INTEGER,
    fiscal_environment TEXT NOT NULL DEFAULT 'academico',
    xml_text TEXT
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id VARCHAR(40) NOT NULL REFERENCES products(id),
    quantity NUMERIC(12, 2) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    unit_cost NUMERIC(12, 2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax_rate NUMERIC(5, 4) NOT NULL,
    line_subtotal NUMERIC(12, 2) NOT NULL,
    line_tax NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(12, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(40) NOT NULL REFERENCES products(id),
    movement_type TEXT NOT NULL,
    quantity NUMERIC(12, 2) NOT NULL,
    reference TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_transactions (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount NUMERIC(12, 2) NOT NULL,
    payment_method TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS cash_sessions (
    id SERIAL PRIMARY KEY,
    opened_by INTEGER,
    opened_at TIMESTAMPTZ NOT NULL,
    opening_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'abierta' CHECK(status IN ('abierta', 'cerrada')),
    closed_by INTEGER,
    closed_at TIMESTAMPTZ,
    expected_cash NUMERIC(12, 2),
    counted_cash NUMERIC(12, 2),
    difference NUMERIC(12, 2),
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cash_movements (
    id SERIAL PRIMARY KEY,
    cash_session_id INTEGER NOT NULL REFERENCES cash_sessions(id) ON DELETE CASCADE,
    movement_type TEXT NOT NULL CHECK(movement_type IN ('entrada', 'salida')),
    amount NUMERIC(12, 2) NOT NULL,
    description TEXT NOT NULL,
    created_by INTEGER,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_payments (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    cash_session_id INTEGER REFERENCES cash_sessions(id),
    payment_method TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS preinvoices (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    ecf_type VARCHAR(2) NOT NULL DEFAULT '32' CHECK(ecf_type IN ('31', '32')),
    payment_method TEXT NOT NULL DEFAULT 'efectivo',
    notes TEXT NOT NULL DEFAULT '',
    subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
    discount_total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    general_discount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'borrador',
    emitted_invoice_id INTEGER REFERENCES invoices(id),
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preinvoice_items (
    id SERIAL PRIMARY KEY,
    preinvoice_id INTEGER NOT NULL REFERENCES preinvoices(id) ON DELETE CASCADE,
    product_id VARCHAR(40) NOT NULL REFERENCES products(id),
    quantity NUMERIC(12, 3) NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax_rate NUMERIC(5, 4) NOT NULL DEFAULT 0.18
);

CREATE TABLE IF NOT EXISTS credit_notes (
    id SERIAL PRIMARY KEY,
    source_invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    en_ncf TEXT NOT NULL UNIQUE,
    modification_code VARCHAR(1) NOT NULL CHECK(modification_code IN ('1', '2', '3')),
    reason TEXT NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    tax NUMERIC(12, 2) NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'emitida',
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL DEFAULT '',
    fiscal_environment TEXT NOT NULL,
    provider_document_id TEXT NOT NULL DEFAULT '',
    track_id TEXT NOT NULL DEFAULT '',
    provider_encf TEXT NOT NULL DEFAULT '',
    api_status TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL DEFAULT '',
    response_json TEXT NOT NULL DEFAULT '',
    api_error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS credit_note_sequences (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    current_number INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS credit_applications (
    id SERIAL PRIMARY KEY,
    credit_note_id INTEGER NOT NULL REFERENCES credit_notes(id),
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    client_id INTEGER NOT NULL REFERENCES clients(id),
    amount NUMERIC(12, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

INSERT INTO credit_note_sequences(id, current_number)
VALUES (1, 1)
ON CONFLICT(id) DO NOTHING;

CREATE TABLE IF NOT EXISTS ai_search_logs (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS ecf_api_records (
    invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id) ON DELETE CASCADE,
    provider_document_id TEXT NOT NULL DEFAULT '',
    track_id TEXT NOT NULL DEFAULT '',
    encf TEXT NOT NULL DEFAULT '',
    api_status TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL DEFAULT '',
    response_json TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS fiscal_companies (
    id SERIAL PRIMARY KEY,
    workspace_name TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    issuer_rnc TEXT NOT NULL,
    company_id TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL,
    portal_url TEXT NOT NULL DEFAULT '',
    environment TEXT NOT NULL DEFAULT 'test',
    encrypted_api_key TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    validated_at TEXT,
    last_test_at TEXT,
    last_test_ok BOOLEAN,
    last_test_message TEXT NOT NULL DEFAULT '',
    created_by INTEGER,
    updated_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'cajero' CHECK(role IN ('admin', 'gerente', 'cajero', 'vendedor', 'almacen')),
    module_permissions_json TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    order_number TEXT NOT NULL UNIQUE,
    supplier_invoice_number TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'borrador' CHECK(status IN ('borrador', 'recibida', 'pagada', 'cancelada')),
    subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    amount_paid NUMERIC(12, 2) NOT NULL DEFAULT 0,
    balance_due NUMERIC(12, 2) NOT NULL DEFAULT 0,
    ordered_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ,
    created_by INTEGER REFERENCES users(id),
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    id SERIAL PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id VARCHAR(40) NOT NULL REFERENCES products(id),
    quantity NUMERIC(12, 3) NOT NULL CHECK(quantity > 0),
    unit_cost NUMERIC(12, 2) NOT NULL CHECK(unit_cost >= 0),
    tax_rate NUMERIC(5, 4) NOT NULL DEFAULT 0.18,
    line_subtotal NUMERIC(12, 2) NOT NULL,
    line_tax NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(12, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_payments (
    id SERIAL PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    cash_session_id INTEGER REFERENCES cash_sessions(id),
    amount NUMERIC(12, 2) NOT NULL CHECK(amount > 0),
    payment_method TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_receivables (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL UNIQUE REFERENCES invoices(id) ON DELETE CASCADE,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    original_amount NUMERIC(12, 2) NOT NULL,
    balance NUMERIC(12, 2) NOT NULL,
    due_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendiente' CHECK(status IN ('pendiente', 'parcial', 'pagada', 'vencida')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_payments (
    id SERIAL PRIMARY KEY,
    receivable_id INTEGER NOT NULL REFERENCES customer_receivables(id) ON DELETE CASCADE,
    cash_session_id INTEGER REFERENCES cash_sessions(id),
    amount NUMERIC(12, 2) NOT NULL CHECK(amount > 0),
    payment_method TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_note_items (
    id SERIAL PRIMARY KEY,
    credit_note_id INTEGER NOT NULL REFERENCES credit_notes(id) ON DELETE CASCADE,
    product_id VARCHAR(40) NOT NULL REFERENCES products(id),
    quantity NUMERIC(12, 3) NOT NULL CHECK(quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax_rate NUMERIC(5, 4) NOT NULL,
    line_subtotal NUMERIC(12, 2) NOT NULL,
    line_tax NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(12, 2) NOT NULL,
    restocked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS public_rate_limits (
    key_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(key_hash, action)
);

CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier ON purchase_orders(supplier_id, ordered_at);
CREATE INDEX IF NOT EXISTS idx_supplier_payments_order ON supplier_payments(purchase_order_id);
CREATE INDEX IF NOT EXISTS idx_receivables_client_status ON customer_receivables(client_id, status, due_date);
CREATE INDEX IF NOT EXISTS idx_customer_payments_receivable ON customer_payments(receivable_id);
CREATE INDEX IF NOT EXISTS idx_credit_note_items_note ON credit_note_items(credit_note_id);
