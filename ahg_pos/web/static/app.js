const state = {
  products: [],
  categories: [],
  clients: [],
  suppliers: [],
  preinvoices: [],
  invoices: [],
  creditNotes: [],
  imecfDiagnostics: {},
  currentPreinvoiceId: null,
  cart: [],
  ecfType: "32",
  imecfActive: false,
  imecfConfigured: false,
  academicMode: true,
  fiscalDocuments: [],
  remoteFiscalDocuments: [],
  fiscalCompanies: [],
  fiscalFilter: "ALL",
  userRole: "",
  userModules: [],
  paypal: null,
  paypalPayment: null,
  paypalSdkPromise: null,
  availableCredit: 0,
  availableCreditNotes: [],
  cashSession: null,
  cashHistory: [],
  fiscalIssuer: {},
  productPagination: null,
  masterProductPagination: null,
  preinvoicePagination: null,
  invoicePagination: null,
  clientPagination: null,
  supplierPagination: null,
  webRequests: [],
  auditPagination: null,
  dashboard: null,
  managementReport: null,
  userName: "",
  purchaseDraft: [],
  purchases: [],
  receivables: [],
  creditSourceItems: [],
  returnSourceItems: [],
};

const MODULE_DEFINITIONS = [
  ["sale", "Venta"],
  ["products", "Maestro de artículos"],
  ["clients", "Clientes"],
  ["suppliers", "Proveedores"],
  ["purchases", "Compras"],
  ["receivables", "Cuentas por cobrar"],
  ["returns", "Devoluciones"],
  ["preinvoices", "Pre-Facturas"],
  ["assistant", "Asistente IA"],
  ["inventory", "Inventario"],
  ["fiscal", "Gestión Fiscal"],
  ["reports", "Facturas"],
  ["cash", "Cuadre de caja"],
  ["audit", "Auditoría"],
  ["admin", "Administración"],
];

const ROLE_DEFAULT_MODULES = {
  admin: MODULE_DEFINITIONS.map(([module]) => module),
  gerente: MODULE_DEFINITIONS.map(([module]) => module).filter((module) => module !== "admin"),
  cajero: ["sale", "clients", "preinvoices", "returns", "receivables", "reports", "cash"],
  vendedor: ["sale", "clients", "preinvoices", "assistant", "returns", "receivables", "reports"],
  almacen: ["products", "suppliers", "purchases", "inventory"],
};

const moduleLabel = (module) => module === "dashboard" ? "Inicio" : MODULE_DEFINITIONS.find(([key]) => key === module)?.[1] || module;
const hasModule = (module) => module === "dashboard" || state.userModules.includes(module);

const money = new Intl.NumberFormat("es-DO", {
  style: "currency",
  currency: "DOP",
  minimumFractionDigits: 2,
});

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const setLoading = (visible) => $("#loading-screen")?.classList.toggle("is-hidden", !visible);

document.addEventListener("DOMContentLoaded", async () => {
  enhanceUi();
  bindTabs();
  bindDashboard();
  bindSale();
  bindProductMaster();
  bindClients();
  bindSuppliers();
  bindPurchases();
  bindReceivables();
  bindReturns();
  bindPreinvoices();
  bindAssistant();
  bindWebRequests();
  bindInventory();
  bindFiscal();
  bindReports();
  bindCash();
  bindAudit();
  bindAdmin();
  bindDialog();
  try {
    await boot();
  } finally {
    setLoading(false);
  }
});

async function boot() {
  const health = await api("/api/health");
  $("#db-status").textContent = `BD ${health.database}`;
  $("#user-status").textContent = `${health.user.name} · ${health.user.role}`;
  state.userRole = health.user.role;
  state.userName = health.user.name || "Usuario";
  state.userModules = Array.isArray(health.user.modules) ? health.user.modules : [];
  state.paypal = health.paypal || { configured: false };
  state.fiscalIssuer = health.fiscal_issuer || {};
  state.academicMode = Boolean(health.academic_mode);
  $("#issuer-label").textContent = `IMECF: ${health.fiscal_issuer.workspace_name} · Emisor certificado: ${health.fiscal_issuer.name} · RNC ${health.fiscal_issuer.rnc}`;
  state.imecfActive = Boolean(health.imecf_active);
  state.imecfConfigured = Boolean(health.imecf_configured);
  renderFiscalMode(health);
  applyModuleAccess();
  await setView("dashboard", true);
}

function renderFiscalMode(health) {
  const status = $("#fiscal-status");
  if (health.imecf_active) {
    status.textContent = "IMECF Test conectado";
    status.className = "status-pill";
    return;
  }
  status.textContent = health.imecf_configured ? "IMECF desactivado" : "IMECF sin configurar";
  status.className = "status-pill warning";
}

function bindTabs() {
  $$(".tab").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
}

function applyModuleAccess() {
  $$(".tab[data-view]").forEach((button) => { button.hidden = !hasModule(button.dataset.view); });
  $$(".view[id]").forEach((section) => {
    const authorized = hasModule(section.id);
    section.setAttribute("aria-hidden", String(!authorized));
    if (!authorized) section.classList.remove("active");
  });
  const firstModule = "dashboard";
  if (!firstModule) toast("Tu usuario no tiene módulos asignados. Solicita acceso al administrador.", true);
  return firstModule;
}

async function refreshViewData(view) {
  if (view === "dashboard") await refreshDashboard();
  if (view === "sale") {
    await refreshProducts();
    await refreshClients();
    await refreshPreinvoices();
    await refreshWebRequests();
  }
  if (view === "fiscal") await refreshFiscal();
  if (view === "products") await refreshProductMaster();
  if (view === "clients") await refreshClients();
  if (view === "suppliers") await refreshSuppliers();
  if (view === "purchases") await refreshPurchases();
  if (view === "receivables") await refreshReceivables();
  if (view === "returns") await refreshReturns();
  if (view === "preinvoices") await refreshPreinvoices();
  if (view === "inventory") await refreshProducts();
  if (view === "reports") await refreshReports();
  if (view === "audit") await refreshAudit();
  if (view === "cash") await refreshCash();
  if (view === "admin") await refreshAdmin();
}

async function setView(view, refresh = true) {
  if (!hasModule(view)) {
    const fallback = "dashboard";
    if (!fallback) return;
    view = fallback;
  }
  $$(".tab").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $$(".tab").forEach((button) => button.setAttribute("aria-selected", String(button.dataset.view === view)));
  $$(".view").forEach((section) => {
    const active = section.id === view;
    section.classList.toggle("active", active);
    if (active) {
      section.classList.remove("view-enter");
      requestAnimationFrame(() => section.classList.add("view-enter"));
    }
  });
  document.body.dataset.view = view;
  if (refresh) await refreshViewData(view);
}

function bindDashboard() {
  $("#dashboard")?.addEventListener("click", (event) => {
    const target = event.target.closest?.("[data-dashboard-view]");
    if (!target) return;
    setView(target.dataset.dashboardView);
  });
}

async function refreshDashboard() {
  const payload = await api("/api/dashboard");
  state.dashboard = payload;
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? "Buenos días" : hour < 18 ? "Buenas tardes" : "Buenas noches";
  $("#dashboard-greeting").textContent = `${greeting}, ${state.userName.split(" ")[0]}`;
  $("#dashboard-date").textContent = new Intl.DateTimeFormat("es-DO", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(now);

  const sales = payload.sales || {};
  const pending = payload.pending || {};
  const inventory = payload.inventory || {};
  const cash = payload.cash || {};
  const pendingTotal = Number(pending.preinvoices || 0) + Number(pending.customer_requests || 0);
  const cashValue = cash.status === "abierta" ? money.format(cash.expected_cash || cash.opening_amount || 0) : "Sin turno";
  $("#dashboard-kpis").innerHTML = [
    ["Ventas de hoy", money.format(sales.total || 0), `${sales.invoice_count || 0} comprobante(s)`, "sale", "teal"],
    ["Pendientes", String(pendingTotal), `${pending.preinvoices || 0} pre-facturas · ${pending.customer_requests || 0} portal`, "preinvoices", "amber"],
    ["Stock crítico", String(inventory.low_stock || 0), `${inventory.active_products || 0} artículos activos`, "inventory", Number(inventory.low_stock || 0) ? "red" : "green"],
    ["Caja", cashValue, cash.status === "abierta" ? "Turno abierto" : "Abre un turno para operar", "cash", cash.status === "abierta" ? "green" : "neutral"],
  ].filter(([, , , view]) => hasModule(view)).map(([label, value, detail, view, tone]) => `
    <button class="dashboard-kpi ${tone}" type="button" data-dashboard-view="${view}">
      <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small><i aria-hidden="true">→</i>
    </button>`).join("");

  renderDashboardChart(payload.trend || []);
  renderDashboardStatus(payload);
  renderDashboardRecent(payload.recent_invoices || []);
  renderDashboardTopProducts(payload.top_products || []);
  renderDashboardQuickActions();
  $$("#dashboard [data-dashboard-view]").forEach((button) => { button.hidden = !hasModule(button.dataset.dashboardView); });
}

function renderDashboardChart(rows) {
  const maximum = Math.max(1, ...rows.map((row) => Number(row.total || 0)));
  const weekTotal = rows.reduce((sum, row) => sum + Number(row.total || 0), 0);
  $("#dashboard-week-total").textContent = money.format(weekTotal);
  $("#dashboard-chart").innerHTML = rows.map((row) => {
    const day = new Date(`${row.date}T12:00:00`);
    const height = Math.max(Number(row.total || 0) > 0 ? 10 : 3, Math.round(Number(row.total || 0) / maximum * 100));
    return `<div class="dashboard-bar-column" title="${escapeHtml(row.date)} · ${money.format(row.total || 0)}">
      <span>${row.invoice_count || 0}</span><div class="dashboard-bar-track"><i style="height:${height}%"></i></div><strong>${escapeHtml(new Intl.DateTimeFormat("es-DO", { weekday: "short" }).format(day).replace(".", ""))}</strong>
    </div>`;
  }).join("");
}

function renderDashboardStatus(payload) {
  const fiscal = payload.fiscal || {};
  const credits = payload.credits || {};
  const sales = payload.sales || {};
  const pending = payload.pending || {};
  const rows = [
    ["ITBIS facturado", money.format(sales.tax || 0), "reports", "normal"],
    ["Descuentos aplicados", money.format(sales.discounts || 0), "reports", "normal"],
    ["Crédito aplicado", money.format(sales.credit_applied || 0), "sale", "normal"],
    ["Notas vigentes", `${credits.count || 0} · ${money.format(credits.available_total || 0)}`, "sale", Number(credits.count || 0) ? "attention" : "normal"],
    ["Cuentas por cobrar", money.format(pending.receivables_due || 0), "receivables", Number(pending.receivables_due || 0) ? "attention" : "normal"],
    ["Cuentas por pagar", money.format(pending.payables_due || 0), "purchases", Number(pending.payables_due || 0) ? "attention" : "normal"],
    ["e-CF aceptados hoy", String(fiscal.accepted_today || 0), "fiscal", "success"],
    ["e-CF por revisar", String(fiscal.attention_today || 0), "fiscal", Number(fiscal.attention_today || 0) ? "danger" : "success"],
  ];
  $("#dashboard-status").innerHTML = rows.filter(([, , view]) => hasModule(view)).map(([label, value, view, tone]) => `<button type="button" data-dashboard-view="${view}"><span><i class="status-dot ${tone}"></i>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></button>`).join("");
}

function renderDashboardRecent(invoices) {
  const container = $("#dashboard-recent");
  container.innerHTML = invoices.map((invoice) => `<button type="button" data-dashboard-view="reports"><span><strong>${escapeHtml(invoice.provider_encf || invoice.en_ncf)}</strong><small>${escapeHtml(invoice.client_name || "Consumidor Final")} · ${escapeHtml(formatDate(invoice.issued_at))}</small></span><span class="dashboard-amount">${money.format(invoice.total || 0)}<small>${escapeHtml(invoice.api_status || invoice.status || "Local")}</small></span></button>`).join("") || `<div class="empty-state">Todavía no hay comprobantes para mostrar.</div>`;
}

function renderDashboardTopProducts(products) {
  $("#dashboard-top-products").innerHTML = products.map((product, index) => `<article><span class="dashboard-rank">${index + 1}</span><div><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.sku)} · ${Number(product.quantity || 0)} unidad(es)</small></div><b>${money.format(product.total || 0)}</b></article>`).join("") || `<div class="empty-state">Las ventas de hoy aparecerán aquí.</div>`;
}

function renderDashboardQuickActions() {
  const actions = [
    ["sale", "Nueva venta", "Crear una pre-factura o comprobante"],
    ["preinvoices", "Pre-facturas", "Revisar solicitudes pendientes"],
    ["inventory", "Inventario", "Consultar existencias y alertas"],
    ["purchases", "Compras", "Recibir mercancía y pagar proveedores"],
    ["receivables", "Cuentas por cobrar", "Registrar cobros de ventas a crédito"],
    ["cash", "Cuadre de caja", "Abrir, revisar o cerrar el turno"],
    ["fiscal", "Gestión fiscal", "Consultar estados y documentos"],
    ["admin", "Usuarios", "Administrar accesos por módulo"],
  ];
  $("#dashboard-quick-actions").innerHTML = actions.filter(([view]) => hasModule(view)).map(([view, title, detail]) => `<button type="button" data-dashboard-view="${view}"><span>${escapeHtml(title.slice(0, 1))}</span><div><strong>${escapeHtml(title)}</strong><small>${escapeHtml(detail)}</small></div><i>→</i></button>`).join("");
}

function bindAdmin() {
  $("#user-form")?.addEventListener("submit", saveUser);
  $("#download-backup")?.addEventListener("click", downloadBackup);
  $("#user-role")?.addEventListener("change", () => renderUserModuleOptions(ROLE_DEFAULT_MODULES[$("#user-role").value] || []));
  renderUserModuleOptions(ROLE_DEFAULT_MODULES.cajero);
}

function renderUserModuleOptions(selected = []) {
  const container = $("#user-module-options");
  if (!container) return;
  const role = $("#user-role").value;
  const effective = role === "admin" ? MODULE_DEFINITIONS.map(([module]) => module) : selected;
  container.innerHTML = MODULE_DEFINITIONS.map(([module, label]) => `<label class="module-option"><input type="checkbox" value="${module}" ${effective.includes(module) ? "checked" : ""} ${role === "admin" ? "disabled" : ""} /><span>${escapeHtml(label)}</span></label>`).join("");
}

function selectedUserModules() {
  return $$("#user-module-options input:checked").map((input) => input.value);
}

function resetUserForm() {
  $("#user-form").reset();
  $("#user-form-id").value = "";
  $("#user-form-title").textContent = "Nuevo usuario";
  $("#user-password").placeholder = "Mínimo 8 caracteres";
  renderUserModuleOptions(ROLE_DEFAULT_MODULES.cajero);
}

async function refreshAdmin() {
  if (!$("#user-list")) return;
  try {
    const payload = await api("/api/users");
    $("#user-list").innerHTML = (payload.users || []).map((user) => `<article class="client-card"><div><strong>${escapeHtml(user.name)}</strong><span>${escapeHtml(user.email)} · ${escapeHtml(user.role)} · ${user.active ? "Activo" : "Inactivo"}</span><span>Último acceso: ${escapeHtml(user.last_login_at ? formatDate(user.last_login_at) : "Nunca")}</span><div class="user-module-summary">${(user.modules || []).map((module) => `<span>${escapeHtml(moduleLabel(module))}</span>`).join("") || "<em>Sin módulos asignados</em>"}</div></div><div class="company-actions"><button class="table-button" type="button" data-edit-user="${user.id}">Editar accesos</button></div></article>`).join("") || `<div class="empty-state">No hay usuarios registrados.</div>`;
    $("#user-list").querySelectorAll("[data-edit-user]").forEach((button) => button.addEventListener("click", () => editUser((payload.users || []).find((user) => String(user.id) === String(button.dataset.editUser)))));
  } catch (exception) { toast(exception.message, true); }
}

function editUser(user) {
  if (!user) return;
  $("#user-form-id").value = user.id; $("#user-name").value = user.name || ""; $("#user-email").value = user.email || ""; $("#user-phone").value = user.phone || ""; $("#user-role").value = user.role || "cajero"; $("#user-active").checked = Boolean(user.active); $("#user-password").value = ""; $("#user-form-title").textContent = "Editar usuario"; $("#user-password").placeholder = "Vacío para conservar la actual";
  renderUserModuleOptions(user.modules || ROLE_DEFAULT_MODULES[user.role] || []);
}

async function saveUser(event) {
  event.preventDefault();
  const id = $("#user-form-id").value, error = $("#user-form-error"), button = $("#save-user");
  error.hidden = true; button.disabled = true;
  try {
    const payload = { name: $("#user-name").value.trim(), email: $("#user-email").value.trim(), phone: $("#user-phone").value.trim(), role: $("#user-role").value, password: $("#user-password").value, active: $("#user-active").checked, modules: selectedUserModules() };
    await api(id ? `/api/users/${id}` : "/api/users", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    resetUserForm(); await refreshAdmin(); toast(id ? "Usuario actualizado." : "Usuario creado.");
  } catch (exception) { error.textContent = exception.message; error.hidden = false; } finally { button.disabled = false; }
}

async function downloadBackup() {
  const status = $("#backup-status"), button = $("#download-backup"); button.disabled = true; status.hidden = true;
  try { const currentPassword = window.prompt("Confirma tu contraseña de administrador para generar el respaldo:"); if (!currentPassword) throw new Error("Respaldo cancelado."); const response = await fetch("/api/admin/backup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ current_password: currentPassword }) }); if (!response.ok) throw new Error((await response.json()).error || "No se pudo generar el backup."); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `ahg-pos-backup-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(url); status.textContent = "Backup sanitizado descargado correctamente."; status.className = "client-validation ok"; status.hidden = false; } catch (exception) { status.textContent = exception.message; status.className = "client-validation error"; status.hidden = false; } finally { button.disabled = false; }
}

function bindAudit() {
  $("#refresh-audit")?.addEventListener("click", () => refreshAudit(1));
  let timer;
  $("#audit-search")?.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => refreshAudit(1), 250); });
}

async function refreshAudit(page = 1) {
  if (!$("#audit-table")) return;
  const query = $("#audit-search").value.trim();
  const payload = await api(`/api/audit?page=${page}&limit=50&q=${encodeURIComponent(query)}`);
  const result = payload.logs || {};
  state.auditPagination = result;
  const logs = result.items || [];
  $("#audit-summary").innerHTML = `<span class="summary-chip">${result.total || 0} acciones de usuarios</span><span class="summary-chip">Página ${result.page || 1} de ${result.pages || 1}</span>`;
  $("#audit-table").innerHTML = logs.map((log) => {
    const details = Object.entries(log.details || {}).map(([key, value]) => `${key}: ${value}`).join(" · ");
    return `<tr><td>${escapeHtml(formatDate(log.created_at))}</td><td>${escapeHtml(log.user_name || "Sistema")}</td><td><strong>${escapeHtml(log.action)}</strong></td><td>${escapeHtml(log.entity_type || "")}</td><td>${escapeHtml(log.entity_id || "—")}</td><td>${escapeHtml(details || "—")}</td></tr>`;
  }).join("") || `<tr><td colspan="6">No hay eventos para este filtro.</td></tr>`;
  renderPager("audit-table", result, (nextPage) => refreshAudit(nextPage));
}

function enhanceUi() {
  document.body.dataset.view = "dashboard";
  $$(".tab").forEach((button) => button.setAttribute("aria-selected", String(button.classList.contains("active"))));
  createCommandPalette();

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const editing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      toggleCommandPalette(true);
      return;
    }
    if (event.key === "Escape") {
      toggleCommandPalette(false);
      return;
    }
    if (event.key === "/" && !editing) {
      event.preventDefault();
      const search = document.body.dataset.view === "products" ? $("#master-search") : $("#product-search");
      search?.focus();
    }
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("button");
    if (!button || button.disabled) return;
    button.classList.remove("click-pulse");
    requestAnimationFrame(() => button.classList.add("click-pulse"));
  });
}

function createCommandPalette() {
  if ($("#command-palette")) return;
  const palette = document.createElement("div");
  palette.id = "command-palette";
  palette.className = "command-palette";
  palette.hidden = true;
  palette.innerHTML = `
    <div class="command-backdrop" data-command-close></div>
    <section class="command-dialog" role="dialog" aria-modal="true" aria-labelledby="command-title">
      <div class="command-head"><div><span class="eyebrow">Acciones rápidas</span><h2 id="command-title">¿Qué deseas hacer?</h2></div><kbd>ESC</kbd></div>
      <div class="command-search-wrap"><span>⌘</span><input id="command-search" type="search" placeholder="Buscar módulo o acción..." autocomplete="off" /></div>
      <div id="command-list" class="command-list"></div>
    </section>`;
  document.body.appendChild(palette);
  const actions = [
    ["Ir al inicio", "Abrir el resumen operativo", "dashboard", "Inicio"],
    ["Nueva venta", "Abrir el mostrador", "sale", "Venta"],
    ["Buscar productos", "Ir al maestro de artículos", "products", "Maestro de artículos"],
    ["Consultar IA", "Buscar una recomendación técnica", "assistant", "Asistente IA"],
    ["Revisar pre-facturas", "Gestionar ventas pendientes", "preinvoices", "Pre-Facturas"],
    ["Consultar inventario", "Actualizar existencias", "inventory", "Inventario"],
    ["Gestión fiscal", "Revisar IMECF y documentos", "fiscal", "Gestión Fiscal"],
  ];
  const render = (term = "") => {
    const needle = normalize(term);
    $("#command-list").innerHTML = actions
      .filter((item) => hasModule(item[2]) && normalize(item.join(" ")).includes(needle))
      .map(([title, description, view, label]) => `<button class="command-item" type="button" data-command-view="${view}"><span class="command-icon">${label.slice(0, 1)}</span><span><strong>${title}</strong><small>${description}</small></span><kbd>↵</kbd></button>`)
      .join("") || `<p class="command-empty">No encontramos esa acción.</p>`;
    $$("[data-command-view]").forEach((button) => button.addEventListener("click", () => { setView(button.dataset.commandView); toggleCommandPalette(false); }));
  };
  render();
  $("#command-search").addEventListener("input", (event) => render(event.target.value));
  palette.addEventListener("click", (event) => { if (event.target.closest("[data-command-close]")) toggleCommandPalette(false); });
}

