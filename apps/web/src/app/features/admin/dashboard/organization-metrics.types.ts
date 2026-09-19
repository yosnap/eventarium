/**
 * Tipos del escritorio de la organización, espejo de
 * `GET /organizations/me/metrics`.
 *
 * Los bloques opcionales son `null` cuando quien consulta no tiene permiso para
 * verlos. Igual que en las métricas de un evento, `ingresos_cents` de cada fila
 * también puede ser `null` aunque el bloque de dinero no venga: la columna se
 * omite en la misma consulta.
 */

export interface EventoDelEscritorio {
  readonly id: string;
  readonly title: string;
  readonly slug: string;
  readonly status: string;
  readonly starts_at: string;
  /** `null` es «este evento no fija aforo», no cero plazas. */
  readonly aforo: number | null;
  /** `null` cuando falta `registrations:read`: la columna ni se pide al servidor. */
  readonly confirmadas: number | null;
  readonly por_aprobar: number | null;
  readonly ingresos_cents: number | null;
}

export interface CifrasDeOrganizacion {
  readonly eventos_por_estado: Readonly<Record<string, number>>;
  readonly inscripciones_por_estado: Readonly<Record<string, number>>;
  readonly reservadas: number;
  readonly aforo_total: number | null;
  readonly por_aprobar: number;
  readonly lista_de_espera: number;
}

export interface EstructuraDeOrganizacion {
  readonly miembros: number;
  readonly roles: number;
  readonly patrocinadores: number;
}

export interface DineroDeOrganizacion {
  readonly por_moneda: Readonly<Record<string, number>>;
  readonly presupuesto_por_moneda: Readonly<Record<string, number>>;
  readonly ejecutado_por_moneda: Readonly<Record<string, number>>;
}

export interface EstadoDeStripe {
  readonly conectada: boolean;
  readonly charges_enabled: boolean;
  readonly payouts_enabled: boolean;
  readonly details_submitted: boolean;
}

export interface MetricasDeOrganizacion {
  readonly eventos_en_borrador: number;
  readonly eventos: readonly EventoDelEscritorio[];
  readonly cifras: CifrasDeOrganizacion | null;
  readonly estructura: EstructuraDeOrganizacion;
  readonly dinero: DineroDeOrganizacion | null;
  readonly stripe: EstadoDeStripe;
}
