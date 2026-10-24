/**
 * Idiomas que el backend acepta en `locale` de la cuenta (espejo del `Locale` de
 * `apps/api/app/core/locale.py`). Distinto de `availableLangs` de Transloco a propósito:
 * un idioma de interfaz que el backend aún no conozca no debe romper el alta con un 422.
 */
export const LOCALES_DE_CUENTA = ['es-ES', 'en-US'] as const;
export type LocaleDeCuenta = (typeof LOCALES_DE_CUENTA)[number];

export function localeDeCuenta(activo: string | null | undefined): LocaleDeCuenta {
  return (LOCALES_DE_CUENTA as readonly string[]).includes(activo ?? '')
    ? (activo as LocaleDeCuenta)
    : 'es-ES';
}
