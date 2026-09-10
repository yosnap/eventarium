import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  computed,
  effect,
  inject,
  input,
  model,
  output,
  signal,
  viewChild,
} from '@angular/core';

/** Una opción tal y como la recibe `app-select`. */
export interface SelectOption {
  readonly value: string;
  readonly label: string;
}

/** Opción interna: añade el marcador de «opción vacía» (`placeholder`), que no se
 * puede elegir con teclado ni con clic, igual que el `<option disabled>` que
 * sustituye. */
interface OpcionInterna extends SelectOption {
  readonly deshabilitada: boolean;
}

/** Milisegundos de inactividad antes de reiniciar la búsqueda por letra. */
const PAUSA_BUSQUEDA_MS = 500;

/**
 * Select moderno, sobre `.sel` de la referencia (`eventarium.css:214-251`): mejora
 * progresiva de un `<select>` nativo real. El nativo sigue en el marcado —oculto con
 * la misma técnica `sr-only` que ya usan otros componentes del repo (recorte a 0×0,
 * `pointer-events:none`)— y guarda el valor de verdad, así que el formulario funciona
 * igual y un test puede leer/escribir el valor sin simular clics de ratón.
 *
 * Encima se pinta un botón (`.sel__btn`) con la opción elegida y un panel
 * `role="listbox"` (`.sel__list`) con las opciones (`role="option"`). El patrón ARIA
 * elegido es «listbox con `aria-activedescendant`»: el foco de verdad se queda
 * siempre en el botón, y la opción resaltada se comunica por `aria-activedescendant`
 * en vez de mover el foco dentro de la lista — así Intro/Escape no compiten con la
 * navegación de flechas por quién tiene el foco.
 *
 * Reemplaza la decisión de la fase 2 («solo estilizar el `<select>` nativo, sin
 * combobox custom») para este componente compartido: el propietario del producto
 * pidió fidelidad literal con el select del catálogo de componentes real, sustituyendo
 * esa decisión de precaución.
 */
