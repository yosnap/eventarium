import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventsListPage } from './events-list-page';

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventsListPage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    document.documentElement.removeAttribute('data-theme');
  });

  it('lista los eventos en tema claro sin violaciones de accesibilidad', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events')
      .flush([
        {
          slug: 'iawic-2026',
          title: 'IA Week in Cascais 2026',
          summary: 'El evento del año.',
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-10-01T09:00:00Z',
          ends_at: '2026-10-03T18:00:00Z',
          location_mode: 'in_person',
          location_name: 'Sala principal',
          city: 'Lisboa',
          registration_mode: 'free',
          capacity: null,
          reserved_count: 0,
        },
      ]);
    await avanzar(fixture);

    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('lista los eventos publicados sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events')
      .flush([
        {
          slug: 'iawic-2026',
          title: 'IA Week in Cascais 2026',
          summary: 'El evento del año.',
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-10-01T09:00:00Z',
          ends_at: '2026-10-03T18:00:00Z',
          location_mode: 'in_person',
          location_name: 'Sala principal',
          city: 'Lisboa',
          registration_mode: 'free',
          capacity: null,
          reserved_count: 0,
        },
      ]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('IA Week in Cascais 2026');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra el mensaje de "sin eventos" cuando el listado está vacío', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http.expectOne((peticion) => peticion.url === '/api/v1/public/events').flush([]);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Todavía no hay eventos publicados');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el buscador filtra por título en el cliente, sin llamar a la API de nuevo', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events')
      .flush([
        {
          slug: 'iawic-2026',
          title: 'IA Week in Cascais 2026',
          summary: 'El evento del año.',
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-10-01T09:00:00Z',
          ends_at: '2026-10-03T18:00:00Z',
          location_mode: 'in_person',
          location_name: 'Sala principal',
          city: 'Lisboa',
          registration_mode: 'free',
          capacity: null,
          reserved_count: 0,
        },
        {
          slug: 'meetup-comunidad',
          title: 'Meetup de la comunidad',
          summary: null,
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-11-05T18:00:00Z',
          ends_at: '2026-11-05T20:00:00Z',
          location_mode: 'online',
          location_name: null,
          city: 'Valencia',
          registration_mode: 'approval',
          capacity: 50,
          reserved_count: 50,
        },
      ]);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    expect(raiz.textContent).toContain('IA Week in Cascais 2026');
    expect(raiz.textContent).toContain('Meetup de la comunidad');
    // Sin `capacity` (null) el evento marca "sin límite"; con las plazas ya
    // consumidas del todo (capacity === reserved_count) marca "Completo".
    expect(raiz.textContent).toContain('Sin límite');
    expect(raiz.textContent).toContain('Completo');

    const buscador = raiz.querySelector('input[type="search"]') as HTMLInputElement;
    buscador.value = 'cascais';
    buscador.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    expect(raiz.textContent).toContain('IA Week in Cascais 2026');
    expect(raiz.textContent).not.toContain('Meetup de la comunidad');
  });

  it('el filtro por formato solo muestra los eventos de esa modalidad', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events')
      .flush([
        {
          slug: 'iawic-2026',
          title: 'IA Week in Cascais 2026',
          summary: null,
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-10-01T09:00:00Z',
          ends_at: '2026-10-03T18:00:00Z',
          location_mode: 'in_person',
          location_name: 'Sala principal',
          city: 'Lisboa',
          registration_mode: 'free',
          capacity: null,
          reserved_count: 0,
        },
        {
          slug: 'meetup-comunidad',
          title: 'Meetup de la comunidad',
          summary: null,
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-11-05T18:00:00Z',
          ends_at: '2026-11-05T20:00:00Z',
          location_mode: 'online',
          location_name: null,
          city: 'Valencia',
          registration_mode: 'approval',
          capacity: 50,
          reserved_count: 50,
        },
      ]);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const tagOnline = Array.from(raiz.querySelectorAll('.tag')).find(
      (b) => b.textContent?.trim() === 'Online',
    ) as HTMLButtonElement;
    tagOnline.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Meetup de la comunidad');
    expect(raiz.textContent).not.toContain('IA Week in Cascais 2026');
    expect(tagOnline.getAttribute('aria-pressed')).toBe('true');
  });

  it('el select de ciudad solo muestra los eventos de la ciudad elegida', async () => {
    const fixture = TestBed.createComponent(EventsListPage);
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events')
      .flush([
        {
          slug: 'iawic-2026',
          title: 'IA Week in Cascais 2026',
          summary: null,
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-10-01T09:00:00Z',
          ends_at: '2026-10-03T18:00:00Z',
          location_mode: 'in_person',
          location_name: 'Sala principal',
          city: 'Lisboa',
          registration_mode: 'free',
          capacity: null,
          reserved_count: 0,
        },
        {
          slug: 'meetup-comunidad',
          title: 'Meetup de la comunidad',
          summary: null,
          cover_url: null,
          timezone: 'Europe/Madrid',
          starts_at: '2026-11-05T18:00:00Z',
          ends_at: '2026-11-05T20:00:00Z',
          location_mode: 'online',
          location_name: null,
          city: 'Valencia',
          registration_mode: 'approval',
          capacity: 50,
          reserved_count: 50,
        },
      ]);
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    const botonCiudad = raiz.querySelector('#ciudad') as HTMLButtonElement;
    expect(botonCiudad).not.toBeNull();

    botonCiudad.click();
    await avanzar(fixture);
    const opcionValencia = Array.from(raiz.querySelectorAll('[role="option"]')).find(
      (opcion) => opcion.textContent?.trim() === 'Valencia',
    ) as HTMLLIElement;
    expect(opcionValencia).toBeDefined();
    opcionValencia.click();
    await avanzar(fixture);

    expect(raiz.textContent).toContain('Meetup de la comunidad');
    expect(raiz.textContent).not.toContain('IA Week in Cascais 2026');
  });
});
