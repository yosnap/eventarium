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
}
