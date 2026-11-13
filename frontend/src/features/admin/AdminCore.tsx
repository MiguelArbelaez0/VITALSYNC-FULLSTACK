import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, dateText, timeText, statuses } from "../../services/api";
import { Loading, ErrorBox, Empty } from "../../components/common";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
export type Row = Record<string, any>;
export type Choice = { value: string | number; label: string };
export type Field = {
  key: string;
  label: string;
  type?: string;
  options?: Choice[];
  required?: boolean;
  min?: number;
  max?: number;
  wide?: boolean;
};
export type Modal = {
  title: string;
  path: string;
  fields: Field[];
  initial?: Row;
  fixed?: Row;
  method?: string;
  description?: string;
  confirm?: boolean;
};
export type Collection = {
  items: Row[];
  total: number;
  page: number;
  pages: number;
};
export type Options = { doctors: Row[]; specialties: Row[]; scopes: string[] };
export type Context = {
  section: string;
  resource: string;
  options: Options | undefined;
  list: Collection;
  data: Row;
  userId: number | undefined;
  open: (m: Modal) => void;
  detail: (title: string, path: string) => void;
  go: (path: string) => void;
  can: (scope: string) => boolean;
  doctorFields: Field[];
  planFields: Field[];
  slotFields: Field[];
};
export const modes: Choice[] = [
  { value: "VIRTUAL", label: "Virtual" },
  { value: "PRESENCIAL", label: "Presencial" },
];
export const scopes: Record<string, string> = {
  dashboard: "Dashboard",
  doctors: "Médicos",
  patients: "Pacientes",
  appointments: "Citas",
  availability: "Disponibilidad",
  plans: "Planes",
  payments: "Pagos",
  refunds: "Devoluciones",
  audit: "Auditoría",
  settings: "Configuración",
  accounts: "Cuentas y permisos",
};
const states: Record<string, string> = {
  ...statuses,
  DISABLED: "Deshabilitado",
  ACTIVE: "Activo",
  REQUESTED: "Solicitada",
  REVIEWING: "En revisión",
  AUTHORIZED: "Autorizada",
  PROCESSED: "Procesada (simulada)",
  FAILED: "Fallida",
  ISSUED: "Enlace emitido",
  USED: "Utilizado",
  REVOKED: "Revocado",
  PENDING: "Pendiente",
  APPROVED: "Aprobado",
  REJECTED: "Rechazado",
  VIRTUAL: "Virtual",
  PRESENCIAL: "Presencial",
  PLAN: "Plan",
  COPAY: "Copago",
};
const labels: Record<string, string> = {
  id: "Identificador",
  name: "Nombre",
  email: "Correo",
  role: "Rol",
  status: "Estado",
  created_at: "Fecha",
  starts_at: "Inicio",
  ends_at: "Fin",
  doctor: "Médico",
  patient: "Paciente",
  specialty: "Especialidad",
  plan: "Plan",
  modality: "Modalidad",
  amount: "Importe",
  copay: "Copago",
  version: "Versión",
  reason: "Motivo",
  actor_id: "Usuario responsable",
  author_id: "Usuario responsable",
  action: "Operación",
  resource: "Recurso",
  entity_id: "Registro",
  phone: "Teléfono",
  document_type: "Tipo de documento",
  document_number: "Documento",
  document_masked: "Documento protegido",
  subscription: "Suscripción",
  appointments: "Citas",
  notifications: "Notificaciones administrativas",
  history: "Historial",
  administrative_history: "Operaciones administrativas",
  revisions: "Versiones",
  terms: "Condiciones conservadas",
  expires_at: "Vencimiento",
  subscriptions: "Contrataciones",
  benefits: "Beneficios",
  restrictions: "Restricciones informativas",
  price: "Precio",
  duration_days: "Vigencia en días",
  modalities: "Modalidades",
  specialty_ids: "Especialidades",
  copays: "Copagos por modalidad",
  consultation_limit: "Consultas por contratación",
  enabled: "Habilitado",
  reference: "Referencia",
  read: "Leída",
  message: "Mensaje",
  details: "Trazabilidad",
  before: "Anterior",
  after: "Nuevo",
  previous_id: "Cita anterior",
  replacement_id: "Nueva cita",
  reschedule: "Reprogramación",
  payment_id: "Pago",
  hold_id: "Retención",
  kind: "Concepto",
  patient_id: "Paciente #",
  doctor_id: "Médico #",
  completion_source: "Origen de finalización",
  clinically_attended: "Atención clínica real",
  cancellation_reason: "Motivo de cancelación",
  cancelled_by: "Cancelado por",
  previous_status: "Estado anterior",
  origin: "Procedencia",
  contracted_at: "Contratación",
  recorded_at: "Registro",
  catalog_enabled: "Disponible para nuevas compras",
  policy: "Política",
};
export function value(v: any): string {
  if (v === null || v === undefined || v === "") return "No registrado";
  if (typeof v === "boolean") return v ? "Sí" : "No";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v))
    return dateText(v) + " · " + timeText(v);
  return states[String(v)] ?? String(v);
}
export function State({ state }: { state: any }) {
  return <span className="admin-status">{value(state)}</span>;
}
export function Tree({ data }: { data: any }) {
  if (data === null || typeof data !== "object") return <>{value(data)}</>;
  if (Array.isArray(data))
    return data.length ? (
      <ul className="admin-history">
        {data.map((item, index) => (
          <li key={item?.id ?? index}>
            <Tree data={item} />
          </li>
        ))}
      </ul>
    ) : (
      <p>No hay registros.</p>
    );
  return (
    <dl>
      {Object.entries(data)
        .filter(
          ([key]) => !["available_actions", "operation_key"].includes(key),
        )
        .map(([key, v]) => (
          <div key={key}>
            <dt>{labels[key] ?? key.replaceAll("_", " ")}</dt>
            <dd>
              {typeof v === "object" && v !== null ? (
                <Tree data={v} />
              ) : (
                value(v)
              )}
            </dd>
          </div>
        ))}
    </dl>
  );
}
export type Column = {
  key: string;
  label: string;
  render?: (row: Row) => ReactNode;
};
export function Table({
  data,
  columns,
  actions,
}: {
  data: Row[];
  columns: Column[];
  actions?: (row: Row) => ReactNode;
}) {
  return data.length ? (
    <div className="panel admin-table-wrap">
      <table className="admin-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
            {actions && <th>Acciones</th>}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.id ?? row.user_id}>
              {columns.map((c) => (
                <td key={c.key} data-label={c.label}>
                  <div>{c.render ? c.render(row) : value(row[c.key])}</div>
                </td>
              ))}
              {actions && (
                <td data-label="Acciones">
                  <div className="admin-actions">{actions(row)}</div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <Empty title="No hay resultados para estos filtros" />
  );
}
export const button = (name: string, run: () => void, disabled = false) => (
  <Button variant="outline" onClick={run} disabled={disabled}>
    {name}
  </Button>
);
export function recovery(c: Context, r: Row) {
  c.open({
    title: "Solicitar recuperación privada",
    path: `/accounts/${r.user_id ?? r.id}/recovery`,
    fields: [],
    confirm: true,
    description:
      "La contraseña actual no cambia. El operador emitirá un enlace de un solo uso mediante el comando local documentado.",
  });
}
export function account(c: Context, r: Row) {
  c.open({
    title:
      r.status === "DISABLED" || r.account_status === "DISABLED"
        ? "Activar cuenta"
        : "Desactivar cuenta",
    path: `/accounts/${r.user_id ?? r.id}/status`,
    fields: [],
    method: "PATCH",
    fixed: {
      status:
        r.status === "DISABLED" || r.account_status === "DISABLED"
          ? "ACTIVE"
          : "DISABLED",
    },
    confirm: true,
    description:
      "Se revocan las sesiones al desactivar. Debes resolver antes las citas y retenciones activas; el servidor indicará los registros afectados.",
  });
}
export function FormModal({
  spec,
  close,
  saved,
}: {
  spec: Modal;
  close: () => void;
  saved: () => void;
}) {
  const [values, setValues] = useState<Row>(() => {
    const initial = { ...spec.initial };
    for (const f of spec.fields) {
      const v = initial[f.key];
      if (f.type === "datetime-local" && v && /Z|[+-]\d{2}:\d{2}$/.test(v))
        initial[f.key] = new Date(v)
          .toLocaleString("sv-SE", { timeZone: "America/Bogota" })
          .replace(" ", "T")
          .slice(0, 16);
    }
    return initial;
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const fields = [
    ...spec.fields,
    {
      key: "reason",
      label: "Motivo de la operación",
      type: "textarea",
      min: 6,
      max: 1000,
      wide: true,
    } as Field,
  ];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const body: Row = { ...spec.fixed };
    for (const f of fields) {
      let v = values[f.key];
      if (f.type === "number")
        v = v === "" || v === undefined || v === null ? null : Number(v);
      if (f.type === "datetime-local")
        v = v ? new Date(v + "-05:00").toISOString() : null;
      if (f.type === "checkbox") v = !!v;
      if (f.type === "multi") v = v ?? [];
      if (f.type === "multi" && f.required !== false && !v.length) {
        setError(new Error("Selecciona una opción en " + f.label));
        return;
      }
      body[f.key] = v === null ? null : (v ?? "");
    }
    setBusy(true);
    try {
      await api("/admin" + spec.path, {
        method: spec.method ?? "POST",
        body: JSON.stringify(body),
      });
      saved();
    } catch (e) {
      setError(
        e instanceof TypeError
          ? new Error(
              "No pudimos conectar. Consulta el estado antes de repetir la operación.",
            )
          : e,
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o && !busy) close();
      }}
      title={spec.title}
      description={
        spec.description ??
        "La operación se valida en el servidor y queda auditada. Se conservan los registros históricos."
      }
    >
      <form className="admin-modal-form" onSubmit={submit}>
        <div className="admin-fields">
          {fields.map((f) => {
            const current = values[f.key];
            if (f.type === "multi")
              return (
                <fieldset key={f.key}>
                  <legend>{f.label}</legend>
                  {f.options?.map((o) => (
                    <label key={o.value}>
                      <input
                        type="checkbox"
                        checked={(current ?? []).includes(o.value)}
                        onChange={(e) =>
                          setValues({
                            ...values,
                            [f.key]: e.target.checked
                              ? [...(current ?? []), o.value]
                              : (current ?? []).filter(
                                  (v: any) => v !== o.value,
                                ),
                          })
                        }
                      />
                      {o.label}
                    </label>
                  ))}
                </fieldset>
              );
            if (f.type === "checkbox")
              return (
                <label key={f.key} className="admin-checkbox wide">
                  <input
                    type="checkbox"
                    checked={!!current}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.checked })
                    }
                  />
                  {f.label}
                </label>
              );
            let shown = current ?? "";
            if (
              f.type === "datetime-local" &&
              shown &&
              /Z|[+-]\d{2}:\d{2}$/.test(shown)
            )
              shown = new Date(shown)
                .toLocaleString("sv-SE", { timeZone: "America/Bogota" })
                .replace(" ", "T")
                .slice(0, 16);
            return (
              <label key={f.key} className={f.wide ? "wide" : ""}>
                {f.label}
                {f.type === "textarea" ? (
                  <textarea
                    required={f.required !== false}
                    minLength={f.min}
                    maxLength={f.max ?? 4000}
                    value={shown}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.value })
                    }
                  />
                ) : f.options ? (
                  <select
                    required={f.required !== false}
                    value={shown}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.value })
                    }
                  >
                    <option value="">Seleccionar</option>
                    {f.options.map((o) => (
                      <option value={o.value} key={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={f.type ?? "text"}
                    required={f.required !== false}
                    min={f.type === "number" ? f.min : undefined}
                    max={f.type === "number" ? f.max : undefined}
                    minLength={f.type !== "number" ? f.min : undefined}
                    maxLength={f.type !== "number" ? (f.max ?? 254) : undefined}
                    value={shown}
                    onChange={(e) =>
                      setValues({ ...values, [f.key]: e.target.value })
                    }
                  />
                )}
              </label>
            );
          })}
        </div>
        {spec.confirm && (
          <label className="admin-checkbox admin-confirm">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            Confirmo la operación y sus consecuencias indicadas.
          </label>
        )}
        <ErrorBox error={error} />
        <div className="admin-actions">
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={close}
          >
            Volver sin guardar
          </Button>
          <Button disabled={busy || (spec.confirm && !confirmed)}>
            {busy ? "Guardando…" : "Confirmar y guardar"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
export function Detail({
  spec,
  close,
}: {
  spec: { title: string; path: string };
  close: () => void;
}) {
  const q = useQuery({
    queryKey: ["admin", "detail", spec.path],
    queryFn: () => api<Row>("/admin" + spec.path),
    retry: false,
    gcTime: 0,
  });
  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) close();
      }}
      title={spec.title}
      description="Información administrativa. Este portal no permite consultar datos clínicos."
    >
      <div className="admin-detail">
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <ErrorBox error={q.error} />
        ) : (
          <Tree data={q.data} />
        )}
      </div>
    </Dialog>
  );
}
