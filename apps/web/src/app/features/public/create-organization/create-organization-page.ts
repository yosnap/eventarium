import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { Reveal } from '../../../shared/ui/reveal.directive';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

type Campo = 'name' | 'firstName' | 'lastName';

/** Intentos de identificador antes de rendirse: el base más sufijos -2, -3… */
const INTENTOS_DE_SLUG = 5;

// Marcas diacríticas combinantes (U+0300-U+036F) que deja `normalize('NFD')` separadas
// de la letra base: quitarlas es lo que convierte "Á" en "a" en vez de en "á".
const MARCAS_DIACRITICAS = /[̀-ͯ]/g;

/** Quita acentos y pasa a minúsculas con guiones, para generar el identificador
 * interno de la organización a partir de su nombre. */
function slugify(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(MARCAS_DIACRITICAS, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Última pantalla del alta libre: de cuenta verificada a organización operativa.
 *
 * Sin dominio por organización (fase 6 del plan de organización sin dominio), el
 * identificador interno ya no aparece en ninguna URL pública ni se muestra en el
 * panel: se genera en silencio a partir del nombre y, si colisiona con otra
 * organización o con uno reservado, se reintenta con un sufijo antes de dar error.
 * La persona solo ve el nombre, quién es, y el desafío de Turnstile.
 */
@Component({
  selector: 'app-create-organization-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Button, Card, Input, Reveal, TurnstileWidget],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('crearOrganizacion.titulo')">
        <div class="envoltura" appReveal>
          <app-card [heading]="t('crearOrganizacion.titulo')">
            @if (creada()) {
              <app-alert tone="exito" [title]="t('crearOrganizacion.exitoTitulo')">
                {{ t('crearOrganizacion.exitoDetalle') }}
              </app-alert>
            } @else {
              <form (submit)="enviar($event)" novalidate>
                <app-input
                  [label]="t('crearOrganizacion.nombre')"
                  [required]="true"
                  [error]="errores().name"
                  [value]="name()"
                  (valueChange)="name.set($event)"
                  (blurred)="validar('name')"
                />
                <app-input
                  [label]="t('crearOrganizacion.nombrePersona')"
                  autocomplete="given-name"
                  [required]="true"
                  [error]="errores().firstName"
                  [(value)]="firstName"
                  (blurred)="validar('firstName')"
                />
                <app-input
                  [label]="t('crearOrganizacion.apellidos')"
                  autocomplete="family-name"
                  [required]="true"
                  [error]="errores().lastName"
                  [(value)]="lastName"
                  (blurred)="validar('lastName')"
                />

                <app-turnstile-widget (resuelto)="turnstileToken.set($event)" />

                @if (error(); as mensaje) {
                  <app-alert tone="error" [title]="t('crearOrganizacion.error')">{{
                    mensaje
                  }}</app-alert>
                }

                <app-button type="submit" [loading]="enviando()">
                  {{ enviando() ? t('crearOrganizacion.creando') : t('crearOrganizacion.crear') }}
                </app-button>
              </form>
            }
          </app-card>
        </div>
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    .envoltura {
      width: min(28rem, 100%);
    }
    form {
      display: grid;
      gap: var(--space-md);
    }
  `,
})
export class CreateOrganizationPage {
  private readonly auth = inject(AuthService);
  private readonly transloco = inject(TranslocoService);

  protected readonly name = signal('');
  protected readonly firstName = signal('');
  protected readonly lastName = signal('');
  protected readonly turnstileToken = signal<string | null>(null);
  protected readonly enviando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly creada = signal(false);
  protected readonly errores = signal<Record<Campo, string | null>>({
    name: null,
    firstName: null,
    lastName: null,
  });

  private errorDe(campo: Campo): string | null {
    switch (campo) {
      case 'name':
        return this.name().trim()
          ? null
          : this.transloco.translate('crearOrganizacion.nombreRequerido');
      case 'firstName':
        return this.firstName().trim()
          ? null
          : this.transloco.translate('crearOrganizacion.nombrePersonaRequerido');
      case 'lastName':
        return this.lastName().trim()
          ? null
          : this.transloco.translate('crearOrganizacion.apellidosRequeridos');
    }
  }

  protected validar(campo: Campo): void {
    this.errores.update((actuales) => ({ ...actuales, [campo]: this.errorDe(campo) }));
  }

  /**
   * Identificador para la organización: el generado a partir del nombre y, si ya
   * está ocupado o reservado, el primero libre con sufijo (`nombre-2`, `nombre-3`…).
   * `null` si el nombre no genera ninguno válido o ninguno de los intentos está
   * libre. Si la comprobación falla por red, se devuelve el base sin sufijo: el
   * `UNIQUE` de la base de datos sigue siendo la fuente de verdad (ver
   * `GET /organizations/check-slug`), así que lo peor que puede pasar es que la
   * creación devuelva el error de conflicto.
   */
  private async elegirSlug(): Promise<string | null> {
    const base = slugify(this.name());
    if (!base) {
      return null;
    }
    try {
      let candidato = base;
      for (let intento = 2; intento <= INTENTOS_DE_SLUG; intento++) {
        if (await this.auth.checkSlug(candidato)) {
          return candidato;
        }
        candidato = `${base}-${intento}`;
      }
      return null;
    } catch {
      return base;
    }
  }

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);

    const nuevosErrores: Record<Campo, string | null> = {
      name: this.errorDe('name'),
      firstName: this.errorDe('firstName'),
      lastName: this.errorDe('lastName'),
    };
    this.errores.set(nuevosErrores);
    if (Object.values(nuevosErrores).some((mensaje) => mensaje)) {
      return;
    }

    this.enviando.set(true);
    try {
      const slug = await this.elegirSlug();
      if (!slug) {
        this.error.set(this.transloco.translate('crearOrganizacion.nombreNoDisponible'));
        return;
      }

      // `createOrganization` ya deja la sesión activa en la organización
      // recién creada (fase 4 del plan de organización sin dominio): sin
      // dominio propio, no hay a qué host redirigir.
      await this.auth.createOrganization({
        name: this.name().trim(),
        slug,
        firstName: this.firstName().trim(),
        lastName: this.lastName().trim(),
        turnstileToken: this.turnstileToken() ?? '',
      });
      this.creada.set(true);
      window.location.href = '/dashboard';
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('crearOrganizacion.error'),
      );
    } finally {
      this.enviando.set(false);
    }
  }
}
