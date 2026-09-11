import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { PlatformIdentityPage } from './platform-identity-page';

const IDENTIDAD_URL = '/api/v1/admin/identity';
const PLANTILLAS_URL = '/api/v1/admin/theme-templates';

const IDENTIDAD = {
  name: 'Eventarium',
  logo_url: null,
  favicon_url: null,
  social_links: [],
  theme_template_id: null,
  theme: null,
};

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('PlatformIdentityPage', () => {
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
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  async function crearYCargar(): Promise<ComponentFixture<PlatformIdentityPage>> {
    const fixture = TestBed.createComponent(PlatformIdentityPage);
    await avanzar(fixture);
    // La pantalla pide identidad y catálogo de plantillas a la vez.
    http.expectOne(IDENTIDAD_URL).flush(IDENTIDAD);
    http.expectOne(PLANTILLAS_URL).flush([]);
    await avanzar(fixture);
    return fixture;
  }

  it('carga el nombre de la plataforma y no tiene violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    expect(fixture.componentInstance.nombre()).toBe('Eventarium');
    // Es la identidad de la instalación: el texto lo deja claro y no aparece
    // ningún concepto de organización.
    expect(fixture.nativeElement.textContent).toContain('Eventarium');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('guarda el nombre con PATCH y refleja la respuesta', async () => {
    const fixture = await crearYCargar();
    fixture.componentInstance.nombre.set('Eventarium Pro');

    const guardado = fixture.componentInstance.guardar(new Event('submit'));
    await avanzar(fixture);
    const peticion = http.expectOne((r) => r.url === IDENTIDAD_URL && r.method === 'PATCH');
    expect(peticion.request.body).toMatchObject({ name: 'Eventarium Pro' });
    peticion.flush({ ...IDENTIDAD, name: 'Eventarium Pro' });
    await guardado;

    expect(fixture.componentInstance.nombre()).toBe('Eventarium Pro');
    expect(fixture.componentInstance.guardado()).toBe(true);
  });

  it('solo ofrece la plantilla por defecto cuando el catálogo está vacío', async () => {
    const fixture = await crearYCargar();
    const opciones = fixture.componentInstance.opcionesDePlantilla();
    expect(opciones).toHaveLength(1);
    expect(opciones[0].value).toBe('');
  });

  it('sube el logotipo como multipart y actualiza la URL', async () => {
    const fixture = await crearYCargar();

    const entrada = document.createElement('input');
    entrada.type = 'file';
    const fichero = new File([new Uint8Array([1])], 'logo.png', { type: 'image/png' });
    Object.defineProperty(entrada, 'files', { value: [fichero] });

    const subida = fixture.componentInstance.subirLogo({ target: entrada } as unknown as Event);
    await avanzar(fixture);
    const peticion = http.expectOne(`${IDENTIDAD_URL}/logo`);
    expect(peticion.request.method).toBe('PUT');
    peticion.flush({ ...IDENTIDAD, logo_url: 'https://cdn.test/logo.png' });
    await subida;

    expect(fixture.componentInstance.logoUrl()).toBe('https://cdn.test/logo.png');
  });
});
