import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { PLATFORM_ID, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { MarkdownSeguro } from './markdown-seguro';

async function montar(
  texto: string,
  plataforma: 'browser' | 'server' = 'browser',
): Promise<HTMLElement> {
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), { provide: PLATFORM_ID, useValue: plataforma }],
  });
  const fixture = TestBed.createComponent(MarkdownSeguro);
  fixture.componentRef.setInput('texto', texto);
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('MarkdownSeguro', () => {
  it('conserva apartados, listas y enlaces', async () => {
    const raiz = await montar(
      '## Reembolsos\n\n### Plazos\n\n- **Uno**\n\n[web](https://ejemplo.com)',
    );
    expect(raiz.querySelector('h2')?.textContent).toBe('Reembolsos');
    expect(raiz.querySelector('h3')?.textContent).toBe('Plazos');
    expect(raiz.querySelector('li strong')?.textContent).toBe('Uno');
    expect(raiz.querySelector('a')?.getAttribute('href')).toBe('https://ejemplo.com');
  });

  it('descarta h1, scripts, iframes y atributos de evento', async () => {
    const raiz = await montar(
      '# Título\n\n<script>alert(1)</script><iframe src="x"></iframe>' +
        '<img src="x" onerror="alert(1)"><p onclick="alert(1)">Texto</p>',
    );
    expect(raiz.querySelector('h1, script, iframe, img')).toBeNull();
    expect(raiz.innerHTML).not.toContain('onclick');
    expect(raiz.innerHTML).not.toContain('onerror');
    expect(raiz.textContent).toContain('Texto');
  });

  it('en el servidor pinta texto plano escapado, nunca HTML', async () => {
    const raiz = await montar('## Título <b>negrita</b>', 'server');
    expect(raiz.querySelector('h2, b')).toBeNull();
    expect(raiz.textContent).toContain('## Título <b>negrita</b>');
  });
});

/**
 * La barrera solo sirve si nadie la esquiva. Cualquier forma de meter HTML en
 * el DOM fuera de `markdown-seguro.ts` tiene que ser el pipe `resaltar` de la
 * landing, que solo recibe textos fijos de `es-ES.json` y los escapa antes de
 * generar `<strong>`: un texto escrito por una organización nunca puede
 * llegar ahí.
 */
describe('HTML sin sanear en la aplicación', () => {
  const raiz = join(import.meta.dirname, '..', '..');
  const ficheros = readdirSync(raiz, { recursive: true, encoding: 'utf-8' })
    .filter((fichero) => /\.(ts|html)$/.test(fichero) && !fichero.endsWith('.spec.ts'))
    .filter((fichero) => !fichero.startsWith(join('core', 'api', 'generated')))
    .map((fichero) => ({ nombre: fichero, texto: readFileSync(join(raiz, fichero), 'utf-8') }));
  const BARRERA = join('shared', 'legal', 'markdown-seguro.ts');
  const PIPE_DE_TEXTOS_FIJOS = join('features', 'public', 'landing', 'resaltar.pipe.ts');

  it('[innerHTML] solo en la barrera de saneado o con el pipe de textos fijos', () => {
    const infractores = ficheros.flatMap(({ nombre, texto }) =>
      nombre === BARRERA
        ? []
        : (texto.match(/\[innerHTML\]\s*=\s*(["'])[^"']*\1/g) ?? [])
            .filter((binding) => !/\|\s*resaltar\s*["']$/.test(binding))
            .map((binding) => `${nombre}: ${binding}`),
    );
    expect(infractores).toEqual([]);
  });

  it('nadie asigna .innerHTML ni se salta el saneador de Angular fuera de su sitio', () => {
    const infractores = ficheros
      .filter(({ texto }) => /\.innerHTML\s*=[^=]|bypassSecurityTrustHtml/.test(texto))
      .map(({ nombre }) => nombre)
      .filter((nombre) => nombre !== PIPE_DE_TEXTOS_FIJOS);
    expect(infractores).toEqual([]);
  });
});
