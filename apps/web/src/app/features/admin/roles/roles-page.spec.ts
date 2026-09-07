import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { RolesPage } from './roles-page';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';

const ROLES = [
  {
    id: '1',
    key: 'owner',
    name: 'Propietario',
    description: 'Control total.',
    is_system: true,
    permissions: ['organizations:read'],
  },
  {
    id: '2',
    key: 'presentador',
    name: 'Presentador',
    description: null,
    is_system: false,
    permissions: [],
  },
];

/** Ver el comentario homónimo en `organization-page.spec.ts`. */
async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('RolesPage', () => {
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

  it('lista los roles, distingue sistema de a medida, y no tiene violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(RolesPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('Propietario');
    expect(fixture.nativeElement.textContent).toContain('Presentador');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('no ofrece borrar un rol del sistema', async () => {
    const fixture = TestBed.createComponent(RolesPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    const botones = Array.from(fixture.nativeElement.querySelectorAll('button')).map((boton) =>
      (boton as HTMLButtonElement).textContent?.trim(),
    );
    // Solo un botón "Eliminar" en toda la página: el del rol a medida.
    expect(botones.filter((texto) => texto === 'Eliminar')).toHaveLength(1);
  });

  it('borrar pide confirmación en línea antes de llamar a la API', async () => {
    const fixture = TestBed.createComponent(RolesPage);
    await avanzar(fixture);
    http.expectOne('/api/v1/roles').flush(ROLES);
    await avanzar(fixture);

    const botonEliminar = Array.from(fixture.nativeElement.querySelectorAll('button')).find(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === 'Eliminar',
    ) as HTMLButtonElement | undefined;
    botonEliminar?.click();
    await avanzar(fixture);

    http.expectNone((peticion) => peticion.method === 'DELETE');
    expect(fixture.nativeElement.textContent).toContain('¿Seguro?');

    const botonConfirmar = Array.from(fixture.nativeElement.querySelectorAll('button')).find(
      (boton) => (boton as HTMLButtonElement).textContent?.trim() === '¿Seguro?',
    ) as HTMLButtonElement | undefined;
    botonConfirmar?.click();
    await avanzar(fixture);

    http.expectOne('/api/v1/roles/2').flush(null);
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).not.toContain('Presentador');
  });
});
