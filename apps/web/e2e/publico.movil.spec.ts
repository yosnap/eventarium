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
    for (const ruta of [ponente].filter((r): r is string => !!r)) {
      await page.goto(ruta);
      await esperarSinDesborde(page, ruta);
    }
  });

  test('las funcionalidades de la home no se apilan en móvil', async ({ page }) => {
    await page.goto('/');
    const tarjeta = page.locator('.landing-tarjeta').first();
    await tarjeta.scrollIntoViewIfNeeded();
    await expect(tarjeta).toHaveCSS('position', 'static');
    // Sin el encogido de la directiva: la tarjeta conserva su tamaño.
    await expect(tarjeta).not.toHaveCSS('transform', /matrix\(0\.9/);
  });
});
