import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from '../api/api.service';

export interface UsuarioAutenticado {
  readonly id: string;
  readonly email: string;
  readonly first_name: string | null;
  readonly last_name: string | null;
  readonly is_superadmin: boolean;
}

/**
 * Nombre para mostrar. El registro no pide nombre, así que puede no haber ninguno
 * todavía: se recurre al correo antes que a un hueco en blanco.
 */
export function displayName(
  usuario: Pick<UsuarioAutenticado, 'email' | 'first_name' | 'last_name'>,
): string {
  const nombre = [usuario.first_name, usuario.last_name].filter(Boolean).join(' ').trim();
  return nombre || usuario.email;
}

interface RespuestaLogin {
  readonly access_token: string;
  readonly expires_in: number;
  readonly user: UsuarioAutenticado;
}

interface RespuestaRefresh {
  readonly access_token: string;
  readonly expires_in: number;
}

interface RespuestaGenerica {
  readonly message: string;
}

export interface EnlaceSocial {
  readonly kind: string;
  readonly url: string;
}

export interface OrganizacionDeLaPersona {
  readonly organization_id: string;
  readonly slug: string;
  readonly name: string;
  readonly host: string | null;
}

/**
 * Sesión del panel de administración.
 *
 * El access token vive **solo en memoria**: guardarlo en `localStorage` lo dejaría al
 * alcance de cualquier XSS y sobreviviría al cierre de la pestaña. El refresh token no
 * lo ve este código en ningún momento: viaja en una cookie `HttpOnly` que gestiona el
 * backend, y por eso todas las peticiones de auth van con `withCredentials`.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ApiService);

  private readonly token = signal<string | null>(null);
  private readonly usuario = signal<UsuarioAutenticado | null>(null);
  /**
   * Access token **sin organización**, emitido al verificar el correo (fase 2). Vive
   * aparte del token de sesión normal a propósito: si compartiera `token`,
   * `isAuthenticated()` daría `true` para alguien que todavía no pertenece a ninguna
   * organización, y `authGuard` le dejaría entrar en `/admin` sin que hubiera nada que
   * mostrar ahí.
   */
  private readonly bridge = signal<string | null>(null);

  readonly accessToken = this.token.asReadonly();
  readonly currentUser = this.usuario.asReadonly();
  readonly isAuthenticated = computed(() => this.token() !== null);
  readonly bridgeToken = this.bridge.asReadonly();

  /**
   * Recarga el usuario actual desde la API.
   *
   * `refresh()` solo renueva el access token con la cookie: tras una recarga completa
   * de página, `currentUser()` queda a `null` aunque la sesión siga viva, porque nada
   * ha vuelto a pedir `/users/me`. Las páginas que necesitan datos frescos del usuario
   * (p. ej. `account-page`) llaman a esto explícitamente en vez de asumir el signal.
   */
  async loadCurrentUser(): Promise<UsuarioAutenticado> {
    const respuesta = await firstValueFrom(
      this.http.get<UsuarioAutenticado>(this.api.url('/users/me')),
    );
    this.usuario.set(respuesta);
    return respuesta;
  }

  async login(email: string, password: string): Promise<void> {
    const respuesta = await firstValueFrom(
      this.http.post<RespuestaLogin>(
        this.api.url('/auth/login'),
        { email, password },
        { withCredentials: true },
      ),
    );
    this.token.set(respuesta.access_token);
    this.usuario.set(respuesta.user);
  }

  /** Renueva el access token con la cookie. Devuelve `false` si ya no hay sesión. */
  async refresh(): Promise<boolean> {
    try {
      const respuesta = await firstValueFrom(
        this.http.post<RespuestaRefresh>(this.api.url('/auth/refresh'), null, {
          withCredentials: true,
        }),
      );
      this.token.set(respuesta.access_token);
      return true;
    } catch {
      this.clear();
      return false;
    }
  }

  async register(email: string, password: string, turnstileToken: string): Promise<void> {
    await firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url('/auth/register'), {
        email,
        password,
        turnstile_token: turnstileToken,
      }),
    );
  }

  async verifyEmail(token: string): Promise<void> {
    const respuesta = await firstValueFrom(
      this.http.get<RespuestaGenerica & { access_token: string }>(
        this.api.url('/auth/verify-email'),
        { params: { token } },
      ),
    );
    this.bridge.set(respuesta.access_token);
  }

  /**
   * Crea la organización con el token puente de `verifyEmail`. La cabecera se fija a
   * mano: el interceptor solo añade automáticamente el token de sesión normal
   * (`accessToken`), que aquí sigue valiendo `null`.
   */
  async createOrganization(datos: {
    name: string;
    slug: string;
    firstName: string;
    lastName: string;
    turnstileToken: string;
  }): Promise<{ id: string; slug: string; host: string }> {
    const token = this.bridge();
    if (!token) {
      throw new Error('No hay una sesión de verificación activa.');
    }
    return firstValueFrom(
      this.http.post<{ id: string; slug: string; host: string }>(
        this.api.url('/organizations'),
        {
          name: datos.name,
          slug: datos.slug,
          first_name: datos.firstName,
          last_name: datos.lastName,
          turnstile_token: datos.turnstileToken,
        },
        { headers: { Authorization: `Bearer ${token}` } },
      ),
    );
  }

  async checkSlug(slug: string): Promise<boolean> {
    const respuesta = await firstValueFrom(
      this.http.get<{ available: boolean }>(this.api.url('/organizations/check-slug'), {
        params: { slug },
      }),
    );
    return respuesta.available;
  }

  async resendVerification(email: string, turnstileToken: string): Promise<void> {
    await firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url('/auth/resend-verification'), {
        email,
        turnstile_token: turnstileToken,
      }),
    );
  }

  async forgotPassword(email: string, turnstileToken: string): Promise<void> {
    await firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url('/auth/forgot-password'), {
        email,
        turnstile_token: turnstileToken,
      }),
    );
  }

  async resetPassword(token: string, newPassword: string): Promise<void> {
    await firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url('/auth/reset-password'), {
        token,
        new_password: newPassword,
      }),
    );
  }

  /** Nombre y locale. El correo tiene su propio flujo (`changeEmail`). */
  async updateMe(datos: { firstName?: string; lastName?: string; locale?: string }): Promise<void> {
    const respuesta = await firstValueFrom(
      this.http.patch<UsuarioAutenticado>(this.api.url('/users/me'), {
        ...(datos.firstName !== undefined ? { first_name: datos.firstName } : {}),
        ...(datos.lastName !== undefined ? { last_name: datos.lastName } : {}),
        ...(datos.locale !== undefined ? { locale: datos.locale } : {}),
      }),
    );
    this.usuario.set(respuesta);
  }

  /** Exige la contraseña actual. El cambio no se aplica hasta confirmarlo por correo. */
  async changeEmail(newEmail: string, password: string): Promise<void> {
    await firstValueFrom(
      this.http.post(this.api.url('/users/me/change-email'), {
        new_email: newEmail,
        password,
      }),
    );
  }

  /** Sin sesión necesaria: el token prueba la propiedad del correo nuevo. */
  async confirmChangeEmail(token: string): Promise<void> {
    await firstValueFrom(this.http.post(this.api.url('/users/me/change-email/confirm'), { token }));
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await firstValueFrom(
      this.http.post(this.api.url('/users/me/change-password'), {
        current_password: currentPassword,
        new_password: newPassword,
      }),
    );
  }

  async listSocialLinks(): Promise<EnlaceSocial[]> {
    return firstValueFrom(this.http.get<EnlaceSocial[]>(this.api.url('/users/me/social-links')));
  }

  async upsertSocialLink(kind: string, url: string): Promise<EnlaceSocial> {
    return firstValueFrom(
      this.http.put<EnlaceSocial>(this.api.url(`/users/me/social-links/${kind}`), { url }),
    );
  }

  async deleteSocialLink(kind: string): Promise<void> {
    await firstValueFrom(this.http.delete(this.api.url(`/users/me/social-links/${kind}`)));
  }

  async listMyOrganizations(): Promise<OrganizacionDeLaPersona[]> {
    return firstValueFrom(
      this.http.get<OrganizacionDeLaPersona[]>(this.api.url('/users/me/organizations')),
    );
  }

  async logout(): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(this.api.url('/auth/logout'), null, { withCredentials: true }),
      );
    } finally {
      this.clear();
    }
  }

  clear(): void {
    this.token.set(null);
    this.usuario.set(null);
    this.bridge.set(null);
  }
}
