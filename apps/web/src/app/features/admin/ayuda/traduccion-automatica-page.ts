import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { Card } from '../../../shared/ui/card';
import { PageHeader } from '../../../shared/ui/page-header';

/** Ayuda paso a paso para activar la traducción automática con la clave propia. */
@Component({
  selector: 'app-traduccion-automatica-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Card, PageHeader, RouterLink, TranslocoDirective],
  template: `
    <ng-container *transloco="let t; prefix: 'ayuda.traduccion'">
      <app-page-header [rotulo]="t('rotulo')">{{ t('titulo') }}</app-page-header>
      <app-card>
        <p>{{ t('intro') }}</p>
        <ol class="pasos">
          <li>
            <strong>{{ t('paso1.titulo') }}</strong>
            <p>{{ t('paso1.texto') }}</p>
            <ul>
              <li>{{ t('paso1.openrouter') }}</li>
              <li>{{ t('paso1.openai') }}</li>
              <li>{{ t('paso1.anthropic') }}</li>
              <li>{{ t('paso1.gemini') }}</li>
            </ul>
          </li>
          <li>
            <strong>{{ t('paso2.titulo') }}</strong>
            <p>{{ t('paso2.texto') }}</p>
            <a routerLink="/dashboard/ia">{{ t('paso2.enlace') }}</a>
          </li>
          <li>
            <strong>{{ t('paso3.titulo') }}</strong>
            <p>{{ t('paso3.texto') }}</p>
          </li>
          <li>
            <strong>{{ t('paso4.titulo') }}</strong>
            <p>{{ t('paso4.texto') }}</p>
          </li>
        </ol>
        <h2>{{ t('costeTitulo') }}</h2>
        <p>{{ t('coste') }}</p>
        <h2>{{ t('sinClaveTitulo') }}</h2>
        <p>{{ t('sinClave') }}</p>
      </app-card>
    </ng-container>
  `,
  styles: `
    .pasos {
      display: grid;
      gap: var(--space-md);
      padding-left: var(--space-lg);
    }
    .pasos p {
      margin: var(--space-xs) 0;
    }
    h2 {
      margin-top: var(--space-lg);
      font-size: var(--fs-h3);
    }
  `,
})
export class TraduccionAutomaticaPage {}
