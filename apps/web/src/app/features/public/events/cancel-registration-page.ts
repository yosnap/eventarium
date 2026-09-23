import { isPlatformBrowser } from '@angular/common';
import { ChangeDetectionStrategy, Component, PLATFORM_ID, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { seoDePagina } from '../../../core/seo/meta.service';
import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { Reveal } from '../../../shared/ui/reveal.directive';

type Estado = 'comprobando' | 'exito' | 'error';

/**
 * Consume el token de autocancelación de una inscripción. Mismo patrón que
 * `verify-registration-page`: CSR, sin interacción del usuario que dispare
 * el resultado, así que se anuncia con `aria-live="assertive"`.
 */
@Component({
  selector: 'app-cancel-registration-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Card, Reveal],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('cancelarInscripcion.titulo')">
        <div class="envoltura" appReveal>
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
        </div>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    .envoltura {
      width: min(26rem, 100%);
    }
  `,
})
export class CancelRegistrationPage {
  private readonly seo = seoDePagina();
  private readonly transloco = inject(TranslocoService);
  private readonly registrations = inject(RegistrationsService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly enNavegador = isPlatformBrowser(inject(PLATFORM_ID));

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly mensaje = signal('');

  constructor() {
    this.seo.set({ title: this.transloco.translate('cancelarInscripcion.titulo') });
    const token = this.ruta.snapshot.queryParamMap.get('token');
    if (!token) {
      this.estado.set('error');
      return;
    }
    // El token es de un solo uso: el servidor pinta «comprobando» con su
    // título y solo el navegador lo consume. Si lo gastara el servidor, la
    // hidratación volvería a intentarlo y mostraría «enlace caducado».
    if (this.enNavegador) {
      void this.cancelar(token);
    }
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
