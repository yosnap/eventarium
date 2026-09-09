import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import type { RegistrationAnswerInput } from '../registrations/registrations.service';

export interface PublicTicketType {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly price_cents: number;
  readonly currency: string;
}

export interface CheckoutQuote {
  readonly price_cents: number;
  readonly discount_cents: number;
  readonly total_cents: number;
  readonly currency: string;
}

export interface StartCheckoutInput {
  readonly email: string;
  readonly fullName: string;
  readonly answers: readonly RegistrationAnswerInput[];
  readonly dataProcessingAccepted: boolean;
  readonly marketingAccepted: boolean;
  readonly recordingAccepted: boolean;
  readonly ticketTypeId: string;
  readonly code: string | null;
  readonly turnstileToken: string;
}

interface CheckoutStartResponse {
  readonly message: string;
  readonly checkout_url: string | null;
}

export interface PaymentStatus {
  readonly registration_status: string;
  readonly payment_status: string | null;
}

/**
 * Compra pública de una entrada (fase 6 del PRD, fase 4 de trabajo): tipos de
 * entrada vendibles, presupuesto y arranque del pago. `getStatus` es la única
 * fuente de verdad para la pantalla de retorno — nunca se da un pago por
 * confirmado por el mero retorno desde Stripe (ver `payment-return.ts`).
 */
@Injectable({ providedIn: 'root' })
export class PublicCheckoutService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  async getTicketTypes(slug: string): Promise<PublicTicketType[]> {
    return firstValueFrom(
      this.http.get<PublicTicketType[]>(this.api.url(`/public/events/${slug}/ticket-types`)),
    );
  }

  async quote(
    slug: string,
    datos: { ticketTypeId: string; code: string | null; turnstileToken: string },
  ): Promise<CheckoutQuote> {
    return firstValueFrom(
      this.http.post<CheckoutQuote>(this.api.url(`/public/events/${slug}/checkout/quote`), {
        ticket_type_id: datos.ticketTypeId,
        code: datos.code,
        turnstile_token: datos.turnstileToken,
      }),
    );
  }

  /** `checkout_url` es `null` cuando la inscripción existente no es pagable ahora mismo. */
  async startCheckout(slug: string, datos: StartCheckoutInput): Promise<CheckoutStartResponse> {
    return firstValueFrom(
      this.http.post<CheckoutStartResponse>(this.api.url(`/public/events/${slug}/checkout`), {
        email: datos.email,
        full_name: datos.fullName,
        answers: datos.answers,
        data_processing_accepted: datos.dataProcessingAccepted,
        marketing_accepted: datos.marketingAccepted,
        recording_accepted: datos.recordingAccepted,
        ticket_type_id: datos.ticketTypeId,
        code: datos.code,
        turnstile_token: datos.turnstileToken,
      }),
    );
  }

  /** Estado real, persistido, del pago — nunca inferido del simple retorno de Stripe. */
  async getStatus(slug: string, registrationId: string): Promise<PaymentStatus> {
    return firstValueFrom(
      this.http.get<PaymentStatus>(
        this.api.url(`/public/events/${slug}/checkout/${registrationId}/status`),
      ),
    );
  }
}
