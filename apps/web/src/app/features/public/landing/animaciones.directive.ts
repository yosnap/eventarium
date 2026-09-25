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
 * Carga GSAP tras el primer render (nunca en SSR ni antes de hidratar, así el
 * HTML servido no depende de la librería), registra la animación bajo
 * `gsap.matchMedia()` y la revierte entera al destruir el elemento —
 * `revert()` mata los ScrollTriggers y limpia los estilos inline, así que al
 * navegar fuera de la landing no queda nada a medias.
 */
abstract class AnimacionConScroll {
  protected readonly elemento: HTMLElement = inject(ElementRef).nativeElement;
  /** Cuándo se anima. Una directiva puede restringirlo (p. ej. solo en pantallas anchas). */
  protected readonly consulta: string = SIN_REDUCIR_MOVIMIENTO;

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
        contexto.add(this.consulta, () => this.animar(gsap));
      });
    });
  }

  protected abstract animar(gsap: GsapCargado): void;
}

/**
 * Parallax ligado al scroll: el elemento se desplaza verticalmente a una
 * fracción de su recorrido por la ventana (`appParallax="0.3"` → ±18 % de su
 * alto entre que entra por abajo y sale por arriba).
 */
@Directive({ selector: '[appParallax]' })
export class Parallax extends AnimacionConScroll {
  readonly velocidad = input(0.25, { alias: 'appParallax', transform: numberAttribute });

  protected animar({ gsap }: GsapCargado): void {
    gsap.fromTo(
      this.elemento,
      { yPercent: this.velocidad() * 60 },
      {
        yPercent: -this.velocidad() * 60,
        ease: 'none',
        scrollTrigger: {
          trigger: this.elemento,
          // `clamp()`: lo que ya está en pantalla al cargar (el hero) empieza en
          // progreso 0 en vez de saltar al valor calculado para su posición.
          start: 'clamp(top bottom)',
          end: 'clamp(bottom top)',
          scrub: 0.4,
        },
      },
    );
  }
}

/** Ventana, desde que el hero se crea, en la que su entrada aún tiene sentido:
 * si GSAP llega más tarde (red lenta), el visitante ya está leyendo y reiniciar
 * la escena sería un parpadeo, no una entrada. Se mide desde la creación del
 * hero y no desde la carga del documento: al volver a la landing navegando
 * dentro de la web, el documento lleva ya mucho tiempo abierto. */
const MARGEN_ENTRADA_MS = 2500;

/**
 * Escena del hero: entrada escalonada de sus piezas (`[data-entrada]`, en
 * orden de documento) nada más cargar, y salida ligada al scroll — se atenúa,
 * se encoge y sube mientras el visitante empieza a bajar, al estilo de las
 * portadas de producto.
 */
@Directive({ selector: '[appHeroEscena]' })
export class HeroEscena extends AnimacionConScroll {
  private readonly creadoEn = performance.now();

  protected animar({ gsap }: GsapCargado): void {
    const piezas = this.elemento.querySelectorAll<HTMLElement>('[data-entrada]');
    if (piezas.length > 0 && performance.now() - this.creadoEn < MARGEN_ENTRADA_MS) {
      gsap.from(piezas, {
        opacity: 0,
        y: 28,
        duration: 0.9,
        ease: 'power3.out',
        stagger: 0.09,
        clearProps: 'opacity,transform',
      });
    }
    const contenido = this.elemento.querySelector<HTMLElement>('[data-hero-contenido]');
    if (contenido) {
      gsap.to(contenido, {
        opacity: 0.15,
        scale: 0.94,
        yPercent: -8,
        ease: 'none',
        scrollTrigger: {
          trigger: this.elemento,
          start: 'clamp(top top)',
          end: 'clamp(bottom 30%)',
          scrub: 0.3,
        },
      });
    }
  }
}

/**
 * Tarjetas apiladas (`.landing-tarjeta`, `position: sticky` por CSS): cuando
 * la siguiente tarjeta sube y se le monta encima, la anterior se encoge en
 * proporción al scroll, de modo que se ve cómo se van apilando. Sin atenuarla:
 * con opacidad, su contenido se transparentaba bajo la tarjeta que sube; la
 * nueva la tapa del todo (su fondo es opaco).
 */
@Directive({ selector: '[appApilado]' })
export class Apilado extends AnimacionConScroll {
  /**
   * Solo desde 48rem, igual que el `sticky` de las tarjetas: en móvil cada
   * tarjeta (texto y captura en columna) es más alta que la pantalla, y
   * apilarla hacía que la siguiente tapase la captura antes de verse.
   */
  protected override readonly consulta = `${SIN_REDUCIR_MOVIMIENTO} and (min-width: 48rem)`;

  protected animar({ gsap }: GsapCargado): void {
    const tarjetas = Array.from(this.elemento.querySelectorAll<HTMLElement>('.landing-tarjeta'));
    tarjetas.forEach((tarjeta, indice) => {
      const siguiente = tarjetas[indice + 1];
      if (!siguiente) return;
      gsap.to(tarjeta, {
        scale: 0.9,
        yPercent: -6,
        ease: 'none',
        transformOrigin: 'center top',
        scrollTrigger: {
          trigger: siguiente,
          start: 'top bottom',
          end: 'top top+=120',
          scrub: true,
        },
      });
    });
  }
}

/**
 * Texto que se «enciende» palabra a palabra con el scroll: cada palabra pasa de
 * atenuada a color pleno según el bloque cruza la ventana. Puede aplicarse a
 * un párrafo o a un contenedor con varios: en ese caso es una sola animación
 * y las palabras se encienden en orden de lectura, de principio a fin, en vez
 * de encenderse todos los párrafos a la vez. Las palabras se
 * envuelven en `<span>` solo aquí, ya hidratado, así que el HTML servido es
 * texto plano normal. Solo se tocan los nodos de texto: el marcado que ya
 * tenga el párrafo (el `<strong>` del resaltado) se conserva.
 */
@Directive({ selector: '[appTextoRevelado]' })
export class TextoRevelado extends AnimacionConScroll {
  protected animar({ gsap }: GsapCargado): void {
    const recorrido = document.createTreeWalker(this.elemento, NodeFilter.SHOW_TEXT);
    const nodos: Text[] = [];
    while (recorrido.nextNode()) nodos.push(recorrido.currentNode as Text);
    for (const nodo of nodos) {
      const trozos = (nodo.textContent ?? '').split(/(\s+)/).filter((t) => t.length > 0);
      nodo.replaceWith(
        ...trozos.map((trozo) => {
          if (/^\s+$/.test(trozo)) return document.createTextNode(trozo);
          const span = document.createElement('span');
          span.textContent = trozo;
          span.className = 'landing-palabra';
          return span;
        }),
      );
    }
    gsap.fromTo(
      this.elemento.querySelectorAll('.landing-palabra'),
      { opacity: 0.22 },
      {
        opacity: 1,
        ease: 'none',
        stagger: 0.05,
        scrollTrigger: {
          trigger: this.elemento,
          start: 'top 85%',
          end: 'bottom 45%',
          scrub: true,
        },
      },
    );
  }
}
