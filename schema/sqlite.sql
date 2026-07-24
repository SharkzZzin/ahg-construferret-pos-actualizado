CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name TEXT NOT NULL,
    technical_description TEXT NOT NULL,
    barcode TEXT NOT NULL DEFAULT '',
    brand TEXT NOT NULL DEFAULT '',
    unit_name TEXT NOT NULL DEFAULT 'unidad',
    location TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    cost REAL NOT NULL DEFAULT 0 CHECK(cost >= 0),
    price REAL NOT NULL CHECK(price >= 0),
    tax_rate REAL NOT NULL DEFAULT 0.18,
    stock REAL NOT NULL DEFAULT 0 CHECK(stock >= 0),
    min_stock REAL NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rnc_cedula TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    fiscal_id TEXT,
    address TEXT NOT NULL DEFAULT '',
    taxpayer_activity TEXT NOT NULL DEFAULT '',
    dgii_locked INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rnc_cedula TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    address TEXT NOT NULL,
    contact_person TEXT NOT NULL DEFAULT '',
    taxpayer_activity TEXT NOT NULL DEFAULT '',
    dgii_locked INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fiscal_sequences (
    type_code TEXT PRIMARY KEY CHECK(type_code IN ('31', '32')),
    description TEXT NOT NULL,
    prefix TEXT NOT NULL,
    current_number INTEGER NOT NULL,
    end_number INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    authorized INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    en_ncf TEXT NOT NULL UNIQUE,
    ecf_type TEXT NOT NULL CHECK(ecf_type IN ('31', '32')),
    client_id INTEGER REFERENCES clients(id),
    subtotal REAL NOT NULL,
    discount_total REAL NOT NULL DEFAULT 0,
    general_discount REAL NOT NULL DEFAULT 0,
    credit_applied REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'emitida',
    payment_method TEXT NOT NULL DEFAULT 'efectivo',
    issued_at TEXT NOT NULL,
    fiscal_environment TEXT NOT NULL DEFAULT 'academico',
    xml_text TEXT
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES products(id),
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL,
    discount_amount REAL NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL,
    line_subtotal REAL NOT NULL,
    line_tax REAL NOT NULL,
    line_total REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(id),
    movement_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    reference TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount REAL NOT NULL,
    payment_method TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preinvoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER REFERENCES clients(id),
    ecf_type TEXT NOT NULL DEFAULT '32' CHECK(ecf_type IN ('31', '32')),
    payment_method TEXT NOT NULL DEFAULT 'efectivo',
    notes TEXT NOT NULL DEFAULT '',
    subtotal REAL NOT NULL DEFAULT 0,
    discount_total REAL NOT NULL DEFAULT 0,
    general_discount REAL NOT NULL DEFAULT 0,
    tax REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'borrador',
    emitted_invoice_id INTEGER REFERENCES invoices(id),
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preinvoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preinvoice_id INTEGER NOT NULL REFERENCES preinvoices(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES products(id),
    quantity REAL NOT NULL,
    unit_price REAL NOT NULL DEFAULT 0,
    discount_amount REAL NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL DEFAULT 0.18
);

CREATE TABLE IF NOT EXISTS credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    en_ncf TEXT NOT NULL UNIQUE,
    modification_code TEXT NOT NULL CHECK(modification_code IN ('1', '2', '3')),
    reason TEXT NOT NULL,
    subtotal REAL NOT NULL,
    tax REAL NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'emitida',
    issued_at TEXT NOT NULL,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_note_id INTEGER NOT NULL REFERENCES credit_notes(id),
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    client_id INTEGER NOT NULL REFERENCES clients(id),
    amount REAL NOT NULL,
    created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO credit_note_sequences(id, current_number) VALUES (1, 1);

CREATE TABLE IF NOT EXISTS ai_search_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fiscal_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_name TEXT NOT NULL,
    issuer_name TEXT NOT NULL,
    issuer_rnc TEXT NOT NULL,
    company_id TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL,
    portal_url TEXT NOT NULL DEFAULT '',
    environment TEXT NOT NULL DEFAULT 'test',
    encrypted_api_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 0,
    validated_at TEXT,
    last_test_at TEXT,
    last_test_ok INTEGER,
    last_test_message TEXT NOT NULL DEFAULT '',
    created_by INTEGER,
    updated_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'cajero' CHECK(role IN ('admin', 'gerente', 'cajero', 'vendedor', 'almacen')),
    active INTEGER NOT NULL DEFAULT 1,
    last_login_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_token_hash ON user_sessions(token_hash);
