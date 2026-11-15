import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { RefreshCw, Plus } from "lucide-react";
import { api } from "../../services/api";
import { PageTitle, Loading, ErrorBox, Empty } from "../../components/common";
import { Button } from "../../components/ui/button";
import { useAuth } from "../../hooks/useAuth";
import {
  FormModal,
  Detail,
  Table,
  button,
  value,
  modes,
  type Modal,
  type Context,
  type Collection,
  type Options,
  type Choice,
} from "./AdminCore";
import { PeopleAppointments } from "./PeopleAppointments";
import { SchedulingPlans, ScheduleActions, editPlan } from "./SchedulingPlans";
import { Finance } from "./Finance";
import { Configuration } from "./Configuration";
import { fields } from "./adminFields";
import "./admin.css";
const titles: Record<string, string> = {
  dashboard: "Dashboard administrativo",
  doctors: "Médicos",
  patients: "Pacientes",
  appointments: "Citas",
  availability: "Disponibilidad médica",
  plans: "Planes",
  payments: "Pagos y devoluciones",
  audit: "Auditoría administrativa",
  configuration: "Configuración",
};
const metrics: Record<string, string> = {
  patients_total: "Total de pacientes",
  patients_active: "Pacientes activos",
  patients_inactive: "Pacientes inactivos",
  doctors_total: "Total de médicos",
  doctors_active: "Médicos activos",
  doctors_inactive: "Médicos inactivos",
  pending_holds: "Retenciones pendientes",
  appointments_confirmed: "Citas confirmadas",
  appointments_virtual: "Citas virtuales",
  appointments_onsite: "Citas presenciales",
  appointments_completed: "Citas finalizadas",
  appointments_cancelled: "Citas canceladas",
  plans_active: "Planes activos en catálogo",
  subscriptions_active: "Suscripciones vigentes",
  payments_approved: "Pagos aprobados",
  payments_rejected: "Pagos rechazados",
  payments_pending: "Pagos pendientes o en conciliación",
  refund_requests: "Solicitudes de devolución",
};
function Chart({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const max = Math.max(1, ...Object.values(data));
  return (
    <section className="panel admin-chart">
      <h2>{title}</h2>
      {Object.keys(data).length ? (
        Object.entries(data).map(([label, count]) => (
          <div className="admin-bar" key={label}>
            <span>{value(label)}</span>
            <span className="admin-bar-track">
              <i style={{ width: Math.round((count / max) * 100) + "%" }} />
            </span>
            <strong>{count}</strong>
          </div>
        ))
      ) : (
        <p>Sin registros en este período.</p>
      )}
    </section>
  );
}
export default function AdminPortal() {
  const { section = "dashboard" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const { user } = useAuth();
  const [modal, setModal] = useState<Modal | null>(null);
  const [detail, setDetail] = useState<{ title: string; path: string } | null>(
    null,
  );
  const [notice, setNotice] = useState("");
  const tab = params.get("tab") ?? "";
  const resource =
    section === "configuration"
      ? "settings"
      : section === "payments" && tab === "refunds"
        ? "refunds"
        : section === "availability" && tab === "blocks"
          ? "blocks"
          : section === "audit" && tab === "legacy"
            ? "audit/legacy"
            : section;
  const opts = useQuery({
    queryKey: ["admin", "options"],
    queryFn: () => api<Options>("/admin/options"),
    retry: false,
  });
  const query = params.toString();
  const q = useQuery({
    queryKey: ["admin", resource, query],
    queryFn: () => api<any>("/admin/" + resource + (query ? "?" + query : "")),
    enabled: !!titles[section],
    retry: false,
    refetchInterval: 15000,
  });
  useEffect(() => {
    setModal(null);
    setDetail(null);
    setNotice("");
  }, [section, tab]);
  function filter(key: string, v: string) {
    const next = new URLSearchParams(params);
    if (v) next.set(key, v);
    else next.delete(key);
    next.delete("page");
    setParams(next);
  }
  function success() {
    setModal(null);
    setNotice("Operación guardada y registrada en auditoría.");
    void client.invalidateQueries();
  }
  const list: Collection = q.data?.items
    ? q.data
    : { items: [], total: 0, page: 1, pages: 1 };
  const c: Context = {
    section,
    resource,
    options: opts.data,
    list,
    data: q.data,
    userId: user?.id,
    open: setModal,
    detail: (title, path) => setDetail({ title, path }),
    go: navigate,
    can: (scope) => opts.data?.scopes.includes(scope) ?? false,
    ...fields(opts.data),
  };
  const choiceFilter = (key: string, label: string, choices: Choice[]) => (
    <label>
      {label}
      <select
        value={params.get(key) ?? ""}
        onChange={(e) => filter(key, e.target.value)}
      >
        <option value="">Todos</option>
        {choices.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
  const doctorChoices =
    opts.data?.doctors.map((d) => ({ value: d.id, label: d.name })) ?? [];
  const specialtyChoices =
    opts.data?.specialties.map((s) => ({ value: s.id, label: s.name })) ?? [];
  const tabButtons = (pairs: [string, string][]) => (
    <div className="tabs" role="tablist">
      {pairs.map(([key, label]) => (
        <button
          key={key}
          role="tab"
          aria-selected={tab === key}
          onClick={() => setParams(key ? { tab: key } : {})}
        >
          {label}
        </button>
      ))}
    </div>
  );
  let content: ReactNode;
  if (q.isPending) content = <Loading />;
  else if (q.error)
    content = (
      <>
        <ErrorBox error={q.error} />
        <Button variant="outline" onClick={() => void q.refetch()}>
          Reintentar consulta
        </Button>
      </>
    );
  else if (section === "dashboard")
    content = (
      <>
        <div className="admin-metrics">
          {Object.entries(q.data.metrics as Record<string, number>).map(
            ([key, count]) => (
              <article className="panel admin-metric" key={key}>
                <span>{metrics[key] ?? key}</span>
                <strong>{count.toLocaleString("es-CO")}</strong>
              </article>
            ),
          )}
        </div>
        <div className="admin-charts">
          <Chart title="Modalidad de las citas" data={q.data.modalities} />
          <Chart
            title="Estados de las citas"
            data={q.data.appointment_states}
          />
        </div>
        <p className="admin-policy">
          Los filtros de fecha aplican a citas, pagos y devoluciones. Las
          cuentas y suscripciones describen el estado actual. Las retenciones
          pendientes aún no son citas confirmadas.
        </p>
      </>
    );
  else if (["doctors", "patients", "appointments"].includes(section))
    content = <PeopleAppointments c={c} />;
  else if (["availability", "plans"].includes(section))
    content = <SchedulingPlans c={c} />;
  else if (section === "payments") content = <Finance c={c} />;
  else if (section === "configuration") content = <Configuration c={c} />;
  else
    content = (
      <>
        <Table
          data={list.items}
          columns={[
            { key: "id", label: "Evento" },
            { key: "action", label: "Operación" },
            { key: "actor_id", label: "Usuario responsable" },
            { key: "resource", label: "Recurso" },
            { key: "entity_id", label: "Registro" },
            { key: "created_at", label: "Fecha" },
          ]}
          actions={
            resource === "audit"
              ? (r) =>
                  button("Ver trazabilidad", () =>
                    c.detail("Trazabilidad del evento", "/audit-event/" + r.id),
                  )
              : undefined
          }
        />
        <p className="admin-policy">
          Este visor no expone contenido clínico, contraseñas ni tokens.
        </p>
      </>
    );
  if (!titles[section])
    return <Empty title="Sección administrativa no encontrada" />;
  return (
    <div className="admin-page">
      <PageTitle
        eyebrow="GESTIÓN INTEGRADA · ENTORNO ACADÉMICO"
        title={titles[section]}
        description="Administra la operación de VITALSYNC. La información clínica permanece reservada al médico tratante."
        action={
          <div className="admin-actions">
            <Button
              variant="outline"
              onClick={() =>
                void client.invalidateQueries({ queryKey: ["admin"] })
              }
            >
              <RefreshCw size={16} />
              Actualizar
            </Button>
            {section === "doctors" && c.can("accounts") && (
              <Button
                onClick={() =>
                  c.open({
                    title: "Registrar médico",
                    path: "/doctors",
                    fields: [
                      c.doctorFields[0],
                      {
                        key: "email",
                        label: "Correo individual",
                        type: "email",
                      },
                      ...c.doctorFields.slice(1),
                    ],
                    initial: {
                      enabled: true,
                      modalities: ["VIRTUAL", "PRESENCIAL"],
                    },
                    description:
                      "Se creará una cuenta individual y una solicitud de recuperación privada. No se publican contraseñas en la aplicación.",
                  })
                }
              >
                <Plus size={16} />
                Registrar médico
              </Button>
            )}
            {section === "plans" && (
              <Button onClick={() => editPlan(c)}>
                <Plus size={16} />
                Crear plan
              </Button>
            )}
          </div>
        }
      />
      {notice && (
        <div className="alert success" role="status">
          {notice}
        </div>
      )}
      {section === "payments" &&
        tabButtons([
          ["", "Pagos simulados"],
          ["refunds", "Devoluciones simuladas"],
        ])}
      {section === "availability" && (
        <>
          {tabButtons([
            ["", "Turnos y jornadas"],
            ["blocks", "Bloqueos de fechas"],
          ])}
          <ScheduleActions c={c} />
        </>
      )}
      {section === "audit" &&
        tabButtons([
          ["", "Operaciones administrativas"],
          ["legacy", "Trazabilidad previa"],
        ])}
      {section !== "configuration" && (
        <section
          className="panel admin-toolbar"
          aria-label="Filtros administrativos"
        >
          {[
            "doctors",
            "patients",
            "appointments",
            "plans",
            "payments",
            "audit",
          ].includes(section) &&
            resource !== "refunds" &&
            resource !== "audit/legacy" && (
              <label className="admin-search">
                {section === "patients"
                  ? "Buscar por nombre, correo o documento"
                  : "Buscar"}
                <input
                  type="search"
                  value={params.get("search") ?? ""}
                  onChange={(e) => filter("search", e.target.value)}
                  placeholder="Escribe para buscar"
                />
              </label>
            )}
          {["appointments", "availability"].includes(section) &&
            choiceFilter("doctor_id", "Médico", doctorChoices)}
          {["doctors", "appointments"].includes(section) &&
            choiceFilter("specialty_id", "Especialidad", specialtyChoices)}
          {section === "doctors" &&
            choiceFilter("enabled", "Estado del profesional", [
              { value: "true", label: "Activo" },
              { value: "false", label: "Inactivo" },
            ])}
          {section === "patients" &&
            choiceFilter("status", "Estado de cuenta", [
              { value: "ACTIVE", label: "Activo" },
              { value: "DISABLED", label: "Inactivo" },
            ])}
          {section === "appointments" && (
            <>
              {choiceFilter("modality", "Modalidad", modes)}
              {choiceFilter(
                "status",
                "Estado",
                [
                  "CONFIRMED",
                  "IN_PROGRESS",
                  "ATTENDED",
                  "CANCELLED",
                  "PATIENT_ABSENT",
                  "DOCTOR_ABSENT",
                  "TECHNICAL_ERROR",
                ].map((v) => ({ value: v, label: value(v) })),
              )}
            </>
          )}
          {["appointments", "availability"].includes(section) && (
            <label>
              Fecha · Bogotá
              <input
                type="date"
                value={params.get("day") ?? ""}
                onChange={(e) => filter("day", e.target.value)}
              />
            </label>
          )}
          {section === "availability" &&
            resource !== "blocks" &&
            choiceFilter("published", "Publicación", [
              { value: "true", label: "Publicado" },
              { value: "false", label: "Borrador" },
            ])}
          {section === "payments" &&
            choiceFilter(
              "status",
              "Estado",
              (resource === "refunds"
                ? [
                    "REQUESTED",
                    "REVIEWING",
                    "APPROVED",
                    "REJECTED",
                    "AUTHORIZED",
                    "PROCESSED",
                    "FAILED",
                  ]
                : ["APPROVED", "REJECTED", "PENDING", "IN_RECONCILIATION"]
              ).map((v) => ({ value: v, label: value(v) })),
            )}
          {["dashboard", "audit"].includes(section) &&
            resource !== "audit/legacy" && (
              <>
                <label>
                  Desde
                  <input
                    type="date"
                    value={params.get("since") ?? ""}
                    onChange={(e) => filter("since", e.target.value)}
                  />
                </label>
                <label>
                  Hasta
                  <input
                    type="date"
                    value={params.get("until") ?? ""}
                    onChange={(e) => filter("until", e.target.value)}
                  />
                </label>
              </>
            )}
          {section === "audit" && resource !== "audit/legacy" && (
            <label>
              Usuario responsable #
              <input
                type="number"
                min="1"
                value={params.get("actor_id") ?? ""}
                onChange={(e) => filter("actor_id", e.target.value)}
              />
            </label>
          )}
        </section>
      )}
      {opts.error && <ErrorBox error={opts.error} />}
      <div aria-live="polite">
        {q.isFetching && !q.isPending && <small>Actualizando registros…</small>}
      </div>
      {content}
      {list.pages > 1 && (
        <div className="admin-pagination">
          <Button
            variant="outline"
            disabled={list.page <= 1}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set("page", String(list.page - 1));
              setParams(next);
            }}
          >
            Anterior
          </Button>
          <span>
            Página {list.page} de {list.pages} · {list.total} registros
          </span>
          <Button
            variant="outline"
            disabled={list.page >= list.pages}
            onClick={() => {
              const next = new URLSearchParams(params);
              next.set("page", String(list.page + 1));
              setParams(next);
            }}
          >
            Siguiente
          </Button>
        </div>
      )}
      {modal && (
        <FormModal
          key={modal.path + modal.title}
          spec={modal}
          close={() => setModal(null)}
          saved={success}
        />
      )}{" "}
      {detail && (
        <Detail key={detail.path} spec={detail} close={() => setDetail(null)} />
      )}
    </div>
  );
}