function toggleCommandPalette(open) {
  const palette = $("#command-palette");
  if (!palette) return;
  palette.hidden = !open;
  if (open) { $("#command-search").value = ""; $("#command-search").dispatchEvent(new Event("input")); $("#command-search").focus(); }
}

function bindWebRequests() {
  $("#refresh-web-requests").addEventListener("click", refreshWebRequests);
  $("#close-web-request-preview").addEventListener("click", () => $("#web-request-preview-dialog").close());
  $("#close-web-request-preview-footer").addEventListener("click", () => $("#web-request-preview-dialog").close());
}

async function refreshWebRequests() {
  const payload = await api("/api/public/quote-requests");
  state.webRequests = payload.requests || [];
  $("#web-request-list").innerHTML = state.webRequests.map((request) => `
    <article class="preinvoice-card">
      <div><div class="document-title"><strong>Solicitud #${request.id} · ${escapeHtml(request.customer_name)}</strong><span class="badge warning">${escapeHtml(request.status)}</span></div>
      <p>${escapeHtml(request.phone)} ${request.email ? `· ${escapeHtml(request.email)}` : ""}</p><p><strong>Motivo:</strong> ${escapeHtml(request.problem||"No indicado")}</p>
      <span>${request.items.length} artículos · ${formatDate(request.created_at)}</span></div>
      <div class="web-request-summary"><strong class="web-request-total">${money.format(request.total)}</strong></div>
    </article>`).join("") || `<div class="empty-state">No hay solicitudes del catálogo.</div>`;
  decorateWebRequests();
}

function decorateWebRequests() {
  $("#web-request-list").querySelectorAll(".preinvoice-card").forEach((card, index) => {
    const request = state.webRequests[index];
    if (!request || card.querySelector("[data-web-request-actions]")) return;
    const actions = document.createElement("div");
    actions.dataset.webRequestActions = request.id;
    actions.className = "web-request-actions";
    const previewButton = document.createElement("button");
    previewButton.className = "request-action-button preview";
    previewButton.type = "button";
    previewButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg><span>Vista previa</span>';
    previewButton.dataset.previewWebRequest = request.id;
    previewButton.addEventListener("click", () => showWebRequestPreview(request.id));
    const loadButton = document.createElement("button");
    loadButton.className = "request-action-button load";
    loadButton.type = "button";
    loadButton.textContent = "Cargar en ventas";
    loadButton.dataset.loadWebRequest = request.id;
    loadButton.addEventListener("click", () => loadWebRequest(request.id));
    const deleteButton = document.createElement("button");
    deleteButton.className = "request-action-button delete";
    deleteButton.type = "button";
    deleteButton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5"/></svg><span>Eliminar</span>';
    deleteButton.dataset.deleteWebRequest = request.id;
    deleteButton.addEventListener("click", () => deleteWebRequest(request.id));
    actions.append(previewButton, loadButton, deleteButton);
    card.lastElementChild?.appendChild(actions);
  });
}

function showWebRequestPreview(requestId) {
  const request = state.webRequests.find((item) => Number(item.id) === Number(requestId));
  if (!request) return;
  $("#web-request-preview-title").textContent = `Prefactura #${request.id}`;
  $("#web-request-preview").innerHTML = `
    <section class="request-preview-customer">
      <div><span>Cliente</span><strong>${escapeHtml(request.customer_name)}</strong></div>
      <div><span>Teléfono</span><strong>${escapeHtml(request.phone || "No indicado")}</strong></div>
      <div><span>Correo</span><strong>${escapeHtml(request.email || "No indicado")}</strong></div>
      <div><span>Comprobante</span><strong>e-CF ${escapeHtml(request.ecf_type || "32")}</strong></div>
    </section>
    <section class="request-preview-note"><span>Motivo o comentario</span><p>${escapeHtml(request.problem || "No indicado")}</p></section>
    <div class="request-preview-table-wrap"><table class="request-preview-table">
      <thead><tr><th>Producto</th><th>Cantidad</th><th>Precio</th><th>Importe</th></tr></thead>
      <tbody>${(request.items || []).map((item) => {
        const quantity = Number(item.quantity || 0);
        const unitPrice = Number(item.unit_price || 0);
        const amount = Number(item.line_subtotal || quantity * unitPrice);
        return `<tr><td><strong>${escapeHtml(item.name || "Producto")}</strong><small>${escapeHtml(item.sku || "")}</small></td><td>${quantity}</td><td>${money.format(unitPrice)}</td><td>${money.format(amount)}</td></tr>`;
      }).join("")}</tbody>
    </table></div>
    <section class="request-preview-totals">
      <div><span>Subtotal</span><strong>${money.format(request.subtotal || 0)}</strong></div>
      <div><span>ITBIS</span><strong>${money.format(request.tax || 0)}</strong></div>
      <div class="total"><span>Total</span><strong>${money.format(request.total || 0)}</strong></div>
    </section>`;
  const dialog = $("#web-request-preview-dialog");
  if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "open");
}

async function deleteWebRequest(requestId) {
  const request = state.webRequests.find((item) => Number(item.id) === Number(requestId));
  if (!request || !window.confirm(`¿Eliminar la prefactura #${request.id} de ${request.customer_name}? Esta acción no se puede deshacer.`)) return;
  await api(`/api/public/quote-requests/${request.id}`, { method: "DELETE" });
  toast(`Prefactura #${request.id} eliminada.`);
  await refreshWebRequests();
}

async function loadWebRequest(requestId) {
  const request = state.webRequests.find((item) => Number(item.id) === Number(requestId));
  if (!request) return;
  const products = await api("/api/products?page=1&limit=100");
  state.cart = [];
  for (const item of request.items || []) {
    const product = (products.products || []).find((row) => String(row.id) === String(item.product_id));
    if (product) state.cart.push({ product_id: product.id, name: product.name, unit_price: Number(item.unit_price || product.price), discount_percent: 0, tax_rate: Number(product.tax_rate), stock: Number(product.stock), quantity: Number(item.quantity || 1) });
  }
  state.ecfType = String(request.ecf_type || "32");
  $("#client-rnc").value = formatFiscalId(request.rnc_cedula || "");
  $("#client-name").value = request.taxpayer_name || request.customer_name || "";
  $("#client-phone").value = request.phone || "";
  $("#client-email").value = request.email || "";
  $("#client-address").value = request.address || "";
  renderCart();
  setView("sale");
  toast(`Solicitud #${request.id} cargada en Ventas.`);
}

function bindProductMaster() {
  $("#product-form").addEventListener("submit", saveProduct);
  let searchTimer;
  $("#master-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => refreshProductMaster(1), 250);
  });
  $("#cancel-product-edit").addEventListener("click", resetProductForm);
}

async function refreshProductMaster(page = 1) {
  const query = $("#master-search").value.trim();
  const [productsPayload, categoriesPayload] = await Promise.all([
    api(`/api/products?page=${page}&limit=25&q=${encodeURIComponent(query)}`),
    api("/api/categories"),
  ]);
  state.products = productsPayload.products || [];
  state.masterProductPagination = productsPayload.pagination || null;
  state.categories = categoriesPayload.categories || [];
  $("#category-options").innerHTML = state.categories
    .map((category) => `<option value="${escapeHtml(category.name)}"></option>`)
    .join("");
  renderProductMaster();
  renderPager("product-master-table", state.masterProductPagination, (nextPage) => refreshProductMaster(nextPage));
}

function renderProductMaster() {
  const query = normalize($("#master-search").value);
  const terms = query.split(" ").filter(Boolean);
  const rows = state.products.filter((product) => {
    const haystack = normalize(`${product.id} ${product.sku} ${product.barcode || ""} ${product.name} ${product.category} ${product.technical_description} ${product.tags}`);
    return terms.every((term) => haystack.includes(term));
  });
  const activeCount = state.products.filter((product) => Boolean(product.active)).length;
  const lowCount = state.products.filter((product) => Number(product.stock) <= Number(product.min_stock)).length;
  $("#product-master-summary").innerHTML = `
    <span><strong>${state.products.length}</strong> registrados</span>
    <span><strong>${activeCount}</strong> activos</span>
    <span><strong>${lowCount}</strong> con stock bajo</span>
  `;
  $("#product-master-table").innerHTML = rows.map((product) => `
    <tr>
      <td><strong>${escapeHtml(product.name)}</strong><span class="table-subtitle">${escapeHtml(product.sku)}${product.brand ? ` · ${escapeHtml(product.brand)}` : ""}${product.barcode ? ` · ${escapeHtml(product.barcode)}` : ""}${product.location ? ` · Ubicación ${escapeHtml(product.location)}` : ""}</span></td>
      <td>${escapeHtml(product.category)}</td>
      <td>${money.format(product.cost || 0)}</td>
      <td>${money.format(product.price)}<span class="table-subtitle">Margen ${Number(product.price) > 0 ? Math.round(((Number(product.price) - Number(product.cost || 0)) / Number(product.price)) * 100) : 0}%</span></td>
      <td><span class="badge ${Number(product.stock) <= Number(product.min_stock) ? "low" : "ok"}">${formatQty(product.stock)}</span></td>
      <td><span class="badge ${product.active ? "ok" : ""}">${product.active ? "Activo" : "Inactivo"}</span></td>
      <td><button class="table-button" data-edit-product="${escapeHtml(product.id)}">Editar</button></td>
    </tr>
  `).join("") || `<tr><td colspan="7" class="muted-text">No hay artículos que coincidan.</td></tr>`;
  $("#product-master-table").querySelectorAll("[data-edit-product]").forEach((button) => {
    button.addEventListener("click", () => editProduct(button.dataset.editProduct));
  });
}

