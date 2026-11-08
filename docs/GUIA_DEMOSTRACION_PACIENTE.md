# Demostración del portal del paciente

Fecha de presentación: **9 de noviembre de 2026**. Todo el recorrido utiliza datos ficticios persistidos en PostgreSQL. No se cobran importes reales.

## 1. Iniciar y comprobar

Abre Docker Desktop en Windows, espera a que el motor Linux responda y, en la raíz de VITALSYNC-FULLSTACK, ejecuta:

```powershell
docker compose up -d --build
docker compose ps
```

Backend y PostgreSQL deben figurar `healthy`. Frontend debe estar `Up`. Abre [el portal](http://localhost:5188), [Swagger](http://localhost:8088/docs) y, si quieres comprobar la conexión real, [health](http://localhost:8088/api/health).

## 2. Iniciar sesión o registrar un paciente nuevo

En `/`, pulsa **Iniciar sesión**. Correo: `paciente@vitalsync.demo`. Contraseña: `Paciente2026!`. Pulsa **Iniciar sesión**.

Verás `/portal` con tu nombre, plan, próximas citas y notificaciones. Si la cuenta de demostración ya fue utilizada, conserva esos cambios. Para comenzar con un plan inactivo, pulsa **Cerrar sesión** (en móvil abre primero **Abrir menú**), entra en **Crea tu cuenta** y registra un correo nuevo y una contraseña de al menos 10 caracteres. El registro inicia sesión automáticamente y solo crea un paciente.

## 3. Consultar el plan inactivo

Entra en **Mi plan**, ruta `/portal/plans`. Se muestra la cobertura actual y el estado **Sin activar** cuando no tienes plan. Puedes demostrar que una cuenta sin plan no reserva: entra en **Buscar médicos**, abre **Ver perfil y disponibilidad**, selecciona un turno y pulsa **Retener horario y continuar**. El backend responde **Debes activar tu plan para solicitar una cita médica** y no crea una retención ni inicia un cobro.

## 4. Activar el plan

Regresa a **Mi plan**. Para mostrar el copago, elige **Básico** y pulsa **Activar plan** en esa tarjeta. El diálogo muestra el importe simulado de $59.000 y advierte que solo un pago aprobado activa la cobertura.

- **Simular rechazo**: la operación queda rechazada y el plan sigue inactivo. Puedes volver a intentar.
- **Simular pendiente**: la operación queda pendiente; no se activa el plan y no se presenta otro pago para duplicarla.
- **Conciliar como aprobado**: resuelve esa operación pendiente, activa el plan y cierra el diálogo.
- También puedes aprobar directamente con **Autorizar y simular aprobación**.

La cobertura muestra **Activo** y su vencimiento. Básico cubre Medicina general y requiere $15.000 por consulta. Estándar cubre Medicina general, Cardiología y Dermatología, con $10.000 de copago. Premium cubre las cinco especialidades y no exige copago. La pantalla detalla los precios vigentes del seed.

## 5. Encontrar médico, fecha y hora

Entra en **Buscar médicos**, ruta `/portal/doctors`. Usa **Buscar por nombre del médico…** o **Todas las especialidades**. Con Básico, selecciona **Medicina general**.

Abre **Ver perfil y disponibilidad** de **Dra. Isabella Ríos**. En su perfil, selecciona una **Fecha de consulta** entre las jornadas publicadas. Los horarios aparecen en hora de Bogotá. Los deshabilitados dicen **No disponible**. A las 11:00 del día siguiente hay un bloqueo administrativo de demostración.

Antes de elegir el médico, selecciona **Presencial** o **Virtual** en **¿Qué modalidad de atención necesitas?**. El directorio y los turnos se filtran por esa modalidad. La cobertura del plan también se valida: Básico cubre consultas presenciales; Estándar y Premium cubren ambas modalidades. En la ficha del médico puedes cambiar de modalidad antes de retener el turno. El servidor vuelve a validar la modalidad, el plan y la disponibilidad al crear y confirmar la retención.

Selecciona un turno habilitado y pulsa **Retener horario y continuar**. El servidor verifica plan, cobertura, agenda y conflictos. Si el horario fue tomado por otro paciente, muestra el conflicto y actualiza disponibilidad: cambia de turno, de fecha o vuelve al directorio para elegir otro médico. No se crea una cita ni un pago cuando falla esta validación.

## 6. Retención temporal

La ruta `/portal/booking/:id` muestra **Un paso más para tu cita**, médico, fecha, hora, modalidad y copago. El contador muestra la vigencia restante de la retención (10 minutos por defecto). Una retención no es una cita confirmada.

**Liberar horario y volver** abandona expresamente el turno. Si vence el contador, se ofrece **Consultar disponibilidad** para volver a empezar. Aunque manipules la interfaz, el backend rechaza una retención vencida.

## 7. Copago condicional

Con Básico, pulsa **Autorizar y simular aprobación** en la sección de copago. Verás **Copago aprobado** y el identificador de transacción. No se piden datos de tarjetas.

Para demostrar errores puedes simular rechazo y luego reintentar mientras siga vigente la retención. Si simulas pendiente o en conciliación, primero debes resolverlo con **Conciliar como aprobado** o **Conciliar como rechazado**. Un pendiente no confirma la cita. Una conciliación aprobada tardía sobre una retención vencida se rechaza; queda la operación pendiente para resolverla como rechazada en este entorno académico.

Con Premium, esta pantalla dice **Tu plan cubre esta consulta** y **No necesitas un pago adicional para esta cita**. No se ofrece un cobro inexistente.

## 8. Confirmar y consultar el comprobante

Pulsa **Confirmar cita**. FastAPI revalida la sesión, plan, cobertura, médico, horario, retención y copago. Si algo falla, muestra el motivo y no anuncia un éxito.

Al aprobarse, navega a `/portal/appointments/:id?confirmed=1` y aparece **¡Tu cita está confirmada!**. El comprobante incluye código `VS-…`, paciente, médico, especialidad, fecha, inicio y fin, plan, estado y copago. Usa **Imprimir comprobante** para imprimirlo o guardar PDF desde el navegador.

El comprobante especifica **Presencial** con la sede ficticia, o **Virtual · Teleconsulta simulada** sin mostrar una dirección presencial.

## 8.1 Sala de teleconsulta simulada

En una cita virtual confirmada, pulsa **Ver teleconsulta simulada** desde el comprobante. La sala muestra paciente, médico, especialidad, fecha, hora y el estado guardado en PostgreSQL. **Simular siguiente estado** avanza de forma secuencial por los estados de demostración; cada cambio queda en el historial de la cita. La cuenta debe ser la paciente propietaria de la cita. Una cita virtual se puede cancelar conforme a la misma política horaria y deja de permitir acceso a la sala.

La sala no conecta audio ni video, no pide permisos del dispositivo y no genera enlaces ni atiende consultas médicas reales.

## 9. Mis citas

Entra en **Mis citas**, ruta `/portal/appointments`. La pestaña **Próximas citas** muestra las citas futuras confirmadas; **Ver detalle** abre su comprobante. **Historial** contiene consultas anteriores no canceladas. El dashboard muestra ahora el conteo y la próxima cita consultados al backend.

Recarga la página para comprobar que el estado proviene de la base y no de un arreglo de React.

## 10. Cancelación y desistimiento

En el detalle pulsa **Cancelar cita**. El diálogo muestra médico, especialidad, fecha, hora y política. Por defecto solo puedes cancelar con **más de 2 horas** de anticipación.

Para demostrar desistimiento pulsa **Conservar mi cita**: no se envía una cancelación y la cita sigue confirmada.

Abre de nuevo **Cancelar cita**, escribe el **Motivo de cancelación**, marca **Confirmo que deseo cancelar mi cita.** y pulsa **Confirmar cancelación**. El servidor verifica pertenencia, estado, anticipación y versión. Si hubo un cambio concurrente, pide actualizar; si la política no se cumple, explica el rechazo.

Al cancelar verás **Cancelada**, la fecha, el motivo y el registro de cambios. Cuando existe copago, se indica que queda sujeto a gestión económica futura. No se hace una devolución automática.

## 11. Historial y notificaciones

Regresa a **Mis citas** y abre **Historial · Canceladas**. La cita permanece visible con su código y **Ver detalle**. El turno se libera para una reserva posterior sin borrar la cita anterior.

Entra en **Notificaciones**, ruta `/portal/notifications`. Allí están la activación del plan, la confirmación y la cancelación. Pulsa **Marcar leída** para actualizar el estado real. En **Mi perfil**, `/portal/profile`, puedes modificar nombre y teléfono con **Guardar cambios**.

## 12. Comprobar persistencia

Conserva tu sesión y la página del detalle. En PowerShell ejecuta:

```powershell
docker compose restart
```

Espera a que los servicios vuelvan a responder, recarga y comprueba que permanecen la sesión, el plan, las citas y el historial. No uses `down -v`.

Para repetir una comprobación automática independiente, sin Playwright en ejecución:

```powershell
python infrastructure/verify_persistence.py
```

El script crea su propia cuenta ficticia, reinicia los tres servicios sin borrar el volumen, compara los datos y deja `docs/persistence-result.json`.

## Preparación del día de la presentación

Ejecuta `python -m app.seed` dentro del backend si quieres ampliar jornadas a partir de la fecha actual: `docker compose exec backend python -m app.seed`. Prepara una cuenta nueva si quieres mostrar plan inactivo desde el inicio. No necesitas reiniciar ni borrar la base para repetir la demostración. La experiencia virtual es simulada; las videollamadas y pagos reales, además de portales de médico/administrador, correos y atención clínica, corresponden a entregas posteriores.
