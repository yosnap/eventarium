import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { SponsorTiersPage } from './sponsor-tiers-page';

const TIERS_URL = '/api/v1/organizations/me/sponsor-tiers';

function pagina() {
  return {
    items: [
      { id: 't1', name: 'Oro', display_order: 0, logo_size: 'large', benefits: null },
      { id: 't2', name: 'Plata', display_order: 1, logo_size: 'medium', benefits: null },
    ],
    total: 2,
    limit: 100,
    offset: 0,
  };
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('SponsorTiersPage', () => {
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

  it('lista los niveles existentes, sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(SponsorTiersPage);
    await avanzar(fixture);
    http.expectOne((p) => p.url === TIERS_URL).flush(pagina());
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent;
    expect(texto).toContain('Oro');
    expect(texto).toContain('Plata');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('reordena intercambiando el display_order de los dos niveles afectados', async () => {
    const fixture = TestBed.createComponent(SponsorTiersPage);
    await avanzar(fixture);
    http.expectOne((p) => p.url === TIERS_URL).flush(pagina());
    await avanzar(fixture);

    const botonBajar = fixture.nativeElement.querySelectorAll('button')[1] as HTMLButtonElement;
    botonBajar.click();
    await avanzar(fixture);

    const primerPatch = http.expectOne((p) => p.method === 'PATCH' && p.url === `${TIERS_URL}/t1`);
    expect(primerPatch.request.body).toEqual({ display_order: 1 });
    primerPatch.flush({
      id: 't1',
      name: 'Oro',
      display_order: 1,
      logo_size: 'large',
      benefits: null,
    });
    await avanzar(fixture);

    const segundoPatch = http.expectOne((p) => p.method === 'PATCH' && p.url === `${TIERS_URL}/t2`);
    expect(segundoPatch.request.body).toEqual({ display_order: 0 });
    segundoPatch.flush({
      id: 't2',
      name: 'Plata',
      display_order: 0,
      logo_size: 'medium',
      benefits: null,
    });
    await avanzar(fixture);

    http.expectOne((p) => p.url === TIERS_URL).flush(pagina());
    await avanzar(fixture);
  });

  it('muestra un error si el borrado falla (p. ej. 409 por patrocinadores asignados)', async () => {
    // Sin `errorInterceptor` registrado en este arnés de test (solo se activa en el
    // `AppConfig` real), el componente recibe el `HttpErrorResponse` crudo, no un
    // `ApiError` con el `detail` de la API — cae en su mensaje genérico. El texto
    // exacto del 409 (`sponsors/service.py:delete_tier`) ya lo cubre
    // `test_sponsors_router.py::test_borrar_nivel_con_patrocinadores_da_409_con_mensaje_claro`.
    const fixture = TestBed.createComponent(SponsorTiersPage);
    await avanzar(fixture);
    http.expectOne((p) => p.url === TIERS_URL).flush(pagina());
    await avanzar(fixture);

    const botonesEliminar = [...fixture.nativeElement.querySelectorAll('button')].filter((b) =>
      b.textContent?.includes('Eliminar'),
    ) as HTMLButtonElement[];
    botonesEliminar[0].click();
    await avanzar(fixture);

    http
      .expectOne((p) => p.method === 'DELETE' && p.url === `${TIERS_URL}/t1`)
      .flush(
        { detail: 'Ese nivel de patrocinio tiene patrocinadores asignados.' },
        { status: 409, statusText: 'Conflict' },
      );
    await avanzar(fixture);

    expect(fixture.nativeElement.textContent).toContain('No hemos podido completar la operación.');
  });
});
