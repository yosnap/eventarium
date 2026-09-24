import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  computed,
  inject,
  input,
  model,
  signal,
} from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { Checkbox } from '../../../shared/ui/checkbox';

/** Ámbitos en el mismo orden que la API (`modules/mcp/scopes.py`). */
export const AMBITOS = [
  'eventos:leer',
  'inscripciones:cifras',
  'eventos:editar',
  'eventos:publicar',
  'patrocinadores:editar',
  'eventos:cancelar',
] as const;
export type Ambito = (typeof AMBITOS)[number];

const LIMITE_EVENTOS = 100;

interface EventoOpcion {
  readonly id: string;
  readonly title: string;
}

/**
 * Qué puede hacer una conexión y sobre qué eventos. Lo comparten el
 * formulario de claves de API y la pantalla de consentimiento OAuth.
 * `permitidos` limita las casillas a lo que el rol de la persona respalda
 * (`null` = todas; la API vuelve a comprobarlo).
 */
@Component({
  selector: 'app-mcp-permisos-selector',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Checkbox],
  template: `
    <ng-container *transloco="let t; read: 'admin.mcp.nueva'">
      <fieldset>
        <legend>{{ t('permisos') }}</legend>
        @for (ambito of visibles(); track ambito) {
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
          @if (errorEventos()) {
            <p class="aviso" role="status">{{ t('eventosError') }}</p>
          } @else if (hayMas()) {
            <p class="aviso">{{ t('eventosTruncados', { n: eventos().length }) }}</p>
          }
          @for (evento of eventos(); track evento.id) {
            <app-checkbox
              [label]="evento.title"
              [checked]="eventosElegidos().has(evento.id)"
              (checkedChange)="alternarEvento(evento.id, $event)"
            />
          }
        }
      </fieldset>
    </ng-container>
  `,
  styles: `
    :host,
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
    .aviso {
      margin: 0;
      color: var(--muted);
    }
  `,
})
export class McpPermisosSelector implements OnInit {
  readonly permitidos = input<readonly string[] | null>(null);
  readonly marcados = model<ReadonlySet<Ambito>>(new Set());
  readonly todosLosEventos = model(true);
  readonly eventosElegidos = model<ReadonlySet<string>>(new Set());

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  protected readonly eventos = signal<readonly EventoOpcion[]>([]);
  protected readonly hayMas = signal(false);
  protected readonly errorEventos = signal(false);
  protected readonly visibles = computed(() => {
    const permitidos = this.permitidos();
    return permitidos ? AMBITOS.filter((a) => permitidos.includes(a)) : AMBITOS;
  });

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

  private async cargarEventos(): Promise<void> {
    try {
      // El máximo que admite la API por página; con más, se avisa.
      const pagina = await firstValueFrom(
        this.http.get<{ items: readonly EventoOpcion[]; total: number }>(this.api.url('/events'), {
          params: { limit: LIMITE_EVENTOS },
        }),
      );
      this.eventos.set(pagina.items);
      this.hayMas.set(pagina.total > pagina.items.length);
    } catch {
      // Sin listado se puede conectar igualmente para todos los eventos.
      this.errorEventos.set(true);
    }
  }
}
