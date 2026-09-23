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
 * Base común: carga GSAP tras el primer render (nunca en SSR ni antes de
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
        start: 'top bottom',
        end: 'bottom top',
        scrub: true,
      },
    });
  }
}

/**
 * Entrada al llegar a pantalla: opacidad y 24 px de subida, una sola vez.
 * `gsap.from` aplica el estado inicial en el mismo instante en que se crea el
 * tween (ya con JS vivo y sin `reduce`), nunca desde el CSS servido.
 */
@Directive({ selector: '[appEntrada]' })
export class Entrada extends AnimacionConScroll {
  readonly retardo = input(0, { alias: 'appEntrada', transform: numberAttribute });

  protected animar({ gsap }: GsapCargado): void {
    gsap.from(this.elemento, {
      opacity: 0,
      y: 24,
      duration: 0.6,
      delay: this.retardo(),
      ease: 'power2.out',
      scrollTrigger: { trigger: this.elemento, start: 'top 85%', once: true },
    });
  }
}
