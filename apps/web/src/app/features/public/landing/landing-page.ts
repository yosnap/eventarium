import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  type OnInit,
  ViewEncapsulation,
  afterNextRender,
  inject,
} from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

import { SeoMetaService } from '../../../core/seo/meta.service';
import { EnDirectoService } from './en-directo.service';
import { GsapLoader } from './gsap';
import { LandingColaborar } from './secciones/colaborar';
import { LandingEnDirecto } from './secciones/en-directo';
import { LandingFuncionalidades } from './secciones/funcionalidades';
import { LandingHero } from './secciones/hero';
import { LandingQuienesSomos } from './secciones/quienes-somos';

/** Cada cuánto se recalcula «en directo» con el reloj del cliente. */
const INTERVALO_EN_DIRECTO_MS = 60_000;

/**
 * Landing de la instalación en la raíz pública. Sustituye al redirect
 * `/` → `/eventos`: el directorio sigue en `/eventos`, la raíz presenta la
 * plataforma (PRD `plans/260921-1445-prd-landing-page-plataforma`).
 */
@Component({
  selector: 'app-landing-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    LandingHero,
    LandingEnDirecto,
    LandingQuienesSomos,
    LandingFuncionalidades,
    LandingColaborar,
  ],
  template: `
    <app-landing-hero />
    <div class="ancho-maximo">
      <app-landing-en-directo />
      <app-landing-quienes-somos />
      <app-landing-funcionalidades />
      <app-landing-colaborar />
    </div>
  `,
  // Sin encapsulación a propósito: estas clases (prefijo `landing-`) las
  // comparten las secciones hijas. Van aquí y no en `styles.css` para que
  // viajen en el chunk lazy de la landing y no en el bundle inicial; cada
  // sección lleva además su propio bloque para que ninguno pase del aviso de
  // 4 kB de `anyComponentStyle`.
  encapsulation: ViewEncapsulation.None,
  styles: `
    app-landing-page {
      display: block;
    }
    .landing-seccion {
      padding: var(--sp-9) 0;
      border-top: 1px solid var(--border);
    }
    .landing-rotulo {
      margin: 0 0 var(--space-xs);
      font-family: var(--font-mono);
      font-size: var(--fs-label);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
    }
    .landing-seccion h2 {
      margin: 0 0 var(--space-md);
      font-family: var(--font-display);
      font-size: var(--fs-h1);
      line-height: 1.1;
      max-width: 28ch;
    }
    .landing-intro {
      margin: 0 0 var(--space-lg);
      max-width: 60ch;
      color: var(--muted);
      font-size: var(--fs-h3);
    }
    .landing-dos-columnas {
      display: grid;
      gap: var(--space-lg);
      align-items: center;
    }
    @media (min-width: 48rem) {
      .landing-dos-columnas {
        grid-template-columns: 1fr 1fr;
      }
      .landing-dos-columnas--invertida > :first-child {
        order: 2;
      }
    }
    .landing-parrafo {
      margin: 0 0 var(--space-sm);
      max-width: 60ch;
      line-height: 1.6;
    }
    .landing-parrafo--grande {
      font-size: var(--fs-h3);
      line-height: 1.45;
      max-width: 40ch;
    }
    .landing-palabra {
      will-change: opacity;
    }
    .landing-foto {
      margin: 0;
      overflow: hidden;
      border-radius: var(--radius-lg);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-lg);
      background: var(--surface-2);
    }
    .landing-foto img {
      display: block;
      width: 100%;
      height: auto;
      aspect-ratio: 4 / 3;
      object-fit: cover;
    }
    .landing-resaltado {
      font-weight: inherit;
      color: var(--accent);
    }
    h1 .landing-resaltado,
    h2 .landing-resaltado {
      font-weight: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-hi));
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }
    .landing-funcionalidad {
      padding: var(--sp-7) 0;
    }
    .landing-funcionalidad + .landing-funcionalidad {
      border-top: 1px solid var(--border);
    }
    .landing-funcionalidad h3 {
      margin: 0 0 var(--space-sm);
      font-family: var(--font-display);
      font-size: var(--fs-h2);
      line-height: 1.15;
    }

    /* Colaborar */
  `,
})
export class LandingPage implements OnInit {
  private readonly seo = inject(SeoMetaService);
  private readonly transloco = inject(TranslocoService);
  private readonly enDirecto = inject(EnDirectoService);

  constructor() {
    const gsap = inject(GsapLoader).cargar();
    const destroyRef = inject(DestroyRef);
    // Solo tras hidratar: el primer render del cliente debe coincidir con el
    // HTML servido (el servicio pinta el conjunto transferido hasta entonces).
    afterNextRender(() => {
      this.enDirecto.refrescar();
      const temporizador = setInterval(() => this.enDirecto.refrescar(), INTERVALO_EN_DIRECTO_MS);
      // `afterNextRender` no ejecuta el valor devuelto como limpieza.
      destroyRef.onDestroy(() => clearInterval(temporizador));
      // ScrollTrigger mide antes de que carguen las fuentes; sin este refresco
      // los disparadores quedan desplazados.
      void gsap.then((cargado) => {
        if (!cargado) return;
        void document.fonts.ready.then(() => cargado.ScrollTrigger.refresh());
      });
    });
  }

  ngOnInit(): void {
    this.seo.set({
      title: this.transloco.translate('publico.landing.seo.titulo'),
      description: this.transloco.translate('publico.landing.seo.descripcion'),
    });
  }
}
