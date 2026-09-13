import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { EventDetails } from './event-details';
import { EventoMetricas, PiezaDelEvento } from './event-metrics.types';

/** Una fila del embudo, ya resuelta para pintar. */
interface Escalon {
  readonly clave: string;
  readonly etiqueta: string;
  readonly valor: number;
  readonly porcentaje: number;
}

/**
 * Escritorio de un evento: cómo va y qué le falta.
 *
 * Es la raíz del ámbito de evento. Antes esa raíz era el formulario, que ahora
 * vive en `/editar` — a quien entra a un evento le interesa «cómo va», no «los
 * campos»—, y `EventDetails` (portada, estado y las secciones) pasa a ser una
 * parte de esta pantalla en vez de toda ella.
 *
 * **Los bloques que no llegan no se pintan.** La API omite los que quien mira no
 * puede ver según su rol (los conteos de inscripción sin `registrations:read`,
 * el dinero sin permiso económico), así que aquí no hay que decidir nada: si el
 * dato no está, el bloque no existe. Duplicar la regla de permisos en la
 * interfaz sería tenerla en dos sitios que pueden divergir.
 */
@Component({
  selector: 'app-event-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Card, Chip, EventDetails],
  template: `
    <ng-container *transloco="let t">
      @if (error(); as mensaje) {
        <app-alert tone="error">{{ t(mensaje) }}</app-alert>
      }

      @if (metricas(); as m) {
        <div class="cifras">
          @if (m.cifras; as c) {
            <app-card [heading]="t('admin.events.metricas.inscripciones')">
              <dl class="lista">
                <div>
                  <dt>{{ t('admin.events.registrations.estadisticas.confirmados') }}</dt>
                  <dd>{{ c.por_estado['confirmed'] ?? 0 }}</dd>
                </div>
                <div>
                  <dt>{{ t('admin.events.metricas.porAprobar') }}</dt>
                  <dd>{{ c.por_aprobar }}</dd>
                </div>
                <div>
                  <dt>{{ t('admin.events.registrations.estadisticas.listaEspera') }}</dt>
                  <dd>{{ c.lista_de_espera }}</dd>
                </div>
                <div>
                  <dt>{{ t('admin.events.metricas.sinEntrar') }}</dt>
                  <dd>{{ c.sin_entrar }}</dd>
                </div>
              </dl>
            </app-card>
          }

          <app-card [heading]="t('admin.events.metricas.ocupacion')">
            @if (m.ocupacion.aforo !== null) {
              <p class="destacado">
                {{ m.ocupacion.reservadas }} / {{ m.ocupacion.aforo }}
              </p>
              <p class="nota">{{ t('admin.events.metricas.reservadasAyuda') }}</p>
            } @else {
              <p class="destacado">{{ m.ocupacion.reservadas }}</p>
              <p class="nota">{{ t('admin.events.metricas.sinAforo') }}</p>
            }
          </app-card>

          @if (m.dinero; as d) {
            <app-card [heading]="t('admin.events.metricas.dinero')">
              <dl class="lista">
                <div>
                  <dt>{{ t('admin.events.metricas.ingresos') }}</dt>
                  <dd>{{ formatearCents(d.ingresos_cobrados_cents, d.moneda) }}</dd>
                </div>
                <div>
                  <dt>{{ t('admin.events.metricas.presupuesto') }}</dt>
                  <dd>{{ formatearCents(d.presupuesto_cents, d.moneda) }}</dd>
                </div>
                <div>
                  <dt>{{ t('admin.events.metricas.ejecutado') }}</dt>
                  <dd>{{ formatearCents(d.ejecutado_cents, d.moneda) }}</dd>
                </div>
              </dl>
            </app-card>
          }
        </div>

        @if (m.embudo; as e) {
          <app-card [heading]="t('admin.events.metricas.embudo')">
            <ol class="embudo">
              @for (escalon of escalones(); track escalon.clave) {
                <li>
                  <span class="etiqueta">{{ t(escalon.etiqueta) }}</span>
                  <span class="barra" aria-hidden="true">
                    <span [style.width.%]="escalon.porcentaje"></span>
                  </span>
                  <span class="valor">{{ escalon.valor }}</span>
                </li>
              }
            </ol>
            @if (e.sin_verificacion_exigida) {
              <p class="nota">{{ t('admin.events.metricas.sinVerificacionExigida') }}</p>
            }
          </app-card>
        }

        @if (piezasPendientes().length > 0) {
          <app-alert tone="info">
            <p>{{ t('admin.events.metricas.falta') }}</p>
            <ul>
              @for (pieza of piezasPendientes(); track pieza.clave) {
                <li>
                  <a [href]="anclaDe(pieza)">{{ etiquetaDe(pieza) }}</a>
                </li>
              }
            </ul>
          </app-alert>
        }

        <app-card [heading]="t('admin.events.metricas.piezas')">
          <ul class="piezas">
            @for (pieza of m.piezas; track pieza.clave) {
              <li>
                <span>{{ t(etiquetaDe(pieza)) }}</span>
                <app-chip [tone]="tonoDe(pieza)">{{ t(estadoDe(pieza)) }}</app-chip>
              </li>
            }
          </ul>
        </app-card>
      }

      <app-event-details [eventId]="eventId()" />
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .cifras {
      display: grid;
      gap: var(--space-md);
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      margin-bottom: var(--space-lg);
    }
    .lista {
      display: grid;
      gap: var(--space-sm);
      margin: 0;
    }
    .lista > div {
      display: flex;
      justify-content: space-between;
      gap: var(--space-md);
    }
    .lista dt {
      color: var(--muted);
    }
    .lista dd {
      margin: 0;
      font-variant-numeric: tabular-nums;
    }
    .destacado {
      margin: 0;
      font-size: 1.75rem;
      font-variant-numeric: tabular-nums;
    }
    .nota {
      margin: var(--space-xs) 0 0;
      color: var(--muted);
      font-size: 0.875rem;
    }
    .embudo {
      display: grid;
      gap: var(--space-sm);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .embudo li {
      display: grid;
      grid-template-columns: 10rem 1fr 4rem;
      gap: var(--space-md);
      align-items: center;
    }
    .barra {
      display: block;
      height: 1rem;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      overflow: hidden;
    }
    .barra > span {
      display: block;
      height: 100%;
      background-color: var(--accent);
    }
    .valor {
      text-align: end;
      font-variant-numeric: tabular-nums;
    }
    .piezas {
      display: grid;
      gap: var(--space-sm);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .piezas li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-md);
    }
    @media (max-width: 40rem) {
      .embudo li {
        grid-template-columns: 1fr 3.5rem;
      }
      .embudo .barra {
        grid-column: 1 / -1;
        grid-row: 2;
      }
    }
  `,
})
export class EventDashboard implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  readonly eventId = input.required<string>();

  protected readonly metricas = signal<EventoMetricas | null>(null);
  protected readonly error = signal<string | null>(null);

  /** Las piezas que aplican al evento y aún están vacías: lo que le falta. */
  protected readonly piezasPendientes = computed(
    () => this.metricas()?.piezas.filter((pieza) => pieza.estado === 'pendiente') ?? [],
  );

  /**
   * El embudo, con el ancho de cada barra calculado sobre el primer escalón.
   * Sin iniciados no hay proporción que dibujar, así que todas van a cero.
   */
  protected readonly escalones = computed<readonly Escalon[]>(() => {
    const embudo = this.metricas()?.embudo;
    if (!embudo) {
      return [];
    }
    const total = embudo.formulario || 0;
    const proporcion = (valor: number): number => (total > 0 ? (valor / total) * 100 : 0);
    return [
      {
        clave: 'formulario',
        etiqueta: 'admin.events.metricas.escalonFormulario',
        valor: embudo.formulario,
        porcentaje: proporcion(embudo.formulario),
      },
      {
        clave: 'verificado',
        etiqueta: 'admin.events.metricas.escalonVerificado',
        valor: embudo.verificado,
        porcentaje: proporcion(embudo.verificado),
      },
      {
        clave: 'aprobado',
        etiqueta: 'admin.events.metricas.escalonAprobado',
        valor: embudo.aprobado,
        porcentaje: proporcion(embudo.aprobado),
      },
      {
        clave: 'emitido',
        etiqueta: 'admin.events.metricas.escalonEmitido',
        valor: embudo.emitido,
        porcentaje: proporcion(embudo.emitido),
      },
    ];
  });

  // En `ngOnInit` y no en el constructor: un `input.required` todavía no tiene
  // valor cuando corre el constructor, así que ahí `eventId()` sería una lectura
  // inválida.
  ngOnInit(): void {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const datos = await firstValueFrom(
        this.http.get<EventoMetricas>(this.api.url(`/events/${this.eventId()}/metrics`)),
      );
      this.metricas.set(datos);
    } catch {
      // El escritorio es informativo: si sus cifras no llegan, el evento se
      // sigue pudiendo gestionar desde las secciones de abajo.
      this.error.set('admin.events.metricas.error');
    }
  }

  protected etiquetaDe(pieza: PiezaDelEvento): string {
    return `admin.events.metricas.pieza.${pieza.clave}`;
  }

  protected estadoDe(pieza: PiezaDelEvento): string {
    return `admin.events.metricas.estado.${pieza.estado}`;
  }

  protected tonoDe(pieza: PiezaDelEvento): ChipTone {
    const tonos: Record<PiezaDelEvento['estado'], ChipTone> = {
      lista: 'ok',
      pendiente: 'espera',
      no_aplica: 'apagado',
    };
    return tonos[pieza.estado];
  }

  /** Ancla a la sección del evento que resuelve esa pieza. */
  protected anclaDe(pieza: PiezaDelEvento): string {
    const anclas: Record<string, string> = {
      agenda: 'agenda',
      sedes: 'sedes',
      tipos_de_entrada: 'entradas',
      descuentos: 'descuentos',
      patrocinadores: 'patrocinadores',
    };
    return `#${anclas[pieza.clave] ?? pieza.clave}`;
  }

  protected formatearCents(cents: number, moneda: string): string {
    return new Intl.NumberFormat('es-ES', { style: 'currency', currency: moneda.toUpperCase() }).format(
      cents / 100,
    );
  }
}
