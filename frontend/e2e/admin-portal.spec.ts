import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const modules = [
  ["", "Dashboard administrativo", "dashboard"],
  ["doctors", "Médicos", "doctors"],
  ["patients", "Pacientes", "patients"],
  ["appointments", "Citas", "appointments"],
  ["availability", "Disponibilidad médica", "availability"],
  ["plans", "Planes", "plans"],
  ["payments", "Pagos y devoluciones", "payments"],
  ["audit", "Auditoría administrativa", "audit"],
  ["configuration", "Configuración", "configuration"],
] as const;

test("administrador accede a los nueve módulos y la agenda visual es responsive", async ({ page }, info) => {
  test.skip(
    process.env.E2E_LIFECYCLE_ISOLATED !== "true" ||
      process.env.E2E_DOCTOR_CONTAINER !== "vitalsync-test-backend-1",
    "Solo se permite el stack administrativo aislado",
  );
  const creds = JSON.parse(readFileSync(process.env.E2E_CREDENTIALS_FILE!, "utf8")).admin;
  await page.setDefaultTimeout(15000);
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill(creds.email);
  await page.getByLabel("Contraseña", { exact: true }).fill(creds.password);
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "Dashboard administrativo" })).toBeVisible();
  const clinical = await page.request.get("/api/doctor/patients/4/clinical-history");
  expect(clinical.status()).toBe(403);

  for (const [path, title, slug] of modules) {
    await page.goto(path ? `/admin/${path}` : "/admin");
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    await expect(page.locator(".admin-page")).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: resolve(import.meta.dirname, `../../docs/screenshots/admin-${slug}-${info.project.name}.png`),
      fullPage: true,
    });
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
