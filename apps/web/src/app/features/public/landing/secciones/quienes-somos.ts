import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Reveal } from '../../../../shared/ui/reveal.directive';
import { Parallax, TextoRevelado } from '../animaciones.directive';
import { LandingIlustracion } from '../ilustraciones/ilustracion';
import { ResaltarPipe } from '../resaltar.pipe';

@Component({
  selector: 'app-landing-quienes-somos',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Reveal, Parallax, TextoRevelado, LandingIlustracion, ResaltarPipe],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-seccion" aria-labelledby="landing-quienes-titulo">
        <div class="landing-dos-columnas">
          <div>
            <p class="landing-rotulo">{{ t('publico.landing.quienesSomos.rotulo') }}</p>
            <h2
              id="landing-quienes-titulo"
              [innerHTML]="t('publico.landing.quienesSomos.titulo') | resaltar"
            ></h2>
            <p
              class="landing-parrafo landing-parrafo--grande"
              appTextoRevelado
              [innerHTML]="t('publico.landing.quienesSomos.parrafo1') | resaltar"
            ></p>
            <p
              class="landing-parrafo landing-parrafo--grande"
              appTextoRevelado
              [innerHTML]="t('publico.landing.quienesSomos.parrafo2') | resaltar"
            ></p>
            <p
              class="landing-parrafo landing-parrafo--grande"
              appTextoRevelado
              [innerHTML]="t('publico.landing.quienesSomos.parrafo3') | resaltar"
            ></p>
            <ul class="landing-cifras">
              @for (cifra of cifras; track cifra; let i = $index) {
                <li class="landing-cifra" appReveal [index]="i">
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
          <app-landing-ilustracion tipo="quienes" appParallax="0.15" />
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
