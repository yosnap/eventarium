import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  type ElementRef,
  afterNextRender,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthService, displayName } from '../../core/auth/auth.service';
import { ApiService } from '../../core/api/api.service';

/**
 * Botón de acceso de la web pública: un icono de cuenta con un desplegable.
 *
 * Con sesión activa muestra el nombre (o correo, si no tiene nombre) y un
 * desplegable de "Mi cuenta" y "Cerrar sesión"; sin sesión, "Iniciar sesión"
 * y "Crear cuenta".
 *
 * ¿Por qué importa? El access token vive **solo en memoria** (ver
 * `AuthService`): tras una recarga de página `isAuthenticated()` es `false`
 * hasta que algo renueva con la cookie `HttpOnly` que el backend dejó. Los
 * guards lo hacen al navegar a `/dashboard` o `/acceder`, pero la web pública
 * no tiene guard que lo haga, y antes de esto el menú era estático: siempre
 * decía "Iniciar sesión" aunque la sesión siguiera viva — y pulsarlo llevaba a
 * `/acceder`, donde `guestGuard` renovaba la sesión y redirigía al panel sin
 * avisar. Con esto, la cabecera pública se hidrata con la misma cookie: al
 * cargar (solo en el cliente, con `afterNextRender`) se renueva una vez, y el
 * menú muestra la cuenta desde el primer momento. El refresh compartido de
 * `AuthService` evita que dos renovaciones en paralelo (menú + guard) roten el
 * refresh token dos veces y revocaran la familia por "reutilización".
 *
 * «Cerrar sesión» no navega: al vaciar el token, el menú reacciona y pasa a
 * mostrar "Iniciar sesión" / "Crear cuenta" en el mismo sitio.
 *
 * Mismo patrón combobox accesible que `AccountMenu` (foco en el botón, opción
 * activa virtual con `aria-activedescendant`), con dos opciones fijas por
 * estado.
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
          @if (usuario()) {
            <span class="nombre">{{ etiqueta() }}</span>
            <span class="chevron" aria-hidden="true">▾</span>
          } @else {
            <svg
              viewBox="0 0 24 24"
              width="20"
              height="20"
              aria-hidden="true"
              fill="none"
            >
              <circle cx="12" cy="8" r="3.5" stroke="currentColor" stroke-width="1.6" />
              <path
                d="M4.5 19.5c1.5-3.5 4.5-5.25 7.5-5.25s6 1.75 7.5 5.25"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
              />
            </svg>
          }
        </button>

        <ul
          #menu
          id="access-menu-lista"
          role="listbox"
          [attr.aria-label]="t('publico.accesoMenu.titulo')"
          [hidden]="!abierta()"
        >
          @if (usuario()) {
            <li role="none" class="email-completo">{{ usuario()!.email }}</li>
            <li role="none">
              <a
                role="option"
                [id]="idOpcion(0)"
                [attr.aria-selected]="'false'"
                class="elemento"
                routerLink="/dashboard/account"
                (click)="abierta.set(false)"
              >
                {{ t('publico.accesoMenu.miCuenta') }}
              </a>
            </li>
            <li role="none" class="separador">
              <button
                role="option"
                type="button"
                [id]="idOpcion(1)"
                [attr.aria-selected]="'false'"
                class="elemento"
                (click)="cerrarSesion()"
              >
                {{ t('publico.accesoMenu.cerrarSesion') }}
              </button>
            </li>
          } @else {
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
          }
        </ul>
      </div>
    </ng-container>
  `,
  styles: `
    /* Puede encoger dentro de la cabecera móvil: el nombre se recorta. */
    :host {
      min-width: 0;
    }
    .selector {
      position: relative;
      min-width: 0;
      max-width: 100%;
    }
    .disparador {
      display: flex;
      align-items: center;
      gap: 8px;
      max-width: 100%;
      min-height: 2.25rem;
      padding: 0 10px;
      border: 1px solid(--border-strong);
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
    .disparador:has(svg) {
      place-items: center;
      width: 2.25rem;
      padding: 0;
    }
    .nombre {
      min-width: 0;
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
    .separador {
      border-top: 1px solid var(--border);
      margin-top: 6px;
      padding-top: 6px;
    }
  `,
})
export class AccessMenu {
  private static contador = 0;

  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);

  private readonly instancia = AccessMenu.contador++;

  protected readonly usuario = this.auth.currentUser;
  /** Nombre a mostrar en el disparador; el correo, si no tiene nombre. */
  protected readonly etiqueta = computed(() =>
    this.usuario() ? displayName(this.usuario()!) : '',
  );

  protected readonly abierta = signal(false);
  protected readonly indiceActivo = signal(0);
  private readonly menu = viewChild.required<ElementRef<HTMLUListElement>>('menu');
  // `viewChild` con cadena = nombre de referencia de plantilla (#anfitrion), no
  // selector CSS: un 'div' sin # nunca resolvería y lanzaría NG0951.
  private readonly anfitrion = viewChild.required<ElementRef<HTMLDivElement>>('anfitrion');

  constructor() {
    // Solo en el cliente y solo tras hidratar: el primer render del servidor no
    // tiene cookie que renovar y el HTML servido debe coincidir con el primer
    // render del cliente (sin sesión). En el cliente, renovar una vez: si hay
    // cookie, el token vuelve a estar y el menú pasa de "Iniciar sesión" a la
    // cuenta; si no, `refresh()` no pinta nada y se queda como estaba. El
    // refresh no devuelve el usuario (solo el token), así que tras una recarga
    // `currentUser()` queda a `null` con la sesión viva: se carga entonces con
    // `/users/me`, el mismo patrón que el panel usa al entrar.
    if (!this.api.isServer) {
      afterNextRender(() => {
        void this.auth.refresh().then(async (renovado) => {
          if (renovado && !this.auth.currentUser()) {
            await this.auth.loadCurrentUser();
          }
        });
      });
    }
  }

  protected idOpcion(indice: number): string {
    return `access-menu-${this.instancia}-opcion-${indice}`;
  }

  protected cerrarSesion(): void {
    this.abierta.set(false);
    // No navegar: al vaciarse el token, el menú muestra de nuevo "Iniciar
    // sesión" / "Crear cuenta" en el mismo sitio (misma página que ahora).
    void this.auth.logout();
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
        this.alternar();
        this.indiceActivo.set(TOTAL_OPCIONES - 1);
        return;
      }
      this.indiceActivo.update((indice) => (indice - 1) % TOTAL_OPCIONES);
    } else if (evento.key === 'Home') {
      evento.preventDefault();
      if (!this.abierta()) {
        this.alternar();
      }
      this.indiceActivo.set(0);
    } else if (evento.key === 'End') {
      evento.preventDefault();
      if (!this.abierta()) {
        this.alternar();
      }
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

/** Opciones por estado (con o sin sesión): siempre dos. */
const TOTAL_OPCIONES = 2;
