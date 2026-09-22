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
import { MediaElegida, MediaPicker } from '../../../shared/ui/media-picker';
import { capitalizarClaveDeTraduccion } from '../../../shared/text/capitalizar-clave-de-traduccion';
import { PORTADA_ACEPTADOS } from '../../../shared/uploads/image-upload-constraints';

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
  imports: [TranslocoDirective, Alert, Button, Card, MediaPicker],
  template: `
    <ng-container *transloco="let t">
      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <div class="fila-superior">
          <app-card [heading]="t('admin.events.formulario.portada')">
            <app-media-picker
              #portadaPicker
              [etiqueta]="t('admin.events.formulario.portada')"
              [aceptados]="PORTADA_ACEPTADOS"
              kind="events"
              variante="ancha"
              [url]="portadaUrl()"
              (mediaElegido)="asignarPortada($event, portadaPicker)"
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
}
