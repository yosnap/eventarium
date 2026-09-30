import { type Route, UrlSegment, type UrlSegmentGroup } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { routes } from './app.routes';
import { coincideConOrganizacion } from './core/routing/rutas-publicas';

/**
 * Resuelve una URL contra el árbol público como lo haría el router: primer
 * hijo cuyo `path` o `matcher` la reconozca. No carga componentes.
 */
function ruta(url: string): Route | undefined {
  const segmentos = url
    .split('/')
    .filter(Boolean)
    .map((parte) => new UrlSegment(parte, {}));
  const publico = routes.find((r) => r.path === '' && r.children && !r.canActivate);
  return publico?.children?.find((hija) => {
    if (hija.matcher) {
      return hija.matcher(segmentos, {} as UrlSegmentGroup, hija) !== null;
    }
    const patron = (hija.path ?? '').split('/').filter(Boolean);
    if (hija.path === '**') {
      return true;
    }
    if (hija.path === '' && hija.pathMatch === 'full') {
      return segmentos.length === 0;
    }
    return (
      patron.length === segmentos.length &&
      patron.every((p, i) => p.startsWith(':') || p === segmentos[i].path)
    );
  });
}

const esComodin = (r: Route | undefined) => r?.path === '**';
const esEnlaceAntiguo = (r: Route | undefined) => !!r?.matcher && r.redirectTo === '/';
const esEventoDeOrganizacion = (r: Route | undefined) =>
  !!r?.matcher && !r.redirectTo && r.matcher !== coincideConOrganizacion;
const esPaginaDeOrganizacion = (r: Route | undefined) => r?.matcher === coincideConOrganizacion;

describe('rutas públicas', () => {
  it.each([
    'legal/privacidad',
    'legal/aviso-legal',
    'mis-eventos/ver',
    'pago/retorno',
    'pago/cancelado',
    'ponentes/ana',
  ])('la ruta estática %s se resuelve antes que :org/:evento', (url) => {
    const r = ruta(url);
    expect(r?.matcher).toBeUndefined();
    expect(esComodin(r)).toBe(false);
  });

  it('el directorio /eventos sigue siendo el listado', () => {
    expect(ruta('eventos')?.path).toBe('eventos');
  });

  it.each(['eventos/iawic', 'eventos/iawic/programa', 'eventos/iawic/sesiones/s1'])(
    'el enlace antiguo %s se redirige a la portada',
    (url) => {
      expect(esEnlaceAntiguo(ruta(url))).toBe(true);
    },
  );

  it.each([
    'acme/iawic',
    'acme/iawic/programa',
    'acme/iawic/inscribirse',
    'acme/iawic/politicas',
    'acme/iawic/sesiones/s1',
    'acme/iawic/patrocinadores/p1',
  ])('/%s es una página de evento de organización', (url) => {
    expect(esEventoDeOrganizacion(ruta(url))).toBe(true);
  });

  it.each(['acme', 'mi-organizacion'])('/%s es la página pública de una organización', (url) => {
    expect(esPaginaDeOrganizacion(ruta(url))).toBe(true);
  });

  it('/eventos sigue siendo el directorio, no una organización llamada «eventos»', () => {
    expect(esPaginaDeOrganizacion(ruta('eventos'))).toBe(false);
    expect(ruta('eventos')?.path).toBe('eventos');
  });

  it.each(['foo.php', '.env', 'acme/index.html', 'wp-admin/setup.php', 'Acme/Iawic', 'a/b/c/d/e'])(
    '/%s no es una página de evento: cae en el 404',
    (url) => {
      expect(esComodin(ruta(url))).toBe(true);
    },
  );

  it('el comodín ya no redirige a la portada: sirve la página 404', () => {
    const comodin = ruta('no-existe.php');
    expect(comodin?.redirectTo).toBeUndefined();
    expect(comodin?.loadComponent).toBeDefined();
  });
});
