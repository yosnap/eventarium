import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

export interface RegistrationQuestion {
  readonly id: string;
  readonly type: 'short_text' | 'single_choice' | 'multiple_choice';
  readonly label: string;
  readonly required: boolean;
  readonly options: readonly string[] | null;
  readonly sort_order: number;
}

export interface RegistrationAnswerInput {
  readonly question_id: string;
  readonly value: string | readonly string[] | null;
}

export interface SubmitRegistrationInput {
  readonly email: string;
  readonly fullName: string;
  readonly answers: readonly RegistrationAnswerInput[];
  readonly dataProcessingAccepted: boolean;
  readonly marketingAccepted: boolean;
  readonly recordingAccepted: boolean;
  readonly turnstileToken: string;
}

interface RespuestaGenerica {
  readonly message: string;
}

interface RespuestaVerificacion {
  readonly message: string;
  readonly status: string;
}

export interface MyTicketInfo {
  readonly status: string;
  readonly full_name: string;
  readonly has_qr: boolean;
}

export interface MyRegistrationItem {
  readonly event_slug: string;
  readonly event_title: string;
  readonly starts_at: string;
  readonly organization_name: string;
  readonly status: string;
}

/**
 * Formulario público de inscripción a un evento (fase 3 del PRD).
 *
 * CSR, como `AuthService`: son llamadas transaccionales, no contenido a
 * indexar. La respuesta de `submit` es siempre la misma exista o no ya el
 * email inscrito — el componente no debe intentar distinguir ambos casos.
 */
@Injectable({ providedIn: 'root' })
export class RegistrationsService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  async getQuestions(slug: string): Promise<RegistrationQuestion[]> {
    return firstValueFrom(
      this.http.get<RegistrationQuestion[]>(
        this.api.url(`/public/events/${slug}/registration-questions`),
      ),
    );
  }

  async submit(slug: string, datos: SubmitRegistrationInput): Promise<string> {
    const respuesta = await firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url(`/public/events/${slug}/registrations`), {
        email: datos.email,
        full_name: datos.fullName,
        answers: datos.answers,
        data_processing_accepted: datos.dataProcessingAccepted,
        marketing_accepted: datos.marketingAccepted,
        recording_accepted: datos.recordingAccepted,
        turnstile_token: datos.turnstileToken,
      }),
    );
    return respuesta.message;
  }

  async verify(token: string): Promise<RespuestaVerificacion> {
    return firstValueFrom(
      this.http.post<RespuestaVerificacion>(this.api.url('/public/registrations/verify'), {
        token,
      }),
    );
  }

  async confirmWaitlistPromotion(token: string): Promise<RespuestaGenerica> {
    return firstValueFrom(
      this.http.post<RespuestaGenerica>(
        this.api.url('/public/registrations/confirm-waitlist-promotion'),
        { token },
      ),
    );
  }

  async cancel(token: string): Promise<RespuestaGenerica> {
    return firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url('/public/registrations/cancel'), { token }),
    );
  }

  /**
   * `/mi-entrada` (fase 4 del PRD): reutiliza el token de autocancelación
   * (`GET`, nunca lo consume) para volver a mostrar el QR si la persona
   * perdió el correo.
   */
  async getMyTicket(token: string): Promise<MyTicketInfo> {
    return firstValueFrom(
      this.http.get<MyTicketInfo>(this.api.url('/public/registrations/my-ticket'), {
        params: { token },
      }),
    );
  }

  /** URL de la imagen PNG del QR — se usa directamente como `src` de un `<img>`. */
  myTicketQrUrl(token: string): string {
    return this.api.url(`/public/registrations/my-ticket/qr?token=${encodeURIComponent(token)}`);
  }

  /**
   * Plan «mis-eventos-asistente»: pide el magic-link de listado. Respuesta
   * anti-enumeración (siempre el mismo mensaje, exista o no el email entre
   * las inscripciones), igual que `AuthService.forgotPassword` — con
   * Turnstile obligatorio delante, mismo motivo (hallazgo de code-review:
   * sin él, el enlace es una herramienta de acoso por correo mucho más
   * barata de explotar).
   */
  async requestMisEventosAccess(
    email: string,
    turnstileToken: string,
  ): Promise<RespuestaGenerica> {
    return firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url('/public/mis-eventos/solicitar'), {
        email,
        turnstile_token: turnstileToken,
      }),
    );
  }

  /**
   * Consume el token del magic-link (un solo uso) y devuelve las
   * inscripciones. `POST`, no `GET` (hallazgo de code-review): el consumo
   * del token es un efecto secundario, y un `GET` con efecto secundario en
   * la propia URL del enlace de correo puede dispararlo sin querer un
   * escáner de enlaces corporativo antes de que la persona real haga clic.
   */
  async getMyRegistrations(token: string): Promise<readonly MyRegistrationItem[]> {
    const respuesta = await firstValueFrom(
      this.http.post<{ registrations: readonly MyRegistrationItem[] }>(
        this.api.url('/public/mis-eventos/ver'),
        { token },
      ),
    );
    return respuesta.registrations;
  }
}
