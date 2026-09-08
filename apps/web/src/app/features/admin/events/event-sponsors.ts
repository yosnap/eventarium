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
import { capitalizarClaveDeTraduccion } from '../../../shared/text/capitalizar-clave-de-traduccion';
import {
  IMAGEN_MIMES_PERMITIDOS,
  IMAGEN_TAMANO_MAXIMO,
} from '../../../shared/uploads/image-upload-constraints';

type ContributionType = 'monetaria' | 'en_especie';

interface SponsorTier {
  readonly id: string;
  readonly name: string;
}

interface Sponsor {
  readonly id: string;
  readonly tier_id: string;
  readonly name: string;
  readonly logo_url: string | null;
  readonly website: string | null;
  readonly contribution_type: ContributionType;
  readonly contribution_amount: string | null;
  readonly contribution_description: string | null;
}

interface Page<T> {
  readonly items: readonly T[];
}

function vacio(): {
  tierId: string;
  name: string;
  website: string;
  contributionType: ContributionType;
  contributionAmount: string;
  contributionDescription: string;
} {
  return {
    tierId: '',
    name: '',
    website: '',
    contributionType: 'monetaria',
    contributionAmount: '',
    contributionDescription: '',
  };
}

/**
 * Patrocinadores de un evento: alta, edición, logo y baja. El tipo de
 * aportación (monetaria/en especie) muestra su campo correspondiente y limpia
 * el otro al cambiar, para que nunca se envíen los dos a la vez (el backend lo
 * rechazaría con 422, pero mostrarlo antes evita el viaje de ida y vuelta).
 */
