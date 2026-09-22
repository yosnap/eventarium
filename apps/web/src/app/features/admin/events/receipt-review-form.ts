import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Checkbox } from '../../../shared/ui/checkbox';
import { Dialog } from '../../../shared/ui/dialog';
import { Select, type SelectOption } from '../../../shared/ui/select';
import {
  type CamposExtraidos,
  type NivelDeConfianza,
  type ReceiptDraft,
  aCents,
  euros,
} from './accounting-types';
import type { PartidaParaGasto } from './expense-form';

/** Los cinco campos que se revisan (la moneda no se edita: el libro es en €). */
type CampoRevisable = 'provider_name' | 'expense_date' | 'base_cents' | 'vat_cents' | 'total_cents';

const CAMPOS: readonly CampoRevisable[] = [
  'provider_name',
  'expense_date',
  'base_cents',
  'vat_cents',
  'total_cents',
];

/** Extensiones que el navegador sabe pintar en un `<img>`. */
const EXTENSIONES_DE_IMAGEN = ['png', 'jpg', 'jpeg', 'webp'];

/**
 * El backend marca este rechazo con `code: "importe_sobre_techo"` en el
 * `problem+json`, que es la comprobación buena. El texto se mira solo como
 * respaldo, por si responde una versión anterior del API: confundirlo con
 * cualquier otro 422 dejaría el gasto sin forma de confirmarse.
 */
function esRechazoPorImporteAlto(error: ApiError): boolean {
  if (error.status !== 422) {
    return false;
  }
  return (
    error.problem?.['code'] === 'importe_sobre_techo' || /techo de confirmaci/i.test(error.message)
  );
}

function fechaParaElCampo(texto: string | null): string {
  // El modelo devuelve la fecha como texto libre (se le pide `AAAA-MM-DD`):
  // lo que no encaje con ese formato no se puede meter en un `input[type=date]`
  // y se trata como «no extraído», que es lo honesto.
  return texto && /^\d{4}-\d{2}-\d{2}$/.test(texto) ? texto : '';
}

function importeParaElCampo(cents: number | null): string {
  return cents === null ? '' : euros(cents);
}

/**
 * Revisión de **un** borrador: los cinco campos con su nivel de confianza, la
 * partida a la que imputar, la validación espejo de la del servidor y las dos
 * salidas posibles (confirmar, que crea el gasto, o descartar, que borra el
 * fichero para siempre).
 *
 * La validación de aquí es espejo, nunca sustituto: si el servidor rechaza
 * algo que esta validación dejó pasar, se muestra su mensaje tal cual.
 *
 * La previsualización va por `fetch` autenticado → `blob` → `objectURL` y no
 * por `<img src>`: el justificante se sirve con `Content-Disposition:
 * attachment` a propósito (un PDF admite JavaScript), así que su URL no se
 * puede incrustar. Se previsualiza la **imagen rasterizada**, que es lo que vio
 * el modelo y por tanto lo que hay que comparar.
 */
