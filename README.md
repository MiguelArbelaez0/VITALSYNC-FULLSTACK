# VITALSYNC

**Portales de pacientes, médicos y administración en una aplicación local con React, FastAPI y PostgreSQL.** Los perfiles, horarios, planes y pagos son de demostración; las operaciones y la persistencia son reales.

## Inicio rápido en Windows 11

Requisitos: Docker Desktop iniciado con contenedores Linux y Docker Compose v2, Git y PowerShell. La primera construcción necesita Internet para descargar dependencias; la aplicación no necesita servicios en la nube. Node 24 LTS y Python son opcionales para desarrollo y pruebas fuera de Docker.

Desde esta carpeta:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
```

También puedes ejecutar el iniciador. Comprueba la configuración y el volumen persistente; requiere que `.env` ya exista:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/Start-Vitalsync.ps1
```

| Servicio | Dirección local predeterminada |
| --- | --- |
| Portal React | http://localhost:5188 |
| Autenticación compartida | http://localhost:5188/auth |
| Portal paciente | http://localhost:5188/portal |
| Portal médico | http://localhost:5188/doctor |
| Portal administrador | http://localhost:5188/admin |
| FastAPI / Swagger | http://localhost:8088/docs |
| OpenAPI JSON | http://localhost:8088/openapi.json |
| Comprobación de BD | http://localhost:8088/api/health |
| PostgreSQL | localhost:5488, base `vitalsync`, usuario `vitalsync` |

Todos los puertos publicados se vinculan exclusivamente a `127.0.0.1`. Se comprobaron libres antes de iniciar. El proyecto Compose se llama `vitalsync` y el volumen persistente `vitalsync_vitalsync_data`. No se usan servicios, datos, credenciales ni puertos de otros proyectos.

**Paciente ficticio de demostración:** `paciente@vitalsync.demo`. Su contraseña no se publica ni se comparte como valor predeterminado; en un entorno nuevo el seed genera una clave aleatoria. Para probar el portal, crea una cuenta desde **Crear mi cuenta**. En instalaciones existentes, el seed conserva las credenciales y el perfil que ya tengas.

**Cuenta de administrador:** `admin@vitalsync.demo`. En instalaciones existentes, el seed conserva la contraseña que ya estaba configurada. Si no la tienes, solicita un enlace de un solo uso usando el procedimiento privado descrito en [docs/admin-portal.md](docs/admin-portal.md); no se restablecen contraseñas automáticamente. Tras iniciar sesión, el rol abre `/admin`.

## Qué puedes hacer

- Landing, registro público e independiente exclusivo de pacientes, login por correo y contraseña, logout, sesión persistente y rutas protegidas.
- Dashboard con plan, vencimiento, próxima cita, conteo de próximas y notificaciones reales.
- Consultar y actualizar nombre y teléfono del perfil; las cuentas históricas pueden añadir una cédula desde Mi perfil.
- Ver planes Básico, Estándar y Premium; activar, renovar, cambiar cobertura y cancelar el plan activo mediante pago simulado y una acción común para cualquier identificador de plan.
- Buscar médicos por nombre y especialidad; consultar perfil, jornadas y horarios publicados.
- Elegir primero teleconsulta virtual simulada (recomendada) o atención presencial; el directorio muestra todas las modalidades de cada médico y filtra profesionales y turnos según la opción elegida.
- Consultar la cobertura de modalidad y especialidades en cada plan; PostgreSQL y el backend verifican el plan vigente antes de retener y confirmar. Mis citas permite filtrar virtuales, presenciales o todas.
- Retener un horario durante 10 minutos; el servidor valida médico, agenda, bloqueos, conflictos y cobertura.
- Pagar copago cuando corresponda, simular rechazo, pendiente o conciliación y resolver el pendiente antes de reintentar.
- Confirmar transaccionalmente, consultar e imprimir el comprobante desde el navegador.
- Consultar Mis citas, detalle, historial y canceladas; cancelar con motivo, confirmación expresa y control de versión.
- Gestionar el ciclo de vida de una teleconsulta simulada: abrir sala, registrar presencias independientes, iniciar/finalizar, reportar ausencias y recuperar incidencias técnicas; no se conecta audio ni video.
- En la rama de desarrollo v1.1.0, habilitar una videollamada LiveKit autohospedada para citas virtuales existentes; con LiveKit configurado, ofrece preingreso de cámara/micrófono, conexión WebRTC entre paciente y médico asignado y finalización formal. La simulación de v1.0.0 permanece disponible cuando LiveKit está desactivado.
- Leer notificaciones guardadas en PostgreSQL.
- Administrar desde `/admin` médicos, pacientes (datos administrativos), citas, disponibilidad, catálogo de planes, pagos simulados, devoluciones simuladas, auditoría, permisos y datos de contacto institucionales.
- Limitar administradores por módulo en el servidor. El rol administrador no puede leer historias clínicas; esa información requiere al médico tratante autorizado.

