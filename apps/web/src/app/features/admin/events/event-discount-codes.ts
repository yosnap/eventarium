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
import { isoAValorLocal } from './datetime-local';

type DiscountType = 'percentage' | 'fixed_amount';

interface TicketTypeOption {
  readonly id: string;
  readonly name: string;
}

interface DiscountCode {
  readonly id: string;
  readonly code: string;
  readonly discount_type: DiscountType;
  readonly discount_value: number;
  readonly max_uses: number | null;
  readonly valid_from: string | null;
  readonly valid_until: string | null;
  readonly ticket_type_id: string | null;
  readonly used_count: number;
}

function vacio(): {
  code: string;
  discountType: DiscountType;
  discountValue: string;
  maxUses: string;
  validFrom: string;
  validUntil: string;
  ticketTypeId: string;
} {
  return {
    code: '',
    discountType: 'percentage',
    discountValue: '',
    maxUses: '',
    validFrom: '',
    validUntil: '',
    ticketTypeId: '',
  };
}

/**
 * Códigos de descuento de un evento de pago: alta, edición y baja. `used_count`
 * viene siempre calculado por el backend a partir de los pagos (nunca un
 * contador editable aquí); pedir 50 presupuestos con el mismo código no lo
 * mueve, solo un pago real lo hace.
 */
