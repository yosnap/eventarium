/**
 * Cálculo de contraste según WCAG 2.1.
 *
 * Verifica que una plantilla de tema (catálogo de superadministración) es legible en
 * sus dos modos. Ya no existe ninguna paleta elegida por el organizador que comprobar
 * (esa personalización desapareció con el sistema de plantillas): por eso
 * `comprobarContrasteDePlantilla` sustituye al antiguo `checkBrandingContrast`.
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

const PATRON_OKLCH =
  /^oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*([\d.]+%?))?\s*\)$/i;

function linealASrgb(valor: number): number {
  const acotado = Math.max(0, Math.min(1, valor));
  return acotado <= 0.0031308 ? acotado * 12.92 : 1.055 * acotado ** (1 / 2.4) - 0.055;
}

/**
 * Convierte `oklch(L% C H)` (con alfa opcional, ignorado para el contraste: el color
 * se compara ya compuesto sobre su fondo) a componentes sRGB 0-255. `null` si la
 * cadena no encaja con el formato. Misma conversión (OKLab → sRGB lineal → sRGB) que
 * porta `apps/api/app/modules/theme_templates/contrast.py`; los dos parsers se
 * verifican contra la misma tabla de valores conocidos.
 */
export function parseOklchColor(color: string): [number, number, number] | null {
  const coincidencia = PATRON_OKLCH.exec(color.trim());
  if (!coincidencia) {
    return null;
  }
  const L = Number.parseFloat(coincidencia[1]) / 100;
  const C = Number.parseFloat(coincidencia[2]);
  const H = Number.parseFloat(coincidencia[3]);
  if (Number.isNaN(L) || Number.isNaN(C) || Number.isNaN(H)) {
    return null;
  }

  const hRad = (H * Math.PI) / 180;
  const a = C * Math.cos(hRad);
  const b = C * Math.sin(hRad);

  const lPrima = L + 0.3963377774 * a + 0.2158037573 * b;
  const mPrima = L - 0.1055613458 * a - 0.0638541728 * b;
  const sPrima = L - 0.0894841775 * a - 1.291485548 * b;

  const l = lPrima ** 3;
  const m = mPrima ** 3;
  const s = sPrima ** 3;

  const rLineal = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const gLineal = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bLineal = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s;

  return [
    Math.round(linealASrgb(rLineal) * 255),
    Math.round(linealASrgb(gLineal) * 255),
    Math.round(linealASrgb(bLineal) * 255),
  ];
}

/** Hex de 3/6 dígitos u `oklch()`, los dos formatos que entiende este módulo. */
export function parseColor(color: string): [number, number, number] | null {
  return parseHexColor(color) ?? parseOklchColor(color);
}

export function relativeLuminance(color: string): number | null {
  const rgb = parseColor(color);
  if (!rgb) {
    return null;
  }
  const [r, g, b] = rgb.map(canalLineal);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Razón de contraste entre dos colores (de 1:1 a 21:1). `null` si alguno no se parsea. */
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
  readonly modo: 'dark' | 'light';
  readonly ratio: number | null;
}

/**
 * Pares críticos del sistema de tokens (fondo/texto/acento/señales). Único contrato,
 * compartido por el editor de plantillas de superadministración, el spec de
 * `tokens.css` y el spec de las plantillas sembradas. Espejo exacto de
 * `PARES_CRITICOS` en `apps/api/app/modules/theme_templates/contrast.py`.
 * `--faint` no entra: es decorativo y no se exige AA de texto sobre él.
 */
export const PARES_CRITICOS: readonly (readonly [string, string])[] = [
  ['fg', 'bg'],
  ['fg', 'surface'],
  ['muted', 'surface'],
  ['on-accent', 'accent'],
  ['fg', 'surface-2'],
  ['danger', 'surface'],
  ['warn', 'surface'],
];

/**
 * Evalúa `PARES_CRITICOS` sobre el juego de tokens de **un modo** de una plantilla
 * (`tokens.dark` o `tokens.light`, sin el prefijo `--`). Un color que no se pueda
 * parsear es un aviso con `ratio: null`, nunca un descarte silencioso: es la misma
 * clase de fallo silencioso que tenía `contrastRatio` con oklch antes de este parser.
 */
export function comprobarContrasteDePlantilla(
  tokens: Readonly<Record<string, string>>,
  modo: 'dark' | 'light',
): readonly AvisoDeContraste[] {
  const avisos: AvisoDeContraste[] = [];
  for (const [primero, segundo] of PARES_CRITICOS) {
    const a = tokens[primero];
    const b = tokens[segundo];
    if (a === undefined || b === undefined) {
      avisos.push({ primero, segundo, modo, ratio: null });
      continue;
    }
    const ratio = contrastRatio(a, b);
    if (ratio === null) {
      avisos.push({ primero, segundo, modo, ratio: null });
      continue;
    }
    if (ratio < CONTRASTE_MINIMO_AA) {
      avisos.push({ primero, segundo, modo, ratio: Math.round(ratio * 100) / 100 });
    }
  }
  return avisos;
}
