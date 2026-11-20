# Google Identity Services · VITALSYNC v1.1

## Configuración de Google Cloud

1. En Google Cloud / Google Auth Platform configura el nombre VITALSYNC, correo de soporte, audiencia y pantalla de consentimiento. Durante pruebas agrega las cuentas autorizadas como usuarios de prueba cuando corresponda.
2. Crea un cliente OAuth de tipo **Aplicación web**. En orígenes JavaScript autorizados agrega `http://localhost:5188` y `http://127.0.0.1:5188`. Para un despliegue público agrega su origen HTTPS exacto.
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
