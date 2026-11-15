import { Button } from "../../components/ui/button";
import {
  Table,
  State,
  button,
  account,
  recovery,
  type Context,
} from "./AdminCore";
export function PeopleAppointments({ c }: { c: Context }) {
  const { section, list, open, detail, go, can } = c;
  if (section === "doctors")
    return (
      <>
        <Table
          data={list.items}
          columns={[
            {
              key: "name",
              label: "Profesional",
              render: (r) => (
                <>
                  <strong>{r.name}</strong>
                  <small>
                    #{r.id} · {r.email ?? "Sin cuenta vinculada"}
                  </small>
                </>
              ),
            },
            { key: "specialty", label: "Especialidad" },
            {
              key: "enabled",
              label: "Estado",
              render: (r) => (
                <State state={r.enabled ? "ACTIVE" : "DISABLED"} />
              ),
            },
            { key: "active_appointments", label: "Citas activas" },
            { key: "appointments_total", label: "Citas totales" },
          ]}
          actions={(r) => (
            <>
              {button("Editar", () =>
                open({
                  title: "Editar médico",
                  path: `/doctors/${r.id}`,
                  fields: c.doctorFields,
                  initial: r,
                  method: "PATCH",
                  confirm: true,
                  description:
                    "Cambiar especialidad o retirar modalidades exige resolver las citas afectadas. Las reservas históricas mantienen sus datos.",
                }),
              )}
              {button("Citas", () =>
                go("/admin/appointments?doctor_id=" + r.id),
              )}
              {button("Horarios", () =>
                go("/admin/availability?doctor_id=" + r.id),
              )}
              {can("accounts") && (
                <>
                  {button(r.enabled ? "Desactivar" : "Activar", () =>
                    account(c, r),
                  )}
                  {button(
                    "Recuperar acceso",
                    () => recovery(c, r),
                    !r.user_id || !r.enabled,
                  )}
                </>
              )}
            </>
          )}
        />
        <section className="panel admin-section">
          <h2>Especialidades</h2>
          <div className="admin-actions">
            <Button
              variant="outline"
              onClick={() =>
                open({
                  title: "Crear especialidad",
                  path: "/specialties",
                  fields: [
                    {
                      key: "name",
                      label: "Nombre de especialidad",
                      min: 3,
                      max: 100,
                    },
                  ],
                })
              }
            >
              Crear especialidad
            </Button>
            {c.options?.specialties.map((s) => (
              <Button
                key={s.id}
                variant="outline"
                onClick={() =>
                  open({
                    title: "Editar especialidad",
                    path: "/specialties/" + s.id,
                    fields: [
                      {
                        key: "name",
                        label: "Nombre de especialidad",
                        min: 3,
                        max: 100,
                      },
                    ],
                    initial: s,
                    method: "PATCH",
                  })
                }
              >
                {s.name}
              </Button>
            ))}
          </div>
        </section>
      </>
    );
  if (section === "patients")
    return (
      <>
        <p className="admin-policy">
          Solo información administrativa. Las historias clínicas están
          reservadas al médico tratante autorizado.
        </p>
        <Table
          data={list.items}
          columns={[
            {
              key: "name",
              label: "Paciente",
              render: (r) => (
                <>
                  <strong>{r.name}</strong>
                  <small>
                    #{r.id} · {r.email}
                  </small>
                </>
              ),
            },
            { key: "document_masked", label: "Documento" },
            {
              key: "status",
              label: "Cuenta",
              render: (r) => <State state={r.status} />,
            },
            { key: "created_at", label: "Registro" },
          ]}
          actions={(r) => (
            <>
              {button("Ver información", () =>
                detail(
                  "Información administrativa del paciente",
                  `/patients/${r.id}`,
                ),
              )}
              {button("Citas", () =>
                go("/admin/appointments?patient_id=" + r.id),
              )}
              {can("accounts") && (
                <>
                  {button(
                    r.status === "ACTIVE" ? "Desactivar" : "Activar",
                    () => account(c, r),
                  )}
                  {button(
                    "Recuperar acceso",
                    () => recovery(c, r),
                    r.status !== "ACTIVE",
                  )}
                </>
              )}
            </>
          )}
        />
      </>
    );
  return (
    <Table
      data={list.items}
      columns={[
        {
          key: "code",
          label: "Cita",
          render: (r) => (
            <>
              <strong>{r.code}</strong>
              <small>
                #{r.id} · {r.patient}
              </small>
            </>
          ),
        },
        {
          key: "doctor",
          label: "Profesional",
          render: (r) => (
            <>
              {r.doctor}
              <small>{r.specialty}</small>
            </>
          ),
        },
        { key: "starts_at", label: "Fecha y hora" },
        {
          key: "modality",
          label: "Modalidad",
          render: (r) => <State state={r.modality} />,
        },
        {
          key: "status",
          label: "Estado",
          render: (r) => <State state={r.status} />,
        },
      ]}
      actions={(r) => (
        <>
          {button("Detalle y trazabilidad", () =>
            detail("Detalle administrativo de cita", `/appointments/${r.id}`),
          )}
          {r.status === "CONFIRMED" &&
            new Date(r.starts_at) > new Date() &&
            button("Cancelar cita", () =>
              open({
                title: "Cancelar cita",
                path: `/appointments/${r.id}/cancel`,
                fields: [],
                fixed: { version: r.version, confirmed: true },
                confirm: true,
                description:
                  "Se avisará al paciente y se conservarán la cita, el pago y su historial. No se realiza una devolución automática.",
              }),
            )}
          {r.status === "CANCELLED" &&
            button("Registrar reprogramación", () =>
              open({
                title: "Registrar reprogramación",
                path: `/appointments/${r.id}/reschedule`,
                fields: [
                  {
                    key: "replacement_id",
                    label: "Identificador de la nueva cita confirmada",
                    type: "number",
                    min: 1,
                  },
                ],
                confirm: true,
                description:
                  "El paciente debe confirmar primero una nueva reserva con su plan y copago correspondientes. Se vinculan ambas citas del mismo paciente, conservando sus condiciones y trazabilidad.",
              }),
            )}
        </>
      )}
    />
  );
}
