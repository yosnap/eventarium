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
  /** Ruta del panel que muestra la captura (barra de la ventana). */
  readonly ruta: string;
}

/** Orden de aparición en la landing. Solo funcionalidades ya implementadas
 * (PRD de la landing, «Contenido ya verificado»): el texto vive en `es-ES.json`,
 * aquí no hay literales. */
export const FUNCIONALIDADES: readonly FuncionalidadLanding[] = [
  {
    clave: 'inscripciones',
    ilustracion: 'inscripciones',
    ruta: '/dashboard/events/…/inscripciones',
  },
  { clave: 'entradas', ilustracion: 'entradas', ruta: '/dashboard/events/…/check-in' },
  { clave: 'marca', ilustracion: 'marca', ruta: '/dashboard/branding' },
  {
    clave: 'patrocinadores',
    ilustracion: 'patrocinadores',
    ruta: '/dashboard/events/…/patrocinadores',
  },
  { clave: 'contabilidad', ilustracion: 'contabilidad', ruta: '/dashboard/events/…/contabilidad' },
  { clave: 'agenda', ilustracion: 'agenda', ruta: '/dashboard/events/…/agenda' },
  { clave: 'ponentes', ilustracion: 'ponentes', ruta: '/dashboard/events/…/ponentes' },
  { clave: 'pagos', ilustracion: 'pagos', ruta: '/dashboard/events/…/entradas' },
];

export const ENLACES_LANDING = {
  repositorio: 'https://github.com/yosnap/eventarium',
  instalacion: 'https://github.com/yosnap/eventarium/blob/main/docs/despliegue.md',
  licencia: 'https://github.com/yosnap/eventarium/blob/main/LICENSE',
} as const;
