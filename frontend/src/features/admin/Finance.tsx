import { Table, State, button, value, type Context } from "./AdminCore";
import { money } from "../../services/api";
export function Finance({ c }: { c: Context }) {
  if (c.resource === "payments")
    return (
      <>
        <p className="admin-policy">
          Pagos exclusivamente simulados. Los importes originales permanecen
          inmutables. Conciliar exige un resultado definitivo y motivo. La
          devolución se gestiona separadamente y requiere autorización.
        </p>
        <Table
          data={c.list.items}
          columns={[
            {
              key: "reference",
              label: "Referencia",
              render: (r) => (
                <>
                  <strong>{r.reference}</strong>
                  <small>{r.patient}</small>
                </>
              ),
            },
            {
              key: "kind",
              label: "Concepto",
              render: (r) => (
                <>
                  {value(r.kind)}
                  <small>
                    {r.plan_id
                      ? "Plan #" + r.plan_id
                      : "Retención #" + r.hold_id}
                  </small>
                </>
              ),
            },
            { key: "amount", label: "Importe", render: (r) => money(r.amount) },
            {
              key: "status",
              label: "Estado",
              render: (r) => <State state={r.status} />,
            },
            { key: "created_at", label: "Fecha" },
          ]}
          actions={(r) => (
            <>
              {button("Historial de pago", () =>
                c.detail("Historial del pago simulado", `/payments/${r.id}`),
              )}
              {["PENDING", "IN_RECONCILIATION"].includes(r.status) &&
                button("Conciliar", () =>
                  c.open({
                    title: "Conciliar pago simulado",
                    path: `/payments/${r.id}/reconcile`,
                    fields: [
                      {
                        key: "status",
                        label: "Resultado",
                        options: [
                          { value: "APPROVED", label: "Aprobado" },
                          { value: "REJECTED", label: "Rechazado" },
                        ],
                      },
                    ],
                    confirm: true,
                    description:
                      "Un pago definitivo no cambia arbitrariamente. Se conservan las validaciones económicas de plan, disponibilidad y copago.",
                  }),
                )}
              {c.can("refunds") &&
                r.status === "APPROVED" &&
                r.amount > 0 &&
                !r.refund_id &&
                button("Solicitar devolución", () =>
                  c.open({
                    title: "Solicitar devolución simulada",
                    path: "/refunds",
                    fields: [],
                    fixed: {
                      payment_id: r.id,
                      operation_key: crypto.randomUUID(),
                    },
                    confirm: true,
                    description:
                      "Requiere una cita cancelada para copagos o una suscripción inactiva para planes. La revisión y autorización son obligatorias. No se transfieren fondos reales.",
                  }),
                )}
            </>
          )}
        />
      </>
    );
  return (
    <>
      <p className="admin-policy">
        Solicitud → Revisión → Aprobación o rechazo → Autorización →
        Procesamiento simulado o fallo definitivo. Un pago admite una sola
        solicitud. Cada paso exige motivo y versión vigentes.
      </p>
      <Table
        data={c.list.items}
        columns={[
          {
            key: "id",
            label: "Solicitud",
            render: (r) => (
              <>
                <strong>Devolución #{r.id}</strong>
                <small>
                  Pago #{r.payment_id} · {r.patient}
                </small>
              </>
            ),
          },
          { key: "amount", label: "Importe", render: (r) => money(r.amount) },
          {
            key: "status",
            label: "Estado",
            render: (r) => <State state={r.status} />,
          },
          { key: "created_at", label: "Fecha" },
        ]}
        actions={(r) => (
          <>
            {button("Historial de devolución", () =>
              c.detail("Historial de devolución simulada", `/refunds/${r.id}`),
            )}
            {r.available_actions.length > 0 &&
              button("Gestionar solicitud", () =>
                c.open({
                  title: "Gestionar devolución simulada",
                  path: `/refunds/${r.id}/transition`,
                  fields: [
                    {
                      key: "status",
                      label: "Siguiente paso",
                      options: r.available_actions.map((v: string) => ({
                        value: v,
                        label: value(v),
                      })),
                    },
                  ],
                  initial: { status: r.available_actions[0] },
                  fixed: {
                    version: r.version,
                    operation_key: crypto.randomUUID(),
                  },
                  confirm: true,
                  description:
                    "Solo se permiten las transiciones indicadas para el estado actual. El procesamiento es académico y conserva el pago original y su historial.",
                }),
              )}
          </>
        )}
      />
    </>
  );
}
