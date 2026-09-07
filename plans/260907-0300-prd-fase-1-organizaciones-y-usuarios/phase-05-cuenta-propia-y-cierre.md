---
phase: 5
title: "Fase 5: Cuenta propia, recuperación y cierre de fase"
status: done
priority: P1
effort: "3-3.5d"
dependencies: [4]
---

# Fase 5: Cuenta propia, recuperación y cierre de fase

## Overview

Lo que le falta a una persona para gestionar su propia cuenta (perfil, contraseña,
recuperación si la olvida, enlaces sociales, selector de organización), más el cierre
de la fase: documentación al día, checklist de accesibilidad completo y verificación de
extremo a extremo del flujo completo de registro.

## Decisiones validadas — Sesión 2026-09-07

- Una persona **sí puede** pertenecer a varias organizaciones. Esta fase incluye el
  selector de organización en el panel.
- La recuperación de contraseña **entra en esta fase**: reutiliza el mecanismo de token
  de un solo uso de la fase 1, con propósito propio (`password_reset`) y las mismas
  protecciones anti-enumeración.

## Hallazgos aplicados en esta fase

### Red-team (seguridad y supuestos no verificados)

| # | Hallazgo | Corrección |
|---|---|---|
| High | Cambio de correo sin exigir la contraseña actual, y sin token de propósito distinto al de verificación de alta (riesgo de confusión de tokens) | Cambio de correo exige la contraseña actual; token con propósito `email_change`, distinto de `email_verify` y `password_reset` |
| High | Cambio de contraseña no revocaba las demás familias de refresh token | Cambiar la contraseña revoca todas las familias de refresh token del usuario excepto la de la sesión actual; lo mismo al confirmar un cambio de correo o al completar una recuperación |
| High | `GET /users/me/organizations` no se puede resolver con una consulta RLS normal: el contexto de organización lo fija el host, no el usuario | Función `SECURITY DEFINER` de alcance mínimo `app_user_organizations(p_user_id)`, con `REVOKE`/`GRANT` como las de la fase 2, y test explícito de que un usuario no puede listar organizaciones ajenas |
| Low | Sin flujo de recuperación de contraseña en el plan original | Se añade en esta fase |
| Low | `users/router.py` estaba etiquetado como "Create" cuando ya existe (`GET /users/me`) | Corregido a "Modify" |

### Predict/debate (5 personas, sobre el plan ya endurecido)

| # | Quién | Hallazgo | Corrección |
|---|---|---|---|
| Importante | Seguridad | `forgot-password` solo tenía límite por IP, sin Turnstile: mismo riesgo de *email bombing* que `resend-verification` en la fase 1 | Turnstile obligatorio en `forgot-password`, reutilizando `core/turnstile.py` |
| Importante | Seguridad | `change-email` no avisaba a la dirección **antigua**: con una sesión robada, el dueño legítimo no recibía ninguna señal hasta que ya era tarde | Se envía un aviso informativo (no un token, no accionable) al correo actual en el momento de **solicitar** el cambio, antes de que se confirme |
| Importante | Seguridad | Los miembros invitados (fase 4) se crean con `password_hash=null` y nunca pasan por `/auth/register`, así que su `email_verified_at` quedaría `null` para siempre — contradiciendo el Goal 1 del plan («cualquiera... crea su organización») | Consumir un token `password_reset` también fija `email_verified_at` si estaba nulo: recibir y usar el enlace en esa bandeja prueba la propiedad del correo igual que `email_verify` |
| Opcional | Accesibilidad | El selector de organización cambia de subdominio (sale de la SPA); si se implementa como manejador de clic en vez de enlace real, la tecnología de asistencia no lo anuncia como navegación | El selector usa elementos `<a href="https://{slug}.{DOMINIO_BASE}/admin">` reales por organización, no un manejador de clic que cambia `location.href` |
| Importante | Accesibilidad | Sin requisito de cómo se comunica un token de recuperación caducado (igual que el de verificación en la fase 1) | Misma pantalla y patrón que `verify-email-page.ts`: `aria-live="assertive"`, explicación, botón directo para solicitar uno nuevo |

## Requirements

