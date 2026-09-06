import { Type } from '@angular/core';

/**
 * Plantillas de la página pública.
 *
 * Cada organización elige la suya con `template_key`. Se cargan de forma perezosa para
 * que el navegador solo descargue la que realmente usa esa organización.
 */
export type TemplateLoader = () => Promise<Type<unknown>>;

export const TEMPLATE_REGISTRY: ReadonlyMap<string, TemplateLoader> = new Map<
  string,
  TemplateLoader
>([
  [
    'classic',
    () => import('../../features/public/home/classic-template').then((m) => m.ClassicTemplate),
  ],
  [
    'minimal',
    () => import('../../features/public/home/minimal-template').then((m) => m.MinimalTemplate),
  ],
]);

export const TEMPLATE_POR_DEFECTO = 'classic';

/** Devuelve el cargador de una plantilla; si la clave no existe, el de `classic`. */
export function resolveTemplate(key: string | null | undefined): TemplateLoader {
  const cargador = key ? TEMPLATE_REGISTRY.get(key) : undefined;
  return cargador ?? TEMPLATE_REGISTRY.get(TEMPLATE_POR_DEFECTO)!;
}

export function templateExists(key: string): boolean {
  return TEMPLATE_REGISTRY.has(key);
}
