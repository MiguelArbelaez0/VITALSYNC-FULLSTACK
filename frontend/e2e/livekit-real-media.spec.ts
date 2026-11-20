import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createSign } from "node:crypto";

test("LiveKit real media connects patient and assigned doctor and records explicit finalization", async ({ page, browser }, info) => {
  test.setTimeout(180000);
  test.skip(process.env.E2E_LIVEKIT_REAL !== "true", "Requiere LiveKit local y una base aislada de pruebas");
  const credentials = JSON.parse(readFileSync(process.env.E2E_CREDENTIALS_FILE!, "utf8"));
  const baseURL = process.env.E2E_BASE_URL!;
  const patientContext = await browser.newContext({
    baseURL,
    viewport: info.project.use.viewport,
    permissions: ["camera", "microphone"],
  });
  const patientPage = await patientContext.newPage();
  async function installGoogleFixture(targetPage: typeof page, sub: string, email: string) {
    await targetPage.exposeFunction("fixtureGoogleCredential", (nonce: string) => {
      const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString("base64url");
      const header = encode({ alg: "RS256", typ: "JWT", kid: "e2e-fixture" });
      const body = encode({ sub, email, name: "Usuario Google de prueba", email_verified: true, aud: "controlled-client.apps.googleusercontent.com", iss: "https://accounts.google.com", iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 300, nonce });
      const signed = `${header}.${body}`;
      return `${signed}.${createSign("RSA-SHA256").update(signed).sign(credentials.google_private_key, "base64url")}`;
    });
    await targetPage.addInitScript(() => {
      let options: any;
      (window as any).google = { accounts: { id: {
        initialize: (value: any) => { options = value; },
        renderButton: (element: HTMLElement) => {
          const button = document.createElement("button"); button.textContent = "Continuar con Google";
          button.onclick = async () => options.callback({ credential: await (window as any).fixtureGoogleCredential(options.nonce) });
          element.appendChild(button);
        },
      } } };
    });
  }
  if (process.env.E2E_GOOGLE_FIXTURE === "true") {
    await installGoogleFixture(page, "e2e-google-doctor", "personal-doctor@example.com");
    await installGoogleFixture(patientPage, "e2e-google-patient", "personal-patient@example.com");
  }
  async function linkAndSignInWithGoogle(targetPage: typeof page, role: "doctor" | "portal", password: string) {
    await targetPage.goto(`/${role}/profile`);
    await targetPage.getByLabel("Contraseña actual para confirmar tu identidad").fill(password);
    await targetPage.getByRole("button", { name: "Verificar contraseña y vincular Google" }).click();
    await targetPage.getByRole("button", { name: "Continuar con Google", exact: true }).click();
    await expect(targetPage.getByText("Cuenta Google vinculada correctamente.")).toBeVisible();
    await targetPage.request.post("/api/auth/logout");
    await targetPage.goto("/login");
    await targetPage.getByRole("button", { name: "Continuar con Google", exact: true }).click();
    await expect(targetPage).toHaveURL(new RegExp(`/${role}$`));
  }
  patientPage.setDefaultTimeout(20000);
  page.setDefaultTimeout(20000);
  await page.context().grantPermissions(["camera", "microphone"], { origin: baseURL });
  try {
    const request = patientContext.request;
    const login = await request.post("/api/auth/login", { data: credentials.patient });
    expect(login.ok()).toBeTruthy();

    await page.goto("/login");
    if (process.env.E2E_GOOGLE_FIXTURE === "true") {
      const prepared = await page.request.post("/api/auth/google/challenge", { headers: { Origin: baseURL }, data: { purpose: "LOGIN" } });
      const unlinkedChallenge = await prepared.json();
      const credential = await page.evaluate((nonce: string) => (window as any).fixtureGoogleCredential(nonce), unlinkedChallenge.nonce);
      const unlinked = await page.request.post("/api/auth/google/exchange", { headers: { Origin: baseURL }, data: { challenge: unlinkedChallenge.challenge, credential } });
      expect((await unlinked.json()).registration_required).toBe(true);
      expect((await page.request.get("/api/doctor/dashboard")).status()).toBe(401);
      // A verified Google identity alone never creates a professional account.
    }
    await page.getByLabel("Correo electrónico").fill(credentials.legacy.email);
    await page.getByLabel("Contraseña", { exact: true }).fill(credentials.legacy.password);
    await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
    await expect(page).toHaveURL(/\/doctor$/);
    if (process.env.E2E_GOOGLE_FIXTURE === "true") await linkAndSignInWithGoogle(page, "doctor", credentials.legacy.password);

    await patientPage.goto("/login");
    await patientPage.getByLabel("Correo electrónico").fill(credentials.patient.email);
    await patientPage.getByLabel("Contraseña", { exact: true }).fill(credentials.patient.password);
    await patientPage.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
    await expect(patientPage).toHaveURL(/\/portal$/);
    if (process.env.E2E_GOOGLE_FIXTURE === "true") await linkAndSignInWithGoogle(patientPage, "portal", credentials.patient.password);
    await patientPage.goto("/portal/appointments");
    await expect(patientPage.getByRole("heading", { name: "Prueba una videollamada ahora" })).toBeVisible();
    await patientPage.getByRole("button", { name: "Probar con Dr. Alejandro Méndez" }).click();
    await expect(patientPage.getByRole("heading", { name: "Crear consulta académica de prueba" })).toBeVisible();
    await patientPage.getByRole("button", { name: "Confirmar y entrar" }).click();
    await expect(patientPage).toHaveURL(/\/portal\/appointments\/\d+\/teleconsult$/);
    const appointmentId = Number(patientPage.url().match(/appointments\/(\d+)\/teleconsult$/)?.[1]);
    expect(appointmentId).toBeGreaterThan(0);
    const appointment = await (await request.get(`/api/appointments/${appointmentId}`)).json();
    expect(appointment.status).toBe("CONFIRMED");
    expect(appointment.modality).toBe("VIRTUAL");
    expect(appointment.is_demo_test).toBe(true);
    expect(appointment.appointment_label).toBe("Consulta académica de prueba");
    expect(appointment.plan).toBe("Consulta académica de prueba");
    expect(appointment.copay).toBe(0);
    expect(appointment.livekit_enabled).toBe(true);
    await expect(patientPage.getByRole("heading", { name: "Videoconsulta" })).toBeVisible();
    await expect(patientPage.locator(".lk-prejoin")).toBeVisible();
    if (process.env.E2E_LIVEKIT_PHYSICAL !== "true") {
      await patientPage.screenshot({ path: resolve(import.meta.dirname, `../../docs/screenshots/livekit-prejoin-${info.project.name}.png`), fullPage: true });
    }

    await page.goto("/doctor/appointments");
    await expect(page.getByText("Consulta académica de prueba").first()).toBeVisible();
    await page.locator(`a[href="/doctor/appointments/${appointmentId}"]`).click();
    await expect(page.getByText("Consulta académica de prueba").first()).toBeVisible();
    await page.getByRole("link", { name: "Ingresar a videollamada" }).click();
    await page.getByRole("button", { name: "Iniciar videollamada" }).click();
    await patientPage.getByRole("button", { name: "Ingresar a videollamada" }).click();
    await expect(page.getByText("Esperando al otro participante", { exact: true })).toBeVisible();
    await expect(patientPage.getByText("Esperando al otro participante", { exact: true })).toBeVisible();
    await expect(page.getByText("Conectado", { exact: true }).first()).toBeVisible({ timeout: 30000 });
    await expect(patientPage.getByText("Conectado", { exact: true }).first()).toBeVisible({ timeout: 30000 });
    await expect.poll(async () => (await (await request.get(`/api/appointments/${appointmentId}`)).json()).status, { timeout: 30000 }).toBe("IN_PROGRESS");
    await expect.poll(async () => (await (await request.get(`/api/appointments/${appointmentId}`)).json()).virtual_state?.started_at, { timeout: 30000 }).toBeTruthy();
    await expect(patientPage.locator(".livekit-duration")).not.toContainText("Pendiente", { timeout: 15000 });

    const remoteVideoHasFrames = async () => patientPage.locator("video").evaluateAll((videos) =>
      videos.filter((element) => element instanceof HTMLVideoElement
        && element.readyState >= 2
        && element.videoWidth > 0
        && element.videoHeight > 0).length,
    );
    await expect.poll(remoteVideoHasFrames, { timeout: 30000 }).toBeGreaterThanOrEqual(2);
    const remoteAudioHasLiveTrack = async (targetPage: typeof patientPage) => targetPage.locator("audio").evaluateAll((elements) =>
      elements.some((element) => element instanceof HTMLAudioElement
        && element.srcObject instanceof MediaStream
        && element.srcObject.getAudioTracks().some((track) => track.readyState === "live")),
    );
    await expect.poll(() => remoteAudioHasLiveTrack(patientPage), { timeout: 15000 }).toBeTruthy();
    await expect.poll(() => remoteAudioHasLiveTrack(page), { timeout: 15000 }).toBeTruthy();
    await expect.poll(async () => page.locator("video").evaluateAll((videos) =>
      videos.filter((element) => element instanceof HTMLVideoElement
        && element.readyState >= 2
        && element.videoWidth > 0
        && element.videoHeight > 0).length,
    ), { timeout: 30000 }).toBeGreaterThanOrEqual(2);
    if (process.env.E2E_LIVEKIT_PHYSICAL !== "true") {
      await patientPage.screenshot({ path: resolve(import.meta.dirname, `../../docs/screenshots/livekit-room-${info.project.name}.png`), fullPage: true });
      if (info.project.name === "desktop") {
        await patientPage.setViewportSize({ width: 390, height: 844 });
        await patientPage.locator('.sidebar-brand button[aria-label="Cerrar menú"]').evaluate((button: HTMLButtonElement) => button.click());
        await patientPage.waitForTimeout(250);
        await patientPage.screenshot({ path: resolve(import.meta.dirname, "../../docs/screenshots/livekit-room-mobile.png"), fullPage: true });
        await patientPage.setViewportSize({ width: 1280, height: 900 });
      }
    }

    await patientPage.getByRole("button", { name: "Salir de la llamada" }).click();
    await expect(patientPage).toHaveURL(/\/portal\/appointments$/);
    await expect(page.getByText("El otro participante salió o perdió la conexión.")).toBeVisible({ timeout: 30000 });
    const afterExit = await (await request.get(`/api/appointments/${appointmentId}`)).json();
    expect(afterExit.status).toBe("IN_PROGRESS");
    await patientPage.goto(`/portal/appointments/${appointmentId}/teleconsult`);
    await patientPage.getByRole("button", { name: "Ingresar a videollamada" }).click();
    await expect(patientPage.getByText("Conectado", { exact: true }).first()).toBeVisible({ timeout: 30000 });

    await page.reload();
    await expect(page.locator(".lk-prejoin")).toBeVisible();
    await expect(patientPage.getByText("El otro participante salió o perdió la conexión.")).toBeVisible({ timeout: 30000 });
    await page.getByRole("button", { name: "Iniciar videollamada" }).click();
    await expect(page.getByText("Conectado", { exact: true }).first()).toBeVisible({ timeout: 30000 });

    await page.getByRole("button", { name: "Finalizar consulta" }).click();
    await page.getByRole("button", { name: "Confirmar y finalizar" }).click();
    await expect(page.getByRole("heading", { name: "Consulta finalizada" })).toBeVisible({ timeout: 20000 });
    await expect(patientPage.getByRole("heading", { name: "Consulta finalizada" })).toBeVisible({ timeout: 20000 });
    if (process.env.E2E_LIVEKIT_PHYSICAL !== "true") {
      await page.screenshot({ path: resolve(import.meta.dirname, "../../docs/screenshots/livekit-finished-desktop.png"), fullPage: true });
      await patientPage.setViewportSize({ width: 390, height: 844 });
      await patientPage.locator('.sidebar-brand button[aria-label="Cerrar menú"]').evaluate((button: HTMLButtonElement) => button.click());
      await patientPage.waitForTimeout(250);
      await patientPage.screenshot({ path: resolve(import.meta.dirname, "../../docs/screenshots/livekit-finished-mobile.png"), fullPage: true });
    }
    const finalToken = await request.post(`/api/appointments/${appointmentId}/livekit-token`, { data: {} });
    expect(finalToken.status()).toBe(409);
    const completed = await (await request.get("/api/appointments?view=completed")).json();
    expect(completed.some((item: any) => item.id === appointmentId && item.status === "ATTENDED")).toBeTruthy();
    const doctorHistory = await (await page.request.get("/api/doctor/appointments?view=history")).json();
    expect(doctorHistory.some((item: any) => item.id === appointmentId && item.status === "ATTENDED")).toBeTruthy();
    const adminContext = await browser.newContext({ baseURL });
    try {
      const adminPage = await adminContext.newPage();
      const adminLogin = await adminContext.request.post("/api/auth/login", { data: credentials.admin });
      expect(adminLogin.ok()).toBeTruthy();
      const adminAppointment = await (await adminContext.request.get(`/api/admin/appointments/${appointmentId}`)).json();
      expect(adminAppointment.status_label).toBe("FINALIZADA");
      expect(adminAppointment.virtual_session.finalized_at).toBeTruthy();
      await adminPage.close();
    } finally { await adminContext.close(); }
  } finally {
    await patientContext.close();
  }
});
