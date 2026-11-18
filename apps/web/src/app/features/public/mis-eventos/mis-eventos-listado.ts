import {
  ChangeDetectionStrategy,
  Component,
  type ElementRef,
  computed,
  input,
  signal,
  viewChildren,
  LOCALE_ID,
  inject,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import type { MyRegistrationItem } from '../../../core/registrations/registrations.service';
import { rutaEvento } from '../../../core/routing/rutas-publicas';
import { AddToCalendar } from '../../../shared/ui/add-to-calendar';
import { formatearFecha } from '../../../shared/text/formatear-fecha';

type Pestana = 'proximos' | 'pasados';
const PESTANAS: readonly Pestana[] = ['proximos', 'pasados'];

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
 * Listado de «Mis eventos» en dos pestañas, «Próximos» y «Pasados». Lo usan
 * la página del enlace por correo y `/mis-eventos` con la sesión iniciada.
 *
 * Un evento en curso (empezado pero sin terminar) sigue en «Próximos»: el
 * corte es su fin. Los próximos van del más cercano al más lejano; los
 * pasados, del más reciente al más antiguo. «Añadir a mi calendario» solo en
 * los próximos y cuando la API lo ofrece (`calendar`: plaza confirmada y
 * evento no cancelado). Pestañas con el patrón de la agenda del evento:
 * tabindex móvil, flechas, Inicio y Fin.
 */
@Component({
  selector: 'app-mis-eventos-listado',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TranslocoDirective, AddToCalendar],
  template: `
    <ng-container *transloco="let t">
      <div class="pestanas" role="tablist" [attr.aria-label]="t('publico.misEventos.pestanasAria')">
        @for (pestana of pestanas; track pestana; let indice = $index) {
          <button
            #boton
            type="button"
            role="tab"
            [id]="'mis-eventos-tab-' + pestana"
            [attr.aria-selected]="pestana === activa()"
            [attr.aria-controls]="'mis-eventos-panel-' + pestana"
            [attr.tabindex]="pestana === activa() ? 0 : -1"
            (click)="seleccionar(indice, false)"
            (keydown)="alPulsarTecla($event, indice)"
          >
            {{
              t('publico.misEventos.pestana.' + pestana, {
                n: pestana === 'proximos' ? proximos().length : pasados().length,
              })
            }}
          </button>
        }
      </div>

      @for (pestana of pestanas; track pestana) {
        <div
          role="tabpanel"
          [id]="'mis-eventos-panel-' + pestana"
          [attr.aria-labelledby]="'mis-eventos-tab-' + pestana"
          [hidden]="pestana !== activa()"
        >
          @let filas = pestana === 'proximos' ? proximos() : pasados();
          @if (filas.length === 0) {
            <p class="vacio">
              {{ t('publico.misEventos.vacio.' + pestana) }}
              @if (pestana === 'proximos') {
                <a routerLink="/eventos">{{ t('publico.misEventos.verEventos') }}</a>
              }
            </p>
          } @else {
            <ul class="listado" [class.listado--pasado]="pestana === 'pasados'">
              @for (fila of filas; track fila.organization.slug + fila.event_slug + fila.status) {
                <li>
                  <a [routerLink]="rutaEvento(fila.organization.slug, fila.event_slug)">{{
                    fila.event_title
                  }}</a>
                  <span class="detalle">
                    {{ fechaDe(fila) }} · {{ fila.organization.name }} ·
                    @if (fila.event_cancelled) {
                      {{ t('publico.misEventos.eventoCancelado') }}
                    } @else {
                      {{ t('publico.misEventos.estado.' + claveDeEstado(fila.status)) }}
                    }
                  </span>
                  @if (pestana === 'proximos' && fila.calendar; as calendario) {
                    <app-add-to-calendar [evento]="calendario" />
                  }
                </li>
              }
            </ul>
          }
        </div>
      }
    </ng-container>
  `,
  styles: `
    .pestanas {
      display: flex;
      width: fit-content;
      gap: var(--sp-1);
      padding: 4px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      margin-bottom: var(--space-md);
    }
    .pestanas button {
      min-height: 2.375rem;
      padding: 0 1rem;
      border: 0;
      border-radius: 3px;
      background-color: transparent;
      color: var(--muted);
      font: inherit;
      font-size: var(--fs-sm);
      cursor: pointer;
      transition:
        background-color 0.15s,
        color 0.15s;
    }
    .pestanas button:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
    .pestanas button[aria-selected='true'] {
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
    }
    .pestanas button:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
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
    /* Pasados: todo en el gris de texto secundario (contraste AA en los dos
       temas, el mismo de .detalle), sin calendario. */
    .listado--pasado li,
    .listado--pasado a {
      color: var(--muted);
    }
    .vacio {
      color: var(--muted);
    }
  `,
})
export class MisEventosListado {
  /** Idioma de la visita, para fechas e importes. */
  private readonly idioma = inject(LOCALE_ID);
  readonly inscripciones = input.required<readonly MyRegistrationItem[]>();

  protected readonly rutaEvento = rutaEvento;
  protected readonly claveDeEstado = claveDeEstado;
  protected readonly pestanas = PESTANAS;
  protected readonly activa = signal<Pestana>('proximos');
  private readonly botones = viewChildren<ElementRef<HTMLButtonElement>>('boton');
  /** Fijado al cargar: la página no está abierta lo bastante para que un
   * evento cambie de pestaña mientras se mira. */
  private readonly ahora = Date.now();

  protected readonly proximos = computed(() =>
    this.inscripciones()
      .filter((fila) => Date.parse(fila.ends_at) >= this.ahora)
      .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at)),
  );
  protected readonly pasados = computed(() =>
    this.inscripciones()
      .filter((fila) => Date.parse(fila.ends_at) < this.ahora)
      .sort((a, b) => Date.parse(b.starts_at) - Date.parse(a.starts_at)),
  );

  /** En la zona del evento, no en la del navegador: `DatePipe` no entiende
   * nombres IANA (`Europe/Madrid`) y caería en silencio a la hora local. Mismo
   * criterio que `cancel-registration-page.ts`. */
  protected fechaDe(fila: MyRegistrationItem): string {
    return formatearFecha(fila.starts_at, this.idioma, {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: fila.timezone,
    });
  }

  protected seleccionar(indice: number, enfocar: boolean): void {
    this.activa.set(PESTANAS[indice]);
    if (enfocar) {
      this.botones()[indice]?.nativeElement.focus();
    }
  }

  protected alPulsarTecla(evento: KeyboardEvent, indice: number): void {
    const total = PESTANAS.length;
    const destinos: Record<string, number> = {
      ArrowRight: (indice + 1) % total,
      ArrowLeft: (indice - 1 + total) % total,
      Home: 0,
      End: total - 1,
    };
    const siguiente = destinos[evento.key];
    if (siguiente !== undefined) {
      evento.preventDefault();
      this.seleccionar(siguiente, true);
    }
  }
}
