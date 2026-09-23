import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';
import { describe, expect, it } from 'vitest';

import { ResaltarPipe } from './resaltar.pipe';

describe('ResaltarPipe', () => {
  function transformar(texto: string): string {
    const pipe = TestBed.runInInjectionContext(() => new ResaltarPipe());
    const seguro = pipe.transform(texto);
    return TestBed.inject(DomSanitizer).sanitize(1, seguro) ?? '';
  }

  it('convierte los marcadores en strong con la clase de resaltado', () => {
    expect(transformar('Organiza con **tu marca**. **Sin comisiones**.')).toBe(
      'Organiza con <strong class="landing-resaltado">tu marca</strong>. <strong class="landing-resaltado">Sin comisiones</strong>.',
    );
  });

  it('escapa cualquier HTML del texto y no admite otras etiquetas', () => {
    expect(transformar('a <b>b</b> & **c**')).toBe(
      'a &lt;b&gt;b&lt;/b&gt; &amp; <strong class="landing-resaltado">c</strong>',
    );
  });

  it('con texto sin marcadores devuelve el texto tal cual', () => {
    expect(transformar('Nada que resaltar')).toBe('Nada que resaltar');
  });
});
