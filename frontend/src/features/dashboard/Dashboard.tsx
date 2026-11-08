import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarDays,
  Clock3,
  HeartPulse,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, dateText, timeText } from "../../services/api";
import type { DashboardData } from "../../types";
import {
  Badge,
  Empty,
  ErrorBox,
  Go,
  Loading,
  PageTitle,
} from "../../components/common";
export function Dashboard() {
  const q = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/dashboard"),
  });
  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const d = q.data;
  return (
    <>
      <PageTitle
        eyebrow="UN BUEN DÍA PARA CUIDARTE"
        title={`Hola, ${d.name.split(" ")[0]} 👋`}
        description="Tu bienestar tiene un lugar aquí. ¿Cómo podemos acompañarte hoy?"
      />
      <section className="welcome-card">
        <div>
          <span className="light-label">
            <span className="live-dot" />
            CONECTAMOS CONTIGO
          </span>
          <h2>
            Más cerca de una
            <br />
            vida saludable.
          </h2>
          <p>
            Encuentra a tu especialista y agenda tu próxima
            <br className="desktop-only" /> consulta, sin complicaciones.
          </p>
          <Go to="/portal/doctors">Buscar un especialista</Go>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="heart-center">
            <HeartPulse />
          </div>
          <span className="art-pill pill-one">
            <ShieldCheck size={21} />
            Cuidado que acompaña
          </span>
          <span className="art-pill pill-two">
            <CalendarDays size={21} />A tu tiempo
          </span>
          <span className="art-cross">+</span>
          <span className="art-dot" />
        </div>
      </section>
      <div className="stats-grid">
        <Link to="/portal/plans" className="stat-card">
          <span className="stat-icon teal">
            <ShieldCheck />
          </span>
          <div>
            <p>Tu plan de salud</p>
            <strong>{d.plan.plan?.name ?? "Aún sin plan"}</strong>
            <span>
              {d.plan.expires_at
                ? "Vence el " + dateText(d.plan.expires_at)
                : "Activa tu acceso al bienestar"}
            </span>
          </div>
          <Badge status={d.plan.status} />
        </Link>
        <Link to="/portal/appointments" className="stat-card">
          <span className="stat-icon blue">
            <CalendarDays />
          </span>
          <div>
            <p>Citas próximas</p>
            <strong>{d.upcoming_count.toString().padStart(2, "0")}</strong>
            <span>Tu agenda, siempre a mano</span>
          </div>
        </Link>
        <Link to="/portal/notifications" className="stat-card">
          <span className="stat-icon violet">
            <Sparkles />
          </span>
          <div>
            <p>Notificaciones</p>
            <strong>
              {d.unread_notifications.toString().padStart(2, "0")}
            </strong>
            <span>Novedades por leer</span>
          </div>
        </Link>
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="section-heading">
            <h2>Tu próxima cita</h2>
            <Link to="/portal/appointments">
              Ver todas <ArrowRight size={16} />
            </Link>
          </div>
          {d.next_appointment ? (
            <div className="next-appointment">
              <span className="avatar large">
                {d.next_appointment.doctor
                  .split(" ")
                  .slice(1, 3)
                  .map((s) => s[0])
                  .join("")}
              </span>
              <div>
                <Badge status={d.next_appointment.status} />
                <h3>{d.next_appointment.doctor}</h3>
                <p>{d.next_appointment.specialty}</p>
                <div className="appointment-meta">
                  <span>
                    <CalendarDays size={16} />
                    {dateText(d.next_appointment.starts_at)}
                  </span>
                  <span>
                    <Clock3 size={16} />
                    {timeText(d.next_appointment.starts_at)}
                  </span>
                </div>
                <Go to={"/portal/appointments/" + d.next_appointment.id}>
                  Ver mi cita
                </Go>
              </div>
            </div>
          ) : (
            <Empty title="Tu próxima cita comienza aquí">
              <p>
                Reserva un espacio para tu salud.
                <br />
                Encuentra al profesional indicado para ti.
              </p>
              <Go to="/portal/doctors">Agendar mi primera cita</Go>
            </Empty>
          )}
        </section>
        <section className="panel quick-panel">
          <div className="section-heading">
            <h2>A un clic de cuidarte</h2>
          </div>
          {[
            {
              to: "/portal/doctors",
              icon: Search,
              title: "Encuentra tu especialista",
              text: "Explora nuestro directorio médico",
            },
            {
              to: "/portal/plans",
              icon: ShieldCheck,
              title: "Conoce tu cobertura",
              text: "Un plan para cada etapa de tu vida",
            },
            {
              to: "/portal/profile",
              icon: HeartPulse,
              title: "Tu información, al día",
              text: "Consulta y actualiza tu perfil",
            },
          ].map((a) => (
            <Link className="quick-link" to={a.to} key={a.to}>
              <span className="quick-icon">
                <a.icon size={21} />
              </span>
              <span>
                <strong>{a.title}</strong>
                <small>{a.text}</small>
              </span>
              <ArrowRight size={18} />
            </Link>
          ))}
          <div className="wellness-note">
            <span>UN PEQUEÑO RECORDATORIO</span>
            <p>
              Cuidarte también es hacer una pausa.
              <br />
              Tu bienestar empieza con pequeños pasos.
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
