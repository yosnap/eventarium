import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import {
  contenidoIcs,
  nombreFicheroIcs,
  urlGoogleCalendar,
  urlOutlook,
  type EventoParaCalendario,
} from '../calendar/calendar-links';
import { urlEvento } from '../../core/routing/rutas-publicas';

/** Milisegundos que se espera antes de liberar el objeto del `.ics`: Safari
 * necesita que el enlace siga vivo un instante después del clic. */
const LIBERAR_ICS_TRAS_MS = 1_000;

/**
 * «Añade el evento a tu calendario»: Google Calendar y Outlook abren su
 * pantalla de nuevo evento ya rellena; Apple Calendar (y cualquier otra
 * aplicación) recibe un archivo `.ics`.
 *
 * Solo debe pintarse con la plaza confirmada: el backend ya entrega el evento
 * únicamente en ese caso, así que quien usa el componente decide con un simple
 * `@if (evento(); as e)`. Sin JavaScript de terceros ni cuentas de por medio —
 * todo son enlaces y un archivo generado en el navegador.
 */
@Component({
  selector: 'app-add-to-calendar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <section class="calendario" *transloco="let t" [attr.aria-labelledby]="idTitulo">
      <h2 class="calendario__titulo" [id]="idTitulo">{{ t('calendario.titulo') }}</h2>
      <div class="calendario__opciones">
        <a
          class="opcion"
          [href]="enlaceGoogle()"
          target="_blank"
          rel="noopener noreferrer"
          [attr.aria-label]="t('calendario.google') + ' ' + t('calendario.nuevaPestana')"
        >
          {{ t('calendario.google') }}
        </a>
        <a
          class="opcion"
          [href]="enlaceOutlook()"
          target="_blank"
          rel="noopener noreferrer"
          [attr.aria-label]="t('calendario.outlook') + ' ' + t('calendario.nuevaPestana')"
        >
          {{ t('calendario.outlook') }}
        </a>
        <button
          type="button"
          class="opcion"
          [attr.aria-label]="t('calendario.apple') + ' ' + t('calendario.descargaIcs')"
          (click)="descargarIcs()"
        >
          {{ t('calendario.apple') }}
        </button>
      </div>
    </section>
  `,
  styles: `
    :host {
      display: block;
    }
    .calendario {
      display: grid;
      gap: var(--space-sm);
      margin-top: var(--space-md);
      padding-top: var(--space-md);
      border-top: 1px dashed var(--border-strong);
      text-align: center;
    }
    .calendario__titulo {
      margin: 0;
      font-size: var(--fs-sm);
      font-weight: 600;
      color: var(--muted);
    }
    .calendario__opciones {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: var(--space-xs);
    }
    /* Mismas medidas que los botones secundarios del panel: 2.75rem de alto
       cumple el tamaño mínimo de objetivo táctil. */
    .opcion {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 2.75rem;
      padding: 0 1rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: none;
      color: var(--fg);
      font: inherit;
      text-decoration: none;
      cursor: pointer;
      transition:
        background-color 0.15s,
        border-color 0.15s;
    }
    .opcion:hover {
      background: var(--surface-hi);
      border-color: var(--faint);
    }
    .opcion:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }
  `,
})
export class AddToCalendar {
  readonly evento = input.required<EventoParaCalendario>();

  private readonly documento = inject(DOCUMENT);
  private static contador = 0;
  protected readonly idTitulo = `calendario-titulo-${AddToCalendar.contador++}`;

  /** Ficha pública del evento. Vacío el origen en servidor: solo importa en el
   * navegador, donde las URL se abren; el enlace resultante nunca se usa en SSR. */
  private readonly urlEvento = computed(
    () =>
      `${this.documento.defaultView?.location.origin ?? ''}${urlEvento(this.evento().organization.slug, this.evento().slug)}`,
  );

  protected readonly enlaceGoogle = computed(() =>
    urlGoogleCalendar(this.evento(), this.urlEvento()),
  );
  protected readonly enlaceOutlook = computed(() => urlOutlook(this.evento(), this.urlEvento()));

  protected descargarIcs(): void {
    const evento = this.evento();
    const contenido = contenidoIcs(evento, this.urlEvento());
    const url = URL.createObjectURL(new Blob([contenido], { type: 'text/calendar;charset=utf-8' }));
    const enlace = this.documento.createElement('a');
    enlace.href = url;
    enlace.download = nombreFicheroIcs(evento);
    this.documento.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), LIBERAR_ICS_TRAS_MS);
  }
}
