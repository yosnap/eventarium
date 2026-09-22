import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  model,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ModeloDelCatalogoOut } from '../../../core/api/generated/models/modelo-del-catalogo-out';
import { ProveedorDelCatalogoOut } from '../../../core/api/generated/models/proveedor-del-catalogo-out';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Select, type SelectOption } from '../../../shared/ui/select';
import { AiCatalogService } from './ai-catalog.service';

/** Resultado de la última prueba de conexión, tal y como lo pinta el aviso. */
interface ResultadoDePrueba {
  ok: boolean;
  /** Código de dominio del fallo; `null` si fue bien. */
  motivo: string | null;
}

/**
 * Los campos de credencial que comparten el panel de la plataforma y el del
 * organizador: proveedor, modelo, dirección y clave.
 *
 * Existe para que los dos paneles no puedan divergir en lo que más importa
 * aquí: qué proveedores hay, qué modelos acepta cada uno, cuáles aceptan
 * imágenes y cuándo el gasto deja de ser auditable. Todo eso sale del catálogo
 * del backend (`GET /ai/catalog`), que el componente recibe ya cargado.
 *
 * La clave **nunca** se rellena: aunque el nivel correspondiente ya tenga una
 * guardada, el campo sale vacío y solo se muestra que existe y la pista de sus
 * últimos caracteres. Dejarlo en blanco al guardar conserva la que había.
 *
 * Los **modelos** no salen del catálogo cerrado sino de lo que el proveedor
 * declara ahora mismo (`GET /ai/catalog/{provider}/models`): al elegir
 * proveedor se piden en vivo. Si el backend no ha podido consultarlo devuelve
 * la última lista conocida marcada con `en_vivo: false`, y aquí se avisa sin
 * bloquear nada — la lista sigue siendo utilizable, solo puede estar
 * incompleta.
 *
 * El botón «Probar conexión» comprueba la clave **escrita en el formulario**,
 * que puede no estar guardada todavía. Usa el mismo listado de modelos como
 * prueba, así que no gasta cuota de generación; cuando va bien, sus modelos
 * sustituyen a los del desplegable, que es la única forma de elegir modelo con
 * una clave recién escrita.
 */