@Component({
  selector: 'app-event-discount-codes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.discountCodes.titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (codigos().length === 0) {
          <p>{{ t('admin.events.discountCodes.sinCodigos') }}</p>
        } @else {
          <ul class="lista">
            @for (codigo of codigos(); track codigo.id) {
              <li>
                <div class="fila">
                  <div>
                    <strong>{{ codigo.code }}</strong>
                    <span class="detalle">
                      {{
                        codigo.discount_type === 'percentage'
                          ? t('admin.events.discountCodes.valorPorcentaje', {
                              valor: codigo.discount_value
                            })
                          : t('admin.events.discountCodes.valorFijo', {
                              valor: codigo.discount_value
                            })
                      }}
                      ·
                      {{
                        t('admin.events.discountCodes.usos', {
                          usados: codigo.used_count,
                          max: codigo.max_uses ?? t('admin.events.discountCodes.sinLimite')
                        })
                      }}
                      @if (codigo.ticket_type_id) {
                        · {{ nombreDeTipo(codigo.ticket_type_id) }}
                      }
                    </span>
                  </div>
                  <div class="acciones">
                    <app-button variant="secundario" type="button" (pulsado)="editar(codigo)">
                      {{ t('admin.events.discountCodes.editar') }}
                    </app-button>
                    <app-button variant="peligro" type="button" (pulsado)="borrar(codigo.id)">
                      {{ t('admin.events.discountCodes.eliminar') }}
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
                ? t('admin.events.discountCodes.editarCodigo')
                : t('admin.events.discountCodes.anadirCodigo')
            }}
          </h3>

          <app-input
            fieldId="codigo-code"
            [label]="t('admin.events.discountCodes.codigo')"
            [required]="true"
            [(value)]="code"
          />

          <div class="campo-select">
            <label for="codigo-tipo-descuento">
              {{ t('admin.events.discountCodes.tipoDescuento') }}
            </label>
            <select
              id="codigo-tipo-descuento"
              [value]="discountType()"
              (change)="alCambiarTipoDescuento($event)"
            >
              <option value="percentage">{{ t('admin.events.discountCodes.porcentaje') }}</option>
              <option value="fixed_amount">{{ t('admin.events.discountCodes.importeFijo') }}</option>
            </select>
          </div>

          <div class="campo-numero">
            <label for="codigo-valor">
              {{
                discountType() === 'percentage'
                  ? t('admin.events.discountCodes.valorPorcentajeLabel')
                  : t('admin.events.discountCodes.valorFijoLabel')
              }}
            </label>
            <input
              id="codigo-valor"
              type="number"
              inputmode="decimal"
              min="0"
              [value]="discountValue()"
              (input)="discountValue.set(alTexto($event))"
            />
          </div>

          <div class="campo-numero">
            <label for="codigo-max-usos">{{ t('admin.events.discountCodes.maxUsos') }}</label>
            <input
              id="codigo-max-usos"
              type="number"
              inputmode="numeric"
              min="1"
              [value]="maxUsos()"
              [attr.aria-describedby]="'codigo-max-usos-ayuda'"
              (input)="maxUsos.set(alTexto($event))"
            />
            <p id="codigo-max-usos-ayuda" class="ayuda">
              {{ t('admin.events.discountCodes.maxUsosAyuda') }}
            </p>
          </div>

          <div class="campo-select">
            <label for="codigo-tipo-entrada">
              {{ t('admin.events.discountCodes.tipoEntrada') }}
            </label>
            <select
              id="codigo-tipo-entrada"
              [value]="ticketTypeId()"
              (change)="alCambiarTipoEntrada($event)"
            >
              <option value="">{{ t('admin.events.discountCodes.todosLosTipos') }}</option>
              @for (tipo of tiposDisponibles(); track tipo.id) {
                <option [value]="tipo.id">{{ tipo.name }}</option>
              }
            </select>
          </div>

          <div class="campo-fecha">
            <label for="codigo-vigente-desde">
              {{ t('admin.events.discountCodes.vigenteDesde') }}
            </label>
            <input
              id="codigo-vigente-desde"
              type="datetime-local"
              [value]="validFrom()"
              (input)="validFrom.set(alTexto($event))"
            />
          </div>
          <div class="campo-fecha">
            <label for="codigo-vigente-hasta">
              {{ t('admin.events.discountCodes.vigenteHasta') }}
            </label>
            <input
              id="codigo-vigente-hasta"
              type="datetime-local"
              [value]="validUntil()"
              (input)="validUntil.set(alTexto($event))"
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
                  ? t('admin.events.discountCodes.guardarCambios')
                  : t('admin.events.discountCodes.anadirCodigo')
              }}
            </app-button>
          </div>
        </form>
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
    .fila {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      flex-wrap: wrap;
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
    .campo-select,
    .campo-numero,
    .campo-fecha {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select,
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
export class EventDiscountCodes implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly codigos = signal<DiscountCode[]>([]);
  protected readonly tiposDisponibles = signal<TicketTypeOption[]>([]);
  protected readonly editandoId = signal<string | null>(null);

  private readonly valoresIniciales = vacio();
  protected readonly code = signal(this.valoresIniciales.code);
  protected readonly discountType = signal(this.valoresIniciales.discountType);
  protected readonly discountValue = signal(this.valoresIniciales.discountValue);
  protected readonly maxUsos = signal(this.valoresIniciales.maxUses);
  protected readonly validFrom = signal(this.valoresIniciales.validFrom);
  protected readonly validUntil = signal(this.valoresIniciales.validUntil);
  protected readonly ticketTypeId = signal(this.valoresIniciales.ticketTypeId);

  ngOnInit(): void {
    void this.cargarTipos();
    void this.cargar();
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  protected nombreDeTipo(ticketTypeId: string): string {
    return this.tiposDisponibles().find((tipo) => tipo.id === ticketTypeId)?.name ?? '—';
  }

  private async cargarTipos(): Promise<void> {
    try {
      const tipos = await firstValueFrom(
        this.http.get<TicketTypeOption[]>(
          this.api.url(`/events/${this.eventId()}/ticket-types`),
        ),
      );
      this.tiposDisponibles.set(tipos.map((tipo) => ({ id: tipo.id, name: tipo.name })));
    } catch {
      // El formulario sigue funcionando salvo el desplegable de tipos; el
      // error principal ya lo cubre `cargar()`.
    }
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const codigos = await firstValueFrom(
        this.http.get<DiscountCode[]>(this.api.url(`/events/${this.eventId()}/discount-codes`)),
      );
      this.codigos.set([...codigos]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.discountCodes.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected alCambiarTipoDescuento(evento: Event): void {
    this.discountType.set((evento.target as HTMLSelectElement).value as DiscountType);
  }

  protected alCambiarTipoEntrada(evento: Event): void {
    this.ticketTypeId.set((evento.target as HTMLSelectElement).value);
  }

  protected editar(codigo: DiscountCode): void {
    this.editandoId.set(codigo.id);
    this.code.set(codigo.code);
    this.discountType.set(codigo.discount_type);
    this.discountValue.set(String(codigo.discount_value));
    this.maxUsos.set(codigo.max_uses !== null ? String(codigo.max_uses) : '');
    this.validFrom.set(codigo.valid_from ? isoAValorLocal(codigo.valid_from) : '');
    this.validUntil.set(codigo.valid_until ? isoAValorLocal(codigo.valid_until) : '');
    this.ticketTypeId.set(codigo.ticket_type_id ?? '');
    this.formError.set(null);
  }

  protected cancelarEdicion(): void {
    this.editandoId.set(null);
    const vacios = vacio();
    this.code.set(vacios.code);
    this.discountType.set(vacios.discountType);
    this.discountValue.set(vacios.discountValue);
    this.maxUsos.set(vacios.maxUses);
    this.validFrom.set(vacios.validFrom);
    this.validUntil.set(vacios.validUntil);
    this.ticketTypeId.set(vacios.ticketTypeId);
    this.formError.set(null);
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.formError.set(null);

    if (!this.code().trim()) {
      this.formError.set(this.transloco.translate('admin.events.discountCodes.codigoRequerido'));
      return;
    }
    const valor = Number(this.discountValue());
    if (!Number.isFinite(valor) || valor <= 0) {
      this.formError.set(this.transloco.translate('admin.events.discountCodes.valorInvalido'));
      return;
    }
    if (this.discountType() === 'percentage' && valor > 100) {
      this.formError.set(
        this.transloco.translate('admin.events.discountCodes.porcentajeFueraDeRango'),
      );
      return;
    }

    const payload: Record<string, unknown> = {
      code: this.code().trim(),
      discount_type: this.discountType(),
      discount_value: Math.round(valor),
      max_uses: this.maxUsos().trim() ? Number(this.maxUsos()) : null,
      valid_from: this.validFrom() ? new Date(this.validFrom()).toISOString() : null,
      valid_until: this.validUntil() ? new Date(this.validUntil()).toISOString() : null,
      ticket_type_id: this.ticketTypeId() || null,
    };

    this.guardando.set(true);
    try {
      const idEnEdicion = this.editandoId();
      if (idEnEdicion) {
        await firstValueFrom(
          this.http.patch(
            this.api.url(`/events/${this.eventId()}/discount-codes/${idEnEdicion}`),
            payload,
          ),
        );
      } else {
        await firstValueFrom(
          this.http.post(this.api.url(`/events/${this.eventId()}/discount-codes`), payload),
        );
      }
      this.cancelarEdicion();
      await this.cargar();
    } catch (error) {
      this.formError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.discountCodes.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  protected async borrar(discountCodeId: string): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.delete(
          this.api.url(`/events/${this.eventId()}/discount-codes/${discountCodeId}`),
        ),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.discountCodes.error'),
      );
    }
  }
}
