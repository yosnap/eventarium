/**
 * Contrato del catálogo de plantillas de tema.
 *
 * Cada plantilla es un juego completo de tokens de color/chrome en sus dos modos.
 * Espaciado, radios, familias y escala tipográfica no entran aquí: siguen siendo de
 * plataforma (`tokens.css`/`typography.css`), no elegibles por plantilla.
 */

/** Juego de tokens de un solo modo, claves sin el prefijo `--`. */
export type TokensDePlantilla = Readonly<Record<string, string>>;

export interface TokensDeTema {
  readonly dark: TokensDePlantilla;
  readonly light: TokensDePlantilla;
}

/** Fila del catálogo (`GET /organizations/me/theme-templates`, `admin/theme-templates`).
 *
 * `is_default`/`default_mode` opcionales por compatibilidad con consumidores
 * antiguos del tipo, pero desde la fase 1 del plan «diseño del evento» los
 * expone también `ThemeTemplateCatalogItem` (antes solo `ThemeTemplateResponse`
 * de superadministración) — la pantalla de Diseño del evento los necesita
 * para resolver en cliente la cadena evento→organización→catálogo. */
export interface PlantillaDeTema {
  readonly id: string;
  readonly key: string;
  readonly name: string;
  readonly tokens: TokensDeTema;
  readonly is_default?: boolean;
  /** El modo con el que abre quien no ha elegido todavía ('dark' | 'light'). */
  readonly default_mode?: string;
}

/**
 * Lista blanca de nombres de token, sin el prefijo `--`. Contrato de dos lados con
 * `TOKENS_DE_PLANTILLA` en `apps/api/app/modules/theme_templates/models.py`: un token
 * fuera de esta lista es un 422 en el backend y se ignora aquí. Debe cubrir exactamente
 * las familias de color/chrome que declara `tokens.css` (ver su cabecera).
 */
export const TOKENS_DE_PLANTILLA: readonly string[] = [
  'bg',
  'surface',
  'surface-2',
  'surface-hi',
  'border',
  'border-strong',
  'fg',
  'muted',
  'faint',
  'accent',
  'accent-hi',
  'accent-dim',
  'on-accent',
  'warn',
  'warn-dim',
  'danger',
  'danger-dim',
  'nav-bg',
  'backdrop',
  'shadow-md',
  'shadow-lg',
  'font-display',
  'font-body',
];

/** Tokens que no son un color suelto sino un `box-shadow` completo: no tienen
 * selector de color, se editan por texto (mismo contrato que el backend). */
export const TOKENS_DE_SOMBRA: readonly string[] = ['shadow-md', 'shadow-lg'];

/** Tokens tipográficos de la plantilla: van en ambos modos con el mismo valor
 * (la tipografía no cambia con el tema) y se eligen de las familias
 * autoalojadas, no se escriben a mano. */
export const TOKENS_DE_FUENTE: readonly string[] = ['font-display', 'font-body'];

/** Familias autoalojadas que una plantilla puede declarar, por rol. Contrato
 * de dos lados con `FAMILIAS_DE_FUENTE` de `theme_templates/schemas.py`. */
export const FAMILIAS_DISPLAY: readonly string[] = [
  'Bebas Neue',
  'Archivo Black',
  'Oswald',
  'Playfair Display',
];

export const FAMILIAS_BODY: readonly string[] = ['DM Sans', 'Inter', 'Lora'];

/** Las claves de fuente admitidas por token (`font-display` → FAMILIAS_DISPLAY). */
export const FAMILIAS_POR_TOKEN: Readonly<Record<string, readonly string[]>> = {
  'font-display': FAMILIAS_DISPLAY,
  'font-body': FAMILIAS_BODY,
};
