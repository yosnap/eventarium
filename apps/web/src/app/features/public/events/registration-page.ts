import { DatePipe, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PLATFORM_ID,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import {
  type CheckoutQuote,
  type PublicTicketType,
  PublicCheckoutService,
} from '../../../core/payments/public-checkout.service';
import {
  type RegistrationAnswerInput,
  type RegistrationQuestion,
  RegistrationsService,
} from '../../../core/registrations/registrations.service';
import { Alert } from '../../../shared/ui/alert';
import { Breadcrumb, type BreadcrumbItem } from '../../../shared/ui/breadcrumb';
import { Button } from '../../../shared/ui/button';
import { Checkbox } from '../../../shared/ui/checkbox';
import { ErrorSummary, type ResumenDeError } from '../../../shared/ui/error-summary';
import { Input } from '../../../shared/ui/input';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';
import type { PublicEventDetail, RegistrationMode } from './event-page.types';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function precioEnEuros(cents: number): string {
  return (cents / 100).toFixed(2);
}

/**
 * Formulario público de inscripción a un evento (fase 3 del PRD; paso de
 * compra añadido en la fase 6 del PRD, fase 4 de trabajo).
 *
 * CSR, como `registro`: es un flujo transaccional. Las preguntas
 * personalizadas se cargan primero (`ngOnInit`) porque su forma decide qué
 * campos mostrar — un enfoque «formulario fijo + JSON suelto» no sirve aquí,
 * cada evento puede definir preguntas distintas.
 *
 * La respuesta de alta es siempre la misma exista o no ya el email inscrito
 * (anti-enumeración, igual que `registro`): el mensaje de éxito nunca dice
 * "ya estabas inscrito" ni "te hemos inscrito", dice lo mismo en ambos casos.
 *
 * **Paso de compra:** `ngOnInit` también pide los tipos de entrada vendibles
 * ahora mismo (`GET /public/events/{slug}/ticket-types`). Un evento es «de
 * pago» a ojos de este formulario si y solo si esa lista no está vacía — no
 * hace falta preguntar por `registration_mode` aparte, y evita duplicar la
 * misma condición en dos sitios. Si hay tipos, el envío pasa por
 * `PublicCheckoutService.startCheckout` (dos transacciones en el servidor,
 * ver `checkout_service.py`) en vez de `RegistrationsService.submit`, y una
 * `checkout_url` no nula redirige el navegador — **nunca** en SSR
 * (`esNavegador`, mismo patrón que `event-check-in.ts`/
 * `offline-scan-queue.service.ts`): en el servidor no hay `window` al que
 * redirigir, y ningún envío real puede ocurrir ahí de todos modos porque el
 * `submit` solo lo dispara un evento de navegador.
 */
@Component({
  selector: 'app-registration-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    TranslocoDirective,
    RouterLink,
    Alert,
    Breadcrumb,
    Button,
    Checkbox,
    ErrorSummary,
    Input,
    Reveal,
    TurnstileWidget,
  ],
  template: `
    <ng-container *transloco="let t">
      <div class="pagina">
        @if (evento(); as evento) {
          <div class="ancho-maximo">
            <app-breadcrumb [items]="migasDePan(evento)" [ariaLabel]="t('publico.eventos.ruta')" />
          </div>
        }
        <div class="ancho-maximo layout" appReveal>
          <div>
            @if (cargandoPreguntas()) {
              <p>{{ t('comun.cargando') }}</p>
            } @else if (noEncontrado()) {
              <app-alert tone="error">{{ t('publico.eventos.noEncontrado') }}</app-alert>
            } @else {
              <!-- Pasos de la referencia (inscripcion.html:55-59): mono, mayúsculas,
                 con conector entre etiquetas, fuera y antes de cualquier título —
                 no dentro de una tarjeta. Las etiquetas y su número dependen del
                 modo de inscripción — gratis/aprobación no pasan por pago, y pago no
                 pasa por revisión manual. -->
              <ol class="pasos" [attr.aria-label]="t('inscripcion.pasos.rotulo')">
                @for (etiqueta of etiquetasPasos(t); track $index) {
                  <li [attr.data-estado]="estadoPaso($index)">{{ $index + 1 }} · {{ etiqueta }}</li>
                }
              </ol>

              <!-- Subtítulo mono + h1 de la referencia (inscripcion.html:63-64):
                 la etiqueta "Inscripción" seguida del titular, sin tarjeta
                 alrededor — la tarjeta de la referencia es solo el resumen de
                 la derecha. -->
              <span class="rotulo-seccion">{{ t('inscripcion.rotulo') }}</span>
              <h1>{{ tituloPaso(t) }}</h1>

              @if (enviado()) {
                <app-alert tone="exito" [title]="t('inscripcion.exitoTitulo')">
                  {{ mensajeExito() }}
                </app-alert>
              } @else {
                <p class="explicacion">{{ textoModo(t) }}</p>

                <form (submit)="enviar($event)" novalidate>
                  <app-error-summary
                    [errores]="resumenErrores()"
                    [titulo]="t('comun.corrigeErrores')"
                  />

                  <!-- .row2 de la referencia (inscripcion.html:69-78): los campos
                     cortos van de dos en dos, no cada uno en su propia fila. -->
                  <div class="fila-doble">
                    <app-input
                      fieldId="insc-email"
                      [label]="t('inscripcion.email')"
                      type="email"
                      autocomplete="email"
                      [required]="true"
                      [error]="errorEmail()"
                      [(value)]="email"
                      (blurred)="validarEmail()"
                    />
                    <app-input
                      fieldId="insc-nombre"
                      [label]="t('inscripcion.nombre')"
                      autocomplete="name"
                      [required]="true"
                      [error]="errorNombre()"
                      [(value)]="fullName"
                      (blurred)="validarNombre()"
                    />
                  </div>

                  @for (pregunta of preguntas(); track pregunta.id) {
                    <div class="pregunta">
                      @switch (pregunta.type) {
                        @case ('short_text') {
                          <app-input
                            [fieldId]="'insc-pregunta-' + pregunta.id"
                            [label]="etiquetaConObligatoria(pregunta)"
                            [required]="pregunta.required"
                            [error]="erroresPreguntas()[pregunta.id] ?? null"
                            [value]="valorTexto(pregunta.id)"
                            (valueChange)="fijarTexto(pregunta.id, $event)"
                          />
                        }
                        @case ('single_choice') {
                          <fieldset [id]="'insc-pregunta-' + pregunta.id" tabindex="-1">
                            <legend>{{ etiquetaConObligatoria(pregunta) }}</legend>
                            @for (opcion of pregunta.options ?? []; track opcion) {
                              <label class="opcion">
                                <input
                                  type="radio"
                                  [name]="'pregunta-' + pregunta.id"
                                  [value]="opcion"
                                  [checked]="valorTexto(pregunta.id) === opcion"
                                  (change)="fijarTexto(pregunta.id, opcion)"
                                />
                                {{ opcion }}
                              </label>
                            }
                            @if (erroresPreguntas()[pregunta.id]; as mensaje) {
                              <p class="error-pregunta">{{ mensaje }}</p>
                            }
                          </fieldset>
                        }
                        @case ('multiple_choice') {
                          <fieldset [id]="'insc-pregunta-' + pregunta.id" tabindex="-1">
                            <legend>{{ etiquetaConObligatoria(pregunta) }}</legend>
                            @for (opcion of pregunta.options ?? []; track opcion) {
                              <app-checkbox
                                [label]="opcion"
                                [checked]="valorLista(pregunta.id).includes(opcion)"
                                (checkedChange)="alternarOpcion(pregunta.id, opcion)"
                              />
                            }
                            @if (erroresPreguntas()[pregunta.id]; as mensaje) {
                              <p class="error-pregunta">{{ mensaje }}</p>
                            }
                          </fieldset>
                        }
                      }
                    </div>
                  }

                  @if (esCompraDePago()) {
                    <fieldset id="insc-tipo-entrada" class="tipo-entrada" tabindex="-1">
                      <legend>{{ t('inscripcion.tipoEntrada.titulo') }} *</legend>
                      @for (tipo of ticketTypes(); track tipo.id) {
                        <label class="opcion">
                          <input
                            type="radio"
                            name="tipo-entrada"
                            [value]="tipo.id"
                            [checked]="ticketTypeId() === tipo.id"
                            (change)="seleccionarTipo(tipo.id)"
                          />
                          {{ tipo.name }} — {{ precioTipo(tipo) }} {{ tipo.currency.toUpperCase() }}
                        </label>
                      }
                      @if (errorTicketType(); as mensaje) {
                        <p class="error-pregunta">{{ mensaje }}</p>
                      }
                    </fieldset>

                    <app-input
                      [label]="t('inscripcion.codigoDescuento')"
                      [required]="false"
                      [(value)]="codigoDescuento"
                      (blurred)="actualizarPresupuesto()"
                    />

                    <div class="presupuesto" aria-live="polite">
                      @if (cargandoPresupuesto()) {
                        <p>{{ t('inscripcion.presupuesto.calculando') }}</p>
                      } @else if (errorPresupuesto(); as mensaje) {
                        <p class="error-pregunta">{{ mensaje }}</p>
                      } @else if (presupuesto(); as presupuesto) {
                        <p>
                          {{ t('inscripcion.presupuesto.total') }}:
                          <strong
                            >{{ precioEuros(presupuesto.total_cents) }}
                            {{ presupuesto.currency.toUpperCase() }}</strong
                          >
                          @if (presupuesto.discount_cents > 0) {
                            ({{
                              t('inscripcion.presupuesto.descuentoAplicado', {
                                importe: precioEuros(presupuesto.discount_cents),
                              })
                            }})
                          }
                        </p>
                      }
                    </div>
                  }

                  <app-checkbox
                    fieldId="insc-tratamiento-datos"
                    [label]="t('inscripcion.tratamientoDatos')"
                    [describedBy]="errorConsentimiento() ? 'insc-tratamiento-datos-error' : null"
                    [(checked)]="dataProcessingAccepted"
                  />
                  @if (errorConsentimiento()) {
                    <p id="insc-tratamiento-datos-error" class="error-pregunta">
                      {{ errorConsentimiento() }}
                    </p>
                  }

                  <app-checkbox
                    [label]="t('inscripcion.marketing')"
                    [(checked)]="marketingAccepted"
                  />

                  <app-checkbox
                    [label]="t('inscripcion.grabacion')"
                    [(checked)]="recordingAccepted"
                  />

                  <app-turnstile-widget (resuelto)="onTurnstileResuelto($event)" />

                  @if (error(); as mensaje) {
                    <app-alert tone="error" [title]="t('inscripcion.error')">{{
                      mensaje
                    }}</app-alert>
                  }

                  <!-- Sin botón "volver al evento" junto al de envío: la miga
                     de pan de arriba ya cubre esa navegación, un segundo
                     enlace sería redundante. -->
                  <div class="acciones">
                    <app-button type="submit" [loading]="enviando()">
                      {{
                        enviando()
                          ? t('inscripcion.enviando')
                          : esCompraDePago()
                            ? t('inscripcion.continuarAlPago')
                            : t('inscripcion.inscribirse')
                      }}
                    </app-button>
                  </div>
                </form>
              }
            }

            @if (enviado() || noEncontrado()) {
              <p>
                <a [routerLink]="['/eventos', slug()]">{{ t('inscripcion.volverAlEvento') }}</a>
              </p>
            }
          </div>

          @if (evento(); as evento) {
            <aside class="resumen">
              <span class="rotulo-seccion">{{ t('inscripcion.resumen.titulo') }}</span>
              <h3>{{ evento.title }}</h3>
              <div class="resumen__fila">
                <span class="muted">{{ t('inscripcion.resumen.fechas') }}</span>
                <span class="num sin-salto">
                  {{ evento.starts_at | date: 'dd.MM.yyyy' : evento.timezone }} –
                  {{ evento.ends_at | date: 'dd.MM.yyyy' : evento.timezone }}
                </span>
              </div>
              @if (evento.location_name) {
                <div class="resumen__fila">
                  <span class="muted">{{ t('inscripcion.resumen.lugar') }}</span>
                  <span>{{ evento.location_name }}</span>
                </div>
              }
              <div class="resumen__fila">
                <span class="muted">{{ t('inscripcion.resumen.precio') }}</span>
                <span class="num">{{ precioResumen(t) }}</span>
              </div>
              @if (plazasLibresResumen(evento); as plazas) {
                <div class="resumen__fila">
                  <span class="muted">{{ t('inscripcion.resumen.plazasLibres') }}</span>
                  <span class="num">{{ plazas }}</span>
                </div>
              }
            </aside>
          }
        </div>
      </div>
    </ng-container>
  `,
  styles: `
    .pagina {
      padding: var(--space-lg) 0;
    }
    app-breadcrumb {
      display: block;
      margin-bottom: var(--space-md);
    }
    /* .layout de la referencia (inscripcion.html:14): formulario + resumen
       sticky en escritorio, apilados en móvil. Ancho del contenedor
       estándar del sitio (clase ancho-maximo, hasta 1240px) — nada de un
       tope propio más estrecho: la referencia no recorta .layout, hereda el
       ancho de .wrap, igual que el resto de páginas públicas. */
    .layout {
      display: grid;
      /* Mismo mínimo que .ficha en event-page.ts (18.75rem): con el de aquí
         (17.5rem) el rango de fechas no cabía en una línea y se partía en
         dos, a la izquierda en vez de pegado al borde derecho. */
      grid-template-columns: minmax(0, 1fr) minmax(18.75rem, 25rem);
      gap: var(--space-lg);
      align-items: start;
    }
    @media (max-width: 56.25rem) {
      .layout {
        grid-template-columns: 1fr;
      }
      .resumen {
        position: static;
      }
    }
    /* .summary de la referencia (inscripcion.html:27): mismo estilo de tarjeta
       que app-card, con su propio maquetado interno en vez de su input
       heading (necesita el rótulo mono ENCIMA del título, no un h3 suelto).
       Ritmo de fila tomado de .ficha__fila (event-page.ts, 14px de padding
       vertical) — aquí sí hace falta padding propio en la tarjeta, a
       diferencia de .ficha, porque encima de las filas va la cabecera
       (rótulo + título) que .ficha no tiene. */
    .resumen {
      position: sticky;
      top: 5.5rem;
      background-color: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 1.5rem;
    }
    .resumen h3 {
      margin: 0.625rem 0 1.125rem;
    }
    .resumen__fila {
      display: flex;
      justify-content: space-between;
      gap: var(--space-md);
      padding: 14px 0;
      border-bottom: 1px solid var(--border);
    }
    .resumen__fila:last-child {
      border-bottom: 0;
    }
    .muted {
      color: var(--muted);
    }
    .num {
      font-family: var(--font-mono);
    }
    /* El rango de fechas de .ficha__fila nunca se parte en dos líneas: se
       queda pegado al borde derecho de la fila en una sola línea. */
    .sin-salto {
      white-space: nowrap;
    }
    /* .steps de la referencia (inscripcion.html:14-19): mono, mayúsculas, con
       un conector de 24px entre etiquetas — el pseudoelemento vive dentro de
       cada <li> (segundo en adelante) porque el propio <li> es un flex row. */
    .pasos {
      display: flex;
      gap: var(--space-sm);
      list-style: none;
      padding: 0;
      margin: 0 0 var(--space-lg);
      flex-wrap: wrap;
    }
    .pasos li {
      display: flex;
      align-items: center;
      gap: 8px;
      font-family: var(--font-mono);
      font-size: 0.75rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .pasos li + li::before {
      content: '';
      width: 24px;
      height: 1px;
      background: var(--border-strong);
    }
    .pasos li[data-estado='hecho'] {
      color: var(--faint);
      text-decoration: line-through;
      text-decoration-color: var(--faint);
    }
    .pasos li[data-estado='actual'] {
      color: var(--accent);
    }
    /* h1/label de la referencia (inscripcion.html:63-64): margen propio,
       distinto del h1 de titular de sección de otras páginas. */
    .layout h1 {
      margin: 0.75rem 0 1rem;
    }
    .explicacion {
      color: var(--muted);
      max-width: 56ch;
      margin: 0 0 var(--space-md);
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
    /* .actions (inscripcion.html:25): botón de envío y "volver al evento"
       en la misma fila. */
    .acciones {
      display: flex;
      align-items: center;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    /* .row2 (inscripcion.html:23): campos cortos de dos en dos, apilados por
       debajo de 220px cada uno. */
    .fila-doble {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(13.75rem, 1fr));
      gap: var(--space-md);
    }
    fieldset {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: var(--space-sm) var(--space-md) var(--space-md);
      display: grid;
      gap: var(--space-xs);
    }
    legend {
      font-weight: 500;
      padding: 0 var(--space-xs);
    }
    .opcion {
      display: flex;
      align-items: center;
      gap: var(--space-xs);
    }
    .error-pregunta {
      margin: 0;
      color: var(--danger);
      font-size: 0.875rem;
    }
    .presupuesto {
      min-height: 1.5rem;
    }
    .presupuesto p {
      margin: 0;
    }
  `,
})
export class RegistrationPage implements OnInit {
  readonly slug = input.required<string>();

