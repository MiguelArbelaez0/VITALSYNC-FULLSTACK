# Portal médico de VITALSYNC

## Despliegue y acceso

Rama `codex/doctor-portal`. Paciente y médico comparten login, frontend, API y PostgreSQL en el proyecto Compose `vitalsync`. Servicios permanentes: `db`, `backend`, `frontend`. Volumen principal externo: `vitalsync_vitalsync_data`; base de aplicación: `vitalsync`. No se creó un segundo proyecto ni se eliminaron volúmenes.

```powershell
docker compose -p vitalsync up -d --build --wait
```

- Login: http://localhost:5188/login
- Paciente: http://localhost:5188/portal
- Médico: http://localhost:5188/doctor
- API: http://localhost:8088/docs

El login redirige según el rol. Registro público: solamente pacientes. El administrador no dispone de visor clínico. El backend comprueba cuenta activa, rol, vinculación profesional única y perfil habilitado en cada solicitud médica.

## Cuentas individuales y entrega privada

Existen cinco perfiles profesionales. El aprovisionamiento conserva la vinculación y contraseña de cualquier cuenta existente; crea solamente las pendientes. La contraseña inicial de cada cuenta nueva es aleatoria e individual, con hash Argon2 en PostgreSQL. El primer acceso exige elegir una contraseña propia antes de acceder a agenda, pacientes o información clínica. El cambio revoca las demás sesiones y queda auditado.

| Perfil | Correo de acceso | Procedencia |
| --- | --- | --- |
| Dra. Isabella Ríos | medico-1@vitalsync.demo | Nueva cuenta individual |
| Dr. Alejandro Méndez | medico@vitalsync.demo | Cuenta y contraseña existentes conservadas |
| Dra. Camila Restrepo | medico-3@vitalsync.demo | Nueva cuenta individual |
| Dra. Sofía Herrera | medico-4@vitalsync.demo | Nueva cuenta individual |
| Dr. Nicolás Vargas | medico-5@vitalsync.demo | Nueva cuenta individual |

