import { useState } from "react";
import { KeyRound } from "lucide-react";
import { post } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Button } from "../../components/ui/button";
import { ErrorBox } from "../../components/common";

export function PatientPasswordForm() {
  const { refresh } = useAuth();
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
      await post("/auth/password", {
        current_password: current,
        new_password: next,
        confirm_password: confirmation,
      });
      setCurrent("");
      setNext("");
      setConfirmation("");
      setSaved(true);
      await refresh();
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
        Seguridad de tu cuenta
      </h2>
      <p>
        Puedes cambiar tu contraseña. Las demás sesiones de tu cuenta se
        cerrarán.
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
