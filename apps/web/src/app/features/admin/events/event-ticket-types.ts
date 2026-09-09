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
import { Input } from '../../../shared/ui/input';
import { Textarea } from '../../../shared/ui/textarea';
import { isoAValorLocal } from './datetime-local';

type RegistrationMode = 'free' | 'approval' | 'paid';

interface EventoResumen {
  readonly registration_mode: RegistrationMode;
}

interface TicketType {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly price_cents: number;
  readonly currency: string;
  readonly max_quantity: number | null;
  readonly sales_start_at: string | null;
  readonly sales_end_at: string | null;
  readonly sort_order: number;
  readonly is_active: boolean;
}

function vacio(): {
  name: string;
  description: string;
  price: string;
  maxQuantity: string;
  salesStartAt: string;
  salesEndAt: string;
} {
  return {
    name: '',
    description: '',
    price: '',
    maxQuantity: '',
    salesStartAt: '',
    salesEndAt: '',
  };
}

function precioAEuros(cents: number): string {
  return (cents / 100).toFixed(2);
}

/**
 * Tipos de entrada de un evento de pago: alta, edición, reordenación (flechas
 * arriba/abajo, que intercambian `sort_order` con el elemento vecino) y
 * activar/desactivar. Borrar falla con 409 si el tipo tiene códigos de
 * descuento o pagos asociados — el mensaje de error lo explica y sugiere
 * desactivarlo en su lugar.
 */
