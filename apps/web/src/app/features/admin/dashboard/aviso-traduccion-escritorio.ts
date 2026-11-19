import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import { AuthService } from '../../../core/auth/auth.service';
import { ThemingService } from '../../../core/theming/theming.service';
import type { EditorDeTraducciones } from '../../../core/traducciones/traducciones.service';
import { AvisoClavePropia } from '../../../shared/ui/aviso-clave-propia';

/**
 * En el escritorio: si la organización publica en varios idiomas y no tiene
 * clave de IA propia, avisa de que no se traducirá sola. Sin permiso para verlo
 * o sin conexión, no muestra nada.
 */
@Component({
  selector: 'app-aviso-traduccion-escritorio',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [AvisoClavePropia],
  template: `
    @if (mostrar()) {
      <app-aviso-clave-propia />
    }
  `,
})
export class AvisoTraduccionEscritorio {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly theming = inject(ThemingService);
  protected readonly mostrar = signal(false);

  constructor() {
    void this.comprobar();
  }

  private async comprobar(): Promise<void> {
    const organizacion = this.auth.currentUser()?.organization_id;
    // Con un solo idioma en la plataforma no hay nada que traducir.
    const varios = (this.theming.plataforma()?.enabled_locales?.length ?? 0) > 1;
    if (!organizacion || !varios) {
      return;
    }
    try {
      const editor = await firstValueFrom(
        this.http.get<EditorDeTraducciones>(
          this.api.url(`/translations/organization/${organizacion}`),
          { params: { locale: 'en-US' } },
        ),
      );
      this.mostrar.set(editor.locales.length > 1 && editor.auto_translation_available === false);
    } catch {
      this.mostrar.set(false);
    }
  }
}
