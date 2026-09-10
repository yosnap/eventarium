import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterNextRender,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { CookieConsentService } from '../../core/cookies/cookie-consent.service';
import { Button } from '../ui/button';
import { Toggle } from '../ui/toggle';

/**
 * Banner de cookies + ventana de personalización, sobre `assets/cookies.js` y
 * `.cookies`/`.cookie-cat`/`.sw-*` de `assets/eventarium.css` (líneas
 * 278-312) del proyecto de referencia real: isla flotante centrada y
 * anclada abajo (no pegada a los bordes), nunca un muro modal — la página
 * sigue siendo legible y navegable mientras el banner está visible. Solo
 * la ventana de personalización es un `<dialog>` modal de verdad.
 *
 * Las dos decisiones directas ("Solo las necesarias" / "Aceptar todas")
 * comparten variante de botón (`secundario`) y tamaño — rechazar cuesta
 * exactamente lo mismo que aceptar. "Elegir" es un tercer control con menos
 * peso (`terciario` compacto), no una tercera opción con la misma caja.
 *
 * Gestión de foco del banner (WCAG 2.4.3): al aparecer, el foco se mueve al
 * primer control; al decidir, vuelve al elemento que tenía el foco antes de
 * que apareciera. Sin trampa de foco en el banner — solo la ventana modal
 * la tiene, y la da gratis el propio `<dialog>` con `showModal()`.
 */
@Component({
  selector: 'app-cookie-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, Toggle],
  template: `
    <ng-container *transloco="let t">
      @if (consentimiento.mostrarBanner() && !personalizando()) {
        <div
          #panel
          class="cookies"
          role="region"
          [attr.aria-label]="t('cookies.banner.titulo')"
          tabindex="-1"
        >
          <p class="cookies__t">
            <strong>{{ t('cookies.banner.textoDestacado') }}</strong>
            {{ t('cookies.banner.texto') }}
          </p>
          <div class="cookies__acts">
            <app-button variant="secundario" (pulsado)="rechazarTodo()">
              {{ t('cookies.banner.rechazarTodo') }}
            </app-button>
            <app-button variant="secundario" (pulsado)="aceptarTodo()">
              {{ t('cookies.banner.aceptarTodo') }}
            </app-button>
            <app-button variant="terciario" [compacto]="true" (pulsado)="abrirPersonalizacion()">
              {{ t('cookies.banner.personalizar') }}
            </app-button>
          </div>
        </div>
      }

      <dialog #ventana (cancel)="cancelar()">
        @if (personalizando()) {
          <div class="dlg__b">
            <p class="label">{{ t('cookies.banner.titulo') }}</p>
            <h3>{{ t('cookies.ventana.titulo') }}</h3>
            <p class="hint">{{ t('cookies.ventana.intro') }}</p>

            <app-toggle
              [label]="t('cookies.banner.necesarias')"
              [estado]="t('cookies.ventana.estadoSiempre')"
              [hint]="t('cookies.ventana.necesariasDetalle')"
              [checked]="true"
              [disabled]="true"
            />
            <app-toggle
              [label]="t('cookies.banner.analiticas')"
              [estado]="analiticas() ? t('cookies.ventana.estadoSi') : t('cookies.ventana.estadoNo')"
              [hint]="t('cookies.ventana.analiticasDetalle')"
              [(checked)]="analiticas"
            />
            <app-toggle
              [label]="t('cookies.banner.marketing')"
              [estado]="marketing() ? t('cookies.ventana.estadoSi') : t('cookies.ventana.estadoNo')"
              [hint]="t('cookies.ventana.marketingDetalle')"
              [(checked)]="marketing"
            />
          </div>
          <div class="dlg__f">
            <app-button variant="terciario" (pulsado)="cancelar()">
              {{ t('comun.cancelar') }}
            </app-button>
            <app-button variant="secundario" (pulsado)="guardarPersonalizacion()">
              {{ t('cookies.ventana.guardar') }}
            </app-button>
          </div>
        }
      </dialog>
    </ng-container>
  `,
  styles: `
    /* .cookies (eventarium.css:278-296): isla flotante centrada y anclada
       abajo, con radio y sombra — no una barra a sangre completa. */
    .cookies {
      position: fixed;
      z-index: 80;
      left: 50%;
      transform: translateX(-50%);
      bottom: var(--sp-4);
      width: min(100% - 32px, var(--max));
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: var(--sp-5);
      align-items: center;
      padding: var(--sp-5);
      background-color: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-lg);
    }
    .cookies:focus {
      outline: none;
    }
    .cookies__t {
      margin: 0;
      font-size: var(--fs-sm);
      line-height: 1.55;
      max-width: 74ch;
    }
    .cookies__t strong {
      font-weight: 500;
    }
    .cookies__acts {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-3);
      align-items: center;
    }
    @media (max-width: 760px) {
      .cookies {
        grid-template-columns: 1fr;
        gap: var(--sp-4);
      }
    }

    /* dialog (panel-ponentes.html:47-50 de la referencia). */
    dialog {
      margin: auto;
      padding: 0;
      max-width: 32.5rem;
      width: calc(100% - 40px);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      color: var(--fg);
    }
    dialog::backdrop {
      background-color: var(--backdrop);
    }
    .dlg__b {
      padding: var(--sp-5);
    }
    .dlg__b .label {
      margin: 0;
    }
    .dlg__b h3 {
      margin: 10px 0 6px;
    }
    .dlg__b > .hint {
      margin: 0 0 var(--sp-3);
    }
    .hint {
      color: var(--muted);
    }
    app-toggle {
      display: block;
      padding: var(--sp-4) 0;
      border-bottom: 1px solid var(--border);
    }
    app-toggle:last-of-type {
      border-bottom: none;
    }
    .dlg__f {
      display: flex;
      gap: var(--sp-3);
      justify-content: flex-end;
      padding: var(--sp-4) var(--sp-5);
      border-top: 1px solid var(--border);
    }
  `,
})
export class CookieBanner {
  protected readonly consentimiento = inject(CookieConsentService);

