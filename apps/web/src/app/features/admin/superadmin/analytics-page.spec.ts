import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { AuthService } from '../../../core/auth/auth.service';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { AnalyticsPage } from './analytics-page';

const AJUSTES_URL = '/api/v1/admin/analytics-settings';
const CONSENTIMIENTOS_URL = '/api/v1/admin/cookie-consents/stats';
const GA4_URL = '/api/v1/admin/analytics-providers/ga4-stats';

const AJUSTES = {
  ga4_measurement_id: 'G-TEST123',
  meta_pixel_id: null,
  cloudflare_analytics_token: 'tok-publico',
};

const CELDAS = [
  { semana: '2026-09-14', categoria: 'necessary', total: 8 },
  { semana: '2026-09-14', categoria: 'analytics', total: 6 },
  { semana: '2024-09-14', categoria: 'marketing', total: null },
];

const GA4_DATOS = {
  estado: 'datos',
  detalle: null,
  usuarios_activos: 812,
  sesiones: 1340,
  vistas_pagina: 4560,
};

const GA4_SIN_CONFIGURAR = {
  estado: 'no_configurado',
  detalle:
    'No hay credencial de la cuenta de servicio de Google configurada (GA4_SERVICE_ACCOUNT_JSON).',
  usuarios_activos: null,
  sesiones: null,
  vistas_pagina: null,
};

interface UsuarioDePrueba {
  is_superadmin: boolean;
  platform_role?: string | null;
}

function configurar(usuario: UsuarioDePrueba = { is_superadmin: true }): void {
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
      { provide: AuthService, useValue: { currentUser: signal(usuario) } },
    ],
  });
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

async function crearYCargar(
  usuario: UsuarioDePrueba = { is_superadmin: true },
  ga4: object = GA4_DATOS,
): Promise<ComponentFixture<AnalyticsPage>> {
  configurar(usuario);
  const fixture = TestBed.createComponent(AnalyticsPage);
  await avanzar(fixture);

  const http = TestBed.inject(HttpTestingController);
  http.expectOne(AJUSTES_URL).flush(AJUSTES);
  http.expectOne((r) => r.url === CONSENTIMIENTOS_URL).flush({ celdas: CELDAS });
  http.expectOne((r) => r.url === GA4_URL).flush(ga4);
  await avanzar(fixture);
  return fixture;
}

afterEach(() => {
  TestBed.resetTestingModule();
});

describe('AnalyticsPage', () => {
  it('carga ajustes, agregados y estadísticas; sin violaciones de accesibilidad', async () => {
    const fixture = await crearYCargar();

    expect(fixture.componentInstance['ga4MeasurementId']()).toBe('G-TEST123');
    expect(fixture.componentInstance['metaPixelId']()).toBe('');
    expect(fixture.componentInstance['cloudflareToken']()).toBe('tok-publico');
    expect(fixture.componentInstance['celdasConsentimientos']()).toHaveLength(3);
    expect(fixture.componentInstance['ga4']()?.estado).toBe('datos');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('el superadmin guarda; un campo vacío se envía como null', async () => {
    const fixture = await crearYCargar();

    fixture.componentInstance['cloudflareToken'].set('   ');
    const guardado = fixture.componentInstance['guardar'](new Event('submit'));
    await avanzar(fixture);

    const http = TestBed.inject(HttpTestingController);
    const peticion = http.expectOne((r) => r.url === AJUSTES_URL && r.method === 'PUT');
    expect(peticion.request.body).toMatchObject({
      ga4_measurement_id: 'G-TEST123',
      meta_pixel_id: null,
      cloudflare_analytics_token: null,
    });
    peticion.flush(AJUSTES);
    await guardado;

    expect(fixture.componentInstance['guardado']()).toBe(true);
  });

  it('soporte ve los campos deshabilitados y no puede guardar', async () => {
    const fixture = await crearYCargar({ is_superadmin: false, platform_role: 'soporte' });

    expect(fixture.nativeElement.querySelectorAll('input:disabled').length).toBe(4);
    expect(fixture.nativeElement.querySelector('button[type="submit"]')).toBeNull();

    await fixture.componentInstance['guardar'](new Event('submit'));
    await avanzar(fixture);
    TestBed.inject(HttpTestingController).verify();
  });

  it('renderiza el agregado semanal con las celdas suprimidas como «—»', async () => {
    const fixture = await crearYCargar();
    const texto = fixture.nativeElement.textContent as string;

    expect(texto).toContain('8');
    expect(texto).toContain('6');
    expect(texto).toContain('—');
  });

  it('la tarjeta de GA4 muestra el estado explícito cuando no está configurada', async () => {
    const fixture = await crearYCargar(undefined, GA4_SIN_CONFIGURAR);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('GA4_SERVICE_ACCOUNT_JSON');
    expect(texto).not.toContain('812');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('cambiar el periodo recarga agregados y estadísticas', async () => {
    const fixture = await crearYCargar();

    fixture.componentInstance['cambiarDiasConsentimientos']('7');
    await avanzar(fixture);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne((r) => r.url === CONSENTIMIENTOS_URL).flush({ celdas: [] });

    fixture.componentInstance['cambiarDiasGa4']('7');
    await avanzar(fixture);
    http.expectOne((r) => r.url === GA4_URL).flush(GA4_DATOS);
    await avanzar(fixture);

    expect(fixture.componentInstance['celdasConsentimientos']()).toHaveLength(0);
  });
});
