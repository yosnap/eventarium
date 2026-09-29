import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { ThemingService } from '../../../core/theming/theming.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Checkbox } from '../../../shared/ui/checkbox';
import { Input } from '../../../shared/ui/input';
import { Textarea } from '../../../shared/ui/textarea';
import { PageHeader } from '../../../shared/ui/page-header';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface Organizacion {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly legal_name: string | null;
  readonly description: string | null;
  readonly website: string | null;
  readonly contact_email: string | null;
  readonly address: string | null;
  readonly public_page_enabled: boolean;
  readonly is_active: boolean;
}

type Campo = 'name' | 'contactEmail' | 'website';

const WEB_RE = /^https?:\/\/\S+$/;

/**
 * Datos generales de la organización: nombre, razón social, descripción, web y correo
 * de contacto. El branding (colores, tipografía, logo) vive en su propia pantalla.
 */
@Component({
  selector: 'app-organization-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    Alert,
    Button,
    Card,
    Checkbox,
    Input,
    Textarea,
    PageHeader,
    RouterLink,
  ],
  template: `
    <ng-container *transloco="let t">
      <app-page-header [rotulo]="t('admin.organizacion.rotulo')">
        {{ t('admin.organizacion.cabeceraInicio') }}
        <span class="mark">{{ t('admin.organizacion.cabeceraMarca') }}</span>
      </app-page-header>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <app-card>
          <form (submit)="guardar($event)" novalidate>
            <app-input
              [label]="t('admin.organizacion.nombre')"
              [required]="true"
              [error]="errores().name"
              [(value)]="name"
              (blurred)="validar('name')"
            />
            <app-input [label]="t('admin.organizacion.nombreLegal')" [(value)]="legalName" />
            <app-textarea
              [label]="t('admin.organizacion.descripcionCampo')"
              [(value)]="description"
            />
            <app-input
              [label]="t('admin.organizacion.web')"
              type="url"
              autocomplete="url"
              [error]="errores().website"
              [(value)]="website"
              (blurred)="validar('website')"
            />
            <app-input
              [label]="t('admin.organizacion.correoContacto')"
              type="email"
              autocomplete="email"
              [error]="errores().contactEmail"
              [(value)]="contactEmail"
              (blurred)="validar('contactEmail')"
            />

            <fieldset class="publica">
              <legend>{{ t('admin.organizacion.paginaPublica.titulo') }}</legend>
              <app-checkbox
                [label]="t('admin.organizacion.paginaPublica.activar')"
                [hint]="t('admin.organizacion.paginaPublica.pista')"
                [(checked)]="publicPageEnabled"
              />
              <app-input
                [label]="t('admin.organizacion.direccion')"
                autocomplete="street-address"
                [(value)]="address"
              />
              <p class="publica__lista-titulo">
                {{ t('admin.organizacion.paginaPublica.seHaraPublico') }}
              </p>
              <ul class="publica__lista">
                <li>{{ t('admin.organizacion.paginaPublica.campos.nombre') }}</li>
                <li>{{ t('admin.organizacion.paginaPublica.campos.descripcion') }}</li>
                <li>{{ t('admin.organizacion.paginaPublica.campos.web') }}</li>
                <li>{{ t('admin.organizacion.paginaPublica.campos.direccion') }}</li>
                <li>{{ t('admin.organizacion.paginaPublica.campos.logo') }}</li>
                <li>{{ t('admin.organizacion.paginaPublica.campos.redes') }}</li>
                <li>{{ t('admin.organizacion.paginaPublica.campos.eventos') }}</li>
              </ul>
              <p class="publica__nota">{{ t('admin.organizacion.paginaPublica.noSePublica') }}</p>
              @if (paginaActiva()) {
                <a class="publica__ver" [routerLink]="['/', slug()]">{{
                  t('admin.organizacion.paginaPublica.ver')
                }}</a>
              }
            </fieldset>

            @if (guardado()) {
              <app-alert tone="exito">{{ t('admin.organizacion.guardado') }}</app-alert>
            }
            @if (error(); as mensaje) {
              <app-alert tone="error" [title]="t('admin.organizacion.error')">{{
                mensaje
              }}</app-alert>
            }

            <app-button type="submit" [loading]="guardando()">
              {{ guardando() ? t('admin.organizacion.guardando') : t('comun.guardar') }}
            </app-button>
          </form>
        </app-card>
      }
    </ng-container>
  `,
  styles: `
    form {
      display: grid;
      gap: var(--space-md);
      max-width: 32rem;
    }
    .publica {
      display: grid;
      gap: var(--space-md);
      margin: 0;
      padding: var(--space-md);
      border: 1px solid var(--line);
      border-radius: var(--radius-md, 8px);
    }
    .publica legend {
      padding: 0 var(--space-sm, 8px);
      font-weight: 600;
    }
    .publica__lista-titulo,
    .publica__nota {
      margin: 0;
      font-size: var(--fs-sm);
      color: var(--muted);
    }
    .publica__lista {
      margin: 0;
      padding-left: 1.25rem;
      font-size: var(--fs-sm);
    }
    .publica__ver {
      justify-self: start;
      color: var(--accent);
    }
  `,
})
export class OrganizationPage {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly theming = inject(ThemingService);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly guardado = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly name = signal('');
  protected readonly legalName = signal('');
  protected readonly description = signal('');
  protected readonly website = signal('');
  protected readonly contactEmail = signal('');
  protected readonly address = signal('');
  protected readonly publicPageEnabled = signal(false);
  protected readonly slug = signal('');
  /** La página existe de verdad: interruptor activado **y guardado**. */
  protected readonly paginaActiva = signal(false);
  protected readonly errores = signal<Record<Campo, string | null>>({
    name: null,
    contactEmail: null,
    website: null,
  });

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      const organizacion = await firstValueFrom(
        this.http.get<Organizacion>(this.api.url('/organizations/me')),
      );
      this.name.set(organizacion.name);
      this.legalName.set(organizacion.legal_name ?? '');
      this.description.set(organizacion.description ?? '');
      this.website.set(organizacion.website ?? '');
      this.contactEmail.set(organizacion.contact_email ?? '');
      this.address.set(organizacion.address ?? '');
      this.publicPageEnabled.set(organizacion.public_page_enabled);
      this.paginaActiva.set(organizacion.public_page_enabled);
      this.slug.set(organizacion.slug);
    } finally {
      this.cargando.set(false);
    }
  }

  private errorDe(campo: Campo): string | null {
    switch (campo) {
      case 'name':
        return this.name().trim()
          ? null
          : this.transloco.translate('admin.organizacion.nombreRequerido');
      case 'website': {
        const valor = this.website().trim();
        if (!valor) return null;
        return WEB_RE.test(valor)
          ? null
          : this.transloco.translate('admin.organizacion.webInvalida');
      }
      case 'contactEmail': {
        const valor = this.contactEmail().trim();
        if (!valor) return null;
        return EMAIL_RE.test(valor)
          ? null
          : this.transloco.translate('admin.organizacion.correoInvalido');
      }
    }
  }

  protected validar(campo: Campo): void {
    this.errores.update((actuales) => ({ ...actuales, [campo]: this.errorDe(campo) }));
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.guardado.set(false);
    this.error.set(null);

    const nuevosErrores: Record<Campo, string | null> = {
      name: this.errorDe('name'),
      contactEmail: this.errorDe('contactEmail'),
      website: this.errorDe('website'),
    };
    this.errores.set(nuevosErrores);
    if (Object.values(nuevosErrores).some((mensaje) => mensaje)) {
      return;
    }

    this.guardando.set(true);
    try {
      await firstValueFrom(
        this.http.patch<Organizacion>(this.api.url('/organizations/me'), {
          name: this.name().trim(),
          legal_name: this.legalName().trim() || null,
          description: this.description().trim() || null,
          website: this.website().trim() || null,
          contact_email: this.contactEmail().trim() || null,
          address: this.address().trim() || null,
          public_page_enabled: this.publicPageEnabled(),
        }),
      );
      this.paginaActiva.set(this.publicPageEnabled());
      // Refresca el branding público: el nombre mostrado en la cabecera del panel y
      // en la portada viene de `ThemingService`, resuelto por host, no de este PATCH.
      await this.theming.load();
      this.guardado.set(true);
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.organizacion.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
