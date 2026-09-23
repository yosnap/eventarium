import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const revert = vi.fn();
const add = vi.fn();
const gsapFalso = {
  revert,
  add,
  to: vi.fn(),
  from: vi.fn(),
  matchMedia: vi.fn(() => ({ add, revert })),
};

import { Entrada, Parallax } from './animaciones.directive';
import { GsapLoader } from './gsap';

const loaderFalso = {
  cargar: () =>
    Promise.resolve({
      gsap: { to: gsapFalso.to, from: gsapFalso.from, matchMedia: gsapFalso.matchMedia },
      ScrollTrigger: { refresh: vi.fn() },
    }),
};

@Component({
  imports: [Parallax, Entrada],
  template: `
    <div id="capa" appParallax="0.3">capa</div>
    <p id="bloque" [appEntrada]="0.2">bloque</p>
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

describe('Parallax y Entrada', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: GsapLoader, useValue: loaderFalso }],
    });
    gsapFalso.add.mockClear();
    gsapFalso.revert.mockClear();
    gsapFalso.to.mockClear();
    gsapFalso.from.mockClear();
  });

  afterEach(() => TestBed.resetTestingModule());

  it('registra cada animación solo bajo prefers-reduced-motion: no-preference', async () => {
    await renderizar();
    expect(gsapFalso.add).toHaveBeenCalledTimes(2);
    for (const [consulta] of gsapFalso.add.mock.calls) {
      expect(consulta).toBe('(prefers-reduced-motion: no-preference)');
    }
    // Sin ejecutar el callback (equivale a `reduce`), no hay ningún tween.
    expect(gsapFalso.to).not.toHaveBeenCalled();
    expect(gsapFalso.from).not.toHaveBeenCalled();
    expect(document.querySelectorAll('[style*="transform"], [style*="opacity"]')).toHaveLength(0);
  });

  it('con movimiento permitido crea el parallax (scrub) y la entrada (once) con sus parámetros', async () => {
    const fixture = await renderizar();
    for (const [, callback] of gsapFalso.add.mock.calls) {
      (callback as () => void)();
    }
    const capa = fixture.nativeElement.querySelector('#capa');
    const bloque = fixture.nativeElement.querySelector('#bloque');
    expect(gsapFalso.to).toHaveBeenCalledWith(
      capa,
      expect.objectContaining({
        yPercent: -30,
        scrollTrigger: expect.objectContaining({ scrub: true }),
      }),
    );
    expect(gsapFalso.from).toHaveBeenCalledWith(
      bloque,
      expect.objectContaining({
        opacity: 0,
        delay: 0.2,
        scrollTrigger: expect.objectContaining({ once: true }),
      }),
    );
  });

  it('revierte las animaciones al destruir el componente', async () => {
    const fixture = await renderizar();
    fixture.destroy();
    expect(gsapFalso.revert).toHaveBeenCalledTimes(2);
  });
});
