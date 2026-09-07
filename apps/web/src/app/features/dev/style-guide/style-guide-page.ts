import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

import { Alert } from '../../../shared/ui/alert';
import { Button } from '../../../shared/ui/button';
import { Card } from '../../../shared/ui/card';
import { Input } from '../../../shared/ui/input';
import { PasswordStrength } from '../../../shared/ui/password-strength';
import { Textarea } from '../../../shared/ui/textarea';

/**
 * Catálogo interno de `shared/ui`, para verlos y probarlos juntos mientras se
 * diseñan. No es una pantalla de producto: no lleva enlace desde ningún sitio ni
 * necesita entrar en el checklist de accesibilidad de `docs/accesibilidad.md` (esa
 * cobertura ya la tienen los componentes en sus propios tests).
 */
@Component({
  selector: 'app-style-guide-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective, Alert, Button, Card, Input, PasswordStrength, Textarea],
  template: `
    <ng-container *transloco="let t">
      <main class="pagina">
        <h1>Catálogo de componentes</h1>
        <p>Uso interno: no forma parte del producto.</p>

        <section>
          <h2>Botones</h2>
          <div class="fila">
            <app-button variant="primario">Primario</app-button>
            <app-button variant="secundario">Secundario</app-button>
            <app-button variant="peligro">Peligro</app-button>
            <app-button [loading]="true">Cargando</app-button>
            <app-button [disabled]="true">Desactivado</app-button>
          </div>
        </section>

        <section>
          <h2>Alertas</h2>
          <div class="columna">
            <app-alert tone="info" title="Información">Mensaje informativo.</app-alert>
            <app-alert tone="exito" title="Éxito">La operación se completó.</app-alert>
            <app-alert tone="error" title="Error">Algo ha ido mal.</app-alert>
          </div>
        </section>

        <section>
          <h2>Tarjetas</h2>
          <app-card heading="Título de la tarjeta">
            <p>Contenido de ejemplo dentro de la tarjeta.</p>
          </app-card>
        </section>

        <section>
          <h2>Campos de formulario</h2>
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
          </div>
        </section>
      </main>
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
      font-size: 1.125rem;
      border-bottom: 1px solid var(--color-border);
      padding-bottom: var(--space-xs);
    }
    .fila {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-sm);
      align-items: center;
    }
    .columna {
      display: grid;
      gap: var(--space-md);
    }
    .campos {
      max-width: 24rem;
    }
  `,
})
export class StyleGuidePage {
  protected readonly texto = signal('');
  protected readonly correo = signal('');
  protected readonly conError = signal('valor con error');
  protected readonly password = signal('');
  protected readonly descripcion = signal('');
}
