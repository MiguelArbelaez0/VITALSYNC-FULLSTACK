import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "../hooks/useAuth";
import { Protected } from "../app/App";
import { Auth } from "../features/auth/Auth";
import {
  DoctorDashboard,
  DoctorAgenda,
  DoctorDetail,
  DoctorPatients,
  DoctorRoom,
} from "../features/doctor/DoctorPortal";

const medicalUser = {
  id: 3,
  doctor_id: 2,
  name: "Dr. Alejandro Méndez",
  role: "DOCTOR",
  email: "medico@vitalsync.demo",
};
const appointment = {
  id: 12,
  code: "VS-MEDICAL",
  patient_id: 2,
  patient: "Paciente Asignado",
  doctor: medicalUser.name,
  specialty: "Cardiología",
  starts_at: new Date(Date.now() + 86400000).toISOString(),
  ends_at: new Date(Date.now() + 88200000).toISOString(),
  duration_minutes: 30,
  modality: "VIRTUAL",
  status: "CONFIRMED",
  version: 1,
  completion_source: null,
  simulated_completed_at: null,
  clinically_attended: false,
  history: [],
};
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function mock(
  extra: (path: string, options?: RequestInit) => Response | undefined,
  account: unknown = medicalUser,
) {
  const fn = vi.fn(
    async (url: string, options?: RequestInit) =>
      extra(url.replace("/api", ""), options) ??
      (url === "/api/auth/me"
        ? response(account)
        : response({ detail: "No definido" }, 404)),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}
function mount(element: React.ReactNode, path = "/doctor") {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>{element}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
describe("Portal médico", () => {
  it("redirige el login médico al portal profesional", async () => {
    let logged = false;
    mock((path) => {
      if (path === "/auth/me")
        return logged
          ? response(medicalUser)
          : response({ detail: "Sin sesión" }, 401);
      if (path === "/auth/login") {
        logged = true;
        return response(medicalUser);
      }
    });
    mount(
      <Routes>
        <Route path="/login" element={<Auth />} />
        <Route path="/doctor" element={<p>Destino médico</p>} />
      </Routes>,
      "/login",
    );
    await userEvent.type(
      screen.getByLabelText("Correo electrónico"),
      "medico@vitalsync.demo",
    );
    await userEvent.type(
      screen.getByLabelText("Contraseña", { exact: true }),
      "DoctorPrueba2026!",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Iniciar sesión" }),
    );
    expect(await screen.findByText("Destino médico")).toBeInTheDocument();
  });
  it.each([
    ["DOCTOR", "PATIENT", "Acceso exclusivo para pacientes"],
    ["PATIENT", "DOCTOR", "Acceso exclusivo para médicos"],
  ] as const)(
    "separa %s de las rutas %s",
    async (actual, required, message) => {
      mock(() => undefined, { ...medicalUser, role: actual });
      mount(
        <Routes>
          <Route element={<Protected role={required} />}>
            <Route path="/doctor" element={<p>Datos privados</p>} />
          </Route>
        </Routes>,
      );
      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(screen.queryByText("Datos privados")).not.toBeInTheDocument();
    },
  );
  it("controla la ausencia de perfil profesional", async () => {
    mock(() => undefined, { ...medicalUser, doctor_id: null });
    mount(
      <Routes>
        <Route element={<Protected role="DOCTOR" />}>
          <Route path="/doctor" element={<p>Datos privados</p>} />
        </Route>
      </Routes>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "perfil profesional válido",
    );
    expect(screen.queryByText("Datos privados")).not.toBeInTheDocument();
  });
  it("muestra métricas y próxima reserva de la API", async () => {
    mock((path) =>
      path === "/doctor/dashboard"
        ? response({
            doctor: { id: 2, name: medicalUser.name, specialty: "Cardiología" },
            date: "2026-11-12",
            metrics: {
              total: 7,
              presencial: 2,
              virtual: 5,
              pending: 4,
              completed: 3,
            },
            next_appointment: appointment,
            agenda: [],
          })
        : undefined,
    );
    mount(<DoctorDashboard />);
    expect(await screen.findByText("07")).toBeInTheDocument();
    expect(screen.getByText("05")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: appointment.patient }),
    ).toBeInTheDocument();
  });
  it("envía filtros de modalidad y estado al backend", async () => {
    const fetch = mock((path) =>
      path.startsWith("/doctor/appointments?")
        ? response([appointment])
        : undefined,
    );
    mount(<DoctorAgenda />);
    await screen.findByText(appointment.patient);
    await userEvent.selectOptions(
      screen.getByLabelText("Modalidad"),
      "VIRTUAL",
    );
    await userEvent.selectOptions(screen.getByLabelText("Estado"), "CONFIRMED");
    await waitFor(() =>
      expect(
        fetch.mock.calls.some(
          ([url]) =>
            url.includes("modality=VIRTUAL") &&
            url.includes("status=CONFIRMED"),
        ),
      ).toBe(true),
    );
  });
  it("exige motivo y confirmación y actualiza el estado al cancelar", async () => {
    let cancelled = false;
    const fetch = mock((path) => {
      if (path === "/doctor/appointments/12/cancel") {
        cancelled = true;
        return response({ status: "CANCELLED" });
      }
      if (path === "/doctor/appointments/12")
        return response({
          ...appointment,
          status: cancelled ? "CANCELLED" : "CONFIRMED",
          cancellation_reason: cancelled ? "Motivo profesional" : null,
        });
    });
    mount(
      <Routes>
        <Route path="/doctor/appointments/:id" element={<DoctorDetail />} />
      </Routes>,
      "/doctor/appointments/12",
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Cancelar cita" }),
    );
    expect(
      screen.getByRole("button", { name: "Confirmar cancelación" }),
    ).toBeDisabled();
    await userEvent.type(
      screen.getByLabelText("Motivo obligatorio"),
      "Motivo profesional",
    );
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(
      screen.getByRole("button", { name: "Confirmar cancelación" }),
    );
    expect(await screen.findByText("Cancelada")).toBeInTheDocument();
    expect(
      fetch.mock.calls.some(
        ([url, options]) =>
          url.endsWith("/cancel") &&
          JSON.parse(options!.body as string).confirmed === true,
      ),
    ).toBe(true);
  });
  it("consulta únicamente las citas relacionadas al paciente elegido", async () => {
    const fetch = mock((path) =>
      path.startsWith("/doctor/patients?")
        ? response([{ id: 2, name: appointment.patient }])
        : path === "/doctor/patients/2"
          ? response({
              id: 2,
              name: appointment.patient,
              appointments: [appointment],
            })
          : undefined,
    );
    mount(<DoctorPatients />);
    await userEvent.click(
      await screen.findByRole("button", { name: appointment.patient }),
    );
    expect(
      await screen.findByText(appointment.code, { exact: false }),
    ).toBeInTheDocument();
    expect(
      fetch.mock.calls.some(([url]) => url === "/api/doctor/patients/2"),
    ).toBe(true);
  });
  it("finaliza la sala con eventos autorizados y retira sus acciones", async () => {
    let finished = false;
    const fetch = mock((path) => {
      if (path.endsWith("/events")) {
        finished = true;
        return response({ status: "FINALIZADA" });
      }
      if (path.endsWith("/teleconsult"))
        return response({
          ...appointment,
          status: finished ? "ATTENDED" : "IN_PROGRESS",
          completion_source: finished ? "DEMO" : null,
          virtual_status: finished ? "FINALIZADA" : "EN_ATENCION",
          demo_mode: true,
          virtual_state: {
            patient_present: true,
            doctor_present: true,
            available_actions: finished ? [] : ["FINALIZE"],
          },
        });
    });
    mount(
      <Routes>
        <Route
          path="/doctor/appointments/:id/teleconsult"
          element={<DoctorRoom />}
        />
      </Routes>,
      "/doctor/appointments/12/teleconsult",
    );
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Finalizar teleconsulta simulada",
      }),
    );
    expect(
      await screen.findByText(/La simulación finalizó/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Finalizar teleconsulta simulada" }),
    ).not.toBeInTheDocument();
    expect(
      fetch.mock.calls.some(
        ([url, opts]) =>
          url.endsWith("/events") &&
          JSON.parse(opts!.body as string).event === "FINALIZE",
      ),
    ).toBe(true);
  });
  it("no ofrece simulaciones fuera del modo demostrativo", async () => {
    mock((path) =>
      path.endsWith("/teleconsult")
        ? response({
            ...appointment,
            demo_mode: false,
            virtual_state: { available_actions: [] },
          })
        : undefined,
    );
    mount(
      <Routes>
        <Route
          path="/doctor/appointments/:id/teleconsult"
          element={<DoctorRoom />}
        />
      </Routes>,
      "/doctor/appointments/12/teleconsult",
    );
    expect(
      await screen.findByText(/deshabilitadas fuera del modo/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Simular|Finalizar/ }),
    ).not.toBeInTheDocument();
  });
});
