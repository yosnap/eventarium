import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { ApiError } from '../../../core/api/error.interceptor';
import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Select, type SelectOption } from '../../../shared/ui/select';

/** Una partida del presupuesto, para el desplegable de imputación. */
export interface PartidaParaGasto {
  readonly id: string;
  readonly name: string;
}

/**
 * Alta de un gasto del evento.
 *
 * Vive aparte del libro de contabilidad porque es un **formulario con su propio
 * estado** (cinco campos, su validación y sus dos errores) dentro de una pantalla
 * que ya era la más larga del proyecto. Separarlo no cambia nada de lo que hace:
 * recibe las partidas que puede elegir y avisa cuando ha creado el gasto, para
 * que la pantalla recargue sus cifras.
 *
 * `total_cents` se calcula aquí (base + IVA) y no se pide: es siempre esa suma, y
 * dejar que se escribiera aparte permitiría guardar un total que no cuadra con
 * sus componentes.
 */
@Component({
  selector: 'app-expense-form',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Select],
  template: `
    <ng-container *transloco="let t">
      <app-card [heading]="t('admin.events.accounting.altaGasto.titulo')">
        <form (submit)="crear($event)" novalidate class="formulario">
          <div class="campo">
            <label for="gasto-proveedor">{{
              t('admin.events.accounting.altaGasto.proveedor')
            }}</label>
            <input
              id="gasto-proveedor"
              type="text"
              [value]="proveedor()"
              (input)="proveedor.set(alTexto($event))"
            />
          </div>
          <app-select
            fieldId="gasto-partida"
            [label]="t('admin.events.accounting.partidas.columnaPartida')"
            [placeholder]="t('admin.events.accounting.altaGasto.sinPartida')"
            [options]="opcionesDePartida()"
            [(value)]="partidaId"
          />
          <div class="campo">
            <label for="gasto-fecha">{{
              t('admin.events.accounting.movimientos.columnaFecha')
            }}</label>
            <input
              id="gasto-fecha"
              type="date"
              [value]="fecha()"
              (input)="fecha.set(alTexto($event))"
            />
          </div>
          <div class="campo">
            <label for="gasto-base">{{ t('admin.events.accounting.altaGasto.base') }}</label>
            <input
              id="gasto-base"
              type="text"
              inputmode="decimal"
              [value]="base()"
              (input)="base.set(alTexto($event))"
            />
          </div>
          <div class="campo">
            <label for="gasto-iva">{{ t('admin.events.accounting.altaGasto.iva') }}</label>
            <input
              id="gasto-iva"
              type="text"
              inputmode="decimal"
              [value]="iva()"
              (input)="iva.set(alTexto($event))"
            />
          </div>

          @if (error(); as mensaje) {
            <app-alert tone="error">{{ mensaje }}</app-alert>
          }

          <app-button type="submit" [loading]="creando()">{{
            t('admin.events.accounting.altaGasto.crear')
          }}</app-button>
        </form>
      </app-card>
    </ng-container>
  `,
  styles: `
    :host {
      display: block;
    }
    .formulario {
      display: grid;
      gap: var(--space-md);
      max-width: 34rem;
    }
    .campo {
      display: grid;
      gap: var(--space-sm);
    }
    label {
      font-weight: 600;
    }
    /* A diferencia de \`select\`, no hay ninguna regla global para \`input\` en
     * \`styles.css\` — sin esto, los cuatro campos de este formulario no
     * llevaban ni borde ni fondo: no es que faltaran, es que eran
     * invisibles sobre el tema oscuro. */
    input {
      box-sizing: border-box;
      width: 100%;
      padding: 0.625rem 0.75rem;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
      color: var(--fg);
      font: inherit;
      min-height: 2.75rem;
    }
    input:focus-visible {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent);
    }
  `,
})
export class ExpenseForm {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly transloco = inject(TranslocoService);

  /** El evento al que se imputa el gasto. */
  readonly eventId = input.required<string>();
  /** Las partidas del presupuesto a las que se puede imputar, si hay alguna. */
  readonly partidas = input.required<readonly PartidaParaGasto[]>();

  /** Avisa de que el gasto se ha creado, para que la pantalla recargue. */
  readonly creado = output<string>();

  protected readonly proveedor = signal('');
  protected readonly partidaId = signal('');
  protected readonly fecha = signal('');
  protected readonly base = signal('');
  protected readonly iva = signal('');
  protected readonly creando = signal(false);

  protected readonly opcionesDePartida = computed<SelectOption[]>(() =>
    this.partidas().map((partida) => ({ value: partida.id, label: partida.name })),
  );
  protected readonly error = signal<string | null>(null);

  protected alTexto(evento: Event): string {
    return (evento.target as HTMLInputElement).value;
  }

  /** Convierte «1.234,56» o «1234.56» a céntimos. `null` si no es un número. */
  private aCents(texto: string): number | null {
    if (!texto.trim()) {
      return null;
    }
    const valor = Number(texto.replace(',', '.'));
    return Number.isFinite(valor) ? Math.round(valor * 100) : null;
  }

  protected async crear(evento: SubmitEvent): Promise<void> {
    evento.preventDefault();
    this.error.set(null);

    const proveedor = this.proveedor().trim();
    const fecha = this.fecha();
    const baseCents = this.aCents(this.base());
    const ivaCents = this.aCents(this.iva());

    if (!proveedor) {
      this.error.set(
        this.transloco.translate('admin.events.accounting.altaGasto.proveedorRequerido'),
      );
      return;
    }
    if (!fecha) {
      this.error.set(this.transloco.translate('admin.events.accounting.altaGasto.fechaRequerida'));
      return;
    }
    if (baseCents === null || baseCents < 0) {
      this.error.set(this.transloco.translate('admin.events.accounting.altaGasto.importeInvalido'));
      return;
    }

    this.creando.set(true);
    try {
      await firstValueFrom(
        this.http.post(this.api.url(`/accounting/events/${this.eventId()}/expenses`), {
          budget_line_id: this.partidaId() || null,
          provider_name: proveedor,
          expense_date: new Date(fecha).toISOString(),
          base_cents: baseCents,
          vat_cents: ivaCents,
          // El total lo compone el formulario: pedirlo aparte dejaría guardar
          // una cifra que no cuadra con sus sumandos.
          total_cents: baseCents + (ivaCents ?? 0),
        }),
      );
      this.proveedor.set('');
      this.partidaId.set('');
      this.fecha.set('');
      this.base.set('');
      this.iva.set('');
      this.creado.emit(this.transloco.translate('admin.events.accounting.altaGasto.creado'));
    } catch (error) {
      this.error.set(
        error instanceof ApiError
          ? error.message
          : this.transloco.translate('admin.events.accounting.error'),
      );
    } finally {
      this.creando.set(false);
    }
  }
}