@Component({
  selector: 'app-receipt-review-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Checkbox, Dialog, Select],
  template: `
    <ng-container *transloco="let t">
      <div class="revision">
        <div class="documento">
          @if (urlPrevisualizacion(); as url) {
            <img
              [src]="url"
              [alt]="t('admin.events.accounting.justificantes.revision.previsualizacion')"
            />
          } @else if (cargandoPrevisualizacion()) {
            <p class="ayuda">
              {{ t('admin.events.accounting.justificantes.revision.cargandoPrevisualizacion') }}
            </p>
          } @else {
            <p class="ayuda">
              {{ t('admin.events.accounting.justificantes.revision.sinPrevisualizacion') }}
            </p>
          }
          <app-button variant="terciario" type="button" (pulsado)="descargarOriginal()">
            {{ t('admin.events.accounting.justificantes.revision.descargarOriginal') }}
          </app-button>
        </div>

        <form (submit)="confirmar($event)" novalidate class="formulario">
          <div class="campo">
            <label [for]="id('proveedor')">{{
              t('admin.events.accounting.justificantes.revision.proveedor')
            }}</label>
            <input
              #primerCampo
              [id]="id('proveedor')"
              type="text"
              [value]="proveedor()"
              [attr.aria-describedby]="descripcion('provider_name')"
              (input)="proveedor.set(alTexto($event))"
            />
            <p class="pista" [id]="id('proveedor') + '-pista'">
              {{ pista('provider_name', t) }}
            </p>
          </div>

          <div class="campo">
            <label [for]="id('fecha')">{{
              t('admin.events.accounting.justificantes.revision.fecha')
            }}</label>
            <input
              [id]="id('fecha')"
              type="date"
              [value]="fecha()"
              [attr.aria-describedby]="descripcion('expense_date')"
              (input)="fecha.set(alTexto($event))"
            />
            <p class="pista" [id]="id('fecha') + '-pista'">{{ pista('expense_date', t) }}</p>
          </div>

          <div class="campo">
            <label [for]="id('base')">{{
              t('admin.events.accounting.justificantes.revision.base')
            }}</label>
            <input
              [id]="id('base')"
              type="text"
              inputmode="decimal"
              [value]="base()"
              [attr.aria-describedby]="descripcion('base_cents')"
              (input)="base.set(alTexto($event))"
            />
            <p class="pista" [id]="id('base') + '-pista'">{{ pista('base_cents', t) }}</p>
          </div>

          <div class="campo">
            <label [for]="id('iva')">{{
              t('admin.events.accounting.justificantes.revision.iva')
            }}</label>
            <input
              [id]="id('iva')"
              type="text"
              inputmode="decimal"
              [value]="iva()"
              [disabled]="exento()"
              [attr.aria-describedby]="descripcion('vat_cents')"
              (input)="iva.set(alTexto($event))"
            />
            <p class="pista" [id]="id('iva') + '-pista'">{{ pista('vat_cents', t) }}</p>
          </div>

          <app-checkbox
            [fieldId]="id('exento')"
            [label]="t('admin.events.accounting.justificantes.revision.exento')"
            [(checked)]="exento"
          />

          <div class="campo">
            <label [for]="id('total')">{{
              t('admin.events.accounting.justificantes.revision.total')
            }}</label>
            <input
              [id]="id('total')"
              type="text"
              inputmode="decimal"
              [value]="total()"
              [attr.aria-describedby]="descripcion('total_cents')"
              (input)="total.set(alTexto($event))"
            />
            <p class="pista" [id]="id('total') + '-pista'">{{ pista('total_cents', t) }}</p>
          </div>

          <app-select
            [fieldId]="id('partida')"
            [label]="t('admin.events.accounting.justificantes.revision.partida')"
            [placeholder]="t('admin.events.accounting.justificantes.revision.sinPartida')"
            [options]="opcionesDePartida()"
            [(value)]="partidaId"
          />

          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          @if (importeAltoPendiente()) {
            <app-alert
              tone="error"
              [title]="t('admin.events.accounting.justificantes.revision.importeAlto.titulo')"
            >
              <p class="importe-alto-texto">
                {{ t('admin.events.accounting.justificantes.revision.importeAlto.texto') }}
              </p>
              <p class="importe-alto">{{ totalConfirmable() }} €</p>
              <p class="importe-alto-texto">
                {{ t('admin.events.accounting.justificantes.revision.importeAlto.aviso') }}
              </p>
              <div class="acciones">
                <app-button
                  #botonImporteAlto
                  variant="peligro"
                  type="button"
                  [loading]="enviando()"
                  (pulsado)="confirmarImporteAlto()"
                >
                  {{ t('admin.events.accounting.justificantes.revision.importeAlto.confirmar') }}
                </app-button>
                <app-button
                  variant="secundario"
                  type="button"
                  (pulsado)="importeAltoPendiente.set(false)"
                >
                  {{ t('admin.events.accounting.justificantes.revision.importeAlto.cancelar') }}
                </app-button>
              </div>
            </app-alert>
          }

          <div class="acciones">
            <app-button type="submit" [loading]="enviando()">
              {{ t('admin.events.accounting.justificantes.revision.confirmar') }}
            </app-button>
            <app-button variant="peligro" type="button" (pulsado)="pedirDescarte()">
              {{ t('admin.events.accounting.justificantes.revision.descartar') }}
            </app-button>
          </div>
        </form>
      </div>

      <app-dialog #dialogoDescarte>
        <div class="dialogo-cuerpo">
          <h4>{{ t('admin.events.accounting.justificantes.revision.descarte.titulo') }}</h4>
          <p>{{ t('admin.events.accounting.justificantes.revision.descarte.texto') }}</p>
        </div>
        <app-button pie variant="secundario" type="button" (pulsado)="cerrarDescarte()">
          {{ t('admin.events.accounting.justificantes.revision.descarte.cancelar') }}
        </app-button>
        <app-button
          pie
          variant="peligro"
          type="button"
          [loading]="enviando()"
          (pulsado)="descartar()"
        >
          {{ t('admin.events.accounting.justificantes.revision.descarte.confirmar') }}
        </app-button>
      </app-dialog>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .revision {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: var(--space-md);
    }
    @media (min-width: 60rem) {
      .revision {
        grid-template-columns: minmax(0, 18rem) minmax(0, 1fr);
      }
    }
    .documento {
      display: grid;
      gap: var(--space-sm);
      align-content: start;
    }
    .documento img {
      max-width: 100%;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      max-width: 34rem;
    }
    .campo {
      display: grid;
      gap: var(--space-xs);
    }
    label {
      font-weight: 600;
    }
    /* Igual que en \`expense-form.ts\`: no hay regla global para \`input\` en
     * \`styles.css\`, así que sin borde ni fondo los campos serían invisibles
     * sobre el tema oscuro. */
    input {
      box-sizing: border-box;
      width: 100%;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
      color: var(--fg);
      font: inherit;
      min-height: 2.75rem;
    }
    input:focus-visible {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent);
    }
    input:disabled {
      opacity: 0.6;
    }
    .pista,
    .ayuda {
      margin: 0;
      font-size: 0.8125rem;
      color: var(--muted);
    }
    .acciones {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    .importe-alto {
      margin: 0;
      font-size: 1.75rem;
      font-weight: 700;
    }
    .importe-alto-texto {
      margin: 0;
    }
    .dialogo-cuerpo {
      display: grid;
      gap: var(--space-sm);
    }
    .dialogo-cuerpo h4,
    .dialogo-cuerpo p {
      margin: 0;
    }
  `,
})
export class ReceiptReviewForm {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly destroyRef = inject(DestroyRef);

