import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Pide la recuperación de una contraseña olvidada. CSR, como `registro`.
 *
 * La respuesta es siempre la misma exista o no la cuenta (anti-enumeración), así que
 * tras enviar el formulario se muestra el mismo mensaje de éxito en ambos casos.
 */
@Component({
  selector: 'app-forgot-password-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    AuthFrame,
    Alert,
    Button,
    Card,
    Input,
    Reveal,
    TurnstileWidget,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('recuperarContrasena.titulo')">
        <div class="envoltura" appReveal>
          <app-card [heading]="t('recuperarContrasena.titulo')">
            @if (enviado()) {
              <app-alert tone="exito" [title]="t('recuperarContrasena.exitoTitulo')">
                {{ t('recuperarContrasena.exitoDetalle') }}
              </app-alert>
            } @else {
              <form (submit)="enviar($event)" novalidate>
                <p>{{ t('recuperarContrasena.instrucciones') }}</p>
                <app-input
                  [label]="t('recuperarContrasena.email')"
                  type="email"
                  autocomplete="email"
                  [required]="true"
                  [error]="errorEmail()"
                  [(value)]="email"
                />
                <app-turnstile-widget (resuelto)="turnstileToken.set($event)" />
                @if (error(); as mensaje) {
                  <app-alert tone="error">{{ mensaje }}</app-alert>
                }
                <app-button type="submit" [loading]="enviando()">
                  {{
                    enviando() ? t('recuperarContrasena.enviando') : t('recuperarContrasena.enviar')
                  }}
                </app-button>
              </form>
            }
            <p>
              <a routerLink="/admin/login">{{ t('registro.yaTengoCuenta') }}</a>
            </p>
          </app-card>
        </div>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    .envoltura {
      width: min(26rem, 100%);
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
  `,
})
export class ForgotPasswordPage {
  private readonly auth = inject(AuthService);
  private readonly transloco = inject(TranslocoService);

  protected readonly email = signal('');
  protected readonly errorEmail = signal<string | null>(null);
  protected readonly turnstileToken = signal<string | null>(null);
  protected readonly enviando = signal(false);
  protected readonly enviado = signal(false);
  protected readonly error = signal<string | null>(null);

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    const correo = this.email().trim();
    this.errorEmail.set(
      EMAIL_RE.test(correo) ? null : this.transloco.translate('registro.emailInvalido'),
    );
    if (this.errorEmail()) {
      return;
    }

    this.enviando.set(true);
    try {
      await this.auth.forgotPassword(correo, this.turnstileToken() ?? '');
      this.enviado.set(true);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('recuperarContrasena.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
