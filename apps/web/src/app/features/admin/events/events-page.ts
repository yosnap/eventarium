import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  LOCALE_ID,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { Select, type SelectOption } from '../../../shared/ui/select';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { DataTable, DataTableColumn } from '../../../shared/ui/data-table';
import { PageHeader } from '../../../shared/ui/page-header';
import { formatearPrecio } from '../../../shared/text/formatear-precio';

type EventStatus = 'draft' | 'published' | 'archived' | 'cancelled';
type RegistrationMode = 'free' | 'approval' | 'paid';

interface EventSummary {
  readonly id: string;
  readonly slug: string;
  readonly title: string;
  readonly status: EventStatus;
  readonly starts_at: string;
  readonly registration_mode: RegistrationMode;
  readonly visibility?: 'public' | 'hidden' | 'private';
  /** `null`: sin límite de plazas. */
  readonly capacity: number | null;
  /** Entrada más barata (solo eventos de pago con entradas definidas). */
  readonly price_from_cents?: number | null;
  readonly price_currency?: string | null;
  readonly price_multiple?: boolean;
}

interface Page<T> {
  readonly items: readonly T[];
}

/** Listado de eventos de la organización, con filtro por estado. */
@Component({
  selector: 'app-events-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    DatePipe,
    Alert,
    Button,
    Chip,
    DataTable,
    PageHeader,
    Select,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.events.rotulo')">
        {{ t('admin.events.cabeceraInicio') }}
        <span class="mark">{{ t('admin.events.cabeceraMarca') }}</span>
        <div acciones>
          <a routerLink="nuevo">
            <app-button type="button">{{ t('admin.events.crearEvento') }}</app-button>
          </a>
        </div>
      </app-page-header>

      <app-select
        class="filtro"
        fieldId="filtro-estado"
        [label]="t('admin.events.filtrarPorEstado')"
        [options]="opcionesDeEstado()"
        [value]="estado()"
        (valueChange)="alCambiarEstado($event)"
      />

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (eventos().length === 0) {
        <p>{{ t('admin.events.sinEventos') }}</p>
      } @else {
        <app-data-table [columnas]="columnasDeEventos()" [caption]="t('admin.events.titulo')">
          @for (evento of eventos(); track evento.id) {
            <tr>
              <td>
                <a [routerLink]="[evento.id]">{{ evento.title }}</a>
                @if (evento.visibility && evento.visibility !== 'public') {
                  <app-chip tone="apagado">{{
                    t('admin.events.formulario.visibilidadOpcion.' + evento.visibility)
                  }}</app-chip>
                }
              </td>
              <td>
                <app-chip [tone]="tonoDeEstado(evento.status)">{{
                  t('admin.events.estado' + estadoClave(evento.status))
                }}</app-chip>
              </td>
              <td>{{ t(claveDeModo(evento.registration_mode)) }}</td>
              <td>{{ precioTexto(evento, t) }}</td>
              <td>
                {{ evento.capacity === null ? t('admin.events.sinLimite') : evento.capacity }}
              </td>
              <td>{{ evento.starts_at | date: 'short' }}</td>
              <td>
                <a
                  class="vista-previa"
                  [routerLink]="['/vista-previa', evento.id]"
                  target="_blank"
                  [attr.aria-label]="t('admin.events.vistaPreviaDe', { titulo: evento.title })"
                  >{{ t('admin.events.vistaPrevia') }}</a
                >
              </td>
            </tr>
          }
        </app-data-table>
      }
    </ng-container>
  `,
  styles: `
    .vista-previa {
      white-space: nowrap;
    }
    .filtro {
      display: block;
      max-width: 18rem;
      margin: var(--space-md) 0;
    }
  `,
})
export class EventsPage {
  /** Idioma de la visita, para fechas e importes. */
  private readonly idioma = inject(LOCALE_ID);
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly eventos = signal<EventSummary[]>([]);
  protected readonly estado = signal<EventStatus | ''>('');
  protected readonly error = signal<string | null>(null);

  /** Las columnas de la tabla de eventos, con la etiqueta ya traducida. */
  protected readonly columnasDeEventos = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    return [
      { key: 'titulo', label: t('admin.events.columnaTitulo') },
      { key: 'estado', label: t('admin.events.columnaEstado') },
      { key: 'inscripcion', label: t('admin.events.columnaInscripcion') },
      { key: 'precio', label: t('admin.events.columnaPrecio') },
      { key: 'aforo', label: t('admin.events.columnaAforo') },
      { key: 'fecha', label: t('admin.events.columnaFecha') },
      { key: 'acciones', label: t('admin.events.columnaAcciones') },
    ];
  });

  constructor() {
    void this.cargar();
  }

  protected claveDeModo(modo: RegistrationMode): string {
    const claves: Record<RegistrationMode, string> = {
      free: 'admin.events.modoLibre',
      approval: 'admin.events.modoAprobacion',
      paid: 'admin.events.modoPago',
    };
    return claves[modo];
  }

  /** «Gratis» si no es de pago; el precio, o «Desde X» si hay varios; y, si es de
   * pago pero aún no tiene entradas, que faltan (sin inventar un importe). */
  protected precioTexto(
    evento: EventSummary,
    traducir: (clave: string, params?: Record<string, unknown>) => string,
  ): string {
    if (evento.registration_mode !== 'paid') return traducir('admin.events.precioGratis');
    if (evento.price_from_cents == null || !evento.price_currency) {
      return traducir('admin.events.precioSinEntradas');
    }
    const precio = formatearPrecio(evento.price_from_cents, evento.price_currency, this.idioma);
    return evento.price_multiple ? traducir('admin.events.precioDesde', { precio }) : precio;
  }

  protected estadoClave(estado: EventStatus): string {
    return estado.charAt(0).toUpperCase() + estado.slice(1);
  }

  /** El estado de un evento se lee por su texto: el color solo lo refuerza. */
  protected tonoDeEstado(estado: EventStatus): ChipTone {
    switch (estado) {
      case 'published':
        return 'ok';
      case 'draft':
        return 'espera';
      case 'archived':
        return 'neutro';
      case 'cancelled':
        return 'apagado';
    }
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const params: Record<string, string> = {};
      if (this.estado()) {
        params['status'] = this.estado();
      }
      const pagina = await firstValueFrom(
        this.http.get<Page<EventSummary>>(this.api.url('/events'), { params }),
      );
      this.eventos.set([...pagina.items]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.events.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected readonly opcionesDeEstado = computed<SelectOption[]>(() => [
    { value: '', label: this.transloco.translate('admin.events.estadoTodos') },
    { value: 'draft', label: this.transloco.translate('admin.events.estadoDraft') },
    { value: 'published', label: this.transloco.translate('admin.events.estadoPublished') },
    { value: 'archived', label: this.transloco.translate('admin.events.estadoArchived') },
    { value: 'cancelled', label: this.transloco.translate('admin.events.estadoCancelled') },
  ]);

  protected alCambiarEstado(valor: string): void {
    this.estado.set(valor as EventStatus | '');
    void this.cargar();
  }
}
