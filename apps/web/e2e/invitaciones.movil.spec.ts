import { expect, type APIRequestContext, type Page, test } from '@playwright/test';

import { esperarSinDesborde } from './desborde';

const MAILPIT = process.env['E2E_MAILPIT_URL'] ?? 'http://localhost:8025';
const PASSWORD = 'Movil-e2e-Pr0bando!';

/**
 * El camino de «invitar a un ponente», tal y como se rompió para los usuarios:
 * desde el móvil, con la vista pequeña. Las dos mitades del flujo viven en
 * navegadores distintos en la vida real (quien invita y quien acepta), pero el
 * flujo completo funciona igual en un solo contexto: la aceptación es pública
 * (`/invitacion?token=…`) y no depende de la sesión del organizador.
 */

/** Enlace `invitacion?token=…` del último correo enviado a `correo` (Mailpit). */
async function enlaceDeInvitacion(request: APIRequestContext, correo: string): Promise<string> {
  for (let intento = 0; intento < 30; intento++) {
    const busqueda = await request.get(`${MAILPIT}/api/v1/search`, {
      params: { query: `to:${correo}` },
    });
    const { messages } = (await busqueda.json()) as { messages: { ID: string }[] };
    if (messages.length > 0) {
      const mensaje = await request.get(`${MAILPIT}/api/v1/message/${messages[0]!.ID}`);
      const { Text } = (await mensaje.json()) as { Text: string };
      const enlace = Text.match(/https?:\/\/\S*invitacion\?token=[^\s]+/)?.[0];
      if (enlace) return new URL(enlace).pathname + new URL(enlace).search;
    }
    await new Promise((resolver) => setTimeout(resolver, 1000));
  }
  throw new Error(`No ha llegado a Mailpit la invitación para ${correo}`);
}

/** Organizador nuevo: registro, verificación del correo y organización creada. */
async function altaDeOrganizador(page: Page): Promise<string> {
  const correo = `movil-${Date.now()}@example.com`;
  const alta = await page.request.post('/api/v1/auth/register', {
    data: { email: correo, password: PASSWORD, turnstile_token: 'e2e' },
  });
  expect(alta.status(), await alta.text()).toBe(202);

  for (let intento = 0; intento < 30; intento++) {
    const busqueda = await page.request.get(`${MAILPIT}/api/v1/search`, {
      params: { query: `to:${correo}` },
    });
    const { messages } = (await busqueda.json()) as { messages: { ID: string }[] };
    if (messages.length > 0) {
      const mensaje = await page.request.get(`${MAILPIT}/api/v1/message/${messages[0]!.ID}`);
      const { Text } = (await mensaje.json()) as { Text: string };
      const enlace = Text.match(/https?:\/\/\S*verificar-correo\?token=[^\s]+/)?.[0];
      if (enlace) {
        await page.goto(enlace!);
        break;
      }
    }
    await new Promise((resolver) => setTimeout(resolver, 1000));
  }
  await page.waitForURL('**/crear-organizacion');
  await page.getByLabel('Nombre de la organización').fill(`Móvil ${Date.now()}`);
  await page.getByLabel('Tu nombre').fill('Prueba');
  await page.getByLabel('Tus apellidos').fill('Móvil');
  await page.getByRole('button', { name: 'Crear organización' }).click();
  await page.waitForURL('**/dashboard**');
  return correo;
}

/** Un evento en borrador. Devuelve su id. */
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
      title: 'Jornada de prueba de invitaciones',
      starts_at: inicio.toISOString(),
      ends_at: fin.toISOString(),
      location_mode: 'in_person',
      location_name: 'Palacio de Congresos',
    },
  });
  expect(evento.status(), await evento.text()).toBe(201);
  return ((await evento.json()) as { id: string }).id;
}

test.describe('Invitaciones a ponentes en el móvil', () => {
  test('invitar, aceptar y aparecer en el roster', async ({ page }) => {
    test.setTimeout(480_000);
    const correo = await altaDeOrganizador(page);
    const eventoId = await crearEvento(page, correo);
    const ponente = `ponente-${Date.now()}@example.com`;

    await page.goto(`/dashboard/events/${eventoId}/ponentes`);
    await expect(page.locator('main h1').first()).toBeVisible();

    await page.getByRole('button', { name: 'Invitar ponente' }).click();
    const correoCampo = page.getByLabel('Correo electrónico');
    await expect(correoCampo).toBeVisible();
    await correoCampo.fill(ponente);
    await page.getByRole('button', { name: 'Invitar como ponente' }).click();
    await expect(page.getByText('Invitación enviada')).toBeVisible();

    const ruta = await enlaceDeInvitacion(page.request, ponente);
    await page.goto(ruta);
    await esperarSinDesborde(page, ruta);
    await expect(page.getByText('Te han invitado a unirte')).toBeVisible();

    await page.locator('#invitacion-nombre').fill('Ponente');
    await page.locator('#invitacion-apellidos').fill('Prueba');
    await page.locator('#invitacion-password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Unirme al equipo' }).click();
    await expect(page.getByText('¡Ya formas parte del equipo!')).toBeVisible();

    await page.goto(`/dashboard/events/${eventoId}/ponentes`);
    await expect(page.getByText(ponente), 'el ponente aceptando aparece en el roster').toBeVisible();
  });

  test('la navegación se repliega al pulsar un enlace', async ({ page }) => {
    test.setTimeout(480_000);
    await altaDeOrganizador(page);

    const boton = page.getByRole('button', { name: 'Abrir navegación' });
    await expect(boton, 'el botón de navegación se ve en el móvil').toBeVisible();
    await boton.click();
    const panel = page.locator('#panel-navegacion-admin');
    await expect(panel).toHaveClass(/abierta/);

    // El pulgar pulsa la sección y sigue navegando: el panel debe repliegarse
    // solo, no quedar cubriendo la pantalla hasta cerrarlo a mano.
    await page.getByRole('link', { name: 'Escritorio' }).click();
    await expect(panel).not.toHaveClass(/abierta/);
  });

  test('el diálogo de alta de ponente cabe en una pantalla pequeña', async ({ page }) => {
    test.setTimeout(480_000);
    const correo = await altaDeOrganizador(page);
    const eventoId = await crearEvento(page, correo);

    // 640 px de alto: el caso típico de una mano en un móvil de gama media
    // (la altura del proyecto, 780, ya es generosa).
    await page.setViewportSize({ width: 360, height: 640 });
    await page.goto(`/dashboard/events/${eventoId}/ponentes`);
    await expect(page.locator('main h1').first()).toBeVisible();

    await page.getByRole('button', { name: 'Invitar ponente' }).click();
    const dialogo = page.locator('dialog[open]');
    await expect(dialogo, 'el diálogo se ha abierto').toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    // `boundingBox()` devuelve null para el `<dialog>` del top-layer; se mide
    // dentro de la página.
    const marco = await dialogo.evaluate((el) => {
      const r = el.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, width: r.width };
    });
    expect(marco.top, 'el diálogo no asoma por arriba').toBeGreaterThanOrEqual(0);
    expect(marco.bottom, 'el diálogo no asoma por abajo').toBeLessThanOrEqual(640);
    expect(marco.width, 'el diálogo no desborda el ancho').toBeLessThanOrEqual(360);
    // El botón de enviar debe quedar a pulgar: si no, el diálogo se corta y
    // quien invita no puede terminar.
    const enviar = page.getByRole('button', { name: 'Invitar como ponente' });
    await expect(enviar, 'el botón de enviar está a pulgar').toBeVisible();
    await expect(enviar).toBeInViewport();
  });
});
