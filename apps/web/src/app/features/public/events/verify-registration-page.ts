import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

type Estado = 'comprobando' | 'exito' | 'error';

/**
 * Consume el token de verificación de una inscripción. CSR, como
 * `verificar-correo`: sin interacción del usuario que dispare el resultado,
 * así que se anuncia con `aria-live="assertive"` para que un lector de
 * pantalla se entere igualmente.
 */
@Component({
  selector: 'app-verify-registration-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('verificarInscripcion.titulo')">
        <app-card [heading]="t('verificarInscripcion.titulo')">
          <div aria-live="assertive">
            @switch (estado()) {
              @case ('comprobando') {
                <app-alert tone="info">{{ t('verificarInscripcion.verificando') }}</app-alert>
              }
              @case ('exito') {
                <app-alert tone="exito" [title]="t('verificarInscripcion.exitoTitulo')">
                  {{ mensaje() }}
                </app-alert>
              }
              @case ('error') {
                <app-alert tone="error" [title]="t('verificarInscripcion.errorTitulo')">
                  {{ t('verificarInscripcion.errorDetalle') }}
                </app-alert>
              }
            }
          </div>
        </app-card>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    app-card {
      width: min(26rem, 100%);
    }
  `,
})
export class VerifyRegistrationPage {
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
    void this.verificar(token);
  }

  private async verificar(token: string): Promise<void> {
    try {
      const resultado = await this.registrations.verify(token);
      this.mensaje.set(resultado.message);
      this.estado.set('exito');
    } catch {
      this.estado.set('error');
    }
  }
}
