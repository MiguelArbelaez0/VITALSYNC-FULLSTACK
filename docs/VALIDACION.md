# Validación de la primera entrega

## Auditoría integral final (14 de noviembre de 2026)

La revisión se ejecutó en la rama local `codex/integration-final`, creada desde `46d22ea`; los commits de paciente, médico y administrador ya forman parte de esa línea. No se hizo merge adicional, push ni publicación. Se agregó un flujo local de GitHub Actions en `.github/workflows/ci.yml`; aún no se ejecuta en GitHub porque no se publicó.

| Comprobación | Resultado |
| --- | --- |
| Backend completo en PostgreSQL | **158 aprobadas** en `vitalsync_test_audit_*` |
| Frontend Vitest | **41 aprobadas** |
| Playwright escritorio y móvil | **16 aprobadas**; paciente, médico, administrador, agenda compartida y teleconsulta |
| TypeScript y build React | **Aprobados**; aviso no bloqueante por chunk principal de 588.81 kB |
| Compose / Docker Desktop | Solo el proyecto `vitalsync`; `db`, `backend` y `frontend` saludables |
| API y rutas SPA | `/api/health` OK; `/login`, `/portal`, `/doctor` y `/admin` responden HTTP 200 |
| Alembic | `20261120_admin_portal` es la versión aplicada y única cabeza |
| BD principal / volumen | `vitalsync` sobre `vitalsync_vitalsync_data`; 55 pacientes, 5 médicos, 60 citas y 3 planes |
| BD de pruebas que ya existía | `vitalsync_test` conservó 15 pacientes, 16 citas y 9 encuentros clínicos |
| Respaldo previo a la auditoría | PASS: `C:\Users\USUARIO\Desktop\VITALSYNC-RESPALDOS\vitalsync-20261114-231519.dump`, 170332 bytes, SHA-256 `1412751ca0e184e2e9b19c2e85ede60eb800b59d6fed9151b2be70c1b6064e42` |

Los runners ahora crean bases temporales con prefijo `vitalsync_test_audit_` y no truncan bases preexistentes. Las cuatro bases creadas durante esta auditoría se mantienen en PostgreSQL; no se borraron. Al iniciar el backend, la migración ya estaba aplicada y el seed dejó intacta la contraseña del paciente existente. El seed ahora crea una clave aleatoria solo para un usuario paciente nuevo, y las guías actuales no publican contraseñas compartidas.

**Seguridad de credenciales:** al iniciar esta publicación, dos claves de cuentas ficticias encontradas en commits históricos todavía autenticaban. Se rotaron las cuentas existentes de administrador y paciente mediante solicitudes administrativas y enlaces locales de un solo uso. Las claves anteriores ahora reciben HTTP 401 y las nuevas se validaron con roles `ADMIN` y `PATIENT`. El archivo local que contiene las nuevas claves tiene ACL protegida para el usuario de Windows y `SYSTEM`; no forma parte del repositorio. Gitleaks no encontró otros secretos con sus reglas estándar. Los valores antiguos continúan en el historial público, pero ya no permiten acceder a esas cuentas. No se reescribió historia.

## Actualización: cancelación universal de planes (9 de noviembre de 2026)

La migración `20261112_plan_cancellation` quedó aplicada en PostgreSQL. La nueva ruta `POST /api/my-plan/cancel` se verificó con los cuatro planes de prueba (Básico, Estándar, Premium y un plan añadido durante la prueba). La suite backend completa aprobó **53 pruebas**; el frontend aprobó **17 pruebas unitarias** y **2 recorridos E2E** en escritorio y emulación iPhone 13. Ambos recorridos E2E cancelaron Estándar con la interfaz real y confirmaron desistimiento, resultado persistido, tarjeta actualizada y ausencia de desplazamiento horizontal. `npm run build` y `git diff --check` finalizaron sin errores.

## Actualización: modalidades y cobertura (9 de noviembre de 2026)

