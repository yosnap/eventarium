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

/** Nivel de confianza de un campo extraído de un justificante. Tres niveles
 * cerrados, nunca un porcentaje: `FieldConfidence` del backend. */
export type NivelDeConfianza = 'alta' | 'media' | 'baja';

/** Estados del borrador de gasto (`CHECK` de `accounting_expense_drafts`).
 * La bandeja solo lista los cuatro primeros: los confirmados ya son un gasto
 * y los descartados no existen. `en_extraccion` es el estado mientras el
 * worker está a mitad de la llamada al modelo — visualmente indistinguible
 * de `pending_extraction` ("Leyendo"), la panel lo trata igual. */
export type EstadoDeDraft =
  | 'pending_extraction'
  | 'en_extraccion'
  | 'pending_review'
  | 'extraction_failed'
  | 'confirmed'
  | 'discarded';

/** Taxonomía cerrada de `error_code` de la pasarela de IA. Cada valor tiene su
 * propio mensaje en `es-ES.json`, y solo `limite_superado` se puede reintentar
 * a mano (los demás darían exactamente el mismo resultado). */
export type ErrorDeExtraccion =
  | 'servicio_desactivado'
  | 'sin_configuracion'
  | 'limite_superado'
  | 'credencial_ilegible'
  | 'proveedor_error'
  | 'modelo_sin_vision'
  | 'clave_rechazada'
  | 'payload_invalido'
  | 'reserva_abandonada';

/** El único `error_code` que la pantalla ofrece reintentar: se agotó el
 * presupuesto de IA y basta con ampliarlo (fase 4, R3). */
export const ERROR_REINTENTABLE: ErrorDeExtraccion = 'limite_superado';

/** Los dos `error_code` que se arreglan desde la configuración de IA de la
 * organización, no reintentando. */
export const ERRORES_DE_CONFIGURACION: readonly ErrorDeExtraccion[] = [
  'sin_configuracion',
  'servicio_desactivado',
];

/** Lo que el modelo leyó. Entrada **no confiable**: una propuesta que una
 * persona corrige y confirma. Un campo de confianza baja llega en `null` a
 * propósito, para que se teclee en vez de darlo por bueno. */
export interface CamposExtraidos {
  readonly provider_name: string | null;
  readonly expense_date: string | null;
  readonly base_cents: number | null;
  readonly vat_cents: number | null;
  readonly total_cents: number | null;
  readonly currency: string | null;
}

export interface ReceiptDraft {
  readonly id: string;
  readonly event_id: string;
  readonly status: EstadoDeDraft;
  readonly error_code: string | null;
  /** `ai_gateway` mientras está pendiente; `"{proveedor}/{modelo}"` efectivo
   * en cuanto la extracción termina. */
  readonly ocr_provider: string;
  readonly receipt_object_key: string;
  /** Solo si hubo que rasterizar un PDF: es la imagen que vio el modelo, y
   * por eso es la que se previsualiza. */
  readonly rasterized_object_key: string | null;
  readonly extracted_fields: CamposExtraidos;
  readonly field_confidence: Readonly<Record<string, NivelDeConfianza>>;
  readonly attempts: number;
  readonly confirmed_expense_id: string | null;
  readonly created_at: string;
}

/** Centinela de `ocr_provider` mientras no se sabe qué modelo lo leerá. */
export const MOTOR_PENDIENTE = 'ai_gateway';

export function euros(cents: number): string {
  return (cents / 100).toFixed(2);
}

/**
 * Convierte «1.234,56» o «1234.56» a céntimos. `null` si no es un número.
 *
 * Vive aquí, y no dentro de un formulario, porque el alta manual y la revisión
 * de un justificante tienen que redondear los céntimos **exactamente igual**:
 * dos copias divergirían en el redondeo y el mismo importe entraría con un
 * céntimo de diferencia según por dónde se diera de alta.
 */
export function aCents(texto: string): number | null {
  if (!texto.trim()) {
    return null;
  }
  const valor = Number(texto.replace(',', '.'));
  return Number.isFinite(valor) ? Math.round(valor * 100) : null;
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
