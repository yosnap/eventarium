import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  type ActivatedRouteSnapshot,
  type RouterStateSnapshot,
  UrlTree,
  provideRouter,
  Router,
} from '@angular/router';
import { describe, expect, it } from 'vitest';

import { NotFoundStatusService } from '../../../core/ssr/not-found-status.service';
import { coincideConEnlaceAntiguo, enlaceAntiguo } from './enlace-antiguo';

function ejecutar(url: string, slug: string) {
  const ruta = { paramMap: { get: () => slug } } as unknown as ActivatedRouteSnapshot;
  const estado = { url } as RouterStateSnapshot;
  return TestBed.runInInjectionContext(() => enlaceAntiguo(ruta, estado));
}

describe('enlaceAntiguo', () => {
  function preparar() {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    return TestBed.inject(HttpTestingController);
  }

  it('redirige a la URL nueva conservando el resto de la ruta, la query y el fragmento', async () => {
    const http = preparar();
    const resultado = ejecutar('/eventos/iawic/programa?dia=2#agenda', 'iawic');
    http
      .expectOne('/api/v1/public/events/iawic/canonical')
      .flush({ organization_slug: 'acme', slug: 'iawic-2026' });

    const destino = await resultado;
    expect(destino).toBeInstanceOf(UrlTree);
    expect(TestBed.inject(Router).serializeUrl(destino as UrlTree)).toBe(
      '/acme/iawic-2026/programa?dia=2#agenda',
    );
  });

  it('si el evento ya no es público deja pasar a la página 404', async () => {
    const http = preparar();
    const resultado = ejecutar('/eventos/oculto', 'oculto');
    http
      .expectOne('/api/v1/public/events/oculto/canonical')
      .flush({ detail: 'x' }, { status: 404, statusText: 'Not Found' });

    expect(await resultado).toBe(true);
    expect(TestBed.inject(NotFoundStatusService).falloTemporal()).toBe(false);
  });

  it.each([429, 500, 0])(
    'un %s del API no se presenta como 404: marca fallo temporal',
    async (status) => {
      const http = preparar();
      const resultado = ejecutar('/eventos/valido', 'valido');
      http
        .expectOne('/api/v1/public/events/valido/canonical')
        .flush({ detail: 'x' }, { status: status || 500, statusText: 'Error' });

      expect(await resultado).toBe(true);
      expect(TestBed.inject(NotFoundStatusService).falloTemporal()).toBe(true);
    },
  );

  it('un slug con caracteres raros no llega al API', async () => {
    const http = preparar();
    expect(await ejecutar('/eventos/..%2F..%2Fadmin', '../../admin')).toBe(true);
    http.expectNone(() => true);
  });

  it('el resto se calcula sobre la URL codificada tal como llegó', async () => {
    const http = preparar();
    const resultado = ejecutar('/eventos/iawic/sesiones/a%20b', 'iawic');
    http
      .expectOne('/api/v1/public/events/iawic/canonical')
      .flush({ organization_slug: 'acme', slug: 'iawic' });

    const destino = await resultado;
    expect(TestBed.inject(Router).serializeUrl(destino as UrlTree)).toBe(
      '/acme/iawic/sesiones/a%20b',
    );
  });
});

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
