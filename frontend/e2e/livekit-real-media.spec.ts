import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("LiveKit real media connects patient and assigned doctor and records explicit finalization", async ({ page, browser }, info) => {
  test.setTimeout(180000);
  test.skip(process.env.E2E_LIVEKIT_REAL !== "true", "Requiere LiveKit local y una base aislada de pruebas");
  const credentials = JSON.parse(readFileSync(process.env.E2E_CREDENTIALS_FILE!, "utf8"));
  const stamp = Date.now();
  const baseURL = process.env.E2E_BASE_URL!;
  const patientContext = await browser.newContext({
    baseURL,
    viewport: info.project.use.viewport,
    permissions: ["camera", "microphone"],
  });
  const patientPage = await patientContext.newPage();
  patientPage.setDefaultTimeout(20000);
  page.setDefaultTimeout(20000);
  await page.context().grantPermissions(["camera", "microphone"], { origin: baseURL });
  try {
    const request = patientContext.request;
    const login = await request.post("/api/auth/login", { data: credentials.patient });
    expect(login.ok()).toBeTruthy();
    const plans = await (await request.get("/api/plans")).json();
    const premium = plans.find((plan: any) => plan.name === "Premium");
    expect(premium).toBeTruthy();
    const activated = await request.post("/api/payments", {
      data: { kind: "PLAN", target_id: premium.id, status: "APPROVED", idempotency_key: `livekit-plan-${stamp}` },
    });
    expect(activated.ok()).toBeTruthy();
    const doctors = await (await request.get("/api/doctors?modality=VIRTUAL")).json();
    const doctor = doctors.find((item: any) => item.name === "Dr. Alejandro Méndez");
    expect(doctor).toBeTruthy();
    const slots = await (await request.get(`/api/doctors/${doctor.id}/availability?modality=VIRTUAL`)).json();
    const slot = slots.find((item: any) => item.available);
    expect(slot).toBeTruthy();
    const holdResponse = await request.post("/api/holds", { data: { availability_id: slot.id, modality: "VIRTUAL" } });
    expect(holdResponse.status()).toBe(201);
    const hold = await holdResponse.json();
    const confirmed = await request.post(`/api/holds/${hold.id}/confirm`);
    expect(confirmed.ok()).toBeTruthy();
    const appointmentId = (await confirmed.json()).id;
    const appointment = await (await request.get(`/api/appointments/${appointmentId}`)).json();
    expect(appointment.status).toBe("CONFIRMED");
    expect(appointment.modality).toBe("VIRTUAL");
    expect(appointment.livekit_enabled).toBe(true);

    await page.goto("/login");
    await page.getByLabel("Correo electrónico").fill(credentials.legacy.email);
    await page.getByLabel("Contraseña", { exact: true }).fill(credentials.legacy.password);
    await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
    await expect(page).toHaveURL(/\/doctor$/);

    await patientPage.goto("/login");
    await patientPage.getByLabel("Correo electrónico").fill(credentials.patient.email);
    await patientPage.getByLabel("Contraseña", { exact: true }).fill(credentials.patient.password);
    await patientPage.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
    await patientPage.goto(`/portal/appointments/${appointmentId}`);
    await expect(patientPage.getByRole("heading", { name: "Detalle de tu cita" })).toBeVisible();
    await patientPage.getByRole("link", { name: "Ingresar a videollamada" }).click();
    await expect(patientPage.getByRole("heading", { name: "Videollamada con tu médico" })).toBeVisible();
    await expect(patientPage.locator(".lk-prejoin")).toBeVisible();
    if (process.env.E2E_LIVEKIT_PHYSICAL !== "true") {
      await patientPage.screenshot({ path: resolve(import.meta.dirname, `../../docs/screenshots/livekit-prejoin-${info.project.name}.png`), fullPage: true });
    }

    await page.goto(`/doctor/appointments/${appointmentId}/teleconsult`);
    await page.getByRole("button", { name: "Iniciar videollamada" }).click();
    await patientPage.getByRole("button", { name: "Ingresar a videollamada" }).click();
    await expect(page.getByText("Esperando al otro participante")).toBeVisible();
    await expect(patientPage.getByText("Esperando al otro participante")).toBeVisible();
    await expect(page.getByText("Paciente y médico conectados")).toBeVisible({ timeout: 30000 });
    await expect(patientPage.getByText("Paciente y médico conectados")).toBeVisible({ timeout: 30000 });

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
    }

    await page.reload();
    await expect(page.locator(".lk-prejoin")).toBeVisible();
    await expect(patientPage.getByText(/reconectando/i)).toBeVisible({ timeout: 30000 });
    await page.getByRole("button", { name: "Iniciar videollamada" }).click();
    await expect(page.getByText("Paciente y médico conectados")).toBeVisible({ timeout: 30000 });

    await page.getByRole("button", { name: "Finalizar consulta" }).click();
    await page.getByRole("button", { name: "Confirmar finalización" }).click();
    await expect(page).toHaveURL(/\/doctor\/appointments$/);
    await expect(patientPage.getByText(/La consulta ya finalizó/)).toBeVisible({ timeout: 20000 });
    const finalToken = await request.post(`/api/appointments/${appointmentId}/livekit-token`, { data: {} });
    expect(finalToken.status()).toBe(409);
    const completed = await (await request.get("/api/appointments?view=completed")).json();
    expect(completed.some((item: any) => item.id === appointmentId && item.status === "ATTENDED")).toBeTruthy();
  } finally {
    await patientContext.close();
  }
});
