import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { ThemingService } from '../../../core/theming/theming.service';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { Textarea } from '../../../shared/ui/textarea';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface Organizacion {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly legal_name: string | null;
  readonly description: string | null;
  readonly website: string | null;
  readonly contact_email: string | null;
  readonly is_active: boolean;
}

type Campo = 'name' | 'contactEmail';

/**
 * Datos generales de la organización: nombre, razón social, descripción, web y correo
 * de contacto. El branding (colores, tipografía, logo) vive en su propia pantalla.
 */
@Component({
  selector: 'app-organization-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, Textarea],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.organizacion.titulo') }}</h1>
      <p>{{ t('admin.organizacion.descripcion') }}</p>

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
              [(value)]="website"
            />
            <app-input
              [label]="t('admin.organizacion.correoContacto')"
              type="email"
              autocomplete="email"
              [error]="errores().contactEmail"
              [(value)]="contactEmail"
              (blurred)="validar('contactEmail')"
            />

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
    h1 {
      margin-top: 0;
    }
    form {
      display: grid;
      gap: var(--space-md);
      max-width: 32rem;
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
  protected readonly errores = signal<Record<Campo, string | null>>({
    name: null,
    contactEmail: null,
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
        }),
      );
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