Comando administrativo para los perfiles actuales o futuros, desde la raíz:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/Provision-Doctors.ps1
```

El script crea una carpeta nueva en el escritorio, `VITALSYNC-CREDENCIALES/<fecha-identificador>/`, con ACL de acceso exclusivo para el usuario de Windows y SYSTEM. Copia `doctores.credentials.json`, verifica SHA256 y retira la copia temporal del contenedor. El JSON privado contiene únicamente las credenciales recién emitidas y los identificadores conservados. Abrirlo localmente y entregar cada acceso a su titular por un canal privado; no adjuntarlo al repositorio ni a reportes. Tras confirmar la entrega y el cambio individual, custodiar o retirar ese archivo según la política local.

Repetir el comando no genera contraseñas para cuentas existentes ni las restablece. Una exportación posterior vacía es normal. No recuperar claves antiguas desde hashes. Un error al copiar conserva el archivo privado temporal del contenedor para recuperación administrativa; no repetir un alta esperando volver a emitir las claves. El comando Python crea su archivo exclusivamente (0600, sin sobrescritura), revierte la transacción si no puede exportar y no imprime secretos.

En un entorno no académico se debe proporcionar un dominio institucional mediante `python -m app.provision_doctors --domain <dominio> --output <archivo-privado>`, con un usuario ADMIN activo como actor. Los perfiles deshabilitados reciben una cuenta DISABLED y no pueden autenticarse. La reactivación es una decisión administrativa explícita; el aprovisionamiento no cambia estados ni contraseñas existentes.

## Historias ficticias y pacientes de demostración

Se autorizó añadir dos pacientes nuevos claramente ficticios. El conjunto académico comprende a Valentina Torres (semilla original identificada por correo, nombre y ausencia de cédula/aceptación de privacidad), Lucía Demostración Académica y Santiago Demostración Académica. Los demás registros no se clasifican como ficticios ni reciben antecedentes inventados.

El seed genera tres historias y nueve consultas anteriores diferenciadas: antecedentes personales, familiares, quirúrgicos y enfermedades previas; alergias; medicamentos actuales y anteriores; diagnóstico, motivo, observaciones, recomendaciones y signos vitales simulados. Cada historia tiene el marcador obligatorio `DATOS FICTICIOS DE DEMOSTRACIÓN`. No se inventa fecha de nacimiento: si falta, la edad figura no registrada; si existe, se calcula con la fecha de Bogotá.

```powershell
docker compose -p vitalsync exec -T backend python -m app.seed_clinical --include-demo-patients
```

Solo funciona con `DEMO_MODE=true`. La opción administrativa crea las dos identidades explícitas una única vez. Sin esa opción, el inicio identifica únicamente la semilla original y conserva todos los registros ya creados. Repetir el seed no completa, modifica ni duplica historias existentes. Una colisión con un correo sin procedencia ficticia detiene y revierte la operación.

Las consultas históricas son registros académicos separados: no crean citas, pagos ni relaciones asistenciales. Los dos pacientes nuevos no obtienen acceso médico automático ni se entregan contraseñas de paciente. Para demostrarlos en la agenda se necesita una reserva válida, realizada por el flujo autorizado. Para probar el visor inmediatamente, la cuenta existente de Alejandro ya tiene una relación asistencial con Valentina: **Mis pacientes → Valentina Torres → Ver historia clínica**. La disponibilidad de ese botón siempre se recalcula según el estado real de las citas.

## Esquema y migraciones

Ruta de actualización: `20261117_lifecycle_merge → 20261118_doctor_accounts → 20261119_clinical_history` (una sola cabeza). Se conservan las migraciones de ambas ramas históricas. La nueva migración crea tablas adicionales; no reemplaza ni reconstruye las existentes y no ejecuta el seed dentro de Alembic.

| Tabla nueva | Relación y validaciones |
| --- | --- |
| `doctor_credential_states` | PK/FK a la cuenta médica; cambio inicial pendiente, emisión y cambio |
| `demo_patients` | PK/FK al paciente existente; procedencia BUILTIN_SEED u OPERATOR_CONFIRMED, actor y fecha |
| `clinical_histories` | Una por paciente ficticio, marcador obligatorio, nacimiento no futuro |
| `clinical_backgrounds` | FK historia; categoría válida y única dentro de la historia |
| `clinical_allergies` | FK historia; sustancia única por historia |
| `clinical_medications` | FK historia; nombre único y estado CURRENT/PREVIOUS |
| `clinical_encounters` | FK historia, médico, especialidad y cita opcional única; clave de seed única por historia; signos JSONB objeto |

Índices en las relaciones de antecedentes/alergias/medicamentos, profesional de la consulta y par historia/fecha. El downgrade destructivo se bloquea expresamente; una reversión exige evaluar una copia respaldada en un entorno aislado.

## API y autorización clínica

| Método y ruta | Operación |
| --- | --- |
| GET `/api/doctor/patients/{patient_id}/clinical-history` | Resumen, antecedentes, alergias, medicamentos y consultas cronológicas |
| GET `/api/doctor/patients/{patient_id}/clinical-history/encounters/{encounter_id}` | Detalle autorizado y signos vitales |
| POST `/api/doctor/password` | Cambio individual con contraseña actual, nueva y confirmación |

Se mantienen las rutas previas de dashboard, agenda con filtros de día/modalidad/estado, detalle, cancelación con motivo/versión/confirmación, pacientes asignados, disponibilidad, perfil editable únicamente en biografía y teleconsultas simuladas.

El servidor deriva el médico de la sesión, nunca de un parámetro del cliente. Para leer una historia exige una cita del mismo paciente y médico en CONFIRMED, IN_PROGRESS o ATTENDED. Una cita CANCELLED o una incidencia por sí sola no concede permiso. La relación se bloquea durante la lectura para serializarla con una cancelación concurrente. Cualquier detalle debe pertenecer a esa misma historia. Un recurso ajeno responde 404, un rol incorrecto 403 y una sesión ausente 401. Un perfil/cuenta deshabilitado no accede. Las contraseñas iniciales pendientes permiten solo el cambio y los metadatos propios de autenticación.

Las lecturas registran actor, fecha y recurso en `audit_events` mediante `CLINICAL_HISTORY_VIEWED` y `CLINICAL_ENCOUNTER_VIEWED`. Si falla la auditoría, no se entrega contenido clínico. No se incluye contenido clínico, documentos, teléfono, pagos ni contraseñas en la auditoría o en endpoints generales. Las respuestas usan `Cache-Control: no-store`; las consultas React clínicas no conservan caché al desmontarse y el cierre de sesión limpia la caché de la sesión. No existen endpoints de edición clínica.

El visor del paciente y el administrador quedan fuera del alcance de esta entrega. Esta restricción de interfaz académica no prejuzga la futura implementación de los derechos del paciente sobre su información.

## Funciones conservadas

La cancelación médica conserva cita, pagos e historial, exige motivo, confirmación y versión y notifica al paciente; no inventa devoluciones. La teleconsulta sigue siendo simulada, sin audio/video real. Ambos participantes deben ingresar antes de iniciar. Finalizar conserva el horario de la reserva, registra `completion_source=DEMO` y `clinically_attended=false`, retira la cita de Próximas y la muestra en Historial en ambos portales. Dashboard, agenda, disponibilidad, perfil, filtros y cierre de sesión mantienen sus rutas y autorizaciones.

## Pruebas reproducibles

Backend, exclusivamente `vitalsync_test`:

```powershell
docker compose -p vitalsync run --rm --no-deps -v "${PWD}\backend:/app" backend python -m pytest -q
```

Frontend:

```powershell
npm --prefix frontend test
npm --prefix frontend run build
```

E2E completo en proceso independiente:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File infrastructure/test-doctor-portal.ps1
```

