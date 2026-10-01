import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  input,
  output,
  viewChild,
} from '@angular/core';

/**
 * Diálogo modal sobre `<dialog>` nativo.
 *
 * Extracción del uso de facto que vivía en `event-payments.ts` (mismos estilos
 * locales, ahora al patrón `.dlg__body`/`.dlg__foot` del prototipo). El nativo
 * ya da lo difícil: foco atrapado dentro, cierre con Escape, `::backdrop` y, por
 * spec, devolución del foco al abrirlo. La restauración manual es un cinturón
 * de seguridad determinista (jsdom y navegadores con bugs de foco lo agradecen),
 * no una corrección del nativo. El `(close)` nativo, con una bandera de dedup,
 * cubre también cierres que no pasen por `cerrar()` (p. ej. un futuro
 * `form method="dialog"` en el cuerpo).
 *
 * Quien lo usa proyecta el cuerpo y, si quiere pie con acciones, la ranura
 * `[pie]` (borde superior, acciones a la derecha, como `.dlg__foot`).
 */
@Component({
  selector: 'app-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- Clic en el fondo: conveniencia de puntero sobre el propio <dialog> (el
         destino del clic nunca es un hijo). La vía de teclado es Escape, que el
         nativo ya gestiona con el evento cancel: no hay equivalente keyup que
         tenga sentido sobre el fondo, de ahí las dos excepciones documentadas. -->
    <!-- eslint-disable-next-line @angular-eslint/template/click-events-have-key-events, @angular-eslint/template/interactive-supports-focus -->
    <dialog
      #elemento
      [class.ancho]="tamano() === 'ancho'"
      (cancel)="cerrar()"
      (close)="procesarCierre()"
      (click)="alClic($event)"
    >
      <div class="cuerpo">
        <ng-content />
      </div>
      <div class="pie">
        <ng-content select="[pie]" />
      </div>
    </dialog>
  `,
  styles: `
    dialog {
      /* El preflight de Tailwind resetea margin:0 en todos los elementos,
         incluido dialog — sin restaurarlo, un dialog abierto con showModal()
         pierde el margin:auto de su hoja de estilos nativa
         (dialog:modal { position: fixed; inset: 0; margin: auto }) y queda
         pegado a la esquina superior izquierda en vez de centrado. */
      margin: auto;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface);
      color: var(--fg);
      padding: 0;
      max-width: 28.75rem;
      width: calc(100% - 40px);
      /* Sin tope de alto, un diálogo más alto que la vista (el caso móvil)
         queda centrado con «margin:auto» y lo que asoma por arriba y por
         abajo vive fuera de la top-layer, inalcanzable: era el motivo de que
         «diera error al dar de alta un ponente» en el móvil. Se corta a la
         vista y el que se desplaza es el cuerpo; el pie, si hay, siempre queda
         a pulgar. */
      max-height: calc(100vh - 40px);
      max-height: calc(100dvh - 40px);
    }
    /* La flexbox solo con el diálogo abierto. Con «display: flex» en la regla
       base (incondicional) la regla de autor ganaba al «display: none» del
       navegador que oculta un dialog cerrado, y TODOS los diálogos cerrados se
       pintaban en el flujo de la página (los de MediaPicker flotaban por encima
       del formulario y se pisaban). showModal() añade el atributo open, así que
       con esta condición se conserva el scroll de cuerpo y el pie a pulgar en
       abierto sin que el estado cerrado se vea. */
    dialog[open] {
      display: flex;
      flex-direction: column;
    }
    /* Variante ancha: modales con contenido de dos columnas (p. ej. el
       editor de imagen, recorte + metadatos lado a lado) que no caben en
       el ancho estrecho por defecto. */
    dialog.ancho {
      max-width: 64rem;
    }
    dialog::backdrop {
      background-color: var(--backdrop);
    }
    /* .dlg__body (panel-organizador.html:47-48). Es la única zona que se
       desplaza cuando el contenido no cabe en la vista (ver la «max-height»
       del dialog); «min-height: 0» porque un flex item, sin ella, no se deja
       recortar y llevaría el scroll fuera del diálogo. */
    .cuerpo {
      padding: var(--sp-5);
      overflow-y: auto;
      min-height: 0;
    }
    /* .dlg__foot (panel-organizador.html:49). No encoje: las acciones de
       cerrar/guardar están ahí y deben quedar siempre a pulgar. */
    .pie {
      display: flex;
      gap: var(--sp-3);
      justify-content: flex-end;
      padding: var(--sp-4) var(--sp-5);
      border-top: 1px solid var(--border);
      flex-shrink: 0;
    }
    .pie:empty {
      display: none;
    }
  `,
})
export class Dialog {
  private readonly elemento = viewChild.required<ElementRef<HTMLDialogElement>>('elemento');

  /** `'normal'` (por defecto): 28.75rem, el ancho de siempre. `'ancho'`:
   * 64rem, para contenido de dos columnas. */
  readonly tamano = input<'normal' | 'ancho'>('normal');

  /** Se emite al cerrar, por cualquier vía (Escape, fondo, `cerrar()`). */
  readonly cerrado = output<void>();

  private focoPrevio: HTMLElement | null = null;
  private cerradoYa = false;

  abrir(): void {
    this.cerradoYa = false;
    this.focoPrevio = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    this.elemento().nativeElement.showModal();
  }

  cerrar(): void {
    // jsdom no implementa el cierre del `<dialog>` nativo: el estado interno se
    // procesa igual y el DOM de prueba no depende de ese método.
    if (typeof this.elemento().nativeElement.close === 'function') {
      this.elemento().nativeElement.close();
    }
    this.procesarCierre();
  }

  /** Cierre por cualquier vía (también externa, vía el evento close del nativo):
   * emite y restaura el foco una sola vez por apertura. */
  protected procesarCierre(): void {
    if (this.cerradoYa) {
      return;
    }
    this.cerradoYa = true;
    this.cerrado.emit();
    this.focoPrevio?.focus();
    this.focoPrevio = null;
  }

  /** Clic en el propio `<dialog>` (no en sus hijos) = clic en el fondo. */
  protected alClic(evento: MouseEvent): void {
    if (evento.target === this.elemento().nativeElement) {
      this.cerrar();
    }
  }
}
