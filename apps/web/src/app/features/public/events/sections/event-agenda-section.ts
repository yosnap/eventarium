import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  input,
  signal,
  viewChildren,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { Chip } from '../../../../shared/ui/chip';
import { Panel } from '../../../../shared/ui/panel';
import { claveTipoSesion, rolLegible, type PublicEventSession } from '../event-page.types';

export interface DiaDeAgenda {
  readonly fecha: string;
  readonly sesiones: readonly PublicEventSession[];
}

/**
 * Selector de día + agenda del día activo, sobre `.days`/`.slot` de la
 * referencia (`evento-iawic.html:120-194`). Extraído de `event-page.ts` para no
 * pasar de las ~700-800 líneas recomendadas en un solo fichero.
 *
 * Pestañas ARIA con navegación por teclado (flechas ←→, roving tabindex): igual
 * que el script inline de la referencia (`evento-iawic.html:327-349`), pero en
 * Angular con `viewChildren` en vez de `querySelectorAll`.
 *
 * Las fechas de `dia.fecha` (calendario, sin hora) se formatean en UTC:
 * ya vienen agrupadas por día en la zona del evento (`fechaEnZona()` en
 * `event-page.ts`), así que fijar el pipe a UTC evita que el navegador vuelva
 * a desplazar ese día calendario. Las horas de sesión sí usan `eventTimezone()`,
 * porque ahí sí hay un instante real que reproyectar.
 */
@Component({
  selector: 'app-event-agenda-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, RouterLink, TranslocoDirective, Chip, Panel],
  template: `
    <ng-container *transloco="let t">
      <div class="dias" role="tablist" [attr.aria-label]="t('publico.eventos.diasAria')">
        @for (dia of dias(); track dia.fecha; let indice = $index) {
          <button
            #pestana
            type="button"
            role="tab"
            [id]="'dia-tab-' + indice"
            [attr.aria-selected]="indice === diaActivo()"
            [attr.aria-controls]="'dia-panel-' + indice"
            [tabIndex]="indice === diaActivo() ? 0 : -1"
            (click)="seleccionar(indice, false)"
            (keydown)="alPulsarTecla($event, indice)"
          >
            {{ dia.fecha + 'T00:00:00Z' | date: 'EEE dd' : 'UTC' }}
          </button>
        }
      </div>

      <app-panel>
        @for (dia of dias(); track dia.fecha; let indice = $index) {
          <div
            role="tabpanel"
            [id]="'dia-panel-' + indice"
            [attr.aria-labelledby]="'dia-tab-' + indice"
            [hidden]="indice !== diaActivo()"
          >
            <p class="dia-fecha" aria-hidden="true">
              {{ dia.fecha + 'T00:00:00Z' | date: 'fullDate' : 'UTC' }}
            </p>
            <ul class="sesiones">
              @for (sesion of dia.sesiones; track sesion.id) {
                <li class="slot">
                  <span class="slot__hora">
                    {{ sesion.starts_at | date: 'shortTime' : eventTimezone() }}
                  </span>
                  <div class="slot__cuerpo">
                    <a [routerLink]="['/eventos', eventSlug(), 'sesiones', sesion.id]">
                      <h3>{{ sesion.title }}</h3>
                    </a>
                    <span class="slot__sala">
                      {{ sesion.ends_at | date: 'shortTime' : eventTimezone() }}
                      @if (sesion.room) {
                        · {{ sesion.room }}
                      }
                    </span>
                    @if (sesion.participants.length > 0) {
                      <ul class="participantes">
                        @for (persona of sesion.participants; track $index + persona.display_name) {
                          <li>
                            @if (persona.public_slug) {
                              <a [routerLink]="['/ponentes', persona.public_slug]">
                                {{ persona.display_name }}
                              </a>
                            } @else {
                              {{ persona.display_name }}
                            }
                            ({{ rolLegible(persona.role_key, t) }})
                          </li>
                        }
                      </ul>
                    }
                  </div>
                  <app-chip class="slot__tipo">{{
                    t(claveTipoSesion(sesion.session_type))
                  }}</app-chip>
                </li>
              }
            </ul>
          </div>
        }
      </app-panel>
    </ng-container>
  `,
  styles: `
    .dias {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-1);
      padding: 4px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      margin-bottom: var(--sp-4);
    }
    .dias button {
      min-height: 2.375rem;
      padding: 0 1rem;
      border: 0;
      border-radius: 3px;
      background-color: transparent;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      cursor: pointer;
      transition:
        background-color 0.15s,
        color 0.15s;
    }
    .dias button:hover {
      background-color: var(--surface-hi);
      color: var(--fg);
    }
    .dias button[aria-selected='true'] {
      background-color: var(--accent);
      color: var(--on-accent);
      font-weight: 700;
    }
    .dia-fecha {
      margin: 0 0 var(--sp-2);
      color: var(--muted);
    }
    .sesiones {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .slot {
      display: grid;
      grid-template-columns: 96px 1fr auto;
      gap: var(--sp-5);
      padding: var(--sp-5) 0;
      border-bottom: 1px solid var(--border);
      align-items: start;
    }
    .slot:last-child {
      border-bottom: 0;
    }
    .slot__hora {
      font-family: var(--font-mono);
      font-size: var(--fs-sm);
      color: var(--muted);
      padding-top: 2px;
    }
    .slot__cuerpo h3 {
      margin: 0;
    }
    .slot__sala {
      display: block;
      font-size: var(--fs-sm);
      color: var(--muted);
      margin-top: 6px;
    }
    .participantes {
      list-style: none;
      margin: var(--sp-2) 0 0;
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-2);
      font-size: var(--fs-sm);
    }
    .slot__tipo {
      align-self: start;
    }
    @media (max-width: 56.25rem) {
      .slot {
        grid-template-columns: 72px 1fr;
        gap: var(--sp-4);
      }
      .slot__tipo {
        grid-column: 2;
        justify-self: start;
      }
    }
  `,
})
export class EventAgendaSection {
  readonly dias = input.required<readonly DiaDeAgenda[]>();
  readonly eventSlug = input.required<string>();
  readonly eventTimezone = input.required<string>();

  protected readonly diaActivo = signal(0);
  private readonly pestanas = viewChildren<ElementRef<HTMLButtonElement>>('pestana');

  protected readonly claveTipoSesion = claveTipoSesion;

  constructor() {
    effect(() => {
      const total = this.dias().length;
      if (total > 0 && this.diaActivo() >= total) {
        this.diaActivo.set(0);
      }
    });
  }

  protected rolLegible(roleKey: string, traducir: (clave: string) => string): string {
    return rolLegible(roleKey, traducir);
  }

  protected seleccionar(indice: number, enfocar: boolean): void {
    this.diaActivo.set(indice);
    if (enfocar) {
      this.pestanas()[indice]?.nativeElement.focus();
    }
  }

  protected alPulsarTecla(evento: KeyboardEvent, indice: number): void {
    const total = this.dias().length;
    let siguiente: number | null = null;
    if (evento.key === 'ArrowRight') {
      siguiente = (indice + 1) % total;
    } else if (evento.key === 'ArrowLeft') {
      siguiente = (indice - 1 + total) % total;
    }
    if (siguiente !== null) {
      evento.preventDefault();
      this.seleccionar(siguiente, true);
    }
  }
}
