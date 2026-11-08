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
  phone: z
    .string()
    .max(30)
    .regex(/^[+\d\s()\-]*$/, "Ingresa un teléfono válido"),
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
    defaultValues: { name: user?.name ?? "", phone: user?.phone ?? "" },
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
        <form
          onSubmit={handleSubmit(async (values) => {
            setError(null);
            setSaved(false);
            try {
              await api("/auth/me", {
                method: "PATCH",
                body: JSON.stringify(values),
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
            {errors.name && (
              <small className="field-error">{errors.name.message}</small>
            )}
          </label>
          <label>
            Teléfono de contacto
            <input {...register("phone")} type="tel" />
            {errors.phone && (
              <small className="field-error">{errors.phone.message}</small>
            )}
          </label>
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
