import { test, expect } from "@playwright/test";

test("Google official GIS button loads with the configured client", async ({ page }, info) => {
  test.skip(process.env.E2E_GOOGLE_OFFICIAL !== "true", "Requiere un Client ID real configurado; no inicia sesión por el usuario");
  const errors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("/login");
  const buttonFrame = page.frameLocator('iframe[src^="https://accounts.google.com/gsi/button"]');
  await expect(buttonFrame.getByRole("button", { name: /google/i })).toBeVisible({ timeout: 30000 });
  expect(errors.filter((message) => /origin.*not allowed|client.*not found|content security policy|refused to load the script/i.test(message))).toEqual([]);
  await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `../docs/screenshots/google-login-${info.project.name}.png`, fullPage: true });
});
