import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { ErrorSummary, ResumenDeError } from '../../../shared/ui/error-summary';
import { FIELD_TYPES, FieldType } from '../../../shared/ui/dynamic-field.model';
import { Input } from '../../../shared/ui/input';
import { Textarea } from '../../../shared/ui/textarea';

const KEY_RE = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;

const PERMISOS = [
  'organizations:read',
  'organizations:write',
  'branding:write',
  'roles:read',
  'roles:write',
  'members:read',
  'members:write',
  'users:read',
] as const;

interface CampoDeFormulario {
  clave: string;
  etiqueta: string;
  tipo: FieldType;
  requerido: boolean;
  opciones: string;
  bloqueado: boolean;
}

interface RoleField {
  readonly key: string;
  readonly label: string;
  readonly field_type: string;
  readonly options: { readonly choices?: readonly string[] } | null;
  readonly is_required: boolean;
  readonly is_locked: boolean;
}

interface RoleDetail {
  readonly id: string;
  readonly key: string;
  readonly name: string;
  readonly description: string | null;
  readonly is_system: boolean;
  readonly system_template_key: string | null;
  readonly permissions: readonly string[];
  readonly profile_fields: readonly RoleField[];
}

function campoDesdeApi(campo: RoleField): CampoDeFormulario {
  return {
    clave: campo.key,
    etiqueta: campo.label,
    tipo: (campo.field_type as FieldType) || 'text',
    requerido: campo.is_required,
    opciones: (campo.options?.choices ?? []).join('\n'),
    bloqueado: campo.is_locked,
  };
}

/**
 * Crear o editar un rol. La misma pantalla sirve para los dos modos: si la ruta trae
 * un id existente se carga ese rol, si no se empieza en blanco.
 *
 * Los permisos que el actor no tiene se muestran deshabilitados con el motivo en
 * `title`, en vez de ocultarse: ocultar una opción sin explicar por qué es más
 * confuso que mostrarla deshabilitada (la API los rechazaría igual si se forzaran).
 */
