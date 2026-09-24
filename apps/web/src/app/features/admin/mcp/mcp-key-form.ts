import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Checkbox } from '../../../shared/ui/checkbox';
import { Input } from '../../../shared/ui/input';

/** Ámbitos en el mismo orden que la API (`modules/mcp/scopes.py`). */
export const AMBITOS = [
  'eventos:leer',
  'inscripciones:cifras',
  'eventos:editar',
  'eventos:publicar',
  'patrocinadores:editar',
  'eventos:cancelar',
] as const;
type Ambito = (typeof AMBITOS)[number];
const POR_DEFECTO: readonly Ambito[] = ['eventos:leer', 'inscripciones:cifras'];

interface EventoOpcion {
  readonly id: string;
  readonly title: string;
}

interface ClaveCreada {
  readonly api_key: string;
  readonly mcp_url: string;
}

/**
 * Alta de una clave de API para conectar un asistente. La clave se enseña una
 * sola vez, con botón de copiar; después solo queda su prefijo en el listado.
 * `eventos:cancelar` nunca viene marcado: reembolsa dinero.
 */
@Component({
  selector: 'app-mcp-key-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Checkbox, Input],
  template: `
    <ng-container *transloco="let t; read: 'admin.mcp.nueva'">
      <app-card [heading]="t('titulo')">
        @if (creada(); as c) {
          <app-alert tone="exito" [title]="t('creadaTitulo')">{{ t('creadaAviso') }}</app-alert>
          <p class="clave">
            <code>{{ c.api_key }}</code>
            <app-button type="button" variant="secundario" (pulsado)="copiar(c.api_key)">
              {{ copiada() ? t('copiada') : t('copiar') }}
            </app-button>
          </p>
          <p>
            {{ t('url') }} <code>{{ c.mcp_url }}</code>
          </p>
          <app-button type="button" (pulsado)="otra()">{{ t('otra') }}</app-button>
        } @else {
          <form (submit)="$event.preventDefault(); crear()">
            <app-input
              [label]="t('nombre')"
              [hint]="t('nombreAyuda')"
              [required]="true"
              [(value)]="nombre"
            />

            <fieldset>
              <legend>{{ t('permisos') }}</legend>
              @for (ambito of ambitos; track ambito) {
                <app-checkbox
                  [label]="t('ambito.' + clave(ambito))"
                  [hint]="t('ambitoAyuda.' + clave(ambito))"
                  [checked]="marcados().has(ambito)"
                  (checkedChange)="alternar(ambito, $event)"
                />
              }
            </fieldset>

            <fieldset>
              <legend>{{ t('eventos') }}</legend>
              <app-checkbox
                [label]="t('todosLosEventos')"
                [checked]="todosLosEventos()"
                (checkedChange)="todosLosEventos.set($event)"
              />
              @if (!todosLosEventos()) {
                @for (evento of eventos(); track evento.id) {
                  <app-checkbox
                    [label]="evento.title"
                    [checked]="eventosElegidos().has(evento.id)"
                    (checkedChange)="alternarEvento(evento.id, $event)"
                  />
                }
              }
            </fieldset>

            <app-input [label]="t('dias')" [hint]="t('diasAyuda')" [(value)]="dias" />

            @if (error(); as mensaje) {
              <app-alert tone="error">{{ mensaje }}</app-alert>
            }
            <app-button type="submit" [loading]="creando()" [disabled]="!valido()">
              {{ t('crear') }}
            </app-button>
          </form>
        }
      </app-card>
    </ng-container>
  `,
  styles: `
    form,
    fieldset {
      display: grid;
      gap: var(--sp-3);
    }
    fieldset {
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: var(--sp-4);
      margin: 0;
    }
    .clave {
      display: flex;
      flex-wrap: wrap;
      gap: var(--sp-3);
      align-items: center;
    }
    code {
      font-family: var(--font-mono);
      word-break: break-all;
    }
  `,
})
export class McpKeyForm implements OnInit {
  readonly creadaUna = output<void>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly ambitos = AMBITOS;
  protected readonly nombre = signal('');
  protected readonly dias = signal('90');
  protected readonly marcados = signal<ReadonlySet<Ambito>>(new Set(POR_DEFECTO));
  protected readonly todosLosEventos = signal(true);
  protected readonly eventos = signal<readonly EventoOpcion[]>([]);
  protected readonly eventosElegidos = signal<ReadonlySet<string>>(new Set());
  protected readonly creada = signal<ClaveCreada | null>(null);
  protected readonly copiada = signal(false);
  protected readonly creando = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly valido = computed(
    () =>
      this.nombre().trim().length > 0 &&
      this.marcados().size > 0 &&
      (this.todosLosEventos() || this.eventosElegidos().size > 0),
  );

  ngOnInit(): void {
    void this.cargarEventos();
  }

  protected clave(ambito: Ambito): string {
    return ambito.replace(':', '_');
  }

  protected alternar(ambito: Ambito, marcado: boolean): void {
    const siguiente = new Set(this.marcados());
    if (marcado) siguiente.add(ambito);
    else siguiente.delete(ambito);
    this.marcados.set(siguiente);
  }

  protected alternarEvento(id: string, marcado: boolean): void {
    const siguiente = new Set(this.eventosElegidos());
    if (marcado) siguiente.add(id);
    else siguiente.delete(id);
    this.eventosElegidos.set(siguiente);
  }

  protected async crear(): Promise<void> {
    if (!this.valido()) return;
    this.creando.set(true);
    this.error.set(null);
    try {
      const creada = await firstValueFrom(
        this.http.post<ClaveCreada>(this.api.url('/users/me/mcp-connections'), {
          name: this.nombre().trim(),
          scopes: AMBITOS.filter((a) => this.marcados().has(a)),
          event_ids: this.todosLosEventos() ? null : [...this.eventosElegidos()],
          days: Number.parseInt(this.dias(), 10) || 90,
        }),
      );
      this.creada.set(creada);
      this.creadaUna.emit();
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.mcp.error'),
      );
    } finally {
      this.creando.set(false);
    }
  }

  protected async copiar(texto: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(texto);
      this.copiada.set(true);
    } catch {
      // Sin portapapeles (contexto no seguro): la clave sigue a la vista.
    }
  }

  protected otra(): void {
    this.creada.set(null);
    this.copiada.set(false);
    this.nombre.set('');
  }

  private async cargarEventos(): Promise<void> {
    try {
      const pagina = await firstValueFrom(
        this.http.get<{ items: readonly EventoOpcion[] }>(this.api.url('/events')),
      );
      this.eventos.set(pagina.items);
    } catch {
      // Sin listado se puede crear igualmente una conexión para todos.
    }
  }
}
