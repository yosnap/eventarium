import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Apilado, HeroEscena, Parallax, TextoRevelado } from './animaciones.directive';
import { GsapLoader } from './gsap';

const revert = vi.fn();
const add = vi.fn();
const gsapFalso = {
  revert,
  add,
  to: vi.fn(),
  from: vi.fn(),
  fromTo: vi.fn(),
  matchMedia: vi.fn(() => ({ add, revert })),
};

const loaderFalso = {
  cargar: () =>
    Promise.resolve({
      gsap: {
        to: gsapFalso.to,
        from: gsapFalso.from,
        fromTo: gsapFalso.fromTo,
        matchMedia: gsapFalso.matchMedia,
      },
      ScrollTrigger: { refresh: vi.fn() },
    }),
};

@Component({
  imports: [Parallax, HeroEscena, Apilado, TextoRevelado],
  template: `
    <section id="hero" appHeroEscena>
      <div data-hero-contenido>
        <p data-entrada>uno</p>
        <p data-entrada>dos</p>
      </div>
    </section>
    <div class="landing-ilustracion">
      <div id="capa" appParallax="0.5"></div>
    </div>
    <div id="apilado" appApilado>
      <article class="landing-tarjeta" id="t1"></article>
      <article class="landing-tarjeta" id="t2"></article>
      <article class="landing-tarjeta" id="t3"></article>
    </div>
    <p id="texto" appTextoRevelado>Tres palabras aquí</p>
  `,
})
class Anfitrion {}

async function renderizar() {
  const fixture = TestBed.createComponent(Anfitrion);
  fixture.detectChanges();
  await fixture.whenStable();
  await Promise.resolve();
  await Promise.resolve();
  return fixture;
}

function ejecutarCallbacks(): void {
  for (const [, callback] of gsapFalso.add.mock.calls) {
    (callback as () => void)();
  }
}

describe('animaciones de la landing', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: GsapLoader, useValue: loaderFalso }],
    });
    for (const fn of [
      gsapFalso.add,
      gsapFalso.revert,
      gsapFalso.to,
      gsapFalso.from,
      gsapFalso.fromTo,
    ]) {
      fn.mockClear();
    }
  });

  afterEach(() => TestBed.resetTestingModule());

  it('todas se registran solo bajo prefers-reduced-motion: no-preference y sin él no tocan el DOM', async () => {
    const fixture = await renderizar();
    expect(gsapFalso.add).toHaveBeenCalledTimes(4);
    for (const [consulta] of gsapFalso.add.mock.calls) {
      expect(consulta).toBe('(prefers-reduced-motion: no-preference)');
    }
    expect(gsapFalso.to).not.toHaveBeenCalled();
    expect(gsapFalso.from).not.toHaveBeenCalled();
    expect(gsapFalso.fromTo).not.toHaveBeenCalled();
    // El texto sigue siendo texto plano: las palabras solo se envuelven al animar.
    expect(fixture.nativeElement.querySelector('#texto').children).toHaveLength(0);
  });

  it('el parallax de una capa usa la ilustración como disparador y la velocidad indicada', async () => {
    const fixture = await renderizar();
    ejecutarCallbacks();
    const capa = fixture.nativeElement.querySelector('#capa');
    const ilustracion = fixture.nativeElement.querySelector('.landing-ilustracion');
    expect(gsapFalso.fromTo).toHaveBeenCalledWith(
      capa,
      { yPercent: 30 },
      expect.objectContaining({
        yPercent: -30,
        scrollTrigger: expect.objectContaining({
          trigger: ilustracion,
          start: 'clamp(top bottom)',
        }),
      }),
    );
  });

  it('el hero entra escalonado y sale atenuándose con el scroll', async () => {
    const fixture = await renderizar();
    ejecutarCallbacks();
    const piezas = fixture.nativeElement.querySelectorAll('[data-entrada]');
    expect(gsapFalso.from).toHaveBeenCalledWith(
      piezas,
      expect.objectContaining({ opacity: 0, stagger: 0.09, clearProps: 'opacity,transform' }),
    );
    const contenido = fixture.nativeElement.querySelector('[data-hero-contenido]');
    expect(gsapFalso.to).toHaveBeenCalledWith(
      contenido,
      expect.objectContaining({
        scale: 0.94,
        scrollTrigger: expect.objectContaining({ scrub: 0.3 }),
      }),
    );
  });

  it('cada tarjeta apilada se encoge cuando la siguiente le pasa por encima; la última no', async () => {
    const fixture = await renderizar();
    ejecutarCallbacks();
    const [t1, t2, t3] = ['#t1', '#t2', '#t3'].map((id) => fixture.nativeElement.querySelector(id));
    const llamadasApilado = gsapFalso.to.mock.calls.filter(([objetivo]) =>
      [t1, t2, t3].includes(objetivo),
    );
    expect(llamadasApilado.map(([objetivo]) => objetivo)).toEqual([t1, t2]);
    expect(llamadasApilado[0][1]).toEqual(
      expect.objectContaining({
        scale: 0.9,
        scrollTrigger: expect.objectContaining({ trigger: t2, scrub: true }),
      }),
    );
  });

  it('el texto revelado envuelve cada palabra y las enciende con scrub', async () => {
    const fixture = await renderizar();
    ejecutarCallbacks();
    const texto: HTMLElement = fixture.nativeElement.querySelector('#texto');
    expect(texto.querySelectorAll('.landing-palabra')).toHaveLength(3);
    expect(texto.textContent).toBe('Tres palabras aquí');
    expect(gsapFalso.fromTo).toHaveBeenCalledWith(
      texto.querySelectorAll('.landing-palabra'),
      { opacity: 0.22 },
      expect.objectContaining({
        opacity: 1,
        scrollTrigger: expect.objectContaining({ scrub: true }),
      }),
    );
  });

  it('revierte todas las animaciones al destruir el componente', async () => {
    const fixture = await renderizar();
    fixture.destroy();
    expect(gsapFalso.revert).toHaveBeenCalledTimes(4);
  });
});
