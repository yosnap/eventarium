import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { Dialog } from '../../../../shared/ui/dialog';
import { KpiCard } from '../../../../shared/ui/kpi-card';
import { PageHeader } from '../../../../shared/ui/page-header';
import { Panel } from '../../../../shared/ui/panel';
import { SegmentedFilter } from '../../../../shared/ui/segmented-filter';
import { TableToolbar } from '../../../../shared/ui/table-toolbar';
import { Button } from '../../../../shared/ui/button';

/**
 * Sección «Patrones de panel»: las piezas de página que abren y estructuran las
 * pantallas de administración (fase 0 del plan 260915-0052).
 *
 * Cabecera de página, tarjetas KPI, panel con cabecera/pie, barra de
 * herramientas con filtro segmentado y diálogo. Cada muestra es el componente
 * real con datos de ejemplo, no una imitación.
 */
@Component({
  selector: 'app-style-guide-patrones-panel-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    TranslocoDirective,
    Button,
    Dialog,
    KpiCard,
    PageHeader,
    Panel,
    SegmentedFilter,
    TableToolbar,
  ],
  template: `
    <ng-container *transloco="let t">
      <section class="sec" id="patrones-panel" aria-labelledby="patrones-panel-h2">
        <div class="sec__cabecera">
          <h2 id="patrones-panel-h2">{{ t('admin.catalogoEstilo.patronesPanel.titulo') }}</h2>
          <span class="rotulo-seccion">{{ t('admin.catalogoEstilo.patronesPanel.uso') }}</span>
        </div>

        <app-page-header [rotulo]="t('admin.catalogoEstilo.patronesPanel.ejemploRotulo')">
          {{ t('admin.catalogoEstilo.patronesPanel.ejemploTitulo') }}
          <span class="mark">{{ t('admin.catalogoEstilo.patronesPanel.ejemploMarca') }}</span>
          {{ t('admin.catalogoEstilo.patronesPanel.ejemploTituloFin') }}
          <app-button acciones variant="secundario" type="button">
            {{ t('admin.catalogoEstilo.patronesPanel.ejemploAccion') }}
          </app-button>
        </app-page-header>

        <div class="kpis">
          <app-kpi-card
            [rotulo]="t('admin.catalogoEstilo.patronesPanel.kpiRotulo')"
            valor="382"
            [descriptor]="t('admin.catalogoEstilo.patronesPanel.kpiDescriptor')"
          />
          <app-kpi-card
            [rotulo]="t('admin.catalogoEstilo.patronesPanel.kpiWarnRotulo')"
            valor="14"
            tono="warn"
            [descriptor]="t('admin.catalogoEstilo.patronesPanel.kpiWarnDescriptor')"
          />
          <app-kpi-card
            [rotulo]="t('admin.catalogoEstilo.patronesPanel.kpiAcentoRotulo')"
            valor="4 215 €"
            tono="accent"
          />
        </div>

        <app-panel>
          <div cabecera>
            <span class="rotulo-seccion">{{
              t('admin.catalogoEstilo.patronesPanel.panelRotulo')
            }}</span>
          </div>
          <div class="panel-cuerpo">
            <app-table-toolbar
              [busqueda]="busqueda()"
              (busquedaChange)="busqueda.set($event)"
              [placeholderBusqueda]="t('admin.catalogoEstilo.patronesPanel.busquedaMarca')"
            >
              <app-segmented-filter
                [opciones]="filtros()"
                [valor]="filtroActivo()"
                [etiqueta]="t('admin.catalogoEstilo.patronesPanel.filtroEtiqueta')"
                (cambio)="filtroActivo.set($event)"
              />
            </app-table-toolbar>
            <p class="nota">{{ t('admin.catalogoEstilo.patronesPanel.toolbarNota') }}</p>
          </div>
          <span pie>{{ t('admin.catalogoEstilo.patronesPanel.pieIzquierda') }}</span>
          <strong pie>382</strong>
        </app-panel>

        <div class="fila-dialogo">
          <app-button variant="secundario" type="button" (pulsado)="dialogo.abrir()">
            {{ t('admin.catalogoEstilo.patronesPanel.abrirDialogo') }}
          </app-button>
          <app-dialog #dialogo>
            <h3>{{ t('admin.catalogoEstilo.patronesPanel.dialogoTitulo') }}</h3>
            <p>{{ t('admin.catalogoEstilo.patronesPanel.dialogoCuerpo') }}</p>
            <div pie>
              <app-button variant="secundario" type="button" (pulsado)="dialogo.cerrar()">
                {{ t('comun.cerrar') }}
              </app-button>
            </div>
          </app-dialog>
        </div>
      </section>
    </ng-container>
  `,
  styles: `
    .kpis {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: var(--sp-4);
      margin-bottom: var(--sp-6);
    }
    .nota {
      margin: var(--space-md) 0 0;
      color: var(--muted);
      font-size: var(--fs-sm);
    }
    .fila-dialogo {
      margin-top: var(--space-md);
    }
    h3 {
      margin: 0 0 var(--space-sm);
    }
    p {
      margin: 0;
    }
  `,
})
export class PatronesPanelSection {
  protected readonly busqueda = signal('');
  protected readonly filtroActivo = signal<'todas' | 'pendientes'>('todas');

  protected readonly filtros = signal<
    readonly { valor: 'todas' | 'pendientes'; etiqueta: string }[]
  >([]);

  constructor() {
    // Las etiquetas van por transloco: se montan aquí para no ensuciar el template.
    const transloco = inject(TranslocoService);
    this.filtros.set([
      {
        valor: 'todas',
        etiqueta: transloco.translate('admin.catalogoEstilo.patronesPanel.filtroTodas'),
      },
      {
        valor: 'pendientes',
        etiqueta: transloco.translate('admin.catalogoEstilo.patronesPanel.filtroPendientes'),
      },
    ]);
  }
}
