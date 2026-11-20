import { useEffect, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@livekit/components-react", () => ({
  LiveKitRoom: ({ children, onConnected }: { children: ReactNode; onConnected?: () => void }) => {
    useEffect(() => { onConnected?.(); }, [onConnected]);
    return <div data-testid="livekit-room">{children}</div>;
  },
  PreJoin: ({ onSubmit, joinLabel }: { onSubmit: (choices: { audioEnabled: boolean; videoEnabled: boolean }) => void; joinLabel: string }) => (
    <button onClick={() => onSubmit({ audioEnabled: true, videoEnabled: true })}>{joinLabel}</button>
  ),
  MediaDeviceSelect: () => <ul />,
  RoomAudioRenderer: () => null,
  VideoTrack: () => <video />,
  useRoomContext: () => ({ localParticipant: { setMicrophoneEnabled: vi.fn(), setCameraEnabled: vi.fn(), isSpeaking: true }, remoteParticipants: new Map(), disconnect: vi.fn() }),
  useLocalParticipant: () => ({ localParticipant: { setMicrophoneEnabled: vi.fn(), setCameraEnabled: vi.fn(), isSpeaking: true }, isMicrophoneEnabled: true, isCameraEnabled: true }),
  useParticipants: () => [],
  useTracks: () => [],
}));

import { LiveKitConsultation } from "../features/appointments/LiveKitConsultation";

const appointment = {
  id: 12,
  code: "VS-LK-12",
  patient: "Paciente",
  doctor: "Médico",
  specialty: "Medicina general",
  plan: "Premium",
  starts_at: "2026-11-15T20:00:00Z",
  ends_at: "2026-11-15T20:30:00Z",
  status: "CONFIRMED",
  version: 1,
  copay: 0,
  modality: "VIRTUAL" as const,
  cancelled_at: null,
  cancellation_reason: null,
  economic_review: false,
  location: null,
  virtual_status: "SALA_DISPONIBLE",
  livekit_enabled: true,
  livekit_connection_state: "WAITING" as const,
};

function mount(role: "PATIENT" | "DOCTOR", item = appointment) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[role === "PATIENT" ? "/portal/appointments/12/teleconsult" : "/doctor/appointments/12/teleconsult"]}>
        <Routes>
          <Route path="/portal/appointments/:id/teleconsult" element={<LiveKitConsultation appointmentId="12" role="PATIENT" />} />
          <Route path="/doctor/appointments/:id/teleconsult" element={<LiveKitConsultation appointmentId="12" role="DOCTOR" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function json(data: unknown, status = 200) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => data } as Response);
}

describe("LiveKit consultation experience", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("asks the patient endpoint for a token before opening the media room", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/appointments/12/teleconsult") return json(appointment);
      if (url === "/api/appointments/12/livekit-token") return json({ token: "short-lived-token", server_url: "ws://localhost:7880", expires_in_seconds: 600 });
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    mount("PATIENT");
    fireEvent.click(await screen.findByRole("button", { name: "Ingresar a videollamada" }));
    expect(await screen.findByRole("button", { name: "Salir de la llamada" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/appointments/12/livekit-token", expect.objectContaining({ method: "POST" }));
  });

  it("requires a doctor confirmation to finalize the persistent consultation", async () => {
    let finished = false;
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/doctor/appointments/12/teleconsult") return json({ ...appointment, status: finished ? "ATTENDED" : "IN_PROGRESS", virtual_status: finished ? "FINALIZADA" : "EN_ATENCION" });
      if (url === "/api/doctor/appointments/12/livekit-token") return json({ token: "doctor-token", server_url: "ws://localhost:7880", expires_in_seconds: 600 });
      if (url === "/api/doctor/appointments/12/livekit-finalize") { finished = true; return json({ appointment_status: "ATTENDED", status: "FINALIZADA", idempotent: false, finalized_at: "2026-11-15T20:25:00Z", started_at: "2026-11-15T20:00:00Z" }); }
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal("fetch", fetch);
    mount("DOCTOR");
    fireEvent.click(await screen.findByRole("button", { name: "Iniciar videollamada" }));
    await screen.findByRole("button", { name: "Salir de la llamada" });
    fireEvent.click(screen.getByRole("button", { name: "Finalizar consulta" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar y finalizar" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/doctor/appointments/12/livekit-finalize", expect.objectContaining({ method: "POST" })));
    expect(await screen.findByRole("heading", { name: "Consulta finalizada" })).toBeInTheDocument();
  });

  it("does not display the prejoin form for a finalized or cancelled appointment", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...appointment, status: "ATTENDED", livekit_enabled: true })));
    mount("PATIENT");
    expect(await screen.findByRole("heading", { name: "Consulta finalizada" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ingresar a videollamada" })).not.toBeInTheDocument();
  });
});
