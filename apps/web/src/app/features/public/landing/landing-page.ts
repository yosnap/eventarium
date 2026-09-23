import { ChangeDetectionStrategy, Component, type OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { SeoMetaService } from '../../../core/seo/meta.service';

/**
 * Landing de la instalación en la raíz pública. Sustituye al redirect
 * `/` → `/eventos`: el directorio sigue en `/eventos`, la raíz presenta la
 * plataforma (PRD `plans/260921-1445-prd-landing-page-plataforma`).
 */
@Component({
  selector: 'app-landing-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-hero" aria-labelledby="landing-hero-titulo">
        <p class="landing-hero-rotulo">{{ t('publico.landing.hero.rotulo') }}</p>
        <h1 id="landing-hero-titulo">{{ t('publico.landing.hero.titulo') }}</h1>
        <p class="landing-hero-subtitulo">{{ t('publico.landing.hero.subtitulo') }}</p>
        <div class="landing-hero-acciones">
          <a class="landing-cta landing-cta--primario" routerLink="/crear-organizacion">
            {{ t('publico.landing.hero.ctaOrganizar') }}
          </a>
          <a class="landing-cta landing-cta--secundario" routerLink="/eventos">
            {{ t('publico.landing.hero.ctaEventos') }}
          </a>
        </div>
      </section>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .landing-hero {
      display: grid;
      gap: var(--space-md);
      max-width: 44rem;
      padding: var(--space-xl) 0;
    }
    .landing-hero-rotulo {
      margin: 0;
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    h1 {
      margin: 0;
      font-family: var(--font-display);
      font-size: var(--fs-hero);
      line-height: 1.05;
    }
    .landing-hero-subtitulo {
      margin: 0;
      font-size: var(--fs-h3);
      color: var(--muted);
    }
    .landing-hero-acciones {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
    /* Enlaces con las métricas de Button (no un botón dentro de un enlace:
       axe lo marca como interactivo anidado). */
    .landing-cta {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 2.75rem;
      padding: 0 1.25rem;
      border: 1px solid transparent;
      border-radius: var(--radius-sm);
      font-weight: 700;
      text-decoration: none;
    }
    .landing-cta--primario {
      background: var(--accent);
      color: var(--on-accent);
    }
    .landing-cta--primario:hover {
      background: var(--accent-hi);
    }
    .landing-cta--secundario {
      border-color: var(--border-strong);
      color: var(--fg);
      font-weight: 500;
    }
    .landing-cta--secundario:hover {
      background: var(--surface-2);
    }
    @media (max-width: 30rem) {
      .landing-cta {
        flex: 1 1 100%;
      }
    }
  `,
})
export class LandingPage implements OnInit {
  private readonly seo = inject(SeoMetaService);
  private readonly transloco = inject(TranslocoService);

  ngOnInit(): void {
    this.seo.set({
      title: this.transloco.translate('publico.landing.seo.titulo'),
      description: this.transloco.translate('publico.landing.seo.descripcion'),
    });
  }
}
