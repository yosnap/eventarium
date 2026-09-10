import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { PasswordStrength, isPasswordValid } from '../../../shared/ui/password-strength';

type Estado = 'formulario' | 'exito' | 'tokenInvalido';

/**
 * Completa la recuperación de contraseña con el token del enlace. CSR.
 *
 * Un token caducado o ya usado se anuncia con `aria-live="assertive"`, mismo patrón
 * que `verify-email-page.ts`, con un botón directo para pedir uno nuevo en lugar de
 * dejar a la persona en un formulario que solo puede fallar.
 */
@Component({
  selector: 'app-reset-password-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, AuthFrame, Alert, Button, Card, Input, PasswordStrength],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('recuperarContrasena.nuevaTitulo')">
        <app-card [heading]="t('recuperarContrasena.nuevaTitulo')">
          <div aria-live="assertive">
            @switch (estado()) {
              @case ('tokenInvalido') {
                <app-alert tone="error" [title]="t('verificarCorreo.errorTitulo')">
                  {{ t('recuperarContrasena.tokenInvalido') }}
                  <p>
                    <a routerLink="/recuperar-contrasena">{{
                      t('recuperarContrasena.pedirOtro')
                    }}</a>
                  </p>
                </app-alert>
              }
              @case ('exito') {
                <app-alert tone="exito" [title]="t('recuperarContrasena.exitoNuevaTitulo')">
                  {{ t('recuperarContrasena.exitoNuevaDetalle') }}
                  <p>
                    <a routerLink="/admin/login">{{ t('registro.yaTengoCuenta') }}</a>
                  </p>
                </app-alert>
              }
              @case ('formulario') {
                <form (submit)="enviar($event)" novalidate>
                  <app-input
                    [label]="t('recuperarContrasena.nueva')"
                    type="password"
                    autocomplete="new-password"
                    [required]="true"
                    [(value)]="password"
                  />
                  <app-password-strength [password]="password()" />
                  @if (error(); as mensaje) {
                    <app-alert tone="error">{{ mensaje }}</app-alert>
                  }
                  <app-button type="submit" [loading]="enviando()">
                    {{
                      enviando()
                        ? t('recuperarContrasena.guardando')
                        : t('recuperarContrasena.guardar')
                    }}
                  </app-button>
                </form>
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
    form {
      display: grid;
      gap: var(--space-md);
    }
  `,
})
export class ResetPasswordPage {
  private readonly auth = inject(AuthService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly transloco = inject(TranslocoService);

  protected readonly estado = signal<Estado>('formulario');
  protected readonly password = signal('');
  protected readonly enviando = signal(false);
  protected readonly error = signal<string | null>(null);
  private readonly token = this.ruta.snapshot.queryParamMap.get('token');

  constructor() {
    if (!this.token) {
      this.estado.set('tokenInvalido');
    }
  }

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    if (!isPasswordValid(this.password())) {
      this.error.set(this.transloco.translate('registro.passwordSinComplejidad'));
      return;
    }
    if (!this.token) {
      this.estado.set('tokenInvalido');
      return;
    }

    this.enviando.set(true);
    try {
      await this.auth.resetPassword(this.token, this.password());
      this.estado.set('exito');
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        this.estado.set('tokenInvalido');
      } else {
        this.error.set(
          error instanceof ApiError
            ? error.message
            : this.transloco.translate('recuperarContrasena.error'),
        );
      }
    } finally {
      this.enviando.set(false);
    }
  }
}
