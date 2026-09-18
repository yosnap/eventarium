import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BrandingPage } from './branding-page';
import { ThemingService } from '../../../core/theming/theming.service';
import { plantillaDeTemaDePrueba } from '../../../../testing/branding.fixture';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const ORGANIZACION_URL = '/api/v1/organizations/me';
const BRANDING_URL = '/api/v1/organizations/me/branding';
const CATALOGO_URL = '/api/v1/organizations/me/theme-templates';

const ORGANIZACION_VALIDA = { name: 'Organización de prueba' };

const PLANTILLA_OSCURA = plantillaDeTemaDePrueba({
  id: 'tema-oscuro',
  key: 'oscuro',
  name: 'Oscuro',
});
const PLANTILLA_CLARA = plantillaDeTemaDePrueba({ id: 'tema-claro', key: 'claro', name: 'Claro' });
const CATALOGO = [PLANTILLA_OSCURA, PLANTILLA_CLARA];

const BRANDING_VALIDO = {
  theme_template_id: PLANTILLA_OSCURA.id,
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
        provideRouter([]),
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

  async function crearYCargar(): Promise<ComponentFixture<BrandingPage>> {
    const fixture = TestBed.createComponent(BrandingPage);
    await avanzar(fixture);
    http.expectOne(ORGANIZACION_URL).flush(ORGANIZACION_VALIDA);
    http.expectOne(BRANDING_URL).flush(BRANDING_VALIDO);
    http.expectOne(CATALOGO_URL).flush(CATALOGO);
    await avanzar(fixture);
    await avanzar(fixture);
    return fixture;
  }

  it('carga el branding y el catálogo, sin violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    expect(fixture.nativeElement.textContent).toContain('Organización de prueba');
    const opciones = Array.from(
      fixture.nativeElement.querySelectorAll('.plantilla-tarjeta'),
    ) as HTMLElement[];
    expect(opciones.length).toBe(2);
    const marcada = opciones.find((r) => r.getAttribute('aria-pressed') === 'true');
    expect(marcada?.textContent).toContain(PLANTILLA_OSCURA.name);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('la galería de plantillas tiene nombre accesible y cada tarjeta indica si está aplicada', async () => {
    const fixture = await crearYCargar();

    const grupo = fixture.nativeElement.querySelector('.plantillas');
    expect(grupo.getAttribute('aria-label')).toBeTruthy();
    const opciones = grupo.querySelectorAll('.plantilla-tarjeta');
    expect(opciones.length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('Claro');
    expect(fixture.nativeElement.textContent).toContain('Oscuro');
  });

  it('elegir otra plantilla de tema la envía en el PUT', async () => {
    const fixture = await crearYCargar();

    const tarjetas = Array.from(
      fixture.nativeElement.querySelectorAll('.plantilla-tarjeta'),
    ) as HTMLButtonElement[];
    const tarjetaClara = tarjetas.find((t) => t.textContent?.includes(PLANTILLA_CLARA.name))!;
    tarjetaClara.click();
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(BRANDING_URL);
    expect(peticion.request.method).toBe('PUT');
    expect(peticion.request.body.theme_template_id).toBe(PLANTILLA_CLARA.id);
    expect(peticion.request.body.template_key).toBeUndefined();
    expect(peticion.request.body.colors).toBeUndefined();
    expect(peticion.request.body.fonts).toBeUndefined();
    peticion.flush({ ...BRANDING_VALIDO, theme_template_id: PLANTILLA_CLARA.id });
    await avanzar(fixture);
    await avanzar(fixture);

    expect(themingLoad).toHaveBeenCalled();
  });

  it('guarda los cambios y refresca el branding público aplicado', async () => {
    const fixture = await crearYCargar();

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(BRANDING_URL);
    expect(peticion.request.method).toBe('PUT');
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
    const fixture = await crearYCargar();

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

  it('si falla la carga inicial, no deja un formulario enviable que pueda sobrescribir el branding', async () => {
    const fixture = TestBed.createComponent(BrandingPage);
    await avanzar(fixture);
    http.expectOne(ORGANIZACION_URL).flush('error', { status: 500, statusText: 'Error' });
    http.expectOne(BRANDING_URL).flush(BRANDING_VALIDO);
    http.expectOne(CATALOGO_URL).flush(CATALOGO);
    await avanzar(fixture);
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('form')).toBeNull();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeTruthy();
  });
});
