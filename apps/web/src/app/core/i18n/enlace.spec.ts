import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { conPrefijo } from './idioma.service';

describe('conPrefijo', () => {
  it('pone el prefijo y traduce los segmentos fijos de la ruta', () => {
    expect(conPrefijo('/', 'en-US')).toBe('/en');
    expect(conPrefijo('/eventos', 'en-US')).toBe('/en/events');
    expect(conPrefijo('/legal/privacidad', 'en-US')).toBe('/en/legal/privacy');
    expect(conPrefijo(['/', 'acme', 'evento'], 'en-US')).toEqual(['/en/acme/evento']);
    expect(conPrefijo(['/', 'acme', 'evento', 'programa'], 'en-US')).toEqual([
      '/en/acme/evento/schedule',
    ]);
    expect(conPrefijo(['/ponentes', 'ana'], 'en-US')).toEqual(['/en/speakers/ana']);
  });

  it('no traduce los identificadores aunque coincidan con una palabra', () => {
    expect(conPrefijo(['/', 'acme', 'programa'], 'en-US')).toEqual(['/en/acme/programa']);
  });

  it('no toca el idioma por defecto, las rutas relativas, los paneles ni otros sitios', () => {
    expect(conPrefijo('/eventos', 'es-ES')).toBe('/eventos');
    expect(conPrefijo('programa', 'en-US')).toBe('programa');
    expect(conPrefijo(['programa'], 'en-US')).toEqual(['programa']);
    expect(conPrefijo('/dashboard/account', 'en-US')).toBe('/dashboard/account');
    expect(conPrefijo(['/dashboard', 'events'], 'en-US')).toEqual(['/dashboard', 'events']);
    expect(conPrefijo('//otro.example', 'en-US')).toBe('//otro.example');
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
