import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { Alert } from './alert';

/**
 * «Para traducir tus eventos automáticamente necesitas tu propia clave de IA»,
 * con el enlace a la configuración de IA y a la ayuda paso a paso. Se muestra
 * cuando la organización publica en más de un idioma y no tiene clave propia.
 */
@Component({
  selector: 'app-aviso-clave-propia',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Alert, RouterLink, TranslocoDirective],
  template: `
    <app-alert
      *transloco="let t; prefix: 'traducciones.clavePropia'"
      tone="info"
      [title]="t('titulo')"
    >
      <p>{{ t('texto') }}</p>
      <p class="enlaces">
        <a routerLink="/dashboard/ia">{{ t('configurar') }}</a>
        <a routerLink="/dashboard/ayuda/traduccion">{{ t('comoHacerlo') }}</a>
      </p>
    </app-alert>
  `,
  styles: `
    p {
      margin: 0;
    }
    .enlaces {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-md);
      font-weight: 600;
    }
  `,
})
export class AvisoClavePropia {}
