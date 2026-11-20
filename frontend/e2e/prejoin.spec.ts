import { test, expect, type Page } from "@playwright/test";

async function openPreview(page: Page) {
  await page.context().grantPermissions(["camera", "microphone"]);
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") return route.fulfill({ status: 403, json: { detail: "No se autorizan escrituras en este fixture" } });
    const data = path === "/api/auth/me" ? { id: 900, name: "Paciente de prueba", email: "preview@example.com", role: "PATIENT", has_document: true }
      : path.endsWith("/teleconsult") || path === "/api/appointments/900" ? { id: 900, code: "VS-PREVIEW", patient: "Paciente de prueba", doctor: "Médico de prueba", specialty: "Medicina general", starts_at: new Date().toISOString(), ends_at: new Date(Date.now() + 1800000).toISOString(), modality: "VIRTUAL", status: "CONFIRMED", virtual_status: "SALA_DISPONIBLE", livekit_enabled: true, livekit_connection_state: "WAITING", history: [], copay: 0 }
        : path === "/api/config" ? { demo_mode: false, livekit_enabled: true } : [];
    await route.fulfill({ json: data });
  });
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    (window as any).previewDiagnostics = { starts: 0, stops: 0 };
    navigator.mediaDevices.getUserMedia = async (constraints) => {
      (window as any).previewDiagnostics.starts++;
      const stream = await original(constraints);
      stream.getTracks().forEach((track) => {
        const stop = track.stop.bind(track);
        track.stop = () => { (window as any).previewDiagnostics.stops++; stop(); };
      });
      return stream;
    };
  });
  await page.goto("/portal/appointments/900/teleconsult");
  await expect(page.getByRole("heading", { name: "Antes de ingresar" })).toBeVisible();
}

test("local preview stays live across the consultation clock renders", async ({ page }, info) => {
  await openPreview(page);
  await page.getByRole("button", { name: "Activar cámara", exact: true }).click();
  await expect.poll(() => page.locator("video").evaluateAll((videos) => videos.some((video) => video instanceof HTMLVideoElement && video.readyState >= 2 && video.videoWidth > 0))).toBe(true);
  const before = await page.evaluate(() => (window as any).previewDiagnostics.starts);
  await page.waitForTimeout(3200); // Cross three deliberate one-second clock renders.
  const after = await page.evaluate(() => (window as any).previewDiagnostics);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `../docs/screenshots/prejoin-${info.project.name}.png`, fullPage: true });
  expect(after.starts).toBe(before);
  expect(after.stops).toBe(0);
  await expect(page.getByRole("button", { name: "Mostrar vista previa" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("preview controls have AA contrast and do not publish before joining", async ({ page }) => {
  let tokenRequests = 0;
  page.on("request", (request) => { if (request.url().includes("livekit-token")) tokenRequests++; });
  await openPreview(page);
  const contrast = () => page.locator(".preview-toggle, .preview-join").evaluateAll((buttons) => buttons.map((button) => {
    const style = getComputedStyle(button);
    const luminance = (color: string) => {
      const components = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map((value) => value / 255).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
      return .2126 * components[0] + .7152 * components[1] + .0722 * components[2];
    };
    const text = luminance(style.color), background = luminance(style.backgroundColor);
    return (Math.max(text, background) + .05) / (Math.min(text, background) + .05);
  }));
  expect(Math.min(...await contrast())).toBeGreaterThanOrEqual(4.5);
  await page.getByRole("button", { name: "Ingresar a videollamada", exact: true }).hover();
  expect(Math.min(...await contrast())).toBeGreaterThanOrEqual(4.5);
  await page.getByRole("button", { name: "Activar cámara", exact: true }).focus();
  expect(await page.getByRole("button", { name: "Activar cámara", exact: true }).evaluate((button) => getComputedStyle(button).outlineStyle)).toBe("solid");
  expect(tokenRequests).toBe(0);
});

for (const [failure, explanation] of [["NotAllowedError", "En Chrome"], ["NotFoundError", "No encontramos la cámara"], ["NotReadableError", "Otra aplicación"]]) {
  test(`preview explains ${failure} and recovers without blocking the microphone`, async ({ page }) => {
    await page.addInitScript((errorName) => {
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      let rejected = false;
      navigator.mediaDevices.getUserMedia = async (constraints) => {
        if (constraints?.video && !rejected) { rejected = true; throw new DOMException("Controlled media failure", errorName); }
        return original(constraints);
      };
    }, failure);
    await openPreview(page);
    await page.getByRole("button", { name: "Activar cámara", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(explanation);
    await page.getByRole("button", { name: "Activar micrófono", exact: true }).click();
    await expect(page.getByRole("button", { name: "Desactivar micrófono", exact: true })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Ingresar a videollamada", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Reintentar cámara" }).click();
    await expect(page.getByText("Cámara activa · Solo vista previa")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.getByRole("button", { name: "Desactivar cámara", exact: true }).click();
    await expect(page.getByText("Tu cámara está desactivada")).toBeVisible();
    await expect(page.getByRole("button", { name: "Ingresar a videollamada", exact: true })).toBeEnabled();
  });
}

test("device selection replaces local tracks and navigation stops all capture", async ({ page }) => {
  await openPreview(page);
  await page.getByRole("button", { name: "Activar cámara", exact: true }).click();
  await page.getByRole("button", { name: "Activar micrófono", exact: true }).click();
  await expect(page.getByRole("button", { name: "Desactivar micrófono", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Desactivar cámara", exact: true })).toBeEnabled();
  const old = await page.evaluate(() => (window as any).previewDiagnostics.starts);
  await page.getByLabel("Seleccionar cámara").selectOption("");
  await expect(page.getByRole("button", { name: "Desactivar cámara", exact: true })).toBeEnabled();
  await page.getByLabel("Seleccionar micrófono").selectOption("");
  await expect(page.getByRole("button", { name: "Desactivar micrófono", exact: true })).toBeEnabled();
  expect(await page.evaluate(() => (window as any).previewDiagnostics.starts)).toBeGreaterThan(old);
  await page.getByRole("link", { name: "← Volver al detalle de la cita" }).click();
  await expect(page).toHaveURL(/\/portal\/appointments\/900$/);
  await expect.poll(() => page.evaluate(() => (window as any).previewDiagnostics.stops)).toBeGreaterThanOrEqual(4);
});
