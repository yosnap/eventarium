/**
 * Tipos y formateadores compartidos por `event-accounting.ts` y sus paneles,
 * calcados del payload JSON que devuelve la API (snake_case tal cual).
 */

export interface ContingencyLine {
  readonly budget_line_id: string | null;
  readonly ejecutado_cents: number;
  readonly budgeted_cents: number;
  readonly exceso_cents: number;
}

export interface TimeSeriesPoint {
  readonly periodo: string;
  readonly ingresos_cents: number;
  readonly gastos_cents: number;
}

export interface BudgetSummary {
  readonly event_id: string;
  readonly budget_approved_at: string | null;
  readonly total_budgeted_cents: number;
  readonly contingency_fund_percent: string;
  readonly contingency_fund_cents: number | null;
  readonly consumido_contingencia_cents: number;
  readonly disponible_contingencia_cents: number | null;
  readonly gasto_sin_partida_cents: number;
  readonly ejecutado_en_especie_cents: number;
  readonly por_partida: readonly ContingencyLine[];
  readonly evolucion_temporal: readonly TimeSeriesPoint[];
}

export interface IncomeLine {
  readonly origen: 'patrocinio' | 'entradas' | 'subvencion';
  readonly concepto: string;
  readonly importe_cents: number;
  readonly fecha: string | null;
  readonly referencia_id: string;
  /** True en las valoraciones en especie: cuenta como ingreso pero nunca
   * pasa por el banco. Opcional porque la API solo lo sirve desde la versión
   * que lo añadió — ausente se trata como cobro bancario. */
  readonly en_especie?: boolean;
}

export interface IncomesView {
  readonly ingresos: readonly IncomeLine[];
  readonly comprometido: readonly IncomeLine[];
  readonly total_ingresos_cents: number;
  readonly moneda: string;
}

export interface BudgetLine {
  readonly id: string;
  readonly event_id: string;
  readonly name: string;
  readonly budgeted_cents: number;
  readonly sort_order: number;
}

export interface Expense {
  readonly id: string;
  readonly event_id: string;
  readonly budget_line_id: string | null;
  readonly sponsor_id: string | null;
  readonly provider_name: string;
  readonly expense_date: string;
  readonly base_cents: number;
  readonly vat_cents: number | null;
  readonly total_cents: number;
}

/** Un movimiento de ingreso, ya marcado como cobrado o comprometido — la
 * fusión de `IncomesView.ingresos` y `.comprometido` que usa la pestaña de
 * movimientos. */
export interface IngresoCombinado extends IncomeLine {
  readonly cobrado: boolean;
}

export function euros(cents: number): string {
  return (cents / 100).toFixed(2);
}

/** Cifra con signo explícito, para las líneas de previsión (`+`/`−`). */
export function eurosConSigno(cents: number): string {
  const signo = cents > 0 ? '+ ' : cents < 0 ? '− ' : '';
  return `${signo}${euros(Math.abs(cents))} €`;
}

/** Nombre de una partida por id, con el rótulo de «sin partida» ya traducido
 * cuando no hay id (fin de línea común a todos los paneles de contabilidad). */
export function nombreDePartida(
  lineas: readonly BudgetLine[],
  budgetLineId: string | null,
  etiquetaSinPartida: string,
): string {
  if (budgetLineId === null) {
    return etiquetaSinPartida;
  }
  return lineas.find((l) => l.id === budgetLineId)?.name ?? etiquetaSinPartida;
}
