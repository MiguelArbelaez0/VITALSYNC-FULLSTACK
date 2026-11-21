import { useEffect, useState, type FormEvent } from "react";
import { api, post } from "../../services/api";
import { Button } from "../../components/ui/button";
import { ErrorBox } from "../../components/common";

type Result = {
  status: "PENDING" | "APPROVED" | "REJECTED";
  institutional_email: string;
  receipt?: string;
  message: string;
  review_reason?: string;
};
const statuses = {
  PENDING: "Solicitud pendiente",
  APPROVED: "Solicitud aprobada",
  REJECTED: "Solicitud rechazada",
};
export function MedicalRegistration() {
  const [names, setNames] = useState({ given_names: "", surnames: "" });
  const [email, setEmail] = useState("");
  const [specialties, setSpecialties] = useState<
    { id: number; name: string }[]
  >([]);
  const [error, setError] = useState<unknown>(null);
  const [previewError, setPreviewError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [receipt, setReceipt] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    api<{ specialties: typeof specialties }>(
      "/auth/medical-registration/options",
    )
      .then((data) => {
        if (active) {
          setSpecialties(data.specialties);
          setError(null);
        }
      })
      .catch((e) => {
        if (active) setError(e);
      });
    return () => {
      active = false;
    };
  }, [reload]);
  useEffect(() => {
    let active = true;
    setEmail("");
    setPreviewError(null);
    if (names.given_names.trim().length < 2 || names.surnames.trim().length < 2)
      return;
    const timer = setTimeout(() => {
      post<{ institutional_email: string }>(
        "/auth/doctor-applications/preview",
        names,
      )
        .then((data) => {
          if (active) setEmail(data.institutional_email);
        })
        .catch((e) => {
          if (active) setPreviewError(e);
        });
    }, 350);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [names]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    try {
      const response = await post<Result>("/auth/doctor-applications", {
        ...names,
        document_type: "CC",
        document_number: data.get("document_number"),
        specialty_id: Number(data.get("specialty_id")),
        professional_number: data.get("professional_number"),
        contact_email: data.get("contact_email") || null,
        phone: data.get("phone"),
        bio: data.get("bio"),
        privacy_accepted: data.get("privacy_accepted") === "on",
      });
      setResult(response);
      setReceipt(response.receipt ?? "");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="notice">
        <strong>Registro profesional con aprobación</strong>
        <p>
          La revisión de esta demostración es académica y simulada; no verifica
          habilitación ante registros oficiales. Solo después de aprobarte se
          crea tu acceso médico y se entrega una contraseña individual de forma
          privada.
        </p>
      </div>
      {!result && (
        <form className="registration-form" onSubmit={submit}>
          <div className="auth-field-grid">
            <label>
              Nombres
              <input
                required
                minLength={2}
                maxLength={60}
                autoComplete="given-name"
                value={names.given_names}
                onChange={(e) =>
                  setNames({ ...names, given_names: e.target.value })
                }
              />
            </label>
            <label>
              Apellidos
              <input
                required
                minLength={2}
                maxLength={60}
                autoComplete="family-name"
                value={names.surnames}
                onChange={(e) =>
                  setNames({ ...names, surnames: e.target.value })
                }
              />
            </label>
          </div>
          <label>
            Correo institucional propuesto
            <input
              readOnly
              value={email}
              placeholder="Completa tus nombres y apellidos"
            />
          </label>
          <small>
            Se reserva al enviar la solicitud; puede variar si otra persona lo
            reserva antes. El dominio .demo es ficticio y no recibe correos.
          </small>
          <ErrorBox error={previewError} />
          <div className="auth-field-grid">
            <label>
              Tipo de documento
              <select defaultValue="CC">
                <option value="CC">CC — Cédula de ciudadanía</option>
              </select>
            </label>
            <label>
              Número de cédula
              <input
                name="document_number"
                required
                pattern="[0-9]{6,10}"
                maxLength={10}
                inputMode="numeric"
                title="De 6 a 10 dígitos, sin puntos"
              />
            </label>
          </div>
          <label>
            Especialidad
            <select name="specialty_id" required defaultValue="">
              <option value="" disabled>
                Selecciona una especialidad
              </option>
              {specialties.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {!specialties.length && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setReload(reload + 1)}
            >
              Recargar especialidades
            </Button>
          )}
          <label>
            Registro profesional
            <input
              name="professional_number"
              required
              minLength={4}
              maxLength={50}
              pattern="[A-Za-z0-9./\-]+"
            />
          </label>
          <label>
            Correo personal de contacto (opcional)
            <input name="contact_email" type="email" autoComplete="email" />
            <small>Este correo no se utiliza para iniciar sesión.</small>
          </label>
          <label>
            Teléfono de contacto
            <input
              name="phone"
              type="tel"
              required
              minLength={7}
              maxLength={30}
              autoComplete="tel"
            />
          </label>
          <label>
            Perfil profesional
            <textarea
              name="bio"
              required
              minLength={20}
              maxLength={2000}
              rows={4}
            />
          </label>
          <div className="privacy-notice">
            <p>
              Usamos los datos de identidad, contacto y formación para revisar
              la solicitud y crear tu cuenta si es aprobada. No introduzcas
              información de pacientes.
            </p>
            <label className="consent-field">
              <input type="checkbox" name="privacy_accepted" required />
              <span>
                Acepto el tratamiento de estos datos para revisar mi solicitud
                profesional.
              </span>
            </label>
          </div>
          <Button disabled={busy || !specialties.length}>
            {busy ? "Enviando…" : "Solicitar cuenta médica"}
          </Button>
        </form>
      )}
      {result && (
        <section className="notice" role="status">
          <h2>{statuses[result.status]}</h2>
          <p>{result.message}</p>
          <p>
            <strong>{result.institutional_email}</strong>
          </p>
          {result.review_reason && <p>Motivo: {result.review_reason}</p>}
          <p>
            Conserva el código de seguimiento en un lugar privado. No es una
            contraseña ni otorga acceso clínico.
          </p>
        </section>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            setResult(
              await post<Result>("/auth/doctor-applications/status", {
                receipt,
              }),
            );
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Código privado de seguimiento
          <input
            value={receipt}
            onChange={(e) => setReceipt(e.target.value)}
            minLength={32}
            maxLength={128}
            required
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <Button variant="outline" disabled={busy}>
          Consultar estado de solicitud
        </Button>
      </form>
      <ErrorBox error={error} />
    </>
  );
}
