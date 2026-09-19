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

/**
 * Menú de cuenta como menú desplegable de primera clase: botón con el email
 * de la persona, y un panel con "Mi cuenta", "Cambiar de espacio de trabajo"
 * y "Cerrar sesión".
 *
 * Sustituye a `OrgSelector` (retirado): antes solo aparecía fuera del panel
 * de plataforma y solo dejaba elegir organización; este menú es visible en
 * `/admin` Y `/dashboard`, y "Cambiar de espacio de trabajo" abre la
 * pantalla completa del selector (organizaciones + plataforma), no un
 * desplegable inline.
 *
 * `nuevaOrganizacion`: `OrgSelector` siempre ofrecía "Nueva organización"
 * (`/crear-organizacion`) dentro de su desplegable; se conserva aquí como
 * cuarto ítem opcional para no perder esa función al retirar el componente
 * — quien monta este menú decide su visibilidad (hoy, solo fuera del panel
 * de plataforma, igual que antes).
 *
 * Mismo patrón combobox del sistema que `org-selector.ts` (y `select.ts`):
 * el foco se queda en el botón, la opción activa es virtual y se anuncia con
 * `aria-activedescendant`. Abre con Enter/Espacio o ArrowDown; flechas, Home
 * y End mueven la opción activa; Enter activa; Escape cierra; clic fuera
 * cierra.
 */
@Component({
  selector: 'app-account-menu',
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
          [attr.aria-label]="t('admin.menuCuenta.titulo')"
          [attr.aria-controls]="'account-menu-lista'"
          [attr.aria-expanded]="abierta()"
          [attr.aria-activedescendant]="abierta() ? idOpcion(indiceActivo()) : null"
          (click)="alternar()"
          (keydown)="alPulsar($event)"
        >
          <span class="email">{{ email() }}</span>
          <span class="chevron" aria-hidden="true">▾</span>
        </button>

        <ul
          #menu
          id="account-menu-lista"
          role="listbox"
          [attr.aria-label]="t('admin.menuCuenta.titulo')"
          [hidden]="!abierta()"
        >
          <li role="none" class="email-completo">{{ email() }}</li>
          <li role="none">
            <a
              role="option"
              [id]="idOpcion(0)"
              [attr.aria-selected]="'false'"
              class="elemento"
              routerLink="/dashboard/account"
              (click)="abierta.set(false)"
            >
              {{ t('admin.menuCuenta.miCuenta') }}
            </a>
          </li>
          <li role="none">
            <a
              role="option"
              [id]="idOpcion(1)"
              [attr.aria-selected]="'false'"
              class="elemento"
              routerLink="/espacio-de-trabajo"
              (click)="abierta.set(false)"
            >
              {{ t('admin.menuCuenta.cambiarEspacio') }}
            </a>
          </li>
          @if (nuevaOrganizacion()) {
            <li role="none">
              <a
                role="option"
                [id]="idOpcion(2)"
                [attr.aria-selected]="'false'"
                class="elemento"
                routerLink="/crear-organizacion"
                (click)="abierta.set(false)"
              >
                {{ t('admin.menuCuenta.nuevaOrganizacion') }}
              </a>
            </li>
          }
          <li role="none" class="separador">
            <button
              role="option"
              type="button"
              [id]="idOpcion(totalOpciones() - 1)"
              [attr.aria-selected]="'false'"
              class="elemento"
              (click)="alCerrarSesion()"
            >
              {{ t('admin.cerrarSesion') }}
            </button>
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
    .email {
      max-width: 12rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
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
    .email-completo {
      padding: 8px 10px;
      font-size: var(--fs-sm);
      color: var(--muted);
      word-break: break-all;
      border-bottom: 1px solid var(--border);
      margin-bottom: 6px;
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
    .separador {
      border-top: 1px solid var(--border);
      margin-top: 6px;
      padding-top: 6px;
    }
  `,
})
export class AccountMenu {
  private static contador = 0;

  readonly email = input.required<string>();
  readonly nuevaOrganizacion = input(false);
  readonly cerrarSesion = output<void>();

  private readonly instancia = AccountMenu.contador++;
  /** "Mi cuenta" + "Cambiar de espacio" + "Cerrar sesión", más "Nueva
   * organización" cuando `nuevaOrganizacion()` es `true`. */
  protected readonly totalOpciones = computed(() => (this.nuevaOrganizacion() ? 4 : 3));

  protected readonly abierta = signal(false);
  protected readonly indiceActivo = signal(0);
  private readonly menu = viewChild.required<ElementRef<HTMLUListElement>>('menu');
  private readonly anfitrion = viewChild.required<ElementRef<HTMLDivElement>>('anfitrion');

  protected idOpcion(indice: number): string {
    return `account-menu-${this.instancia}-opcion-${indice}`;
  }

  protected alCerrarSesion(): void {
    this.abierta.set(false);
    this.cerrarSesion.emit();
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
    this.indiceActivo.set(0);
    this.abierta.set(true);
  }

  protected alPulsar(evento: KeyboardEvent): void {
    const total = this.totalOpciones();
    if (evento.key === 'Escape') {
      evento.preventDefault();
      this.cerrar();
      return;
    }
    if (evento.key === 'Tab') {
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
    const opciones = this.menu().nativeElement.querySelectorAll('[role="option"]');
    const elemento = opciones[indice] as HTMLElement | null;
    elemento?.click();
  }
}
