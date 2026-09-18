import { contrastRatio } from './contrast';
import { componentesOklchDeHex } from './oklch';

/**
 * Deriva la familia de acento de una plantilla (accent/accent-hi/accent-dim/
 * on-accent, en los dos modos) a partir de un único color elegido por el
 * organizador de un evento.
 *
 * Puerto directo de `apps/api/app/modules/theme_templates/accent_palette.py`
 * (mismo criterio de portabilidad que `contrast.ts`/`contrast.py` entre sí):
 * los dos lados se prueban contra el mismo fixture de casos conocidos
 * (`tests/fixtures/casos_paleta_acento.json`, fase 3 del plan «diseño del
 * evento») para que no diverjan. Las constantes de abajo deben coincidir
 * EXACTAMENTE con las del lado Python — si se edita una, editar la otra.
 *
 * Ver el docstring del módulo Python para la justificación completa de por
 * qué esto es una aproximación calibrada (no una réplica exacta del tema
 * por defecto de la plataforma) y por qué `CROMA_MAXIMA` es 0.15 y no el
 * 0.2286 del verde de referencia.
 */

/** Por debajo de este croma el matiz no está perceptualmente definido:
 * blanco, negro y cualquier gris darían el mismo resultado sin aviso. */
export const UMBRAL_CROMA_MINIMO = 0.02;

export const CROMA_MAXIMA = 0.15;

export const L_OSCURO_ACCENT = 0.8761;
export const L_OSCURO_ACCENT_HI = 0.94;
export const L_CLARO_ACCENT = 0.45;
export const L_CLARO_ACCENT_HI = 0.52;

export type ModoDeTema = 'dark' | 'light';

export interface PaletaDeAcento {
  readonly dark: Record<string, string>;
  readonly light: Record<string, string>;
}

/** `true` si el color tiene suficiente croma para servir de acento (mismo
 * umbral que el backend) — para rechazar en cliente ANTES de disparar el
 * PATCH, sin esperar al 422. */
export function colorTieneCromaSuficiente(hex: string): boolean {
  const componentes = componentesOklchDeHex(hex);
  return componentes !== null && componentes.C >= UMBRAL_CROMA_MINIMO;
}

/** Blanco o negro, el que cumpla mejor el PEOR de los dos contrastes
 * (contra `accent` y contra `accent-hi` — este último es el fondo real del
 * estado `:hover` de los botones). */
function mejorOnAccent(accent: string, accentHi: string): string {
  const candidatos = ['#ffffff', '#000000'] as const;
  const peorRatio = (candidato: string): number =>
    Math.min(contrastRatio(candidato, accent) ?? 0, contrastRatio(candidato, accentHi) ?? 0);
  return peorRatio(candidatos[0]) >= peorRatio(candidatos[1]) ? candidatos[0] : candidatos[1];
}

/**
 * Deriva `{accent, accent-hi, accent-dim, on-accent}` para `dark` y `light`
 * a partir de un único color hex. Devuelve `null` si el hex no es válido o
 * no tiene croma suficiente (usar `colorTieneCromaSuficiente` para
 * distinguir el caso antes de llamar, si hace falta un mensaje distinto).
 */
export function derivarPaletaDeAcento(hex: string): PaletaDeAcento | null {
  const componentes = componentesOklchDeHex(hex);
  if (!componentes || componentes.C < UMBRAL_CROMA_MINIMO) {
    return null;
  }
  const croma = Math.min(componentes.C, CROMA_MAXIMA);
  const tono = componentes.H;

  const paraModo = (lBase: number, lHi: number): Record<string, string> => {
    const accent = `oklch(${(lBase * 100).toFixed(2)}% ${croma.toFixed(4)} ${tono.toFixed(2)})`;
    const accentHi = `oklch(${(lHi * 100).toFixed(2)}% ${croma.toFixed(4)} ${tono.toFixed(2)})`;
    return {
      accent,
      'accent-hi': accentHi,
      'accent-dim': accent.replace(')', ' / 0.1)'),
      'on-accent': mejorOnAccent(accent, accentHi),
    };
  };

  return {
    dark: paraModo(L_OSCURO_ACCENT, L_OSCURO_ACCENT_HI),
    light: paraModo(L_CLARO_ACCENT, L_CLARO_ACCENT_HI),
  };
}
