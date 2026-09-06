import { NgComponentOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  PendingTasks,
  Type,
  inject,
  signal,
} from '@angular/core';

import { ThemingService } from '../../../core/theming/theming.service';
import { resolveTemplate } from '../../../core/theming/template-registry';

/**
 * Página pública de inicio.
 *
 * No decide su aspecto: monta la plantilla que la organización haya elegido en su
 * branding. Añadir una plantilla nueva no requiere tocar esta página.
 */
@Component({
  selector: 'app-home-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgComponentOutlet],
  template: `
    @if (plantilla(); as componente) {
      <ng-container *ngComponentOutlet="componente" />
    }
  `,
})
export class HomePage {
  private readonly theming = inject(ThemingService);
  private readonly tareasPendientes = inject(PendingTasks);

  protected readonly plantilla = signal<Type<unknown> | null>(null);

  constructor() {
    // La carga se registra como tarea pendiente para que el renderizado en servidor
    // espere al `import()`; si no, el HTML se serializaría con la plantilla vacía.
    void this.tareasPendientes.run(async () => {
      this.plantilla.set(await resolveTemplate(this.theming.templateKey())());
    });
  }
}
