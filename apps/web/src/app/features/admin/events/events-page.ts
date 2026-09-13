import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { DataTable, DataTableColumn } from '../../../shared/ui/data-table';

type EventStatus = 'draft' | 'published' | 'archived';

interface EventSummary {
  readonly id: string;
  readonly slug: string;
  readonly title: string;
  readonly status: EventStatus;
  readonly starts_at: string;
}

interface Page<T> {
  readonly items: readonly T[];
}

/** Listado de eventos de la organización, con filtro por estado. */
@Component({
  selector: 'app-events-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, DatePipe, Alert, Button, Chip, DataTable],
  template: `
    <ng-container *transloco="let t">
      <div class="cabecera">
        <div>
          <h1>{{ t('admin.events.titulo') }}</h1>
          <p>{{ t('admin.events.descripcion') }}</p>
        </div>
        <a routerLink="nuevo">
          <app-button type="button">{{ t('admin.events.crearEvento') }}</app-button>
        </a>
      </div>

      <div class="filtro">
        <label for="filtro-estado">{{ t('admin.events.filtrarPorEstado') }}</label>
        <select id="filtro-estado" [value]="estado()" (change)="alCambiarEstado($event)">
          <option value="">{{ t('admin.events.estadoTodos') }}</option>
          <option value="draft">{{ t('admin.events.estadoDraft') }}</option>
          <option value="published">{{ t('admin.events.estadoPublished') }}</option>
          <option value="archived">{{ t('admin.events.estadoArchived') }}</option>
        </select>
      </div>

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
              </td>
              <td>
                <app-chip [tone]="tonoDeEstado(evento.status)">{{
                  t('admin.events.estado' + estadoClave(evento.status))
                }}</app-chip>
              </td>
              <td>{{ evento.starts_at | date: 'short' }}</td>
            </tr>
          }
        </app-data-table>
      }
    </ng-container>
  `,
  styles: `
    .cabecera {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    h1 {
      margin: 0;
    }
    .filtro {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin: var(--space-md) 0;
    }
    .filtro select {
      /* La pintura del control la da la regla compartida de styles.css. */
      min-height: 2.5rem;
    }
  `,
})
export class EventsPage {
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
      { key: 'fecha', label: t('admin.events.columnaFecha') },
    ];
  });

  constructor() {
    void this.cargar();
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

  protected alCambiarEstado(evento: Event): void {
    this.estado.set((evento.target as HTMLSelectElement).value as EventStatus | '');
    void this.cargar();
  }
}
