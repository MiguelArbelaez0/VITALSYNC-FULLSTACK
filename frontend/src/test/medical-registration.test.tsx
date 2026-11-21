import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MedicalRegistration } from "../features/auth/MedicalRegistration";
const response = (data: unknown) =>
  ({ ok: true, json: async () => data }) as Response;
it("proposes a read-only email and submits only a pending professional application", async () => {
  const fetch = vi.fn(async (url: string) =>
    response(
      url.endsWith("options")
        ? { specialties: [{ id: 1, name: "Medicina general" }] }
        : url.endsWith("preview")
          ? { institutional_email: "maria.gomez@doctor.vitalsync.demo" }
          : {
              status: "PENDING",
              institutional_email: "maria.gomez@doctor.vitalsync.demo",
              receipt: "x".repeat(43),
              message: "Pendiente de aprobación",
            },
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const { container } = render(<MedicalRegistration />);
  await screen.findByRole("option", { name: "Medicina general" });
  fireEvent.change(screen.getByLabelText("Nombres"), {
    target: { value: "María" },
  });
  fireEvent.change(screen.getByLabelText("Apellidos"), {
    target: { value: "Gómez" },
  });
  await waitFor(() =>
    expect(screen.getByLabelText("Correo institucional propuesto")).toHaveValue(
      "maria.gomez@doctor.vitalsync.demo",
    ),
  );
  expect(
    screen.getByLabelText("Correo institucional propuesto"),
  ).toHaveAttribute("readonly");
  fireEvent.change(screen.getByLabelText("Número de cédula"), {
    target: { value: "9988776655" },
  });
  fireEvent.change(screen.getByLabelText("Especialidad"), {
    target: { value: "1" },
  });
  fireEvent.change(screen.getByLabelText("Registro profesional"), {
    target: { value: "REG-1234" },
  });
  fireEvent.change(screen.getByLabelText("Teléfono de contacto"), {
    target: { value: "3001234567" },
  });
  fireEvent.change(screen.getByLabelText("Perfil profesional"), {
    target: { value: "Profesional ficticia para pruebas académicas" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.submit(container.querySelector("form")!);
  expect(
    await screen.findByRole("heading", { name: "Solicitud pendiente" }),
  ).toBeVisible();
  expect(screen.getByLabelText("Código privado de seguimiento")).toHaveValue(
    "x".repeat(43),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/auth/doctor-applications",
    expect.objectContaining({ method: "POST" }),
  );
  expect(screen.queryByLabelText("Contraseña")).not.toBeInTheDocument();
});
it("shows a rejection when the holder supplies the private tracking code", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      response(
        url.endsWith("options")
          ? { specialties: [] }
          : {
              status: "REJECTED",
              institutional_email: "maria.gomez@doctor.vitalsync.demo",
              message: "Solicitud rechazada",
              review_reason: "Datos incompletos",
            },
      ),
    ),
  );
  const { container } = render(<MedicalRegistration />);
  fireEvent.change(screen.getByLabelText("Código privado de seguimiento"), {
    target: { value: "x".repeat(43) },
  });
  fireEvent.submit(container.querySelectorAll("form")[1]);
  expect(
    await screen.findByRole("heading", { name: "Solicitud rechazada" }),
  ).toBeVisible();
  expect(screen.getByText("Motivo: Datos incompletos")).toBeVisible();
});
