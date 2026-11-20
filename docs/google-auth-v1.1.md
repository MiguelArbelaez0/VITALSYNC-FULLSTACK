# Google Identity Services · VITALSYNC v1.1

## Configuración de Google Cloud

1. En Google Cloud / Google Auth Platform configura el nombre VITALSYNC, correo de soporte, audiencia y pantalla de consentimiento. Durante pruebas agrega las cuentas autorizadas como usuarios de prueba cuando corresponda.
2. Crea un cliente OAuth de tipo **Aplicación web**. Para desarrollo, Google exige registrar ambos orígenes `http://localhost` y `http://localhost:5188`. Agrega también `http://127.0.0.1:5188` si usarás esa dirección. Para un despliegue público agrega su origen HTTPS exacto. Guarda los cambios y espera su propagación; no agregues rutas como `/login` a los orígenes.
3. Copia el Client ID público a ambas variables de `.env`:

```dotenv
GOOGLE_CLIENT_ID=TU_CLIENT_ID.apps.googleusercontent.com
VITE_GOOGLE_CLIENT_ID=TU_CLIENT_ID.apps.googleusercontent.com
```

4. Ejecuta `docker compose -p vitalsync --profile video up -d --build --wait`. La variable Vite se incorpora durante la compilación; reiniciar un contenedor sin recompilar no la cambia.
5. Abre `http://localhost:5188/login`. El botón oficial se carga desde `https://accounts.google.com/gsi/client`. No se necesita Client Secret: se utiliza popup/callback de GIS e intercambio de ID token con FastAPI, sin código de autorización ni redirect URI OAuth.

Sin Client ID, el login tradicional sigue disponible y Google se presenta deshabilitado con una explicación. Los IDs del navegador y backend deben coincidir. No se usa un ID ficticio en el despliegue principal.