Las retenciones no son citas. Los pagos pendientes no activan planes ni confirman citas. La cancelación de un plan es inmediata porque estos planes no tienen renovación automática: termina la cobertura para nuevas reservas, conserva citas, pagos e historial, y registra titular, plan, transición, fecha y auditoría. Los pagos pendientes o retenciones activas deben resolverse antes. No se genera una devolución automática.

Para habilitar la sala local de video, configura claves aleatorias en `.env` y activa el perfil Compose:

```powershell
.\infrastructure\Configure-LiveKit.ps1
docker compose --profile video up -d --build
```

La configuración local usa puertos de loopback y no admite llamadas desde Internet u otras redes. La guía de permisos, medios, puertos, pruebas y limitaciones está en [docs/video-consultations-v1.1.md](docs/video-consultations-v1.1.md).

## Stack y estructura

Frontend: React 19, Vite 8, TypeScript 6, React Router 7, Tailwind 4, componentes locales shadcn/ui Button y Dialog basados en Radix/CVA, TanStack Query, React Hook Form, Zod y Lucide. `@livekit/components-react`, sus estilos y `livekit-client` se cargan bajo demanda en la sala. `package-lock.json` fija las versiones resueltas.

Backend: Python 3.13 en Docker, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg, SDK oficial `livekit-api` y Argon2id con pwdlib. `requirements.txt` expresa compatibilidad y `requirements.lock` fija el entorno Linux probado en Docker. PostgreSQL 17 con `btree_gist`, claves foráneas, checks, índices y exclusiones de solapamiento.

```text
frontend/src/
  app/                    rutas, landing y estructura responsive
  features/               auth, dashboard, doctors, plans, appointments, notifications
  features/admin/         panel responsive por módulos administrativos
  components/ui/          componentes shadcn/ui
  hooks/                  estado de sesión
  services/               cliente REST y formatos de Bogotá/COP
  types/                  contratos TypeScript
  styles/                 diseño y responsive
backend/
  app/main.py             API, permisos, validación de origen y errores
  app/core/               configuración y seguridad
  app/models/             entidades SQLAlchemy
  app/schemas/            solicitudes Pydantic
  app/services/           reglas de reserva, cancelación, pagos y administración
  app/repositories/       consultas y proyecciones
  app/db/                 unidad de trabajo transaccional
  alembic/versions/        migraciones versionadas
  tests/                  pruebas con PostgreSQL aislado
infrastructure/           inicio Windows, pruebas y verificación de persistencia
docs/                     guía, arquitectura, validación y capturas reales
```

React se comunica por `/api` con nginx (o el proxy Vite). FastAPI concentra permisos y negocio. La base es la única fuente de datos; no hay médicos, citas o métricas simulados en arreglos del frontend. Los perfiles del seed sí son ficticios, guardados en PostgreSQL.

## Registro, documento y privacidad

En **Crear mi cuenta**, cada paciente registra nombres, apellidos, cédula de ciudadanía (CC), correo, teléfono y contraseña. Debe aceptar sin premarcar el aviso de privacidad para continuar. El backend asigna el rol `PATIENT`; la API no admite seleccionar roles. Después del alta se inicia sesión con cookie HttpOnly y cada cuenta tiene su propio perfil, plan, reservas, pagos y notificaciones.

La cédula se conserva como texto para mantener ceros iniciales. La validación de demostración exige entre 6 y 10 dígitos, sin puntos ni espacios. Es una regla de formato: VITALSYNC no comprueba identidad ni consulta a la Registraduría. PostgreSQL garantiza que no se repita un documento CC. Los errores de documento/correo duplicado son genéricos para no ofrecer una búsqueda pública de personas.

Los números completos de documento no se devuelven desde el perfil: solo se muestra el tipo y los últimos cuatro dígitos. Los usuarios existentes conservan su cuenta sin documento y pueden completarlo desde **Mi perfil** después de aceptar el aviso. Los campos documentales y el consentimiento de usuarios históricos permanecen nullable; no se crean identidades ficticias ni se cambia una contraseña durante la migración. No introduzcas cédulas reales en la demostración.

