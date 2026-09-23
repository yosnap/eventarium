import {
  ChangeDetectionStrategy,
  Component,
  afterNextRender,
  computed,
  inject,
  input,
  model,
  signal,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import {
  type PoliticasPublicas,
  PublicPoliciesService,
} from '../../../core/policies/public-policies.service';
import { Button } from '../../../shared/ui/button';
import { Checkbox } from '../../../shared/ui/checkbox';

type EstadoDeCarga = 'cargando' | 'listo' | 'error';

/**
 * Consentimientos del formulario de inscripción, cada uno independiente:
 * tratamiento de datos (obligatorio), marketing y grabación (opcionales, sin
 * condicionar la inscripción) y, si el evento tiene textos propios, la
 * aceptación de las condiciones del organizador (obligatoria). Quien lo usa
 * guarda los valores y los valida; este componente carga los textos vigentes
 * y sabe qué versiones se están aceptando.
 *
 * Los textos se piden solo en el navegador y tras el primer render: así el
 * servidor y la hidratación pintan lo mismo (sin casilla). Hasta que llegan, o
 * si fallan, no se puede enviar (`listo()`): sin ellos no se sabe si hay que
 * aceptar algo, y el servidor rechazaría el envío.
 */
@Component({
  selector: 'app-registration-consents',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, Checkbox],
  template: `
    <ng-container *transloco="let t">
      @if (estado() === 'error') {
        <div class="aviso" role="alert">
          <p>{{ t('inscripcion.politicas.errorCarga') }}</p>
          <app-button variant="secundario" [compacto]="true" (pulsado)="recargar()">
            {{ t('inscripcion.politicas.reintentar') }}
          </app-button>
        </div>
      } @else if (hayPoliticas()) {
        <app-checkbox
          fieldId="insc-politicas"
          [label]="
            t('inscripcion.politicas.aceptar', { organizacion: politicas()!.organization_name })
          "
          [describedBy]="
            errorPoliticas()
              ? 'insc-politicas-enlace insc-politicas-error'
              : 'insc-politicas-enlace'
          "
          [(checked)]="politicasAceptadas"
        />
        <p id="insc-politicas-enlace" class="enlace">
          <a [href]="enlacePoliticas()" target="_blank" rel="noopener">
            {{ t('inscripcion.politicas.leer') }}
          </a>
        </p>
        @if (errorPoliticas()) {
          <p id="insc-politicas-error" class="error-pregunta" role="alert">
            {{ errorPoliticas() }}
          </p>
        }
      }

      <app-checkbox
        fieldId="insc-tratamiento-datos"
        [label]="t('inscripcion.tratamientoDatos')"
        [describedBy]="errorConsentimiento() ? 'insc-tratamiento-datos-error' : null"
        [(checked)]="dataProcessingAccepted"
      />
      <p class="enlace">
        <a [href]="enlacePrivacidad()" target="_blank" rel="noopener">
          {{ t('inscripcion.politicas.leerPrivacidad') }}
        </a>
      </p>
      @if (errorConsentimiento()) {
        <p id="insc-tratamiento-datos-error" class="error-pregunta" role="alert">
          {{ errorConsentimiento() }}
        </p>
      }

      <app-checkbox [label]="t('inscripcion.marketing')" [(checked)]="marketingAccepted" />

      <app-checkbox [label]="t('inscripcion.grabacion')" [(checked)]="recordingAccepted" />
    </ng-container>
  `,
  styles: `
    :host {
      display: contents;
    }
    .error-pregunta {
      margin: 0;
      color: var(--danger);
      font-size: 0.875rem;
    }
    .enlace {
      margin: calc(-1 * var(--space-sm)) 0 0;
      font-size: 0.875rem;
    }
    .aviso {
      display: grid;
      gap: var(--space-sm);
      justify-items: start;
      padding: var(--space-md);
      border: 1px solid var(--danger);
      border-radius: var(--radius-md);
    }
    .aviso p {
      margin: 0;
    }
  `,
})
export class RegistrationConsents {
  readonly slug = input.required<string>();
  readonly errorConsentimiento = input<string | null>(null);
  readonly errorPoliticas = input<string | null>(null);

  readonly dataProcessingAccepted = model(false);
  readonly marketingAccepted = model(false);
  readonly recordingAccepted = model(false);
  readonly politicasAceptadas = model(false);

  private readonly servicio = inject(PublicPoliciesService);

  protected readonly estado = signal<EstadoDeCarga>('cargando');
  protected readonly politicas = signal<PoliticasPublicas | null>(null);
  protected readonly hayPoliticas = computed(() => (this.politicas()?.policies.length ?? 0) > 0);

  protected readonly enlacePoliticas = computed(() => `/eventos/${this.slug()}/politicas`);
  /** La privacidad del organizador si la tiene; si no, la general. */
  protected readonly enlacePrivacidad = computed(() =>
    this.politicas()?.policies.some((politica) => politica.kind === 'privacidad')
      ? `/eventos/${this.slug()}/politicas#privacidad`
      : '/legal/privacidad',
  );

  /** Ya se sabe qué hay que aceptar: sin esto, no se debe enviar. */
  readonly listo = computed(() => this.estado() === 'listo');

  /** Falta marcar la casilla de las condiciones del organizador. */
  readonly faltaAceptarPoliticas = computed(
    () => this.hayPoliticas() && !this.politicasAceptadas(),
  );

  /** Versiones que se muestran y se aceptan (vacía si el evento no tiene). */
  readonly idsAceptados = computed(() =>
    this.politicasAceptadas()
      ? (this.politicas()?.policies.map((politica) => politica.version_id) ?? [])
      : [],
  );

  constructor() {
    afterNextRender(() => void this.recargar());
  }

  /** Lee los textos vigentes y desmarca la casilla. Se usa al cargar, al
   * reintentar tras un fallo y cuando el servidor responde que los textos han
   * cambiado mientras se rellenaba el formulario. Devuelve si lo consiguió. */
  async recargar(): Promise<boolean> {
    this.politicasAceptadas.set(false);
    this.estado.set('cargando');
    try {
      this.politicas.set(await this.servicio.obtener(this.slug()));
      this.estado.set('listo');
      return true;
    } catch (error) {
      // Una API anterior a esta funcionalidad no tiene el endpoint: equivale a
      // un evento sin textos, y la inscripción no debe bloquearse por ello.
      if (error instanceof ApiError && error.status === 404) {
        this.politicas.set(null);
        this.estado.set('listo');
        return true;
      }
      this.politicas.set(null);
      this.estado.set('error');
      return false;
    }
  }
}
