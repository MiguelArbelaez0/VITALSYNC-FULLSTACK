import { resolve } from "node:path";
import { test, expect } from "@playwright/test";

async function chooseAvailableSlot(page: import("@playwright/test").Page) {
  const dateSelect = page.getByLabel("Fecha de consulta");
  await expect(dateSelect).toBeVisible();
  const dates = await dateSelect.locator("option").evaluateAll((options) =>
    options.map((option) => (option as HTMLOptionElement).value),
  );
  for (const date of dates) {
    await dateSelect.selectOption(date);
    const slot = page.locator(".time-slot:not([disabled])").first();
    if ((await slot.count()) > 0) {
      await slot.click();
      return;
    }
  }
  throw new Error("No hay turnos disponibles en las fechas publicadas");
}

test("Paciente real: registro, login, plan, copago, cita y cancelación", async ({
  page,
}, testInfo) => {
  const email = `e2e-${testInfo.project.name}-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByPlaceholder("Tus nombres").fill("Paciente");
  await page.getByPlaceholder("Tus apellidos").fill("Proyecto E2E");
  await page.getByPlaceholder("Solo dígitos").fill(String(Date.now()).slice(-9));
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByPlaceholder("+57 300 123 4567").fill("+57 300 123 4567");
  await page.getByPlaceholder("Al menos 10 caracteres").fill("PacienteE2E2026!");
  await page.getByPlaceholder("Escribe nuevamente tu contraseña").fill("PacienteE2E2026!");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Crear mi cuenta" }).click();
  await expect(page.getByRole("status")).toContainText("Tu cuenta de paciente fue creada correctamente");
  await expect(
    page.getByRole("heading", { name: "Hola, Paciente 👋" }),
  ).toBeVisible();
  if (testInfo.project.name === "mobile")
    await page.getByRole("button", { name: "Abrir menú" }).click();
  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByPlaceholder("Tu contraseña").fill("PacienteE2E2026!");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(
    page.getByRole("heading", { name: "Hola, Paciente 👋" }),
  ).toBeVisible();
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      "../../docs/screenshots",
      `dashboard-${testInfo.project.name}.png`,
    ),
    fullPage: true,
  });
  await page.goto("/portal/doctors?modality=PRESENCIAL");
  await page
    .getByRole("link", { name: "Ver perfil y disponibilidad" })
    .first()
    .click();
  await chooseAvailableSlot(page);
  await page
    .getByRole("button", { name: "Retener horario y continuar" })
    .click();
  await expect(page.getByRole("alert")).toContainText("Debes activar tu plan");
  await page.goto("/portal/plans");
  await page
    .locator(".plan-card")
    .filter({ has: page.getByRole("heading", { name: "Básico", exact: true }) })
    .getByRole("button", { name: "Activar plan" })
    .click();
  await page
    .getByRole("button", { name: "Simular rechazo", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Rechazado");
  await page
    .getByRole("button", { name: "Simular pendiente", exact: true })
    .click();
  await expect(page.getByText("Pendiente", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Conciliar como aprobado" }).click();
  await expect(page.getByRole("status")).toContainText("Tu plan se activó");
  await page.goto("/portal/doctors?modality=VIRTUAL");
  await page.getByRole("link", { name: "Ver perfil y disponibilidad" }).first().click();
  await expect(page.getByText(/Tu plan actual no incluye consultas virtuales/)).toBeVisible();
  await expect(page.locator(".time-slot:not([disabled])")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retener horario y continuar" })).toBeDisabled();
  await page.goto("/portal/plans");
  await page
    .locator(".plan-card")
    .filter({ has: page.getByRole("heading", { name: "Estándar", exact: true }) })
    .getByRole("button", { name: "Activar plan" })
    .click();
  await page.getByRole("button", { name: "Autorizar y simular aprobación" }).click();
  await expect(page.getByRole("status")).toContainText("Tu plan se activó");
  await page.goto("/portal/doctors?modality=PRESENCIAL");
  await page
    .getByLabel("Filtrar por especialidad")
    .selectOption({ label: "Medicina general" });
  await page.getByRole("link", { name: "Ver perfil y disponibilidad" }).click();
  await chooseAvailableSlot(page);
  await page
    .getByRole("button", { name: "Retener horario y continuar" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Un paso más para tu cita" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Autorizar y simular aprobación" })
    .click();
  await expect(page.getByText(/Copago aprobado/)).toBeVisible();
  await page
    .getByRole("button", { name: "Confirmar cita", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "¡Tu cita está confirmada!" }),
  ).toBeVisible();
  const appointmentUrl = page.url();
  const code = await page.locator("dl dd").first().innerText();
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      "../../docs/screenshots",
      `receipt-${testInfo.project.name}.png`,
    ),
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByText(code, { exact: true })).toBeVisible();
  await page.goto("/portal/appointments");
  await expect(page.getByText(code, { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Ver detalle" }).click();
  await page
    .getByRole("button", { name: "Cancelar cita", exact: true })
    .click();
  await page.getByRole("button", { name: "Conservar mi cita" }).click();
  await expect(page.getByText("Confirmada", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Cancelar cita", exact: true })
    .click();
  await page
    .getByLabel("Motivo de cancelación")
    .fill("Cambio de agenda para prueba integral");
  await page.getByLabel("Confirmo que deseo cancelar mi cita.").check();
  await page.getByRole("button", { name: "Confirmar cancelación" }).click();
  await expect(page.getByText("Cancelada", { exact: true })).toBeVisible();
  await page.goto("/portal/appointments");
  await page.getByRole("tab", { name: "Historial · Canceladas" }).click();
  await expect(page.getByText(code, { exact: true })).toBeVisible();
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      "../../docs/screenshots",
      `history-${testInfo.project.name}.png`,
    ),
    fullPage: true,
  });
  await page.goto("/portal/notifications");
  await expect(
    page.getByText(new RegExp(`Tu cita ${code} ha sido cancelada`)),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.goto(appointmentUrl);
  await expect(page.getByText("Cancelada", { exact: true })).toBeVisible();
  await page.goto("/portal/plans");
  await page
    .locator(".plan-card")
    .filter({ has: page.getByRole("heading", { name: "Estándar", exact: true }) })
    .getByRole("button", { name: "Renovar plan" })
    .click();
  await page.getByRole("button", { name: "Autorizar y simular aprobación" }).click();
  await expect(page.getByRole("status")).toContainText("Tu plan se activó");
  await page.goto("/portal/doctors?modality=VIRTUAL");
  await expect(page.getByRole("heading", { name: "¿Qué modalidad de atención necesitas?" })).toBeVisible();
  await page.getByRole("link", { name: "Ver perfil y disponibilidad" }).first().click();
  await expect(page.getByRole("button", { name: /Virtual/ })).toHaveAttribute("aria-pressed", "true");
  await chooseAvailableSlot(page);
  await page.getByRole("button", { name: "Retener horario y continuar" }).click();
  await expect(page.locator(".booking-summary")).toContainText("Virtual · Sala demostrativa");
  await page.getByRole("button", { name: "Autorizar y simular aprobación" }).click();
  await page.getByRole("button", { name: "Confirmar cita", exact: true }).click();
  await expect(page.getByRole("heading", { name: "¡Tu cita está confirmada!" })).toBeVisible();
  await expect(page.locator(".receipt")).toContainText("Consulta virtual · Teleconsulta simulada");
  const teleconsultLink = page.getByRole("link", { name: "Ver teleconsulta simulada" });
  const enabledColors = await teleconsultLink.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    text: getComputedStyle(element).color,
    icon: getComputedStyle(element.querySelector("svg")!).color,
    radius: getComputedStyle(element).borderRadius,
  }));
  expect(enabledColors).toEqual({
    background: "rgb(18, 119, 132)",
    text: "rgb(255, 255, 255)",
    icon: "rgb(255, 255, 255)",
    radius: "9px",
  });
  await teleconsultLink.hover();
  await expect(teleconsultLink).toHaveCSS("background-color", "rgb(13, 101, 114)");
  await teleconsultLink.click();
  await expect(page.getByText("Teleconsulta simulada — sin conexión de audio o video")).toBeVisible();
  const advanceClock = page.getByRole("button", { name: "Avanzar reloj de demostración" });
  if (await advanceClock.count()) await advanceClock.click();
  await page.getByRole("button", { name: "Abrir sala simulada" }).click();
  await expect(page.getByText("Sala disponible")).toBeVisible();
  await page.screenshot({
    path: resolve(
      import.meta.dirname,
      "../../docs/screenshots",
      `teleconsult-${testInfo.project.name}.png`,
    ),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Volver al comprobante" }).click();
  await page.getByRole("button", { name: "Cancelar cita", exact: true }).click();
  await page.getByLabel("Motivo de cancelación").fill("Liberar horario al finalizar E2E");
  await page.getByLabel("Confirmo que deseo cancelar mi cita.").check();
  await page.getByRole("button", { name: "Confirmar cancelación" }).click();
  await expect(page.getByText("Cancelada", { exact: true })).toBeVisible();
  const unavailableTeleconsult = page.getByRole("button", { name: "Ver teleconsulta simulada" });
  await expect(unavailableTeleconsult).toBeDisabled();
  await expect(page.getByText("La cita está cancelada; la teleconsulta no está disponible.")).toBeVisible();
  const disabledColors = await unavailableTeleconsult.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    text: getComputedStyle(element).color,
    icon: getComputedStyle(element.querySelector("svg")!).color,
    opacity: getComputedStyle(element).opacity,
  }));
  expect(disabledColors).toEqual({
    background: "rgb(220, 232, 236)",
    text: "rgb(36, 76, 89)",
    icon: "rgb(36, 76, 89)",
    opacity: "1",
  });
  await page.goto("/portal/plans");
  const standardPlan = page
    .locator(".plan-card")
    .filter({ has: page.getByRole("heading", { name: "Estándar", exact: true }) });
  await expect(standardPlan.getByRole("button", { name: "Cancelar plan" })).toBeVisible();
  await standardPlan.getByRole("button", { name: "Cancelar plan" }).click();
  await expect(page.getByRole("dialog")).toContainText("Estándar");
  await expect(page.getByRole("dialog")).toContainText("Inmediatamente al confirmar");
  await page.getByRole("button", { name: "Mantener mi plan" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await standardPlan.getByRole("button", { name: "Cancelar plan" }).click();
  await page.getByRole("button", { name: "Confirmar cancelación" }).click();
  await expect(page.getByRole("status")).toContainText("Estándar se canceló");
  await expect(page.getByText("Cancelada", { exact: true })).toBeVisible();
  await expect(standardPlan.getByRole("button", { name: "Activar plan" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
});
