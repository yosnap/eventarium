import { NgTemplateOutlet } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  inject,
  input,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import {
  type RegistrationQuestionResponse,
  type RegistrationQuestionType,
} from './registration-types';

const TIPOS_DISPONIBLES: readonly RegistrationQuestionType[] = [
  'short_text',
  'single_choice',
  'multiple_choice',
];

function vacio(): {
  type: RegistrationQuestionType;
  label: string;
  required: boolean;
  opciones: string;
} {
  return { type: 'short_text', label: '', required: false, opciones: '' };
}

/**
 * CRUD de las preguntas personalizadas del formulario de inscripción de un
 * evento. La edición se hace en línea (la propia fila despliega el
 * formulario) en vez de con un modal, para no depender de una librería de
 * diálogos que el proyecto no tiene.
 */
@Component({
  selector: 'app-registration-questions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, NgTemplateOutlet, Alert, Button, Card, Input],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.registrationQuestions.titulo')">
        @if (error(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }
        @if (borrarError(); as mensaje) {
          <app-alert tone="error">{{ mensaje }}</app-alert>
        }

        @if (cargando()) {
          <p>{{ t('comun.cargando') }}</p>
        } @else if (preguntas().length === 0) {
          <p>{{ t('admin.events.registrationQuestions.sinPreguntas') }}</p>
        } @else {
          <ul class="lista">
            @for (pregunta of preguntas(); track pregunta.id) {
              <li>
                @if (editandoId() === pregunta.id) {
                  <ng-container
                    [ngTemplateOutlet]="formulario"
                    [ngTemplateOutletContext]="{ $implicit: pregunta.id }"
                  />
                } @else {
                  <div class="fila">
                    <div>
                      <p class="etiqueta">
                        {{ pregunta.label }}
                        @if (pregunta.required) {
                          <span class="insignia">{{
                            t('admin.events.registrationQuestions.obligatoria')
                          }}</span>
                        }
                      </p>
                      <p class="detalle">
                        {{
                          t('admin.events.registrationQuestions.tipo' + tipoClave(pregunta.type))
                        }}
                        @if (pregunta.options && pregunta.options.length > 0) {
                          · {{ pregunta.options.join(', ') }}
                        }
                      </p>
                    </div>
                    <div class="acciones">
                      <app-button variant="secundario" type="button" (pulsado)="editar(pregunta)">
                        {{ t('admin.events.registrationQuestions.editar') }}
                      </app-button>
                      @if (pendienteDeBorrar() === pregunta.id) {
                        <app-button
                          variant="peligro"
                          type="button"
                          [loading]="borrando() === pregunta.id"
                          (pulsado)="confirmarBorrado(pregunta.id)"
                        >
                          {{ t('admin.events.registrationQuestions.confirmarEliminar') }}
                        </app-button>
                        <app-button
                          variant="secundario"
                          type="button"
                          (pulsado)="pendienteDeBorrar.set(null)"
                        >
                          {{ t('comun.cancelar') }}
                        </app-button>
                      } @else {
                        <app-button
                          variant="secundario"
                          type="button"
                          (pulsado)="pendienteDeBorrar.set(pregunta.id)"
                        >
                          {{ t('admin.events.registrationQuestions.eliminar') }}
                        </app-button>
                      }
                    </div>
                  </div>
                }
              </li>
            }
          </ul>
        }

        @if (!editandoId()) {
          <ng-container
            [ngTemplateOutlet]="formulario"
            [ngTemplateOutletContext]="{ $implicit: null }"
          />
        }
      </app-card>

      <ng-template #formulario let-idEnEdicion>
        <form (submit)="guardar($event, idEnEdicion)" novalidate class="formulario">
          <h3>
            {{
              idEnEdicion
                ? t('admin.events.registrationQuestions.editarPregunta')
                : t('admin.events.registrationQuestions.anadirPregunta')
            }}
          </h3>

          <div class="campo-select">
            <label [for]="'pregunta-tipo-' + (idEnEdicion ?? 'nueva')">
              {{ t('admin.events.registrationQuestions.tipo') }}
            </label>
            <select
              [id]="'pregunta-tipo-' + (idEnEdicion ?? 'nueva')"
              [value]="tipo()"
              (change)="alCambiarTipo($event)"
            >
              @for (opcion of tiposDisponibles; track opcion) {
                <option [value]="opcion">
                  {{ t('admin.events.registrationQuestions.tipo' + tipoClave(opcion)) }}
                </option>
              }
            </select>
          </div>

          <app-input
            [fieldId]="'pregunta-etiqueta-' + (idEnEdicion ?? 'nueva')"
            [label]="t('admin.events.registrationQuestions.etiqueta')"
            [required]="true"
            [(value)]="etiqueta"
          />

          <label class="campo-checkbox">
            <input
              type="checkbox"
              [checked]="obligatoria()"
              (change)="alCambiarObligatoria($event)"
            />
            {{ t('admin.events.registrationQuestions.obligatoria') }}
          </label>

          @if (tipo() !== 'short_text') {
            <div class="campo-materiales">
              <label [for]="'pregunta-opciones-' + (idEnEdicion ?? 'nueva')">
                {{ t('admin.events.registrationQuestions.opciones') }}
              </label>
              <textarea
                [id]="'pregunta-opciones-' + (idEnEdicion ?? 'nueva')"
                rows="4"
                [value]="opciones()"
                (input)="opciones.set(alTextarea($event))"
              ></textarea>
              <p class="ayuda">{{ t('admin.events.registrationQuestions.opcionesAyuda') }}</p>
            </div>
          }

          @if (formError(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <div class="acciones-finales">
            @if (idEnEdicion) {
              <app-button variant="secundario" type="button" (pulsado)="cancelarEdicion()">
                {{ t('comun.cancelar') }}
              </app-button>
            }
            <app-button type="submit" [loading]="guardando()">
              {{
                idEnEdicion
                  ? t('admin.events.registrationQuestions.guardarCambios')
                  : t('admin.events.registrationQuestions.anadir')
              }}
            </app-button>
          </div>
        </form>
      </ng-template>
    </ng-container>
  `,
  styles: `
    h3 {
      margin: var(--space-md) 0 var(--space-xs);
    }
    .lista {
      list-style: none;
      margin: 0 0 var(--space-md);
      padding: 0;
      display: grid;
      gap: var(--space-sm);
    }
    .lista li {
      border-bottom: 1px solid var(--color-border);
      padding-bottom: var(--space-sm);
    }
    .fila {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: var(--space-md);
      flex-wrap: wrap;
    }
    .etiqueta {
      margin: 0;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .detalle {
      margin: var(--space-xs) 0 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.875rem;
    }
    .insignia {
      font-size: 0.75rem;
      font-weight: 500;
      padding: 0.125rem 0.5rem;
      border-radius: var(--radius-sm);
      background-color: var(--color-surface-muted);
      color: var(--color-text-muted, #6b7280);
    }
    .acciones {
      display: flex;
      gap: var(--space-sm);
      flex-wrap: wrap;
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      margin-top: var(--space-lg);
      padding-top: var(--space-lg);
      border-top: 1px solid var(--color-border);
    }
    .campo-select,
    .campo-materiales {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select,
    textarea {
      width: 100%;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
    }
    .campo-checkbox {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      font-weight: 500;
    }
    .ayuda {
      margin: 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.8125rem;
    }
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class RegistrationQuestions implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly tiposDisponibles = TIPOS_DISPONIBLES;

  protected readonly cargando = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly preguntas = signal<RegistrationQuestionResponse[]>([]);

  protected readonly editandoId = signal<string | null>(null);
  protected readonly guardando = signal(false);
  protected readonly formError = signal<string | null>(null);

  protected readonly pendienteDeBorrar = signal<string | null>(null);
  protected readonly borrando = signal<string | null>(null);
  protected readonly borrarError = signal<string | null>(null);

  private readonly valoresIniciales = vacio();
  protected readonly tipo = signal(this.valoresIniciales.type);
  protected readonly etiqueta = signal(this.valoresIniciales.label);
  protected readonly obligatoria = signal(this.valoresIniciales.required);
  protected readonly opciones = signal(this.valoresIniciales.opciones);

  ngOnInit(): void {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.cargando.set(true);
    try {
      const preguntas = await firstValueFrom(
        this.http.get<RegistrationQuestionResponse[]>(
          this.api.url(`/events/${this.eventId()}/registration-questions`),
        ),
      );
      this.preguntas.set([...preguntas].sort((a, b) => a.sort_order - b.sort_order));
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrationQuestions.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected tipoClave(tipo: string): string {
    return tipo
      .split('_')
      .map((parte) => parte.charAt(0).toUpperCase() + parte.slice(1))
      .join('');
  }

  protected alCambiarTipo(evento: Event): void {
    this.tipo.set((evento.target as HTMLSelectElement).value as RegistrationQuestionType);
  }

  protected alCambiarObligatoria(evento: Event): void {
    this.obligatoria.set((evento.target as HTMLInputElement).checked);
  }

  protected alTextarea(evento: Event): string {
    return (evento.target as HTMLTextAreaElement).value;
  }

  private opcionesComoLista(): string[] {
    return this.opciones()
      .split('\n')
      .map((linea) => linea.trim())
      .filter((linea) => linea.length > 0);
  }

  protected editar(pregunta: RegistrationQuestionResponse): void {
    this.editandoId.set(pregunta.id);
    this.tipo.set(pregunta.type);
    this.etiqueta.set(pregunta.label);
    this.obligatoria.set(pregunta.required);
    this.opciones.set((pregunta.options ?? []).join('\n'));
    this.formError.set(null);
  }

  protected cancelarEdicion(): void {
    this.editandoId.set(null);
    const vacios = vacio();
    this.tipo.set(vacios.type);
    this.etiqueta.set(vacios.label);
    this.obligatoria.set(vacios.required);
    this.opciones.set(vacios.opciones);
    this.formError.set(null);
  }

  protected async guardar(evento: Event, idEnEdicion: string | null): Promise<void> {
    evento.preventDefault();
    this.formError.set(null);

    if (!this.etiqueta().trim()) {
      this.formError.set(
        this.transloco.translate('admin.events.registrationQuestions.camposRequeridos'),
      );
      return;
    }
    const opciones = this.opcionesComoLista();
    if (this.tipo() !== 'short_text' && opciones.length < 2) {
      this.formError.set(
        this.transloco.translate('admin.events.registrationQuestions.opcionesRequeridas'),
      );
      return;
    }

    const payload = {
      type: this.tipo(),
      label: this.etiqueta().trim(),
      required: this.obligatoria(),
      sort_order: idEnEdicion
        ? (this.preguntas().find((p) => p.id === idEnEdicion)?.sort_order ??
          this.preguntas().length)
        : this.preguntas().length,
      options: this.tipo() === 'short_text' ? null : opciones,
    };

    this.guardando.set(true);
    try {
      if (idEnEdicion) {
        await firstValueFrom(
          this.http.patch(
            this.api.url(`/events/${this.eventId()}/registration-questions/${idEnEdicion}`),
            payload,
          ),
        );
      } else {
        await firstValueFrom(
          this.http.post(this.api.url(`/events/${this.eventId()}/registration-questions`), payload),
        );
      }
      this.cancelarEdicion();
      await this.cargar();
    } catch (error) {
      this.formError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrationQuestions.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }

  protected async confirmarBorrado(id: string): Promise<void> {
    this.borrarError.set(null);
    this.borrando.set(id);
    try {
      await firstValueFrom(
        this.http.delete(this.api.url(`/events/${this.eventId()}/registration-questions/${id}`)),
      );
      this.pendienteDeBorrar.set(null);
      await this.cargar();
    } catch (error) {
      // Se deja la fila en estado «¿Seguro?» para no perder el contexto de qué
      // pregunta ha fallado al borrar (p. ej. 409 porque ya tiene respuestas).
      this.borrarError.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.registrationQuestions.errorEliminar'),
      );
    } finally {
      this.borrando.set(null);
    }
  }
}
