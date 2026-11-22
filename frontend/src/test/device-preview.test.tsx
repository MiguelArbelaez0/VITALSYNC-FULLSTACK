import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const sdk = vi.hoisted(() => ({ camera: vi.fn(), microphone: vi.fn(), cleanup: vi.fn(async () => {}) }));
vi.mock("livekit-client", () => ({ createLocalVideoTrack: sdk.camera, createLocalAudioTrack: sdk.microphone, createAudioAnalyser: () => ({ calculateVolume: () => 0.35, cleanup: sdk.cleanup }) }));
import { DevicePreview } from "../features/appointments/DevicePreview";

function track(id: string) {
  return { mediaStreamTrack: { onended: null as (() => void) | null, getSettings: () => ({ deviceId: id }) }, attach: vi.fn(), detach: vi.fn(), stop: vi.fn() };
}
const devices = ["cam-a", "cam-b", "mic-a", "mic-b"].map((id) => ({ deviceId: id, kind: id.startsWith("cam") ? "videoinput" : "audioinput", label: id }));
function mount(onJoin = vi.fn(async () => {})) { return { ...render(<DevicePreview busy={false} joinLabel="Ingresar a videollamada" onJoin={onJoin} />), onJoin }; }
function failure(name: string) { return new DOMException("Internal device detail that must not appear", name); }

describe("Private local device preview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn(), enumerateDevices: vi.fn(async () => devices), addEventListener: vi.fn(), removeEventListener: vi.fn() } });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    sdk.camera.mockImplementation(async (options) => track(options?.deviceId?.exact || "cam-a"));
    sdk.microphone.mockImplementation(async (options) => track(options?.deviceId?.exact || "mic-a"));
  });

  it("starts only on user action, survives parent rerenders and stops on unmount", async () => {
    const camera = track("cam-a"); sdk.camera.mockResolvedValue(camera);
    const view = mount();
    expect(sdk.camera).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    await screen.findByText("Cámara activa · Solo vista previa");
    await waitFor(() => expect(camera.attach).toHaveBeenCalledWith(screen.getByLabelText("Vista previa local de tu cámara")));
    view.rerender(<DevicePreview busy={false} joinLabel="Ingresar a videollamada" onJoin={async () => {}} />);
    expect(sdk.camera).toHaveBeenCalledTimes(1); expect(camera.stop).not.toHaveBeenCalled();
    view.unmount(); expect(camera.stop).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["NotAllowedError", "En Chrome"], ["NotFoundError", "No encontramos la cámara"],
    ["NotReadableError", "Otra aplicación"], ["OverconstrainedError", "no es compatible"], ["AbortError", "No se pudo iniciar la cámara"],
  ])("explains %s and recovers after retry", async (name, message) => {
    sdk.camera.mockRejectedValueOnce(failure(name));
    mount(); fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText("Internal device detail that must not appear")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar cámara" }));
    await screen.findByText("Cámara activa · Solo vista previa");
  });

  it("recovers incompatible saved device constraints with the default capture", async () => {
    sdk.camera.mockRejectedValueOnce(failure("OverconstrainedError"));
    mount(); await screen.findByRole("option", { name: "cam-b" });
    fireEvent.change(screen.getByLabelText("Seleccionar cámara"), { target: { value: "cam-b" } });
    fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    await screen.findByText(/Se recuperó el dispositivo predeterminado/);
    expect(sdk.camera).toHaveBeenNthCalledWith(1, { deviceId: { exact: "cam-b" } });
    expect(sdk.camera).toHaveBeenNthCalledWith(2, {});
  });

  it("switches both devices, releases previous tracks and submits the actual selected inputs", async () => {
    const camera = track("cam-a"), microphone = track("mic-a"), newCamera = track("cam-b"), newMic = track("mic-b");
    sdk.camera.mockResolvedValueOnce(camera).mockResolvedValueOnce(newCamera);
    sdk.microphone.mockResolvedValueOnce(microphone).mockResolvedValueOnce(newMic);
    const view = mount();
    fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    fireEvent.click(screen.getByRole("button", { name: "Activar micrófono" }));
    await screen.findByRole("button", { name: "Desactivar micrófono" });
    fireEvent.change(screen.getByLabelText("Seleccionar cámara"), { target: { value: "cam-b" } });
    fireEvent.change(screen.getByLabelText("Seleccionar micrófono"), { target: { value: "mic-b" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Ingresar a videollamada" })).toBeEnabled());
    expect(camera.stop).toHaveBeenCalledTimes(1); expect(microphone.stop).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Ingresar a videollamada" }));
    expect(view.onJoin).toHaveBeenCalledWith({ audioEnabled: true, videoEnabled: true, audioDeviceId: "mic-b", videoDeviceId: "cam-b" });
    expect(newCamera.stop).toHaveBeenCalledTimes(1); expect(newMic.stop).toHaveBeenCalledTimes(1);
  });

  it("allows audio-only entry after voluntarily stopping the camera", async () => {
    const camera = track("cam-a"); sdk.camera.mockResolvedValue(camera);
    const view = mount();
    fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    fireEvent.click(await screen.findByRole("button", { name: "Desactivar cámara" }));
    fireEvent.click(screen.getByRole("button", { name: "Activar micrófono" }));
    await screen.findByText("Habla para comprobar el micrófono");
    fireEvent.click(screen.getByRole("button", { name: "Ingresar a videollamada" }));
    expect(view.onJoin).toHaveBeenCalledWith(expect.objectContaining({ videoEnabled: false, audioEnabled: true }));
    expect(camera.stop).toHaveBeenCalledTimes(1);
  });

  it("does not let microphone denial hide a usable camera", async () => {
    sdk.microphone.mockRejectedValueOnce(failure("NotAllowedError"));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    fireEvent.click(screen.getByRole("button", { name: "Activar micrófono" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Permiso denegado para el micrófono");
    expect(screen.getByText("Cámara activa · Solo vista previa")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ingresar a videollamada" })).toBeEnabled();
  });

  it("blocks entry only during pending acquisition and releases late tracks after unmount", async () => {
    let resolve!: (value: ReturnType<typeof track>) => void;
    sdk.camera.mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    const view = mount(); fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    expect(screen.getByRole("button", { name: "Ingresar a videollamada" })).toBeDisabled();
    view.unmount(); const late = track("late-camera");
    await act(async () => { resolve(late); });
    expect(late.stop).toHaveBeenCalledTimes(1);
  });

  it("explains insecure origins without asking for media", async () => {
    vi.stubGlobal("isSecureContext", false); mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTPS o desde http://localhost:5188");
    expect(screen.getByRole("button", { name: "Ingresar a videollamada" })).toBeDisabled();
    expect(sdk.camera).not.toHaveBeenCalled();
  });

  it("explains an unplugged camera and releases its track", async () => {
    const camera = track("cam-a"); sdk.camera.mockResolvedValueOnce(camera);
    mount(); fireEvent.click(screen.getByRole("button", { name: "Activar cámara" }));
    await screen.findByText("Cámara activa · Solo vista previa");
    act(() => camera.mediaStreamTrack.onended?.());
    expect(await screen.findByRole("alert")).toHaveTextContent("Se desconectó la cámara");
    expect(camera.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Reintentar cámara" })).toBeEnabled();
  });

  it("offers a retry when the device inventory cannot be read", async () => {
    vi.mocked(navigator.mediaDevices.enumerateDevices).mockRejectedValueOnce(new Error("inventory failure"));
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos listar los dispositivos");
    fireEvent.click(screen.getByRole("button", { name: "Reintentar búsqueda" }));
    await screen.findByRole("option", { name: "cam-b" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
