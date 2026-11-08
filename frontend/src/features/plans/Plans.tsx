import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, ShieldCheck } from "lucide-react";
import { api, post, dateText, money, statuses } from "../../services/api";
import type { Plan, Membership, Specialty, Payment, Config } from "../../types";
import { Badge, ErrorBox, Loading, PageTitle } from "../../components/common";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
export function PaymentControls({
  kind,
  targetId,
  onApproved,
}: {
  kind: "PLAN" | "COPAY";
  targetId: number;
  onApproved: () => void;
}) {
  const client = useQueryClient();
  const config = useQuery({
    queryKey: ["config"],
    queryFn: () => api<Config>("/config"),
  });
  const q = useQuery({
    queryKey: ["payments"],
    queryFn: () => api<Payment[]>("/payments"),
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [latest, setLatest] = useState<Payment | null>(null);
  const pending = q.data?.find(
    (p) =>
      p.kind === kind &&
      (kind === "PLAN" ? p.plan_id === targetId : p.hold_id === targetId) &&
      ["PENDING", "IN_RECONCILIATION"].includes(p.status),
  );
  const approved =
    kind === "COPAY"
      ? q.data?.find((p) => p.hold_id === targetId && p.status === "APPROVED")
      : undefined;
  async function pay(status: string) {
    setBusy(true);
    setError(null);
    try {
      const p = await post<Payment>("/payments", {
        kind,
        target_id: targetId,
        status,
        idempotency_key: key,
      });
      setLatest(p);
      setKey(crypto.randomUUID());
      await client.invalidateQueries();
      if (p.status === "APPROVED") onApproved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function reconcile(status: string) {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const p = await post<Payment>("/payments/" + pending.id + "/reconcile", {
        status,
      });
      setLatest(p);
      await client.invalidateQueries();
      if (p.status === "APPROVED") onApproved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (config.isPending || q.isPending) return <Loading />;
  if (config.error || q.error)
    return <ErrorBox error={config.error || q.error} />;
  if (!config.data?.demo_mode)
    return (
      <div className="notice">
        Los pagos de demostración están deshabilitados.
      </div>
    );
  if (approved)
    return (
      <div className="alert success">
        <Check />
        Copago aprobado · Transacción #{approved.id}
      </div>
    );
  return (
    <div className="payment-controls">
      <div className="notice">
        <strong>Pago simulado · Sin cargos reales</strong>
        <p>
          No ingreses datos bancarios. Autoriza un resultado para esta operación
          académica.
        </p>
      </div>
      {pending ? (
        <>
          <Badge status={pending.status} />
          <p>
            Transacción #{pending.id}. Concilia el resultado antes de iniciar
            otro pago.
          </p>
          <div className="button-row">
            <Button disabled={busy} onClick={() => void reconcile("APPROVED")}>
              Conciliar como aprobado
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void reconcile("REJECTED")}
            >
              Conciliar como rechazado
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="button-row">
            <Button disabled={busy} onClick={() => void pay("APPROVED")}>
              Autorizar y simular aprobación
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void pay("REJECTED")}
            >
              Simular rechazo
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void pay("PENDING")}
            >
              Simular pendiente
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void pay("IN_RECONCILIATION")}
            >
              Simular en conciliación
            </Button>
          </div>
          {latest && (
            <div
              className={
                "alert " + (latest.status === "REJECTED" ? "error" : "success")
              }
              role="status"
            >
              Transacción #{latest.id}: {statuses[latest.status]}.{" "}
              {latest.status === "REJECTED"
                ? "Puedes volver a intentarlo."
                : ""}
            </div>
          )}
        </>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
export function Plans() {
  const [selected, setSelected] = useState<Plan | null>(null);
  const [success, setSuccess] = useState(false);
  const q = useQuery({
    queryKey: ["plans"],
    queryFn: () => api<Plan[]>("/plans"),
  });
  const m = useQuery({
    queryKey: ["my-plan"],
    queryFn: () => api<Membership>("/my-plan"),
  });
  const s = useQuery({
    queryKey: ["specialties"],
    queryFn: () => api<Specialty[]>("/specialties"),
  });
  return (
    <>
      <PageTitle
        title="Un plan para cuidar de ti"
        description="Elige la cobertura que acompaña tu momento de vida. Valores en pesos colombianos."
      />
      {success && (
        <div className="alert success" role="status">
          <Check />
          Tu plan se activó correctamente. Ya puedes buscar un horario;
          verificaremos de nuevo la disponibilidad.
        </div>
      )}
      {m.isPending ? (
        <Loading />
      ) : m.error ? (
        <ErrorBox error={m.error} />
      ) : (
        <section className="membership-banner">
          <span className="stat-icon teal">
            <ShieldCheck />
          </span>
          <div>
            <span className="eyebrow">TU COBERTURA ACTUAL</span>
            <h2>{m.data.plan?.name ?? "Tu bienestar comienza con un plan"}</h2>
            <p>
              {m.data.expires_at
                ? "Vigencia hasta el " + dateText(m.data.expires_at)
                : "Activa un plan para solicitar tus citas médicas."}
            </p>
          </div>
          <Badge status={m.data.status} />
        </section>
      )}
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : (
        <div className="plans-grid">
          {q.data.map((p, i) => (
            <article
              className={"plan-card panel " + (i === 1 ? "featured" : "")}
              key={p.id}
            >
              {i === 1 && (
                <span className="plan-ribbon">MÁS COBERTURA PARA TI</span>
              )}
              <ShieldCheck className="plan-icon" />
              <h2>{p.name}</h2>
              <p>{p.description}</p>
              <div className="price">
                {money(p.price)}
                <small>/ {p.duration_days} días</small>
              </div>
              <span className="copay-line">
                {p.copay
                  ? "Copago por cita: " + money(p.copay)
                  : "Sin copagos por consulta"}
              </span>
              <hr />
              <ul className="coverage-list">
                {s.data
                  ?.filter((x) => p.specialty_ids.includes(x.id))
                  .map((x) => (
                    <li key={x.id}>
                      <Check size={17} />
                      {x.name}
                    </li>
                  ))}
              </ul>
              <p className="coverage-modalities">Modalidades: {p.modalities.map((x) => x === "VIRTUAL" ? "Virtual" : "Presencial").join(" · ")}</p>
              <Button
                className="full"
                variant={i === 1 ? "default" : "outline"}
                onClick={() => {
                  setSelected(p);
                  setSuccess(false);
                }}
              >
                {m.data?.plan?.id === p.id ? "Renovar plan" : "Activar plan"}
              </Button>
            </article>
          ))}
        </div>
      )}
      <ErrorBox error={s.error} />
      <section className="notice">
        <strong>¿Cómo funciona la renovación?</strong>
        <p>
          Si renuevas tu mismo plan activo, se agregan 30 días a la vigencia
          restante. Si cambias de plan, la nueva cobertura comienza al aprobar
          el pago y reemplaza la anterior.
        </p>
      </section>
      <Dialog
        open={!!selected}
        onOpenChange={(v) => !v && setSelected(null)}
        title={"Activar plan " + (selected?.name ?? "")}
        description="Solo un pago aprobado activa o renueva la cobertura."
      >
        {selected && (
          <>
            <div className="payment-total">
              <span>Total simulado</span>
              <strong>{money(selected.price)}</strong>
            </div>
            <PaymentControls
              key={selected.id}
              kind="PLAN"
              targetId={selected.id}
              onApproved={() => {
                setSelected(null);
                setSuccess(true);
              }}
            />
          </>
        )}
      </Dialog>
    </>
  );
}
