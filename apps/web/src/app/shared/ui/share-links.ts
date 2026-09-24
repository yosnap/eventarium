import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { ICONOS_REDES } from './share-links-iconos';

interface Red {
  readonly id: keyof typeof ICONOS_REDES;
  readonly nombre: string;
  readonly href: string;
}

/**
 * Enlaces para compartir una página en redes y por correo. Son enlaces
 * normales a las URL de compartir de cada red (sin SDK ni scripts de
 * terceros, así que no cargan nada ni ponen cookies hasta que se pulsan).
 * La vista previa que enseña cada red sale de las etiquetas OG de la página.
 */
@Component({
  selector: 'app-share-links',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t; read: 'publico.compartir'">
      <div class="compartir" role="group" [attr.aria-label]="t('titulo')">
        <span class="compartir__rotulo">{{ t('titulo') }}</span>
        <ul class="compartir__lista">
          @for (red of redes(); track red.id) {
            <li>
              <a
                class="compartir__boton"
                [href]="red.href"
                target="_blank"
                rel="noopener noreferrer"
                [attr.aria-label]="t('en', { red: red.nombre })"
                [attr.title]="red.nombre"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                  <path [attr.d]="iconos[red.id]" fill="currentColor" />
                </svg>
              </a>
            </li>
          }
          <li>
            <a
              class="compartir__boton"
              [href]="enlaceCorreo()"
              [attr.aria-label]="t('correo')"
              [attr.title]="t('correo')"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none">
                <rect
                  x="3"
                  y="5"
                  width="18"
                  height="14"
                  rx="2"
                  stroke="currentColor"
                  stroke-width="1.6"
                />
                <path
                  d="m3.5 6.5 8.5 6.5 8.5-6.5"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linejoin="round"
                />
              </svg>
            </a>
          </li>
          <li>
            <button
              type="button"
              class="compartir__boton"
              [attr.aria-label]="t('copiar')"
              [attr.title]="t('copiar')"
              (click)="copiar()"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none">
                <path
                  d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linecap="round"
                />
              </svg>
            </button>
          </li>
        </ul>
        <span class="compartir__aviso" aria-live="polite">
          @if (copiado()) {
            {{ t('copiado') }}
          }
        </span>
      </div>
    </ng-container>
  `,
  styles: `
    .compartir {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--sp-3);
    }
    .compartir__rotulo {
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .compartir__lista {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-2);
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .compartir__boton {
      display: inline-grid;
      place-items: center;
      /* 44 px: objetivo táctil mínimo. */
      width: 44px;
      height: 44px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background: var(--surface);
      color: var(--fg);
      cursor: pointer;
      transition:
        color 0.15s,
        border-color 0.15s;
    }
    .compartir__boton:hover,
    .compartir__boton:focus-visible {
      color: var(--accent);
      border-color: var(--accent);
    }
    .compartir__aviso {
      font-size: var(--fs-sm);
      color: var(--accent);
    }
  `,
})
export class ShareLinks {
  /** URL absoluta de la página que se comparte. */
  readonly url = input.required<string>();
  readonly titulo = input.required<string>();

  protected readonly iconos = ICONOS_REDES;
  protected readonly copiado = signal(false);

  protected readonly redes = computed<Red[]>(() => {
    const url = encodeURIComponent(this.url());
    const titulo = encodeURIComponent(this.titulo());
    const tituloYUrl = encodeURIComponent(`${this.titulo()} ${this.url()}`);
    return [
      { id: 'x', nombre: 'X', href: `https://x.com/intent/post?text=${titulo}&url=${url}` },
      {
        id: 'linkedin',
        nombre: 'LinkedIn',
        href: `https://www.linkedin.com/sharing/share-offsite/?url=${url}`,
      },
      {
        id: 'facebook',
        nombre: 'Facebook',
        href: `https://www.facebook.com/sharer/sharer.php?u=${url}`,
      },
      { id: 'whatsapp', nombre: 'WhatsApp', href: `https://wa.me/?text=${tituloYUrl}` },
      {
        id: 'telegram',
        nombre: 'Telegram',
        href: `https://t.me/share/url?url=${url}&text=${titulo}`,
      },
      {
        id: 'bluesky',
        nombre: 'Bluesky',
        href: `https://bsky.app/intent/compose?text=${tituloYUrl}`,
      },
    ];
  });

  protected readonly enlaceCorreo = computed(
    () =>
      `mailto:?subject=${encodeURIComponent(this.titulo())}&body=${encodeURIComponent(this.url())}`,
  );

  protected async copiar(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.url());
      this.copiado.set(true);
      setTimeout(() => this.copiado.set(false), 2500);
    } catch {
      // Sin permiso de portapapeles (contexto no seguro): el resto de opciones
      // sigue sirviendo, así que no se muestra error.
    }
  }
}
