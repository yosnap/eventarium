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

import { Parallax } from './animaciones.directive';
import { GsapLoader } from './gsap';

const loaderFalso = {
  cargar: () =>
    Promise.resolve({
      gsap: { to: gsapFalso.to, matchMedia: gsapFalso.matchMedia },
      ScrollTrigger: { refresh: vi.fn() },
    }),
};

@Component({
  imports: [Parallax],
  template: `<div id="capa" appParallax="0.3">capa</div>`,
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

describe('Parallax', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: GsapLoader, useValue: loaderFalso }],
    });
    gsapFalso.add.mockClear();
    gsapFalso.revert.mockClear();
    gsapFalso.to.mockClear();
  });

  afterEach(() => TestBed.resetTestingModule());

  it('registra cada animación solo bajo prefers-reduced-motion: no-preference', async () => {
    await renderizar();
    expect(gsapFalso.add).toHaveBeenCalledTimes(1);
    for (const [consulta] of gsapFalso.add.mock.calls) {
      expect(consulta).toBe('(prefers-reduced-motion: no-preference)');
    }
    // Sin ejecutar el callback (equivale a `reduce`), no hay ningún tween.
    expect(gsapFalso.to).not.toHaveBeenCalled();
    expect(document.querySelectorAll('[style*="transform"], [style*="opacity"]')).toHaveLength(0);
  });

  it('con movimiento permitido crea el parallax con scrub y arranque acotado', async () => {
    const fixture = await renderizar();
    for (const [, callback] of gsapFalso.add.mock.calls) {
      (callback as () => void)();
    }
    const capa = fixture.nativeElement.querySelector('#capa');
    expect(gsapFalso.to).toHaveBeenCalledWith(
      capa,
      expect.objectContaining({
        yPercent: -30,
        scrollTrigger: expect.objectContaining({ scrub: true, start: 'clamp(top bottom)' }),
      }),
    );
  });

  it('revierte las animaciones al destruir el componente', async () => {
    const fixture = await renderizar();
    fixture.destroy();
    expect(gsapFalso.revert).toHaveBeenCalledTimes(1);
  });
});
