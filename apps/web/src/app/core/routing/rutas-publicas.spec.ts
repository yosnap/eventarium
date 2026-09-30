import { type Route, type UrlMatcher, UrlSegment, type UrlSegmentGroup } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { apiEvento, coincideConEvento, rutaEvento, slugValido, urlEvento } from './rutas-publicas';

const aplicar = (matcher: UrlMatcher, ...partes: string[]) =>
  matcher(
    partes.map((p) => new UrlSegment(p, {})),
    {} as UrlSegmentGroup,
    {} as Route,
  );

describe('rutas-publicas', () => {
  it('construye la ruta de Angular, la URL y la ruta del API de un evento', () => {
    expect(rutaEvento('acme', 'iawic', 'programa')).toEqual(['/', 'acme', 'iawic', 'programa']);
    expect(urlEvento('acme', 'iawic')).toBe('/acme/iawic');
    expect(urlEvento('acme', 'iawic', 'sesiones', 3)).toBe('/acme/iawic/sesiones/3');
    expect(apiEvento('acme', 'iawic', '/policies')).toBe(
      '/public/organizations/acme/events/iawic/policies',
    );
  });

  it('slugValido devuelve el valor solo si es un slug', () => {
    expect(slugValido('acme')).toBe('acme');
    expect(slugValido(null)).toBeNull();
    expect(slugValido('../../admin')).toBeNull();
    expect(slugValido('Acme')).toBeNull();
    expect(slugValido('')).toBeNull();
  });

  it('el matcher toma organización y evento, y los parámetros del resto', () => {
    const resultado = aplicar(
      coincideConEvento('sesiones/:sessionId'),
      'acme',
      'iawic',
      'sesiones',
      'abc',
    );
    expect(resultado?.posParams?.['org'].path).toBe('acme');
    expect(resultado?.posParams?.['slug'].path).toBe('iawic');
    expect(resultado?.posParams?.['sessionId'].path).toBe('abc');
  });

  it('el matcher exige el número de segmentos y el literal esperado', () => {
    const ficha = coincideConEvento();
    expect(aplicar(ficha, 'acme', 'iawic')).not.toBeNull();
    expect(aplicar(ficha, 'acme')).toBeNull();
    expect(aplicar(ficha, 'acme', 'iawic', 'programa')).toBeNull();
    expect(aplicar(coincideConEvento('programa'), 'acme', 'iawic', 'otra')).toBeNull();
  });

  it('el matcher ignora los parámetros matriz: no pueden sustituir a la organización', () => {
    const conMatriz = [new UrlSegment('acme', {}), new UrlSegment('iawic', { org: '../../mcp' })];
    const resultado = coincideConEvento()(conMatriz, {} as UrlSegmentGroup, {} as Route);
    expect(resultado?.consumed.every((s) => Object.keys(s.parameters).length === 0)).toBe(true);
    expect(resultado?.posParams?.['org'].parameters).toEqual({});
  });

  it('el matcher rechaza lo que no es un slug (extensiones, puntos, mayúsculas)', () => {
    const ficha = coincideConEvento();
    expect(aplicar(ficha, 'foo.php', 'x')).toBeNull();
    expect(aplicar(ficha, '.env', 'x')).toBeNull();
    expect(aplicar(ficha, 'acme', 'index.html')).toBeNull();
    expect(aplicar(ficha, 'Acme', 'x')).toBeNull();
  });
});
