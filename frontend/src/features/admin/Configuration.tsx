import { useQuery } from "@tanstack/react-query";
import { api } from "../../services/api";
import { Loading, ErrorBox } from "../../components/common";
import { Button } from "../../components/ui/button";
import {
  Tree,
  Table,
  State,
  account,
  recovery,
  scopes,
  type Context,
  type Row,
  type Collection,
} from "./AdminCore";
export function Configuration({ c }: { c: Context }) {
  const admins = useQuery({
    queryKey: ["admin", "administrators"],
    queryFn: () => api<Row[]>("/admin/administrators"),
    enabled: c.can("accounts"),
    retry: false,
  });
  const requests = useQuery({
    queryKey: ["admin", "recoveries"],
    queryFn: () => api<Collection>("/admin/recoveries"),
    enabled: c.can("accounts"),
    retry: false,
  });
  const choices = (c.options?.scopes ?? []).map((v) => ({
    value: v,
    label: scopes[v] ?? v,
  }));
  return (
    <>
      <section className="panel admin-section">
        <h2>Institución y políticas</h2>
        <Tree data={c.data.institution} />
        <p className="admin-policy">
          Modo demostración: {c.data.demo_mode ? "activado" : "desactivado"}. Se
          configura en el despliegue. Historias clínicas: acceso exclusivo del
          médico tratante. Las cuentas conservan su rol; los permisos
          administrativos se conceden por módulo.
        </p>
        <Button
          variant="outline"
          onClick={() =>
            c.open({
              title: "Editar información institucional",
              path: "/settings",
              fields: [
                {
                  key: "display_name",
                  label: "Nombre visible",
                  min: 3,
                  max: 120,
                },
                {
                  key: "support_email",
                  label: "Correo de soporte",
                  type: "email",
                },
                {
                  key: "support_phone",
                  label: "Teléfono de soporte",
                  min: 7,
                  max: 30,
                },
              ],
              initial: c.data.institution,
              method: "PUT",
            })
          }
        >
          Editar información institucional
        </Button>
      </section>
      <section className="panel admin-section">
        <h2>Mis permisos</h2>
        <div className="admin-actions">
          {c.data.scopes.map((s: string) => (
            <span className="admin-status" key={s}>
              {scopes[s] ?? s}
            </span>
          ))}
        </div>
      </section>
      {c.can("accounts") && (
        <>
          <section className="panel admin-section">
            <h2>Administradores y permisos</h2>
            <Button
              onClick={() =>
                c.open({
                  title: "Crear administrador",
                  path: "/administrators",
                  fields: [
                    { key: "name", label: "Nombre", min: 3, max: 120 },
                    { key: "email", label: "Correo individual", type: "email" },
                    {
                      key: "scopes",
                      label: "Permisos concedidos",
                      type: "multi",
                      required: false,
                      options: choices,
                    },
                  ],
                  initial: { scopes: [] },
                  confirm: true,
                  description:
                    "Se crea una cuenta individual con acceso privado por recuperación. No se conceden permisos superiores a los propios.",
                })
              }
            >
              Crear administrador
            </Button>
            {admins.isPending ? (
              <Loading />
            ) : admins.error ? (
              <ErrorBox error={admins.error} />
            ) : (
              <Table
                data={admins.data ?? []}
                columns={[
                  { key: "name", label: "Administrador" },
                  { key: "email", label: "Correo" },
                  {
                    key: "status",
                    label: "Estado",
                    render: (r) => <State state={r.status} />,
                  },
                  {
                    key: "scopes",
                    label: "Permisos",
                    render: (r) =>
                      r.scopes.map((v: string) => scopes[v] ?? v).join(" · "),
                  },
                ]}
                actions={(r) => (
                  <>
                    <Button
                      variant="outline"
                      disabled={r.id === c.userId}
                      onClick={() =>
                        c.open({
                          title: "Modificar permisos administrativos",
                          path: "/administrators/" + r.id + "/permissions",
                          fields: [
                            {
                              key: "scopes",
                              label: "Permisos concedidos",
                              type: "multi",
                              required: false,
                              options: choices,
                            },
                          ],
                          initial: r,
                          method: "PATCH",
                          confirm: true,
                          description:
                            "Se cerrarán las sesiones del usuario. Debe conservarse un administrador activo con todos los permisos. Otro administrador autorizado debe modificar los tuyos.",
                        })
                      }
                    >
                      Permisos
                    </Button>
                    <Button
                      variant="outline"
                      disabled={r.id === c.userId}
                      onClick={() => account(c, r)}
                    >
                      {r.status === "ACTIVE" ? "Desactivar" : "Activar"}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => recovery(c, r)}
                      disabled={r.status !== "ACTIVE"}
                    >
                      Recuperar acceso
                    </Button>
                  </>
                )}
              />
            )}
          </section>
          <section className="panel admin-section">
            <h2>Entrega privada de acceso</h2>
            <p className="admin-policy">
              El operador emite enlaces desde el comando local documentado. Son
              de un solo uso y vencen en 24 horas. La aplicación nunca muestra
              códigos ni contraseñas. Revocar permite solicitar un enlace nuevo
              sin cambiar la contraseña actual.
            </p>
            {requests.isPending ? (
              <Loading />
            ) : requests.error ? (
              <ErrorBox error={requests.error} />
            ) : (
              <Table
                data={requests.data?.items ?? []}
                columns={[
                  { key: "id", label: "Solicitud" },
                  { key: "email", label: "Cuenta" },
                  {
                    key: "status",
                    label: "Estado",
                    render: (r) => <State state={r.status} />,
                  },
                  { key: "expires_at", label: "Vencimiento" },
                ]}
                actions={(r) => (
                  <Button
                    variant="outline"
                    disabled={!["PENDING", "ISSUED"].includes(r.status)}
                    onClick={() =>
                      c.open({
                        title: "Revocar enlace de recuperación",
                        path: "/recoveries/" + r.id + "/revoke",
                        fields: [],
                        confirm: true,
                        description:
                          "El enlace anterior dejará de funcionar. La contraseña de la cuenta no se modifica.",
                      })
                    }
                  >
                    Revocar
                  </Button>
                )}
              />
            )}
          </section>
        </>
      )}
    </>
  );
}
