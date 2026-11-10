import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthProvider, useAuth } from "../hooks/useAuth";
import { Auth } from "../features/auth/Auth";
import { Protected } from "../app/App";
import { Dashboard } from "../features/dashboard/Dashboard";
import { Doctors, DoctorProfile } from "../features/doctors/Doctors";
import { Booking } from "../features/appointments/Booking";
import {
  AppointmentDetail,
  Appointments,
  Teleconsultation,
} from "../features/appointments/Appointments";
import { PaymentControls, Plans } from "../features/plans/Plans";
const user = {
  id: 2,
  name: "Valentina Torres",
  email: "paciente@vitalsync.demo",
  phone: "",
  role: "PATIENT",
};
const appointment = {
  id: 1,
  code: "VS-TEST",
  doctor: "Dra. Isabella Ríos",
  specialty: "Medicina general",
  patient: "Valentina Torres",
  plan: "Premium",
  starts_at: "2026-11-12T14:00:00Z",
  ends_at: "2026-11-12T14:30:00Z",
  copay: 0,
  status: "CONFIRMED",
  version: 1,
  history: [],
};
function respond(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function mockApi(
  routes: Record<string, unknown>,
  extra?: (path: string, options?: RequestInit) => Response | undefined,
) {
  const fn = vi.fn(async (url: string, options?: RequestInit) => {
    const path = url.replace("/api", "");
    const custom = extra?.(path, options);
    if (custom) return custom;
    if (path === "/auth/me") return respond(user);
    if (path === "/config")
      return respond({
        demo_mode: true,
        cancellation_hours: 2,
        hold_minutes: 10,
      });
    if (path in routes) return respond(routes[path]);
    return respond({ detail: "Ruta de prueba no definida: " + path }, 404);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
function wrapper(node: React.ReactNode, path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>{node}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
describe("Autenticación y acceso", () => {
  it("cierra la sesión y retira el contenido protegido", async () => {
    let loggedOut = false;
    mockApi({}, (path) => {
      if(path === '/auth/logout') { loggedOut = true; return respond({message:'Sesión cerrada'}); }
      if(path === '/auth/me' && loggedOut) return respond({detail:'Sesión expirada'},401);
    });
    function Exit() { const {logout} = useAuth(); return <button onClick={()=>void logout()}>Salir de prueba</button>; }
    wrapper(<Routes><Route element={<Protected/>}><Route path="/portal" element={<Exit/>}/></Route><Route path="/login" element={<p>Sesión finalizada</p>}/></Routes>, '/portal');
    await userEvent.click(await screen.findByRole('button',{name:'Salir de prueba'}));
    expect(await screen.findByText('Sesión finalizada')).toBeInTheDocument();
  });
  it("valida registro antes de enviar", async () => {
    const fetch = mockApi({});
    wrapper(<Auth register />);
    await userEvent.click(
      screen.getByRole("button", { name: "Crear mi cuenta" }),
    );
    expect(
      await screen.findByText("Ingresa un correo válido"),
    ).toBeInTheDocument();
    expect(screen.getByText("Usa al menos 10 caracteres")).toBeInTheDocument();
    expect(fetch.mock.calls.every((c) => c[0].endsWith("/auth/me"))).toBe(true);
  });
  it("rechaza formato de cédula inválido en el registro React", async () => {
    const fetch = mockApi({});
    wrapper(<Auth register />);
    await userEvent.type(screen.getByPlaceholderText("Tus nombres"), "Ana Maria");
    await userEvent.type(screen.getByPlaceholderText("Tus apellidos"), "Torres Ríos");
    await userEvent.type(screen.getByPlaceholderText("Solo dígitos"), "123 456");
    await userEvent.type(screen.getByPlaceholderText("tu@correo.com"), "ana@example.com");
    await userEvent.type(screen.getByPlaceholderText("+57 300 123 4567"), "+57 300 123 4567");
    await userEvent.type(screen.getByPlaceholderText("Al menos 10 caracteres"), "Password2026!");
    await userEvent.type(screen.getByPlaceholderText("Escribe nuevamente tu contraseña"), "Password2026!");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));
    expect(await screen.findByText("Escribe de 6 a 10 dígitos, sin espacios ni puntos")).toBeInTheDocument();
    expect(fetch.mock.calls.some((call) => call[0] === "/api/auth/register")).toBe(false);
  });
  it("valida la fortaleza y coincidencia de las contraseñas", async () => {
    const fetch = mockApi({});
    wrapper(<Auth register />);
    await userEvent.type(screen.getByPlaceholderText("Tus nombres"), "Ana Maria");
    await userEvent.type(screen.getByPlaceholderText("Tus apellidos"), "Torres Ríos");
    await userEvent.type(screen.getByPlaceholderText("Solo dígitos"), "12345678");
    await userEvent.type(screen.getByPlaceholderText("tu@correo.com"), "ana@example.com");
    await userEvent.type(screen.getByPlaceholderText("+57 300 123 4567"), "+57 300 123 4567");
    const password = screen.getByPlaceholderText("Al menos 10 caracteres");
    const confirmation = screen.getByPlaceholderText("Escribe nuevamente tu contraseña");
    await userEvent.type(password, "lowercasepass1");
    await userEvent.type(confirmation, "lowercasepass1");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));
    expect(await screen.findByText("Usa mayúsculas, minúsculas y al menos un número")).toBeInTheDocument();
    await userEvent.clear(password);
    await userEvent.type(password, "Password2026!");
    await userEvent.clear(confirmation);
    await userEvent.type(confirmation, "Different2026!");
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));
    expect(await screen.findByText("Las contraseñas no coinciden")).toBeInTheDocument();
    expect(fetch.mock.calls.some((call) => call[0] === "/api/auth/register")).toBe(false);
  });
  it("crea una cuenta independiente con cédula como texto y privacidad aceptada", async () => {
    const fetch = mockApi({}, (path) =>
      path === "/auth/register"
        ? respond({ ...user, name: "Ana Maria Torres Ríos", has_document: true, document_masked: "••••3456" })
        : undefined,
    );
    wrapper(
      <Routes>
        <Route path="/register" element={<Auth register />} />
        <Route path="/portal" element={<p>Portal abierto</p>} />
      </Routes>,
      "/register",
    );
    await userEvent.type(screen.getByPlaceholderText("Tus nombres"), "Ana Maria");
    await userEvent.type(screen.getByPlaceholderText("Tus apellidos"), "Torres Ríos");
    await userEvent.type(screen.getByPlaceholderText("Solo dígitos"), "00123456");
    await userEvent.type(screen.getByPlaceholderText("tu@correo.com"), "Ana@Example.com");
    await userEvent.type(screen.getByPlaceholderText("+57 300 123 4567"), "+57 300 123 4567");
    await userEvent.type(screen.getByPlaceholderText("Al menos 10 caracteres"), "Password2026!");
    await userEvent.type(screen.getByPlaceholderText("Escribe nuevamente tu contraseña"), "Password2026!");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));
    expect(await screen.findByText("Portal abierto")).toBeInTheDocument();
    const [, request] = fetch.mock.calls.find((call) => call[0] === "/api/auth/register")!;
    const body = JSON.parse(String(request?.body));
    expect(body).toMatchObject({
      given_names: "Ana Maria",
      surnames: "Torres Ríos",
      document_type: "CC",
      document_number: "00123456",
      privacy_accepted: true,
    });
    expect(body.role).toBeUndefined();
    expect(body.confirm_password).toBeUndefined();
  });
  it("envía login y navega al portal", async () => {
    const fetch = mockApi({}, (path) =>
      path === "/auth/login" ? respond(user) : undefined,
    );
    wrapper(
      <Routes>
        <Route path="/login" element={<Auth />} />
        <Route path="/portal" element={<p>Portal abierto</p>} />
      </Routes>,
      "/login",
    );
    await userEvent.type(
      screen.getByLabelText("Correo electrónico"),
      "paciente@vitalsync.demo",
    );
    await userEvent.type(screen.getByLabelText("Contraseña"), "Paciente2026!");
    await userEvent.click(
      screen.getByRole("button", { name: "Iniciar sesión" }),
    );
    expect(await screen.findByText("Portal abierto")).toBeInTheDocument();
    expect(fetch.mock.calls.some((c) => c[0] === "/api/auth/login")).toBe(true);
  });
  it("redirige una sesión no autenticada", async () => {
    mockApi({}, (path) =>
      path === "/auth/me"
        ? respond({ detail: "Sesión expirada" }, 401)
        : undefined,
    );
    wrapper(
      <Routes>
        <Route element={<Protected />}>
          <Route path="/portal" element={<p>Privado</p>} />
        </Route>
        <Route path="/login" element={<p>Acceso requerido</p>} />
      </Routes>,
      "/portal",
    );
    expect(await screen.findByText("Acceso requerido")).toBeInTheDocument();
    expect(screen.queryByText("Privado")).not.toBeInTheDocument();
  });
});
describe("Datos, estados y disponibilidad", () => {
  it("renderiza métricas reales del dashboard", async () => {
    mockApi({
      "/dashboard": {
        name: user.name,
        plan: { status: "INACTIVE", plan: null, expires_at: null },
        upcoming_count: 0,
        next_appointment: null,
        unread_notifications: 3,
      },
    });
    wrapper(<Dashboard />);
    expect(await screen.findByText("Hola, Valentina 👋")).toBeInTheDocument();
    expect(screen.getByText("03")).toBeInTheDocument();
    expect(screen.getByText("Sin activar")).toBeInTheDocument();
    expect(screen.getByText("No tienes próximas citas programadas")).toBeInTheDocument();
    expect(screen.getByText("Agendar una cita")).toBeInTheDocument();
  });
  it("muestra carga y error del servicio", async () => {
    mockApi({}, (path) =>
      path === "/dashboard"
        ? respond({ detail: "Base de datos no disponible" }, 503)
        : undefined,
    );
    wrapper(<Dashboard />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Base de datos no disponible",
    );
  });
  it("consulta médicos y filtros", async () => {
    const fetch = mockApi(
      {
        "/specialties": [{ id: 1, name: "Medicina general" }],
        "/doctors?search=&modality=VIRTUAL": [
          { id: 1, name: "Dra. Isabella Ríos", specialty: "Medicina general", modalities: ["PRESENCIAL", "VIRTUAL"] },
        ],
      },
      (path) =>
        path.startsWith("/doctors?search=I") ? respond([]) : undefined,
    );
    wrapper(<Doctors />);
    expect(await screen.findByText("Dra. Isabella Ríos")).toBeInTheDocument();
    await userEvent.type(
      screen.getByRole("textbox", { name: "Buscar médico" }),
      "I",
    );
    expect(
      await screen.findByText("No encontramos médicos con estos filtros"),
    ).toBeInTheDocument();
    expect(fetch.mock.calls.some((c) => c[0].includes("search=I"))).toBe(true);
  });
  it("selecciona fecha y retiene un horario mediante backend", async () => {
    const fetch = mockApi(
      {
        "/doctors/1": {
          id: 1,
          name: "Dra. Isabella Ríos",
          specialty: "Medicina general",
          specialty_id: 1,
          bio: "Perfil ficticio",
          modalities: ["PRESENCIAL", "VIRTUAL"],
        },
        "/my-plan": { status: "ACTIVE", plan: { id: 1, specialty_ids: [1], modalities: ["PRESENCIAL"] } },
        "/doctors/1/availability?modality=PRESENCIAL": [
          {
            id: 10,
            starts_at: "2026-11-12T14:00:00Z",
            ends_at: "2026-11-12T14:30:00Z",
            available: true,
          },
          {
            id: 11,
            starts_at: "2026-11-13T15:00:00Z",
            ends_at: "2026-11-13T15:30:00Z",
            available: true,
          },
        ],
      },
      (path) => (path === "/holds" ? respond({ id: 9 }, 201) : undefined),
    );
    wrapper(
      <Routes>
        <Route path="/portal/doctors/:id" element={<DoctorProfile />} />
        <Route path="/portal/booking/:id" element={<p>Retención creada</p>} />
      </Routes>,
      "/portal/doctors/1?modality=PRESENCIAL",
    );
    await screen.findByRole("combobox");
    await userEvent.selectOptions(screen.getByRole("combobox"), "2026-11-13");
    await userEvent.click(screen.getByRole("button", { name: /10:00/ }));
    await userEvent.click(
      screen.getByRole("button", { name: "Retener horario y continuar" }),
    );
    expect(await screen.findByText("Retención creada")).toBeInTheDocument();
    expect(fetch.mock.calls.find((c) => c[0] === "/api/holds")?.[1]?.body).toBe(
      JSON.stringify({ availability_id: 11, modality: "PRESENCIAL" }),
    );
  });
});
describe("Reserva, comprobante y cancelación", () => {
  it("la sala virtual muestra avisos explícitos y persiste estados", async () => {
    const fetch = mockApi(
      {
        "/appointments/1/teleconsult": {
          ...appointment,
          modality: "VIRTUAL",
          virtual_status: "PROGRAMADA",
          virtual_state: { status: "PROGRAMADA", lifecycle_status: "PROGRAMADA", patient_present: false, doctor_present: false, demo_clock_advanced: false, available_actions: ["OPEN_ROOM"], room_open_minutes: 5, wait_grace_minutes: 15, demo_mode: true },
          message: "Teleconsulta simulada — sin conexión de audio o video",
        },
      },
      (path) =>
        path === "/appointments/1/teleconsult/status"
          ? respond({ status: "SALA_DISPONIBLE" })
          : undefined,
    );
    wrapper(<Routes><Route path="/portal/appointments/:id/teleconsult" element={<Teleconsultation/>}/></Routes>, "/portal/appointments/1/teleconsult");
    expect(await screen.findByText("Teleconsulta simulada — sin conexión de audio o video")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abrir sala simulada" }));
    expect(fetch.mock.calls.some((c) => c[0] === "/api/appointments/1/teleconsult/status")).toBe(true);
  });
  it("ofrece simular la ausencia del paciente cuando la sala está disponible", async () => {
    const fetch = mockApi(
      {
        "/appointments/1/teleconsult": {
          ...appointment,
          modality: "VIRTUAL",
          virtual_status: "SALA_DISPONIBLE",
          virtual_state: { status: "PACIENTE_EN_ESPERA", lifecycle_status: "SALA_DISPONIBLE", patient_present: false, doctor_present: false, demo_clock_advanced: true, available_actions: ["PATIENT_ABSENT"], room_open_minutes: 5, wait_grace_minutes: 15, demo_mode: true },
          message: "Teleconsulta simulada — sin conexión de audio o video",
        },
      },
      (path) => path === "/appointments/1/teleconsult/status"
        ? respond({ status: "PACIENTE_AUSENTE" })
        : undefined,
    );
    wrapper(<Routes><Route path="/portal/appointments/:id/teleconsult" element={<Teleconsultation/>}/></Routes>, "/portal/appointments/1/teleconsult");
    await userEvent.click(await screen.findByRole("button", { name: "Registrar ausencia del paciente" }));
    expect(fetch.mock.calls.some((call) => call[1]?.body === JSON.stringify({ event: "PATIENT_ABSENT" }))).toBe(true);
  });
  it("muestra la finalización como solo lectura y enlaza el historial", async () => {
    mockApi({
      "/appointments/1/teleconsult": {
        ...appointment,
        modality: "VIRTUAL",
        status: "ATTENDED",
        virtual_status: "FINALIZADA",
        virtual_state: {
          status: "FINALIZADA", lifecycle_status: "FINALIZADA", patient_present: true,
          doctor_present: true, demo_clock_advanced: false, finalized_at: "2026-11-09T15:00:00Z",
          available_actions: [], room_open_minutes: 5, wait_grace_minutes: 15, demo_mode: true,
        },
      },
    });
    wrapper(<Routes><Route path="/portal/appointments/:id/teleconsult" element={<Teleconsultation/>}/></Routes>, "/portal/appointments/1/teleconsult");
    expect(await screen.findByText(/Atención finalizada en modo demostración/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /finalizar teleconsulta/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver historial de mi cita" })).toHaveAttribute("href", "/portal/appointments/1");
  });
  it("confirma una retención sin copago por API", async () => {
    const fetch = mockApi(
      {
        "/holds/9": {
          id: 9,
          doctor_id: 1,
          status: "ACTIVE",
          expires_at: new Date(Date.now() + 600000).toISOString(),
          starts_at: "2026-11-12T14:00:00Z",
          copay: 0,
        },
        "/doctors/1": {
          name: "Dra. Isabella Ríos",
          specialty: "Medicina general",
        },
      },
      (path) => (path === "/holds/9/confirm" ? respond({ id: 1 }) : undefined),
    );
    wrapper(
      <Routes>
        <Route path="/portal/booking/:id" element={<Booking />} />
        <Route path="/portal/appointments/:id" element={<p>Cita guardada</p>} />
      </Routes>,
      "/portal/booking/9",
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Confirmar cita" }),
    );
    expect(await screen.findByText("Cita guardada")).toBeInTheDocument();
    expect(fetch.mock.calls.some((c) => c[0] === "/api/holds/9/confirm")).toBe(
      true,
    );
  });
  it("no anuncia confirmación si backend rechaza", async () => {
    mockApi(
      {
        "/holds/9": {
          id: 9,
          doctor_id: 1,
          status: "ACTIVE",
          expires_at: new Date(Date.now() + 600000).toISOString(),
          starts_at: "2026-11-12T14:00:00Z",
          copay: 0,
        },
        "/doctors/1": { name: "Dra. Isabella Ríos" },
      },
      (path) =>
        path === "/holds/9/confirm"
          ? respond({ detail: "La retención ha vencido" }, 409)
          : undefined,
    );
    wrapper(
      <Routes>
        <Route path="/portal/booking/:id" element={<Booking />} />
      </Routes>,
      "/portal/booking/9",
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Confirmar cita" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La retención ha vencido",
    );
  });
  it("muestra comprobante y exige confirmación expresa al cancelar", async () => {
    let cancelled = false;
    const fetch = mockApi({}, (path, options) => {
      if (path === "/appointments/1" && options?.method === "POST")
        return undefined;
      if (path === "/appointments/1/cancel") {
        cancelled = true;
        return respond({ status: "CANCELLED" });
      }
      if (path === "/appointments/1")
        return respond({
          ...appointment,
          modality: "VIRTUAL",
          status: cancelled ? "CANCELLED" : "CONFIRMED",
          cancelled_at: cancelled ? "2026-11-08T14:00:00Z" : null,
        });
    });
    wrapper(
      <Routes>
        <Route
          path="/portal/appointments/:id"
          element={<AppointmentDetail />}
        />
      </Routes>,
      "/portal/appointments/1",
    );
    expect(await screen.findByText("VS-TEST")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Ver teleconsulta simulada" }),
    ).toHaveAttribute("href", "/portal/appointments/1/teleconsult");
    await userEvent.click(
      screen.getByRole("button", { name: "Cancelar cita" }),
    );
    expect(
      screen.getByRole("button", { name: "Confirmar cancelación" }),
    ).toBeDisabled();
    await userEvent.click(
      screen.getByRole("button", { name: "Conservar mi cita" }),
    );
    expect(cancelled).toBe(false);
    await userEvent.click(
      screen.getByRole("button", { name: "Cancelar cita" }),
    );
    await userEvent.type(
      screen.getByLabelText("Motivo de cancelación"),
      "Cambio de agenda",
    );
    await userEvent.click(
      screen.getByLabelText("Confirmo que deseo cancelar mi cita."),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Confirmar cancelación" }),
    );
    expect(await screen.findByText("Cancelada")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ver teleconsulta simulada" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "La cita está cancelada; la teleconsulta no está disponible.",
      ),
    ).toBeInTheDocument();
    expect(
      fetch.mock.calls.find((c) => c[0].endsWith("/cancel"))?.[1]?.body,
    ).toContain('"confirmed":true');
  });
  it("muestra canceladas desde el historial", async () => {
    mockApi({ "/appointments": [{ ...appointment, status: "CANCELLED" }] });
    wrapper(<Appointments />);
    await userEvent.click(
      screen.getByRole("tab", { name: "Historial · Canceladas" }),
    );
    expect(await screen.findByText("Cancelada")).toBeInTheDocument();
    expect(screen.getByText("Dra. Isabella Ríos")).toBeInTheDocument();
  });
  it("filtra Mis citas por modalidad sin mezclar virtuales y presenciales", async () => {
    mockApi({
      "/appointments": [
        { ...appointment, id: 1, modality: "VIRTUAL" },
        { ...appointment, id: 2, code: "VS-PRES", modality: "PRESENCIAL" },
      ],
    });
    wrapper(<Appointments />);
    await screen.findByText(/Cita virtual/);
    expect(screen.getByText(/Cita presencial/)).toBeInTheDocument();
    const filter = screen.getByRole("combobox", { name: "Filtrar citas por modalidad" });
    await userEvent.selectOptions(filter, "VIRTUAL");
    expect(screen.getByText(/Cita virtual/)).toBeInTheDocument();
    expect(screen.queryByText(/Cita presencial/)).not.toBeInTheDocument();
    await userEvent.selectOptions(filter, "PRESENCIAL");
    expect(screen.getByText(/Cita presencial/)).toBeInTheDocument();
    expect(screen.queryByText(/Cita virtual/)).not.toBeInTheDocument();
  });
  it("pago pendiente ofrece conciliación sin duplicar", async () => {
    const fetch = mockApi({
      "/payments": [{ id: 5, kind: "COPAY", hold_id: 9, status: "PENDING" }],
    });
    wrapper(
      <PaymentControls kind="COPAY" targetId={9} onApproved={() => {}} />,
    );
    expect(await screen.findByText("Pendiente")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Conciliar como aprobado" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Autorizar y simular aprobación" }),
    ).not.toBeInTheDocument();
    expect(fetch.mock.calls.every((c) => c[1]?.method !== "POST")).toBe(true);
  });
});

