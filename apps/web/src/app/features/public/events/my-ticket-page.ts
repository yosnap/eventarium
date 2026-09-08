import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { RegistrationsService } from '../../../core/registrations/registrations.service';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';

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
 */
@Component({
  selector: 'app-my-ticket-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Card],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" class="pagina">
        <app-card [heading]="t('miEntrada.titulo')">
          <div aria-live="polite">
            @switch (estado()) {
              @case ('comprobando') {
                <app-alert tone="info">{{ t('miEntrada.comprobando') }}</app-alert>
              }
              @case ('con-qr') {
                <p>{{ t('miEntrada.saludo', { nombre: nombre() }) }}</p>
                <img [src]="qrUrl()" [alt]="t('miEntrada.qrAlt')" width="240" height="240" />
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
      text-align: center;
    }
    img {
      display: block;
      margin: 0 auto;
      border-radius: var(--radius-md);
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
