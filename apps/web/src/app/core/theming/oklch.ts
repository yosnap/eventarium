import { parseOklchColor } from './contrast';

/**
 * Conversiones bidireccionales entre los formatos de token del sistema
 * (`oklch(...)`, con o sin alfa) y el `#rrggbb` que exige el selector nativo
 * de color. La dirección oklch → sRGB ya vive en `contrast.ts` (compartida y
 * verificada con el backend); aquí solo se añade sRGB → OKLCH y el pegamento
 * de hex.
 */

/** Componentes sRGB 0-255 a sRGB lineal 0-1 (curva inversa de `linealASrgb`). */
function srgbALineal(canal: number): number {
  const v = canal / 255;
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

/** Extrae la alfa textual de un valor oklch (`/ 0.1`), si la lleva. */
function alfaDeOklch(valor: string): string | null {
  const coincidencia = /\/\s*([\d.]+%?)\s*\)$/.exec(valor.trim());
  return coincidencia ? coincidencia[1] : null;
}

/** `oklch(...)` → `#rrggbb`. `null` si el valor no es un color oklch válido. */
export function hexDeOklch(valor: string): string | null {
  const rgb = parseOklchColor(valor);
  if (!rgb) {
    return null;
  }
  return (
    '#' +
    rgb
      .map((canal) => canal.toString(16).padStart(2, '0'))
      .join('')
  );
}

/**
 * `#rrggbb` → `oklch(L% C H)`. Con `alfa`, el resultado lleva `/ alfa`
 * (`oklch(L% C H / 0.1)`) para conservar la transparencia del token original.
 */
export function oklchDeHex(hex: string, alfa: string | null = null): string | null {
  const rgb = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!rgb) {
    return null;
  }
  const r = srgbALineal(parseInt(rgb[1].slice(0, 2), 16));
  const g = srgbALineal(parseInt(rgb[1].slice(2, 4), 16));
  const b = srgbALineal(parseInt(rgb[1].slice(4, 6), 16));

  // sRGB lineal → OKLab (Björn Ottosson), con los coeficientes de referencia.
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);

  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const b2 = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;

  const C = Math.sqrt(a * a + b2 * b2);
  let H = (Math.atan2(b2, a) * 180) / Math.PI;
  if (H < 0) {
    H += 360;
  }

  const conAlfa = alfa ? ` / ${alfa}` : '';
  return `oklch(${(L * 100).toFixed(1)}% ${C.toFixed(3)} ${H.toFixed(2)}${conAlfa})`;
}

/**
 * Hex para pintar el selector nativo de un valor de token: `#rrggbb` si el
 * valor ya lo es, la conversión si es `oklch(...)`, y `null` si no es
 * coloreable (las sombras, valores vacíos) — quien llama decide el fallback.
 * La alfa se descarta: el selector siempre abre con el color opaco.
 */
export function hexParaSelector(valor: string): string | null {
  const limpio = valor.trim();
  if (/^#[0-9a-f]{6}$/i.test(limpio)) {
    return limpio.toLowerCase();
  }
  return hexDeOklch(limpio);
}

/** Alfa textual del token, para reconstruirla al elegir en el selector. */
export function alfaDe(valor: string): string | null {
  return /^oklch\(/i.test(valor.trim()) ? alfaDeOklch(valor) : null;
}