  private readonly registrations = inject(RegistrationsService);
  private readonly checkout = inject(PublicCheckoutService);
  private readonly transloco = inject(TranslocoService);
  private readonly esNavegador = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  protected readonly cargandoPreguntas = signal(true);
  protected readonly noEncontrado = signal(false);
  protected readonly preguntas = signal<RegistrationQuestion[]>([]);

  protected migasDePan(evento: PublicEventDetail): BreadcrumbItem[] {
    return [
      {
        label: this.transloco.translate('publico.eventos.listadoTitulo'),
        routerLink: ['/eventos'],
      },
      { label: evento.title, routerLink: ['/eventos', this.slug()] },
      { label: this.transloco.translate('publico.eventos.inscribirse') },
    ];
  }

  /** Resumen del evento (`.summary` de `inscripcion.html:172-181`): consulta
   * de solo lectura aparte de `cargarPreguntas`/`cargarTiposDeEntrada`, en
   * mejor esfuerzo — si falla, el formulario sigue siendo usable sin resumen
   * en vez de bloquear la inscripción por un dato accesorio. */
  protected readonly evento = signal<PublicEventDetail | null>(null);

  protected readonly email = signal('');
  protected readonly fullName = signal('');
  protected readonly errorEmail = signal<string | null>(null);
  protected readonly errorNombre = signal<string | null>(null);
  protected readonly erroresPreguntas = signal<Record<string, string | null>>({});
  protected readonly errorConsentimiento = signal<string | null>(null);

