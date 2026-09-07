import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  afterNextRender,
  output,
  viewChild,
} from '@angular/core';

import { environment } from '../../../environments/environment';

declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: Record<string, unknown>) => string;
      remove: (widgetId: string) => void;
    };
  }
}

let cargaScript: Promise<void> | null = null;

function cargarTurnstile(): Promise<void> {
  cargaScript ??= new Promise((resolve, reject) => {
    if (window.turnstile) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('No se pudo cargar Turnstile.'));
    document.head.appendChild(script);
  });
  return cargaScript;
}

/**
 * Widget de Cloudflare Turnstile, compartido por registro, reenvío de verificación y
 * (fases posteriores) recuperación de contraseña.
 *
 * Es un iframe de terceros que axe no audita: se ha comprobado manualmente con lector
 * de pantalla y teclado (ver `docs/accesibilidad.md`). Cuando Turnstile está
 * desactivado —solo fuera de producción— no se renderiza y se emite un token vacío,
 * que la API ignora mientras `TURNSTILE_ENABLED=false`.
 */
@Component({
  selector: 'app-turnstile-widget',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (activo) {
      <div #contenedor></div>
    }
  `,
})
export class TurnstileWidget implements OnDestroy {
  readonly resuelto = output<string>();

  protected readonly activo = environment.turnstileEnabled;
  private readonly contenedor = viewChild<ElementRef<HTMLElement>>('contenedor');
  private widgetId: string | null = null;

  constructor() {
    if (!this.activo) {
      queueMicrotask(() => this.resuelto.emit(''));
      return;
    }
    afterNextRender(() => {
      void this.renderizar();
    });
  }

  private async renderizar(): Promise<void> {
    const elemento = this.contenedor()?.nativeElement;
    if (!elemento) {
      return;
    }
    await cargarTurnstile();
    this.widgetId =
      window.turnstile?.render(elemento, {
        sitekey: environment.turnstileSiteKey,
        callback: (token: string) => this.resuelto.emit(token),
      }) ?? null;
  }

  ngOnDestroy(): void {
    if (this.widgetId && window.turnstile) {
      window.turnstile.remove(this.widgetId);
    }
  }
}
