import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Activity,
  CalendarDays,
  FileText,
  Pill,
  ShieldCheck,
  Stethoscope,
  Users,
} from "lucide-react";
import { api, dateText, timeText } from "../../services/api";
import { Empty, ErrorBox, Loading, PageTitle } from "../../components/common";
import { Button } from "../../components/ui/button";
import "./clinical.css";

export interface ClinicalVisitSummary {
  id: number;
  occurred_at: string;
  doctor: string;
  specialty: string;
  reason: string;
  diagnosis: string;
}
export interface ClinicalRecord {
  id: number;
  demo_marker: string;
  read_only: boolean;
  patient: {
    id: number;
    name: string;
    birth_date: string | null;
    age: number | null;
    demographic_note: string | null;
  };
  backgrounds: { category: string; description: string }[];
  allergies: { substance: string; reaction: string }[];
  medications: { name: string; note: string; status: string }[];
  encounters: ClinicalVisitSummary[];
}
interface ClinicalVisit extends ClinicalVisitSummary {
  patient_id: number;
  demo_marker: string;
  observations: string;
  recommendations: string;
  vitals: Record<string, number>;
}
const sections: Record<string, string> = {
  PERSONAL: "Antecedentes personales",
  FAMILY: "Antecedentes familiares",
  SURGICAL: "Antecedentes quirúrgicos",
  PREVIOUS_DISEASE: "Enfermedades previas",
};

