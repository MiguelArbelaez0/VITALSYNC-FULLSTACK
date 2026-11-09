import { expect, test } from "@playwright/test";

test("el botón de teleconsulta mantiene contraste y foco accesible", async ({
  page,
}) => {
  await page.goto("/");
  await page.evaluate(() => {
    document.body.innerHTML = `
      <main style="padding: 40px">
        <div class="notice virtual-link">
          <strong>Teleconsulta simulada</strong>
          <p>Esta experiencia no usa conexión de audio o video.</p>
          <a class="btn btn-primary virtual-teleconsult-button" href="#teleconsult">
            <svg aria-hidden="true" width="17" height="17" viewBox="0 0 17 17"><circle cx="8" cy="8" r="7" fill="currentColor" /></svg>
            Ver teleconsulta simulada
          </a>
          <button class="btn btn-primary virtual-teleconsult-button" type="button" disabled>
            <svg aria-hidden="true" width="17" height="17" viewBox="0 0 17 17"><circle cx="8" cy="8" r="7" fill="currentColor" /></svg>
            Ver teleconsulta simulada
          </button>
        </div>
      </main>`;
  });

  const enabled = page.locator("a.virtual-teleconsult-button");
  const enabledColors = await enabled.evaluate((element) => ({
    background: getComputedStyle(element).backgroundColor,
    text: getComputedStyle(element).color,
    icon: getComputedStyle(element.querySelector("svg")!).color,
  }));
  expect(enabledColors).toEqual({
    background: "rgb(18, 119, 132)",
    text: "rgb(255, 255, 255)",
    icon: "rgb(255, 255, 255)",
  });

  await enabled.hover();
  await expect(enabled).toHaveCSS("background-color", "rgb(13, 101, 114)");
  await page.keyboard.press("Tab");
  await expect(enabled).toBeFocused();
  await expect(enabled).toHaveCSS("outline-style", "solid");

  const disabled = page.locator("button.virtual-teleconsult-button");
  await expect(disabled).toBeDisabled();
  const disabledColors = await disabled.evaluate((element) => ({
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
});
