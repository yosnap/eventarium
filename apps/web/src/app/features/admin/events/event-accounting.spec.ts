import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { EventAccounting } from './event-accounting';

const BASE = '/api/v1/accounting/events/e1';

function resumen(sobreescritura: Partial<Record<string, unknown>> = {}) {
  return {
    event_id: 'e1',
    budget_approved_at: null,
    total_budgeted_cents: 100_000,
    contingency_fund_percent: '5.00',
    contingency_fund_cents: 5_000,
    consumido_contingencia_cents: 1_000,
    disponible_contingencia_cents: 4_000,
    gasto_sin_partida_cents: 0,
    ejecutado_en_especie_cents: 2_000,
    por_partida: [
      { budget_line_id: 'bl1', ejecutado_cents: 60_000, budgeted_cents: 100_000, exceso_cents: 0 },
    ],
    evolucion_temporal: [{ periodo: '2026-09', ingresos_cents: 80_000, gastos_cents: 60_000 }],
    ...sobreescritura,
  };
}

function ingresos() {
  return {
    ingresos: [
      {
        origen: 'subvencion',
        concepto: 'Ayuntamiento',
        importe_cents: 80_000,
        fecha: '2026-09-01T00:00:00Z',
        peso_sobre_el_total: '1.000000',
        referencia_id: 'i1',
      },
    ],
    comprometido: [],
    total_ingresos_cents: 80_000,
    moneda: 'eur',
    ingresos_excluidos_por_moneda: 0,
  };
}

function lineas() {
  return [{ id: 'bl1', event_id: 'e1', name: 'Catering', budgeted_cents: 100_000, sort_order: 0 }];
}

function gastos() {
  return [
    {
      id: 'g1',
      event_id: 'e1',
      budget_line_id: 'bl1',
      sponsor_id: null,
      provider_name: 'Proveedor real',
      expense_date: '2026-09-05T00:00:00Z',
      base_cents: 50_000,
      vat_cents: 10_000,
      total_cents: 60_000,
    },
  ];
}

async function avanzar(fixture: ComponentFixture<unknown>): Promise<void> {
  await fixture.whenStable();
  fixture.detectChanges();
}

/**
 * `Promise.all` de cuatro peticiones añade varios saltos de microtarea más
 * que un único `firstValueFrom`: un solo `avanzar()` no basta siempre para
 * que el `finally` que apaga `cargando` llegue a ejecutarse antes de mirar
 * el DOM. Se repite hasta que el efecto se refleja, con un tope para no
 * colgar el test si de verdad hay un error.
 */
async function avanzarHastaQueTermineLaCarga(fixture: ComponentFixture<unknown>): Promise<void> {
  for (let intento = 0; intento < 5; intento += 1) {
    await avanzar(fixture);
  }
}

/**
 * Los tres `tabpanel` de movimientos se renderizan siempre en el DOM y se
 * ocultan con `[hidden]` (patrón WCAG del roving tabindex), así que
 * `nativeElement.textContent` incluye el contenido de las tres pestañas a la
 * vez y no sirve para comprobar cuál está activa. Este helper aísla el único
 * panel sin `hidden` y falla explícitamente si no hay exactamente uno.
 */
function panelVisible(fixture: ComponentFixture<unknown>): HTMLElement {
  const paneles = (fixture.nativeElement as HTMLElement).querySelectorAll(
    '[role="tabpanel"]',
  ) as NodeListOf<HTMLElement>;
  const visibles = Array.from(paneles).filter((panel) => !panel.hidden);
  expect(visibles.length).toBe(1);
  return visibles[0];
}

function flushCarga(http: HttpTestingController): void {
  http.expectOne((p) => p.url === `${BASE}/budget/summary` && p.method === 'GET').flush(resumen());
  http.expectOne((p) => p.url === `${BASE}/incomes` && p.method === 'GET').flush(ingresos());
  http.expectOne((p) => p.url === `${BASE}/budget-lines` && p.method === 'GET').flush(lineas());
  http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'GET').flush(gastos());
}

/**
 * La bandeja de justificantes pide su listado en cuanto la pantalla pinta el
 * resumen (antes no existe en el DOM), así que va después de `flushCarga` y
 * de su ronda de detección de cambios.
 */
function flushJustificantes(http: HttpTestingController, borradores: unknown[] = []): void {
  http.expectOne((p) => p.url === `${BASE}/expense-drafts` && p.method === 'GET').flush(borradores);
}

