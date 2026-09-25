import { expect, type APIRequestContext, type Page, test } from '@playwright/test';

import { esperarSinDesborde } from './desborde';

const MAILPIT = process.env['E2E_MAILPIT_URL'] ?? 'http://localhost:8025';
const PASSWORD = 'Movil-e2e-Pr0bando!';

/** Enlace de verificación del último correo enviado a `correo` (Mailpit de desarrollo). */
async function enlaceDeVerificacion(request: APIRequestContext, correo: string): Promise<string> {
  for (let intento = 0; intento < 30; intento++) {
    const busqueda = await request.get(`${MAILPIT}/api/v1/search`, {
      params: { query: `to:${correo}` },
    });
    const { messages } = (await busqueda.json()) as { messages: { ID: string }[] };
    if (messages.length > 0) {
      const mensaje = await request.get(`${MAILPIT}/api/v1/message/${messages[0]!.ID}`);
      const { Text } = (await mensaje.json()) as { Text: string };
      const enlace = Text.match(/https?:\/\/\S*verificar-correo\?token=[^\s]+/)?.[0];
      if (enlace) return new URL(enlace).pathname + new URL(enlace).search;
    }
    await new Promise((resolver) => setTimeout(resolver, 1000));
  }
  throw new Error(`No ha llegado a Mailpit el correo de verificación de ${correo}`);
}

/**
 * El camino completo de alguien nuevo, el mismo que falló en producción:
 * registrarse, verificar el correo, crear la organización y aterrizar en el
 * escritorio sin el error «No se pudieron cargar los datos».
 */
async function altaDeOrganizador(page: Page): Promise<string> {
  const correo = `movil-${Date.now()}@example.com`;
  const alta = await page.request.post('/api/v1/auth/register', {
    data: { email: correo, password: PASSWORD, turnstile_token: 'e2e' },
  });
  expect(alta.status(), await alta.text()).toBe(202);

  await page.goto(await enlaceDeVerificacion(page.request, correo));
  await page.waitForURL('**/crear-organizacion');
  await page.getByLabel('Nombre de la organización').fill(`Móvil ${Date.now()}`);
  await page.getByLabel('Tu nombre').fill('Prueba');
  await page.getByLabel('Tus apellidos').fill('Móvil');
  await page.getByRole('button', { name: 'Crear organización' }).click();
  await page.waitForURL('**/dashboard**');
  await expect(page.getByText('No se pudieron cargar los datos de tu organización')).toHaveCount(0);
  return correo;
}

/** Un evento en borrador para poder recorrer sus pantallas. Devuelve su id. */
async function crearEvento(page: Page, correo: string): Promise<string> {
  const sesion = await page.request.post('/api/v1/auth/login', {
    data: { email: correo, password: PASSWORD },
  });
  const { access_token } = (await sesion.json()) as { access_token: string };
  const inicio = new Date(Date.now() + 30 * 86_400_000);
  const fin = new Date(inicio.getTime() + 8 * 3_600_000);
  const evento = await page.request.post('/api/v1/events', {
    headers: { Authorization: `Bearer ${access_token}` },
    data: {
      slug: `movil-${Date.now()}`,
      title: 'Jornada de prueba en móvil con un título bastante largo',
      starts_at: inicio.toISOString(),
      ends_at: fin.toISOString(),
      location_mode: 'in_person',
      location_name: 'Palacio de Congresos',
    },
  });
  expect(evento.status(), await evento.text()).toBe(201);
  return ((await evento.json()) as { id: string }).id;
}

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
    test.setTimeout(240_000);
    const correo = await altaDeOrganizador(page);
    const eventoId = await crearEvento(page, correo);

    for (const ruta of [...PANEL, ...DEL_EVENTO.map((s) => `/dashboard/events/${eventoId}${s}`)]) {
      await page.goto(ruta);
      await esperarSinDesborde(page, ruta);
    }
  });
});
