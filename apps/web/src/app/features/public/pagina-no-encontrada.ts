import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { seoDePagina } from '../../core/seo/meta.service';
import { NotFoundStatusService } from '../../core/ssr/not-found-status.service';
import { Alert } from '../../shared/ui/alert';

/**
 * Destino del comodín: una URL que no es de ninguna página. Responde 404 real
 * en SSR (no una portada con 200) y no llama al API.
 */
@Component({
  selector: 'app-pagina-no-encontrada',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Alert, RouterLink, TranslocoDirective],
  template: `
    <main class="pagina-no-encontrada" *transloco="let t">
      <app-alert tone="error">{{
        transitorio ? t('publico.noEncontrada.temporal') : t('publico.noEncontrada.mensaje')
      }}</app-alert>
      <p>
        <a routerLink="/">{{ t('publico.noEncontrada.volver') }}</a>
      </p>
    </main>
  `,
  styles: `
    .pagina-no-encontrada {
      max-width: 40rem;
      margin: var(--sp-8) auto;
      padding: 0 var(--sp-4);
    }
  `,
})
export class PaginaNoEncontrada implements OnInit {
  private readonly notFound = inject(NotFoundStatusService);
  private readonly seo = seoDePagina();
  private readonly transloco = inject(TranslocoService);
  protected transitorio = false;

  ngOnInit(): void {
    this.transitorio = this.notFound.falloTemporal();
    this.notFound.falloTemporal.set(false);
    if (this.transitorio) {
      this.notFound.markUnavailable();
    } else {
      this.notFound.mark();
    }
    // Sin esto se quedaría el título y la canónica de la página anterior.
    this.seo.set({
      title: this.transloco.translate('publico.noEncontrada.mensaje'),
      noIndexar: true,
    });
  }
}
