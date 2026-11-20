import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, post } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Button } from "../../components/ui/button";
import { ErrorBox } from "../../components/common";
import "./google-auth.css";

const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";
type Challenge = { challenge: string; nonce: string; client_id: string };
type Outcome = { registration_required?: boolean; name?: string; email?: string; redirect_to?: string; linked?: boolean };
type GoogleSDK = { accounts: { id: {
  initialize: (options: { client_id: string; nonce: string; auto_select: boolean; callback: (result: { credential: string }) => void }) => void;
  renderButton: (element: HTMLElement, options: Record<string, unknown>) => void;
} } };
declare global { interface Window { google?: GoogleSDK } }
let sdkPromise: Promise<void> | undefined;
function loadSDK() {
  if (window.google) return Promise.resolve();
  if (!sdkPromise) sdkPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.referrerPolicy = "strict-origin-when-cross-origin";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => { sdkPromise = undefined; script.remove(); reject(new Error("No pudimos cargar Google. Comprueba tu conexión e intenta de nuevo.")); };
    document.head.appendChild(script);
  });
  return sdkPromise;
}

export function GoogleSignIn({ password, linking = false, onLinked }: { password?: string; linking?: boolean; onLinked?: () => void }) {
  const element = useRef<HTMLDivElement>(null);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [registration, setRegistration] = useState<Outcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [retry, setRetry] = useState(0);
  const { refresh } = useAuth();
  const navigate = useNavigate();
  async function complete(outcome: Outcome) {
    if (outcome.linked) { onLinked?.(); return; }
    if (!outcome.redirect_to || !["/portal", "/doctor"].includes(outcome.redirect_to)) throw new Error("No se pudo determinar tu portal.");
    await refresh();
    navigate(outcome.redirect_to);
  }
  useEffect(() => {
    if (!clientId) return;
    let active = true;
    setError(null); setBusy(true);
    void (async () => {
      try {
        const issued = await post<Challenge>("/auth/google/challenge", { purpose: linking ? "LINK" : "LOGIN", ...(linking ? { current_password: password } : {}) });
        await loadSDK();
        if (!active || !element.current) return;
        if (issued.client_id !== clientId) throw new Error("La configuración de Google no coincide. Contacta a VITALSYNC.");
        setChallenge(issued);
        window.google!.accounts.id.initialize({ client_id: clientId, nonce: issued.nonce, auto_select: false,
          callback: (result) => {
            setBusy(true); setError(null);
            void post<Outcome>("/auth/google/exchange", { challenge: issued.challenge, credential: result.credential })
              .then(async (outcome) => { if (!active) return; if (outcome.registration_required) setRegistration(outcome); else await complete(outcome); })
              .catch((cause) => { if (active) setError(cause); })
              .finally(() => { if (active) setBusy(false); });
          } });
        element.current.replaceChildren();
        window.google!.accounts.id.renderButton(element.current, { type: "standard", theme: "outline", size: "large", text: "continue_with", shape: "rectangular", locale: "es", width: Math.min(element.current.clientWidth || 300, 400) });
      } catch (cause) { if (active) setError(cause); }
      finally { if (active) setBusy(false); }
    })();
    return () => { active = false; };
  }, [linking, password, retry]);

  if (!clientId) return <div className="google-auth"><Button type="button" variant="outline" disabled>Continuar con Google</Button><p>Google estará disponible cuando se configure el acceso de la aplicación.</p></div>;
  return <section className="google-auth" aria-label={linking ? "Confirmar vinculación con Google" : "Continuar con Google"}>
    {!registration && <div ref={element} className={busy ? "google-button is-busy" : "google-button"} aria-busy={busy} />}
    {busy && <p role="status">Verificando acceso con Google…</p>}
    {registration && <form className="google-registration" onSubmit={(event) => {
      event.preventDefault(); if (busy || !challenge) return;
      const data = new FormData(event.currentTarget);
      setBusy(true); setError(null);
      void post<Outcome>("/auth/google/register", { challenge: challenge.challenge, document_number: data.get("document_number"), phone: data.get("phone"), privacy_accepted: data.get("privacy") === "on" })
        .then(complete).catch(setError).finally(() => setBusy(false));
    }}>
      <h2>Completa tu registro de paciente</h2><p>{registration.name} · {registration.email}</p>
      <label>Cédula colombiana (CC)<input name="document_number" required pattern="[0-9]{6,10}" inputMode="numeric" maxLength={10} autoComplete="off" /></label>
      <label>Teléfono<input name="phone" required type="tel" maxLength={30} autoComplete="tel" /></label>
      <label className="checkbox-label"><input type="checkbox" name="privacy" required />Acepto el aviso de privacidad de VITALSYNC para crear y proteger mi cuenta y gestionar mi atención. Versión 2026-11-v1.</label>
      <Button disabled={busy}>{busy ? "Creando cuenta…" : "Crear mi cuenta de paciente"}</Button>
    </form>}
    <ErrorBox error={error} />
    {!!error && <Button type="button" variant="outline" onClick={() => { setRegistration(null); setRetry((value) => value + 1); }}>Reintentar verificación</Button>}
  </section>;
}

export function GoogleAccountLink() {
  const [password, setPassword] = useState("");
  const [confirmedPassword, setConfirmedPassword] = useState<string>();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const q = useQuery({ queryKey: ["google-identity"], queryFn: () => api<{ linked: boolean; email: string | null; enabled: boolean }>("/auth/google/identity"), enabled: !!clientId });
  async function unlink() {
    setBusy(true); setError(null);
    try { await post("/auth/google/unlink", { current_password: password, reason: "Desvinculación solicitada por el titular desde su perfil" }); await q.refetch(); setPassword(""); setNotice("Google desvinculado. Las demás sesiones se cerraron."); }
    catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  return <section className="panel google-account"><h2>Acceso con Google</h2>
    <p>Vincula tu cuenta Google para entrar a tu portal. Conservas tu correo institucional o registrado y tu contraseña.</p>
    {!clientId ? <p>La integración Google aún no está configurada.</p> : <>
      {q.isPending ? <p>Cargando vinculación…</p> : <>
        <p>{q.data?.linked ? `Cuenta vinculada: ${q.data.email}` : "Todavía no tienes una cuenta Google vinculada."}</p>
        <form onSubmit={(event) => { event.preventDefault(); setError(null); setNotice(""); if (q.data?.linked) void unlink(); else setConfirmedPassword(password); }}>
          <label>Contraseña actual para confirmar tu identidad<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required minLength={8} maxLength={128} /></label>
          <Button disabled={busy || q.isError}>{q.data?.linked ? "Desvincular Google y cerrar otras sesiones" : "Verificar contraseña y vincular Google"}</Button>
        </form>
        {confirmedPassword && !q.data?.linked && <GoogleSignIn linking password={confirmedPassword} onLinked={() => { setConfirmedPassword(undefined); setPassword(""); setNotice("Cuenta Google vinculada correctamente."); void q.refetch(); }} />}
      </>}
    </>}
    {notice && <p role="status">{notice}</p>}<ErrorBox error={error || q.error} />
  </section>;
}
