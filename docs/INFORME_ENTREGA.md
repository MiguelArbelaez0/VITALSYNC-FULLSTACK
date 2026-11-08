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
| Alembic | Dos revisiones aplicadas hasta `20261108_overlap` |
| Docker | Tres servicios propios; inicio mediante Compose y script Windows |
| Git | Rama local `codex/patient-portal`, commits por bloques; sin push |

## Qué funciona de extremo a extremo

Registro exclusivo como paciente, login/logout y sesión persistente; dashboard con datos reales; perfil editable; catálogo, activación y renovación de planes; directorio y perfiles médicos; selección de fecha y turno; validación de cobertura y de disponibilidad; retención temporal; copago condicional; pagos simulados aprobados, rechazados, pendientes o en conciliación; conciliación sin duplicar operaciones; confirmación transaccional; comprobante imprimible; Mis citas; cancelación propia con motivo, confirmación expresa, política y versión; historial de canceladas y notificaciones persistentes.

Un paciente sin plan no puede retener. Un pago pendiente/rechazado no activa ni confirma. Un horario ocupado o bloqueado no se cobra. La confirmación revalida las reglas. Las citas propias simultáneas y los conflictos de médicos se controlan por intervalos. Las cancelaciones no eliminan la cita ni devuelven dinero automáticamente.

## Pruebas ejecutadas

| Prueba | Resultado |
| --- | --- |
| Pytest + PostgreSQL aislado | **40 aprobadas** |
| Vitest + React Testing Library | **13 aprobadas** |
| Playwright con API y PostgreSQL reales | **2 aprobadas**, escritorio y móvil; 10,3 segundos |
| TypeScript y build Vite | Correctos |
| Persistencia después de reiniciar los tres servicios | **PASS** |
| Auditoría npm de las dependencias instaladas | Sin vulnerabilidades reportadas |

La prueba de persistencia conserva y compara perfil, plan, pago, cita, historial, notificaciones y autenticación con la misma cookie. Luego cancela la cita que creó. Los datos no se borran. Evidencia: [persistence-result.json](persistence-result.json). Las pruebas backend cubren simultaneidad, restricciones SQL y rollback incluso ante un fallo al hacer commit.

Se inspeccionaron las capturas reales de dashboard, comprobante e historial en ambos tamaños. [Detalle de validación](VALIDACION.md).

## Acceso e instrucciones de prueba

Portal: http://localhost:5188. Documentación FastAPI: http://localhost:8088/docs. PostgreSQL: localhost:5488, base y usuario `vitalsync`.

Paciente ficticio: **paciente@vitalsync.demo** / **Paciente2026!**. La cuenta original conserva su plan inactivo, salvo acciones posteriores del usuario. Las pruebas E2E y de persistencia usan cuentas nuevas, sin sobrescribir la cuenta de presentación.

```powershell
docker compose up -d --build
```

Recorrido recomendado: iniciar sesión → Mi plan → activar Básico → Buscar médicos → Medicina general → Ver perfil y disponibilidad → seleccionar fecha y hora → Retener horario y continuar → autorizar copago simulado → Confirmar cita → comprobante → Mis citas → Ver detalle → Cancelar cita → motivo y confirmación expresa → Historial · Canceladas → Notificaciones.

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

`1dd6f0a05515` crea entidades, relaciones, estados, checks e índices. `20261108_overlap` agrega las exclusiones GiST para impedir solapamientos de médico y paciente. Las migraciones se aplican al arrancar el backend. El seed es idempotente y respeta los datos existentes.

La API incluye autenticación/perfil, dashboard, planes, especialidades, médicos y disponibilidad, retenciones y liberación, pagos y conciliación, confirmación, citas y cancelación, notificaciones y lectura. Tabla de métodos y rutas: [ARQUITECTURA.md](ARQUITECTURA.md). Contrato completo e interactivo en Swagger.

## Commits locales

- `23d7bd2`: backend, autenticación, planes y reservas transaccionales.
- `a22a7df`: frontend responsive conectado y recorrido del paciente.
- `21adaba`: control del commit antes de responder, pruebas de simultaneidad y rollback, recuperación local de contraseña, dependencias Python fijadas y scripts Windows.
- El bloque final incorpora README, guía, arquitectura, validación y capturas reales.

Consulta los identificadores definitivos con `git log --oneline`. No se creó un remoto ni se realizó push.

## Pendientes, límites y bloqueos

No quedan bloqueos observados en el recorrido validado del paciente. Docker Desktop estaba apagado inicialmente y se inició correctamente. Se corrigieron la FK del seed, la actualización de la vista al cerrar sesión y el desplazamiento de la navegación móvil.

Quedan fuera de esta entrega: dashboards médico/administrador, atención de consultas, historia clínica, videollamada/teleconsulta completa, reprogramación avanzada, devoluciones, pasarela real, correos, push, app nativa y publicación. Las consultas ficticias son presenciales; no se anuncia una videollamada disponible.

La emulación móvil se ejecutó con Chromium, no en Safari ni en un iPhone físico. El comprobante usa impresión del navegador; no genera PDF en el servidor. Hay una advertencia no bloqueante por tamaño del bundle Vite y otra de deprecación del adaptador Starlette/httpx en pruebas. No equivalen a fallos de compilación o de prueba. No se hizo prueba de carga sostenida ni auditoría de seguridad para despliegue público.

## Siguiente módulo recomendado

Administración de médicos, jornadas y bloqueos con permisos de administrador, reutilizando el mismo bloqueo del médico, restricciones PostgreSQL y auditoría. Después puede incorporarse el portal médico y el flujo diferenciado de cancelación por el profesional.
