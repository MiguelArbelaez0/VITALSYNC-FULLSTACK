import { useState, type ComponentProps } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  LiveKitRoom,
  PreJoin,
  VideoConference,
} from "@livekit/components-react";
import { api, post, dateText, timeText } from "../../services/api";
import type { Appointment } from "../../types";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
import { ErrorBox, Loading, PageTitle } from "../../components/common";
import "@livekit/components-styles";
import "./livekit-consultation.css";

type UserChoices = Parameters<NonNullable<ComponentProps<typeof PreJoin>["onSubmit"]>>[0];
type TokenResponse = { token: string; server_url: string; expires_in_seconds: number };

export function LiveKitConsultation({
  appointmentId,
  role,
}: {
  appointmentId: string;
  role: "PATIENT" | "DOCTOR";
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [credentials, setCredentials] = useState<TokenResponse | null>(null);
  const [choices, setChoices] = useState<UserChoices | null>(null);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const prefix = role === "PATIENT" ? "/appointments/" : "/doctor/appointments/";
  const roomPath = role === "PATIENT"
    ? `${prefix}${appointmentId}/teleconsult`
    : `${prefix}${appointmentId}/teleconsult`;
  const tokenPath = role === "PATIENT"
    ? `${prefix}${appointmentId}/livekit-token`
    : `${prefix}${appointmentId}/livekit-token`;
  const q = useQuery({
    queryKey: [role === "PATIENT" ? "teleconsult" : "doctor", "livekit", appointmentId],
    queryFn: () => api<Appointment>(roomPath),
    refetchInterval: credentials ? 5000 : 15000,
  });

  async function joinRoom(selected: UserChoices) {
    setBusy(true);
    setError(null);
    try {
      const issued = await post<TokenResponse>(tokenPath, {});
      setChoices(selected);
      setCredentials(issued);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function finishConsultation() {
    setFinalizing(true);
    setError(null);
    try {
      await post(`/doctor/appointments/${appointmentId}/livekit-finalize`, {});
      await queryClient.invalidateQueries();
      setFinalizeOpen(false);
      navigate("/doctor/appointments");
    } catch (cause) {
      setError(cause);
    } finally {
      setFinalizing(false);
    }
  }

  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const appointment = q.data;
  const terminal = ["ATTENDED", "CANCELLED", "PATIENT_ABSENT", "DOCTOR_ABSENT"].includes(appointment.status);
  const title = role === "PATIENT" ? "Videollamada con tu médico" : "Videollamada con el paciente";
  const canFinish = role === "DOCTOR" && appointment.status === "IN_PROGRESS" && appointment.virtual_status !== "FINALIZADA";

  return (
    <main className="livekit-page">
      <Link className="text-link back-link" to={role === "PATIENT" ? `/portal/appointments/${appointmentId}` : `/doctor/appointments/${appointmentId}`}>
        ← Volver al detalle de la cita
      </Link>
      <PageTitle
        eyebrow="SALA PRIVADA DE CITA VIRTUAL"
        title={title}
        description={`${appointment.patient ?? "Paciente"} · ${appointment.doctor} · ${dateText(appointment.starts_at)} · ${timeText(appointment.starts_at)} · Bogotá`}
      />
      <section className="panel livekit-panel">
        {terminal ? (
          <div className="notice" role="status">
            {appointment.status === "ATTENDED"
              ? "La consulta ya finalizó. Puedes revisar el detalle en el historial de la cita."
              : "Esta cita no admite ingreso a la sala de videollamada."}
          </div>
        ) : credentials && choices ? (
          <>
            <p className="livekit-status" role="status">
              {appointment.livekit_connection_state === "CONNECTED"
                ? "Paciente y médico conectados"
                : connected ? "Esperando al otro participante" : "Conectando con la sala…"}
              {appointment.livekit_connection_state === "RECONNECTING" && " · Un participante está reconectando"}
            </p>
            <LiveKitRoom
              token={credentials.token}
              serverUrl={credentials.server_url}
              connect
              audio={choices.audioEnabled}
              video={choices.videoEnabled}
              options={{ adaptiveStream: true, dynacast: true }}
              onConnected={() => setConnected(true)}
              onDisconnected={() => {
                setConnected(false);
                setCredentials(null);
                setChoices(null);
                void queryClient.invalidateQueries();
              }}
              onError={(cause) => setError(cause)}
              data-lk-theme="default"
              className="livekit-room"
            >
              <VideoConference />
            </LiveKitRoom>
            <ErrorBox error={error} />
            {canFinish && (
              <div className="livekit-finish-row">
                <p>Al finalizar, la cita pasará al historial de ambos portales y la sala cerrará.</p>
                <Button onClick={() => setFinalizeOpen(true)}>Finalizar consulta</Button>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="notice livekit-preparation-note">
              Esta videollamada usa audio y video en tiempo real. Comprueba los permisos y dispositivos antes de ingresar. No se graba audio ni video.
            </div>
            <PreJoin
              defaults={{ username: role === "PATIENT" ? "Paciente" : "Médico" }}
              onSubmit={(selected) => void joinRoom(selected)}
              onError={(cause) => setError(cause)}
              userLabel={role === "PATIENT" ? "Paciente" : "Médico"}
              joinLabel={busy ? "Solicitando acceso…" : role === "PATIENT" ? "Ingresar a videollamada" : "Iniciar videollamada"}
              persistUserChoices
            />
            <ErrorBox error={error} />
            {appointment.livekit_connection_state === "RECONNECTING" && (
              <p className="livekit-retry-note" role="status">Se detectó una desconexión temporal. Comprueba tu conexión y vuelve a ingresar.</p>
            )}
          </>
        )}
      </section>
      <Dialog
        open={finalizeOpen}
        onOpenChange={(open) => !finalizing && setFinalizeOpen(open)}
        title="Finalizar consulta"
        description="Esta acción cerrará la sala y moverá la cita a Finalizadas para el paciente y el médico. La plataforma no guarda la grabación."
      >
        <div className="button-row">
          <Button type="button" variant="outline" disabled={finalizing} onClick={() => setFinalizeOpen(false)}>Continuar consulta</Button>
          <Button disabled={finalizing} onClick={() => void finishConsultation()}>{finalizing ? "Finalizando…" : "Confirmar finalización"}</Button>
        </div>
        <ErrorBox error={error} />
      </Dialog>
    </main>
  );
}
