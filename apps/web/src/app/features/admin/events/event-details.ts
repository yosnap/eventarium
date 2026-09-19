import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  inject,
  input,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { capitalizarClaveDeTraduccion } from '../../../shared/text/capitalizar-clave-de-traduccion';
import {
  IMAGEN_MIMES_PERMITIDOS,
  IMAGEN_TAMANO_MAXIMO,
} from '../../../shared/uploads/image-upload-constraints';

type EventStatus = 'draft' | 'published' | 'archived';

interface EventoResumen {
  readonly cover_url: string | null;
  readonly status: EventStatus;
}

/**
 * Solo lo que es del evento en sí, no de sus secciones: portada y estado
 * (publicar/archivar). Agenda, sedes, ponentes, patrocinadores, entradas,
 * descuentos, inscripciones y check-in ya tienen su propia ruta y su propia
 * entrada en `enlacesDeEvento()` (`admin-nav.ts`) — antes vivían también aquí,
 * duplicadas dentro de «Editar datos», lo que hacía de esa pantalla un cajón
 * de sastre con todo el evento a la vez, en vez del formulario de datos que
 * su nombre promete.
 *
 * `event-form.ts` delega aquí en cuanto hay un `eventId` — este componente carga sus
 * propios datos a partir de él, igual que ya hace cada sección con la suya, en vez de
 * heredarlos del padre.
 */
@Component({
  selector: 'app-event-details',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <div class="fila-superior">
          <app-card [heading]="t('admin.events.formulario.portada')">
            @if (portadaUrl(); as url) {
              <img [src]="url" [alt]="t('admin.events.formulario.portada')" height="120" />
            } @else {
              <p>{{ t('admin.events.formulario.sinPortada') }}</p>
            }
            <!-- TODO(media-picker): sustituir por app-media-picker en cuanto la
                 rama feat/cookies-analitica-externa (donde vive ese componente)
                 se fusione en develop — hoy no está disponible en esta rama. -->
            <label class="etiqueta-fichero" for="portada">{{
              t('admin.events.formulario.subirPortada')
            }}</label>
            <input
              id="portada"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              (change)="alSeleccionarPortada($event)"
            />
            @if (errorPortada(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }
          </app-card>

          <app-card [heading]="t('admin.events.formulario.estadoActual')">
            <p>
              {{ t('admin.events.estado' + capitaliza(estadoActual())) }}
            </p>
            <div class="acciones-estado">
              @if (estadoActual() === 'draft') {
                <app-button
                  type="button"
                  variant="secundario"
                  [loading]="cambiandoEstado()"
                  (pulsado)="cambiarEstado('published')"
                >
                  {{ t('admin.events.formulario.publicar') }}
                </app-button>
              }
              @if (estadoActual() !== 'archived') {
                <app-button
                  type="button"
                  variant="peligro"
                  [loading]="cambiandoEstado()"
                  (pulsado)="cambiarEstado('archived')"
                >
                  {{ t('admin.events.formulario.archivar') }}
                </app-button>
              }
            </div>
            @if (errorEstado(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }
          </app-card>
        </div>
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    /* Portada y estado caben de sobra una junto a la otra: antes iban
     * apiladas a todo el ancho de la página sin motivo. */
    .fila-superior {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
      gap: var(--space-lg);
      align-items: start;
    }
    .etiqueta-fichero {
      display: block;
      margin-top: var(--space-sm);
      font-weight: 500;
    }
    .acciones-estado {
      display: flex;
      gap: var(--space-md);
      margin-top: var(--space-sm);
    }
  `,
})
export class EventDetails implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly cambiandoEstado = signal(false);
  protected readonly errorEstado = signal<string | null>(null);
  protected readonly errorPortada = signal<string | null>(null);

  protected readonly estadoActual = signal<EventStatus>('draft');
  protected readonly portadaUrl = signal<string | null>(null);

  ngOnInit(): void {
    void this.cargar();
  }

  protected capitaliza(valor: string): string {
    return capitalizarClaveDeTraduccion(valor);
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const evento = await firstValueFrom(
        this.http.get<EventoResumen>(this.api.url(`/events/${this.eventId()}`)),
      );
      this.estadoActual.set(evento.status);
      this.portadaUrl.set(evento.cover_url);
    } catch (error) {
      this.errorEstado.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected async cambiarEstado(nuevoEstado: EventStatus): Promise<void> {
    this.cambiandoEstado.set(true);
    this.errorEstado.set(null);
    try {
      const actualizado = await firstValueFrom(
        this.http.patch<EventoResumen>(this.api.url(`/events/${this.eventId()}`), {
          status: nuevoEstado,
        }),
      );
      this.estadoActual.set(actualizado.status);
    } catch (error) {
      this.errorEstado.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    } finally {
      this.cambiandoEstado.set(false);
    }
  }

  protected alSeleccionarPortada(evento: Event): void {
    this.errorPortada.set(null);
    const fichero = (evento.target as HTMLInputElement).files?.[0] ?? null;
    if (!fichero) {
      return;
    }
    if (!IMAGEN_MIMES_PERMITIDOS.has(fichero.type)) {
      this.errorPortada.set(this.transloco.translate('admin.events.formulario.portadaNoValida'));
      (evento.target as HTMLInputElement).value = '';
      return;
    }
    if (fichero.size > IMAGEN_TAMANO_MAXIMO) {
      this.errorPortada.set(
        this.transloco.translate('admin.events.formulario.portadaDemasiadoGrande'),
      );
      (evento.target as HTMLInputElement).value = '';
      return;
    }
    void this.subirPortada(fichero);
  }

  private async subirPortada(fichero: File): Promise<void> {
    const datos = new FormData();
    datos.append('fichero', fichero);
    try {
      const actualizado = await firstValueFrom(
        this.http.put<EventoResumen>(this.api.url(`/events/${this.eventId()}/cover`), datos),
      );
      this.portadaUrl.set(actualizado.cover_url);
    } catch (error) {
      this.errorPortada.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    }
  }
}
