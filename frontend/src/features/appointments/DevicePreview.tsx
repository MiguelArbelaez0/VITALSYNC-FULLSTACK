import { useCallback, useEffect, useRef, useState } from "react";
import { createLocalAudioTrack, createLocalVideoTrack, createAudioAnalyser, type LocalAudioTrack, type LocalVideoTrack } from "livekit-client";
import { Camera, CameraOff, Mic, MicOff, RefreshCw } from "lucide-react";

export type PreviewChoices = {
  audioEnabled: boolean; videoEnabled: boolean; audioDeviceId: string; videoDeviceId: string;
};
type InputKind = "camera" | "microphone";
type PreviewTrack = LocalAudioTrack | LocalVideoTrack;

export function mediaErrorMessage(error: unknown, kind: InputKind) {
  const device = kind === "camera" ? "la cámara" : "el micrófono";
  const name = error && typeof error === "object" && "name" in error ? String(error.name) : "";
  switch (name) {
    case "NotAllowedError": case "PermissionDeniedError": case "SecurityError":
      return `Permiso denegado para ${device}. En Chrome, abre el icono de controles del sitio junto a la dirección, permite su uso y pulsa Reintentar.`;
    case "NotFoundError": case "DevicesNotFoundError":
      return `No encontramos ${device}. Conecta un dispositivo o elige otro en la lista y pulsa Reintentar.`;
    case "NotReadableError": case "TrackStartError":
      return `No se pudo abrir ${device}. Otra aplicación podría estar utilizándolo; ciérrala y pulsa Reintentar.`;
    case "OverconstrainedError": case "ConstraintNotSatisfiedError":
      return `La configuración de ${device} no es compatible. Elige el dispositivo predeterminado y pulsa Reintentar.`;
    case "InsecureContext":
      return "Para usar cámara y micrófono abre VITALSYNC con HTTPS o desde http://localhost:5188. Este origen no es seguro.";
    default:
      return `No se pudo iniciar ${device}. Comprueba la conexión del dispositivo y pulsa Reintentar.`;
  }
}

function usePreviewInput(kind: InputKind) {
  const [track, setTrack] = useState<PreviewTrack | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const current = useRef<PreviewTrack | null>(null);
  const generation = useRef(0);
  const mounted = useRef(true);

  const release = useCallback(() => {
    const previous = current.current;
    current.current = null;
    if (previous) {
      previous.mediaStreamTrack.onended = null;
      previous.detach();
      previous.stop();
    }
  }, []);
  const stop = useCallback(() => {
    generation.current++;
    release();
    setTrack(null); setRequesting(false); setError(""); setNotice("");
  }, [release]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; generation.current++; release(); };
  }, [release]);

  const start = useCallback(async (selectedId: string) => {
    const attempt = ++generation.current;
    release(); setTrack(null); setError(""); setNotice(""); setRequesting(true);
    const create = (id: string) => kind === "camera"
      ? createLocalVideoTrack(id ? { deviceId: { exact: id } } : {})
      : createLocalAudioTrack(id ? { deviceId: { exact: id } } : {});
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw { name: "InsecureContext" };
      let acquired: PreviewTrack;
      let recovered = false;
      try { acquired = await create(selectedId); }
      catch (cause) {
        if (cause && typeof cause === "object" && "name" in cause && ["OverconstrainedError", "ConstraintNotSatisfiedError"].includes(String(cause.name)) && selectedId) {
          acquired = await create(""); recovered = true;
        } else throw cause;
      }
      if (!mounted.current || attempt !== generation.current) { acquired.stop(); return; }
      current.current = acquired;
      acquired.mediaStreamTrack.onended = () => {
        if (current.current !== acquired) return;
        release(); setTrack(null);
        setError(`Se desconectó ${kind === "camera" ? "la cámara" : "el micrófono"}. Elige otro dispositivo y pulsa Reintentar.`);
      };
      setDeviceId(acquired.mediaStreamTrack.getSettings().deviceId || selectedId);
      setTrack(acquired);
      if (recovered) setNotice("La selección anterior no era compatible. Se recuperó el dispositivo predeterminado.");
    } catch (cause) {
      if (mounted.current && attempt === generation.current) setError(mediaErrorMessage(cause, kind));
    } finally {
      if (mounted.current && attempt === generation.current) setRequesting(false);
    }
  }, [kind, release]);
  function select(id: string) {
    setDeviceId(id);
    if (current.current || requesting || error) void start(id);
  }
  return { track, deviceId, requesting, error, notice, start, stop, select };
}

function CameraVideo({ track }: { track: LocalVideoTrack }) {
  const video = useRef<HTMLVideoElement>(null);
  const [playError, setPlayError] = useState(false);
  const play = useCallback(() => {
    const element = video.current;
    if (!element) return;
    void element.play().then(() => { if (video.current === element) setPlayError(false); })
      .catch(() => { if (video.current === element) setPlayError(element.paused); });
  }, []);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    track.attach(element); play();
    return () => { track.detach(element); element.srcObject = null; };
  }, [track, play]);
  return <><video ref={video} autoPlay muted playsInline onPlaying={() => setPlayError(false)} aria-label="Vista previa local de tu cámara" />{playError && <button className="preview-play" type="button" onClick={play}>Mostrar vista previa</button>}</>;
}

