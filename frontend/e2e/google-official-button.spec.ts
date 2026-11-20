import { test, expect } from "@playwright/test";

test("Google official GIS button loads with the configured client", async ({ page }, info) => {
  test.skip(process.env.E2E_GOOGLE_OFFICIAL !== "true", "Requiere un Client ID real configurado; no inicia sesión por el usuario");
  const errors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("/login");
  // GIS can render its accessible button in the parent document rather
  // than inside its internal iframe. Assert the official SDK output.
  const parentButton = page.locator(".google-button").getByRole("button", { name: /google/i }).first();
  const iframe = page.locator('iframe[src^="https://accounts.google.com/gsi/button"]');
  await expect.poll(async () => {
    if (await parentButton.isVisible()) return true;
    if (await iframe.count()) return page.frameLocator('iframe[src^="https://accounts.google.com/gsi/button"]').getByRole("button", { name: /google/i }).isVisible().catch(() => false);
    return false;
  }, { timeout: 30000 }).toBe(true);
  expect(await page.evaluate(() => !!window.google?.accounts.id)).toBe(true);
  await expect(page.locator('script[src="https://accounts.google.com/gsi/client"]')).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: `../docs/screenshots/google-login-${info.project.name}.png`, fullPage: true });
  expect(errors.filter((message) => /origin.*not allowed|client.*not found|content security policy|refused to load the script/i.test(message)), "Autoriza el origen exacto de VITALSYNC en el cliente de Google Cloud y espera su propagación").toEqual([]);
});