  readonly draft = input.required<ReceiptDraft>();
  readonly partidas = input.required<readonly PartidaParaGasto[]>();
  /** La bandeja lo pone en el borrador que acaba de quedar listo, para que el
   * foco vaya al primer campo sin que la persona tenga que buscarlo. */
  readonly enfocar = input(false);

  /** Aviso ya traducido de que el gasto se ha creado. */
  readonly confirmado = output<string>();
  /** Aviso ya traducido de que el justificante se ha descartado. */
  readonly descartado = output<string>();

  protected readonly proveedor = signal('');
  protected readonly fecha = signal('');
  protected readonly base = signal('');
  protected readonly iva = signal('');
  protected readonly total = signal('');
  protected readonly exento = signal(false);
  protected readonly partidaId = signal('');

  protected readonly enviando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly importeAltoPendiente = signal(false);

  protected readonly urlPrevisualizacion = signal<string | null>(null);
  protected readonly cargandoPrevisualizacion = signal(false);

  /** Campos que llegaron sin valor (confianza baja, o texto que no se puede
   * usar): se presentan como «no extraído, rellénalo», nunca como un hueco
   * vacío indistinguible de uno que el modelo sí leyó en blanco. */
  private readonly sinExtraer = signal<ReadonlySet<CampoRevisable>>(new Set());

  private readonly primerCampo = viewChild<ElementRef<HTMLInputElement>>('primerCampo');
  private readonly botonImporteAlto = viewChild('botonImporteAlto', { read: ElementRef });
  private readonly dialogoDescarte = viewChild.required<Dialog>('dialogoDescarte');

  /** La identidad del borrador que se está revisando. Cambia solo al cambiar
   * de borrador, no cuando la bandeja reemplaza el objeto por otro igual. */
  private readonly idDelBorrador = computed(() => this.draft().id);

  protected readonly opcionesDePartida = computed<SelectOption[]>(() =>
    this.partidas().map((partida) => ({ value: partida.id, label: partida.name })),
  );

  /** El total que se enviaría ahora mismo, para enseñarlo en grande en la
   * segunda confirmación. */
  protected readonly totalConfirmable = computed(() => {
    const cents = aCents(this.total());
    return cents === null ? '0.00' : euros(cents);
  });

