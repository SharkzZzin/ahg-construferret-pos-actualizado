# Manual de instalación - AHG CONSTRUFERRET POS

Versión 3.0 - agosto de 2026

Este documento explica cómo preparar el proyecto para desarrollo local y cómo publicarlo con Vercel y Supabase. Las integraciones fiscales y de pago se configuran exclusivamente en sus ambientes de prueba.

## 1. Arquitectura

La solución utiliza:

- **Vercel:** aplicación web, portal Customer y rutas API.
- **Supabase PostgreSQL:** datos compartidos y persistentes.
- **GitHub:** control de versiones y despliegues.
- **Resend o Gmail SMTP:** confirmaciones de pre-facturas.
- **IMECF TESTeCF:** transmisión académica de comprobantes electrónicos.

SQLite se utiliza solamente en desarrollo local. En Vercel se debe configurar PostgreSQL porque el almacenamiento local de una función no es persistente.

## 2. Requisitos

- Git.
- Python 3.12 o superior.
- Cuenta de GitHub con acceso al repositorio.
- Proyecto de Vercel.
- Proyecto de Supabase con acceso al Pooler IPv4.
- Navegador actualizado.
- Vercel CLI, opcional para administrar despliegues desde PowerShell.

## 3. Descargar el proyecto

En PowerShell:

    git clone https://github.com/SharkzZzin/ahg-construferret-pos-actualizado.git
    cd ahg-construferret-pos-actualizado
    git switch agent/pos-updated-20260727

Para actualizar una copia existente:

    git fetch origin
    git switch agent/pos-updated-20260727
    git pull --ff-only

## 4. Preparar el entorno local

Crear y activar el entorno virtual:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

Iniciar la aplicación:

    $env:PYTHONPATH="$PWD\src"
    python -m ahg_pos.app

Abrir `http://127.0.0.1:8765/`. Si no se define `DATABASE_URL`, se crea una base SQLite local en `data/ahg_demo.db`.

## 5. Preparar Supabase

1. Crea o abre el proyecto de Supabase.
2. En **Connect**, selecciona la cadena PostgreSQL del **Transaction Pooler** compatible con IPv4.
3. Reemplaza la contraseña en la cadena.
4. Conserva activado SSL con `sslmode=require`.
5. Ejecuta `schema/postgres.sql` en el SQL Editor si la base todavía no tiene el esquema.

Ejemplo de formato:

    postgresql://usuario:CONTRASENA@host-pooler:6543/postgres?sslmode=require

No publiques esta cadena ni la guardes en Git.

## 6. Variables de entorno

Registra las variables en **Vercel > Project > Settings > Environment Variables**. Aplica los valores necesarios a Production, Preview y Development según el uso.

Variables principales:

- `DATABASE_URL`: cadena PostgreSQL de Supabase.
- `SECRET_KEY`: secreto largo y aleatorio para sesiones.
- `PUBLIC_BASE_URL`: `https://ahg-construferret-pos.vercel.app`.
- `PAYMENT_MODE`: modo de prueba configurado para el proyecto.
- `PAYPAL_CLIENT_ID` y `PAYPAL_CLIENT_SECRET`: credenciales sandbox si PayPal está habilitado.
- `PAYPAL_MODE`: `sandbox`.

Correo mediante Resend:

- `RESEND_API_KEY`.
- `EMAIL_FROM`: remitente verificado.

Correo mediante Gmail SMTP, como alternativa:

- `SMTP_HOST`: `smtp.gmail.com`.
- `SMTP_PORT`: `587`.
- `SMTP_USER`: cuenta Gmail remitente.
- `SMTP_PASSWORD`: contraseña de aplicación de Google, sin espacios.
- `SMTP_USE_TLS`: `true`.
- `EMAIL_FROM`: cuenta Gmail remitente.

IMECF:

- Registra en el módulo **Gestión Fiscal** las credenciales y URL suministradas para TESTeCF.
- Usa únicamente la URL de prueba.
- Verifica la conexión antes de emitir.
- Nunca guardes tokens o secretos en el repositorio.

## 7. Vincular y desplegar en Vercel