function editProduct(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;
  $("#master-product-id").value = product.id;
  $("#master-id").value = product.id;
  $("#master-id").disabled = true;
  $("#master-name").value = product.name;
  $("#master-sku").value = product.sku;
  $("#master-barcode").value = product.barcode || "";
  $("#master-brand").value = product.brand || "";
  $("#master-unit").value = product.unit_name || "unidad";
  $("#master-location").value = product.location || "";
  $("#master-supplier").value = product.supplier || "";
  $("#master-category").value = product.category;
  $("#master-cost").value = Number(product.cost || 0);
  $("#master-price").value = Number(product.price);
  $("#master-tax").value = Number(product.tax_rate) * 100;
  $("#master-stock").value = Number(product.stock);
  $("#master-min-stock").value = Number(product.min_stock);
  $("#master-description").value = product.technical_description || "";
  $("#master-tags").value = product.tags || "";
  $("#master-active").checked = Boolean(product.active);
  $("#product-form-title").textContent = "Editar artículo";
  $("#save-product").textContent = "Guardar cambios";
  $("#cancel-product-edit").hidden = false;
  $(".product-form-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetProductForm() {
  $("#product-form").reset();
  $("#master-product-id").value = "";
  $("#master-id").disabled = false;
  $("#master-cost").value = "0";
  $("#master-unit").value = "unidad";
  $("#master-tax").value = "18";
  $("#master-stock").value = "0";
  $("#master-min-stock").value = "0";
  $("#master-active").checked = true;
  $("#product-form-title").textContent = "Nuevo artículo";
  $("#save-product").textContent = "Guardar artículo";
  $("#cancel-product-edit").hidden = true;
  $("#product-form-error").hidden = true;
}

async function saveProduct(event) {
  event.preventDefault();
  const editingId = $("#master-product-id").value;
  const payload = {
    id: $("#master-id").value.trim(),
    name: $("#master-name").value.trim(),
    sku: $("#master-sku").value.trim(),
    barcode: $("#master-barcode").value.trim(),
    brand: $("#master-brand").value.trim(),
    unit_name: $("#master-unit").value.trim(),
    location: $("#master-location").value.trim(),
    supplier: $("#master-supplier").value.trim(),
    category: $("#master-category").value.trim(),
    cost: $("#master-cost").value,
    price: $("#master-price").value,
    tax_rate: $("#master-tax").value,
    stock: $("#master-stock").value,
    min_stock: $("#master-min-stock").value,
    technical_description: $("#master-description").value.trim(),
    tags: $("#master-tags").value.trim(),
    active: $("#master-active").checked,
  };
  const button = $("#save-product");
  const error = $("#product-form-error");
  button.disabled = true;
  error.hidden = true;
  try {
    await api(editingId ? `/api/products/${encodeURIComponent(editingId)}` : "/api/products", {
      method: editingId ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetProductForm();
    await refreshProducts();
    await refreshProductMaster();
    toast(editingId ? "Artículo actualizado." : "Artículo creado.");
  } catch (exception) {
    error.textContent = exception.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
}

function bindClients() {
  $("#client-form").addEventListener("submit", saveClient);
  let searchTimer;
  $("#client-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => refreshClients(1), 250);
  });
  $("#cancel-client-edit").addEventListener("click", resetClientForm);
  $("#lookup-customer")?.addEventListener("click", () => lookupParty("customer"));
  bindPartyInputs("customer");
}

async function refreshClients(page = 1) {
  const query = $("#client-search").value.trim();
  const payload = await api(`/api/clients?page=${page}&limit=25&q=${encodeURIComponent(query)}`);
  state.clients = payload.clients || [];
  state.clientPagination = payload.pagination || null;
  $("#client-select").innerHTML = `
    <option value="">Consumidor final / nuevo cliente</option>
    ${state.clients.filter((client) => client.active).map((client) => `<option value="${client.id}">${escapeHtml(client.name)}${client.rnc_cedula ? ` · ${escapeHtml(formatFiscalId(client.rnc_cedula))}` : ""}</option>`).join("")}
  `;
  renderClients();
  renderPager("client-list", state.clientPagination, (nextPage) => refreshClients(nextPage));
}

function renderClients() {
  const query = normalize($("#client-search").value);
  $("#client-list").innerHTML = state.clients.filter((client) => {
    const haystack = normalize(`${client.name} ${client.rnc_cedula} ${client.phone} ${client.email}`);
    return !query || haystack.includes(query);
  }).map((client) => `
    <article class="client-card">
      <div>
        <strong>${escapeHtml(client.name)}</strong>
        <span>${escapeHtml(client.rnc_cedula || "Sin RNC/cédula")} · ${escapeHtml(client.phone || "Sin teléfono")}</span>
        <span>${escapeHtml(client.email || "Sin correo")}${client.address ? ` · ${escapeHtml(client.address)}` : ""}</span>
        <span>Crédito disponible: ${money.format(client.credit_balance || 0)}${client.taxpayer_activity ? ` · ${escapeHtml(client.taxpayer_activity)}` : ""}</span>
      </div>
      <div class="company-actions">
        <span class="badge ${client.active ? "ok" : ""}">${client.active ? "Activo" : "Inactivo"}</span>
        <button class="table-button" data-edit-client="${client.id}">Editar</button>
        <button class="table-button danger" data-delete-client="${client.id}">Eliminar</button>
        <button class="table-button" data-use-client="${client.id}">Usar en venta</button>
      </div>
    </article>
  `).join("") || `<div class="empty-state">No hay clientes registrados.</div>`;
  $("#client-list").querySelectorAll("[data-edit-client]").forEach((button) => button.addEventListener("click", () => editClient(button.dataset.editClient)));
  $("#client-list").querySelectorAll("[data-delete-client]").forEach((button) => button.addEventListener("click", () => deleteClient(button.dataset.deleteClient)));
  $("#client-list").querySelectorAll("[data-use-client]").forEach((button) => button.addEventListener("click", () => useClientInSale(button.dataset.useClient)));
}

function editClient(clientId) {
  const client = state.clients.find((item) => Number(item.id) === Number(clientId));
  if (!client) return;
  $("#client-form-id").value = client.id;
  $("#customer-name").value = client.name;
  $("#customer-rnc").value = formatFiscalId(client.rnc_cedula || "");
  $("#customer-phone").value = formatPhone(client.phone || "");
  $("#customer-email").value = client.email || "";
  $("#customer-address").value = client.address || "";
  $("#customer-activity").value = client.taxpayer_activity || "";
  $("#customer-name").readOnly = Boolean(client.dgii_locked);
  $("#customer-name").dataset.dgiiLocked = client.dgii_locked ? "1" : "";
  $("#customer-notes").value = client.notes || "";
  $("#customer-active").checked = Boolean(client.active);
  showPartyLookupResult("customer", {
    nombre: client.name,
    direccion: client.address,
    actividad: client.taxpayer_activity,
  });
  $("#client-form-title").textContent = "Editar cliente";
  $("#save-client").textContent = "Guardar cambios";
  $("#cancel-client-edit").hidden = false;
}

function resetClientForm() {
  $("#client-form").reset();
  $("#client-form-id").value = "";
  $("#customer-active").checked = true;
  $("#customer-name").readOnly = false;
  $("#customer-name").dataset.dgiiLocked = "";
  $("#customer-activity").value = "";
  $("#customer-lookup-result").hidden = true;
  $("#client-form-title").textContent = "Nuevo cliente";
  $("#save-client").textContent = "Guardar cliente";
  $("#cancel-client-edit").hidden = true;
  $("#client-form-error").hidden = true;
}

async function saveClient(event) {
  event.preventDefault();
  const id = $("#client-form-id").value;
  const payload = partyPayload("customer");
  payload.notes = $("#customer-notes").value.trim();
  payload.active = $("#customer-active").checked;
  const error = $("#client-form-error");
  error.hidden = true;
  const localError = validatePartyPayload(payload, "cliente");
  if (localError) {
    error.textContent = localError;
    error.hidden = false;
    return;
  }
  try {
    await api(id ? `/api/clients/${id}` : "/api/clients", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetClientForm();
    await refreshClients();
    toast(id ? "Cliente actualizado." : "Cliente registrado.");
  } catch (exception) {
    error.textContent = exception.message;
    error.hidden = false;
  }
}

async function deleteClient(clientId) {
  const password = window.prompt("Contraseña de seguridad para eliminar cliente:");
  if (password === null) return;
  try {
    await api(`/api/clients/${clientId}`, { method: "DELETE", body: JSON.stringify({ password }) });
    await refreshClients();
    toast("Cliente eliminado.");
  } catch (exception) {
    toast(exception.message, true);
  }
}

function bindSuppliers() {
  $("#supplier-form")?.addEventListener("submit", saveSupplier);
  let searchTimer;
  $("#supplier-search")?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => refreshSuppliers(1), 250);
  });
  $("#cancel-supplier-edit")?.addEventListener("click", resetSupplierForm);
  $("#lookup-supplier")?.addEventListener("click", () => lookupParty("supplier"));
  bindPartyInputs("supplier");
}

async function refreshSuppliers(page = 1) {
  const query = $("#supplier-search").value.trim();
  const payload = await api(`/api/suppliers?page=${page}&limit=25&q=${encodeURIComponent(query)}`);
  state.suppliers = payload.suppliers || [];
  state.supplierPagination = payload.pagination || null;
  renderSuppliers();
  renderPager("supplier-list", state.supplierPagination, (nextPage) => refreshSuppliers(nextPage));
}

function renderSuppliers() {
  const list = $("#supplier-list");
  if (!list) return;
  const query = normalize($("#supplier-search").value);
  list.innerHTML = state.suppliers.filter((supplier) => {
    const haystack = normalize(`${supplier.name} ${supplier.rnc_cedula} ${supplier.phone} ${supplier.email} ${supplier.address} ${supplier.contact_person}`);
    return !query || haystack.includes(query);
  }).map((supplier) => `
    <article class="client-card">
      <div>
        <strong>${escapeHtml(supplier.name)}</strong>
        <span>${escapeHtml(formatFiscalId(supplier.rnc_cedula))} · ${escapeHtml(formatPhone(supplier.phone))}</span>
        <span>${escapeHtml(supplier.email)} · ${escapeHtml(supplier.address)}</span>
        ${supplier.contact_person ? `<span>Contacto: ${escapeHtml(formatPhone(supplier.contact_person))}</span>` : ""}
        ${supplier.taxpayer_activity ? `<span>Actividad DGII: ${escapeHtml(supplier.taxpayer_activity)}</span>` : ""}
      </div>
      <div class="company-actions">
        <span class="badge ${supplier.active ? "ok" : ""}">${supplier.active ? "Activo" : "Inactivo"}</span>
        <button class="table-button" data-edit-supplier="${supplier.id}">Editar</button>
        <button class="table-button danger" data-delete-supplier="${supplier.id}">Eliminar</button>
      </div>
    </article>
  `).join("") || `<div class="empty-state">No hay proveedores registrados.</div>`;
  list.querySelectorAll("[data-edit-supplier]").forEach((button) => button.addEventListener("click", () => editSupplier(button.dataset.editSupplier)));
  list.querySelectorAll("[data-delete-supplier]").forEach((button) => button.addEventListener("click", () => deleteSupplier(button.dataset.deleteSupplier)));
}

function editSupplier(supplierId) {
  const supplier = state.suppliers.find((item) => Number(item.id) === Number(supplierId));
  if (!supplier) return;
  $("#supplier-form-id").value = supplier.id;
  $("#supplier-name").value = supplier.name;
  $("#supplier-rnc").value = formatFiscalId(supplier.rnc_cedula || "");
  $("#supplier-phone").value = formatPhone(supplier.phone || "");
  $("#supplier-email").value = supplier.email || "";
  $("#supplier-address").value = supplier.address || "";
  $("#supplier-activity").value = supplier.taxpayer_activity || "";
  $("#supplier-name").readOnly = Boolean(supplier.dgii_locked);
  $("#supplier-name").dataset.dgiiLocked = supplier.dgii_locked ? "1" : "";
  $("#supplier-contact").value = formatPhone(supplier.contact_person || "");
  $("#supplier-notes").value = supplier.notes || "";
  $("#supplier-active").checked = Boolean(supplier.active);
  showPartyLookupResult("supplier", {
    nombre: supplier.name,
    direccion: supplier.address,
    actividad: supplier.taxpayer_activity,
  });
  $("#supplier-form-title").textContent = "Editar proveedor";
  $("#save-supplier").textContent = "Guardar cambios";
  $("#cancel-supplier-edit").hidden = false;
}

function resetSupplierForm() {
  $("#supplier-form").reset();
  $("#supplier-form-id").value = "";
  $("#supplier-active").checked = true;
  $("#supplier-name").readOnly = false;
  $("#supplier-name").dataset.dgiiLocked = "";
  $("#supplier-activity").value = "";
  $("#supplier-lookup-result").hidden = true;
  $("#supplier-form-title").textContent = "Nuevo proveedor";
  $("#save-supplier").textContent = "Guardar proveedor";
  $("#cancel-supplier-edit").hidden = true;
  $("#supplier-form-error").hidden = true;
}

async function saveSupplier(event) {
  event.preventDefault();
  const id = $("#supplier-form-id").value;
  const payload = partyPayload("supplier");
  payload.contact_person = onlyDigits($("#supplier-contact").value, 10);
  payload.notes = $("#supplier-notes").value.trim();
  payload.active = $("#supplier-active").checked;
  const error = $("#supplier-form-error");
  error.hidden = true;
  const localError = validatePartyPayload(payload, "proveedor");
  if (localError) {
    error.textContent = localError;
    error.hidden = false;
    return;
  }
  if (payload.contact_person && payload.contact_person.length !== 10) {
    error.textContent = "El contacto del proveedor debe tener 10 dígitos.";
    error.hidden = false;
    return;
  }
  try {
    await api(id ? `/api/suppliers/${id}` : "/api/suppliers", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    resetSupplierForm();
    await refreshSuppliers();
    toast(id ? "Proveedor actualizado." : "Proveedor registrado.");
  } catch (exception) {
    error.textContent = exception.message;
    error.hidden = false;
  }
}

async function deleteSupplier(supplierId) {
  const password = window.prompt("Contraseña de seguridad para eliminar proveedor:");
  if (password === null) return;
  try {
    await api(`/api/suppliers/${supplierId}`, { method: "DELETE", body: JSON.stringify({ password }) });
    await refreshSuppliers();
    toast("Proveedor eliminado.");
  } catch (exception) {
    toast(exception.message, true);
  }
}

function useClientInSale(clientId) {
  setView("sale");
  $("#client-select").value = String(clientId);
  selectRegisteredClient();
}

function bindPreinvoices() {
  $("#refresh-preinvoices").addEventListener("click", refreshPreinvoices);
}

async function refreshPreinvoices(page = 1) {
  const payload = await api(`/api/preinvoices?page=${page}&limit=25`);
  state.preinvoices = payload.preinvoices || [];
  state.preinvoicePagination = payload.pagination || null;
  renderPreinvoices();
  renderPager("preinvoice-list", state.preinvoicePagination, (nextPage) => refreshPreinvoices(nextPage));
}

function renderPreinvoices() {
  $("#preinvoice-list").innerHTML = state.preinvoices.map((draft) => `
    <article class="preinvoice-card">
      <div>
        <div class="document-title"><strong>Pre-Factura #${draft.id}</strong><span class="badge ${draft.status === "emitida" ? "ok" : "warning"}">${escapeHtml(draft.status)}</span></div>
        <p>${escapeHtml(draft.client_name)} · e-CF ${escapeHtml(draft.ecf_type)} · ${money.format(draft.total)}</p>
        <span>${formatDate(draft.updated_at)} · ${escapeHtml(draft.payment_method)}</span>
      </div>
      <div class="company-actions">
        ${draft.status === "borrador" ? `<button class="table-button" data-load-preinvoice="${draft.id}">Abrir</button><button class="primary-button compact" data-issue-preinvoice="${draft.id}" ${Number(draft.total) <= 0 ? "disabled" : ""}>Emitir</button>` : `<span class="muted-text">Factura #${draft.emitted_invoice_id}</span>`}
      </div>
    </article>
  `).join("") || `<div class="empty-state">No hay pre-facturas guardadas.</div>`;
  $("#preinvoice-list").querySelectorAll("[data-load-preinvoice]").forEach((button) => button.addEventListener("click", () => loadPreinvoice(button.dataset.loadPreinvoice)));
  $("#preinvoice-list").querySelectorAll("[data-issue-preinvoice]").forEach((button) => button.addEventListener("click", () => issuePreinvoice(button.dataset.issuePreinvoice)));
}

async function loadPreinvoice(preinvoiceId) {
  const payload = await api(`/api/preinvoices/${preinvoiceId}`);
  const draft = payload.preinvoice;
  state.currentPreinvoiceId = Number(draft.id);
  state.paypalPayment = null;
  state.ecfType = draft.ecf_type;
  state.cart = draft.items.map((item) => ({
    product_id: item.product_id,
    name: item.name,
    unit_price: Number(item.unit_price),
    discount_percent: percentFromAmount(item.discount_amount, Number(item.unit_price) * Number(item.quantity)),
    tax_rate: Number(item.tax_rate),
    stock: Number(item.stock),
    quantity: Number(item.quantity),
  }));
  $$(".segment").forEach((button) => button.classList.toggle("active", button.dataset.ecf === state.ecfType));
  $("#payment-method").value = draft.payment_method;
  $("#sale-notes").value = draft.notes || "";
  $("#general-discount").value = percentFromAmount(draft.general_discount, preinvoiceBaseAfterItemDiscounts(draft)).toFixed(2);
  $("#client-select").value = draft.client_id ? String(draft.client_id) : "";
  $("#client-rnc").value = formatFiscalId(draft.rnc_cedula || "");
  $("#client-name").value = draft.client_name || "";
  $("#client-phone").value = formatPhone(draft.phone || "");
  $("#client-email").value = draft.email || "";
  $("#client-address").value = draft.address || "";
  renderCart();
  renderOnlinePaymentStatus();
  setView("sale");
  toast(`Pre-Factura #${draft.id} abierta.`);
}

async function issuePreinvoice(preinvoiceId) {
  await loadPreinvoice(preinvoiceId);
  await issueInvoice();
}

function bindSale() {
  let searchTimer;
  $("#product-search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => refreshProducts(1), 250);
  });
  $("#clear-cart").addEventListener("click", () => {
    state.cart = [];
    state.currentPreinvoiceId = null;
    $("#sale-notes").value = "";
    $("#general-discount").value = "0";
    resetCreditRedemption();
    renderCart();
  });
  $$(".segment").forEach((button) => {
    button.addEventListener("click", () => {
      state.ecfType = button.dataset.ecf;
      $$(".segment").forEach((item) => item.classList.toggle("active", item === button));
      renderBuyerRequirement();
    });
  });
  $("#issue-invoice").addEventListener("click", issueInvoice);
  $("#save-preinvoice").addEventListener("click", savePreinvoice);
  $("#general-discount").addEventListener("input", () => {
    state.paypalPayment = null;
    renderTotals();
  });
  $("#lookup-client").addEventListener("click", lookupClient);
  $("#client-select").addEventListener("change", selectRegisteredClient);
  $("#check-credit").addEventListener("click", () => refreshCreditAvailability(true));
  $("#credit-note-code").addEventListener("input", (event) => {
    event.target.value = event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 13);
    state.availableCredit = 0;
    state.availableCreditNotes = [];
    $("#credit-amount").value = "0";
    renderCreditAvailability();
    renderTotals();
  });
  $("#credit-amount").addEventListener("input", () => {
    state.paypalPayment = null;
    renderTotals();
  });
  bindPartyInputs("client");
  $("#payment-method").addEventListener("change", () => {
    state.paypalPayment = null;
    renderSplitPayment();
    renderOnlinePaymentStatus();
  });
  $("#split-payment-enabled").addEventListener("change", () => {
    state.paypalPayment = null;
    renderSplitPayment(true);
  });
  $("#primary-payment-amount").addEventListener("input", () => {
    state.paypalPayment = null;
    renderSplitPayment();
  });
  $("#secondary-payment-method").addEventListener("change", () => {
    state.paypalPayment = null;
    renderSplitPayment();
  });
  $("#open-payment-gateway").addEventListener("click", () => {
    let online = null;
    try { online = paymentRowsFromForm().find((row) => ["tarjeta", "paypal"].includes(row.payment_method)); } catch (exception) { toast(exception.message, true); return; }
    const total = Number(online?.amount || 0);
    if (total <= 0) {
      toast("Agrega artículos con un total mayor que cero para cobrar.", true);
      return;
    }
    openPaymentGateway(online.payment_method, total);
  });
  $("#close-payment-dialog").addEventListener("click", () => $("#payment-dialog").close());
  $("#paypal-simulate-pay")?.addEventListener("click", () => confirmSimulatedPayment("paypal"));
  $("#paypal-simulated-portal")?.addEventListener("submit", (event) => {
    event.preventDefault();
    confirmSimulatedPayment("paypal");
  });
  $("#card-simulated-portal")?.addEventListener("submit", (event) => {
    event.preventDefault();
    confirmSimulatedPayment("tarjeta");
  });
  $("#sim-card-number")?.addEventListener("input", formatCardNumberInput);
  $("#sim-card-expiry")?.addEventListener("input", formatCardExpiryInput);
}

async function selectRegisteredClient() {
  const client = state.clients.find((item) => Number(item.id) === Number($("#client-select").value));
  const loadedCode = $("#credit-note-code").value.trim();
  fillRegisteredClient(client);
  $("#credit-amount").value = "0";
  state.availableCredit = 0;
  state.availableCreditNotes = [];
  renderBuyerRequirement();
  await refreshCreditAvailability();
  if (loadedCode && state.availableCredit > 0) {
    $("#credit-amount").value = Math.min(Number(state.availableCredit), cartTotals().total).toFixed(2);
    renderTotals();
  }
}

function fillRegisteredClient(client) {
  $("#client-rnc").value = formatFiscalId(client?.rnc_cedula || "");
  $("#client-name").value = client?.name || "";
  $("#client-phone").value = formatPhone(client?.phone || "");
  $("#client-email").value = client?.email || "";
  $("#client-address").value = client?.address || "";
}

function paymentRowsFromForm() {
  const total = salePayableTotal();
  const primaryMethod = $("#payment-method").value;
  if (primaryMethod === "credito") return [];
  if (!$("#split-payment-enabled").checked) {
    return total > 0 ? [{ payment_method: primaryMethod, amount: Math.round(total * 100) / 100 }] : [];
  }
  const primaryAmount = Math.round(Number($("#primary-payment-amount").value || 0) * 100) / 100;
  const secondaryMethod = $("#secondary-payment-method").value;
  const secondaryAmount = Math.round((total - primaryAmount) * 100) / 100;
  if (primaryMethod === secondaryMethod) throw new Error("Selecciona dos formas de pago diferentes.");
  if (primaryAmount <= 0 || secondaryAmount <= 0) throw new Error("Cada forma de pago debe tener un monto mayor que cero.");
  return [
    { payment_method: primaryMethod, amount: primaryAmount },
    { payment_method: secondaryMethod, amount: secondaryAmount },
  ];
}

function renderSplitPayment(resetAmount = false) {
  const enabled = Boolean($("#split-payment-enabled")?.checked);
  const panel = $("#split-payment-panel");
  if (!panel) return;
  const hasCredit = effectiveCreditAmount() > 0;
  $("#payment-method-label").textContent = hasCredit ? "Forma de pago del monto restante" : "Pago";
  $("#split-payment-title").textContent = hasCredit ? "Dividir saldo restante" : "Pago con dos formas";
  $("#split-payment-caption").textContent = hasCredit ? "Usar dos medios adicionales (opcional)" : "Dividir el monto a cobrar";
  panel.hidden = !enabled;
  $("#split-payment-enabled").disabled = $("#payment-method").value === "credito";
  if ($("#payment-method").value === "credito" && enabled) {
    $("#split-payment-enabled").checked = false;
    panel.hidden = true;
    return;
  }
  if (!enabled) return;
  const total = salePayableTotal();
  if (resetAmount || !Number($("#primary-payment-amount").value)) {
    $("#primary-payment-amount").value = (Math.round(total * 50) / 100).toFixed(2);
  }
  const primary = Math.max(0, Math.min(total, Number($("#primary-payment-amount").value || 0)));
  const remaining = Math.max(0, Math.round((total - primary) * 100) / 100);
  $("#secondary-payment-amount").value = remaining.toFixed(2);
  $("#split-payment-summary").textContent = `${paymentLabelFor($("#payment-method").value)} ${money.format(primary)} + ${paymentLabelFor($("#secondary-payment-method").value)} ${money.format(remaining)} = ${money.format(total)}`;
  renderOnlinePaymentStatus();
}

function requestedCreditAmount() {
  const amount = Number($("#credit-amount")?.value || 0);
  return Number.isFinite(amount) && amount > 0 ? Math.round(amount * 100) / 100 : 0;
}

function effectiveCreditAmount() {
  return Math.min(requestedCreditAmount(), Number(state.availableCredit || 0), cartTotals().total);
}

function salePayableTotal() {
  return Math.max(0, Math.round((cartTotals().total - effectiveCreditAmount()) * 100) / 100);
}

function resetCreditRedemption() {
  state.availableCredit = 0;
  state.availableCreditNotes = [];
  if ($("#credit-note-code")) $("#credit-note-code").value = "";
  if ($("#credit-amount")) $("#credit-amount").value = "0";
  renderCreditAvailability();
}

function renderCreditAvailability() {
  const box = $("#credit-availability");
  const list = $("#available-credit-list");
  if (!box) return;
  const clientId = Number($("#client-select")?.value || 0);
  const code = $("#credit-note-code")?.value.trim() || "";
  box.className = `credit-availability ${state.availableCredit > 0 ? "available" : ""}`;
  if (!clientId && code && state.availableCredit > 0) {
    box.textContent = `Nota ${code} cargada · saldo ${money.format(state.availableCredit)}. Selecciona el cliente que presenta el vale.`;
  } else if (!clientId && state.availableCreditNotes.length) {
    box.textContent = `${state.availableCreditNotes.length} nota(s) vigente(s). Carga una para aplicarla; si es de Consumidor Final, selecciona quién presenta el vale.`;
  } else if (!clientId) {
    box.textContent = code ? `No encontramos una nota vigente con el e-NCF ${code}.` : "Consulta las notas vigentes o selecciona un cliente registrado.";
  } else if (state.availableCredit > 0) {
    const source = code ? `Vale ${code}` : `${state.availableCreditNotes.length} nota(s) aceptada(s)`;
    box.textContent = `${source} · Saldo disponible: ${money.format(state.availableCredit)}.`;
  } else {
    box.textContent = code ? `El vale ${code} no existe, no está aceptado o ya fue consumido.` : "Este cliente no tiene notas de crédito disponibles.";
  }
  if (list) {
    list.innerHTML = state.availableCreditNotes.map((note) => `
      <article class="available-credit-item">
        <div><strong>${escapeHtml(note.display_encf)}</strong><span>${escapeHtml(note.source_client_name || "Consumidor Final")} · vence ${escapeHtml(formatReceiptDate(note.expires_at))}</span></div>
        <div class="available-credit-action"><strong>${money.format(note.available_amount)}</strong><button class="table-button" type="button" data-select-credit="${note.id}">Cargar nota</button></div>
      </article>
    `).join("");
    list.querySelectorAll("[data-select-credit]").forEach((button) => button.addEventListener("click", () => {
      const note = state.availableCreditNotes.find((item) => Number(item.id) === Number(button.dataset.selectCredit));
      if (!note) return;
      const sourceClient = state.clients.find((item) => Number(item.id) === Number(note.source_client_id));
      if (sourceClient) {
        $("#client-select").value = String(sourceClient.id);
        fillRegisteredClient(sourceClient);
        renderBuyerRequirement();
      }
      $("#credit-note-code").value = note.display_encf;
      $("#credit-amount").value = Math.min(Number(note.available_amount), cartTotals().total).toFixed(2);
      state.availableCredit = Number(note.available_amount);
      state.availableCreditNotes = [note];
      $("#split-payment-enabled").checked = false;
      renderCreditAvailability();
      renderTotals();
      toast(sourceClient ? `Nota ${note.display_encf} cargada.` : `Nota ${note.display_encf} cargada. Selecciona el cliente que presenta el vale.`);
    }));
  }
}

async function refreshCreditAvailability(showMessage = false) {
  const clientId = Number($("#client-select")?.value || 0);
  state.availableCredit = 0;
  state.availableCreditNotes = [];
  const code = $("#credit-note-code").value.trim().toUpperCase();
  const result = await api(`/api/credit-notes/available?client_id=${clientId}&code=${encodeURIComponent(code)}`);
  state.availableCredit = Number(result.available_total || 0);
  state.availableCreditNotes = result.credit_notes || [];
  renderCreditAvailability();
  renderTotals();
  if (showMessage) {
    toast(state.availableCredit > 0 ? `${state.availableCreditNotes.length} nota(s) vigente(s) encontrada(s).` : "No hay notas de crédito vigentes disponibles.", state.availableCredit <= 0);
  }
}

function renderCreditPaymentPlan() {
  const plan = $("#credit-payment-plan");
  if (!plan) return;
  const credit = effectiveCreditAmount();
  const remaining = salePayableTotal();
  plan.hidden = credit <= 0;
  if (credit <= 0) return;
  const remainder = remaining > 0
    ? `<span>+</span><div><small>${escapeHtml(paymentLabelFor($("#payment-method").value))}</small><strong>${money.format(remaining)}</strong></div>`
    : "";
  plan.innerHTML = `<div><small>Nota de crédito</small><strong>${money.format(credit)}</strong></div>${remainder}<span>=</span><div><small>Total cubierto</small><strong>${money.format(credit + remaining)}</strong></div>`;
}

function selectedClientPayload() {
  return {
    id: Number($("#client-select").value || 0) || null,
    rnc_cedula: onlyDigits($("#client-rnc").value, 11),
    name: $("#client-name").value.trim().toUpperCase(),
    phone: onlyDigits($("#client-phone").value, 10),
    email: $("#client-email").value.trim().toLowerCase(),
    address: $("#client-address").value.trim().toUpperCase(),
  };
}

function validateSaleClientPayload(client, total) {
  if (client.id) return "";
  const requiresFiscalId = state.ecfType === "31" || (state.ecfType === "32" && total >= 250000);
  const hasClientData = Boolean(client.rnc_cedula || client.name || client.phone || client.email || client.address);
  if (!requiresFiscalId && !hasClientData) return "";
  return validatePartyPayload(client, "cliente");
}

function renderBuyerRequirement() {
  const total = cartTotals().total;
  const required = state.ecfType === "31" || (state.ecfType === "32" && total >= 250000);
  const box = $("#buyer-requirement");
  const selected = state.clients.find((item) => Number(item.id) === Number($("#client-select").value));
  const credit = Number(selected?.credit_balance || 0);
  box.className = `buyer-requirement ${required ? "required" : ""}`;
  const baseText = state.ecfType === "31"
    ? "El E31 requiere RNC o cédula del comprador."
    : total >= 250000
      ? "Este E32 alcanza RD$250,000: debes identificar al comprador."
      : "En E32 menor de RD$250,000 la identificación del comprador es opcional.";
  box.textContent = credit > 0 ? `${baseText} Crédito disponible del cliente: ${money.format(credit)}.` : baseText;
}

async function lookupClient() {
  const input = $("#client-rnc");
  const digits = input.value.replace(/\D/g, "");
  if (![9, 11].includes(digits.length)) {
    toast("Escribe un RNC de 9 dígitos o una cédula de 11.", true);
    return;
  }
  const button = $("#lookup-client");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Buscando...";
  try {
    let result;
    let source;
    try {
      result = await api(`/api/dgii/taxpayer?value=${encodeURIComponent(digits)}`);
      source = "DGII";
    } catch (error) {
      if (digits.length !== 11) throw error;
      result = await api(`/api/dgii/jce?cedula=${encodeURIComponent(digits)}`);
      source = "JCE";
    }
    renderClientValidation(result, source);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function renderClientValidation(result, source) {
  const box = $("#client-validation");
  const found = result.success !== false && result.found !== false;
  if (!found) {
    box.hidden = false;
    box.className = "client-validation error";
    box.textContent = result.message || "No se encontraron datos para este documento.";
    return;
  }
  const name = result.nombre || result.razonSocial || result.nombreComercial || "";
  if (name) $("#client-name").value = name;
  const details = [
    result.estado ? `Estado: ${result.estado}` : "",
    result.regimen ? `Régimen: ${result.regimen}` : "",
    result.actividad ? `Actividad: ${result.actividad}` : "",
    result.fechaNacimiento ? `Nacimiento: ${formatDate(result.fechaNacimiento)}` : "",
  ].filter(Boolean);
  box.hidden = false;
  box.className = "client-validation success";
  box.innerHTML = `
    ${result.foto ? `<img src="${escapeHtml(result.foto)}" alt="Foto de identificación" />` : ""}
    <div>
      <strong>${escapeHtml(name || "Documento validado")}</strong>
      <span>Fuente: ${escapeHtml(source)}${details.length ? ` · ${escapeHtml(details.join(" · "))}` : ""}</span>
    </div>
  `;
  toast(`Cliente validado en ${source}.`);
}

async function lookupParty(prefix) {
  const input = $(`#${prefix}-rnc`);
  const digits = onlyDigits(input?.value || "", 11);
  if (![9, 11].includes(digits.length)) {
    toast("Escribe un RNC de 9 dígitos o una cédula de 11.", true);
    return;
  }
  const button = $(`#lookup-${prefix}`);
  const original = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "Consultando...";
  }
  try {
    const result = await lookupTaxpayerOrCitizen(digits);
    if (!partyWasFound(result)) {
      showPartyLookupResult(prefix, null, "este contribuyente no existe en DGII");
      toast("este contribuyente no existe en DGII", true);
      return;
    }
    applyPartyLookup(prefix, result);
    showPartyLookupResult(prefix, result);
    toast("Contribuyente encontrado en DGII.");
  } catch (exception) {
    toast(exception.message || "este contribuyente no existe en DGII", true);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

async function lookupTaxpayerOrCitizen(digits) {
  try {
    return await api(`/api/dgii/taxpayer?value=${encodeURIComponent(digits)}`);
  } catch (error) {
    if (digits.length !== 11) throw new Error("este contribuyente no existe en DGII");
    return api(`/api/dgii/jce?cedula=${encodeURIComponent(digits)}`);
  }
}

function partyWasFound(result) {
  if (!result || result.success === false || result.found === false) return false;
  const name = extractPartyName(result);
  return Boolean(name || result.nombreComercial || result.razonSocial);
}

function extractPartyName(result) {
  return String(
    result.nombre ||
    result.razonSocial ||
    result.razon_social ||
    result.nombreComercial ||
    result.nombre_comercial ||
    result.name ||
    ""
  ).trim().toUpperCase();
}

function extractPartyAddress(result) {
  return String(
    result.direccion ||
    result.direccionCompleta ||
    result.address ||
    result.domicilio ||
    ""
  ).trim().toUpperCase();
}

function extractPartyActivity(result) {
  return String(
    result.actividad ||
    result.actividadEconomica ||
    result.actividad_economica ||
    result.descripcionActividad ||
    ""
  ).trim().toUpperCase();
}

function applyPartyLookup(prefix, result) {
  const name = extractPartyName(result);
  const address = extractPartyAddress(result);
  const activity = extractPartyActivity(result);
  const nameInput = $(`#${prefix}-name`);
  if (nameInput && name) {
    nameInput.value = name;
    nameInput.readOnly = true;
    nameInput.dataset.dgiiLocked = "1";
  }
  if (address && $(`#${prefix}-address`)) $(`#${prefix}-address`).value = address;
  if ($(`#${prefix}-activity`)) $(`#${prefix}-activity`).value = activity;
}

function showPartyLookupResult(prefix, result, error = "") {
  const box = $(`#${prefix}-lookup-result`);
  if (!box) return;
  box.hidden = false;
  if (error) {
    box.className = "client-validation error";
    box.textContent = error;
    return;
  }
  const name = extractPartyName(result);
  const address = extractPartyAddress(result);
  const activity = extractPartyActivity(result);
  box.className = "client-validation success";
  box.innerHTML = `
    <div>
      <strong>${escapeHtml(name || "Contribuyente encontrado")}</strong>
      <span>${address ? `Dirección: ${escapeHtml(address)}` : "Dirección no disponible"}</span>
      <span>${activity ? `Actividad DGII: ${escapeHtml(activity)}` : "Actividad DGII no disponible"}</span>
    </div>
  `;
}

$("#logout-button").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST", body: "{}" });
  window.location.assign("/login");
});

function bindAssistant() {
  $("#send-ai").addEventListener("click", runAssistant);
  $("#ai-budget").addEventListener("input", formatMoneyInput);
  $("#ai-query").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      runAssistant();
    }
  });
}

