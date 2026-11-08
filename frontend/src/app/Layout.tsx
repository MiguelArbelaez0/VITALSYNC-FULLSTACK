import { NavLink, Outlet, Link } from "react-router-dom";
import {
  Bell,
  CalendarDays,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { Logo, ErrorBox } from "../components/common";
const navigation = [
  { to: "/portal", icon: LayoutDashboard, label: "Inicio", end: true },
  { to: "/portal/doctors", icon: Search, label: "Buscar médicos" },
  { to: "/portal/appointments", icon: CalendarDays, label: "Mis citas" },
  { to: "/portal/plans", icon: ShieldCheck, label: "Mi plan" },
  { to: "/portal/notifications", icon: Bell, label: "Notificaciones" },
  { to: "/portal/profile", icon: UserRound, label: "Mi perfil" },
];
export function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  async function closeSession() {
    setLoggingOut(true);
    setLogoutError(null);
    try { await logout(); } catch (error) { setLogoutError(error); }
    finally { setLoggingOut(false); }
  }
  return (
    <div className="shell">
      <aside className={"sidebar " + (open ? "is-open" : "")}>
        <div className="sidebar-brand">
          <Logo />
          <button
            className="icon-button mobile-only"
            aria-label="Cerrar menú"
            onClick={() => setOpen(false)}
          >
            <X />
          </button>
        </div>
        <p className="nav-caption">ESPACIO DEL PACIENTE</p>
        <nav>
          {navigation.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                "nav-item " + (isActive ? "selected" : "")
              }
            >
              <n.icon size={20} />
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="care-note">
            <HeartPulse size={25} />
            <strong>Tu bienestar nos conecta</strong>
            <p>Un espacio para cuidar de ti, a tu ritmo.</p>
          </div>
          <ErrorBox error={logoutError}/>
          <button className="nav-item logout" disabled={loggingOut} onClick={() => void closeSession()}>
            <LogOut size={18} />
            Cerrar sesión
          </button>
          <small>© 2026 VITALSYNC</small>
        </div>
      </aside>
      {open && (
        <button
          className="menu-backdrop"
          aria-label="Cerrar navegación"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="main-area">
        <header className="topbar">
          <div className="topbar-label">
            <button
              className="icon-button mobile-only"
              aria-label="Abrir menú"
              onClick={() => setOpen(true)}
            >
              <Menu />
            </button>
            <span>Mi espacio de salud</span>
          </div>
          <div className="topbar-right">
            <span className="demo-dot">Entorno de demostración</span>
            <Link
              className="icon-button"
              to="/portal/notifications"
              aria-label="Ver notificaciones"
            >
              <Bell size={21} />
            </Link>
            <span className="divider" />
            <Link to="/portal/profile" className="user-chip">
              <span className="avatar small">
                {user?.name
                  .split(" ")
                  .map((s) => s[0])
                  .slice(0, 2)
                  .join("")}
              </span>
              <span>
                <strong>{user?.name}</strong>
                <small>Paciente</small>
              </span>
            </Link>
          </div>
        </header>
        <main className="page">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>VITALSYNC · Tu salud, en sintonía.</span>
          <span>
            <ShieldCheck size={13} />
            Sesión protegida
          </span>
        </footer>
      </div>
    </div>
  );
}
