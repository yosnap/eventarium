import { expect, test } from '@playwright/test';

import { esperarSinDesborde } from './desborde';

/** El evento de la semilla con más contenido (sedes, sesiones, ponentes). */
const EVENTO = process.env['E2E_EVENTO'] ?? 'demo-multisede-tres';

const RUTAS_FIJAS = [
  '/',
  '/eventos',
  `/eventos/${EVENTO}`,
  `/eventos/${EVENTO}/programa`,
  `/eventos/${EVENTO}/inscribirse`,
  `/eventos/${EVENTO}/politicas`,
  '/acceder',
  '/registro',
  '/recuperar-contrasena',
  '/mis-eventos',
  '/legal/aviso-legal',
  '/legal/privacidad',
  '/legal/cookies',
  '/legal/condiciones-de-inscripcion',
];

test.describe('Páginas públicas en un móvil de 360 px', () => {
  for (const ruta of RUTAS_FIJAS) {
    test(`sin desborde horizontal: ${ruta}`, async ({ page }) => {
      await page.goto(ruta);
      await esperarSinDesborde(page, ruta);
    });
  }

  test('sin desborde en una sesión y un ponente de la agenda', async ({ page }) => {
    await page.goto(`/eventos/${EVENTO}`);
    const sesion = await page.locator('a[href*="/sesiones/"]').first().getAttribute('href');
    expect(sesion, 'la agenda de la semilla enlaza alguna sesión').toBeTruthy();
    await page.goto(sesion!);
    await esperarSinDesborde(page, sesion!);
    const ponente = await page.locator('a[href^="/ponentes/"]').first().getAttribute('href');
    expect(ponente, 'la sesión de la semilla enlaza algún ponente').toBeTruthy();
    await page.goto(ponente!);
    await esperarSinDesborde(page, ponente!);
  });

  for (const ancho of [360, 768]) {
    test(`las funcionalidades de la home se apilan bajo la cabecera y caben a ${ancho} px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: ancho, height: 780 });
      await page.goto('/');
      const tarjetas = page.locator('.landing-tarjeta');
      await expect(tarjetas.first()).toBeVisible();
      await expect(tarjetas.first()).toHaveCSS('position', 'sticky');
      await page.evaluate(() => document.fonts.ready);
      const { cabecera, medidas } = await page.evaluate(() => ({
        cabecera: document.querySelector('header')!.getBoundingClientRect().height,
        medidas: [...document.querySelectorAll('.landing-tarjeta')].map((el) => ({
          top: parseFloat(getComputedStyle(el).top),
          alto: el.getBoundingClientRect().height,
        })),
      }));
      // Pegada a su `top`, la tarjeta queda por debajo de la cabecera y se
      // ve entera: si no, la cabecera o la siguiente tarjeta la tapan.
      for (const { top, alto } of medidas) {
        expect(top).toBeGreaterThanOrEqual(cabecera);
        expect(top + alto).toBeLessThanOrEqual(780);
      }
    });
  }
});
