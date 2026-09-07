import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { OrganizationPage } from './organization-page';
import { ThemingService } from '../../../core/theming/theming.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const ORGANIZACION = {
  id: '1',
  slug: 'org-de-prueba',
  name: 'Org de prueba',
  legal_name: null,
  description: null,
  website: null,
  contact_email: null,
  is_active: true,
};

/**
 * `whenStable()` no basta tras un `HttpTestingController.flush()`: la escritura de la
 * señal ocurre en la continuación de una promesa que el planificador zoneless no
 * sincroniza a tiempo con el siguiente `await`. `detectChanges()` fuerza esa
 * sincronización — sin él, el DOM se queda mostrando el estado anterior aunque la
 * señal ya haya cambiado.
 */
async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('OrganizationPage', () => {
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
        { provide: ThemingService, useValue: { load: vi.fn().mockResolvedValue(undefined) } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('carga los datos actuales y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(OrganizationPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/organizations/me').flush(ORGANIZACION);
    await avanzar(fixture);

    expect(fixture.nativeElement.querySelector('input').value).toBe('Org de prueba');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('exige el nombre antes de guardar', async () => {
    const fixture = TestBed.createComponent(OrganizationPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/organizations/me').flush({ ...ORGANIZACION, name: '' });
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.method === 'PATCH');
    expect(fixture.nativeElement.textContent).toContain('nombre');
  });

  it('guarda los cambios y refresca el branding público', async () => {
    const fixture = TestBed.createComponent(OrganizationPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/organizations/me').flush(ORGANIZACION);
    await avanzar(fixture);

    const campoNombre = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    campoNombre.value = 'Nuevo nombre';
    campoNombre.dispatchEvent(new Event('input'));
    await avanzar(fixture);

    (fixture.nativeElement.querySelector('form') as HTMLFormElement).dispatchEvent(
      new Event('submit'),
    );
    await avanzar(fixture);

    const peticion = http.expectOne('/api/v1/organizations/me');
    expect(peticion.request.method).toBe('PATCH');
    expect(peticion.request.body.name).toBe('Nuevo nombre');
    peticion.flush({ ...ORGANIZACION, name: 'Nuevo nombre' });
    // Dos ciclos: uno para la respuesta del PATCH, otro para el `await` encadenado a
    // `theming.load()` dentro de `guardar()`.
    await avanzar(fixture);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('guardado');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });
});
