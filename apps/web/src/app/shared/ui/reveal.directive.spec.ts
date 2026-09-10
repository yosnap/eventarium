import { Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Reveal } from './reveal.directive';

@Component({
  selector: 'app-anfitrion-reveal',
  imports: [Reveal],
  template: `<p appReveal [index]="indice">Contenido</p>`,
})
class AnfitrionReveal {
  indice = 0;
}

describe('Reveal', () => {
  let fixture: ComponentFixture<AnfitrionReveal>;
  let capturedCallback: IntersectionObserverCallback | null = null;
  let observadoresDesconectados = 0;

  beforeEach(() => {
    capturedCallback = null;
    observadoresDesconectados = 0;
    document.documentElement.classList.remove('js-activo');

    class ObservadorFalso {
      constructor(callback: IntersectionObserverCallback) {
        capturedCallback = callback;
      }
      observe(): void {
        // Intencionalmente vacío: el fake solo necesita capturar el callback.
      }
      unobserve(): void {
        // Intencionalmente vacío: el fake solo necesita capturar el callback.
      }
      disconnect(): void {
        observadoresDesconectados++;
      }
    }
    vi.stubGlobal('IntersectionObserver', ObservadorFalso);

    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(AnfitrionReveal);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.classList.remove('js-activo');
  });

  it('marca <html> como "js-activo" al montar, para que la ocultación por CSS solo aplique con JS confirmado', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    expect(document.documentElement.classList.contains('js-activo')).toBe(true);
  });

  it('añade "es-visible" cuando el observador informa que el elemento entró en pantalla', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    const elemento: HTMLElement = fixture.nativeElement.querySelector('p');
    expect(elemento.classList.contains('es-visible')).toBe(false);

    capturedCallback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as never);
    expect(elemento.classList.contains('es-visible')).toBe(true);
  });

  it('no añade "es-visible" mientras el elemento no ha entrado en pantalla', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    capturedCallback?.([{ isIntersecting: false } as IntersectionObserverEntry], {} as never);
    const elemento: HTMLElement = fixture.nativeElement.querySelector('p');
    expect(elemento.classList.contains('es-visible')).toBe(false);
  });

  it('fija --i a partir de `index`, para el escalonado entre elementos de un mismo grupo', async () => {
    fixture.componentInstance.indice = 3;
    fixture.detectChanges();
    await fixture.whenStable();
    const elemento: HTMLElement = fixture.nativeElement.querySelector('p');
    expect(elemento.style.getPropertyValue('--i')).toBe('3');
  });

  it('desconecta el observador al destruirse, sin dejarlo colgado', async () => {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.destroy();
    expect(observadoresDesconectados).toBe(1);
  });
});
