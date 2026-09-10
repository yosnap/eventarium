import { isPlatformBrowser } from '@angular/common';
import {
  type AfterViewInit,
  Directive,
  ElementRef,
  Input,
  type OnDestroy,
  PLATFORM_ID,
  inject,
} from '@angular/core';

/**
 * Revelado sutil al entrar en pantalla, sobre `[data-reveal]`/`reveal.js` de la
 * referencia (`eventarium.css:281-294`): opacidad 0→1 y `translateY(14px)→0`
 * la primera vez que el elemento cruza el viewport, con
 * `IntersectionObserver` — no un listener de `scroll` a mano.
 *
 * Dos salvaguardas que la referencia exige explícitamente y que aquí se
 * cumplen igual:
 * - **Sin JavaScript, nada se oculta.** La clase que esconde el contenido
 *   (`.js-activo`) solo se añade a `<html>` cuando esta directiva confirma
 *   que el JS arrancó (ver `reveal-activo.service.ts`); si el bootstrapeo
 *   fallara, el contenido servido por SSR se queda visible.
 * - **`prefers-reduced-motion: reduce` no mueve nada.** La regla vive en
 *   `styles.css` como CSS puro (no aquí): con ese ajuste del sistema, el
 *   contenido aparece ya visible sin transición, sin que esta directiva
 *   necesite saberlo.
 *
 * `index` (opcional) escalona la entrada dentro de un mismo grupo —
 * `--i` en CSS, 70ms por posición, igual que la referencia.
 */
@Directive({
  selector: '[appReveal]',
})
export class Reveal implements AfterViewInit, OnDestroy {
  @Input() index = 0;

  private readonly elementRef = inject(ElementRef<HTMLElement>);
  private readonly plataforma = inject(PLATFORM_ID);
  private observador: IntersectionObserver | null = null;

  ngAfterViewInit(): void {
    if (!isPlatformBrowser(this.plataforma)) {
      return;
    }
    const elemento = this.elementRef.nativeElement;
    elemento.style.setProperty('--i', String(this.index));
    document.documentElement.classList.add('js-activo');

    if (typeof IntersectionObserver === 'undefined') {
      elemento.classList.add('es-visible');
      return;
    }

    this.observador = new IntersectionObserver(
      (entradas) => {
        for (const entrada of entradas) {
          if (entrada.isIntersecting) {
            elemento.classList.add('es-visible');
            this.observador?.unobserve(elemento);
          }
        }
      },
      { threshold: 0.1 },
    );
    this.observador.observe(elemento);
  }

  ngOnDestroy(): void {
    this.observador?.disconnect();
  }
}
