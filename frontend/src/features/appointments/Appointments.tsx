import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { CalendarDays, CheckCircle2, Clock3, Printer } from "lucide-react";
import {
  api,
  post,
  dateText,
  timeText,
  money,
  statuses,
} from "../../services/api";
import type { Appointment, Config } from "../../types";
import {
  Badge,
  Empty,
  ErrorBox,
  Go,
  Loading,
  PageTitle,
} from "../../components/common";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
export function Appointments() {
  const [tab, setTab] = useState("upcoming");
  const q = useQuery({
    queryKey: ["appointments"],
    queryFn: () => api<Appointment[]>("/appointments"),
  });
  const items = q.data
    ?.filter((a) =>
      tab === "cancelled"
        ? a.status === "CANCELLED"
        : tab === "history"
          ? a.status !== "CANCELLED" &&
            (a.status === "ATTENDED" || new Date(a.starts_at) <= new Date())
          : a.status === "CONFIRMED" && new Date(a.starts_at) > new Date(),
    )
    .sort((a, b) =>
      tab === "upcoming"
        ? a.starts_at.localeCompare(b.starts_at)
        : b.starts_at.localeCompare(a.starts_at),
    );
  return (
    <>
      <PageTitle
        title="Tu agenda, en sintonía"
        description="Consulta tus próximas citas y encuentra el historial de tu cuidado."
        action={<Go to="/portal/doctors">Agendar una cita</Go>}
      />
      <div className="tabs" role="tablist" aria-label="Mis citas">
        {[
          ["upcoming", "Próximas citas"],
          ["history", "Historial"],
          ["cancelled", "Historial · Canceladas"],
        ].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : !items?.length ? (
        <Empty
          title={
            tab === "cancelled"
              ? "No tienes citas canceladas"
              : tab === "history"
                ? "Tu historial aparecerá aquí"
                : "Todavía no tienes citas próximas"
          }
        >
          <p>Cada consulta es un paso hacia tu bienestar.</p>
          <Go to="/portal/doctors">Buscar médicos</Go>
        </Empty>
      ) : (
        <div className="appointments-list">
          {items.map((a) => (
            <article className="panel appointment-row" key={a.id}>
              <div className="date-tile">
                <CalendarDays />
                <strong>
                  {new Intl.DateTimeFormat("es-CO", {
                    day: "2-digit",
                    timeZone: "America/Bogota",
                  }).format(new Date(a.starts_at))}
                </strong>
                <span>
                  {new Intl.DateTimeFormat("es-CO", {
                    month: "short",
                    timeZone: "America/Bogota",
                  }).format(new Date(a.starts_at))}
                </span>
              </div>
              <div className="appointment-primary">
                <Badge status={a.status} />
                <h2>{a.doctor}</h2>
                <p>{a.specialty}</p>
                <small>{a.code}</small>
              </div>
              <div className="appointment-meta">
                <span>
                  <CalendarDays size={17} />
                  {dateText(a.starts_at)}
                </span>
                <span>
                  <Clock3 size={17} />
                  {timeText(a.starts_at)} · Presencial
                </span>
              </div>
              <Button asChild variant="outline">
                <Link to={"/portal/appointments/" + a.id}>Ver detalle</Link>
              </Button>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
export function AppointmentDetail() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const q = useQuery({
    queryKey: ["appointment", id],
    queryFn: () => api<Appointment>("/appointments/" + id),
  });
  const config = useQuery({
    queryKey: ["config"],
    queryFn: () => api<Config>("/config"),
  });
  async function cancel() {
    if (!q.data) return;
    setBusy(true);
    setError(null);
    try {
      await post("/appointments/" + id + "/cancel", {
        version: q.data.version,
        reason,
        confirmed: accepted,
      });
      setOpen(false);
      await client.invalidateQueries();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const a = q.data;
  return (
    <>
      <Link className="text-link back-link" to="/portal/appointments">
        ← Volver a Mis citas
      </Link>
      {params.has("confirmed") && a.status === "CONFIRMED" && (
        <div className="confirmation-banner">
          <CheckCircle2 />
          <div>
            <h2>¡Tu cita está confirmada!</h2>
            <p>Guardamos tu comprobante y una notificación en tu cuenta.</p>
          </div>
        </div>
      )}
      <PageTitle
        title="Detalle de tu cita"
        description={"Comprobante " + a.code}
        action={
          <Button variant="outline" onClick={() => window.print()}>
            <Printer size={17} />
            Imprimir comprobante
          </Button>
        }
      />
      <section className="panel receipt">
        <div className="receipt-heading">
          <div>
            <span className="eyebrow">VITALSYNC · COMPROBANTE DE CITA</span>
            <h2>{a.doctor}</h2>
            <p>{a.specialty}</p>
          </div>
          <Badge status={a.status} />
        </div>
        <dl>
          <div>
            <dt>Código de cita</dt>
            <dd>{a.code}</dd>
          </div>
          <div>
            <dt>Paciente</dt>
            <dd>{a.patient}</dd>
          </div>
          <div>
            <dt>Fecha</dt>
            <dd>{dateText(a.starts_at)}</dd>
          </div>
          <div>
            <dt>Horario</dt>
            <dd>
              {timeText(a.starts_at)} – {timeText(a.ends_at)} · Bogotá
            </dd>
          </div>
          <div>
            <dt>Plan utilizado</dt>
            <dd>{a.plan}</dd>
          </div>
          <div>
            <dt>Copago simulado</dt>
            <dd>{a.copay ? money(a.copay) : "No requerido"}</dd>
          </div>
          <div>
            <dt>Lugar de consulta</dt>
            <dd>Presencial · Sede VITALSYNC Bogotá (ficticia)</dd>
          </div>
        </dl>
        {a.status === "CANCELLED" && (
          <div className="notice">
            <strong>Cita cancelada el {dateText(a.cancelled_at!)}</strong>
            <p>Motivo: {a.cancellation_reason}</p>
            {a.economic_review && (
              <p>
                Copago sujeto a gestión económica futura. No se ha emitido una
                devolución automática.
              </p>
            )}
          </div>
        )}
        {a.history && (
          <div className="timeline">
            <h3>Registro de la cita</h3>
            {a.history.map((h) => (
              <p key={h.id}>
                <span className="live-dot" />
                {statuses[h.status]} · {dateText(h.created_at)} · {h.reason}
              </p>
            ))}
          </div>
        )}
        {a.status === "CONFIRMED" && (
          <div className="cancel-area">
            <p>
              Política de demostración: cancela con más de{" "}
              {config.data?.cancellation_hours ?? "…"} horas de anticipación. El
              servidor valida la política.
            </p>
            <Button
              variant="destructive"
              onClick={() => {
                setOpen(true);
                setError(null);
              }}
            >
              Cancelar cita
            </Button>
          </div>
        )}
      </section>
      <Dialog
        open={open}
        onOpenChange={(v) => {
          if (!busy) setOpen(v);
        }}
        title="¿Quieres cancelar esta cita?"
        description="Revisa los datos y confirma expresamente. La cita permanecerá en el historial."
      >
        <div className="notice">
          <strong>
            {a.doctor} · {a.specialty}
          </strong>
          <p>
            {dateText(a.starts_at)} a las {timeText(a.starts_at)}
          </p>
          <p>
            Anticipación mínima: {config.data?.cancellation_hours ?? "…"} horas.
          </p>
          {a.copay > 0 && (
            <p>
              Existe un copago asociado; quedará pendiente de gestión económica
              futura.
            </p>
          )}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void cancel();
          }}
        >
          <label>
            Motivo de cancelación
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              minLength={3}
              maxLength={500}
              required
              placeholder="Cuéntanos el motivo"
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              required
            />
            Confirmo que deseo cancelar mi cita.
          </label>
          <ErrorBox error={error} />
          <div className="button-row">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Conservar mi cita
            </Button>
            <Button
              variant="destructive"
              disabled={busy || !accepted || reason.trim().length < 3}
            >
              {busy ? "Cancelando…" : "Confirmar cancelación"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
