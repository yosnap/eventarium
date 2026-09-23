/** Ilustración dibujada en CSS que acompaña a cada funcionalidad (fase 3). */
export type Ilustracion =
  | 'quienes'
  | 'inscripciones'
  | 'entradas'
  | 'marca'
  | 'patrocinadores'
  | 'contabilidad'
  | 'agenda'
  | 'ponentes'
  | 'pagos';

export interface FuncionalidadLanding {
  /** Clave bajo `publico.landing.funcionalidades.items`. */
  readonly clave: Ilustracion;
  readonly ilustracion: Ilustracion;
}

/** Orden de aparición en la landing. Solo funcionalidades ya implementadas
 * (PRD de la landing, «Contenido ya verificado»): el texto vive en `es-ES.json`,
 * aquí no hay literales. */
export const FUNCIONALIDADES: readonly FuncionalidadLanding[] = [
  { clave: 'inscripciones', ilustracion: 'inscripciones' },
  { clave: 'entradas', ilustracion: 'entradas' },
  { clave: 'marca', ilustracion: 'marca' },
  { clave: 'patrocinadores', ilustracion: 'patrocinadores' },
  { clave: 'contabilidad', ilustracion: 'contabilidad' },
  { clave: 'agenda', ilustracion: 'agenda' },
  { clave: 'ponentes', ilustracion: 'ponentes' },
  { clave: 'pagos', ilustracion: 'pagos' },
];

export const ENLACES_LANDING = {
  repositorio: 'https://github.com/yosnap/eventarium',
  instalacion: 'https://github.com/yosnap/eventarium/blob/main/docs/despliegue.md',
  licencia: 'https://github.com/yosnap/eventarium/blob/main/LICENSE',
} as const;
