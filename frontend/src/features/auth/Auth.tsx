import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Check, HeartPulse } from "lucide-react";
import { post } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Button } from "../../components/ui/button";
import { ErrorBox, Logo } from "../../components/common";
export const authSchema = z.object({
  email: z.email("Ingresa un correo válido"),
  password: z.string().min(10, "Usa al menos 10 caracteres"),
  name: z.string().optional(),
});
type Values = z.infer<typeof authSchema>;
export function Auth({ register = false }: { register?: boolean }) {
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState<unknown>(null);
  const schema = register
    ? authSchema.refine((v) => (v.name?.trim().length ?? 0) >= 2, {
        message: "Ingresa tu nombre completo",
        path: ["name"],
      })
    : authSchema.extend({
        password: z.string().min(8, "Ingresa tu contraseña"),
      });
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });
  async function submit(v: Values) {
    setError(null);
    try {
      await post(
        "/auth/" + (register ? "register" : "login"),
        register ? v : { email: v.email, password: v.password },
      );
      await refresh();
      navigate("/portal");
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className="auth-page">
      <div className="auth-story">
        <Logo />
        <div>
          <span className="eyebrow">CERCA DE TI, EN CADA ETAPA</span>
          <h1>
            Tu salud merece
            <br />
            estar en buenas manos.
          </h1>
          <p>
            Conecta con especialistas y encuentra el tiempo para lo que más
            importa: tú.
          </p>
          <div className="auth-benefits">
            {[
              "Especialistas en un solo lugar",
              "Tu agenda médica, bajo control",
              "Planes que se adaptan a ti",
            ].map((t) => (
              <span key={t}>
                <Check size={18} />
                {t}
              </span>
            ))}
          </div>
        </div>
        <small>VITALSYNC · Plataforma académica de demostración</small>
        <HeartPulse className="auth-watermark" />
      </div>
      <div className="auth-form">
        <Link className="text-link" to="/">
          <ArrowLeft size={16} />
          Volver al inicio
        </Link>
        <div className="form-content">
          <span className="eyebrow">TU ESPACIO DE BIENESTAR</span>
          <h1>
            {register ? "Comienza a cuidarte" : "Qué bueno verte de nuevo"}
          </h1>
          <p>
            {register
              ? "Crea tu cuenta de paciente en unos minutos."
              : "Ingresa a tu cuenta y continúa cuidando de ti."}
          </p>
          <form onSubmit={handleSubmit(submit)} noValidate>
            {register && (
              <label>
                Nombre completo
                <input
                  autoComplete="name"
                  {...field("name")}
                  placeholder="Tu nombre y apellido"
                />
                {errors.name && (
                  <small className="field-error">{errors.name.message}</small>
                )}
              </label>
            )}
            <label>
              Correo electrónico
              <input
                type="email"
                autoComplete="email"
                {...field("email")}
                placeholder="tu@correo.com"
              />
              {errors.email && (
                <small className="field-error">{errors.email.message}</small>
              )}
            </label>
            <label>
              Contraseña
              <input
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                {...field("password")}
                placeholder={
                  register ? "Al menos 10 caracteres" : "Tu contraseña"
                }
              />
              {errors.password && (
                <small className="field-error">{errors.password.message}</small>
              )}
            </label>
            <ErrorBox error={error} />
            <Button disabled={isSubmitting} className="full">
              {isSubmitting
                ? "Un momento…"
                : register
                  ? "Crear mi cuenta"
                  : "Iniciar sesión"}
            </Button>
          </form>
          <p className="auth-switch">
            {register ? "¿Ya tienes cuenta?" : "¿Primera vez por aquí?"}{" "}
            <Link to={register ? "/login" : "/register"}>
              {register ? "Inicia sesión" : "Crea tu cuenta"}
            </Link>
          </p>
          <div className="notice">
            <strong>Demostración local</strong>
            <p>
              Usa paciente@vitalsync.demo con la contraseña Paciente2026! o crea
              tu propia cuenta. Todos los pagos son simulados.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
