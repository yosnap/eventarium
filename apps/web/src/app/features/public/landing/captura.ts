import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Captura real del panel dentro de una «ventana» dibujada en CSS. Se sirven las
 * dos versiones (clara y oscura, `assets/landing/capturas/<nombre>-<tema>.webp`)
 * y el tema activo decide cuál se ve: `:root` es oscuro por defecto y
 * `[data-theme='light']` conmuta al claro (styles/tokens.css). Las capturas se
 * regeneran con las herramientas de desarrollo cuando cambie el panel.
 */
@Component({
  selector: 'app-landing-captura',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <figure class="ventana">
      <div class="barra" aria-hidden="true">
        <span class="punto"></span><span class="punto"></span><span class="punto"></span>
        <span class="direccion">{{ ruta() }}</span>
      </div>
      <img
        class="captura captura--oscuro"
        [src]="'assets/landing/capturas/' + nombre() + '-oscuro.webp'"
        [alt]="alt()"
        width="1184"
        height="823"
        loading="lazy"
        decoding="async"
      />
      <img
        class="captura captura--claro"
        [src]="'assets/landing/capturas/' + nombre() + '-claro.webp'"
        [alt]="alt()"
        width="1184"
        height="823"
        loading="lazy"
        decoding="async"
      />
    </figure>
  `,
  styles: `
    :host {
      display: block;
    }
    .ventana {
      margin: 0;
      overflow: hidden;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-lg);
      background: var(--surface-2);
      box-shadow: var(--shadow-lg);
    }
    .barra {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.55rem 0.75rem;
      border-bottom: 1px solid var(--border);
      background: var(--surface-hi);
    }
    .punto {
      width: 0.6rem;
      height: 0.6rem;
      border-radius: 50%;
      background: var(--border-strong);
    }
    .direccion {
      margin-left: 0.5rem;
      padding: 0.15rem 0.6rem;
      border-radius: 999px;
      background: var(--surface);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      color: var(--muted);
    }
    .captura {
      display: block;
      width: 100%;
      height: auto;
    }
    /* En móvil la tarjeta apilada tiene que caber entera en la pantalla: la
       captura se recorta por abajo (como una ventana con scroll) en vez de
       empujar la tarjeta más allá del borde inferior. */
    @media (max-width: 47.99rem) {
      .captura {
        max-height: 25svh;
        object-fit: cover;
        object-position: top;
      }
    }
    .captura--claro {
      display: none;
    }
    :host-context([data-theme='light']) .captura--claro {
      display: block;
    }
    :host-context([data-theme='light']) .captura--oscuro {
      display: none;
    }
  `,
})
export class LandingCaptura {
  /** Nombre base del fichero en `assets/landing/capturas/`. */
  readonly nombre = input.required<string>();
  readonly alt = input.required<string>();
  /** Ruta que se muestra en la barra de la ventana (solo decorativa). */
  readonly ruta = input('/dashboard');
}
