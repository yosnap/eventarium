import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  computed,
  effect,
  inject,
  input,
  model,
  output,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { TranslocoService } from '@jsverse/transloco';

/** Hora que se aplica al elegir un día cuando el valor todavía no traía hora:
 * un evento no suele empezar de madrugada, así que el punto de partida amable
 * es media mañana y no `00:00` — quien necesite otra la cambia en el mismo
 * panel, sin desplazarse por celdas oscuras. */
const HORA_POR_DEFECTO = '09:00';

/** Lo que muestra el campo de hora mientras no hay valor. */
const HORA_VACIA = '--:--';

/** Una celda del calendario: la fecha real y los estados que la pintan. */
interface CeldaDia {
  readonly fecha: Date;
  readonly fueraDeMes: boolean;
  readonly esHoy: boolean;
  readonly esSeleccionado: boolean;
  readonly etiqueta: string;
}

interface PartesValor {
  readonly anio: number;
  readonly mes: number;
  readonly dia: number;
  readonly hora: number;
  readonly minuto: number;
}

function dosCifras(n: number): string {
  return String(n).padStart(2, '0');
}

/** `YYYY-MM-DDTHH:mm`, el formato de `<input type="datetime-local">` que este
 * componente usa como valor de verdad. */
function aValorLocal(partes: {
  anio: number;
  mes: number;
  dia: number;
  hora: number;
  minuto: number;
}): string {
  return (
    `${partes.anio}-${dosCifras(partes.mes + 1)}-${dosCifras(partes.dia)}` +
    `T${dosCifras(partes.hora)}:${dosCifras(partes.minuto)}`
  );
}

function partirValor(valor: string): PartesValor | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(valor);
  if (!m) return null;
  return {
    anio: Number(m[1]),
    mes: Number(m[2]) - 1,
    dia: Number(m[3]),
    hora: Number(m[4]),
    minuto: Number(m[5]),
  };
}

function hoy(): PartesValor {
  const ahora = new Date();
  return {
    anio: ahora.getFullYear(),
    mes: ahora.getMonth(),
    dia: ahora.getDate(),
    hora: ahora.getHours(),
    minuto: ahora.getMinutes(),
  };
}

/** Entiende lo que cabe esperar que teclee una persona en la caja de hora:
 * «9» (09:00), «935» (09:35), «9:35» o «09:35». Devuelve null mientras lo
 * tecleado todavía no forma una hora válida. */
function parseHoraTexto(texto: string): { hora: number; minuto: number } | null {
  const digitos = texto.replace(/\D/g, '');
  if (digitos.length === 0 || digitos.length > 4) return null;
  const hora = digitos.length <= 2 ? Number(digitos) : Number(digitos.slice(0, digitos.length - 2));
  const minuto = digitos.length <= 2 ? 0 : Number(digitos.slice(-2));
  if (Number.isNaN(hora) || Number.isNaN(minuto)) return null;
  if (hora > 23 || minuto > 59) return null;
  return { hora, minuto };
}

/** Texto reactivo de Transloco: `translate()` a secas no es reactivo y, si la
 * primera pintura ocurre antes de que el idioma esté cargado, dejaría la clave
 * cruda congelada en la plantilla. `selectTranslate` emite cuando la
 * traducción está lista y `toSignal` obliga a repintar. */
function texto(transloco: TranslocoService, clave: string) {
  return toSignal(transloco.selectTranslate(clave).pipe(takeUntilDestroyed()), {
    initialValue: '',
  });
}

/**
 * Selector de fecha y hora en dos campos (fecha y hora) bajo una misma
 * etiqueta, con el mismo contrato que `Input`/`Select`: mejora progresiva
 * sobre un `<input type="datetime-local">` nativo real, oculto con la técnica
 * `sr-only` de siempre, que guarda el valor de verdad
 * (`YYYY-MM-DDTHH:mm`). Así el formulario funciona igual y un test puede
 * leer o escribir el valor sin simular clics.
 *
 * El campo de fecha abre un calendario mensual; el de hora, rejillas de hora
 * y minuto. Elegir un día cierra su panel (siguiendo con la hora es el paso
 * natural); el panel de hora permanece abierto hasta «Listo», Escape o clic
 * fuera, porque ajustar hora y minuto son dos clics.
 *
 * La navegación por teclado usa tabindex itinerante: solo el día enfocado (y
 * la hora/minuto activos) son parada de Tab; las flechas mueven el foco
 * dentro de cada grupo.
 */
