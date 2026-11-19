import {
  EnvironmentInjector,
  provideZonelessChangeDetection,
  runInInjectionContext,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, UrlSegment, provideRouter, type RedirectFunction } from '@angular/router';
import { RenderMode } from '@angular/ssr';
import { describe, expect, it } from 'vitest';

import { routes } from './app.routes';
import { PAGINAS_PUBLICAS_SOLO_DE_CLIENTE, serverRoutes } from './app.routes.server';
import { IDIOMAS, PREFIJO_DE_IDIOMA } from './core/i18n/idioma';
import { rutaDeServidor, rutaEn } from './core/i18n/rutas-traducidas';

const PREFIJOS = IDIOMAS.map((idioma) => PREFIJO_DE_IDIOMA[idioma]).filter(Boolean);

/** `en` + `acceder` → `en/login`. */
function conRutaTraducida(prefijo: string, pagina: string): string {
  const idioma = IDIOMAS.find((i) => PREFIJO_DE_IDIOMA[i] === prefijo)!;
  return `${prefijo}/${rutaDeServidor(idioma, pagina)}`;
}

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
      // Las mismas páginas, con su ruta traducida al idioma del prefijo.
      const idioma = IDIOMAS.find((i) => PREFIJO_DE_IDIOMA[i] === prefijo)!;
      const traducir = (ruta: string) =>
        ruta.startsWith('shell:')
          ? `shell:${rutaEn(idioma, ruta.slice('shell:'.length))}`
          : rutaEn(idioma, ruta);
      expect(conPrefijo).toEqual(expect.arrayContaining(raiz.map(traducir)));
      // Mismo shell, mismas rutas y en el mismo orden (los matchers no tienen nombre).
      const shellRaiz = routes.find((r) => r.path === '' && r.children)?.children ?? [];
      const shellPrefijo =
        routes.find((r) => r.path === prefijo)?.children?.find((r) => r.path === '' && r.children)
          ?.children ?? [];
      expect(shellPrefijo.map((r) => (r.path === undefined ? 'matcher' : 'ruta'))).toEqual(
        shellRaiz.map((r) => (r.path === undefined ? 'matcher' : 'ruta')),
      );
      expect(conPrefijo).not.toContain('dashboard');
    }
  });

  it('las páginas de token y de sesión son solo de cliente con cualquier prefijo', () => {
    const indiceComodin = serverRoutes.findIndex((r) => r.path === '**');
    for (const pagina of PAGINAS_PUBLICAS_SOLO_DE_CLIENTE) {
      for (const ruta of [pagina, ...PREFIJOS.map((p) => conRutaTraducida(p, pagina))]) {
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
      for (const ruta of [pagina, ...PREFIJOS.map((p) => conRutaTraducida(p, pagina))]) {
        expect(serverRoutes.find((r) => r.path === ruta)?.renderMode, ruta).toBe(RenderMode.Client);
      }
    }
  });

  it('con el idioma desactivado, su prefijo lleva a la misma página en español con su consulta', () => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
    const respaldo = routes.filter((r) => r.path === 'en')[1];
    // Va justo detrás de la ruta con `canMatch`: solo se alcanza si esta no encaja.
    expect(routes.indexOf(respaldo)).toBe(routes.findIndex((r) => r.path === 'en') + 1);
    const redirigir = respaldo.children?.[0].redirectTo as RedirectFunction;
    const url = ['my-ticket'].map((p) => new UrlSegment(p, {}));
    const destino = runInInjectionContext(TestBed.inject(EnvironmentInjector), () =>
      redirigir({ url, queryParams: { token: 'abc' }, fragment: 'qr' } as never),
    );
    expect(TestBed.inject(Router).serializeUrl(destino as never)).toBe('/mi-entrada?token=abc#qr');
    TestBed.resetTestingModule();
  });
});