- Functional:
  - `PATCH /users/me`: nombre, locale. No incluye correo (tiene su propio flujo).
  - `POST /users/me/change-email` (correo nuevo, contraseña actual): 409 genérico si el
    correo ya está en uso (sin filtrar si es de otra cuenta verificada o no, para no
    repetir el problema de enumeración de la fase 1); envía un **aviso informativo** al
    correo actual (no un token, no revierte nada por sí mismo) y envía verificación al
    correo nuevo con token de propósito `email_change`; el cambio **no se aplica**
    hasta confirmarlo. Confirmar revoca las demás sesiones.
  - `POST /users/me/change-password` (actual, nueva): exige la actual; revoca las demás
    familias de refresh token.
  - `POST /api/v1/auth/forgot-password` (correo, token de Turnstile): respuesta
    anti-enumeración idéntica exista o no la cuenta; token de propósito
    `password_reset`, un solo uso.
  - `POST /api/v1/auth/reset-password` (token, nueva contraseña): consume el token,
    aplica la contraseña (con la misma validación de la fase 1), **fija
    `email_verified_at` si estaba nulo** (cubre el caso de miembros invitados que nunca
    pasaron por el registro), revoca todas las familias de refresh token.
  - CRUD de `user_social_links` bajo `/users/me/social-links` (el modelo existe desde la
    fase 0.3.0, sin router hasta ahora).
  - `GET /users/me/organizations`: lista las organizaciones del usuario vía
    `app_user_organizations`. Selector en la cabecera del panel, con enlaces `<a href>`
    reales por organización, visible cuando hay más de una.
- Non-functional: todos los flujos de correo/contraseña comparten el módulo de
  verificación de la fase 1, diferenciados por propósito de token, nunca por
  reutilizar el mismo token entre flujos distintos; Turnstile fail-closed en
  `forgot-password`, igual que en el registro.

## Architecture

- `apps/api/app/modules/users/router.py` (**modificar**, ya existe con `GET /users/me`):
  se amplía con `PATCH`, `change-email`, `change-password`, CRUD de enlaces sociales y
  `GET /organizations`.
- `apps/api/app/modules/auth/router.py`: se amplía con `forgot-password` y
  `reset-password`, ambos con Turnstile.
- `apps/api/app/modules/auth/verification.py` (de la fase 1): se generaliza para
  aceptar un propósito (`email_verify`, `email_change`, `password_reset`) en la clave
  de Redis, de modo que un token de un flujo nunca se acepte en otro. `reset-password`
  fija `email_verified_at` como efecto secundario documentado si estaba nulo.
- `app_user_organizations(p_user_id uuid) RETURNS TABLE (...)`: función `SECURITY
  DEFINER` de alcance mínimo, con `REVOKE ALL ... GRANT EXECUTE TO app_user`. Solo
  devuelve las organizaciones donde `user_id` coincide con el usuario del token
  autenticado — el parámetro no permite consultar por un `p_user_id` arbitrario salvo
  que coincida con el propio.
- Revocar sesiones: reutiliza el mecanismo de familias de refresh token de la fase 0
  (`_revoke_family` en `modules/auth/service.py`), extendido a "revocar todas las
  familias de un usuario" (hoy solo revoca una familia conocida).
- Aviso de cambio de correo: reutiliza `EmailProvider` de la fase 1 con una plantilla
  nueva, sin token ni enlace accionable — solo informa.
- `forgot-password-page.ts` / `reset-password-page.ts` (páginas públicas, CSR, mismo
  precedente que registro): la pantalla de token caducado reutiliza el patrón de
  `verify-email-page.ts` (`aria-live="assertive"`, botón directo de reenvío).

## Related Code Files

- Modify: `apps/api/app/modules/users/router.py`, `schemas.py` (el router ya existe)
- Modify: `apps/api/app/modules/auth/router.py`, `service.py`, `schemas.py`
- Modify: `apps/api/app/modules/auth/verification.py` (propósito de token)
- Create: `apps/api/alembic/versions/` (nueva migración: `app_user_organizations`)
- Create: `apps/api/tests/modules/test_users_account.py`
- Create: `apps/api/tests/test_password_reset.py`
- Create: `apps/web/src/app/features/admin/account/account-page.ts`
- Create: `apps/web/src/app/features/public/forgot-password/forgot-password-page.ts`
- Create: `apps/web/src/app/features/public/forgot-password/reset-password-page.ts`
- Modify: `apps/web/src/app/layouts/admin/admin-shell.ts` (selector de organización con
  `<a href>` reales)

## Implementation Steps

1. Generalizar `verification.py` con propósito de token; migrar los usos existentes de
   la fase 1 (`email_verify`) sin romperlos.
