import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { ThemingService } from '../../core/theming/theming.service';
import { BrandMark } from './brand-mark';

/**
 * Logotipo de la plataforma, idéntico en todas las cabeceras (web pública, acceso y
 * panel). Si la plataforma ha subido un logotipo, se pinta tal cual; si no, el
 * lockup textual: la caja de `app-brand-mark` hace de mayúscula inicial y el resto
 * del nombre sigue en mayúsculas más pequeñas, sobre la misma línea base, de modo
 * que se lee como una sola palabra ("[E]VENTARIUM").
 *
 * Usa `--font-marca` y no `--font-display`: la plantilla de un evento redefine
 * `--font-display` en `<body>`, y el logo no debe cambiar de fuente al entrar en un
 * evento. El color sí sigue al tema (`--accent`, `currentColor`).
 */
@Component({
  selector: 'app-brand-lockup',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [BrandMark],
  template: `
    @if (theming.plataforma()?.logo_url; as logo) {
      <img [src]="logo" [alt]="nombre()" height="40" />
    } @else if (nombre()) {
      <!-- Sin nombre (branding aún sin cargar) no se pinta nada: una imagen
           accesible con la etiqueta vacía no dice nada al lector de pantalla. -->
      <span class="lockup" [attr.aria-label]="nombre()" role="img">
        <app-brand-mark [nombre]="nombre()" />
        <span class="resto" aria-hidden="true">{{ restoDelNombre() }}</span>
      </span>
    }
  `,
  styles: `
    :host {
      display: inline-flex;
    }
    img {
      display: block;
      height: 40px;
      width: auto;
    }
    .lockup {
      display: inline-flex;
      align-items: baseline;
      gap: 3px;
    }
    .resto {
      font-family: var(--font-marca);
      font-size: 1.1rem;
      line-height: 1;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }
  `,
})
export class BrandLockup {
  protected readonly theming = inject(ThemingService);

  protected readonly nombre = computed(() => this.theming.nombreDeMarca());

  /** La inicial ya va dentro de la caja: sin quitarla, se leería "[E]EVENTARIUM". */
  protected readonly restoDelNombre = computed(() => this.nombre().trim().slice(1));
}