El runner agrega temporalmente `test-backend` y `test-frontend` dentro de **vitalsync**, con puertos 8189/5289 y la base desechable `vitalsync_test` del servidor existente. El fixture verifica el nombre de la base antes de truncar sus tablas, genera cuentas ficticias y exporta claves a un archivo local protegido fuera de Git. No almacenar datos útiles en esa base ni ejecutar pytest al mismo tiempo. La aplicación `vitalsync` conserva sus datos. Al terminar se retiran únicamente los dos servicios temporales, sin borrar redes compartidas ni volúmenes. Las pruebas de escritorio incluyen reinicio de PostgreSQL/backend, con recuperación de sesiones y estados.

Las pruebas cubren los cinco médicos, contraseñas existentes, futuras altas, concurrencia, idempotencia, perfiles deshabilitados, cambio inicial, revocación de sesiones y reversión por auditoría fallida. Cubren estados asistenciales válidos e inválidos, aislamiento entre pacientes/médicos, administrador/paciente/anónimo, IDOR, seed académico limitado y lectura únicamente autorizada. E2E comprueba el recorrido paciente-reserva-médico-historia-teleconsulta-historial, cancelación y notificación, escritorio y móvil.

## Capturas verificadas

Capturas tomadas con datos ficticios en la aplicación ejecutándose; se revisaron visualmente escritorio y móvil:

- [Historia clínica, escritorio](screenshots/doctor-clinical-desktop.png)
- [Historia clínica, móvil](screenshots/doctor-clinical-mobile.png)
- [Dashboard](screenshots/doctor-dashboard-desktop.png)
- [Agenda](screenshots/doctor-agenda-desktop.png)
- [Sala finalizada](screenshots/doctor-room-desktop.png)

## Resultado de validación

La suite backend completa aprobó 145 pruebas; las cinco pruebas adicionales de concurrencia y seguridad aprobaron después (150 pruebas distintas, ninguna fallida). Tras el ajuste final del seed se repitieron las 29 pruebas de clínica, seguridad y migraciones: 29 aprobadas. Frontend: 41/41 aprobadas. React y ambas imágenes Docker compilan correctamente.

E2E completo: 14/14 aprobadas, sin pruebas omitidas, en escritorio y móvil. La primera ejecución completa tuvo un fallo de selector en móvil: esperaba un `dd` en el comprobante cuando allí el estado aparece como etiqueta. Se corrigió la prueba para exigir la URL y título del comprobante y verificar el estado visible; conserva la comprobación del estado ATTENDED y metadatos persistidos en API. Se volvió a ejecutar toda la suite con éxito.

Respaldo anterior al despliegue: `Desktop/VITALSYNC-RESPALDOS/vitalsync-20261112-232816.dump`, 105467 bytes, SHA256 `0dea1aaa7c64c3e82b84ba0dcd9595eeeb7e47206ce165486c666f1861792c2f`. Lectura completa del archivo con `pg_restore --file=/dev/null` y coincidencia de hash entre contenedor y copia local: PASS. El manifiesto está junto al respaldo, fuera de Git.

