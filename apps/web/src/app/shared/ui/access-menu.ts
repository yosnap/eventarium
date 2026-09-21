import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  type ElementRef,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

const TOTAL_OPCIONES = 2;

/**
 * Botón de acceso de la web pública: un icono de cuenta en vez de dos
 * enlaces de texto sueltos ("Acceso al panel" / "Crear cuenta"), con un
 * desplegable de "Iniciar sesión" y "Crear cuenta". Mismo patrón combobox
 * accesible que `AccountMenu` (foco en el botón, opción activa virtual con
 * `aria-activedescendant`), simplificado: sin email, solo dos opciones fijas.
 */
@Component({
  selector: 'app-access-menu',
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
          [attr.aria-label]="t('publico.accesoMenu.titulo')"
          [attr.aria-controls]="'access-menu-lista'"
          [attr.aria-expanded]="abierta()"
          [attr.aria-activedescendant]="abierta() ? idOpcion(indiceActivo()) : null"
          (click)="alternar()"
          (keydown)="alPulsar($event)"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none">
            <circle cx="12" cy="8" r="3.5" stroke="currentColor" stroke-width="1.6" />
            <path
              d="M4.5 19.5c1.5-3.5 4.5-5.25 7.5-5.25s6 1.75 7.5 5.25"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
          </svg>
        </button>

        <ul
          #menu
          id="access-menu-lista"
          role="listbox"
          [attr.aria-label]="t('publico.accesoMenu.titulo')"
          [hidden]="!abierta()"
        >
          <li role="none">
            <a
              role="option"
              [id]="idOpcion(0)"
              [attr.aria-selected]="'false'"
              class="elemento"
              routerLink="/acceder"
              (click)="abierta.set(false)"
            >
              {{ t('publico.accesoMenu.iniciarSesion') }}
            </a>
          </li>
          <li role="none">
            <a
              role="option"
              [id]="idOpcion(1)"
              [attr.aria-selected]="'false'"
              class="elemento"
              routerLink="/registro"
              (click)="abierta.set(false)"
            >
              {{ t('publico.accesoMenu.crearCuenta') }}
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
      display: grid;
      place-items: center;
      width: 2.25rem;
      height: 2.25rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background-color: var(--bg);
      color: var(--fg);
      cursor: pointer;
    }
    .disparador:hover {
      background-color: var(--surface-hi);
    }
    ul {
      position: absolute;
      right: 0;
      top: calc(100% + 6px);
      min-width: 12rem;
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
    .elemento:hover {
      background-color: var(--surface-hi);
    }
  `,
})
export class AccessMenu {
  private static contador = 0;

  private readonly instancia = AccessMenu.contador++;

  protected readonly abierta = signal(false);
  protected readonly indiceActivo = signal(0);
  private readonly menu = viewChild.required<ElementRef<HTMLUListElement>>('menu');
  private readonly anfitrion = viewChild.required<ElementRef<HTMLDivElement>>('anfitrion');

  protected idOpcion(indice: number): string {
    return `access-menu-${this.instancia}-opcion-${indice}`;
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
      this.indiceActivo.update((indice) => (indice + 1) % TOTAL_OPCIONES);
    } else if (evento.key === 'ArrowUp') {
      evento.preventDefault();
      if (!this.abierta()) {
        this.abierta.set(true);
        this.indiceActivo.set(TOTAL_OPCIONES - 1);
        return;
      }
      this.indiceActivo.update((indice) => (indice - 1 + TOTAL_OPCIONES) % TOTAL_OPCIONES);
    } else if (evento.key === 'Home') {
      evento.preventDefault();
      this.abierta.set(true);
      this.indiceActivo.set(0);
    } else if (evento.key === 'End') {
      evento.preventDefault();
      this.abierta.set(true);
      this.indiceActivo.set(TOTAL_OPCIONES - 1);
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
