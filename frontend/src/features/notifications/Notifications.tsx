import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Check } from "lucide-react";
import { api, post, dateText, timeText } from "../../services/api";
import type { Notice } from "../../types";
import { Empty, ErrorBox, Loading, PageTitle } from "../../components/common";
import { Button } from "../../components/ui/button";
import { useState } from "react";
export function Notifications() {
  const client = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<Notice[]>("/notifications"),
  });
  async function read(id: number) {
    try {
      await post("/notifications/" + id + "/read");
      await client.invalidateQueries();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <>
      <PageTitle
        title="Estamos en contacto"
        description="Aquí encuentras las novedades de tus planes y tus citas."
      />
      <ErrorBox error={error} />
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : !q.data.length ? (
        <Empty title="Todo al día">
          <p>Aún no hay notificaciones.</p>
        </Empty>
      ) : (
        <div className="notifications-list">
          {q.data.map((n) => (
            <article
              className={"panel notification-row " + (!n.read ? "unread" : "")}
              key={n.id}
            >
              <span className="stat-icon teal">
                <Bell />
              </span>
              <div>
                <p>{n.message}</p>
                <small>
                  {dateText(n.created_at)} · {timeText(n.created_at)}
                </small>
              </div>
              {!n.read ? (
                <Button variant="outline" onClick={() => void read(n.id)}>
                  Marcar leída
                </Button>
              ) : (
                <span className="read-label">
                  <Check size={16} />
                  Leída
                </span>
              )}
            </article>
          ))}
        </div>
      )}
    </>
  );
}
