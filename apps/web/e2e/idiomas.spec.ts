import { expect, test } from '@playwright/test';

/**
 * Web pública en otro idioma bajo su prefijo (`/en/…`), renderizada en el servidor.
 *
 * Necesita el SSR, no `ng serve`: lánzalo contra la build de producción
 * (`pnpm run serve:ssr:web`) con `E2E_BASE_URL`.
 */
const EVENTO = process.env['E2E_EVENTO'] ?? 'demo-multisede-tres';
const ORG = process.env['E2E_ORG'] ?? 'acme';

function atributo(html: string, patron: RegExp): string | null {
  return html.match(patron)?.[1] ?? null;
}

test.describe('Web pública en inglés', () => {
  test('la ficha de un evento se sirve en SSR en inglés y apunta al original', async ({
    request,
  }) => {
    const respuesta = await request.get(`/en/${ORG}/${EVENTO}`);
    expect(respuesta.status()).toBe(200);
    const html = await respuesta.text();
    expect(html).toContain('ng-server-context="ssr"');
    expect(atributo(html, /<html[^>]*\slang="([^"]+)"/)).toBe('en-US');
    // El contenido del organizador aún no está traducido: canonical al original
    // y ninguna alternativa anunciada.
    expect(atributo(html, /<link rel="canonical" href="([^"]+)"/)).toMatch(
      new RegExp(`[^/]/${ORG}/${EVENTO}$`),
    );
    expect(html).not.toContain('<link rel="alternate"');
    expect(html).toContain('content="en_US"');
  });

  test('las páginas de la plataforma anuncian sus dos idiomas', async ({ request }) => {
    const html = await (await request.get('/en/eventos')).text();
    expect(atributo(html, /<link rel="canonical" href="([^"]+)"/)).toMatch(/\/en\/eventos$/);
    expect(html).toMatch(/hreflang="es-ES" href="[^"]+\/eventos"/);
    expect(html).toMatch(/hreflang="en-US" href="[^"]+\/en\/eventos"/);
    expect(html).toMatch(/hreflang="x-default" href="[^"]+\/eventos"/);
  });

  test('una página inexistente bajo /en/ es un 404', async ({ request }) => {
    const respuesta = await request.get(`/en/${ORG}/${EVENTO}/no-existe/de-verdad`);
    expect(respuesta.status()).toBe(404);
  });

  test('las páginas de token bajo /en/ no se pintan en el servidor', async ({ request }) => {
    const html = await (await request.get('/en/verificar-correo?token=prueba')).text();
    expect(html).not.toContain('ng-server-context="ssr"');
  });

  test('la navegación interna conserva el prefijo', async ({ page }) => {
    await page.goto('/en/eventos');
    const enlace = page.locator(`a[href^="/en/"][href*="/${EVENTO}"]`).first();
    await expect(enlace).toBeVisible();
    await enlace.click();
    await expect(page).toHaveURL(new RegExp(`/en/[^/]+/${EVENTO}$`));
    await expect(page.locator('html')).toHaveAttribute('lang', 'en-US');
  });

  test('el selector de idioma lleva a la misma página en el otro idioma', async ({ page }) => {
    await page.goto(`/en/${ORG}/${EVENTO}`);
    // El banner de cookies tapa el pie: se rechazan (primer botón del banner).
    await page.locator('app-cookie-banner button').first().click();
    const espanol = page.locator('footer a[hreflang="es-ES"]');
    await expect(espanol).toHaveAttribute('href', `/${ORG}/${EVENTO}`);
    await espanol.click();
    await expect(page).toHaveURL(new RegExp(`/${ORG}/${EVENTO}$`));
    await expect(page.locator('html')).toHaveAttribute('lang', 'es-ES');
  });
});
