import { expect, test, type Page } from "@playwright/test";

const password = "PacienteE2E2026!";

async function createPatient(
  page: Page,
  email: string,
  names: string,
  surnames: string,
  documentNumber: string,
) {
  await page.goto("/register");
  await page.getByPlaceholder("Tus nombres").fill(names);
  await page.getByPlaceholder("Tus apellidos").fill(surnames);
  await page.getByPlaceholder("Solo dígitos").fill(documentNumber);
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByPlaceholder("+57 300 123 4567").fill("+57 300 123 4567");
  await page.getByPlaceholder("Al menos 10 caracteres").fill(password);
  await page.getByPlaceholder("Escribe nuevamente tu contraseña").fill(password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Crear mi cuenta" }).click();
  await expect(page.getByRole("status")).toContainText("Tu cuenta de paciente fue creada correctamente");
}

test("dos pacientes se registran y conservan identidad y plan separados", async ({ page }, testInfo) => {
  const suffix = String(Date.now()).slice(-8);
  const documentA = `1${suffix}`;
  const documentB = `2${suffix}`;
  const emailA = `register-a-${testInfo.project.name}-${Date.now()}@example.com`;
  const emailB = `register-b-${testInfo.project.name}-${Date.now()}@example.com`;

  await createPatient(page, emailA, "Ana Maria", "Paciente Prueba", documentA);
  await expect(page.getByRole("heading", { name: "Hola, Ana 👋" })).toBeVisible();
  await page.goto("/portal/profile");
  await expect(page.getByText(`CC · •${"•".repeat(documentA.length - 5)}${documentA.slice(-4)}`)).toBeVisible();
  await expect(page.getByText(documentA, { exact: true })).toHaveCount(0);

  await page.goto("/portal/plans");
  const basic = page.locator(".plan-card").filter({ has: page.getByRole("heading", { name: "Básico", exact: true }) });
  await basic.getByRole("button", { name: "Activar plan" }).click();
  await page.getByRole("button", { name: "Autorizar y simular aprobación" }).click();
  await expect(page.getByRole("status")).toContainText("Tu plan se activó correctamente");

  await createPatient(page, emailB, "Bruno", "Paciente Independiente", documentB);
  await expect(page.getByRole("heading", { name: "Hola, Bruno 👋" })).toBeVisible();
  await page.goto("/portal/profile");
  await expect(page.getByText(`CC · •${"•".repeat(documentB.length - 5)}${documentB.slice(-4)}`)).toBeVisible();
  await expect(page.getByText(documentB, { exact: true })).toHaveCount(0);
  await page.goto("/portal/plans");
  const secondBasic = page.locator(".plan-card").filter({ has: page.getByRole("heading", { name: "Básico", exact: true }) });
  await expect(secondBasic.getByRole("button", { name: "Activar plan" })).toBeVisible();
  await expect(page.getByText("Activa un plan para solicitar tus citas médicas.")).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill(emailA);
  await page.getByPlaceholder("Tu contraseña").fill(password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.getByRole("heading", { name: "Hola, Ana 👋" })).toBeVisible();
  await page.goto("/portal/plans");
  await expect(page.locator(".membership-banner")).toContainText("Básico");
});
