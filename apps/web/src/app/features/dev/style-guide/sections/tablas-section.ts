import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Button } from '../../../../shared/ui/button';
import { Chip } from '../../../../shared/ui/chip';
import { DataTable, type DataTableColumn } from '../../../../shared/ui/data-table';

/**
 * Sección «Tablas»: `app-data-table` (ya envuelto en `app-panel`) con dos filas de
 * ejemplo (persona/solicitada/estado/acción), usando `app-chip` para el estado.
 */
@Component({
  selector: 'app-style-guide-tablas-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button, Chip, DataTable],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="tablas" aria-labelledby="tablas-h2">
        <div class="sec__cabecera">
          <h2 id="tablas-h2">{{ t('admin.catalogoEstilo.tablas.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.tablas.uso') }}</span>
        </div>
        <app-data-table [caption]="t('admin.catalogoEstilo.tablas.caption')" [columnas]="columnas(t)">
          <tr>
            <td>{{ t('admin.catalogoEstilo.tablas.persona1') }}</td>
            <td class="numerica muted">{{ t('admin.catalogoEstilo.tablas.solicitada1') }}</td>
            <td><app-chip tone="espera">{{ t('admin.catalogoEstilo.tablas.pendiente') }}</app-chip></td>
            <td class="acciones">
              <app-button variant="secundario" [compacto]="true">{{
                t('admin.catalogoEstilo.tablas.aprobar')
              }}</app-button>
            </td>
          </tr>
          <tr>
            <td>{{ t('admin.catalogoEstilo.tablas.persona2') }}</td>
            <td class="numerica muted">{{ t('admin.catalogoEstilo.tablas.solicitada2') }}</td>
            <td><app-chip tone="ok">{{ t('admin.catalogoEstilo.tablas.confirmada') }}</app-chip></td>
            <td class="acciones">
              <app-button variant="terciario" [compacto]="true">{{
                t('admin.catalogoEstilo.tablas.verFicha')
              }}</app-button>
            </td>
          </tr>
        </app-data-table>
        <p class="nota">{{ t('admin.catalogoEstilo.tablas.nota') }}</p>
      </section>
    </ng-container>
  `,
  styles: `
    .sec__cabecera {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-md);
      align-items: baseline;
      justify-content: space-between;
      margin-bottom: var(--space-md);
    }
    h2 {
      margin: 0;
      font-family: var(--font-body);
      font-size: var(--fs-h3);
      font-weight: 500;
    }
    .nota {
      font-size: var(--fs-sm);
      color: var(--muted);
      max-width: 70ch;
      margin: var(--space-md) 0 0;
    }
    td.muted {
      color: var(--muted);
    }
    td.acciones {
      text-align: right;
    }
  `,
})
export class TablasSection {
  protected columnas(t: (clave: string) => string): readonly DataTableColumn[] {
    return [
      { key: 'persona', label: t('admin.catalogoEstilo.tablas.colPersona') },
      { key: 'solicitada', label: t('admin.catalogoEstilo.tablas.colSolicitada'), numerica: true },
      { key: 'estado', label: t('admin.catalogoEstilo.tablas.colEstado') },
      { key: 'acciones', label: t('admin.catalogoEstilo.tablas.colAcciones') },
    ];
  }
}
