import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import es from '../../../../../../public/assets/i18n/es-ES.json';
import { GsapLoader } from '../gsap';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../../testing/axe';
import { EnDirectoService, estaEnDirecto, type EventoEnDirecto } from '../en-directo.service';
import { LandingEnDirecto } from './en-directo';

const HORA = 60 * 60 * 1000;

function evento(slug: string, desdeMs: number, hastaMs: number): EventoEnDirecto {
  const ahora = Date.now();
  return {
    slug,
    title: `Evento ${slug}`,
    cover_url: null,
    starts_at: new Date(ahora + desdeMs).toISOString(),
    ends_at: new Date(ahora + hastaMs).toISOString(),
    location_mode: 'online',
    location_name: null,
    city: 'Valencia',
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('estaEnDirecto', () => {
  it('solo es cierto cuando la ventana cubre el instante', () => {
    const ahora = Date.now();
    expect(estaEnDirecto(evento('a', -HORA, HORA), ahora)).toBe(true);
    expect(estaEnDirecto(evento('b', HORA, 2 * HORA), ahora)).toBe(false);
    expect(estaEnDirecto(evento('c', -3 * HORA, -HORA), ahora)).toBe(false);
  });
});

describe('LandingEnDirecto', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        // GSAP no se carga en jsdom (matchMedia no existe): la animación no es
        // objeto de estos specs.
        { provide: GsapLoader, useValue: { cargar: () => Promise.resolve(null) } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('muestra solo los eventos cuya ventana cubre el instante actual', async () => {
    const fixture = TestBed.createComponent(LandingEnDirecto);
    fixture.detectChanges();
    http
      .expectOne((p) => p.url === '/api/v1/public/events')
      .flush([
        evento('en-curso', -HORA, HORA),
        evento('futuro', HORA, 2 * HORA),
        evento('pasado', -3 * HORA, -HORA),
      ]);
    await avanzar(fixture);

    const enlaces = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('a.landing-directo-tarjeta'),
    );
    expect(enlaces.map((a) => a.getAttribute('href'))).toEqual(['/eventos/en-curso']);
    expect(fixture.nativeElement.textContent).toContain(es.publico.eventos.formato.online);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('con la lista vacía muestra el estado vacío con enlace al directorio', async () => {
    const fixture = TestBed.createComponent(LandingEnDirecto);
    fixture.detectChanges();
    http.expectOne((p) => p.url === '/api/v1/public/events').flush([]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain(es.publico.landing.enDirecto.vacio);
    expect(fixture.nativeElement.querySelector('.landing-vacio a')?.getAttribute('href')).toBe(
      '/eventos',
    );
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('refrescar() incorpora un evento que empieza después de cargar la página', async () => {
    const fixture = TestBed.createComponent(LandingEnDirecto);
    fixture.detectChanges();
    http
      .expectOne((p) => p.url === '/api/v1/public/events')
      .flush([evento('inminente', 500, HORA)]);
    await avanzar(fixture);
    const servicio = TestBed.inject(EnDirectoService);
    expect(servicio.eventos()).toHaveLength(0);

    vi.useFakeTimers({ now: Date.now() + 1000 });
    try {
      servicio.refrescar();
      expect(servicio.eventos().map((e) => e.slug)).toEqual(['inminente']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('un 429 del limitador deja la franja vacía sin error sin capturar', async () => {
    const fixture = TestBed.createComponent(LandingEnDirecto);
    fixture.detectChanges();
    http
      .expectOne((p) => p.url === '/api/v1/public/events')
      .flush({ detail: 'demasiadas peticiones' }, { status: 429, statusText: 'Too Many Requests' });
    await avanzar(fixture);

    expect(TestBed.inject(EnDirectoService).eventos()).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain(es.publico.landing.enDirecto.vacio);
  });
});
