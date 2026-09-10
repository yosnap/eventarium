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
import { PasswordStrength, isPasswordValid } from '../../../shared/ui/password-strength';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type Campo = 'email' | 'password' | 'confirmPassword';

/**
 * Alta de una cuenta. CSR, como `admin/login`: es un flujo transaccional, no
 * contenido público indexable.
 *
 * Sin campo de nombre a propósito: un único «nombre completo» es ambiguo para
 * repartir en nombre y apellidos después. Se pide más tarde, en el punto donde de
 * verdad hace falta — crear una organización, inscribirse a un evento — no aquí.
 *
 * Cada campo se valida al perder el foco (no en cada pulsación, que interrumpiría
 * mientras se escribe, ni solo al enviar). La respuesta del servidor es siempre la
 * misma exista o no ya la cuenta (anti-enumeración), así que tras enviar el
 * formulario se muestra el mismo mensaje de éxito en ambos casos.
 */
@Component({
  selector: 'app-register-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    AuthFrame,
    Alert,
    Button,
    Card,
    Input,
    PasswordStrength,
    Reveal,
    TurnstileWidget,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('registro.titulo')">
        <div class="envoltura" appReveal>
          <app-card [heading]="t('registro.titulo')">
            @if (enviado()) {
              <app-alert tone="exito" [title]="t('registro.exitoTitulo')">
                {{ t('registro.exitoDetalle') }}
              </app-alert>
            } @else {
              <form (submit)="enviar($event)" novalidate>
                <app-input
                  [label]="t('registro.email')"
                  type="email"
                  autocomplete="email"
                  [required]="true"
                  [error]="errores().email"
                  [(value)]="email"
                  (blurred)="validar('email')"
                />
                <app-input
                  [label]="t('registro.password')"
                  type="password"
                  autocomplete="new-password"
                  [required]="true"
                  [error]="errores().password"
                  [hint]="t('registro.passwordAyuda')"
                  [(value)]="password"
                  (blurred)="validar('password')"
                />
                <app-password-strength [password]="password()" />

                <app-input
                  [label]="t('registro.confirmarPassword')"
                  type="password"
                  autocomplete="new-password"
                  [required]="true"
                  [error]="errores().confirmPassword"
                  [hint]="t('registro.confirmarPasswordAyuda')"
                  [(value)]="confirmPassword"
                  (blurred)="validar('confirmPassword')"
                />

                <app-turnstile-widget (resuelto)="turnstileToken.set($event)" />

                @if (error(); as mensaje) {
                  <app-alert tone="error" [title]="t('registro.error')">{{ mensaje }}</app-alert>
                }

                <app-button type="submit" [loading]="enviando()">
                  {{ enviando() ? t('registro.creando') : t('registro.crearCuenta') }}
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
      width: min(28rem, 100%);
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
  `,
})
export class RegisterPage {
  private readonly auth = inject(AuthService);
  private readonly transloco = inject(TranslocoService);

  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly confirmPassword = signal('');
  protected readonly turnstileToken = signal<string | null>(null);
  protected readonly enviando = signal(false);
  protected readonly enviado = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errores = signal<Record<Campo, string | null>>({
    email: null,
    password: null,
    confirmPassword: null,
  });

  private errorDe(campo: Campo): string | null {
    switch (campo) {
      case 'email': {
        const valor = this.email().trim();
        if (!valor) return this.transloco.translate('registro.emailRequerido');
        return EMAIL_RE.test(valor) ? null : this.transloco.translate('registro.emailInvalido');
      }
      case 'password': {
        const valor = this.password();
        if (valor.length < 8) return this.transloco.translate('registro.passwordRequerida');
        return isPasswordValid(valor)
          ? null
          : this.transloco.translate('registro.passwordSinComplejidad');
      }
      case 'confirmPassword': {
        if (!this.confirmPassword()) {
          return this.transloco.translate('registro.confirmarPasswordRequerida');
        }
        return this.confirmPassword() === this.password()
          ? null
          : this.transloco.translate('registro.passwordsNoCoinciden');
      }
    }
  }

  protected validar(campo: Campo): void {
    this.errores.update((actuales) => ({ ...actuales, [campo]: this.errorDe(campo) }));
  }

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);

    const nuevosErrores: Record<Campo, string | null> = {
      email: this.errorDe('email'),
      password: this.errorDe('password'),
      confirmPassword: this.errorDe('confirmPassword'),
    };
    this.errores.set(nuevosErrores);
    if (Object.values(nuevosErrores).some((mensaje) => mensaje)) {
      return;
    }

    this.enviando.set(true);
    try {
      await this.auth.register(this.email().trim(), this.password(), this.turnstileToken() ?? '');
      this.enviado.set(true);
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('registro.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
