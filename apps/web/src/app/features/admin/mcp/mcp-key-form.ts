import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
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
import { Input } from '../../../shared/ui/input';
import { AMBITOS, type Ambito, McpPermisosSelector } from './mcp-permisos-selector';

const POR_DEFECTO: readonly Ambito[] = ['eventos:leer', 'inscripciones:cifras'];

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
  imports: [TranslocoDirective, Alert, Button, Card, Input, McpPermisosSelector],
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

            <app-mcp-permisos-selector
              [(marcados)]="marcados"
              [(todosLosEventos)]="todosLosEventos"
              [(eventosElegidos)]="eventosElegidos"
            />

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
    form {
      display: grid;
      gap: var(--sp-3);
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
export class McpKeyForm {
  readonly creadaUna = output<void>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly nombre = signal('');
  protected readonly dias = signal('90');
  protected readonly marcados = signal<ReadonlySet<Ambito>>(new Set(POR_DEFECTO));
  protected readonly todosLosEventos = signal(true);
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
}