@Component({
  selector: 'app-event-sponsors',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, Textarea],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.sponsors.titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (nivelesDisponibles().length === 0) {
          <p>{{ t('admin.events.sponsors.sinNiveles') }}</p>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (patrocinadores().length === 0) {
          <p>{{ t('admin.events.sponsors.sinPatrocinadores') }}</p>
        } @else {
          <ul class="lista">
            @for (patrocinador of patrocinadores(); track patrocinador.id) {
              <li>
                <div class="fila">
                  @if (patrocinador.logo_url) {
                    <img
                      class="logo"
                      [src]="patrocinador.logo_url"
                      [alt]="t('admin.events.sponsors.logoDe', { nombre: patrocinador.name })"
                    />
                  }
                  <div>
                    <strong>{{ patrocinador.name }}</strong>
                    <span class="detalle">
                      {{ nombreDeNivel(patrocinador.tier_id) }} ·
                      {{
                        t('admin.events.sponsors.tipo' + capitaliza(patrocinador.contribution_type))
                      }}
                    </span>
                  </div>
                  <div class="acciones">
                    <label class="etiqueta-fichero" [for]="'logo-' + patrocinador.id">
                      {{ t('admin.events.sponsors.subirLogo') }}
                    </label>
                    <input
                      [id]="'logo-' + patrocinador.id"
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      (change)="alSeleccionarLogo($event, patrocinador.id)"
                    />
                    <app-button variant="secundario" type="button" (pulsado)="editar(patrocinador)">
                      {{ t('admin.events.sponsors.editar') }}
                    </app-button>
                    <app-button variant="peligro" type="button" (pulsado)="borrar(patrocinador.id)">
                      {{ t('admin.events.sponsors.eliminar') }}
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
                ? t('admin.events.sponsors.editarPatrocinador')
                : t('admin.events.sponsors.anadirPatrocinador')
            }}
          </h3>

          <div class="campo-select">
            <label for="patrocinador-nivel">{{ t('admin.events.sponsors.nivel') }}</label>
            <select id="patrocinador-nivel" [value]="tierId()" (change)="alCambiarNivel($event)">
              <option value="">{{ t('admin.events.sponsors.elegirNivel') }}</option>
              @for (nivel of nivelesDisponibles(); track nivel.id) {
                <option [value]="nivel.id">{{ nivel.name }}</option>
              }
            </select>
          </div>

          <app-input
            fieldId="patrocinador-nombre"
            [label]="t('admin.events.sponsors.nombre')"
            [required]="true"
            [(value)]="nombre"
          />
          <app-input
            fieldId="patrocinador-web"
            type="url"
            [label]="t('admin.events.sponsors.web')"
            [(value)]="website"
          />

          <div class="campo-select">
            <label for="patrocinador-tipo">{{ t('admin.events.sponsors.tipoAportacion') }}</label>
            <select
              id="patrocinador-tipo"
              [value]="tipoAportacion()"
              (change)="alCambiarTipo($event)"
            >
              <option value="monetaria">{{ t('admin.events.sponsors.tipoMonetaria') }}</option>
              <option value="en_especie">{{ t('admin.events.sponsors.tipoEnEspecie') }}</option>
            </select>
          </div>

          @if (tipoAportacion() === 'monetaria') {
            <app-input
              fieldId="patrocinador-importe"
              [label]="t('admin.events.sponsors.importe')"
              [required]="true"
              [(value)]="importe"
            />
          } @else {
            <app-textarea
              fieldId="patrocinador-descripcion"
              [label]="t('admin.events.sponsors.descripcionAportacion')"
              [(value)]="descripcion"
            />
          }

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
                  ? t('admin.events.sponsors.guardarCambios')
                  : t('admin.events.sponsors.anadirPatrocinador')
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
    .logo {
      height: 2.5rem;
      width: auto;
      border-radius: var(--radius-sm, 4px);
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
    .etiqueta-fichero {
      font-size: 0.8125rem;
      font-weight: 500;
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      margin-top: var(--space-lg);
      padding-top: var(--space-lg);
      border-top: 1px solid var(--color-border);
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
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class EventSponsors implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly patrocinadores = signal<Sponsor[]>([]);
  protected readonly nivelesDisponibles = signal<SponsorTier[]>([]);
  protected readonly editandoId = signal<string | null>(null);

  private readonly valoresIniciales = vacio();
  protected readonly tierId = signal(this.valoresIniciales.tierId);
  protected readonly nombre = signal(this.valoresIniciales.name);
  protected readonly website = signal(this.valoresIniciales.website);
  protected readonly tipoAportacion = signal(this.valoresIniciales.contributionType);
  protected readonly importe = signal(this.valoresIniciales.contributionAmount);
  protected readonly descripcion = signal(this.valoresIniciales.contributionDescription);

  ngOnInit(): void {
    void this.cargarNiveles();
    void this.cargar();
  }

  protected capitaliza(valor: string): string {
    return capitalizarClaveDeTraduccion(valor);
  }

  protected nombreDeNivel(tierId: string): string {
    return this.nivelesDisponibles().find((n) => n.id === tierId)?.name ?? '—';
  }

  private async cargarNiveles(): Promise<void> {
    try {
      const pagina = await firstValueFrom(
        this.http.get<Page<SponsorTier>>(this.api.url('/organizations/me/sponsor-tiers'), {
          params: { limit: 100, offset: 0 },
        }),
      );
      this.nivelesDisponibles.set([...pagina.items]);
    } catch {
      // El formulario de patrocinadores sigue funcionando salvo la lista de
      // niveles; el error principal ya lo cubre `cargar()`.
    }
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const patrocinadores = await firstValueFrom(
        this.http.get<Sponsor[]>(this.api.url(`/events/${this.eventId()}/sponsors`)),
      );
      this.patrocinadores.set([...patrocinadores]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.sponsors.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected alCambiarNivel(evento: Event): void {
    this.tierId.set((evento.target as HTMLSelectElement).value);
  }

  protected alCambiarTipo(evento: Event): void {
    this.tipoAportacion.set((evento.target as HTMLSelectElement).value as ContributionType);
    // El backend rechaza tener los dos campos a la vez: al cambiar de tipo se
    // limpia el que ya no aplica en vez de arrastrarlo oculto en el formulario.
    this.importe.set('');
    this.descripcion.set('');
  }

  protected editar(patrocinador: Sponsor): void {
    this.editandoId.set(patrocinador.id);
    this.tierId.set(patrocinador.tier_id);
    this.nombre.set(patrocinador.name);
    this.website.set(patrocinador.website ?? '');
    this.tipoAportacion.set(patrocinador.contribution_type);
    this.importe.set(patrocinador.contribution_amount ?? '');
    this.descripcion.set(patrocinador.contribution_description ?? '');
    this.formError.set(null);
  }

  protected cancelarEdicion(): void {
    this.editandoId.set(null);
    const vacios = vacio();
    this.tierId.set(vacios.tierId);
    this.nombre.set(vacios.name);
    this.website.set(vacios.website);
    this.tipoAportacion.set(vacios.contributionType);
    this.importe.set(vacios.contributionAmount);
    this.descripcion.set(vacios.contributionDescription);
    this.formError.set(null);
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.formError.set(null);

    if (!this.tierId() || !this.nombre().trim()) {
      this.formError.set(this.transloco.translate('admin.events.sponsors.camposRequeridos'));
      return;
    }
    if (this.tipoAportacion() === 'monetaria' && !this.importe().trim()) {
      this.formError.set(this.transloco.translate('admin.events.sponsors.importeRequerido'));
      return;
    }
    if (this.tipoAportacion() === 'en_especie' && !this.descripcion().trim()) {
      this.formError.set(this.transloco.translate('admin.events.sponsors.descripcionRequerida'));
      return;
    }

    const payload = {
      tier_id: this.tierId(),
      name: this.nombre().trim(),
      website: this.website().trim() || null,
      contribution_type: this.tipoAportacion(),
      contribution_amount: this.tipoAportacion() === 'monetaria' ? this.importe().trim() : null,
      contribution_description:
        this.tipoAportacion() === 'en_especie' ? this.descripcion().trim() : null,
    };

    this.guardando.set(true);
    try {
      const idEnEdicion = this.editandoId();
      if (idEnEdicion) {
        await firstValueFrom(
          this.http.patch(
            this.api.url(`/events/${this.eventId()}/sponsors/${idEnEdicion}`),
            payload,
          ),
        );
      } else {
        await firstValueFrom(
          this.http.post(this.api.url(`/events/${this.eventId()}/sponsors`), payload),
        );
      }
      this.cancelarEdicion();
      await this.cargar();
    } catch (error) {
      this.formError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.sponsors.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  protected async borrar(sponsorId: string): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/sponsors/${sponsorId}`)),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.sponsors.error'),
      );
    }
  }

  protected alSeleccionarLogo(evento: Event, sponsorId: string): void {
    this.error.set(null);
    const fichero = (evento.target as HTMLInputElement).files?.[0] ?? null;
    if (!fichero) {
      return;
    }
    if (!IMAGEN_MIMES_PERMITIDOS.has(fichero.type)) {
      this.error.set(this.transloco.translate('admin.events.sponsors.logoNoValido'));
      (evento.target as HTMLInputElement).value = '';
      return;
    }
    if (fichero.size > IMAGEN_TAMANO_MAXIMO) {
      this.error.set(this.transloco.translate('admin.events.sponsors.logoDemasiadoGrande'));
      (evento.target as HTMLInputElement).value = '';
      return;
    }
    void this.subirLogo(sponsorId, fichero);
  }

  private async subirLogo(sponsorId: string, fichero: File): Promise<void> {
    const datos = new FormData();
    datos.append('fichero', fichero);
    try {
      await firstValueFrom(
        this.http.put(this.api.url(`/events/${this.eventId()}/sponsors/${sponsorId}/logo`), datos),
      );
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.sponsors.error'),
      );
    }
  }
}
