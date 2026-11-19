import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import type { Idioma } from '../i18n/idioma';

/** Tipos de contenido que tienen pestaña de idioma en el panel. */
export type TipoTraducible =
  | 'event'
  | 'session'
  | 'session_type'
  | 'venue'
  | 'ticket_type'
  | 'question'
  | 'sponsor_tier'
  | 'sponsor'
  | 'member_profile'
  | 'organization'
  | 'policy_version'
  | 'nearby_place';

export interface TextoTraducible {
  readonly entity_type: string;
  readonly entity_id: string;
  readonly field: string;
  readonly original: string;
  readonly value: string | null;
  readonly origin: 'ia' | 'manual' | 'revisada' | null;
  readonly status: 'al_dia' | 'desactualizada' | 'pendiente';
}

export interface EditorDeTraducciones {
  readonly locale: Idioma;
  readonly source_locale: Idioma;
  /** Idiomas en que publica la organización: con uno solo no hay pestañas. */
  readonly locales: readonly Idioma[];
  readonly items: readonly TextoTraducible[];
  /** La organización tiene clave de IA propia: si no, no hay traducción automática. */
  readonly auto_translation_available?: boolean;
}

export interface CambioDeTraduccion {
  readonly entity_type: string;
  readonly entity_id: string;
  readonly field: string;
  /** Vacío borra la traducción. */
  readonly value: string;
}

export interface ResumenDeTraduccion {
  readonly source_locale: Idioma;
  readonly locales: readonly { locale: Idioma; total: number; up_to_date: number }[];
  readonly auto_translation_available?: boolean;
}

/** Traducciones del contenido del organizador (`/translations`). */
@Injectable({ providedIn: 'root' })
export class TraduccionesService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  private url(tipo: TipoTraducible, id: string): string {
    return this.api.url(`/translations/${tipo}/${id}`);
  }

  obtener(tipo: TipoTraducible, id: string, locale: Idioma): Promise<EditorDeTraducciones> {
    return firstValueFrom(
      this.http.get<EditorDeTraducciones>(this.url(tipo, id), { params: { locale } }),
    );
  }

  guardar(
    tipo: TipoTraducible,
    id: string,
    locale: Idioma,
    items: readonly CambioDeTraduccion[],
  ): Promise<EditorDeTraducciones> {
    return firstValueFrom(
      this.http.put<EditorDeTraducciones>(this.url(tipo, id), { items }, { params: { locale } }),
    );
  }

  revisar(
    tipo: TipoTraducible,
    id: string,
    locale: Idioma,
    texto: Pick<TextoTraducible, 'entity_type' | 'entity_id' | 'field' | 'original'>,
  ): Promise<EditorDeTraducciones> {
    return firstValueFrom(
      this.http.post<EditorDeTraducciones>(
        `${this.url(tipo, id)}/review`,
        {
          entity_type: texto.entity_type,
          entity_id: texto.entity_id,
          field: texto.field,
          // El original que se ve: si cambió mientras tanto, la API responde 409.
          original: texto.original,
        },
        { params: { locale } },
      ),
    );
  }

  resumenDeEvento(eventId: string): Promise<ResumenDeTraduccion> {
    return firstValueFrom(
      this.http.get<ResumenDeTraduccion>(this.api.url(`/translations/events/${eventId}/summary`)),
    );
  }
}
