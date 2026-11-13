import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Check, Eye, EyeOff, HeartPulse } from "lucide-react";
import type { User } from "../../types";
import { post } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Button } from "../../components/ui/button";
import { ErrorBox, Logo } from "../../components/common";

const authFields = z.object({
  email: z.email("Ingresa un correo válido"),
  password: z.string(),
  given_names: z.string().optional(),
  surnames: z.string().optional(),
  document_type: z.string().optional(),
  document_number: z.string().optional(),
  phone: z.string().optional(),
  confirm_password: z.string().optional(),
  privacy_accepted: z.boolean().optional(),
});

function authSchema(register: boolean) {
  return authFields.superRefine((value, context) => {
    const issue = (path: keyof typeof value, message: string) =>
      context.addIssue({ code: "custom", path: [path], message });
    if (!register) {
      if (value.password.length < 8)
        issue("password", "Ingresa una contraseña de al menos 8 caracteres");
      return;
    }
    if ((value.given_names?.trim().length ?? 0) < 2)
      issue("given_names", "Ingresa tus nombres");
    if ((value.surnames?.trim().length ?? 0) < 2)
      issue("surnames", "Ingresa tus apellidos");
    if (value.document_type !== "CC")
      issue("document_type", "Selecciona un tipo de documento");
    if (!value.document_number || !/^[0-9]{6,10}$/.test(value.document_number))
      issue(
        "document_number",
        "Escribe de 6 a 10 dígitos, sin espacios ni puntos",
      );
    const phoneDigits = (value.phone ?? "").replace(/\D/g, "").length;
    if (
      !value.phone ||
      !/^\+?[\d\s()\-]{7,30}$/.test(value.phone) ||
      phoneDigits < 7 ||
      phoneDigits > 15
    )
      issue("phone", "Ingresa un teléfono válido de 7 a 15 dígitos");
    if (value.password.length < 10)
      issue("password", "Usa al menos 10 caracteres");
    else if (
      !/[a-z]/.test(value.password) ||
      !/[A-Z]/.test(value.password) ||
      !/[0-9]/.test(value.password)
    )
      issue("password", "Usa mayúsculas, minúsculas y al menos un número");
    if (value.confirm_password !== value.password)
      issue("confirm_password", "Las contraseñas no coinciden");
    if (value.privacy_accepted !== true)
      issue("privacy_accepted", "Acepta el aviso de privacidad para continuar");
  });
}

type Values = z.infer<typeof authFields>;

