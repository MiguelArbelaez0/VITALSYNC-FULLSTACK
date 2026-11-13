import { test, expect, Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";

test("historia ficticia protegida, primer acceso individual y teleconsulta entre portales", async ({
  page,
  browser,
}, info) => {
  test.setTimeout(150000);
  test.skip(
    process.env.E2E_LIFECYCLE_ISOLATED !== "true" ||
      process.env.E2E_DOCTOR_CONTAINER !== "vitalsync-test-backend-1",
    "Requiere servicios de pruebas del proyecto vitalsync",
  );
  const credentialFile = process.env.E2E_CREDENTIALS_FILE!;
  async function loginDoctor(target: Page, id: number) {
    const data = JSON.parse(readFileSync(credentialFile, "utf8"));
    const credential = data.new_credentials.find(
      (c: any) => c.doctor_id === id,
    );
    await target.goto("/login");
    await target.getByLabel("Correo electrónico").fill(credential.email);
    await target
      .getByLabel("Contraseña", { exact: true })
      .fill(credential.current_password ?? credential.temporary_password);
    await target
      .getByRole("button", { name: "Iniciar sesión", exact: true })
      .click();
    if (!credential.current_password) {
      await expect(target.getByText("PRIMER ACCESO MÉDICO")).toBeVisible();
      expect((await target.request.get("/api/doctor/dashboard")).status()).toBe(
        403,
      );
      const fresh = "IndividualA1" + randomBytes(24).toString("hex");
      await target
        .getByLabel("Contraseña actual o inicial")
        .fill(credential.temporary_password);
      await target.getByLabel("Nueva contraseña", { exact: true }).fill(fresh);
      await target.getByLabel("Repetir nueva contraseña").fill(fresh);
      await target.getByRole("button", { name: "Guardar contraseña" }).click();
      await expect(
        target.getByRole("heading", { name: "Hola, " + credential.name }),
      ).toBeVisible();
      credential.current_password = fresh;
      writeFileSync(credentialFile, JSON.stringify(data));
    }
    await expect(target).toHaveURL(/\/doctor$/);
  }
  const pc = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL,
    viewport: info.project.use.viewport,
  });
  const patient = await pc.newPage();
  const login = await patient.request.post("/api/auth/login", {
    data: { email: "paciente@vitalsync.demo", password: "Paciente2026!" },
  });
  expect(login.ok()).toBeTruthy();
  const patientId = (await login.json()).id;
  const plans = await (await patient.request.get("/api/plans")).json();
  expect(
    (
      await patient.request.post("/api/payments", {
        data: {
          kind: "PLAN",
          target_id: plans.find((p: any) => p.name === "Premium").id,
          status: "APPROVED",
          idempotency_key: "clinical-" + Date.now(),
        },
      })
    ).ok(),
  ).toBeTruthy();
  const slots = await (
    await patient.request.get("/api/doctors/1/availability?modality=VIRTUAL")
  ).json();
  const slot = slots.find((s: any) => s.available);
  expect(slot).toBeTruthy();
  const hold = await patient.request.post("/api/holds", {
    data: { availability_id: slot.id, modality: "VIRTUAL" },
  });
  expect(hold.status()).toBe(201);
  const reservation = await patient.request.post(
    "/api/holds/" + (await hold.json()).id + "/confirm",
  );
  expect(reservation.ok()).toBeTruthy();
  const appointmentId = (await reservation.json()).id;
  await loginDoctor(page, 1);
  const agenda = await (
    await page.request.get("/api/doctor/appointments?view=all")
  ).json();
  expect(agenda.some((a: any) => a.id === appointmentId)).toBe(true);
  await page.goto("/doctor/patients");
  await page
    .getByRole("button", { name: "Valentina Torres", exact: true })
    .click();
  await page.getByRole("link", { name: "Ver historia clínica" }).click();
  await expect(
    page.getByText("DATOS FICTICIOS DE DEMOSTRACIÓN", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Alergias conocidas" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Medicamentos registrados" }),
  ).toBeVisible();
  const history = await (
    await page.request.get(`/api/doctor/patients/${patientId}/clinical-history`)
  ).json();
  expect(history.encounters).toHaveLength(3);
  await page
    .getByRole("button", { name: /Ver detalle de consulta/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Signos vitales simulados" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      `../../docs/screenshots/doctor-clinical-${info.project.name}.png`,
    ),
    fullPage: true,
  });
  await page
    .getByLabel("Filtrar consultas por especialidad")
    .selectOption({ label: history.encounters[0].specialty });
  expect(
    await page.getByRole("button", { name: /Ver detalle de consulta/ }).count(),
  ).toBe(1);
  const otherContext = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL,
  });
  const other = await otherContext.newPage();
  await loginDoctor(other, 3);
  expect(
    (
      await other.request.get(
        `/api/doctor/patients/${patientId}/clinical-history`,
      )
    ).status(),
  ).toBe(404);
  await other.goto(`/doctor/patients/${patientId}/clinical-history`);
  await expect(other.getByRole("alert")).toBeVisible();
  await expect(other.getByText("DATOS FICTICIOS DE DEMOSTRACIÓN")).toHaveCount(
    0,
  );
  expect(
    (
      await patient.request.get(
        `/api/doctor/patients/${patientId}/clinical-history`,
      )
    ).status(),
  ).toBe(403);
  expect(
    (
      await page.request.get(`/api/doctor/patients/999999/clinical-history`)
    ).status(),
  ).toBe(404);
  expect(
    (
      await page.request.get(
        `/api/doctor/patients/${patientId}/clinical-history/encounters/999999`,
      )
    ).status(),
  ).toBe(404);
  await page.goto(`/doctor/appointments/${appointmentId}/teleconsult`);
  await page
    .getByRole("button", { name: "Avanzar reloj de demostración" })
    .click();
  await page.getByRole("button", { name: "Abrir sala simulada" }).click();
  await page.getByRole("button", { name: "Ingresar como médico" }).click();
  expect(
    (
      await patient.request.post(
        `/api/appointments/${appointmentId}/teleconsult/status`,
        { data: { event: "PATIENT_JOIN" } },
      )
    ).ok(),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Iniciar atención simulada" }).click();
  await page
    .getByRole("button", { name: "Finalizar teleconsulta simulada" })
    .click();
  await expect(page.getByText(/La simulación finalizó/)).toBeVisible();
  await patient.goto("/portal/appointments");
  await expect(
    patient.locator(`a[href="/portal/appointments/${appointmentId}"]`),
  ).toHaveCount(0);
  await patient
    .getByRole("tab", { name: "Historial · Finalizadas", exact: true })
    .click();
  await expect(
    patient.locator(`a[href="/portal/appointments/${appointmentId}"]`),
  ).toBeVisible();
  const counts = JSON.parse(
    execFileSync(
      "docker",
      [
        "exec",
        "vitalsync-test-backend-1",
        "python",
        "-c",
        "from app.db.session import SessionLocal; from app.models.entities import AuditEvent; from sqlalchemy import select,func; import json; d=SessionLocal(); print(json.dumps({a:d.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action==a)) for a in ['CLINICAL_HISTORY_VIEWED','CLINICAL_ENCOUNTER_VIEWED']}))",
      ],
      { encoding: "utf8" },
    ),
  );
  expect(counts.CLINICAL_HISTORY_VIEWED).toBeGreaterThan(0);
  expect(counts.CLINICAL_ENCOUNTER_VIEWED).toBeGreaterThan(0);
  await otherContext.close();
  await pc.close();
});
