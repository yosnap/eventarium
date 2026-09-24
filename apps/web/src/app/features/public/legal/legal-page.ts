import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  computed,
  inject,
  input,
  makeStateKey,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { seoDePagina } from '../../../core/seo/meta.service';
import { MarkdownSeguro } from '../../../shared/legal/markdown-seguro';
import { Alert } from '../../../shared/ui/alert';
import { Reveal } from '../../../shared/ui/reveal.directive';

/** Ruta pública → título traducible y ruta de la API. */
const PAGINAS = {
  'aviso-legal': { titulo: 'legal.avisoLegal', api: 'aviso-legal' },
  privacidad: { titulo: 'legal.privacidad', api: 'privacidad' },
  cookies: { titulo: 'legal.cookies', api: 'cookies' },
  'condiciones-de-inscripcion': {
    titulo: 'legal.condicionesInscripcion',
    api: 'condiciones-de-inscripcion',
  },
} as const;

type ClavePagina = keyof typeof PAGINAS;

interface LegalPageResponse {
  readonly content: string;
}

/**
 * Página legal pública: aviso legal, privacidad, cookies o condiciones de
 * inscripción.
 *
 * El contenido llega en SSR como Markdown restringido (mismo patrón
 * `TransferState` que `event-page.ts`) y lo pinta `<app-markdown-seguro>`:
 * texto plano escapado en SSR y antes de hidratar, HTML saneado solo en el
 * navegador. Al ser un `computed` sobre la entrada, también se sanea cuando
 * el contenido llega tarde en una navegación cliente-cliente. Un `<script>`
 * guardado como contenido legal nunca llega a ejecutarse.
 */
@Component({
  selector: 'app-legal-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Reveal, MarkdownSeguro],
  template: `
    <ng-container *transloco="let t">
      <div class="ancho-maximo" appReveal>
        <h1>{{ t(tituloClave()) }}</h1>

        @if (cargando()) {
          <p>{{ t('legal.cargando') }}</p>
        } @else if (error()) {
          <app-alert tone="error">{{ t('legal.error') }}</app-alert>
        } @else {
          <app-markdown-seguro [texto]="contenidoBruto() ?? ''" />
        }
      </div>
    </ng-container>
  `,
  styles: `
    .ancho-maximo {
      padding: var(--space-lg) 0;
    }
    h1 {
      margin-top: 0;
    }
  `,
})
export class LegalPage implements OnInit {
  readonly page = input.required<ClavePagina>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = seoDePagina();
  private readonly transloco = inject(TranslocoService);

  protected readonly contenidoBruto = signal<string | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal(false);

  protected readonly tituloClave = computed(() => PAGINAS[this.page()].titulo);

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<LegalPageResponse>(`legal-page:${this.page()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
      this.cargando.set(false);
      return;
    }

    try {
      const respuesta = await firstValueFrom(
        this.http.get<LegalPageResponse>(
          this.api.url(`/public/legal/${PAGINAS[this.page()].api}`),
          { headers: this.api.serverForwardHeaders() },
        ),
      );
      this.aplicar(respuesta);
      if (this.api.isServer) {
        this.transferState.set(clave, respuesta);
      }
    } catch {
      this.error.set(true);
    } finally {
      this.cargando.set(false);
    }
  }

  private aplicar(respuesta: LegalPageResponse): void {
    this.contenidoBruto.set(respuesta.content);
    this.seo.set({ title: this.transloco.translate(this.tituloClave()) });
  }
}
