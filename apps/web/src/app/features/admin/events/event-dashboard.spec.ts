import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { describe, expect, it } from 'vitest';

import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import es from '../../../../../public/assets/i18n/es-ES.json';
import { EventDashboard } from './event-dashboard';
import { EventoMetricas } from './event-metrics.types';

/**
 * El escritorio del evento decide qué pinta **según lo que recibe**: los bloques
 * que la API omite por falta de permiso no existen en la respuesta, y aquí no
 * debe haber una segunda copia de la regla de permisos que pueda divergir de la
 * del servidor.
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

function metricas(overrides: Partial<EventoMetricas> = {}): EventoMetricas {
  return {
    event_id: 'e1',
    embudo: {
      formulario: 100,
      verificado: 80,
      aprobado: 60,
      emitido: 50,
      sin_verificacion_exigida: false,
    },
    ocupacion: { reservadas: 50, aforo: 200 },
    cifras: { por_estado: { confirmed: 50 }, lista_de_espera: 5, por_aprobar: 3, sin_entrar: 12 },
    piezas: [
      { clave: 'agenda', estado: 'lista', cantidad: 4 },
      { clave: 'tipos_de_entrada', estado: 'no_aplica', cantidad: 0 },
    ],
    dinero: {
      ingresos_cobrados_cents: 450000,
      presupuesto_cents: 600000,
      ejecutado_cents: 120000,
      moneda: 'eur',
    },
    ...overrides,
  };
}

/** Deja pendientes las peticiones de las secciones que cuelgan de `EventDetails`. */
function resolverHijas(http: HttpTestingController): void {
  // La carga base del evento: `EventDetails` la pide para la portada y el estado.
  // Sin resolverla, su plantilla evalúa el estado vacío y revienta al
  // capitalizarlo — el fallo se ve en `EventDetails`, pero el origen es esta
  // petición sin contestar.
  const base = http.match((p) => p.url === '/api/v1/events/e1');
  for (const peticion of base) {
    peticion.flush({ cover_url: null, status: 'draft', registration_mode: 'free' });
  }

  for (const peticion of http.match((p) => p.url.startsWith('/api/v1/events/e1'))) {
    if (peticion.request.url === '/api/v1/events/e1/metrics') {
      continue;
    }
    peticion.flush(peticion.request.url.endsWith('/venues') ? [] : { items: [], total: 0 });
  }
  for (const peticion of http.match((p) => p.url.startsWith('/api/v1/organizations/me'))) {
    peticion.flush({ items: [], total: 0, limit: 200, offset: 0 });
  }
}

async function montar(
  http: HttpTestingController,
  cuerpo: EventoMetricas = metricas(),
): Promise<ComponentFixture<EventDashboard>> {
  const fixture = TestBed.createComponent(EventDashboard);
  fixture.componentRef.setInput('eventId', 'e1');
  await avanzar(fixture);

  http.expectOne((p) => p.url === '/api/v1/events/e1/metrics').flush(cuerpo);
  await avanzar(fixture);
  resolverHijas(http);
  await avanzar(fixture);
  return fixture;
}

describe('EventDashboard', () => {
  // `http` se guarda al configurar y no se resuelve con `TestBed.inject` en el
  // `afterEach`: inyectar cuando el módulo de un `describe` vecino aún no se ha
  // configurado deja el TestBed instanciado, y el siguiente que intente
  // configurarlo falla con «already been instantiated».
  let http: HttpTestingController;

  function configurarYGuardarHttp() {
    configurar();
    http = TestBed.inject(HttpTestingController);
  }

  it('pinta el embudo con sus cuatro escalones y la proporción sobre el primero', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http);
    const raiz = fixture.nativeElement as HTMLElement;

    const filas = Array.from(raiz.querySelectorAll('.embudo li'));
    expect(filas.length).toBe(4);
    expect(filas[0].textContent).toContain('100');
    expect(filas[1].textContent).toContain('80');
    expect(filas[3].textContent).toContain('50');

    // La barra del último escalón es la mitad de ancha que la del primero.
    const anchos = filas.map(
      (fila) => (fila.querySelector('.barra > span') as HTMLElement).style.width,
    );
    expect(anchos[0]).toBe('100%');
    expect(anchos[3]).toBe('50%');
  });

  it('sin permiso de inscripciones no pinta ni el embudo ni sus cifras', async () => {
    // La API los omite cuando falta el permiso: no se reciben y se esconden,
    // es que no vienen. Aquí se comprueba que la pantalla no los inventa.
    configurarYGuardarHttp();
    const fixture = await montar(http, metricas({ embudo: null, cifras: null }));
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.querySelector('.embudo')).toBeNull();
    expect(raiz.textContent).not.toContain('Por aprobar');
    // Lo que sí puede ver sigue ahí.
    expect(raiz.textContent).toContain('Ocupación');
  });

  it('sin permiso económico no pinta el bloque de dinero', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http, metricas({ dinero: null }));
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).not.toContain('Ingresos cobrados');
    expect(raiz.textContent).not.toContain('Presupuesto');
  });

  it('un aforo nulo se explica como «sin aforo», no como cero plazas', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http, metricas({ ocupacion: { reservadas: 7, aforo: null } }));
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('7');
    expect(raiz.textContent).not.toContain('/ 200');
    expect(raiz.textContent).toContain('no fija aforo');
  });

  it('avisa solo de las piezas que faltan teniendo que estar', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(
      http,
      metricas({
        piezas: [
          { clave: 'agenda', estado: 'lista', cantidad: 4 },
          { clave: 'tipos_de_entrada', estado: 'no_aplica', cantidad: 0 },
        ],
      }),
    );
    const raiz = fixture.nativeElement as HTMLElement;

    // Ninguna pieza pendiente: no hay aviso que dar.
    expect(raiz.textContent).not.toContain('esto le falta');
  });

  it('cuando algo falta, lo dice y lo enlaza', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(
      http,
      metricas({
        piezas: [{ clave: 'agenda', estado: 'pendiente', cantidad: 0 }],
      }),
    );
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('esto le falta');
    expect(raiz.querySelector('a[href="#agenda"]')).not.toBeNull();
  });

  it('el estado del evento no se lee solo por color: cada pieza lleva su palabra', async () => {
    configurarYGuardarHttp();
    const fixture = await montar(http);
    const raiz = fixture.nativeElement as HTMLElement;

    const piezas = Array.from(raiz.querySelectorAll('.piezas li'));
    expect(piezas.length).toBe(2);
    for (const pieza of piezas) {
      expect(pieza.textContent?.trim().length).toBeGreaterThan(0);
    }
    expect(raiz.textContent).toContain('No aplica');
  });

  it('si las métricas fallan, el error se avisa y las secciones siguen', async () => {
    configurarYGuardarHttp();
    const fixture = TestBed.createComponent(EventDashboard);
    fixture.componentRef.setInput('eventId', 'e1');
    await avanzar(fixture);

    http
      .expectOne((p) => p.url === '/api/v1/events/e1/metrics')
      .flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    await avanzar(fixture);
    resolverHijas(http);
    await avanzar(fixture);
    const raiz = fixture.nativeElement as HTMLElement;

    expect(raiz.textContent).toContain('No se pudieron cargar las cifras');
    // El evento se sigue pudiendo gestionar: sus secciones están debajo.
    expect(raiz.querySelector('app-event-details')).not.toBeNull();
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