  private readonly respuestasTexto = signal<Record<string, string>>({});
  private readonly respuestasLista = signal<Record<string, string[]>>({});

  protected readonly dataProcessingAccepted = signal(false);
  protected readonly marketingAccepted = signal(false);
  protected readonly recordingAccepted = signal(false);
  protected readonly turnstileToken = signal<string | null>(null);

  protected readonly enviando = signal(false);
  protected readonly enviado = signal(false);
  protected readonly mensajeExito = signal('');
  protected readonly error = signal<string | null>(null);

  /** No vacía únicamente cuando el evento vende entradas ahora mismo: ver el
   * docstring de la clase sobre por qué esta lista basta para decidirlo. */
  protected readonly ticketTypes = signal<PublicTicketType[]>([]);
  protected readonly esCompraDePago = computed(() => this.ticketTypes().length > 0);
  protected readonly ticketTypeId = signal<string | null>(null);
  protected readonly errorTicketType = signal<string | null>(null);
  protected readonly codigoDescuento = signal('');
  protected readonly presupuesto = signal<CheckoutQuote | null>(null);
  protected readonly cargandoPresupuesto = signal(false);

  /** Agrega los errores de validación visibles en un momento dado, enlazados
   * por id a su campo: `app-error-summary` solo se pinta a partir de dos, así
   * que un único fallo sigue resolviéndose con el mensaje inline del campo. */
  protected readonly resumenErrores = computed<ResumenDeError[]>(() => {
    const errores: ResumenDeError[] = [];
    if (this.errorEmail()) {
      errores.push({ campoId: 'insc-email', mensaje: this.errorEmail()! });
    }
    if (this.errorNombre()) {
      errores.push({ campoId: 'insc-nombre', mensaje: this.errorNombre()! });
    }
    for (const [id, mensaje] of Object.entries(this.erroresPreguntas())) {
      if (mensaje) {
        errores.push({ campoId: `insc-pregunta-${id}`, mensaje });
      }
    }
    if (this.errorConsentimiento()) {
      errores.push({ campoId: 'insc-tratamiento-datos', mensaje: this.errorConsentimiento()! });
    }
    if (this.esCompraDePago() && this.errorTicketType()) {
      errores.push({ campoId: 'insc-tipo-entrada', mensaje: this.errorTicketType()! });
    }
    return errores;
  });
  protected readonly errorPresupuesto = signal<string | null>(null);

