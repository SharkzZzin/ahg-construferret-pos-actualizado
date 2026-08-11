# AHG CONSTRUFERRET POS

Sistema web de punto de venta para ferretería, desarrollado en Python y publicado con Vercel y Supabase PostgreSQL. Integra catálogo público, pre-facturas, inventario, recomendaciones locales, comprobantes electrónicos de prueba, notas de crédito, pagos mixtos, cuadre de caja, auditoría y permisos por módulo.

Aplicación publicada: https://ahg-construferret-pos.vercel.app/

> Proyecto académico: las integraciones fiscales y de pago se ejecutan exclusivamente en ambientes de prueba.

## Funciones principales

- Dashboard inicial con ventas del día, pendientes, stock crítico, caja, notas vigentes, tendencia semanal y accesos rápidos.
- Venta y pre-factura con e-CF 31/32, descuentos por línea y generales.
- Pagos en efectivo, tarjeta, transferencia, PayPal Sandbox y combinaciones de varios medios.
- Consulta, carga y aplicación de notas de crédito vigentes; permite nota de crédito más otro medio de pago.
- Portal Customer para buscar productos, recibir orientación del asistente y enviar pre-facturas.
- Confirmación por correo al cliente cuando proporciona una dirección válida.
- Maestro de artículos, categorías, precios, ITBIS, costos, stock y mínimo.
- Directorios de clientes y proveedores con consulta fiscal.
- Inventario con existencias, alertas y movimientos.
- Gestión fiscal con IMECF en TESTeCF, estados, tracking, XML y e-CF 34.
- Facturas con vista previa, forma de pago, descuentos, QR y consulta DGII.
- Cuadre de caja con apertura, movimientos, pagos, cierre y diferencia.
- Auditoría limitada a acciones realizadas por usuarios.
- Administración de usuarios con acceso individual por módulo y respaldo JSON.
- Búsqueda y recomendación local por nombre, SKU, código de barras o necesidad.

## Arquitectura

| Componente | Tecnología | Función |
|---|---|---|
| Aplicación | Python 3.12 | Servidor HTTP, reglas de negocio y API |
| Interfaz | HTML, CSS y JavaScript | POS, dashboard y portal Customer |
| Producción | Vercel Functions | Publicación web y API serverless |
| Datos | Supabase PostgreSQL | Persistencia multiusuario |
| Desarrollo | SQLite | Ejecución local y pruebas |
| Fiscal | IMECF TESTeCF | Envío y consulta de documentos de prueba |
| Correo | Resend o SMTP | Confirmación de pre-facturas |
| Pago | PayPal Sandbox y simulador de tarjeta | Flujos académicos sin cargos reales |

## Inicio rápido local

En PowerShell:

```powershell
git clone https://github.com/SharkzZzin/ahg-construferret-pos-actualizado.git
cd ahg-construferret-pos-actualizado
git switch agent/pos-updated-20260727

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:PYTHONPATH="$PWD\src"
$env:AHG_DEMO_MODE="1"
$env:AHG_AUTH_SECURE_COOKIE="0"
python -m ahg_pos.app
```

Direcciones locales:

- POS: http://127.0.0.1:8765/
- Inicio de sesión: http://127.0.0.1:8765/login
- Portal Customer: http://127.0.0.1:8765/catalog

La primera ejecución crea `data/ahg_demo.db`. Las credenciales iniciales se definen con `AHG_ADMIN_EMAIL`, `AHG_ADMIN_PHONE` y `AHG_ADMIN_PASSWORD`; cambia cualquier contraseña de demostración antes de compartir el sistema.

## Ejecutar las pruebas