describe("Modalidades de atención", () => {
  it("prioriza teleconsulta simulada y muestra todas las modalidades del médico", async () => {
    const fetch = mockApi({
      "/doctors?search=&modality=VIRTUAL": [{
        id: 1,
        name: "Dra. Isabella Ríos",
        specialty_id: 1,
        specialty: "Medicina general",
        bio: "Profesional de demostración.",
        enabled: true,
        modalities: ["PRESENCIAL", "VIRTUAL"],
      }],
      "/specialties": [{ id: 1, name: "Medicina general" }],
    });
    wrapper(<Doctors />);
    const options = await screen.findAllByRole("button", { name: /Consulta|Cita/ });
    expect(options[0]).toHaveTextContent("Consulta virtual");
    expect(options[0]).toHaveTextContent("Recomendada");
    expect(options[0]).toHaveAttribute("aria-pressed", "true");
    const doctorModes = await screen.findByRole("group", { name: "Modalidades de Dra. Isabella Ríos" });
    expect(doctorModes).toHaveTextContent("Virtual");
    expect(doctorModes).toHaveTextContent("Presencial");
    expect(fetch.mock.calls.some(([url]) => url === "/api/doctors?search=&modality=VIRTUAL")).toBe(true);
  });
});

describe("Cancelación universal de planes", () => {
  const basic = { id: 1, name: "Básico", description: "Cobertura esencial", price: 59000, copay: 15000, duration_days: 30, specialty_ids: [1], modalities: ["PRESENCIAL"] };
  const standard = { id: 2, name: "Estándar", description: "Cobertura extendida", price: 109000, copay: 10000, duration_days: 30, specialty_ids: [1], modalities: ["PRESENCIAL", "VIRTUAL"] };
  const premium = { id: 3, name: "Premium", description: "Cobertura total", price: 189000, copay: 0, duration_days: 30, specialty_ids: [1], modalities: ["PRESENCIAL", "VIRTUAL"] };
  const expires = "2026-12-09T17:00:00Z";

  it("permite desistir y limita renovar/cancelar al plan activo", async () => {
    const fetch = mockApi({
      "/plans": [basic, standard, premium],
      "/my-plan": { status: "ACTIVE", plan: standard, expires_at: expires, cancelled_at: null },
      "/specialties": [{ id: 1, name: "Medicina general" }],
    }, (path) => path === "/payments" ? respond([]) : undefined);
    wrapper(<Plans />);
    await screen.findByText("Renovar plan");
    const planCard = (name: string) => screen.getAllByRole("heading", { name: new RegExp(`^${name}$`) })
      .map((heading) => heading.closest("article"))
      .find((article) => article !== null);
    const standardCard = planCard("Estándar");
    const basicCard = planCard("Básico");
    const premiumCard = planCard("Premium");
    expect(standardCard).toHaveTextContent("Renovar plan");
    expect(standardCard).toHaveTextContent("Cancelar plan");
    expect(standardCard).toHaveTextContent("Consultas virtuales");
    expect(basicCard).toHaveTextContent("Activar plan");
    expect(basicCard).not.toHaveTextContent("Cancelar plan");
    expect(basicCard).toHaveTextContent("No incluye consultas virtuales");
    expect(premiumCard).toHaveTextContent("Activar plan");
    expect(premiumCard).not.toHaveTextContent("Cancelar plan");

    await userEvent.click(within(standardCard!).getByRole("button", { name: "Cancelar plan" }));
    expect(await screen.findByText("Estándar", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Activo", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("Inmediatamente al confirmar", { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/Tus citas, pagos e historial se conservan/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mantener mi plan" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => url === "/api/my-plan/cancel")).toBe(false);
    expect(screen.getByText("Activo", { selector: "span" })).toBeInTheDocument();
  });

  it("confirma en el backend y refresca la cobertura y su historial", async () => {
    let cancelled = false;
    let cancellationBody: unknown;
    const fetch = mockApi({
      "/plans": [basic, standard, premium],
      "/specialties": [{ id: 1, name: "Medicina general" }],
    }, (path, options) => {
      if (path === "/my-plan") return respond(cancelled ? {
        status: "INACTIVE", plan: standard, expires_at: expires,
        cancelled_at: "2026-11-09T18:00:00Z", cancelled_by: 2,
        cancellation_history: [{ id: 1, plan_id: 2, plan_name: "Estándar", previous_status: "ACTIVE", new_status: "INACTIVE", policy: "IMMEDIATE", cancelled_at: "2026-11-09T18:00:00Z", effective_at: "2026-11-09T18:00:00Z", changed_by: 2, reason: "Cancelación confirmada" }],
      } : { status: "ACTIVE", plan: standard, expires_at: expires, cancelled_at: null });
      if (path === "/my-plan/cancel" && options?.method === "POST") {
        cancellationBody = JSON.parse(String(options.body));
        cancelled = true;
        return respond({ plan_id: 2, plan_name: "Estándar", previous_status: "ACTIVE", status: "INACTIVE", policy: "IMMEDIATE", cancelled_at: "2026-11-09T18:00:00Z", effective_at: "2026-11-09T18:00:00Z" });
      }
      return undefined;
    });
    wrapper(<Plans />);
    await screen.findByText("Renovar plan");
    const card = screen.getAllByRole("heading", { name: /^Estándar$/ })
      .map((heading) => heading.closest("article"))
      .find((article) => article !== null);
    await userEvent.click(within(card!).getByRole("button", { name: "Cancelar plan" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmar cancelación" }));
    expect(await screen.findByText(/Estándar se canceló/)).toBeInTheDocument();
    expect(cancellationBody).toEqual({ plan_id: 2, confirmed: true });
    expect(screen.getByText("Historial de planes")).toBeInTheDocument();
    expect(screen.getAllByText(/Cancelado el/).length).toBeGreaterThan(0);
    expect(await within(card!).findByRole("button", { name: "Activar plan" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancelar plan" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([url]) => url === "/api/my-plan").length).toBeGreaterThan(1);
  });
});