Referencias oficiales: [configurar el cliente](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid), [botón oficial](https://developers.google.com/identity/gsi/web/guides/display-button), [verificación de ID tokens](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token), [nonce y callback](https://developers.google.com/identity/gsi/web/reference/js-reference).

## Flujos

El login es compartido. Google entrega una identidad; PostgreSQL determina el usuario y rol. La respuesta backend contiene `/portal` o `/doctor`. No se conceden permisos por correo, dominio ni datos enviados por React. Las cuentas administrativas continúan con contraseña y no admiten vinculación Google.

- **Paciente nuevo:** Google verifica nombre/correo; el formulario solicita CC colombiana de 6–10 dígitos, teléfono y consentimiento. Se aplican las validaciones tradicionales y restricciones únicas PostgreSQL. Se crea únicamente un paciente con identidad Google vinculada. La cuenta recibe un hash de contraseña aleatoria no conocida; puede establecer una contraseña por la recuperación privada existente, sin inventar una contraseña compartida.
- **Cuenta existente sin vincular:** una coincidencia de correo produce una indicación de iniciar sesión con contraseña y vincular desde el perfil. No se crea una cuenta duplicada ni se fusiona por correo.
- **Vinculación de paciente/médico:** desde Mi perfil, confirmar la contraseña actual y luego la identidad Google. La solicitud dura cinco minutos y está vinculada al usuario y a la sesión exacta que confirmó la contraseña. El correo institucional, hash de contraseña y datos profesionales no cambian.
- **Acceso vinculado:** se busca el `sub` único y se emite la misma cookie de sesión local que usa el login tradicional. Un médico debe conservar perfil profesional activo; un usuario deshabilitado no accede.
- **Desvinculación propia:** requiere contraseña; revoca Google, solicitudes pendientes y demás sesiones. Para cuentas creadas solo con Google, establecer primero una contraseña mediante recuperación.
- **Revocación administrativa:** en Pacientes o Médicos, `Revocar Google` requiere permiso `accounts`, contraseña actual del administrador y motivo. Revoca la identidad, solicitudes pendientes y todas las sesiones del usuario; queda registrada en auditoría. No reemplaza la contraseña del titular.

## Seguridad y persistencia

`google-auth` verifica la firma RSA contra certificados oficiales de Google, audiencia, emisor y tiempo de validez; el servidor exige además correo verificado, `sub` válido y nonce exacto. El token Google no se persiste ni registra. No se guardan access tokens, refresh tokens ni Client Secret.

El callback JavaScript usa una protección propia de navegador: Origin obligatorio en la lista autorizada, nonce de alta entropía, cookie HttpOnly/SameSite Strict y comparación con el desafío del cuerpo. El desafío se persiste como hash, caduca a los cinco minutos y se consume con bloqueo transaccional. La fase de registro conserva solo nombre, correo y sub ya verificados; no acepta esos valores desde el formulario. La cookie de flujo tiene path `/api/auth/google`. La sesión final mantiene HttpOnly, SameSite Strict y `COOKIE_SECURE` de la plataforma.

La migración `20261123_google_identity`, descendiente de `20261122_demo_instant_calls`, agrega `google_identities` y `google_challenges`. `sub` es clave primaria y `user_id` es único. No modifica usuarios, contraseñas, pacientes, citas ni permisos. Se mantiene una única cabeza Alembic.

## Endpoints

| Ruta | Función |
| --- | --- |
| POST `/api/auth/google/challenge` | Preparar LOGIN o LINK; LINK exige sesión y contraseña |
| POST `/api/auth/google/exchange` | Verificar ID token y nonce; autenticar, vincular o preparar registro |
| POST `/api/auth/google/register` | Completar el paciente nuevo desde la identidad verificada |
| GET `/api/auth/google/identity` | Consultar únicamente la propia vinculación |
| POST `/api/auth/google/unlink` | Desvinculación con contraseña y cierre de otras sesiones |
| POST `/api/admin/users/{id}/google-revoke` | Revocar con permiso accounts, contraseña y motivo |

## Pruebas reproducibles

```powershell
.\infrastructure\Test-Backend.ps1
cd frontend
npm test
npm run build
cd ..
.\infrastructure\test-livekit.ps1 -GoogleProviderFixture
```

Backend usa tokens RSA firmados con claves efímeras de fixture, reemplazando solo el transporte de certificados: el verificador real sigue comprobando firma y claims. Incluye tokens válidos/inválidos/expirados, audiencia, emisor, nonce, correo verificado, CSRF, registro, vinculación segura, sub duplicado, roles, permisos y revocación.

El E2E con `-GoogleProviderFixture` utiliza una base `vitalsync_test_audit_*` y otro frontend/backend/LiveKit. Inyecta un SDK simulado en los navegadores, emite tokens RSA con una clave temporal exportada únicamente al archivo privado del fixture y usa el servidor `tests/google_e2e_app.py`. Este servidor se niega a iniciar fuera de una base audit explícita. No se incluye esa configuración en el despliegue principal.

El flujo vincula paciente y médico desde sus perfiles tras confirmar contraseña, cierra sus sesiones, entra con Google a cada portal, conecta ambos a LiveKit y verifica salida temporal, reconexión, finalización, historial y proyección administrativa. Los medios son sintéticos; no se verifica audio audible real. La simulación no demuestra que Google Cloud esté configurado ni sustituye una prueba con cuentas Google reales.

## Validación manual pendiente con Google real

Con un Client ID autorizado y cuentas reales, comprobar popup, consentimiento, selección de cuenta, rechazo de permisos, usuario nuevo, coincidencia de correo sin vincular, vinculación de médico, login posterior, revocación y sesión en móvil. Validar HTTPS y cookies seguras en el dominio final. No se afirma que estos pasos reales se hayan ejecutado sin esa evidencia.

LiveKit conserva los mismos endpoints, ventanas horarias, permisos por rol y ciclo de atención. El administrador no recibe acceso a la sala ni a historias clínicas.

## Comprobación local del 20 de noviembre de 2026

- Backend: **182 aprobadas**. Frontend: **50 aprobadas**. Compilación React de producción: aprobada; conserva el aviso de tamaño de algunos chunks.
- E2E con proveedor Google controlado: aprobado. Vinculación de paciente y médico con contraseña, login Google según rol, rechazo del médico sin vincular, conexión LiveKit, salida/reingreso y finalización con historial.
- Docker actualizado: `vitalsync` con `db`, `backend`, `frontend` y `livekit`. Se conserva `vitalsync_vitalsync_data`.
- Alembic: única cabeza `20261123_google_identity`, aplicada a la base principal.
- Conservación de datos: los contenidos completos de `users`, `patients`, `appointments` y `payments` producen los mismos hashes agregados antes/después de migrar: **61 usuarios, 55 pacientes, 63 citas y 147 pagos**. No se reemplazaron contraseñas ni registros existentes.
- Respaldo anterior a migrar: `Desktop/VITALSYNC-RESPALDOS/vitalsync-before-google-20261120-012123.dump`, índice comprobado con `pg_restore -l`. SHA-256: `6C05B988D0DFF90A92E26358294781586B3249F4876B784AD726348A100D8593`.
- El Client ID proporcionado por el titular se configuró en ambas variables de `.env`, que permanece ignorado por Git. El SDK oficial y el botón cargan; la prueba real detectó **“The given origin is not allowed for the given client ID”** en escritorio y móvil. La consola Google Cloud muestra únicamente `http://localhost:5188` en el formulario, y el titular confirma haberlo guardado. Se solicitó agregar también `http://localhost`, como indica la guía oficial, y esperar propagación. La autenticación real permanece pendiente de esa autorización y de la selección manual de cuenta.

Para repetir únicamente la prueba del botón oficial (no autentica al usuario):

```powershell
cd frontend
$env:E2E_GOOGLE_OFFICIAL = 'true'
npm run test:e2e -- --grep 'Google official GIS button' --output test-results-google
Remove-Item Env:E2E_GOOGLE_OFFICIAL
```

La política CSP permite los recursos oficiales GIS. El test admite que Google renderice el botón accesible en el documento principal o gestione internamente un iframe; no depende del contenido del iframe. Las pruebas de proveedor controlado y Google oficial usan carpetas de salida distintas cuando se ejecutan por separado.

Capturas del SDK oficial cargado (no demuestran autenticación real): [escritorio](screenshots/google-login-desktop.png), [móvil](screenshots/google-login-mobile.png).

## Cómo probar paciente y médico

Abre `http://localhost:5188/login` y utiliza cuentas Google distintas para paciente y médico: cada identidad `sub` se puede vincular a un solo usuario VITALSYNC.

1. **Paciente existente:** inicia con su correo y contraseña habituales; abre `http://localhost:5188/portal/profile`. En Acceso con Google confirma la contraseña y pulsa el botón Google. Selecciona la cuenta personal y espera la confirmación de vinculación. Cierra sesión; vuelve al login, pulsa Continuar con Google y selecciona esa misma cuenta. Debe abrir `/portal`.
2. **Paciente nuevo:** desde el login pulsa Continuar con Google con una cuenta aún no vinculada ni coincidente con un usuario existente. Completa CC, teléfono y privacidad. Se crea únicamente una cuenta de paciente y abre `/portal`.
3. **Médico:** inicia con su correo institucional y contraseña actuales; abre `http://localhost:5188/doctor/profile`. Confirma la contraseña en Acceso con Google y selecciona una cuenta Google real que no esté vinculada a otro usuario. Al confirmar, cierra sesión y entra desde el login con esa misma cuenta Google. Debe abrir `/doctor` conservando especialidad, citas y permisos.

Si el correo Google coincide con una cuenta existente, hay que vincular desde la sesión con contraseña; el sistema no fusiona por correo. Una cuenta Google sin vincular jamás adquiere el rol médico. El administrador conserva su inicio con contraseña.