2. Extender la revocación de refresh tokens a "todas las familias del usuario".
3. `change-email`: exige contraseña, valida disponibilidad con 409 genérico, envía
   aviso informativo al correo actual, token `email_change` al nuevo, no aplica hasta
   confirmar, revoca sesiones al confirmar.
4. `change-password`: exige la actual, revoca sesiones.
5. `forgot-password` (con Turnstile) / `reset-password`: anti-enumeración, token
   `password_reset`, fija `email_verified_at` si estaba nulo, revoca sesiones al
   completar.
6. CRUD de `user_social_links`.
7. Migración y función `app_user_organizations`; `GET /users/me/organizations`.
8. `account-page.ts`, páginas públicas de recuperación (con Turnstile y pantalla de
   token caducado accesible), selector de organización en `admin-shell.ts` con enlaces
   reales.
9. Tests: cada flujo de esta fase por separado, más un test cruzado que confirme que un
   token de un propósito no verifica en otro endpoint (p. ej. un token de
   `password_reset` no sirve para `verify-email`); `app_user_organizations` no permite
   listar organizaciones ajenas; un miembro invitado sin `email_verified_at` que
   completa `reset-password` queda verificado y puede crear organización después;
   `forgot-password` exige Turnstile y responde igual exista o no la cuenta.
10. **Cierre de fase**: recorrer el checklist de `Success Criteria` del `plan.md`
    completo, no solo de esta fase de trabajo; actualizar `docs/arquitectura.md`
    (las tres funciones `SECURITY DEFINER` nuevas del plan, el servicio `scheduler`) y
    `docs/modelo-de-datos.md` (`email_verified_at`, el índice parcial); completar
    `docs/accesibilidad.md`.
11. Verificación de extremo a extremo: una persona sin cuenta llega a registrarse,
    verifica, crea su organización, la personaliza, invita a alguien, esa persona
    recupera su contraseña (en vez de tener una desde el alta) para completar su
    perfil y queda verificada por ese camino — todo sin intervención manual en base de
    datos.

## Success Criteria

- [x] Cambiar el correo exige la contraseña actual, avisa al correo antiguo, y
      verificar el nuevo antes de aplicarlo; confirmar revoca las demás sesiones
- [x] Cambiar la contraseña exige la actual y revoca las demás sesiones
- [x] Recuperar una contraseña olvidada exige Turnstile, funciona sin exponer si el
      correo existe, y revoca las sesiones al completarse
- [x] Un miembro invitado sin correo verificado que completa la recuperación de
      contraseña queda verificado y puede crear su propia organización después
- [x] Un token de un propósito no es válido en el endpoint de otro propósito
- [x] La pantalla de token caducado (verificación o recuperación) anuncia el error con
      `aria-live` y ofrece un botón directo para solicitar uno nuevo
- [x] Los enlaces sociales se gestionan desde el panel
- [x] `app_user_organizations` no devuelve organizaciones ajenas (test explícito)
- [x] El selector de organización usa enlaces `<a href>` reales y cambia de
      organización navegando al subdominio correcto
- [x] El flujo de extremo a extremo del plan completo se ha ejecutado una vez,
      incluida la recuperación de contraseña, y documentado — no solo declarado
- [x] `docs/` refleja el estado real del código
- [x] Cero violaciones de axe; checklist WCAG de la fase 1 del PRD completo

## Risk Assessment

- Permitir cambiar el correo o la contraseña sin revocar sesiones dejaría una sesión ya
  robada viva hasta que expire → revocación explícita en los tres flujos (cambio de
  correo, cambio de contraseña, recuperación), cubierta por tests.
- Reutilizar el mismo token entre flujos de correo, cambio y recuperación → propósito
  incluido en la clave de Redis; test cruzado que confirma que no son intercambiables.
- Un cambio de correo iniciado con una sesión robada pasaría inadvertido → aviso
  informativo al correo antiguo en el momento de solicitarlo, no solo al confirmarlo.
- Un miembro invitado quedaría atrapado sin poder verificar nunca su correo por el
  camino normal de registro → `reset-password` verifica como efecto secundario
  documentado.
- Cerrar la fase sin la verificación de extremo a extremo repetiría el patrón de la
  fase 0, donde varios fallos reales pasaban con CI en verde → paso explícito de
  verificación manual antes de dar la fase por cerrada.
