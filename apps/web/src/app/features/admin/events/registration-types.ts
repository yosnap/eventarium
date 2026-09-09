/**
 * Tipos compartidos por los componentes de inscripciones y preguntas de
 * inscripción de un evento, calcados del payload JSON que devuelve la API
 * (snake_case tal cual, sin remapear a camelCase).
 */

export type RegistrationStatus =
  | 'pending_verification'
  | 'pending_approval'
  | 'pending_payment'
  | 'confirmed'
  | 'rejected'
  | 'cancelled'
  | 'waitlisted';

export const ESTADOS_DE_INSCRIPCION: readonly RegistrationStatus[] = [
  'pending_verification',
  'pending_approval',
  'pending_payment',
  'confirmed',
  'rejected',
  'cancelled',
  'waitlisted',
];

export interface RegistrationListItem {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
  readonly status: RegistrationStatus;
  readonly created_at: string;
  readonly verified_at: string | null;
  readonly confirmed_at: string | null;
  readonly waitlist_promoted_at: string | null;
  readonly waitlist_promotion_expires_at: string | null;
}

export interface RegistrationAnswerOut {
  readonly question_id: string;
  readonly label: string;
  readonly value: string | readonly string[] | null;
}

export interface RegistrationConsentOut {
  readonly data_processing_accepted_at: string;
  readonly marketing_accepted_at: string | null;
  readonly recording_accepted_at: string | null;
}

export interface RegistrationDetail extends RegistrationListItem {
  readonly approved_at: string | null;
  readonly rejected_at: string | null;
  readonly cancelled_at: string | null;
  readonly answers: readonly RegistrationAnswerOut[];
  readonly consent: RegistrationConsentOut | null;
}

export interface RegistrationStats {
  readonly initiated: number;
  readonly verified: number;
  readonly pending_approval: number;
  readonly pending_payment: number;
  readonly confirmed: number;
  readonly rejected: number;
  readonly cancelled: number;
  readonly waitlisted: number;
  readonly verified_conversion_rate: number | null;
  readonly confirmed_conversion_rate: number | null;
}

export type RegistrationQuestionType = 'short_text' | 'single_choice' | 'multiple_choice';

export interface RegistrationQuestionResponse {
  readonly id: string;
  readonly type: RegistrationQuestionType;
  readonly label: string;
  readonly required: boolean;
  readonly sort_order: number;
  readonly options: readonly string[] | null;
}

export interface RegistrationPage {
  readonly items: readonly RegistrationListItem[];
  readonly total: number;
  readonly limit: number;
  readonly offset: number;
}

/**
 * Convierte un valor snake_case (p. ej. `pending_approval`) en PascalCase
 * (`PendingApproval`) para componer la clave de i18n del estado, del mismo modo
 * que `events-page` capitaliza sus estados de una sola palabra.
 */
export function claveDeEstado(valor: string): string {
  return valor
    .split('_')
    .map((parte) => parte.charAt(0).toUpperCase() + parte.slice(1))
    .join('');
}
