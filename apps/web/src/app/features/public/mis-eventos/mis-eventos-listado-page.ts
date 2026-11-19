import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import {
  type MyRegistrationItem,
  RegistrationsService,
} from '../../../core/registrations/registrations.service';
import { MisEventosListado } from './mis-eventos-listado';
import { Alert } from '../../../shared/ui/alert';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { EnlacePipe } from '../../../core/i18n/enlace.pipe';

type Estado = 'comprobando' | 'conInscripciones' | 'sinInscripciones' | 'tokenInvalido';

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
  imports: [EnlacePipe, TranslocoDirective, RouterLink, Alert, Reveal, MisEventosListado],
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
                  <a [routerLink]="'/mis-eventos' | enlace">{{
                    t('publico.misEventos.pedirOtro')
                  }}</a>
                </p>
              </app-alert>
            }
            @case ('sinInscripciones') {
              <app-alert tone="info">{{ t('publico.misEventos.sinInscripciones') }}</app-alert>
            }
            @case ('conInscripciones') {
              <app-mis-eventos-listado [inscripciones]="inscripciones()" />
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
  `,
})
export class MisEventosListadoPage {
  private readonly registrations = inject(RegistrationsService);
  private readonly ruta = inject(ActivatedRoute);

  protected readonly estado = signal<Estado>('comprobando');
  protected readonly inscripciones = signal<readonly MyRegistrationItem[]>([]);

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