export function Auth({ register = false }: { register?: boolean }) {
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState<unknown>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const {
    register: field,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(authSchema(register)),
    defaultValues: { document_type: "CC", privacy_accepted: false },
  });

  async function submit(values: Values) {
    setError(null);
    try {
      const payload = register
        ? {
            given_names: values.given_names?.trim(),
            surnames: values.surnames?.trim(),
            document_type: values.document_type,
            document_number: values.document_number,
            email: values.email,
            phone: values.phone?.trim(),
            password: values.password,
            privacy_accepted: values.privacy_accepted,
          }
        : { email: values.email, password: values.password };
      const account = await post<User>(
        "/auth/" + (register ? "register" : "login"),
        payload,
      );
      await refresh();
      navigate(
        account.role === "ADMIN"
          ? "/admin"
          : account.role === "DOCTOR"
            ? "/doctor"
            : "/portal",
        { state: { registrationComplete: register } },
      );
    } catch (e) {
      setError(e);
    }
  }

  const errorText = (name: keyof Values) => errors[name]?.message;
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
            {register
              ? "Crea tu cuenta de paciente"
              : "Qué bueno verte de nuevo"}
          </h1>
          <p>
            {register
              ? "Regístrate de forma independiente. No necesitas una cuenta de demostración."
              : "Ingresa a tu cuenta y continúa cuidando de ti."}
          </p>
          <form
            className={register ? "registration-form" : undefined}
            onSubmit={handleSubmit(submit)}
            noValidate
          >
            {register && (
              <>
                <div className="auth-field-grid">
                  <label>
                    Nombres{" "}
                    <span className="required-mark" aria-hidden="true">
                      *
                    </span>
                    <input
                      autoComplete="given-name"
                      {...field("given_names")}
                      aria-invalid={Boolean(errors.given_names)}
                      aria-describedby={
                        errors.given_names ? "given-names-error" : undefined
                      }
                      placeholder="Tus nombres"
                    />
                    {errorText("given_names") && (
                      <small
                        id="given-names-error"
                        className="field-error"
                        role="alert"
                      >
                        {errorText("given_names")}
                      </small>
                    )}
                  </label>
                  <label>
                    Apellidos{" "}
                    <span className="required-mark" aria-hidden="true">
                      *
                    </span>
                    <input
                      autoComplete="family-name"
                      {...field("surnames")}
                      aria-invalid={Boolean(errors.surnames)}
                      aria-describedby={
                        errors.surnames ? "surnames-error" : undefined
                      }
                      placeholder="Tus apellidos"
                    />
                    {errorText("surnames") && (
                      <small
                        id="surnames-error"
                        className="field-error"
                        role="alert"
                      >
                        {errorText("surnames")}
                      </small>
                    )}
                  </label>
                </div>
                <div className="auth-field-grid document-fields">
                  <label>
                    Tipo de documento{" "}
                    <span className="required-mark" aria-hidden="true">
                      *
                    </span>
                    <select
                      {...field("document_type", { value: "CC" })}
                      aria-invalid={Boolean(errors.document_type)}
                    >
                      <option value="CC">CC — Cédula de ciudadanía</option>
                    </select>
                    {errorText("document_type") && (
                      <small className="field-error" role="alert">
                        {errorText("document_type")}
                      </small>
                    )}
                  </label>
                  <label>
                    Número de cédula{" "}
                    <span className="required-mark" aria-hidden="true">
                      *
                    </span>
                    <input
                      type="text"
                      inputMode="numeric"
                      autoComplete="off"
                      maxLength={10}
                      {...field("document_number")}
                      aria-invalid={Boolean(errors.document_number)}
                      aria-describedby={
                        errors.document_number
                          ? "document-number-error"
                          : "document-format-hint"
                      }
                      placeholder="Solo dígitos"
                    />
                    <small id="document-format-hint" className="field-hint">
                      De 6 a 10 dígitos. No se verifica identidad ante entidades
                      oficiales.
                    </small>
                    {errorText("document_number") && (
                      <small
                        id="document-number-error"
                        className="field-error"
                        role="alert"
                      >
                        {errorText("document_number")}
                      </small>
                    )}
                  </label>
                </div>
              </>
            )}
            <label>
              Correo electrónico{" "}
              {register && (
                <span className="required-mark" aria-hidden="true">
                  *
                </span>
              )}
              <input
                type="email"
                autoComplete="email"
                {...field("email")}
                aria-invalid={Boolean(errors.email)}
                placeholder="tu@correo.com"
              />
              {errors.email && (
                <small className="field-error" role="alert">
                  {errors.email.message}
                </small>
              )}
            </label>
            {register && (
              <label>
                Teléfono de contacto{" "}
                <span className="required-mark" aria-hidden="true">
                  *
                </span>
                <input
                  type="tel"
                  autoComplete="tel"
                  {...field("phone")}
                  aria-invalid={Boolean(errors.phone)}
                  placeholder="+57 300 123 4567"
                />
                {errorText("phone") && (
                  <small className="field-error" role="alert">
                    {errorText("phone")}
                  </small>
                )}
              </label>
            )}
            <label htmlFor="auth-password">
              Contraseña{" "}
              {register && (
                <span className="required-mark" aria-hidden="true">
                  *
                </span>
              )}
            </label>
            <div className="auth-password-control">
              <span className="password-field">
                <input
                  id="auth-password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={register ? "new-password" : "current-password"}
                  {...field("password")}
                  aria-label="Contraseña"
                  aria-invalid={Boolean(errors.password)}
                  placeholder={
                    register ? "Al menos 10 caracteres" : "Tu contraseña"
                  }
                />
                <button
                  type="button"
                  className="password-toggle"
                  aria-label={
                    showPassword ? "Ocultar contraseña" : "Mostrar contraseña"
                  }
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
              {register && (
                <small className="field-hint">
                  Usa 10 caracteres o más, con mayúscula, minúscula y número.
                </small>
              )}
              {errors.password && (
                <small className="field-error" role="alert">
                  {errors.password.message}
                </small>
              )}
            </div>
            {register && (
              <>
                <label htmlFor="auth-password-confirmation">
                  Confirmar contraseña{" "}
                  <span className="required-mark" aria-hidden="true">
                    *
                  </span>
                </label>
                <div className="auth-password-control">
                  <span className="password-field">
                    <input
                      id="auth-password-confirmation"
                      type={showConfirmation ? "text" : "password"}
                      autoComplete="new-password"
                      {...field("confirm_password")}
                      aria-label="Confirmar contraseña"
                      aria-invalid={Boolean(errors.confirm_password)}
                      placeholder="Escribe nuevamente tu contraseña"
                    />
                    <button
                      type="button"
                      className="password-toggle"
                      aria-label={
                        showConfirmation
                          ? "Ocultar confirmación"
                          : "Mostrar confirmación"
                      }
                      aria-pressed={showConfirmation}
                      onClick={() => setShowConfirmation(!showConfirmation)}
                    >
                      {showConfirmation ? (
                        <EyeOff size={18} />
                      ) : (
                        <Eye size={18} />
                      )}
                    </button>
                  </span>
                  {errorText("confirm_password") && (
                    <small className="field-error" role="alert">
                      {errorText("confirm_password")}
                    </small>
                  )}
                </div>
                <div className="privacy-notice">
                  <strong>Aviso de privacidad · versión 2026-11-v1</strong>
                  <p>
                    Usamos tu nombre, cédula, correo y teléfono para crear y
                    proteger tu cuenta, gestionar tu plan y coordinar la
                    atención que solicites. Esta demostración no consulta
                    registros oficiales ni verifica la identidad.
                  </p>
                  <label className="consent-field">
                    <input
                      type="checkbox"
                      {...field("privacy_accepted")}
                      aria-invalid={Boolean(errors.privacy_accepted)}
                      aria-describedby={
                        errors.privacy_accepted ? "privacy-error" : undefined
                      }
                    />
                    <span>
                      He leído el aviso y acepto el tratamiento de estos datos
                      para los fines descritos.{" "}
                      <span className="required-mark" aria-hidden="true">
                        *
                      </span>
                    </span>
                  </label>
                  {errorText("privacy_accepted") && (
                    <small
                      id="privacy-error"
                      className="field-error"
                      role="alert"
                    >
                      {errorText("privacy_accepted")}
                    </small>
                  )}
                </div>
              </>
            )}
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
          {!register && (
            <div className="notice">
              <strong>Demostración local</strong>
              <p>
                También puedes crear una cuenta independiente desde “Crea tu
                cuenta”. Todos los pagos son simulados.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
