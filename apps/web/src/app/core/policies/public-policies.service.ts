import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

export type TipoDePolitica = 'condiciones' | 'reembolsos' | 'privacidad' | 'otras';

export interface PoliticaPublica {
  readonly version_id: string;
  readonly kind: TipoDePolitica;
  readonly version: number;
  readonly content: string;
  readonly created_at: string;
}

/** Contrato de `GET /public/events/{slug}/policies`. */
export interface PoliticasPublicas {
  readonly organization_name: string;
  /** Solo los textos vigentes; vacía si el evento no tiene ninguno. */
  readonly policies: readonly PoliticaPublica[];
}

/** Código del 409 cuando lo aceptado no cuadra con los textos vigentes. */
export const CODIGO_POLITICAS_CAMBIADAS = 'politicas_cambiadas';

/** Políticas y condiciones que cada organizador fija para su evento. */
@Injectable({ providedIn: 'root' })
export class PublicPoliciesService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  obtener(slug: string): Promise<PoliticasPublicas> {
    return firstValueFrom(
      this.http.get<PoliticasPublicas>(this.api.url(`/public/events/${slug}/policies`), {
        headers: this.api.serverForwardHeaders(),
      }),
    );
  }
}
