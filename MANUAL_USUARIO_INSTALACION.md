# AHG CONSTRUFERRET POS

## 1. Requisitos

- Python 3.11 o superior.
- Dependencias de `requirements.txt`.
- Para producción: PostgreSQL 16 o un servicio compatible.
- Para desplegar en GCP: Google Cloud CLI, un proyecto activo y permisos para Cloud Run, Artifact Registry y Cloud SQL.

## 2. Instalación local

```powershell
cd "C:\Users\ronie\OneDrive\Documentos\ahg_construferret_pos"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH="$PWD\src"
python -m ahg_pos.app
```

Abrir `http://127.0.0.1:8765`. El modo demo crea una base SQLite local en `data/ahg_demo.db`.

Usuario inicial: `admin@ahg.local` / `Cambiar123!`. Cambiarlo antes de usar el sistema.

## 3. Flujo de usuario

1. Iniciar sesión.
2. En **Maestro de artículos**, registrar artículos, precio, ITBIS, stock y stock mínimo.
3. En **Venta**, escribir el nombre, SKU o código de barras. La búsqueda consulta al servidor y trae solo la página solicitada.
4. Agregar artículos a la pre-factura, seleccionar cliente y tipo e-CF.
5. Guardar la pre-factura o emitir el comprobante.
6. Usar **Facturas** y **Gestión Fiscal** para revisar estado, track DGII y XML.
7. Al emitir, el sistema genera un token de seguimiento. El enlace de consulta no requiere iniciar sesión y solo muestra el estado fiscal básico.

## 3.1 Portal de clientes

Abrir `/catalog` para que un cliente pueda:

- Visualizar únicamente artículos activos con existencia.
- Buscar por producto, SKU, categoría, uso o problemática.
- Describir una necesidad al asesor IA.
- Responder preguntas de medida, ambiente, material o presupuesto.
- Recibir una recomendación principal, alternativas y complementos.
- Crear una lista de selección y copiarla para solicitar atención.

El asesor actual funciona con reglas locales, sin enviar datos a un modelo externo. Esto permite controlar las respuestas contra el inventario real. Para hacerlo generativo se debe agregar un proveedor/modelo y una política de privacidad antes de enviar consultas de clientes fuera del sistema.

## 4. API de consultas paginadas

Las consultas aceptan `page`, `limit` y, cuando corresponde, `q`:

```text
/api/products?page=1&limit=25&q=tuberia
/api/clients?page=1&limit=25&q=empresa
/api/suppliers?page=1&limit=25&q=cemento
/api/preinvoices?page=1&limit=25
/api/invoices?page=1&limit=25&q=E3200000001
/api/credit-notes?page=1&limit=25
```

La respuesta incluye `pagination` con `page`, `limit`, `total`, `pages`, `has_next` y `has_previous`.

## 5. PostgreSQL local

```powershell
docker compose up -d
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ahg_pos"
$env:PYTHONPATH="$PWD\src"
python -m ahg_pos.app
```

## 6. Despliegue en GCP Cloud Run

Cloud Run no debe usar SQLite como base principal porque el almacenamiento local es efímero. Crear primero una instancia Cloud SQL PostgreSQL y usar su cadena de conexión mediante un secreto.

```powershell
gcloud auth login
gcloud config set project TU_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com sqladmin.googleapis.com
gcloud builds submit --tag REGION-docker.pkg.dev/TU_PROJECT_ID/ahg/pos:latest
gcloud run deploy ahg-pos `
  --image REGION-docker.pkg.dev/TU_PROJECT_ID/ahg/pos:latest `
  --region REGION `
  --allow-unauthenticated `
  --set-env-vars "AHG_HOST=0.0.0.0,AHG_PORT=8080,AHG_AUTH_SECURE_COOKIE=1,DATABASE_URL=postgresql://..."
```

No subir `.env` ni API keys al repositorio. En producción, usar Secret Manager para `DATABASE_URL`, `AHG_CREDENTIAL_SECRET`, `IMECF_API_KEY` y las credenciales de PayPal.

## 7. Advertencias de producción

La facturación electrónica requiere rangos autorizados, firma digital, XSD oficial y validación DGII. El modo académico/local no sustituye esos requisitos.
