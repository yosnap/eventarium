import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { DynamicField } from '../../../shared/ui/dynamic-field';
import { ProfileField, validateDynamicFieldValue } from '../../../shared/ui/dynamic-field.model';
import { ErrorSummary, ResumenDeError } from '../../../shared/ui/error-summary';
import { Input } from '../../../shared/ui/input';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface RoleOption {
  readonly id: string;
  readonly key: string;
  readonly name: string;
  readonly profile_fields: readonly ProfileField[];
}

type CampoBase = 'email' | 'firstName' | 'lastName' | 'roleId';

/**
 * Alta de un miembro. Los campos de perfil que pide dependen del rol elegido: se
 * recargan al cambiar la selección, con la definición que ya trae `GET /roles` (sin
 * pedirla de nuevo por rol).
 */
@Component({
  selector: 'app-member-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card, DynamicField, ErrorSummary, Input],
  template: `
    <ng-container *transloco="let t">
      <h1>{{ t('admin.members.formulario.titulo') }}</h1>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <form (submit)="guardar($event)" novalidate>
          <app-error-summary [errores]="resumenDeErrores()" [titulo]="t('comun.corrigeErrores')" />

          <app-card>
            <app-input
              fieldId="miembro-correo"
              [label]="t('admin.members.formulario.correo')"
              type="email"
              autocomplete="email"
              [required]="true"
              [error]="erroresBase().email"
              [(value)]="email"
              (blurred)="validarBase('email')"
            />
            <app-input
              fieldId="miembro-nombre"
              [label]="t('admin.members.formulario.nombre')"
              autocomplete="given-name"
              [required]="true"
              [error]="erroresBase().firstName"
              [(value)]="firstName"
              (blurred)="validarBase('firstName')"
            />
            <app-input
              fieldId="miembro-apellidos"
              [label]="t('admin.members.formulario.apellidos')"
              autocomplete="family-name"
              [required]="true"
              [error]="erroresBase().lastName"
              [(value)]="lastName"
              (blurred)="validarBase('lastName')"
            />

            <div class="campo-select">
              <label for="miembro-rol">{{ t('admin.members.formulario.rol') }}</label>
              <select id="miembro-rol" [value]="roleId()" (change)="alElegirRol($event)">
                <option value="" disabled>{{ t('admin.members.formulario.rolRequerido') }}</option>
                @for (rol of roles(); track rol.id) {
                  <option [value]="rol.id">{{ rol.name }}</option>
                }
              </select>
              @if (erroresBase().roleId) {
                <p class="error">{{ erroresBase().roleId }}</p>
              }
            </div>
          </app-card>

          @if (rolElegido(); as rol) {
            @if (rol.profile_fields.length > 0) {
              <app-card [heading]="rol.name">
                @for (campo of rol.profile_fields; track campo.key) {
                  <app-dynamic-field
                    [fieldId]="'perfil-' + campo.key"
                    [field]="campo"
                    [error]="erroresDePerfil()[campo.key] ?? null"
                    [value]="valoresDePerfil()[campo.key] ?? ''"
                    (valueChange)="actualizarValorDePerfil(campo.key, $event)"
                    (blurred)="validarCampoDePerfil(campo)"
                  />
                }
              </app-card>
            }
          }

          @if (exito()) {
            <app-alert tone="exito">{{ t('admin.members.formulario.exito') }}</app-alert>
          }
          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <div class="acciones-finales">
            <a routerLink="/admin/members">
              <app-button variant="secundario" type="button">{{
                t('admin.roles.cancelar')
              }}</app-button>
            </a>
            <app-button type="submit" [loading]="guardando()">
              {{
                guardando()
                  ? t('admin.members.formulario.anadiendo')
                  : t('admin.members.formulario.anadir')
              }}
            </app-button>
          </div>
        </form>
      }
    </ng-container>
  `,
  styles: `
    h1 {
      margin-top: 0;
    }
    form {
      display: grid;
      gap: var(--space-lg);
      margin-top: var(--space-md);
      max-width: 34rem;
    }
    .campo-select {
      display: grid;
      gap: var(--space-xs);
    }
    .campo-select select {
      width: 100%;
      box-sizing: border-box;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: var(--radius-md);
      background-color: var(--color-surface);
      color: var(--color-text);
      font: inherit;
      min-height: 2.75rem;
    }
    .error {
      margin: 0;
      color: var(--color-danger);
      font-size: 0.875rem;
    }
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class MemberForm {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly router = inject(Router);

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly exito = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly email = signal('');
  protected readonly firstName = signal('');
  protected readonly lastName = signal('');
  protected readonly roleId = signal('');
  protected readonly roles = signal<RoleOption[]>([]);
  protected readonly valoresDePerfil = signal<Record<string, string | boolean>>({});

  protected readonly rolElegido = computed(() =>
    this.roles().find((rol) => rol.id === this.roleId()),
  );

  protected readonly erroresBase = signal<Record<CampoBase, string | null>>({
    email: null,
    firstName: null,
    lastName: null,
    roleId: null,
  });
  protected readonly erroresDePerfil = signal<Record<string, string | null>>({});

  protected readonly resumenDeErrores = computed<ResumenDeError[]>(() => {
    const base = this.erroresBase();
    const perfil = this.erroresDePerfil();
    const resumen: ResumenDeError[] = [];
    if (base.email) resumen.push({ campoId: 'miembro-correo', mensaje: base.email });
    if (base.firstName) resumen.push({ campoId: 'miembro-nombre', mensaje: base.firstName });
    if (base.lastName) resumen.push({ campoId: 'miembro-apellidos', mensaje: base.lastName });
    if (base.roleId) resumen.push({ campoId: 'miembro-rol', mensaje: base.roleId });
    for (const [clave, mensaje] of Object.entries(perfil)) {
      if (mensaje) resumen.push({ campoId: `perfil-${clave}`, mensaje });
    }
    return resumen;
  });

  constructor() {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    try {
      this.roles.set(await firstValueFrom(this.http.get<RoleOption[]>(this.api.url('/roles'))));
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.members.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  protected alElegirRol(evento: Event): void {
    this.roleId.set((evento.target as HTMLSelectElement).value);
    this.valoresDePerfil.set({});
    this.erroresDePerfil.set({});
  }

  protected actualizarValorDePerfil(clave: string, valor: string | boolean): void {
    this.valoresDePerfil.update((actuales) => ({ ...actuales, [clave]: valor }));
  }

  private errorDeBase(campo: CampoBase): string | null {
    switch (campo) {
      case 'email': {
        const valor = this.email().trim();
        if (!valor) return this.transloco.translate('admin.members.formulario.correoRequerido');
        return EMAIL_RE.test(valor)
          ? null
          : this.transloco.translate('admin.members.formulario.correoInvalido');
      }
      case 'firstName':
        return this.firstName().trim()
          ? null
          : this.transloco.translate('admin.members.formulario.nombreRequerido');
      case 'lastName':
        return this.lastName().trim()
          ? null
          : this.transloco.translate('admin.members.formulario.apellidosRequeridos');
      case 'roleId':
        return this.roleId()
          ? null
          : this.transloco.translate('admin.members.formulario.rolRequerido');
    }
  }

  protected validarBase(campo: CampoBase): void {
    this.erroresBase.update((actuales) => ({ ...actuales, [campo]: this.errorDeBase(campo) }));
  }

  protected validarCampoDePerfil(campo: ProfileField): void {
    const valor = this.valoresDePerfil()[campo.key] ?? '';
    this.erroresDePerfil.update((actuales) => ({
      ...actuales,
      [campo.key]: validateDynamicFieldValue(campo, valor),
    }));
  }

  private validarTodo(): boolean {
    const base: Record<CampoBase, string | null> = {
      email: this.errorDeBase('email'),
      firstName: this.errorDeBase('firstName'),
      lastName: this.errorDeBase('lastName'),
      roleId: this.errorDeBase('roleId'),
    };
    this.erroresBase.set(base);

    const campos = this.rolElegido()?.profile_fields ?? [];
    const perfil: Record<string, string | null> = {};
    for (const campo of campos) {
      perfil[campo.key] = validateDynamicFieldValue(campo, this.valoresDePerfil()[campo.key] ?? '');
    }
    this.erroresDePerfil.set(perfil);

    return (
      Object.values(base).every((mensaje) => !mensaje) &&
      Object.values(perfil).every((mensaje) => !mensaje)
    );
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    this.exito.set(false);
    if (!this.validarTodo()) {
      return;
    }

    this.guardando.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url('/organizations/me/members'), {
          email: this.email().trim(),
          first_name: this.firstName().trim(),
          last_name: this.lastName().trim(),
          role_id: this.roleId(),
          profile_data: this.valoresDePerfil(),
        }),
      );
      await this.router.navigateByUrl('/admin/members');
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.members.formulario.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
