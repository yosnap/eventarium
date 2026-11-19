import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  inject,
  input,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { MediaElegida, MediaPicker } from '../../../shared/ui/media-picker';
import { capitalizarClaveDeTraduccion } from '../../../shared/text/capitalizar-clave-de-traduccion';
import { PORTADA_ACEPTADOS } from '../../../shared/uploads/image-upload-constraints';
import { EventCancelCard } from './event-cancel-card';
import { EventNearbyPlaces } from './event-nearby-places';
import { EventTranslationSummary } from './event-translation-summary';

type EventStatus = 'draft' | 'published' | 'archived' | 'cancelled';

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
 * `event-form.ts` delega aquí en cuanto hay un `eventId` y proyecta su formulario,
 * que esta ficha coloca junto a portada y estado — este componente carga sus
 * propios datos a partir de él, igual que ya hace cada sección con la suya, en vez de
 * heredarlos del padre.
 */
@Component({
  selector: 'app-event-details',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    EventNearbyPlaces,
    TranslocoDirective,
    Alert,
    Button,
    Card,
    MediaPicker,
    EventCancelCard,
    EventTranslationSummary,
  ],
  template: `
    <ng-container *transloco="let t">
      <!-- El formulario de datos llega proyectado desde \`event-form.ts\` y queda
           fuera del @if: no debe esperar a que carguen portada y estado. -->
      <div class="principal">
        <div class="principal__formulario"><ng-content /></div>

        <aside class="lateral">
          @if (cargando()) {
            <p>{{ t('comun.cargando') }}</p>
          } @else {
            <app-event-translation-summary [eventId]="eventId()" />
            <div class="estado-cancelar">
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
                  @if (estadoActual() !== 'archived' && estadoActual() !== 'cancelled') {
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
              @if (estadoActual() === 'published' || estadoActual() === 'cancelled') {
                <app-event-cancel-card
                  [eventId]="eventId()"
                  [yaCancelado]="estadoActual() === 'cancelled'"
                  (cancelacionConfirmada)="estadoActual.set('cancelled')"
                  (eliminado)="alEliminar()"
                />
              }
            </div>

            <app-card [heading]="t('admin.events.formulario.portada')">
              <app-media-picker
                #portadaPicker
                [etiqueta]="t('admin.events.formulario.portada')"
                [aceptados]="PORTADA_ACEPTADOS"
                kind="events"
                variante="ancha"
                [url]="portadaUrl()"
                [permitirQuitar]="true"
                [quitando]="quitandoPortada()"
                (mediaElegido)="asignarPortada($event, portadaPicker)"
                (quitado)="quitarPortada()"
              />
              @if (errorPortada(); as mensaje) {
                <app-alert tone="error">{{ mensaje }}</app-alert>
              }
            </app-card>

            <app-event-nearby-places [eventId]="eventId()" />
          }
        </aside>
      </div>
    </ng-container>
  `,
  styles: `
    /* El formulario a la izquierda (3/5 del ancho) y, a la derecha, estado y
     * cancelar el evento en una fila; debajo, la portada y «Qué hay cerca». */
    :host {
      display: block;
    }
    .principal {
      display: grid;
      grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
      gap: var(--space-lg);
      align-items: start;
    }
    .lateral {
      display: grid;
      gap: var(--space-lg);
      min-width: 0;
    }
    /* Estado y cancelar lado a lado mientras quepan; si no, uno bajo otro.
     * Con la misma altura: cada host se estira a la fila y, al ser rejilla,
     * estira también la tarjeta que lleva dentro. */
    .estado-cancelar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(14rem, 100%), 1fr));
      gap: var(--space-lg);
    }
    .estado-cancelar > * {
      display: grid;
    }
    /* Sin sitio para la columna lateral, todo baja tras el formulario. */
    @media (max-width: 75rem) {
      .principal {
        grid-template-columns: minmax(0, 1fr);
      }
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
  protected readonly PORTADA_ACEPTADOS = PORTADA_ACEPTADOS;

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly router = inject(Router);

  protected readonly cargando = signal(true);
  protected readonly cambiandoEstado = signal(false);
  protected readonly errorEstado = signal<string | null>(null);
  protected readonly errorPortada = signal<string | null>(null);
  protected readonly quitandoPortada = signal(false);

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

  /** Desasigna la portada en el servidor (`DELETE /events/{id}/cover`): la
   * imagen sigue en la biblioteca. Sin previsualización optimista: el
   * selector solo vuelve a vacío cuando la API lo confirma. */
  protected async quitarPortada(): Promise<void> {
    this.errorPortada.set(null);
    this.quitandoPortada.set(true);
    try {
      const actualizado = await firstValueFrom(
        this.http.delete<EventoResumen>(this.api.url(`/events/${this.eventId()}/cover`)),
      );
      this.portadaUrl.set(actualizado.cover_url);
    } catch (error) {
      this.errorPortada.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    } finally {
      this.quitandoPortada.set(false);
    }
  }

  /** El fichero/URL/biblioteca ya se resolvió a un `media_id` dentro de
   * `MediaPicker` (Fase 3 del plan de biblioteca de medios): aquí solo queda
   * asignarlo como portada. Si la asignación falla, `picker.revertir()`
   * deshace la previsualización optimista — si no, se quedaría mostrando
   * la imagen nueva como si estuviera guardada (hallazgo de code-review). */
  protected async asignarPortada(media: MediaElegida, picker: MediaPicker): Promise<void> {
    this.errorPortada.set(null);
    try {
      const actualizado = await firstValueFrom(
        this.http.put<EventoResumen>(this.api.url(`/events/${this.eventId()}/cover`), {
          media_id: media.id,
        }),
      );
      this.portadaUrl.set(actualizado.cover_url);
    } catch (error) {
      picker.revertir();
      this.errorPortada.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    }
  }

  /** El evento acaba de eliminarse: ya no existe en el panel, se vuelve al listado. */
  protected alEliminar(): void {
    void this.router.navigate(['/dashboard/events']);
  }
}
