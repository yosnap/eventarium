import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Entrada, Parallax } from '../animaciones.directive';

@Component({
  selector: 'app-landing-quienes-somos',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Entrada, Parallax],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-seccion" aria-labelledby="landing-quienes-titulo">
        <div class="landing-dos-columnas">
          <div>
            <p class="landing-rotulo">{{ t('publico.landing.quienesSomos.rotulo') }}</p>
            <h2 id="landing-quienes-titulo">{{ t('publico.landing.quienesSomos.titulo') }}</h2>
            <p class="landing-parrafo">{{ t('publico.landing.quienesSomos.parrafo1') }}</p>
            <p class="landing-parrafo">{{ t('publico.landing.quienesSomos.parrafo2') }}</p>
            <p class="landing-parrafo">{{ t('publico.landing.quienesSomos.parrafo3') }}</p>
            <ul class="landing-cifras">
              @for (cifra of cifras; track cifra; let i = $index) {
                <li class="landing-cifra" [appEntrada]="i * 0.08">
                  <span class="landing-cifra-valor">{{
                    t('publico.landing.quienesSomos.cifras.' + cifra + '.valor')
                  }}</span>
                  <span class="landing-cifra-etiqueta">{{
                    t('publico.landing.quienesSomos.cifras.' + cifra + '.etiqueta')
                  }}</span>
                </li>
              }
            </ul>
          </div>
          <div class="landing-ilustracion" aria-hidden="true" appParallax="0.15">
            <div
              class="landing-capa landing-capa--circulo landing-capa--suave"
              style="inset: 8% auto auto 8%; width: 30%; aspect-ratio: 1"
            ></div>
            <div class="landing-capa" style="inset: 22% 10% 28% 30%"></div>
            <div
              class="landing-capa landing-capa--linea"
              style="left: 36%; top: 34%; width: 40%"
            ></div>
            <div
              class="landing-capa landing-capa--linea"
              style="left: 36%; top: 44%; width: 28%"
            ></div>
            <div
              class="landing-capa landing-capa--linea landing-capa--acento"
              style="left: 36%; top: 56%; width: 20%"
            ></div>
            <div
              class="landing-capa landing-capa--acento"
              style="inset: auto 8% 10% auto; width: 26%; height: 16%"
            ></div>
          </div>
        </div>
      </section>
    </ng-container>
  `,
  styles: `
    .landing-cifras {
      display: grid;
      gap: var(--space-sm);
      grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
      margin: var(--space-lg) 0 0;
      padding: 0;
      list-style: none;
    }
    .landing-cifra {
      padding: var(--space-md);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--surface);
    }
    .landing-cifra-valor {
      display: block;
      font-family: var(--font-display);
      font-size: var(--fs-metric);
      line-height: 1;
      color: var(--accent);
    }
    .landing-cifra-etiqueta {
      display: block;
      margin-top: var(--space-xs);
      font-size: var(--fs-sm);
      color: var(--muted);
    }

    /* En directo */
  `,
})
export class LandingQuienesSomos {
  protected readonly cifras = ['comision', 'licencia', 'marca'] as const;
}