El aviso registra la versión `VITALSYNC-PRIVACIDAD-2026-11-v1` y la fecha de aceptación. Informa que nombre, cédula, correo y teléfono se utilizan para crear y proteger la cuenta, gestionar el plan y coordinar la atención solicitada. Es una explicación funcional para esta demostración y no una certificación legal.

## Concurrencia, transacciones y seguridad

Las operaciones críticas bloquean primero la fila del paciente y después la del médico con `SELECT FOR UPDATE`. La segunda transacción espera y vuelve a consultar conflictos antes de escribir. Se comprueban solapamientos, incluyendo horarios parcialmente superpuestos y citas del propio paciente con otro médico. La base además tiene exclusiones GiST para intervalos confirmados de médico y paciente y unicidad por retención.

Los pagos se serializan por paciente y tienen una clave idempotente única. La repetición de una clave devuelve la operación existente; una pendiente bloquea otra para el mismo destino. La conciliación aplica la activación una sola vez. Un copago tardío no puede aprobar una retención vencida. Los cambios, auditoría, notificación e historial se confirman juntos. FastAPI termina la transacción **antes** de enviar una respuesta exitosa; también se prueba el fallo al hacer commit.

Sesiones opacas aleatorias en cookie `HttpOnly`, `SameSite=Strict`; en la BD solo se guarda el hash SHA-256 del token. Las contraseñas usan Argon2id. No se guardan tokens en localStorage ni sessionStorage. Se rechazan orígenes no autorizados y solicitudes de navegador marcadas `cross-site`. Los roles públicos no son seleccionables. Los errores internos de SQL no se exponen al usuario.

`COOKIE_SECURE=false` permite HTTP de localhost en esta demostración. Un eventual despliegue deberá habilitar HTTPS, cookie segura, gestión de secretos, limitación de intentos de login, monitorización y un proveedor de pagos real. Esta entrega se limita al entorno local.

## Variables de entorno

| Variable | Predeterminado | Efecto |
| --- | --- | --- |
| `VITALSYNC_FRONTEND_PORT` | `5188` | Puerto HTTP del portal |
| `VITALSYNC_BACKEND_PORT` | `8088` | Puerto HTTP de API y documentación |
| `VITALSYNC_POSTGRES_PORT` | `5488` | Puerto local de PostgreSQL |
| `POSTGRES_DB` / `POSTGRES_USER` | `vitalsync` | Base y usuario propios |
| `POSTGRES_PASSWORD` | valor ficticio en `.env.example` | Contraseña local de demostración |
| `DEMO_MODE` | `true` en Compose | Seed y controles de pago simulado; fuera de Compose el backend predetermina `false` |
| `HOLD_MINUTES` | `10` | Duración de retención |
| `CANCELLATION_HOURS` | `2` | Se exige cancelar con **más** de 2 horas de anticipación |
| `TELECONSULT_ROOM_OPEN_MINUTES` | `5` | Minutos antes de la cita para habilitar la sala virtual |
| `TELECONSULT_WAIT_GRACE_MINUTES` | `15` | Plazo de espera usado para registrar ausencias en demostración |
| `SESSION_HOURS` | `12` | Vigencia de sesión |
| `COOKIE_SECURE` | `false` | Cookie HTTPS cuando es `true` |

Compose deriva `DATABASE_URL` y `ALLOWED_ORIGINS` de las variables anteriores. Si los puertos están ocupados, edita `.env` y vuelve a ejecutar Compose; no detengas otros proyectos. Mantén `localhost` como host durante todo el recorrido. No cambies usuario/contraseña de PostgreSQL sobre un volumen ya inicializado sin migrar sus credenciales.

## Migraciones y seed

El backend ejecuta `alembic upgrade head` al arrancar y luego `python -m app.seed` si `DEMO_MODE=true`. Migraciones:

1. `1dd6f0a05515`: entidades, FKs, estados, checks, unicidades e índices.
2. `20261108_overlap`: extensión `btree_gist` y restricciones de solapamiento.
3. `20261109_virtual`: modalidades virtual/presencial con registros antiguos conservados como presenciales y cobertura de planes actualizada.
4. `20261110_virtual_history`: amplía el historial para guardar transiciones de la sala virtual simulada.
5. `20261114_patient_identity`: añade estado y fecha de creación de cuentas, aceptación versionada del aviso y documento nullable con formato y unicidad para CC. Las cuentas anteriores conservan sus valores nulos.
6. `20261115_teleconsult_lifecycle`: agrega presencias y marcas de tiempo; reconcilia la cita con su teleconsulta ligada por `appointment_id`; conserva el historial y amplía estados cancelables/bloqueos de agenda.
7. `20261120_admin_portal`: crea sidecars de permisos, auditoría, recuperación de acceso, devoluciones, revisiones de catálogo y capturas económicas. Las condiciones heredadas se etiquetan como observadas durante la migración; no modifica citas, pagos ni planes existentes.