function bindInventory() {
  $("#refresh-inventory").addEventListener("click", refreshProducts);
}

function bindReports() {
  $("#refresh-reports").addEventListener("click", refreshReports);
  $("#run-management-report")?.addEventListener("click", refreshManagementReport);
  $("#test-imecf").addEventListener("click", testImecfConnection);
  $("#open-e34-center").addEventListener("click", () => {
    setView("fiscal");
    setTimeout(() => $(".fiscal-credit-notes-panel")?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
  });
}

function bindFiscal() {
  $("#refresh-fiscal").addEventListener("click", refreshFiscal);
  $("#retry-integrations")?.addEventListener("click", async () => {
    const result = await api("/api/integrations/retry", { method: "POST", body: "{}" });
    toast(`Reintentos procesados: ${result.processed}. Completados: ${result.completed}.`, result.failed > 0);
    await refreshFiscal();
  });
  $("#fiscal-test-connection").addEventListener("click", testImecfConnection);
  $("#validate-fiscal-issuer").addEventListener("click", validateFiscalIssuer);
  $("#fiscal-sync-documents").addEventListener("click", syncFiscalDocuments);
  $("#fiscal-search").addEventListener("input", renderFiscalDocuments);
  $("#credit-note-form").addEventListener("submit", issueCreditNote);
  $("#credit-source-invoice").addEventListener("change", loadCreditReturnItems);
  $("#credit-status-filter").addEventListener("change", renderCreditNotes);
  if (!$("#credit-expires-at").value) $("#credit-expires-at").value = defaultCreditExpiry();
  $("#fiscal-config-form").addEventListener("submit", saveFiscalCompany);
  $("#cancel-fiscal-config").addEventListener("click", resetFiscalCompanyForm);
  $$(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.fiscalFilter = button.dataset.fiscalFilter;
      $$(".filter-button").forEach((item) => item.classList.toggle("active", item === button));
      renderFiscalDocuments();
    });
  });
}

async function loadFiscalCompanies(canManage) {
  $("#fiscal-admin-config").hidden = !canManage;
  $("#fiscal-access-note").hidden = canManage;
  if (!canManage) return;
  const payload = await api("/api/fiscal/companies");
  state.fiscalCompanies = payload.companies || [];
  renderFiscalCompanies();
}

function renderFiscalCompanies() {
  $("#fiscal-company-list").innerHTML = state.fiscalCompanies.map((company) => {
    const validated = Boolean(company.validated_at);
    const tested = Boolean(company.last_test_ok);
    return `
      <article class="fiscal-company-card ${company.active ? "active" : ""}">
        <div class="fiscal-company-head">
          <div>
            <strong>${escapeHtml(company.workspace_name)}</strong>
            <span>${escapeHtml(company.issuer_name)} · RNC ${escapeHtml(company.issuer_rnc)}</span>
          </div>
          <span class="badge ${company.active ? "ok" : company.enabled ? "warning" : ""}">${company.active ? "Activa" : company.enabled ? "Pendiente" : "Deshabilitada"}</span>
        </div>
        <div class="company-checks">
          <span class="${validated ? "check-ok" : ""}">${validated ? "Validada en DGII" : "Falta validar emisor"}</span>
          <span class="${tested ? "check-ok" : ""}">${tested ? "Conexión probada" : "Falta probar conexión"}</span>
          <span>API Key ${escapeHtml(company.api_key_masked || "no configurada")}</span>
          <span>${escapeHtml(company.environment === "production" ? "Producción" : "Test")}</span>
        </div>
        ${company.last_test_message ? `<p>${escapeHtml(company.last_test_message)}</p>` : ""}
        <div class="company-actions">
          <button class="table-button" data-company-action="edit" data-company-id="${company.id}">Editar</button>
          <button class="table-button" data-company-action="validate" data-company-id="${company.id}">Validar emisor</button>
          <button class="table-button" data-company-action="test" data-company-id="${company.id}">Probar conexión</button>
          ${!company.active ? `<button class="primary-button compact" data-company-action="activate" data-company-id="${company.id}" ${!company.enabled || !validated || !tested ? "disabled" : ""}>Activar</button>` : ""}
        </div>
      </article>
    `;
  }).join("") || `<div class="empty-state">No hay empresas fiscales configuradas.</div>`;
  $("#fiscal-company-list").querySelectorAll("[data-company-action]").forEach((button) => {
    button.addEventListener("click", () => runFiscalCompanyAction(button));
  });
}

function editFiscalCompany(companyId) {
  const company = state.fiscalCompanies.find((item) => Number(item.id) === Number(companyId));
  if (!company) return;
  $("#fiscal-config-id").value = company.id;
  $("#config-workspace").value = company.workspace_name;
  $("#config-issuer-name").value = company.issuer_name;
  $("#config-issuer-rnc").value = company.issuer_rnc;
  $("#config-company-id").value = company.company_id || "";
  $("#config-environment").value = company.environment;
  $("#config-api-key").value = "";
  $("#config-base-url").value = company.base_url;
  $("#config-portal-url").value = company.portal_url || "";
  $("#config-enabled").checked = Boolean(company.enabled);
  $("#fiscal-config-title").textContent = "Editar empresa IMECF";
  $("#save-fiscal-config").textContent = "Guardar y volver a validar";
  $("#cancel-fiscal-config").hidden = false;
  $(".fiscal-config-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetFiscalCompanyForm() {
  $("#fiscal-config-form").reset();
  $("#fiscal-config-id").value = "";
  $("#config-base-url").value = "https://ecf-platform-backend-50801509587.us-central1.run.app";
  $("#config-portal-url").value = "https://ecf-platform-frontend-50801509587.us-central1.run.app";
  $("#config-environment").value = "test";
  $("#fiscal-config-title").textContent = "Agregar empresa IMECF";
  $("#save-fiscal-config").textContent = "Guardar configuración";
  $("#cancel-fiscal-config").hidden = true;
  $("#fiscal-config-error").hidden = true;
}

async function saveFiscalCompany(event) {
  event.preventDefault();
  const id = $("#fiscal-config-id").value;
  const payload = {
    id: id || null,
    workspace_name: $("#config-workspace").value.trim(),
    issuer_name: $("#config-issuer-name").value.trim(),
    issuer_rnc: $("#config-issuer-rnc").value.trim(),
    company_id: $("#config-company-id").value.trim(),
    environment: $("#config-environment").value,
    api_key: $("#config-api-key").value.trim(),
    base_url: $("#config-base-url").value.trim(),
    portal_url: $("#config-portal-url").value.trim(),
    enabled: $("#config-enabled").checked,
    current_password: $("#config-current-password").value,
  };
  const button = $("#save-fiscal-config");
  const error = $("#fiscal-config-error");
  button.disabled = true;
  error.hidden = true;
  try {
    await api("/api/fiscal/companies", { method: "POST", body: JSON.stringify(payload) });
    resetFiscalCompanyForm();
    await refreshFiscal();
    toast("Configuración guardada. Valida y prueba la empresa antes de activarla.");
  } catch (exception) {
    error.textContent = exception.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
}

async function runFiscalCompanyAction(button) {
  const id = Number(button.dataset.companyId);
  const action = button.dataset.companyAction;
  if (action === "edit") {
    editFiscalCompany(id);
    return;
  }
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Procesando...";
  try {
    const result = await api(`/api/fiscal/companies/${id}/${action}`, { method: "POST", body: "{}" });
    toast(result.message || (action === "activate" ? "Empresa fiscal activada." : "Operación completada."), result.valid === false || result.ok === false);
    await refreshFiscal();
    if (action === "activate") window.location.reload();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

async function validateFiscalIssuer() {
  const button = $("#validate-fiscal-issuer");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Validando...";
  try {
    const result = await api("/api/fiscal/validate-issuer");
    toast(result.message, !result.valid);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

async function refreshFiscal() {
  const [payload, creditPayload, invoicePayload] = await Promise.all([
    api("/api/fiscal/dashboard"),
    api("/api/credit-notes"),
    api("/api/invoices?page=1&limit=100"),
  ]);
  state.creditNotes = creditPayload.credit_notes || [];
  state.invoices = invoicePayload.invoices || [];
  state.imecfConfigured = Boolean(payload.provider?.configured);
  state.imecfActive = Boolean(payload.provider?.active);
  state.fiscalDocuments = payload.documents || [];
  if (state.imecfActive && state.remoteFiscalDocuments.length === 0) {
    const remote = await api("/api/imecf/documents?page=1&limit=100");
    state.remoteFiscalDocuments = (remote.data || []).map(normalizeRemoteDocument);
  } else if (!state.imecfActive) {
    state.remoteFiscalDocuments = [];
  }
  const totals = { ...(payload.totals || {}) };
  if (state.remoteFiscalDocuments.length) {
    totals.documents = state.remoteFiscalDocuments.length;
    totals.accepted = state.remoteFiscalDocuments.filter((item) => normalize(item.api_status).includes("acept")).length;
    totals.errors = state.remoteFiscalDocuments.filter((item) => item.api_error || normalize(item.api_status).includes("error") || normalize(item.api_status).includes("rechaz")).length;
    totals.local = state.fiscalDocuments.filter((item) => !item.api_status && !item.api_error).length;
  }
  renderFiscalHealth(totals);
  renderFiscalProvider(payload.provider || {});
  await loadFiscalCompanies(Boolean(payload.can_manage_credentials));
  renderFiscalSequences(payload.sequences || []);
  renderCreditNotes();
  renderFiscalDocuments();
}

function renderCreditNotes() {
  const eligible = state.invoices.filter((invoice) => invoice.provider_encf);
  $("#credit-source-invoice").innerHTML = `<option value="">Selecciona una factura aceptada</option>${eligible.map((invoice) => `<option value="${invoice.id}">${escapeHtml(invoice.provider_encf)} · ${escapeHtml(invoice.client_name)} · ${money.format(invoice.total)}</option>`).join("")}`;
  const filter = $("#credit-status-filter")?.value || "vigente";
  const notes = state.creditNotes.filter((note) => filter === "todas" || note.credit_status === filter);
  $("#credit-note-list").innerHTML = notes.map((note) => `
    <article class="credit-note-card">
      <div class="document-title"><strong>${escapeHtml(note.provider_encf || note.en_ncf)}</strong><span class="badge ${note.credit_status === "vigente" ? "ok" : note.credit_status === "rechazada" || note.credit_status === "vencida" ? "low" : "warning"}">${escapeHtml(note.credit_status || note.api_status || note.status)}</span></div>
      <p>Modifica ${escapeHtml(note.source_encf)} · ${money.format(note.total)}</p>
      <p>Cliente: ${escapeHtml(note.source_client_name || "Consumidor Final")} · Saldo: ${money.format(note.available_amount || 0)}</p>
      <p>Vigencia comercial hasta ${escapeHtml(formatReceiptDate(note.expires_at))}</p>
      <span>${escapeHtml(note.reason)}</span>
      <div class="credit-card-actions"><button class="table-button" type="button" data-credit-voucher="${note.id}">Comprobante</button>${note.credit_status === "vigente" ? `<button class="table-button" type="button" data-use-credit="${note.id}">Usar en venta</button>` : ""}</div>
    </article>
  `).join("") || `<div class="empty-state">No hay notas de crédito para este filtro.</div>`;
  $("#credit-note-list").querySelectorAll("[data-credit-voucher]").forEach((button) => button.addEventListener("click", () => openCreditVoucher(Number(button.dataset.creditVoucher))));
  $("#credit-note-list").querySelectorAll("[data-use-credit]").forEach((button) => button.addEventListener("click", () => {
    const note = state.creditNotes.find((item) => Number(item.id) === Number(button.dataset.useCredit));
    const client = state.clients.find((item) => normalize(item.name) === normalize(note?.source_client_name));
    setView("sale");
    if (client) { $("#client-select").value = client.id; selectRegisteredClient(); }
    $("#credit-note-code").value = note?.provider_encf || note?.en_ncf || "";
    $("#credit-amount").value = Number(note?.available_amount || 0).toFixed(2);
    refreshCreditAvailability();
  }));
}

function bindPurchases() {
  $("#refresh-purchases")?.addEventListener("click", refreshPurchases);
  $("#purchase-list")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-pay-purchase]"); if (!button) return;
    const row = state.purchases.find((item) => Number(item.id) === Number(button.dataset.payPurchase));
    const amount = Number(window.prompt(`Monto a pagar (balance ${money.format(row?.balance_due || 0)}):`, String(row?.balance_due || "")) || 0);
    if (!amount) return;
    const paymentMethod = (window.prompt("Forma de pago: transferencia, efectivo o tarjeta", "transferencia") || "transferencia").toLowerCase();
    await api(`/api/purchases/${row.id}/payments`, { method: "POST", body: JSON.stringify({ amount, payment_method: paymentMethod }) });
    toast("Pago al proveedor registrado."); await refreshPurchases();
  });
  $("#purchase-product")?.addEventListener("change", () => {
    const product = state.products.find((item) => String(item.id) === $("#purchase-product").value);
    if (product) $("#purchase-unit-cost").value = Number(product.cost || 0).toFixed(2);
  });
  $("#add-purchase-line")?.addEventListener("click", () => {
    const product = state.products.find((item) => String(item.id) === $("#purchase-product").value);
    const quantity = Number($("#purchase-quantity").value || 0), unitCost = Number($("#purchase-unit-cost").value || 0);
    if (!product || quantity <= 0 || unitCost < 0) { toast("Selecciona un producto, cantidad y costo válidos.", true); return; }
    const existing = state.purchaseDraft.find((item) => String(item.product_id) === String(product.id));
    if (existing) { existing.quantity += quantity; existing.unit_cost = unitCost; }
    else state.purchaseDraft.push({ product_id: product.id, name: product.name, quantity, unit_cost: unitCost, tax_rate: Number(product.tax_rate || 0) });
    renderPurchaseDraft();
  });
  $("#purchase-draft")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-purchase]");
    if (!button) return;
    state.purchaseDraft = state.purchaseDraft.filter((item) => String(item.product_id) !== button.dataset.removePurchase);
    renderPurchaseDraft();
  });
  $("#purchase-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.purchaseDraft.length) { toast("Agrega al menos un artículo a la compra.", true); return; }
    await api("/api/purchases", { method: "POST", body: JSON.stringify({
      supplier_id: Number($("#purchase-supplier").value), supplier_invoice_number: $("#purchase-supplier-invoice").value.trim(),
      amount_paid: Number($("#purchase-paid").value || 0), payment_method: $("#purchase-payment-method").value,
      notes: $("#purchase-notes").value.trim(), items: state.purchaseDraft,
    }) });
    state.purchaseDraft = []; $("#purchase-form").reset(); renderPurchaseDraft(); toast("Compra recibida e inventario actualizado."); await refreshPurchases();
  });
}

function renderPurchaseDraft() {
  const target = $("#purchase-draft"); if (!target) return;
  target.innerHTML = state.purchaseDraft.map((item) => `<article><div><strong>${escapeHtml(item.name)}</strong><span>${Number(item.quantity).toLocaleString("es-DO")} × ${money.format(item.unit_cost)}</span></div><button class="table-button danger" type="button" data-remove-purchase="${escapeHtml(item.product_id)}">Quitar</button></article>`).join("") || `<div class="empty-state">Agrega los artículos recibidos.</div>`;
}

