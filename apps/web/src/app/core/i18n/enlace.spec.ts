import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { conPrefijo } from './idioma.service';

describe('conPrefijo', () => {
  it('antepone el prefijo a las rutas públicas absolutas', () => {
    expect(conPrefijo('/', 'en')).toBe('/en');
    expect(conPrefijo('/eventos', 'en')).toBe('/en/eventos');
    expect(conPrefijo(['/', 'acme', 'evento'], 'en')).toEqual(['/', 'en', 'acme', 'evento']);
    expect(conPrefijo(['/ponentes', 'ana'], 'en')).toEqual(['/en/ponentes', 'ana']);
  });

  it('no toca el idioma por defecto, las rutas relativas, los paneles ni otros sitios', () => {
    expect(conPrefijo('/eventos', '')).toBe('/eventos');
    expect(conPrefijo('programa', 'en')).toBe('programa');
    expect(conPrefijo(['programa'], 'en')).toEqual(['programa']);
    expect(conPrefijo('/dashboard/account', 'en')).toBe('/dashboard/account');
    expect(conPrefijo(['/dashboard', 'events'], 'en')).toEqual(['/dashboard', 'events']);
    expect(conPrefijo('//otro.example', 'en')).toBe('//otro.example');
  });
});

/** Todos los `.ts` de una carpeta, sin los specs. */
function fuentes(carpeta: string): string[] {
  return readdirSync(carpeta).flatMap((nombre) => {
    const ruta = join(carpeta, nombre);
    if (statSync(ruta).isDirectory()) {
      return fuentes(ruta);
    }
    return ruta.endsWith('.ts') && !ruta.endsWith('.spec.ts') ? [ruta] : [];
  });
}

describe('enlaces de la parte pública', () => {
  it('ningún routerLink absoluto se escribe sin el pipe `enlace`', () => {
    const carpetas = ['src/app/features/public', 'src/app/layouts/public', 'src/app/shared'];
    const literales = carpetas.flatMap(fuentes).flatMap((fichero) =>
      [...readFileSync(fichero, 'utf-8').matchAll(/(?<!\[)routerLink="(\/[^"]*)"/g)]
        .map((m) => m[1])
        .filter((ruta) => !/^\/(dashboard|admin)\b/.test(ruta))
        .map((ruta) => `${fichero}: ${ruta}`),
    );
    expect(literales).toEqual([]);
  });
});
