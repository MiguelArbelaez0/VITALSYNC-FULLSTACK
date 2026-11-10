# Ciclo de vida de teleconsultas demostrativas

La simulación requiere `DEMO_MODE=true` en FastAPI. Fuera de ese modo, el portal de pacientes no puede ejecutar ninguna transición demostrativa, incluso durante la fecha de la cita. Este flujo no acredita atención clínica ni implementa audio o video.

La finalización conserva el estado compatible `ATTENDED` y exige `completion_source=DEMO`, `simulated_completed_at` y `clinically_attended=false`. React muestra **Finalizada (simulación)**. La fecha programada no cambia.

El servicio `app/services/teleconsultations.py` bloquea paciente, cita y teleconsulta. La dependencia `get_db`, con alcance de función, confirma la transacción antes de enviar la respuesta. Estado de cita, estado de sala, historial, auditoría y notificación se guardan juntos; cualquier fallo revierte la operación. Una repetición o carrera devuelve 409 sin duplicar eventos.

Las presencias tienen marcas independientes: puede llegar primero cualquiera de los participantes. Iniciar atención requiere ambas. `IN_PROGRESS` mantiene las restricciones de solapamiento de paciente y médico. Ausencias e incidencia técnica son terminales y no se contabilizan como atención finalizada.

`GET /api/appointments?view=upcoming` consulta PostgreSQL y excluye estados terminales, aunque su fecha programada sea futura. `view=completed` incluye `ATTENDED` independientemente de la fecha. `view=history` conserva estados terminales y citas vencidas; canceladas tienen su vista separada. El dashboard usa los mismos estados pendientes. Cada transición invalida las consultas de TanStack Query, incluyendo agenda, detalle, dashboard y notificaciones.

Las migraciones `20261115_demo_completion` y `20261116_demo_metadata` agregan metadatos y restricciones. La primera repara teleconsultas previamente finalizadas, iniciadas o con ausencia cuya cita seguía confirmada, conservando los eventos anteriores y agregando evidencia de reparación. No modifica citas ya canceladas ni elimina registros. El downgrade se rechaza explícitamente para evitar perder evidencia; recuperar una revisión anterior requiere una copia de respaldo anterior.

## Verificación reproducible

Backend: ejecutar `pytest -q` dentro del contenedor backend con `TEST_DATABASE_URL` apuntando a **vitalsync_test**. La suite exige ese nombre y limpia únicamente esa base aislada. Nunca apuntar las pruebas a la base de demostración.

Frontend, desde `frontend`: `npm test` y `npm run build`.

Migraciones y contenedores: `docker compose exec -T backend alembic check`, `docker compose exec -T backend alembic current` y `docker compose config --quiet`.

El E2E `frontend/e2e/demo-lifecycle.spec.ts` requiere un backend separado con una base aislada y un frontend que lo use. Para esta verificación se utilizó `vitalsync_e2e`, backend en 8089 y Vite en 5189, configurado con `VITALSYNC_API_TARGET=http://127.0.0.1:8089`. El backend de prueba permite exclusivamente ese origen mediante `ALLOWED_ORIGINS=http://127.0.0.1:5189`.

Con ese entorno preparado, definir `E2E_BASE_URL=http://127.0.0.1:5189` y `E2E_LIFECYCLE_ISOLATED=true`; ejecutar `npx playwright test e2e/demo-lifecycle.spec.ts`. La prueba crea pacientes ficticios únicos y verifica escenarios con una y dos citas futuras, en escritorio y móvil. Si se definen `E2E_RESTART_CONTAINER` y `E2E_RESTART_POSTGRES` con los nombres de los contenedores de prueba, también reinicia los servicios sin eliminar volúmenes, vuelve a iniciar sesión y comprueba los registros persistidos. Ejecutar estos reinicios después de terminar las demás pruebas que usan PostgreSQL.

Las pruebas de dominio cubren rollback ante fallo de notificación, finalización concurrente, acceso ajeno, modo normal, orden de presencia, ausencias, incidencia técnica, metadatos, historial, próxima cita y conservación de otras reservas. La suite existente cubre reservas presenciales, planes y pagos.
