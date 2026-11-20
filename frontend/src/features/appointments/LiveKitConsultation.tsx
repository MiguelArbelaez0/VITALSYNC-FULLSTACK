import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  LiveKitRoom,
  MediaDeviceSelect,
  RoomAudioRenderer,
  type TrackReference,
  VideoTrack,
  useLocalParticipant,
  useParticipants,
  useRoomContext,
  useTracks,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import {
  Camera, CameraOff, Check, Clock3, Headphones, Mic, MicOff,
  Phone, PhoneOff, Settings2, Video,
} from "lucide-react";
import { api, post, dateText, timeText } from "../../services/api";
import type { Appointment } from "../../types";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
import { ErrorBox, Loading, PageTitle } from "../../components/common";
import "@livekit/components-styles";
import "./livekit-consultation.css";
import { DevicePreview, mediaErrorMessage, type PreviewChoices } from "./DevicePreview";

type TokenResponse = { token: string; server_url: string; expires_in_seconds: number };
type FinalizeResponse = { status: string; appointment_status: string; finalized_at?: string; started_at?: string; idempotent: boolean };

const portalPath = (role: "PATIENT" | "DOCTOR") => role === "PATIENT" ? "/portal/appointments" : "/doctor/appointments";

function displayError(error: unknown) {
  if (!(error instanceof Error)) return "Ocurrió un problema con la videollamada. Intenta de nuevo.";
  const message = error.message.toLowerCase();
  if (message.includes("permission") || message.includes("notallowed") || message.includes("permiso")) return "El navegador no permitió usar cámara o micrófono. Revisa los permisos del sitio.";
  if (message.includes("device") || message.includes("notfound") || message.includes("not found")) return "No encontramos el dispositivo seleccionado. Conecta o elige otro dispositivo.";
  if (message.includes("409") || message.includes("terminó") || message.includes("finaliz")) return "Esta consulta ya no admite nuevos ingresos.";
  if (message.includes("404") || message.includes("no pertenece")) return "No tienes acceso a esta sala.";
  return "No se pudo completar la acción. Comprueba tu conexión e inténtalo nuevamente.";
}

function durationLabel(startedAt?: string | null, endedAt?: string | null, now = Date.now()) {
  if (!startedAt) return "Pendiente";
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : now;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "No disponible";
  const minutes = Math.floor((end - start) / 60000);
  return `${minutes} min`;
}

