import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { type ComponentFixture, TestBed } from '@angular/core/testing';
import { Title } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { TranslocoTestingModule } from '@jsverse/transloco';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import es from '../../../../../public/assets/i18n/es-ES.json';
import { GsapLoader } from './gsap';
import { esperarSinViolacionesDeAccesibilidad } from '../../../../testing/axe';
import { LandingPage } from './landing-page';

async function renderizar(): Promise<{
  fixture: ComponentFixture<LandingPage>;
  raiz: HTMLElement;
}> {
  const fixture = TestBed.createComponent(LandingPage);
  fixture.detectChanges();
  TestBed.inject(HttpTestingController)
    .expectOne((peticion) => peticion.url === '/api/v1/public/events')
    .flush([]);
  await fixture.whenStable();
  fixture.detectChanges();
  return { fixture, raiz: fixture.nativeElement };
}

describe('LandingPage', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [
        TranslocoTestingModule.forRoot({
          langs: { 'es-ES': es },
          translocoConfig: { availableLangs: ['es-ES'], defaultLang: 'es-ES' },
          preloadLangs: true,
        }),
      ],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        // GSAP no se carga en jsdom (matchMedia no existe): la animación no es
        // objeto de estos specs.
        { provide: GsapLoader, useValue: { cargar: () => Promise.resolve(null) } },
      ],
    });
  });

  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
    document.documentElement.removeAttribute('data-theme');
  });

  it('renderiza las seis secciones del PRD con un único h1 y las dos llamadas a la acción', async () => {
    const { raiz } = await renderizar();

    expect(raiz.querySelectorAll('h1')).toHaveLength(1);
    expect(raiz.querySelector('h1')?.textContent).toContain(
      es.publico.landing.hero.titulo.replaceAll('**', ''),
    );
    expect(raiz.querySelectorAll('h1 strong.landing-resaltado').length).toBeGreaterThan(0);
    expect(raiz.querySelectorAll('section')).toHaveLength(5);
    const titulos = Array.from(raiz.querySelectorAll('h2')).map((h) => h.textContent?.trim());
    expect(titulos).toContain(es.publico.landing.enDirecto.titulo);
    expect(titulos).toContain(es.publico.landing.quienesSomos.titulo.replaceAll('**', ''));
    expect(titulos).toContain(es.publico.landing.funcionalidades.titulo.replaceAll('**', ''));
    expect(titulos.some((t) => t?.startsWith(es.publico.landing.colaborar.titulo))).toBe(true);
    expect(raiz.querySelectorAll('article')).toHaveLength(8);
    expect(raiz.querySelector('a[href="/crear-organizacion"]')).not.toBeNull();
    expect(raiz.querySelector('a[href="/eventos"]')).not.toBeNull();
    expect(TestBed.inject(Title).getTitle()).toBe(es.publico.landing.seo.titulo);
  });

  it('las imágenes son las dos fotos (hero, quiénes somos) y las 16 capturas del panel', async () => {
    const { raiz } = await renderizar();
    expect(raiz.querySelectorAll('video, picture')).toHaveLength(0);
    const fotos = Array.from(raiz.querySelectorAll<HTMLImageElement>('.landing-foto img'));
    expect(fotos.map((img) => img.getAttribute('src'))).toEqual([
      'assets/landing/hero.webp',
      'assets/landing/quienes-somos.webp',
    ]);
    const capturas = Array.from(raiz.querySelectorAll<HTMLImageElement>('app-landing-captura img'));
    expect(capturas).toHaveLength(16);
    for (const img of capturas) {
      expect(img.getAttribute('src')).toMatch(
        /^assets\/landing\/capturas\/[a-z]+-(claro|oscuro)\.webp$/,
      );
      expect(img.getAttribute('alt')).toBeTruthy();
      expect(img.getAttribute('loading')).toBe('lazy');
    }
  });

  it.each(['light', 'dark'])('no tiene violaciones de accesibilidad en tema %s', async (tema) => {
    document.documentElement.setAttribute('data-theme', tema);
    const { raiz } = await renderizar();
    await esperarSinViolacionesDeAccesibilidad(raiz);
  });
});
