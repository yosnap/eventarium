import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { Chip, type ChipTone } from '../../../shared/ui/chip';
import { Reveal } from '../../../shared/ui/reveal.directive';

type Estado = 'comprobando' | 'exito' | 'error';

/** Estado real de la inscripción tras verificar (`_MENSAJES_POR_ESTADO` en
 * `registrations/public_router.py`): nunca "cancelled"/"rejected" — esos solo
 * se alcanzan desde el panel del organizador o una autocancelación, no desde
 * el enlace de verificación de email. */
const CLAVE_POR_ESTADO: Record<string, string> = {
  confirmed: 'confirmada',
  pending_approval: 'pendienteAprobacion',
  pending_payment: 'pendientePago',
  waitlisted: 'listaEspera',
};

const TONO_POR_ESTADO: Record<string, ChipTone> = {
  confirmed: 'ok',
  pending_approval: 'espera',
  pending_payment: 'espera',
  waitlisted: 'espera',
};

/**
 * Consume el token de verificación de una inscripción. CSR, como
 * `verificar-correo`: sin interacción del usuario que dispare el resultado,
 * así que se anuncia con `aria-live="assertive"` para que un lector de
 * pantalla se entere igualmente.
 *
 * El estado (`status`) que devuelve `/registrations/verify` distingue si la
 * inscripción quedó confirmada, pendiente de aprobación, pendiente de pago o
 * en lista de espera — un chip de estado (mismo componente que el panel del
 * organizador) refuerza visualmente el mensaje sin inventar un dato que el
 * backend no da (código de entrada, fecha, etc.).
 */
@Component({
  selector: 'app-verify-registration-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Card, Chip, Reveal],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('verificarInscripcion.titulo')">
        <div class="envoltura" appReveal>
          <app-card [heading]="t('verificarInscripcion.titulo')">
            <div aria-live="assertive">
              @switch (estado()) {
                @case ('comprobando') {
                  <app-alert tone="info">{{ t('verificarInscripcion.verificando') }}</app-alert>
                }
                @case ('exito') {
                  @if (claveEstado(); as clave) {
                    <app-chip class="chip-estado" [tone]="tonoEstado()">
                      {{ t('verificarInscripcion.estado.' + clave) }}
                    </app-chip>
                  }
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
        </div>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    .envoltura {
      width: min(26rem, 100%);
    }
    .chip-estado {
      display: block;
      margin-bottom: var(--space-md);
    }
  `,
})
export class VerifyRegistrationPage {
  private readonly registrations = inject(RegistrationsService);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly mensaje = signal('');
  protected readonly claveEstado = signal<string | null>(null);
  protected readonly tonoEstado = signal<ChipTone>('neutro');

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
      this.claveEstado.set(CLAVE_POR_ESTADO[resultado.status] ?? null);
      this.tonoEstado.set(TONO_POR_ESTADO[resultado.status] ?? 'neutro');
      this.estado.set('exito');
    } catch {
      this.estado.set('error');
    }
  }
}
