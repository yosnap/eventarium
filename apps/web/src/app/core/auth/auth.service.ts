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
  /** Ausente en la respuesta del login (`UserSummary`, sin organización
   * resuelta todavía en ese momento); presente en `loadCurrentUser()`
   * (`/users/me`, `CurrentUserResponse`). La organización activa de la
   * sesión — nunca la del host, que ya no determina nada. */
  readonly organization_id?: string;
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

export interface MembresiaPublicable {
  readonly organization_member_id: string;
  readonly role_key: string;
  readonly role_name: string;
}

export interface EstadoDePerfilPublico {
  readonly profile: {
    readonly active: boolean;
    readonly public_slug: string | null;
    readonly source_organization_member_id: string | null;
  };
  readonly eligible_memberships: readonly MembresiaPublicable[];
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

  /**
   * Sesión de impersonación activa: a quién se suplanta y con qué token.
   *
   * El token del administrador **no se toca**: se guarda aparte el de la
   * suplantación, que es el que viaja en las peticiones mientras dura. Así
   * «salir» es simplemente descartar este estado y volver al del admin, y una
   * recarga de página pierde la suplantación (el token vive en memoria, nunca
   * en `localStorage`) — documentado como comportamiento esperado.
   */
  private readonly impersonacion = signal<{
    token: string;
    usuarioId: string;
    nombre: string;
  } | null>(null);

  readonly accessToken = this.token.asReadonly();
  readonly currentUser = this.usuario.asReadonly();
  readonly isAuthenticated = computed(() => this.token() !== null);
  readonly bridgeToken = this.bridge.asReadonly();
  /** Datos de la suplantación en curso, o `null` si no la hay. */
  readonly suplantando = this.impersonacion.asReadonly();

  /**
   * Token que deben usar las peticiones: el de la suplantación si la hay, y si
   * no el de la sesión normal. El interceptor lee `accessToken`, así que este
   * es el punto donde una suplantación toma el relevo.
   */
  readonly tokenEfectivo = computed(() => this.impersonacion()?.token ?? this.token());

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
   * Crea la organización con el token puente de `verifyEmail` cuando existe (alta
   * justo tras verificar el correo, sin sesión normal todavía); si no, con la sesión
   * normal ya iniciada — el backend acepta cualquiera de los dos
   * (`VerifiedUserDep` solo exige un token válido con el correo verificado, no un
   * tipo de token concreto), así que una cuenta que ya tiene una organización puede
   * dar de alta otra sin volver a verificar nada. La cabecera se fija a mano porque
   * el interceptor solo añade automáticamente el token de sesión normal, que en el
   * primer caso (justo tras verificar) todavía vale `null`.
   */
  /**
   * Crea la organización y activa la sesión completa que devuelve la propia
   * respuesta — quien llama puede venir de verificar su correo, sin ninguna
   * sesión normal todavía (fase 4 del plan de organización sin dominio: sin
   * dominio propio, no hay a qué host redirigir).
   */
  async createOrganization(datos: {
    name: string;
    slug: string;
    firstName: string;
    lastName: string;
    turnstileToken: string;
  }): Promise<{ id: string; slug: string; host: string }> {
    const token = this.bridge() ?? this.tokenEfectivo();
    if (!token) {
      throw new Error('No hay una sesión activa.');
    }
    const respuesta = await firstValueFrom(
      this.http.post<{
        id: string;
        slug: string;
        host: string;
        access_token: string;
        expires_in: number;
      }>(
        this.api.url('/organizations'),
        {
          name: datos.name,
          slug: datos.slug,
          first_name: datos.firstName,
          last_name: datos.lastName,
          turnstile_token: datos.turnstileToken,
        },
        { headers: { Authorization: `Bearer ${token}` }, withCredentials: true },
      ),
    );
    this.token.set(respuesta.access_token);
    this.bridge.set(null);
    return respuesta;
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

  async getPublicProfile(): Promise<EstadoDePerfilPublico> {
    return firstValueFrom(
      this.http.get<EstadoDePerfilPublico>(this.api.url('/users/me/public-profile')),
    );
  }

  /** `publicSlug: null` desactiva el perfil. Activarlo exige la membresía de origen. */
  async updatePublicProfile(
    publicSlug: string | null,
    sourceOrganizationMemberId?: string,
  ): Promise<EstadoDePerfilPublico> {
    return firstValueFrom(
      this.http.patch<EstadoDePerfilPublico>(this.api.url('/users/me/public-profile'), {
        public_slug: publicSlug,
        ...(sourceOrganizationMemberId
          ? { source_organization_member_id: sourceOrganizationMemberId }
          : {}),
      }),
    );
  }

  async checkPublicSlug(slug: string): Promise<boolean> {
    const respuesta = await firstValueFrom(
      this.http.get<{ available: boolean }>(this.api.url('/users/me/public-profile/check-slug'), {
        params: { slug },
      }),
    );
    return respuesta.available;
  }

  async listMyOrganizations(): Promise<OrganizacionDeLaPersona[]> {
    return firstValueFrom(
      this.http.get<OrganizacionDeLaPersona[]>(this.api.url('/users/me/organizations')),
    );
  }

  /**
   * Cambia la organización activa sin volver a loguearse.
   *
   * `withCredentials: true` porque el backend necesita la cookie de refresco
   * (rota el refresh token igual que un `/auth/refresh` normal, con la
   * organización de destino) — no basta con el access token de la sesión.
   * Sin dominio por organización, esto sustituye por completo al antiguo
   * enlace a `https://{host}/dashboard`.
   */
  async switchOrganization(organizationId: string): Promise<void> {
    const respuesta = await firstValueFrom(
      this.http.post<RespuestaRefresh>(
        this.api.url('/auth/switch-organization'),
        { organization_id: organizationId },
        { withCredentials: true },
      ),
    );
    this.token.set(respuesta.access_token);
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

  /**
   * Abre una sesión de impersonación sobre otro usuario (solo lectura).
   *
   * Exige la contraseña del propio administrador y un motivo, y la organización
   * en la que se suplanta: el usuario puede pertenecer a varias y el token fija
   * una, así que hay que decir cuál. El token del administrador se conserva
   * intacto para poder salir.
   */
  async impersonar(datos: {
    userId: string;
    organizationId: string;
    reason: string;
    password: string;
    nombreVisible: string;
  }): Promise<void> {
    const respuesta = await firstValueFrom(
      this.http.post<{ access_token: string }>(this.api.url('/admin/impersonate'), {
        user_id: datos.userId,
        organization_id: datos.organizationId,
        reason: datos.reason,
        password: datos.password,
      }),
    );
    this.impersonacion.set({
      token: respuesta.access_token,
      usuarioId: datos.userId,
      nombre: datos.nombreVisible,
    });
  }

  /**
   * Sale de la suplantación.
   *
   * El `POST` de salida se hace **con el token de suplantación** (que es lo que
   * el interceptor pone ahora en la cabecera), y es lo que revoca la sesión en
   * el servidor. Después se descarta el estado local: el administrador vuelve a
   * su propia sesión, que nunca se había tocado.
   */
  async salirDeImpersonacion(): Promise<void> {
    if (this.impersonacion() === null) {
      return;
    }
    try {
      await firstValueFrom(this.http.post(this.api.url('/admin/impersonate/stop'), null));
    } finally {
      this.impersonacion.set(null);
    }
  }

  clear(): void {
    this.token.set(null);
    this.usuario.set(null);
    this.bridge.set(null);
    this.impersonacion.set(null);
  }
}
