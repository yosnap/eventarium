import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthService } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

type Estado = 'comprobando' | 'exito' | 'error';

/**
 * Consume el token de confirmación de cambio de correo. CSR, mismo patrón que
 * `verify-email-page.ts`: la comprobación ocurre sin interacción, así que el
 * resultado se anuncia con `aria-live="assertive"`.
 */
@Component({
  selector: 'app-confirm-email-change-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" class="pagina">
        <app-card [heading]="t('cuenta.confirmarCorreo.titulo')">
          <div aria-live="assertive">
            @switch (estado()) {
              @case ('comprobando') {
                <app-alert tone="info">{{ t('cuenta.confirmarCorreo.comprobando') }}</app-alert>
              }
              @case ('exito') {
                <app-alert tone="exito" [title]="t('cuenta.confirmarCorreo.exitoTitulo')">
                  {{ t('cuenta.confirmarCorreo.exitoDetalle') }}
                  <p>
                    <a routerLink="/admin/login">{{ t('registro.yaTengoCuenta') }}</a>
                  </p>
                </app-alert>
              }
              @case ('error') {
                <app-alert tone="error" [title]="t('verificarCorreo.errorTitulo')">
                  {{ t('cuenta.confirmarCorreo.errorDetalle') }}
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
export class ConfirmEmailChangePage {
  private readonly auth = inject(AuthService);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly estado = signal<Estado>('comprobando');

  constructor() {
    const token = this.ruta.snapshot.queryParamMap.get('token');
    if (!token) {
      this.estado.set('error');
      return;
    }
    void this.confirmar(token);
  }

  private async confirmar(token: string): Promise<void> {
    try {
      await this.auth.confirmChangeEmail(token);
      this.estado.set('exito');
    } catch {
      this.estado.set('error');
    }
  }
}
