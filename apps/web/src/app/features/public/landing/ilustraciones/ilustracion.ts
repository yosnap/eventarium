import { ChangeDetectionStrategy, Component, ViewEncapsulation, input } from '@angular/core';

import { Parallax } from '../animaciones.directive';
import type { Ilustracion } from '../landing-contenido';

/**
 * Ilustraciones dibujadas en CSS (nada de imágenes): un lienzo con capas
 * absolutas posicionadas en línea. Sin encapsulación: el hero dibuja su propia
 * ilustración con estas mismas clases. Decorativas: `aria-hidden`.
 */
@Component({
  selector: 'app-landing-ilustracion',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Parallax],
  host: { class: 'landing-ilustracion', 'aria-hidden': 'true' },
  encapsulation: ViewEncapsulation.None,
  styles: `
    /* Ilustraciones: un lienzo cuadrado con capas absolutas. Cada ilustración
     * declara sus capas con \`landing-capa\`; el movimiento lo pone GSAP (fase 4). */
    .landing-ilustracion {
      position: relative;
      aspect-ratio: 4 / 3;
      overflow: hidden;
      border-radius: var(--radius-lg);
      background:
        radial-gradient(circle at 20% 20%, var(--accent-dim), transparent 45%),
        linear-gradient(var(--grid-line) 1px, transparent 1px) 0 0 / var(--grid-size)
          var(--grid-size),
        linear-gradient(90deg, var(--grid-line) 1px, transparent 1px) 0 0 / var(--grid-size)
          var(--grid-size),
        var(--surface);
    }
    .landing-capa {
      position: absolute;
      border-radius: var(--radius-md);
      background: var(--surface-hi);
      border: 1px solid var(--border-strong);
      box-shadow: var(--shadow-md);
    }
    .landing-capa--acento {
      background: var(--accent);
      border-color: transparent;
    }
    .landing-capa--suave {
      background: var(--accent-dim);
      border-color: transparent;
    }
    .landing-capa--linea {
      height: 0.5rem;
      border: 0;
      border-radius: 999px;
      background: var(--border-strong);
      box-shadow: none;
    }
    .landing-capa--punto {
      width: 0.9rem;
      height: 0.9rem;
      border-radius: 50%;
      box-shadow: none;
    }
    .landing-capa--circulo {
      border-radius: 50%;
    }
    .landing-capa--qr {
      background:
        linear-gradient(var(--fg) 0 0) 12% 12% / 22% 22% no-repeat,
        linear-gradient(var(--fg) 0 0) 66% 12% / 22% 22% no-repeat,
        linear-gradient(var(--fg) 0 0) 12% 66% / 22% 22% no-repeat,
        repeating-linear-gradient(90deg, var(--fg) 0 8%, transparent 8% 16%) 45% 50% / 45% 12%
          no-repeat,
        repeating-linear-gradient(var(--fg) 0 8%, transparent 8% 16%) 66% 66% / 12% 30% no-repeat,
        var(--surface-hi);
    }
  `,
  template: `
    @switch (tipo()) {
      @case ('quienes') {
        <div
          appParallax="0.15"
          class="landing-capa landing-capa--circulo landing-capa--suave"
          style="inset: 8% auto auto 8%; width: 30%; aspect-ratio: 1"
        ></div>
        <div appParallax="0.15" class="landing-capa" style="inset: 22% 10% 28% 30%"></div>
        <div
          appParallax="0.35"
          class="landing-capa landing-capa--linea"
          style="left: 36%; top: 34%; width: 40%"
        ></div>
        <div
          appParallax="0.25"
          class="landing-capa landing-capa--linea"
          style="left: 36%; top: 44%; width: 28%"
        ></div>
        <div
          appParallax="0.35"
          class="landing-capa landing-capa--linea landing-capa--acento"
          style="left: 36%; top: 56%; width: 20%"
        ></div>
        <div
          appParallax="0.25"
          class="landing-capa landing-capa--acento"
          style="inset: auto 8% 10% auto; width: 26%; height: 16%"
        ></div>
      }
      @case ('inscripciones') {
        <div appParallax="0.5" class="landing-capa" style="inset: 16% 30% 16% 14%"></div>
        <div
          appParallax="0.2"
          class="landing-capa landing-capa--linea"
          style="left: 22%; top: 28%; width: 30%"
        ></div>
        <div
          appParallax="0.4"
          class="landing-capa landing-capa--linea"
          style="left: 22%; top: 40%; width: 40%"
        ></div>
        <div
          appParallax="0.3"
          class="landing-capa landing-capa--linea"
          style="left: 22%; top: 52%; width: 24%"
        ></div>
        <div
          appParallax="0.5"
          class="landing-capa landing-capa--acento"
          style="left: 22%; top: 66%; width: 28%; height: 10%"
        ></div>
        <div
          appParallax="0.2"
          class="landing-capa landing-capa--circulo landing-capa--suave"
          style="right: 10%; top: 24%; width: 24%; aspect-ratio: 1"
        ></div>
        <div
          appParallax="0.4"
          class="landing-capa landing-capa--punto landing-capa--acento"
          style="right: 18%; top: 34%"
        ></div>
      }
      @case ('entradas') {
        <div
          appParallax="0.3"
          class="landing-capa"
          style="inset: 22% 18% 22% 18%; border-radius: var(--radius-lg)"
        ></div>
        <div
          appParallax="0.45"
          class="landing-capa landing-capa--qr"
          style="left: 24%; top: 32%; width: 26%; aspect-ratio: 1; box-shadow: none"
        ></div>
        <div
          appParallax="0.45"
          class="landing-capa landing-capa--linea"
          style="left: 56%; top: 36%; width: 20%"
        ></div>
        <div
          appParallax="0.1"
          class="landing-capa landing-capa--linea"
          style="left: 56%; top: 46%; width: 14%"
        ></div>
        <div
          appParallax="0.1"
          class="landing-capa landing-capa--linea landing-capa--acento"
          style="left: 56%; top: 58%; width: 18%"
        ></div>
        <div
          appParallax="0.15"
          class="landing-capa landing-capa--punto landing-capa--acento"
          style="left: 15%; top: 48%"
        ></div>
        <div
          appParallax="0.35"
          class="landing-capa landing-capa--punto landing-capa--acento"
          style="right: 15%; top: 48%"
        ></div>
      }
      @case ('marca') {
        <div appParallax="0.15" class="landing-capa" style="inset: 14% 14% 20% 14%"></div>
        <div
          appParallax="0.25"
          class="landing-capa landing-capa--acento"
          style="left: 14%; top: 14%; width: 72%; height: 12%; border-radius: var(--radius-md) var(--radius-md) 0 0"
        ></div>
        <div
          appParallax="0.5"
          class="landing-capa landing-capa--circulo landing-capa--suave"
          style="left: 20%; top: 34%; width: 16%; aspect-ratio: 1"
        ></div>
        <div
          appParallax="0.35"
          class="landing-capa landing-capa--linea"
          style="left: 42%; top: 38%; width: 34%"
        ></div>
        <div
          appParallax="0.25"
          class="landing-capa landing-capa--linea"
          style="left: 42%; top: 48%; width: 22%"
        ></div>
        <div
          appParallax="0.2"
          class="landing-capa landing-capa--suave"
          style="left: 20%; top: 60%; width: 56%; height: 12%"
        ></div>
      }
      @case ('patrocinadores') {
        <div
          appParallax="0.4"
          class="landing-capa landing-capa--acento"
          style="left: 14%; top: 18%; width: 30%; height: 22%"
        ></div>
        <div
          appParallax="0.5"
          class="landing-capa"
          style="left: 50%; top: 18%; width: 18%; height: 22%"
        ></div>
        <div
          appParallax="0.2"
          class="landing-capa"
          style="left: 72%; top: 18%; width: 14%; height: 22%"
        ></div>
        <div
          appParallax="0.3"
          class="landing-capa landing-capa--suave"
          style="left: 14%; top: 48%; width: 22%; height: 16%"
        ></div>
        <div
          appParallax="0.45"
          class="landing-capa landing-capa--suave"
          style="left: 40%; top: 48%; width: 22%; height: 16%"
        ></div>
        <div
          appParallax="0.1"
          class="landing-capa landing-capa--suave"
          style="left: 66%; top: 48%; width: 20%; height: 16%"
        ></div>
        <div
          appParallax="0.4"
          class="landing-capa landing-capa--linea"
          style="left: 14%; top: 74%; width: 72%"
        ></div>
      }
      @case ('contabilidad') {
        <div appParallax="0.3" class="landing-capa" style="inset: 14% 14% 14% 14%"></div>
        <div
          appParallax="0.15"
          class="landing-capa landing-capa--suave"
          style="left: 22%; bottom: 24%; width: 10%; height: 26%; border-radius: 4px 4px 0 0"
        ></div>
        <div
          appParallax="0.35"
          class="landing-capa landing-capa--acento"
          style="left: 36%; bottom: 24%; width: 10%; height: 44%; border-radius: 4px 4px 0 0"
        ></div>
        <div
          appParallax="0.25"
          class="landing-capa landing-capa--suave"
          style="left: 50%; bottom: 24%; width: 10%; height: 34%; border-radius: 4px 4px 0 0"
        ></div>
        <div
          appParallax="0.5"
          class="landing-capa landing-capa--acento"
          style="left: 64%; bottom: 24%; width: 10%; height: 52%; border-radius: 4px 4px 0 0"
        ></div>
        <div
          appParallax="0.2"
          class="landing-capa landing-capa--linea"
          style="left: 20%; bottom: 22%; width: 60%; height: 2px"
        ></div>
      }
      @case ('agenda') {
        <div appParallax="0.45" class="landing-capa" style="inset: 14% 14% 14% 14%"></div>
        <div
          appParallax="0.1"
          class="landing-capa landing-capa--linea"
          style="left: 20%; top: 26%; width: 12%"
        ></div>
        <div
          appParallax="0.4"
          class="landing-capa landing-capa--acento"
          style="left: 36%; top: 24%; width: 44%; height: 10%"
        ></div>
        <div
          appParallax="0.15"
          class="landing-capa landing-capa--linea"
          style="left: 20%; top: 42%; width: 12%"
        ></div>
        <div
          appParallax="0.3"
          class="landing-capa landing-capa--suave"
          style="left: 36%; top: 40%; width: 30%; height: 10%"
        ></div>
        <div
          appParallax="0.35"
          class="landing-capa landing-capa--linea"
          style="left: 20%; top: 58%; width: 12%"
        ></div>
        <div
          appParallax="0.45"
          class="landing-capa landing-capa--suave"
          style="left: 36%; top: 56%; width: 44%; height: 10%; border: 1px dashed var(--border-strong); background: transparent"
        ></div>
        <div
          appParallax="0.25"
          class="landing-capa landing-capa--linea"
          style="left: 20%; top: 74%; width: 12%"
        ></div>
        <div
          appParallax="0.1"
          class="landing-capa landing-capa--acento"
          style="left: 36%; top: 72%; width: 24%; height: 10%"
        ></div>
      }
      @case ('ponentes') {
        <div
          appParallax="0.15"
          class="landing-capa landing-capa--circulo landing-capa--acento"
          style="left: 18%; top: 20%; width: 18%; aspect-ratio: 1"
        ></div>
        <div
          appParallax="0.35"
          class="landing-capa landing-capa--circulo landing-capa--suave"
          style="left: 42%; top: 20%; width: 18%; aspect-ratio: 1"
        ></div>
        <div
          appParallax="0.25"
          class="landing-capa landing-capa--circulo"
          style="left: 66%; top: 20%; width: 18%; aspect-ratio: 1"
        ></div>
        <div appParallax="0.5" class="landing-capa" style="inset: 50% 16% 16% 16%"></div>
        <div
          appParallax="0.2"
          class="landing-capa landing-capa--linea"
          style="left: 24%; top: 60%; width: 40%"
        ></div>
        <div
          appParallax="0.4"
          class="landing-capa landing-capa--linea"
          style="left: 24%; top: 70%; width: 52%"
        ></div>
      }
      @case ('pagos') {
        <div
          appParallax="0.5"
          class="landing-capa"
          style="inset: 26% 20% 26% 20%; border-radius: var(--radius-lg)"
        ></div>
        <div
          appParallax="0.2"
          class="landing-capa landing-capa--acento"
          style="left: 20%; top: 38%; width: 60%; height: 12%; border-radius: 0"
        ></div>
        <div
          appParallax="0.3"
          class="landing-capa landing-capa--linea"
          style="left: 26%; top: 60%; width: 24%"
        ></div>
        <div
          appParallax="0.4"
          class="landing-capa landing-capa--suave"
          style="right: 26%; top: 58%; width: 14%; height: 8%"
        ></div>
        <div
          appParallax="0.3"
          class="landing-capa landing-capa--circulo landing-capa--suave"
          style="right: 8%; top: 10%; width: 20%; aspect-ratio: 1"
        ></div>
        <div
          appParallax="0.45"
          class="landing-capa landing-capa--punto landing-capa--acento"
          style="right: 15%; top: 18%"
        ></div>
      }
    }
  `,
})
export class LandingIlustracion {
  readonly tipo = input.required<Ilustracion>();
}
