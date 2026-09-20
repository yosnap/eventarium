import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { TranslocoDirective } from '@jsverse/transloco';

/** Un requisito de la política de contraseña, con su comprobación. */
export interface PasswordRequirement {
  readonly key: string;
  readonly test: (password: string) => boolean;
}

/**
 * Política de contraseña del registro: mínimo 8 caracteres, mayúscula, minúscula,
 * número y carácter especial. Mismo conjunto de caracteres especiales que valida la
 * API (`core/security.py:password_meets_complexity`), para que el cliente no acepte
 * una contraseña que el servidor rechazaría después.
 */
export const PASSWORD_REQUIREMENTS: readonly PasswordRequirement[] = [
  { key: 'longitud', test: (p) => p.length >= 8 },
  { key: 'mayuscula', test: (p) => /[A-Z]/.test(p) },
  { key: 'minuscula', test: (p) => /[a-z]/.test(p) },
  { key: 'numero', test: (p) => /[0-9]/.test(p) },
  { key: 'especial', test: (p) => /[!@#$%^&*(),.?":{}|<>]/.test(p) },
];

export function isPasswordValid(password: string): boolean {
  return PASSWORD_REQUIREMENTS.every((req) => req.test(password));
}

function passwordStrength(password: string): number {
  if (!password) return 0;
  return PASSWORD_REQUIREMENTS.filter((req) => req.test(password)).length;
}

const ETIQUETAS_FUERZA = [
  'registro.fuerza.muyDebil',
  'registro.fuerza.muyDebil',
  'registro.fuerza.debil',
  'registro.fuerza.aceptable',
  'registro.fuerza.buena',
  'registro.fuerza.fuerte',
] as const;

/**
 * Indicador de fuerza de la contraseña, con la lista de requisitos.
 *
 * La barra de color es solo apoyo visual (1.4.1, no es el único medio): cada
 * requisito lleva además su texto de estado («cumplido»/«pendiente»), legible por un
 * lector de pantalla sin depender del color ni de un `aria-live` que interrumpiría en
 * cada pulsación.
 */
@Component({
  selector: 'app-password-strength',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TranslocoDirective],
  template: `
    <ng-container *transloco="let t">
      @if (password()) {
        <div class="fuerza">
          <div class="barra">
            <div class="relleno" [class]="clase()" [style.width.%]="porcentaje()"></div>
          </div>
          <span class="etiqueta">{{ t('registro.fuerza.titulo') }}: {{ t(etiqueta()) }}</span>
        </div>
        <ul class="requisitos">
          @for (req of requisitos; track req.key) {
            <li [class.cumplido]="req.test(password())">
              <span aria-hidden="true">{{ req.test(password()) ? '✓' : '✗' }}</span>
              {{ t('registro.requisitos.' + req.key) }}
              <span class="visualmente-oculto">
                {{
                  req.test(password())
                    ? t('registro.requisitoCumplido')
                    : t('registro.requisitoPendiente')
                }}
              </span>
            </li>
          }
        </ul>
      }
    </ng-container>
  `,
  styles: `
    .fuerza {
      display: grid;
      gap: var(--space-xs);
      margin-top: var(--space-xs);
    }
    .barra {
      height: 0.375rem;
      border-radius: var(--radius-md);
      background-color: var(--surface-2);
      overflow: hidden;
    }
    .relleno {
      height: 100%;
      transition: width 0.2s ease;
    }
    .debil {
      background-color: var(--danger);
    }
    .media {
      background-color: var(--warn);
    }
    .fuerte {
      background-color: var(--accent);
    }
    .etiqueta {
      font-size: 0.8125rem;
    }
    .requisitos {
      list-style: none;
      margin: var(--space-xs) 0 0;
      padding: 0;
      display: grid;
      gap: 0.25rem;
      font-size: 0.8125rem;
      color: var(--muted);
    }
    .requisitos li.cumplido {
      color: var(--accent-hi);
    }
    .visualmente-oculto {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }
  `,
})
export class PasswordStrength {
  readonly password = input.required<string>();

  protected readonly requisitos = PASSWORD_REQUIREMENTS;

  protected readonly fuerza = computed(() => passwordStrength(this.password()));
  protected readonly porcentaje = computed(
    () => (this.fuerza() / PASSWORD_REQUIREMENTS.length) * 100,
  );
  protected readonly etiqueta = computed(() => ETIQUETAS_FUERZA[this.fuerza()]);
  protected readonly clase = computed(() => {
    const fuerza = this.fuerza();
    if (fuerza <= 2) return 'debil';
    if (fuerza <= 4) return 'media';
    return 'fuerte';
  });
}
