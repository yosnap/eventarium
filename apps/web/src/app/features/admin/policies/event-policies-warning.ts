import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  type OnInit,
  inject,
  input,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { Alert } from '../../../shared/ui/alert';
import { type PoliticasDeEvento } from './policies-types';

/**
 * Aviso en el resumen del evento cuando no le queda ningún texto vigente (ni
 * propio ni de la organización). Informativo: no impide publicar.
 */
@Component({
  selector: 'app-event-policies-warning',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, RouterLink, Alert],
  template: `
    <ng-container *transloco="let t">
      @if (sinTextos()) {
        <app-alert tone="info" [title]="t('admin.politicas.pendientesTitulo')">
          {{ t('admin.politicas.pendientes') }}
          <a [routerLink]="['/dashboard/events', eventId(), 'politicas']">
            {{ t('admin.politicas.irAPoliticas') }}
          </a>
        </app-alert>
      }
    </ng-container>
  `,
})
export class EventPoliciesWarning implements OnInit {
  readonly eventId = input.required<string>();

  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  protected readonly sinTextos = signal(false);

  ngOnInit(): void {
    void this.comprobar();
  }

  private async comprobar(): Promise<void> {
    try {
      const respuesta = await firstValueFrom(
        this.http.get<PoliticasDeEvento>(this.api.url(`/events/${this.eventId()}/policies`)),
      );
      this.sinTextos.set((respuesta.items ?? []).every((item) => item.origin === 'ninguno'));
    } catch {
      // Informativo: si no se puede comprobar, no se avisa de nada.
    }
  }
}
