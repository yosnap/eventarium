import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { errorInterceptor } from '../../../core/api/error.interceptor';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { ServicesPage } from './services-page';

const SERVICIOS_URL = '/api/v1/admin/services';
const ORGANIZACIONES_URL = '/api/v1/admin/organizations';
const ORGANIZACION_ID = '44444444-4444-4444-4444-444444444444';
const SERVICIOS_DE_LA_ORG_URL = `${ORGANIZACIONES_URL}/${ORGANIZACION_ID}/services`;

const GLOBALES = [
  {
    service_key: 'ai',
    etiqueta: 'Pasarela de IA',
    descripcion: 'Permite que las funciones que usan IA llamen al proveedor configurado.',
    enabled: true,
  },
];

const ORGANIZACIONES = [{ id: ORGANIZACION_ID, name: 'IA Week', slug: 'ia-week', is_active: true }];

const DE_LA_ORG = [
  {
    service_key: 'ai',
    etiqueta: 'Pasarela de IA',
    global_enabled: true,
    overridden_off: false,
    enabled: true,
  },
];

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('ServicesPage', () => {
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
        provideHttpClient(withInterceptors([errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  async function crearYCargar(
    globales: typeof GLOBALES = GLOBALES,
  ): Promise<ComponentFixture<ServicesPage>> {
    const fixture = TestBed.createComponent(ServicesPage);
    await avanzar(fixture);
    http.expectOne(SERVICIOS_URL).flush(globales);
    http.expectOne(ORGANIZACIONES_URL).flush(ORGANIZACIONES);
    await avanzar(fixture);
    await avanzar(fixture);
    return fixture;
  }

  it('pinta los interruptores globales sin violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    expect(fixture.nativeElement.textContent).toContain('Pasarela de IA');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('apagar el interruptor global lo envía y relee el estado', async () => {
    const fixture = await crearYCargar();

    const cambiando = fixture.componentInstance.cambiarGlobal('ai', false);
    await avanzar(fixture);
    const peticion = http.expectOne({ method: 'PUT', url: SERVICIOS_URL });
    expect(peticion.request.body).toEqual({ services: [{ service_key: 'ai', enabled: false }] });
    peticion.flush([{ ...GLOBALES[0], enabled: false }]);
    await cambiando;
    await avanzar(fixture);

    expect(fixture.componentInstance.globales()[0].enabled).toBe(false);
  });

  it('al elegir una organización pide su estado de servicios', async () => {
    const fixture = await crearYCargar();

    const eligiendo = fixture.componentInstance.elegirOrganizacion(ORGANIZACION_ID);
    await avanzar(fixture);
    http.expectOne(SERVICIOS_DE_LA_ORG_URL).flush(DE_LA_ORG);
    await eligiendo;
    await avanzar(fixture);

    expect(fixture.componentInstance.deLaOrganizacion()).toHaveLength(1);
  });

  it('el override por organización solo apaga: forzar off manda enabled=false', async () => {
    const fixture = await crearYCargar();
    const eligiendo = fixture.componentInstance.elegirOrganizacion(ORGANIZACION_ID);
    await avanzar(fixture);
    http.expectOne(SERVICIOS_DE_LA_ORG_URL).flush(DE_LA_ORG);
    await eligiendo;
    await avanzar(fixture);

    const cambiando = fixture.componentInstance.cambiarDeLaOrganizacion('ai', false);
    await avanzar(fixture);
    const peticion = http.expectOne({ method: 'PUT', url: SERVICIOS_DE_LA_ORG_URL });
    expect(peticion.request.body).toEqual({ services: [{ service_key: 'ai', enabled: false }] });
    peticion.flush([{ ...DE_LA_ORG[0], overridden_off: true, enabled: false }]);
    await cambiando;
    await avanzar(fixture);

    expect(fixture.componentInstance.deLaOrganizacion()[0].overridden_off).toBe(true);
  });

  it('con el servicio apagado globalmente, el interruptor de la organización queda bloqueado', async () => {
    // V-7: un servicio apagado globalmente no se reactiva por organización.
    const fixture = await crearYCargar([{ ...GLOBALES[0], enabled: false }]);
    const eligiendo = fixture.componentInstance.elegirOrganizacion(ORGANIZACION_ID);
    await avanzar(fixture);
    http
      .expectOne(SERVICIOS_DE_LA_ORG_URL)
      .flush([{ ...DE_LA_ORG[0], global_enabled: false, enabled: false }]);
    await eligiendo;
    await avanzar(fixture);

    const interruptor = fixture.nativeElement.querySelector(
      '#servicio-org-ai',
    ) as HTMLButtonElement;
    expect(interruptor.disabled).toBe(true);
  });
});
