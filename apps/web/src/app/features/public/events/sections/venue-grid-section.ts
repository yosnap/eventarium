import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import type { PublicEventSession, PublicVenue } from '../event-page.types';
import { estiloDeSede } from '../venue-colors';

/** Franja de la parrilla, en minutos: el prototipo usa 30 (`evento-multisede.html:207`). */
const FRANJA_MINUTOS = 30;

/** Una sede visible, con su índice **dentro de la lista completa del evento**
 * (no de la lista ya filtrada): ese índice es el que fija su color
 * (`estiloDeSede()`), para que no cambie según qué otras sedes estén ocultas. */
export interface SedeActiva {
  readonly sede: PublicVenue;
  readonly indiceOriginal: number;
}

/** Un bloque ya colocado en la rejilla: fila y número de franjas que ocupa. */
export interface BloqueDeParrilla {
  readonly sesion: PublicEventSession;
  readonly fila: number;
  readonly franjas: number;
  readonly columna: number;
  readonly indiceOriginal: number;
  readonly horaInicio: string;
  readonly horaFin: string;
  readonly esDescanso: boolean;
}

export interface DiaDeParrilla {
  readonly fecha: string;
  readonly bloques: readonly BloqueDeParrilla[];
  /** Filas de la rejilla (franjas desde la primera sesión hasta la última). */
  readonly filas: number;
  /** Hora de cada fila, para la columna izquierda. */
  readonly horas: readonly string[];
}

