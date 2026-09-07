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

  readonly accessToken = this.token.asReadonly();
  readonly currentUser = this.usuario.asReadonly();
  readonly isAuthenticated = computed(() => this.token() !== null);

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
    await firstValueFrom(
      this.http.get<RespuestaGenerica>(this.api.url('/auth/verify-email'), { params: { token } }),
    );
  }

  async resendVerification(email: string, turnstileToken: string): Promise<void> {
    await firstValueFrom(
      this.http.post<RespuestaGenerica>(this.api.url('/auth/resend-verification'), {
        email,
        turnstile_token: turnstileToken,
      }),
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
  }
}
