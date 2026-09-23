import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Meta } from '@angular/platform-browser';
import { beforeEach, describe, expect, it } from 'vitest';

import { IMAGEN_OG_POR_DEFECTO, SeoMetaService } from './meta.service';

describe('SeoMetaService', () => {
  let seo: SeoMetaService;
  let meta: Meta;

  const contenido = (selector: string): string | null | undefined =>
    meta.getTag(selector)?.getAttribute('content');

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    seo = TestBed.inject(SeoMetaService);
    meta = TestBed.inject(Meta);
  });

  it('usa la tarjeta de la plataforma, en URL absoluta, si la página no trae imagen', () => {
    seo.set({ title: 'Landing' });

    const esperada = new URL(IMAGEN_OG_POR_DEFECTO, `${location.origin}/`).href;
    expect(contenido('property="og:image"')).toBe(esperada);
    expect(contenido('name="twitter:image"')).toBe(esperada);
    expect(contenido('name="twitter:card"')).toBe('summary_large_image');
  });

  it('respeta la imagen propia y no la arrastra a la página siguiente', () => {
    seo.set({ title: 'Evento', image: 'https://cdn.example.org/portada.jpg' });
    expect(contenido('property="og:image"')).toBe('https://cdn.example.org/portada.jpg');

    seo.set({ title: 'Sesión' });
    expect(contenido('property="og:image"')).toContain(IMAGEN_OG_POR_DEFECTO);
  });

  it('la tarjeta por defecto existe en public/', () => {
    expect(existsSync(join(process.cwd(), 'public', IMAGEN_OG_POR_DEFECTO))).toBe(true);
  });
});
