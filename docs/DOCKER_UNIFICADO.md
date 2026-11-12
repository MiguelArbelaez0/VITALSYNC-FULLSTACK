# VITALSYNC: Docker unificado

Validado el 12 de noviembre de 2026 sobre `codex/doctor-portal`, desde el código `cca6642` que contiene ambos portales. No se hizo push, merge ni cambio de contraseñas.

## Resultado operativo

Docker Desktop se comprobó visualmente: un único proyecto Compose `vitalsync` con `db-1`, `backend-1` y `frontend-1` activos. El contenedor independiente `empresa` es ajeno a VITALSYNC y se conservó detenido. `docker compose ls --all` confirma únicamente `vitalsync`, `running(3)`.

| Servicio | Función | Acceso local |
| --- | --- | --- |
| `frontend` | Un build React/Vite servido por nginx; login compartido y rutas por rol | `http://localhost:5188/login`, `/portal`, `/doctor` |
| `backend` | FastAPI compartida, pacientes, médicos, citas y simulación | `http://localhost:8088/docs` |
| `db` | PostgreSQL 17, misma base principal existente | `127.0.0.1:5488` |

Los dos portales comparten la base de aplicación `vitalsync`. La base `vitalsync_test` ya existente en el servidor se mantiene exclusivamente para pruebas y no sirve a los portales; no se eliminó ninguna base. El backend usa el host interno `db`, no una segunda instancia. El alias DNS `postgres` del mismo servicio se conserva por compatibilidad con herramientas antiguas.

## Configuración e inventario revisados

Se revisaron `.env` y `.env.example` sin publicar valores privados ni modificarlos. La configuración efectiva conserva los puertos 5188/8088/5488 y las credenciales existentes. El nombre principal se fija en `docker-compose.yml` y los scripts operativos seleccionan explícitamente `-p vitalsync`.

El volumen de producción queda fijado como **externo**: `vitalsync_vitalsync_data`. No se genera un volumen nuevo vacío si falta el original. El arranque protegido comprueba el nombre de la base, la existencia del volumen y que ningún contenedor ajeno al servicio `vitalsync/db` esté ejecutándose sobre ese PGDATA. Los tres servicios usan `restart: unless-stopped`.

El cambio de nombre `postgres` → `db` se realizó deteniendo primero frontend/backend y el servidor anterior. Solo después arrancó `vitalsync-db-1` con el mismo volumen. Nunca se ejecutaron simultáneamente dos PostgreSQL contra el volumen principal. Tras verificar datos, login, agenda y reinicios, se retiró el contenedor detenido `vitalsync-postgres-1`.

El segundo proyecto observado se llamaba realmente `vitalsync-doctor-check`; era el entorno E2E detenido, no un segundo portal de producción. Su base `vitalsync_test` tenía 16 pacientes y 20 citas de prueba antes de esta operación; sus 18 cuentas pertenecían a dominios de demostración/pruebas. Se respaldó y conservó su volumen sin mezclar sus identificadores con la base principal. No existía un proyecto con el nombre exacto `vitalsync-doctor`.

| Volumen | Estado final |
| --- | --- |
| `vitalsync_vitalsync_data` | Principal, conectado exclusivamente a `vitalsync-db-1` |
| `vitalsync-doctor-check_vitalsync_data` | Conservado, sin contenedores activos; pruebas temporales |
| `vitalsync-e2e_vitalsync_data` | Conservado, sin despliegue activo |
| `vitalsync-merge-check_vitalsync_data` | Conservado, sin despliegue activo |
| Otros volúmenes de Docker | Conservados sin modificaciones |

Los contenedores y la red del proyecto antiguo se retiraron sin opción de eliminación de volúmenes. El runner E2E ahora selecciona un override de pruebas explícito, comprueba su volumen separado y retira automáticamente sus contenedores y red en `finally`, incluso ante fallos. Así no deja un segundo despliegue permanente en Docker Desktop.

## Respaldo verificable

Antes de detener o cambiar servicios se crearon archivos de formato personalizado de PostgreSQL fuera del repositorio:

`C:\Users\USUARIO\Desktop\VITALSYNC-RESPALDOS\unificacion-20261112-181015`

| Archivo | Bytes | SHA256 |
| --- | ---: | --- |
| `principal.dump` | 105467 | `fe05b7d43d7290ab1a2174fb31aa0c2682b51b0efa89d934c45772627b848f52` |
| `pruebas-antiguo.dump` | 84895 | `611fbe72e87b88de91db7d6e3ef6f5d892aff64f79d55e2b100e85276014d5e2` |

Ambos archivos se leyeron completos mediante `pg_restore --exit-on-error --file=/dev/null`; el SHA256 de la copia local coincidió con el archivo dentro del contenedor. `manifest.json` conserva tamaños y hashes, y `before.json` / `after.json` conservan conteos y resúmenes de contenido sin filas personales. No se restauró ni sobrescribió la base principal.

También se probó el nuevo comando de respaldo sobre `db`: `vitalsync-20261112-181540.dump`, 105518 bytes, SHA256 `268267e91de77501e8582a22275f2ccaa540e730de33e99de144261e8f6689af`, en la misma carpeta general de respaldos. La diferencia de tamaño del archivo no implica cambios de negocio: las sesiones de comprobación son persistentes y forman parte del dump.

## Integridad y migraciones

La base ya estaba en `20261118_doctor_accounts` al comenzar. El arranque ejecutó el flujo normal de Alembic/seed sin reconstruir tablas ni duplicar datos. `alembic current` y `alembic heads` coinciden en esa única cabeza.

