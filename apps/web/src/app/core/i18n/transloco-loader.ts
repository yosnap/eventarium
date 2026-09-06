import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Translation, TranslocoLoader } from '@jsverse/transloco';

import { ApiService } from '../api/api.service';

/** Carga los ficheros de traducción de `src/assets/i18n`. */
@Injectable({ providedIn: 'root' })
export class TraduccionesLoader implements TranslocoLoader {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  getTranslation(idioma: string) {
    // En SSR la ruta relativa no resuelve contra ningún origen: hay que dar una absoluta.
    const base = this.api.isServer ? 'http://localhost:4000' : '';
    return this.http.get<Translation>(`${base}/assets/i18n/${idioma}.json`);
  }
}
