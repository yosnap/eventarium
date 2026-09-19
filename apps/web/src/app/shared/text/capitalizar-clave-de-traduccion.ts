/**
 * Convierte una clave `snake_case` o de una sola palabra en el sufijo
 * `PascalCase` que concatenan las plantillas para formar una clave de
 * `transloco` (p. ej. `'admin.events.agenda.tipo' + capitalizarClaveDeTraduccion('talk')`
 * → `'admin.events.agenda.tipoTalk'`, o con `'en_especie'` →
 * `'...tipoEnEspecie'`).
 *
 * Antes había cuatro copias de esta función (una por cada pantalla que
 * capitaliza un valor de enumeración para armar su clave de traducción), y
 * una de ellas (`event-sponsors.ts`) intentaba cubrir el caso `snake_case`
 * con un `.replace('_', '')` que quitaba el guion bajo pero no ponía en
 * mayúscula la letra siguiente — para `en_especie` producía `Enespecie` en
 * vez de `EnEspecie`, sin coincidir con la clave real del JSON de idioma.
 */
export function capitalizarClaveDeTraduccion(valor: string): string {
  return valor
    .split('_')
    .map((parte) => (parte.length > 0 ? parte.charAt(0).toUpperCase() + parte.slice(1) : parte))
    .join('');
}
