# Portal médico de VITALSYNC

Implementado en `codex/doctor-portal`, creada desde `6739a25` (incluye `bd25468` y la integración del ciclo de vida del paciente). La rama del paciente no se modifica ni se fusiona en esta entrega.

## Arquitectura y archivos

- `backend/app/core/security.py`: sesión autenticada genérica, dependencia de paciente y dependencia médica. Cada solicitud médica comprueba rol, cuenta activa, vinculación y profesional habilitado.
- `backend/app/models/entities.py`: `DoctorAccount`, asociación única entre `users` y el perfil existente en `doctors`.
- `backend/app/routers/doctor.py`: rutas médicas y proyecciones permitidas; el identificador profesional siempre se deriva de la sesión.
- `backend/app/services/doctor_portal.py`: agenda, fechas de Bogotá, datos limitados y cancelación transaccional.
- `backend/app/services/teleconsultation.py`: una máquina de estados compartida por ambos portales, con bloqueo de filas y autoría diferenciada.
- `backend/app/doctor_demo.py`: alta idempotente y configuración explícita de contraseña local.
- `frontend/src/features/doctor/DoctorPortal.tsx` y `doctor.css`: resumen, agenda, detalle, pacientes, perfil, disponibilidad y sala.
- `frontend/src/app/App.tsx`, `Layout.tsx`, `features/auth/Auth.tsx`: protección, navegación y destino según rol.
- Las consultas de ambos portales se actualizan después de mutaciones, al recuperar foco y periódicamente. Las salas médicas se actualizan cada 5 segundos y las agendas cada 15 segundos.

## API

Todas las rutas siguientes requieren una cuenta DOCTOR activa con perfil habilitado. Un paciente recibe 403 y una sesión ausente o vencida recibe 401. Un recurso ajeno responde 404; las transiciones inválidas, estados terminales o versiones antiguas responden 409.

| Método y ruta | Operación |
| --- | --- |
| GET `/api/doctor/me` | Perfil profesional |
| PATCH `/api/doctor/me` | Editar solamente `bio` |
| GET `/api/doctor/dashboard` | Métricas de hoy en Bogotá, siguiente cita y agenda del día |
| GET `/api/doctor/appointments` | Agenda; filtros `day=YYYY-MM-DD`, `modality`, `status`, `view=all/upcoming/history/cancelled` |
| GET `/api/doctor/appointments/{id}` | Reserva asignada y su historial |
| POST `/api/doctor/appointments/{id}/cancel` | `{version, reason, confirmed:true}` |
| GET `/api/doctor/patients?search=` | Nombre e identificador de pacientes asignados |
| GET `/api/doctor/patients/{id}` | Reservas del paciente relacionadas únicamente con este profesional |
| GET `/api/doctor/availability?day=` | Turnos institucionales y bloqueos de lectura |
| GET `/api/doctor/appointments/{id}/teleconsult` | Estado, presencias, acciones permitidas e historial |
| POST `/api/doctor/appointments/{id}/teleconsult/events` | `{event, reason?}` con los eventos existentes de la máquina de estados |

Las respuestas médicas usan una lista explícita de campos permitidos. No incluyen pagos, copagos, cédulas, teléfonos, contraseñas ni reservas de otros profesionales. La edición de perfil rechaza campos adicionales como `role`, `name` o `specialty`.

## Reglas de operación

La cancelación médica exige una cita CONFIRMED futura, motivo, confirmación y versión vigentes. Puede efectuarse dentro del plazo en el que el paciente ya no puede cancelar. Se bloquea al paciente, a la cita y al profesional en el mismo orden que las reservas existentes. Se conserva la cita, el pago y el historial; se registran actor, momento, motivo y transición CONFIRMED → CANCELLED. La sala queda cancelada y se notifica al paciente. No hay devoluciones ni reasignaciones automáticas. La respuesta `rescheduling_status=CONTACT_SUPPORT` deja explícita la gestión posterior de una nueva reserva.