function minutosDelDia(iso: string, zona: string): number {
  const partes = new Intl.DateTimeFormat('en-GB', {
    timeZone: zona,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(iso));
  const [hora, minuto] = partes.split(':').map(Number);
  return hora * 60 + minuto;
}

function hhmm(minutosTotales: number): string {
  const hora = Math.floor(minutosTotales / 60) % 24;
  const minuto = minutosTotales % 60;
  return `${String(hora).padStart(2, '0')}:${String(minuto).padStart(2, '0')}`;
}

/**
 * Parrilla del programa: filas = franjas de media hora, columnas = sedes activas.
 *
 * Sobre `.gridwrap`/`.tt` de la referencia (`evento-multisede.html:34-55`): cada
 * bloque ocupa su duración real (`grid-row: N / span M`), no una fila fija. En
 * pantallas estrechas el CSS oculta esta rejilla y aparece
 * `app-venue-list-section` con la misma información en lista — igual que la
 * referencia, que sirve dos vistas y oculta una con una media query.
 *
 * Se construye en CSS Grid nativo (no `<table>`): la referencia usa rejilla y
 * así el bloque puede crecer en vertical sin partirse.
 */
@Component({
  selector: 'app-venue-grid-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      @if (sedesActivas().length === 0) {
        <p class="vacio">{{ t('publico.eventos.multisede.sinSedes') }}</p>
      } @else if (dia(); as dia) {
        <div class="rejilla-scroll">
          <div
            class="tt"
            role="table"
            [attr.aria-label]="t('publico.eventos.multisede.parrillaAria')"
            [style.--cols]="sedesActivas().length"
          >
            <div class="tt__h" role="columnheader">
              <span class="rotulo-seccion">{{ t('publico.eventos.multisede.hora') }}</span>
            </div>
            @for (activa of sedesActivas(); track activa.sede.id) {
              <div class="tt__h" role="columnheader">
                <span
                  class="punto"
                  [style.background-color]="estiloDeSede(activa.indiceOriginal).relleno"
                  [style.border-color]="estiloDeSede(activa.indiceOriginal).borde"
                  aria-hidden="true"
                ></span>
                <span>
                  <strong class="tt__nombre">{{ activa.sede.name }}</strong>
                  @if (activa.sede.capacity !== null) {
                    <span class="hint tt__sala">
                      {{ t('publico.eventos.multisede.aforoSede', { n: activa.sede.capacity }) }}
                    </span>
                  }
                </span>
              </div>
            }

            @for (hora of dia.horas; track $index; let f = $index) {
              <div class="tt__t" [style.gridRow]="f + 2">{{ hora }}</div>
              @for (activa of sedesActivas(); track activa.sede.id; let c = $index) {
                <div class="celda" [style.gridColumn]="c + 2" [style.gridRow]="f + 2"></div>
              }
            }

            @for (bloque of dia.bloques; track bloque.sesion.id) {
              <div
                class="ses"
                [class.ses--descanso]="bloque.esDescanso"
                [style.border-left-color]="estiloDeSede(bloque.indiceOriginal).borde"
                [style.gridColumn]="bloque.columna + 2"
                [style.gridRow]="bloque.fila + 2 + ' / span ' + bloque.franjas"
              >
                <strong>{{ bloque.sesion.title }}</strong>
                <span class="meta">
                  {{ bloque.horaInicio }}–{{ bloque.horaFin }}
                  @if (bloque.sesion.room) {
                    · {{ bloque.sesion.room }}
                  }
                </span>
              </div>
            }
          </div>
        </div>
      }
    </ng-container>
  `,
  styles: `
    /* .gridwrap (evento-multisede.html:35): la parrilla puede desplazarse en
       horizontal cuando hay muchas sedes, sin desbordar la página. */
    .rejilla-scroll {
      overflow-x: auto;
      padding: var(--sp-6) 0 var(--sp-8);
    }
    /* .tt (evento-multisede.html:36-38). */
    .tt {
      display: grid;
      grid-template-columns: 78px repeat(var(--cols, 3), minmax(13.125rem, 1fr));
      grid-auto-rows: 46px;
      gap: 1px;
      background-color: var(--border);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      overflow: hidden;
      min-width: 45rem;
    }
    .tt__h {
      grid-row: 1;
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 12px 14px;
      background-color: var(--surface-2);
    }
    .tt__nombre {
      font-weight: 500;
    }
    .tt__sala {
      display: block;
    }
    /* .tt__t (evento-multisede.html:41-42). */
    .tt__t {
      grid-column: 1;
      display: flex;
      align-items: flex-start;
      justify-content: flex-end;
      padding: 6px 12px 0 0;
      background-color: var(--surface-2);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      color: var(--muted);
    }
    .celda {
      background-color: var(--bg);
    }
    /* .ses (evento-multisede.html:44-55). */
    .ses {
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 10px 13px;
      overflow: hidden;
      background-color: var(--surface);
      border-left: 2px solid var(--faint);
      transition:
        background-color 0.15s,
        border-color 0.15s;
    }
    .ses:hover {
      background-color: var(--surface-hi);
      border-left-color: var(--fg);
    }
    .ses strong {
      font-size: var(--fs-sm);
      font-weight: 500;
      line-height: 1.3;
    }
    .ses .meta {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.08em;
      color: var(--muted);
    }
    .ses--descanso {
      background-color: var(--surface-2);
      border-left-style: dashed;
    }
    .ses--descanso strong {
      color: var(--muted);
      font-weight: 400;
    }
    /* .vdot (evento-multisede.html:17-20): tamaño/forma fijos, el color lo
       pone estiloDeSede() por [style.*] (ver el componente). */
    .punto {
      flex: 0 0 auto;
      width: 10px;
      height: 10px;
      border-radius: 2px;
      border: 1px solid var(--faint);
    }
    .vacio {
      padding: var(--sp-8) 0;
      color: var(--muted);
    }
  `,
})
export class VenueGridSection {
  readonly sesiones = input.required<readonly PublicEventSession[]>();
  readonly sedes = input.required<readonly PublicVenue[]>();
  /** Ids de sede activos, en el orden en que se pintan las columnas. */
  readonly sedesVisibles = input.required<readonly string[]>();
  readonly fecha = input.required<string>();
  readonly eventTimezone = input.required<string>();

  protected readonly estiloDeSede = estiloDeSede;

  protected readonly sedesActivas = computed<readonly SedeActiva[]>(() => {
    const visibles = this.sedesVisibles();
    return this.sedes()
      .map((sede, indiceOriginal) => ({ sede, indiceOriginal }))
      .filter((activa) => visibles.includes(activa.sede.id));
  });

  protected readonly dia = computed<DiaDeParrilla>(() => {
    const sedes = this.sedesActivas();
    const zona = this.eventTimezone();
    const sesiones = this.sesiones();

    if (sedes.length === 0 || sesiones.length === 0) {
      return { fecha: this.fecha(), bloques: [], filas: 0, horas: [] };
    }

    const conMinutos = sesiones
      .map((sesion) => ({
        sesion,
        inicio: minutosDelDia(sesion.starts_at, zona),
        fin: minutosDelDia(sesion.ends_at, zona),
      }))
      .sort((a, b) => a.inicio - b.inicio);

    // La rejilla empieza en la franja de la primera sesión, no a las 00:00: el
    // prototipo arranca a las 09:00 porque su programa empieza ahí.
    const primerMinuto = Math.floor(conMinutos[0].inicio / FRANJA_MINUTOS) * FRANJA_MINUTOS;
    const ultimoMinuto = Math.max(...conMinutos.map((s) => s.fin));
    const filas = Math.max(1, Math.ceil((ultimoMinuto - primerMinuto) / FRANJA_MINUTOS));

    const bloques: BloqueDeParrilla[] = [];
    for (const { sesion, inicio, fin } of conMinutos) {
      const columna = sedes.findIndex((activa) => activa.sede.id === sesion.venue_id);
      if (columna < 0) {
        continue;
      }
      bloques.push({
        sesion,
        columna,
        indiceOriginal: sedes[columna].indiceOriginal,
        fila: Math.round((inicio - primerMinuto) / FRANJA_MINUTOS),
        franjas: Math.max(1, Math.round((fin - inicio) / FRANJA_MINUTOS)),
        horaInicio: hhmm(inicio),
        horaFin: hhmm(fin),
        esDescanso: sesion.session_type === 'break',
      });
    }

    return {
      fecha: this.fecha(),
      bloques,
      filas,
      horas: Array.from({ length: filas }, (_, i) => hhmm(primerMinuto + i * FRANJA_MINUTOS)),
    };
  });
}
