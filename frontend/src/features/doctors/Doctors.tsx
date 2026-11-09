import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import {
  CalendarDays,
  Clock3,
  MapPin,
  Monitor,
  Search,
  ShieldCheck,
} from "lucide-react";
import { api, post, dateText, dayKey, timeText } from "../../services/api";
import type { Doctor, Specialty, Slot, Hold, Membership, Modality } from "../../types";
import {
  Empty,
  ErrorBox,
  Go,
  Loading,
  PageTitle,
} from "../../components/common";
import { Button } from "../../components/ui/button";
export function Doctors() {
  const [search, setSearch] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [searchParams] = useSearchParams();
  const initialModality = searchParams.get("modality");
  const [modality, setModality] = useState<Modality>(initialModality === "PRESENCIAL" ? "PRESENCIAL" : "VIRTUAL");
  const q = useQuery({
    queryKey: ["doctors", search, specialty, modality],
    queryFn: () =>
      api<Doctor[]>(
        "/doctors?search=" +
          encodeURIComponent(search) +
          (specialty ? "&specialty_id=" + specialty : "") +
          "&modality=" + modality,
      ),
  });
  const s = useQuery({
    queryKey: ["specialties"],
    queryFn: () => api<Specialty[]>("/specialties"),
  });
  return (
    <>
      <PageTitle
        title="El cuidado que necesitas"
        description="Encuentra al profesional que te acompañará en tu próximo paso."
      />
      <section className="modality-picker" aria-label="Modalidad de atención">
        <h2>¿Qué modalidad de atención necesitas?</h2>
        <div className="modality-options">
          <button aria-pressed={modality === "VIRTUAL"} className={modality === "VIRTUAL" ? "selected recommended-modality" : "recommended-modality"} onClick={() => setModality("VIRTUAL")}><Monitor/><span><strong>Consulta virtual <em>Recomendada</em></strong><small>Teleconsulta virtual simulada, sin audio ni video</small></span></button>
          <button aria-pressed={modality === "PRESENCIAL"} className={modality === "PRESENCIAL" ? "selected" : ""} onClick={() => setModality("PRESENCIAL")}><MapPin/><span><strong>Consulta presencial</strong><small>Atención en sede VITALSYNC (ficticia)</small></span></button>
        </div>
      </section>
      <div className="filters">
        <label className="search-field">
          <Search size={20} />
          <input
            aria-label="Buscar médico"
            placeholder="Buscar por nombre del médico…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
        <select
          aria-label="Filtrar por especialidad"
          value={specialty}
          onChange={(e) => setSpecialty(e.target.value)}
        >
          <option value="">Todas las especialidades</option>
          {s.data?.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </select>
      </div>
      <ErrorBox error={s.error} />
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : !q.data.length ? (
        <Empty title="No encontramos médicos con estos filtros">
          <p>Prueba con otro nombre o especialidad.</p>
          <Button
            variant="outline"
            onClick={() => {
              setSearch("");
              setSpecialty("");
            }}
          >
            Limpiar filtros
          </Button>
        </Empty>
      ) : (
        <>
          <p className="results-count">
            {q.data.length} profesionales para acompañarte
          </p>
          <div className="doctors-grid">
            {q.data.map((d, i) => (
              <article className="doctor-card panel" key={d.id}>
                <div className={"doctor-portrait portrait-" + (i % 5)}>
                  <span>
                    {d.name
                      .split(" ")
                      .slice(1, 3)
                      .map((n) => n[0])
                      .join("")}
                  </span>
                  <ShieldCheck size={24} />
                </div>
                <div className="doctor-info">
                  <span className="eyebrow">{d.specialty}</span>
                  <h2>{d.name}</h2>
                  <p>
                    {modality === "VIRTUAL" ? <Monitor size={15} /> : <MapPin size={15} />}
                    {modality === "VIRTUAL" ? "Teleconsulta virtual simulada" : "Bogotá · Consulta presencial"}
                  </p>
                  <div className="doctor-modalities" role="group" aria-label={"Modalidades de " + d.name}>
                    {d.modalities.includes("VIRTUAL") && <span><Monitor size={14} /> Virtual</span>}
                    {d.modalities.includes("PRESENCIAL") && <span><MapPin size={14} /> Presencial</span>}
                  </div>
                  <p className="doctor-summary">
                    Atención cercana y personalizada para tu bienestar.
                  </p>
                  <Go to={"/portal/doctors/" + d.id + "?modality=" + modality}>
                    Ver perfil y disponibilidad
                  </Go>
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </>
  );
}
export function DoctorProfile() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const initialModality = searchParams.get("modality");
  const [modality, setModality] = useState<Modality>(initialModality === "PRESENCIAL" ? "PRESENCIAL" : "VIRTUAL");
  const navigate = useNavigate();
  const client = useQueryClient();
  const [day, setDay] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const d = useQuery({
    queryKey: ["doctor", id],
    queryFn: () => api<Doctor>("/doctors/" + id),
  });
  const slots = useQuery({
    queryKey: ["availability", id, modality],
    queryFn: () => api<Slot[]>("/doctors/" + id + "/availability?modality=" + modality),
    refetchInterval: 20_000,
  });
  const plan = useQuery({
    queryKey: ["my-plan"],
    queryFn: () => api<Membership>("/my-plan"),
  });
  const days = [...new Set(slots.data?.map((s) => dayKey(s.starts_at)))];
  const activeDay = day || days[0] || "";
  const activePlanDoesNotCover = plan.data?.status === "ACTIVE" && (
    !plan.data.plan?.specialty_ids?.includes(d.data?.specialty_id ?? -1) ||
    !plan.data.plan?.modalities?.includes(modality)
  );
  async function reserve() {
    if (!selected) return;
    setError(null);
    setBusy(true);
    try {
      const h = await post<Hold>("/holds", { availability_id: selected, modality });
      await client.invalidateQueries({ queryKey: ["availability"] });
      navigate("/portal/booking/" + h.id);
    } catch (e) {
      setError(e);
      void slots.refetch();
    } finally {
      setBusy(false);
    }
  }
  if (d.isPending) return <Loading />;
  if (d.error) return <ErrorBox error={d.error} />;
  return (
    <>
      <Link className="text-link back-link" to="/portal/doctors">
        ← Volver al directorio
      </Link>
      <PageTitle
        eyebrow={d.data.specialty}
        title={d.data.name}
        description="Un espacio de atención pensado para ti."
      />
      <div className="booking-grid">
        <section className="panel doctor-about">
          <span className="avatar xlarge">
            {d.data.name
              .split(" ")
              .slice(1, 3)
              .map((s) => s[0])
              .join("")}
          </span>
          <h2>Conoce a tu especialista</h2>
          <p>{d.data.bio}</p>
          {modality === "PRESENCIAL" && <div className="info-line"><MapPin />Sede VITALSYNC · Bogotá (ficticia)</div>}
          <div className="info-line">
            <Clock3 />
            {modality === "VIRTUAL" ? "Cita virtual simulada · 30 minutos" : "Consulta presencial · 30 minutos"}
          </div>
          <div className="notice">
            <strong>Profesional de demostración</strong>
            <p>
              Los perfiles y horarios son ficticios y están publicados en la
              base de datos para el ejercicio académico.
            </p>
          </div>
        </section>
        <section className="panel availability-panel">
          <div className="modality-toggle" aria-label="Modalidad de atención">
            <button disabled={!d.data.modalities?.includes("VIRTUAL")} aria-pressed={modality === "VIRTUAL"} className={modality === "VIRTUAL" ? "selected recommended-modality" : "recommended-modality"} onClick={() => {setModality("VIRTUAL"); setSelected(null)}}><Monitor size={17}/> Virtual · Recomendada</button>
            <button disabled={!d.data.modalities?.includes("PRESENCIAL")} aria-pressed={modality === "PRESENCIAL"} className={modality === "PRESENCIAL" ? "selected" : ""} onClick={() => {setModality("PRESENCIAL"); setSelected(null)}}><MapPin size={17}/> Presencial</button>
          </div>
          <div className="section-heading">
            <h2>
              <CalendarDays size={22} />
              Selecciona tu horario
            </h2>
          </div>
          <p>
            Hora local de Bogotá (UTC−5). La disponibilidad se verifica al
            reservar.
          </p>
          <ErrorBox error={slots.error || plan.error} />
          {plan.data?.status !== "ACTIVE" && (
            <div className="notice">
              <strong>
                {plan.data?.status === "EXPIRED"
                  ? "Tu plan ha vencido. Debes renovarlo para continuar"
                  : "Debes activar tu plan para solicitar una cita médica"}
              </strong>
              <Link to="/portal/plans">Consultar y activar mi plan →</Link>
            </div>
          )}
          {plan.data?.status === "ACTIVE" && !plan.data.plan?.specialty_ids?.includes(d.data.specialty_id) && (
            <div className="alert error">
              Tu plan actual no incluye esta especialidad. <Link to="/portal/plans">Ver planes</Link>
            </div>
          )}
          {plan.data?.status === "ACTIVE" && plan.data.plan?.specialty_ids?.includes(d.data.specialty_id) && !plan.data.plan?.modalities?.includes(modality) && (
            <div className="alert error">
              {modality === "VIRTUAL"
                ? "Tu plan actual no incluye consultas virtuales. Puedes cambiar a un plan con esta modalidad."
                : "Tu plan actual no incluye consultas presenciales. Puedes cambiar a un plan con esta modalidad."}{" "}
              <Link to="/portal/plans">Ver planes</Link>
            </div>
          )}
          {slots.isPending ? (
            <Loading />
          ) : days.length === 0 ? (
            <Empty title="No hay jornadas publicadas">
              <Go to="/portal/doctors">Elegir otro médico</Go>
            </Empty>
          ) : (
            <>
              <label>
                Fecha de consulta
                <select
                  aria-label="Fecha de consulta"
                  value={activeDay}
                  onChange={(e) => {
                    setDay(e.target.value);
                    setSelected(null);
                  }}
                >
                  {days.map((day) => (
                    <option key={day} value={day}>
                      {dateText(day + "T12:00:00-05:00")}
                    </option>
                  ))}
                </select>
              </label>
              <div className="time-slots">
                {slots.data
                  ?.filter((s) => dayKey(s.starts_at) === activeDay)
                  .map((s) => (
                    <button
                      key={s.id}
                      disabled={!s.available}
                      aria-pressed={selected === s.id}
                      onClick={() => setSelected(s.id)}
                      className={
                        "time-slot " + (selected === s.id ? "chosen" : "")
                      }
                    >
                      {timeText(s.starts_at)}
                      {!s.available && <small>No disponible</small>}
                    </button>
                  ))}
              </div>
              <div className="slot-legend">
                <span /> Disponible <span className="unavailable" /> Ocupado o
                bloqueado
              </div>
              <ErrorBox error={error} />
              <Button
                className="full"
                disabled={!selected || busy || activePlanDoesNotCover}
                onClick={() => void reserve()}
              >
                {busy
                  ? "Verificando disponibilidad…"
                  : "Retener horario y continuar"}
              </Button>
              <small className="muted">
                La retención es temporal. Tu cita se confirma en el siguiente
                paso.
              </small>
            </>
          )}
        </section>
      </div>
    </>
  );
}