Se crean 5 especialidades, 5 médicos, 3 planes, un paciente sin plan y el administrador. Se publican los siguientes 21 días, con 6 turnos diarios por médico, y se registra un bloqueo de demostración a las 11:00 del día siguiente. Todos los turnos duran 30 minutos y tienen autoría administrativa. Las fechas se calculan en `America/Bogota`, se persisten y no se generan aleatoriamente en las consultas. Reiniciar no duplica turnos ni sobrescribe datos existentes.

```powershell
docker compose exec backend alembic current
docker compose exec backend python -m app.seed
```

## Pruebas

Backend real en una base temporal con prefijo `vitalsync_test_audit_`, dentro de PostgreSQL. El runner crea una base nueva por ejecución y la suite solo admite nombres de prueba autorizados antes de truncar sus propias tablas:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/Test-Backend.ps1
```

El script toma la configuración efectiva y usa el servicio `db`. No modifica ni trunca la base acumulada `vitalsync_test`, la base principal `vitalsync` ni otros datos preexistentes. Conserva la base de auditoría recién creada para que sus resultados puedan inspeccionarse.

Frontend:

```powershell
cd frontend
npm ci
npm test
npm run build
cd ..
```

El E2E que crea cuentas y reservas usa una base temporal nueva `vitalsync_test_audit_*`, con dos servicios dentro del proyecto `vitalsync`. El script selecciona `infrastructure/compose.test.yml` y retira solo esos servicios; conserva el servidor PostgreSQL, sus volúmenes y todas las bases preexistentes:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/test-doctor-portal.ps1
```

El script comprueba la contraseña de la cuenta médica de pruebas y no la sobrescribe. Si el volumen de pruebas es nuevo, la contraseña de demostración aislada debe configurarse explícitamente antes del primer E2E. Más información en [doctor-portal.md](docs/doctor-portal.md).

Para verificar paciente y médico y la persistencia de la base principal sin crear cuentas, citas o pagos, usa cuentas existentes. El programa solicita sus contraseñas de forma oculta; también admite `VITALSYNC_PATIENT_EMAIL`, `VITALSYNC_PATIENT_PASSWORD`, `VITALSYNC_DOCTOR_EMAIL` y `VITALSYNC_DOCTOR_PASSWORD` como variables del proceso:

```powershell
python infrastructure/verify_persistence.py --restart --output docs/docker-unification-validation.json
```

Esta comprobación solicita de forma oculta las contraseñas existentes de paciente, médico y administrador; también admite las variables `VITALSYNC_PATIENT_PASSWORD`, `VITALSYNC_DOCTOR_PASSWORD` y `VITALSYNC_ADMIN_PASSWORD` en el proceso. Verifica los tres roles, deniega acceso cruzado y comprueba que sus sesiones y los datos persisten tras reiniciar; no cambia contraseñas ni cancela reservas. No la ejecutes simultáneamente con otros usuarios o pruebas que estén modificando reservas.

Resultados y alcance comprobados: [VALIDACION.md](docs/VALIDACION.md).

## Desarrollo fuera de contenedores

Puedes mantener PostgreSQL en Docker y usar Vite y FastAPI locales. Para Python utiliza una versión soportada por las dependencias (3.12 o 3.13), no el Python 3.15 predeterminado de esta máquina:

```powershell
docker compose -p vitalsync up -d db
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL='postgresql+psycopg://vitalsync:local_demo_change_me@localhost:5488/vitalsync'
$env:DEMO_MODE='true'
alembic upgrade head
python -m app.seed
uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
```

En otra terminal: `cd frontend`, `npm ci`, `npm run dev`. Detén primero los contenedores backend/frontend si usan esos mismos puertos. Vite redirige `/api` al puerto 8088; si lo cambias, ajusta `frontend/vite.config.ts`.

## Reinicios y diagnóstico

```powershell
docker compose logs --tail 80 backend
docker compose logs --tail 80 frontend
docker compose -p vitalsync restart
docker compose -p vitalsync stop
docker compose -p vitalsync up -d --wait
```

