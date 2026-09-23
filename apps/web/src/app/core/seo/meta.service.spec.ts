import { existsSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Meta, Title } from '@angular/platform-browser';
import { beforeEach, describe, expect, it } from 'vitest';

import { IMAGEN_OG_POR_DEFECTO, SeoMetaService, seoDePagina } from './meta.service';

@Component({ selector: 'app-pagina-publica', template: '' })
class PaginaPublica {
  readonly seo = seoDePagina();
}

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

  it('una respuesta que llega con la página ya cerrada no pisa el título de la siguiente', () => {
    const anterior = TestBed.createComponent(PaginaPublica);
    anterior.destroy();
    seo.set({ title: 'Sesión' });

    anterior.componentInstance.seo.set({ title: 'Evento A' });

    expect(TestBed.inject(Title).getTitle()).toBe('Sesión');
    expect(contenido('property="og:title"')).toBe('Sesión');
  });
});