Migración principal aplicada y cabeza única comprobada: `20261119_clinical_history`. Todas las filas originales de 17 tablas conservan su huella: 53 pacientes, 55 usuarios, 5 médicos, 60 citas, 147 pagos, 166 transiciones, 428 auditorías y demás filas originales, sin eliminaciones ni modificaciones. Informe: [doctor-data-preservation.json](doctor-data-preservation.json). Después de las altas autorizadas: 55 pacientes, 61 usuarios, 5 cuentas médicas, 3 historias y 9 consultas académicas; citas y pagos conservan sus cantidades originales.

Aprovisionamiento principal: primera ejecución 4 creadas / 1 conservada; segunda 0 creadas / 5 conservadas. Seed explícito: primera ejecución 2 pacientes / 2 historias adicionales; segunda 0 / 0. Se verificó la ACL privada de carpeta y archivo (únicamente usuario actual y SYSTEM). La entrega inicial está en `Desktop/VITALSYNC-CREDENCIALES/20261112-232938-c79437/doctores.credentials.json`; la segunda exportación vacía no reemplaza esa entrega.

Los cinco médicos habilitados autenticaron correctamente en el despliegue principal. Las cuatro cuentas nuevas conservan cambio inicial pendiente; la cuenta anterior conserva su acceso. Se consultaron dashboard, agenda, pacientes, perfil y disponibilidad de Alejandro, su historia autorizada y un detalle. Paciente y recurso ajeno recibieron denegación. Auditoría con actor correcto, fecha y acciones de historia/detalle: PASS. Los cinco hashes médicos son Argon2. Informe sin secretos: [doctor-live-verification.json](doctor-live-verification.json).

Reinicio de db, backend y frontend: PASS. Las 25 tablas mantuvieron sus cantidades y digest completo, salvo sesiones excluidas del digest; las sesiones existentes también se comprobaron por autenticación después del reinicio. Las tres citas compartidas del paciente de demostración y Alejandro conservaron su contenido. Historias 3, consultas 9, cuentas médicas 5 y estados de cambio inicial persistieron. Se volvió a comparar cada fila original y a ejecutar el seed: contenido idéntico. Informe: [doctor-finalization-persistence.json](doctor-finalization-persistence.json).

Compose muestra únicamente `vitalsync`, `running(3)`, con sus tres servicios saludables. Los siete volúmenes previamente inventariados siguen presentes, incluidos los de pruebas antiguas, sin eliminaciones. No se ejecutaron push, merge, borrado de base ni eliminación de volumen.

Todos los criterios de aceptación de esta entrega tienen evidencia de pruebas o verificación del despliegue. No quedan fallos de pruebas pendientes. Las cuatro contraseñas temporales deben ser cambiadas por sus titulares al primer ingreso.

Advertencias no bloqueantes: Vite informa un bundle de unos 583 kB; Starlette advierte sobre la futura retirada de su integración de pruebas con httpx. No se incorporó videollamada real ni escritura clínica. Las dos identidades nuevas no tienen reservas automáticas ni credenciales de paciente entregadas.

## Archivos de esta entrega

- Backend: `app/models/entities.py`, `app/core/security.py`, `app/main.py`, `app/routers/doctor.py`, `app/schemas/requests.py`, `app/seed.py`; servicios nuevos `clinical_history.py` y `doctor_accounts.py`; comandos nuevos `provision_doctors.py` y `seed_clinical.py`; migración `20261119_clinical_history.py`.
- Pruebas: `test_clinical_history.py`, `test_clinical_security.py`, `test_demo_migration.py` (cabeza esperada), fixture `bootstrap_e2e.py`; React `clinical.test.tsx`; E2E `clinical-history.spec.ts`, adaptación del test médico existente al mismo proyecto y credenciales privadas, y corrección de `demo-lifecycle.spec.ts` para esperar la navegación al comprobante y validar allí el estado visible.
- Frontend: `App.tsx`, `types/index.ts`, `DoctorPortal.tsx`, componentes nuevos `ClinicalHistory.tsx`, `DoctorPassword.tsx` y `clinical.css`.
- Infraestructura: `Provision-Doctors.ps1`, `test-doctor-portal.ps1`, `compose.test.yml`, `nginx.test.conf`, `snapshot_rows.py`.
- Documentación, capturas y exclusión `*.credentials.json` en `.gitignore`.
