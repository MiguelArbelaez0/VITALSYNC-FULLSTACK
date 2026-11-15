# Portal administrativo de VITALSYNC

El portal está dentro del despliegue `vitalsync`, comparte el login y la API de los portales de paciente y médico, y usa la misma base PostgreSQL. En local se abre en [http://localhost:5188/admin](http://localhost:5188/admin). Un usuario autenticado con rol `ADMIN` entra en `/admin`; los otros roles se redirigen a su propio portal.

## Secciones

La navegación contiene nueve áreas:

1. **Dashboard:** conteos consultados en PostgreSQL, filtrables por fecha; estados de cita, modalidad y pagos.
2. **Médicos:** perfil, especialidad, biografía, modalidades, agenda, estado de acceso y solicitud de recuperación. Alta y edición usan cuentas vinculadas; nunca se muestra su contraseña.
3. **Pacientes:** búsqueda por nombre, correo o documento; estado administrativo, plan contratado, citas y notificaciones. El panel no consulta modelos clínicos ni incluye diagnósticos, alergias, medicamentos o evoluciones.
4. **Citas:** búsqueda y filtros por paciente, profesional, especialidad, fecha, estado y modalidad; detalle de transiciones, cancelación justificada y enlace de reprogramación a una reserva nueva ya confirmada.
5. **Disponibilidad:** turnos individuales y jornadas futuras por médico, borradores/publicación y bloqueos de fechas reversibles con auditoría.
6. **Planes:** catálogo editable por especialidades, modalidad, precio, duración, copagos, cupo, beneficios y restricciones; historial de versiones y contrataciones.
7. **Pagos y devoluciones:** pagos simulados, conciliación idempotente y solicitudes de devolución con su historial.
8. **Auditoría:** operaciones administrativas actuales e historial de auditoría previo, excluyendo eventos clínicos.
9. **Configuración:** contacto institucional, políticas visibles, administradores, permisos por módulo y cola de recuperación de acceso.

Las listas se paginan y consultan al servidor; las acciones muestran errores y estados de guardado. El diseño se adapta a escritorio y móvil. El portal actualiza sus consultas TanStack Query después de cada mutación.

## Privacidad y autorización

El backend valida `ADMIN` y un permiso para cada módulo: `dashboard`, `doctors`, `patients`, `appointments`, `availability`, `plans`, `payments`, `refunds`, `audit`, `settings` y `accounts`. La interfaz oculta acciones de cuentas cuando el usuario no tiene ese permiso, pero la autorización verdadera siempre la aplica FastAPI. Un usuario sin concesión explícita conserva el conjunto completo solo para la cuenta administrativa preexistente de demostración; las nuevas cuentas reciben los módulos concedidos al crearlas.

No hay un endpoint administrativo de historias clínicas. El detalle de paciente se proyecta mediante campos administrativos permitidos; la auditoría de accesos denegados conserva método, ruta de plantilla y estado HTTP, sin cuerpos, tokens, consultas ni contenido clínico. La API de historia clínica mantiene los controles médicos existentes y deniega a `ADMIN`.

La gestión no cambia roles de cuentas. Una persona titular conserva su contraseña hasta que canjea expresamente un enlace. Desactivar cuenta cierra sus sesiones; no se permite bloquear la propia cuenta administrativa ni retirar al último administrador activo de privilegios completos.

## Reglas de negocio

- Las ediciones del catálogo generan versiones. Cada contratación conserva los términos y el importe capturados al comprar; las citas guardan la información histórica mostrada en su reserva. Cambiar o desactivar un plan afecta compras y renovaciones futuras, no reescribe pagos, citas o condiciones contratadas. Las condiciones antiguas que no se podían reconstruir se etiquetan `LEGACY_OBSERVED` en vez de inventarlas.
- Las renovaciones son manuales (`MANUAL_NO_AUTORENEW`): cada persona inicia y aprueba su pago. Renovar el mismo plan extiende el período por la duración vigente del catálogo; comprar otro plan sustituye las condiciones vigentes después de la aprobación. No hay débitos automáticos.
- Deshabilitar un médico, cambiar su especialidad/modalidades o editar un turno no puede dejar citas futuras o retenciones huérfanas. FastAPI bloquea el médico, revisa conflictos y revierte el cambio completo si hay conflicto. Para resolver la agenda se cancela con motivo y se crea una reserva nueva por el flujo normal del paciente; se puede dejar trazado el vínculo de reprogramación.
- La liberación de un bloqueo agrega un registro de liberación; el bloqueo original se conserva para auditoría. No se borran turnos pasados.
- La conciliación solo admite resultado aprobado o rechazado y llama a la misma lógica de pagos del paciente. La repetición no vuelve a activar una suscripción ni a confirmar una cita.
- Las devoluciones son **simuladas** y por el valor completo del pago aprobado. Se admite una solicitud por pago. El grafo es `REQUESTED → REVIEWING → APPROVED` o `REJECTED`, después `APPROVED → AUTHORIZED → PROCESSED` o `FAILED`. Se comprueba otra vez la elegibilidad al autorizar/procesar; no se procesan devoluciones reales ni se altera el pago original. Un copago requiere una cita cancelada; un pago de plan requiere que ya no esté vigente. Claves de operación y versiones controlan duplicados y escrituras obsoletas.
- La reprogramación administrativa vincula una cita cancelada con otra cita confirmada futura de la misma persona. No mueve el cobro ni crea cobertura, retención, pago o reserva por fuera del flujo del paciente.

## Iniciar y entrar

Desde la raíz del repositorio, inicia el proyecto existente:

```powershell
docker compose -p vitalsync up -d --build --wait
docker compose -p vitalsync ps
```

El inicio conserva el volumen externo `vitalsync_vitalsync_data`. No ejecutes `down -v` ni elimines volúmenes. La contraseña de `admin@vitalsync.demo` no se reemplaza al arrancar ni al ejecutar el seed. En esta instalación usa la contraseña que ya tenía la cuenta. Si no está disponible, usa el procedimiento de recuperación siguiente para elegir una nueva contraseña sin exponerla en la aplicación ni cambiarla antes de que su titular canjee el enlace.

## Entrega privada y recuperación de acceso

1. Entra con una cuenta administrativa autorizada y ve a **Configuración → Administradores y permisos**.
2. Usa **Recuperar acceso** para crear una solicitud. La API solo registra `PENDING`; no modifica la contraseña ni entrega el token.
3. En la misma computadora local, ejecuta el wrapper como operador autorizado:

   ```powershell
   powershell -ExecutionPolicy Bypass -File infrastructure/Issue-Access-Recovery.ps1 -Email admin@vitalsync.demo
   ```

   `-Email` limita la emisión a esa cuenta. Para emitir varias solicitudes pendientes debes indicarlo explícitamente con `-AllPending`. El comando crea un archivo JSON bajo `Escritorio\VITALSYNC-CREDENCIALES\<fecha-id>\recovery-links.json`, con ACL solo para el usuario de Windows y `SYSTEM`, valida SHA-256 y borra la copia temporal del contenedor. Mantén ese archivo privado; contiene enlaces de un solo uso válidos por 24 horas.
4. Abre el `local_url` del registro correspondiente en el mismo navegador. La página limpia el fragmento del URL y permite que la persona titular elija una contraseña de al menos 12 caracteres con mayúscula, minúscula y número. El token se invalida al canjearlo; se revocan sesiones anteriores y se registra auditoría.
5. Borra el archivo privado cuando la entrega termine.

No copies esos enlaces en documentación, Git, correo o capturas. La contraseña nunca se imprime ni se entrega por la aplicación. Crear una cuenta profesional desde el portal también genera una solicitud de recuperación, sin contraseña por defecto publicada.

## Migración y mantenimiento

La revisión `20261120_admin_portal` depende de `20261119_clinical_history` y crea tablas laterales para permisos, términos capturados, versiones, auditoría, recuperación, devoluciones, reprogramaciones, liberación de bloqueos y configuración. La migración añade observaciones desde filas existentes sin actualizar ni recrear pacientes, médicos, pagos, planes contratados, citas o historiales. El downgrade se bloquea porque eliminar esas nuevas tablas destruiría trazabilidad. Antes de aplicarla, usa el respaldo documentado en [DOCKER_UNIFICADO.md](DOCKER_UNIFICADO.md).

Comandos útiles:

```powershell
docker compose -p vitalsync exec backend alembic current
docker compose -p vitalsync exec backend python -m app.seed
docker compose -p vitalsync logs --tail 100 backend
powershell -ExecutionPolicy Bypass -File infrastructure/Backup-Vitalsync.ps1
```

## Validación y capturas

La suite backend y Playwright crean bases temporales únicas `vitalsync_test_audit_*`; sus guardas validan el nombre antes del `TRUNCATE`. No modifican la base de prueba preexistente ni la aplicación. Frontend: `cd frontend; npm test; npm run build`. Ejecuta pytest y Playwright en serie para evitar contención de recursos.

Capturas E2E con datos de la base aislada:

| Módulo | Escritorio | Móvil |
| --- | --- | --- |
| Dashboard | [Ver captura](screenshots/admin-dashboard-desktop.png) | [Ver captura](screenshots/admin-dashboard-mobile.png) |
| Médicos | [Ver captura](screenshots/admin-doctors-desktop.png) | [Ver captura](screenshots/admin-doctors-mobile.png) |
| Pacientes | [Ver captura](screenshots/admin-patients-desktop.png) | [Ver captura](screenshots/admin-patients-mobile.png) |
| Citas | [Ver captura](screenshots/admin-appointments-desktop.png) | [Ver captura](screenshots/admin-appointments-mobile.png) |
| Disponibilidad | [Ver captura](screenshots/admin-availability-desktop.png) | [Ver captura](screenshots/admin-availability-mobile.png) |
| Planes | [Ver captura](screenshots/admin-plans-desktop.png) | [Ver captura](screenshots/admin-plans-mobile.png) |
| Pagos y devoluciones | [Ver captura](screenshots/admin-payments-desktop.png) | [Ver captura](screenshots/admin-payments-mobile.png) |
| Auditoría | [Ver captura](screenshots/admin-audit-desktop.png) | [Ver captura](screenshots/admin-audit-mobile.png) |
| Configuración | [Ver captura](screenshots/admin-configuration-desktop.png) | [Ver captura](screenshots/admin-configuration-mobile.png) |

Los datos y cuentas de las capturas provienen únicamente de `vitalsync_test`; no se presentan registros personales del volumen principal como ficticios. Las pruebas se reportan con sus resultados reales en [VALIDACION.md](VALIDACION.md).
