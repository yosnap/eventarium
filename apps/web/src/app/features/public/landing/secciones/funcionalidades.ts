import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Reveal } from '../../../../shared/ui/reveal.directive';
import { Parallax } from '../animaciones.directive';
import { LandingIlustracion } from '../ilustraciones/ilustracion';
import { FUNCIONALIDADES } from '../landing-contenido';

@Component({
  selector: 'app-landing-funcionalidades',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Reveal, Parallax, LandingIlustracion],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-seccion" aria-labelledby="landing-funcionalidades-titulo">
        <p class="landing-rotulo">{{ t('publico.landing.funcionalidades.rotulo') }}</p>
        <h2 id="landing-funcionalidades-titulo">
          {{ t('publico.landing.funcionalidades.titulo') }}
        </h2>
        <p class="landing-intro">{{ t('publico.landing.funcionalidades.intro') }}</p>
        @for (item of funcionalidades; track item.clave; let i = $index) {
          <article
            class="landing-funcionalidad landing-dos-columnas"
            [class.landing-dos-columnas--invertida]="i % 2 === 1"
            [attr.aria-labelledby]="'landing-funcionalidad-' + item.clave"
          >
            <div appReveal>
              <h3 [id]="'landing-funcionalidad-' + item.clave">
                {{ t('publico.landing.funcionalidades.items.' + item.clave + '.titulo') }}
              </h3>
              <p class="landing-parrafo">
                {{ t('publico.landing.funcionalidades.items.' + item.clave + '.texto') }}
              </p>
            </div>
            <app-landing-ilustracion [tipo]="item.ilustracion" appParallax="0.18" />
          </article>
        }
      </section>
    </ng-container>
  `,
})
export class LandingFuncionalidades {
  protected readonly funcionalidades = FUNCIONALIDADES;
}
