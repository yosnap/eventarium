import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ENLACES_LANDING } from '../landing-contenido';
import { ResaltarPipe } from '../resaltar.pipe';

@Component({
  selector: 'app-landing-colaborar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, ResaltarPipe],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-seccion" aria-labelledby="landing-colaborar-titulo">
        <p class="landing-rotulo">{{ t('publico.landing.colaborar.rotulo') }}</p>
        <h2 id="landing-colaborar-titulo">
          {{ t('publico.landing.colaborar.titulo') }}
          <span class="landing-insignia">MIT</span>
        </h2>
        <p class="landing-intro" [innerHTML]="t('publico.landing.colaborar.texto') | resaltar"></p>
        <ul class="landing-enlaces">
          <li>
            <a
              class="landing-enlace"
              [href]="enlaces.repositorio"
              rel="noopener noreferrer"
              target="_blank"
            >
              {{ t('publico.landing.colaborar.repositorio') }}
            </a>
          </li>
          <li>
            <a
              class="landing-enlace"
              [href]="enlaces.instalacion"
              rel="noopener noreferrer"
              target="_blank"
            >
              {{ t('publico.landing.colaborar.instalar') }}
            </a>
          </li>
          <li>
            <a
              class="landing-enlace"
              [href]="enlaces.licencia"
              rel="noopener noreferrer"
              target="_blank"
            >
              {{ t('publico.landing.colaborar.licencia') }}
            </a>
          </li>
        </ul>
      </section>
    </ng-container>
  `,
  styles: `
    .landing-enlaces {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      margin: var(--space-md) 0 0;
      padding: 0;
      list-style: none;
    }
    .landing-enlace {
      display: inline-flex;
      align-items: center;
      gap: var(--space-xs);
      min-height: 2.75rem;
      padding: 0 1rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      color: var(--fg);
      text-decoration: none;
    }
    .landing-enlace:hover,
    .landing-enlace:focus-visible {
      background: var(--surface-2);
    }
    .landing-insignia {
      display: inline-block;
      padding: 0.1rem 0.5rem;
      border-radius: 999px;
      background: var(--accent-dim);
      color: var(--fg);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
    }
  `,
})
export class LandingColaborar {
  protected readonly enlaces = ENLACES_LANDING;
}
