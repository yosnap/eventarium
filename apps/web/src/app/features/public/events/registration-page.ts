import { isPlatformBrowser } from '@angular/common';
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
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

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
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card, Input, TurnstileWidget],
  template: `
    <ng-container *transloco="let t">
      <main id="contenido" class="pagina">
        <app-card [heading]="t('inscripcion.titulo')">
          @if (cargandoPreguntas()) {
            <p>{{ t('comun.cargando') }}</p>
          } @else if (noEncontrado()) {
            <app-alert tone="error">{{ t('publico.eventos.noEncontrado') }}</app-alert>
          } @else if (enviado()) {
            <app-alert tone="exito" [title]="t('inscripcion.exitoTitulo')">
              {{ mensajeExito() }}
            </app-alert>
          } @else {
            <form (submit)="enviar($event)" novalidate>
              <app-input
                [label]="t('inscripcion.email')"
                type="email"
                autocomplete="email"
                [required]="true"
                [error]="errorEmail()"
                [(value)]="email"
                (blurred)="validarEmail()"
              />
              <app-input
                [label]="t('inscripcion.nombre')"
                autocomplete="name"
                [required]="true"
                [error]="errorNombre()"
                [(value)]="fullName"
                (blurred)="validarNombre()"
              />

              @for (pregunta of preguntas(); track pregunta.id) {
                <div class="pregunta">
                  @switch (pregunta.type) {
                    @case ('short_text') {
                      <app-input
                        [label]="etiquetaConObligatoria(pregunta)"
                        [required]="pregunta.required"
                        [error]="erroresPreguntas()[pregunta.id] ?? null"
                        [value]="valorTexto(pregunta.id)"
                        (valueChange)="fijarTexto(pregunta.id, $event)"
                      />
                    }
                    @case ('single_choice') {
                      <fieldset>
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
                      <fieldset>
                        <legend>{{ etiquetaConObligatoria(pregunta) }}</legend>
                        @for (opcion of pregunta.options ?? []; track opcion) {
                          <label class="opcion">
                            <input
                              type="checkbox"
                              [checked]="valorLista(pregunta.id).includes(opcion)"
                              (change)="alternarOpcion(pregunta.id, opcion)"
                            />
                            {{ opcion }}
                          </label>
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
                <fieldset class="tipo-entrada">
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

              <label class="consentimiento">
                <input
                  type="checkbox"
                  [checked]="dataProcessingAccepted()"
                  (change)="dataProcessingAccepted.set(!dataProcessingAccepted())"
                />
                {{ t('inscripcion.tratamientoDatos') }}
              </label>
              @if (errorConsentimiento()) {
                <p class="error-pregunta">{{ errorConsentimiento() }}</p>
              }

              <label class="consentimiento">
                <input
                  type="checkbox"
                  [checked]="marketingAccepted()"
                  (change)="marketingAccepted.set(!marketingAccepted())"
                />
                {{ t('inscripcion.marketing') }}
              </label>

              <label class="consentimiento">
                <input
                  type="checkbox"
                  [checked]="recordingAccepted()"
                  (change)="recordingAccepted.set(!recordingAccepted())"
                />
                {{ t('inscripcion.grabacion') }}
              </label>

              <app-turnstile-widget (resuelto)="onTurnstileResuelto($event)" />

              @if (error(); as mensaje) {
                <app-alert tone="error" [title]="t('inscripcion.error')">{{ mensaje }}</app-alert>
              }

              <app-button type="submit" [loading]="enviando()">
                {{
                  enviando()
                    ? t('inscripcion.enviando')
                    : esCompraDePago()
                      ? t('inscripcion.continuarAlPago')
                      : t('inscripcion.inscribirse')
                }}
              </app-button>
            </form>
          }

          <p>
            <a [routerLink]="['/eventos', slug()]">{{ t('inscripcion.volverAlEvento') }}</a>
          </p>
        </app-card>
      </main>
    </ng-container>
  `,
  styles: `
    .pagina {
      display: grid;
      place-items: center;
      min-height: 100vh;
      padding: var(--space-lg);
      background-color: var(--color-surface-muted);
    }
    app-card {
      width: min(32rem, 100%);
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
    fieldset {
      border: 1px solid var(--color-border);
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
    .consentimiento {
      display: flex;
      align-items: flex-start;
      gap: var(--space-xs);
    }
    .error-pregunta {
      margin: 0;
      color: var(--color-danger);
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

  protected readonly cargandoPreguntas = signal(true);
  protected readonly noEncontrado = signal(false);
  protected readonly preguntas = signal<RegistrationQuestion[]>([]);

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
  protected readonly errorPresupuesto = signal<string | null>(null);

  ngOnInit(): void {
    void this.cargarPreguntas();
    void this.cargarTiposDeEntrada();
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
