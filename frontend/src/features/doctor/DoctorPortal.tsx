import { useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  Clock3,
  MapPin,
  Monitor,
  Search,
  ShieldCheck,
  Stethoscope,
  Users,
} from "lucide-react";
import {
  api,
  post,
  dateText,
  timeText,
  dayKey,
  statuses,
} from "../../services/api";
import type {
  MedicalAppointment,
  MedicalDashboard,
  MedicalProfile,
} from "../../types";
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
import "./doctor.css";

const prefix = "/doctor";
const today = () => dayKey(new Date().toISOString());
const displayDay = (day: string) => dateText(day + "T12:00:00-05:00");
function State({
  pending,
  error,
  children,
}: {
  pending: boolean;
  error: unknown;
  children: ReactNode;
}) {
  return pending ? <Loading /> : error ? <ErrorBox error={error} /> : children;
}
function AppointmentCard({ item }: { item: MedicalAppointment }) {
  return (
    <article className="medical-appointment">
      <div className="medical-time">
        <strong>{timeText(item.starts_at)}</strong>
        <small>{item.duration_minutes} min</small>
      </div>
      <div className="medical-person">
        <span className="avatar">
          {item.patient
            .split(" ")
            .map((n) => n[0])
            .slice(0, 2)
            .join("")}
        </span>
        <div>
          <h3>{item.patient}</h3>
          <small>
            {dateText(item.starts_at)} · {item.code}
          </small>
        </div>
      </div>
      <div className="medical-modality">
        {item.modality === "VIRTUAL" ? (
          <Monitor size={17} />
        ) : (
          <MapPin size={17} />
        )}
        <span>{item.modality === "VIRTUAL" ? "Virtual" : "Presencial"}</span>
      </div>
      <Badge
        status={
          item.completion_source === "DEMO" ? "DEMO_COMPLETED" : item.status
        }
      />
      <Link
        className="medical-detail-link"
        aria-label={"Ver cita de " + item.patient}
        to={prefix + "/appointments/" + item.id}
      >
        Ver detalle <ArrowUpRight size={17} />
      </Link>
    </article>
  );
}
function AppointmentList({ items }: { items: MedicalAppointment[] }) {
  return items.length ? (
    <div className="medical-list">
      {items.map((item) => (
        <AppointmentCard key={item.id} item={item} />
      ))}
    </div>
  ) : (
    <Empty title="No hay citas para esta selección">
      <p>Las reservas asignadas aparecerán aquí.</p>
    </Empty>
  );
}
export function DoctorDashboard() {
  const q = useQuery({
    queryKey: ["doctor", "dashboard"],
    queryFn: () => api<MedicalDashboard>(prefix + "/dashboard"),
    refetchInterval: 15000,
  });
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data;
  const metrics = [
    ["Citas de hoy", d.metrics.total, CalendarDays],
    ["Presenciales", d.metrics.presencial, MapPin],
    ["Virtuales", d.metrics.virtual, Monitor],
    ["Pendientes", d.metrics.pending, Clock3],
    ["Finalizadas", d.metrics.completed, CheckCircle2],
  ] as const;
  return (
    <div className="medical-page">
      <PageTitle
        eyebrow="TU ESPACIO PROFESIONAL"
        title={"Hola, " + d.doctor.name}
        description={
          d.doctor.specialty + " · " + displayDay(d.date) + " · Bogotá"
        }
        action={<Go to={prefix + "/appointments"}>Ver mi agenda</Go>}
      />
      <section className="medical-welcome">
        <div>
          <span className="light-label">CUIDAMOS EN EQUIPO</span>
          <h2>
            Tu agenda, al día.
            <br />
            Más tiempo para acompañar.
          </h2>
          <p>
            Consulta tus reservas y gestiona cada encuentro desde un solo lugar.
          </p>
          <Link to={prefix + "/patients"}>
            Consultar mis pacientes <ArrowUpRight size={18} />
          </Link>
        </div>
        <div className="medical-welcome-art" aria-hidden="true">
          <Stethoscope size={90} strokeWidth={1.2} />
          <span>
            <ShieldCheck size={18} />
            Acceso profesional
          </span>
        </div>
      </section>
      <section className="medical-metrics" aria-label="Resumen de hoy">
        {metrics.map(([label, value, Icon]) => (
          <article className="panel" key={label}>
            <Icon size={21} />
            <strong>{String(value).padStart(2, "0")}</strong>
            <span>{label}</span>
          </article>
        ))}
      </section>
      <section className="panel medical-next">
        <div>
          <span className="eyebrow">PRÓXIMO ENCUENTRO</span>
          <h2>
            {d.next_appointment
              ? d.next_appointment.patient
              : "Tu agenda tiene espacio"}
          </h2>
          <p>
            {d.next_appointment
              ? `${displayDay(dayKey(d.next_appointment.starts_at))} · ${timeText(d.next_appointment.starts_at)} · ${d.next_appointment.modality === "VIRTUAL" ? "Consulta virtual simulada" : "Consulta presencial"}`
              : "Las nuevas reservas aparecerán aquí cuando un paciente confirme su cita."}
          </p>
        </div>
        {d.next_appointment && (
          <Go to={prefix + "/appointments/" + d.next_appointment.id}>
            Ver consulta
          </Go>
        )}
      </section>
      <section className="panel medical-agenda">
        <div className="section-heading">
          <div>
            <span className="eyebrow">HOY EN TU CONSULTORIO</span>
            <h2>Agenda del día</h2>
          </div>
          <span className="medical-count">{d.agenda.length} citas</span>
        </div>
        <AppointmentList items={d.agenda} />
      </section>
    </div>
  );
}
export function DoctorAgenda() {
  const [day, setDay] = useState("");
  const [view, setView] = useState("upcoming");
  const [modality, setModality] = useState("");
  const [status, setStatus] = useState("");
  const params = new URLSearchParams({ view });
  if (day) params.set("day", day);
  if (modality) params.set("modality", modality);
  if (status) params.set("status", status);
  const q = useQuery({
    queryKey: ["doctor", "appointments", params.toString()],
    queryFn: () =>
      api<MedicalAppointment[]>(prefix + "/appointments?" + params),
    refetchInterval: 15000,
  });
  return (
    <div className="medical-page">
      <PageTitle
        eyebrow="CADA ENCUENTRO CUENTA"
        title="Mi agenda"
        description="Reservas asignadas a tu perfil profesional, con horario de Bogotá."
      />
      <div className="tabs" role="tablist" aria-label="Agenda médica">
        {[
          ["upcoming", "Próximas"],
          ["history", "Realizadas e incidencias"],
          ["cancelled", "Canceladas"],
          ["all", "Todas"],
        ].map(([value, label]) => (
          <button
            role="tab"
            aria-selected={view === value}
            key={value}
            onClick={() => setView(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="panel medical-filters">
        <label>
          Fecha
          <input
            type="date"
            value={day}
            onChange={(e) => setDay(e.target.value)}
          />
        </label>
        <label>
          Modalidad
          <select
            aria-label="Modalidad"
            value={modality}
            onChange={(e) => setModality(e.target.value)}
          >
            <option value="">Todas las modalidades</option>
            <option value="PRESENCIAL">Presencial</option>
            <option value="VIRTUAL">Virtual</option>
          </select>
        </label>
        <label>
          Estado
          <select
            aria-label="Estado"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">Todos los estados</option>
            {[
              "CONFIRMED",
              "IN_PROGRESS",
              "ATTENDED",
              "CANCELLED",
              "PATIENT_ABSENT",
              "DOCTOR_ABSENT",
              "TECHNICAL_ERROR",
            ].map((s) => (
              <option value={s} key={s}>
                {statuses[s]}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="outline"
          onClick={() => {
            setDay("");
            setModality("");
            setStatus("");
          }}
        >
          Limpiar filtros
        </Button>
      </div>
      <section className="panel medical-agenda">
        <State pending={q.isPending} error={q.error}>
          <AppointmentList items={q.data ?? []} />
        </State>
      </section>
    </div>
  );
}
function useMedicalRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      [
        "doctor",
        "appointments",
        "appointment",
        "dashboard",
        "notifications",
        "teleconsult",
      ].map((key) => client.invalidateQueries({ queryKey: [key] })),
    );
}
function History({ item }: { item: MedicalAppointment }) {
  return (
    <section className="panel medical-history">
      <span className="eyebrow">TRAZABILIDAD DE LA RESERVA</span>
      <h2>Historial de estados</h2>
      {item.history?.map((h, index) => (
        <article key={index}>
          <span className="medical-timeline-dot" />
          <div>
            <Badge status={h.status} />
            <p>{h.reason}</p>
            <small>
              {dateText(h.created_at)} · {timeText(h.created_at)}
            </small>
          </div>
        </article>
      ))}
    </section>
  );
}
export function DoctorDetail() {
  const { id } = useParams();
  const refresh = useMedicalRefresh();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const q = useQuery({
    queryKey: ["doctor", "appointment", id],
    queryFn: () => api<MedicalAppointment>(prefix + "/appointments/" + id),
    refetchInterval: 10000,
  });
  async function cancel(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(prefix + "/appointments/" + id + "/cancel", {
        version: q.data!.version,
        reason,
        confirmed,
      });
      await refresh();
      setOpen(false);
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
    <div className="medical-page">
      <Link className="text-link" to={prefix + "/appointments"}>
        ← Volver a mi agenda
      </Link>
      <PageTitle
        eyebrow="RESERVA ASIGNADA"
        title={a.patient}
        description={a.specialty + " · " + a.code}
      />
      <section className="panel medical-record">
        <div className="section-heading">
          <h2>Detalle de la cita</h2>
          <Badge
            status={
              a.completion_source === "DEMO" ? "DEMO_COMPLETED" : a.status
            }
          />
        </div>
        <dl>
          <div>
            <dt>Modalidad</dt>
            <dd>
              {a.modality === "VIRTUAL"
                ? "Consulta virtual simulada"
                : "Consulta presencial"}
            </dd>
          </div>
          <div>
            <dt>Fecha reservada</dt>
            <dd>{dateText(a.starts_at)}</dd>
          </div>
          <div>
            <dt>Horario en Bogotá</dt>
            <dd>
              {timeText(a.starts_at)} – {timeText(a.ends_at)} ·{" "}
              {a.duration_minutes} minutos
            </dd>
          </div>
          <div>
            <dt>Profesional</dt>
            <dd>{a.doctor}</dd>
          </div>
        </dl>
        {a.completion_source === "DEMO" && (
          <div className="notice">
            Finalizada en modo de demostración. No acredita atención médica
            real.
            {a.simulated_completed_at && (
              <p>
                {dateText(a.simulated_completed_at)} ·{" "}
                {timeText(a.simulated_completed_at)}
              </p>
            )}
          </div>
        )}
        {a.cancellation_reason && (
          <div className="notice">
            <strong>Motivo de cancelación</strong>
            <p>{a.cancellation_reason}</p>
          </div>
        )}
        <div className="medical-actions">
          {a.modality === "VIRTUAL" && (
            <Go to={prefix + "/appointments/" + id + "/teleconsult"}>
              {a.status === "ATTENDED"
                ? "Ver registro de simulación"
                : "Ver sala simulada"}
            </Go>
          )}
          {a.status === "CONFIRMED" && new Date(a.starts_at) > new Date() && (
            <Button
              variant="outline"
              onClick={() => {
                setError(null);
                setOpen(true);
              }}
            >
              Cancelar cita
            </Button>
          )}
        </div>
      </section>
      <History item={a} />
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
        title="Cancelar cita asignada"
        description="La cancelación se notificará al paciente y quedará registrada con tu autoría."
      >
        <form onSubmit={cancel}>
          <p>
            {a.patient} · {dateText(a.starts_at)} · {timeText(a.starts_at)}
          </p>
          <label>
            Motivo obligatorio
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              minLength={3}
              maxLength={500}
              required
            />
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              required
            />
            Confirmo la cancelación de esta cita.
          </label>
          <div className="notice">
            El paciente podrá contactar a VITALSYNC para una nueva reserva.
            Cualquier gestión económica se revisa por separado.
          </div>
          <ErrorBox error={error} />
          <div className="button-row">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Mantener cita
            </Button>
            <Button disabled={busy || !confirmed || reason.trim().length < 3}>
              {busy ? "Guardando…" : "Confirmar cancelación"}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
export function DoctorPatients() {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const q = useQuery({
    queryKey: ["doctor", "patients", search],
    queryFn: () =>
      api<{ id: number; name: string }[]>(
        prefix + "/patients?search=" + encodeURIComponent(search),
      ),
  });
  const detail = useQuery({
    queryKey: ["doctor", "patient", selected],
    queryFn: () =>
      api<{ id: number; name: string; appointments: MedicalAppointment[] }>(
        prefix + "/patients/" + selected,
      ),
    enabled: selected !== null,
  });
  return (
    <div className="medical-page">
      <PageTitle
        eyebrow="PERSONAS QUE ACOMPAÑAS"
        title="Mis pacientes"
        description="Consulta únicamente las reservas de pacientes asignadas a tu agenda."
      />
      <label className="panel medical-search">
        <Search size={20} />
        <input
          aria-label="Buscar paciente por nombre"
          placeholder="Buscar por nombre"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <State pending={q.isPending} error={q.error}>
        <div className="medical-patients">
          {q.data?.map((p) => (
            <button
              className={
                "panel medical-patient " + (selected === p.id ? "selected" : "")
              }
              key={p.id}
              onClick={() => setSelected(p.id)}
            >
              <span className="avatar">
                <Users size={21} />
              </span>
              <strong>{p.name}</strong>
              <ArrowUpRight size={18} />
            </button>
          ))}
          {q.data?.length === 0 && (
            <Empty title="No hay pacientes para esta búsqueda" />
          )}
        </div>
      </State>
      {selected !== null && (
        <section className="panel medical-agenda">
          <State pending={detail.isPending} error={detail.error}>
            <h2>{detail.data?.name}</h2>
            <p>Reservas relacionadas con este profesional.</p>
            <AppointmentList items={detail.data?.appointments ?? []} />
          </State>
        </section>
      )}
    </div>
  );
}
export function DoctorProfilePage() {
  const q = useQuery({
    queryKey: ["doctor", "me"],
    queryFn: () => api<MedicalProfile>(prefix + "/me"),
  });
  const refresh = useMedicalRefresh();
  const [bio, setBio] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await api(prefix + "/me", {
        method: "PATCH",
        body: JSON.stringify({ bio }),
      });
      await refresh();
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data;
  return (
    <div className="medical-page">
      <PageTitle
        eyebrow="IDENTIDAD PROFESIONAL"
        title="Mi perfil"
        description="Tu información institucional y presentación profesional."
      />
      <section className="panel medical-profile">
        <span className="medical-profile-icon">
          <Stethoscope size={38} />
        </span>
        <h2>{d.name}</h2>
        <p>{d.specialty}</p>
        <div className="medical-actions">
          {d.modalities.map((m) => (
            <span className="medical-count" key={m}>
              {m === "VIRTUAL" ? "Virtual" : "Presencial"}
            </span>
          ))}
        </div>
        <div className="notice">
          <ShieldCheck size={20} /> Nombre, especialidad y modalidades son
          administrados por VITALSYNC.
        </div>
        <form onSubmit={save}>
          <label>
            Biografía profesional · editable
            <textarea
              value={bio ?? d.bio}
              onChange={(e) => {
                setBio(e.target.value);
                setSaved(false);
              }}
              minLength={20}
              maxLength={2000}
              required
              rows={5}
            />
          </label>
          <ErrorBox error={error} />
          {saved && <p role="status">Biografía guardada correctamente.</p>}
          <Button disabled={busy || bio === null || bio.trim().length < 20}>
            {busy ? "Guardando…" : "Guardar biografía"}
          </Button>
        </form>
      </section>
    </div>
  );
}
interface AvailabilityData {
  read_only: boolean;
  slots: {
    id: number;
    starts_at: string;
    ends_at: string;
    modalities: string[];
    published: boolean;
  }[];
  blocks: { starts_at: string; ends_at: string; reason: string }[];
}
export function DoctorAvailability() {
  const [day, setDay] = useState(today);
  const q = useQuery({
    queryKey: ["doctor", "availability", day],
    queryFn: () => api<AvailabilityData>(prefix + "/availability?day=" + day),
  });
  return (
    <div className="medical-page">
      <PageTitle
        eyebrow="HORARIOS INSTITUCIONALES"
        title="Mi disponibilidad"
        description="Consulta los turnos y bloqueos de tu perfil profesional."
      />
      <section className="panel medical-filters">
        <label>
          Fecha
          <input
            type="date"
            value={day}
            required
            onChange={(e) => {
              if (e.target.value) setDay(e.target.value);
            }}
          />
        </label>
        <p>
          <ShieldCheck size={18} /> Solo lectura · Publicación y cambios a cargo
          de administración.
        </p>
      </section>
      <State pending={q.isPending} error={q.error}>
        <section className="panel medical-agenda">
          <h2>Horarios publicados</h2>
          {!q.data?.slots.length && (
            <Empty title="No hay horarios para esta fecha" />
          )}
          {q.data?.slots.map((s) => (
            <div className="medical-slot" key={s.id}>
              <Clock3 size={19} />
              <strong>
                {timeText(s.starts_at)} – {timeText(s.ends_at)}
              </strong>
              <span>
                {s.modalities
                  .map((m) => (m === "VIRTUAL" ? "Virtual" : "Presencial"))
                  .join(" · ")}
              </span>
              <Badge status={s.published ? "ACTIVE" : "INACTIVE"} />
            </div>
          ))}
        </section>
        <section className="panel medical-agenda">
          <h2>Bloqueos de agenda</h2>
          {!q.data?.blocks.length && <p>No hay bloqueos para esta fecha.</p>}
          {q.data?.blocks.map((b, i) => (
            <div className="notice" key={i}>
              <strong>
                {timeText(b.starts_at)} – {timeText(b.ends_at)}
              </strong>
              <p>{b.reason}</p>
            </div>
          ))}
        </section>
      </State>
    </div>
  );
}
export function DoctorRoom() {
  const { id } = useParams();
  const q = useQuery({
    queryKey: ["doctor", "room", id],
    queryFn: () =>
      api<MedicalAppointment>(prefix + "/appointments/" + id + "/teleconsult"),
    refetchInterval: 5000,
  });
  const refresh = useMedicalRefresh();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [reason, setReason] = useState("");
  async function act(event: string) {
    setBusy(true);
    setError(null);
    try {
      await post(prefix + "/appointments/" + id + "/teleconsult/events", {
        event,
        ...(reason.trim() ? { reason } : {}),
      });
      await refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const a = q.data;
  const state = a.virtual_state;
  const labels: Record<string, string> = {
    ADVANCE_DEMO_CLOCK: "Avanzar reloj de demostración",
    OPEN_ROOM: "Abrir sala simulada",
    PATIENT_JOIN: "Simular ingreso del paciente",
    DOCTOR_JOIN: "Ingresar como médico",
    START: "Iniciar atención simulada",
    FINALIZE: "Finalizar teleconsulta simulada",
    PATIENT_ABSENT: "Registrar ausencia del paciente",
    DOCTOR_ABSENT: "Simular ausencia médica",
    TECHNICAL_ERROR: "Simular incidencia técnica",
    RETRY: "Reintentar sala simulada",
  };
  return (
    <div className="medical-page">
      <Link className="text-link" to={prefix + "/appointments/" + id}>
        ← Volver al detalle
      </Link>
      <PageTitle
        eyebrow="SALA DE DEMOSTRACIÓN"
        title="Teleconsulta simulada"
        description={
          a.patient +
          " · " +
          dateText(a.starts_at) +
          " · " +
          timeText(a.starts_at)
        }
      />
      <section className="panel medical-room">
        <span className="medical-room-icon">
          <Monitor size={42} />
        </span>
        <h2>{a.patient}</h2>
        <Badge
          status={
            a.completion_source === "DEMO"
              ? "DEMO_COMPLETED"
              : (a.virtual_status ?? a.status)
          }
        />
        <p role="status">
          {a.virtual_status === "FINALIZADA"
            ? "La simulación finalizó y quedó guardada en el historial de ambos portales."
            : "Consulta las presencias y las acciones disponibles para el estado actual."}
        </p>
        <div className="medical-presences">
          <div>
            <Users size={23} />
            <span>Paciente</span>
            <strong>
              {state?.patient_present ? "Presente" : "En espera de ingreso"}
            </strong>
          </div>
          <div>
            <Stethoscope size={23} />
            <span>Médico</span>
            <strong>
              {state?.doctor_present ? "Presente" : "En espera de ingreso"}
            </strong>
          </div>
        </div>
        <div className="notice">
          Sin audio ni video. Esta simulación no acredita atención clínica real.
          La fecha reservada permanece sin cambios.
        </div>
        {!a.demo_mode && (
          <p>
            Las acciones simuladas están deshabilitadas fuera del modo
            demostración.
          </p>
        )}
        {state?.demo_clock_advanced && (
          <p>
            Reloj de demostración avanzado. La fecha y hora reservadas se
            conservaron.
          </p>
        )}
        {state?.incident_reason && <p role="status">{state.incident_reason}</p>}
        {a.demo_mode && !!state?.available_actions.length && (
          <>
            <label>
              Observación para ausencia o incidencia (opcional)
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={300}
              />
            </label>
            <div className="medical-actions">
              {state.available_actions.map((event) => (
                <Button
                  key={event}
                  disabled={busy}
                  variant={
                    event === "START" || event === "FINALIZE"
                      ? "default"
                      : "outline"
                  }
                  onClick={() => void act(event)}
                >
                  {labels[event]}
                </Button>
              ))}
            </div>
          </>
        )}
        <ErrorBox error={error} />
      </section>
      <History item={a} />
    </div>
  );
}
