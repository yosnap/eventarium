---
phase: 4
title: "Fase 4: Frontend Angular y theming"
status: completed
priority: P1
effort: "2-3d"
dependencies: [2, 3]
---

# Fase 4: Frontend Angular y theming

## Overview
App Angular única (público + admin) con arquitectura por features, cliente API tipado desde OpenAPI, autenticación con refresh en cookie `HttpOnly`, i18n con Transloco (`es-ES`), accesibilidad WCAG 2.1 AA verificada con axe y checklist manual, y el sistema de theming multi-organización: design tokens como CSS custom properties sobrescritas en runtime con el branding de la API, más un registro de plantillas de layout público intercambiables. Depende de la fase 3 (contrato real de branding, seed y login).

## Requirements
- Functional: rutas públicas (`/`, placeholder de evento) con SSR y rutas admin (`/admin/login`, `/admin`, `/admin/branding` solo lectura) con guard; `ThemingService` carga `/api/v1/tenant/branding` en el arranque y aplica colores, fuentes, logo y `template_key`; `TemplateRegistry` con `classic` y `minimal`; `AuthService` con login/refresh/logout; interceptores de auth y errores; SSR reenvía el host original a la API; textos externalizados.
- Non-functional: **Angular 21 LTS** (validación #2), standalone, <!-- Updated: Validation Session 1 - Angular 21 --> Signals, `OnPush`, zone.js por defecto; Tailwind v4 con `@theme` sobre CSS vars; sin Angular Material; Transloco; Vitest; ESLint (angular-eslint + reglas a11y) + Prettier; `axe-core` en tests con **0 violaciones de cualquier impacto**; checklist manual WCAG 2.1 AA por pantalla (`docs/accesibilidad.md`); tipos generados con `ng-openapi-gen` desde `openapi.json` versionado; ficheros ≤ 300 líneas; SSR solo en rutas públicas.

## Architecture
```
apps/web/src/
├── styles/{tokens,tailwind}.css
└── app/
    ├── core/
    │   ├── api/          # cliente generado + ApiClient base, interceptores
    │   ├── auth/         # AuthService (signals), authGuard, refresh
    │   ├── theming/      # Branding, ThemingService, applyTokens(), TemplateRegistry
    │   ├── tenant/       # TenantService
    │   └── i18n/         # Transloco
    ├── layouts/{public,admin}/
    ├── features/{public/home, admin/{login,dashboard,branding}}
    └── shared/ui/        # button, input, card, alert
```
- **Tokens**: `applyTokens(branding)` escribe variables en `document.documentElement` (solo en navegador); en SSR se inyecta un `<style>` con las variables en el HTML servido para evitar flash.
- **Carga de branding (hallazgo #12)**: `provideAppInitializer` sin timeout silencioso: si la API falla, el SSR responde 503 con página de error mínima y lo registra; en navegador, error visible en consola y pantalla de "sitio no disponible". Nunca se pinta el tema por defecto como si fuera el de la organización. En servidor, la petición a la API incluye `X-Forwarded-Host` = host original de la petición entrante (que la API acepta solo desde el proxy de confianza) y usa `TransferState` para no repetir la llamada al hidratar.
- **Auth (hallazgo #9)**: access token en memoria (signal); refresh en cookie `HttpOnly` gestionada por el backend (`withCredentials: true`); nada en `localStorage`; interceptor reintenta una vez tras 401 llamando a `/auth/refresh`; en SSR no se ejecuta lógica de auth (admin es CSR).
- **Plantillas**: `TemplateRegistry = Map<key, () => Promise<Type<unknown>>>` con carga perezosa; `NgComponentOutlet` en `public-shell`.
- **Accesibilidad (hallazgo #14)**: skip-link, landmarks, foco visible, contraste verificado (la paleta por defecto y un validador de contraste sobre el branding recibido que avisa en admin si no cumple 4.5:1); tests axe por componente y por shell; checklist manual WCAG AA (teclado, lector de pantalla, zoom 200 %, reduced motion) documentado y completado antes de cerrar la fase.

## Related Code Files
- Create: `apps/web/` (`ng new web --standalone --style=css --ssr`), `apps/web/eslint.config.js`, `.prettierrc`
- Create: `apps/web/src/styles/{tokens,tailwind}.css`
- Create: `apps/web/src/app/core/{api,auth,theming,tenant,i18n}/*.ts`
- Create: `apps/web/src/app/layouts/{public,admin}/**/*.ts`, `features/{public,admin}/**/*.ts`, `shared/ui/*.ts`
- Create: `apps/web/src/assets/i18n/es-ES.json`
- Create: `apps/web/src/app/app.routes.ts`, `app.config.ts`, `app.config.server.ts`, `server.ts` (reenvío de `X-Forwarded-Host`)
- Create: `apps/web/src/environments/environment{,.development}.ts`
- Create: `apps/web/Dockerfile` (build SSR + node runtime; sin secretos)
- Create: `docs/accesibilidad.md` (checklist WCAG 2.1 AA por pantalla)
- Modify: `Makefile` (`web`, `api-types` = generar desde `apps/api/openapi.json` exportado por `make api-openapi`)

## Implementation Steps
1. `pnpm dlx @angular/cli@21 new web --standalone --style=css --ssr` en `apps/`; añadir Tailwind v4, angular-eslint, Prettier, Transloco, Vitest, `axe-core`/`vitest-axe`, `ng-openapi-gen`; fijar versiones.
2. `tokens.css` + `tailwind.css` con `@theme`; verificar que `bg-primary` responde al cambio de variable.
3. `make api-openapi` (backend exporta `apps/api/openapi.json`, versionado) y `make api-types` (genera desde ese fichero, mismo comando en local y CI).
4. `core/theming` con `TransferState`, inyección de `<style>` en SSR y manejo de error visible.
5. `server.ts`: propagar `X-Forwarded-Host` y `X-Forwarded-Proto` a las llamadas a la API.
6. `core/auth` con cookie `HttpOnly` (`withCredentials`), sin `localStorage`.
7. `core/i18n`: Transloco `es-ES`.
8. Layouts, features placeholder, `shared/ui` con tests axe.
9. Rutas: públicas SSR; `admin` con `renderMode: Client`.
10. Validador de contraste del branding en `admin/branding` (solo lectura, muestra aviso).
11. Tests: `applyTokens`; `TemplateRegistry`; `authGuard`; shells con branding mock sin violaciones axe; SSR con host simulado obtiene el branding correcto (test de integración contra API con seed).
12. Completar `docs/accesibilidad.md` para las pantallas de esta fase.
13. `Dockerfile` y target `make web`.

## Success Criteria
- [x] Cambiar `colors.primary` en BD y recargar cambia el color sin rebuild; sin flash de tema por defecto en SSR
- [x] `template_key` `classic` ↔ `minimal` cambia el layout público
- [x] `/admin` sin sesión → `/admin/login`; login del seed → dashboard; refresh funciona solo con cookie, `localStorage` vacío
- [x] SSR tras Caddy con dos hosts distintos devuelve el branding de cada organización
- [x] Logo servido desde `S3_PUBLIC_BASE_URL`
- [x] `ng lint`, `ng test`, `ng build` en verde; **0 violaciones axe** en shells y `shared/ui`; checklist WCAG AA completado
- [x] Todos los textos visibles vienen de `es-ES.json`

## Risk Assessment
- Tailwind v4 con Angular CLI: integración PostCSS varía por versión → consultar docs vigentes al implementar; fallback a Tailwind v3.
- Cookie `HttpOnly` requiere mismo host → en desarrollo se accede siempre por `http://localhost:8080` (Caddy de la fase 1), nunca por `:4200` directo; documentar en `docs/desarrollo.md`.
- Deriva de tipos API ↔ front → `openapi.json` versionado y `git diff --exit-code` en CI tras regenerar.
