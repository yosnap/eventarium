import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventPage } from './event-page';

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
    sessions: [
      {
        id: 's1',
        session_type: 'talk',
        title: 'Charla de apertura',
        description: null,
        starts_at: '2026-10-01T09:00:00Z',
        ends_at: '2026-10-01T10:00:00Z',
        room: 'Sala A',
        video_platform: null,
        video_url: null,
        materials: [],
        participants: [{ display_name: 'Ana Ponente', role_key: 'speaker', public_slug: 'ana' }],
      },
    ],
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
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('agrupa los patrocinadores por nivel, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventPage);
    fixture.componentRef.setInput('slug', 'iawic-2026');
    fixture.detectChanges();
    http.expectOne((peticion) => peticion.url === '/api/v1/public/events/iawic-2026').flush({
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
