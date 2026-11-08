import type { ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CalendarDays,
  LoaderCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { statuses } from "../services/api";
import { Button } from "./ui/button";
export function Logo() {
  return (
    <Link to="/" className="logo">
      <span className="logo-symbol">
        <Activity size={25} />
      </span>
      VITAL<span>SYNC</span>
    </Link>
  );
}
export function Loading() {
  return (
    <div className="state" role="status">
      <LoaderCircle className="spin" /> Cargando tu información…
    </div>
  );
}
export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="alert error" role="alert">
      <AlertCircle size={19} />
      <span>{error instanceof Error ? error.message : String(error)}</span>
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="state empty">
      <CalendarDays size={34} />
      <h3>{title}</h3>
      {children}
    </div>
  );
}
export function Badge({ status }: { status: string }) {
  return (
    <span className={"badge badge-" + status.toLowerCase()}>
      {statuses[status] ?? status}
    </span>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        <span className="eyebrow">{eyebrow ?? "TU PORTAL DE BIENESTAR"}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Go({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Button asChild>
      <Link to={to}>
        {children}
        <ArrowRight size={17} />
      </Link>
    </Button>
  );
}
