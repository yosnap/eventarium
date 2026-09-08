import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { LegalPagesPage } from './legal-pages-page';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

function respuestaLegal(sobrescribir: Record<string, unknown> = {}) {
  return {
    legal_notice: { content: 'Plantilla de aviso legal.', is_custom: false },
    privacy_policy: { content: 'Plantilla de privacidad.', is_custom: false },
    cookies_policy: { content: 'Plantilla de cookies.', is_custom: false },
    registration_terms: { content: 'Plantilla de condiciones.', is_custom: false },
    ...sobrescribir,
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('LegalPagesPage', () => {
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

  it('carga las cuatro páginas y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(LegalPagesPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/organizations/me/legal-pages').flush(respuestaLegal());
    await avanzar(fixture);

    const textareas = fixture.nativeElement.querySelectorAll('textarea');
    expect(textareas.length).toBe(4);
    expect(fixture.nativeElement.textContent).toContain('Plantilla de aviso legal.');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el botón de restaurar plantilla está desactivado si la página no está editada', async () => {
    const fixture = TestBed.createComponent(LegalPagesPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/organizations/me/legal-pages').flush(respuestaLegal());
    await avanzar(fixture);

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as HTMLButtonElement[];
    const restaurar = botones.filter((b) => b.textContent?.includes('Restaurar plantilla'));
    expect(restaurar.length).toBe(4);
    expect(restaurar.every((b) => b.disabled)).toBe(true);
  });

  it('restaurar una página editada envía `null` explícito, no la omite', async () => {
    const fixture = TestBed.createComponent(LegalPagesPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/organizations/me/legal-pages').flush(
      respuestaLegal({
        privacy_policy: { content: 'Texto editado a mano.', is_custom: true },
      }),
    );
    await avanzar(fixture);

    const botones = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as HTMLButtonElement[];
    const restaurarPrivacidad = botones.find(
      (b) => b.textContent?.includes('Restaurar plantilla') && !b.disabled,
    );
    expect(restaurarPrivacidad).toBeDefined();
    restaurarPrivacidad?.dispatchEvent(new Event('click'));
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/organizations/me/legal-pages');
    expect(peticion.request.method).toBe('PATCH');
    expect(peticion.request.body).toEqual({ privacy_policy_content: null });
    peticion.flush(respuestaLegal());
  });
});