@Component({
  selector: 'app-ai-config-fields',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Select],
  template: `
    <ng-container *transloco="let t">
      <div class="campos">
        <app-select
          [fieldId]="idDe('proveedor')"
          [label]="t('admin.ia.campos.proveedor')"
          [placeholder]="t('admin.ia.campos.elegirProveedor')"
          [options]="opcionesDeProveedor()"
          [disabled]="disabled()"
          [(value)]="provider"
        />

        @if (proveedorElegido(); as elegido) {
          @if (elegido.modelos_abiertos) {
            <div class="campo">
              <label [for]="idDe('modelo-libre')">{{ t('admin.ia.campos.modelo') }}</label>
              <input
                [id]="idDe('modelo-libre')"
                type="text"
                autocomplete="off"
                [disabled]="disabled()"
                [attr.aria-describedby]="idDe('modelo-libre-ayuda')"
                [value]="defaultModel()"
                (input)="defaultModel.set(alTexto($event))"
              />
              <p class="ayuda" [id]="idDe('modelo-libre-ayuda')">
                {{ t('admin.ia.campos.modeloLibreAyuda') }}
              </p>
            </div>
          } @else {
            <app-select
              [fieldId]="idDe('modelo')"
              [label]="t('admin.ia.campos.modelo')"
              [placeholder]="t('admin.ia.campos.elegirModelo')"
              [options]="opcionesDeModelo()"
              [disabled]="disabled() || cargandoModelos()"
              [hint]="t('admin.ia.campos.modeloAyuda')"
              [(value)]="defaultModel"
            />
            <!-- Estado en vivo, anunciado: el desplegable cambia de contenido
                 sin que se mueva el foco. -->
            <p class="ayuda" role="status">
              @if (cargandoModelos()) {
                {{ t('admin.ia.campos.cargandoModelos') }}
              } @else if (motivoDeFallback(); as motivo) {
                {{ t('admin.ia.campos.catalogoNoEnVivo', { motivo: textoDeMotivo(motivo) }) }}
              }
            </p>
          }

          @if (elegido.api_base_editable) {
            <div class="campo">
              <label [for]="idDe('api-base')">{{ t('admin.ia.campos.apiBase') }}</label>
              <input
                [id]="idDe('api-base')"
                type="url"
                autocomplete="off"
                inputmode="url"
                [disabled]="disabled()"
                [value]="apiBase()"
                (input)="apiBase.set(alTexto($event))"
              />
            </div>
          } @else if (elegido.api_base_fijo) {
            <p class="informativo">
              {{ t('admin.ia.campos.apiBaseFija', { direccion: elegido.api_base_fijo }) }}
            </p>
          }
        }

        <div class="campo">
          <label [for]="idDe('clave')">{{ t('admin.ia.campos.clave') }}</label>
          <input
            [id]="idDe('clave')"
            type="password"
            autocomplete="off"
            [disabled]="disabled()"
            [attr.aria-describedby]="idDe('clave-ayuda')"
            [placeholder]="marcadorDeClave()"
            [value]="apiKey()"
            (input)="apiKey.set(alTexto($event))"
          />
          <p class="ayuda" [id]="idDe('clave-ayuda')">{{ textoDeLaClave() }}</p>

          <div class="prueba">
            <app-button
              variant="secundario"
              [compacto]="true"
              [disabled]="!sePuedeProbar()"
              [loading]="probando()"
              (pulsado)="probarConexion()"
            >
              {{ t('admin.ia.campos.probarConexion') }}
            </app-button>
            <span class="ayuda">{{ t('admin.ia.campos.probarConexionAyuda') }}</span>
          </div>

          <!-- Se usa el aviso del sistema de diseño y no un texto de color: el
               resultado no puede depender solo del color para distinguirse. -->
          @if (resultado(); as prueba) {
            @if (prueba.ok) {
              <app-alert tone="exito" [title]="t('admin.ia.campos.conexionCorrectaTitulo')">
                {{ t('admin.ia.campos.conexionCorrecta') }}
              </app-alert>
            } @else {
              <app-alert tone="error" [title]="t('admin.ia.campos.conexionFallidaTitulo')">
                {{ textoDeMotivo(prueba.motivo) }}
              </app-alert>
            }
          }
        </div>

        @if (avisoDeVision()) {
          <app-alert tone="info" [title]="t('admin.ia.avisos.sinVisionTitulo')">
            {{ t('admin.ia.avisos.sinVision') }}
          </app-alert>
        }
        @if (avisoDeCoste()) {
          <app-alert tone="info" [title]="t('admin.ia.avisos.costeNoAuditableTitulo')">
            {{ t('admin.ia.avisos.costeNoAuditable') }}
          </app-alert>
        }
      </div>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .campos {
      display: grid;
      gap: var(--space-md);
    }
    .campo {
      display: grid;
      gap: var(--space-sm);
    }
    label {
      font-weight: 600;
    }
    /* No hay regla global para \`input\` en \`styles.css\`: sin esto, los campos
       serían invisibles sobre el tema oscuro (misma corrección que en
       \`expense-form.ts\`). */
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
      opacity: 0.65;
      cursor: not-allowed;
    }
    .ayuda,
    .informativo {
      color: var(--muted);
      font-size: var(--fs-sm);
      margin: 0;
    }
    .prueba {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: var(--space-sm) var(--space-md);
    }
  `,
})
export class AiConfigFields {
  private readonly transloco = inject(TranslocoService);
  private readonly catalogoDeIa = inject(AiCatalogService);

  /** El catálogo cerrado ya cargado por la pantalla que aloja el formulario. */
  readonly catalogo = input.required<readonly ProveedorDelCatalogoOut[]>();
  /** Prefijo de los `id` del formulario: los dos paneles usan el componente. */
  readonly idPrefijo = input.required<string>();
  /** `true` si el nivel que se edita ya tiene una clave guardada. */
  readonly hasKey = input(false);
  /**
   * Últimos caracteres de la clave **propia** de este nivel. Llega a `null` en
   * la vista heredada del organizador: la pista de la clave de plataforma no
   * se enseña a ninguna organización (V-11).
   */
  readonly apiKeyHint = input<string | null>(null);
  /**
   * El proveedor de la clave YA guardada de este nivel, o `null` si no hay
   * ninguna. Distinto de `provider` (el del formulario, que la persona
   * puede cambiar antes de guardar): sirve para saber si «Probar conexión»
   * con el campo de clave vacío puede usar la guardada — solo tiene sentido
   * si sigue siendo la del mismo proveedor que se está probando.
   */
  readonly savedProvider = input<string | null>(null);
  readonly disabled = input(false);

