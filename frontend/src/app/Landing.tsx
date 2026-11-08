import {
  ArrowRight,
  CalendarCheck2,
  HeartPulse,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Logo } from "../components/common";
import { Button } from "../components/ui/button";
export function Landing() {
  return (
    <div className="landing">
      <header>
        <Logo />
        <nav>
          <a href="#como-funciona">Cómo funciona</a>
          <Button variant="outline" asChild>
            <Link to="/login">Iniciar sesión</Link>
          </Button>
          <Button asChild>
            <Link to="/register">Crear mi cuenta</Link>
          </Button>
        </nav>
      </header>
      <main>
        <section className="landing-hero">
          <div>
            <span className="eyebrow">TU SALUD, EN SINTONÍA</span>
            <h1>
              Cuidarte se siente
              <br />
              mejor cuando
              <br />
              <em>estamos conectados.</em>
            </h1>
            <p>
              Encuentra especialistas, elige tu plan y gestiona tus citas en un
              solo lugar. Más cerca de ti, en cada etapa.
            </p>
            <div className="button-row">
              <Button asChild>
                <Link to="/register">
                  Comenzar a cuidarme
                  <ArrowRight size={18} />
                </Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/login">Ya tengo una cuenta</Link>
              </Button>
            </div>
            <span className="landing-note">
              <ShieldCheck size={17} />
              Portal de demostración · Sin pagos reales
            </span>
          </div>
          <div className="landing-visual">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <HeartPulse className="landing-heart" />
            <div className="floating-card">
              <span className="stat-icon teal">
                <CalendarCheck2 />
              </span>
              <div>
                <strong>Un espacio para tu bienestar</strong>
                <p>Tu próxima consulta comienza aquí.</p>
              </div>
            </div>
            <span className="landing-plus">+</span>
          </div>
        </section>
        <section className="landing-steps" id="como-funciona">
          <span className="eyebrow">SIMPLE, CERCANO, CONTIGO</span>
          <h2>Tu bienestar, paso a paso.</h2>
          <div>
            {[
              {
                icon: ShieldCheck,
                title: "Elige tu plan",
                text: "Activa la cobertura que se adapta a ti con un pago simulado.",
              },
              {
                icon: Search,
                title: "Encuentra tu especialista",
                text: "Consulta perfiles y horarios publicados de nuestros médicos.",
              },
              {
                icon: CalendarCheck2,
                title: "Agenda y gestiona",
                text: "Confirma tu cita, guarda el comprobante y consulta tu historial.",
              },
            ].map((x, i) => (
              <article key={x.title}>
                <span className="step-number">0{i + 1}</span>
                <x.icon />
                <h3>{x.title}</h3>
                <p>{x.text}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
      <footer>
        <Logo />
        <p>Plataforma académica · Datos ficticios · Bogotá, Colombia</p>
      </footer>
    </div>
  );
}
