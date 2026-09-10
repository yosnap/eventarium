import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { ErrorSummary, ResumenDeError } from '../../../shared/ui/error-summary';
import { Input } from '../../../shared/ui/input';
import { AddressMap } from '../../../shared/ui/address-map';
import { isoAValorLocal } from './datetime-local';
import { EventDetails } from './event-details';

type LocationMode = 'in_person' | 'online' | 'hybrid';

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

interface EventoBase {
  readonly id: string;
  readonly slug: string;
  readonly title: string;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly location_mode: LocationMode;
  readonly city: string | null;
  readonly location_address: string | null;
  readonly latitude: number | null;
  readonly longitude: number | null;
  readonly payment_checkout_window_minutes: number;
}

type CampoBase = 'slug' | 'title' | 'startsAt' | 'endsAt' | 'paymentWindow';

// Rango de `events.payment_checkout_window_minutes` (fase 6 del PRD, fase 2
// de trabajo): espejo del `CHECK` de base de datos y del schema del
// backend, entregados ambos en la fase 1 — aquí no se duplica la regla, solo
// se refleja en el cliente.
const VENTANA_DE_PAGO_MIN = 30;
const VENTANA_DE_PAGO_MAX = 1439;
const VENTANA_DE_PAGO_POR_DEFECTO = 30;

/**
 * Alta y edición de los datos base de un evento (título, slug, fechas, modalidad,
 * ventana de pago). Portada, estado y las secciones del evento viven en
 * `EventDetails`, que este componente delega en cuanto hay un `eventId`.
 */