  readonly provider = model('');
  readonly defaultModel = model('');
  readonly apiBase = model('');
  readonly apiKey = model('');

  /**
   * Modelos declarados por el proveedor. `null` mientras no se sepan: ahí el
   * desplegable usa los del catálogo cerrado, que es la última lista conocida.
   */
  readonly modelosEnVivo = signal<readonly ModeloDelCatalogoOut[] | null>(null);
  readonly cargandoModelos = signal(false);
  /**
   * Por qué el backend no pudo consultar al proveedor, o `null` si sí pudo.
   * Solo cambia el aviso: la lista se pinta igual.
   */
  readonly motivoDeFallback = signal<string | null>(null);
  readonly probando = signal(false);
  readonly resultado = signal<ResultadoDePrueba | null>(null);

  /**
   * Cambiar de proveedor invalida todo lo que se sabía del anterior: sus
   * modelos, el aviso de fallback y el resultado de la última prueba. Sin
   * esto, el desplegable enseñaría los modelos de un proveedor bajo el nombre
   * de otro.
   */
  constructor() {
    effect(() => {
      const proveedor = this.provider();
      this.modelosEnVivo.set(null);
      this.motivoDeFallback.set(null);
      this.resultado.set(null);
      if (proveedor) {
        void this.cargarModelos(proveedor);
      }
    });
  }

  private async cargarModelos(proveedor: string): Promise<void> {
    this.cargandoModelos.set(true);
    try {
      const respuesta = await this.catalogoDeIa.modelosDe(proveedor);
      // El proveedor pudo cambiar mientras la petición estaba en vuelo: sin
      // esta comprobación, una respuesta lenta pisaría la lista de otro.
      if (this.provider() !== proveedor) {
        return;
      }
      this.modelosEnVivo.set(respuesta.modelos);
      this.motivoDeFallback.set(respuesta.en_vivo ? null : (respuesta.motivo ?? 'proveedor_error'));
    } catch {
      // La petición en sí falló (sesión caducada, límite de peticiones). No es
      // un aviso que aporte nada aquí: el desplegable se queda con el catálogo
      // cerrado, que es exactamente lo que había antes de este endpoint.
      if (this.provider() === proveedor) {
        this.modelosEnVivo.set(null);
      }
    } finally {
      if (this.provider() === proveedor) {
        this.cargandoModelos.set(false);
      }
    }
  }

  /**
   * `true` si hay una clave guardada de este nivel para el proveedor
   * elegido AHORA MISMO en el formulario — no basta con `hasKey()`: si la
   * persona cambia de proveedor sin escribir una clave nueva, la guardada
   * es de otro proveedor y no sirve para probar este.
   */
  protected readonly puedeUsarLaClaveGuardada = computed(
    () => this.hasKey() && this.provider().trim() === (this.savedProvider() ?? ''),
  );

  /**
   * Asteriscos en el propio campo cuando hay clave guardada para este
   * proveedor y no se ha escrito ninguna nueva: antes solo lo decía el
   * texto de ayuda de debajo, y de un vistazo el campo vacío podía parecer
   * "no hay nada guardado" (hallazgo del usuario).
   */
  protected readonly marcadorDeClave = computed(() =>
    this.puedeUsarLaClaveGuardada() && !this.apiKey().trim() ? '••••••••' : '',
  );

  /**
   * Probar exige proveedor y, o bien una clave escrita, o bien una ya
   * guardada de ESE MISMO proveedor (`puedeUsarLaClaveGuardada`) — antes el
   * botón se quedaba deshabilitado con el campo vacío aunque ya hubiera una
   * clave guardada, y comprobar que seguía siendo válida exigía volver a
   * escribirla (hallazgo del usuario). La dirección del endpoint solo hace
   * falta si se escribe una clave nueva: si se usa la guardada, el backend
   * cae al `api_base` que ya tiene guardado.
   */
  protected readonly sePuedeProbar = computed(() => {
    if (this.disabled() || this.probando()) {
      return false;
    }
    const elegido = this.proveedorElegido();
    if (elegido === null) {
      return false;
    }
    const claveEscrita = this.apiKey().trim().length > 0;
    if (!claveEscrita && !this.puedeUsarLaClaveGuardada()) {
      return false;
    }
    if (claveEscrita && elegido.api_base_editable) {
      return this.apiBase().trim().length > 0;
    }
    return true;
  });

