import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

type Estado = 'comprobando' | 'exito' | 'error';

/**
 * Consume el token de verificación de la URL. CSR, como `admin/login`.
 *
 * Un enlace caducado o ya usado se anuncia con `aria-live="assertive"` — sin eso, un
 * lector de pantalla no se entera de que la comprobación terminó en error, porque
 * ocurre sin ninguna interacción del usuario que la dispare. Se ofrece reenviar el
 * enlace directamente desde aquí, sin volver a `/registro`.
 */
@Component({
  selector: 'app-verify-email-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, AuthFrame, Alert, Button, Card, Input, TurnstileWidget],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('verificarCorreo.titulo')">
        <app-card [heading]="t('verificarCorreo.titulo')">
          <div aria-live="assertive">
            @switch (estado()) {
              @case ('comprobando') {
                <app-alert tone="info">{{ t('verificarCorreo.verificando') }}</app-alert>
              }
              @case ('exito') {
                <app-alert tone="exito" [title]="t('verificarCorreo.exitoTitulo')">
                  {{ t('verificarCorreo.exitoDetalle') }}
                  <p>
                    <a routerLink="/crear-organizacion">{{ t('verificarCorreo.continuar') }}</a>
                  </p>
                </app-alert>
              }
              @case ('error') {
                <app-alert tone="error" [title]="t('verificarCorreo.errorTitulo')">
                  {{ t('verificarCorreo.errorDetalle') }}
                </app-alert>
              }
            }
          </div>

          @if (estado() === 'error') {
            @if (reenviado()) {
              <app-alert tone="exito" [title]="t('verificarCorreo.reenviadoTitulo')">
                {{ t('verificarCorreo.reenviadoDetalle') }}
              </app-alert>
            } @else {
              <form (submit)="reenviar($event)" novalidate>
                <app-input
                  [label]="t('verificarCorreo.email')"
                  type="email"
                  autocomplete="email"
                  [required]="true"
                  [error]="errorEmail()"
                  [(value)]="email"
                />
                <app-turnstile-widget (resuelto)="turnstileToken.set($event)" />
                <app-button type="submit" [loading]="reenviando()">
                  {{
                    reenviando() ? t('verificarCorreo.reenviando') : t('verificarCorreo.reenviar')
                  }}
                </app-button>
              </form>
            }
          }
        </app-card>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    app-card {
      width: min(26rem, 100%);
    }
    form {
      display: grid;
      gap: var(--space-md);
      margin-top: var(--space-md);
    }
  `,
})
export class VerifyEmailPage {
  private readonly auth = inject(AuthService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly transloco = inject(TranslocoService);

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly email = signal('');
  protected readonly errorEmail = signal<string | null>(null);
  protected readonly turnstileToken = signal<string | null>(null);
  protected readonly reenviando = signal(false);
  protected readonly reenviado = signal(false);

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
      await this.auth.verifyEmail(token);
      this.estado.set('exito');
      // Breve pausa para que el mensaje de éxito sea legible antes de continuar:
      // desaparecer la pantalla al instante no daría tiempo a leerlo, y menos aún a
      // quien usa un lector de pantalla.
      setTimeout(() => void this.router.navigateByUrl('/crear-organizacion'), 1500);
    } catch {
      this.estado.set('error');
    }
  }

  protected async reenviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.errorEmail.set(
      this.email().trim() ? null : this.transloco.translate('verificarCorreo.emailRequerido'),
    );
    if (this.errorEmail()) {
      return;
    }

    this.reenviando.set(true);
    try {
      await this.auth.resendVerification(this.email().trim(), this.turnstileToken() ?? '');
      this.reenviado.set(true);
    } catch (error) {
      // El reenvío responde siempre igual; un fallo aquí es de red o de límite de
      // peticiones, no de que la cuenta no exista.
      this.errorEmail.set(
        error instanceof ApiError ? error.message : this.transloco.translate('registro.error'),
      );
    } finally {
      this.reenviando.set(false);
    }
  }
}
