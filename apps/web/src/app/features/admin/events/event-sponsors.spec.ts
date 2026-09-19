import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventSponsors } from './event-sponsors';

const TIERS_URL = '/api/v1/organizations/me/sponsor-tiers';
const SPONSORS_URL = '/api/v1/events/e1/sponsors';

function niveles() {
  return {
    items: [{ id: 't1', name: 'Oro', display_order: 0, logo_size: 'large', benefits: null }],
    total: 1,
    limit: 100,
    offset: 0,
  };
}

function patrocinadores() {
  return [
    {
      id: 's1',
      tier_id: 't1',
      name: 'Acme Corp',
      logo_url: null,
      website: 'https://acme.example',
      contribution_type: 'monetaria',
      contribution_amount: '500.00',
      contribution_description: null,
    },
    {
      id: 's2',
      tier_id: 't1',
      name: 'Beta SL',
      logo_url: null,
      website: null,
      contribution_type: 'en_especie',
      contribution_amount: null,
      contribution_description: 'Catering',
    },
  ];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('EventSponsors', () => {
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
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lista los patrocinadores del evento con su nivel, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventSponsors);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    http.expectOne((p) => p.url === TIERS_URL).flush(niveles());
    http.expectOne((p) => p.url === SPONSORS_URL).flush(patrocinadores());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Acme Corp');
    expect(texto).toContain('Oro');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('asigna el logo elegido al sponsor_id de SU fila, no al de otra', async () => {
    const fixture = TestBed.createComponent(EventSponsors);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne((p) => p.url === TIERS_URL).flush(niveles());
    http.expectOne((p) => p.url === SPONSORS_URL).flush(patrocinadores());
    await avanzar(fixture);

    const raiz = fixture.nativeElement as HTMLElement;
    // Cada `MediaPicker` también monta un `MediaDialog` con su propia
    // `MediaFields` (para "Cambiar"), así que hay 2 inputs de fichero por
    // fila — el segundo selector filtra solo el dropzone visible (hijo
    // directo del picker, no el que vive dentro del diálogo cerrado).
    const camposFichero = Array.from(
      raiz.querySelectorAll('app-media-picker > app-media-fields input[type="file"]'),
    ) as HTMLInputElement[];
    expect(camposFichero.length).toBe(2);

    const campoDeBeta = camposFichero[1];
    const fichero = new File([new Uint8Array([1])], 'logo.png', { type: 'image/png' });
    Object.defineProperty(campoDeBeta, 'files', { value: [fichero] });
    campoDeBeta.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    const subida = http.expectOne('/api/v1/organizations/me/media');
    subida.flush({ id: 'media-beta', url: 'https://cdn.test/beta.webp' });
    await avanzar(fixture);

    const asignacion = http.expectOne(
      (p) => p.url === '/api/v1/events/e1/sponsors/s2/logo' && p.method === 'PUT',
    );
    expect(asignacion.request.body).toEqual({ media_id: 'media-beta' });
    asignacion.flush({});
    await avanzar(fixture);

    http.expectOne((p) => p.url === SPONSORS_URL).flush(patrocinadores());
    await avanzar(fixture);
  });

  it('exige nivel y nombre antes de dar de alta un patrocinador', async () => {
    const fixture = TestBed.createComponent(EventSponsors);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);
    http.expectOne((p) => p.url === TIERS_URL).flush(niveles());
    http.expectOne((p) => p.url === SPONSORS_URL).flush([]);
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((p) => p.method === 'POST');
    expect(fixture.nativeElement.textContent).toContain(
      'Elige un nivel y escribe el nombre del patrocinador.',
    );
  });
});
