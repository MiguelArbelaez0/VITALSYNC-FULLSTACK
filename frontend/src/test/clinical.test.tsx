import { it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { DoctorClinicalHistory } from "../features/doctor/ClinicalHistory";
import { DoctorPasswordSetup } from "../features/doctor/DoctorPassword";
import { AuthProvider } from "../hooks/useAuth";
const user = {
  id: 3,
  doctor_id: 1,
  name: "Doctora ficticia",
  role: "DOCTOR",
  must_change_password: true,
};
function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function mount(node: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={["/doctor/patients/2/clinical-history"]}>
        <AuthProvider>
          <Routes>
            <Route
              path="/doctor/patients/:id/clinical-history"
              element={node}
            />
            <Route path="/doctor" element={<p>Agenda habilitada</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const visit = {
  id: 7,
  occurred_at: "2026-10-01T10:00:00Z",
  doctor: "Doctora ficticia",
  specialty: "Medicina general",
  reason: "Revisión ficticia",
  diagnosis: "Diagnóstico simulado",
};
const record = {
  id: 1,
  demo_marker: "DATOS FICTICIOS DE DEMOSTRACIÓN",
  read_only: true,
  patient: {
    id: 2,
    name: "Paciente ficticio",
    age: null,
    birth_date: null,
    demographic_note: null,
  },
  backgrounds: [{ category: "FAMILY", description: "Familia ficticia" }],
  allergies: [
    { substance: "Alérgeno simulado", reaction: "Reacción ficticia" },
  ],
  medications: [
    {
      name: "Medicamento académico",
      note: "Sin prescripción real",
      status: "PREVIOUS",
    },
  ],
  encounters: [visit],
};
it("presenta historia de solo lectura y carga el detalle autorizado al seleccionarlo", async () => {
  const fetch = vi.fn(async (url: string) =>
    response(
      url.endsWith("/auth/me")
        ? user
        : url.endsWith("/encounters/7")
          ? {
              ...visit,
              demo_marker: record.demo_marker,
              observations: "Observación académica",
              recommendations: "Solo simulación",
              vitals: {
                systolic: 120,
                diastolic: 80,
                heart_rate: 70,
                temperature_c: 36.5,
                spo2: 98,
              },
            }
          : record,
    ),
  );
  vi.stubGlobal("fetch", fetch);
  mount(<DoctorClinicalHistory />);
  expect(await screen.findByText(record.demo_marker)).toBeVisible();
  expect(screen.getByText("Familia ficticia")).toBeVisible();
  expect(screen.getByText("Alérgeno simulado")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /Guardar/ }),
  ).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([u]) => u.endsWith("/encounters/7"))).toBe(
    false,
  );
  await userEvent.click(
    screen.getByRole("button", { name: /Ver detalle de consulta/ }),
  );
  expect(await screen.findByText("Observación académica")).toBeVisible();
  expect(screen.getByText("120/80")).toBeVisible();
});
it.each([401, 403, 404])(
  "controla HTTP %s sin exponer datos clínicos",
  async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/auth/me")
          ? response(user)
          : response({ detail: "Historia no disponible" }, status),
      ),
    );
    mount(<DoctorClinicalHistory />);
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.queryByText(record.demo_marker)).not.toBeInTheDocument();
    expect(screen.queryByText("Familia ficticia")).not.toBeInTheDocument();
  },
);
it("exige cambio individual de contraseña y refresca la sesión", async () => {
  let changed = false;
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("/doctor/password")) {
      changed = true;
      return response({ message: "ok" });
    }
    return response({ ...user, must_change_password: !changed });
  });
  vi.stubGlobal("fetch", fetch);
  mount(<DoctorPasswordSetup />);
  const save = await screen.findByRole("button", {
    name: "Guardar contraseña",
  });
  expect(save).toBeDisabled();
  await userEvent.type(
    screen.getByLabelText("Contraseña actual o inicial"),
    "TemporalPrueba2026!",
  );
  await userEvent.type(
    screen.getByLabelText("Nueva contraseña", { exact: true }),
    "IndividualPrueba2026!",
  );
  await userEvent.type(
    screen.getByLabelText("Repetir nueva contraseña"),
    "IndividualPrueba2026!",
  );
  await userEvent.click(save);
  expect(await screen.findByText("Agenda habilitada")).toBeVisible();
  expect(
    fetch.mock.calls.some(
      ([u, o]) => u.endsWith("/doctor/password") && o?.method === "POST",
    ),
  ).toBe(true);
});
