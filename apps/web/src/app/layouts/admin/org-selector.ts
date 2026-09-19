import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  type ElementRef,
  computed,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { monograma } from '../../shared/text/monograma';

/**
 * Selector de organizaciones como menú desplegable de primera clase: botón
 * con el monograma y el nombre de la organización activa, y un panel con
 * todas las organizaciones (la activa marcada) y la acción de dar de alta
 * una nueva.
 *
 * Patrón combobox del sistema (el mismo que `select.ts`): el foco se queda
 * en el botón y la opción activa es virtual, anunciada con
 * `aria-activedescendant` — nada de perseguir el foco DOM por las opciones.
 * Abre con Enter/Espacio o ArrowDown; flechas, Home y End mueven la opción
 * activa; Enter activa; Escape cierra. La organización activa se anuncia
 * con `aria-selected`; cambiar a la que ya está activa no existe aquí.
 */
@Component({
  selector: 'app-org-selector',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      <div #anfitrion class="selector">
        <button
          #disparador
          type="button"
          class="disparador"
          role="combobox"
          aria-haspopup="listbox"
          [attr.aria-label]="t('admin.selectorOrganizacion.titulo')"
          [attr.aria-controls]="'org-selector-lista'"
          [attr.aria-expanded]="abierta()"
          [attr.aria-activedescendant]="abierta() ? idOpcion(indiceActivo()) : null"
          [disabled]="cambiando()"
          (click)="alternar()"
          (keydown)="alPulsar($event)"
        >
          @if (activa(); as org) {
            <span class="monograma" aria-hidden="true">{{
              monograma(org.name, null, org.name)
            }}</span>
          }
          <span class="nombre">{{ activa()?.name }}</span>
          <span class="chevron" aria-hidden="true">▾</span>
        </button>

        <ul
          #menu
          id="org-selector-lista"
          role="listbox"
          [attr.aria-label]="t('admin.selectorOrganizacion.titulo')"
          [hidden]="!abierta()"
        >
          @for (organizacion of organizaciones(); track organizacion.organization_id) {
            <li role="none">
              @if (esActiva(organizacion)) {
                <span
                  role="option"
                  [id]="idOpcion($index)"
                  [attr.aria-selected]="'true'"
                  class="elemento activa"
                >
                  <span class="monograma" aria-hidden="true">{{
                    monograma(organizacion.name, null, organizacion.name)
                  }}</span>
                  <span>{{ organizacion.name }}</span>
                  <span class="check" aria-hidden="true">✓</span>
                </span>
              } @else {
                <button
                  role="option"
                  type="button"
                  [id]="idOpcion($index)"
                  [attr.aria-selected]="'false'"
                  class="elemento"
                  [disabled]="cambiando()"
                  (click)="cambiar.emit(organizacion.organization_id)"
                >
                  <span class="monograma" aria-hidden="true">{{
                    monograma(organizacion.name, null, organizacion.name)
                  }}</span>
                  <span>{{ organizacion.name }}</span>
                </button>
              }
            </li>
          }
          <li role="none" class="separador">
            <a
              role="option"
              [id]="idOpcion(organizaciones().length)"
              [attr.aria-selected]="'false'"
              class="elemento nueva"
              routerLink="/crear-organizacion"
              (click)="abierta.set(false)"
            >
              {{ t('admin.selectorOrganizacion.nueva') }}
            </a>
          </li>
        </ul>
      </div>
    </ng-container>
  `,
  styles: `
    .selector {
      position: relative;
    }
    .disparador {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 2.25rem;
      padding: 0 10px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--bg);
      color: var(--fg);
      font: inherit;
      font-size: var(--fs-sm);
      cursor: pointer;
    }
    .disparador:hover {
      background-color: var(--surface-hi);
    }
    .disparador:disabled {
      cursor: wait;
      opacity: 0.6;
    }
    .nombre {
      max-width: 12rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .monograma {
      width: 24px;
      height: 24px;
      flex: 0 0 auto;
      display: grid;
      place-items: center;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--surface-2);
      font-family: var(--font-display);
      font-size: 0.75rem;
      color: var(--muted);
    }
    .chevron {
      color: var(--muted);
    }
    ul {
      position: absolute;
      right: 0;
      top: calc(100% + 6px);
      min-width: 14rem;
      margin: 0;
      padding: 6px;
      list-style: none;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      box-shadow: 0 12px 28px rgb(0 0 0 / 0.18);
      z-index: 50;
    }
    .elemento {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 8px 10px;
      border: 0;
      background: none;
      border-radius: var(--radius-sm);
      color: var(--fg);
      text-decoration: none;
      font: inherit;
      font-size: var(--fs-sm);
      text-align: left;
      cursor: pointer;
    }
    a.elemento:hover,
    button.elemento:hover {
      background-color: var(--surface-hi);
    }
    .activa {
      color: var(--fg);
      background-color: var(--surface-hi);
    }
    .activa .check {
      margin-left: auto;
      color: var(--accent);
    }
    .separador {
      border-top: 1px solid var(--border);
      margin-top: 6px;
      padding-top: 6px;
    }
  `,
})
export class OrgSelector {
  private static contador = 0;

  readonly organizaciones = input.required<readonly { organization_id: string; name: string }[]>();
  readonly activaId = input<string | null>(null);
  readonly cambiando = input(false);

  readonly cambiar = output<string>();

  private readonly instancia = OrgSelector.contador++;

  protected readonly monograma = monograma;
  protected readonly abierta = signal(false);
  protected readonly indiceActivo = signal(0);
  private readonly menu = viewChild.required<ElementRef<HTMLUListElement>>('menu');
  private readonly anfitrion = viewChild.required<ElementRef<HTMLDivElement>>('anfitrion');

  protected readonly activa = computed(
    () => this.organizaciones().find((o) => o.organization_id === this.activaId()) ?? null,
  );

  protected idOpcion(indice: number): string {
    return `org-selector-${this.instancia}-opcion-${indice}`;
  }

  protected esActiva(organizacion: { organization_id: string }): boolean {
    return organizacion.organization_id === this.activaId();
  }

  @HostListener('document:click', ['$event'])
  protected alClicarFuera(evento: MouseEvent): void {
    if (!this.abierta()) return;
    const objetivo = evento.target as HTMLElement;
    if (objetivo instanceof Node && this.anfitrion().nativeElement.contains(objetivo)) return;
    this.abierta.set(false);
  }

  protected alternar(): void {
    if (this.abierta()) {
      this.cerrar();
      return;
    }
    // Al abrir, la opción activa es la primera (el botón es el anfitrión del
    // foco; el índice solo elige qué opción anunciar y activar).
    this.indiceActivo.set(0);
    this.abierta.set(true);
  }

  protected alPulsar(evento: KeyboardEvent): void {
    const total = this.totalDeOpciones();
    if (evento.key === 'Escape') {
      evento.preventDefault();
      this.cerrar();
      return;
    }
    if (evento.key === 'Tab') {
      // El menú no retiene el foco: se cierra y la tabulación continúa.
      this.cerrar();
      return;
    }
    if (evento.key === 'ArrowDown') {
      evento.preventDefault();
      if (!this.abierta()) {
        this.alternar();
        return;
      }
      this.indiceActivo.update((indice) => (indice + 1) % total);
    } else if (evento.key === 'ArrowUp') {
      evento.preventDefault();
      if (!this.abierta()) {
        this.abierta.set(true);
        this.indiceActivo.set(total - 1);
        return;
      }
      this.indiceActivo.update((indice) => (indice - 1 + total) % total);
    } else if (evento.key === 'Home') {
      evento.preventDefault();
      this.abierta.set(true);
      this.indiceActivo.set(0);
    } else if (evento.key === 'End') {
      evento.preventDefault();
      this.abierta.set(true);
      this.indiceActivo.set(total - 1);
    } else if (evento.key === 'Enter' || evento.key === ' ') {
      if (!this.abierta()) {
        evento.preventDefault();
        this.alternar();
        return;
      }
      evento.preventDefault();
      this.activarIndice(this.indiceActivo());
    }
  }

  private cerrar(): void {
    this.abierta.set(false);
  }

  private activarIndice(indice: number): void {
    if (indice === this.totalDeOpciones() - 1) {
      // La última opción es «Nueva organización», que navega por routerLink:
      // su click se dispara aquí para que el botón anfitrión maneje todo.
      this.menu().nativeElement.querySelector<HTMLAnchorElement>('.nueva')?.click();
      return;
    }
    // El índice recorre las opciones en orden; el elemento que toca puede ser
    // el span de la activa (sin acción) o un botón de cambio.
    const opciones = this.menu().nativeElement.querySelectorAll('[role="option"]');
    const elemento = opciones[indice] as HTMLElement | null;
    if (elemento instanceof HTMLButtonElement) {
      elemento.click();
    }
  }

  private totalDeOpciones(): number {
    // Una opción por organización, más «Nueva organización» al pie.
    return this.organizaciones().length + 1;
  }
}
