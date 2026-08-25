# Guía general - AHG CONSTRUFERRET POS

Versión 3.0 - agosto de 2026

Esta guía reúne los puntos de entrada de la documentación vigente del sistema publicado con Vercel y Supabase.

## Acceso

Aplicación productiva: `https://ahg-construferret-pos.vercel.app/`

Cuando no hay una sesión activa se presenta una portada informativa. Pulsa **Acceder** en la parte derecha para abrir el formulario de inicio de sesión.

Después de iniciar sesión se abre el dashboard principal, con ventas del día, pendientes, stock crítico, caja, tendencia, estado fiscal, documentos recientes, productos destacados y accesos rápidos según los permisos del usuario.

## Manual de usuario

Consulta `docs/manuales/MANUAL_USUARIO.md` para aprender, con capturas reales, a:

- utilizar el dashboard;
- facturar y crear pre-facturas;
- consultar y aplicar notas de crédito vigentes;
- registrar pagos mixtos;
- administrar artículos, clientes y proveedores;
- recibir compras, actualizar costos y pagar balances de proveedores;
- administrar cuentas por cobrar y registrar abonos;
- emitir devoluciones parciales o totales con reposición de inventario;
- atender solicitudes Customer;
- controlar inventario;
- operar Gestión Fiscal e IMECF en prueba;
- consultar facturas;
- abrir y cuadrar caja;
- revisar auditoría;
- configurar usuarios y módulos;
- usar los portales Customer y su asistente.

La versión imprimible está en `output/pdf/manual_usuario_ahg_construferret_pos.pdf`.

## Manual de instalación

Consulta `docs/manuales/MANUAL_INSTALACION.md` para:

- clonar la rama vigente de GitHub;
- ejecutar el proyecto localmente;
- conectar Supabase;
- registrar variables en Vercel;
- configurar correo y servicios de prueba;
- desplegar, verificar, respaldar y actualizar el sistema.

La versión imprimible está en `output/pdf/manual_instalacion_ahg_construferret_pos.pdf`.

## Instalación rápida

    git clone https://github.com/SharkzZzin/ahg-construferret-pos-actualizado.git
    cd ahg-construferret-pos-actualizado
    git switch agent/pos-updated-20260727
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    $env:PYTHONPATH="$PWD"
    python -m ahg_pos.app

Abre `http://127.0.0.1:8765/`. El modo local usa SQLite cuando no existe `DATABASE_URL`; la publicación en Vercel debe usar Supabase PostgreSQL.

## Flujo operativo breve

1. Inicia sesión y revisa el dashboard.
2. Abre caja si vas a recibir efectivo.
3. Atiende pre-facturas y solicitudes Customer.
4. Factura y registra todos los medios de pago.
5. Consulta una nota vigente antes de aplicarla.
6. Recibe mercancía en Compras y registra cobros o pagos pendientes.
7. Gestiona devoluciones y verifica su nota de crédito.
8. Revisa inventario y documentos fiscales pendientes.
9. Cierra la caja y valida Auditoría.

## Seguridad

No guardes claves en Git. Protege la cadena de Supabase, el secreto de sesión, las contraseñas de aplicación, las credenciales IMECF y las claves de pago. Asigna a cada usuario únicamente los módulos que necesita.
