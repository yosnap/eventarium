import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Apilado } from '../animaciones.directive';
import { LandingCaptura } from '../captura';
import { FUNCIONALIDADES } from '../landing-contenido';
import { ResaltarPipe } from '../resaltar.pipe';

@Component({
  selector: 'app-landing-funcionalidades',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Apilado, LandingCaptura, ResaltarPipe],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-seccion" aria-labelledby="landing-funcionalidades-titulo">
        <p class="landing-rotulo">{{ t('publico.landing.funcionalidades.rotulo') }}</p>
        <h2
          id="landing-funcionalidades-titulo"
          [innerHTML]="t('publico.landing.funcionalidades.titulo') | resaltar"
        ></h2>
        <p
          class="landing-intro"
          [innerHTML]="t('publico.landing.funcionalidades.intro') | resaltar"
        ></p>
        <div class="landing-apilado" appApilado>
          @for (item of funcionalidades; track item.clave; let i = $index) {
            <article
              class="landing-tarjeta"
              [class.landing-tarjeta--invertida]="i % 2 === 1"
              [attr.aria-labelledby]="'landing-funcionalidad-' + item.clave"
              [style.--indice]="i"
            >
              <div class="landing-tarjeta-texto">
                <span class="landing-tarjeta-numero" aria-hidden="true">
                  {{ i + 1 < 10 ? '0' + (i + 1) : i + 1 }}
                </span>
                <h3 [id]="'landing-funcionalidad-' + item.clave">
                  {{ t('publico.landing.funcionalidades.items.' + item.clave + '.titulo') }}
                </h3>
                <p
                  class="landing-parrafo"
                  [innerHTML]="
                    t('publico.landing.funcionalidades.items.' + item.clave + '.texto') | resaltar
                  "
                ></p>
              </div>
              <app-landing-captura
                [nombre]="item.clave"
                [ruta]="item.ruta"
                [alt]="t('publico.landing.funcionalidades.items.' + item.clave + '.captura')"
              />
            </article>
          }
        </div>
      </section>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .landing-apilado {
      display: grid;
      gap: var(--space-lg);
      /* Cada tarjeta se queda pegada bajo la cabecera y la siguiente le pasa
         por encima; la directiva appApilado encoge la anterior (sin atenuarla). */
      --apilado-top: 5.5rem;
    }
    .landing-tarjeta {
      position: sticky;
      top: calc(var(--apilado-top) + var(--indice) * 0.75rem);
      display: grid;
      gap: var(--space-lg);
      align-items: center;
      min-height: min(70vh, 34rem);
      padding: var(--space-lg);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-lg);
      /* Opaco a propósito: --surface lleva alfa y, apiladas, la tarjeta de
         delante dejaría ver el texto de la de detrás. */
      background: linear-gradient(var(--surface), var(--surface)), var(--bg);
      /* Borde de elevación por arriba: es lo que separa una tarjeta de la que
         asoma por detrás cuando se apilan (en tema oscuro los tonos de fondo
         se parecen y sin esto parecen transparentes). */
      box-shadow:
        0 -1px 0 var(--surface-hi),
        0 -18px 48px -12px oklch(0% 0 0 / 0.45),
        var(--shadow-lg);
      will-change: transform;
    }
    @media (min-width: 48rem) {
      .landing-tarjeta {
        grid-template-columns: 1fr 1fr;
        padding: var(--sp-7);
      }
      .landing-tarjeta--invertida > :first-child {
        order: 2;
      }
    }
    .landing-tarjeta-texto {
      display: grid;
      gap: var(--space-sm);
    }
    .landing-tarjeta-numero {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      color: var(--accent);
      letter-spacing: 0.08em;
    }
    h3 {
      margin: 0;
      font-family: var(--font-display);
      font-size: var(--fs-h2);
      line-height: 1.1;
      letter-spacing: -0.01em;
      text-wrap: balance;
    }
  `,
})
export class LandingFuncionalidades {
  protected readonly funcionalidades = FUNCIONALIDADES;
}