Las teleconsultas operan solamente como demostración. En DEMO_MODE=true se puede avanzar el reloj virtual sin cambiar la fecha reservada, abrir sala, registrar presencias, iniciar con ambos participantes, finalizar, registrar ausencias o recuperar incidencias. El médico puede simular la llegada del paciente o esperar su ingreso desde el portal del paciente. En DEMO_MODE=false el portal médico no ofrece ni acepta eventos simulados. Ninguna finalización demostrativa acredita atención clínica real.

La finalización actualiza dentro de una sola transacción la cita, la sala, `completion_source=DEMO`, fecha simulada, `clinically_attended=false`, historial, auditoría y notificación. Los bloqueos impiden finalizaciones duplicadas. Los dos portales obtienen el mismo estado persistido y excluyen la cita de Próximas.

## Migración y datos

`20261118_doctor_accounts` desciende de `20261117_lifecycle_merge`; conserva ambas migraciones de demostración de 20261115/20261116 y la unión de ramas existente. Crea únicamente la tabla de vinculación con claves foráneas y unicidad en ambas direcciones. No reemplaza médicos, citas ni historiales. La vinculación de demostración se hace en el seed administrativo, después de migrar, y no dentro de Alembic.

Para ejecutar la versión revisada localmente, desde la raíz:

```powershell
docker compose up -d --build
```

El inicio del backend ejecuta `alembic upgrade head` y el seed idempotente. Se conserva el volumen existente. No es necesario recrear la base ni eliminar volúmenes.

## Acceso médico de demostración

Requiere DEMO_MODE=true. El seed vincula una cuenta nueva `medico@vitalsync.demo` al perfil existente **Dr. Alejandro Méndez (Cardiología)**. No duplica profesionales, no toma control de un correo ya existente y no modifica contraseñas existentes. Si el profesional ya tiene otra cuenta vinculada, se conserva su vinculación.

La contraseña inicial es aleatoria y no se publica. Establecer explícitamente una contraseña local mediante entrada oculta:

```powershell
docker compose exec backend python -m app.doctor_demo --set-password
```

El comando pide la contraseña dos veces, exige 10–128 caracteres, mayúscula, minúscula y número, y registra la operación. Es exclusivamente de demostración. El seed posterior conserva la contraseña elegida. No se modifica `.env` ni se requiere guardar una contraseña en Git.

Abrir `http://localhost:5188/login`, entrar con el correo médico y la contraseña elegida. El destino será `/doctor`. El registro público sigue creando solamente pacientes y el acceso ADMIN permanece restringido.

## Pruebas reproducibles

Backend (solo base aislada `vitalsync_test`, protegida por una aserción de la fixture):

```powershell
docker compose run --rm --no-deps -v "${PWD}\backend:/app" backend python -m pytest -q
```

Frontend:

```powershell
cd frontend
npm test
npm run build
```

