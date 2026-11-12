import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

test("paciente y médico comparten reserva, finalización y cancelación persistentes", async ({
  page,
  browser,
}, info) => {
  test.setTimeout(150000);
  test.skip(
    process.env.E2E_LIFECYCLE_ISOLATED !== "true" ||
      process.env.E2E_DOCTOR_CONTAINER !== "vitalsync-doctor-check-backend-1",
    "Solo se permite el stack médico aislado",
  );
  page.setDefaultTimeout(15000);
  const baseURL = process.env.E2E_BASE_URL!;
  const patientContext = await browser.newContext({
    baseURL,
    viewport: info.project.use.viewport,
  });
  const patient = await patientContext.newPage();
  patient.setDefaultTimeout(15000);
  const request = patient.request;
  const stamp = Date.now();
  const surnames = "Portal Médico " + String(stamp).slice(-6);
  const name = "Paciente " + surnames;
  const registration = await request.post("/api/auth/register", {
    data: {
      given_names: "Paciente",
      surnames,
      document_type: "CC",
      document_number: String(stamp).slice(-10),
      email: `doctor-flow-${stamp}@example.com`,
      password: "PacienteE2E2026!",
      phone: "+57 300 123 4567",
      privacy_accepted: true,
    },
  });
  expect(registration.status()).toBe(201);
  const plans = await (await request.get("/api/plans")).json();
  expect(
    (
      await request.post("/api/payments", {
        data: {
          kind: "PLAN",
          target_id: plans.find((p: any) => p.name === "Premium").id,
          status: "APPROVED",
          idempotency_key: `doctor-plan-${stamp}`,
        },
      })
    ).ok(),
  ).toBeTruthy();
  const doctors = await (
    await request.get("/api/doctors?modality=VIRTUAL")
  ).json();
  const doctor = doctors.find((d: any) => d.name === "Dr. Alejandro Méndez");
  async function reserve(modality: string) {
    const slots = await (
      await request.get(
        `/api/doctors/${doctor.id}/availability?modality=${modality}`,
      )
    ).json();
    const slot = slots.find((s: any) => s.available);
    expect(slot).toBeTruthy();
    const hold = await request.post("/api/holds", {
      data: { availability_id: slot.id, modality },
    });
    expect(hold.status()).toBe(201);
    const confirmed = await request.post(
      `/api/holds/${(await hold.json()).id}/confirm`,
    );
    expect(confirmed.ok()).toBeTruthy();
    return (await confirmed.json()).id;
  }
  const virtual = await reserve("VIRTUAL");
  const onsite = await reserve("PRESENCIAL");
  await patient.goto("/doctor");
  await expect(
    patient.getByText("Acceso exclusivo para médicos"),
  ).toBeVisible();
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("medico@vitalsync.demo");
  await page.getByLabel("Contraseña", { exact: true }).fill("DoctorE2E2026!");
  await page
    .getByRole("button", { name: "Iniciar sesión", exact: true })
    .click();
  await expect(page).toHaveURL(/\/doctor$/);
  await expect(
    page.getByRole("heading", { name: "Hola, Dr. Alejandro Méndez" }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      `../../docs/screenshots/doctor-dashboard-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  await page.goto("/portal");
  await expect(page.getByText("Acceso exclusivo para pacientes")).toBeVisible();
  await page.goto("/doctor/appointments");
  await expect(
    page.locator(`a[href="/doctor/appointments/${virtual}"]`),
  ).toBeVisible();
  await expect(
    page.locator(`a[href="/doctor/appointments/${onsite}"]`),
  ).toBeVisible();
  await page.getByLabel("Modalidad", { exact: true }).selectOption("VIRTUAL");
  await expect(
    page.locator(`a[href="/doctor/appointments/${onsite}"]`),
  ).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      `../../docs/screenshots/doctor-agenda-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  await page.locator(`a[href="/doctor/appointments/${virtual}"]`).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.getByRole("link", { name: "Ver sala simulada" }).click();
  await expect(
    page.getByRole("button", { name: "Avanzar reloj de demostración" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Avanzar reloj de demostración" })
    .click();
  await page.getByRole("button", { name: "Abrir sala simulada" }).click();
  await page.getByRole("button", { name: "Ingresar como médico" }).click();
  await expect(
    page.getByRole("button", { name: "Iniciar atención simulada" }),
  ).toHaveCount(0);
  expect(
    (
      await request.post(`/api/appointments/${virtual}/teleconsult/status`, {
        data: { event: "PATIENT_JOIN" },
      })
    ).ok(),
  ).toBeTruthy();
  // The room polls so the patient joining from another session is reflected here.
  await page.getByRole("button", { name: "Iniciar atención simulada" }).click();
  await page
    .getByRole("button", { name: "Finalizar teleconsulta simulada" })
    .click();
  await expect(
    page.getByText(
      "La simulación finalizó y quedó guardada en el historial de ambos portales.",
    ),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      `../../docs/screenshots/doctor-room-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  await patient.goto("/portal/appointments");
  await expect(
    patient.locator(`a[href="/portal/appointments/${virtual}"]`),
  ).toHaveCount(0);
  await expect(
    patient.locator(`a[href="/portal/appointments/${onsite}"]`),
  ).toBeVisible();
  await patient
    .getByRole("tab", { name: "Historial · Finalizadas", exact: true })
    .click();
  await expect(
    patient.locator(`a[href="/portal/appointments/${virtual}"]`),
  ).toBeVisible();
  await page.goto("/doctor/appointments");
  await page.getByRole("tab", { name: "Realizadas e incidencias" }).click();
  await expect(
    page.locator(`a[href="/doctor/appointments/${virtual}"]`),
  ).toBeVisible();
  await page.goto(`/doctor/appointments/${onsite}`);
  await page
    .getByRole("button", { name: "Cancelar cita", exact: true })
    .click();
  await page
    .getByLabel("Motivo obligatorio")
    .fill("Indisponibilidad médica de demostración");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Confirmar cancelación" }).click();
  await expect(
    page.getByText("Cancelada", { exact: true }).first(),
  ).toBeVisible();
  await patient.goto("/portal/notifications");
  await expect(
    patient.getByText(/El médico Dr. Alejandro Méndez canceló tu cita/),
  ).toBeVisible();
  await page.goto("/doctor/patients");
  await page.getByLabel("Buscar paciente por nombre").fill(name);
  await expect(page.getByRole("button", { name })).toBeVisible();
  await page.goto("/doctor/profile");
  await expect(page.getByText("Cardiología", { exact: true })).toBeVisible();
  await expect(
    page.getByLabel("Biografía profesional · editable"),
  ).toBeVisible();
  await page.goto("/doctor/availability");
  await expect(
    page.getByRole("heading", { name: "Mi disponibilidad" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBeTruthy();
  const persisted = await (
    await request.get(`/api/appointments/${virtual}`)
  ).json();
  expect(persisted).toMatchObject({
    status: "ATTENDED",
    completion_source: "DEMO",
    clinically_attended: false,
  });
  if (info.project.name === "desktop") {
    execFileSync("docker", ["restart", "vitalsync-doctor-check-postgres-1"], {
      timeout: 60000,
    });
    await expect
      .poll(
        async () => {
          try {
            return (await request.get("/api/health")).status();
          } catch {
            return 0;
          }
        },
        { timeout: 45000 },
      )
      .toBe(200);
    execFileSync("docker", ["restart", "vitalsync-doctor-check-backend-1"], {
      timeout: 60000,
    });
    await expect
      .poll(
        async () => {
          try {
            return (await request.get("/api/health")).status();
          } catch {
            return 0;
          }
        },
        { timeout: 45000 },
      )
      .toBe(200);
    expect(
      await (await request.get(`/api/appointments/${virtual}`)).json(),
    ).toEqual(persisted);
    expect((await page.request.get("/api/doctor/me")).status()).toBe(200);
    expect(
      (await (await request.get(`/api/appointments/${onsite}`)).json()).status,
    ).toBe("CANCELLED");
  }
  await patientContext.close();
});
