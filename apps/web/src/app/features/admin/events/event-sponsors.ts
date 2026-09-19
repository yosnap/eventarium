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
import { MediaElegida, MediaPicker } from '../../../shared/ui/media-picker';
import { Textarea } from '../../../shared/ui/textarea';
import { PageHeader } from '../../../shared/ui/page-header';
import { capitalizarClaveDeTraduccion } from '../../../shared/text/capitalizar-clave-de-traduccion';
import { LOGO_ACEPTADOS } from '../../../shared/uploads/image-upload-constraints';

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
  imports: [TranslocoDirective, Alert, Button, Card, Input, MediaPicker, Textarea, PageHeader],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.events.sponsors.titulo')">
        {{ t('admin.events.sponsors.cabeceraInicio') }}
        <span class="mark">{{ t('admin.events.sponsors.cabeceraMarca') }}</span>
      </app-page-header>

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
                  <div>
                    <strong>{{ patrocinador.name }}</strong>
                    <span class="detalle">
                      {{ nombreDeNivel(patrocinador.tier_id) }} ·
                      {{
                        t('admin.events.sponsors.tipo' + capitaliza(patrocinador.contribution_type))
                      }}
                    </span>
                  </div>
                  <app-media-picker
                    class="logo-picker"
                    [etiqueta]="t('admin.events.sponsors.logoDe', { nombre: patrocinador.name })"
                    [aceptados]="LOGO_ACEPTADOS"
                    kind="sponsors"
                    [url]="patrocinador.logo_url"
                    (mediaElegido)="asignarLogo(patrocinador.id, $event)"
                  />
                  <div class="acciones">
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
      border-bottom: 1px solid var(--border);
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
      color: var(--muted);
      font-size: 0.875rem;
    }
    .logo-picker {
      min-width: 12rem;
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
      border-top: 1px solid var(--border);
      max-width: 34rem;
    }
    .campo-select {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select {
      /* La pintura del control la da la regla compartida de styles.css. */
      width: 100%;
    }
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class EventSponsors implements OnInit {
  readonly eventId = input.required<string>();
  protected readonly LOGO_ACEPTADOS = LOGO_ACEPTADOS;

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

  /** El fichero/URL/biblioteca ya se resolvió a un `media_id` dentro de
   * `MediaPicker` (Fase 3 del plan de biblioteca de medios): aquí solo queda
   * asignarlo al patrocinador de ESA fila — `sponsorId` lo aporta la
   * plantilla, el picker no lo conoce. */
  protected async asignarLogo(sponsorId: string, media: MediaElegida): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(
        this.http.put(this.api.url(`/events/${this.eventId()}/sponsors/${sponsorId}/logo`), {
          media_id: media.id,
        }),
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