@Component({
  selector: 'app-select',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="campo">
      <span class="rotulo" [class.sr-only]="etiquetaOculta()" [id]="idEtiqueta()">{{
        label()
      }}</span>
      <div class="sel" [class.sel--up]="haciaArriba()">
        <select
          class="sel__native"
          tabindex="-1"
          aria-hidden="true"
          [id]="idNativo()"
          [disabled]="disabled()"
          [required]="required()"
        >
          @for (opcion of opcionesEfectivas(); track opcion.value) {
            <option
              [value]="opcion.value"
              [disabled]="opcion.deshabilitada"
              [selected]="opcion.value === value()"
            >
              {{ opcion.label }}
            </option>
          }
        </select>
        <button
          #boton
          type="button"
          class="sel__btn"
          role="combobox"
          aria-haspopup="listbox"
          [id]="idCampo()"
          [attr.aria-expanded]="abierto()"
          [attr.aria-controls]="idLista()"
          [attr.aria-labelledby]="idEtiqueta() + ' ' + idCampo()"
          [attr.aria-activedescendant]="idOpcionActiva()"
          [attr.aria-invalid]="error() ? 'true' : null"
          [attr.aria-describedby]="descripcionId()"
          [attr.aria-required]="required() ? 'true' : null"
          [disabled]="disabled()"
          (click)="alternar()"
          (keydown)="alPulsarTecla($event)"
          (blur)="blurred.emit()"
        >
          <span>{{ etiquetaVisible() }}</span>
        </button>
        <ul
          class="sel__list"
          role="listbox"
          [id]="idLista()"
          [attr.aria-labelledby]="idEtiqueta()"
          [hidden]="!abierto()"
        >
          @for (opcion of opcionesEfectivas(); track opcion.value; let i = $index) {
            <!--
              Patrón ARIA «listbox con aria-activedescendant»: la opción NO debe
              recibir foco (por diseño, el foco de verdad se queda siempre en
              .sel__btn); el teclado ya está cubierto en el botón
              (alPulsarTecla), el clic es solo el complemento para ratón.
            -->
            <!-- eslint-disable-next-line @angular-eslint/template/click-events-have-key-events, @angular-eslint/template/interactive-supports-focus -->
            <li
              class="sel__o"
              role="option"
              [id]="idOpcion(i)"
              [class.is-active]="i === indiceActivo()"
              [attr.aria-selected]="opcion.value === value()"
              [attr.aria-disabled]="opcion.deshabilitada ? 'true' : null"
              (click)="alElegirOpcion(i)"
              (mousemove)="alPasarRaton(i)"
            >
              {{ opcion.label }}
            </li>
          }
        </ul>
      </div>
      @if (error()) {
        <p [id]="idError()" class="error">{{ error() }}</p>
      } @else if (hint()) {
        <p [id]="idAyuda()" class="ayuda">{{ hint() }}</p>
      }
    </div>
  `,
  styles: `
    .campo {
      display: grid;
      gap: var(--space-xs);
    }
    .rotulo {
      display: block;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .sel {
      position: relative;
    }
    .sel__native {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
      pointer-events: none;
    }
    .sel__btn {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      width: 100%;
      min-height: 46px;
      padding: 11px 13px;
      background: var(--surface-2);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      color: var(--fg);
      font: inherit;
      text-align: left;
      cursor: pointer;
      transition:
        border-color 0.15s,
        background-color 0.15s;
    }
    .sel__btn:hover {
      border-color: var(--faint);
      background: var(--surface);
    }
    .sel__btn[aria-expanded='true'] {
      border-color: var(--accent);
      background: var(--surface);
    }
    .sel__btn[aria-invalid='true'] {
      border-color: var(--danger);
    }
    .sel__btn:disabled {
      cursor: not-allowed;
      opacity: 0.6;
    }
    .sel__btn::after {
      content: '';
      width: 8px;
      height: 8px;
      flex: 0 0 auto;
      margin-right: 2px;
      /* Flechita: dos bordes en ángulo recto rotados 45°, no un glifo de fuente. */
      border-right: 1.5px solid var(--muted);
      border-bottom: 1.5px solid var(--muted);
      transform: translateY(-2px) rotate(45deg);
      transition:
        transform 0.2s,
        border-color 0.15s;
    }
    .sel__btn:hover::after,
    .sel__btn[aria-expanded='true']::after {
      border-color: var(--fg);
    }
    .sel__btn[aria-expanded='true']::after {
      transform: translateY(1px) rotate(-135deg);
    }
    .sel__list {
      position: absolute;
      z-index: 60;
      top: calc(100% + 6px);
      left: 0;
      right: 0;
      max-height: 264px;
      overflow: auto;
      padding: 4px;
      margin: 0;
      list-style: none;
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      box-shadow: var(--shadow-md);
    }
    .sel__list[hidden] {
      display: none;
    }
    .sel__o {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 40px;
      padding: 9px 11px;
      border-radius: 3px;
      cursor: pointer;
      color: var(--fg);
    }
    .sel__o[aria-disabled='true'] {
      color: var(--muted);
      cursor: default;
    }
    .sel__o[aria-selected='true']::after {
      content: '';
      width: 6px;
      height: 11px;
      flex: 0 0 auto;
      /* Marca de verificación: dos bordes en ángulo recto rotados 45°, igual que
       * la flechita del botón, no un glifo de fuente. */
      border-right: 2px solid var(--accent);
      border-bottom: 2px solid var(--accent);
      transform: rotate(45deg);
    }
    .sel__o.is-active {
      background: var(--surface-hi);
    }
    .sel__o:hover {
      background: var(--surface-hi);
    }
    .sel--up .sel__list {
      top: auto;
      bottom: calc(100% + 6px);
    }
    .error {
      margin: 0;
      color: var(--danger);
      font-size: 0.875rem;
    }
    .ayuda {
      margin: 0;
      color: var(--muted);
      font-size: 0.8125rem;
    }
  `,
})
export class Select {
  readonly label = input.required<string>();
  readonly options = input.required<readonly SelectOption[]>();
  /** Opción vacía inicial (equivalente al `<option disabled>` que sustituye): no se
   * puede elegir con teclado ni con clic, solo indica que no hay nada elegido. */
  readonly placeholder = input<string | null>(null);
  readonly disabled = input(false);
  readonly required = input(false);
  /** Oculta visualmente el rótulo (`.sr-only`), sin quitarlo del árbol de
   * accesibilidad: para contextos donde el propio control ya deja claro qué
   * es (p. ej. el select de ciudad de `descubrir-eventos.html`, que muestra
   * "Cualquier ciudad" dentro del botón en vez de un rótulo "Ciudad" aparte). */
  readonly etiquetaOculta = input(false);
  readonly error = input<string | null>(null);
  /** Texto de ayuda bajo el campo, oculto mientras haya un error que mostrar. */
  readonly hint = input<string | null>(null);
  /** Id estable para enlazar desde fuera (p. ej. un resumen de errores). Si se omite,
   * se genera uno automático. */
  readonly fieldId = input<string | null>(null);
  readonly value = model('');
  /** Se emite al perder el foco el botón, para validar en el momento en que tiene
   * sentido — mismo patrón que `Input`/`Textarea`. */
  readonly blurred = output<void>();

  private readonly elementoAnfitrion = inject(ElementRef<HTMLElement>);
  private readonly destroyRef = inject(DestroyRef);
  private readonly botonRef = viewChild<ElementRef<HTMLButtonElement>>('boton');

  private static contador = 0;
  private readonly indice = Select.contador++;
  protected readonly idCampo = computed(() => this.fieldId() ?? `sel-${this.indice}`);
  /** Id del `<select>` nativo oculto: distinto del id externo (`idCampo`), que ahora
   * vive en el botón real —el único elemento enfocable— para que los enlaces de fuera
   * (p. ej. `app-error-summary`) lleven el foco a un control alcanzable. */
  protected readonly idNativo = computed(() => `${this.idCampo()}-nativo`);
  protected readonly idLista = computed(() => `${this.idCampo()}-lista`);
  protected readonly idEtiqueta = computed(() => `${this.idCampo()}-etiqueta`);
  protected readonly idError = computed(() => `${this.idCampo()}-error`);
  protected readonly idAyuda = computed(() => `${this.idCampo()}-ayuda`);
  protected readonly descripcionId = computed(() => {
    if (this.error()) return this.idError();
    if (this.hint()) return this.idAyuda();
    return null;
  });

  protected readonly abierto = signal(false);
  protected readonly haciaArriba = signal(false);
  protected readonly indiceActivo = signal(-1);
  protected readonly idOpcionActiva = computed(() =>
    this.abierto() && this.indiceActivo() >= 0 ? this.idOpcion(this.indiceActivo()) : null,
  );

  protected readonly opcionesEfectivas = computed<readonly OpcionInterna[]>(() => {
    const base = this.options().map((opcion) => ({ ...opcion, deshabilitada: false }));
    const marcador = this.placeholder();
    return marcador ? [{ value: '', label: marcador, deshabilitada: true }, ...base] : base;
  });

  protected readonly etiquetaVisible = computed(() => {
    const opciones = this.opcionesEfectivas();
    const seleccionada = opciones.find((opcion) => opcion.value === this.value());
    return seleccionada?.label ?? this.placeholder() ?? '';
  });

  private bufferBusqueda = '';
  private temporizadorBusqueda: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    // Desplaza la opción activa a la vista cada vez que cambia mientras el panel
    // está abierto: la navegación por teclado (flechas, Home/End, búsqueda por
    // letra) puede moverla fuera del área visible de `.sel__list`
    // (`max-height: 264px; overflow: auto`).
    effect(() => {
      const indice = this.indiceActivo();
      if (!this.abierto() || indice < 0) return;
      const elemento = this.elementoAnfitrion.nativeElement.querySelector(
        `#${this.idOpcion(indice)}`,
      ) as HTMLElement | null;
      elemento?.scrollIntoView?.({ block: 'nearest' });
    });
    this.destroyRef.onDestroy(() => {
      if (this.temporizadorBusqueda) clearTimeout(this.temporizadorBusqueda);
    });
  }

  protected idOpcion(indice: number): string {
    return `${this.idCampo()}-o-${indice}`;
  }

  @HostListener('document:click', ['$event'])
  protected alClicarFuera(evento: MouseEvent): void {
    if (!this.abierto()) return;
    const dentro = this.elementoAnfitrion.nativeElement.contains(evento.target as Node);
    if (!dentro) this.cerrar(false);
  }

  protected alternar(): void {
    if (this.disabled()) return;
    if (this.abierto()) {
      this.cerrar(true);
    } else {
      this.abrir();
    }
  }

  protected alElegirOpcion(indice: number): void {
    if (this.disabled()) return;
    this.confirmarSeleccion(indice);
  }

  protected alPasarRaton(indice: number): void {
    const opcion = this.opcionesEfectivas()[indice];
    if (opcion && !opcion.deshabilitada) this.indiceActivo.set(indice);
  }

  protected alPulsarTecla(evento: KeyboardEvent): void {
    if (this.disabled()) return;
    switch (evento.key) {
      case 'ArrowDown':
        evento.preventDefault();
        if (!this.abierto()) {
          this.abrir();
          return;
        }
        this.indiceActivo.set(this.siguienteSeleccionable(this.indiceActivo(), 1));
        return;
      case 'ArrowUp':
        evento.preventDefault();
        if (!this.abierto()) {
          this.abrir();
          return;
        }
        this.indiceActivo.set(this.siguienteSeleccionable(this.indiceActivo(), -1));
        return;
      case 'Home':
        if (!this.abierto()) return;
        evento.preventDefault();
        this.indiceActivo.set(this.primeraSeleccionable());
        return;
      case 'End':
        if (!this.abierto()) return;
        evento.preventDefault();
        this.indiceActivo.set(this.ultimaSeleccionable());
        return;
      case 'Enter':
      case ' ':
        evento.preventDefault();
        if (!this.abierto()) {
          this.abrir();
          return;
        }
        this.confirmarSeleccion(this.indiceActivo());
        return;
      case 'Escape':
        if (!this.abierto()) return;
        evento.preventDefault();
        this.cerrar(true);
        return;
      case 'Tab':
        this.cerrar(false);
        return;
      default:
        if (evento.key.length === 1 && /[a-zA-Z0-9áéíóúñÁÉÍÓÚÑ]/.test(evento.key)) {
          evento.preventDefault();
          this.buscarPorLetra(evento.key);
        }
    }
  }

  private abrir(): void {
    this.actualizarDireccion();
    this.abierto.set(true);
    // Siempre se resincroniza con el valor vigente al abrir (no con la opción que
    // hubiera quedado activa la última vez que se cerró el panel): si se cerró con
    // Escape o clic fuera sin elegir, la opción activa no debe «recordar» ese estado
    // transitorio.
    this.indiceActivo.set(this.indiceInicial());
  }

  private cerrar(devolverFoco: boolean): void {
    this.abierto.set(false);
    if (devolverFoco) this.botonRef()?.nativeElement.focus();
  }

  private confirmarSeleccion(indice: number): void {
    const opcion = this.opcionesEfectivas()[indice];
    if (opcion && !opcion.deshabilitada) {
      this.value.set(opcion.value);
    }
    this.cerrar(true);
  }

  /** Si no cabe hacia abajo (menos espacio que la altura máxima del panel,
   * `eventarium.css:236`), se despliega hacia arriba (`eventarium.css:251`). */
  private actualizarDireccion(): void {
    const boton = this.botonRef()?.nativeElement;
    if (!boton) return;
    const ALTURA_MAXIMA_LISTA = 264;
    const rect = boton.getBoundingClientRect();
    const espacioAbajo = window.innerHeight - rect.bottom;
    this.haciaArriba.set(espacioAbajo < ALTURA_MAXIMA_LISTA);
  }

  private indiceInicial(): number {
    const opciones = this.opcionesEfectivas();
    const indiceValor = opciones.findIndex((opcion) => opcion.value === this.value());
    if (indiceValor >= 0 && !opciones[indiceValor].deshabilitada) return indiceValor;
    return this.primeraSeleccionable();
  }

  private primeraSeleccionable(): number {
    return this.opcionesEfectivas().findIndex((opcion) => !opcion.deshabilitada);
  }

  private ultimaSeleccionable(): number {
    const opciones = this.opcionesEfectivas();
    for (const [i, opcion] of [...opciones.entries()].reverse()) {
      if (!opcion.deshabilitada) return i;
    }
    return -1;
  }

  private siguienteSeleccionable(desde: number, direccion: 1 | -1): number {
    const opciones = this.opcionesEfectivas();
    let i = desde;
    let pasos = 0;
    while (pasos < opciones.length) {
      i += direccion;
      if (i < 0 || i >= opciones.length) return desde;
      if (!opciones[i].deshabilitada) return i;
      pasos++;
    }
    return desde;
  }

  private buscarPorLetra(letra: string): void {
    this.bufferBusqueda += letra.toLowerCase();
    if (this.temporizadorBusqueda) clearTimeout(this.temporizadorBusqueda);
    this.temporizadorBusqueda = setTimeout(() => {
      this.bufferBusqueda = '';
    }, PAUSA_BUSQUEDA_MS);

    const opciones = this.opcionesEfectivas();
    const indice = opciones.findIndex(
      (opcion) => !opcion.deshabilitada && opcion.label.toLowerCase().startsWith(this.bufferBusqueda),
    );
    if (indice < 0) return;
    if (!this.abierto()) {
      this.actualizarDireccion();
      this.abierto.set(true);
    }
    this.indiceActivo.set(indice);
  }
}
