/**
 * Estilo visual determinista por posición de sede, reutilizado en toda la
 * página de programa multisede (tarjetas del hero, filtro, cabecera de la
 * parrilla, bloques de sesión y vista de lista).
 *
 * Sobre `.vdot[data-v="..."]`/`.ses[data-v="..."]` de la referencia
 * (`evento-multisede.html:17-20,47-49`): el prototipo fija 3 slugs de sede
 * ("naves"/"marina"/"campus") con un estilo cada uno — acento sólido, gris
 * sólido, hueco con borde fuerte. Aquí las sedes son UUIDs dinámicos del
 * backend, no slugs fijos, así que el estilo se deriva de la **posición** de
 * la sede dentro de la lista completa del evento (`PublicEventDetail.venues`,
 * en su orden real), nunca de la lista ya filtrada por el visitante — para
 * que el color de una sede no cambie según qué otras estén visibles en ese
 * momento.
 */
export interface EstiloDeSede {
  readonly relleno: string;
  readonly borde: string;
}

const PALETA: readonly EstiloDeSede[] = [
  { relleno: 'var(--accent)', borde: 'var(--accent)' },
  { relleno: 'var(--muted)', borde: 'var(--muted)' },
  { relleno: 'transparent', borde: 'var(--fg)' },
  { relleno: 'var(--warn)', borde: 'var(--warn)' },
];

/** Cicla la paleta si hay más sedes que estilos definidos: mejor repetir un
 * estilo que dejar una sede sin color. */
export function estiloDeSede(indice: number): EstiloDeSede {
  return PALETA[indice % PALETA.length];
}