Se comparó el contenido de 18 tablas públicas antes de la transición y después de los reinicios y pruebas. Coincidieron tanto los conteos como los resúmenes de cada fila ordenada. Se excluyó solamente la tabla de sesiones porque las comprobaciones crean y cierran sesiones; además, se verificó expresamente que las cookies y sesiones sobrevivieran a los reinicios.

| Dato principal | Antes | Después |
| --- | ---: | ---: |
| Pacientes | 53 | 53 |
| Médicos | 5 | 5 |
| Citas | 60 | 60 |
| Pagos | 147 | 147 |
| Planes | 3 | 3 |
| Historial de citas | 166 | 166 |
| Auditorías | 428 | 428 |

Se conservaron también usuarios, contraseñas almacenadas, vinculaciones médicas, notificaciones, planes contratados, disponibilidades, bloqueos y salas virtuales. La comprobación del despliegue principal no registró pacientes, creó reservas, pagó, canceló ni restableció contraseñas.

## Pruebas y evidencia

| Comprobación | Resultado |
| --- | --- |
| Configuración Compose principal y override aislado | Válidas; volúmenes diferentes |
| Login React de paciente y redirección `/portal` | Aprobado |
| Login React médico y redirección `/doctor` | Aprobado |
| Rechazo de acceso cruzado por rol | Aprobado en API y React |
| Agenda médica | 3 citas, mismas IDs que PostgreSQL y las reservas del paciente consultado |
| `/docs` | HTTP 200 |
| Reinicio de `db`, backend y frontend | Datos y sesiones conservados |
| Integridad de las 18 tablas comprobadas | Sin cambios |
| Backend, exclusivamente en `vitalsync_test` | 124 aprobadas |
| React | 36 aprobadas |
| E2E de integración, escritorio y móvil | 2 aprobadas; entorno temporal retirado al terminar |
| Build TypeScript/Vite y contenedores | Aprobado |
| Fallos finales | 0 |

Vite conserva su aviso de paquete JavaScript de más de 500 kB y Starlette/httpx su aviso de deprecación en pruebas. No son fallos de compilación ni de funcionamiento.

Evidencias sin credenciales: [estado efectivo de Compose](docker-compose-state.json) y [comprobación de persistencia/roles](docker-unification-validation.json). Las pruebas que crean datos se ejecutaron solo en bases aisladas, no en `vitalsync`.

## Arranque, actualización y mantenimiento

Desde la raíz del repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/Start-Vitalsync.ps1
docker compose -p vitalsync ps
docker compose -p vitalsync logs --tail 80 backend db frontend
```

Antes de actualizar imágenes o migraciones:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/Backup-Vitalsync.ps1
powershell -ExecutionPolicy Bypass -File infrastructure/Start-Vitalsync.ps1
```

El respaldo se guarda por defecto en `Escritorio\VITALSYNC-RESPALDOS`, se valida la lectura del archivo y se compara SHA256. Los archivos `.dump` / `.pgdump` están excluidos de Git. Conserva los respaldos fuera del repositorio. Si falta el volumen principal, el arranque se detiene: recupera un respaldo revisado en vez de sustituirlo por una base vacía.

Para detener sin retirar contenedores ni datos:

```powershell
docker compose -p vitalsync stop
```

Para comprobar persistencia y ambos roles usando cuentas existentes, con contraseñas solicitadas de forma oculta:

```powershell
python infrastructure/verify_persistence.py --restart --output docs/docker-unification-validation.json
```

Las variables `VITALSYNC_PATIENT_EMAIL`, `VITALSYNC_PATIENT_PASSWORD`, `VITALSYNC_DOCTOR_EMAIL` y `VITALSYNC_DOCTOR_PASSWORD` son alternativas para un proceso local; no se guardan ni se imprimen. Si una contraseña existente no permite entrar, se informa del fallo sin restablecerla. `VITALSYNC_BASE_URL`, si se usa, debe coincidir con el frontend local configurado.

No es necesario crear otro proyecto para entrar al médico. El login compartido es `http://localhost:5188/login`; cada cuenta se dirige según su rol. Si existe una sesión del otro rol, ciérrala antes de cambiar de cuenta. Las contraseñas anteriores se mantuvieron sin cambios.

Las pruebas E2E temporales están en `infrastructure/test-doctor-portal.ps1`; requieren el override `infrastructure/compose.test.yml` y nunca deben usar el volumen principal. El script verifica la contraseña de pruebas existente sin cambiarla y conserva su volumen después de retirar contenedores/red. No se requiere mantener ese entorno levantado para usar ningún portal.

## Modificaciones de esta entrega

- `docker-compose.yml`: servicios únicos `db`, `backend`, `frontend`, nombre estable, volumen externo principal y reinicio automático.
- `infrastructure/Start-Vitalsync.ps1`: arranque protegido, volumen existente y servidor único sobre PGDATA.
- `infrastructure/Backup-Vitalsync.ps1`: respaldo local, lectura completa y verificación SHA256.
- `infrastructure/database_snapshot.py`: conteos y resúmenes de contenido sin exponer filas.
- `infrastructure/verify_persistence.py`: comprobación de cuentas existentes, roles, agenda, sesiones y datos; sin generar datos de negocio.
- `infrastructure/Test-Backend.ps1` y `backend/tests/conftest.py`: host `db` y base de pruebas aislada con credenciales efectivas.
- `infrastructure/compose.test.yml`, `infrastructure/test-doctor-portal.ps1` y `frontend/e2e/doctor-portal.spec.ts`: entorno temporal separado, nuevo nombre `db` y limpieza automática sin borrar volúmenes.
- README, documentación del médico y guía del paciente: instrucciones consistentes con un solo despliegue.
- `.gitignore`: protección adicional para archivos de respaldo.

No se modificaron `.env`, contraseñas, lógica de negocio, historial de Alembic ni las ramas remotas.
