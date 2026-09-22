import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';

import { AiUsageErrorOut } from '../../../core/api/generated/models/ai-usage-error-out';
import { AiUsageRecordOut } from '../../../core/api/generated/models/ai-usage-record-out';
import { Chip, type ChipTone } from '../../../shared/ui/chip';
import { DataTable, type DataTableColumn } from '../../../shared/ui/data-table';

/** Un registro de uso, con la organización solo en el panel del admin. */
export type RegistroDeUso = AiUsageRecordOut & { readonly organization_id?: string };

/**
 * Las dos tablas de actividad que comparten los dos paneles: las últimas
 * llamadas y los últimos códigos de error agrupados.
 *
 * No es un panel de series temporales (no-objetivo del PRD): son tablas de lo
 * que ha pasado, que es lo que hace falta para diagnosticar «por qué el OCR no
 * responde» sin abrir los registros del servidor.
 */
@Component({
  selector: 'app-ai-usage-tables',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Chip, DataTable, DatePipe],
  template: `
    <ng-container *transloco="let t">
      <div class="tablas">
        <app-data-table [columnas]="columnasDeLlamadas()" [caption]="t('admin.ia.uso.ultimas')">
          @for (registro of registros(); track registro.id) {
            <tr>
              <td>{{ registro.created_at | date: 'short' }}</td>
              @if (conOrganizacion()) {
                <td class="monoespaciada">{{ registro.organization_id }}</td>
              }
              <td>{{ registro.use_case }}</td>
              <td>{{ registro.provider }} / {{ registro.model }}</td>
              <td>
                <app-chip [tone]="tonoDelEstado(registro.status)">
                  {{ t('admin.ia.uso.estado.' + registro.status) }}
                </app-chip>
              </td>
              <td class="numerica">{{ registro.input_tokens ?? '—' }}</td>
              <td class="numerica">{{ registro.output_tokens ?? '—' }}</td>
              <td class="numerica">
                {{ importe(registro.cost_usd) }}
                @if (!registro.cost_auditable) {
                  <span class="estimado">{{ t('admin.ia.uso.estimado') }}</span>
                }
              </td>
            </tr>
          } @empty {
            <tr>
              <td [attr.colspan]="columnasDeLlamadas().length">
                {{ t('admin.ia.uso.sinLlamadas') }}
              </td>
            </tr>
          }
        </app-data-table>

        <app-data-table [columnas]="columnasDeErrores()" [caption]="t('admin.ia.uso.errores')">
          @for (fallo of errores(); track fallo.error_code) {
            <tr>
              <td class="monoespaciada">{{ fallo.error_code }}</td>
              <td class="numerica">{{ fallo.veces }}</td>
              <td>{{ fallo.ultima_vez | date: 'short' }}</td>
            </tr>
          } @empty {
            <tr>
              <td [attr.colspan]="columnasDeErrores().length">
                {{ t('admin.ia.uso.sinErrores') }}
              </td>
            </tr>
          }
        </app-data-table>
      </div>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .tablas {
      display: grid;
      gap: var(--space-lg);
    }
    .monoespaciada {
      font-family: var(--font-mono, monospace);
      font-size: var(--fs-sm);
    }
    .estimado {
      color: var(--muted);
      font-size: var(--fs-sm);
      margin-inline-start: 0.35rem;
    }
  `,
})
export class AiUsageTables {
  private readonly transloco = inject(TranslocoService);

  readonly registros = input.required<readonly RegistroDeUso[]>();
  readonly errores = input.required<readonly AiUsageErrorOut[]>();
  /** `true` solo en el panel del admin, donde el agregado cruza organizaciones. */
  readonly conOrganizacion = input(false);

  protected readonly columnasDeLlamadas = computed<DataTableColumn[]>(() => {
    const t = (clave: string): string => this.transloco.translate(clave);
    const columnas: DataTableColumn[] = [{ key: 'fecha', label: t('admin.ia.uso.columnaFecha') }];
    if (this.conOrganizacion()) {
      columnas.push({ key: 'organizacion', label: t('admin.ia.uso.columnaOrganizacion') });
    }
    columnas.push(
      { key: 'caso', label: t('admin.ia.uso.columnaCaso') },
      { key: 'modelo', label: t('admin.ia.uso.columnaModelo') },
      { key: 'estado', label: t('admin.ia.uso.columnaEstado') },
      { key: 'entrada', label: t('admin.ia.uso.columnaEntrada'), numerica: true },
      { key: 'salida', label: t('admin.ia.uso.columnaSalida'), numerica: true },
      { key: 'coste', label: t('admin.ia.uso.columnaCoste'), numerica: true },
    );
    return columnas;
  });

  protected readonly columnasDeErrores = computed<DataTableColumn[]>(() => [
    { key: 'codigo', label: this.transloco.translate('admin.ia.uso.columnaCodigo') },
    { key: 'veces', label: this.transloco.translate('admin.ia.uso.columnaVeces'), numerica: true },
    { key: 'ultima', label: this.transloco.translate('admin.ia.uso.columnaUltimaVez') },
  ]);

  /** `apagado` es el tono de «fallido»: no hay tono de error en `app-chip`, y
   * el estado se lee por el texto del chip, no por su color. */
  protected tonoDelEstado(estado: string): ChipTone {
    if (estado === 'liquidado') {
      return 'ok';
    }
    return estado === 'fallido' ? 'apagado' : 'espera';
  }

  /** Importe en USD con seis decimales tal y como llega, sin redondear a céntimos. */
  protected importe(valor: string): string {
    const numero = Number(valor);
    return Number.isFinite(numero) ? `$${numero.toFixed(4)}` : valor;
  }
}