  /** Modo de inscripción a efectos de visualización (pasos + texto
   * explicativo): "pago" se decide por `esCompraDePago()`, la misma condición
   * que ya gobierna qué endpoint dispara `enviar()` — así los pasos nunca
   * pueden prometer un camino distinto del que de verdad va a seguir el
   * envío. Entre gratis y aprobación no hay divergencia funcional posible
   * (los dos envían por `RegistrationsService.submit`), así que ahí sí basta
   * con `evento().registration_mode`, que es el dato real del backend. */
  protected readonly modoInscripcion = computed<RegistrationMode>(() => {
    if (this.esCompraDePago()) {
      return 'paid';
    }
    return this.evento()?.registration_mode === 'approval' ? 'approval' : 'free';
  });

  private static readonly CLAVES_PASOS_POR_MODO: Record<
    RegistrationMode,
    readonly [string, string]
  > = {
    free: ['inscripcion.pasos.datos', 'inscripcion.pasos.confirmacionEmail'],
    approval: ['inscripcion.pasos.datos', 'inscripcion.pasos.revision'],
    paid: ['inscripcion.pasos.datosYEntrada', 'inscripcion.pasos.pago'],
  };

  private static readonly CLAVE_TEXTO_POR_MODO: Record<RegistrationMode, string> = {
    free: 'inscripcion.modo.gratisTexto',
    approval: 'inscripcion.modo.aprobacionTexto',
    paid: 'inscripcion.modo.pagoTexto',
  };

