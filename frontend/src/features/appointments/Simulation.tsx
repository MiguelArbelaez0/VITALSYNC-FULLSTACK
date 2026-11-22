import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LiveKitRoom, StartAudio } from "@livekit/components-react";
import { useAuth } from "../../hooks/useAuth";
import { api, post } from "../../services/api";
import { ErrorBox, Loading } from "../../components/common";
import { Button } from "../../components/ui/button";
import { DevicePreview, type PreviewChoices } from "./DevicePreview";
import { RoomSurface } from "./LiveKitConsultation";

type Room = { id: string; owner: boolean; invitation?: string; expires_at: string };
type Connection = { token: string; server_url: string; choices: PreviewChoices };
const roomOptions = { adaptiveStream: true, dynacast: true, singlePeerConnection: false };

export default function Simulation() {
  const { user } = useAuth();
  const access = useQuery({ queryKey: ["simulation-access", user?.id],
    queryFn: () => api<{ available: boolean }>("/simulation/access"), retry: false });
  const [room, setRoom] = useState<Room | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [invitation, setInvitation] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [ended, setEnded] = useState(false);
  const previousRooms = useQuery({ queryKey: ["simulation-rooms", user?.id],
    queryFn: () => api<Room[]>("/simulation/rooms"),
    enabled: Boolean(access.data?.available && !room), staleTime: 0 });
  const status = useQuery({ queryKey: ["simulation-room-status", room?.id],
    queryFn: () => api<{ active: boolean }>("/simulation/rooms/" + room?.id),
    enabled: Boolean(room && !ended), refetchInterval: 3000, retry: false });
  useEffect(() => {
    if (status.data?.active === false) {
      setConnection(null); setEnded(true);
    }
  }, [status.data]);
  useEffect(() => {
    if (!room) return;
    const timeout = window.setTimeout(() => {
      setConnection(null); setEnded(true);
    }, Math.max(0, new Date(room.expires_at).getTime() - Date.now()));
    return () => window.clearTimeout(timeout);
  }, [room]);
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await action(); } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  function create(shared: boolean) {
    return run(async () => setRoom(await post<Room>("/simulation/rooms", { shared })));
  }
  if (access.isPending) return <Loading />;
  if (access.error) return <ErrorBox error={access.error} />;
  return <div className="livekit-page simulation-page">
    <header className="panel">
      <h1>Sala de simulación</h1>
      <strong>SIMULACIÓN ACADÉMICA — NO CORRESPONDE A UNA CONSULTA MÉDICA</strong>
      <p>Participas como {user?.name}. No se graban los medios compartidos.</p>
    </header>
    {!access.data?.available ? <p>LiveKit no está disponible en este entorno.</p> : ended ? <section className="panel">
      <h2>Simulación finalizada</h2>
      <Button onClick={() => { setRoom(null); setEnded(false); }}>Volver a la sala de simulación</Button>
    </section> : !room ? <section className="panel">
      {previousRooms.data?.map(item => <Button key={item.id} variant="outline" onClick={() => setRoom(item)}>Reanudar simulación {item.owner ? "propia" : "compartida"}</Button>)}
      <ErrorBox error={previousRooms.error} />
      <Button disabled={busy} onClick={() => void create(false)}>Prueba individual</Button>
      <Button disabled={busy} onClick={() => void create(true)}>Crear sala privada</Button>
      <form onSubmit={e => { e.preventDefault(); void run(async () => {
        setRoom(await post<Room>("/simulation/join", { invitation: invitation.trim() })); setInvitation("");
      }); }}>
        <label>Código de invitación<input value={invitation} onChange={e => setInvitation(e.target.value)} required maxLength={128} autoComplete="off" /></label>
        <Button disabled={busy}>Aceptar invitación</Button>
      </form>
    </section> : <>
      {room.invitation && <label>Invitación privada (vigente hasta {new Date(room.expires_at).toLocaleTimeString("es-CO")})<input readOnly value={room.invitation} /></label>}
      <section className="livekit-video-stage">
        {connection ? <LiveKitRoom token={connection.token} serverUrl={connection.server_url} connect
          options={roomOptions}
          audio={connection.choices.audioEnabled && { deviceId: connection.choices.audioDeviceId || undefined }}
          video={connection.choices.videoEnabled && { deviceId: connection.choices.videoDeviceId || undefined }}
          onError={() => setError(new Error("No se pudo conectar con LiveKit. Comprueba tu red y vuelve a ingresar."))} onDisconnected={() => setConnection(null)} className="livekit-room" data-lk-theme="default">
          <StartAudio label="Activar reproducción de audio" />
          <RoomSurface simulation remoteLabel="Otro participante" localLabel={user?.name ?? "Tú"}
            elapsed="Sala de práctica" consultationInProgress={false} onExit={() => setConnection(null)} finishing={busy} />
        </LiveKitRoom> : <DevicePreview busy={busy} joinLabel="Ingresar a simulación" onJoin={choices => run(async () => {
          const credentials = await post<Omit<Connection, "choices">>("/simulation/rooms/" + room.id + "/token");
          setConnection({ ...credentials, choices });
        })} />}
      </section>
      {room.owner && <Button disabled={busy} onClick={() => void run(async () => {
        await post("/simulation/rooms/" + room.id + "/end");
        setConnection(null); setEnded(true);
      })}>Terminar simulación</Button>}
    </>}
    <ErrorBox error={error} />
  </div>;
}
