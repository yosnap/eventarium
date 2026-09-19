import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import type { PublicEventSession, PublicVenue } from '../event-page.types';
import { estiloDeSede } from '../venue-colors';

interface FilaDeLista {
  readonly id: string;
  readonly hora: string;
  readonly titulo: string;
  readonly detalle: string;
}

interface GrupoDeSede {
  readonly sede: PublicVenue;
  /** Posición de la sede en la lista completa del evento: fija su color
   * (`estiloDeSede()`), igual que en la parrilla. */
  readonly indiceOriginal: number;
  readonly filas: readonly FilaDeLista[];
}

function horaEnZona(iso: string, zona: string): string {
  return new Intl.DateTimeFormat('es-ES', {
    timeZone: zona,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(iso));
}

/**
 * La misma información que `app-venue-grid-section`, como lista agrupada por
 * sede: la vista que la referencia (`evento-multisede.html:57-63`) sirve por
 * debajo de 820 px, donde la parrilla cruzada no cabe. Se pintan las dos y el
 * CSS decide cuál se ve, igual que el prototipo — sin depender de un ancho de
 * ventana leído desde JavaScript, que no existe en el renderizado de servidor.
 */
@Component({
  selector: 'app-venue-list-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      @if (grupos().length === 0) {
        <p class="vacio">{{ t('publico.eventos.multisede.sinSedes') }}</p>
      } @else {
        @for (grupo of grupos(); track grupo.sede.id) {
          <div class="grupo">
            <h3>
              <span
                class="punto"
                [style.background-color]="estiloDeSede(grupo.indiceOriginal).relleno"
                [style.border-color]="estiloDeSede(grupo.indiceOriginal).borde"
                aria-hidden="true"
              ></span>
              {{ grupo.sede.name }}
            </h3>
            @for (fila of grupo.filas; track fila.id) {
              <div class="fila">
                <span class="num">{{ fila.hora }}</span>
                <span>
                  <strong>{{ fila.titulo }}</strong>
                  <span class="hint detalle">{{ fila.detalle }}</span>
                </span>
              </div>
            }
          </div>
        }
      }
    </ng-container>
  `,
  styles: `
    /* .listwrap (evento-multisede.html:58-63). */
    .grupo {
      margin-bottom: var(--sp-6);
    }
    h3 {
      display: flex;
      align-items: center;
      gap: 9px;
      margin-bottom: var(--sp-3);
    }
    .fila {
      display: grid;
      grid-template-columns: 4rem 1fr;
      gap: var(--sp-4);
      padding: 12px 0;
      border-bottom: 1px solid var(--border);
    }
    .fila:last-child {
      border-bottom: 0;
    }
    .fila .num {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .detalle {
      display: block;
    }
    .punto {
      flex: 0 0 auto;
      width: 10px;
      height: 10px;
      border-radius: 2px;
      border: 1px solid var(--faint);
    }
    .vacio {
      color: var(--muted);
    }
  `,
})
export class VenueListSection {
  readonly sesiones = input.required<readonly PublicEventSession[]>();
  readonly sedes = input.required<readonly PublicVenue[]>();
  readonly sedesVisibles = input.required<readonly string[]>();
  readonly eventTimezone = input.required<string>();

  protected readonly estiloDeSede = estiloDeSede;

  protected readonly grupos = computed<readonly GrupoDeSede[]>(() => {
    const visibles = this.sedesVisibles();
    const zona = this.eventTimezone();
    return this.sedes()
      .map((sede, indiceOriginal) => ({ sede, indiceOriginal }))
      .filter((activa) => visibles.includes(activa.sede.id))
      .map(({ sede, indiceOriginal }) => ({
        sede,
        indiceOriginal,
        filas: this.sesiones()
          .filter((sesion) => sesion.venue_id === sede.id)
          .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
          .map((sesion) => ({
            id: sesion.id,
            hora: horaEnZona(sesion.starts_at, zona),
            titulo: sesion.title,
            detalle: `${horaEnZona(sesion.starts_at, zona)}–${horaEnZona(sesion.ends_at, zona)}${
              sesion.room ? ` · ${sesion.room}` : ''
            }`,
          })),
      }))
      .filter((grupo) => grupo.filas.length > 0);
  });
}