  /** Titular (`<h1>`) de la referencia (inscripcion.html:64/122/144): cambia
   * con el modo mientras se rellena el formulario, y con un titular propio
   * una vez enviado — el mismo hueco visual que en la referencia ocupan los
   * pasos 2/3, aunque aquí no sean pantallas propias (ver
   * `indicePasoActivo`). */
  private static readonly CLAVE_TITULO_FORMULARIO_POR_MODO: Record<RegistrationMode, string> = {
    free: 'inscripcion.titulos.formularioGratis',
    approval: 'inscripcion.titulos.formularioAprobacion',
    paid: 'inscripcion.titulos.formularioPago',
  };

  /** Índice del paso resaltado (0 = "Tus datos…", 1 = el paso siguiente):
   * también en pago, donde no hay una pantalla propia de "paso 2" — el envío
   * redirige fuera de la app —, resaltarlo mientras `enviando()` es cierto
   * confirma visualmente que el clic sí iba camino del pago. */
  protected readonly indicePasoActivo = computed(() => (this.enviando() || this.enviado() ? 1 : 0));

  protected etiquetasPasos(traducir: (clave: string) => string): readonly [string, string] {
    const [primero, segundo] = RegistrationPage.CLAVES_PASOS_POR_MODO[this.modoInscripcion()];
    return [traducir(primero), traducir(segundo)];
  }

