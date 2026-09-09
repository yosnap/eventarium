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

/** Fila del catálogo (`GET /organizations/me/theme-templates`, `admin/theme-templates`). */
export interface PlantillaDeTema {
  readonly id: string;
  readonly key: string;
  readonly name: string;
  readonly tokens: TokensDeTema;
  /** Ausente en el catálogo público (`ThemeTemplateCatalogItem`); presente en la
   * respuesta de superadministración (`ThemeTemplateResponse`), que sí gestiona cuál
   * es la plantilla por defecto. */
  readonly is_default?: boolean;
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
];
