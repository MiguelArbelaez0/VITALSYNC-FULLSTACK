# Validación de la primera entrega

Entorno probado: Windows, Docker Desktop con motor Linux, Node 24.14.1, React 19.3.1, Vite 8.3.6, Python 3.13 dentro de contenedor y PostgreSQL 17. Ejecución del 8 de noviembre de 2026 (Bogotá).

## Evidencia automatizada

| Verificación | Resultado |
| --- | --- |
| `npm run build` | TypeScript y compilación Vite correctos |
| `infrastructure/Test-Backend.ps1` | 40 pruebas Pytest aprobadas sobre PostgreSQL real |
| `npm test` | 13 pruebas Vitest / React Testing Library aprobadas |
| `npm run test:e2e` | 2 recorridos Playwright aprobados: escritorio e iPhone 13 emulado en Chromium |
| `python infrastructure/verify_persistence.py` | PASS; reinicio real de frontend, backend y PostgreSQL conservando el volumen |
| `npm install` / `npm ci` | Auditoría npm sin vulnerabilidades reportadas en las dependencias instaladas |
| Alembic | `20261108_overlap (head)` aplicado en la base de demostración |

La suite backend usa exclusivamente `vitalsync_test`, creada dentro del contenedor PostgreSQL de VITALSYNC. La BD de demostración no se trunca. Las 40 pruebas pasaron en 38,91 segundos. El resultado de los servicios se registra en el informe de entrega.

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
- Rollback en confirmación, cancelación y fallo al hacer commit; nunca respuesta de éxito sobre un commit fallido.
- Seed idempotente, restricciones en la BD y pagos demo deshabilitados fuera de demo.

## Cobertura frontend

Validación de formularios, login conectado, rutas protegidas, logout que retira la vista, métricas del dashboard, carga/error, directorio y filtros, selección de fecha, retención por API, confirmación sin copago, rechazo del backend sin falso éxito, comprobante, desistimiento, confirmación expresa de cancelación, historial de canceladas y conciliación de pagos pendientes.

Estas pruebas de componente usan respuestas controladas para aislar la interfaz. La persistencia y la integración reales se comprueban con Playwright y PostgreSQL, sin interceptar peticiones.

## Recorrido web real

En cada tamaño Playwright crea una cuenta nueva, cierra e inicia sesión, intenta reservar sin plan, simula rechazo de pago de plan, genera un pendiente, lo concilia, busca Medicina general, selecciona un horario disponible, retiene, aprueba copago, confirma, revisa y recarga el comprobante, consulta Mis citas, desiste de cancelar, cancela expresamente, consulta Canceladas y comprueba la notificación. También verifica ausencia de desplazamiento horizontal en Notificaciones.

Capturas obtenidas de esos recorridos e inspeccionadas visualmente:

| Pantalla | Escritorio | Móvil |
| --- | --- | --- |
| Dashboard | [Ver](screenshots/dashboard-desktop.png) | [Ver](screenshots/dashboard-mobile.png) |
| Comprobante | [Ver](screenshots/receipt-desktop.png) | [Ver](screenshots/receipt-mobile.png) |
| Historial canceladas | [Ver](screenshots/history-desktop.png) | [Ver](screenshots/history-mobile.png) |

La prueba móvil es emulación de dimensiones y entrada táctil de iPhone 13 en Chromium. No se ejecutó Safari ni un iPhone físico.

## Persistencia tras reiniciar

El script independiente crea una cuenta nueva, aprueba un plan Premium, retiene y confirma una cita y guarda una instantánea de perfil, plan, pagos, cita con historial y notificaciones. Luego ejecuta `docker compose restart`, espera la API y compara todos esos datos utilizando la misma cookie de sesión. La comparación fue idéntica. Finalmente cancela su cita. Evidencia: [persistence-result.json](persistence-result.json).

## Incidencias corregidas durante la validación

- Seed: se insertó el paciente antes de crear su notificación para respetar la FK.
- Logout: se corrigió la invalidación de la caché para retirar inmediatamente la pantalla autenticada.
- Navegación móvil: se agregó desplazamiento al menú para alcanzar todas las acciones en alturas cortas.
- Transacciones: el commit se realiza antes de enviar la respuesta, con prueba de fallo al confirmar el commit.

## Límites de esta validación

Vite muestra una advertencia de tamaño del bundle principal (~526 kB sin gzip, ~164 kB comprimido); no impide compilar ni ejecutar la demo. Starlette emite una advertencia de deprecación sobre su adaptador de pruebas con httpx; las pruebas ejecutadas pasan. La cobertura aquí es funcional, no una auditoría de seguridad o una prueba de carga sostenida.

No se probaron videollamadas, pagos reales, correos, push, atención médica, módulos administrativos, devoluciones ni despliegue porque no están implementados. Los errores de base de datos se prueban mediante fallo inyectado y rollback, sin dañar la base de demostración. No se utilizó SQLite ni se declaró un navegador real sin ejecutarlo.