@Component({
  selector: 'app-event-ticket-types',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, Textarea],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.ticketTypes.titulo')">
        @if (cargandoEvento()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (!aceptaPagos()) {
          <app-alert tone="info">{{ t('admin.events.ticketTypes.eventoGratuito') }}</app-alert>
        } @else {
          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          @if (cargando()) {
            <p>{{ t('comun.cargando') }}</p>
          } @else if (tipos().length === 0) {
            <p>{{ t('admin.events.ticketTypes.sinTipos') }}</p>
          } @else {
            <ul class="lista">
              @for (tipo of tipos(); track tipo.id; let primero = $first; let ultimo = $last) {
                <li [class.inactivo]="!tipo.is_active">
                  <div class="fila">
                    <div class="orden">
                      <button
                        type="button"
                        [attr.aria-label]="t('admin.events.ticketTypes.subir')"
                        [disabled]="primero"
                        (click)="mover(tipo, -1)"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        [attr.aria-label]="t('admin.events.ticketTypes.bajar')"
                        [disabled]="ultimo"
                        (click)="mover(tipo, 1)"
                      >
                        ↓
                      </button>
                    </div>
                    <div>
                      <strong>{{ tipo.name }}</strong>
                      @if (!tipo.is_active) {
                        <span class="insignia">{{ t('admin.events.ticketTypes.inactivo') }}</span>
                      }
                      <span class="detalle">
                        {{ precioEnEuros(tipo.price_cents) }} {{ tipo.currency.toUpperCase() }}
                        @if (tipo.max_quantity !== null) {
                          · {{ t('admin.events.ticketTypes.cupo', { cupo: tipo.max_quantity }) }}
                        }
                      </span>
                    </div>
                    <div class="acciones">
                      <app-button variant="secundario" type="button" (pulsado)="editar(tipo)">
                        {{ t('admin.events.ticketTypes.editar') }}
                      </app-button>
                      <app-button
                        variant="secundario"
                        type="button"
                        (pulsado)="alternarActivo(tipo)"
                      >
                        {{
                          tipo.is_active
                            ? t('admin.events.ticketTypes.desactivar')
                            : t('admin.events.ticketTypes.activar')
                        }}
                      </app-button>
                      <app-button variant="peligro" type="button" (pulsado)="borrar(tipo.id)">
                        {{ t('admin.events.ticketTypes.eliminar') }}
                      </app-button>
                    </div>
                  </div>
                </li>
              }
            </ul>
          }

          <form (submit)="guardar($event)" novalidate class="formulario">
            <h3>
              {{
                editandoId()
                  ? t('admin.events.ticketTypes.editarTipo')
                  : t('admin.events.ticketTypes.anadirTipo')
              }}
            </h3>

            <app-input
              fieldId="tipo-nombre"
              [label]="t('admin.events.ticketTypes.nombre')"
              [required]="true"
              [(value)]="nombre"
            />
            <app-textarea
              fieldId="tipo-descripcion"
              [label]="t('admin.events.ticketTypes.descripcion')"
              [(value)]="descripcion"
            />

            <div class="campo-numero">
              <label for="tipo-precio">{{ t('admin.events.ticketTypes.precio') }}</label>
              <input
                id="tipo-precio"
                type="text"
                inputmode="decimal"
                [value]="precio()"
                [attr.aria-describedby]="'tipo-precio-ayuda'"
                (input)="precio.set(alTexto($event))"
              />
              <p id="tipo-precio-ayuda" class="ayuda">
                {{ t('admin.events.ticketTypes.precioAyuda') }}
              </p>
            </div>

            <div class="campo-numero">
              <label for="tipo-cupo">{{ t('admin.events.ticketTypes.cupoMaximo') }}</label>
              <input
                id="tipo-cupo"
                type="number"
                inputmode="numeric"
                min="1"
                [value]="maxCantidad()"
                [attr.aria-describedby]="'tipo-cupo-ayuda'"
                (input)="maxCantidad.set(alTexto($event))"
              />
              <p id="tipo-cupo-ayuda" class="ayuda">
                {{ t('admin.events.ticketTypes.cupoAyuda') }}
              </p>
            </div>

            <div class="campo-fecha">
              <label for="tipo-inicio-venta">{{ t('admin.events.ticketTypes.inicioVenta') }}</label>
              <input
                id="tipo-inicio-venta"
                type="datetime-local"
                [value]="inicioVenta()"
                (input)="inicioVenta.set(alTexto($event))"
              />
            </div>
            <div class="campo-fecha">
              <label for="tipo-fin-venta">{{ t('admin.events.ticketTypes.finVenta') }}</label>
              <input
                id="tipo-fin-venta"
                type="datetime-local"
                [value]="finVenta()"
                (input)="finVenta.set(alTexto($event))"
              />
            </div>

            @if (formError(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }

            <div class="acciones-finales">
              @if (editandoId()) {
                <app-button variant="secundario" type="button" (pulsado)="cancelarEdicion()">
                  {{ t('comun.cancelar') }}
                </app-button>
              }
              <app-button type="submit" [loading]="guardando()">
                {{
                  editandoId()
                    ? t('admin.events.ticketTypes.guardarCambios')
                    : t('admin.events.ticketTypes.anadirTipo')
                }}
              </app-button>
            </div>
          </form>
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    h3 {
      margin: var(--space-lg) 0 0;
    }
    .lista {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-sm);
    }
    .lista li {
      border-bottom: 1px solid var(--color-border);
      padding-bottom: var(--space-sm);
    }
    .lista li.inactivo {
      opacity: 0.6;
    }
    .fila {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    .orden {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .orden button {
      min-width: 2rem;
      min-height: 2rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-sm, 4px);
      background: var(--color-surface);
      cursor: pointer;
    }
    .orden button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
    .insignia {
      margin-left: var(--space-xs);
      font-size: 0.75rem;
      color: var(--color-text-muted, #6b7280);
    }
    .detalle {
      display: block;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.875rem;
    }
    .acciones {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      margin-left: auto;
      flex-wrap: wrap;
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      margin-top: var(--space-lg);
      padding-top: var(--space-lg);
      border-top: 1px solid var(--color-border);
      max-width: 34rem;
    }
    .campo-numero,
    .campo-fecha {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-numero input,
    .campo-fecha input {
      width: 100%;
      max-width: 16rem;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 2.75rem;
    }
    .ayuda {
      margin: 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.8125rem;
    }
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class EventTicketTypes implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  /** Mientras no se conozca el modo de inscripción del evento, no tiene sentido
   * cargar ni pintar el gestor de tipos de entrada: solo aplica a eventos de pago. */
  protected readonly cargandoEvento = signal(true);
  protected readonly aceptaPagos = signal(false);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly tipos = signal<TicketType[]>([]);
  protected readonly editandoId = signal<string | null>(null);

  private readonly valoresIniciales = vacio();
  protected readonly nombre = signal(this.valoresIniciales.name);
  protected readonly descripcion = signal(this.valoresIniciales.description);
  protected readonly precio = signal(this.valoresIniciales.price);
  protected readonly maxCantidad = signal(this.valoresIniciales.maxQuantity);
  protected readonly inicioVenta = signal(this.valoresIniciales.salesStartAt);
  protected readonly finVenta = signal(this.valoresIniciales.salesEndAt);

  ngOnInit(): void {
    void this.iniciar();
  }

  protected precioEnEuros(cents: number): string {
    return precioAEuros(cents);
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  private async iniciar(): Promise<void> {
    this.cargandoEvento.set(true);
    try {
      const evento = await firstValueFrom(
        this.http.get<EventoResumen>(this.api.url(`/events/${this.eventId()}`)),
      );
      this.aceptaPagos.set(evento.registration_mode === 'paid');
    } catch (error) {
      // Si no se puede confirmar el modo de inscripción, se trata como si no
      // aceptara pagos: mostrar el gestor de entradas sin saber si aplica sería
      // peor que mostrar el mensaje explicativo de más.
      this.aceptaPagos.set(false);
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.ticketTypes.error'),
      );
      return;
    } finally {
      this.cargandoEvento.set(false);
    }
    if (this.aceptaPagos()) {
      await this.cargar();
    }
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const tipos = await firstValueFrom(
        this.http.get<TicketType[]>(this.api.url(`/events/${this.eventId()}/ticket-types`)),
      );
      this.tipos.set([...tipos]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.ticketTypes.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected editar(tipo: TicketType): void {
    this.editandoId.set(tipo.id);
    this.nombre.set(tipo.name);
    this.descripcion.set(tipo.description ?? '');
    this.precio.set(precioAEuros(tipo.price_cents));
    this.maxCantidad.set(tipo.max_quantity !== null ? String(tipo.max_quantity) : '');
    this.inicioVenta.set(tipo.sales_start_at ? isoAValorLocal(tipo.sales_start_at) : '');
    this.finVenta.set(tipo.sales_end_at ? isoAValorLocal(tipo.sales_end_at) : '');
    this.formError.set(null);
  }

  protected cancelarEdicion(): void {
    this.editandoId.set(null);
    const vacios = vacio();
    this.nombre.set(vacios.name);
    this.descripcion.set(vacios.description);
    this.precio.set(vacios.price);
    this.maxCantidad.set(vacios.maxQuantity);
    this.inicioVenta.set(vacios.salesStartAt);
    this.finVenta.set(vacios.salesEndAt);
    this.formError.set(null);
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.formError.set(null);

    if (!this.nombre().trim()) {
      this.formError.set(this.transloco.translate('admin.events.ticketTypes.nombreRequerido'));
      return;
    }
    const precioEnCentimos = Math.round(Number.parseFloat(this.precio().replace(',', '.')) * 100);
    if (!Number.isFinite(precioEnCentimos) || precioEnCentimos < 0) {
      this.formError.set(this.transloco.translate('admin.events.ticketTypes.precioInvalido'));
      return;
    }

    const payload: Record<string, unknown> = {
      name: this.nombre().trim(),
      description: this.descripcion().trim() || null,
      price_cents: precioEnCentimos,
      max_quantity: this.maxCantidad().trim() ? Number(this.maxCantidad()) : null,
      sales_start_at: this.inicioVenta() ? new Date(this.inicioVenta()).toISOString() : null,
      sales_end_at: this.finVenta() ? new Date(this.finVenta()).toISOString() : null,
    };

    const idEnEdicion = this.editandoId();
    if (!idEnEdicion) {
      // Al alta, se coloca al final de la lista: sin esto, todos los tipos
      // nuevos comparten el `sort_order` por defecto (0) y las flechas de
      // reordenación no tendrían ningún efecto visible entre ellos.
      payload['sort_order'] = this.tipos().length;
    }

    this.guardando.set(true);
    try {
      if (idEnEdicion) {
        await firstValueFrom(
          this.http.patch(
            this.api.url(`/events/${this.eventId()}/ticket-types/${idEnEdicion}`),
            payload,
          ),
        );
      } else {
        await firstValueFrom(
          this.http.post(this.api.url(`/events/${this.eventId()}/ticket-types`), payload),
        );
      }
      this.cancelarEdicion();
      await this.cargar();
    } catch (error) {
      this.formError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.ticketTypes.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  protected async alternarActivo(tipo: TicketType): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.patch(this.api.url(`/events/${this.eventId()}/ticket-types/${tipo.id}`), {
          is_active: !tipo.is_active,
        }),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.ticketTypes.error'),
      );
    }
  }

  protected async mover(tipo: TicketType, direccion: -1 | 1): Promise<void> {
    const lista = this.tipos();
    const indice = lista.findIndex((t) => t.id === tipo.id);
    const vecino = lista[indice + direccion];
    if (!vecino) return;

    this.error.set(null);
    try {
      await Promise.all([
        firstValueFrom(
          this.http.patch(this.api.url(`/events/${this.eventId()}/ticket-types/${tipo.id}`), {
            sort_order: vecino.sort_order,
          }),
        ),
        firstValueFrom(
          this.http.patch(this.api.url(`/events/${this.eventId()}/ticket-types/${vecino.id}`), {
            sort_order: tipo.sort_order,
          }),
        ),
      ]);
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.ticketTypes.error'),
      );
    }
  }

  protected async borrar(ticketTypeId: string): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/ticket-types/${ticketTypeId}`)),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.ticketTypes.error'),
      );
    }
  }
}
