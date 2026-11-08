# Informe de entrega · Portal del paciente

8 de noviembre de 2026 · Preparación para la demostración del 9 de noviembre de 2026.

## Resultado

Se implementó el portal del paciente desde una carpeta inicialmente vacía, conectando React, FastAPI y PostgreSQL mediante una API REST. El recorrido de registro a cancelación fue ejecutado en navegador real Chromium, tanto en escritorio como en emulación de iPhone 13, sin mocks de API.

## Estado de los componentes

| Componente | Estado comprobado |
| --- | --- |
| React | Compila con TypeScript/Vite, servido por nginx y conectado a `/api` |
| FastAPI | Responde a health, autenticación, consultas, pagos y operaciones de agenda |
| PostgreSQL | Datos reales persistidos en volumen Docker propio |
| Alembic | Revisiones de solapamiento y modalidad virtual aplicadas hasta `20261110_virtual_history` |
| Docker | Tres servicios propios; inicio mediante Compose y script Windows |
| Git | Rama local `codex/patient-portal`, commits por bloques; sin push |

## Qué funciona de extremo a extremo

Registro exclusivo como paciente, login/logout y sesión persistente; dashboard con datos reales; perfil editable; catálogo, activación y renovación de planes; directorio y perfiles médicos; selección de modalidad presencial o virtual antes de elegir turno; cobertura por modalidad; retención temporal; copago condicional; pagos simulados aprobados, rechazados, pendientes o en conciliación; confirmación transaccional; comprobante imprimible; Mis citas; cancelación propia; historial y notificaciones persistentes. La cita virtual ofrece una sala de estados demostrativos guardados en PostgreSQL, accesible solo al paciente dueño.

Un paciente sin plan no puede retener. Un pago pendiente/rechazado no activa ni confirma. Un horario ocupado o bloqueado no se cobra. La confirmación revalida las reglas. Las citas propias simultáneas y los conflictos de médicos se controlan por intervalos. Las cancelaciones no eliminan la cita ni devuelven dinero automáticamente.

## Pruebas ejecutadas

| Prueba | Resultado |
| --- | --- |
| Pytest + PostgreSQL aislado | **47 aprobadas** |
| Vitest + React Testing Library | **15 aprobadas** |
| Playwright con API y PostgreSQL reales | **2 aprobadas**, escritorio y móvil |
| TypeScript y build Vite | Correctos |
| Persistencia después de reiniciar los tres servicios | **PASS** |
| Auditoría npm de las dependencias instaladas | Sin vulnerabilidades reportadas |

La prueba de persistencia conserva y compara perfil, plan, pago, cita presencial, cita virtual, estado de teleconsulta, historial, notificaciones y autenticación con la misma cookie. Luego cancela las dos citas que creó. Los datos existentes no se borran. Evidencia: [persistence-result.json](persistence-result.json). Las pruebas backend cubren simultaneidad, restricciones SQL y rollback incluso ante un fallo al hacer commit.

Se inspeccionaron las capturas reales de dashboard, comprobante e historial en ambos tamaños. [Detalle de validación](VALIDACION.md).

## Acceso e instrucciones de prueba

Portal: http://localhost:5188. Documentación FastAPI: http://localhost:8088/docs. PostgreSQL: localhost:5488, base y usuario `vitalsync`.

Paciente ficticio: **paciente@vitalsync.demo** / **Paciente2026!**. La cuenta original conserva su plan inactivo, salvo acciones posteriores del usuario. Las pruebas E2E y de persistencia usan cuentas nuevas, sin sobrescribir la cuenta de presentación.

```powershell
docker compose up -d --build
```

Recorrido presencial recomendado: iniciar sesión → Mi plan → activar Básico → Buscar médicos → Medicina general → elegir Presencial → seleccionar fecha y hora → retener → autorizar copago simulado → confirmar → comprobante.

Recorrido virtual: activar Estándar o Premium → Buscar médicos → elegir Virtual → retener turno virtual → autorizar copago según el plan → confirmar → **Ver teleconsulta simulada** → avanzar el estado. Esta demostración no conecta audio ni video ni representa una consulta médica real.

Guía completa con rutas y botones reales: [GUIA_DEMOSTRACION_PACIENTE.md](GUIA_DEMOSTRACION_PACIENTE.md).

Pruebas reproducibles:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/Test-Backend.ps1
cd frontend
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
cd ..
python infrastructure/verify_persistence.py
```

Ejecuta la comprobación de persistencia después de terminar Playwright, porque reinicia los servicios.

## Migraciones y endpoints

`1dd6f0a05515` crea entidades y relaciones. `20261108_overlap` agrega exclusiones GiST. `20261109_virtual` agrega modalidades con valor `PRESENCIAL` para las citas existentes y cobertura virtual para Estándar/Premium. `20261110_virtual_history` amplía el historial de estados para registrar la sala simulada. Las migraciones se aplican al arrancar el backend y no eliminan citas ni datos persistidos.

La API incluye autenticación/perfil, dashboard, planes, especialidades, médicos y disponibilidad, retenciones y liberación, pagos y conciliación, confirmación, citas y cancelación, notificaciones y lectura. Tabla de métodos y rutas: [ARQUITECTURA.md](ARQUITECTURA.md). Contrato completo e interactivo en Swagger.

## Commits locales

- `23d7bd2`: backend, autenticación, planes y reservas transaccionales.
- `a22a7df`: frontend responsive conectado y recorrido del paciente.
- `21adaba`: control del commit antes de responder, pruebas de simultaneidad y rollback, recuperación local de contraseña, dependencias Python fijadas y scripts Windows.
- El bloque final incorpora README, guía, arquitectura, validación y capturas reales.

Consulta los identificadores definitivos con `git log --oneline`. No se creó un remoto ni se realizó push.

## Pendientes, límites y bloqueos

No quedan bloqueos observados en el recorrido validado del paciente. Docker Desktop estaba apagado inicialmente y se inició correctamente. Se corrigieron la FK del seed, la actualización de la vista al cerrar sesión y el desplazamiento de la navegación móvil.

Quedan fuera de esta entrega: dashboards médico/administrador, atención médica real, historia clínica, audio/video, reprogramación avanzada, devoluciones, pasarela real, correos, push, app nativa y publicación. La sala virtual solo permite cambiar estados de demostración persistidos y no anuncia videollamada disponible.

La emulación móvil se ejecutó con Chromium, no en Safari ni en un iPhone físico. El comprobante usa impresión del navegador; no genera PDF en el servidor. Hay una advertencia no bloqueante por tamaño del bundle Vite y otra de deprecación del adaptador Starlette/httpx en pruebas. No equivalen a fallos de compilación o de prueba. No se hizo prueba de carga sostenida ni auditoría de seguridad para despliegue público.

## Siguiente módulo recomendado

Administración de médicos, jornadas y bloqueos con permisos de administrador, reutilizando el mismo bloqueo del médico, restricciones PostgreSQL y auditoría. Después puede incorporarse el portal médico y el flujo diferenciado de cancelación por el profesional.