async function refreshPurchases() {
  const [productsPayload, suppliersPayload, purchasesPayload] = await Promise.all([
    api("/api/products?page=1&limit=100"), api("/api/suppliers?page=1&limit=100"), api("/api/purchases"),
  ]);
  state.products = productsPayload.products || []; state.suppliers = suppliersPayload.suppliers || []; state.purchases = purchasesPayload.purchases || [];
  $("#purchase-supplier").innerHTML = `<option value="">Selecciona un proveedor</option>${state.suppliers.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("")}`;
  $("#purchase-product").innerHTML = `<option value="">Selecciona un producto</option>${state.products.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.sku)} · ${escapeHtml(item.name)}</option>`).join("")}`;
  $("#purchase-list").innerHTML = state.purchases.map((item) => `<article><div><strong>${escapeHtml(item.order_number)} · ${escapeHtml(item.supplier_name)}</strong><span>${escapeHtml(formatReceiptDateTime(item.received_at || item.ordered_at))} · Factura ${escapeHtml(item.supplier_invoice_number || "s/n")}</span></div><div><strong>${money.format(item.total)}</strong><span>Balance ${money.format(item.balance_due)}</span>${Number(item.balance_due || 0) > 0 ? `<button class="table-button" data-pay-purchase="${item.id}">Registrar pago</button>` : ""}</div></article>`).join("") || `<div class="empty-state">Todavía no hay compras registradas.</div>`;
  renderPurchaseDraft();
}

function bindReceivables() {
  $("#refresh-receivables")?.addEventListener("click", refreshReceivables);
  $("#receivable-list")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-collect-receivable]"); if (!button) return;
    const row = state.receivables.find((item) => Number(item.id) === Number(button.dataset.collectReceivable));
    const amount = Number(window.prompt(`Monto a cobrar (balance ${money.format(row?.balance || 0)}):`, String(row?.balance || "")) || 0);
    if (!amount) return;
    const paymentMethod = (window.prompt("Forma de pago: efectivo, tarjeta o transferencia", "efectivo") || "efectivo").toLowerCase();
    await api(`/api/receivables/${row.id}/payments`, { method: "POST", body: JSON.stringify({ amount, payment_method: paymentMethod }) });
    toast("Cobro registrado correctamente."); await refreshReceivables();
  });
}

async function refreshReceivables() {
  const payload = await api("/api/receivables"); state.receivables = payload.receivables || [];
  $("#receivable-list").innerHTML = state.receivables.map((item) => `<article><div><strong>${escapeHtml(item.client_name)} · ${escapeHtml(item.en_ncf)}</strong><span>Vence ${escapeHtml(formatReceiptDate(item.due_date))} · ${escapeHtml(item.status)}</span></div><div><strong>${money.format(item.balance)}</strong>${item.status !== "pagada" ? `<button class="table-button" data-collect-receivable="${item.id}">Registrar cobro</button>` : ""}</div></article>`).join("") || `<div class="empty-state">No hay cuentas por cobrar.</div>`;
}

function bindReturns() {
  $("#return-source-invoice")?.addEventListener("change", loadReturnModuleItems);
  $("#return-create-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const items = Array.from($$("#return-create-items [data-return-module-product]:checked")).map((checkbox) => ({ product_id: checkbox.dataset.returnModuleProduct, quantity: Number($(`#return-create-items [data-return-module-quantity="${CSS.escape(checkbox.dataset.returnModuleProduct)}"]`).value || 0) }));
    if (!items.length) { toast("Selecciona al menos un artículo.", true); return; }
    const result = await api("/api/credit-notes", { method: "POST", body: JSON.stringify({
      source_invoice_id: Number($("#return-source-invoice").value), modification_code: "1",
      reason: $("#return-reason").value.trim(), expires_at: $("#return-expires-at").value,
      restock: $("#return-restock").checked, items,
    }) });
    toast(result.imecf_warning || "Devolución y nota de crédito registradas.", Boolean(result.imecf_warning));
    $("#return-create-form").reset(); $("#return-expires-at").value = defaultCreditExpiry(); await refreshReturns();
  });
}
async function loadReturnModuleItems() {
  const invoiceId = Number($("#return-source-invoice")?.value || 0); state.returnSourceItems = [];
  if (!invoiceId) { $("#return-create-items").innerHTML = `<div class="empty-state">Selecciona una factura.</div>`; return; }
  const payload = await api(`/api/invoices/${invoiceId}`); state.returnSourceItems = payload.invoice?.items || [];
  $("#return-create-items").innerHTML = state.returnSourceItems.map((item) => `<label class="credit-return-row"><input type="checkbox" data-return-module-product="${escapeHtml(item.product_id)}" checked /><span>${escapeHtml(item.name)}</span><input class="input" data-return-module-quantity="${escapeHtml(item.product_id)}" type="number" min="0.01" max="${Number(item.quantity)}" step="0.01" value="${Number(item.quantity)}" /><small>de ${Number(item.quantity).toLocaleString("es-DO")}</small></label>`).join("");
}
async function refreshReturns() {
  const [payload, invoicesPayload] = await Promise.all([api("/api/credit-notes"), api("/api/invoices?page=1&limit=100")]); state.creditNotes = payload.credit_notes || []; state.invoices = invoicesPayload.invoices || [];
  $("#return-source-invoice").innerHTML = `<option value="">Selecciona una factura aceptada</option>${state.invoices.filter((invoice) => invoice.provider_encf).map((invoice) => `<option value="${invoice.id}">${escapeHtml(invoice.provider_encf)} · ${escapeHtml(invoice.client_name || "Consumidor final")} · ${money.format(invoice.total)}</option>`).join("")}`;
  if (!$("#return-expires-at").value) $("#return-expires-at").value = defaultCreditExpiry();
  $("#return-note-list").innerHTML = state.creditNotes.map((note) => `<article><div><strong>${escapeHtml(note.provider_encf || note.en_ncf)}</strong><span>${escapeHtml(note.source_client_name || "Consumidor final")} · ${escapeHtml(note.credit_status || note.status)}</span></div><div><strong>${money.format(note.available_amount || 0)}</strong><span>Saldo disponible</span></div></article>`).join("") || `<div class="empty-state">No hay notas de crédito emitidas.</div>`;
}

async function loadCreditReturnItems() {
  const invoiceId = Number($("#credit-source-invoice")?.value || 0);
  state.creditSourceItems = [];
  if (!invoiceId) { $("#credit-return-items").innerHTML = `<div class="empty-state">Selecciona la factura original.</div>`; return; }
  const payload = await api(`/api/invoices/${invoiceId}`);
  state.creditSourceItems = payload.invoice?.items || [];
  $("#credit-return-items").innerHTML = state.creditSourceItems.map((item) => `<label class="credit-return-row"><input type="checkbox" data-return-product="${escapeHtml(item.product_id)}" checked /><span>${escapeHtml(item.name)}</span><input class="input" data-return-quantity="${escapeHtml(item.product_id)}" type="number" min="0.01" max="${Number(item.quantity)}" step="0.01" value="${Number(item.quantity)}" /><small>de ${Number(item.quantity).toLocaleString("es-DO")}</small></label>`).join("");
}

function bindCash() {
  $("#refresh-cash")?.addEventListener("click", refreshCash);
  $("#cash-open-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/api/cash-register/open", { method: "POST", body: JSON.stringify({ terminal_name: $("#cash-terminal-name").value.trim() || "Principal", opening_amount: Number($("#cash-opening-amount").value || 0), notes: $("#cash-opening-notes").value.trim() }) });
    $("#cash-open-form").reset();
    toast("Caja abierta correctamente.");
    await refreshCash();
  });
  $("#cash-movement-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/api/cash-register/movement", { method: "POST", body: JSON.stringify({ movement_type: $("#cash-movement-type").value, amount: Number($("#cash-movement-amount").value || 0), description: $("#cash-movement-description").value.trim() }) });
    $("#cash-movement-form").reset();
    toast("Movimiento de caja registrado.");
    await refreshCash();
  });
  $("#cash-close-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = await api("/api/cash-register/close", { method: "POST", body: JSON.stringify({ counted_cash: Number($("#cash-counted-amount").value || 0), notes: $("#cash-closing-notes").value.trim() }) });
    const difference = Number(result.session?.difference || 0);
    toast(`Caja cerrada. Diferencia: ${money.format(difference)}.`, Math.abs(difference) > 0.01);
    $("#cash-close-form").reset();
    await refreshCash();
  });
}

async function refreshCash() {
  if (!$("#cash-session-summary")) return;
  const payload = await api("/api/cash-register");
  state.cashSession = payload.session || { status: "sin_apertura" };
  state.cashHistory = payload.history || [];
  renderCash();
}

function renderCash() {
  const session = state.cashSession || { status: "sin_apertura" };
  const open = session.status === "abierta";
  $("#cash-open-form").hidden = open;
  $("#cash-close-form").hidden = !open;
  $("#cash-movement-form").querySelectorAll("input, select, button").forEach((element) => { element.disabled = !open; });
  $("#cash-action-title").textContent = open ? `Caja #${session.id} · ${session.terminal_name || "Principal"}` : "Abrir caja";
  const metrics = open || session.status === "cerrada" ? [
    ["Estado", open ? "Abierta" : "Cerrada"],
    ["Fondo inicial", money.format(session.opening_amount || 0)],
    ["Ventas en efectivo", money.format(session.cash_sales || 0)],
    ["Efectivo esperado", money.format(session.expected_cash || 0)],
    ["Comprobantes", session.invoice_count || 0],
  ] : [["Estado", "Sin apertura"], ["Fondo inicial", money.format(0)], ["Ventas en efectivo", money.format(0)], ["Efectivo esperado", money.format(0)], ["Comprobantes", 0]];
  $("#cash-session-summary").innerHTML = metrics.map(([label, value]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  $("#cash-payment-breakdown").innerHTML = (session.payments || []).map((row) => `<article><strong>${escapeHtml(paymentLabelFor(row.payment_method))}</strong><span>${money.format(row.amount)}</span></article>`).join("") || `<div class="empty-state">Este turno todavía no tiene pagos registrados.</div>`;
  $("#cash-movement-list").innerHTML = (session.movements || []).map((row) => `<article><strong>${row.movement_type === "entrada" ? "+" : "-"}${money.format(row.amount)} · ${escapeHtml(row.description)}</strong><span>${escapeHtml(row.user_name)} · ${escapeHtml(formatReceiptDateTime(row.created_at))}</span></article>`).join("") || `<div class="empty-state">Sin entradas o salidas manuales.</div>`;
  $("#cash-history").innerHTML = state.cashHistory.map((row) => {
    const difference = Number(row.difference || 0);
    return `<article><strong>Caja #${row.id} · ${escapeHtml(row.status)}</strong><span>${escapeHtml(formatReceiptDateTime(row.opened_at))}${row.closed_at ? ` → ${escapeHtml(formatReceiptDateTime(row.closed_at))}` : ""}</span><span>Esperado ${money.format(row.expected_cash || 0)} · Contado ${row.counted_cash == null ? "Pendiente" : money.format(row.counted_cash)} · <b class="${difference < 0 ? "cash-difference-negative" : "cash-difference-positive"}">Diferencia ${money.format(difference)}</b></span></article>`;
  }).join("") || `<div class="empty-state">Todavía no hay turnos de caja.</div>`;
}

async function issueCreditNote(event) {
  event.preventDefault();
  const sourceInvoiceId = Number($("#credit-source-invoice").value);
  if (!sourceInvoiceId) {
    toast("Selecciona la factura electrónica que será modificada.", true);
    return;
  }
  const button = $("#issue-credit-note");
  button.disabled = true;
  try {
    const items = Array.from($$("#credit-return-items [data-return-product]:checked")).map((checkbox) => ({ product_id: checkbox.dataset.returnProduct, quantity: Number($(`#credit-return-items [data-return-quantity="${CSS.escape(checkbox.dataset.returnProduct)}"]`).value || 0) }));
    if (!items.length) { toast("Selecciona al menos un artículo para devolver.", true); return; }
    const result = await api("/api/credit-notes", {
      method: "POST",
      body: JSON.stringify({
        source_invoice_id: sourceInvoiceId,
        modification_code: $("#credit-modification-code").value,
        reason: $("#credit-reason").value.trim(),
        expires_at: $("#credit-expires-at").value,
        items,
        restock: $("#credit-restock").checked,
      }),
    });
    toast(result.imecf_warning || `E34 ${result.credit_note.provider_encf || result.credit_note.en_ncf} procesado.`, Boolean(result.imecf_warning));
    $("#credit-note-form").reset();
    $("#credit-expires-at").value = defaultCreditExpiry();
    await refreshFiscal();
  } finally {
    button.disabled = false;
  }
}

function renderFiscalHealth(totals) {
  const metrics = [
    ["Documentos", totals.documents || 0],
    ["Aceptados", totals.accepted || 0],
    ["Con errores", totals.errors || 0],
    ["Solo locales", totals.local || 0],
    ["Secuencias disponibles", Number(totals.available_sequences || 0).toLocaleString("es-DO")],
  ];
  $("#fiscal-health").innerHTML = metrics
    .map(([label, value]) => `<article class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`)
    .join("");
}

function renderFiscalProvider(provider) {
  const badge = $("#provider-badge");
  badge.textContent = provider.active ? "Conectado" : provider.configured ? "Desactivado" : "Modo local";
  badge.className = `badge ${provider.active ? "ok" : "warning"}`;
  $("#provider-details").innerHTML = `
    <div><span>Proveedor actual</span><strong>${escapeHtml(provider.name || "Proveedor local")}</strong></div>
    <div><span>Ambiente</span><strong>${escapeHtml(provider.environment || "local")}</strong></div>
    <div><span>Modo</span><strong>${escapeHtml(provider.mode || "local")}</strong></div>
    <div><span>Credenciales</span><strong>${provider.configured ? "Configuradas" : "Pendientes"}</strong></div>
    <div class="provider-company"><span>Empresa IMECF</span><strong>${escapeHtml(provider.workspace_name || "UTESA")} · ${escapeHtml(provider.company_id || "Sin asignar")}</strong></div>
    <div class="provider-company"><span>Titular del certificado fiscal</span><strong>${escapeHtml(provider.issuer_name || "")} · RNC ${escapeHtml(provider.issuer_rnc || "")}</strong></div>
  `;
  $("#open-imecf-portal").href = provider.dashboard_url || "#";
}

function renderFiscalSequences(sequences) {
  $("#fiscal-sequences").innerHTML = sequences.map((sequence) => {
    const total = Math.max(1, Number(sequence.end_number));
    const used = Number(sequence.used || 0);
    const percent = Math.min(100, Math.round((used / total) * 100));
    return `
      <article class="sequence-card">
        <div class="sequence-title">
          <div><strong>e-CF ${escapeHtml(sequence.type_code)}</strong><span>${escapeHtml(sequence.description)}</span></div>
          <span class="badge ${sequence.state === "Activa" ? "ok" : "low"}">${escapeHtml(sequence.state)}</span>
        </div>
        <div class="sequence-progress"><i style="width:${percent}%"></i></div>
        <div class="sequence-stats">
          <span>Próximo <strong>${escapeHtml(sequence.prefix)}${String(sequence.current_number).padStart(10, "0")}</strong></span>
          <span>Disponibles <strong>${Number(sequence.available).toLocaleString("es-DO")}</strong></span>
          <span>Vence <strong>${escapeHtml(sequence.expires_at)}</strong></span>
        </div>
      </article>
    `;
  }).join("") || `<div class="empty-state">No hay secuencias configuradas.</div>`;
}

function renderFiscalDocuments() {
  const query = normalize($("#fiscal-search").value);
  const filter = state.fiscalFilter;
  const creditDocuments = state.creditNotes.map(normalizeCreditNoteDocument);
  const rows = [...state.remoteFiscalDocuments, ...state.fiscalDocuments, ...creditDocuments].filter((invoice) => {
    const status = invoice.api_error ? "ERROR" : normalize(invoice.api_status || "LOCAL").toUpperCase();
    const matchesFilter =
      filter === "ALL" ||
      filter === invoice.ecf_type ||
      (filter === "LOCAL" && !invoice.api_status && !invoice.api_error) ||
      (filter === "ERROR" && Boolean(invoice.api_error)) ||
      (filter === "ACCEPTED" && status.includes("ACEPT")) ||
      (filter === "PENDING" && (status.includes("PEND") || status.includes("ENV")));
    const haystack = normalize(`${invoice.provider_encf || invoice.en_ncf} ${invoice.client_name} ${invoice.rnc_cedula} ${invoice.api_status} ${invoice.api_error}`);
    return matchesFilter && (!query || haystack.includes(query));
  });
  $("#fiscal-documents").innerHTML = rows.map(fiscalDocumentCard).join("")
    || `<div class="empty-state">No hay documentos que coincidan con el filtro.</div>`;
  $("#fiscal-documents").querySelectorAll("[data-fiscal-action]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.fiscalAction === "detail") runRemoteFiscalLookup(button);
      else if (button.dataset.providerId) runRemoteFiscalAction(button);
      else runFiscalAction(button);
    });
  });
}

function normalizeCreditNoteDocument(note) {
  return {
    _creditNote: true,
    id: note.id,
    provider_document_id: note.provider_document_id || "",
    provider_encf: note.provider_encf || note.en_ncf || "",
    en_ncf: note.en_ncf || "",
    ecf_type: "34",
    client_name: note.client_name || "Cliente de factura original",
    rnc_cedula: note.rnc_cedula || "",
    total: Number(note.total || 0),
    api_status: note.api_status || note.status || "",
    api_error: note.api_error || "",
    track_id: note.track_id || "",
    issued_at: note.issued_at || "",
    source_encf: note.source_encf || "",
    reason: note.reason || "",
  };
}

function fiscalDocumentCard(invoice) {
  const encf = invoice.provider_encf || invoice.en_ncf;
  const status = invoice.api_error ? "Error IMECF" : invoice.api_status || "Documento local";
  const tone = invoice.api_error ? "low" : invoice.api_status ? "ok" : "";
  const providerActionId = invoice._remote || invoice._creditNote ? invoice.provider_document_id : "";
  const liveDiagnostic = providerActionId ? state.imecfDiagnostics[providerActionId] || "" : "";
  const xmlHref = providerActionId ? `/api/imecf/documents/${providerActionId}/xml` : `/api/invoices/${invoice.id}/xml`;
  return `
    <article class="fiscal-document">
      <div class="document-main">
        <div class="document-title">
          <strong>${escapeHtml(encf)}</strong>
          <span class="badge">e-CF ${escapeHtml(invoice.ecf_type)}</span>
          ${invoice._creditNote ? `<span class="badge warning">Nota de credito</span>` : ""}
          <span class="badge ${tone}">${escapeHtml(status)}</span>
        </div>
        <div class="document-data">
          <span>Cliente <strong>${escapeHtml(invoice.client_name)}</strong></span>
          <span>RNC/Cédula <strong>${escapeHtml(invoice.rnc_cedula || "No identificado")}</strong></span>
          <span>Total <strong>${money.format(invoice.total)}</strong></span>
          <span>Fecha <strong>${escapeHtml(formatDate(invoice.issued_at))}</strong></span>
        </div>
        ${invoice.source_encf ? `<p class="document-track">Factura afectada: ${escapeHtml(invoice.source_encf)}</p>` : ""}
        ${invoice.reason ? `<p class="document-track">Motivo: ${escapeHtml(invoice.reason)}</p>` : ""}
        ${invoice.track_id ? `<p class="document-track">TrackId: ${escapeHtml(invoice.track_id)}</p>` : ""}
        ${invoice.api_error ? `<p class="notice-error">${escapeHtml(invoice.api_error)}</p>` : ""}
        ${liveDiagnostic ? `<p class="notice-error">Detalle IMECF: ${escapeHtml(liveDiagnostic)}</p>` : ""}
      </div>
      <div class="document-actions">
        <a class="table-button" href="${xmlHref}" target="_blank" rel="noreferrer">XML</a>
        ${invoice.provider_document_id ? `
          <button class="table-button" data-fiscal-action="status" data-invoice-id="${invoice.id || ""}" data-provider-id="${providerActionId}">Consultar estado</button>
          <button class="table-button" data-fiscal-action="detail" data-provider-id="${providerActionId}" data-encf="${escapeHtml(encf)}">Ver detalle</button>
          ${invoice.dgii_url
            ? `<a class="table-button" href="${escapeHtml(invoice.dgii_url)}" target="_blank" rel="noreferrer">DGII TesteCF</a>`
            : invoice.track_id
              ? `<button class="table-button" data-fiscal-action="track" data-invoice-id="${invoice.id || ""}" data-provider-id="${providerActionId}">Rastrear</button>`
              : `<span class="muted-text">Sin trackId; usa Estado</span>`}
        ` : `<span class="muted-text">Pendiente de enlace IMECF</span>`}
      </div>
    </article>
  `;
}