export function LiveKitConsultation({ appointmentId, role }: { appointmentId: string; role: "PATIENT" | "DOCTOR" }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [credentials, setCredentials] = useState<TokenResponse | null>(null);
  const [choices, setChoices] = useState<PreviewChoices | null>(null);
  const audioCapture = useMemo(() => choices?.audioDeviceId ? { deviceId: choices.audioDeviceId } : {}, [choices]);
  const videoCapture = useMemo(() => choices?.videoDeviceId ? { deviceId: choices.videoDeviceId } : {}, [choices]);
  const roomOptions = useMemo(() => ({ adaptiveStream: true, dynacast: true, audioCaptureDefaults: audioCapture, videoCaptureDefaults: videoCapture }), [audioCapture, videoCapture]);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [finalizeOpen, setFinalizeOpen] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const exitRequested = useRef(false);
  const roomPath = `/appointments/${appointmentId}/teleconsult`;
  const tokenPath = `/appointments/${appointmentId}/livekit-token`;
  const queryKey = [role === "PATIENT" ? "teleconsult" : "doctor", "livekit", appointmentId];
  const q = useQuery({
    queryKey,
    queryFn: () => api<Appointment>(role === "PATIENT" ? roomPath : `/doctor${roomPath}`),
    refetchInterval: credentials ? 3000 : 10000,
  });

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  async function joinRoom(selected: PreviewChoices) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const path = role === "PATIENT" ? tokenPath : `/doctor${tokenPath}`;
      const issued = await post<TokenResponse>(path, {});
      exitRequested.current = false;
      setChoices(selected);
      setCredentials(issued);
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }

  async function finishConsultation() {
    if (finalizing) return;
    setFinalizing(true);
    setError(null);
    try {
      const result = await post<FinalizeResponse>(`/doctor/appointments/${appointmentId}/livekit-finalize`, {});
      const current = queryClient.getQueryData<Appointment>(queryKey);
      const finalTimestamp = result.finalized_at ?? current?.virtual_state?.finalized_at ?? null;
      const startTimestamp = result.started_at ?? current?.virtual_state?.started_at ?? null;
      if (current) queryClient.setQueryData<Appointment>(queryKey, {
        ...current,
        status: "ATTENDED",
        attended_at: finalTimestamp,
        virtual_status: "FINALIZADA",
        livekit_connection_state: "DISCONNECTED",
        virtual_state: current.virtual_state ? {
          ...current.virtual_state,
          status: "FINALIZADA",
          lifecycle_status: "FINALIZADA",
          finalized_at: finalTimestamp,
          started_at: startTimestamp,
        } : current.virtual_state,
      });
      setFinalizeOpen(false);
      setCredentials(null);
      setChoices(null);
      await queryClient.invalidateQueries();
    } catch (cause) {
      setError(cause);
    } finally {
      setFinalizing(false);
    }
  }

  if (q.isPending) return <Loading />;
  if (q.error) return <ErrorBox error={displayError(q.error)} />;
  const appointment = q.data;
  const terminal = appointment.status === "ATTENDED" || appointment.virtual_status === "FINALIZADA";
  const canceled = ["CANCELLED", "PATIENT_ABSENT", "DOCTOR_ABSENT"].includes(appointment.status);
  const title = "Videoconsulta";
  const canFinish = role === "DOCTOR" && appointment.status === "IN_PROGRESS" && appointment.virtual_status === "EN_ATENCION";
  const startedAt = appointment.virtual_state?.started_at;
  const finalizedAt = appointment.virtual_state?.finalized_at ?? appointment.attended_at;
  const backPath = role === "PATIENT" ? `/portal/appointments/${appointmentId}` : `/doctor/appointments/${appointmentId}`;

  return (
    <main className="livekit-page">
      <div className="livekit-breadcrumb">
        <Link className="text-link" to={backPath}>← Volver al detalle de la cita</Link>
        <span className={`livekit-status-pill ${terminal ? "is-finished" : canceled ? "is-muted" : connected ? "is-connected" : ""}`}>
          <span aria-hidden="true" />{terminal ? "Finalizada" : canceled ? "No disponible" : connected ? "En curso" : appointment.livekit_connection_state === "RECONNECTING" ? "Reconectando" : "Sala virtual"}
        </span>
      </div>
      <PageTitle
        eyebrow="SALA PRIVADA · VITALSYNC"
        title={title}
        description={`${appointment.patient ?? "Paciente"} · ${appointment.doctor} · ${appointment.specialty} · ${dateText(appointment.starts_at)} · ${timeText(appointment.starts_at)} · Bogotá`}
      />

      {terminal ? (
        <section className="livekit-finished-card" role="status" aria-live="polite">
          <span className="livekit-finished-mark"><Check size={38} strokeWidth={2.5} /></span>
          <p className="eyebrow">VITALSYNC · VIDEOCONSULTA</p>
          <h2>Consulta finalizada</h2>
          <p className="livekit-finished-copy">La consulta médica terminó correctamente. El registro ya está disponible en el historial.</p>
          <div className="livekit-summary-grid">
            <div><span>Estado</span><strong>FINALIZADA</strong></div>
            <div><span>Fecha de atención</span><strong>{startedAt ? dateText(startedAt) : dateText(appointment.starts_at)}</strong></div>
            <div><span>Hora de finalización</span><strong>{finalizedAt ? timeText(finalizedAt) : "No registrada"}</strong></div>
            <div><span>Duración</span><strong>{durationLabel(startedAt, finalizedAt, clock)}</strong></div>
            <div><span>Profesional</span><strong>{appointment.doctor}</strong></div>
            <div><span>Especialidad</span><strong>{appointment.specialty}</strong></div>
          </div>
          <Link className="livekit-primary-link" to={portalPath(role)}>{role === "PATIENT" ? "Ver historial de citas" : "Volver a mis consultas"}</Link>
        </section>
      ) : canceled ? (
        <section className="livekit-finished-card" role="status">
          <span className="livekit-finished-mark is-neutral"><PhoneOff size={34} /></span>
          <h2>Esta consulta no está disponible</h2>
          <p className="livekit-finished-copy">La cita está cancelada o cerrada por el flujo de asistencia y no admite ingreso a la sala.</p>
          <Link className="livekit-primary-link" to={portalPath(role)}>{role === "PATIENT" ? "Volver a mis citas" : "Volver a mis consultas"}</Link>
        </section>
      ) : (
        <section className="livekit-workspace">
          <div className="livekit-stage-column">
            <section className="livekit-video-stage" aria-label="Sala de videoconsulta">
              {credentials && choices ? (
                <LiveKitRoom
                  token={credentials.token}
                  serverUrl={credentials.server_url}
                  connect
                  audio={choices.audioEnabled ? audioCapture : false}
                  video={choices.videoEnabled ? videoCapture : false}
                  options={roomOptions}
                  onConnected={() => setConnected(true)}
                  onDisconnected={() => {
                    setConnected(false);
                    setCredentials(null);
                    setChoices(null);
                    void queryClient.invalidateQueries({ queryKey });
                    if (exitRequested.current) navigate(portalPath(role));
                  }}
                  onError={setError}
                  data-lk-theme="default"
                  className="livekit-room"
                >
                  <RoomSurface
                    remoteLabel={role === "PATIENT" ? appointment.doctor : appointment.patient ?? "Paciente"}
                    localLabel={role === "PATIENT" ? "Tú · Paciente" : "Tú · Médico"}
                    consultationInProgress={appointment.status === "IN_PROGRESS"}
                    onExit={() => { exitRequested.current = true; }}
                    onFinish={canFinish ? () => setFinalizeOpen(true) : undefined}
                    finishing={finalizing}
                    elapsed={durationLabel(startedAt, null, clock)}
                  />
                </LiveKitRoom>
              ) : (
                <div className="livekit-prejoin-shell">
                  <div className="livekit-prejoin-heading"><span className="livekit-prejoin-icon"><Video size={24} /></span><div><h2>Antes de ingresar</h2><p>Comprueba cámara, micrófono y conexión.</p></div></div>
                  <p className="livekit-privacy-note">Videollamada privada en tiempo real. No se graba audio, video ni transcripciones.</p>
                  <DevicePreview busy={busy} onJoin={joinRoom} joinLabel={role === "PATIENT" ? "Ingresar a videollamada" : "Iniciar videollamada"} />
                  <ErrorBox error={error ? displayError(error) : null} />
                  {appointment.livekit_connection_state === "RECONNECTING" && <p className="livekit-retry-note" role="status">El otro participante se desconectó temporalmente. Puedes ingresar de nuevo cuando estés listo.</p>}
                </div>
              )}
            </section>
            <ErrorBox error={error ? displayError(error) : null} />
            {credentials && <p className="livekit-security-note"><span /> Conexión segura · La desconexión no finaliza la cita</p>}
          </div>

          <aside className="livekit-info-card" aria-label="Información de la videoconsulta">
            <h2>Detalles de la consulta</h2>
            <InfoRow label="Paciente" value={appointment.patient ?? "Paciente"} />
            <InfoRow label="Médico" value={appointment.doctor} />
            <InfoRow label="Especialidad" value={appointment.specialty} />
            <InfoRow label="Modalidad" value="Virtual · LiveKit" />
            <div className="livekit-info-state"><span>Estado de conexión</span><strong className={connected ? "connected" : ""}><span />{connectionLabel(appointment.livekit_connection_state, connected)}</strong></div>
            <div className="livekit-duration"><Clock3 size={19} /><span>Duración</span><strong>{durationLabel(startedAt, null, clock)}</strong></div>
            <p className="livekit-leave-help">Puedes salir de la llamada sin finalizar la consulta. Si la cita continúa activa, podrás volver a entrar.</p>
          </aside>
        </section>
      )}

      <Dialog
        open={finalizeOpen}
        onOpenChange={(open) => !finalizing && setFinalizeOpen(open)}
        title="Finalizar consulta"
        description={`La sala se cerrará para ti y ${appointment.patient ?? "el paciente"}. Esta acción guardará la consulta como finalizada para ambos portales y no se podrá volver a ingresar. No se guarda ninguna grabación.`}
      >
        <div className="livekit-confirm-details"><strong>{appointment.patient ?? "Paciente"}</strong><span>{appointment.doctor} · {appointment.specialty}</span><span>Tiempo transcurrido: {durationLabel(startedAt, null, clock)}</span></div>
        <div className="button-row">
          <Button type="button" variant="outline" disabled={finalizing} onClick={() => setFinalizeOpen(false)}>Continuar consulta</Button>
          <Button disabled={finalizing || !connected} onClick={() => void finishConsultation()}>{finalizing ? "Guardando finalización…" : "Confirmar y finalizar"}</Button>
        </div>
        <ErrorBox error={error ? displayError(error) : null} />
      </Dialog>
    </main>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <div className="livekit-info-row"><span>{label}</span><strong>{value}</strong></div>;
}

