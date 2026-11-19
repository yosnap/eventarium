import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';
import { apiEvento } from '../routing/rutas-publicas';
import type { EventoParaCalendario } from '../../shared/calendar/calendar-links';

export interface RegistrationQuestion {
  readonly id: string;
  readonly type: 'short_text' | 'single_choice' | 'multiple_choice';
  readonly label: string;
  readonly required: boolean;
  /** Valores originales: los que se envían y valida la inscripción. */
  readonly options: readonly string[] | null;
  /** Las mismas opciones con el texto en el idioma de la página. */
  readonly choices?: readonly { readonly value: string; readonly label: string }[] | null;
  readonly sort_order: number;
}

/** Opciones de una pregunta como pares valor original / texto que se muestra. */
export function opcionesDePregunta(
  pregunta: RegistrationQuestion,
): { readonly valor: string; readonly etiqueta: string }[] {
  if (pregunta.choices) {
    return pregunta.choices.map((opcion) => ({ valor: opcion.value, etiqueta: opcion.label }));
  }
  return (pregunta.options ?? []).map((opcion) => ({ valor: opcion, etiqueta: opcion }));
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
  /** Versiones de las políticas del organizador aceptadas (vacía si no hay). */
  readonly acceptedPolicyVersionIds: readonly string[];
  readonly turnstileToken: string;
}

interface RespuestaGenerica {
  readonly message: string;
}

interface RespuestaVerificacion {
  readonly message: string;
  readonly status: string;
  /** Solo con la plaza confirmada: lo necesario para «añadir al calendario». */
  readonly event: EventoParaCalendario | null;
}

interface RespuestaPromocion {
  readonly message: string;
  /** Solo si la plaza queda confirmada (un evento de pago pasa a pendiente de pago). */
  readonly event: EventoParaCalendario | null;
}

export interface MyTicketInfo {
  readonly status: string;
  readonly full_name: string;
  readonly has_qr: boolean;
  /** Solo con la plaza confirmada: lo necesario para «añadir al calendario». */
  readonly event: EventoParaCalendario | null;
}

export interface MyRegistrationItem {
  readonly organization: {
    readonly slug: string;
    readonly name: string;
    readonly page_public: boolean;
  };
  readonly event_slug: string;
  readonly event_title: string;
  readonly starts_at: string;
  readonly organization_name: string;
  readonly status: string;
  /** La organización canceló el evento (no la persona). */
  readonly event_cancelled?: boolean;
  readonly ends_at: string;
  readonly timezone: string;
  /** Solo con la plaza confirmada y el evento en pie: lo necesario para
   * «añadir al calendario». */
  readonly calendar: EventoParaCalendario | null;
}

/** `refund`: `en_curso` si se devolvería el pago, `sin_reembolso` si no, nulo sin pago. */
export interface VistaPreviaCancelacion {
  readonly status: string;
  readonly event_title: string;
  readonly starts_at: string;
  readonly timezone: string;
  readonly already_started: boolean;
  readonly refund?: 'en_curso' | 'sin_reembolso' | null;
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

  async getQuestions(org: string, slug: string): Promise<RegistrationQuestion[]> {
    return firstValueFrom(
      this.http.get<RegistrationQuestion[]>(
        this.api.url(apiEvento(org, slug, '/registration-questions')),
      ),
    );
  }

  async submit(org: string, slug: string, datos: SubmitRegistrationInput): Promise<string> {
    const respuesta = await firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url(apiEvento(org, slug, '/registrations')), {
        email: datos.email,
        full_name: datos.fullName,
        answers: datos.answers,
        data_processing_accepted: datos.dataProcessingAccepted,
        marketing_accepted: datos.marketingAccepted,
        recording_accepted: datos.recordingAccepted,
        accepted_policy_version_ids: datos.acceptedPolicyVersionIds,
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

  async confirmWaitlistPromotion(token: string): Promise<RespuestaPromocion> {
    return firstValueFrom(
      this.http.post<RespuestaPromocion>(
        this.api.url('/public/registrations/confirm-waitlist-promotion'),
        { token },
      ),
    );
  }

  /** Qué se cancelaría con el enlace, sin gastarlo (la página pide confirmación). */
  async previewCancel(token: string): Promise<VistaPreviaCancelacion> {
    return firstValueFrom(
      this.http.post<VistaPreviaCancelacion>(this.api.url('/public/registrations/cancel/preview'), {
        token,
      }),
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
  async requestMisEventosAccess(email: string, turnstileToken: string): Promise<RespuestaGenerica> {
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

  /** «Mis eventos» con la sesión iniciada: sin enlace, del correo de la cuenta.
   * La API responde 403 si ese correo no está verificado o durante una
   * suplantación. */
  async getMyAccountRegistrations(): Promise<readonly MyRegistrationItem[]> {
    const respuesta = await firstValueFrom(
      this.http.get<{ registrations: readonly MyRegistrationItem[] }>(
        this.api.url('/public/mis-eventos/mios'),
      ),
    );
    return respuesta.registrations;
  }
}
