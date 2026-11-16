# Videollamadas para citas virtuales · v1.1.0

## Alcance

La rama `feature/video-calls-v1.1.0` agrega LiveKit autohospedado como proveedor opcional para las citas virtuales que ya registra VITALSYNC. No crea reservas independientes. La versión estable `v1.0.0` y su etiqueta no se modifican.

La videollamada solo se habilita si el entorno tiene LiveKit configurado. Si LiveKit está apagado, continúan disponibles las pantallas demostrativas existentes. Pagos, citas presenciales e historias clínicas permanecen fuera del flujo audiovisual.

## Arquitectura

- React carga los componentes oficiales `PreJoin`, `LiveKitRoom` y `VideoConference` bajo demanda, desde los portales de paciente y médico.
- FastAPI emite tokens cortos después de verificar sesión, rol, cita virtual, titularidad, asignación y ventana horaria.
- PostgreSQL conserva el nombre estable de la sala por cita, estado de conexión, auditoría e historial de eventos administrativos. Nunca almacena audio, video ni transcripciones.
- El servidor LiveKit se incorpora al Compose existente `vitalsync` bajo el perfil `video`; el volumen de PostgreSQL no cambia.
- Los webhooks firmados por LiveKit registran entradas y desconexiones. `event_id` único hace idempotente el registro de entregas repetidas.

