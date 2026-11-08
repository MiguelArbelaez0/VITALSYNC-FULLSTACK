# Validación de la primera entrega

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
