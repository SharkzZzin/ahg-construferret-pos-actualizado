# Integracion IMECF

## Estado actual

La aplicacion ya soporta:

- Perfiles independientes para varias empresas IMECF.
- Credenciales cifradas y acceso exclusivo para administradores.
- Confirmacion de contrasena antes de modificar credenciales.
- Validacion DGII y prueba de conexion obligatorias antes de activar un perfil.
- Cambio dinamico de empresa, RNC, ambiente y portal sin reiniciar el codigo.
- Enviar e-CF 31 y 32.
- Guardar ID del documento, trackId, eNCF y estado devueltos por IMECF.
- Consultar el estado del documento por ID.
- Consultar el trackId directamente en DGII.
- Buscar documentos por eNCF.
- Listar documentos con filtros y paginacion.
- Descargar el XML firmado.
- Continuar en modo academico cuando IMECF este apagado.
- Generar el cuerpo completo de e-CF 31 y 32 con totales, ITBIS, forma de pago y detalles.
- Probar la conexion desde Reportes sin transmitir un documento.
- Operar con proveedor local cuando la integracion real no esta configurada.

## Reutilizacion de Negocio Cloud

Se reviso el modulo ubicado en `negocio-cloud`. Su proveedor IMECF real todavia
bloquea deliberadamente los envios. Por esa razon no se sustituyo el cliente
actual, que ya implementa los endpoints reales documentados.

Se reutilizaron y adaptaron estas decisiones:

- Separacion explicita entre proveedor local y real.
- Prueba de conexion independiente de la emision.
- Variables de entorno para credenciales.
- Registro de estado y mensajes del proveedor.

Tambien se adapto su login al backend Python:

- Identificacion por correo o telefono.
- Hash de contrasena con scrypt.
- Sesiones persistentes y cookie HttpOnly.
- Usuario y rol visibles en el POS.
- Cierre de sesion.

## Datos confirmados

- Espacio de trabajo asignado en IMECF: UTESA.
- Titular del certificado fiscal `.p12`: PARTY S FOOD SRL.
- RNC del emisor fiscal: 132907401.
- Ambiente: Test.
- Estado: Activa.
- La API Key identifica automaticamente la empresa.
- IMECF administra el certificado `.p12`; la aplicacion no almacena ni manipula
  el archivo del certificado.

## Activacion

1. Regenera la API Key antes de pasar a produccion, porque fue compartida por mensaje.
2. Crea una copia de `.env.example` llamada `.env`.
3. Completa:

```text
IMECF_API_KEY=TU_CLAVE
IMECF_ENABLED=1
AHG_FISCAL_ENV=test
AHG_COMPANY_RNC=132907401
AHG_COMPANY_NAME=PARTY S FOOD SRL
IMECF_WORKSPACE_NAME=UTESA
```

4. Inicia la aplicacion normalmente:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m ahg_pos.app
```

El archivo `.env` esta excluido por `.gitignore`.

## Validacion de compradores

La aplicacion ya integra:

- Consulta DGII por RNC o cedula mediante `GET /api/v1/dgii/rnc`.
- Validacion de cedula en JCE mediante `GET /api/v1/dgii/jce`.
- Autocompletado del nombre del comprador y visualizacion de su foto cuando
  la respuesta de JCE la incluye.

## Pendiente antes de produccion

- Confirmar el formato de `DetallesItems.Item` para varios articulos.
- Completar el catalogo de unidades de medida distintas de la unidad `43`.
- Validar las reglas de articulos exentos y tasas de ITBIS diferentes.
- Emitir un comprobante controlado en Test y verificar estado, trackId y XML.