@Component({
  selector: 'app-datetime-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- Etiqueta flotante como Input: dentro del campo cuando está vacío y
         en reposo, arriba al ganar foco o haber valor. Cubre el par fecha+hora
         pero está enlazada (for/id) al botón de fecha, el campo principal. -->
    <div class="campo" [class.flotando]="flotando()">
      <div class="dt" [class.dt--up]="haciaArriba()">
        <input
          class="dt__native"
          type="datetime-local"
          tabindex="-1"
          aria-hidden="true"
          [id]="idNativo()"
          [disabled]="disabled()"
          [required]="required()"
          [value]="value()"
          (input)="alEscribirEnNativo($event)"
        />
        <div class="dt__controles">
          <button
            #botonFecha
            type="button"
            class="dt__btn"
            [id]="idCampo()"
            aria-haspopup="dialog"
            [attr.aria-expanded]="panelAbierto() === 'fecha'"
            [attr.aria-controls]="idPanelFecha()"
            [attr.aria-invalid]="error() ? 'true' : null"
            [attr.aria-describedby]="descripcionId()"
            [disabled]="disabled()"
            (click)="alternar('fecha')"
          >
            <span>{{ etiquetaFecha() }}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
              <rect x="3" y="5" width="18" height="16" rx="2" />
              <path d="M8 3v4M16 3v4M3 10h18" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <!-- Campo de hora editable a mano: se puede escribir «9», «935» o
               «9:35» y se aplica en cuanto forma una hora válida; las flechas
               del teclado suman o restan de 5 en 5 minutos (PágArriba/PágAbajo,
               de hora en hora). El botón del reloj despliega los saltos. -->
          <div class="dt__hora" [class.abierto]="panelAbierto() === 'hora'">
            <input
              #cajaHora
              type="text"
              inputmode="numeric"
              maxlength="5"
              autocomplete="off"
              placeholder="--:--"
              [id]="idCampoHora()"
              [attr.aria-label]="tHora()"
              [attr.aria-invalid]="error() ? 'true' : null"
              [attr.aria-describedby]="descripcionId()"
              [disabled]="disabled()"
              [value]="horaEnCaja()"
              (input)="alEscribirHora($event)"
              (keydown)="alPulsarTeclaEnHora($event)"
              (blur)="alDesenfocarHora()"
            />
            <button
              type="button"
              class="dt__hora-saltos"
              aria-haspopup="dialog"
              [attr.aria-expanded]="panelAbierto() === 'hora'"
              [attr.aria-controls]="idPanelHora()"
              [attr.aria-label]="tElegirHora()"
              [disabled]="disabled()"
              (click)="alternar('hora')"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>
          </div>
        </div>
        <label [for]="idCampo()" [class.sr-only]="etiquetaOculta()">{{ label() }}</label>

        @if (panelAbierto() === 'fecha') {
          <div
            class="dt__panel"
            role="dialog"
            [id]="idPanelFecha()"
            [attr.aria-label]="tElegirFecha()"
            (keydown)="alPulsarTeclaEnPanel($event, 'fecha')"
          >
            <div class="dt__mes">
              <button
                type="button"
                class="dt__flecha"
                [attr.aria-label]="tMesAnterior()"
                (click)="moverMes(-1)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M15 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
              <span class="dt__titulo" aria-live="polite">{{ cabeceraMes() }}</span>
              <button
                type="button"
                class="dt__flecha"
                [attr.aria-label]="tMesSiguiente()"
                (click)="moverMes(1)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
            </div>

            <div class="dt__semana" aria-hidden="true">
              @for (inicial of inicialesSemana(); track $index) {
                <span>{{ inicial }}</span>
              }
            </div>
            <div class="dt__dias" role="group" [attr.aria-label]="cabeceraMes()">
              @for (celda of dias(); track celda.fecha.getTime(); let i = $index) {
                <button
                  type="button"
                  class="dt__dia"
                  [id]="idDia(i)"
                  [attr.aria-label]="celda.etiqueta"
                  [attr.aria-current]="celda.esHoy ? 'date' : null"
                  [class.fuera]="celda.fueraDeMes"
                  [class.hoy]="celda.esHoy"
                  [class.elegido]="celda.esSeleccionado"
                  [tabindex]="i === indiceDiaEnfocado() ? 0 : -1"
                  (click)="elegirDia(celda)"
                  (focus)="indiceDiaEnfocado.set(i)"
                >
                  {{ celda.fecha.getDate() }}
                </button>
              }
            </div>

            <div class="dt__pie">
              <button type="button" class="dt__atajo" (click)="elegirHoy()">
                {{ tHoy() }}
              </button>
            </div>
          </div>
        }

        @if (panelAbierto() === 'hora') {
          <div
            class="dt__panel dt__panel--hora"
            role="dialog"
            [id]="idPanelHora()"
            [attr.aria-label]="tElegirHora()"
            (keydown)="alPulsarTeclaEnPanel($event, 'hora')"
          >
            <p class="dt__hora-actual" aria-live="polite">{{ etiquetaHora() }}</p>
            <div class="dt__saltos">
              <button
                type="button"
                class="dt__salto"
                [attr.aria-label]="tMenosUnaHora()"
                (click)="ajustarHora(-60)"
              >
                −1 h
              </button>
              <button
                type="button"
                class="dt__salto"
                [attr.aria-label]="tMenosCincoMinutos()"
                (click)="ajustarHora(-5)"
              >
                −5 min
              </button>
              <button
                type="button"
                class="dt__salto"
                [attr.aria-label]="tMasCincoMinutos()"
                (click)="ajustarHora(5)"
              >
                +5 min
              </button>
              <button
                type="button"
                class="dt__salto"
                [attr.aria-label]="tMasUnaHora()"
                (click)="ajustarHora(60)"
              >
                +1 h
              </button>
            </div>

            <div class="dt__pie">
              <button type="button" class="dt__atajo" (click)="elegirAhora()">
                {{ tAhora() }}
              </button>
              <button type="button" class="dt__listo" (click)="cerrar('hora', true)">
                {{ tListo() }}
              </button>
            </div>
          </div>
        }
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
    }
    .dt {
      position: relative;
    }
    .dt__native {
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
    .dt__controles {
      display: grid;
      /* min-width 0: sin él, la fecha («jue, 29 oct 2026», sin saltos de
       * línea) impide que la columna encoja y el par desborda su hueco. */
      grid-template-columns: minmax(0, 1fr) auto;
      gap: var(--space-xs);
    }
    /* Mismas medidas que el input de Input (3.25rem, superficie 2, radio
       pequeño): con la etiqueta flotante encima, este par de botones calca el
       aspecto del resto de campos del formulario. */
    .dt__btn {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      width: 100%;
      min-width: 0;
      min-height: 3.25rem;
      padding: 1.25rem 0.75rem 0.4rem;
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
    .dt__btn:hover {
      border-color: var(--faint);
      background: var(--surface);
    }
    .dt__btn[aria-expanded='true'] {
      border-color: var(--accent);
      background: var(--surface);
    }
    .dt__btn[aria-invalid='true'] {
      border-color: var(--danger);
    }
    .dt__btn:disabled {
      cursor: not-allowed;
      opacity: 0.6;
    }
    .dt__btn svg {
      width: 18px;
      height: 18px;
      flex: 0 0 auto;
      color: var(--muted);
    }
    .dt__btn span.vacio {
      color: var(--muted);
    }
    .dt__btn span {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    /* Campo de hora: mismo aspecto que el botón de fecha, pero editable a
       mano. El botón de saltos (reloj) va pegado a su derecha, dentro del
       mismo borde. */
    .dt__hora {
      display: flex;
      align-items: center;
      flex: 0 0 auto;
      min-height: 3.25rem;
      background: var(--surface-2);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      transition:
        border-color 0.15s,
        background-color 0.15s;
    }
    .dt__hora:hover {
      border-color: var(--faint);
      background: var(--surface);
    }
    .dt__hora:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent);
    }
    .dt__hora.abierto {
      border-color: var(--accent);
      background: var(--surface);
    }
    .dt__hora input {
      width: 5.5rem;
      box-sizing: border-box;
      padding: 1.25rem 0 0.4rem 0.75rem;
      border: none;
      background: none;
      color: var(--fg);
      font: inherit;
      font-variant-numeric: tabular-nums;
      text-align: left;
    }
    .dt__hora input:focus {
      outline: none;
    }
    .dt__hora input::placeholder {
      color: var(--muted);
    }
    .dt__hora-saltos {
      display: grid;
      place-items: center;
      width: 2.25rem;
      height: 2.25rem;
      margin-right: 0.5rem;
      border: none;
      border-radius: var(--radius-md);
      background: none;
      color: var(--muted);
      cursor: pointer;
    }
    .dt__hora-saltos:hover {
      background: var(--surface-hi);
      color: var(--fg);
    }
    .dt__hora-saltos[aria-expanded='true'] {
      color: var(--accent);
    }
    .dt__hora-saltos svg {
      width: 18px;
      height: 18px;
    }
    /* Etiqueta flotante, calco de la de Input: dentro del campo en reposo,
       arriba (y en color acento) con foco o valor. Va sobre el botón de
       fecha, que es el ancho flexible del par. */
    .campo > .dt > label {
      position: absolute;
      left: 0.8rem;
      top: 50%;
      transform: translateY(-50%);
      transform-origin: left top;
      font-weight: 500;
      color: var(--muted);
      pointer-events: none;
      transition:
        transform 0.15s ease,
        top 0.15s ease,
        color 0.15s ease;
      max-width: calc(100% - 3.5rem);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .campo.flotando > .dt > label {
      top: 0.6rem;
      transform: translateY(0) scale(0.78);
      color: var(--accent);
    }
    @media (prefers-reduced-motion: reduce) {
      .campo > .dt > label {
        transition: none;
      }
    }
    .dt__panel {
      position: absolute;
      z-index: 60;
      top: calc(100% + 6px);
      left: 0;
      display: grid;
      gap: var(--space-sm);
      width: 19rem;
      max-width: calc(100vw - 2rem);
      padding: var(--space-md);
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      box-shadow: var(--shadow-md);
    }
    .dt--up .dt__panel {
      top: auto;
      bottom: calc(100% + 6px);
    }
    .dt__mes {
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: center;
      gap: var(--space-xs);
    }
    .dt__titulo {
      text-align: center;
      font-weight: 600;
      text-transform: capitalize;
    }
    .dt__flecha {
      display: grid;
      place-items: center;
      width: 2rem;
      height: 2rem;
      border: none;
      border-radius: var(--radius-md);
      background: none;
      color: var(--muted);
      cursor: pointer;
    }
    .dt__flecha:hover {
      background: var(--surface-hi);
      color: var(--fg);
    }
    .dt__flecha svg {
      width: 16px;
      height: 16px;
    }
    .dt__semana,
    .dt__dias {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 2px;
    }
    .dt__semana span {
      padding: 2px 0;
      text-align: center;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .dt__dia {
      position: relative;
      min-height: 2.25rem;
      border: none;
      border-radius: var(--radius-md);
      background: none;
      color: var(--fg);
      font: inherit;
      cursor: pointer;
    }
    .dt__dia:hover {
      background: var(--surface-hi);
    }
    .dt__dia.fuera {
      color: var(--muted);
      opacity: 0.55;
    }
    .dt__dia.hoy::after {
      content: '';
      position: absolute;
      left: 50%;
      bottom: 4px;
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: var(--accent);
      transform: translateX(-50%);
    }
    .dt__dia.elegido {
      background: var(--accent);
      color: var(--accent-contrast, #fff);
      font-weight: 600;
    }
    .dt__dia.elegido::after {
      background: var(--accent-contrast, #fff);
    }
    /* Panel de saltos de hora: la hora vigente grande y cuatro saltos con
       aire (el «muy pegado, sin padding» de las antiguas rejillas). */
    .dt__hora-actual {
      margin: 0;
      text-align: center;
      font-size: 1.75rem;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      color: var(--fg);
    }
    .dt__saltos {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: var(--space-xs);
    }
    .dt__salto {
      min-height: 2.5rem;
      padding: 0 0.5rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: none;
      color: var(--fg);
      font: inherit;
      font-variant-numeric: tabular-nums;
      cursor: pointer;
    }
    .dt__salto:hover {
      background: var(--surface-hi);
      border-color: var(--faint);
    }
    .dt__pie {
      display: flex;
      justify-content: space-between;
      gap: var(--space-sm);
      border-top: 1px solid var(--border);
      padding-top: var(--space-sm);
    }
    .dt__atajo,
    .dt__listo {
      min-height: 2.25rem;
      padding: 0 0.875rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: none;
      color: var(--fg);
      font: inherit;
      cursor: pointer;
    }
    .dt__atajo:hover,
    .dt__listo:hover {
      background: var(--surface-hi);
    }
    .dt__listo {
      background: var(--accent);
      border-color: var(--accent);
      color: var(--accent-contrast, #fff);
      font-weight: 600;
    }
    .dt__listo:hover {
      background: var(--accent);
      opacity: 0.9;
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
export class DatetimePicker {
  readonly label = input.required<string>();
  readonly disabled = input(false);
  readonly required = input(false);
  readonly etiquetaOculta = input(false);
  readonly error = input<string | null>(null);
  readonly hint = input<string | null>(null);
  readonly fieldId = input<string | null>(null);
  /** `YYYY-MM-DDTHH:mm`, lo mismo que entendía el `<input datetime-local>` que
   * sustituye: quien consuma el componente no cambia ni una línea de su lógica
   * de fechas (parsear, validar, convertir a ISO…). */
  readonly value = model('');
  readonly blurred = output<void>();

  private readonly elementoAnfitrion = inject(ElementRef<HTMLElement>);
  private readonly transloco = inject(TranslocoService);

  private static contador = 0;
  private readonly indice = DatetimePicker.contador++;
  protected readonly idCampo = computed(() => this.fieldId() ?? `dt-${this.indice}`);
  protected readonly idCampoHora = computed(() => `${this.idCampo()}-hora`);
  protected readonly idNativo = computed(() => `${this.idCampo()}-nativo`);
  protected readonly idPanelFecha = computed(() => `${this.idCampo()}-panel-fecha`);
  protected readonly idPanelHora = computed(() => `${this.idCampo()}-panel-hora`);
  protected readonly idError = computed(() => `${this.idCampo()}-error`);
  protected readonly idAyuda = computed(() => `${this.idCampo()}-ayuda`);
  protected readonly descripcionId = computed(() => {
    if (this.error()) return this.idError();
    if (this.hint()) return this.idAyuda();
    return null;
  });

  /** Panel abierto: el de fecha, el de hora, o ninguno. */
  protected readonly panelAbierto = signal<'fecha' | 'hora' | null>(null);
  protected readonly haciaArriba = signal(false);
  /** Mes que muestra el calendario (primer día del mes), independiente de lo
   * elegido: se puede hojear sin cambiar el valor. */
  private readonly mesVisible = signal(primerDiaDeMes(new Date()));
  protected readonly indiceDiaEnfocado = signal(0);
  /** Lo tecleado en la caja de hora mientras se edita: `null` significa que
   * la caja muestra la hora canónica del valor. Se necesita para no
   * reformatear en cada pulsación (escribir «9» no debe saltar a «09:00»). */
  protected readonly horaCaja = signal<string | null>(null);

  private readonly locale = () => this.transloco.getActiveLang() || 'es-ES';

  // Textos reactivos: ver `texto()` para por qué no basta con `translate()`.
  protected readonly tElegirFecha = texto(this.transloco, 'comun.datetime.elegirFecha');
  protected readonly tElegirHora = texto(this.transloco, 'comun.datetime.elegirHora');
  protected readonly tMesAnterior = texto(this.transloco, 'comun.datetime.mesAnterior');
  protected readonly tMesSiguiente = texto(this.transloco, 'comun.datetime.mesSiguiente');
  protected readonly tHora = texto(this.transloco, 'comun.datetime.hora');
  protected readonly tMenosUnaHora = texto(this.transloco, 'comun.datetime.menosUnaHora');
  protected readonly tMenosCincoMinutos = texto(this.transloco, 'comun.datetime.menosCincoMinutos');
  protected readonly tMasCincoMinutos = texto(this.transloco, 'comun.datetime.masCincoMinutos');
  protected readonly tMasUnaHora = texto(this.transloco, 'comun.datetime.masUnaHora');
  protected readonly tHoy = texto(this.transloco, 'comun.datetime.hoy');
  protected readonly tAhora = texto(this.transloco, 'comun.datetime.ahora');
  protected readonly tListo = texto(this.transloco, 'comun.datetime.listo');

  protected readonly partes = computed(() => partirValor(this.value()));

  /** La etiqueta flota mientras el foco ande por cualquier parte del campo
   * (botones o paneles) o haya valor — de ahí el focusin/focusout del host en
   * vez de un blur suelto por botón. */
  protected readonly enFoco = signal(false);
  protected readonly flotando = computed(
    () => this.enFoco() || this.panelAbierto() !== null || this.value().length > 0,
  );

  protected readonly etiquetaFecha = computed(() => {
    const partes = this.partes();
    if (!partes) return '';
    return new Intl.DateTimeFormat(this.locale(), {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(new Date(partes.anio, partes.mes, partes.dia));
  });

  protected readonly etiquetaHora = computed(() => {
    const partes = this.partes();
    return partes ? `${dosCifras(partes.hora)}:${dosCifras(partes.minuto)}` : HORA_VACIA;
  });

  /** Lo que pinta la caja de hora: lo tecleado mientras se edita, la hora del
   * valor (o nada, que deja ver el `--:--` del placeholder) en reposo. */
  protected readonly horaEnCaja = computed(() => {
    const tecleado = this.horaCaja();
    if (tecleado !== null) return tecleado;
    const partes = this.partes();
    return partes ? `${dosCifras(partes.hora)}:${dosCifras(partes.minuto)}` : '';
  });

  protected readonly cabeceraMes = computed(() =>
    new Intl.DateTimeFormat(this.locale(), { month: 'long', year: 'numeric' }).format(
      this.mesVisible(),
    ),
  );

  /** Iniciales de los días de semana, de lunes a domingo, en el locale activo. */
  protected readonly inicialesSemana = computed(() => {
    const formato = new Intl.DateTimeFormat(this.locale(), { weekday: 'narrow' });
    // 2026-10-05 es lunes: una semana cualquiera que empieza donde queremos.
    const lunes = new Date(2026, 9, 5);
    return Array.from({ length: 7 }, (_, i) =>
      formato.format(new Date(lunes.getFullYear(), lunes.getMonth(), lunes.getDate() + i)),
    );
  });

  /** Seis semanas fijas (42 celdas) para que el panel no cambie de altura al
   * hojear meses: el febrero más corto empieza en domingo y termina rodeado. */
  protected readonly dias = computed<CeldaDia[]>(() => {
    const primero = this.mesVisible();
    // getDay() cuenta desde el domingo (0); el offset lleva el lunes a la primera columna.
    const offset = (primero.getDay() + 6) % 7;
    const inicio = new Date(primero.getFullYear(), primero.getMonth(), 1 - offset);
    const elegido = this.partes();
    const actual = new Date();
    const formatoEtiqueta = new Intl.DateTimeFormat(this.locale(), {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    });
    return Array.from({ length: 42 }, (_, i) => {
      const fecha = new Date(inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + i);
      const esHoy =
        fecha.getFullYear() === actual.getFullYear() &&
        fecha.getMonth() === actual.getMonth() &&
        fecha.getDate() === actual.getDate();
      const esSeleccionado =
        elegido !== null &&
        fecha.getFullYear() === elegido.anio &&
        fecha.getMonth() === elegido.mes &&
        fecha.getDate() === elegido.dia;
      return {
        fecha,
        fueraDeMes: fecha.getMonth() !== primero.getMonth(),
        esHoy,
        esSeleccionado,
        etiqueta: formatoEtiqueta.format(fecha),
      };
    });
  });

  constructor() {
    // Al abrir cada panel, lo elegido (u hoy) entra en el foco y en la vista:
    // es donde sigue la conversación después de pulsar el botón. Solo se
    // dispara con el cambio de panel: los días se leen con `untracked` para
    // que hojear meses con el teclado (foco en las flechas) no relance el
    // efecto y robe el foco en cada salto.
    effect(() => {
      const panel = this.panelAbierto();
      const anfitrion = this.elementoAnfitrion.nativeElement;
      if (panel === 'fecha') {
        const dias = untracked(this.dias);
        const elegido = dias.findIndex((celda) => celda.esSeleccionado);
        const hoyIdx = dias.findIndex((celda) => celda.esHoy);
        const indice = elegido >= 0 ? elegido : hoyIdx >= 0 ? hoyIdx : 0;
        this.indiceDiaEnfocado.set(indice);
        this.enfocar(anfitrion.querySelector(`#${this.idDia(indice)}`));
      } else if (panel === 'hora') {
        // El foco va a la caja: escribir o usar flechas es el camino principal.
        this.enfocar(anfitrion.querySelector(`#${this.idCampoHora()}`));
      }
    });
  }

  @HostListener('document:click', ['$event'])
  protected alClicarFuera(evento: MouseEvent): void {
    const panel = this.panelAbierto();
    if (!panel) return;
    if (!this.elementoAnfitrion.nativeElement.contains(evento.target as Node)) {
      this.cerrar(panel, false);
    }
  }

  @HostListener('focusin')
  protected alGanarFoco(): void {
    this.enFoco.set(true);
  }

  @HostListener('focusout', ['$event'])
  protected alPerderFoco(evento: FocusEvent): void {
    const hacia = evento.relatedTarget as Node | null;
    this.enFoco.set(hacia !== null && this.elementoAnfitrion.nativeElement.contains(hacia));
    if (hacia === null || !this.elementoAnfitrion.nativeElement.contains(hacia)) {
      this.blurred.emit();
    }
  }

  protected idDia(indice: number): string {
    return `${this.idCampo()}-dia-${indice}`;
  }

  protected alternar(panel: 'fecha' | 'hora'): void {
    if (this.disabled()) return;
    if (this.panelAbierto() === panel) {
      this.cerrar(panel, true);
      return;
    }
    const anfitrion = this.elementoAnfitrion.nativeElement;
    const boton = anfitrion.querySelector('.dt__btn') as HTMLElement | null;
    if (boton) {
      const rect = boton.getBoundingClientRect();
      // Altura aproximada del panel: calendario (~15rem) + rejillas de tiempo.
      this.haciaArriba.set(window.innerHeight - rect.bottom < 380);
    }
    if (panel === 'fecha') {
      // Resincroniza el mes con el valor vigente al abrir, no con el último
      // que se hojeó: cerrar sin elegir no debe dejar un mes huérfano recordado.
      const partes = this.partes();
      this.mesVisible.set(
        partes ? new Date(partes.anio, partes.mes, 1) : primerDiaDeMes(new Date()),
      );
    }
    this.panelAbierto.set(panel);
  }

  protected cerrar(panel: 'fecha' | 'hora', devolverFoco: boolean): void {
    if (this.panelAbierto() !== panel) return;
    this.panelAbierto.set(null);
    if (panel === 'hora') this.horaCaja.set(null);
    if (devolverFoco) {
      const selector = panel === 'fecha' ? '.dt__btn' : `#${this.idCampoHora()}`;
      const destino = this.elementoAnfitrion.nativeElement.querySelector(
        selector,
      ) as HTMLElement | null;
      destino?.focus();
    }
  }

  protected moverMes(direccion: 1 | -1): void {
    const actual = this.mesVisible();
    this.mesVisible.set(new Date(actual.getFullYear(), actual.getMonth() + direccion, 1));
  }

  /** Elegir día fija la fecha conservando la hora (o la convención de media
   * mañana si aún no había) y cierra el panel: seguir con la hora, si hace
   * falta, es el paso natural siguiente. */
  protected elegirDia(celda: CeldaDia): void {
    const existentes = this.partes();
    const [hora, minuto] = existentes
      ? [existentes.hora, existentes.minuto]
      : HORA_POR_DEFECTO.split(':').map(Number);
    this.value.set(
      aValorLocal({
        anio: celda.fecha.getFullYear(),
        mes: celda.fecha.getMonth(),
        dia: celda.fecha.getDate(),
        hora,
        minuto,
      }),
    );
    this.cerrar('fecha', true);
  }

  /** «Hoy» fija la fecha de hoy conservando la hora elegida. */
  protected elegirHoy(): void {
    const existentes = this.partes();
    const [hora, minuto] = existentes
      ? [existentes.hora, existentes.minuto]
      : HORA_POR_DEFECTO.split(':').map(Number);
    const actual = new Date();
    this.value.set(
      aValorLocal({
        anio: actual.getFullYear(),
        mes: actual.getMonth(),
        dia: actual.getDate(),
        hora,
        minuto,
      }),
    );
    this.cerrar('fecha', true);
  }

  /** Fija la hora sobre la fecha vigente (o hoy, si todavía no hay). */
  private aplicarHora(hora: number, minuto: number): void {
    const base = this.partes() ?? { ...hoy(), hora: 0, minuto: 0 };
    this.value.set(aValorLocal({ ...base, hora, minuto }));
  }

  /** Lo tecleado en la caja («9», «935», «9:35») se aplica en cuanto forma
   * una hora válida; mientras tanto la caja conserva el texto crudo para no
   * pelearse con quien está escribiendo. */
  protected alEscribirHora(evento: Event): void {
    const bruto = (evento.target as HTMLInputElement).value;
    this.horaCaja.set(bruto);
    const hora = parseHoraTexto(bruto);
    if (hora) this.aplicarHora(hora.hora, hora.minuto);
  }

  /** Al desenfocar la caja, la hora canónica del valor vuelve a la pantalla. */
  protected alDesenfocarHora(): void {
    this.horaCaja.set(null);
    this.blurred.emit();
  }

  /** Flechas en la caja: ↑/↓ mueven de 5 en 5 minutos, RePág/AvPág de hora en
   * hora (con vuelta a la medianoche). Intro cierra el panel de saltos si está
   * abierto; Escape también. */
  protected alPulsarTeclaEnHora(evento: KeyboardEvent): void {
    switch (evento.key) {
      case 'ArrowUp':
        evento.preventDefault();
        this.ajustarHora(5);
        return;
      case 'ArrowDown':
        evento.preventDefault();
        this.ajustarHora(-5);
        return;
      case 'PageUp':
        evento.preventDefault();
        this.ajustarHora(60);
        return;
      case 'PageDown':
        evento.preventDefault();
        this.ajustarHora(-60);
        return;
      case 'Enter':
        // Sin preventDefault, Intro enviaría el formulario entero.
        evento.preventDefault();
        if (this.panelAbierto() === 'hora') this.cerrar('hora', true);
        return;
      case 'Escape':
        if (this.panelAbierto() === 'hora') {
          evento.preventDefault();
          this.cerrar('hora', true);
        }
        return;
    }
  }

  /** Salto de hora en minutos (negativo o positivo), con vuelta al día: las
   * 23:55 + 10 min son las 00:05 del mismo valor de fecha. */
  protected ajustarHora(saltoMinutos: number): void {
    const partes = this.partes() ?? { ...hoy(), hora: 0, minuto: 0 };
    const total = (((partes.hora * 60 + partes.minuto + saltoMinutos) % 1440) + 1440) % 1440;
    this.aplicarHora(Math.floor(total / 60), total % 60);
    this.horaCaja.set(null);
  }

  /** «Ahora» fija la hora actual conservando la fecha elegida. */
  protected elegirAhora(): void {
    const actual = new Date();
    this.aplicarHora(actual.getHours(), actual.getMinutes());
    this.horaCaja.set(null);
  }

  /** Escape cierra el panel; en el de fecha, las flechas mueven el foco entre
   * días con el tabindex itinerante. */
  protected alPulsarTeclaEnPanel(evento: KeyboardEvent, panel: 'fecha' | 'hora'): void {
    if (evento.key === 'Escape') {
      evento.preventDefault();
      this.cerrar(panel, true);
      return;
    }
    if (panel !== 'fecha') return;
    const salto = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[evento.key];
    if (salto !== undefined) {
      evento.preventDefault();
      this.enfocarDia(this.indiceDiaEnfocado() + salto);
    }
  }

  protected alEscribirEnNativo(evento: Event): void {
    this.value.set((evento.target as HTMLInputElement).value);
  }

  private enfocarDia(indice: number): void {
    const dias = this.dias();
    if (indice < 0 || indice >= dias.length) return;
    this.indiceDiaEnfocado.set(indice);
    this.enfocar(this.elementoAnfitrion.nativeElement.querySelector(`#${this.idDia(indice)}`));
  }

  private enfocar(elemento: Element | null): void {
    (elemento as HTMLElement | null)?.focus?.();
  }
}

function primerDiaDeMes(fecha: Date): Date {
  return new Date(fecha.getFullYear(), fecha.getMonth(), 1);
}
