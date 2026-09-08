import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterNextRender,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

import { CookieConsentService } from '../../core/cookies/cookie-consent.service';
import { Button } from '../ui/button';

/**
 * Banner de cookies (fase 5 del PRD): tres acciones con el mismo peso visual
 * ("Aceptar todo" / "Rechazar todo" / "Personalizar"), sin ninguna
 * preseleccionada ni destacada — las tres usan la variante `secundario` de
 * `Button` a propósito, nunca `primario`, que sí llevaría color de énfasis.
 *
 * Gestión de foco (WCAG 2.4.3): al aparecer, el foco se mueve al primer
 * control del banner; al decidir (banner desaparece), vuelve al elemento que
 * tenía el foco antes de que apareciera. Sin trampa de foco: el resto de la
 * página sigue siendo alcanzable con Tab mientras el banner está visible, no
 * es un diálogo modal que bloquee la navegación.
 */
@Component({
  selector: 'app-cookie-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, TranslocoDirective, Button],
  template: `
    <ng-container *transloco="let t">
      @if (consentimiento.mostrarBanner()) {
        <div
          #panel
          class="banner"
          role="region"
          [attr.aria-label]="t('cookies.banner.titulo')"
          tabindex="-1"
        >
          <p>
            {{ t('cookies.banner.texto') }}
            <a routerLink="/legal/cookies">{{ t('legal.cookies') }}</a>
          </p>

          @if (personalizando()) {
            <fieldset>
              <legend>{{ t('cookies.banner.categorias') }}</legend>
              <label class="opcion">
                <input type="checkbox" checked disabled />
                {{ t('cookies.banner.necesarias') }}
              </label>
              <label class="opcion">
                <input
                  type="checkbox"
                  [checked]="analiticas()"
                  (change)="analiticas.set(!analiticas())"
                />
                {{ t('cookies.banner.analiticas') }}
              </label>
              <label class="opcion">
                <input
                  type="checkbox"
                  [checked]="marketing()"
                  (change)="marketing.set(!marketing())"
                />
                {{ t('cookies.banner.marketing') }}
              </label>
            </fieldset>
            <div class="acciones">
              <app-button variant="secundario" (pulsado)="guardarPersonalizacion()">
                {{ t('cookies.banner.guardarPreferencias') }}
              </app-button>
              <app-button variant="secundario" (pulsado)="personalizando.set(false)">
                {{ t('cookies.banner.volver') }}
              </app-button>
            </div>
          } @else {
            <div class="acciones">
              <app-button variant="secundario" (pulsado)="aceptarTodo()">
                {{ t('cookies.banner.aceptarTodo') }}
              </app-button>
              <app-button variant="secundario" (pulsado)="rechazarTodo()">
                {{ t('cookies.banner.rechazarTodo') }}
              </app-button>
              <app-button variant="secundario" (pulsado)="personalizando.set(true)">
                {{ t('cookies.banner.personalizar') }}
              </app-button>
            </div>
          }
        </div>
      }
    </ng-container>
  `,
  styles: `
    .banner {
      position: fixed;
      inset-inline: 0;
      bottom: 0;
      z-index: 100;
      display: grid;
      gap: var(--space-md);
      padding: var(--space-lg);
      background-color: var(--color-surface);
      border-top: 1px solid var(--color-border);
      box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.12);
    }
    .banner:focus {
      outline: none;
    }
    p {
      margin: 0;
      max-width: 60rem;
    }
    fieldset {
      display: grid;
      gap: var(--space-xs);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      padding: var(--space-sm) var(--space-md);
    }
    .opcion {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
    }
    .acciones {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
    }
  `,
})
export class CookieBanner {
  protected readonly consentimiento = inject(CookieConsentService);

  protected readonly personalizando = signal(false);
  protected readonly analiticas = signal(false);
  protected readonly marketing = signal(false);

  private readonly panel = viewChild<ElementRef<HTMLElement>>('panel');
  private elementoConFocoPrevio: HTMLElement | null = null;

  constructor() {
    afterNextRender(() => {
      if (this.consentimiento.mostrarBanner()) {
        this.moverFocoAlBanner();
      }
    });
  }

  private moverFocoAlBanner(): void {
    this.elementoConFocoPrevio = document.activeElement as HTMLElement | null;
    this.panel()?.nativeElement.focus();
  }

  private devolverFoco(): void {
    this.elementoConFocoPrevio?.focus();
    this.elementoConFocoPrevio = null;
  }

  protected async aceptarTodo(): Promise<void> {
    await this.consentimiento.aceptarTodo();
    this.devolverFoco();
  }

  protected async rechazarTodo(): Promise<void> {
    await this.consentimiento.rechazarTodo();
    this.devolverFoco();
  }

  protected async guardarPersonalizacion(): Promise<void> {
    const categorias: ('analytics' | 'marketing')[] = [];
    if (this.analiticas()) categorias.push('analytics');
    if (this.marketing()) categorias.push('marketing');
    await this.consentimiento.personalizar(categorias);
    this.personalizando.set(false);
    this.devolverFoco();
  }
}
