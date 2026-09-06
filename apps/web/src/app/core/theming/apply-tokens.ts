import { Branding } from './branding.model';

/**
 * Traduce el branding a custom properties CSS.
 *
 * La API devuelve claves como `primary` o `text-muted`; en CSS viven como
 * `--color-primary` y `--color-text-muted`. Las fuentes siguen la misma regla con el
 * prefijo `--font-`.
 */
export function brandingToCssVariables(branding: Branding): Record<string, string> {
  const variables: Record<string, string> = {};

  for (const [clave, valor] of Object.entries(branding.colors ?? {})) {
    if (esValorSeguro(valor)) {
      variables[`--color-${clave}`] = valor;
    }
  }
  for (const [clave, valor] of Object.entries(branding.fonts ?? {})) {
    if (esValorSeguro(valor)) {
      variables[`--font-${clave}`] = valor;
    }
  }
  return variables;
}

/**
 * Un valor de branding acaba dentro de una hoja de estilo, así que se rechaza todo lo
 * que pueda cerrar la declaración o abrir una regla nueva. El branding lo edita el
 * organizador, no un tercero, pero no hay motivo para confiar en él a ciegas.
 */
function esValorSeguro(valor: unknown): valor is string {
  return (
    typeof valor === 'string' &&
    valor.length > 0 &&
    valor.length <= 200 &&
    !/[;{}<>]/.test(valor) &&
    !/url\s*\(/i.test(valor) &&
    !/expression\s*\(/i.test(valor)
  );
}

/** Aplica el branding al documento. Solo tiene efecto en el navegador. */
export function applyTokens(branding: Branding, documento: Document): void {
  const raiz = documento.documentElement;
  for (const [propiedad, valor] of Object.entries(brandingToCssVariables(branding))) {
    raiz.style.setProperty(propiedad, valor);
  }
}

/** Bloque `<style>` equivalente, para inyectarlo en el HTML servido por SSR. */
export function brandingToStyleBlock(branding: Branding): string {
  const declaraciones = Object.entries(brandingToCssVariables(branding))
    .map(([propiedad, valor]) => `${propiedad}:${valor};`)
    .join('');
  return `:root{${declaraciones}}`;
}
