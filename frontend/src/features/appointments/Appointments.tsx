import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { CalendarDays, CheckCircle2, Clock3, Printer, MapPin, Monitor } from "lucide-react";
import {
  api,
  post,
  dateText,
  timeText,
  money,
  statuses,
} from "../../services/api";
import type { Appointment, Config, Modality } from "../../types";
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
  const [modalityFilter, setModalityFilter] = useState<"ALL" | Modality>("ALL");
  const views: Record<string, string> = { upcoming: "upcoming", completed: "completed", history: "history", cancelled: "cancelled" };
  const q = useQuery({
    queryKey: ["appointments", tab],
    queryFn: () => api<Appointment[]>("/appointments?view=" + (views[tab] ?? "all")),
    refetchInterval: 15000,
  });
  const items = q.data
    ?.filter((a) =>
      (modalityFilter === "ALL" || a.modality === modalityFilter) &&
      (tab === "cancelled"
        ? a.status === "CANCELLED"
        : tab === "completed" || tab === "finalized"
          ? a.status === "ATTENDED"
          : tab === "incidents"
            ? ["PATIENT_ABSENT", "DOCTOR_ABSENT", "TECHNICAL_ERROR"].includes(a.status)
            : tab === "in_progress"
              ? a.status === "IN_PROGRESS"
              : tab === "history"
                ? a.status !== "CANCELLED" &&
                  (!["CONFIRMED", "IN_PROGRESS", "TECHNICAL_ERROR"].includes(a.status) || new Date(a.ends_at) <= new Date())
                : ["CONFIRMED", "TECHNICAL_ERROR"].includes(a.status) && new Date(a.starts_at) > new Date()),
    )
    .sort((a, b) =>
      tab === "upcoming"
        ? a.starts_at.localeCompare(b.starts_at)
        : b.starts_at.localeCompare(a.starts_at),
    );  return (
    <>
      <PageTitle
        title="Tu agenda, en sintonía"
        description="Consulta tus próximas citas y encuentra el historial de tu cuidado."
        action={<Go to="/portal/doctors">Agendar una cita</Go>}
      />
      <div className="tabs" role="tablist" aria-label="Mis citas">
        {[
          ["upcoming", "Próximas citas"],
          ["in_progress", "En atención"],
          ["history", "Historial"],
          ["completed", "Historial · Finalizadas"],
          ["cancelled", "Historial · Canceladas"],
          ["incidents", "Ausencias e incidencias"],
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
      <label className="appointment-modality-filter">
        Filtrar por modalidad
        <select
          aria-label="Filtrar citas por modalidad"
          value={modalityFilter}
          onChange={(event) => setModalityFilter(event.target.value as "ALL" | Modality)}
        >
          <option value="ALL">Todas</option>
          <option value="VIRTUAL">Virtuales</option>
          <option value="PRESENCIAL">Presenciales</option>
        </select>
      </label>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : !items?.length ? (
        <Empty
          title={
            tab === "cancelled"
              ? "No tienes citas canceladas"
              : tab === "completed" || tab === "finalized"
                ? "No tienes citas finalizadas"
              : tab === "history"
                ? "Tu historial aparecerá aquí"
                : tab === "in_progress"
                  ? "No tienes citas en atención"
                  : tab === "incidents"
                    ? "No tienes ausencias ni incidencias"
                    : "No tienes próximas citas programadas"
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
                <Badge status={a.completion_source === "DEMO" ? "DEMO_COMPLETED" : a.status} />
                <h2>{a.doctor}</h2>
                <p>{a.specialty}</p>
                <small>{a.code}</small>
                {a.simulated_completed_at && <p>Simulación: {dateText(a.simulated_completed_at)} · {timeText(a.simulated_completed_at)}. No hubo atención médica real.</p>}
              </div>
              <div className="appointment-meta">
                <span>
                  <CalendarDays size={17} />
                  {dateText(a.starts_at)}
                </span>
                <span>
                  <Clock3 size={17} />
                  {a.modality === 'VIRTUAL' ? 'Cita virtual' : 'Cita presencial'} · {timeText(a.starts_at)}
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
    refetchInterval: 15000,
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
          <Badge status={a.completion_source === "DEMO" ? "DEMO_COMPLETED" : a.status} />
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
            <dt>Modalidad</dt>
            <dd>{a.modality === 'VIRTUAL' ? 'Consulta virtual · Teleconsulta simulada' : 'Consulta presencial · Sede VITALSYNC Bogotá (ficticia)'}</dd>
          </div>
        </dl>
        {a.simulated_completed_at && <p className="notice">Finalizada (simulación) · {dateText(a.simulated_completed_at)} · {timeText(a.simulated_completed_at)}. No hubo atención médica real.</p>}
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
                {statuses[h.status] ?? statuses[h.status.replace("VIRTUAL_", "")] ?? h.status} · {dateText(h.created_at)} · {timeText(h.created_at)} · {h.reason}
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
        {a.modality === "VIRTUAL" && (
          <div className="notice virtual-link">
            <strong>Teleconsulta simulada</strong>
            {["CONFIRMED", "IN_PROGRESS", "TECHNICAL_ERROR"].includes(a.status) ? (
              <>
                <p>Esta experiencia no usa conexión de audio o video.</p>
                <Button
                  className="virtual-teleconsult-button"
                  asChild
                >
                  <Link to={"/portal/appointments/" + a.id + "/teleconsult"}>
                    <Monitor size={17} />
                    Ver teleconsulta simulada
                  </Link>
                </Button>
              </>
            ) : (
              <>
                <p>
                  {a.status === "CANCELLED"
                    ? "La cita está cancelada; la teleconsulta no está disponible."
                    : a.completion_source === "DEMO"
                      ? "La simulación ha finalizado; consulta el registro de la cita."
                    : ["PATIENT_ABSENT", "DOCTOR_ABSENT", "TECHNICAL_ERROR"].includes(a.status)
                      ? "La teleconsulta terminó con una incidencia; no se registró una atención finalizada."
                    : a.status === "ATTENDED"
                      ? "Atención finalizada en modo demostración. Consulta el historial de la cita."
                      : "La teleconsulta estará disponible cuando la cita esté confirmada."}
                </p>
                {a.status === "ATTENDED" ? (
                  <Button className="virtual-teleconsult-button" asChild>
                    <Link to={"/portal/appointments/" + a.id + "/teleconsult"}>
                      <Monitor size={17} />Ver historial de cita
                    </Link>
                  </Button>
                ) : (
                  <Button className="virtual-teleconsult-button" type="button" disabled>
                    <Monitor size={17} />Ver teleconsulta simulada
                  </Button>
                )}
              </>
            )}
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

export function Teleconsultation() {
  const { id } = useParams();
  const client = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const q = useQuery({
    queryKey: ["teleconsult", id],
    queryFn: () => api<Appointment>("/appointments/" + id + "/teleconsult"),
    refetchInterval: 15000,
  });
  async function advance(event: string) {
    setBusy(true);
    setError(null);
    try {
      await post("/appointments/" + id + "/teleconsult/status", { event });
      await Promise.all(["teleconsult", "appointment", "appointments", "dashboard", "notifications"].map((key) =>
        client.invalidateQueries({ queryKey: [key, ...(key === "teleconsult" || key === "appointment" ? [id] : [])] }),
      ));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const a = q.data;
  const status = a.virtual_status ?? "PROGRAMADA";
  const virtual = a.virtual_state;
  const actionLabels: Record<string, string> = {
    ADVANCE_DEMO_CLOCK: "Avanzar reloj de demostración",
    OPEN_ROOM: "Abrir sala simulada",
    PATIENT_JOIN: "Ingresar como paciente",
    DOCTOR_JOIN: "Simular ingreso del médico",
    START: "Iniciar atención simulada",
    FINALIZE: "Finalizar teleconsulta simulada",
    PATIENT_ABSENT: "Registrar ausencia del paciente",
    DOCTOR_ABSENT: "Registrar ausencia del médico",
    TECHNICAL_ERROR: "Simular incidencia técnica",
    RETRY: "Reintentar sala simulada",
  };
  const terminal = ["FINALIZADA", "PACIENTE_AUSENTE", "MEDICO_AUSENTE", "CANCELADA"].includes(virtual?.lifecycle_status ?? status);
  const stateExplanation: Record<string, string> = {
    PROGRAMADA: "La cita está programada. La sala estará disponible dentro del horario configurado.",
    SALA_DISPONIBLE: "La sala está abierta. El paciente y, en demostración, el médico pueden registrar su presencia.",
    PACIENTE_EN_ESPERA: "El paciente ya ingresó y espera al médico.",
    MEDICO_EN_ESPERA: "El médico está en la sala y espera al paciente.",
    AMBOS_PRESENTES: "Ambos participantes están presentes; en modo demostración se puede iniciar la atención simulada.",
    EN_ATENCION: "La atención simulada está en curso.",
    ERROR_TECNICO: "La incidencia técnica está registrada; el reintento conserva el estado anterior.",
    FINALIZADA: "La sesión terminó y la cita se conserva en el historial.",
    PACIENTE_AUSENTE: "La cita se cerró por ausencia del paciente y permanece en el historial.",
    MEDICO_AUSENTE: "La ausencia médica quedó registrada; no se marcó como atención finalizada.",
  };
  const patientPresent = virtual?.patient_present ?? Boolean(a.patient_present_at);
  const doctorPresent = virtual?.doctor_present ?? Boolean(a.doctor_present_at);
  return (
    <>
      <Link className="text-link back-link" to={"/portal/appointments/" + id}>
        ← Volver al comprobante
      </Link>
      <PageTitle
        eyebrow="EXPERIENCIA DE DEMOSTRACIÓN"
        title="Teleconsulta simulada"
        description="Representación de estados de una cita virtual. No se conecta audio ni video."
      />
      <section className="panel virtual-room">
        <Monitor size={50} />
        <h2>Sin conexión de audio o video</h2>
        <div className="alert success">Teleconsulta simulada — sin conexión de audio o video</div>
        <Badge status={a.completion_source === "DEMO" ? "DEMO_COMPLETED" : status} />
        <p role="status">{stateExplanation[status] ?? "Consulta el estado persistido de esta sesión."}</p>
        <dl>
          <div><dt>Paciente</dt><dd>{a.patient}</dd></div>
          <div><dt>Médico</dt><dd>{a.doctor}</dd></div>
          <div><dt>Especialidad</dt><dd>{a.specialty}</dd></div>
          <div><dt>Fecha</dt><dd>{dateText(a.starts_at)}</dd></div>
          <div><dt>Hora</dt><dd>{timeText(a.starts_at)} · Bogotá</dd></div>
          <div><dt>Estado de la cita</dt><dd>{a.completion_source === "DEMO" ? "Finalizada (simulación)" : statuses[a.status]}</dd></div>
          <div><dt>Presencia del paciente</dt><dd>{patientPresent ? "Presente" : "Aún no ha ingresado"}</dd></div>
          <div><dt>Presencia del médico</dt><dd>{doctorPresent ? "Presente" : "Aún no ha ingresado"}</dd></div>
          {(virtual?.finalized_at ?? a.simulated_completed_at) && <div><dt>Finalizada</dt><dd>{dateText((virtual?.finalized_at ?? a.simulated_completed_at)!)} · {timeText((virtual?.finalized_at ?? a.simulated_completed_at)!)}</dd></div>}
        </dl>
        <p>La simulación no conecta audio ni video y no acredita atención médica real. La sala abre {virtual?.room_open_minutes ?? 5} minutos antes de la cita; el plazo de espera es {virtual?.wait_grace_minutes ?? 15} minutos.</p>
        {virtual?.demo_clock_advanced && <p>Reloj demostrativo avanzado. La fecha y hora reservadas no se modificaron.</p>}
        {virtual?.incident_reason && <p role="status">{virtual.incident_reason}</p>}
        {a.completion_source === "DEMO" && <div className="alert success">Atención finalizada en modo demostración. No hubo atención médica real.</div>}
        {a.demo_mode === false && !virtual?.available_actions?.length && <p>La simulación está deshabilitada fuera del modo demostración.</p>}
        {!terminal && (virtual?.available_actions ?? []).map((action) => (
          <Button key={action} variant={action === "FINALIZE" ? "default" : "outline"} disabled={busy} onClick={() => void advance(action)}>
            {actionLabels[action] ?? action}
          </Button>
        ))}
        {terminal && <Button asChild variant="outline"><Link to={"/portal/appointments/" + id}>Ver historial de cita</Link></Button>}
        <ErrorBox error={error} />
      </section>
    </>
  );
}
