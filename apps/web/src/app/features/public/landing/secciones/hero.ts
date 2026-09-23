import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { HeroEscena } from '../animaciones.directive';
import { LandingIlustracion } from '../ilustraciones/ilustracion';
import { ResaltarPipe } from '../resaltar.pipe';

@Component({
  selector: 'app-landing-hero',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, HeroEscena, LandingIlustracion, ResaltarPipe],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-hero" aria-labelledby="landing-hero-titulo" appHeroEscena>
        <div class="ancho-maximo landing-hero-en" data-hero-contenido>
          <div class="landing-hero-texto">
            <p class="landing-rotulo" data-entrada>{{ t('publico.landing.hero.rotulo') }}</p>
            <h1
              id="landing-hero-titulo"
              data-entrada
              [innerHTML]="t('publico.landing.hero.titulo') | resaltar"
            ></h1>
            <p
              class="landing-hero-subtitulo"
              data-entrada
              [innerHTML]="t('publico.landing.hero.subtitulo') | resaltar"
            ></p>
            <div class="landing-hero-acciones" data-entrada>
              <a class="landing-cta landing-cta--primario" routerLink="/crear-organizacion">
                {{ t('publico.landing.hero.ctaOrganizar') }}
              </a>
              <a class="landing-cta landing-cta--secundario" routerLink="/eventos">
                {{ t('publico.landing.hero.ctaEventos') }}
              </a>
            </div>
          </div>
          <app-landing-ilustracion tipo="inscripciones" data-entrada />
        </div>
      </section>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .landing-hero {
      /* A sangre completa: el fondo ocupa la ventana, el contenido va dentro
         de .ancho-maximo como en el resto de páginas. */
      min-height: calc(100vh - 4rem);
      display: grid;
      align-items: center;
      background:
        radial-gradient(60% 50% at 80% 20%, var(--accent-dim), transparent 70%),
        linear-gradient(var(--grid-line) 1px, transparent 1px) 0 0 / var(--grid-size)
          var(--grid-size),
        linear-gradient(90deg, var(--grid-line) 1px, transparent 1px) 0 0 / var(--grid-size)
          var(--grid-size);
      border-bottom: 1px solid var(--border);
    }
    .landing-hero-en {
      display: grid;
      gap: var(--space-lg);
      align-items: center;
      padding: var(--sp-8) 0;
      will-change: transform, opacity;
    }
    @media (min-width: 60rem) {
      .landing-hero-en {
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
      line-height: 1.02;
      letter-spacing: -0.02em;
      text-wrap: balance;
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
