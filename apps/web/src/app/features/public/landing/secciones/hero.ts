import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { Parallax } from '../animaciones.directive';
import { LandingIlustracion } from '../ilustraciones/ilustracion';

@Component({
  selector: 'app-landing-hero',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Parallax, LandingIlustracion],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-hero" aria-labelledby="landing-hero-titulo">
        <div class="landing-hero-texto">
          <p class="landing-rotulo">{{ t('publico.landing.hero.rotulo') }}</p>
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
        </div>
        <app-landing-ilustracion tipo="inscripciones" appParallax="0.12" />
      </section>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .landing-hero {
      display: grid;
      gap: var(--space-lg);
      align-items: center;
      padding: var(--sp-8) 0 var(--sp-9);
    }
    @media (min-width: 60rem) {
      .landing-hero {
        grid-template-columns: 1.15fr 1fr;
      }
    }
    .landing-hero-texto {
      display: grid;
      gap: var(--space-md);
    }
    h1 {
      margin: 0;
      font-family: var(--font-display);
      font-size: var(--fs-hero);
      line-height: 1.05;
    }
    .landing-hero-subtitulo {
      margin: 0;
      max-width: 52ch;
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
export class LandingHero {}
