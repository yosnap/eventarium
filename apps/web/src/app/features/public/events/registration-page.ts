import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
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

/**
 * Formulario público de inscripción a un evento (fase 3 del PRD).
 *
 * CSR, como `registro`: es un flujo transaccional. Las preguntas
 * personalizadas se cargan primero (`ngOnInit`) porque su forma decide qué
 * campos mostrar — un enfoque «formulario fijo + JSON suelto» no sirve aquí,
 * cada evento puede definir preguntas distintas.
 *
 * La respuesta de alta es siempre la misma exista o no ya el email inscrito
 * (anti-enumeración, igual que `registro`): el mensaje de éxito nunca dice
 * "ya estabas inscrito" ni "te hemos inscrito", dice lo mismo en ambos casos.
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

              <app-turnstile-widget (resuelto)="turnstileToken.set($event)" />

              @if (error(); as mensaje) {
                <app-alert tone="error" [title]="t('inscripcion.error')">{{ mensaje }}</app-alert>
              }

              <app-button type="submit" [loading]="enviando()">
                {{ enviando() ? t('inscripcion.enviando') : t('inscripcion.inscribirse') }}
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
  `,
})
export class RegistrationPage implements OnInit {
  readonly slug = input.required<string>();

  private readonly registrations = inject(RegistrationsService);
  private readonly transloco = inject(TranslocoService);

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

  ngOnInit(): void {
    void this.cargarPreguntas();
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

    if (
      this.errorEmail() ||
      this.errorNombre() ||
      !preguntasValidas ||
      this.errorConsentimiento()
    ) {
      return;
    }

    this.enviando.set(true);
    try {
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
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('inscripcion.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
