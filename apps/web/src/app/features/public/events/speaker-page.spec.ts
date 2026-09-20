import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { SpeakerPage } from './speaker-page';

function perfilPublico() {
  return {
    display_name: 'Ana Ponente',
    public_slug: 'ana',
    fields: { bio: 'Biografía de Ana.', web: 'https://ana.example.com' },
    social_links: [{ kind: 'twitter', url: 'https://twitter.com/ana' }],
    history: [
      {
        event_slug: 'iawic-2026',
        event_title: 'IA Week in Cascais 2026',
        session_id: 's1',
        session_title: 'Charla de apertura',
        starts_at: '2026-10-01T09:00:00Z',
        role_key: 'speaker',
      },
    ],
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('SpeakerPage', () => {
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

  it('muestra el perfil en tema claro sin violaciones de accesibilidad', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const fixture = TestBed.createComponent(SpeakerPage);
    fixture.componentRef.setInput('publicSlug', 'ana');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/speakers/ana')
      .flush(perfilPublico());
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Ana Ponente');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('muestra la lista blanca de campos, redes y el historial agrupado por evento', async () => {
    const fixture = TestBed.createComponent(SpeakerPage);
    fixture.componentRef.setInput('publicSlug', 'ana');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/speakers/ana')
      .flush(perfilPublico());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Ana Ponente');
    expect(texto).toContain('Biografía de Ana.');
    expect(texto).toContain('IA Week in Cascais 2026');
    expect(texto).toContain('Charla de apertura');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('marca "no encontrado" cuando el ponente no existe', async () => {
    const fixture = TestBed.createComponent(SpeakerPage);
    fixture.componentRef.setInput('publicSlug', 'no-existe');
    fixture.detectChanges();
    http
      .expectOne((peticion) => peticion.url === '/api/v1/public/speakers/no-existe')
      .flush({ detail: 'El ponente no existe.' }, { status: 404, statusText: 'Not Found' });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('No hemos encontrado este perfil');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
