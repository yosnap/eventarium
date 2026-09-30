import { TestBed } from '@angular/core/testing';
import { provideRouter, Router, UrlTree, type ActivatedRouteSnapshot } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { coincideConEnlaceAntiguo, enlaceAntiguoALaPortada } from './enlace-antiguo';

describe('coincideConEnlaceAntiguo', () => {
  it('reconoce /eventos/:slug y su cola, no el directorio /eventos', () => {
    const segmento = (path: string) => ({ path, parameters: {} }) as never;
    expect(coincideConEnlaceAntiguo([segmento('eventos')])).toBeNull();
    expect(coincideConEnlaceAntiguo([segmento('eventos'), segmento('x')])).not.toBeNull();
    expect(
      coincideConEnlaceAntiguo([segmento('eventos'), segmento('x'), segmento('programa')]),
    ).not.toBeNull();
    expect(coincideConEnlaceAntiguo([segmento('otra'), segmento('x')])).toBeNull();
    expect(coincideConEnlaceAntiguo([segmento('eventos'), segmento('../x')])).toBeNull();
  });
});

describe('enlaceAntiguoALaPortada', () => {
  it('devuelve un UrlTree a la portada (redirección real en SSR)', () => {
    TestBed.configureTestingModule({ providers: [provideRouter([])] });
    const resultado = TestBed.runInInjectionContext(() =>
      enlaceAntiguoALaPortada({} as ActivatedRouteSnapshot, { url: '/eventos/x' } as never),
    );
    expect(resultado).toBeInstanceOf(UrlTree);
    expect(TestBed.inject(Router).serializeUrl(resultado as UrlTree)).toBe('/');
  });
});
