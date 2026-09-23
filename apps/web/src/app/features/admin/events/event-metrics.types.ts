/**
 * Tipos de las métricas del escritorio de un evento, espejo de
 * `GET /events/{id}/metrics`.
 *
 * Los bloques opcionales son `null` cuando quien consulta no tiene permiso para
 * verlos: la API los omite en el servidor en vez de mandarlos y esconderlos, así
 * que la interfaz no necesita saber de permisos — si el dato no está, no se
 * pinta.
 */

export type EstadoDePieza = 'lista' | 'pendiente' | 'no_aplica';

export interface Embudo {
  readonly formulario: number;
  readonly verificado: number;
  readonly aprobado: number;
  readonly emitido: number;
  /** El evento no exige verificar el correo: «verificado» es igual a «formulario». */
  readonly sin_verificacion_exigida: boolean;
}

export interface Ocupacion {
  /** Plazas reservadas tal como las cuenta el sistema, no solo las confirmadas. */
  readonly reservadas: number;
  /** `null` es «sin aforo», que no es lo mismo que cero plazas. */
  readonly aforo: number | null;
}

export interface PiezaDelEvento {
  readonly clave: string;
  readonly estado: EstadoDePieza;
  readonly cantidad: number;
}

export interface Cifras {
  // Solo trae los estados con alguna inscripción: una clave puede faltar.
  readonly por_estado: Readonly<Partial<Record<string, number>>>;
  readonly lista_de_espera: number;
  readonly por_aprobar: number;
  readonly sin_entrar: number;
}

export interface Dinero {
  readonly ingresos_cobrados_cents: number;
  readonly presupuesto_cents: number;
  readonly ejecutado_cents: number;
  readonly moneda: string;
}

export interface EventoMetricas {
  readonly event_id: string;
  readonly embudo: Embudo | null;
  readonly ocupacion: Ocupacion;
  readonly cifras: Cifras | null;
  readonly piezas: readonly PiezaDelEvento[];
  readonly dinero: Dinero | null;
}
