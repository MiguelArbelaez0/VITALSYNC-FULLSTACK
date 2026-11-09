import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import { ErrorBox, PageTitle } from "../../components/common";
import { Button } from "../../components/ui/button";

const schema = z.object({
  name: z.string().trim().min(2, "Ingresa tu nombre").max(120),
  phone: z.string().max(30).regex(/^[+\d\s()\-]*$/, "Ingresa un teléfono válido"),
  document_type: z.string().optional(),
  document_number: z.string().optional(),
  privacy_accepted: z.boolean().optional(),
}).superRefine((value, context) => {
  if (value.document_number && !/^[0-9]{6,10}$/.test(value.document_number)) {
    context.addIssue({ code: "custom", path: ["document_number"], message: "Escribe de 6 a 10 dígitos, sin espacios ni puntos" });
  }
  if (value.document_number && value.privacy_accepted !== true) {
    context.addIssue({ code: "custom", path: ["privacy_accepted"], message: "Acepta el aviso de privacidad para registrar tu documento" });
  }
});

export function Profile() {
  const { user, refresh } = useAuth();
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: user?.name ?? "",
      phone: user?.phone ?? "",
      document_type: "CC",
      privacy_accepted: false,
    },
  });
  return (
    <>
      <PageTitle
        title="Tu información, al día"
        description="Una atención cercana comienza por conocerte."
      />
      <section className="panel profile-panel">
        <span className="avatar xlarge">{user?.name[0]}</span>
        <h2>Mi perfil</h2>
        <p>Cuenta de paciente · {user?.email}</p>
        {user?.has_document ? (
          <div className="notice profile-document" aria-label="Documento registrado">
            <strong>Documento registrado</strong>
            <p>{user.document_type} · {user.document_masked}</p>
            <small>Por seguridad, el número completo no se muestra.</small>
          </div>
        ) : (
          <div className="notice profile-document">
            <strong>Completa tu perfil de identidad</strong>
              <p>Las cuentas existentes pueden añadir su cédula aquí. No necesitas volver a registrarte.</p>
              <p>La usamos para crear y proteger tu cuenta, gestionar tu plan y coordinar la atención que solicites. VITALSYNC no consulta registros oficiales ni verifica identidad. Aviso de privacidad, versión 2026-11-v1.</p>
          </div>
        )}
        <form
          onSubmit={handleSubmit(async (values) => {
            setError(null);
            setSaved(false);
            try {
              const payload = {
                name: values.name,
                phone: values.phone,
                ...(values.document_number
                  ? {
                      document_type: values.document_type,
                      document_number: values.document_number,
                      privacy_accepted: values.privacy_accepted,
                    }
                  : {}),
              };
              await api("/auth/me", {
                method: "PATCH",
                body: JSON.stringify(payload),
              });
              await refresh();
              setSaved(true);
            } catch (e) {
              setError(e);
            }
          })}
        >
          <label>
            Nombre completo
            <input {...register("name")} />
            {errors.name && <small className="field-error" role="alert">{errors.name.message}</small>}
          </label>
          <label>
            Teléfono de contacto
            <input {...register("phone")} type="tel" />
            {errors.phone && <small className="field-error" role="alert">{errors.phone.message}</small>}
          </label>
          {!user?.has_document && (
            <>
              <label>
                Tipo de documento
                <select {...register("document_type", { value: "CC" })}>
                  <option value="CC">CC — Cédula de ciudadanía</option>
                </select>
              </label>
              <label>
                Número de cédula
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={10}
                  placeholder="De 6 a 10 dígitos"
                  {...register("document_number")}
                  aria-invalid={Boolean(errors.document_number)}
                />
                {errors.document_number && <small className="field-error" role="alert">{errors.document_number.message}</small>}
              </label>
              <label className="consent-field">
                <input type="checkbox" {...register("privacy_accepted")} aria-invalid={Boolean(errors.privacy_accepted)} />
                <span>He leído el aviso y acepto el tratamiento de estos datos para los fines descritos.</span>
              </label>
              {errors.privacy_accepted && <small className="field-error" role="alert">{errors.privacy_accepted.message}</small>}
            </>
          )}
          <ErrorBox error={error} />
          {saved && (
            <div className="alert success" role="status">
              Perfil actualizado correctamente.
            </div>
          )}
          <Button disabled={isSubmitting}>
            {isSubmitting ? "Guardando…" : "Guardar cambios"}
          </Button>
        </form>
      </section>
    </>
  );
}