La consulta virtual aparece primero como recomendada y se puede cambiar por presencial. Se validó la cobertura por las modalidades y especialidades configuradas, los copagos, los profesionales y turnos compatibles, el filtro de Mis citas y el rechazo de modalidades no admitidas. Alembic aplicó `20261113_modality_guards` sobre PostgreSQL existente con restricciones JSONB e índices GIN; no se borraron ni recrearon volúmenes. Resultado: **64 pruebas backend**, **19 frontend**, **2 E2E** (escritorio y móvil) y compilación de producción aprobados. E2E verificó que Básico no puede retener cita virtual, cambió a Estándar, reservó en ambas modalidades y completó cancelación e historial. La comprobación `verify_persistence.py` terminó en **PASS** tras reiniciar los servicios conservando PostgreSQL y comprobar cita presencial y virtual, pagos, plan, sesión, sala virtual e historial.

Entorno probado: Windows, Docker Desktop con motor Linux, Node 24.14.1, React 19.3.1, Vite 8.3.6, Python 3.13 dentro de contenedor y PostgreSQL 17. Ejecución del 8 de noviembre de 2026 (Bogotá).

## Evidencia automatizada

| Verificación | Resultado |
| --- | --- |
| `npm run build` | TypeScript y compilación Vite correctos |
| `infrastructure/Test-Backend.ps1` | 47 pruebas Pytest aprobadas sobre PostgreSQL real |
| `npm test` | 15 pruebas Vitest / React Testing Library aprobadas |
| `npm run test:e2e` | 2 recorridos Playwright aprobados: escritorio e iPhone 13 emulado en Chromium |
| `python infrastructure/verify_persistence.py` | PASS; reinicio real de frontend, backend y PostgreSQL conservando el volumen |
| `npm install` / `npm ci` | Auditoría npm sin vulnerabilidades reportadas en las dependencias instaladas |
| Alembic | `20261110_virtual_history (head)` aplicado en la base de demostración; los datos previos se mantienen |

La suite backend usa exclusivamente `vitalsync_test`, creada dentro del contenedor PostgreSQL de VITALSYNC. La BD de demostración no se trunca. Las 47 pruebas pasaron en 49,65 segundos. La base de demostración mantiene citas presenciales y virtuales; la nueva columna conserva el valor `PRESENCIAL` para los registros antiguos. El resultado de los servicios se registra en el informe de entrega.

## Cobertura backend

- Registro, duplicado, inyección de rol rechazada, hash Argon2 y cookie HttpOnly/SameSite.
- Login correcto/incorrecto, logout, revocación y persistencia de sesión, expiración, rol administrativo rechazado y origen cruzado bloqueado.
- Perfil y dashboard derivados de datos reales.
- Plan inexistente, vencido, cobertura insuficiente; aprobación, rechazo, pendiente y conciliación.
- Idempotencia del pago del plan, renovación de vigencia sin doble aplicación y resultado definitivo de conciliación.
- Directorio, filtros, especialidades, horarios libres y bloqueados; horario pasado rechazado antes de cobro.
- Retención, liberación, expiración y rechazo de pago tardío.
- Copago requerido, rechazo y reintento; pendiente/en conciliación sin duplicación; Premium sin copago.
- Confirmación idempotente, revalidación de médico, bloqueos nuevos, plan, copago y jornada publicada.
- Dos pacientes concurrentes compiten por el mismo horario: uno obtiene retención y otro recibe conflicto.
- Dos confirmaciones simultáneas de la misma retención devuelven la misma cita.
- Solapamientos parciales rechazados en el servicio y por la restricción PostgreSQL ante inserción directa.
- Cancelación propia, conservación de historial, notificación y liberación del horario.
- Cita ajena, atendida, cancelación repetida, política, versión y falta de confirmación expresa.
- Cancelación simultánea: una sola actualización e historial/notificación únicos.
- Filtrado de médicos y turnos por modalidad; cobertura virtual rechazada cuando el plan no la incluye; Estándar/Premium virtual con copago correcto.
- Conflicto de horario entre una reserva presencial y otra virtual; sala virtual persistida, transiciones secuenciales, acceso solo de la persona propietaria y cancelación.
- Migración virtual conserva las citas anteriores y crea cobertura/modalidades compatibles.
- Rollback en confirmación, cancelación y fallo al hacer commit; nunca respuesta de éxito sobre un commit fallido.
- Seed idempotente, restricciones en la BD y pagos demo deshabilitados fuera de demo.

## Cobertura frontend

