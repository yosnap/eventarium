import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { GsapLoader } from './gsap';

describe('GsapLoader', () => {
  beforeAll(() => {
    // jsdom no implementa matchMedia y ScrollTrigger lo consulta al registrarse.
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
      })),
    );
  });

  it('devuelve null fuera del navegador sin importar la librería', async () => {
    TestBed.configureTestingModule({ providers: [{ provide: PLATFORM_ID, useValue: 'server' }] });
    expect(await TestBed.inject(GsapLoader).cargar()).toBeNull();
  });

  it('en navegador carga gsap con ScrollTrigger registrado y reutiliza la carga', async () => {
    TestBed.configureTestingModule({ providers: [{ provide: PLATFORM_ID, useValue: 'browser' }] });
    const loader = TestBed.inject(GsapLoader);
    const resultado = await loader.cargar();
    expect(resultado?.ScrollTrigger).toBeTruthy();
    expect(typeof resultado?.gsap.to).toBe('function');
    expect(await loader.cargar()).toBe(resultado);
  });
});