  constructor() {
    // Solo al cambiar de borrador, nunca en cada emisión del input: la bandeja
    // reconstruye el listado en cada pasada de su *polling*, y rellenar otra
    // vez borraría lo que la persona esté corrigiendo en ese momento.
    effect(() => {
      this.idDelBorrador();
      untracked(() => this.rellenarDesdeElBorrador(this.draft()));
    });
    effect(() => {
      if (this.enfocar()) {
        this.primerCampo()?.nativeElement.focus();
      }
    });
    effect(() => {
      // La clave es un `computed`: mientras devuelva la misma cadena no
      // notifica, así que la previsualización no se revoca ni se vuelve a
      // descargar por una pasada de *polling* que no cambió nada.
      const clave = this.claveDePrevisualizacion();
      // `untracked`: la carga lee y escribe `urlPrevisualizacion`, y sin esto
      // el propio efecto se volvería a disparar con su escritura.
      untracked(() => void this.cargarPrevisualizacion(clave));
    });
    // El foco va a la segunda confirmación en cuanto aparece: sin esto, quien
    // navega con teclado no se entera de que el envío no ha pasado.
    effect(() => {
      if (this.importeAltoPendiente()) {
        this.botonImporteAlto()?.nativeElement.querySelector('button')?.focus();
      }
    });
    this.destroyRef.onDestroy(() => this.liberarPrevisualizacion());
  }

