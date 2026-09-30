import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { PATRON_SLUG } from '../../../core/routing/rutas-publicas';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Checkbox } from '../../../shared/ui/checkbox';
import { Input } from '../../../shared/ui/input';
import { PageHeader } from '../../../shared/ui/page-header';

interface Categoria {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly display_order: number;
  readonly is_active: boolean;
}

/** Copia editable de una categoría: los campos de la fila mientras se edita. */
interface FilaEditable {
  readonly categoria: Categoria;
  readonly nombre: string;
  readonly orden: string;
  readonly activa: boolean;
}

/**
 * Catálogo de categorías de eventos (solo superadmin). No se borran: una
 * categoría en uso se desactiva, y deja de poder asignarse y de mostrarse en
 * público sin tocar los eventos que ya la tienen. El identificador forma parte
 * de las URLs de filtro del directorio, así que no se cambia una vez creado.
 */
@Component({
  selector: 'app-event-categories-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Checkbox, Input, PageHeader],
  template: `
    <ng-container *transloco="let t; read: 'admin.categorias'">
      <app-page-header [rotulo]="t('rotulo')">
        {{ t('cabeceraInicio') }}
        <span class="mark">{{ t('cabeceraMarca') }}</span>
      </app-page-header>

      <app-card [heading]="t('nueva')">
        <form class="nueva" (submit)="crear($event)" novalidate>
          <app-input
            [label]="t('identificador')"
            [hint]="t('identificadorAyuda')"
            [error]="errorSlug()"
            [(value)]="slugNuevo"
          />
          <app-input [label]="t('nombre')" [(value)]="nombreNuevo" />
          <app-input [label]="t('orden')" inputmode="numeric" [(value)]="ordenNuevo" />
          <app-button type="submit" [loading]="creando()">{{ t('anadir') }}</app-button>
        </form>
        @if (errorCrear(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
      </app-card>

      <app-card [heading]="t('titulo')">
        @if (cargando()) {
          <p>{{ t('cargando') }}</p>
        } @else if (filas().length === 0) {
          <p>{{ t('vacio') }}</p>
        } @else {
          <ul class="lista">
            @for (fila of filas(); track fila.categoria.id) {
              <li class="fila">
                <code class="fila__slug">{{ fila.categoria.slug }}</code>
                <app-input
                  [label]="t('nombre')"
                  [etiquetaOculta]="true"
                  [value]="fila.nombre"
                  (valueChange)="editar(fila.categoria.id, { nombre: $event })"
                />
                <app-input
                  [label]="t('orden')"
                  [etiquetaOculta]="true"
                  inputmode="numeric"
                  [value]="fila.orden"
                  (valueChange)="editar(fila.categoria.id, { orden: $event })"
                />
                <app-checkbox
                  [label]="t('activa')"
                  [checked]="fila.activa"
                  (checkedChange)="editar(fila.categoria.id, { activa: $event })"
                />
                <app-button
                  type="button"
                  variant="secundario"
                  [disabled]="!hayCambios(fila)"
                  [loading]="guardando() === fila.categoria.id"
                  (pulsado)="guardar(fila)"
                >
                  {{ t('guardar') }}
                </app-button>
              </li>
            }
          </ul>
          <p class="nota">{{ t('nota') }}</p>
        }
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    .nueva {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
      gap: var(--space-md);
      align-items: end;
    }
    .lista {
      display: grid;
      gap: var(--space-md);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .fila {
      display: grid;
      grid-template-columns: minmax(6rem, 10rem) 1fr 6rem auto auto;
      gap: var(--space-md);
      align-items: center;
    }
    .fila__slug {
      overflow-wrap: anywhere;
      color: var(--muted);
    }
    .nota {
      margin: var(--space-md) 0 0;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    @media (max-width: 47.5rem) {
      .fila {
        grid-template-columns: 1fr 1fr;
      }
    }
  `,
})
export class EventCategoriesPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly filas = signal<readonly FilaEditable[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly guardando = signal<string | null>(null);

  protected readonly slugNuevo = signal('');
  protected readonly nombreNuevo = signal('');
  protected readonly ordenNuevo = signal('0');
  protected readonly creando = signal(false);
  protected readonly errorSlug = signal<string | null>(null);
  protected readonly errorCrear = signal<string | null>(null);

  constructor() {
    void this.cargar();
  }

  private aFila(categoria: Categoria): FilaEditable {
    return {
      categoria,
      nombre: categoria.name,
      orden: String(categoria.display_order),
      activa: categoria.is_active,
    };
  }

  /** Mismo orden que el catálogo del API: por `display_order` y luego por nombre. */
  private ordenadas(filas: readonly FilaEditable[]): FilaEditable[] {
    return [...filas].sort(
      (a, b) =>
        a.categoria.display_order - b.categoria.display_order ||
        a.categoria.name.localeCompare(b.categoria.name),
    );
  }

  private async cargar(): Promise<void> {
    try {
      const categorias = await firstValueFrom(
        this.http.get<Categoria[]>(this.api.url('/admin/event-categories')),
      );
      this.filas.set(categorias.map((c) => this.aFila(c)));
    } catch (error) {
      this.error.set(this.mensaje(error));
    } finally {
      this.cargando.set(false);
    }
  }

  protected editar(
    id: string,
    cambios: { nombre?: string; orden?: string; activa?: boolean },
  ): void {
    this.filas.update((filas) =>
      filas.map((f) => (f.categoria.id === id ? { ...f, ...cambios } : f)),
    );
  }

  protected hayCambios(fila: FilaEditable): boolean {
    return (
      fila.nombre.trim() !== fila.categoria.name ||
      fila.orden !== String(fila.categoria.display_order) ||
      fila.activa !== fila.categoria.is_active
    );
  }

  private ordenValido(valor: string): number | null {
    const numero = Number(valor);
    return Number.isInteger(numero) && numero >= 0 && numero <= 10000 ? numero : null;
  }

  protected async crear(evento: Event): Promise<void> {
    evento.preventDefault();
    this.errorCrear.set(null);
    this.errorSlug.set(null);
    const slug = this.slugNuevo().trim();
    const nombre = this.nombreNuevo().trim();
    const orden = this.ordenValido(this.ordenNuevo().trim());
    if (!PATRON_SLUG.test(slug) || slug.length < 2 || slug.length > 40) {
      this.errorSlug.set(this.transloco.translate('admin.categorias.identificadorInvalido'));
      return;
    }
    if (!nombre || orden === null) {
      this.errorCrear.set(this.transloco.translate('admin.categorias.datosInvalidos'));
      return;
    }
    this.creando.set(true);
    try {
      const creada = await firstValueFrom(
        this.http.post<Categoria>(this.api.url('/admin/event-categories'), {
          slug,
          name: nombre,
          display_order: orden,
        }),
      );
      this.filas.update((filas) => this.ordenadas([...filas, this.aFila(creada)]));
      this.slugNuevo.set('');
      this.nombreNuevo.set('');
      this.ordenNuevo.set('0');
    } catch (error) {
      this.errorCrear.set(this.mensaje(error));
    } finally {
      this.creando.set(false);
    }
  }

  protected async guardar(fila: FilaEditable): Promise<void> {
    const orden = this.ordenValido(fila.orden.trim());
    const nombre = fila.nombre.trim();
    if (!nombre || orden === null) {
      this.error.set(this.transloco.translate('admin.categorias.datosInvalidos'));
      return;
    }
    this.error.set(null);
    this.guardando.set(fila.categoria.id);
    try {
      const guardada = await firstValueFrom(
        this.http.patch<Categoria>(this.api.url(`/admin/event-categories/${fila.categoria.id}`), {
          name: nombre,
          display_order: orden,
          is_active: fila.activa,
        }),
      );
      this.filas.update((filas) =>
        this.ordenadas(
          filas.map((f) => (f.categoria.id === guardada.id ? this.aFila(guardada) : f)),
        ),
      );
    } catch (error) {
      this.error.set(this.mensaje(error));
    } finally {
      this.guardando.set(null);
    }
  }

  private mensaje(error: unknown): string {
    return error instanceof ApiError
      ? error.message
      : this.transloco.translate('admin.categorias.error');
  }
}
