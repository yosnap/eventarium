/**
 * Cálculo de contraste según WCAG 2.1.
 *
 * Sirve para avisar en el panel cuando una paleta elegida por el organizador deja
 * texto ilegible: la accesibilidad no puede depender de que acierte con los colores.
 */

/** Mínimo exigido por WCAG 2.1 AA para texto normal. */
export const CONTRASTE_MINIMO_AA = 4.5;

function canalLineal(valor: number): number {
  const proporcion = valor / 255;
  return proporcion <= 0.03928 ? proporcion / 12.92 : ((proporcion + 0.055) / 1.055) ** 2.4;
}

/** Convierte `#rgb` o `#rrggbb` a componentes. Devuelve `null` si no es un hex válido. */
export function parseHexColor(color: string): [number, number, number] | null {
  const limpio = color.trim().replace('#', '');
  const expandido =
    limpio.length === 3
      ? limpio
          .split('')
          .map((c) => c + c)
          .join('')
      : limpio;
  if (!/^[0-9a-f]{6}$/i.test(expandido)) {
    return null;
  }
  return [
    Number.parseInt(expandido.slice(0, 2), 16),
    Number.parseInt(expandido.slice(2, 4), 16),
    Number.parseInt(expandido.slice(4, 6), 16),
  ];
}

export function relativeLuminance(color: string): number | null {
  const rgb = parseHexColor(color);
  if (!rgb) {
    return null;
  }
  const [r, g, b] = rgb.map(canalLineal);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Razón de contraste entre dos colores (de 1:1 a 21:1). `null` si alguno no es hex. */
export function contrastRatio(primero: string, segundo: string): number | null {
  const a = relativeLuminance(primero);
  const b = relativeLuminance(segundo);
  if (a === null || b === null) {
    return null;
  }
  const claro = Math.max(a, b);
  const oscuro = Math.min(a, b);
  return (claro + 0.05) / (oscuro + 0.05);
}

export interface AvisoDeContraste {
  readonly primero: string;
  readonly segundo: string;
  readonly ratio: number;
}

/** Pares de colores que deben ser legibles juntos. */
const PARES_A_COMPROBAR: readonly (readonly [string, string])[] = [
  ['text', 'surface'],
  ['text-muted', 'surface'],
  ['primary-contrast', 'primary'],
  ['text', 'surface-muted'],
];

/** Devuelve los pares de la paleta que no llegan al mínimo AA. */
export function checkBrandingContrast(
  colors: Readonly<Record<string, string>>,
): readonly AvisoDeContraste[] {
  const avisos: AvisoDeContraste[] = [];
  for (const [primero, segundo] of PARES_A_COMPROBAR) {
    const a = colors[primero];
    const b = colors[segundo];
    if (!a || !b) {
      continue;
    }
    const ratio = contrastRatio(a, b);
    if (ratio !== null && ratio < CONTRASTE_MINIMO_AA) {
      avisos.push({ primero, segundo, ratio: Math.round(ratio * 100) / 100 });
    }
  }
  return avisos;
}
