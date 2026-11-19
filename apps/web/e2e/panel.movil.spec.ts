import { expect, test } from '@playwright/test';

import { altaDeOrganizador, crearEvento } from './alta-organizador';

import { esperarSinDesborde } from './desborde';

const PANEL = [
  '/dashboard',
  '/dashboard/organization',
  '/dashboard/branding',
  '/dashboard/politicas',
  '/dashboard/roles',
  '/dashboard/members',
  '/dashboard/members/nuevo',
  '/dashboard/events',
  '/dashboard/events/nuevo',
  '/dashboard/sponsor-tiers',
  '/dashboard/stripe',
  '/dashboard/ia',
  '/dashboard/account',
  '/dashboard/mcp',
];

const DEL_EVENTO = [
  '',
  '/agenda',
  '/diseno',
  '/entradas',
  '/descuentos',
  '/patrocinadores',
  '/ponentes',
  '/politicas',
  '/inscripciones',
  '/payments',
  '/contabilidad',
  '/check-in',
];

test.describe('Panel del organizador en un móvil de 360 px', () => {
  test('alta completa y todas las pantallas sin desborde', async ({ page }) => {
    test.setTimeout(480_000);
    const correo = await altaDeOrganizador(page);
    const eventoId = await crearEvento(page, correo);

    for (const ruta of [...PANEL, ...DEL_EVENTO.map((s) => `/dashboard/events/${eventoId}${s}`)]) {
      await page.goto(ruta);
      // Que la pantalla se haya pintado de verdad, no una vacía o un error.
      await expect(page.locator('main h1').first(), `${ruta}: sin título`).toBeVisible();
      await esperarSinDesborde(page, ruta);
    }
  });
});
