import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

export interface StripeAccountStatus {
  readonly connected: boolean;
  readonly charges_enabled: boolean;
  readonly payouts_enabled: boolean;
  readonly details_submitted: boolean;
  readonly connected_at: string | null;
  readonly deauthorized_at: string | null;
  readonly last_synced_at: string | null;
}

interface StripeOnboardingResponse {
  readonly onboarding_url: string;
}

/**
 * Conexión Stripe Connect de la organización (fase 6 del PRD, fase 2 de
 * trabajo): onboarding hosted, estado persistido y sincronización manual.
 *
 * Las rutas van por `{organizationId}` (no `/organizations/me/...`, a
 * diferencia del resto del panel): el backend exige que ese identificador
 * coincida con el de la sesión y responde 404 en caso contrario, así que el
 * aislamiento cross-tenant se puede probar contra la propia URL.
 */
@Injectable({ providedIn: 'root' })
export class PaymentsService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  private base(organizationId: string): string {
    return `/organizations/${organizationId}/stripe`;
  }

  async getStatus(organizationId: string): Promise<StripeAccountStatus> {
    return firstValueFrom(
      this.http.get<StripeAccountStatus>(this.api.url(this.base(organizationId))),
    );
  }

  async startOnboarding(organizationId: string): Promise<string> {
    const respuesta = await firstValueFrom(
      this.http.post<StripeOnboardingResponse>(
        this.api.url(`${this.base(organizationId)}/onboarding`),
        {},
      ),
    );
    return respuesta.onboarding_url;
  }

  async sync(organizationId: string): Promise<StripeAccountStatus> {
    return firstValueFrom(
      this.http.post<StripeAccountStatus>(this.api.url(`${this.base(organizationId)}/sync`), {}),
    );
  }
}