function connectionLabel(serverState: Appointment["livekit_connection_state"], connected: boolean) {
  if (connected) return "Conectado";
  if (serverState === "CONNECTED") return "Participante conectado";
  if (serverState === "RECONNECTING") return "Participante reconectando";
  if (serverState === "WAITING") return "Esperando al otro participante";
  return "Esperando ingreso";
}

function RoomSurface({
  remoteLabel, localLabel, onExit, onFinish, finishing, elapsed,
  consultationInProgress,
}: {
  remoteLabel: string; localLabel: string; onExit: () => void;
  onFinish?: () => void; finishing: boolean; elapsed: string; consultationInProgress: boolean;
}) {
  const room = useRoomContext();
  const { localParticipant, isMicrophoneEnabled, isCameraEnabled } = useLocalParticipant();
  const participants = useParticipants();
  const tracks = useTracks([{ source: Track.Source.Camera, withPlaceholder: true }]);
  const remoteTrack = useMemo(() => tracks.find((track) => !track.participant.isLocal), [tracks]);
  const localTrack = useMemo(() => tracks.find((track) => track.participant.isLocal), [tracks]);
  const [deviceMenu, setDeviceMenu] = useState(false);
  const [operation, setOperation] = useState("");
  const [mediaError, setMediaError] = useState("");
  const cameraError = useCallback((cause: Error) => setMediaError(mediaErrorMessage(cause, "camera")), []);
  const microphoneError = useCallback((cause: Error) => setMediaError(mediaErrorMessage(cause, "microphone")), []);
  const outputError = useCallback(() => setMediaError("No se pudo seleccionar la salida de audio. Revisa el dispositivo y vuelve a elegirlo en Dispositivos."), []);
  const remoteConnected = participants.some((participant) => !participant.isLocal);

  async function toggle(kind: "microphone" | "camera") {
    setOperation(kind);
    setMediaError("");
    try {
      if (kind === "microphone") await localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled);
      else await localParticipant.setCameraEnabled(!isCameraEnabled);
    } catch (cause) { setMediaError(mediaErrorMessage(cause, kind)); }
    finally { setOperation(""); }
  }

  async function leave() {
    onExit();
    try { await room.localParticipant.setMicrophoneEnabled(false); } catch { /* best-effort media shutdown before leaving */ }
    try { await room.localParticipant.setCameraEnabled(false); } catch { /* best-effort media shutdown before leaving */ }
    await room.disconnect();
  }

  return (
    <div className="livekit-live-surface">
      <div className="livekit-live-heading"><div><span className="livekit-live-dot" /><div><strong>Consulta en curso</strong><small>{elapsed} transcurridos</small></div></div><span className="livekit-encrypted">Sala privada</span></div>
      {consultationInProgress && !remoteConnected && <div className="livekit-peer-notice" role="status"><strong>El otro participante salió o perdió la conexión.</strong><span>La consulta sigue activa; podrá volver a ingresar mientras la cita esté autorizada.</span></div>}
      <div className="livekit-video-grid">
        <div className="livekit-main-video">
          {remoteTrack?.publication && !remoteTrack.publication.isMuted ? <VideoTrack trackRef={remoteTrack as TrackReference} /> : <div className="livekit-video-placeholder"><span>{remoteLabel.slice(0, 1).toUpperCase()}</span><strong>{remoteLabel}</strong><small>{remoteTrack ? "Cámara desactivada" : "Esperando al otro participante…"}</small></div>}
          <div className="livekit-video-name"><span className="livekit-live-dot" />{remoteLabel}</div>
          <RoomAudioRenderer />
        </div>
        <div className={`livekit-self-video ${!isCameraEnabled ? "is-off" : ""}`}>
          {localTrack && isCameraEnabled && "publication" in localTrack && localTrack.publication ? <VideoTrack trackRef={localTrack as TrackReference} /> : <div className="livekit-self-placeholder"><CameraOff size={24} /><span>Cámara apagada</span></div>}
          <span className="livekit-self-label">{localLabel}</span>
        </div>
      </div>
      <div className="livekit-controls" aria-label="Controles de llamada">
        <button type="button" className={`livekit-control ${!isMicrophoneEnabled ? "is-muted" : ""}`} onClick={() => void toggle("microphone")} disabled={operation === "microphone"} aria-pressed={isMicrophoneEnabled}>
          {isMicrophoneEnabled ? <Mic /> : <MicOff />}<span>{isMicrophoneEnabled ? "Silenciar" : "Activar micrófono"}</span>
        </button>
        <button type="button" className={`livekit-control ${!isCameraEnabled ? "is-muted" : ""}`} onClick={() => void toggle("camera")} disabled={operation === "camera"} aria-pressed={isCameraEnabled}>
          {isCameraEnabled ? <Camera /> : <CameraOff />}<span>{isCameraEnabled ? "Apagar cámara" : "Activar cámara"}</span>
        </button>
        <div className="livekit-device-control">
          <button type="button" className={`livekit-control ${deviceMenu ? "is-selected" : ""}`} onClick={() => setDeviceMenu((shown) => !shown)} aria-expanded={deviceMenu}>
            <Settings2 /><span>Dispositivos</span>
          </button>
          {deviceMenu && <div className="livekit-device-menu"><h3>Micrófono</h3><MediaDeviceSelect kind="audioinput" onError={microphoneError} onDeviceSelectError={microphoneError} /><h3>Cámara</h3><MediaDeviceSelect kind="videoinput" onError={cameraError} onDeviceSelectError={cameraError} /><h3>Salida de audio</h3><MediaDeviceSelect kind="audiooutput" onError={outputError} onDeviceSelectError={outputError} /><p>Compartir pantalla no está habilitado para esta sala.</p></div>}
        </div>
        <span className="livekit-control-spacer" />
        <button type="button" className="livekit-control livekit-leave-control" onClick={() => void leave()}><PhoneOff /><span>Salir de la llamada</span></button>
        {onFinish && <button type="button" className="livekit-control livekit-finish-control" onClick={onFinish} disabled={finishing}>
          <Phone /><span>{finishing ? "Finalizando…" : "Finalizar consulta"}</span>
        </button>}
      </div>
      {mediaError && <p className="livekit-peer-notice" role="alert">{mediaError} Usa el control correspondiente para reintentar.</p>}
      <div className="livekit-connected-footer"><Headphones size={16} /><span>Audio y video en tiempo real · No se graba</span><span className="livekit-connected-label"><span />Conectado</span></div>
    </div>
  );
}
