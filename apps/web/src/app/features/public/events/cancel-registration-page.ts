import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

type Estado = 'comprobando' | 'exito' | 'error';

/**
 * Consume el token de autocancelación de una inscripción. Mismo patrón que
 * `verify-registration-page`: CSR, sin interacción del usuario que dispare
 * el resultado, así que se anuncia con `aria-live="assertive"`.
 */
@Component({
  selector: 'app-cancel-registration-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" class="pagina">
        <app-card [heading]="t('cancelarInscripcion.titulo')">
          <div aria-live="assertive">
            @switch (estado()) {
              @case ('comprobando') {
                <app-alert tone="info">{{ t('cancelarInscripcion.comprobando') }}</app-alert>
              }
              @case ('exito') {
                <app-alert tone="exito" [title]="t('cancelarInscripcion.exitoTitulo')">
                  {{ mensaje() }}
                </app-alert>
              }
              @case ('error') {
                <app-alert tone="error" [title]="t('cancelarInscripcion.errorTitulo')">
                  {{ t('cancelarInscripcion.errorDetalle') }}
                </app-alert>
              }
            }
          </div>
        </app-card>
      </main>
    </ng-container>
  `,
  styles: `
    .pagina {
      display: grid;
      place-items: center;
      min-height: 100vh;
      padding: var(--space-lg);
      background-color: var(--color-surface-muted);
    }
    app-card {
      width: min(26rem, 100%);
    }
  `,
})
export class CancelRegistrationPage {
  private readonly registrations = inject(RegistrationsService);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly mensaje = signal('');

  constructor() {
    const token = this.ruta.snapshot.queryParamMap.get('token');
    if (!token) {
      this.estado.set('error');
      return;
    }
    void this.cancelar(token);
  }

  private async cancelar(token: string): Promise<void> {
    try {
      const resultado = await this.registrations.cancel(token);
      this.mensaje.set(resultado.message);
      this.estado.set('exito');
    } catch {
      this.estado.set('error');
    }
  }
}
