import { RenderMode } from '@angular/ssr';
import { describe, expect, it } from 'vitest';

import { routes } from './app.routes';
import { PAGINAS_PUBLICAS_SOLO_DE_CLIENTE, serverRoutes } from './app.routes.server';
import { IDIOMAS, PREFIJO_DE_IDIOMA } from './core/i18n/idioma';

const PREFIJOS = IDIOMAS.map((idioma) => PREFIJO_DE_IDIOMA[idioma]).filter(Boolean);

/** Rutas de primer nivel con `path` literal (las de acceso) y las del shell público. */
function rutasPublicas(hijas: typeof routes): string[] {
  const shell = hijas.find((r) => r.path === '' && r.children);
  const deAcceso = hijas.filter((r) => r.loadComponent && r.path).map((r) => r.path as string);
  const delShell = (shell?.children ?? []).map((r) => r.path ?? `matcher:${r.matcher?.name}`);
  return [...deAcceso, ...delShell.map((p) => `shell:${p}`)];
}

describe('rutas con prefijo de idioma', () => {
  it('hay un prefijo por cada idioma que no es el de por defecto', () => {
    expect(PREFIJOS).toEqual(['en']);
    for (const prefijo of PREFIJOS) {
      expect(routes.findIndex((r) => r.path === prefijo)).toBe(0);
    }
  });

  it('bajo el prefijo están todas las páginas públicas y de acceso de la raíz', () => {
    // Los paneles y lo que depende de la sesión del panel no llevan prefijo.
    const raiz = rutasPublicas(routes).filter(
      (r) =>
        !['oauth/consentimiento', 'espacio-de-trabajo'].includes(r) &&
        !/^(admin|dashboard)\b/.test(r),
    );
    for (const prefijo of PREFIJOS) {
      const conPrefijo = rutasPublicas(routes.find((r) => r.path === prefijo)?.children ?? []);
      expect(conPrefijo).toEqual(expect.arrayContaining(raiz));
      // Mismo shell, mismas rutas y en el mismo orden (los matchers no tienen nombre).
      const shellRaiz = routes.find((r) => r.path === '' && r.children)?.children ?? [];
      const shellPrefijo =
        routes.find((r) => r.path === prefijo)?.children?.find((r) => r.path === '' && r.children)
          ?.children ?? [];
      expect(shellPrefijo.map((r) => r.path ?? r.matcher?.toString())).toEqual(
        shellRaiz.map((r) => r.path ?? r.matcher?.toString()),
      );
      expect(conPrefijo).not.toContain('dashboard');
    }
  });

  it('las páginas de token y de sesión son solo de cliente con cualquier prefijo', () => {
    const indiceComodin = serverRoutes.findIndex((r) => r.path === '**');
    for (const pagina of PAGINAS_PUBLICAS_SOLO_DE_CLIENTE) {
      for (const ruta of [pagina, ...PREFIJOS.map((p) => `${p}/${pagina}`)]) {
        const indice = serverRoutes.findIndex((r) => r.path === ruta);
        expect(indice, ruta).toBeGreaterThanOrEqual(0);
        expect(indice, ruta).toBeLessThan(indiceComodin);
        expect(serverRoutes[indice].renderMode, ruta).toBe(RenderMode.Client);
      }
    }
    // Lista escrita a mano a propósito: si alguien quita una página de la lista
    // compartida, este test lo detecta en vez de recorrer la misma lista.
    for (const pagina of [
      'acceder',
      'mis-eventos',
      'vista-previa/**',
      'verificar-correo',
      'recuperar-contrasena/nueva',
      'cuenta/confirmar-correo',
      'mis-eventos/ver',
    ]) {
      for (const ruta of [pagina, ...PREFIJOS.map((p) => `${p}/${pagina}`)]) {
        expect(serverRoutes.find((r) => r.path === ruta)?.renderMode, ruta).toBe(RenderMode.Client);
      }
    }
  });
});
