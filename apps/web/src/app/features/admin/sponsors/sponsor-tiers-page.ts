import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
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

type LogoSize = 'large' | 'medium' | 'small';

interface SponsorTier {
  readonly id: string;
  readonly name: string;
  readonly display_order: number;
  readonly logo_size: LogoSize;
  readonly benefits: string | null;
}

interface Page<T> {
  readonly items: readonly T[];
}

const TIERS_URL = '/organizations/me/sponsor-tiers';
const TAMANOS: readonly LogoSize[] = ['large', 'medium', 'small'];

function vacio(): { name: string; logoSize: LogoSize; benefits: string } {
  return { name: '', logoSize: 'medium', benefits: '' };
}

/**
 * Niveles de patrocinio de la organización (ej. Oro, Plata, Bronce): alta,
 * edición, reordenación por botones (nunca arrastrar y soltar sin alternativa
 * por teclado, WCAG 2.1 AA) y borrado, bloqueado con 409 si el nivel tiene
 * patrocinadores asignados en algún evento.
 */
@Component({
  selector: 'app-sponsor-tiers-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, Textarea],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.sponsorTiers.titulo') }}</h1>
      <p>{{ t('admin.sponsorTiers.descripcion') }}</p>

      @if (error(); as mensaje) {
        <app-alert tone="error">{{ mensaje }}</app-alert>
      }

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (niveles().length === 0) {
        <p>{{ t('admin.sponsorTiers.sinNiveles') }}</p>
      } @else {
        <app-card>
          <ul class="niveles">
            @for (nivel of niveles(); track nivel.id; let indice = $index) {
              <li>
                <div class="fila">
                  <div>
                    <strong>{{ nivel.name }}</strong>
                    <span class="detalle">
                      {{ t('admin.sponsorTiers.tamanoLogo' + capitaliza(nivel.logo_size)) }}
                    </span>
                  </div>
                  <div class="acciones">
                    <app-button
                      variant="secundario"
                      type="button"
                      [disabled]="indice === 0"
                      [attr.aria-label]="t('admin.sponsorTiers.subir', { nombre: nivel.name })"
                      (pulsado)="mover(indice, -1)"
                    >
                      ↑
                    </app-button>
                    <app-button
                      variant="secundario"
                      type="button"
                      [disabled]="indice === niveles().length - 1"
                      [attr.aria-label]="t('admin.sponsorTiers.bajar', { nombre: nivel.name })"
                      (pulsado)="mover(indice, 1)"
                    >
                      ↓
                    </app-button>
                    <app-button variant="secundario" type="button" (pulsado)="editar(nivel)">
                      {{ t('admin.sponsorTiers.editar') }}
                    </app-button>
                    <app-button variant="peligro" type="button" (pulsado)="borrar(nivel.id)">
                      {{ t('admin.sponsorTiers.eliminar') }}
                    </app-button>
                  </div>
                </div>
              </li>
            }
          </ul>
        </app-card>
      }

      <app-card [heading]="editandoId() ? t('admin.sponsorTiers.editarNivel') : t('admin.sponsorTiers.anadirNivel')">
        <form (submit)="guardar($event)" novalidate class="formulario">
          <app-input
            fieldId="nivel-nombre"
            [label]="t('admin.sponsorTiers.nombre')"
            [required]="true"
            [(value)]="nombre"
          />

          <div class="campo-select">
            <label for="nivel-tamano">{{ t('admin.sponsorTiers.tamanoLogoCampo') }}</label>
            <select id="nivel-tamano" [value]="tamanoLogo()" (change)="alCambiarTamano($event)">
              @for (opcion of tamanosDisponibles; track opcion) {
                <option [value]="opcion">
                  {{ t('admin.sponsorTiers.tamanoLogo' + capitaliza(opcion)) }}
                </option>
              }
            </select>
          </div>

          <app-textarea
            fieldId="nivel-beneficios"
            [label]="t('admin.sponsorTiers.beneficios')"
            [(value)]="beneficios"
          />

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
                  ? t('admin.sponsorTiers.guardarCambios')
                  : t('admin.sponsorTiers.anadirNivel')
              }}
            </app-button>
          </div>
        </form>
      </app-card>
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    .niveles {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: var(--space-sm);
    }
    .niveles li {
      border-bottom: 1px solid var(--color-border);
      padding-bottom: var(--space-sm);
    }
    .fila {
      display: flex;
      justify-content: space-between;
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
      gap: var(--space-sm);
      flex-wrap: wrap;
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
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
export class SponsorTiersPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly tamanosDisponibles = TAMANOS;

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly formError = signal<string | null>(null);
  protected readonly niveles = signal<SponsorTier[]>([]);
  protected readonly editandoId = signal<string | null>(null);

  private readonly valoresIniciales = vacio();
  protected readonly nombre = signal(this.valoresIniciales.name);
  protected readonly tamanoLogo = signal(this.valoresIniciales.logoSize);
  protected readonly beneficios = signal(this.valoresIniciales.benefits);

  constructor() {
    void this.cargar();
  }

  protected capitaliza(valor: string): string {
    return capitalizarClaveDeTraduccion(valor);
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const pagina = await firstValueFrom(
        this.http.get<Page<SponsorTier>>(this.api.url(TIERS_URL), {
          params: { limit: 100, offset: 0 },
        }),
      );
      this.niveles.set([...pagina.items]);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.sponsorTiers.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected alCambiarTamano(evento: Event): void {
    this.tamanoLogo.set((evento.target as HTMLSelectElement).value as LogoSize);
  }

  protected editar(nivel: SponsorTier): void {
    this.editandoId.set(nivel.id);
    this.nombre.set(nivel.name);
    this.tamanoLogo.set(nivel.logo_size);
    this.beneficios.set(nivel.benefits ?? '');
    this.formError.set(null);
  }

  protected cancelarEdicion(): void {
    this.editandoId.set(null);
    const vacios = vacio();
    this.nombre.set(vacios.name);
    this.tamanoLogo.set(vacios.logoSize);
    this.beneficios.set(vacios.benefits);
    this.formError.set(null);
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.formError.set(null);

    if (!this.nombre().trim()) {
      this.formError.set(this.transloco.translate('admin.sponsorTiers.nombreRequerido'));
      return;
    }

    const payload = {
      name: this.nombre().trim(),
      logo_size: this.tamanoLogo(),
      benefits: this.beneficios().trim() || null,
    };

    this.guardando.set(true);
    try {
      const idEnEdicion = this.editandoId();
      if (idEnEdicion) {
        await firstValueFrom(this.http.patch(this.api.url(`${TIERS_URL}/${idEnEdicion}`), payload));
      } else {
        const maximo = this.niveles().reduce((acc, n) => Math.max(acc, n.display_order), -1);
        await firstValueFrom(
          this.http.post(this.api.url(TIERS_URL), { ...payload, display_order: maximo + 1 }),
        );
      }
      this.cancelarEdicion();
      await this.cargar();
    } catch (error) {
      this.formError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.sponsorTiers.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  protected async mover(indice: number, delta: 1 | -1): Promise<void> {
    const lista = this.niveles();
    const destino = indice + delta;
    if (destino < 0 || destino >= lista.length) {
      return;
    }
    const actual = lista[indice];
    const vecino = lista[destino];
    this.error.set(null);
    try {
      // Los dos `PATCH` tocan filas distintas (dos niveles de patrocinio
      // distintos) sin ninguna restricción `UNIQUE` sobre `display_order`, así
      // que no compiten entre sí: van en paralelo en vez de en serie.
      await Promise.all([
        firstValueFrom(
          this.http.patch(this.api.url(`${TIERS_URL}/${actual.id}`), {
            display_order: vecino.display_order,
          }),
        ),
        firstValueFrom(
          this.http.patch(this.api.url(`${TIERS_URL}/${vecino.id}`), {
            display_order: actual.display_order,
          }),
        ),
      ]);
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.sponsorTiers.error'),
      );
    }
  }

  protected async borrar(tierId: string): Promise<void> {
    this.error.set(null);
    try {
      await firstValueFrom(this.http.delete(this.api.url(`${TIERS_URL}/${tierId}`)));
      await this.cargar();
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.sponsorTiers.error'),
      );
    }
  }
}
