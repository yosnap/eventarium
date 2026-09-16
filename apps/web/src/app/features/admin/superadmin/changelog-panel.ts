import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { Button } from '../../../shared/ui/button';
import { Chip, ChipTone } from '../../../shared/ui/chip';
import { ChangelogCategoria, ChangelogVersion } from './changelog.data';

const VERSIONES_POR_PAGINA = 6;

/**
 * Historial de cambios de la instalación, en la portada del panel de plataforma.
 *
 * Patrón: lista de versiones en acordeón (solo la primera empieza abierta),
 * cada una con sus cambios agrupados por categoría — réplica del «Historial de
 * canvis» de Motoraldia, adaptada al sistema de diseño de Eventarium (chip en
 * vez de badge+icono de Lucide, que no está instalado aquí).
 *
 * Paginado en cliente porque el propio historial es un array estático
 * (`changelog.data.ts`), no una consulta a la API: no hay offset/limit que
 * pedir al servidor, así que pagina() corta el array ya cargado.
 */
@Component({
  selector: 'app-changelog-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, Chip],
  template: `
    <ng-container *transloco="let t">
      <section class="changelog" aria-labelledby="changelog-titulo">
        <div class="cabecera">
          <h2 id="changelog-titulo">{{ t('admin.plataforma.changelog.titulo') }}</h2>
          @if (versionActual(); as v) {
            <span class="version-actual">{{ t('admin.plataforma.changelog.version', { v }) }}</span>
          }
        </div>

        @if (visibles().length === 0) {
          <p class="vacio">{{ t('admin.plataforma.changelog.sinDatos') }}</p>
        }

        <ul class="lista">
          @for (release of visibles(); track release.version; let i = $index) {
            <li class="release">
              <button
                type="button"
                class="release-cabecera"
                [attr.aria-expanded]="estaAbierta(release.version, i)"
                [attr.aria-controls]="'changelog-cuerpo-' + release.version"
                (click)="alternar(release.version, i)"
              >
                <span class="release-version">v{{ release.version }}</span>
                <span class="release-fecha">{{ fecha(release.fecha) }}</span>
                <span class="release-flecha" [class.abierta]="estaAbierta(release.version, i)"
                  >›</span
                >
              </button>

              @if (estaAbierta(release.version, i)) {
                <div class="release-cuerpo" [id]="'changelog-cuerpo-' + release.version">
                  @for (seccion of release.secciones; track seccion.categoria) {
                    <div class="seccion">
                      <app-chip [tone]="tonoDeCategoria(seccion.categoria)">{{
                        t('admin.plataforma.changelog.categoria.' + seccion.categoria)
                      }}</app-chip>
                      <ul class="items">
                        @for (item of seccion.items; track item.titulo) {
                          <li><strong>{{ item.titulo }}</strong>: {{ item.descripcion }}</li>
                        }
                      </ul>
                    </div>
                  }
                </div>
              }
            </li>
          }
        </ul>

        @if (totalPaginas() > 1) {
          <nav [attr.aria-label]="t('admin.plataforma.changelog.titulo')" class="paginacion">
            <app-button
              variant="secundario"
              type="button"
              [disabled]="pagina() === 0"
              (pulsado)="irAPagina(-1)"
            >
              {{ t('admin.members.anterior') }}
            </app-button>
            <span>
              {{
                t('admin.members.paginaDe', { actual: pagina() + 1, total: totalPaginas() })
              }}
            </span>
            <app-button
              variant="secundario"
              type="button"
              [disabled]="pagina() + 1 >= totalPaginas()"
              (pulsado)="irAPagina(1)"
            >
              {{ t('admin.members.siguiente') }}
            </app-button>
          </nav>
        }
      </section>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .changelog {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      padding: var(--sp-5);
    }
    .cabecera {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--sp-3);
      margin-bottom: var(--sp-4);
    }
    h2 {
      margin: 0;
    }
    .version-actual {
      font-family: var(--font-mono);
      font-size: var(--fs-sm);
      padding: 3px 9px;
      border-radius: 3px;
      color: var(--accent);
      border: 1px solid color-mix(in oklch, var(--accent), transparent 55%);
      background: var(--accent-dim);
    }
    .vacio {
      color: var(--muted);
      margin: 0;
    }
    .lista {
      display: grid;
      gap: var(--sp-3);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .release {
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
    }
    .release-cabecera {
      display: flex;
      align-items: center;
      gap: var(--sp-3);
      width: 100%;
      padding: var(--sp-3) var(--sp-4);
      background: none;
      border: none;
      color: var(--fg);
      font: inherit;
      text-align: left;
      cursor: pointer;
      min-height: 2.75rem;
    }
    .release-version {
      font-family: var(--font-mono);
      font-weight: 600;
    }
    .release-fecha {
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .release-flecha {
      margin-left: auto;
      transition: transform 0.15s ease;
    }
    .release-flecha.abierta {
      transform: rotate(90deg);
    }
    .release-cuerpo {
      padding: 0 var(--sp-4) var(--sp-4);
      display: grid;
      gap: var(--sp-4);
    }
    .seccion {
      display: grid;
      gap: var(--sp-2);
    }
    .items {
      margin: 0;
      padding-left: 1.25rem;
    }
    .items li {
      margin-bottom: var(--space-xs);
    }
    .items li:last-child {
      margin-bottom: 0;
    }
    .paginacion {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      margin-top: var(--sp-4);
    }
  `,
})
export class ChangelogPanel {
  private readonly transloco = inject(TranslocoService);

  readonly versiones = input.required<readonly ChangelogVersion[]>();

  protected readonly versionActual = computed(() => this.versiones()[0]?.version ?? null);

  protected readonly pagina = signal(0);
  protected readonly abiertas = signal<ReadonlySet<string>>(new Set());
  protected readonly tocado = signal(false);

  protected readonly totalPaginas = computed(() =>
    Math.max(1, Math.ceil(this.versiones().length / VERSIONES_POR_PAGINA)),
  );

  protected readonly visibles = computed(() => {
    const inicio = this.pagina() * VERSIONES_POR_PAGINA;
    return this.versiones().slice(inicio, inicio + VERSIONES_POR_PAGINA);
  });

  protected estaAbierta(version: string, indice: number): boolean {
    if (this.abiertas().has(version)) {
      return true;
    }
    return !this.tocado() && this.pagina() === 0 && indice === 0;
  }

  protected alternar(version: string, indice: number): void {
    const abierta = this.estaAbierta(version, indice);
    this.tocado.set(true);
    this.abiertas.update((actual) => {
      const copia = new Set(actual);
      if (abierta) {
        copia.delete(version);
      } else {
        copia.add(version);
      }
      return copia;
    });
  }

  protected irAPagina(delta: number): void {
    this.pagina.update((p) => Math.max(0, Math.min(this.totalPaginas() - 1, p + delta)));
  }

  protected tonoDeCategoria(categoria: ChangelogCategoria): ChipTone {
    const tonos: Record<ChangelogCategoria, ChipTone> = {
      agregado: 'ok',
      corregido: 'espera',
      modificado: 'neutro',
    };
    return tonos[categoria];
  }

  protected fecha(iso: string): string {
    return new Intl.DateTimeFormat('es-ES', { dateStyle: 'long' }).format(new Date(iso));
  }
}
