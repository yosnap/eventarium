import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { AuthService } from '../../core/auth/auth.service';
import { Button } from '../../shared/ui/button';

/**
 * Aviso permanente de que se está suplantando a otra persona.
 *
 * Se pinta en la raíz de la aplicación, así que aparece en cualquier pantalla —
 * no se puede esquivar navegando. Es **UX**, no la barrera de seguridad: quien
 * salte la interfaz (una petición directa) sigue encontrando el bloqueo de solo
 * lectura en el backend, que es donde está la garantía real.
 */
@Component({
  selector: 'app-impersonation-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Button],
  template: `
    <ng-container *transloco="let t">
      @if (auth.suplantando(); as sesion) {
        <div class="aviso" role="status">
          <p>
            {{ t('impersonacion.aviso', { nombre: sesion.nombre }) }}
          </p>
          <app-button
            variant="terciario"
            [compacto]="true"
            [loading]="saliendo()"
            (pulsado)="salir()"
          >
            {{ t('impersonacion.salir') }}
          </app-button>
        </div>
      }
    </ng-container>
  `,
  styles: `
    .aviso {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 1rem;
      padding: 0.5rem 1rem;
      background: var(--warn);
      color: var(--bg);
      font-weight: 600;
    }
    .aviso p {
      margin: 0;
    }
  `,
})
export class ImpersonationBanner {
  protected readonly auth = inject(AuthService);
  protected readonly saliendo = signal(false);

  protected async salir(): Promise<void> {
    this.saliendo.set(true);
    try {
      await this.auth.salirDeImpersonacion();
      // Recarga completa: el estado del administrador (su organización, sus
      // permisos) es el que corresponde ahora, y reconstruirlo a mano por toda
      // la aplicación sería más frágil que volver a pedirlo.
      window.location.reload();
    } finally {
      this.saliendo.set(false);
    }
  }
}