export function DoctorClinicalHistory() {
  const { id } = useParams();
  const [specialty, setSpecialty] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const detailRef = useRef<HTMLElement>(null);
  const q = useQuery({
    queryKey: ["doctor", "clinical-history", id],
    queryFn: () =>
      api<ClinicalRecord>(`/doctor/patients/${id}/clinical-history`),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
  const visit = useQuery({
    queryKey: ["doctor", "clinical-visit", id, selected],
    queryFn: () =>
      api<ClinicalVisit>(
        `/doctor/patients/${id}/clinical-history/encounters/${selected}`,
      ),
    enabled: selected !== null && !q.error,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
  useEffect(() => {
    setSelected(null);
    setSpecialty("");
  }, [id]);
  useEffect(() => {
    if (visit.data) detailRef.current?.focus();
  }, [visit.data]);
  if (q.isPending) return <Loading />;
  if (q.error)
    return (
      <div className="medical-page">
        <Link className="text-link" to="/doctor/patients">
          ← Volver a mis pacientes
        </Link>
        <PageTitle
          title="Historia clínica"
          description="Consulta reservada al médico tratante autorizado."
        />
        <ErrorBox error={q.error} />
      </div>
    );
  const h = q.data;
  const encounters = h.encounters.filter(
    (e) => !specialty || e.specialty === specialty,
  );
  const specialties = [...new Set(h.encounters.map((e) => e.specialty))];
  const diagnoses = [...new Set(h.encounters.map((e) => e.diagnosis))];
  return (
    <div className="medical-page clinical-page">
      <Link className="text-link" to="/doctor/patients">
        ← Volver a mis pacientes
      </Link>
      <PageTitle
        eyebrow="CONSULTA CLÍNICA ACADÉMICA"
        title="Historia clínica"
        description={h.patient.name + " · Paciente #" + h.patient.id}
      />
      <div className="clinical-demo-label" role="note">
        <ShieldCheck size={23} />
        <div>
          <strong>{h.demo_marker}</strong>
          <p>
            Entorno académico. Solo lectura. Estos registros no acreditan una
            atención médica real.
          </p>
        </div>
      </div>
      <section className="panel clinical-summary">
        <span className="clinical-icon">
          <FileText size={31} />
        </span>
        <div>
          <h2>{h.patient.name}</h2>
          <p>Identificador interno #{h.patient.id}</p>
        </div>
        <div>
          <small>Edad registrada</small>
          <strong>
            {h.patient.age === null ? "No registrada" : `${h.patient.age} años`}
          </strong>
        </div>
        <div>
          <small>Fecha de nacimiento</small>
          <strong>{h.patient.birth_date ?? "No registrada"}</strong>
        </div>
        {h.patient.demographic_note && (
          <p className="clinical-demographics">{h.patient.demographic_note}</p>
        )}
      </section>
      <section
        aria-label="Antecedentes clínicos"
        className="clinical-backgrounds"
      >
        {h.backgrounds.map((b) => (
          <article className="panel" key={b.category}>
            <span className="clinical-mini-icon">
              <Users size={20} />
            </span>
            <h2>{sections[b.category] ?? b.category}</h2>
            <p>{b.description}</p>
          </article>
        ))}
      </section>
      <div className="clinical-two-columns">
        <section className="panel clinical-section">
          <h2>
            <Activity size={21} />
            Alergias conocidas
          </h2>
          {h.allergies.length ? (
            h.allergies.map((a) => (
              <article className="clinical-item" key={a.substance}>
                <strong>{a.substance}</strong>
                <p>{a.reaction}</p>
              </article>
            ))
          ) : (
            <p>No registradas en este escenario ficticio.</p>
          )}
        </section>
        <section className="panel clinical-section">
          <h2>
            <Pill size={21} />
            Medicamentos registrados
          </h2>
          {h.medications.map((m) => (
            <article className="clinical-item" key={m.name}>
              <span className="clinical-tag">
                {m.status === "CURRENT"
                  ? "Actual · ficticio"
                  : "Anterior · ficticio"}
              </span>
              <strong>{m.name}</strong>
              <p>{m.note}</p>
            </article>
          ))}
        </section>
      </div>
      <section className="panel clinical-section">
        <h2>
          <Stethoscope size={21} />
          Diagnósticos anteriores ficticios
        </h2>
        <div className="clinical-diagnoses">
          {diagnoses.map((d) => (
            <span key={d}>{d}</span>
          ))}
        </div>
      </section>
      <section className="panel clinical-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">REGISTROS ACADÉMICOS ANTERIORES</span>
            <h2>Historial de consultas</h2>
            <p>
              Más recientes primero. No se crearon reservas ni se marcaron citas
              reales como atendidas.
            </p>
          </div>
          <label>
            Filtrar consultas por especialidad
            <select
              aria-label="Filtrar consultas por especialidad"
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
            >
              <option value="">Todas las especialidades</option>
              {specialties.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>
        {encounters.length ? (
          <div className="clinical-visits">
            {encounters.map((e) => (
              <article key={e.id}>
                <span className="clinical-mini-icon">
                  <CalendarDays size={22} />
                </span>
                <div>
                  <h3>{e.specialty}</h3>
                  <p>
                    {dateText(e.occurred_at)} · {e.doctor}
                  </p>
                  <strong>{e.reason}</strong>
                  <small>{e.diagnosis}</small>
                </div>
                <Button variant="outline" onClick={() => setSelected(e.id)}>
                  Ver detalle de consulta del {dateText(e.occurred_at)}
                </Button>
              </article>
            ))}
          </div>
        ) : (
          <Empty title="No hay consultas para esta selección" />
        )}
      </section>
      {selected !== null && (
        <section
          className="panel clinical-section clinical-visit-detail"
          ref={detailRef}
          tabIndex={-1}
          aria-label="Detalle de consulta seleccionada"
        >
          <h2>Detalle de consulta</h2>
          {visit.isPending ? (
            <Loading />
          ) : visit.error ? (
            <ErrorBox error={visit.error} />
          ) : (
            visit.data && (
              <>
                <span className="clinical-tag">{visit.data.demo_marker}</span>
                <p>
                  {dateText(visit.data.occurred_at)} ·{" "}
                  {timeText(visit.data.occurred_at)} · {visit.data.specialty} ·{" "}
                  {visit.data.doctor}
                </p>
                <dl>
                  <div>
                    <dt>Motivo de consulta</dt>
                    <dd>{visit.data.reason}</dd>
                  </div>
                  <div>
                    <dt>Observaciones médicas ficticias</dt>
                    <dd>{visit.data.observations}</dd>
                  </div>
                  <div>
                    <dt>Diagnóstico ficticio</dt>
                    <dd>{visit.data.diagnosis}</dd>
                  </div>
                  <div>
                    <dt>Recomendaciones simuladas</dt>
                    <dd>{visit.data.recommendations}</dd>
                  </div>
                </dl>
                <h3>Signos vitales simulados</h3>
                <div className="clinical-vitals">
                  <div>
                    <small>Presión arterial</small>
                    <strong>
                      {visit.data.vitals.systolic}/{visit.data.vitals.diastolic}{" "}
                      <span>mmHg</span>
                    </strong>
                  </div>
                  <div>
                    <small>Pulso</small>
                    <strong>
                      {visit.data.vitals.heart_rate} <span>lpm</span>
                    </strong>
                  </div>
                  <div>
                    <small>Temperatura</small>
                    <strong>
                      {visit.data.vitals.temperature_c} <span>°C</span>
                    </strong>
                  </div>
                  <div>
                    <small>Saturación</small>
                    <strong>
                      {visit.data.vitals.spo2} <span>%</span>
                    </strong>
                  </div>
                </div>
              </>
            )
          )}
        </section>
      )}
      <p className="clinical-access-note">
        <ShieldCheck size={17} />
        Cada consulta de la historia y sus detalles queda registrada en
        auditoría con el usuario y la fecha.
      </p>
    </div>
  );
}
