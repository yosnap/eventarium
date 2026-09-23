import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Checkbox } from '../../../shared/ui/checkbox';

/**
 * Consentimientos del formulario de inscripción, cada uno independiente:
 * tratamiento de datos (obligatorio), marketing y grabación (opcionales, sin
 * condicionar la inscripción). Quien lo usa guarda los valores y los valida.
 */
@Component({
  selector: 'app-registration-consents',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Checkbox],
  template: `
    <ng-container *transloco="let t">
      <app-checkbox
        fieldId="insc-tratamiento-datos"
        [label]="t('inscripcion.tratamientoDatos')"
        [describedBy]="errorConsentimiento() ? 'insc-tratamiento-datos-error' : null"
        [(checked)]="dataProcessingAccepted"
      />
      @if (errorConsentimiento()) {
        <p id="insc-tratamiento-datos-error" class="error-pregunta">
          {{ errorConsentimiento() }}
        </p>
      }

      <app-checkbox [label]="t('inscripcion.marketing')" [(checked)]="marketingAccepted" />

      <app-checkbox [label]="t('inscripcion.grabacion')" [(checked)]="recordingAccepted" />
    </ng-container>
  `,
  styles: `
    :host {
      display: contents;
    }
    .error-pregunta {
      margin: 0;
      color: var(--danger);
      font-size: 0.875rem;
    }
  `,
})
export class RegistrationConsents {
  readonly errorConsentimiento = input<string | null>(null);

  readonly dataProcessingAccepted = model(false);
  readonly marketingAccepted = model(false);
  readonly recordingAccepted = model(false);
}
