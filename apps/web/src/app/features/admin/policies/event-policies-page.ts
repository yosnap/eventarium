import { HttpClient } from '@angular/common/http';
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
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { MarkdownSeguro } from '../../../shared/legal/markdown-seguro';
import { Alert } from '../../../shared/ui/alert';
import { Card } from '../../../shared/ui/card';
import { RadioGroup } from '../../../shared/ui/radio';
import { type PoliticaDeEvento, type PoliticasDeEvento, type TipoPolitica } from './policies-types';
import { PolicyEditor } from './policy-editor';
import { PolicyResponsibilityNotice } from './policy-responsibility-notice';

type Modo = 'heredar' | 'propio';

/**
 * Pestaña «Políticas» de un evento: para cada documento, usar el de la
 * organización o un texto propio de este evento. Volver a heredar guarda una
 * versión nula; el historial de lo aceptado se conserva siempre.
 */
@Component({
  selector: 'app-event-policies-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    RouterLink,
    MarkdownSeguro,
    Alert,
    Card,
    RadioGroup,
    PolicyEditor,
    PolicyResponsibilityNotice,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-policy-responsibility-notice />

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else if (errorDeCarga()) {
        <app-alert tone="error">{{ t('admin.politicas.errorCarga') }}</app-alert>
      } @else {
        @if (!puedeEditar()) {
          <app-alert tone="info">{{ t('admin.politicas.soloLectura') }}</app-alert>
        }
        <p class="ayuda">
          {{ t('admin.politicas.ayudaEvento') }}
          <a routerLink="/dashboard/politicas">{{ t('admin.politicas.irAOrganizacion') }}</a>
        </p>

        @for (politica of politicas(); track politica.kind) {
          <app-card [heading]="t('admin.politicas.tipos.' + politica.kind)">
            @if (puedeEditar()) {
              <app-radio-group
                class="modo"
                [etiqueta]="t('admin.politicas.origen')"
                [nombre]="'modo-' + politica.kind"
                [opciones]="opcionesDeModo(t)"
                [valor]="modoDe(politica)"
                (valorChange)="elegirModo(politica, $event)"
              />
            }

            @if (modoDe(politica) === 'propio' && puedeEditar()) {
              <app-policy-editor
                [etiqueta]="t('admin.politicas.tipos.' + politica.kind)"
                [valor]="politica.origin === 'evento' ? (politica.current?.content ?? '') : ''"
                [guardando]="guardandoTipo() === politica.kind"
                [error]="errores()[politica.kind] ?? null"
                [afectaAEventoPublicado]="publicado()"
                (guardar)="guardar(politica.kind, $event)"
              />
            } @else if (politica.origin === 'evento' && politica.current; as propio) {
              <p class="meta">{{ t('admin.politicas.textoPropioVigente') }}</p>
              <app-markdown-seguro [texto]="propio.content" />
            } @else if (politica.organization; as heredada) {
              <p class="meta">{{ t('admin.politicas.heredado') }}</p>
              <app-markdown-seguro [texto]="heredada.content" />
            } @else {
              <p class="meta">{{ t('admin.politicas.organizacionSinTexto') }}</p>
            }
            @if (errores()[politica.kind] && modoDe(politica) === 'heredar') {
              <app-alert tone="error">{{ errores()[politica.kind] }}</app-alert>
            }
          </app-card>
        }
      }
    </ng-container>
  `,
  styles: `
    :host {
      display: grid;
      gap: var(--space-lg);
    }
    .ayuda,
    .meta {
      margin: 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .meta {
      margin-bottom: var(--space-sm);
    }
    .modo {
      display: block;
      margin-bottom: var(--space-md);
    }
  `,
})
export class EventPoliciesPage implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  protected readonly cargando = signal(true);
  protected readonly errorDeCarga = signal(false);
  protected readonly puedeEditar = signal(false);
  protected readonly publicado = signal(false);
  protected readonly politicas = signal<readonly PoliticaDeEvento[]>([]);
  protected readonly guardandoTipo = signal<TipoPolitica | null>(null);
  protected readonly errores = signal<Partial<Record<TipoPolitica, string>>>({});
  /** Modo elegido en pantalla antes de guardar (p. ej. «propio» sin texto aún). */
  private readonly modosElegidos = signal<Partial<Record<TipoPolitica, Modo>>>({});

  ngOnInit(): void {
    void this.cargar();
  }

  protected opcionesDeModo(t: (clave: string) => string): { valor: Modo; etiqueta: string }[] {
    return [
      { valor: 'heredar', etiqueta: t('admin.politicas.usarOrganizacion') },
      { valor: 'propio', etiqueta: t('admin.politicas.textoPropio') },
    ];
  }

  protected modoDe(politica: PoliticaDeEvento): Modo {
    return (
      this.modosElegidos()[politica.kind] ?? (politica.origin === 'evento' ? 'propio' : 'heredar')
    );
  }

  private url(sufijo = ''): string {
    return this.api.url(`/events/${this.eventId()}/policies${sufijo}`);
  }

  /** `kind`: solo se olvida el modo elegido del documento recién guardado,
   * para no cerrar el editor a medio escribir de otro. Sin `kind` (carga
   * completa), se olvidan todos. */
  private aplicar(respuesta: PoliticasDeEvento, kind?: TipoPolitica): void {
    this.puedeEditar.set(respuesta.can_edit);
    this.politicas.set(respuesta.items);
    if (kind === undefined) {
      this.modosElegidos.set({});
    } else {
      this.modosElegidos.update((actuales) => ({ ...actuales, [kind]: undefined }));
    }
  }

  private async cargar(): Promise<void> {
    try {
      const [politicas, evento] = await Promise.all([
        firstValueFrom(this.http.get<PoliticasDeEvento>(this.url())),
        firstValueFrom(
          this.http.get<{ readonly status: string }>(this.api.url(`/events/${this.eventId()}`)),
        ),
      ]);
      this.aplicar(politicas);
      this.publicado.set(evento.status === 'published');
    } catch {
      this.errorDeCarga.set(true);
    } finally {
      this.cargando.set(false);
    }
  }

  /** «Usar el de la organización» guarda la vuelta a heredar si había texto
   * propio; «texto propio» solo abre el editor (se guarda al pulsar Guardar). */
  protected async elegirModo(politica: PoliticaDeEvento, modo: Modo): Promise<void> {
    this.modosElegidos.update((actuales) => ({ ...actuales, [politica.kind]: modo }));
    if (modo === 'heredar' && politica.origin === 'evento') {
      const guardado = await this.guardar(politica.kind, null);
      if (!guardado) {
        // El evento sigue con su texto propio: el selector tiene que decirlo.
        this.modosElegidos.update((actuales) => ({ ...actuales, [politica.kind]: 'propio' }));
      }
    }
  }

  protected async guardar(kind: TipoPolitica, content: string | null): Promise<boolean> {
    this.guardandoTipo.set(kind);
    this.errores.update((actuales) => ({ ...actuales, [kind]: undefined }));
    try {
      this.aplicar(
        await firstValueFrom(this.http.put<PoliticasDeEvento>(this.url(`/${kind}`), { content })),
        kind,
      );
      return true;
    } catch (error) {
      const mensaje =
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.politicas.errorGuardar');
      this.errores.update((actuales) => ({ ...actuales, [kind]: mensaje }));
      if (error instanceof ApiError && error.status === 409) {
        await this.cargar();
      }
      return false;
    } finally {
      this.guardandoTipo.set(null);
    }
  }
}