```powershell
$env:PYTHONPATH="$PWD\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Configuración de producción

La aplicación productiva requiere una base PostgreSQL persistente. Para Vercel se recomienda la cadena Session Pooler IPv4 de Supabase.

Variables principales:

```text
DATABASE_URL=postgresql://...
AHG_CREDENTIAL_SECRET=<secreto-largo>
AHG_ACADEMIC_MODE=1
AHG_DEMO_MODE=0
AHG_AUTH_SECURE_COOKIE=1
IMECF_BASE_URL=https://ecf-platform-backend-50801509587.us-central1.run.app
IMECF_API_KEY=<clave-de-prueba>
IMECF_ENABLED=1
PAYPAL_ENVIRONMENT=sandbox
PAYPAL_NO_CHARGE=1
```

Para correo con Resend:

```text
RESEND_API_KEY=<clave>
EMAIL_FROM=<remitente-verificado>
```

Alternativa SMTP:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=<correo>
SMTP_PASSWORD=<contraseña-de-aplicación>
SMTP_USE_TLS=1
EMAIL_FROM=<correo-remitente>
```

No publiques `.env`, `DATABASE_URL`, contraseñas, cookies, claves IMECF ni secretos de correo.

## Despliegue en Vercel

```powershell
vercel.cmd login
vercel.cmd link --project ahg-construferret-pos
vercel.cmd pull --yes --environment production
vercel.cmd deploy --prod --yes
```

`vercel.json` dirige las rutas al handler Python de `api/index.py`. El esquema se verifica al iniciar y se actualiza de forma compatible para SQLite y PostgreSQL.

## Operación resumida

1. Inicia sesión; el dashboard será la primera pantalla.
2. Revisa pendientes, stock crítico, caja y documentos fiscales.
3. Abre **Venta**, agrega productos y selecciona cliente y tipo de comprobante.
4. Si usarás una nota, pulsa **Consultar notas vigentes** y luego **Cargar nota**.
5. Selecciona el medio para el monto restante; usa **Dividir saldo restante** solo si habrá dos medios adicionales.
6. Guarda una pre-factura o emite el comprobante de prueba.
7. Consulta el documento en **Facturas** o **Gestión Fiscal**.
8. Cierra el turno desde **Cuadre de caja**.

## Permisos

El dashboard está disponible para todo usuario autenticado. En **Administración**, un administrador elige qué módulos puede abrir cada usuario. La protección se aplica tanto en el menú como en la API.

Perfiles iniciales sugeridos:

- `admin`: acceso completo.
- `gerente`: operación completa excepto Administración.
- `cajero`: venta, clientes, pre-facturas, facturas y caja.
- `vendedor`: venta, clientes, pre-facturas, asistente y facturas.
- `almacen`: artículos, proveedores e inventario.

## Documentación

- [Manual de usuario](docs/manuales/MANUAL_USUARIO.md)
- [Manual de instalación](docs/manuales/MANUAL_INSTALACION.md)
- [Manual de usuario PDF](output/pdf/manual_usuario_ahg_construferret_pos.pdf)
- [Manual de instalación PDF](output/pdf/manual_instalacion_ahg_construferret_pos.pdf)
- [Integración IMECF](INTEGRACION_IMECF.md)

Para regenerar los PDF:

```powershell
python scripts/generate_manual_pdfs.py
```

## Estructura del repositorio

```text
api/                         Entrada para Vercel
docs/manuales/               Manuales y capturas
output/pdf/                  Manuales PDF generados
schema/                      Esquemas SQLite y PostgreSQL
scripts/                     Generadores y utilidades
src/ahg_pos/                 Aplicación y lógica de negocio
src/ahg_pos/web/             Interfaces POS y Customer
tests/                       Pruebas automatizadas
vercel.json                  Configuración de despliegue
```

## Seguridad y respaldo

- Cambia las credenciales iniciales.
- Configura permisos mínimos por usuario.
- Conserva `AHG_CREDENTIAL_SECRET`; cambiarlo invalida credenciales cifradas existentes.
- Usa el respaldo JSON de Administración y las copias de Supabase.
- Revisa Auditoría y los logs de Vercel ante errores.
- Mantén IMECF y PayPal únicamente en sus ambientes de prueba para este proyecto.