Validación de formularios, login conectado, rutas protegidas, logout que retira la vista, métricas del dashboard, carga/error, directorio y filtros, selección de modalidad, retención por API, confirmación, comprobante y sala virtual con estados traducidos.

Estas pruebas de componente usan respuestas controladas para aislar la interfaz. La persistencia y la integración reales se comprueban con Playwright y PostgreSQL, sin interceptar peticiones.

## Recorrido web real

En cada tamaño Playwright crea una cuenta nueva, cierra e inicia sesión, intenta reservar sin plan, simula rechazo de pago de plan, genera un pendiente y lo concilia; luego agenda presencial, revisa y recarga el comprobante, verifica Mis citas y cancelación, activa Estándar, agenda virtual, abre la teleconsulta simulada, avanza un estado y cancela para liberar el turno de prueba. El recorrido también consulta historial y notificaciones y verifica ausencia de desplazamiento horizontal.

Capturas obtenidas de esos recorridos e inspeccionadas visualmente:

| Pantalla | Escritorio | Móvil |
| --- | --- | --- |
| Dashboard | [Ver](screenshots/dashboard-desktop.png) | [Ver](screenshots/dashboard-mobile.png) |
| Comprobante | [Ver](screenshots/receipt-desktop.png) | [Ver](screenshots/receipt-mobile.png) |
| Sala virtual simulada | [Ver](screenshots/teleconsult-desktop.png) | [Ver](screenshots/teleconsult-mobile.png) |
| Historial canceladas | [Ver](screenshots/history-desktop.png) | [Ver](screenshots/history-mobile.png) |

La prueba móvil es emulación de dimensiones y entrada táctil de iPhone 13 en Chromium. No se ejecutó Safari ni un iPhone físico.

## Persistencia tras reiniciar

El script independiente crea una cuenta nueva, aprueba un plan Premium, confirma una cita presencial y otra virtual, y avanza el estado de la sala virtual. Guarda una instantánea de perfil, plan, pagos, ambas citas, sala, historial y notificaciones. Luego ejecuta `docker compose restart`, espera la API y compara todos esos datos usando la misma cookie. Después cancela ambas citas. Evidencia: [persistence-result.json](persistence-result.json).

## Incidencias corregidas durante la validación

- Seed: se insertó el paciente antes de crear su notificación para respetar la FK.
- Logout: se corrigió la invalidación de la caché para retirar inmediatamente la pantalla autenticada.
- Navegación móvil: se agregó desplazamiento al menú para alcanzar todas las acciones en alturas cortas.
- Transacciones: el commit se realiza antes de enviar la respuesta, con prueba de fallo al confirmar el commit.

## Límites de esta validación

Vite muestra una advertencia de tamaño del bundle principal (~526 kB sin gzip, ~164 kB comprimido); no impide compilar ni ejecutar la demo. Starlette emite una advertencia de deprecación sobre su adaptador de pruebas con httpx; las pruebas ejecutadas pasan. La cobertura aquí es funcional, no una auditoría de seguridad o una prueba de carga sostenida.

No se probaron videollamadas, pagos reales, correos, push, atención médica, módulos administrativos, devoluciones ni despliegue porque no están implementados. Los errores de base de datos se prueban mediante fallo inyectado y rollback, sin dañar la base de demostración. No se utilizó SQLite ni se declaró un navegador real sin ejecutarlo.

## Actualización: portal administrativo integrado (14 de noviembre de 2026)

Se completó en la rama `codex/admin-portal`, usando el proyecto Compose `vitalsync` y la base principal existente. El administrador comparte login y despliegue con los portales de paciente y médico. Se añadieron los nueve módulos descritos en [admin-portal.md](admin-portal.md), controles de permisos por módulo en servidor, auditoría, recuperación privada y protección para que administración no acceda a historias clínicas.

