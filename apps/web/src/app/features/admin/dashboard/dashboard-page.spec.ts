import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { DashboardPage } from './dashboard-page';
import { MetricasDeOrganizacion } from './organization-metrics.types';

/**
 * El escritorio decide qué pinta **según lo que recibe**: los bloques que la API
 * omite por falta de permiso no existen en la respuesta. Aquí no puede haber una
 * segunda copia de la regla de permisos que diverja de la del servidor.
 */

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

function configurar() {
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
}

function metricas(overrides: Partial<MetricasDeOrganizacion> = {}): MetricasDeOrganizacion {
  return {
    eventos_en_borrador: 0,
    eventos: [
      {
        id: 'e1',
        title: 'IA Week',
        slug: 'ia-week',
        status: 'published',
        starts_at: '2026-10-01T09:00:00Z',
        confirmadas: 50,
        aforo: 200,
        por_aprobar: 0,
        ingresos_cents: 450000,
      },
    ],
    cifras: {
      eventos_por_estado: { published: 1 },
      inscripciones_por_estado: { confirmed: 50 },
      reservadas: 50,
      aforo_total: 200,
      por_aprobar: 0,
      lista_de_espera: 5,
    },
    estructura: { miembros: 3, roles: 4, patrocinadores: 2 },
    dinero: { por_moneda: { eur: 450000 }, presupuesto_por_moneda: { eur: 0 }, ejecutado_por_moneda: { eur: 0 } },
    stripe: {
      conectada: true,
      charges_enabled: true,
      payouts_enabled: true,
      details_submitted: true,
    },
    ...overrides,
  };
}

async function montar(
  http: HttpTestingController,
  cuerpo: MetricasDeOrganizacion = metricas(),
): Promise<ComponentFixture<DashboardPage>> {
  const fixture = TestBed.createComponent(DashboardPage);
  await avanzar(fixture);

  http.expectOne((p) => p.url === '/api/v1/organizations/me/metrics').flush(cuerpo);
  await avanzar(fixture);
  return fixture;
}

describe('DashboardPage', () => {
  let http: HttpTestingController;

  function configurarYGuardarHttp() {
    configurar();
    http = TestBed.inject(HttpTestingController);
  }

  it('la tabla de eventos lleva las cifras de cada uno', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http);
    const raiz = fixture.nativeElement as HTMLElement;

    const filas = Array.from(raiz.querySelectorAll('tbody tr'));
    expect(filas.length).toBe(1);
    expect(filas[0].textContent).toContain('IA Week');
    expect(filas[0].textContent).toContain('50');
    expect(filas[0].textContent).toContain('200');
  });

  it('sin eventos invita a crear el primero, en vez de dejar un hueco', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(
      http,
      metricas({
        eventos: [],
        eventos_en_borrador: 0,
        cifras: {
          eventos_por_estado: {},
          inscripciones_por_estado: {},
          reservadas: 0,
          aforo_total: null,
          por_aprobar: 0,
          lista_de_espera: 0,
        },
      }),
    );
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('no has creado ningún evento');
    expect(raiz.querySelector('a[href="/dashboard/events/nuevo"]')).not.toBeNull();
  });

  it('sin permiso económico no pinta la columna de ingresos ni el bloque de dinero', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http, metricas({ dinero: null }));
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).not.toContain('Ingresos');
    // Ni se queja de Stripe: cobrar no es asunto de quien no ve el dinero.
    expect(raiz.textContent).not.toContain('Conectar con Stripe');
  });

  it('con permiso económico y Stripe a medias, lo pone en lo pendiente', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(
      http,
      metricas({
        stripe: {
          conectada: true,
          charges_enabled: false,
          payouts_enabled: false,
          details_submitted: false,
        },
      }),
    );
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('Requiere tu atención');
    expect(raiz.textContent).toContain('a medias');
  });

  it('sin permiso de inscripciones no aparece «por aprobar»', async () => {
    // La API omite las cifras cuando falta el permiso, y también las columnas
    // por evento: el dato viajaba dentro de cada fila, no solo en su bloque.
    configurarYGuardarHttp();
    const fixture = await montar(
      http,
      metricas({
        cifras: null,
        eventos: [
          {
            id: 'e1',
            title: 'IA Week',
            slug: 'ia-week',
            status: 'published',
            starts_at: '2026-10-01T09:00:00Z',
            confirmadas: null,
            aforo: 200,
            por_aprobar: null,
            ingresos_cents: null,
          },
        ],
      }),
    );
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).not.toContain('Por aprobar');
    // La tabla y la estructura sí siguen.
    expect(raiz.textContent).toContain('IA Week');
    expect(raiz.textContent).toContain('Miembros');
  });

  it('sin cifras por evento no pinta sus columnas, ni siquiera vacías', async () => {
    // Una cabecera «Por aprobar» sin dato detrás promete una información que no
    // va a llegar: la columna desaparece entera, no se deja con guiones.
    configurarYGuardarHttp();
    const fixture = await montar(
      http,
      metricas({
        cifras: null,
        eventos: [
          {
            id: 'e1',
            title: 'IA Week',
            slug: 'ia-week',
            status: 'published',
            starts_at: '2026-10-01T09:00:00Z',
            confirmadas: null,
            aforo: 200,
            por_aprobar: null,
            ingresos_cents: null,
          },
        ],
      }),
    );
    const raiz = fixture.nativeElement as HTMLElement;

    const cabeceras = Array.from(raiz.querySelectorAll('thead th')).map((th) =>
      th.textContent?.trim(),
    );
    expect(cabeceras).not.toContain('Por aprobar');
    expect(cabeceras).not.toContain('Ocupación');
    // La tabla sigue: nombre, fecha y estado no dependen de permisos.
    expect(cabeceras).toContain('Evento');
  });

  it('si todo va bien, no hay nada en «requiere tu atención»', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).not.toContain('Requiere tu atención');
  });

  it('el estado del evento lleva su palabra, no solo su color', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('Publicado');
  });

  it('si la carga falla, se avisa', async () => {
    configurarYGuardarHttp();
    const fixture = TestBed.createComponent(DashboardPage);
    await avanzar(fixture);

    http
      .expectOne((p) => p.url === '/api/v1/organizations/me/metrics')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('No se pudieron cargar');
  });

  it('no tiene violaciones de accesibilidad en tema oscuro', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http);
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
  });

  it('no tiene violaciones de accesibilidad en tema claro', async () => {
    configurarYGuardarHttp();
    document.documentElement.setAttribute('data-theme', 'light');
    try {
      const fixture = await montar(http);
      await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });
});
