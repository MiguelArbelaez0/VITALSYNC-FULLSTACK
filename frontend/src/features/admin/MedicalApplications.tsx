import { Table, button, type Context } from "./AdminCore";
export function MedicalApplications({
  c,
  academic,
}: {
  c: Context;
  academic: boolean;
}) {
  if (c.section === "doctor-credential-deliveries")
    return (
      <>
        <div className="notice">
          <h2>Entrega privada y única</h2>
          <p>
            Un operador autorizado debe ejecutar{" "}
            <code>
              .\infrastructure\Export-DoctorCredentials.ps1 -DeliveryId ID
              -AdminEmail CORREO_ADMIN
            </code>{" "}
            en el equipo del despliegue. Se exige la contraseña administrativa y
            se genera un archivo local protegido. Entrega ese archivo al
            profesional por un canal privado; los correos .demo no reciben
            mensajes reales.
          </p>
        </div>
        <Table
          data={c.list.items}
          columns={[
            { key: "id", label: "ID de entrega" },
            { key: "email", label: "Correo de acceso" },
            { key: "status", label: "Estado" },
            { key: "created_at", label: "Creación" },
            { key: "delivered_at", label: "Entrega" },
            { key: "reason", label: "Motivo" },
          ]}
        />
      </>
    );
  return (
    <>
      <p className="notice">
        {academic
          ? "Revisión académica simulada: no acredita habilitación profesional real."
          : "Revisión manual: verifica la habilitación profesional por los canales oficiales antes de aprobar."}{" "}
        Las solicitudes pendientes no tienen permisos clínicos.
      </p>
      {button("Ver entregas privadas", () =>
        c.go("/admin/doctor-credential-deliveries"),
      )}
      <Table
        data={c.list.items}
        columns={[
          {
            key: "given_names",
            label: "Solicitante",
            render: (r) => (
              <>
                {r.given_names} {r.surnames}
              </>
            ),
          },
          { key: "specialty", label: "Especialidad" },
          { key: "institutional_email", label: "Correo reservado" },
          { key: "status", label: "Estado" },
          { key: "delivery_id", label: "ID de entrega" },
          { key: "delivery_status", label: "Estado de entrega" },
        ]}
        actions={(r) => (
          <>
            {button("Revisar solicitud e historial", () =>
              c.detail("Solicitud médica", "/doctor-applications/" + r.id),
            )}
            {r.status === "PENDING" && c.can("accounts") && (
              <>
                {button("Aprobar solicitud", () =>
                  c.open({
                    title: "Aprobar solicitud médica",
                    path: `/doctor-applications/${r.id}/approve`,
                    description: `Se creará una cuenta individual para ${r.institutional_email}. La contraseña se entregará mediante el operador autorizado.`,
                    fields: [
                      {
                        key: "professional_review_confirmed",
                        type: "checkbox",
                        label: academic
                          ? "Confirmo la revisión académica simulada de los datos profesionales"
                          : "Confirmo que revisé la habilitación profesional",
                      },
                    ],
                    fixed: {
                      version: r.version,
                      verification_kind: academic
                        ? "ACADEMIC_SIMULATED"
                        : "MANUAL_REVIEW",
                    },
                    confirm: true,
                  }),
                )}
                {button("Rechazar solicitud", () =>
                  c.open({
                    title: "Rechazar solicitud médica",
                    path: `/doctor-applications/${r.id}/reject`,
                    fields: [],
                    fixed: { version: r.version },
                    confirm: true,
                  }),
                )}
              </>
            )}
          </>
        )}
      />
    </>
  );
}