Para el arranque habitual usa `infrastructure/Start-Vitalsync.ps1`: fija el proyecto `vitalsync`, comprueba el volumen principal y espera a que los servicios estén saludables. El volumen externo existente es `vitalsync_vitalsync_data`; Compose se detiene si falta para evitar reemplazar los datos por una base vacía. No elimines volúmenes para actualizar imágenes. Consulta el [informe de unificación y mantenimiento](docs/DOCKER_UNIFICADO.md) para respaldo y recuperación.

No hay recuperación por correo. El administrador solicita una recuperación en Configuración; un operador local emite un enlace de un solo uso en un archivo protegido de Windows. La persona titular elige su contraseña en `/recover`; la contraseña existente se conserva hasta que la persona redima el enlace. Consulta [Portal administrativo](docs/admin-portal.md).

## Documentación y capturas

- [Guía exacta para presentar el portal](docs/GUIA_DEMOSTRACION_PACIENTE.md)
- [Arquitectura, estados y API](docs/ARQUITECTURA.md)
- [Portal administrativo: módulos, permisos, privacidad y recuperación](docs/admin-portal.md)
- [Captura del dashboard administrativo](docs/screenshots/admin-dashboard-desktop.png)
- [Validación ejecutada y límites](docs/VALIDACION.md)

![Dashboard real](docs/screenshots/dashboard-desktop.png)

## Límites de la demostración

La administración y las devoluciones operan con registros simulados: no realizan transferencias ni procesan pagos reales. Con LiveKit desactivado, la teleconsulta conserva el ciclo de demostración v1.0.0 sin usar audio o video. En esta rama v1.1.0, al activar el perfil `video`, las citas virtuales usan una sala WebRTC privada. La prueba de dos navegadores pasó con medios sintéticos y con cámara/micrófono físicos de este equipo; en ambos casos verificó video y pistas de audio activas en las dos direcciones, reconexión y finalización. No se midió la calidad audible, ni se validaron llamadas entre redes distintas. No se incluye correo, notificación push, app nativa ni despliegue público.

El comprobante se imprime con el navegador (puedes elegir Guardar como PDF); no hay un generador de PDF en el servidor. Las notificaciones y pagos listan las últimas 100 operaciones. Las retenciones vencidas dejan de bloquear por su fecha, sin requerir un proceso programado. El seed amplía la agenda al reiniciar; no sustituye un módulo administrativo.

No se realizó push ni publicación en GitHub.


## Portal del médico

La implementación médica comparte la aplicación y las sesiones existentes. Para iniciar la versión revisada:

```powershell
docker compose -p vitalsync up -d --build --wait
```

Con `DEMO_MODE=true`, el seed vincula `medico@vitalsync.demo` al Dr. Alejandro Méndez sin duplicar profesionales ni sobrescribir contraseñas. Todos inician sesión desde `/auth`; el backend identifica el rol y la aplicación dirige al médico a `/doctor`, al administrador a `/admin` y al paciente a `/portal`. `/login` y `/register` siguen funcionando como enlaces compatibles. El registro público crea únicamente pacientes y admite correos personales válidos. Las cuentas médicas nuevas se crean desde **Administración → Médicos**, con el formato `nombre.apellido@doctor.vitalsync.demo`; si hay una coincidencia se añade un identificador estable. Las cuentas previas mantienen su correo y contraseña. Para recuperación, usa el enlace disponible en `/auth`; las solicitudes administrativas siguen el flujo privado documentado.

Consulta [arquitectura, rutas, migración, pruebas y acceso local del portal médico](docs/doctor-portal.md).


## Docker unificado

El único despliegue permanente es `vitalsync`, con `frontend`, `backend` y `db`. Los tres portales comparten la API, el login y la base principal existente. El volumen principal es externo y queda fijado por nombre; no se genera una base vacía si desaparece.

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/Start-Vitalsync.ps1
powershell -ExecutionPolicy Bypass -File infrastructure/Backup-Vitalsync.ps1
docker compose -p vitalsync ps
```

Los respaldos quedan fuera del repositorio, en `Escritorio\VITALSYNC-RESPALDOS`, con comprobación de lectura del archivo y SHA256. El arranque requiere el volumen principal existente o restaurado; un equipo nuevo debe recuperar un respaldo revisado antes de iniciar esta configuración protegida.

Consulta [infraestructura, respaldo, volúmenes y resultados de la unificación](docs/DOCKER_UNIFICADO.md).