E2E médico, desde la raíz y en un proceso PowerShell independiente:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/test-doctor-portal.ps1
```

El script usa temporalmente el proyecto `vitalsync-doctor-check`, el override explícito `infrastructure/compose.test.yml`, base `vitalsync_test`, volumen propio y puertos 5589/8189/5289. En `finally` retira sus contenedores y red, conservando su volumen, incluso si las pruebas fallan. El despliegue permanente de ambos portales sigue siendo únicamente `vitalsync`. Comprueba la contraseña existente de pruebas y no la modifica. Playwright verifica escritorio y móvil, reserva presencial y virtual, separación de roles, presencias, finalización compartida, historial, cancelación y notificaciones. En escritorio reinicia PostgreSQL y backend, sin borrar volúmenes, y vuelve a comprobar estados y sesiones persistentes. Las capturas están en `docs/screenshots/doctor-*.png`; los reportes y trazas temporales de Playwright están excluidos de Git.

El volumen de pruebas anterior ya tiene la contraseña de pruebas configurada. Para un volumen nuevo, el alta del seed conserva una contraseña aleatoria. Un operador debe levantar explícitamente el override aislado y ejecutar allí `python -m app.doctor_demo --set-password` para elegir la contraseña de pruebas `DoctorE2E2026!`; el runner no restablece contraseñas existentes. Nunca se debe usar el volumen principal en ese override.

El servicio PostgreSQL se llama ahora `db`. El E2E reinicia `vitalsync-doctor-check-db-1` y su backend para comprobar persistencia. Consulta [Docker unificado](DOCKER_UNIFICADO.md) para arranque, volúmenes y limpieza.


## Validación de entrega · 12 de noviembre de 2026

| Comprobación | Resultado |
| --- | --- |
| Backend existente y médico | 121 casos aprobados en la suite completa |
| Casos adicionales de desactivación y cancelación concurrente | 3 aprobados |
| React | 36 aprobados (26 existentes y 10 médicos) |
| E2E médico | 2 aprobados: escritorio y móvil |
| E2E existentes del paciente | 10 aprobados: escritorio y móvil |
| TypeScript + Vite, local y Docker | Compilación aprobada |
| Alembic | Una cabeza: `20261118_doctor_accounts`; actualización desde ambos historiales y reparación histórica aprobadas |
| Persistencia | PostgreSQL y backend reiniciados en el stack aislado; estados, historial y sesiones conservados |
| Fallos finales | Ninguno |

Los fallos iniciales de validación se corrigieron: un selector de prueba no admitido por TypeScript, una fecha fija de fixture que ya había pasado y el nombre accesible de los selectores de agenda. Vite conserva el aviso de tamaño del paquete JavaScript (>500 kB); la suite backend avisa de una deprecación de Starlette/httpx. Ninguno impide las pruebas o la compilación.

En la entrega inicial del portal médico, el Docker principal no se migró durante las pruebas. Posteriormente se activó y unificó el despliegue principal con `20261118_doctor_accounts`, conservando sus datos; el estado actual y sus comprobaciones están en [DOCKER_UNIFICADO.md](DOCKER_UNIFICADO.md). Las pruebas backend y E2E siguen usando bases aisladas.

### Capturas reales

- [Resumen de escritorio](screenshots/doctor-dashboard-desktop.png)
- [Resumen móvil](screenshots/doctor-dashboard-mobile.png)
- [Agenda de escritorio](screenshots/doctor-agenda-desktop.png)
- [Agenda móvil](screenshots/doctor-agenda-mobile.png)
- [Sala finalizada de escritorio](screenshots/doctor-room-desktop.png)
- [Sala finalizada móvil](screenshots/doctor-room-mobile.png)


## Archivos de esta entrega

- `README.md`
- `backend/alembic/versions/20261118_doctor_accounts.py`
- `backend/app/core/security.py`
- `backend/app/doctor_demo.py`
- `backend/app/main.py`
- `backend/app/models/entities.py`
- `backend/app/routers/__init__.py`
- `backend/app/routers/doctor.py`
- `backend/app/seed.py`
- `backend/app/services/doctor_portal.py`
- `backend/app/services/teleconsultation.py`
- `backend/tests/test_demo_migration.py`
- `backend/tests/test_doctor_portal.py`
- `docs/doctor-portal.md`
- `docs/screenshots/doctor-agenda-desktop.png`
- `docs/screenshots/doctor-agenda-mobile.png`
- `docs/screenshots/doctor-dashboard-desktop.png`
- `docs/screenshots/doctor-dashboard-mobile.png`
- `docs/screenshots/doctor-room-desktop.png`
- `docs/screenshots/doctor-room-mobile.png`
- `frontend/e2e/doctor-portal.spec.ts`
- `frontend/src/app/App.tsx`
- `frontend/src/app/Layout.tsx`
- `frontend/src/features/appointments/Appointments.tsx`
- `frontend/src/features/auth/Auth.tsx`
- `frontend/src/features/dashboard/Dashboard.tsx`
- `frontend/src/features/doctor/DoctorPortal.tsx`
- `frontend/src/features/doctor/doctor.css`
- `frontend/src/features/notifications/Notifications.tsx`
- `frontend/src/hooks/useAuth.tsx`
- `frontend/src/test/doctor.test.tsx`
- `frontend/src/test/portal.test.tsx`
- `frontend/src/types/index.ts`
- `infrastructure/test-doctor-portal.ps1`
