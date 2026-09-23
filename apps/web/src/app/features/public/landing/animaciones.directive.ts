import {
  DestroyRef,
  Directive,
  ElementRef,
  afterNextRender,
  inject,
  input,
  numberAttribute,
} from '@angular/core';

import { type GsapCargado, GsapLoader } from './gsap';

/** Solo se anima cuando el sistema no pide reducir el movimiento. Bajo
 * `reduce` no se crea ningún tween ni ScrollTrigger: el contenido queda tal
 * como lo sirvió el SSR. */
const SIN_REDUCIR_MOVIMIENTO = '(prefers-reduced-motion: no-preference)';

/**
 * Carga GSAP tras el primer render (nunca en SSR ni antes de
 * hidratar, así el HTML servido no depende de la librería), registra la
 * animación bajo `gsap.matchMedia()` y la revierte entera al destruir el
 * elemento — `revert()` mata los ScrollTriggers y limpia los estilos inline,
 * así que al navegar fuera de la landing no queda nada a medias.
 */
abstract class AnimacionConScroll {
  protected readonly elemento: HTMLElement = inject(ElementRef).nativeElement;

  constructor() {
    const destroyRef = inject(DestroyRef);
    const carga = inject(GsapLoader).cargar();
    afterNextRender(() => {
      let contexto: ReturnType<GsapCargado['gsap']['matchMedia']> | null = null;
      let destruido = false;
      destroyRef.onDestroy(() => {
        destruido = true;
        contexto?.revert();
      });
      void carga.then((gsap) => {
        if (!gsap || destruido) return;
        contexto = gsap.gsap.matchMedia();
        contexto.add(SIN_REDUCIR_MOVIMIENTO, () => this.animar(gsap));
      });
    });
  }

  protected abstract animar(gsap: GsapCargado): void;
}

/**
 * Parallax ligado al scroll: el elemento se desplaza verticalmente a una
 * fracción de la velocidad de la página (`appParallax="0.3"` → 30 % del alto
 * de la ventana a lo largo de su recorrido). Solo `transform`, con `scrub`.
 */
@Directive({ selector: '[appParallax]' })
export class Parallax extends AnimacionConScroll {
  readonly velocidad = input(0.25, { alias: 'appParallax', transform: numberAttribute });

  protected animar({ gsap }: GsapCargado): void {
    gsap.to(this.elemento, {
      yPercent: -this.velocidad() * 100,
      ease: 'none',
      scrollTrigger: {
        trigger: this.elemento,
        // `clamp()`: lo que ya está en pantalla al cargar (el hero) empieza en
        // progreso 0 en vez de saltar al valor calculado para su posición.
        start: 'clamp(top bottom)',
        end: 'clamp(bottom top)',
        scrub: true,
      },
    });
  }
}
