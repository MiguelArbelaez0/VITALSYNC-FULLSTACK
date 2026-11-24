import { expect, type Page, type Browser } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";

// Only called by the explicitly isolated Docker LiveKit test harness.
export async function registerApprovedDoctor(
  page: Page,
  patientPage: Page,
  browser: Browser,
  credentials: any,
  baseURL: string,
) {
  const suffix = Date.now().toString().slice(-8);
  await page.goto("/login?mode=register");
  await page.getByRole("button", { name: "Médico", exact: true }).click();
  await page.getByLabel("Nombres", { exact: true }).fill("María Elena");
  await page.getByLabel("Apellidos", { exact: true }).fill("Gómez Académica");
  await expect(page.getByLabel("Correo institucional propuesto")).toHaveValue(
    "maria.gomez@doctor.vitalsync.demo",
  );
  await expect(
    page.getByLabel("Correo institucional propuesto"),
  ).toHaveAttribute("readonly", "");
  await page.getByLabel("Número de cédula").fill("91" + suffix);
  await page
    .getByRole("combobox", { name: "Especialidad", exact: true })
    .selectOption({ index: 1 });
  await page.getByLabel("Registro profesional").fill("E2E-" + suffix);
  await page.getByLabel("Teléfono de contacto").fill("3001234567");
  await page
    .getByLabel("Perfil profesional")
    .fill("Profesional ficticia creada en la base aislada de pruebas.");
  await page.getByRole("checkbox").check();
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      "../../docs/screenshots/medical-registration-desktop.png",
    ),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBeTruthy();
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      "../../docs/screenshots/medical-registration-mobile.png",
    ),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/auth/doctor-applications") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Solicitar cuenta médica" }).click();
  const pending = await (await submitted).json();
  expect(pending.status).toBe("PENDING");
  await expect(
    page.getByRole("heading", { name: "Solicitud pendiente" }),
  ).toBeVisible();
  expect((await page.request.get("/api/doctor/dashboard")).status()).toBe(401);
  const admin = await browser.newContext({ baseURL });
  let doctor: any;
  try {
    const adminPage = await admin.newPage();
    await adminPage.goto("/login");
    await adminPage
      .getByLabel("Correo electrónico")
      .fill(credentials.admin.email);
    await adminPage
      .getByLabel("Contraseña", { exact: true })
      .fill(credentials.admin.password);
    await adminPage
      .getByRole("button", { name: "Iniciar sesión", exact: true })
      .click();
    await expect(adminPage).toHaveURL(/\/admin$/);
    await adminPage.goto("/admin/doctor-applications");
    await adminPage
      .getByRole("button", { name: "Aprobar solicitud", exact: true })
      .click();
    const dialog = adminPage.getByRole("dialog");
    await dialog
      .getByLabel(
        "Confirmo la revisión académica simulada de los datos profesionales",
      )
      .check();
    await dialog
      .getByLabel("Motivo de la operación")
      .fill("Revisión académica de datos ficticios para integración E2E");
    await dialog.locator(".admin-confirm input").check();
    const approval = adminPage.waitForResponse((r) =>
      r.url().endsWith(`/doctor-applications/${pending.id}/approve`),
    );
    await dialog.getByRole("button", { name: "Confirmar y guardar" }).click();
    const approved = await (await approval).json();
    expect(approved.status).toBe("APPROVED");
    expect(approved.delivery_id).toBeGreaterThan(0);
    await expect(dialog).toHaveCount(0);
    await adminPage.screenshot({
      path: resolve(
        import.meta.dirname,
        "../../docs/screenshots/medical-approval-desktop.png",
      ),
      fullPage: true,
    });
    const output = `/tmp/e2e-medical-${randomUUID()}.json`;
    execFileSync(
      "docker",
      [
        "exec",
        "vitalsync-test-backend-1",
        "python",
        "-c",
        "from app.db.session import engine; assert engine.url.database.startswith('vitalsync_test_audit_')",
      ],
      { stdio: "pipe" },
    );
    execFileSync(
      "docker",
      [
        "exec",
        "-i",
        "vitalsync-test-backend-1",
        "python",
        "-m",
        "app.medical_credentials",
        "--actor-email",
        credentials.admin.email,
        "--delivery-id",
        String(approved.delivery_id),
        "--output",
        output,
      ],
      { input: credentials.admin.password + "\n", stdio: "pipe" },
    );
    doctor = JSON.parse(
      execFileSync(
        "docker",
        ["exec", "vitalsync-test-backend-1", "cat", output],
        { encoding: "utf8", stdio: "pipe" },
      ),
    );
    execFileSync(
      "docker",
      [
        "exec",
        "vitalsync-test-backend-1",
        "python",
        "-c",
        `from pathlib import Path; Path('${output}').unlink()`,
      ],
      { stdio: "pipe" },
    );
    const start = new Date(Date.now() + 10 * 60 * 1000);
    const slotResponse = await admin.request.post("/api/admin/availability", {
      data: {
        doctor_id: approved.doctor_id,
        starts_at: start.toISOString(),
        ends_at: new Date(start.getTime() + 30 * 60 * 1000).toISOString(),
        modalities: ["VIRTUAL", "PRESENCIAL"],
        published: true,
        reason: "Disponibilidad ficticia para integración E2E",
      },
    });
    expect(slotResponse.ok()).toBeTruthy();
    credentials.newSlot = await slotResponse.json();
  } finally {
    await admin.close();
  }
  credentials.legacy = { email: doctor.email, password: doctor.password };
  credentials.patient = {
    email: `paciente.e2e.${suffix}@outlook.com`,
    password: randomUUID() + "Aa1!",
  };
  await patientPage.goto("/login?mode=register");
  await patientPage.getByPlaceholder("Tus nombres").fill("Paciente");
  await patientPage.getByPlaceholder("Tus apellidos").fill("Académico Nuevo");
  await patientPage.getByPlaceholder("Solo dígitos").fill("92" + suffix);
  await patientPage
    .getByLabel("Correo electrónico")
    .fill(credentials.patient.email);
  await patientPage.getByLabel("Teléfono de contacto").fill("3001234567");
  await patientPage
    .getByLabel("Contraseña", { exact: true })
    .fill(credentials.patient.password);
  await patientPage
    .getByLabel("Confirmar contraseña", { exact: true })
    .fill(credentials.patient.password);
  await patientPage.getByRole("checkbox").check();
  await patientPage.screenshot({
    path: resolve(
      import.meta.dirname,
      "../../docs/screenshots/patient-registration-desktop.png",
    ),
    fullPage: true,
    mask: [patientPage.locator('input[type="password"]')],
  });
  await patientPage
    .getByRole("button", { name: "Crear mi cuenta", exact: true })
    .click();
  await expect(patientPage).toHaveURL(/\/portal$/);
  await patientPage.request.post("/api/auth/logout");
}

export async function bookRegisteredDoctor(
  patientPage: Page,
  credentials: any,
) {
  const api = patientPage.request;
  const plans = await (await api.get("/api/plans")).json();
  const plan = plans.find((p: any) => p.name === "Premium");
  expect(
    (
      await api.post("/api/payments", {
        data: {
          kind: "PLAN",
          target_id: plan.id,
          status: "APPROVED",
          idempotency_key: randomUUID(),
        },
      })
    ).ok(),
  ).toBeTruthy();
  const held = await api.post("/api/holds", {
    data: { availability_id: credentials.newSlot.id, modality: "VIRTUAL" },
  });
  expect(held.status()).toBe(201);
  const hold = await held.json();
  if (hold.copay)
    expect(
      (
        await api.post("/api/payments", {
          data: {
            kind: "COPAY",
            target_id: hold.id,
            status: "APPROVED",
            idempotency_key: randomUUID(),
          },
        })
      ).ok(),
    ).toBeTruthy();
  const confirmed = await api.post(`/api/holds/${hold.id}/confirm`);
  expect(confirmed.ok()).toBeTruthy();
  await patientPage.goto(
    `/portal/appointments/${(await confirmed.json()).id}/teleconsult`,
  );
}
