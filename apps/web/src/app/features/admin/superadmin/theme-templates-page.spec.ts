import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ThemeTemplatesPage } from './theme-templates-page';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { plantillaDeTemaDePrueba } from '../../../../testing/branding.fixture';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const CATALOGO_URL = '/api/v1/admin/theme-templates';

const PLANTILLA = plantillaDeTemaDePrueba({ id: 'tema-1', key: 'oscuro', name: 'Oscuro' });

/** Ver el comentario homónimo en `organization-page.spec.ts`. */
async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('ThemeTemplatesPage', () => {
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
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  async function crearYCargar(): Promise<ComponentFixture<ThemeTemplatesPage>> {
    const fixture = TestBed.createComponent(ThemeTemplatesPage);
    await avanzar(fixture);
    http.expectOne(CATALOGO_URL).flush([PLANTILLA]);
    await avanzar(fixture);
    return fixture;
  }

  it('carga el catálogo y no tiene violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    expect(fixture.nativeElement.textContent).toContain('Oscuro');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('bloquea el guardado con role="alert" si un par crítico no cumple 4,5:1', async () => {
    const fixture = await crearYCargar();

    (fixture.nativeElement.querySelector('.fila') as HTMLButtonElement).click();
    await avanzar(fixture);

    // Deja los campos oscuros de fg/bg casi iguales: el par crítico deja de cumplir AA.
    const campoFg = fixture.nativeElement.querySelector(
      '#token-dark-fg',
    ) as HTMLInputElement;
    campoFg.value = '#050505';
    campoFg.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    const aviso = fixture.nativeElement.querySelector('[role="alert"]');
    expect(aviso).toBeTruthy();
    expect(aviso.textContent).toContain('fg');

    const boton = fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(boton.disabled).toBe(true);
  });

  it('muestra el rechazo del servidor (422) en el mismo role="alert", nunca un genérico', async () => {
    const fixture = await crearYCargar();

    (fixture.nativeElement.querySelector('.fila') as HTMLButtonElement).click();
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(`${CATALOGO_URL}/${PLANTILLA.id}`);
    expect(peticion.request.method).toBe('PATCH');
    peticion.flush(
      { detail: 'El par «fg»/«bg» en modo oscuro da 1,2:1, por debajo de 4,5:1.' },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('1,2:1');
    expect(fixture.nativeElement.textContent).not.toContain('error inesperado');
  });

  it('pinta el detalle exacto (par, modo, ratio) de `problem.errors` en el mismo role="alert" que el aviso local', async () => {
    const fixture = await crearYCargar();

    (fixture.nativeElement.querySelector('.fila') as HTMLButtonElement).click();
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(`${CATALOGO_URL}/${PLANTILLA.id}`);
    peticion.flush(
      {
        detail: 'La plantilla no supera el contraste mínimo AA (4,5:1) en alguno de sus pares críticos.',
        errors: [{ primero: 'fg', segundo: 'bg', modo: 'dark', ratio: 1.23 }],
      },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    await avanzar(fixture);

    const aviso = fixture.nativeElement.querySelector('[role="alert"]');
    expect(aviso).toBeTruthy();
    expect(aviso.textContent).toContain('fg');
    expect(aviso.textContent).toContain('bg');
    expect(aviso.textContent).toContain('1.23');
  });

  it('en el alta, propone una clave en kebab-case a partir del nombre y la envía tal cual', async () => {
    const fixture = await crearYCargar();

    const botones: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    );
    botones.find((boton) => boton.textContent?.includes('Nueva plantilla'))?.click();
    await avanzar(fixture);

    const campoNombre = fixture.nativeElement.querySelector(
      '#plantilla-nombre',
    ) as HTMLInputElement;
    campoNombre.value = 'Claro Vibrante';
    campoNombre.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    const campoClave = fixture.nativeElement.querySelector(
      '#plantilla-clave',
    ) as HTMLInputElement;
    expect(campoClave.value).toBe('claro-vibrante');

    // Solo hacen falta los tokens que entran en los pares críticos: el resto se queda
    // vacío y no bloquea el envío, porque `comprobarContrasteDePlantilla` no los mira.
    for (const modo of ['dark', 'light'] as const) {
      for (const [token, valor] of Object.entries(PLANTILLA.tokens[modo])) {
        const campo = fixture.nativeElement.querySelector(
          `#token-${modo}-${token}`,
        ) as HTMLInputElement | null;
        if (campo) {
          campo.value = valor;
          campo.dispatchEvent(new Event('input'));
        }
      }
    }
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(CATALOGO_URL);
    expect(peticion.request.method).toBe('POST');
    expect(peticion.request.body).toMatchObject({ key: 'claro-vibrante', name: 'Claro Vibrante' });
    peticion.flush({ ...PLANTILLA, id: 'tema-2', key: 'claro-vibrante', name: 'Claro Vibrante' });
    await avanzar(fixture);

    http.expectOne(CATALOGO_URL).flush([PLANTILLA]);
    await avanzar(fixture);
  });

  it('si la clave no sigue el patrón kebab-case, deshabilita el guardado y muestra el error', async () => {
    const fixture = await crearYCargar();

    const botones: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    );
    botones.find((boton) => boton.textContent?.includes('Nueva plantilla'))?.click();
    await avanzar(fixture);

    const campoClave = fixture.nativeElement.querySelector(
      '#plantilla-clave',
    ) as HTMLInputElement;
    campoClave.value = 'Clave Con Espacios';
    campoClave.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    const boton = fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(boton.disabled).toBe(true);
    expect(fixture.nativeElement.textContent).toContain(
      'La clave debe ir en minúsculas y con guiones',
    );
  });

  it('permite marcar la plantilla como predeterminada al editar, y lo envía en el PATCH', async () => {
    const fixture = await crearYCargar();

    (fixture.nativeElement.querySelector('.fila') as HTMLButtonElement).click();
    await avanzar(fixture);

    const casilla = fixture.nativeElement.querySelector(
      '.predeterminada input[type="checkbox"]',
    ) as HTMLInputElement;
    expect(casilla.checked).toBe(false);
    casilla.checked = true;
    casilla.dispatchEvent(new Event('change'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne(`${CATALOGO_URL}/${PLANTILLA.id}`);
    expect(peticion.request.body).toMatchObject({ is_default: true });
    peticion.flush({ ...PLANTILLA, is_default: true });
    await avanzar(fixture);

    http.expectOne(CATALOGO_URL).flush([{ ...PLANTILLA, is_default: true }]);
    await avanzar(fixture);
  });
});