@Component({
  selector: 'app-role-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert, Button, Card, ErrorSummary, Input, Textarea],
  template: `
    <ng-container *transloco="let t">
      <h1>
        {{
          esEdicion()
            ? t('admin.roles.formulario.tituloEditar', { nombre: name() })
            : t('admin.roles.formulario.tituloCrear')
        }}
      </h1>

      @if (cargando()) {
        <p>{{ t('comun.cargando') }}</p>
      } @else {
        <form (submit)="guardar($event)" novalidate>
          <app-error-summary [errores]="resumenDeErrores()" [titulo]="t('comun.corrigeErrores')" />

          <app-card>
            @if (!esEdicion()) {
              <app-input
                fieldId="rol-clave"
                [label]="t('admin.roles.formulario.clave')"
                [hint]="t('admin.roles.formulario.claveAyuda')"
                [required]="true"
                [error]="errores().clave"
                [(value)]="key"
                (blurred)="validar('clave')"
              />
            }
            <app-input
              fieldId="rol-nombre"
              [label]="t('admin.roles.formulario.nombre')"
              [required]="true"
              [error]="errores().nombre"
              [(value)]="name"
              (blurred)="validar('nombre')"
            />
            <app-textarea
              [label]="t('admin.roles.formulario.descripcion')"
              [(value)]="description"
            />

            @if (!esEdicion() && plantillas().length > 0) {
              <div class="campo-select">
                <label for="rol-plantilla">{{ t('admin.roles.formulario.plantilla') }}</label>
                <select
                  id="rol-plantilla"
                  [value]="fromTemplate()"
                  (change)="alElegirPlantilla($event)"
                >
                  <option value="">{{ t('admin.roles.formulario.plantillaNinguna') }}</option>
                  @for (plantilla of plantillas(); track plantilla.key) {
                    <option [value]="plantilla.key">{{ plantilla.name }}</option>
                  }
                </select>
              </div>
            }
          </app-card>

          <app-card [heading]="t('admin.roles.formulario.permisos')">
            <div class="permisos">
              @for (permiso of permisosDisponibles; track permiso) {
                <label
                  class="permiso"
                  [title]="
                    actorTienePermiso(permiso)
                      ? ''
                      : t('admin.roles.formulario.permisoNoDisponible')
                  "
                >
                  <input
                    type="checkbox"
                    [checked]="permissions().has(permiso)"
                    [disabled]="!actorTienePermiso(permiso)"
                    (change)="alCambiarPermiso(permiso, $event)"
                  />
                  {{ t('admin.roles.permisosClaves.' + permiso) }}
                </label>
              }
            </div>
          </app-card>

          <app-card [heading]="t('admin.roles.formulario.campos')">
            <div class="campos">
              @for (campo of profileFields(); track $index) {
                <div class="campo-fila">
                  @if (campo.bloqueado) {
                    <p class="bloqueado">
                      <strong>{{ campo.etiqueta }}</strong>
                      <code>{{ campo.clave }}</code>
                      · {{ t('admin.roles.formulario.tipos.' + campo.tipo) }}
                      @if (campo.requerido) {
                        · {{ t('admin.roles.formulario.campoObligatorio') }}
                      }
                    </p>
                    <p class="ayuda">{{ t('admin.roles.formulario.campoBloqueado') }}</p>
                  } @else {
                    <app-input
                      [fieldId]="'campo-clave-' + $index"
                      [label]="t('admin.roles.formulario.campoClave')"
                      [hint]="t('admin.roles.formulario.campoClaveAyuda')"
                      [error]="errores().campos[$index] ?? null"
                      [value]="campo.clave"
                      (valueChange)="actualizarCampo($index, 'clave', $event)"
                      (blurred)="validarCampo($index)"
                    />
                    <app-input
                      [fieldId]="'campo-etiqueta-' + $index"
                      [label]="t('admin.roles.formulario.campoEtiqueta')"
                      [value]="campo.etiqueta"
                      (valueChange)="actualizarCampo($index, 'etiqueta', $event)"
                      (blurred)="validarCampo($index)"
                    />
                    <div class="campo-select">
                      <label [for]="'campo-tipo-' + $index">{{
                        t('admin.roles.formulario.campoTipo')
                      }}</label>
                      <select
                        [id]="'campo-tipo-' + $index"
                        (change)="alCambiarTipoDeCampo($index, $event)"
                      >
                        @for (tipo of tiposDeCampos; track tipo) {
                          <option [value]="tipo" [selected]="tipo === campo.tipo">
                            {{ t('admin.roles.formulario.tipos.' + tipo) }}
                          </option>
                        }
                      </select>
                    </div>
                    @if (campo.tipo === 'select') {
                      <app-textarea
                        [label]="t('admin.roles.formulario.campoOpciones')"
                        [value]="campo.opciones"
                        (valueChange)="actualizarCampo($index, 'opciones', $event)"
                        (blurred)="validarCampo($index)"
                      />
                    }
                    <label class="requerido">
                      <input
                        type="checkbox"
                        [checked]="campo.requerido"
                        (change)="alCambiarRequerido($index, $event)"
                      />
                      {{ t('admin.roles.formulario.campoObligatorio') }}
                    </label>
                    <app-button variant="secundario" type="button" (pulsado)="quitarCampo($index)">
                      {{ t('admin.roles.formulario.quitarCampo') }}
                    </app-button>
                  }
                </div>
              }
            </div>
            <app-button variant="secundario" type="button" (pulsado)="anadirCampo()">
              {{ t('admin.roles.formulario.anadirCampo') }}
            </app-button>
          </app-card>

          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <div class="acciones-finales">
            <a routerLink="/admin/roles">
              <app-button variant="secundario" type="button">{{
                t('admin.roles.cancelar')
              }}</app-button>
            </a>
            <app-button type="submit" [loading]="guardando()">
              {{
                guardando()
                  ? t('admin.roles.formulario.guardando')
                  : t('admin.roles.formulario.guardar')
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
      max-width: 40rem;
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
    .permisos {
      display: grid;
      gap: var(--space-sm);
    }
    .permiso {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      min-height: 2.75rem;
    }
    .campos {
      display: grid;
      gap: var(--space-lg);
    }
    .campo-fila {
      display: grid;
      gap: var(--space-sm);
      padding-bottom: var(--space-md);
      border-bottom: 1px solid var(--color-border);
    }
    .campo-fila:last-child {
      border-bottom: none;
    }
    .bloqueado {
      margin: 0;
    }
    .ayuda {
      margin: 0;
      color: var(--color-text-muted, #6b7280);
      font-size: 0.8125rem;
    }
    .requerido {
      display: flex;
      align-items: center;
      gap: var(--space-sm);
      min-height: 2.75rem;
    }
    .acciones-finales {
      display: flex;
      gap: var(--space-md);
    }
  `,
})
export class RoleForm {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);
  private readonly ruta = inject(ActivatedRoute);
  private readonly router = inject(Router);

  protected readonly permisosDisponibles = PERMISOS;
  protected readonly tiposDeCampos = FIELD_TYPES;

  protected readonly cargando = signal(true);
  protected readonly guardando = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly roleId = signal<string | null>(null);
  protected readonly esEdicion = computed(() => this.roleId() !== null);

  protected readonly key = signal('');
  protected readonly name = signal('');
  protected readonly description = signal('');
  protected readonly fromTemplate = signal('');
  protected readonly permissions = signal<Set<string>>(new Set());
  protected readonly profileFields = signal<CampoDeFormulario[]>([]);
  protected readonly plantillas = signal<{ key: string; name: string }[]>([]);
  private plantillasCompletas: RoleDetail[] = [];

  private readonly actorPermissions = signal<Set<string>>(new Set());

  protected readonly errores = signal<{
    clave: string | null;
    nombre: string | null;
    campos: (string | null)[];
  }>({ clave: null, nombre: null, campos: [] });

  protected readonly resumenDeErrores = computed<ResumenDeError[]>(() => {
    const actuales = this.errores();
    const resumen: ResumenDeError[] = [];
    if (actuales.clave) resumen.push({ campoId: 'rol-clave', mensaje: actuales.clave });
    if (actuales.nombre) resumen.push({ campoId: 'rol-nombre', mensaje: actuales.nombre });
    actuales.campos.forEach((mensaje, indice) => {
      if (mensaje) resumen.push({ campoId: `campo-clave-${indice}`, mensaje });
    });
    return resumen;
  });

  constructor() {
    const id = this.ruta.snapshot.paramMap.get('id');
    this.roleId.set(id && id !== 'nuevo' ? id : null);
    void this.cargar();
  }

  protected actorTienePermiso(permiso: string): boolean {
    return this.actorPermissions().has(permiso);
  }

  private async cargar(): Promise<void> {
    try {
      const [persona, roles] = await Promise.all([
        firstValueFrom(
          this.http.get<{ permissions: readonly string[] }>(this.api.url('/users/me')),
        ),
        firstValueFrom(this.http.get<RoleDetail[]>(this.api.url('/roles'))),
      ]);
      this.actorPermissions.set(new Set(persona.permissions));
      this.plantillasCompletas = roles.filter((rol) => rol.is_system);
      this.plantillas.set(
        this.plantillasCompletas.map((rol) => ({ key: rol.key, name: rol.name })),
      );

      const id = this.roleId();
      if (id) {
        const rol = roles.find((r) => r.id === id) ?? (await this.obtenerRol(id));
        this.name.set(rol.name);
        this.key.set(rol.key);
        this.description.set(rol.description ?? '');
        this.permissions.set(new Set(rol.permissions));
        this.profileFields.set(rol.profile_fields.map(campoDesdeApi));
      }
    } catch (error) {
      this.error.set(
        error instanceof ApiError ? error.message : this.transloco.translate('admin.roles.error'),
      );
    } finally {
      this.cargando.set(false);
    }
  }

  private async obtenerRol(id: string): Promise<RoleDetail> {
    return firstValueFrom(this.http.get<RoleDetail>(this.api.url(`/roles/${id}`)));
  }

  protected alElegirPlantilla(evento: Event): void {
    const clave = (evento.target as HTMLSelectElement).value;
    this.fromTemplate.set(clave);
    const plantilla = this.plantillasCompletas.find((rol) => rol.key === clave);
    if (!plantilla) {
      return;
    }
    // Vista previa de lo que se recibiría: la fusión real la hace la API con
    // `from_template`, esto solo evita que la persona firme a ciegas. Los campos
    // llegan editables aunque en el rol del sistema del que se copian estén
    // bloqueados: `create_role` nunca bloquea campos en un rol nuevo, el bloqueo
    // solo protege los campos que ya trae un rol del sistema existente.
    this.permissions.set(
      new Set(plantilla.permissions.filter((permiso) => this.actorTienePermiso(permiso))),
    );
    this.profileFields.set(
      plantilla.profile_fields.map((campo) => ({ ...campoDesdeApi(campo), bloqueado: false })),
    );
  }

  protected alCambiarPermiso(permiso: string, evento: Event): void {
    const marcado = (evento.target as HTMLInputElement).checked;
    this.permissions.update((actuales) => {
      const nuevo = new Set(actuales);
      if (marcado) nuevo.add(permiso);
      else nuevo.delete(permiso);
      return nuevo;
    });
  }

  protected anadirCampo(): void {
    this.profileFields.update((actuales) => [
      ...actuales,
      { clave: '', etiqueta: '', tipo: 'text', requerido: false, opciones: '', bloqueado: false },
    ]);
    this.errores.update((actuales) => ({ ...actuales, campos: [...actuales.campos, null] }));
  }

  protected quitarCampo(indice: number): void {
    this.profileFields.update((actuales) => actuales.filter((_, i) => i !== indice));
    this.errores.update((actuales) => ({
      ...actuales,
      campos: actuales.campos.filter((_, i) => i !== indice),
    }));
  }

  protected actualizarCampo(
    indice: number,
    propiedad: 'clave' | 'etiqueta' | 'opciones',
    valor: string,
  ): void {
    this.profileFields.update((actuales) =>
      actuales.map((campo, i) => (i === indice ? { ...campo, [propiedad]: valor } : campo)),
    );
  }

  protected alCambiarTipoDeCampo(indice: number, evento: Event): void {
    const tipo = (evento.target as HTMLSelectElement).value as FieldType;
    this.profileFields.update((actuales) =>
      actuales.map((campo, i) => (i === indice ? { ...campo, tipo } : campo)),
    );
  }

  protected alCambiarRequerido(indice: number, evento: Event): void {
    const requerido = (evento.target as HTMLInputElement).checked;
    this.profileFields.update((actuales) =>
      actuales.map((campo, i) => (i === indice ? { ...campo, requerido } : campo)),
    );
  }

  private errorDeClave(): string | null {
    if (this.esEdicion()) return null;
    const valor = this.key().trim();
    if (!valor) return this.transloco.translate('admin.roles.formulario.claveRequerida');
    return KEY_RE.test(valor)
      ? null
      : this.transloco.translate('admin.roles.formulario.claveInvalida');
  }

  private errorDeNombre(): string | null {
    return this.name().trim()
      ? null
      : this.transloco.translate('admin.roles.formulario.nombreRequerido');
  }

  private errorDeCampo(indice: number): string | null {
    const campo = this.profileFields()[indice];
    if (!campo || campo.bloqueado) return null;
    const clave = campo.clave.trim();
    if (!clave) return this.transloco.translate('admin.roles.formulario.campoClaveRequerida');
    if (!KEY_RE.test(clave)) {
      return this.transloco.translate('admin.roles.formulario.campoClaveInvalida');
    }
    const repetida = this.profileFields().some(
      (otro, i) => i !== indice && otro.clave.trim() === clave,
    );
    if (repetida) return this.transloco.translate('admin.roles.formulario.campoClaveRepetida');
    if (!campo.etiqueta.trim()) {
      return this.transloco.translate('admin.roles.formulario.campoEtiquetaRequerida');
    }
    if (campo.tipo === 'select' && !campo.opciones.trim()) {
      return this.transloco.translate('admin.roles.formulario.campoOpcionesRequeridas');
    }
    return null;
  }

  protected validar(campo: 'clave' | 'nombre'): void {
    this.errores.update((actuales) => ({
      ...actuales,
      [campo]: campo === 'clave' ? this.errorDeClave() : this.errorDeNombre(),
    }));
  }

  protected validarCampo(indice: number): void {
    this.errores.update((actuales) => {
      const campos = [...actuales.campos];
      campos[indice] = this.errorDeCampo(indice);
      return { ...actuales, campos };
    });
  }

  private validarTodo(): boolean {
    const campos = this.profileFields().map((_, indice) => this.errorDeCampo(indice));
    this.errores.set({ clave: this.errorDeClave(), nombre: this.errorDeNombre(), campos });
    return !this.errorDeClave() && !this.errorDeNombre() && campos.every((mensaje) => !mensaje);
  }

  protected async guardar(evento: Event): Promise<void> {
    evento.preventDefault();
    this.error.set(null);
    if (!this.validarTodo()) {
      return;
    }

    const camposParaEnviar = this.profileFields().map((campo, indice) => ({
      key: campo.clave.trim(),
      label: campo.etiqueta.trim(),
      field_type: campo.tipo,
      is_required: campo.requerido,
      sort_order: indice * 10,
      options:
        campo.tipo === 'select'
          ? {
              choices: campo.opciones
                .split('\n')
                .map((linea) => linea.trim())
                .filter(Boolean),
            }
          : null,
    }));

    this.guardando.set(true);
    try {
      if (this.esEdicion()) {
        await firstValueFrom(
          this.http.patch(this.api.url(`/roles/${this.roleId()}`), {
            name: this.name().trim(),
            description: this.description().trim() || null,
            permissions: [...this.permissions()],
            profile_fields: camposParaEnviar,
          }),
        );
      } else {
        await firstValueFrom(
          this.http.post(this.api.url('/roles'), {
            key: this.key().trim(),
            name: this.name().trim(),
            description: this.description().trim() || null,
            from_template: this.fromTemplate() || null,
            permissions: [...this.permissions()],
            profile_fields: camposParaEnviar,
          }),
        );
      }
      await this.router.navigateByUrl('/admin/roles');
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.roles.formulario.error'),
      );
    } finally {
      this.guardando.set(false);
    }
  }
}
