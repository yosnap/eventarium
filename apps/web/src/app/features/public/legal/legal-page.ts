import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  PendingTasks,
  TransferState,
  computed,
  effect,
  inject,
  input,
  makeStateKey,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { SeoMetaService } from '../../../core/seo/meta.service';
import { markdownToSafeHtml } from '../../../shared/legal/sanitize-markdown';
import { Alert } from '../../../shared/ui/alert';

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
 * `TransferState` que `event-page.ts`) y se muestra primero como **texto
 * plano interpolado por Angular** — siempre escapado, nunca HTML — tanto en
 * SSR como antes de hidratar. Solo en el navegador se sustituye por el HTML
 * saneado con `marked` + `DOMPurify` (`sanitize-markdown.ts`), mediante un
 * `effect()` que reacciona a `contenidoBruto()` (nunca un `afterNextRender`
 * de una sola vez: `cargar()` es asíncrono y en una navegación cliente-cliente
 * el contenido puede llegar después del primer render, dejando la página en
 * texto plano para siempre si nadie reintenta el saneado). El `effect()` no
 * hace nada en el servidor (`this.api.isServer`): `DOMPurify` necesita un DOM
 * de navegador real. Un `<script>` guardado como contenido legal nunca llega
 * a ejecutarse en ninguna de las dos fases.
 */
@Component({
  selector: 'app-legal-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t(tituloClave()) }}</h1>

      @if (cargando()) {
        <p>{{ t('legal.cargando') }}</p>
      } @else if (error()) {
        <app-alert tone="error">{{ t('legal.error') }}</app-alert>
      } @else if (htmlSeguro(); as html) {
        <div class="contenido" [innerHTML]="html"></div>
      } @else {
        <p class="contenido-plano">{{ contenidoBruto() }}</p>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    .contenido,
    .contenido-plano {
      max-width: 48rem;
      white-space: pre-line;
      line-height: 1.6;
    }
    .contenido ::ng-deep ul,
    .contenido ::ng-deep ol {
      padding-inline-start: 1.5rem;
    }
  `,
})
export class LegalPage implements OnInit {
  readonly page = input.required<ClavePagina>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transferState = inject(TransferState);
  private readonly tareasPendientes = inject(PendingTasks);
  private readonly seo = inject(SeoMetaService);
  private readonly transloco = inject(TranslocoService);

  protected readonly contenidoBruto = signal<string | null>(null);
  protected readonly htmlSeguro = signal<string | null>(null);
  protected readonly cargando = signal(true);
  protected readonly error = signal(false);

  protected readonly tituloClave = computed(() => PAGINAS[this.page()].titulo);

  constructor() {
    // Reacciona a cada cambio de `contenidoBruto()`, no solo al primer
    // render: en una navegación cliente-cliente `cargar()` puede resolver
    // después de que el componente ya se haya pintado una vez. Nunca corre en
    // el servidor: el saneado con DOMPurify necesita un DOM de navegador real
    // (ver `sanitize-markdown.ts`).
    effect(() => {
      const bruto = this.contenidoBruto();
      if (bruto === null || this.api.isServer) {
        return;
      }
      this.htmlSeguro.set(markdownToSafeHtml(bruto));
    });
  }

  ngOnInit(): void {
    void this.tareasPendientes.run(() => this.cargar());
  }

  private async cargar(): Promise<void> {
    const clave = makeStateKey<LegalPageResponse>(`legal-page:${this.page()}`);
    const transferido = this.transferState.get(clave, null);
    if (transferido) {
      this.transferState.remove(clave);
      this.aplicar(transferido);
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
