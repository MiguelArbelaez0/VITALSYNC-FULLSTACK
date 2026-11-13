import { useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../../services/api";
import { Button } from "../../components/ui/button";
import { Logo, ErrorBox } from "../../components/common";
import "./admin.css";
export default function Recover() {
  const [token, setToken] = useState(() => {
    const hash = new URLSearchParams(location.hash.slice(1));
    const value = hash.get("token") ?? "";
    if (value) history.replaceState(null, "", location.pathname);
    return value;
  });
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/auth/recover", {
        token,
        new_password: password,
        confirm_password: confirmation,
      });
      setToken("");
      setPassword("");
      setConfirmation("");
      setDone(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="admin-recovery">
      <Logo />
      <section className="panel">
        <h1>Recuperar mi acceso</h1>
        <p>
          Usa el enlace privado recibido del operador. Es válido por 24 horas y
          se consume una sola vez. Las demás sesiones se cerrarán al guardar tu
          contraseña.
        </p>
        {done ? (
          <div role="status">
            <p>Contraseña guardada. Ya puedes iniciar sesión.</p>
            <Button asChild>
              <Link to="/login">Ir a iniciar sesión</Link>
            </Button>
          </div>
        ) : (
          <form onSubmit={submit}>
            <label>
              Código privado de recuperación
              <input
                type="password"
                autoComplete="off"
                required
                minLength={40}
                maxLength={128}
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </label>
            <label>
              Nueva contraseña
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              Confirmar nueva contraseña
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
              />
            </label>
            <small>
              Al menos 12 caracteres, mayúscula, minúscula y número.
            </small>
            <ErrorBox error={error} />
            <Button
              disabled={
                busy ||
                password !== confirmation ||
                !/[A-Z]/.test(password) ||
                !/[a-z]/.test(password) ||
                !/[0-9]/.test(password)
              }
            >
              {busy ? "Guardando…" : "Guardar mi contraseña"}
            </Button>
          </form>
        )}
      </section>
    </main>
  );
}
