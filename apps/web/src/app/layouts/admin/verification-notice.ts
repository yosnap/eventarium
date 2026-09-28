import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import { ApiError } from '../../core/api/error.interceptor';
import { AuthService } from '../../core/auth/auth.service';
import { VerificationStatusResponse } from '../../core/api/generated/models/verification-status-response';
import { Alert } from '../../shared/ui/alert';
import { Button } from '../../shared/ui/button';

/**
 * Aviso del panel para quien aún no ha verificado su correo: la cuenta está
 * limitada (el backend le niega crear organización con 403) y, sin este
 * aviso, lo único que veía era «No se pudieron cargar los datos».
 *
 * Consulta `/users/me/verification`, que no exige organización activa —una
 * cuenta sin verificar casi nunca tiene una—, y ofrece reenviar el enlace
 * sin volver a escribir el correo ni pasar Turnstile (ya hay sesión).
 * Si la consulta falla no pinta nada: es un aviso, no algo que deba tapar
 * el panel.
 *
 * Tono `error` a propósito (borde de peligro, `role="alert"`): la cuenta no
 * puede hacer lo que vino a hacer, y el shell lo monta una sola vez por
 * sesión, así que el anuncio asertivo no se repite al navegar.
 * Durante una suplantación el aviso se ve (el superadmin debe saberlo) pero
 * sin botón: el backend rechaza el reenvío porque la sesión es de solo lectura.
 */
@Component({
  selector: 'app-verification-notice',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button],
  template: `
    @if (estado(); as actual) {
      @if (!actual.email_verified) {
        <ng-container *transloco="let t">
          <div class="aviso">
            <app-alert tone="error" [title]="t('admin.verificacionPendiente.titulo')">
              <p>{{ t('admin.verificacionPendiente.texto', { correo: actual.email }) }}</p>
              @if (mensaje(); as texto) {
                <p class="resultado">{{ texto }}</p>
              }
              @if (!auth.suplantando()) {
                <div>
                  <app-button
                    type="button"
                    variant="secundario"
                    [compacto]="true"
                    [loading]="enviando()"
                    [disabled]="enviado()"
                    (pulsado)="reenviar()"
                  >
                    {{ t('admin.verificacionPendiente.reenviar') }}
                  </app-button>
                </div>
              }
            </app-alert>
          </div>
        </ng-container>
      }
    }
  `,
  styles: `
    .aviso {
      margin-bottom: var(--space-md);
    }
    p {
      margin: 0;
    }
    .resultado {
      font-weight: 600;
    }
  `,
})
export class VerificationNotice {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  protected readonly auth = inject(AuthService);

  protected readonly estado = signal<VerificationStatusResponse | null>(null);
  protected readonly enviando = signal(false);
  /** Tras un reenvío correcto el botón queda deshabilitado: repetirlo solo
   * choca con el límite por cuenta del backend. */
  protected readonly enviado = signal(false);
  protected readonly mensaje = signal<string | null>(null);

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      this.estado.set(
        await firstValueFrom(
          this.http.get<VerificationStatusResponse>(this.api.url('/users/me/verification')),
        ),
      );
    } catch {
      // Sin estado no hay aviso: ver el comentario de la clase.
    }
  }

  protected async reenviar(): Promise<void> {
    this.enviando.set(true);
    this.mensaje.set(null);
    try {
      await firstValueFrom(this.http.post(this.api.url('/users/me/resend-verification'), {}));
      this.enviado.set(true);
      this.mensaje.set(this.transloco.translate('admin.verificacionPendiente.reenviado'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // Verificada mientras tanto (en otra pestaña): el aviso sobra.
        this.estado.update((actual) => (actual ? { ...actual, email_verified: true } : actual));
        return;
      }
      this.mensaje.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.verificacionPendiente.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
