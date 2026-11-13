import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";

for (const appointmentCount of [1, 2]) test(`finalización futura con ${appointmentCount} citas persiste y actualiza la agenda`, async ({ page }) => {
  test.setTimeout(180000);
  test.skip(process.env.E2E_LIFECYCLE_ISOLATED !== "true", "Requiere backend con base aislada; no usar datos de demostración");
  const request = page.request;
  const email = `lifecycle-${Date.now()}@example.com`;
  const password = "Paciente2026!";
  const registered = await request.post('/api/auth/register', { data: {
    given_names: 'Paciente', surnames: 'Prueba Ciclo', document_type: 'CC',
    document_number: String(Date.now()).slice(-10), email, password,
    phone: '+57 300 123 4567', privacy_accepted: true,
  }});
  expect(registered.status()).toBe(201);
  const plans = await (await request.get('/api/plans')).json();
  expect((await request.post('/api/payments', { data: {
    kind: 'PLAN', target_id: plans.find((p: any) => p.name === 'Premium').id,
    status: 'APPROVED', idempotency_key: `plan-${Date.now()}`,
  }})).ok()).toBeTruthy();
  const doctors = await (await request.get('/api/doctors?modality=VIRTUAL')).json();
  const ids: number[] = [];
  for (const doctor of doctors.slice(0, appointmentCount)) {
    const slots = await (await request.get(`/api/doctors/${doctor.id}/availability?modality=VIRTUAL`)).json();
    const existing = await (await request.get('/api/appointments')).json();
    const slot = slots.find((s: any) => s.available && !existing.some((a: any) => a.starts_at === s.starts_at));
    const hold = await (await request.post('/api/holds', { data: { availability_id: slot.id, modality: 'VIRTUAL' }})).json();
    const confirmation = await request.post(`/api/holds/${hold.id}/confirm`);
    expect(confirmation.ok()).toBeTruthy();
    ids.push((await confirmation.json()).id);
  }
  const [aid, other] = ids;
  const original = await (await request.get(`/api/appointments/${aid}`)).json();
  await request.post('/api/auth/logout');
  await page.goto('/login');
  await page.getByLabel('Correo electrónico').fill(email);
  await page.getByLabel('Contraseña', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  await expect(page).toHaveURL(/portal/);
  await page.goto('/portal/appointments');
  await page.locator(`a[href="/portal/appointments/${aid}"]`).click();
  await page.getByRole('link', { name: 'Ver teleconsulta simulada' }).click();
  await expect(page.getByRole('button', { name: /Avanzar reloj de demostración|Abrir sala simulada/ }).first()).toBeVisible();
  const advanceClock = page.getByRole('button', { name: 'Avanzar reloj de demostración' });
  if (await advanceClock.count()) await advanceClock.click();
  await page.getByRole('button', { name: 'Abrir sala simulada' }).click();
  await page.getByRole('button', { name: 'Ingresar como paciente' }).click();
  await page.getByRole('button', { name: 'Simular ingreso del médico' }).click();
  await page.getByRole('button', { name: 'Iniciar atención simulada' }).click();
  await page.getByRole('button', { name: 'Finalizar teleconsulta simulada' }).click();
  await expect(page.getByRole('link', { name: 'Ver historial de cita' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Simular|Finalizar/ })).toHaveCount(0);
  await page.getByRole('link', { name: 'Ver historial de cita' }).click();
  await expect(page).toHaveURL(new RegExp(`/portal/appointments/${aid}$`));
  await expect(page.getByRole('heading', { name: 'Detalle de tu cita' })).toBeVisible();
  await expect(page.getByText('Finalizada (simulación)', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancelar cita', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: '← Volver a Mis citas' }).click();
  await expect(page.locator(`a[href="/portal/appointments/${aid}"]`)).toHaveCount(0);
  if (other) await expect(page.locator(`a[href="/portal/appointments/${other}"]`)).toBeVisible();
  await page.getByRole('tab', { name: 'Historial · Finalizadas', exact: true }).click();
  await expect(page.locator(`a[href="/portal/appointments/${aid}"]`)).toBeVisible();
  await page.reload();
  await page.getByRole('tab', { name: 'Historial · Finalizadas', exact: true }).click();
  await expect(page.locator(`a[href="/portal/appointments/${aid}"]`)).toBeVisible();
  await page.goto('/portal');
  if (other) await expect(page.locator(`a[href="/portal/appointments/${other}"]`)).toBeVisible();
  else await expect(page.getByText("No tienes próximas citas programadas")).toBeVisible();
  const persisted = await (await request.get(`/api/appointments/${aid}`)).json();
  expect(persisted).toMatchObject({ status: 'ATTENDED', virtual_status: 'FINALIZADA', completion_source: 'DEMO', clinically_attended: false, starts_at: original.starts_at });
  if (process.env.E2E_RESTART_CONTAINER) {
    if (process.env.E2E_RESTART_POSTGRES) {
      execFileSync('docker', ['restart', process.env.E2E_RESTART_POSTGRES], { timeout: 60000 });
    }
    execFileSync('docker', ['restart', process.env.E2E_RESTART_CONTAINER], { timeout: 60000 });
    await expect.poll(async () => {
      try { return (await request.get('/api/health')).status(); } catch { return 0; }
    }, { timeout: 60000 }).toBe(200);
    await request.post('/api/auth/logout');
    await page.goto('/login');
    await page.getByLabel('Correo electrónico').fill(email);
    await page.getByLabel('Contraseña', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
    await expect(page).toHaveURL(/portal/);
    const after = await (await request.get(`/api/appointments/${aid}`)).json();
    expect(after).toEqual(persisted);
    const dashboard = await (await request.get('/api/dashboard')).json();
    expect(dashboard.upcoming_count).toBe(appointmentCount - 1);
    if (other) expect(dashboard.next_appointment.id).toBe(other);
    else expect(dashboard.next_appointment).toBeNull();
  }
  await page.screenshot({ path: `test-results/demo-lifecycle-${appointmentCount}-${test.info().project.name}.png`, fullPage: true });
});
