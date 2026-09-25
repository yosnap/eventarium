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

  test('las funcionalidades de la home se apilan y cada tarjeta cabe en la pantalla', async ({
    page,
  }) => {
    await page.goto('/');
    const tarjetas = page.locator('.landing-tarjeta');
    await expect(tarjetas.first()).toHaveCSS('position', 'sticky');
    const alto = page.viewportSize()!.height;
    const medidas = await tarjetas.evaluateAll((els) =>
      els.map((el) => ({
        top: parseFloat(getComputedStyle(el).top),
        alto: el.getBoundingClientRect().height,
      })),
    );
    // Pegada a su `top`, la tarjeta entera tiene que verse: si no, la
    // siguiente la tapa antes de que se vea su captura.
    for (const { top, alto: altoTarjeta } of medidas) {
      expect(top + altoTarjeta).toBeLessThanOrEqual(alto);
    }
  });
});
