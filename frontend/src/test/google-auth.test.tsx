import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
vi.hoisted(() => { vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "controlled-client.apps.googleusercontent.com"); });
vi.mock("../hooks/useAuth", () => ({ useAuth: () => ({ refresh: async () => {} }) }));
import { GoogleAccountLink, GoogleSignIn } from "../features/auth/GoogleAuth";
let callback: (result: { credential: string }) => void;
function mount(component: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Routes><Route path="/" element={component} /><Route path="/portal" element={<h1>Portal paciente</h1>} /><Route path="/doctor" element={<h1>Portal médico</h1>} /></Routes></MemoryRouter></QueryClientProvider>);
}
const response = (data: unknown, status = 200) => ({ ok: status < 400, status, json: async () => data }) as Response;
describe("Google unified authentication", () => {
  beforeEach(() => {
    window.google = { accounts: { id: {
      initialize: (options) => { callback = options.callback; },
      renderButton: (element) => { const button = document.createElement("button"); button.textContent = "Continuar con Google"; button.onclick = () => callback({ credential: "test-provider-credential" }); element.appendChild(button); },
    } } };
  });
  it("renders the official button and follows the server portal after exchange", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => response(String(input).endsWith("challenge")
      ? { challenge: "a".repeat(43), nonce: "a".repeat(43), client_id: "controlled-client.apps.googleusercontent.com" }
      : { redirect_to: "/doctor", role: "DOCTOR" }));
    vi.stubGlobal("fetch", fetch);
    mount(<GoogleSignIn />);
    fireEvent.click(await screen.findByRole("button", { name: "Continuar con Google" }));
    expect(await screen.findByRole("heading", { name: "Portal médico" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/auth/google/exchange", expect.objectContaining({ method: "POST" }));
  });
  it("requires identity and privacy details before completing a new patient", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("challenge")) return response({ challenge: "a".repeat(43), nonce: "a".repeat(43), client_id: "controlled-client.apps.googleusercontent.com" });
      if (url.endsWith("exchange")) return response({ registration_required: true, name: "Paciente Google", email: "google@example.com" });
      return response({ role: "PATIENT", redirect_to: "/portal" });
    });
    vi.stubGlobal("fetch", fetch);
    mount(<GoogleSignIn />);
    fireEvent.click(await screen.findByRole("button", { name: "Continuar con Google" }));
    await screen.findByRole("heading", { name: "Completa tu registro de paciente" });
    fireEvent.change(screen.getByLabelText("Cédula colombiana (CC)"), { target: { value: "1234567890" } });
    fireEvent.change(screen.getByLabelText("Teléfono"), { target: { value: "3001234567" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Crear mi cuenta de paciente" }));
    expect(await screen.findByRole("heading", { name: "Portal paciente" })).toBeInTheDocument();
  });
  it("explains an existing email conflict and keeps traditional authentication available", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => String(input).endsWith("challenge")
      ? response({ challenge: "a".repeat(43), nonce: "a".repeat(43), client_id: "controlled-client.apps.googleusercontent.com" })
      : response({ detail: "Inicia sesión con contraseña y vincula Google desde tu perfil." }, 409)));
    mount(<GoogleSignIn />);
    fireEvent.click(await screen.findByRole("button", { name: "Continuar con Google" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("vincula Google desde tu perfil");
    expect(screen.getByRole("button", { name: "Reintentar verificación" })).toBeInTheDocument();
  });
  it("requires current password before requesting a medical link challenge", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => String(input).endsWith("identity")
      ? response({ linked: false, enabled: true, email: null })
      : response({ detail: "Confirma tu contraseña actual para continuar" }, 403));
    vi.stubGlobal("fetch", fetch);
    mount(<GoogleAccountLink />);
    await screen.findByText("Todavía no tienes una cuenta Google vinculada.");
    fireEvent.change(screen.getByLabelText("Contraseña actual para confirmar tu identidad"), { target: { value: "WrongPassword123" } });
    fireEvent.click(screen.getByRole("button", { name: "Verificar contraseña y vincular Google" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/auth/google/challenge", expect.objectContaining({ body: JSON.stringify({ purpose: "LINK", current_password: "WrongPassword123" }) })));
    expect(await screen.findByRole("alert")).toHaveTextContent("Confirma tu contraseña");
  });
});
