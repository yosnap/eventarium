import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Chip } from '../../../shared/ui/chip';
import { DataTable, type DataTableColumn } from '../../../shared/ui/data-table';
import { ErrorSummary, type ResumenDeError } from '../../../shared/ui/error-summary';
import { Input } from '../../../shared/ui/input';
import { PasswordStrength } from '../../../shared/ui/password-strength';
import { Textarea } from '../../../shared/ui/textarea';

/**
 * Catálogo interno de `shared/ui`, organizado por categorías (acciones, estado,
 * formularios, superficies, datos, retroalimentación), para ver y probar cada
 * componente junto a sus variantes y estados mientras se diseña.
 *
 * No es una pantalla de producto: vive dentro de `admin/estilo` (autenticado). A
 * diferencia de la versión anterior, esta pantalla sí entra en la suite de axe
 * (`style-guide-page.spec.ts`): es la única que reúne todos los componentes a la vez,
 * así que es donde antes se detecta una regresión de contraste.
 *
 * Sin conmutador de tema propio: reutiliza el de la fase 1, ya presente en el chrome
 * de `AdminShell`.
 *
 * Sin `<main>` propio a propósito: `AdminShell` ya pone el suyo alrededor de
 * `<router-outlet>`, y dos landmarks `main` en la misma página confundirían a un
 * lector de pantalla.
 */
@Component({
  selector: 'app-style-guide-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    Alert,
    Button,
    Card,
    Chip,
    DataTable,
    ErrorSummary,
    Input,
    PasswordStrength,
    Textarea,
  ],
  template: `
    <ng-container *transloco="let t">
      <div class="pagina">
        <h1>Catálogo de componentes</h1>
        <p>Uso interno: no forma parte del producto.</p>

        <section aria-labelledby="cat-acciones">
          <h2 id="cat-acciones" class="rotulo-seccion">Acciones</h2>
          <div class="fila">
            <app-button variant="primario">Primario</app-button>
            <app-button variant="secundario">Secundario</app-button>
            <app-button variant="terciario">Terciario</app-button>
            <app-button variant="peligro">Peligro</app-button>
          </div>
          <div class="fila">
            <app-button [loading]="true">Cargando</app-button>
            <app-button [disabled]="true">Desactivado</app-button>
            <app-button [compacto]="true">Compacto</app-button>
          </div>
          <div class="fila bloque">
            <app-button [bloque]="true">Botón a bloque</app-button>
          </div>
        </section>

        <section aria-labelledby="cat-estado">
          <h2 id="cat-estado" class="rotulo-seccion">Estado</h2>
          <div class="fila">
            <app-chip tone="neutro">Borrador</app-chip>
            <app-chip tone="ok">Confirmado</app-chip>
            <app-chip tone="espera">Pendiente</app-chip>
            <app-chip tone="apagado">Cancelado</app-chip>
          </div>
        </section>

        <section aria-labelledby="cat-formularios">
          <h2 id="cat-formularios" class="rotulo-seccion">Formularios</h2>
          <div class="columna campos">
            <app-input label="Nombre" [(value)]="texto" hint="Texto de ayuda de ejemplo." />
            <app-input label="Correo electrónico" type="email" [(value)]="correo" />
            <app-input
              label="Con error"
              [(value)]="conError"
              error="Este campo tiene un error de ejemplo."
            />
            <app-input
              label="Contraseña"
              type="password"
              autocomplete="new-password"
              [(value)]="password"
              hint="Mínimo 8 caracteres, con mayúscula, minúscula, número y carácter especial."
            />
            <app-password-strength [password]="password()" />
            <app-textarea
              label="Descripción"
              [(value)]="descripcion"
              hint="Campo de varias líneas."
            />
            <div class="campo-select-demo">
              <label for="select-demo">Categoría</label>
              <select id="select-demo">
                <option value="publico">Público</option>
                <option value="privado">Privado</option>
              </select>
            </div>
          </div>
        </section>

        <section aria-labelledby="cat-superficies">
          <h2 id="cat-superficies" class="rotulo-seccion">Superficies</h2>
          <div class="columna">
            <app-card heading="Sin acciones">
              <p>Contenido de ejemplo dentro de la tarjeta.</p>
            </app-card>
            <app-card heading="Con acciones en la cabecera">
              <p>La ranura de acciones no rompe el modo sin ella.</p>
              <div acciones>
                <app-button variant="secundario" [compacto]="true">Editar</app-button>
                <app-button variant="peligro" [compacto]="true">Borrar</app-button>
              </div>
            </app-card>
          </div>
        </section>

        <section aria-labelledby="cat-datos">
          <h2 id="cat-datos" class="rotulo-seccion">Datos</h2>
          <app-data-table caption="Ejemplo de inscripciones" [columnas]="columnasTabla">
            <tr>
              <td>Ana García</td>
              <td>ana@example.com</td>
              <td class="numerica">2</td>
            </tr>
            <tr>
              <td>Luis Pérez</td>
              <td>luis@example.com</td>
              <td class="numerica">1</td>
            </tr>
          </app-data-table>
        </section>

        <section aria-labelledby="cat-retroalimentacion">
          <h2 id="cat-retroalimentacion" class="rotulo-seccion">Retroalimentación</h2>
          <div class="columna">
            <app-alert tone="info" title="Información">Mensaje informativo.</app-alert>
            <app-alert tone="exito" title="Éxito">La operación se completó.</app-alert>
            <app-alert tone="error" title="Error">Algo ha ido mal.</app-alert>
            <app-error-summary [errores]="erroresDeEjemplo" titulo="Corrige lo siguiente:" />
          </div>
        </section>
      </div>
    </ng-container>
  `,
  styles: `
    .pagina {
      max-width: 40rem;
      margin: 0 auto;
      padding: var(--space-xl) var(--space-lg);
      display: grid;
      gap: var(--space-xl);
    }
    h1 {
      margin: 0;
    }
    section {
      display: grid;
      gap: var(--space-md);
    }
    h2 {
      margin: 0;
      padding-bottom: var(--space-xs);
      border-bottom: 1px solid var(--border);
    }
    .fila {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      align-items: center;
    }
    .fila.bloque {
      display: block;
    }
    .columna {
      display: grid;
      gap: var(--space-md);
    }
    .campos {
      max-width: 24rem;
    }
    .campo-select-demo {
      display: grid;
      gap: var(--space-xs);
    }
  `,
})
export class StyleGuidePage {
  protected readonly texto = signal('');
  protected readonly correo = signal('');
  protected readonly conError = signal('valor con error');
  protected readonly password = signal('');
  protected readonly descripcion = signal('');

  protected readonly columnasTabla: readonly DataTableColumn[] = [
    { key: 'nombre', label: 'Nombre' },
    { key: 'correo', label: 'Correo' },
    { key: 'entradas', label: 'Entradas', numerica: true },
  ];

  protected readonly erroresDeEjemplo: readonly ResumenDeError[] = [
    { campoId: 'select-demo', mensaje: 'Elige una categoría.' },
    { campoId: 'campo-1', mensaje: 'Falta el nombre.' },
  ];
}