  protected readonly personalizando = signal(false);
  protected readonly analiticas = signal(false);
  protected readonly marketing = signal(false);

  private readonly panel = viewChild<ElementRef<HTMLElement>>('panel');
  private readonly ventana = viewChild<ElementRef<HTMLDialogElement>>('ventana');
  private elementoConFocoPrevio: HTMLElement | null = null;

  constructor() {
    afterNextRender(() => {
      if (this.consentimiento.mostrarBanner()) {
        this.moverFocoAlBanner();
      }
    });

    // Reabierto desde "Preferencias de cookies" (pie de página): precarga
    // las categorías ya elegidas, no un estado vacío como si fuera la
    // primera visita, y abre directamente la ventana de personalización.
    effect(() => {
      if (!this.consentimiento.gestionAbierta()) {
        return;
      }
      const activas = this.consentimiento.categorias();
      this.analiticas.set(activas.has('analytics'));
      this.marketing.set(activas.has('marketing'));
      this.abrirPersonalizacion();
    });
  }

  /** `showModal()` puede faltar (jsdom en pruebas, un navegador muy antiguo):
   * en ese caso se degrada a marcar/quitar el atributo `open` a mano, sin
   * trampa de foco ni `::backdrop` — el contenido sigue siendo alcanzable.
   * Se decide un único modo por diálogo (nunca se mezcla `showModal()` con
   * `removeAttribute()`, que en jsdom deja `open` desincronizado). */
  private abrirDialogo(dialogo: HTMLDialogElement): void {
    if (typeof dialogo.showModal === 'function') {
      dialogo.showModal();
    } else {
      dialogo.setAttribute('open', '');
    }
  }

  private cerrarDialogo(dialogo: HTMLDialogElement): void {
    if (typeof dialogo.showModal === 'function') {
      dialogo.close();
    } else {
      dialogo.removeAttribute('open');
    }
  }

  private moverFocoAlBanner(): void {
    this.elementoConFocoPrevio = document.activeElement as HTMLElement | null;
    this.panel()?.nativeElement.focus();
  }

  private devolverFoco(): void {
    this.elementoConFocoPrevio?.focus();
    this.elementoConFocoPrevio = null;
  }

  protected abrirPersonalizacion(): void {
    if (!this.consentimiento.gestionAbierta()) {
      this.elementoConFocoPrevio ??= document.activeElement as HTMLElement | null;
    }
    this.personalizando.set(true);
    const dialogo = this.ventana()?.nativeElement;
    if (dialogo && !dialogo.hasAttribute('open')) {
      this.abrirDialogo(dialogo);
    }
  }

  protected async aceptarTodo(): Promise<void> {
    await this.consentimiento.aceptarTodo();
    this.devolverFoco();
  }

  protected async rechazarTodo(): Promise<void> {
    await this.consentimiento.rechazarTodo();
    this.devolverFoco();
  }

  protected async guardarPersonalizacion(): Promise<void> {
    const categorias: ('analytics' | 'marketing')[] = [];
    if (this.analiticas()) categorias.push('analytics');
    if (this.marketing()) categorias.push('marketing');
    await this.consentimiento.personalizar(categorias);
    this.cerrarVentana();
  }

  /** "Cancelar" (botón o tecla Esc): si se llegó aquí desde "Preferencias de
   * cookies" (ya había una decisión previa), cierra sin cambiar nada; si es
   * la primera visita, vuelve al banner con las tres opciones iniciales. */
  protected cancelar(): void {
    if (this.consentimiento.gestionAbierta()) {
      this.consentimiento.cerrarGestionDeCookies();
    }
    this.cerrarVentana();
  }

  private cerrarVentana(): void {
    this.personalizando.set(false);
    const dialogo = this.ventana()?.nativeElement;
    if (dialogo && dialogo.hasAttribute('open')) {
      this.cerrarDialogo(dialogo);
    }
    this.devolverFoco();
  }
}
