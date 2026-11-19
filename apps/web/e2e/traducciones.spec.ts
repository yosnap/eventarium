import { expect, test } from '@playwright/test';

import { altaDeOrganizador, crearEvento, tokenDeApi } from './alta-organizador';

/**
 * El organizador activa el inglés, escribe el título en inglés desde la
 * pestaña de idioma del formulario del evento y la ficha pública en `/en/` lo
 * muestra, con `canonical` propio y `hreflang` en los dos idiomas.
 */
test('el organizador traduce el evento y /en/ lo muestra', async ({ page }) => {
  const correo = await altaDeOrganizador(page);
  const eventId = await crearEvento(page, correo);

  const autorizacion = { Authorization: `Bearer ${await tokenDeApi(page, correo)}` };
  const organizacion = await page.request.patch('/api/v1/organizations/me', {
    headers: autorizacion,
    data: { content_locales: ['es-ES', 'en-US'] },
  });
  expect(organizacion.status(), await organizacion.text()).toBe(200);
  const { slug: org } = (await organizacion.json()) as { slug: string };
  const publicado = await page.request.patch(`/api/v1/events/${eventId}`, {
    headers: autorizacion,
    data: { status: 'published', visibility: 'public' },
  });
  expect(publicado.status(), await publicado.text()).toBe(200);
  const { slug } = (await publicado.json()) as { slug: string };

  await page.goto(`/dashboard/events/${eventId}/editar`);
  await page.getByRole('tab', { name: 'English' }).click();
  const editor = page.locator('app-editor-de-traducciones');
  await editor.getByLabel('Título', { exact: true }).fill('A test day');
  // Con un campo sin traducir la página aún no cuenta como «al día» en inglés.
  await editor.getByLabel('Nombre del lugar', { exact: true }).fill('Conference Centre');
  await page.getByRole('button', { name: 'Guardar traducciones' }).click();
  await expect(editor.getByText('Al día')).toHaveCount(2);

  await page.goto(`/en/${org}/${slug}`);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('A test day');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    new RegExp(`/en/${org}/${slug}$`),
  );
  await expect(page.locator('link[rel="alternate"][hreflang="es-ES"]')).toHaveCount(1);

  // «Solo con enlace» al terminar: no ocupa los listados de la base de desarrollo.
  await page.request.patch(`/api/v1/events/${eventId}`, {
    headers: autorizacion,
    data: { visibility: 'hidden' },
  });
});
