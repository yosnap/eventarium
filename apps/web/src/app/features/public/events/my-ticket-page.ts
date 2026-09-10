import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { Chip } from '../../../shared/ui/chip';
import { Reveal } from '../../../shared/ui/reveal.directive';

type Estado = 'comprobando' | 'con-qr' | 'sin-qr' | 'error';

const CLAVE_POR_ESTADO: Record<string, string> = {
  confirmed: 'confirmada',
  cancelled: 'cancelada',
  rejected: 'rechazada',
  waitlisted: 'listaEspera',
  pending_approval: 'pendienteAprobacion',
  pending_verification: 'pendienteVerificacion',
};

/**
 * `/mi-entrada` (fase 4 del PRD, fase 4 de trabajo): vuelve a mostrar el QR
 * de una entrada reutilizando el token de autocancelación — nunca genera uno
 * nuevo (`RegistrationsService.getMyTicket` hace un `GET`, no lo consume).
 * Mismo patrón que `verify-registration-page`/`cancel-registration-page`.
 *
 * El maquetado del estado `con-qr` sigue la tarjeta `.ticket` de la
 * referencia (`inscripcion.html:148-161`): rótulo + nombre arriba, QR grande
 * en el centro, chip de validez abajo. `MyTicketInfo` no trae fecha, lugar ni
 * código de entrada — solo `status`/`full_name`/`has_qr` —, así que esos
 * campos del prototipo no se replican aquí: mostrar un dato inventado sería
 * peor que no mostrarlo.
 */
@Component({
  selector: 'app-my-ticket-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Card, Chip, Reveal],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('miEntrada.titulo')">
        <div class="envoltura" appReveal>
          <app-card [heading]="t('miEntrada.titulo')">
            <div aria-live="polite">
              @switch (estado()) {
                @case ('comprobando') {
                  <app-alert tone="info">{{ t('miEntrada.comprobando') }}</app-alert>
                }
                @case ('con-qr') {
                  <div class="ticket">
                    <div class="ticket__top">
                      <span class="rotulo-seccion">{{ t('miEntrada.titulo') }}</span>
                      <p class="ticket__nombre">{{ t('miEntrada.saludo', { nombre: nombre() }) }}</p>
                    </div>
                    <div class="marco-qr">
                      <img [src]="qrUrl()" [alt]="t('miEntrada.qrAlt')" width="220" height="220" />
                    </div>
                    <div class="ticket__pie">
                      <app-chip tone="ok">{{ t('miEntrada.chipValida') }}</app-chip>
                    </div>
                  </div>
                }
                @case ('sin-qr') {
                  <app-alert tone="info" [title]="t('miEntrada.estado.' + claveEstado())">
                    {{ t('miEntrada.sinQrDetalle') }}
                  </app-alert>
                }
                @case ('error') {
                  <app-alert tone="error" [title]="t('miEntrada.errorTitulo')">
                    {{ t('miEntrada.errorDetalle') }}
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
      text-align: center;
    }
    .ticket {
      display: grid;
      gap: var(--space-md);
    }
    .ticket__top {
      padding-bottom: var(--space-md);
      border-bottom: 1px dashed var(--border-strong);
    }
    .ticket__nombre {
      margin: 0.5rem 0 0;
    }
    /* El QR se lee con la cámara del móvil, no con la pantalla en el modo de
       color que tenga la persona: fondo claro fijo en los dos temas, no
       "white" invertido a negro en oscuro, o muchos lectores de código dejan
       de reconocerlo. Literal intencionado, no un color de marca. */
    .marco-qr {
      display: inline-block;
      padding: var(--space-md);
      background-color: white;
      border-radius: var(--radius-md);
    }
    img {
      display: block;
      margin: 0 auto;
    }
    .ticket__pie {
      display: flex;
      justify-content: center;
    }
  `,
})
export class MyTicketPage {
  private readonly registrations = inject(RegistrationsService);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly nombre = signal('');
  protected readonly claveEstado = signal('confirmada');
  protected readonly qrUrl = signal('');

  constructor() {
    const token = this.ruta.snapshot.queryParamMap.get('token');
    if (!token) {
      this.estado.set('error');
      return;
    }
    void this.cargar(token);
  }

  private async cargar(token: string): Promise<void> {
    try {
      const info = await this.registrations.getMyTicket(token);
      this.nombre.set(info.full_name);
      this.claveEstado.set(CLAVE_POR_ESTADO[info.status] ?? info.status);
      if (info.has_qr) {
        this.qrUrl.set(this.registrations.myTicketQrUrl(token));
        this.estado.set('con-qr');
      } else {
        this.estado.set('sin-qr');
      }
    } catch {
      this.estado.set('error');
    }
  }
}