  protected textoModo(traducir: (clave: string) => string): string {
    return traducir(RegistrationPage.CLAVE_TEXTO_POR_MODO[this.modoInscripcion()]);
  }

  protected tituloPaso(traducir: (clave: string) => string): string {
    if (this.enviado()) {
      return traducir('inscripcion.titulos.enviado');
    }
    return traducir(RegistrationPage.CLAVE_TITULO_FORMULARIO_POR_MODO[this.modoInscripcion()]);
  }

  protected estadoPaso(indice: number): 'hecho' | 'actual' | null {
    const activo = this.indicePasoActivo();
    return indice < activo ? 'hecho' : indice === activo ? 'actual' : null;
  }

  ngOnInit(): void {
    void this.cargarPreguntas();
    void this.cargarTiposDeEntrada();
    void this.cargarEvento();
  }

  private async cargarEvento(): Promise<void> {
    try {
      this.evento.set(
        await firstValueFrom(
          this.http.get<PublicEventDetail>(this.api.url(`/public/events/${this.slug()}`), {
            headers: this.api.serverForwardHeaders(),
          }),
        ),
      );
    } catch {
      // Best-effort, igual que `cargarTiposDeEntrada`: sin resumen el
      // formulario se sigue pudiendo enviar.
      this.evento.set(null);
    }
  }

