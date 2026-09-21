import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import {
  type MyRegistrationItem,
  RegistrationsService,
} from '../../../core/registrations/registrations.service';
import { Alert } from '../../../shared/ui/alert';
import { Reveal } from '../../../shared/ui/reveal.directive';

type Estado = 'comprobando' | 'conInscripciones' | 'sinInscripciones' | 'tokenInvalido';

/**
 * Convierte `pending_verification` en `PendingVerification`, para componer
 * la clave de i18n del estado — mismo criterio que `claveDeEstado` del panel
 * de organizador (`features/admin/events/registration-types.ts`), duplicado
 * aquí a propósito: esta página vive en el árbol público, sin acoplar su
 * texto (más neutro, dirigido al asistente) al namespace `admin.*`.
 */
function claveDeEstado(valor: string): string {
  return valor
    .split('_')
    .map((parte) => parte.charAt(0).toUpperCase() + parte.slice(1))
    .join('');
}

/**
 * Consume el token del magic-link de «Mis eventos» y lista las
 * inscripciones. CSR, como `VerifyRegistrationPage`: sin interacción que
 * dispare el resultado, así que se anuncia con `aria-live="assertive"`.
 *
 * Token de un solo uso: recargar esta página pide un enlace nuevo (trade-off
 * de UX aceptado en el plan) — un token inválido y uno caducado comparten el
 * mismo mensaje, sin distinguir el motivo (misma decisión anti-enumeración
 * que en la solicitud).
 */
@Component({
  selector: 'app-mis-eventos-listado-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, TranslocoDirective, RouterLink, Alert, Reveal],
  template: `
    <ng-container *transloco="let t">
      <div class="ancho-maximo envoltura" appReveal>
        <h1>{{ t('publico.misEventos.listadoTitulo') }}</h1>

        <div aria-live="assertive">
          @switch (estado()) {
            @case ('comprobando') {
              <app-alert tone="info">{{ t('publico.misEventos.comprobando') }}</app-alert>
            }
            @case ('tokenInvalido') {
              <app-alert tone="error" [title]="t('publico.misEventos.errorTitulo')">
                {{ t('publico.misEventos.tokenInvalido') }}
                <p>
                  <a routerLink="/mis-eventos">{{ t('publico.misEventos.pedirOtro') }}</a>
                </p>
              </app-alert>
            }
            @case ('sinInscripciones') {
              <app-alert tone="info">{{ t('publico.misEventos.sinInscripciones') }}</app-alert>
            }
            @case ('conInscripciones') {
              <ul class="listado">
                @for (fila of inscripciones(); track fila.event_slug + fila.status) {
                  <li>
                    <a [routerLink]="['/eventos', fila.event_slug]">{{ fila.event_title }}</a>
                    <span class="detalle">
                      {{ fila.starts_at | date: 'd MMM y, HH:mm' }} · {{ fila.organization_name }}
                      · {{ t('publico.misEventos.estado.' + claveDeEstado(fila.status)) }}
                    </span>
                  </li>
                }
              </ul>
            }
          }
        </div>
      </div>
    </ng-container>
  `,
  styles: `
    .envoltura {
      padding: var(--space-lg) 0;
    }
    .listado {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-md);
    }
    .listado li {
      display: grid;
      gap: var(--space-xs);
      padding: var(--space-md);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
    .detalle {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
  `,
})
export class MisEventosListadoPage {
  private readonly registrations = inject(RegistrationsService);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly inscripciones = signal<readonly MyRegistrationItem[]>([]);
  protected readonly claveDeEstado = claveDeEstado;

  constructor() {
    const token = this.ruta.snapshot.queryParamMap.get('token');
    if (!token) {
      this.estado.set('tokenInvalido');
      return;
    }
    void this.cargar(token);
  }

  private async cargar(token: string): Promise<void> {
    try {
      const inscripciones = await this.registrations.getMyRegistrations(token);
      this.inscripciones.set(inscripciones);
      this.estado.set(inscripciones.length > 0 ? 'conInscripciones' : 'sinInscripciones');
    } catch {
      this.estado.set('tokenInvalido');
    }
  }
}