function MicrophoneMeter({ track }: { track: LocalAudioTrack | null }) {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    if (!track) { setLevel(0); return; }
    try {
      const meter = createAudioAnalyser(track);
      const timer = window.setInterval(() => setLevel(Math.round(Math.min(1, meter.calculateVolume()) * 100)), 120);
      return () => { window.clearInterval(timer); void meter.cleanup().catch(() => {}); };
    } catch { return; } // Capture can still work on a browser without an audio analyser.
  }, [track]);
  return <div className="preview-meter"><span>{track ? "Habla para comprobar el micrófono" : "Micrófono desactivado"}</span><meter min={0} max={100} value={level} aria-label="Nivel del micrófono" /></div>;
}

export function DevicePreview({ busy, joinLabel, onJoin }: { busy: boolean; joinLabel: string; onJoin: (choices: PreviewChoices) => Promise<void> }) {
  const camera = usePreviewInput("camera");
  const microphone = usePreviewInput("microphone");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceError, setDeviceError] = useState(false);
  const mounted = useRef(true);
  const refresh = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    try {
      const available = await navigator.mediaDevices.enumerateDevices();
      if (mounted.current) { setDevices(available); setDeviceError(false); }
    }
    catch { if (mounted.current) setDeviceError(true); }
  }, []);
  useEffect(() => {
    mounted.current = true;
    navigator.mediaDevices?.addEventListener?.("devicechange", refresh);
    return () => { mounted.current = false; navigator.mediaDevices?.removeEventListener?.("devicechange", refresh); };
  }, [refresh]);
  useEffect(() => { void refresh(); }, [camera.track, microphone.track, refresh]);
  const insecure = !window.isSecureContext || !navigator.mediaDevices?.getUserMedia;
  const pending = busy || camera.requesting || microphone.requesting;

  return <div className="vitalsync-prejoin" data-lk-theme="default">
    <div className="preview-video-box" aria-label="Vista previa privada">
      {camera.track ? <CameraVideo track={camera.track as LocalVideoTrack} /> : <div className="preview-placeholder"><CameraOff size={40} /><strong>{camera.requesting ? "Solicitando permiso de cámara…" : camera.error ? "Cámara no disponible" : "Tu cámara está desactivada"}</strong><span>{camera.error ? "Revisa el mensaje y vuelve a intentarlo." : "Pulsa Activar cámara para ver tu imagen antes de ingresar."}</span></div>}
      <span className="preview-state" role="status">{camera.requesting ? "Solicitando permiso" : camera.track ? "Cámara activa · Solo vista previa" : camera.error ? "Error de cámara" : "Cámara desactivada"}</span>
    </div>
    {insecure && <p className="preview-error" role="alert">{mediaErrorMessage({ name: "InsecureContext" }, "camera")}</p>}
    <div className="preview-toggles">
      <button type="button" className={`preview-toggle ${camera.track ? "is-on" : ""}`} aria-pressed={!!camera.track} disabled={busy || camera.requesting} onClick={() => camera.track ? camera.stop() : void camera.start(camera.deviceId)}>{camera.track ? <Camera /> : <CameraOff />}{camera.requesting ? "Solicitando cámara…" : camera.track ? "Desactivar cámara" : "Activar cámara"}</button>
      <button type="button" className={`preview-toggle ${microphone.track ? "is-on" : ""}`} aria-pressed={!!microphone.track} disabled={busy || microphone.requesting} onClick={() => microphone.track ? microphone.stop() : void microphone.start(microphone.deviceId)}>{microphone.track ? <Mic /> : <MicOff />}{microphone.requesting ? "Solicitando micrófono…" : microphone.track ? "Desactivar micrófono" : "Activar micrófono"}</button>
    </div>
    <div className="preview-device-selects">
      {([['videoinput', 'Cámara', camera], ['audioinput', 'Micrófono', microphone]] as const).map(([kind, label, input]) => {
        const inputs = devices.filter((device) => device.kind === kind && device.deviceId);
        return <div key={kind}><label>{label}<select aria-label={`Seleccionar ${label.toLowerCase()}`} value={input.deviceId} disabled={busy || input.requesting} onChange={(event) => input.select(event.target.value)}><option value="">Dispositivo predeterminado</option>{input.deviceId && !inputs.some((device) => device.deviceId === input.deviceId) && <option value={input.deviceId}>Dispositivo seleccionado</option>}{inputs.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `${label} ${index + 1}`}</option>)}</select></label>{input.error && <div className="preview-error" role="alert"><p>{input.error}</p><button type="button" disabled={busy || input.requesting} onClick={() => void input.start(input.deviceId)}><RefreshCw size={16} />Reintentar {label.toLowerCase()}</button></div>}{input.notice && <p className="preview-recovery" role="status">{input.notice}</p>}</div>;
      })}
    </div>
    <MicrophoneMeter track={microphone.track as LocalAudioTrack | null} />
    {deviceError && <p className="preview-error" role="alert">No pudimos listar los dispositivos. <button type="button" onClick={() => void refresh()}>Reintentar búsqueda</button></p>}
    <p className="preview-help">Puedes entrar sin cámara y activarla después. Estos medios son locales: solo se compartirán al confirmar el ingreso.</p>
    <button type="button" className="preview-join" disabled={pending || insecure} onClick={() => {
      if (pending || insecure) return;
      const choices = { audioEnabled: !!microphone.track, videoEnabled: !!camera.track, audioDeviceId: microphone.deviceId, videoDeviceId: camera.deviceId };
      camera.stop(); microphone.stop();
      void onJoin(choices);
    }}>{busy ? "Solicitando acceso…" : joinLabel}</button>
  </div>;
}
