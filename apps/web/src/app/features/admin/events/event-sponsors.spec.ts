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
      providers: [provideZonelessChangeDetection(), provideHttpClient(), provideHttpClientTesting()],
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
