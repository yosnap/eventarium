/**
 * Tipos del escritorio de la plataforma, espejo de `GET /admin/metrics`.
 *
 * Este fichero no tiene —ni puede tener— ningún campo monetario: el
 * administrador de la instalación no ve el negocio de las organizaciones. La
 * frontera la sostiene el esquema del servidor, que es un allowlist cerrado con
 * un test que lo comprueba; aquí se refleja.
 */

export interface SaludDeLaInstalacion {
  readonly database: string;
  readonly storage: string;
  readonly redis: string;
}

export interface CifrasDeLaInstalacion {
  readonly organizaciones_activas: number;
  readonly organizaciones_totales: number;
  readonly eventos_totales: number;
  readonly eventos_publicados: number;
  readonly usuarios: number;
  readonly miembros: number;
}

export interface ActividadDeOrganizacion {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly is_active: boolean;
  readonly eventos: number;
  readonly eventos_publicados: number;
  readonly inscripciones: number;
  readonly miembros: number;
  /** `null` es «no consta», no una fecha lejana. */
  readonly evento_mas_reciente: string | null;
  readonly ultimo_evento_creado: string | null;
  readonly ultima_inscripcion: string | null;
  readonly ultimo_acceso: string | null;
  readonly stripe_conectada: boolean;
  readonly tiene_stripe_pendiente_con_eventos_de_pago: boolean;
  readonly publicados_sin_inscripciones: boolean;
}

export interface MetricasDePlataforma {
  readonly salud: SaludDeLaInstalacion;
  readonly cifras: CifrasDeLaInstalacion;
  readonly organizaciones: readonly ActividadDeOrganizacion[];
}
