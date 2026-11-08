import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Check, Clock3, ShieldCheck } from "lucide-react";
import type { Hold, Doctor, Appointment } from "../../types";
import { api, post, dateText, timeText, money } from "../../services/api";
import {
  Empty,
  ErrorBox,
  Go,
  Loading,
  PageTitle,
} from "../../components/common";
import { Button } from "../../components/ui/button";
import { PaymentControls } from "../plans/Plans";
export function Booking() {
  const { id } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [clock, setClock] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const h = useQuery({
    queryKey: ["hold", id],
    queryFn: () => api<Hold>("/holds/" + id),
  });
  const d = useQuery({
    queryKey: ["doctor", h.data?.doctor_id],
    queryFn: () => api<Doctor>("/doctors/" + h.data!.doctor_id),
    enabled: !!h.data,
  });
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(
    0,
    Math.floor((new Date(h.data?.expires_at ?? 0).getTime() - clock) / 1000),
  );
  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const a = await post<Appointment>("/holds/" + id + "/confirm");
      await client.invalidateQueries();
      navigate("/portal/appointments/" + a.id + "?confirmed=1");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function release() {
    setBusy(true);
    setError(null);
    try {
      await post("/holds/" + id + "/release");
      await client.invalidateQueries();
      navigate("/portal/doctors");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (h.isPending) return <Loading />;
  if (h.error) return <ErrorBox error={h.error} />;
  if (!seconds || h.data.status !== "ACTIVE")
    return (
      <Empty title="La retención ya no está activa">
        <p>Selecciona un nuevo horario para continuar.</p>
        <Go to="/portal/doctors">Consultar disponibilidad</Go>
      </Empty>
    );
  return (
    <>
      <PageTitle
        title="Un paso más para tu cita"
        description="Revisa los datos, completa el copago si corresponde y confirma tu consulta."
      />
      <div className="stepper">
        <span className="done">
          <Check size={16} />
          Horario
        </span>
        <span className="current">2 · Revisión y pago</span>
        <span>3 · Confirmación</span>
      </div>
      <div className="booking-grid">
        <section className="panel booking-summary">
          <span className="eyebrow">RESUMEN DE TU CONSULTA</span>
          <h2>{d.data?.name ?? "Consulta médica"}</h2>
          <p>{d.data?.specialty}</p>
          <ErrorBox error={d.error} />
          <dl>
            <div>
              <dt>Fecha</dt>
              <dd>{dateText(h.data.starts_at)}</dd>
            </div>
            <div>
              <dt>Hora</dt>
              <dd>{timeText(h.data.starts_at)} · Bogotá</dd>
            </div>
            <div>
              <dt>Modalidad</dt>
              <dd>Presencial · Sede Bogotá</dd>
            </div>
            <div>
              <dt>Copago</dt>
              <dd>{h.data.copay ? money(h.data.copay) : "No requerido"}</dd>
            </div>
          </dl>
          <div className="hold-countdown" role="timer">
            <Clock3 />
            <div>
              <strong>
                Horario retenido durante {Math.floor(seconds / 60)}:
                {String(seconds % 60).padStart(2, "0")}
              </strong>
              <p>Esta retención todavía no es una cita confirmada.</p>
            </div>
          </div>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void release()}
          >
            Liberar horario y volver
          </Button>
        </section>
        <section className="panel checkout">
          <h2>
            {h.data.copay
              ? "Autoriza tu copago"
              : "Tu plan cubre esta consulta"}
          </h2>
          {h.data.copay ? (
            <>
              <p>
                Importe a simular: <strong>{money(h.data.copay)}</strong>
              </p>
              <PaymentControls
                kind="COPAY"
                targetId={h.data.id}
                onApproved={() => void client.invalidateQueries()}
              />
            </>
          ) : (
            <div className="alert success">
              <ShieldCheck />
              No necesitas un pago adicional para esta cita.
            </div>
          )}
          <hr />
          <ErrorBox error={error} />
          <Button
            className="full"
            disabled={busy || !seconds}
            onClick={() => void confirm()}
          >
            {busy ? "Confirmando…" : "Confirmar cita"}
          </Button>
          <p className="muted">
            Al confirmar, el servidor vuelve a verificar tu plan, el horario y
            el resultado del pago.
          </p>
          <Link className="text-link" to="/portal/plans">
            Consultar mi plan
          </Link>
        </section>
      </div>
    </>
  );
}
