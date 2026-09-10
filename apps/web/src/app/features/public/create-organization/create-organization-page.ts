import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { ApiError } from '../../../core/api/error.interceptor';
import { AuthService } from '../../../core/auth/auth.service';
import { AuthFrame } from '../../../layouts/public/auth-frame';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { TurnstileWidget } from '../../../shared/ui/turnstile-widget';

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DEBOUNCE_MS = 400;

type Campo = 'name' | 'slug' | 'firstName' | 'lastName';

// Marcas diacríticas combinantes (U+0300-U+036F) que deja `normalize('NFD')` separadas
// de la letra base: quitarlas es lo que convierte "Á" en "a" en vez de en "á".
const MARCAS_DIACRITICAS = /[̀-ͯ]/g;

/** Quita acentos y pasa a minúsculas con guiones, para sugerir un slug a partir del nombre. */
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
 * El slug se sugiere a partir del nombre mientras la persona no lo haya tocado a
 * mano, y se comprueba en vivo contra `check-slug` con *debounce* — sin él, cada
 * pulsación gastaría una petición y el límite se agotaría con el uso normal, no con
 * un ataque.
 */
@Component({
  selector: 'app-create-organization-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, AuthFrame, Alert, Button, Card, Input, TurnstileWidget],
  template: `
    <ng-container *transloco="let t">
      <app-auth-frame [titulo]="t('crearOrganizacion.titulo')">
        <app-card [heading]="t('crearOrganizacion.titulo')">
          @if (creada(); as organizacion) {
            <app-alert tone="exito" [title]="t('crearOrganizacion.exitoTitulo')">
              {{ t('crearOrganizacion.exitoDetalle') }}
              <p>
                <a [href]="urlPanel(organizacion.host)">{{ t('crearOrganizacion.irAlPanel') }}</a>
              </p>
            </app-alert>
          } @else {
            <form (submit)="enviar($event)" novalidate>
              <app-input
                [label]="t('crearOrganizacion.nombre')"
                [required]="true"
                [error]="errores().name"
                [value]="name()"
                (valueChange)="alEscribirNombre($event)"
                (blurred)="validar('name')"
              />
              <app-input
                [label]="t('crearOrganizacion.slug')"
                [required]="true"
                [error]="errores().slug"
                [hint]="ayudaSlug(t)"
                [value]="slug()"
                (valueChange)="alEscribirSlug($event)"
                (blurred)="validar('slug')"
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
      </app-auth-frame>
    </ng-container>
  `,
  styles: `
    app-card {
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
  protected readonly slug = signal('');
  protected readonly firstName = signal('');
  protected readonly lastName = signal('');
  protected readonly turnstileToken = signal<string | null>(null);
  protected readonly enviando = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly creada = signal<{ host: string } | null>(null);
  protected readonly errores = signal<Record<Campo, string | null>>({
    name: null,
    slug: null,
    firstName: null,
    lastName: null,
  });

  /** `null` = todavía sin comprobar; se distingue de `true`/`false` para no mostrar
   * ni «disponible» ni «ocupado» mientras la persona sigue escribiendo. */
  protected readonly slugDisponible = signal<boolean | null>(null);
  protected readonly comprobandoSlug = signal(false);
  private slugTocadoManualmente = false;
  private debounce: ReturnType<typeof setTimeout> | null = null;

  protected alEscribirNombre(valor: string): void {
    this.name.set(valor);
    if (!this.slugTocadoManualmente) {
      this.slug.set(slugify(valor));
      this.programarComprobacionSlug();
    }
  }

  protected alEscribirSlug(valor: string): void {
    this.slugTocadoManualmente = true;
    this.slug.set(valor.toLowerCase());
    this.programarComprobacionSlug();
  }

  private programarComprobacionSlug(): void {
    this.slugDisponible.set(null);
    if (this.debounce) {
      clearTimeout(this.debounce);
    }
    const valor = this.slug().trim();
    if (!valor || !SLUG_RE.test(valor)) {
      return;
    }
    this.debounce = setTimeout(() => void this.comprobarSlug(valor), DEBOUNCE_MS);
  }

  private async comprobarSlug(valor: string): Promise<void> {
    this.comprobandoSlug.set(true);
    try {
      const disponible = await this.auth.checkSlug(valor);
      // Descarta el resultado si la persona ya ha vuelto a escribir: evita que una
      // respuesta lenta de una comprobación antigua pise a una más reciente.
      if (valor === this.slug().trim()) {
        this.slugDisponible.set(disponible);
      }
    } catch {
      this.slugDisponible.set(null);
    } finally {
      this.comprobandoSlug.set(false);
    }
  }

  protected ayudaSlug(t: (clave: string) => string): string {
    if (this.comprobandoSlug()) return t('crearOrganizacion.comprobandoSlug');
    if (this.slugDisponible() === true) return t('crearOrganizacion.slugDisponible');
    if (this.slugDisponible() === false) return t('crearOrganizacion.slugNoDisponible');
    return t('crearOrganizacion.slugAyuda');
  }

  private errorDe(campo: Campo): string | null {
    switch (campo) {
      case 'name':
        return this.name().trim()
          ? null
          : this.transloco.translate('crearOrganizacion.nombreRequerido');
      case 'slug': {
        const valor = this.slug().trim();
        if (!valor) return this.transloco.translate('crearOrganizacion.slugRequerido');
        if (!SLUG_RE.test(valor)) return this.transloco.translate('crearOrganizacion.slugInvalido');
        if (this.slugDisponible() === false) {
          return this.transloco.translate('crearOrganizacion.slugNoDisponible');
        }
        return null;
      }
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

  protected urlPanel(host: string): string {
    return `${typeof window === 'undefined' ? 'https:' : window.location.protocol}//${host}/admin/login`;
  }

  protected async enviar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);

    const nuevosErrores: Record<Campo, string | null> = {
      name: this.errorDe('name'),
      slug: this.errorDe('slug'),
      firstName: this.errorDe('firstName'),
      lastName: this.errorDe('lastName'),
    };
    this.errores.set(nuevosErrores);
    if (Object.values(nuevosErrores).some((mensaje) => mensaje)) {
      return;
    }

    this.enviando.set(true);
    try {
      const organizacion = await this.auth.createOrganization({
        name: this.name().trim(),
        slug: this.slug().trim(),
        firstName: this.firstName().trim(),
        lastName: this.lastName().trim(),
        turnstileToken: this.turnstileToken() ?? '',
      });
      this.creada.set({ host: organizacion.host });
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