describe('EventAccounting', () => {
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

  it('carga el resumen y renderiza los bloques principales sin violaciones de accesibilidad', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Catering');
    // «Proveedor real» (pestaña «Gastos») está en el DOM aunque oculta con
    // `[hidden]`, pero no en la pestaña activa por defecto («Ingresos»): lo
    // cubre `panelVisible()` en el test de cambio de pestaña.
    expect(texto).toContain('Ayuntamiento');
    await esperarSinViolacionesDeAccesibilidad(fixture.nativeElement);
    // Esta pantalla monta ocho bloques y axe los recorre enteros: con la
    // máquina cargada se pasa de los 5 s por defecto sin que nada esté mal.
  }, 20_000);

  it('muestra los KPI calculados a partir del resumen y los ingresos', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    // Presupuesto: 1000.00 €
    expect(texto).toContain('1000.00');
    // Ingresos: 800.00 €
    expect(texto).toContain('800.00');
  });

  it('cambia de pestaña entre ingresos, gastos y en especie', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const botones = fixture.nativeElement.querySelectorAll(
      '[role="tab"]',
    ) as NodeListOf<HTMLButtonElement>;
    expect(botones.length).toBe(3);

    botones[1].click();
    await avanzar(fixture);
    expect(panelVisible(fixture).id).toBe('movimiento-panel-gastos');
    expect(panelVisible(fixture).textContent).toContain('Proveedor real');
  });

  it('las tres pestañas de movimientos son alcanzables por teclado (flechas, WCAG 2.1.1)', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const botones = fixture.nativeElement.querySelectorAll(
      '[role="tab"]',
    ) as NodeListOf<HTMLButtonElement>;
    expect(botones.length).toBe(3);
    // Solo la pestaña activa (por defecto, «Ingresos») está en el orden de
    // tabulación: roving tabindex, no las tres a la vez.
    expect(botones[0].tabIndex).toBe(0);
    expect(botones[1].tabIndex).toBe(-1);
    expect(botones[2].tabIndex).toBe(-1);

    botones[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    await avanzar(fixture);
    expect(botones[1].getAttribute('aria-selected')).toBe('true');
    expect(botones[1].tabIndex).toBe(0);
    expect(botones[0].tabIndex).toBe(-1);
    expect(document.activeElement).toBe(botones[1]);
    expect(panelVisible(fixture).id).toBe('movimiento-panel-gastos');
    expect(panelVisible(fixture).textContent).toContain('Proveedor real');

    botones[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    await avanzar(fixture);
    expect(botones[2].getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(botones[2]);

    // Flecha derecha en la última pestaña vuelve a la primera (wrap-around).
    botones[2].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    await avanzar(fixture);
    expect(botones[0].getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(botones[0]);

    botones[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    await avanzar(fixture);
    expect(botones[2].getAttribute('aria-selected')).toBe('true');
    expect(document.activeElement).toBe(botones[2]);
  });

  it('muestra «Ejecutado en metálico», «Ejecutado en especie» y «Saldo» como KPI separados', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    // Ejecutado en metálico: 60000 cents (única partida) = 600.00 €.
    expect(texto).toContain('600.00');
    // Ejecutado en especie (resumen): 2000 cents = 20.00 €.
    expect(texto).toContain('20.00');
    // Saldo = 800.00 (ingresos) - (600.00 metálico + 20.00 especie) = 180.00 €.
    expect(texto).toContain('180.00');
  });

  it('muestra un error si la carga del resumen falla', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    http
      .expectOne((p) => p.url === `${BASE}/budget/summary` && p.method === 'GET')
      .flush({ detail: 'error' }, { status: 500, statusText: 'Error' });
    http.expectOne((p) => p.url === `${BASE}/incomes` && p.method === 'GET').flush(ingresos());
    http.expectOne((p) => p.url === `${BASE}/budget-lines` && p.method === 'GET').flush(lineas());
    http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'GET').flush(gastos());
    await avanzarHastaQueTermineLaCarga(fixture);

    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeTruthy();
  });

  it('una partida que se pasa del presupuesto se marca con warn, aviso en cabecera y consumo de contingencia', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    http
      .expectOne((p) => p.url === `${BASE}/budget/summary` && p.method === 'GET')
      .flush(
        resumen({
          consumido_contingencia_cents: 30_000,
          disponible_contingencia_cents: -25_000,
          por_partida: [
            {
              budget_line_id: 'bl1',
              ejecutado_cents: 60_000,
              budgeted_cents: 100_000,
              exceso_cents: 0,
            },
            {
              budget_line_id: null,
              ejecutado_cents: 50_000,
              budgeted_cents: 20_000,
              exceso_cents: 30_000,
            },
          ],
        }),
      );
    http.expectOne((p) => p.url === `${BASE}/incomes` && p.method === 'GET').flush(ingresos());
    http.expectOne((p) => p.url === `${BASE}/budget-lines` && p.method === 'GET').flush(lineas());
    http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'GET').flush(gastos());
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    // Aviso de cabecera del panel de presupuesto, en singular.
    expect(texto).toContain('Una partida se ha pasado');
    // El desglose de contingencia nombra la partida que se pasó y su exceso.
    expect(texto).toContain('Sin partida · se pasó de 200.00 € a 500.00 €');
    expect(texto).toContain('− 300.00 €');
    // El raíl de contingencia anuncia las dos cifras reales, no solo color.
    expect(texto).toContain('300.00 € consumidos');

    // La fila pasada lleva la clase de warn y su porcentaje también.
    const filaSobre = fixture.nativeElement.querySelector('.part.sobre') as HTMLElement;
    expect(filaSobre).not.toBeNull();
    expect(filaSobre.querySelector('.pct.sobre')).not.toBeNull();
  });

  it('la previsión de cierre muestra cobrado, pagado y caja hoy derivados de los datos', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    // La vista de ingresos incluye una valoración en especie: cuenta como
    // ingreso en el libro, pero la foto de caja la excluye.
    const base = ingresos();
    const ingresosConEspecie = {
      ...base,
      ingresos: [
        ...base.ingresos,
        {
          origen: 'patrocinio' as const,
          concepto: 'Patrocinio en especie — Localia',
          importe_cents: 20_000,
          fecha: null,
          peso_sobre_el_total: '0.200000',
          referencia_id: 'sp1',
          en_especie: true,
        },
      ],
    };
    http
      .expectOne((p) => p.url === `${BASE}/budget/summary` && p.method === 'GET')
      .flush(resumen());
    http
      .expectOne((p) => p.url === `${BASE}/incomes` && p.method === 'GET')
      .flush(ingresosConEspecie);
    http.expectOne((p) => p.url === `${BASE}/budget-lines` && p.method === 'GET').flush(lineas());
    http.expectOne((p) => p.url === `${BASE}/expenses` && p.method === 'GET').flush(gastos());
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Cobrado');
    expect(texto).toContain('Pagado');
    expect(texto).toContain('Caja hoy');
    // Cobrado = 800.00 (solo bancario: la especie de 200.00 no entra) ·
    // Pagado = 600.00 (metálico) · Caja = +200.00.
    expect(texto).toContain('+ 200.00 €');
    // El pie de ingresos SÍ suma la especie (total del libro, no de caja).
    expect(texto).toContain('Total de ingresos');
  });

  it('las tablas de movimientos muestran su pie de totales', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const texto = fixture.nativeElement.textContent as string;
    expect(texto).toContain('Total de ingresos');
    expect(texto).toContain('800.00 €');
    expect(texto).toContain('Total de gastos en metálico');
    expect(texto).toContain('600.00 €');
    expect(texto).toContain('Total valorado en especie');
  });

  it('monta el alta por justificante junto al alta manual, no dentro de ella', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http);
    await avanzar(fixture);

    const alta = fixture.nativeElement.querySelector('app-expense-form') as HTMLElement;
    const justificantes = fixture.nativeElement.querySelector(
      'app-receipt-drafts-panel',
    ) as HTMLElement;
    expect(justificantes).not.toBeNull();
    expect(alta.contains(justificantes)).toBe(false);
  });

  it('confirmar un justificante recarga las cifras del libro', async () => {
    const fixture = TestBed.createComponent(EventAccounting);
    fixture.componentRef.setInput('eventId', 'e1');
    fixture.detectChanges();
    await avanzar(fixture);

    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    flushJustificantes(http, [
      {
        id: 'd1',
        event_id: 'e1',
        status: 'pending_review',
        error_code: null,
        ocr_provider: 'openai/gpt-4o-mini',
        receipt_object_key: 'orgs/o1/accounting-receipts/abc.pdf',
        rasterized_object_key: null,
        extracted_fields: {
          provider_name: 'Catering SL',
          expense_date: '2026-09-05',
          base_cents: 10_000,
          vat_cents: 2_100,
          total_cents: 12_100,
          currency: 'EUR',
        },
        field_confidence: {
          provider_name: 'alta',
          expense_date: 'alta',
          base_cents: 'alta',
          vat_cents: 'alta',
          total_cents: 'alta',
          currency: 'alta',
        },
        attempts: 1,
        confirmed_expense_id: null,
        created_at: '2026-09-05T10:00:00Z',
      },
    ]);
    await avanzar(fixture);

    const formularioDeRevision = fixture.nativeElement.querySelector(
      'app-receipt-review-form form',
    ) as HTMLFormElement;
    formularioDeRevision.dispatchEvent(new Event('submit'));
    await avanzar(fixture);

    http.expectOne('/api/v1/accounting/expense-drafts/d1/confirm').flush({ id: 'g1' });
    await avanzarHastaQueTermineLaCarga(fixture);

    // El gasto nuevo obliga a releer resumen, ingresos, partidas y gastos.
    flushCarga(http);
    await avanzarHastaQueTermineLaCarga(fixture);
    // La recarga repinta la pantalla entera, así que la bandeja vuelve a
    // pedir su listado al montarse de nuevo.
    flushJustificantes(http);
    await avanzarHastaQueTermineLaCarga(fixture);

    expect(fixture.nativeElement.textContent).toContain('Gasto dado de alta desde el justificante');
  });
});
