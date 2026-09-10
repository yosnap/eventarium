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
import { AddressMap } from '../../../shared/ui/address-map';

interface EventVenue {
  readonly id: string;
  readonly name: string;
  readonly address: string | null;
  readonly capacity: number | null;
  readonly display_order: number;
  readonly latitude: number | null;
  readonly longitude: number | null;
  readonly geocoded_at: string | null;
}

function vacio(): {
  name: string;
  address: string;
  capacity: string;
  displayOrder: string;
} {
  return { name: '', address: '', capacity: '', displayOrder: '0' };
}

/**
 * Sedes de un evento multisede: alta, edición (nombre, dirección con mapa, aforo,
 * orden) y baja. La geocodificación de la dirección la hace el backend al guardar,
 * a partir del texto elegido en `app-address-map`; esta pantalla nunca envía
 * `latitude`/`longitude` a mano.
 */
@Component({
  selector: 'app-event-venues',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, AddressMap],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.venues.titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (sedes().length === 0) {
          <p>{{ t('admin.events.venues.sinSedes') }}</p>
        } @else {
          <ul class="lista">
            @for (sede of sedes(); track sede.id) {
              <li>
                <div class="fila">
                  <div>
                    <strong>{{ sede.name }}</strong>
                    <span class="detalle">
                      @if (sede.address) {
                        {{ sede.address }} ·
                      }
                      @if (sede.capacity) {
                        {{ t('admin.events.venues.aforo') }}: {{ sede.capacity }} ·
                      }
                      @if (sede.latitude !== null && sede.longitude !== null) {
                        {{ t('admin.events.venues.geocodificada') }}
                      } @else {
                        {{ t('admin.events.venues.sinGeocodificar') }}
                      }
                    </span>
                  </div>
                  <div class="acciones">
                    <app-button variant="secundario" type="button" (pulsado)="editar(sede)">
                      {{ t('admin.events.venues.editar') }}
                    </app-button>
                    <app-button variant="peligro" type="button" (pulsado)="borrar(sede.id)">
                      {{ t('admin.events.venues.eliminar') }}
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
              editandoId() ? t('admin.events.venues.editarSede') : t('admin.events.venues.anadirSede')
            }}
          </h3>

          <app-input
            fieldId="sede-nombre"
            [label]="t('admin.events.venues.nombre')"
            [required]="true"
            [(value)]="nombre"
          />

          <app-address-map
            fieldId="sede-direccion"
            [label]="t('admin.events.venues.direccion')"
            [(value)]="direccion"
            [initialLatitude]="latitudInicial()"
            [initialLongitude]="longitudInicial()"
          />

          <div class="campo-numero">
            <label for="sede-aforo">{{ t('admin.events.venues.aforo') }}</label>
            <input
              id="sede-aforo"
              type="number"
              inputmode="numeric"
              min="1"
              [value]="aforo()"
              (input)="aforo.set(alNumero($event))"
            />
          </div>

          <div class="campo-numero">
            <label for="sede-orden">{{ t('admin.events.venues.orden') }}</label>
            <input
              id="sede-orden"
              type="number"
              inputmode="numeric"
              [value]="orden()"
              (input)="orden.set(alNumero($event))"
            />
          </div>

          @if (formError(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <div class="acciones-finales">
            @if (editandoId()) {
              <app-button variant="secundario" type="button" (pulsado)="cancelarEdicion()">
                {{ t('admin.roles.cancelar') }}
              </app-button>
            }
            <app-button type="submit" [loading]="guardando()">
              {{
                editandoId()
                  ? t('admin.events.venues.guardarCambios')
                  : t('admin.events.venues.anadirSede')
              }}
            </app-button>
          </div>
        </form>
      </app-card>
    </ng-container>
  `,
  styles: `
    h3 {
      margin: var(--sp-4) 0 0;
    }
    .lista {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--sp-3);
    }
    .lista li {
      border-bottom: 1px solid var(--color-border, var(--border));
      padding-bottom: var(--sp-3);
    }
    .fila {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--sp-4);
      flex-wrap: wrap;
    }
    .detalle {
      display: block;
      color: var(--muted, var(--color-text-muted, #6b7280));
      font-size: 0.875rem;
    }
    .acciones {
      display: flex;
      align-items: center;
      gap: var(--sp-2);
      flex-wrap: wrap;
    }
    .formulario {
      display: grid;
      gap: var(--sp-4);
      margin-top: var(--sp-5);
      padding-top: var(--sp-5);
      border-top: 1px solid var(--color-border, var(--border));
      max-width: 34rem;
    }
    .campo-numero {
      display: grid;
      gap: var(--sp-1);
    }
    .campo-numero input {
      width: 100%;
      box-sizing: border-box;
      max-width: 12rem;
      padding: var(--sp-3);
      border: 1px solid var(--color-border, var(--border));
      border-radius: var(--radius-md);
      background-color: var(--color-surface, var(--surface));
      color: var(--color-text, var(--fg));
      font: inherit;
      min-height: 2.75rem;
    }
    .acciones-finales {
      display: flex;
      gap: var(--sp-4);
    }
  `,
})
export class EventVenues implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly sedes = signal<EventVenue[]>([]);
  protected readonly editandoId = signal<string | null>(null);

  private readonly valoresIniciales = vacio();
  protected readonly nombre = signal(this.valoresIniciales.name);
  protected readonly direccion = signal(this.valoresIniciales.address);
  protected readonly aforo = signal(this.valoresIniciales.capacity);
  protected readonly orden = signal(this.valoresIniciales.displayOrder);
  protected readonly latitudInicial = signal<number | null>(null);
  protected readonly longitudInicial = signal<number | null>(null);

  ngOnInit(): void {
    void this.cargar();
  }

  protected alNumero(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const sedes = await firstValueFrom(
        this.http.get<EventVenue[]>(this.api.url(`/events/${this.eventId()}/venues`)),
      );
      this.sedes.set([...sedes]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.venues.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected editar(sede: EventVenue): void {
    this.editandoId.set(sede.id);
    this.nombre.set(sede.name);
    this.direccion.set(sede.address ?? '');
    this.aforo.set(sede.capacity !== null ? String(sede.capacity) : '');
    this.orden.set(String(sede.display_order));
    this.latitudInicial.set(sede.latitude);
    this.longitudInicial.set(sede.longitude);
    this.formError.set(null);
  }

  protected cancelarEdicion(): void {
    this.editandoId.set(null);
    const vacios = vacio();
    this.nombre.set(vacios.name);
    this.direccion.set(vacios.address);
    this.aforo.set(vacios.capacity);
    this.orden.set(vacios.displayOrder);
    this.latitudInicial.set(null);
    this.longitudInicial.set(null);
    this.formError.set(null);
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.formError.set(null);

    if (!this.nombre().trim()) {
      this.formError.set(this.transloco.translate('admin.events.venues.camposRequeridos'));
      return;
    }

    const aforo = this.aforo().trim();
    const orden = this.orden().trim();
    const payload = {
      name: this.nombre().trim(),
      address: this.direccion().trim() || null,
      capacity: aforo ? Number(aforo) : null,
      display_order: orden ? Number(orden) : 0,
    };

    this.guardando.set(true);
    try {
      const idEnEdicion = this.editandoId();
      if (idEnEdicion) {
        await firstValueFrom(
          this.http.patch(this.api.url(`/events/${this.eventId()}/venues/${idEnEdicion}`), payload),
        );
      } else {
        await firstValueFrom(
          this.http.post(this.api.url(`/events/${this.eventId()}/venues`), payload),
        );
      }
      this.cancelarEdicion();
      await this.cargar();
    } catch (error) {
      this.formError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.venues.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  protected async borrar(venueId: string): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/venues/${venueId}`)),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.venues.error'),
      );
    }
  }
}
