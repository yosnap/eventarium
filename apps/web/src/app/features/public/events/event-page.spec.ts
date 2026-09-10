import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TransferState, makeStateKey, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventPage } from './event-page';
import type { PublicEventDetail } from './event-page.types';

function eventoDetalle() {
  return {
    slug: 'iawic-2026',
    title: 'IA Week in Cascais 2026',
    summary: 'El evento del año.',
    description: 'Descripción larga del evento.',
    cover_url: null,
    timezone: 'Europe/Madrid',
    starts_at: '2026-10-01T09:00:00Z',
    ends_at: '2026-10-02T18:00:00Z',
    location_mode: 'in_person',
    location_name: 'Sala principal',
    location_address: null,
    online_url: null,
    capacity: null,
    registration_mode: 'free',
    reserved_count: 0,
    latitude: null,
    longitude: null,
    sessions: [
      {
        id: 's1',
        session_type: 'talk',
        title: 'Charla de apertura',
        description: null,
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-01T10:00:00Z',
        room: 'Sala A',
        venue_id: null,
        video_platform: null,
        video_url: null,
        materials: [],
        participants: [{ display_name: 'Ana Ponente', role_key: 'speaker', public_slug: 'ana' }],
      },
    ],
    venues: [],
    sponsor_tiers: [],
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventPage', () => {
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

  it('deja de mostrar «cargando» cuando el dato llega por TransferState (hidratación), sin llamar a la API', async () => {
    // Regresión: hasta corregirlo, la rama de `TransferState` no ponía
    // `cargando` a `false`, así que tras una carga completa de página (la
    // hidratación SSR real, no la navegación SPA que sí dispara la petición
    // HTTP) la ficha se quedaba en «Cargando…» para siempre aunque el dato ya
    // estuviera disponible.
    const clave = makeStateKey<PublicEventDetail>('public-event:iawic-2026');
    const transferState = TestBed.inject(TransferState);
    transferState.set(clave, eventoDetalle() as PublicEventDetail);

    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.detectChanges();
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.url === '/api/v1/public/events/iawic-2026');
    expect(fixture.nativeElement.textContent).toContain('IA Week in Cascais 2026');
    expect(fixture.nativeElement.textContent).not.toContain('Cargando');
  });

  it('muestra el evento en tema claro sin violaciones de accesibilidad', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026')
      .flush(eventoDetalle());
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('IA Week in Cascais 2026');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra el evento, su agenda y participantes, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    // `ngOnInit` registra la carga como `PendingTasks`: `whenStable()` esperaría a
    // que termine, así que hay que disparar `ngOnInit` (con `detectChanges()`, sin
    // esperar estabilidad todavía) antes de responder la petición simulada.
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026')
      .flush(eventoDetalle());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('IA Week in Cascais 2026');
    expect(texto).toContain('Charla de apertura');
    expect(texto).toContain('Ana Ponente');
    expect(texto).toContain('Descripción larga del evento.');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('agrupa los patrocinadores por nivel, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026')
      .flush({
        ...eventoDetalle(),
        sponsor_tiers: [
          {
            name: 'Oro',
            logo_size: 'large',
            sponsors: [{ name: 'Acme Corp', logo_url: null, website: 'https://acme.example' }],
          },
          {
            name: 'Colaboradores',
            logo_size: 'small',
            sponsors: [{ name: 'Espacio Cedido', logo_url: null, website: null }],
          },
        ],
      });
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Oro');
    expect(texto).toContain('Acme Corp');
    expect(texto).toContain('Colaboradores');
    expect(texto).toContain('Espacio Cedido');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra el aforo, el chip de inscripción y los ponentes derivados de la agenda', async () => {
    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026')
      .flush({ ...eventoDetalle(), capacity: 120, registration_mode: 'approval' });
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Aforo · 120');
    expect(texto).toContain('confirmadas');
    expect(texto).toContain('disponibles');
    expect(texto).toContain('Inscripción con aprobación');
    expect(texto).toContain('Ponente');
    expect(texto).not.toContain('speaker');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('cambia de día de agenda con las flechas del teclado en las pestañas', async () => {
    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026')
      .flush({
        ...eventoDetalle(),
        sessions: [
          ...eventoDetalle().sessions,
          {
            id: 's2',
            session_type: 'break',
            title: 'Pausa del segundo día',
            description: null,
            starts_at: '2026-10-02T09:00:00Z',
            ends_at: '2026-10-02T09:30:00Z',
            room: null,
            video_platform: null,
            video_url: null,
            materials: [],
            participants: [],
          },
        ],
      });
    await avanzar(fixture);

    const pestanas = fixture.nativeElement.querySelectorAll('[role="tab"]');
    const paneles = fixture.nativeElement.querySelectorAll('[role="tabpanel"]');
    expect(pestanas.length).toBe(2);
    expect(paneles[1].hasAttribute('hidden')).toBe(true);

    pestanas[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    await avanzar(fixture);

    expect(pestanas[1].getAttribute('aria-selected')).toBe('true');
    expect(paneles[1].hasAttribute('hidden')).toBe(false);
    expect(paneles[1].textContent).toContain('Pausa del segundo día');
    expect(paneles[1].textContent).toContain('Descanso');
    expect(paneles[1].textContent).not.toContain('break');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('marca "no encontrado" cuando la API responde 404', async () => {
    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'no-existe');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/events/no-existe')
      .flush({ detail: 'El evento no existe.' }, { status: 404, statusText: 'Not Found' });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('No hemos encontrado este evento');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
