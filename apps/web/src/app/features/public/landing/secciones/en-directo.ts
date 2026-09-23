import { ChangeDetectionStrategy, Component, type OnInit, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { Chip } from '../../../../shared/ui/chip';
import { Reveal } from '../../../../shared/ui/reveal.directive';
import { EnDirectoService, type EventoEnDirecto } from '../en-directo.service';

const CLAVE_FORMATO: Record<EventoEnDirecto['location_mode'], string> = {
  in_person: 'publico.eventos.formato.presencial',
  online: 'publico.eventos.formato.online',
  hybrid: 'publico.eventos.formato.hibrido',
};

@Component({
  selector: 'app-landing-en-directo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Chip, Reveal],
  template: `
    <ng-container *transloco="let t">
      <section class="landing-seccion" aria-labelledby="landing-directo-titulo">
        <p class="landing-rotulo">{{ t('publico.landing.enDirecto.rotulo') }}</p>
        <h2 id="landing-directo-titulo">
          <span class="landing-pulso" aria-hidden="true"></span>
          {{ t('publico.landing.enDirecto.titulo') }}
        </h2>
        @if (servicio.eventos().length > 0) {
          <ul class="landing-directo-lista">
            @for (evento of servicio.eventos(); track evento.slug; let i = $index) {
              <li appReveal [index]="i">
                <a class="landing-directo-tarjeta" [routerLink]="['/eventos', evento.slug]">
                  <span class="landing-directo-portada">
                    @if (evento.cover_url) {
                      <img
                        [src]="evento.cover_url"
                        alt=""
                        width="640"
                        height="280"
                        loading="lazy"
                      />
                    }
                  </span>
                  <span class="landing-directo-cuerpo">
                    <h3>{{ evento.title }}</h3>
                    <span class="landing-directo-meta">
                      <app-chip tone="ok">{{ t(claveFormato(evento)) }}</app-chip>
                      @if (evento.location_name || evento.city) {
                        <span>{{ lugar(evento) }}</span>
                      }
                    </span>
                  </span>
                </a>
              </li>
            }
          </ul>
        } @else if (!servicio.cargando()) {
          <div class="landing-vacio">
            <p>{{ t('publico.landing.enDirecto.vacio') }}</p>
            <a routerLink="/eventos">{{ t('publico.landing.enDirecto.vacioEnlace') }}</a>
          </div>
        }
      </section>
    </ng-container>
  `,
  styles: `
    .landing-directo-lista {
      display: grid;
      gap: var(--space-sm);
      grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
      margin: 0;
      padding: 0;
      list-style: none;
    }
    .landing-directo-tarjeta {
      display: grid;
      grid-template-rows: auto 1fr;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--surface);
      color: inherit;
      text-decoration: none;
      transition: border-color 0.15s ease;
    }
    .landing-directo-tarjeta:hover,
    .landing-directo-tarjeta:focus-visible {
      border-color: var(--accent);
    }
    .landing-directo-portada {
      aspect-ratio: 16 / 7;
      background: linear-gradient(135deg, var(--accent-dim), transparent 60%), var(--surface-2);
    }
    .landing-directo-portada img {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .landing-directo-cuerpo {
      display: grid;
      gap: var(--space-xs);
      padding: var(--space-md);
    }
    .landing-directo-cuerpo h3 {
      margin: 0;
      font-size: var(--fs-h3);
    }
    .landing-directo-meta {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-xs);
      align-items: center;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .landing-pulso {
      display: inline-block;
      width: 0.6rem;
      height: 0.6rem;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 0 var(--accent-dim);
      animation: landing-pulso 1.6s ease-out infinite;
    }
    @keyframes landing-pulso {
      to {
        box-shadow: 0 0 0 0.6rem transparent;
      }
    }
    .landing-vacio {
      display: grid;
      gap: var(--space-xs);
      justify-items: start;
      padding: var(--space-lg);
      border: 1px dashed var(--border-strong);
      border-radius: var(--radius-md);
      color: var(--muted);
    }

    /* Funcionalidades */
    :host {
      display: block;
    }
    h2 {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
  `,
})
export class LandingEnDirecto implements OnInit {
  protected readonly servicio = inject(EnDirectoService);

  ngOnInit(): void {
    void this.servicio.cargar();
  }

  protected claveFormato(evento: EventoEnDirecto): string {
    return CLAVE_FORMATO[evento.location_mode];
  }

  protected lugar(evento: EventoEnDirecto): string {
    return [evento.location_name, evento.city].filter(Boolean).join(' · ');
  }
}
