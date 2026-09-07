import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BrandingPage } from './branding-page';
import { ThemingService } from '../../../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const BRANDING_URL = '/api/v1/organizations/me/branding';

const BRANDING_VALIDO = {
  template_key: 'classic',
  colors: {
    primary: '#1d4ed8',
    'primary-contrast': '#ffffff',
    secondary: '#0f766e',
    surface: '#ffffff',
    'surface-muted': '#f1f5f9',
    text: '#0f172a',
    'text-muted': '#475569',
    border: '#cbd5e1',
    danger: '#b91c1c',
    success: '#15803d',
  },
  fonts: { sans: 'system-ui', heading: 'system-ui' },
  social_links: [],
  organizer_blurb: null,
  logo_url: null,
};

/** Ver el comentario homónimo en `organization-page.spec.ts`. */
async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('BrandingPage', () => {
  let http: HttpTestingController;
  let themingLoad: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    themingLoad = vi.fn().mockResolvedValue(undefined);
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
        { provide: ThemingService, useValue: { load: themingLoad } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('carga el branding y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(BrandingPage);
    await avanzar(fixture);
    http.expectOne(BRANDING_URL).flush(BRANDING_VALIDO);
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('select').value).toBe('classic');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('avisa de contraste insuficiente y el aviso desaparece al corregirlo', async () => {
    const fixture = TestBed.createComponent(BrandingPage);
    await avanzar(fixture);
    http
      .expectOne(BRANDING_URL)
      .flush({ ...BRANDING_VALIDO, colors: { ...BRANDING_VALIDO.colors, text: '#f5f5f5' } });
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('contraste');

    const campoTexto = Array.from(
      fixture.nativeElement.querySelectorAll('input[type="text"], input:not([type])'),
    ).find((el) => (el as HTMLInputElement).value === '#f5f5f5') as HTMLInputElement;
    campoTexto.value = '#0f172a';
    campoTexto.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).not.toContain('contraste');
  });

  it('guarda los cambios y refresca el branding público aplicado', async () => {
    const fixture = TestBed.createComponent(BrandingPage);
    await avanzar(fixture);
    http.expectOne(BRANDING_URL).flush(BRANDING_VALIDO);
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(BRANDING_URL);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body.template_key).toBe('classic');
    peticion.flush(BRANDING_VALIDO);
    // Dos ciclos: uno para la respuesta del PUT, otro para el `await` encadenado a
    // `theming.load()` dentro de `guardar()`.
    await avanzar(fixture);
    await avanzar(fixture);

    expect(themingLoad).toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('guardado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('rechaza en el cliente un logotipo con un tipo no permitido', async () => {
    const fixture = TestBed.createComponent(BrandingPage);
    await avanzar(fixture);
    http.expectOne(BRANDING_URL).flush(BRANDING_VALIDO);
    await avanzar(fixture);

    const campoFichero = fixture.nativeElement.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const ficheroSvg = new File(['<svg></svg>'], 'logo.svg', { type: 'image/svg+xml' });
    Object.defineProperty(campoFichero, 'files', { value: [ficheroSvg] });
    campoFichero.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('PNG, JPEG o WebP');

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);
    // Solo el PUT de datos de branding, nunca el de subida del logo rechazado.
    http.expectOne(BRANDING_URL).flush(BRANDING_VALIDO);
  });
});
