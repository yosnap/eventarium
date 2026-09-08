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
import { isoAValorLocal } from './datetime-local';
import { EventAgenda } from './event-agenda';
import { EventRegistrations } from './event-registrations';

type EventStatus = 'draft' | 'published' | 'archived';
type LocationMode = 'in_person' | 'online' | 'hybrid';

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const COVER_MIMES_PERMITIDOS = new Set(['image/png', 'image/jpeg', 'image/webp']);
const COVER_TAMANO_MAXIMO = 5 * 1024 * 1024;

interface EventDetail {
  readonly id: string;
  readonly slug: string;
  readonly title: string;
  readonly summary: string | null;
  readonly cover_url: string | null;
  readonly status: EventStatus;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly location_mode: LocationMode;
}

type CampoBase = 'slug' | 'title' | 'startsAt' | 'endsAt';

/** Alta y edición de un evento: campos, portada, publicar/archivar y agenda. */
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
    EventAgenda,
    EventRegistrations,
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
          </app-card>

          @if (esEdicion()) {
            <app-card [heading]="t('admin.events.formulario.portada')">
              @if (portadaUrl(); as url) {
                <img [src]="url" [alt]="t('admin.events.formulario.portada')" height="120" />
              } @else {
                <p>{{ t('admin.events.formulario.sinPortada') }}</p>
              }
              <label class="etiqueta-fichero" for="portada">{{
                t('admin.events.formulario.subirPortada')
              }}</label>
              <input
                id="portada"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                (change)="alSeleccionarPortada($event)"
              />
              @if (errorPortada(); as mensaje) {
                <app-alert tone="error">{{ mensaje }}</app-alert>
              }
            </app-card>

            <app-card [heading]="t('admin.events.formulario.estadoActual')">
              <p>
                {{ t('admin.events.estado' + capitaliza(estadoActual())) }}
              </p>
              <div class="acciones-estado">
                @if (estadoActual() === 'draft') {
                  <app-button
                    type="button"
                    variant="secundario"
                    [loading]="cambiandoEstado()"
                    (pulsado)="cambiarEstado('published')"
                  >
                    {{ t('admin.events.formulario.publicar') }}
                  </app-button>
                }
                @if (estadoActual() !== 'archived') {
                  <app-button
                    type="button"
                    variant="peligro"
                    [loading]="cambiandoEstado()"
                    (pulsado)="cambiarEstado('archived')"
                  >
                    {{ t('admin.events.formulario.archivar') }}
                  </app-button>
                }
              </div>
            </app-card>
          }

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

        @if (esEdicion()) {
          <app-event-agenda [eventId]="eventId()!" />
          <app-event-registrations [eventId]="eventId()!" />
          <a [routerLink]="['/admin/events', eventId(), 'check-in']">
            <app-button variant="secundario" type="button">
              {{ t('admin.events.checkIn.enlaceDesdeEvento') }}
            </app-button>
          </a>
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
    .campo-select {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select {
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
    .etiqueta-fichero {
      display: block;
      margin-top: var(--space-sm);
      font-weight: 500;
    }
    .acciones-estado {
      display: flex;
      gap: var(--space-md);
      margin-top: var(--space-sm);
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
  protected readonly cambiandoEstado = signal(false);
  protected readonly exito = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly errorPortada = signal<string | null>(null);

  protected readonly slug = signal('');
  protected readonly title = signal('');
  protected readonly startsAt = signal('');
  protected readonly endsAt = signal('');
  protected readonly locationMode = signal<LocationMode>('in_person');
  protected readonly estadoActual = signal<EventStatus>('draft');
  protected readonly portadaUrl = signal<string | null>(null);

  protected readonly errores = signal<Record<CampoBase, string | null>>({
    slug: null,
    title: null,
    startsAt: null,
    endsAt: null,
  });

  protected readonly resumenDeErrores = computed<ResumenDeError[]>(() => {
    const actuales = this.errores();
    const resumen: ResumenDeError[] = [];
    if (actuales.title) resumen.push({ campoId: 'evento-titulo', mensaje: actuales.title });
    if (actuales.slug) resumen.push({ campoId: 'evento-slug', mensaje: actuales.slug });
    if (actuales.startsAt) resumen.push({ campoId: 'evento-inicio', mensaje: actuales.startsAt });
    if (actuales.endsAt) resumen.push({ campoId: 'evento-fin', mensaje: actuales.endsAt });
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

  protected capitaliza(valor: string): string {
    return valor.charAt(0).toUpperCase() + valor.slice(1);
  }

  private async cargar(id: string): Promise<void> {
    this.cargando.set(true);
    try {
      const evento = await firstValueFrom(
        this.http.get<EventDetail>(this.api.url(`/events/${id}`)),
      );
      this.slug.set(evento.slug);
      this.title.set(evento.title);
      this.startsAt.set(isoAValorLocal(evento.starts_at));
      this.endsAt.set(isoAValorLocal(evento.ends_at));
      this.locationMode.set(evento.location_mode);
      this.estadoActual.set(evento.status);
      this.portadaUrl.set(evento.cover_url);
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
    };

    this.guardando.set(true);
    try {
      const id = this.eventId();
      if (id) {
        await firstValueFrom(this.http.patch(this.api.url(`/events/${id}`), payload));
      } else {
        const creado = await firstValueFrom(
          this.http.post<EventDetail>(this.api.url('/events'), payload),
        );
        this.eventId.set(creado.id);
        this.estadoActual.set(creado.status);
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

  protected async cambiarEstado(nuevoEstado: EventStatus): Promise<void> {
    const id = this.eventId();
    if (!id) return;
    this.cambiandoEstado.set(true);
    this.error.set(null);
    try {
      const actualizado = await firstValueFrom(
        this.http.patch<EventDetail>(this.api.url(`/events/${id}`), { status: nuevoEstado }),
      );
      this.estadoActual.set(actualizado.status);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    } finally {
      this.cambiandoEstado.set(false);
    }
  }

  protected alSeleccionarPortada(evento: Event): void {
    this.errorPortada.set(null);
    const fichero = (evento.target as HTMLInputElement).files?.[0] ?? null;
    if (!fichero) {
      return;
    }
    if (!COVER_MIMES_PERMITIDOS.has(fichero.type)) {
      this.errorPortada.set(this.transloco.translate('admin.events.formulario.portadaNoValida'));
      (evento.target as HTMLInputElement).value = '';
      return;
    }
    if (fichero.size > COVER_TAMANO_MAXIMO) {
      this.errorPortada.set(
        this.transloco.translate('admin.events.formulario.portadaDemasiadoGrande'),
      );
      (evento.target as HTMLInputElement).value = '';
      return;
    }

    const id = this.eventId();
    if (!id) return;
    void this.subirPortada(id, fichero);
  }

  private async subirPortada(id: string, fichero: File): Promise<void> {
    const datos = new FormData();
    datos.append('fichero', fichero);
    try {
      const actualizado = await firstValueFrom(
        this.http.put<EventDetail>(this.api.url(`/events/${id}/cover`), datos),
      );
      this.portadaUrl.set(actualizado.cover_url);
    } catch (error) {
      this.errorPortada.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.formulario.error'),
      );
    }
  }
}