  protected id(sufijo: string): string {
    return `draft-${this.draft().id}-${sufijo}`;
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  protected descripcion(campo: CampoRevisable): string {
    return `${this.id(this.sufijoDeCampo(campo))}-pista`;
  }

  /** Texto bajo el campo: o «no extraído, rellénalo», o el nivel de confianza.
   * Nunca un porcentaje — el contrato solo tiene tres niveles. */
  protected pista(campo: CampoRevisable, t: (clave: string) => string): string {
    const base = 'admin.events.accounting.justificantes.revision.';
    if (this.sinExtraer().has(campo)) {
      return t(`${base}noExtraido`);
    }
    const nivel = this.draft().field_confidence[campo] ?? 'baja';
    return t(`${base}${this.claveDeConfianza(nivel)}`);
  }

  private claveDeConfianza(nivel: NivelDeConfianza): string {
    if (nivel === 'alta') return 'confianzaAlta';
    return nivel === 'media' ? 'confianzaMedia' : 'confianzaBaja';
  }

  private sufijoDeCampo(campo: CampoRevisable): string {
    switch (campo) {
      case 'provider_name':
        return 'proveedor';
      case 'expense_date':
        return 'fecha';
      case 'base_cents':
        return 'base';
      case 'vat_cents':
        return 'iva';
      default:
        return 'total';
    }
  }

  private rellenarDesdeElBorrador(borrador: ReceiptDraft): void {
    const campos: CamposExtraidos = borrador.extracted_fields;
    const proveedor = campos.provider_name ?? '';
    const fecha = fechaParaElCampo(campos.expense_date);
    const base = importeParaElCampo(campos.base_cents);
    const iva = importeParaElCampo(campos.vat_cents);
    const total = importeParaElCampo(campos.total_cents);

    this.proveedor.set(proveedor);
    this.fecha.set(fecha);
    this.base.set(base);
    this.iva.set(iva);
    this.total.set(total);
    this.exento.set(false);
    this.partidaId.set('');
    this.error.set(null);
    this.importeAltoPendiente.set(false);

    const vacios = new Map<CampoRevisable, string>([
      ['provider_name', proveedor],
      ['expense_date', fecha],
      ['base_cents', base],
      ['vat_cents', iva],
      ['total_cents', total],
    ]);
    this.sinExtraer.set(new Set(CAMPOS.filter((campo) => !vacios.get(campo))));
  }

  // --- Previsualización -----------------------------------------------------

  /** La rasterizada si la hay (es lo que vio el modelo); si no, el original,
   * y solo cuando es una imagen: un PDF no se pinta en un `<img>`. */
  private readonly claveDePrevisualizacion = computed<string | null>(() => {
    const borrador = this.draft();
    if (borrador.rasterized_object_key) {
      return borrador.rasterized_object_key;
    }
    const extension = borrador.receipt_object_key.split('.').pop()?.toLowerCase() ?? '';
    return EXTENSIONES_DE_IMAGEN.includes(extension) ? borrador.receipt_object_key : null;
  });

  private async cargarPrevisualizacion(clave: string | null): Promise<void> {
    this.liberarPrevisualizacion();
    if (clave === null) {
      return;
    }
    this.cargandoPrevisualizacion.set(true);
    try {
      const blob = await this.descargar(clave);
      this.urlPrevisualizacion.set(URL.createObjectURL(blob));
    } catch {
      // La previsualización es una comodidad, no el dato: si falla (o el
      // entorno no sabe crear object URLs), se revisa igual con el enlace de
      // descarga del original.
      this.urlPrevisualizacion.set(null);
    } finally {
      this.cargandoPrevisualizacion.set(false);
    }
  }

  private liberarPrevisualizacion(): void {
    const url = this.urlPrevisualizacion();
    if (url !== null) {
      URL.revokeObjectURL(url);
      this.urlPrevisualizacion.set(null);
    }
  }

  private descargar(clave: string): Promise<Blob> {
    return firstValueFrom(
      this.http.get(this.api.url(`/accounting/receipts/${clave}`), { responseType: 'blob' }),
    );
  }

  /** El original se sirve con `Content-Disposition: attachment` y solo por
   * endpoint autenticado, así que no vale un `<a href>`: se descarga con la
   * sesión puesta y se entrega como fichero, igual que el export del libro. */
  protected async descargarOriginal(): Promise<void> {
    this.error.set(null);
    const clave = this.draft().receipt_object_key;
    try {
      const blob = await this.descargar(clave);
      const url = URL.createObjectURL(blob);
      const enlace = document.createElement('a');
      enlace.href = url;
      enlace.download = clave.split('/').pop() ?? 'justificante';
      enlace.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      this.error.set(this.mensajeDeError(error));
    }
  }

  // --- Confirmación ---------------------------------------------------------

  protected confirmar(evento: SubmitEvent): void {
    evento.preventDefault();
    void this.enviarConfirmacion(false);
  }

  protected confirmarImporteAlto(): void {
    void this.enviarConfirmacion(true);
  }

  private async enviarConfirmacion(confirmarImporteAlto: boolean): Promise<void> {
    this.error.set(null);
    const cuerpo = this.cuerpoValidado();
    if (cuerpo === null) {
      return;
    }

    this.enviando.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/accounting/expense-drafts/${this.draft().id}/confirm`), {
          ...cuerpo,
          confirmar_importe_alto: confirmarImporteAlto,
        }),
      );
      this.importeAltoPendiente.set(false);
      this.confirmado.emit(
        this.transloco.translate('admin.events.accounting.justificantes.revision.confirmado'),
      );
    } catch (error) {
      if (error instanceof ApiError && esRechazoPorImporteAlto(error)) {
        this.importeAltoPendiente.set(true);
        return;
      }
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.enviando.set(false);
    }
  }

  /**
   * Las mismas cinco validaciones que aplica el alta manual, espejo de las del
   * servidor. Devuelve `null` —y deja el mensaje puesto— cuando no pasa.
   */
  private cuerpoValidado(): Record<string, unknown> | null {
    const base = 'admin.events.accounting.justificantes.revision.';
    const proveedor = this.proveedor().trim();
    const fecha = this.fecha();
    const baseCents = aCents(this.base());
    const ivaCents = this.exento() ? null : (aCents(this.iva()) ?? 0);
    const totalCents = aCents(this.total());

    if (!proveedor) {
      return this.rechazar(`${base}proveedorRequerido`);
    }
    if (!fecha) {
      return this.rechazar(`${base}fechaRequerida`);
    }
    if (baseCents === null || baseCents < 0) {
      return this.rechazar(`${base}baseInvalida`);
    }
    if (ivaCents !== null && ivaCents < 0) {
      return this.rechazar(`${base}ivaInvalido`);
    }
    if (totalCents === null || totalCents < 0) {
      return this.rechazar(`${base}totalInvalido`);
    }
    const esperado = baseCents + (ivaCents ?? 0);
    if (totalCents !== esperado) {
      return this.rechazar(`${base}totalNoCuadra`, { esperado: euros(esperado) });
    }

    return {
      budget_line_id: this.partidaId() || null,
      provider_name: proveedor,
      expense_date: new Date(fecha).toISOString(),
      base_cents: baseCents,
      vat_cents: ivaCents,
      total_cents: totalCents,
    };
  }

  private rechazar(clave: string, parametros?: Record<string, unknown>): null {
    this.error.set(this.transloco.translate(clave, parametros));
    return null;
  }

  // --- Descarte -------------------------------------------------------------

  protected pedirDescarte(): void {
    this.dialogoDescarte().abrir();
  }

  protected cerrarDescarte(): void {
    this.dialogoDescarte().cerrar();
  }

  protected async descartar(): Promise<void> {
    this.error.set(null);
    this.enviando.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/accounting/expense-drafts/${this.draft().id}/discard`), {}),
      );
      this.cerrarDescarte();
      this.descartado.emit(
        this.transloco.translate('admin.events.accounting.justificantes.revision.descartado'),
      );
    } catch (error) {
      this.cerrarDescarte();
      this.error.set(this.mensajeDeError(error));
    } finally {
      this.enviando.set(false);
    }
  }

  private mensajeDeError(error: unknown): string {
    return error instanceof ApiError
      ? error.message
      : this.transloco.translate('admin.events.accounting.error');
  }
}
