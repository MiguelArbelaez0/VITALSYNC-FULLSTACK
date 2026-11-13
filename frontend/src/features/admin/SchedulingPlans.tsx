import {
  Table,
  State,
  button,
  modes,
  type Context,
  type Row,
  type Modal,
} from "./AdminCore";
import { money } from "../../services/api";
import { Button } from "../../components/ui/button";
export function editPlan(c: Context, row?: Row) {
  c.open({
    title: row ? "Editar plan" : "Crear plan",
    path: row ? `/plans/${row.id}` : "/plans",
    fields: c.planFields,
    initial: row
      ? {
          ...row,
          virtual_copay: row.copays?.VIRTUAL,
          onsite_copay: row.copays?.PRESENCIAL,
        }
      : {
          price: 0,
          copay: 0,
          duration_days: 30,
          enabled: true,
          modalities: ["PRESENCIAL"],
          specialty_ids: [],
        },
    fixed: { version: row?.version ?? 1 },
    method: row ? "PATCH" : "POST",
    confirm: true,
    description:
      "Las suscripciones vigentes conservan sus condiciones. Los cambios aplican a nuevas compras y renovaciones; los pagos y reservas históricos mantienen sus importes.",
  });
}
export function ScheduleActions({ c }: { c: Context }) {
  const doctorChoices =
    c.options?.doctors.map((d) => ({ value: d.id, label: d.name })) ?? [];
  const schedule: Modal = {
    title: "Publicar jornada",
    path: "/schedules",
    fields: [
      {
        key: "doctor_id",
        label: "Médico",
        type: "number",
        options: doctorChoices,
      },
      { key: "first_day", label: "Primer día", type: "date" },
      { key: "last_day", label: "Último día", type: "date" },
      { key: "start_time", label: "Hora inicial · Bogotá", type: "time" },
      { key: "end_time", label: "Hora final · Bogotá", type: "time" },
      {
        key: "minutes",
        label: "Minutos por consulta",
        type: "number",
        options: [15, 20, 30, 45, 60].map((n) => ({
          value: n,
          label: String(n),
        })),
      },
      {
        key: "weekdays",
        label: "Días incluidos",
        type: "multi",
        options: [
          "Lunes",
          "Martes",
          "Miércoles",
          "Jueves",
          "Viernes",
          "Sábado",
          "Domingo",
        ].map((label, i) => ({ value: i, label })),
      },
      {
        key: "modalities",
        label: "Modalidades",
        type: "multi",
        options: modes,
      },
      {
        key: "published",
        label: "Publicada (desmarcar: borrador)",
        type: "checkbox",
      },
    ],
    initial: {
      start_time: "09:00",
      end_time: "10:00",
      minutes: 30,
      weekdays: [0, 1, 2, 3, 4],
      modalities: ["VIRTUAL", "PRESENCIAL"],
      published: true,
    },
    confirm: true,
    description:
      "Hasta 31 días con turnos sin solapamientos. Un conflicto revierte la jornada completa.",
  };
  return (
    <div className="admin-actions">
      <Button
        onClick={() =>
          c.open({
            title: "Crear turno",
            path: "/availability",
            fields: c.slotFields,
            initial: { published: true, modalities: ["VIRTUAL", "PRESENCIAL"] },
          })
        }
      >
        Crear turno
      </Button>
      <Button variant="outline" onClick={() => c.open(schedule)}>
        Publicar jornada
      </Button>
      <Button
        variant="outline"
        onClick={() =>
          c.open({
            title: "Bloquear intervalo futuro",
            path: "/blocks",
            fields: c.slotFields.filter(
              (f) => !["modalities", "published"].includes(f.key),
            ),
            confirm: true,
            description:
              "Resuelve primero las citas y retenciones afectadas. Los turnos se conservan al bloquear y liberar fechas.",
          })
        }
      >
        Bloquear fechas
      </Button>
    </div>
  );
}
export function SchedulingPlans({ c }: { c: Context }) {
  if (c.section === "plans")
    return (
      <>
        <p className="admin-policy">
          El catálogo nuevo conserva las condiciones ya contratadas. La
          cobertura se valida por especialidad, modalidad, vigencia, cupo y
          copago. Los textos de beneficios y restricciones son informativos; las
          reglas ejecutables tienen campos específicos.
        </p>
        <Table
          data={c.list.items}
          columns={[
            {
              key: "name",
              label: "Plan",
              render: (r) => (
                <>
                  <strong>{r.name}</strong>
                  <small>
                    #{r.id} · versión {r.version}
                  </small>
                </>
              ),
            },
            { key: "price", label: "Precio", render: (r) => money(r.price) },
            {
              key: "copays",
              label: "Copagos",
              render: (r) => (
                <>
                  Virtual: {money(r.copays.VIRTUAL)}
                  <small>Presencial: {money(r.copays.PRESENCIAL)}</small>
                </>
              ),
            },
            {
              key: "modalities",
              label: "Cobertura",
              render: (r) => r.modalities.join(" · "),
            },
            {
              key: "enabled",
              label: "Catálogo",
              render: (r) => (
                <State state={r.enabled ? "ACTIVE" : "DISABLED"} />
              ),
            },
            { key: "subscribers", label: "Suscripciones vigentes" },
          ]}
          actions={(r) => (
            <>
              {button("Editar", () => editPlan(c, r))}
              {button("Versiones y suscripciones", () =>
                c.detail("Condiciones e historial del plan", `/plans/${r.id}`),
              )}
            </>
          )}
        />
      </>
    );
  return (
    <>
      <p className="admin-policy">
        Un solapamiento, cita o retención incompatible impide el cambio.
        Despublicar conserva el turno como borrador. Liberar un bloqueo conserva
        su historial.
      </p>
      <Table
        data={c.list.items}
        columns={[
          { key: "id", label: "Registro" },
          { key: "doctor", label: "Médico" },
          { key: "starts_at", label: "Inicio · Bogotá" },
          { key: "ends_at", label: "Fin · Bogotá" },
          c.resource === "blocks"
            ? { key: "released", label: "Liberado" }
            : { key: "published", label: "Publicado" },
        ]}
        actions={(r) =>
          c.resource === "blocks"
            ? button(
                "Liberar bloqueo",
                () =>
                  c.open({
                    title: "Liberar bloqueo",
                    path: `/blocks/${r.id}/release`,
                    fields: [],
                    confirm: true,
                    description:
                      "El registro histórico se conserva; el horario volverá a evaluarse para reservas.",
                  }),
                r.released,
              )
            : button(
                "Editar turno",
                () =>
                  c.open({
                    title: "Editar turno futuro",
                    path: `/availability/${r.id}`,
                    fields: c.slotFields,
                    initial: r,
                    method: "PATCH",
                    confirm: true,
                    description:
                      "No se puede mover ni retirar silenciosamente una reserva confirmada. Resuelve primero las citas y retenciones afectadas.",
                  }),
                new Date(r.starts_at) <= new Date(),
              )
        }
      />
    </>
  );
}