Desde la carpeta del proyecto:

    vercel login
    vercel link
    vercel env pull .env.local
    vercel --prod

Al vincular, selecciona el equipo y el proyecto `ahg-construferret-pos`. También puede conectarse el repositorio desde el panel de Vercel para desplegar automáticamente cada actualización de la rama configurada.

Después del despliegue:

1. Abre `https://ahg-construferret-pos.vercel.app/`.
2. Inicia sesión y confirma que aparece el dashboard.
3. Revisa que no existan errores en los Runtime Logs de Vercel.
4. Confirma que ventas, solicitudes Customer e inventario usan la misma base.

## 8. Inicialización y seguridad

En la primera instalación, cambia inmediatamente cualquier contraseña inicial. Después:

1. Crea un usuario administrador nominal.
2. Asigna módulos desde **Administración**.
3. Restringe Auditoría, Administración, Gestión Fiscal y respaldos.
4. Cierra y vuelve a iniciar sesión con cada perfil de prueba.
5. Verifica que el menú y las API respeten los módulos permitidos.

No compartas `DATABASE_URL`, `SECRET_KEY`, contraseñas de aplicación, credenciales fiscales ni claves de pago.

## 9. Verificación funcional

Ejecuta las pruebas automatizadas:

    $env:PYTHONPATH="$PWD\src"
    python -m pytest -q

Lista mínima de verificación manual:

- El dashboard carga indicadores sin errores.
- Se puede crear una venta de contado.
- Los pagos mixtos deben sumar exactamente el monto pendiente.
- Una nota de crédito vigente puede cargarse y combinarse con otro medio.
- El stock cambia una sola vez por operación.
- Las solicitudes Customer aparecen en Pre-facturas.
- La confirmación por correo se envía cuando se proporciona dirección.
- Gestión Fiscal muestra respuesta y estado del proveedor de prueba.
- Apertura, movimientos y cierre de caja cuadran.
- Auditoría muestra acciones de usuarios, no eventos técnicos internos.
- Un usuario restringido no puede abrir el módulo por menú ni por API.

## 10. Respaldo y recuperación

Para la base compartida, usa las herramientas de respaldo de Supabase. Conserva copias en una ubicación protegida y prueba periódicamente su recuperación.

El respaldo descargable desde Administración se limita a usuarios autorizados. No uses una copia de `data/ahg_demo.db` como respaldo de producción cuando Vercel trabaja con Supabase.

## 11. Actualizaciones

Antes de actualizar:

1. Verifica que el árbol de trabajo esté limpio.
2. Realiza un respaldo de la base.
3. Descarga los cambios con `git pull --ff-only`.
4. Instala dependencias nuevas.
5. Ejecuta todas las pruebas.
6. Despliega y completa la lista de verificación funcional.

Si el cambio modifica el esquema, ejecuta primero la migración prevista y no elimines columnas o datos sin una copia comprobada.

## 12. Solución de problemas

- **Vercel no conecta con Supabase:** confirma Pooler IPv4, puerto, contraseña codificada y `sslmode=require`.
- **El despliegue no refleja cambios:** verifica la rama conectada, el último commit y el alias de producción.
- **No llega el correo:** revisa variables, remitente, contraseña de aplicación, spam y Runtime Logs.
- **Customer y POS muestran datos diferentes:** ambos deben usar la misma `DATABASE_URL`.
- **IMECF no responde:** prueba conexión, credenciales, URL TESTeCF y diagnóstico del documento.
- **Un módulo sigue visible:** guarda permisos, cierra sesión y vuelve a entrar.
- **La aplicación local no inicia:** activa `.venv`, reinstala dependencias y define `PYTHONPATH`.

## 13. Documentación relacionada

- `README.md`: presentación y referencia rápida del repositorio.
- `docs/manuales/MANUAL_USUARIO.md`: operación completa con capturas.
- `output/pdf/manual_usuario_ahg_construferret_pos.pdf`: manual de usuario imprimible.
- `output/pdf/manual_instalacion_ahg_construferret_pos.pdf`: este manual en PDF.
