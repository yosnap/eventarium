/** Claves de las funcionalidades, en `publico.landing.funcionalidades.items`. */
export type ClaveFuncionalidad =
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
  readonly clave: ClaveFuncionalidad;
  /** Ruta del panel que muestra la captura (barra de la ventana). */
  readonly ruta: string;
}

/** Orden de aparición en la landing. Solo funcionalidades ya implementadas
 * (PRD de la landing, «Contenido ya verificado»): el texto vive en `es-ES.json`,
 * aquí no hay literales. */
export const FUNCIONALIDADES: readonly FuncionalidadLanding[] = [
  {
    clave: 'inscripciones',
    ruta: '/dashboard/events/…/inscripciones',
  },
  { clave: 'entradas', ruta: '/dashboard/events/…/check-in' },
  { clave: 'marca', ruta: '/dashboard/branding' },
  {
    clave: 'patrocinadores',
    ruta: '/dashboard/events/…/patrocinadores',
  },
  { clave: 'contabilidad', ruta: '/dashboard/events/…/contabilidad' },
  { clave: 'agenda', ruta: '/dashboard/events/…/agenda' },
  { clave: 'ponentes', ruta: '/dashboard/events/…/ponentes' },
  { clave: 'pagos', ruta: '/dashboard/events/…/entradas' },
];

export const ENLACES_LANDING = {
  repositorio: 'https://github.com/yosnap/eventarium',
  instalacion: 'https://github.com/yosnap/eventarium/blob/main/docs/despliegue.md',
  licencia: 'https://github.com/yosnap/eventarium/blob/main/LICENSE',
} as const;
