import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService, EnlaceSocial, displayName } from '../../../core/auth/auth.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { PasswordStrength, isPasswordValid } from '../../../shared/ui/password-strength';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TIPOS_DE_ENLACE = ['twitter', 'linkedin', 'instagram', 'web'] as const;

/**
 * Cuenta propia: perfil, correo (con confirmación), contraseña y enlaces sociales.
 *
 * Cada sección tiene su propio estado de guardado y error: son cuatro operaciones
 * independientes, y un fallo en una no debe bloquear ni aparentar afectar a las demás.
 */
@Component({
  selector: 'app-account-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, PasswordStrength],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.cuenta.titulo') }}</h1>

      <app-card [heading]="t('admin.cuenta.perfil.titulo')">
        <form (submit)="guardarPerfil($event)" novalidate>
          <app-input
            [label]="t('admin.cuenta.perfil.nombre')"
            autocomplete="given-name"
            [(value)]="firstName"
          />
          <app-input
            [label]="t('admin.cuenta.perfil.apellidos')"
            autocomplete="family-name"
            [(value)]="lastName"
          />
          @if (errorPerfil(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }
          @if (exitoPerfil()) {
            <app-alert tone="exito">{{ t('admin.cuenta.perfil.exito') }}</app-alert>
          }
          <app-button type="submit" [loading]="guardandoPerfil()">
            {{ t('admin.cuenta.guardar') }}
          </app-button>
        </form>
      </app-card>

      <app-card [heading]="t('admin.cuenta.correo.titulo')">
        <p>{{ t('admin.cuenta.correo.actual', { correo: auth.currentUser()?.email ?? '' }) }}</p>
        @if (exitoCorreo()) {
          <app-alert tone="exito">{{ t('admin.cuenta.correo.exito') }}</app-alert>
        } @else {
          <form (submit)="solicitarCambioDeCorreo($event)" novalidate>
            <app-input
              [label]="t('admin.cuenta.correo.nuevo')"
              type="email"
              autocomplete="email"
              [(value)]="nuevoCorreo"
            />
            <app-input
              [label]="t('admin.cuenta.correo.passwordActual')"
              type="password"
              autocomplete="current-password"
              [(value)]="passwordParaCorreo"
            />
            @if (errorCorreo(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }
            <app-button type="submit" [loading]="guardandoCorreo()">
              {{ t('admin.cuenta.correo.solicitar') }}
            </app-button>
          </form>
        }
      </app-card>

      <app-card [heading]="t('admin.cuenta.contrasena.titulo')">
        @if (exitoContrasena()) {
          <app-alert tone="exito">{{ t('admin.cuenta.contrasena.exito') }}</app-alert>
        } @else {
          <form (submit)="cambiarContrasena($event)" novalidate>
            <app-input
              [label]="t('admin.cuenta.contrasena.actual')"
              type="password"
              autocomplete="current-password"
              [(value)]="passwordActual"
            />
            <app-input
              [label]="t('admin.cuenta.contrasena.nueva')"
              type="password"
              autocomplete="new-password"
              [(value)]="passwordNueva"
            />
            <app-password-strength [password]="passwordNueva()" />
            @if (errorContrasena(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }
            <app-button type="submit" [loading]="guardandoContrasena()">
              {{ t('admin.cuenta.contrasena.cambiar') }}
            </app-button>
          </form>
        }
      </app-card>

      <app-card [heading]="t('admin.cuenta.enlaces.titulo')">
        @if (cargandoEnlaces()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else {
          <ul class="enlaces">
            @for (tipo of tiposDeEnlace; track tipo) {
              <li>
                <app-input
                  [label]="tipo"
                  [(value)]="valoresDeEnlace()[tipo]"
                  (blurred)="guardarEnlace(tipo)"
                />
              </li>
            }
          </ul>
          @if (errorEnlaces(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    app-card {
      display: block;
      margin-bottom: var(--space-lg);
    }
    form {
      display: grid;
      gap: var(--space-md);
      max-width: 26rem;
    }
    .enlaces {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-md);
      max-width: 26rem;
    }
  `,
})
export class AccountPage {
  protected readonly auth = inject(AuthService);
  private readonly transloco = inject(TranslocoService);
  protected readonly nombreDe = displayName;
  protected readonly tiposDeEnlace = TIPOS_DE_ENLACE;

  protected readonly firstName = signal(this.auth.currentUser()?.first_name ?? '');
  protected readonly lastName = signal(this.auth.currentUser()?.last_name ?? '');
  protected readonly guardandoPerfil = signal(false);
  protected readonly exitoPerfil = signal(false);
  protected readonly errorPerfil = signal<string | null>(null);

  protected readonly nuevoCorreo = signal('');
  protected readonly passwordParaCorreo = signal('');
  protected readonly guardandoCorreo = signal(false);
  protected readonly exitoCorreo = signal(false);
  protected readonly errorCorreo = signal<string | null>(null);

  protected readonly passwordActual = signal('');
  protected readonly passwordNueva = signal('');
  protected readonly guardandoContrasena = signal(false);
  protected readonly exitoContrasena = signal(false);
  protected readonly errorContrasena = signal<string | null>(null);

  protected readonly cargandoEnlaces = signal(true);
  protected readonly errorEnlaces = signal<string | null>(null);
  protected readonly valoresDeEnlace = signal<Record<string, string>>(
    Object.fromEntries(TIPOS_DE_ENLACE.map((tipo) => [tipo, ''])),
  );

  constructor() {
    void this.cargarPerfil();
    void this.cargarEnlaces();
  }

  private async cargarPerfil(): Promise<void> {
    // `currentUser()` puede seguir a `null` tras una recarga completa de página
    // aunque la sesión siga viva (`refresh()` solo renueva el token). Se pide el
    // usuario explícitamente en vez de asumir que el signal ya está poblado.
    const usuario = this.auth.currentUser() ?? (await this.auth.loadCurrentUser());
    this.firstName.set(usuario.first_name ?? '');
    this.lastName.set(usuario.last_name ?? '');
  }

  private async cargarEnlaces(): Promise<void> {
    try {
      const lista = await this.auth.listSocialLinks();
      this.valoresDeEnlace.set({
        ...this.valoresDeEnlace(),
        ...Object.fromEntries(lista.map((enlace: EnlaceSocial) => [enlace.kind, enlace.url])),
      });
    } catch (error) {
      this.errorEnlaces.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.cuenta.error'),
      );
    } finally {
      this.cargandoEnlaces.set(false);
    }
  }

  protected async guardarPerfil(evento: Event): Promise<void> {
    evento.preventDefault();
    this.errorPerfil.set(null);
    this.exitoPerfil.set(false);
    this.guardandoPerfil.set(true);
    try {
      await this.auth.updateMe({
        firstName: this.firstName().trim(),
        lastName: this.lastName().trim(),
      });
      this.exitoPerfil.set(true);
    } catch (error) {
      this.errorPerfil.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.cuenta.error'),
      );
    } finally {
      this.guardandoPerfil.set(false);
    }
  }

  protected async solicitarCambioDeCorreo(evento: Event): Promise<void> {
    evento.preventDefault();
    this.errorCorreo.set(null);
    const correo = this.nuevoCorreo().trim();
    if (!EMAIL_RE.test(correo)) {
      this.errorCorreo.set(this.transloco.translate('admin.cuenta.correo.invalido'));
      return;
    }
    if (!this.passwordParaCorreo()) {
      this.errorCorreo.set(this.transloco.translate('admin.cuenta.correo.passwordRequerida'));
      return;
    }

    this.guardandoCorreo.set(true);
    try {
      await this.auth.changeEmail(correo, this.passwordParaCorreo());
      this.exitoCorreo.set(true);
    } catch (error) {
      this.errorCorreo.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.cuenta.error'),
      );
    } finally {
      this.guardandoCorreo.set(false);
    }
  }

  protected async cambiarContrasena(evento: Event): Promise<void> {
    evento.preventDefault();
    this.errorContrasena.set(null);
    if (!isPasswordValid(this.passwordNueva())) {
      this.errorContrasena.set(this.transloco.translate('registro.passwordSinComplejidad'));
      return;
    }

    this.guardandoContrasena.set(true);
    try {
      await this.auth.changePassword(this.passwordActual(), this.passwordNueva());
      this.exitoContrasena.set(true);
    } catch (error) {
      this.errorContrasena.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.cuenta.error'),
      );
    } finally {
      this.guardandoContrasena.set(false);
    }
  }

  protected async guardarEnlace(tipo: string): Promise<void> {
    const url = this.valoresDeEnlace()[tipo]?.trim() ?? '';
    this.errorEnlaces.set(null);
    try {
      if (url) {
        await this.auth.upsertSocialLink(tipo, url);
      } else {
        await this.auth.deleteSocialLink(tipo);
      }
    } catch (error) {
      this.errorEnlaces.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.cuenta.error'),
      );
    }
  }
}
