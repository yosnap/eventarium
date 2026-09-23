import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Alert } from '../../../shared/ui/alert';

/**
 * Aviso fijo en las pantallas de políticas: los textos son del organizador,
 * que responde de ellos; la plataforma no los revisa ni los valida.
 */
@Component({
  selector: 'app-policy-responsibility-notice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert],
  template: `
    <ng-container *transloco="let t">
      <app-alert tone="info" [title]="t('admin.politicas.responsabilidadTitulo')">
        {{ t('admin.politicas.responsabilidad') }}
      </app-alert>
    </ng-container>
  `,
})
export class PolicyResponsibilityNotice {}
