import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

test("LiveKit real media practice rooms work without appointments", async ({ page, browser }, info) => {
  test.skip(process.env.E2E_LIVEKIT_REAL !== "true", "Requiere los servicios de prueba aislados");
  const credentials = JSON.parse(readFileSync(process.env.E2E_CREDENTIALS_FILE!, "utf8"));
  const doctor = await browser.newContext({ baseURL: process.env.E2E_BASE_URL });
  try {
    if (process.env.E2E_LIVEKIT_PHYSICAL !== "true") {
      await page.addInitScript(() => {
        // Synthetic capture exercises real LiveKit screen publication without a native picker.
        Object.defineProperty(navigator.mediaDevices, "getDisplayMedia", {
          configurable: true,
          value: async () => {
            const canvas = document.createElement("canvas");
            canvas.width = 640;
            canvas.height = 360;
            const stream = canvas.captureStream(10);
            const track = stream.getVideoTracks()[0] as CanvasCaptureMediaStreamTrack;
            const draw = () => {
              const context = canvas.getContext("2d")!;
              context.fillStyle = "#127b80";
              context.fillRect(0, 0, 640, 360);
              track.requestFrame();
            };
            draw();
            const timer = window.setInterval(() => {
              if (track.readyState === "ended") window.clearInterval(timer);
              else draw();
            }, 100);
            return stream;
          },
        });
      });
    }
    await page.context().grantPermissions(["camera", "microphone"]);
    await doctor.grantPermissions(["camera", "microphone"]);
    expect((await page.request.post("/api/auth/login", { data: credentials.patient })).ok()).toBeTruthy();
    expect((await doctor.request.post("/api/auth/login", { data: credentials.legacy })).ok()).toBeTruthy();
    const before = await (await page.request.get("/api/appointments")).json();
    await page.goto("/portal/simulation");
    await page.getByRole("button", { name: "Prueba individual" }).click();
    await page.getByRole("button", { name: "Ingresar a simulación" }).click();
    await expect(page.getByText("Conectado", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Activar micrófono", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Terminar simulación", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Simulación finalizada" })).toBeVisible();
    await page.getByRole("button", { name: "Volver a la sala de simulación" }).click();
    await page.getByRole("button", { name: "Crear sala privada" }).click();
    const invite = page.getByRole("textbox", { name: /Invitación privada/ });
    await expect(invite).toBeVisible();
    const guest = await doctor.newPage();
    await guest.goto("/doctor/simulation");
    await guest.getByLabel("Código de invitación").fill(await invite.inputValue());
    await guest.getByRole("button", { name: "Aceptar invitación" }).click();
    await page.getByRole("button", { name: "Activar cámara", exact: true }).click();
    await page.getByRole("button", { name: "Desactivar cámara", exact: true }).waitFor();
    await guest.getByRole("button", { name: "Activar micrófono", exact: true }).click();
    await guest.getByRole("button", { name: "Desactivar micrófono", exact: true }).waitFor();
    await page.getByRole("button", { name: "Ingresar a simulación" }).click();
    await guest.getByRole("button", { name: "Ingresar a simulación" }).click();
    await expect(page.getByText("Participantes (2)", { exact: true })).toBeVisible({ timeout: 20000 });
    if (process.env.E2E_LIVEKIT_PHYSICAL !== "true") {
      await page.getByRole("button", { name: "Compartir pantalla", exact: true }).click();
      await expect(guest.getByText(/Pantalla compartida/)).toBeVisible({ timeout: 15000 });
      await expect.poll(() => guest.locator("video.livekit-screen").evaluate(video => (video as HTMLVideoElement).videoWidth)).toBeGreaterThan(0);
      await guest.screenshot({ path: info.outputPath("simulation-shared-screen.png"), fullPage: true });
      await page.getByRole("button", { name: "Dejar de compartir", exact: true }).click();
      await expect(guest.locator("video.livekit-screen")).toHaveCount(0);
    }
    if (await page.getByRole("button", { name: "Pantalla completa", exact: true }).isVisible()) {
      await page.getByRole("button", { name: "Pantalla completa", exact: true }).click();
      await expect(page.getByRole("button", { name: "Restaurar tamaño", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Restaurar tamaño", exact: true }).click();
    }
    await guest.getByRole("button", { name: "Salir de la sala" }).click();
    await guest.getByRole("button", { name: "Ingresar a simulación" }).click();
    await expect(page.getByText("Participantes (2)", { exact: true })).toBeVisible({ timeout: 20000 });
    await page.screenshot({ path: info.outputPath("simulation.png"), mask: [invite], maskColor: "#e5f5f3", fullPage: true });
    const rooms = await (await page.request.get("/api/simulation/rooms")).json();
    const issued = await (await page.request.post(`/api/simulation/rooms/${rooms[0].id}/token`)).json();
    const validate = async () => (await fetch(issued.server_url.replace(/^ws/, "http") + "/rtc/validate", {
      headers: { Authorization: "Bearer " + issued.token },
    })).status;
    expect(await validate()).toBe(200);
    await page.getByRole("button", { name: "Terminar simulación", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Simulación finalizada" })).toBeVisible();
    await expect(guest.getByRole("heading", { name: "Simulación finalizada" })).toBeVisible({ timeout: 15000 });
    await expect.poll(validate, { timeout: 10000 }).toBe(404);
    expect(await (await page.request.get("/api/appointments")).json()).toEqual(before);
  } finally { await doctor.close(); }
});