  private async cargarPreguntas(): Promise<void> {
    try {
      this.preguntas.set(await this.registrations.getQuestions(this.slug()));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        this.noEncontrado.set(true);
      } else {
        this.noEncontrado.set(true);
      }
    } finally {
      this.cargandoPreguntas.set(false);
    }
  }

  private async cargarTiposDeEntrada(): Promise<void> {
    try {
      this.ticketTypes.set(await this.checkout.getTicketTypes(this.slug()));
    } catch {
      // Best-effort: si esta llamada falla, el formulario se comporta como
      // un evento gratuito. `cargarPreguntas` ya cubre el caso «evento
      // inexistente» con su propio mensaje.
      this.ticketTypes.set([]);
    }
  }

  protected precioTipo(tipo: PublicTicketType): string {
    return precioEnEuros(tipo.price_cents);
  }

  protected precioEuros(cents: number): string {
    return precioEnEuros(cents);
  }

  /** `.summary__row` "Precio" (`inscripcion.html:178`): el más barato de los
   * tipos de entrada vendibles, con «Desde» si hay más de uno. Sin tipos, el
   * evento es gratuito (mismo criterio que `esCompraDePago`). */
  protected precioResumen(traducir: (clave: string) => string): string {
    const tipos = this.ticketTypes();
    if (tipos.length === 0) {
      return traducir('inscripcion.resumen.gratis');
    }
    const masBarato = tipos.reduce((min, tipo) =>
      tipo.price_cents < min.price_cents ? tipo : min,
    );
    const precio = `${this.precioEuros(masBarato.price_cents)} ${masBarato.currency.toUpperCase()}`;
    return tipos.length > 1 ? `${traducir('inscripcion.resumen.desde')} ${precio}` : precio;
  }

  /** `.summary__row` "Plazas libres" (`inscripcion.html:179`): `null` con
   * aforo sin límite, mismo criterio que la ficha del evento. */
  protected plazasLibresResumen(evento: PublicEventDetail): number | null {
    return evento.capacity === null ? null : Math.max(evento.capacity - evento.reserved_count, 0);
  }

  protected seleccionarTipo(id: string): void {
    this.ticketTypeId.set(id);
    this.errorTicketType.set(null);
    void this.actualizarPresupuesto();
  }

  protected onTurnstileResuelto(token: string): void {
    this.turnstileToken.set(token);
    void this.actualizarPresupuesto();
  }

  protected async actualizarPresupuesto(): Promise<void> {
    const ticketTypeId = this.ticketTypeId();
    if (!ticketTypeId) {
      return;
    }
    // Mismo criterio que el envío final (`turnstileToken() ?? ''`): con
    // Turnstile desactivado el token resuelve a `''` de inmediato; con
    // Turnstile activo, un presupuesto pedido antes de resolver el reto
    // fallará una vez (mensaje de error, autocorregible) y
    // `onTurnstileResuelto` vuelve a pedirlo en cuanto llegue el token real.
    this.cargandoPresupuesto.set(true);
    this.errorPresupuesto.set(null);
    try {
      this.presupuesto.set(
        await this.checkout.quote(this.slug(), {
          ticketTypeId,
          code: this.codigoDescuento().trim() || null,
          turnstileToken: this.turnstileToken() ?? '',
        }),
      );
    } catch (error) {
      this.presupuesto.set(null);
      this.errorPresupuesto.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('inscripcion.presupuesto.error'),
      );
    } finally {
      this.cargandoPresupuesto.set(false);
    }
  }

  protected etiquetaConObligatoria(pregunta: RegistrationQuestion): string {
    return pregunta.required ? `${pregunta.label} *` : pregunta.label;
  }

  protected valorTexto(questionId: string): string {
    return this.respuestasTexto()[questionId] ?? '';
  }

  protected fijarTexto(questionId: string, valor: string): void {
    this.respuestasTexto.update((actuales) => ({ ...actuales, [questionId]: valor }));
  }

  protected valorLista(questionId: string): string[] {
    return this.respuestasLista()[questionId] ?? [];
  }

  protected alternarOpcion(questionId: string, opcion: string): void {
    this.respuestasLista.update((actuales) => {
      const lista = actuales[questionId] ?? [];
      const siguiente = lista.includes(opcion)
        ? lista.filter((valor) => valor !== opcion)
        : [...lista, opcion];
      return { ...actuales, [questionId]: siguiente };
    });
  }

  protected validarEmail(): void {
    const valor = this.email().trim();
    this.errorEmail.set(
      !valor
        ? this.transloco.translate('inscripcion.emailRequerido')
        : EMAIL_RE.test(valor)
          ? null
          : this.transloco.translate('inscripcion.emailInvalido'),
    );
  }

  protected validarNombre(): void {
    this.errorNombre.set(
      this.fullName().trim() ? null : this.transloco.translate('inscripcion.nombreRequerido'),
    );
  }

  private validarPreguntas(): boolean {
    const errores: Record<string, string | null> = {};
    let valido = true;
    for (const pregunta of this.preguntas()) {
      if (!pregunta.required) {
        continue;
      }
      const respondida =
        pregunta.type === 'multiple_choice'
          ? this.valorLista(pregunta.id).length > 0
          : this.valorTexto(pregunta.id).trim().length > 0;
      if (!respondida) {
        errores[pregunta.id] = this.transloco.translate('inscripcion.preguntaObligatoria');
        valido = false;
      }
    }
    this.erroresPreguntas.set(errores);
    return valido;
  }

  private construirRespuestas(): RegistrationAnswerInput[] {
    const respuestas: RegistrationAnswerInput[] = [];
    for (const pregunta of this.preguntas()) {
      if (pregunta.type === 'multiple_choice') {
        const lista = this.valorLista(pregunta.id);
        if (lista.length > 0) {
          respuestas.push({ question_id: pregunta.id, value: lista });
        }
        continue;
      }
      const texto = this.valorTexto(pregunta.id).trim();
      if (texto) {
        respuestas.push({ question_id: pregunta.id, value: texto });
      }
    }
    return respuestas;
  }

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);

    this.validarEmail();
    this.validarNombre();
    const preguntasValidas = this.validarPreguntas();
    this.errorConsentimiento.set(
      this.dataProcessingAccepted()
        ? null
        : this.transloco.translate('inscripcion.tratamientoDatosRequerido'),
    );
    const esCompraDePago = this.esCompraDePago();
    if (esCompraDePago) {
      this.errorTicketType.set(
        this.ticketTypeId()
          ? null
          : this.transloco.translate('inscripcion.tipoEntrada.obligatorio'),
      );
    }

    if (
      this.errorEmail() ||
      this.errorNombre() ||
      !preguntasValidas ||
      this.errorConsentimiento() ||
      (esCompraDePago && this.errorTicketType())
    ) {
      return;
    }

    this.enviando.set(true);
    try {
      if (esCompraDePago) {
        await this.enviarCompra();
      } else {
        const mensaje = await this.registrations.submit(this.slug(), {
          email: this.email().trim(),
          fullName: this.fullName().trim(),
          answers: this.construirRespuestas(),
          dataProcessingAccepted: this.dataProcessingAccepted(),
          marketingAccepted: this.marketingAccepted(),
          recordingAccepted: this.recordingAccepted(),
          turnstileToken: this.turnstileToken() ?? '',
        });
        this.mensajeExito.set(mensaje);
        this.enviado.set(true);
      }
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('inscripcion.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }

  /** Extraído de `enviar` solo para no anidar el `try` de la compra dentro
   * del `try` general: mismas reglas de error, misma señal de "enviando". */
  private async enviarCompra(): Promise<void> {
    const resultado = await this.checkout.startCheckout(this.slug(), {
      email: this.email().trim(),
      fullName: this.fullName().trim(),
      answers: this.construirRespuestas(),
      dataProcessingAccepted: this.dataProcessingAccepted(),
      marketingAccepted: this.marketingAccepted(),
      recordingAccepted: this.recordingAccepted(),
      ticketTypeId: this.ticketTypeId()!,
      code: this.codigoDescuento().trim() || null,
      turnstileToken: this.turnstileToken() ?? '',
    });
    if (resultado.checkout_url) {
      // Nunca en SSR: aquí no hay `window`, y un envío real nunca puede
      // llegar a ejecutarse en el servidor (lo dispara un evento de
      // navegador). El `if` es la comprobación explícita que lo garantiza
      // también en las pruebas.
      if (this.esNavegador) {
        window.location.href = resultado.checkout_url;
      }
      return;
    }
    this.mensajeExito.set(resultado.message);
    this.enviado.set(true);
  }
}
