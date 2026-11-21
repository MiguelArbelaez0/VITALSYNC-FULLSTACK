# Registro y acceso unificados · VITALSYNC v1.1

La política vigente reemplaza el acceso Google para médicos y su cambio de contraseña desde el portal. El login compartido es `/login` (también `/auth`); el backend valida credenciales, estado y rol. React dirige PATIENT a `/portal`, DOCTOR a `/doctor` y ADMIN a `/admin`. No existe registro público de administradores.

## Pacientes

En **Registrarse → Paciente**, completar nombres, apellidos, CC de 6–10 dígitos, correo personal de cualquier proveedor válido, teléfono, contraseña y consentimiento. El alta crea exclusivamente PATIENT y abre su sesión. Google permite registro y acceso solo de pacientes; exige ID token válido, firma, emisor, audiencia, vencimiento, nonce y correo verificado. El identificador es `sub`; nunca se fusionan cuentas por coincidencia de correo.

Una cuenta existente vincula Google desde **Mi perfil**, confirmando su contraseña. Una cuenta creada solo con Google puede establecer contraseña por el procedimiento privado de recuperación existente. El paciente puede cambiar su contraseña en su perfil; se revocan las otras sesiones. Recuperación: `/recover` y operador autorizado, según `admin-portal.md`.

## Solicitud médica

1. En el mismo registro seleccionar **Médico**. Completar identidad, especialidad, registro profesional, teléfono y perfil. El contacto personal es opcional y no sirve para iniciar sesión.
2. El correo propuesto es de solo lectura. Se normaliza el primer nombre y primer apellido, eliminando tildes y separadores; se añade un sufijo numérico si está ocupado. La dirección definitiva se reserva al enviar, bajo bloqueo transaccional y restricciones únicas PostgreSQL.
3. Se crea `doctor_applications` en PENDING, sin User ni acceso clínico. Guardar el código privado de seguimiento: solo su hash queda en la base. Permite consultar el estado sin mostrar documentos ni credenciales.
4. Administración → **Solicitudes médicas** permite buscar, filtrar, revisar datos e historial y aprobar o rechazar con motivo. En DEMO_MODE la verificación es **académica simulada**, no una consulta a registros oficiales. Fuera de demo el operador debe realizar una revisión profesional manual; la aplicación no la realiza automáticamente.
5. Solo aprobar crea Doctor, User DOCTOR y DoctorAccount. Una aprobación repetida es idempotente. Los registros existentes conservan sus identificadores, correos, hashes, especialidades, horarios, citas y permisos.
6. La aprobación genera una contraseña criptográficamente aleatoria e individual. Su hash Argon2id autentica; una copia temporal cifrada con Fernet permite la entrega privada única. Nunca se devuelve esa contraseña en las API generales.

Las solicitudes rechazadas conservan su trazabilidad y reserva; para revisar un rechazo se contacta a administración. No se reaprueban silenciosamente. Los perfiles antiguos no tienen necesariamente documento profesional; las coincidencias de nombre completo se remiten a revisión administrativa para evitar duplicaciones.

## Configuración y entrega privada

Desde la raíz, preparar una vez la clave de cifrado local y arrancar:

```powershell
.\infrastructure\Configure-DoctorCredentials.ps1
docker compose -p vitalsync --profile video up -d --build --wait
```

El script conserva cualquier clave existente. `DOCTOR_CREDENTIAL_KEY` vive únicamente en `.env`, ignorado por Git, y en el backend. No va a Vite, logs ni respuestas HTTP. Se reutiliza `cryptography`, ya instalado para Google; no se añaden dependencias. Si falta la clave, la aprobación falla sin crear parcialmente la cuenta.

Administración → **Entregas privadas** muestra ID, correo y estado, nunca el secreto. En PowerShell del equipo de despliegue:

```powershell
.\infrastructure\Export-DoctorCredentials.ps1 -DeliveryId 123 -AdminEmail admin@vitalsync.demo
```

Sustituir el ID por la entrega PENDING real. El comando exige contraseña administrativa sin mostrarla, verifica rol y permiso `accounts` y genera un archivo exclusivo protegido. Copia a `Escritorio\VITALSYNC-CREDENCIALES\medico-<identificador>\medico.credentials.json`, restringido por ACL al usuario de Windows y SYSTEM. Comprueba SHA-256 y retira el archivo temporal del contenedor. La transacción marca DELIVERED y elimina el secreto cifrado. No admite una segunda exportación.

El operador verifica la identidad del titular y le entrega su archivo por un canal privado. **No se envían correos reales a `.demo`.** No adjuntar el archivo a Git, capturas, informes o chats compartidos. Ante un fallo de copia, recuperar el archivo privado que el script conserva en el contenedor; no reiniciar ese contenedor antes de recuperarlo. El hash nunca permite consultar contraseñas antiguas.

El médico ingresa inmediatamente con su correo asignado y contraseña individual: no hay cambio obligatorio ni Google. Para pérdida o compromiso, Administración → Médicos → **Restablecer credenciales**, confirmar contraseña administrativa y motivo. Se genera otro secreto, se revocan sesiones y entregas anteriores pendientes, y se audita la operación. Entregar el nuevo archivo siguiendo el mismo procedimiento.

Guardar una copia protegida de `.env` junto con la estrategia de respaldo, separada del repositorio. No reemplazar `DOCTOR_CREDENTIAL_KEY` mientras existan entregas pendientes: sin esa clave no se pueden descifrar. Si se pierde, se requiere restablecimiento administrativo individual, no reconstruir cuentas. El respaldo PostgreSQL conserva datos y ciphertext, pero no sustituye la custodia de la clave.

## Migración y conservación

`20261124_medical_registration` depende de `20261123_google_identity`, crea exclusivamente solicitudes y entregas con sus claves foráneas, restricciones e índice. No modifica las filas históricas ni recrea tablas existentes. Las vinculaciones Google antiguas de médicos permanecen almacenadas, pero el servidor rechaza usarlas para autenticar o vincular. Sus sesiones válidas con contraseña se conservan. Mantener el volumen externo `vitalsync_vitalsync_data`; nunca ejecutar `down -v`.

## Demostración y pruebas

```powershell
.\infrastructure\Test-Backend.ps1
npm --prefix frontend test
npm --prefix frontend run build
.\infrastructure\test-livekit.ps1 -GoogleProviderFixture
```

Las pruebas backend crean bases `vitalsync_test_audit_*`; nunca se truncan las tablas principales. El E2E usa servicios temporales del mismo proyecto y cuentas ficticias: prueba los usuarios existentes y el ciclo solicitud → aprobación administrativa → entrega privada autenticada → login médico → paciente nuevo → reserva virtual → conexión simultánea → reingreso → finalización → historiales.

Google E2E utiliza un SDK controlado y tokens RSA firmados con certificados efímeros; no es una prueba de consentimiento con una cuenta Google real. LiveKit sí transporta pistas entre dos navegadores, pero usa cámara y micrófono sintéticos. La webcam física y la ventana real de Google requieren verificación manual en Chrome.

Para una demostración manual, registrar un paciente ficticio y una solicitud médica ficticia, aprobarla desde la cuenta administrativa existente y emitir la entrega privada. Publicar disponibilidad del nuevo médico, activar un plan compatible al paciente y reservar una cita virtual. Abrir paciente y médico en perfiles Chrome separados; permitir cámara/micrófono, entrar dentro de la ventana autorizada y finalizar desde el médico. Comprobar ambos historiales. No usar documentos ni historias clínicas reales en esta demostración académica.
