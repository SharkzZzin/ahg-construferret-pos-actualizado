# AHG CONSTRUFERRET POS

Sistema academico en Python para el proyecto integrador: ventas, inventario, recomendaciones con IA/MCP y facturacion e-CF 31/32.

## Que incluye

- Interfaz web moderna para mostrador, caja, asistente IA, inventario y reportes.
- Maestro de articulos con alta, edicion, categorias, costos, precios, ITBIS,
  inventario, estado, codigo de barras y datos tecnicos.
- Base de datos preparada para PostgreSQL, con modo demo local sin instalar dependencias.
- Busqueda por nombre, SKU, codigo de barras y lenguaje natural.
- Recomendaciones con sinonimos tecnicos, errores ortograficos leves,
  presupuesto y explicacion de coincidencias.
- Servidor MCP por `stdio` con herramientas `buscar_articulos`, `recomendar_articulos` y `stock_critico`.
- Facturador academico para e-CF 31 y e-CF 32 con e-NCF secuencial, ITBIS, XML interno y consulta de facturas.
- Centro de Gestion Fiscal con salud, secuencias, proveedor IMECF, filtros,
  consulta de estado, track DGII y descarga XML.
- Registro de movimientos cuando el stock se ajusta desde el maestro.

## Ejecutar demo local

Desde PowerShell:

```powershell
cd "C:\Users\raule\Documents\Codex\2026-06-01\files-mentioned-by-the-user-proyecto\outputs\ahg_construferret_pos"
$env:PYTHONPATH="$PWD\src"
python -m ahg_pos.app
```

Abre:

```text
http://127.0.0.1:8765
```

Portal público para clientes:

```text
http://127.0.0.1:8765/catalog
```

El portal permite explorar artículos disponibles, buscar por problemática y conversar
con el asesor IA autónomo. El asesor solo recomienda artículos activos con existencia,
explica compatibilidad y puede añadir complementos a una lista de selección.

Acceso inicial:

```text
Correo: admin@ahg.local
Contraseña: Cambiar123!
```

Puedes cambiar esas credenciales antes del primer inicio mediante
`AHG_ADMIN_EMAIL`, `AHG_ADMIN_PHONE` y `AHG_ADMIN_PASSWORD`. El sistema guarda
la contraseña con `scrypt`; nunca conserva el texto original.

Las variables de administrador solo se usan cuando la tabla de usuarios esta
vacia. Cambiarlas despues de crear el primer usuario no modifica su contrasena.

La demo crea `data/ahg_demo.db` con inventario inicial. Es util para presentar el prototipo sin configurar PostgreSQL.

## Usar PostgreSQL

1. Levanta PostgreSQL con Docker:

```powershell
docker compose up -d
```

2. Instala el conector:

```powershell
pip install -r requirements.txt
```

3. Ejecuta la app apuntando a PostgreSQL:

```powershell
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ahg_pos"
$env:PYTHONPATH="$PWD\src"
python -m ahg_pos.app
```

La app crea tablas y datos demo automaticamente si la base esta vacia.

## Servidor MCP

Comando para conectar desde un cliente MCP:

```powershell
cd "C:\Users\raule\Documents\Codex\2026-06-01\files-mentioned-by-the-user-proyecto\outputs\ahg_construferret_pos"
$env:PYTHONPATH="$PWD\src"
python -m ahg_pos.mcp_server
```

Herramientas disponibles:

- `buscar_articulos`: busca productos por necesidad escrita en lenguaje natural.
- `recomendar_articulos`: recomienda productos y devuelve la razon tecnica.
- `stock_critico`: muestra articulos por debajo del minimo.

## Integracion IMECF

La integracion usa perfiles fiscales administrables. Cada empresa conserva su espacio
IMECF, razon social, RNC, ambiente, URLs e API Key cifrada. La clave nunca se devuelve
completa al navegador.

La gestion de credenciales:

- Solo esta disponible para usuarios con rol `admin`.
- Exige confirmar la contrasena actual antes de guardar.
- Invalida la activacion cuando se modifica una credencial.
- Exige validar el emisor en DGII y probar la conexion antes de activar la empresa.
- Permite registrar varias empresas, manteniendo una sola empresa fiscal activa.

Para iniciar con IMECF:

```powershell
$env:IMECF_BASE_URL="https://ecf-platform-backend-50801509587.us-central1.run.app"
$env:IMECF_API_KEY="TU_NUEVA_CLAVE"
$env:IMECF_ENABLED="1"
$env:PYTHONPATH="$PWD\src"
python -m ahg_pos.app
```

Las variables IMECF se importan como perfil inicial cuando la base no tiene empresas
fiscales. Despues, la configuracion se administra desde **Gestion Fiscal**.

Funciones integradas:

- Envio de e-CF mediante `POST /api/v1/ecf/send`.
- Consulta de estado por ID.
- Consulta del trackId en DGII.
- Consulta por eNCF.
- Listado paginado con filtros.
- Descarga del XML firmado.

La clave compartida previamente debe regenerarse porque quedo expuesta en un mensaje.

## Nota fiscal importante

Este prototipo genera e-NCF con estructura academica `E` + tipo `31/32` + secuencia de 10 digitos, calcula ITBIS y produce un XML interno para demostracion. Para operar legalmente en produccion se requiere autorizacion de DGII, rangos reales, XML conforme al XSD oficial, firma digital y comunicacion con los servicios oficiales de facturacion electronica.

Fuentes consultadas:

- DGII, Tipos y estructura e-CF: https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/TipoyEstructurae-CF.aspx/1000
- DGII, Documentacion sobre e-CF: https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/documentacionSobreE-CF.aspx
- DGII, Formato Comprobante Fiscal Electronico v1.0: https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Formatos%20XML/Formato%20Comprobante%20Fiscal%20Electr%C3%B3nico%20%28e-CF%29%20v1.0.pdf