async function syncFiscalDocuments() {
  if (!state.imecfConfigured) {
    toast("Configura IMECF para sincronizar documentos remotos.", true);
    return;
  }
  const button = $("#fiscal-sync-documents");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Sincronizando...";
  try {
    const payload = await api("/api/imecf/documents?page=1&limit=100");
    state.remoteFiscalDocuments = (payload.data || []).map(normalizeRemoteDocument);
    toast(`${state.remoteFiscalDocuments.length} documentos remotos sincronizados.`);
    renderFiscalDocuments();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function normalizeRemoteDocument(document) {
  return {
    _remote: true,
    id: "",
    provider_document_id: document.id || "",
    provider_encf: document.encf || document.eNCF || "",
    en_ncf: document.encf || document.eNCF || "",
    ecf_type: String(document.tipoEcf || document.tipoECF || "").replace(/^E/, ""),
    client_name: document.razonSocialComprador || document.comprador?.razonSocial || "Cliente IMECF",
    rnc_cedula: document.rncComprador || document.comprador?.rnc || "",
    total: Number(document.montoTotal || document.total || 0),
    api_status: document.estado || document.status || "Remoto",
    api_error: document.errorMessage || "",
    track_id: document.trackId || "",
    dgii_url: document.dgiiUrl || document.dgii_url || "",
    issued_at: document.createdAt || document.fechaEmision || "",
  };
}

async function runRemoteFiscalAction(button) {
  const action = button.dataset.fiscalAction;
  const providerId = button.dataset.providerId;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "...";
  try {
    const result = await api(`/api/imecf/documents/${providerId}/${action}`);
    const status = result.estado || result.status || "consulta completada";
    const diagnostic = imecfDiagnostic(result);
    const rejected = normalize(status).includes("rechaz") || Boolean(diagnostic);
    const summary = `${status}${diagnostic ? ` · ${diagnostic}` : ""}`;
    state.imecfDiagnostics[providerId] = summary;
    toast(`IMECF: ${summary}`, rejected);
    await syncFiscalDocuments();
    renderFiscalDocuments();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function defaultCreditExpiry() {
  const expiry = new Date();
  expiry.setDate(expiry.getDate() + 90);
  return expiry.toISOString().slice(0, 10);
}

async function openCreditVoucher(noteId) {
  const payload = await api(`/api/credit-notes/${noteId}`);
  const note = payload.credit_note;
  const encf = note.provider_encf || note.en_ncf;
  $("#dialog-eyebrow").textContent = "Comprobante de nota de crédito";
  $("#dialog-ncf").textContent = encf;
  $("#xml-link").hidden = !note.provider_document_id;
  if (note.provider_document_id) $("#xml-link").href = `/api/imecf/documents/${encodeURIComponent(note.provider_document_id)}/xml`;
  $("#issue-dialog-preinvoice").hidden = true;
  $("#invoice-preview").innerHTML = `
    <section class="aux-receipt credit-voucher">
      <header class="aux-fiscal-header"><div class="aux-issuer-card"><img class="aux-company-logo" src="/static/logo-ahg.png" alt="AHG Construferret" /><div><h3>AHG CONSTRUFERRET</h3><strong>${escapeHtml(state.fiscalIssuer.name || "")}</strong><br /><strong>RNC:</strong> ${escapeHtml(formatFiscalId(state.fiscalIssuer.rnc || ""))}<br /><strong>Fecha de emisión:</strong> ${escapeHtml(formatReceiptDate(note.issued_at))}</div></div><div class="aux-document-card"><h4>Nota de Crédito Electrónica</h4><strong>e-NCF:</strong> ${escapeHtml(encf)}<br /><strong>Estado:</strong> ${escapeHtml(note.api_status || note.status)}</div></header>
      <section class="aux-buyer-card"><strong>Cliente:</strong> ${escapeHtml(note.client_name || "Consumidor Final")}<br /><strong>RNC/Cédula:</strong> ${escapeHtml(formatFiscalId(note.rnc_cedula || "")) || "No identificado"}</section>
      <div class="credit-voucher-meta"><div><span>Comprobante afectado</span><strong>${escapeHtml(note.source_encf)}</strong></div><div><span>Motivo</span><strong>${escapeHtml(note.reason)}</strong></div><div><span>Monto original del crédito</span><strong>${money.format(note.total)}</strong></div><div><span>Saldo disponible</span><strong>${money.format(note.available_amount)}</strong></div><div><span>Vigencia comercial</span><strong>${escapeHtml(formatReceiptDate(note.expires_at))}</strong></div><div><span>Aplicado</span><strong>${money.format(note.applied_amount || 0)}</strong></div></div>
      <p class="section-copy">La vigencia mostrada controla el canje del saldo en este POS. La secuencia fiscal E34 no lleva fecha de vencimiento ante la DGII.</p>
      <footer class="aux-fiscal-footer">Sin validez fiscal.</footer>
    </section>`;
  const dialog = $("#invoice-dialog");
  if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "open");
}

async function runRemoteFiscalLookup(button) {
  const providerId = button.dataset.providerId;
  const encf = button.dataset.encf;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "...";
  try {
    const result = await api(`/api/imecf/by-encf/${encodeURIComponent(encf)}`);
    const status = result.estado || result.status || "detalle consultado";
    const diagnostic = imecfDiagnostic(result);
    const summary = `${status}${diagnostic ? ` · ${diagnostic}` : ""}`;
    state.imecfDiagnostics[providerId] = summary;
    toast(`IMECF: ${summary}`, normalize(status).includes("rechaz"));
    renderFiscalDocuments();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function imecfDiagnostic(result) {
  const messages = [];
  const diagnosticKey = /(error|mensaje|message|detail|detalle|motivo|razon|rechaz|validacion|validation|descripcion)/i;
  function visit(value, key = "", depth = 0) {
    if (depth > 6 || value == null) return;
    if (Array.isArray(value)) {
      value.forEach((item) => visit(item, key, depth + 1));
      return;
    }
    if (typeof value === "object") {
      Object.entries(value).forEach(([childKey, child]) => visit(child, childKey, depth + 1));
      return;
    }
    if (diagnosticKey.test(key) && String(value).trim()) messages.push(String(value).trim());
  }
  visit(result);
  return [...new Set(messages)].join(" · ").slice(0, 600);
}

async function testImecfConnection() {
  const button = $("#test-imecf");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Probando...";
  try {
    const result = await api("/api/imecf/connection");
    toast(result.message, !result.ok);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function bindDialog() {
  $("#close-dialog").addEventListener("click", () => $("#invoice-dialog").close());
  $("#print-invoice").addEventListener("click", () => window.print());
  $("#issue-dialog-preinvoice").addEventListener("click", async () => {
    const id = $("#issue-dialog-preinvoice").dataset.preinvoiceId;
    if (id) await issuePreinvoice(id);
  });
}

async function refreshProducts(page = 1) {
  const query = $("#product-search").value.trim();
  const payload = await api(`/api/products?page=${page}&limit=25&q=${encodeURIComponent(query)}`);
  state.products = payload.products || [];
  state.productPagination = payload.pagination || null;
  renderProducts();
  renderInventory();
  renderPager("product-list", state.productPagination, (nextPage) => refreshProducts(nextPage));
}

async function refreshReports() {
  await Promise.all([refreshInvoicePage(1), refreshManagementReport()]);
}

async function refreshManagementReport() {
  if (!$("#management-report-totals")) return;
  const today = new Date();
  const startDefault = new Date(today); startDefault.setDate(today.getDate() - 29);
  if (!$("#report-end").value) $("#report-end").value = today.toISOString().slice(0, 10);
  if (!$("#report-start").value) $("#report-start").value = startDefault.toISOString().slice(0, 10);
  const payload = await api(`/api/reports/management?start=${encodeURIComponent($("#report-start").value)}&end=${encodeURIComponent($("#report-end").value)}`);
  state.managementReport = payload.report;
  renderManagementReport();
}

function renderManagementReport() {
  const report = state.managementReport || { totals: {}, payments: [], top_products: [] };
  const totals = report.totals || {};
  $("#management-report-totals").innerHTML = [
    ["Ventas", money.format(totals.sales || 0)], ["Comprobantes", totals.invoice_count || 0],
    ["Margen estimado", money.format(totals.estimated_margin || 0)], ["ITBIS", money.format(totals.tax || 0)],
    ["Descuentos", money.format(totals.discounts || 0)], ["Notas de crédito", money.format(totals.credits || 0)],
  ].map(([label, value]) => `<article class="summary-card"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></article>`).join("");
  $("#management-payment-list").innerHTML = (report.payments || []).map((row) => `<article><strong>${escapeHtml(paymentLabelFor(row.payment_method))}</strong><span>${money.format(row.amount)}</span></article>`).join("") || `<div class="empty-state">Sin pagos en el período.</div>`;
  $("#management-product-list").innerHTML = (report.top_products || []).slice(0, 5).map((row) => `<article><strong>${escapeHtml(row.name)}</strong><span>${Number(row.quantity || 0)} uds. · ${money.format(row.total)}</span></article>`).join("") || `<div class="empty-state">Sin ventas en el período.</div>`;
}

async function refreshInvoicePage(page = 1) {
  const payload = await api(`/api/invoices?page=${page}&limit=25`);
  state.invoices = payload.invoices || [];
  state.invoicePagination = payload.pagination || null;
  renderReports(payload.invoices, payload.summary);
  renderCreditNotes();
  renderPager("invoice-table", state.invoicePagination, (nextPage) => refreshInvoicePage(nextPage));
}

function renderProducts() {
  const list = $("#product-list");
  const rows = state.products.filter((product) => {
    if (!product.active) return false;
    return true;
  });
  list.innerHTML = rows.map(productRow).join("") || `<div class="empty-state">Sin coincidencias</div>`;
  list.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", () => addToCart(button.dataset.add));
  });
}

function renderPager(targetId, pagination, onPage) {
  const target = document.getElementById(targetId);
  if (!target || !pagination) return;
  let pager = document.getElementById(`${targetId}-pagination`) || target.parentElement.querySelector(`[data-pager-for="${targetId}"]`);
  if (!pager) {
    pager = document.createElement("div");
    pager.dataset.pagerFor = targetId;
    pager.className = "pagination-controls";
    target.parentElement.appendChild(pager);
  }
  pager.innerHTML = `
    <button class="secondary-button compact" ${pagination.has_previous ? "" : "disabled"} data-page-prev>Anterior</button>
    <span>Página ${pagination.page} de ${pagination.pages} · ${pagination.total} registros</span>
    <button class="secondary-button compact" ${pagination.has_next ? "" : "disabled"} data-page-next>Siguiente</button>
  `;
  pager.querySelector("[data-page-prev]")?.addEventListener("click", () => onPage(pagination.page - 1));
  pager.querySelector("[data-page-next]")?.addEventListener("click", () => onPage(pagination.page + 1));
}

function productRow(product) {
  const stockClass = Number(product.stock) <= Number(product.min_stock) ? "low" : "ok";
  return `
    <article class="product-row">
      <div>
        <h3>${escapeHtml(product.name)}</h3>
        <div class="product-meta">
          <span class="badge">${escapeHtml(product.sku)}</span>
          <span class="badge">${escapeHtml(product.category)}</span>
          <span class="badge ${stockClass}">Stock ${formatQty(product.stock)}</span>
          <span class="badge">${money.format(product.price)}</span>
        </div>
      </div>
      <button class="add-button" data-add="${escapeHtml(product.id)}" title="Agregar">+</button>
    </article>
  `;
}

function addToCart(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;
  const line = state.cart.find((item) => item.product_id === productId);
  if (line) {
    if (line.quantity + 1 > Number(product.stock)) {
      toast("No hay más existencia disponible.", true);
      return;
    }
    line.quantity += 1;
  } else {
    state.cart.push({
      product_id: product.id,
      name: product.name,
      unit_price: Number(product.price),
      discount_percent: 0,
      tax_rate: Number(product.tax_rate),
      stock: Number(product.stock),
      quantity: 1,
    });
  }
  renderCart();
  toast("Artículo agregado.");
}

function renderCart() {
  const list = $("#cart-list");
  if (!state.cart.length) {
    list.className = "cart-list empty-state";
    list.innerHTML = "Sin artículos";
  } else {
    list.className = "cart-list";
    list.innerHTML = state.cart.map(cartRow).join("");
    list.querySelectorAll("[data-dec]").forEach((button) => button.addEventListener("click", () => changeQty(button.dataset.dec, -1)));
    list.querySelectorAll("[data-inc]").forEach((button) => button.addEventListener("click", () => changeQty(button.dataset.inc, 1)));
    list.querySelectorAll("[data-price]").forEach((input) => input.addEventListener("change", () => changeLinePrice(input.dataset.price, input.value)));
    list.querySelectorAll("[data-line-discount]").forEach((input) => input.addEventListener("change", () => changeLineDiscount(input.dataset.lineDiscount, input.value)));
  }
  renderTotals();
}

function cartRow(line) {
  return `
    <article class="cart-row">
      <div>
        <h3>${escapeHtml(line.name)}</h3>
        <div class="line-meta">
          <label class="line-price">Precio <input data-price="${escapeHtml(line.product_id)}" type="number" min="0" step="0.01" value="${Number(line.unit_price).toFixed(2)}" /></label>
          <label class="line-price">Desc. % <input data-line-discount="${escapeHtml(line.product_id)}" type="number" min="0" max="100" step="0.01" value="${Number(line.discount_percent || 0).toFixed(2)}" /></label>
          <span>ITBIS ${Math.round(line.tax_rate * 100)}%</span>
        </div>
      </div>
      <div class="qty-controls">
        <button class="qty-button danger" data-dec="${escapeHtml(line.product_id)}" title="Restar">−</button>
        <strong>${formatQty(line.quantity)}</strong>
        <button class="qty-button" data-inc="${escapeHtml(line.product_id)}" title="Sumar">+</button>
      </div>
    </article>
  `;
}

function changeQty(productId, delta) {
  const line = state.cart.find((item) => item.product_id === productId);
  if (!line) return;
  line.quantity += delta;
  if (line.quantity <= 0) {
    state.cart = state.cart.filter((item) => item.product_id !== productId);
  }
  if (line.quantity > line.stock) {
    line.quantity = line.stock;
    toast("Stock máximo alcanzado.", true);
  }
  renderCart();
}

function changeLinePrice(productId, value) {
  const line = state.cart.find((item) => item.product_id === productId);
  if (!line) return;
  line.unit_price = Math.max(0, Number(value || 0));
  state.paypalPayment = null;
  renderTotals();
}

function changeLineDiscount(productId, value) {
  const line = state.cart.find((item) => item.product_id === productId);
  if (!line) return;
  line.discount_percent = Math.min(100, Math.max(0, Number(value || 0)));
  state.paypalPayment = null;
  renderCart();
}

function cartTotals() {
  const grossSubtotal = state.cart.reduce((sum, item) => sum + item.unit_price * item.quantity, 0);
  const itemDiscount = state.cart.reduce((sum, item) => sum + lineDiscountAmount(item), 0);
  const baseAfterItems = Math.max(0, grossSubtotal - itemDiscount);
  const generalDiscountPercent = Math.min(100, Math.max(0, Number($("#general-discount")?.value || 0)));
  const generalDiscount = baseAfterItems * generalDiscountPercent / 100;
  const discountTotal = itemDiscount + generalDiscount;
  const taxableSubtotal = Math.max(0, baseAfterItems - generalDiscount);
  const tax = state.cart.reduce((sum, item) => {
    const lineBase = Math.max(0, item.unit_price * item.quantity - lineDiscountAmount(item));
    const share = baseAfterItems > 0 ? (lineBase / baseAfterItems) * generalDiscount : 0;
    return sum + Math.max(0, lineBase - share) * item.tax_rate;
  }, 0);
  return {
    grossSubtotal,
    discountTotal,
    taxableSubtotal,
    tax,
    total: taxableSubtotal + tax,
    generalDiscount,
    generalDiscountPercent,
  };
}

function lineDiscountAmount(item) {
  return Math.max(0, item.unit_price * item.quantity) * Math.min(100, Math.max(0, Number(item.discount_percent || 0))) / 100;
}

function percentFromAmount(amount, base) {
  const numericBase = Number(base || 0);
  if (numericBase <= 0) return 0;
  return Math.min(100, Math.max(0, (Number(amount || 0) / numericBase) * 100));
}

function preinvoiceBaseAfterItemDiscounts(draft) {
  return (draft.items || []).reduce((sum, item) => {
    const gross = Number(item.unit_price || 0) * Number(item.quantity || 0);
    return sum + Math.max(0, gross - Number(item.discount_amount || 0));
  }, 0);
}

function renderTotals() {
  const totals = cartTotals();
  $("#subtotal").textContent = money.format(totals.grossSubtotal);
  $("#discount-total").textContent = money.format(totals.discountTotal);
  $("#tax").textContent = money.format(totals.tax);
  $("#total").textContent = money.format(totals.total);
  const credit = effectiveCreditAmount();
  $("#credit-applied").textContent = `-${money.format(credit)}`;
  $("#credit-applied-row").hidden = credit <= 0;
  $("#amount-due").textContent = money.format(Math.max(0, totals.total - credit));
  $("#amount-due-row").hidden = credit <= 0;
  renderCreditPaymentPlan();
  renderBuyerRequirement();
  renderSplitPayment();
  if (!$("#split-payment-enabled")?.checked) renderOnlinePaymentStatus();
}

async function issueInvoice() {
  if (!state.cart.length) {
    toast("Agrega al menos un artículo.", true);
    return;
  }
  const client = selectedClientPayload();
  const total = cartTotals().total;
  if ((state.ecfType === "31" || (state.ecfType === "32" && total >= 250000)) && !client.rnc_cedula) {
    toast(state.ecfType === "31" ? "No se abre el portal: el e-CF 31 requiere RNC o cedula antes del pago." : "No se abre el portal: este e-CF 32 requiere RNC o cedula por su monto.", true);
    return;
  }
  const clientError = validateSaleClientPayload(client, total);
  if (clientError) {
    toast(clientError, true);
    return;
  }
  const paymentMethod = $("#payment-method").value;
  const requestedCredit = requestedCreditAmount();
  if (requestedCredit > 0) {
    if (!client.id) {
      toast("Selecciona un cliente registrado para aplicar la nota de crédito.", true);
      return;
    }
    await refreshCreditAvailability();
    if (requestedCredit > Number(state.availableCredit || 0) + 0.001) {
      toast(`Crédito insuficiente. Disponible: ${money.format(state.availableCredit)}.`, true);
      return;
    }
    if (requestedCredit > total + 0.001) {
      toast("El crédito no puede superar el total de la venta.", true);
      return;
    }
    if (paymentMethod === "credito" && requestedCredit < total - 0.001) {
      toast("Selecciona una forma de pago inmediata para el monto restante.", true);
      return;
    }
  }
  const payableTotal = Math.max(0, Math.round((total - requestedCredit) * 100) / 100);
  let payments = [];
  try {
    payments = paymentRowsFromForm();
  } catch (exception) {
    toast(exception.message, true);
    return;
  }
  const onlineRows = payments.filter((row) => ["tarjeta", "paypal"].includes(row.payment_method));
  if (onlineRows.length > 1) {
    toast("Usa solo una forma electrónica por venta mixta.", true);
    return;
  }
  if (onlineRows.length === 1) {
    const onlinePayment = onlineRows[0];
    const paidTotal = Number(state.paypalPayment?.amount_dop || 0);
    if (onlinePayment.amount > 0 && (state.paypalPayment?.method !== onlinePayment.payment_method || Math.abs(paidTotal - onlinePayment.amount) > 0.01)) {
      await openPaymentGateway(onlinePayment.payment_method, onlinePayment.amount);
      return;
    }
  }
  const payload = {
    ecf_type: state.ecfType,
    client,
    payment_method: paymentMethod,
    payments,
    general_discount_percent: cartTotals().generalDiscountPercent,
    credit_amount: requestedCredit,
    credit_note_code: $("#credit-note-code").value.trim().toUpperCase(),
    due_date: $("#sale-due-date").value,
    manager_identifier: $("#manager-identifier").value.trim(),
    manager_password: $("#manager-password").value,
    items: state.cart.map((item) => ({ product_id: item.product_id, quantity: item.quantity, unit_price: item.unit_price, discount_percent: Number(item.discount_percent || 0) })),
  };
  const button = $("#issue-invoice");
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = state.imecfActive ? "Enviando a IMECF..." : "Procesando...";
  try {
    if (state.currentPreinvoiceId) {
      await api(`/api/preinvoices/${state.currentPreinvoiceId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    }
    const endpoint = state.currentPreinvoiceId ? `/api/preinvoices/${state.currentPreinvoiceId}/issue` : "/api/invoices";
    const result = await api(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await finishIssuedInvoice(result);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

function renderOnlinePaymentStatus() {
  const box = $("#online-payment-status");
  const button = $("#open-payment-gateway");
  let online = null;
  try { online = paymentRowsFromForm().find((row) => ["tarjeta", "paypal"].includes(row.payment_method)); } catch (_) { online = null; }
  const method = online?.payment_method || "";
  const payableTotal = Number(online?.amount || 0);
  if (!online || payableTotal <= 0) {
    box.hidden = true;
    button.hidden = true;
    return;
  }
  box.hidden = false;
  button.hidden = false;
  button.textContent = method === "tarjeta" ? "Ingresar tarjeta de forma segura" : "Abrir PayPal";
  if (state.paypalPayment?.method === method) {
    box.className = "online-payment-status paid";
    box.textContent = `Pago confirmado por PayPal · Orden ${state.paypalPayment.order_id}`;
  } else {
    box.className = "online-payment-status";
    box.textContent = state.paypal?.configured
      ? "El cobro se abrirá al emitir el comprobante."
      : "Pasarela PayPal Sandbox pendiente de credenciales.";
  }
}

async function loadPayPalSdk() {
  if (window.paypal) return window.paypal;
  if (state.paypalSdkPromise) return state.paypalSdkPromise;
  const config = state.paypal;
  state.paypalSdkPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(config.client_id)}&currency=${encodeURIComponent(config.currency)}&components=buttons,card-fields`;
    script.onload = () => resolve(window.paypal);
    script.onerror = () => reject(new Error("No fue posible cargar la pasarela de PayPal."));
    document.head.appendChild(script);
  });
  return state.paypalSdkPromise;
}

async function createPayPalOrder(total) {
  const result = await api("/api/payments/paypal/order", {
    method: "POST",
    body: JSON.stringify({
      amount_dop: total,
      description: `Venta ${state.ecfType === "31" ? "E31" : "E32"} AHG CONSTRUFERRET`,
    }),
  });
  return result.order.id;
}

async function capturePayPalOrder(orderId, method, total) {
  const endpoint = state.paypal?.no_charge ? "authorize" : "capture";
  const result = await api(`/api/payments/paypal/${encodeURIComponent(orderId)}/${endpoint}`, {
    method: "POST",
    body: "{}",
  });
  state.paypalPayment = {
    order_id: orderId,
    method,
    amount_dop: total,
    capture: result.capture || null,
    authorization: result.authorization || null,
    no_charge: Boolean(state.paypal?.no_charge),
  };
  $("#payment-dialog").close();
  renderOnlinePaymentStatus();
  toast("Pago confirmado. Emitiendo comprobante...");
  await issueInvoice();
}

async function openPaymentGateway(method, total) {
  const dialog = $("#payment-dialog");
  $("#payment-dialog-title").textContent = method === "tarjeta" ? "Pagar con tarjeta" : "Pagar con PayPal";
  $("#payment-conversion").textContent = state.paypal?.currency === "USD"
    ? `${money.format(total)} · PayPal cobrará aproximadamente USD ${(total / Number(state.paypal.dop_per_usd || 60)).toFixed(2)}`
    : money.format(total);
  $("#paypal-not-configured").hidden = Boolean(state.paypal?.configured);
  $("#paypal-button-container").innerHTML = "";
  $("#card-field-container").hidden = method !== "tarjeta";
  $("#paypal-button-container").hidden = method !== "paypal";
  dialog.showModal();
  if (!state.paypal?.configured) return;

  const paypal = await loadPayPalSdk();
  const createOrder = () => createPayPalOrder(total);
  const onApprove = (data) => capturePayPalOrder(data.orderID, method, total);
  const onError = (error) => toast(error.message || "El pago no pudo completarse.", true);

  if (method === "paypal") {
    await paypal.Buttons({
      style: { layout: "vertical", shape: "rect", label: "paypal" },
      createOrder,
      onApprove,
      onCancel: () => toast("Pago cancelado.", true),
      onError,
    }).render("#paypal-button-container");
    return;
  }

  if (!paypal.CardFields) {
    $("#card-field-container").innerHTML = '<div class="payment-warning">El formulario de tarjeta no está habilitado para esta cuenta PayPal.</div>';
    return;
  }
  const cardFields = paypal.CardFields({ createOrder, onApprove, onError });
  if (!cardFields.isEligible()) {
    $("#card-field-container").innerHTML = '<div class="payment-warning">El formulario de tarjeta no está habilitado para esta cuenta PayPal.</div>';
    return;
  }
  if (cardFields.NameField) cardFields.NameField().render("#card-name-field-container");
  cardFields.NumberField().render("#card-number-field-container");
  cardFields.ExpiryField().render("#card-expiry-field-container");
  cardFields.CVVField().render("#card-cvv-field-container");
  $("#card-field-submit").onclick = () => cardFields.submit();
}

async function savePreinvoice() {
  const client = selectedClientPayload();
  const clientError = validateSaleClientPayload(client, cartTotals().total);
  if (clientError) {
    toast(clientError, true);
    return;
  }
  const payload = {
    ecf_type: state.ecfType,
    client,
    payment_method: $("#payment-method").value,
    notes: $("#sale-notes").value.trim(),
    general_discount_percent: cartTotals().generalDiscountPercent,
    items: state.cart.map((item) => ({
      product_id: item.product_id,
      quantity: item.quantity,
      unit_price: item.unit_price,
      discount_percent: Number(item.discount_percent || 0),
    })),
  };
  const id = state.currentPreinvoiceId;
  const result = await api(id ? `/api/preinvoices/${id}` : "/api/preinvoices", {
    method: id ? "PUT" : "POST",
    body: JSON.stringify(payload),
  });
  state.currentPreinvoiceId = Number(result.preinvoice.id);
  await refreshPreinvoices();
  await refreshReports();
  toast(`Pre-Factura #${result.preinvoice.id} guardada por ${money.format(result.preinvoice.total)}.`);
}

async function finishIssuedInvoice(result) {
  state.cart = [];
  state.currentPreinvoiceId = null;
  state.paypalPayment = null;
  $("#sale-notes").value = "";
  $("#general-discount").value = "0";
  $("#split-payment-enabled").checked = false;
  $("#primary-payment-amount").value = "";
  renderSplitPayment();
  resetCreditRedemption();
  renderCart();
  renderOnlinePaymentStatus();
  await refreshProducts();
  await refreshPreinvoices();
  await refreshReports();
  await refreshClients();
  await refreshFiscal();
  showInvoice(result.invoice, result.imecf_warning);
}

async function runAssistant() {
  const query = cleanAiInput($("#ai-query").value);
  if (!query) {
    toast("Escribe la necesidad del cliente.", true);
    return;
  }
  $("#ai-query").value = query;
  const results = $("#ai-results");
  results.innerHTML = `<div class="empty-state">Buscando articulos...</div>`;
  const budget = parseFormattedMoney($("#ai-budget").value);
  const payload = await api("/api/recommend", {
    method: "POST",
    body: JSON.stringify({
      query,
      limit: Number($("#ai-limit").value || 6),
      budget: budget > 0 ? budget : null,
    }),
  });
  const rows = payload.recommendations || [];
  renderAiGuidance(payload.guidance || {}, rows.length);
  results.innerHTML = rows.map(recommendationRow).join("") || noRecommendationState(payload.guidance || {});
  results.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", () => {
      addToCart(button.dataset.add);
      button.classList.add("added");
      button.textContent = "\u2713";
      button.title = "Agregado a la Pre-Factura";
    });
  });
  results.querySelectorAll("[data-ai-suggestion]").forEach((button) => {
    button.addEventListener("click", () => {
      $("#ai-query").value = cleanAiInput(button.dataset.aiSuggestion);
      runAssistant();
    });
  });
}

const AI_SPELLING_FIXES = new Map([
  ["acttualizar", "actualizar"],
  ["arituclos", "articulos"],
  ["articulos", "articulos"],
  ["busqeda", "busqueda"],
  ["bucqueda", "busqueda"],
  ["calinte", "caliente"],
  ["conctreto", "concreto"],
  ["exitencia", "existencia"],
  ["exixtencia", "existencia"],
  ["fugga", "fuga"],
  ["humeda", "humeda"],
  ["instalacion", "instalacion"],
  ["plomeria", "plomeria"],
  ["prefactura", "Pre-Factura"],
  ["proteccion", "proteccion"],
  ["tuberia", "tuberia"],
]);

function cleanAiInput(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text
    .split(/(\W+)/u)
    .map((part) => {
      const key = normalizePlain(part);
      if (!key || !AI_SPELLING_FIXES.has(key)) return part;
      const replacement = AI_SPELLING_FIXES.get(key);
      return part === part.toUpperCase() ? replacement.toUpperCase() : replacement;
    })
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizePlain(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function parseFormattedMoney(value) {
  return Number(String(value || "").replace(/,/g, "")) || 0;
}

function formatMoneyInput(event) {
  const input = event.target;
  const raw = String(input.value || "").replace(/[^\d.]/g, "");
  if (!raw) {
    input.value = "";
    return;
  }
  const [wholeRaw, decimalRaw = ""] = raw.split(".");
  const whole = Number(wholeRaw || 0).toLocaleString("en-US");
  input.value = raw.includes(".") ? `${whole}.${decimalRaw.slice(0, 2)}` : whole;
}

function renderAiGuidance(guidance, resultCount) {
  const box = $("#ai-guidance");
  if (!box) return;
  const summary = guidance.result_summary || (resultCount
    ? `Encontr\u00e9 ${resultCount} ${resultCount === 1 ? "art\u00edculo" : "art\u00edculos"}.`
    : "No encontr\u00e9 art\u00edculos disponibles.");
  box.innerHTML = `
    <span class="ai-summary-mark" aria-hidden="true">IA</span>
    <strong>${escapeHtml(summary)}</strong>
  `;
}

function noRecommendationState(guidance) {
  return `
    <div class="empty-state ai-empty-state">
      <strong>No encontr\u00e9 art\u00edculos disponibles</strong>
      <span>Prueba escribiendo el nombre, uso o medida del art\u00edculo.</span>
    </div>
  `;
}

function recommendationRow(product) {
  return `
    <article class="recommendation">
      <div>
        <h3>${escapeHtml(product.name)}</h3>
        <p>${escapeHtml(product.reason)}</p>
        <div class="product-meta">
          <span class="badge">${money.format(product.price)}</span>
          <span class="badge ok">Stock ${formatQty(product.stock)}</span>
          <span class="badge">${escapeHtml(product.category)}</span>
        </div>
      </div>
      <button class="add-button" data-add="${escapeHtml(product.id)}" title="Agregar a la Pre-Factura">+</button>
    </article>
  `;
}

function renderInventory() {
  const alerts = state.products.filter((item) => item.active && Number(item.stock) <= Number(item.min_stock));
  $("#stock-alerts").innerHTML = alerts.length
    ? alerts.slice(0, 9).map((item) => `<article class="alert-card"><strong>${escapeHtml(item.name)}</strong><span>Baja existencia: stock ${formatQty(item.stock)} / minimo ${formatQty(item.min_stock)}</span></article>`).join("")
    : `<article class="alert-card"><strong>Inventario estable</strong><span>Sin articulos por debajo del minimo.</span></article>`;
  $("#inventory-table").innerHTML = state.products
    .map((item) => {
      const badge = Number(item.stock) <= Number(item.min_stock) ? "low" : "ok";
      return `
        <tr>
          <td>${escapeHtml(item.sku)}</td>
          <td>${escapeHtml(item.name)}<span class="table-subtitle">${escapeHtml(item.location || "")}</span></td>
          <td>${escapeHtml(item.category)}</td>
          <td>${money.format(item.price)}</td>
          <td>
            <div class="inventory-stock-editor">
              <input class="inventory-stock-input" data-inventory-stock="${escapeHtml(item.id)}" type="number" min="0" step="0.001" value="${Number(item.stock || 0)}" />
              <span class="badge ${badge}">min. ${formatQty(item.min_stock)}</span>
            </div>
          </td>
          <td><button class="table-button" type="button" data-save-stock="${escapeHtml(item.id)}">Guardar</button></td>
        </tr>
      `;
    })
    .join("");
  $("#inventory-table").querySelectorAll("[data-save-stock]").forEach((button) => {
    button.addEventListener("click", () => updateInventoryStock(button.dataset.saveStock));
  });
}

async function updateInventoryStock(productId) {
  const product = state.products.find((item) => String(item.id) === String(productId));
  const input = Array.from(document.querySelectorAll("[data-inventory-stock]"))
    .find((field) => String(field.dataset.inventoryStock) === String(productId));
  if (!product || !input) return;
  const stock = Math.max(0, Number(input.value || 0));
  const payload = {
    id: product.id,
    name: product.name,
    sku: product.sku,
    barcode: product.barcode || "",
    brand: product.brand || "",
    unit_name: product.unit_name || "unidad",
    location: product.location || "",
    supplier: product.supplier || "",
    category: product.category,
    cost: Number(product.cost || 0),
    price: Number(product.price || 0),
    tax_rate: Number(product.tax_rate || 0) > 1 ? Number(product.tax_rate || 0) : Number(product.tax_rate || 0) * 100,
    stock,
    min_stock: Number(product.min_stock || 0),
    technical_description: product.technical_description || "",
    tags: product.tags || "",
    active: Boolean(product.active),
  };
  await api(`/api/products/${encodeURIComponent(productId)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  await refreshProducts();
  toast("Existencia actualizada.");
}

function renderReports(invoices, summary) {
  $("#summary").innerHTML = (summary.length ? summary : [{ ecf_type: "31", invoice_count: 0, total: 0 }, { ecf_type: "32", invoice_count: 0, total: 0 }])
    .map((row) => `<article class="summary-card"><strong>e-CF ${escapeHtml(row.ecf_type)}</strong><span>${row.invoice_count} facturas · ${money.format(row.total)}</span></article>`)
    .join("");
  $("#invoice-table").innerHTML = invoices
    .map((invoice) => `
      <tr>
        <td>${escapeHtml(invoice.provider_encf || invoice.en_ncf)}</td>
        <td>e-CF ${escapeHtml(invoice.ecf_type)}</td>
        <td>${escapeHtml(invoice.client_name)}</td>
        <td>${money.format(invoice.total)}</td>
        <td>${fiscalStatusBadge(invoice)}</td>
        <td>${escapeHtml(formatDate(invoice.issued_at))}</td>
        <td>${fiscalActions(invoice)}</td>
      </tr>
    `)
    .join("") || `<tr><td colspan="7">Sin facturas emitidas</td></tr>`;
  $("#invoice-table").querySelectorAll("[data-fiscal-action]").forEach((button) => {
    button.addEventListener("click", () => runFiscalAction(button));
  });
  $("#invoice-table").querySelectorAll("[data-credit-source]").forEach((button) => {
    button.addEventListener("click", () => openCreditNoteForInvoice(button.dataset.creditSource));
  });
}

function fiscalStatusBadge(invoice) {
  if (invoice.api_error) {
    return `<span class="badge low">Error IMECF</span>`;
  }
  if (invoice.api_status) {
    return `<span class="badge ok">${escapeHtml(invoice.api_status)}</span>`;
  }
  return `<span class="badge">Local</span>`;
}

function fiscalActions(invoice) {
  if (!invoice.provider_document_id) return `<span class="muted-text">Sin enlace</span>`;
  return `
    <div class="row-actions">
      <button class="table-button" data-fiscal-action="status" data-invoice-id="${invoice.id}">Estado</button>
      ${invoice.dgii_url
        ? `<a class="table-button" href="${escapeHtml(invoice.dgii_url)}" target="_blank" rel="noreferrer">DGII TesteCF</a>`
        : invoice.track_id
          ? `<button class="table-button" data-fiscal-action="track" data-invoice-id="${invoice.id}">Rastrear</button>`
          : `<span class="muted-text">Sin trackId</span>`}
      <button class="table-button" data-credit-source="${invoice.id}">E34</button>
    </div>
  `;
}

async function openCreditNoteForInvoice(invoiceId) {
  setView("fiscal");
  await refreshFiscal();
  $("#credit-source-invoice").value = String(invoiceId);
  $(".fiscal-credit-notes-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  $("#credit-reason").focus();
}

async function runFiscalAction(button) {
  const action = button.dataset.fiscalAction;
  const invoiceId = button.dataset.invoiceId;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "...";
  try {
    const result = await api(`/api/invoices/${invoiceId}/${action}`);
    toast(`Estado actualizado: ${result.invoice.api_status || "consultado"}`);
    await refreshReports();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function showInvoice(invoice, imecfWarning = "") {
  $("#dialog-ncf").textContent = invoice.display_encf || invoice.en_ncf;
  $("#dialog-eyebrow").textContent = "Comprobante emitido";
  $("#xml-link").href = `/api/invoices/${invoice.id}/xml`;
  $("#xml-link").hidden = false;
  $("#issue-dialog-preinvoice").hidden = true;
  $("#issue-dialog-preinvoice").dataset.preinvoiceId = "";
  $("#invoice-preview").innerHTML = auxiliaryInvoiceHtml(invoice, imecfWarning || invoice.api_error || "");
  const dialog = $("#invoice-dialog");
  if (dialog.showModal) dialog.showModal();
  else dialog.setAttribute("open", "open");
}

function auxiliaryInvoiceHtml(invoice, warning = "") {
  const issuer = state.fiscalIssuer || {};
  const encf = invoice.display_encf || invoice.en_ncf || "";
  const issueDate = formatReceiptDate(invoice.issued_at);
  const signatureDate = invoice.signed_at ? formatReceiptDateTime(invoice.signed_at) : "Pendiente";
  const items = invoice.items || [];
  const basePaymentLabel = paymentLabelFor(invoice.payment_method);
  const creditApplied = Number(invoice.credit_applied || 0);
  const paymentRows = invoice.payments || [];
  const paymentLabel = paymentRows.length
    ? paymentRows.map((row) => `${paymentLabelFor(row.payment_method)} ${money.format(row.amount)}`).join(" + ")
    : creditApplied > 0
    ? `${creditApplied >= Number(invoice.total || 0) ? "Nota de crédito" : `Nota de crédito + ${basePaymentLabel}`}`
    : basePaymentLabel;
  const qrHref = invoice.dgii_url || "";
  const sequenceExpiry = invoice.sequence_expires_at ? formatReceiptDate(invoice.sequence_expires_at) : "Pendiente";
  const fiscalIssuerName = invoice.provider_issuer_name || issuer.name || "UTESA";
  const fiscalIssuerRnc = invoice.provider_issuer_rnc || issuer.rnc || "";
  const fiscalIssuerAddress = invoice.provider_issuer_address || issuer.address || "";
  const fiscalMunicipality = invoice.provider_issuer_municipality || issuer.municipality || "No disponible";
  const fiscalProvince = invoice.provider_issuer_province || issuer.province || "No disponible";
  const showBuyer = invoice.ecf_type === "31" || Number(invoice.total || 0) >= 250000 || Boolean(invoice.rnc_cedula);
  const showExpiry = invoice.ecf_type === "31";
  return `
    <section class="aux-receipt">
      <header class="aux-fiscal-header">
        <div class="aux-issuer-card">
          <img class="aux-company-logo" src="/static/logo-ahg.png" alt="AHG Construferret" />
          <div>
            <h3>AHG CONSTRUFERRET</h3>
            <strong>${escapeHtml(fiscalIssuerName)}</strong><br />
            <strong>Punto de emisi&oacute;n:</strong> ${escapeHtml(issuer.workspace_name || "Sucursal principal")}<br />
            <strong>RNC:</strong> ${escapeHtml(formatFiscalId(fiscalIssuerRnc)) || "No disponible"}<br />
            <strong>Direcci&oacute;n:</strong> ${escapeHtml(fiscalIssuerAddress) || "No disponible"}<br />
            <strong>Municipio:</strong> ${escapeHtml(fiscalMunicipality)} &middot; <strong>Provincia:</strong> ${escapeHtml(fiscalProvince)}<br />
            <strong>Fecha Emisi&oacute;n:</strong> ${escapeHtml(issueDate)}
          </div>
        </div>
        <div class="aux-document-card">
          <h4>${escapeHtml(invoice.ecf_label || `e-CF ${invoice.ecf_type}`)}</h4>
          <strong>e-NCF:</strong> ${escapeHtml(encf)}<br />
          ${showExpiry ? `<strong>Fecha Vencimiento:</strong> ${escapeHtml(sequenceExpiry)}` : ""}
        </div>
      </header>

      ${showBuyer ? `
        <section class="aux-buyer-card">
          <strong>Raz&oacute;n Social Cliente:</strong> ${escapeHtml(invoice.client_name || "Consumidor Final")}<br />
          <strong>RNC Cliente:</strong> ${escapeHtml(formatFiscalId(invoice.rnc_cedula || "")) || "No identificado"}
        </section>
      ` : `<div class="aux-section-divider" aria-hidden="true"></div>`}

      <table class="aux-items-table">
        <thead>
          <tr>
            <th>Cantidad</th>
            <th>Descripci&oacute;n</th>
            <th>Unidad de<br />Medida</th>
            <th>Precio</th>
            <th>ITBIS</th>
            <th>Valor</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((item, index) => auxiliaryItemRow(item, index)).join("") || `<tr><td colspan="6">Sin detalle</td></tr>`}
        </tbody>
      </table>

      <div class="aux-bottom-grid">
        <div class="aux-verification-block">
          <div class="aux-qr-row">
            ${qrHref ? `
              <a class="aux-qr" href="${escapeHtml(qrHref)}" target="_blank" rel="noreferrer" aria-label="Consultar comprobante en DGII TesteCF">
                <img src="/api/invoices/${encodeURIComponent(invoice.id)}/qr.svg" alt="QR oficial de consulta DGII TesteCF" />
              </a>
              <div class="aux-qr-copy">
                <strong>C&oacute;digo de Seguridad:</strong> ${escapeHtml(invoice.security_code || "Pendiente")}<br />
                <strong>Fecha Firma:</strong> ${escapeHtml(signatureDate)}<br />
                <a class="aux-dgii-link" href="${escapeHtml(qrHref)}" target="_blank" rel="noreferrer">Consultar comprobante en DGII</a>
              </div>
            ` : `
              <div class="aux-qr-unavailable">QR DGII pendiente</div>
              <span>El proveedor todav&iacute;a no devolvi&oacute; una URL oficial de TESTeCF. No se genera un QR ficticio ni un c&oacute;digo de seguridad oficial.</span>
            `}
          </div>
        </div>

        <div class="aux-total-stack">
          ${auxTotalRow("Subtotal gravado", invoice.subtotal)}
          ${auxTotalRow("Descuento aplicado", invoice.discount_total || 0)}
          ${auxTotalRow("Total ITBIS", invoice.tax)}
          ${auxTotalRow("Total", invoice.total, true)}
          ${creditApplied > 0 ? auxTotalRow("Nota de crédito aplicada", -creditApplied) : ""}
          ${creditApplied > 0 ? auxTotalRow("Monto cobrado", invoice.amount_due || 0, true) : ""}
          <div class="aux-payment-summary"><span>Forma de pago</span><strong>${escapeHtml(paymentLabel)}</strong></div>
        </div>
      </div>

      <footer class="aux-fiscal-footer">Sin validez fiscal.</footer>
      ${warning ? `<p class="notice-error aux-warning"><strong>Motivo de rechazo:</strong> ${escapeHtml(warning)}</p>` : ""}
    </section>
  `;
}

function auxiliaryItemRow(item, index) {
  const quantity = Number(item.quantity || 0);
  const unitPrice = Number(item.unit_price || 0);
  const discount = Number(item.discount_amount || 0);
  const tax = Number(item.line_tax || 0);
  const subtotal = Number(item.line_subtotal || (quantity * unitPrice));
  const value = Math.max(0, subtotal - discount);
  const exemptIndicator = Number(item.tax_rate || 0) === 0 ? "E " : "";
  const discountNote = discount > 0 ? ` <small>(Desc. ${plainMoney(discount)})</small>` : "";
  return `
    <tr>
      <td>${formatQty(quantity)}</td>
      <td>${exemptIndicator}${escapeHtml(item.name || item.product_id || "Articulo")}${discountNote}</td>
      <td>UND</td>
      <td>${plainMoney(unitPrice)}</td>
      <td>${plainMoney(tax)}</td>
      <td>${plainMoney(value)}</td>
    </tr>
  `;
}

function auxTotalRow(label, value, strong = false) {
  const display = typeof value === "number" || !Number.isNaN(Number(value)) ? plainMoney(value) : escapeHtml(value);
  return `<div class="aux-total-row"><span>${escapeHtml(label)}</span><strong>${strong ? `<b>${display}</b>` : display}</strong></div>`;
}

function paymentLabelFor(method) {
  return {
    efectivo: "Efectivo",
    tarjeta: "Tarjeta",
    paypal: "PayPal",
    transferencia: "Transferencia / depósito bancario",
    credito: "Crédito",
    nota_credito: "Nota de crédito",
    mixto: "Pago mixto",
  }[String(method || "").toLowerCase()] || "Efectivo";
}

function plainMoney(value) {
  return Number(value || 0).toFixed(2);
}

function formatReceiptDate(value) {
  const text = String(value || "");
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (dateOnly) return `${dateOnly[3]}/${dateOnly[2]}/${dateOnly[1]}`;
  const date = new Date(value || Date.now());
  if (Number.isNaN(date.getTime())) return String(value || "");
  return date.toLocaleDateString("es-DO", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatReceiptDateTime(value) {
  const date = new Date(value || Date.now());
  if (Number.isNaN(date.getTime())) return String(value || "");
  return date.toLocaleString("es-DO", { dateStyle: "short", timeStyle: "medium" });
}

function renderOnlinePaymentStatus() {
  const box = $("#online-payment-status");
  const button = $("#open-payment-gateway");
  let online = null;
  try { online = paymentRowsFromForm().find((row) => ["tarjeta", "paypal"].includes(row.payment_method)); } catch (_) { online = null; }
  const method = online?.payment_method || "";
  const payableTotal = Number(online?.amount || 0);
  if (!online || payableTotal <= 0) {
    box.hidden = true;
    button.hidden = true;
    return;
  }
  box.hidden = false;
  button.hidden = false;
  button.textContent = method === "tarjeta" ? "Abrir portal de tarjeta" : "Abrir portal PayPal";
  if (state.paypalPayment?.method === method) {
    box.className = "online-payment-status paid";
    box.textContent = `Pago validado sin cargo - Ref. ${state.paypalPayment.order_id}`;
    return;
  }
  box.className = "online-payment-status";
  box.textContent = method === "tarjeta"
    ? "La tarjeta se validara antes de emitir el comprobante."
    : "PayPal se abrira para validar el pago antes de emitir el comprobante.";
}

async function openPaymentGateway(method, total) {
  const dialog = $("#payment-dialog");
  $("#payment-dialog-title").textContent = method === "tarjeta" ? "Portal de tarjeta" : "Portal PayPal";
  $("#payment-conversion").textContent = state.paypal?.currency === "USD"
    ? `${money.format(total)} - referencia USD ${(total / Number(state.paypal.dop_per_usd || 60)).toFixed(2)}`
    : money.format(total);
  resetPaymentGateway();
  const realHint = $("#paypal-real-hint");
  if (realHint) realHint.hidden = !state.paypal?.configured;
  const cardError = $("#card-payment-error");
  if (cardError) cardError.hidden = true;
  const paypalError = $("#paypal-payment-error");
  if (paypalError) paypalError.hidden = true;
  if (dialog.showModal) dialog.showModal();
  else dialog.setAttribute("open", "open");
  if (method === "tarjeta") {
    openLocalPaymentGateway(method);
    return;
  }
  openLocalPaymentGateway(method);
  if (state.paypal?.no_charge) {
    return;
  }
  if (state.paypal?.configured) {
    await openRealPayPalGateway(method, total);
    return;
  }
}

function resetPaymentGateway() {
  $("#paypal-simulated-portal").hidden = true;
  $("#card-simulated-portal").hidden = true;
  $("#paypal-button-container").hidden = true;
  $("#paypal-button-container").innerHTML = "";
  resetRealCardContainer();
  $("#card-field-container").hidden = true;
}

function resetRealCardContainer(message = "") {
  $("#card-field-container").innerHTML = message || `
    <div id="card-name-field-container" class="hosted-card-field"></div>
    <div id="card-number-field-container" class="hosted-card-field"></div>
    <div class="card-field-row">
      <div id="card-expiry-field-container" class="hosted-card-field"></div>
      <div id="card-cvv-field-container" class="hosted-card-field"></div>
    </div>
    <button id="card-field-submit" class="primary-button" type="button">Pagar con tarjeta</button>
  `;
}

function openLocalPaymentGateway(method) {
  $("#paypal-simulated-portal").hidden = method !== "paypal";
  $("#card-simulated-portal").hidden = method !== "tarjeta";
}

async function openRealPayPalGateway(method, total) {
  try {
    const paypal = await loadPayPalSdk();
    const createOrder = () => createPayPalOrder(total);
    const onApprove = (data) => capturePayPalOrder(data.orderID, method, total);
    const onError = (error) => {
      toast(error.message || "El pago no pudo completarse.", true);
    };
    if (method === "paypal") {
      $("#paypal-button-container").hidden = false;
      await paypal.Buttons({
        style: { layout: "vertical", shape: "rect", label: "paypal" },
        createOrder,
        onApprove,
        onCancel: () => toast("Pago cancelado.", true),
        onError,
      }).render("#paypal-button-container");
      return;
    }
    await openRealCardFields(paypal, createOrder, onApprove, onError);
  } catch (error) {
    toast(`PayPal Sandbox: ${error.message}. Se habilito el portal de validacion.`, true);
    openLocalPaymentGateway(method);
  }
}

async function openRealCardFields(paypal, createOrder, onApprove, onError) {
  if (!paypal.CardFields) {
    $("#card-field-container").hidden = false;
    resetRealCardContainer('<div class="payment-warning">La cuenta PayPal Sandbox no tiene Card Fields habilitado. Usa el portal de tarjeta local.</div>');
    $("#card-simulated-portal").hidden = false;
    return;
  }
  const cardFields = paypal.CardFields({ createOrder, onApprove, onError });
  if (!cardFields.isEligible()) {
    $("#card-field-container").hidden = false;
    resetRealCardContainer('<div class="payment-warning">La cuenta PayPal Sandbox no es elegible para tarjetas avanzadas. Usa el portal de tarjeta local.</div>');
    $("#card-simulated-portal").hidden = false;
    return;
  }
  $("#card-field-container").hidden = false;
  resetRealCardContainer();
  if (cardFields.NameField) cardFields.NameField().render("#card-name-field-container");
  cardFields.NumberField().render("#card-number-field-container");
  cardFields.ExpiryField().render("#card-expiry-field-container");
  cardFields.CVVField().render("#card-cvv-field-container");
  $("#card-field-submit").onclick = () => cardFields.submit();
}

function confirmSimulatedPayment(method) {
  const total = salePayableTotal();
  if (total <= 0) {
    toast("Agrega articulos con un total mayor que cero para cobrar.", true);
    return;
  }
  if (method === "paypal" && !validateSimulatedPayPal()) return;
  if (method === "tarjeta" && !validateSimulatedCard()) return;
  state.paypalPayment = {
    order_id: `${method.toUpperCase()}-${Date.now()}`,
    method,
    amount_dop: total,
    approved: true,
  };
  $("#payment-dialog").close();
  renderOnlinePaymentStatus();
  toast("Pago confirmado. Emitiendo comprobante...");
  issueInvoice();
}

function validateSimulatedPayPal() {
  const error = $("#paypal-payment-error");
  const email = $("#paypal-email")?.value.trim() || "";
  const password = $("#paypal-password")?.value || "";
  error.hidden = true;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    error.textContent = "Escribe un correo valido de PayPal para continuar.";
    error.hidden = false;
    return false;
  }
  if (password.length < 6) {
    error.textContent = "La contrasena debe tener al menos 6 caracteres.";
    error.hidden = false;
    return false;
  }
  return true;
}

function validateSimulatedCard() {
  const error = $("#card-payment-error");
  const name = $("#sim-card-name").value.trim();
  const number = $("#sim-card-number").value.replace(/\D/g, "");
  const expiry = $("#sim-card-expiry").value.trim();
  const cvv = $("#sim-card-cvv").value.replace(/\D/g, "");
  const brand = detectCardBrand(number);
  error.hidden = true;
  if (name.length < 3) {
    error.textContent = "Escribe el nombre del titular de la tarjeta.";
    error.hidden = false;
    return false;
  }
  if (!brand) {
    error.textContent = "Solo se aceptan tarjetas Visa o Mastercard.";
    error.hidden = false;
    return false;
  }
  if (number.length < 13 || number.length > 19 || !luhnCheck(number)) {
    error.textContent = "El numero de tarjeta no es valido.";
    error.hidden = false;
    return false;
  }
  if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(expiry)) {
    error.textContent = "La fecha debe tener formato MM/AA.";
    error.hidden = false;
    return false;
  }
  if (isExpiredCard(expiry)) {
    error.textContent = "La tarjeta esta vencida.";
    error.hidden = false;
    return false;
  }
  if (cvv.length < 3 || cvv.length > 4) {
    error.textContent = "El CVV debe tener 3 o 4 digitos.";
    error.hidden = false;
    return false;
  }
  return true;
}

function formatCardNumberInput(event) {
  const digits = event.target.value.replace(/\D/g, "").slice(0, 19);
  event.target.value = digits.replace(/(.{4})/g, "$1 ").trim();
  renderCardBrand(digits);
}

function formatCardExpiryInput(event) {
  const digits = event.target.value.replace(/\D/g, "").slice(0, 4);
  event.target.value = digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits;
}

function detectCardBrand(number) {
  if (/^4\d{0,18}$/.test(number)) return "visa";
  const firstTwo = Number(number.slice(0, 2));
  const firstFour = Number(number.slice(0, 4));
  if ((firstTwo >= 51 && firstTwo <= 55) || (firstFour >= 2221 && firstFour <= 2720)) return "mastercard";
  return "";
}

function renderCardBrand(number) {
  const brand = detectCardBrand(number);
  $("#visa-brand")?.classList.toggle("active", brand === "visa");
  $("#mastercard-brand")?.classList.toggle("active", brand === "mastercard");
}

function isExpiredCard(expiry) {
  const [monthText, yearText] = expiry.split("/");
  const month = Number(monthText);
  const year = 2000 + Number(yearText);
  const now = new Date();
  const lastDayOfMonth = new Date(year, month, 0, 23, 59, 59);
  return lastDayOfMonth < now;
}

function luhnCheck(value) {
  let sum = 0;
  let doubleDigit = false;
  for (let index = value.length - 1; index >= 0; index -= 1) {
    let digit = Number(value[index]);
    if (doubleDigit) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
    doubleDigit = !doubleDigit;
  }
  return sum % 10 === 0;
}

function renderReports(invoices, summary) {
  const drafts = state.preinvoices || [];
  $("#summary").innerHTML = [
    ...(summary.length ? summary : [{ ecf_type: "31", invoice_count: 0, total: 0 }, { ecf_type: "32", invoice_count: 0, total: 0 }]),
    { ecf_type: "Borradores", invoice_count: drafts.filter((draft) => draft.status === "borrador").length, total: drafts.reduce((sum, draft) => sum + Number(draft.total || 0), 0) },
  ]
    .map((row) => `<article class="summary-card"><strong>${escapeHtml(row.ecf_type === "Borradores" ? "Pre-Facturas" : `e-CF ${row.ecf_type}`)}</strong><span>${row.invoice_count} documentos - ${money.format(row.total)}</span></article>`)
    .join("");
  const draftRows = drafts.map((draft) => ({ ...draft, _draft: true }));
  const rows = [...draftRows, ...invoices];
  $("#invoice-table").innerHTML = rows
    .map((row) => row._draft ? preinvoiceReportRow(row) : invoiceReportRow(row))
    .join("") || `<tr><td colspan="7">Sin facturas ni pre-facturas</td></tr>`;
  $("#invoice-table").querySelectorAll("[data-fiscal-action]").forEach((button) => {
    button.addEventListener("click", () => runFiscalAction(button));
  });
  $("#invoice-table").querySelectorAll("[data-review-invoice]").forEach((button) => {
    button.addEventListener("click", () => reviewInvoice(button.dataset.reviewInvoice));
  });
  $("#invoice-table").querySelectorAll("[data-review-preinvoice]").forEach((button) => {
    button.addEventListener("click", () => reviewPreinvoice(button.dataset.reviewPreinvoice));
  });
  $("#invoice-table").querySelectorAll("[data-load-preinvoice]").forEach((button) => {
    button.addEventListener("click", () => loadPreinvoice(button.dataset.loadPreinvoice));
  });
  $("#invoice-table").querySelectorAll("[data-issue-preinvoice]").forEach((button) => {
    button.addEventListener("click", () => issuePreinvoice(button.dataset.issuePreinvoice));
  });
}

function invoiceReportRow(invoice) {
  return `
    <tr>
      <td>${escapeHtml(invoice.provider_encf || invoice.en_ncf)}</td>
      <td>e-CF ${escapeHtml(invoice.ecf_type)}</td>
      <td>${escapeHtml(invoice.client_name)}</td>
      <td>${money.format(invoice.total)}</td>
      <td>${fiscalStatusBadge(invoice)}</td>
      <td>${escapeHtml(formatDate(invoice.issued_at))}</td>
      <td>
        <div class="row-actions">
          <button class="table-button" data-review-invoice="${escapeHtml(invoice.id)}">Revisar</button>
          ${fiscalActions(invoice)}
        </div>
      </td>
    </tr>
  `;
}

async function reviewInvoice(invoiceId) {
  const payload = await api(`/api/invoices/${encodeURIComponent(invoiceId)}`);
  showInvoice(payload.invoice);
}

function preinvoiceReportRow(draft) {
  const isDraft = draft.status === "borrador";
  return `
    <tr>
      <td>Pre-Factura #${escapeHtml(draft.id)}</td>
      <td>e-CF ${escapeHtml(draft.ecf_type)}</td>
      <td>${escapeHtml(draft.client_name || "Sin cliente")}</td>
      <td>${money.format(draft.total)}</td>
      <td><span class="badge ${isDraft ? "warning" : "ok"}">${escapeHtml(draft.status)}</span></td>
      <td>${escapeHtml(formatDate(draft.updated_at))}</td>
      <td>
        <div class="row-actions">
          <button class="table-button" data-review-preinvoice="${draft.id}">Revisar</button>
          ${isDraft ? `<button class="table-button" data-load-preinvoice="${draft.id}">Editar</button><button class="primary-button compact" data-issue-preinvoice="${draft.id}" ${Number(draft.total) <= 0 ? "disabled" : ""}>Emitir</button>` : `<span class="muted-text">Factura #${escapeHtml(draft.emitted_invoice_id || "")}</span>`}
        </div>
      </td>
    </tr>
  `;
}

async function reviewPreinvoice(preinvoiceId) {
  const payload = await api(`/api/preinvoices/${preinvoiceId}`);
  showPreinvoice(payload.preinvoice);
}

function showPreinvoice(draft) {
  $("#dialog-eyebrow").textContent = "Pre-Factura guardada";
  $("#dialog-ncf").textContent = `Pre-Factura #${draft.id}`;
  $("#xml-link").hidden = true;
  $("#issue-dialog-preinvoice").hidden = draft.status !== "borrador" || Number(draft.total) <= 0;
  $("#issue-dialog-preinvoice").dataset.preinvoiceId = draft.id;
  $("#invoice-preview").innerHTML = `
    <div class="receipt-line"><span>Tipo</span><strong>e-CF ${escapeHtml(draft.ecf_type)}</strong></div>
    <div class="receipt-line"><span>Cliente</span><strong>${escapeHtml(draft.client_name || "Sin cliente")}</strong></div>
    <div class="receipt-line"><span>RNC/Cedula</span><strong>${escapeHtml(draft.rnc_cedula || "No identificado")}</strong></div>
    <div class="receipt-line"><span>Pago</span><strong>${escapeHtml(draft.payment_method)}</strong></div>
    <div class="receipt-line"><span>Estado</span><strong>${escapeHtml(draft.status)}</strong></div>
    <div class="receipt-line"><span>Subtotal</span><strong>${money.format(draft.subtotal)}</strong></div>
    <div class="receipt-line"><span>Descuento</span><strong>${money.format(draft.discount_total || 0)}</strong></div>
    <div class="receipt-line"><span>ITBIS</span><strong>${money.format(draft.tax)}</strong></div>
    <div class="receipt-line"><span>Total</span><strong>${money.format(draft.total)}</strong></div>
    ${draft.notes ? `<p class="payment-security">${escapeHtml(draft.notes)}</p>` : ""}
    <div class="preinvoice-print-items">
      ${(draft.items || []).map((item) => `<div class="receipt-line"><span>${escapeHtml(item.name)} x ${formatQty(item.quantity)}${Number(item.discount_amount || 0) > 0 ? ` - desc. ${money.format(item.discount_amount)}` : ""}</span><strong>${money.format(Number(item.unit_price) * Number(item.quantity) - Number(item.discount_amount || 0))}</strong></div>`).join("") || `<p class="muted-text">Pre-Factura en cero sin articulos.</p>`}
    </div>
  `;
  const dialog = $("#invoice-dialog");
  if (dialog.showModal) dialog.showModal();
  else dialog.setAttribute("open", "open");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = payload.error || payload || "Error de comunicación";
    if (response.status === 401) {
      window.location.assign("/login");
      throw new Error(message);
    }
    toast(message, true);
    throw new Error(message);
  }
  return payload;
}


function onlyDigits(value, limit = 40) {
  return String(value || "").replace(/\D/g, "").slice(0, limit);
}

function formatFiscalId(value) {
  const digits = onlyDigits(value, 11);
  const parts = digits.length > 9
    ? [digits.slice(0, 3), digits.slice(3, 10), digits.slice(10, 11)]
    : [digits.slice(0, 1), digits.slice(1, 3), digits.slice(3, 8), digits.slice(8, 9)];
  return parts.filter(Boolean).join("-");
}

function formatPhone(value) {
  const digits = onlyDigits(value, 10);
  return [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6, 10)].filter(Boolean).join("-");
}

function bindPartyInputs(prefix) {
  const name = $(`#${prefix}-name`);
  const rnc = $(`#${prefix}-rnc`);
  const phone = $(`#${prefix}-phone`);
  const email = $(`#${prefix}-email`);
  const address = $(`#${prefix}-address`);
  const contact = $(`#${prefix}-contact`);
  name?.addEventListener("input", () => { name.value = name.value.toUpperCase(); });
  address?.addEventListener("input", () => { address.value = address.value.toUpperCase(); });
  contact?.addEventListener("input", () => { contact.value = formatPhone(contact.value); });
  rnc?.addEventListener("input", () => { rnc.value = formatFiscalId(rnc.value); });
  phone?.addEventListener("input", () => { phone.value = formatPhone(phone.value); });
  email?.addEventListener("input", () => { email.setCustomValidity(email.value.includes("@") ? "" : "El correo debe incluir @."); });
  email?.addEventListener("blur", () => {
    if (email.value && !email.value.includes("@")) {
      email.reportValidity();
      toast("El correo debe incluir @.", true);
    }
  });
}

function partyPayload(prefix) {
  return {
    name: $(`#${prefix}-name`).value.trim().toUpperCase(),
    rnc_cedula: onlyDigits($(`#${prefix}-rnc`).value, 11),
    phone: onlyDigits($(`#${prefix}-phone`).value, 10),
    email: $(`#${prefix}-email`).value.trim().toLowerCase(),
    address: $(`#${prefix}-address`).value.trim().toUpperCase(),
    taxpayer_activity: $(`#${prefix}-activity`)?.value.trim().toUpperCase() || "",
    dgii_locked: $(`#${prefix}-name`)?.dataset.dgiiLocked === "1",
  };
}

function validatePartyPayload(payload, label) {
  if (payload.name.length < 2) return `El nombre de ${label} es obligatorio.`;
  if (![9, 11].includes(payload.rnc_cedula.length)) return `El RNC o cedula de ${label} debe tener 9 u 11 digitos.`;
  if (payload.phone.length !== 10) return `El telefono de ${label} debe tener 10 digitos.`;
  if (!payload.email.includes("@") || payload.email.startsWith("@") || payload.email.endsWith("@")) return `El correo de ${label} debe incluir @ y ser valido.`;
  if (!payload.address) return `La direccion de ${label} es obligatoria.`;
  return "";
}

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatQty(value) {
  const number = Number(value);
  return Number.isInteger(number) ? String(number) : number.toFixed(2);
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("es-DO", { dateStyle: "short", timeStyle: "short" });
}

let toastTimer;
function toast(message, isError = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 2600);
}