| Comprobación | Resultado |
| --- | --- |
| Backend completo, PostgreSQL aislado `vitalsync_test` | **158 aprobadas** |
| Frontend Vitest / React | **41 aprobadas** |
| Playwright con build Docker final | **16 aprobadas**: escritorio y emulación móvil Chromium |
| `npm run build` | TypeScript y Vite aprobados; advertencia de chunk principal de 588.81 kB |
| Acceso al administrador de la base principal | Login válido, dashboard OK, cierre de sesión OK |
| Acceso administrativo a historia clínica | **403** |
| Migración Alembic | `20261120_admin_portal` aplicada; una sola cabeza |
| Persistencia principal después de reinicio | **PASS**, proyecto `vitalsync`, 3 servicios saludables, 38 tablas verificadas, sesiones de los tres roles persistidas |
| Agenda entre médico y paciente | 3 citas asignadas verificadas; 3 compartidas en ambas vistas |
| Filas previas a la migración | Huellas de contenido idénticas para las 24 tablas anteriores |
| Datos de negocio creados por la validación principal | 0 usuarios, citas o pagos nuevos |

La migración agregó 13 tablas laterales y no actualizó registros existentes de pacientes, médicos, citas, pagos o planes. La base pasó de 24 a 37 tablas de aplicación (38 al contar `alembic_version`; se excluyen sesiones en la comparación de persistencia). Se conservó el volumen `vitalsync_vitalsync_data`; no se ejecutaron comandos de borrado de datos o volúmenes.

El respaldo anterior a la migración se verificó con `pg_restore -l` y SHA-256: `C:\Users\USUARIO\Desktop\VITALSYNC-RESPALDOS\vitalsync-before-admin-20261114-193653.dump` (132398 bytes; `94172414E8A3C15865CFF3DDC022D67BD161C7BEA130F4F6762AC09FE469E268`). Los archivos de huellas anterior/posterior están en esa misma carpeta, fuera del repositorio. El informe automatizado sin credenciales es [admin-portal-validation.json](admin-portal-validation.json).

Las 18 capturas administrativas se generaron sobre cuentas ficticias de la base de pruebas y se revisaron visualmente: [dashboard](screenshots/admin-dashboard-desktop.png), [configuración](screenshots/admin-configuration-desktop.png), [pacientes móvil](screenshots/admin-patients-mobile.png), y el conjunto completo por módulo/tamaño en [admin-portal.md](admin-portal.md). No se guardaron capturas del volumen principal.

El navegador E2E emula móvil con Chromium; no se probó Safari ni un iPhone físico. Permanecen las advertencias no bloqueantes de deprecación de Starlette/httpx y tamaño del bundle principal. No se realizó push.
## Validación local de v1.1.0

- PostgreSQL conserva el volumen externo `vitalsync_vitalsync_data`. La migración aditiva `20261125_simulation_rooms` es la única cabeza Alembic. El respaldo previo se verificó con `pg_restore` y SHA-256.
- Se conservaron los cinco médicos originales. Se aprovisionaron diez profesionales ficticios adicionales mediante `infrastructure/Provision-Doctors.ps1 -AddAcademicProfiles`. Las diez cuentas nuevas iniciaron sesión y abrieron el portal médico. Las credenciales quedan en un archivo privado fuera de Git.
- Backend completo: 200 pruebas aprobadas en la ejecución final contra PostgreSQL aislado. Frontend: 66 aprobadas y compilación React correcta. Vite conserva el aviso de tamaño para la carga diferida de LiveKit.
- Se probaron en Playwright el registro médico, aprobación, entrega privada, reserva, videollamada, reconexión, finalización e historiales. La simulación se comprobó con un participante y con dos, sin crear citas ni pagos, y con inicio sin cámara ni micrófono. Se verificaron la publicación y recepción de pantalla de prueba, la restauración del diseño y pantalla completa. Capturas: [simulación en escritorio](screenshots/simulation-desktop.png), [simulación en móvil](screenshots/simulation-mobile.png), [pantalla compartida](screenshots/simulation-shared-screen.png).
- LiveKit rechazó tokens previos después de cerrar simulaciones y teleconsultas. El botón oficial de Google cargó en escritorio y móvil tras corregir la resolución del backend al recrear contenedores. Se verificó la privacidad clínica y la entrada médica sin cambio de contraseña en escritorio y móvil.
- El proveedor Google de las pruebas emite tokens RSA de prueba para verificar el flujo. La integración local no valida consentimiento con una cuenta Google real. Las pruebas audiovisuales de esta revisión usan medios sintéticos y dos contextos de navegador en un solo equipo. No evalúan sonido audible, captura física ni conectividad entre redes. Un despliegue externo requiere orígenes HTTPS, señalización WSS y conectividad ICE/TURN adecuada.