LiveKit documenta `PreJoin` para previsualizar y seleccionar cámara y micrófono antes de conectar, y `LiveKitRoom` como proveedor React de la sesión ([PreJoin](https://docs.livekit.io/reference/components/react/component/prejoin/), [LiveKitRoom](https://docs.livekit.io/reference/components/react/component/livekitroom/)).

## Preparación local en Windows

Desde PowerShell, en la carpeta del repositorio:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\infrastructure\Configure-LiveKit.ps1
docker compose --profile video up -d --build
docker compose ps
```

El script genera una clave y un secreto aleatorios para el entorno local, conserva las demás variables existentes y no muestra los valores. `.env` permanece ignorado por Git. El perfil `video` es requerido para iniciar LiveKit. El volumen de PostgreSQL se declara externo como `vitalsync_vitalsync_data`; no ejecutar `down -v`.

Accesos de la aplicación: `http://localhost:5188/login`, `http://localhost:5188/portal`, `http://localhost:5188/doctor` y `http://localhost:8088/docs`.

## Variables

| Variable | Uso |
| --- | --- |
| `LIVEKIT_ENABLED` | Habilita las rutas reales en el backend. El script local la activa. |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | Firma de tokens, API y webhooks; solo backend y LiveKit. No se compilan dentro de React. |
| `LIVEKIT_API_URL` | URL interna del servidor para las operaciones servidor a servidor. |
| `LIVEKIT_PUBLIC_URL` | URL WebSocket que el backend entrega al participante autorizado. En local es `ws://localhost:7880`. |
| `LIVEKIT_TOKEN_TTL_SECONDS` | Duración solicitada del token, limitada a 60–900 segundos (local: 600). |

La configuración local usa credenciales generadas y puertos ligados a loopback. Para cualquier ambiente público se requieren credenciales nuevas, TLS y valores separados; no se debe copiar `.env` local ni sus claves.

## Acceso y privacidad

- Paciente: solo puede obtener token para sus propias citas virtuales.
- Médico: solo para una cita virtual asignada a su perfil profesional vinculado.
- Administrador: consulta metadatos de conexión desde el portal, sin acceso a salas ni medios.
- Presencial, cancelada, finalizada, fuera de horario, usuario anónimo o participante externo: sin token.
- Los tokens permiten entrar únicamente a la sala persistida de la cita y publicar cámara/micrófono. No permiten crear/listar salas, administrar, grabar ni publicar datos de sala. La identidad técnica es `user:<id>`; el nombre visible es el rol genérico.
- No hay grabación, transcripción, exportación audiovisual ni historia clínica dentro de la sala. La auditoría guarda tipo de evento, rol, usuario y cita, nunca contenido multimedia.

Rutas de acceso: `POST /api/appointments/{id}/livekit-token` para el titular paciente y `POST /api/doctor/appointments/{id}/livekit-token` para el médico asignado. La finalización formal corresponde a `POST /api/doctor/appointments/{id}/livekit-finalize`.

## Estados y ciclo

La cita virtual conserva su ciclo de negocio actual. El estado técnico LiveKit se muestra aparte como `WAITING`, `CONNECTED`, `RECONNECTING` o `DISCONNECTED`. Cada sala tiene un nombre aleatorio estable creado al confirmar la cita; recargar o solicitar otro token no genera una sala nueva.

Cuando ambos participantes se conectan, la cita pasa a `IN_PROGRESS` y se registran el historial y auditoría. Una pérdida de conexión actualiza solo el estado técnico y permite reconectar; cerrar la pestaña no finaliza la consulta. El médico confirma **Finalizar consulta**. La operación actualiza PostgreSQL, notifica al paciente, invalida nuevos tokens, cierra la sala en segundo plano y mueve la cita a `ATTENDED` en Próximas/Historial. La repetición de la finalización no crea eventos duplicados.

La interfaz de administración muestra si el proveedor está configurado y el estado de conexión; no expone nombre de sala, token ni medios.

## Dispositivos y errores

`PreJoin` ofrece vista previa y selección de dispositivos. Los componentes LiveKit controlan cámara, micrófono, selección de dispositivos y salida temporal. Permisos denegados, falta de dispositivos, servidor no disponible o red interrumpida se muestran como errores de conexión; se puede volver a preparación y solicitar un token nuevo mientras la cita siga dentro de su ventana.

Los tokens duran como máximo 15 minutos. Si expiran antes del ingreso, se solicita otro mediante la misma comprobación de permisos. Una consulta finalizada o cancelada nunca vuelve a emitirlos.

## Docker y puertos

El servicio corre dentro de la red del proyecto Compose `vitalsync` y se inicia con el perfil `video`. En el equipo local:

- `7880/TCP`: señalización y WebSocket.
- `7881/TCP`: transporte WebRTC/TCP de respaldo.
- `50000–50100/UDP`: medios WebRTC/ICE.

Los puertos publicados en este Compose local quedan asociados a `127.0.0.1`. LiveKit documenta además los puertos ICE/TURN y requiere una dirección pública conocida para despliegues detrás de NAT ([puertos y firewall](https://docs.livekit.io/transport/self-hosting/ports-firewall/), [despliegue self-hosted](https://docs.livekit.io/transport/self-hosting/deployment/)).

## Pruebas

Backend: `.\infrastructure\Test-Backend.ps1` crea una base de pruebas aislada con prefijo `vitalsync_test_audit_`; las pruebas no usan ni truncan la base `vitalsync`.

Para una comprobación audiovisual local entre dos contextos Chromium con entradas sintéticas de cámara y micrófono:

```powershell
.\infrastructure\test-livekit.ps1
```

La variante `.\infrastructure\test-livekit.ps1 -UsePhysicalDevices` usa los dispositivos físicos conectados. Apaga screenshots y trazas para no guardar imágenes o contenido de la cámara. Ambos modos levantan una base aislada y transmiten medios solo a LiveKit local; no se graban.

El script crea otra base temporal aislada, emite credenciales de fixture a una carpeta local protegida, inicia el servicio LiveKit de prueba en el mismo proyecto y ejecuta el E2E de medios. El modo sintético y el modo con dispositivos físicos verifican video y pistas de audio activas en ambos navegadores, reconexión y finalización. La prueba física usa los medios localmente y no guarda capturas, trazas ni grabaciones. No mide calidad audible ni equivale a una llamada entre redes distintas.

## Capturas

El E2E local completó la preparación, conexión de dos participantes, publicación y recepción de video/audio, reconexión tras recargar el portal médico y finalización. Las capturas siguientes se generaron con medios sintéticos reproducibles; la prueba con dispositivos físicos pasó sin generar capturas.

![Preparación de cámara y micrófono antes de ingresar](screenshots/livekit-prejoin-desktop.png)

![Sala LiveKit local con video bidireccional](screenshots/livekit-room-desktop.png)

## Diferentes redes y limitaciones

Esta configuración no habilita conexiones desde Internet ni desde otra red. Para ello hacen falta un dominio resoluble, HTTPS para la aplicación, WSS para LiveKit, certificados públicos válidos, DNS, dirección pública anunciada por el servidor, configuración NAT/firewall y puertos WebRTC accesibles. Redes corporativas pueden requerir TURN/TLS o TURN/UDP. LiveKit advierte que el despliegue WebRTC debe exponer sus puertos ICE y anunciar correctamente la IP ([requisitos de firewall](https://docs.livekit.io/transport/self-hosting/ports-firewall/)).

No se contrataron servicios, publicaron puertos, crearon DNS ni desplegaron TURN. Esa validación queda pendiente de infraestructura y autorización. El producto sigue siendo académico y no reemplaza atención clínica real.