@Component({
  selector: 'app-event-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    Alert,
    Button,
    Card,
    ErrorSummary,
    Input,
    AddressMap,
    EventDetails,
  ],
  template: `
    <ng-container *transloco="let t">
      <h1>
        {{
          esEdicion()
            ? t('admin.events.formulario.tituloEditar')
            : t('admin.events.formulario.tituloCrear')
        }}
      </h1>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <form (submit)="guardar($event)" novalidate>
          <app-error-summary [errores]="resumenDeErrores()" [titulo]="t('comun.corrigeErrores')" />

          <app-card>
            <app-input
              fieldId="evento-titulo"
              [label]="t('admin.events.formulario.titulo')"
              [required]="true"
              [error]="errores().title"
              [(value)]="title"
              (blurred)="validar('title')"
            />
            <app-input
              fieldId="evento-slug"
              [label]="t('admin.events.formulario.slug')"
              [required]="true"
              [error]="errores().slug"
              [(value)]="slug"
              (blurred)="validar('slug')"
            />
            <app-input
              fieldId="evento-inicio"
              type="datetime-local"
              [label]="t('admin.events.formulario.inicio')"
              [required]="true"
              [error]="errores().startsAt"
              [(value)]="startsAt"
              (blurred)="validar('startsAt')"
            />
            <app-input
              fieldId="evento-fin"
              type="datetime-local"
              [label]="t('admin.events.formulario.fin')"
              [required]="true"
              [error]="errores().endsAt"
              [(value)]="endsAt"
              (blurred)="validar('endsAt')"
            />

            <div class="campo-select">
              <label for="evento-modalidad">{{ t('admin.events.formulario.modalidad') }}</label>
              <select
                id="evento-modalidad"
                [value]="locationMode()"
                (change)="alCambiarModalidad($event)"
              >
                <option value="in_person">{{ t('admin.events.formulario.presencial') }}</option>
                <option value="online">{{ t('admin.events.formulario.online') }}</option>
                <option value="hybrid">{{ t('admin.events.formulario.hibrido') }}</option>
              </select>
            </div>

            @if (locationMode() !== 'online') {
              <app-address-map
                fieldId="evento-direccion"
                [label]="t('admin.events.formulario.direccion')"
                [(value)]="locationAddress"
                [initialLatitude]="latitud()"
                [initialLongitude]="longitud()"
              />
            }

            <app-input
              fieldId="evento-ciudad"
              [label]="t('admin.events.formulario.ciudad')"
              [(value)]="city"
            />

            <div class="campo-numero">
              <label for="evento-ventana-pago">{{
                t('admin.events.formulario.ventanaDePago')
              }}</label>
              <input
                id="evento-ventana-pago"
                type="number"
                inputmode="numeric"
                [min]="ventanaDePagoMin"
                [max]="ventanaDePagoMax"
                [value]="paymentWindow()"
                [attr.aria-invalid]="errores().paymentWindow ? 'true' : null"
                [attr.aria-describedby]="
                  errores().paymentWindow
                    ? 'evento-ventana-pago-error'
                    : 'evento-ventana-pago-ayuda'
                "
                (input)="alCambiarVentanaDePago($event)"
                (blur)="validar('paymentWindow')"
              />
              @if (errores().paymentWindow; as mensaje) {
                <p id="evento-ventana-pago-error" class="error-campo">{{ mensaje }}</p>
              } @else {
                <p id="evento-ventana-pago-ayuda" class="ayuda-campo">
                  {{ t('admin.events.formulario.ventanaDePagoAyuda') }}
                </p>
              }
            </div>
          </app-card>

          @if (exito()) {
            <app-alert tone="exito">{{ t('admin.events.formulario.exito') }}</app-alert>
          }
          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <div class="acciones-finales">
            <a routerLink="/admin/events">
              <app-button variant="secundario" type="button">{{
                t('admin.roles.cancelar')
              }}</app-button>
            </a>
            <app-button type="submit" [loading]="guardando()">
              {{
                guardando()
                  ? t('admin.events.formulario.guardando')
                  : t('admin.events.formulario.guardar')
              }}
            </app-button>
          </div>
        </form>

        @if (eventId(); as id) {
          <app-event-details [eventId]="id" />
        }
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    form {
      display: grid;
      gap: var(--space-lg);
      margin-top: var(--space-md);
      max-width: 34rem;
    }
    .campo-select,
    .campo-numero {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select,
    .campo-numero input {
      width: 100%;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 2.75rem;
    }
    .campo-numero input {
      max-width: 12rem;
    }
    .error-campo {
      margin: 0;
      color: var(--color-danger);
      font-size: 0.875rem;
    }
    .ayuda-campo {
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
export class EventForm {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly route = inject(ActivatedRoute);

  protected readonly eventId = signal<string | null>(null);
  protected readonly esEdicion = computed(() => this.eventId() !== null);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly exito = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly slug = signal('');
  protected readonly title = signal('');
  protected readonly startsAt = signal('');
  protected readonly endsAt = signal('');
  protected readonly locationMode = signal<LocationMode>('in_person');
  protected readonly city = signal('');
  protected readonly locationAddress = signal('');
  protected readonly latitud = signal<number | null>(null);
  protected readonly longitud = signal<number | null>(null);
  protected readonly paymentWindow = signal(VENTANA_DE_PAGO_POR_DEFECTO);
  protected readonly ventanaDePagoMin = VENTANA_DE_PAGO_MIN;
  protected readonly ventanaDePagoMax = VENTANA_DE_PAGO_MAX;

  protected readonly errores = signal<Record<CampoBase, string | null>>({
    slug: null,
    title: null,
    startsAt: null,
    endsAt: null,
    paymentWindow: null,
  });

  protected readonly resumenDeErrores = computed<ResumenDeError[]>(() => {
    const actuales = this.errores();
    const resumen: ResumenDeError[] = [];
    if (actuales.title) resumen.push({ campoId: 'evento-titulo', mensaje: actuales.title });
    if (actuales.slug) resumen.push({ campoId: 'evento-slug', mensaje: actuales.slug });
    if (actuales.startsAt) resumen.push({ campoId: 'evento-inicio', mensaje: actuales.startsAt });
    if (actuales.endsAt) resumen.push({ campoId: 'evento-fin', mensaje: actuales.endsAt });
    if (actuales.paymentWindow) {
      resumen.push({ campoId: 'evento-ventana-pago', mensaje: actuales.paymentWindow });
    }
    return resumen;
  });

  constructor() {
    const id = this.route.snapshot.paramMap.get('id');
    if (id && id !== 'nuevo') {
      this.eventId.set(id);
      void this.cargar(id);
    } else {
      this.cargando.set(false);
    }
  }

  private async cargar(id: string): Promise<void> {
    this.cargando.set(true);
    try {
      const evento = await firstValueFrom(this.http.get<EventoBase>(this.api.url(`/events/${id}`)));
      this.slug.set(evento.slug);
      this.title.set(evento.title);
      this.startsAt.set(isoAValorLocal(evento.starts_at));
      this.endsAt.set(isoAValorLocal(evento.ends_at));
      this.locationMode.set(evento.location_mode);
      this.city.set(evento.city ?? '');
      this.locationAddress.set(evento.location_address ?? '');
      this.latitud.set(evento.latitude);
      this.longitud.set(evento.longitude);
      this.paymentWindow.set(evento.payment_checkout_window_minutes);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected alCambiarModalidad(evento: Event): void {
    this.locationMode.set((evento.target as HTMLSelectElement).value as LocationMode);
  }

  protected alCambiarVentanaDePago(evento: Event): void {
    const bruto = (evento.target as HTMLInputElement).value;
    this.paymentWindow.set(bruto === '' ? Number.NaN : Number(bruto));
  }

  private errorDe(campo: CampoBase): string | null {
    switch (campo) {
      case 'title':
        return this.title().trim()
          ? null
          : this.transloco.translate('admin.events.formulario.tituloRequerido');
      case 'slug': {
        const valor = this.slug().trim();
        if (!valor) return this.transloco.translate('admin.events.formulario.slugRequerido');
        return SLUG_RE.test(valor)
          ? null
          : this.transloco.translate('admin.events.formulario.slugInvalido');
      }
      case 'startsAt':
        return this.startsAt()
          ? null
          : this.transloco.translate('admin.events.formulario.inicioRequerido');
      case 'endsAt':
        if (!this.endsAt()) {
          return this.transloco.translate('admin.events.formulario.finRequerido');
        }
        return new Date(this.endsAt()) > new Date(this.startsAt())
          ? null
          : this.transloco.translate('admin.events.formulario.finAnteriorAlInicio');
      case 'paymentWindow': {
        const valor = this.paymentWindow();
        if (Number.isNaN(valor)) {
          return this.transloco.translate('admin.events.formulario.ventanaDePagoRequerida');
        }
        return valor >= VENTANA_DE_PAGO_MIN && valor <= VENTANA_DE_PAGO_MAX
          ? null
          : this.transloco.translate('admin.events.formulario.ventanaDePagoFueraDeRango');
      }
    }
  }

  protected validar(campo: CampoBase): void {
    this.errores.update((actuales) => ({ ...actuales, [campo]: this.errorDe(campo) }));
  }

  private validarTodo(): boolean {
    const actuales: Record<CampoBase, string | null> = {
      slug: this.errorDe('slug'),
      title: this.errorDe('title'),
      startsAt: this.errorDe('startsAt'),
      endsAt: this.errorDe('endsAt'),
      paymentWindow: this.errorDe('paymentWindow'),
    };
    this.errores.set(actuales);
    return Object.values(actuales).every((mensaje) => !mensaje);
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    this.exito.set(false);
    if (!this.validarTodo()) {
      return;
    }

    const payload = {
      slug: this.slug().trim(),
      title: this.title().trim(),
      starts_at: new Date(this.startsAt()).toISOString(),
      ends_at: new Date(this.endsAt()).toISOString(),
      location_mode: this.locationMode(),
      city: this.city().trim() || null,
      location_address:
        this.locationMode() !== 'online' ? this.locationAddress().trim() || null : null,
      payment_checkout_window_minutes: this.paymentWindow(),
    };

    this.guardando.set(true);
    try {
      const id = this.eventId();
      if (id) {
        await firstValueFrom(this.http.patch(this.api.url(`/events/${id}`), payload));
      } else {
        const creado = await firstValueFrom(
          this.http.post<EventoBase>(this.api.url('/events'), payload),
        );
        this.eventId.set(creado.id);
      }
      this.exito.set(true);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