  /**
   * Comprueba la clave del formulario contra el proveedor — o, con el campo
   * vacío, la ya guardada de ese mismo proveedor. Cuando va bien, sus
   * modelos pasan a ser los del desplegable: son los que esa clave ve.
   */
  async probarConexion(): Promise<void> {
    if (!this.sePuedeProbar()) {
      return;
    }
    const proveedor = this.provider().trim();
    const direccion = this.apiBase().trim();
    const clave = this.apiKey().trim();
    this.probando.set(true);
    this.resultado.set(null);
    try {
      const respuesta = await this.catalogoDeIa.probar({
        provider: proveedor,
        ...(clave ? { apiKey: clave } : {}),
        ...(direccion ? { apiBase: direccion } : {}),
      });
      if (this.provider().trim() !== proveedor) {
        return;
      }
      this.resultado.set({ ok: respuesta.ok, motivo: respuesta.motivo ?? null });
      if (respuesta.ok) {
        this.modelosEnVivo.set(respuesta.modelos);
        this.motivoDeFallback.set(null);
      }
    } catch {
      this.resultado.set({ ok: false, motivo: null });
    } finally {
      this.probando.set(false);
    }
  }

  /** Traduce un código de motivo; los desconocidos caen a un texto genérico. */
  protected textoDeMotivo(motivo: string | null): string {
    const clave = `admin.ia.motivos.${motivo ?? 'desconocido'}`;
    const texto = this.transloco.translate(clave);
    return texto === clave ? this.transloco.translate('admin.ia.motivos.desconocido') : texto;
  }

  /**
   * Qué se dice bajo el campo de clave. Tres estados, nunca el valor: no hay
   * clave todavía, hay una y se conocen sus últimos caracteres, o hay una
   * heredada de la plataforma cuya pista no se enseña (V-11).
   */
  protected readonly textoDeLaClave = computed(() => {
    if (!this.hasKey()) {
      return this.transloco.translate('admin.ia.campos.claveAyudaSinClave');
    }
    const pista = this.apiKeyHint();
    return pista
      ? this.transloco.translate('admin.ia.campos.claveAyudaConPista', { pista })
      : this.transloco.translate('admin.ia.campos.claveAyudaGuardada');
  });

  protected readonly proveedorElegido = computed<ProveedorDelCatalogoOut | null>(
    () => this.catalogo().find((entrada) => entrada.clave === this.provider()) ?? null,
  );

  protected readonly opcionesDeProveedor = computed<SelectOption[]>(() =>
    this.catalogo().map((entrada) => ({ value: entrada.clave, label: entrada.etiqueta })),
  );

  /**
   * Los modelos que se pueden elegir: los declarados por el proveedor si ya se
   * conocen, y si no los del catálogo cerrado.
   */
  protected readonly modelosDisponibles = computed<readonly ModeloDelCatalogoOut[]>(
    () => this.modelosEnVivo() ?? this.proveedorElegido()?.modelos ?? [],
  );

  /** Los modelos disponibles, marcando cuáles aceptan imágenes. */
  protected readonly opcionesDeModelo = computed<SelectOption[]>(() => {
    const elegido = this.proveedorElegido();
    if (!elegido) {
      return [];
    }
    return this.modelosDisponibles().map((modelo) => ({
      value: modelo.clave,
      label: modelo.vision
        ? `${modelo.etiqueta} · ${this.transloco.translate('admin.ia.campos.conVision')}`
        : modelo.etiqueta,
    }));
  });

  /**
   * Aviso de modelo sin visión: el OCR de justificantes manda la factura como
   * imagen, así que un modelo que no las acepta deja esa función inservible.
   * En un proveedor de modelo abierto no se avisa: no se sabe qué acepta.
   */
  protected readonly avisoDeVision = computed(() => {
    const elegido = this.proveedorElegido();
    if (!elegido || elegido.modelos_abiertos) {
      return false;
    }
    const modelo = this.modelosDisponibles().find(
      (entrada) => entrada.clave === this.defaultModel(),
    );
    return modelo !== undefined && !modelo.vision;
  });

  /** Gasto no auditable: el proveedor está fuera del mapa de precios. */
  protected readonly avisoDeCoste = computed(() => {
    const elegido = this.proveedorElegido();
    return elegido !== null && !elegido.coste_auditable;
  });

  protected idDe(sufijo: string): string {
    return `${this.idPrefijo()}-${sufijo}`;
  }

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }
}
