import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound, ShieldCheck } from "lucide-react";
import { post } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Button } from "../../components/ui/button";
import { ErrorBox, Logo } from "../../components/common";

export function DoctorPasswordForm({ initial = false }: { initial?: boolean }) {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    setSaved(false);
    try {
      await post("/doctor/password", {
        current_password: current,
        new_password: next,
        confirm_password: confirmation,
      });
      setCurrent("");
      setNext("");
      setConfirmation("");
      setSaved(true);
      await refresh();
      if (initial) navigate("/doctor", { replace: true });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const valid =
    next.length >= 12 &&
    /[A-Z]/.test(next) &&
    /[a-z]/.test(next) &&
    /[0-9]/.test(next) &&
    next === confirmation;
  return (
    <form className="medical-password-form" onSubmit={submit}>
      <h2>
        <KeyRound size={22} />
        {initial ? "Elige tu contraseña individual" : "Seguridad de tu cuenta"}
      </h2>
      <p>
        {initial
          ? "Tu acceso inicial es temporal. Elige una contraseña propia antes de consultar la agenda o información clínica."
          : "Puedes cambiar tu contraseña. Las demás sesiones de tu cuenta se cerrarán."}
      </p>
      <label>
        Contraseña actual o inicial
        <input
          type="password"
          autoComplete="current-password"
          required
          minLength={8}
          maxLength={128}
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
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
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </label>
      <small>Usa al menos 12 caracteres, mayúscula, minúscula y número.</small>
      <label>
        Repetir nueva contraseña
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
      <ErrorBox error={error} />
      {saved && <p role="status">Contraseña actualizada correctamente.</p>}
      <Button disabled={busy || !valid || !current}>
        {busy ? "Guardando…" : "Guardar contraseña"}
      </Button>
    </form>
  );
}
export function DoctorPasswordSetup() {
  const { user, logout } = useAuth();
  const [error, setError] = useState<unknown>(null);
  return (
    <main className="doctor-initial-access">
      <Logo />
      <section className="panel">
        <span className="eyebrow">
          <ShieldCheck size={18} /> PRIMER ACCESO MÉDICO
        </span>
        <h1>{user?.name}</h1>
        <DoctorPasswordForm initial />
        <ErrorBox error={error} />
        <Button variant="outline" onClick={() => void logout().catch(setError)}>
          Cerrar sesión
        </Button>
      </section>
    </main>
  );
}
