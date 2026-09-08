# Fase 3 — Legal, cookies y consentimientos: informe de implementación

Fecha: 2026-09-08. Plan: `260908-1610-prd-fase-5-patrocinadores-legal-superadmin`.

## Qué se creó

### Backend (`apps/api`)

- `app/modules/legal/templates.py`: plantillas de texto/Markdown restringido
  de las cuatro páginas legales, f-strings de Python (mismo patrón que
  `app/core/tasks.py`, sin motor de plantillas nuevo), rellenadas con
  `legal_name`/`contact_email`/`legal_address`/`tax_id` de la organización.
  La plantilla de `/legal/cookies` declara explícitamente Cloudflare
  Turnstile como script necesario con base legal de interés legítimo.
- `app/modules/legal/schemas.py`: `LegalPageResponse`, `LegalPagesAdminResponse`
  (con `is_custom` por página), `LegalPagesUpdate` (mismo patrón
  `exclude_unset` que `OrganizationUpdate`: campo ausente = no tocar, campo
  `null` = restaurar plantilla), `CookieConsentCreate` (categorías con
  `Literal["necessary", "analytics", "marketing"]`).
- `app/modules/legal/router.py`: tres routers.
  - `router_admin` (`/organizations/me/legal-pages`, GET/PATCH,
    `organizations:read`/`write`).
  - `router_public` (`/public/legal/{aviso-legal,privacidad,cookies,
    condiciones-de-inscripcion}`, resuelto por host, `limit_per_ip`).
  - `router_cookie_consent` (`POST /public/cookie-consent`, sin autenticar,
    `limit_per_ip`). El insert usa `sqlalchemy.insert()` de Core en vez de
    `session.add()`: el ORM añade `RETURNING` para leer `created_at`
    (`server_default`), y `app_user` solo tiene `GRANT INSERT` sobre
    `cookie_consents` (fase 1) — `INSERT ... RETURNING` exige además
    `SELECT`, que el rol no tiene a propósito. Descubierto al ejecutar los
    tests (fallo real `InsufficientPrivilegeError`, no una suposición).
- `app/core/ratelimit.py`: `LEGAL_PAGES_POR_IP` (= `PUBLICO_POR_IP`),
  `COOKIE_CONSENT_POR_IP` (30/min).
- `app/main.py`: registro de los tres routers nuevos.
- `apps/api/openapi.json` regenerado (`uv run python -m app.cli export-openapi`).
- Tests: `tests/test_legal_pages_y_cookie_consent.py` (10 tests): plantilla
  por defecto con datos reales, declaración de Turnstile en `/legal/cookies`,
  host desconocido → 404, editar/restaurar página, `<script>` guardado no se
  ejecuta (verificado a nivel de respuesta JSON), 403 sin permiso,
  `cookie_consents` sin datos personales, `necessary` forzado si falta,
  categoría inválida → 422, aislamiento entre organizaciones.

### Frontend (`apps/web`)

- Dependencias añadidas: `marked`, `dompurify` (dependencies). `jsdom` ya
  existía como devDependency (usado solo por Vitest, no en el bundle SSR —
  ver decisión de diseño más abajo).
- `shared/legal/sanitize-markdown.ts` + `.spec.ts`: `marked` → `DOMPurify`
  con lista blanca explícita (`p, strong, em, b, i, ul, ol, li, a, br`,
  atributo `href` únicamente). 6 tests unitarios, incluido `<script>`,
  `onclick`, `<iframe>` y encabezados Markdown (fuera de la lista blanca a
  propósito).
- `core/cookies/`: `cookie-category.ts`, `dummy-analytics.service.ts` (script
  de ejemplo, `public/assets/dummy-analytics.js`), `cookie-consent.service.ts`
  (estado con signals, persistencia en `localStorage`, `POST
  /public/cookie-consent`, activa el script de ejemplo solo si `analytics`
  está aceptada).
- `shared/cookies/cookie-banner.ts` + `.spec.ts` (7 tests, incluido axe):
  banner con "Aceptar todo"/"Rechazar todo"/"Personalizar", misma variante de
  botón (`secundario`) en los tres — verificado comparando clases CSS, no
  solo visualmente. Gestión de foco: al aparecer, foco al panel; al decidir,
  foco de vuelta al elemento anterior. Sin trampa de foco (no es modal).
- `features/public/legal/legal-page.ts` + `.spec.ts` (3 tests): página
  pública SSR (patrón `TransferState`/`serverForwardHeaders` de
  `event-page.ts`). Contenido mostrado primero como texto plano interpolado
  (SSR y pre-hidratación), sustituido por HTML saneado solo en el navegador
  vía `afterNextRender` (nunca corre en el servidor). Test explícito: un
  `<script>alert(1)</script>` guardado no aparece como etiqueta real en el
  DOM en ningún momento.
- `features/admin/legal/legal-pages-page.ts` + `.spec.ts` (3 tests, incluido
  axe): editor con un textarea por página y botón "restaurar plantilla por
  defecto" (deshabilitado si la página no está editada; envía `null`
  explícito al restaurar).
- Rutas nuevas: 4 públicas (`/legal/aviso-legal`, `/legal/privacidad`,
  `/legal/cookies`, `/legal/condiciones-de-inscripcion`) y una de panel
  (`/admin/legal`, enlazada en `admin-shell.ts`).
- `layouts/public/public-shell.ts`: `<app-cookie-banner>` + enlaces a las
  cuatro páginas legales en el footer, visibles en toda página pública.
  `shells.spec.ts` actualizado con `provideHttpClient`/`provideHttpClientTesting`
  (necesario porque `PublicShell` ahora integra `CookieBanner`, que inyecta
  `HttpClient` vía `CookieConsentService`).
- i18n: secciones `cookies.banner`, `legal`, `publico.enlacesLegales`,
  `admin.legal`/`admin.legalNav` añadidas a `es-ES.json` con un script
  Python (`json.load`/`dump`) para no romper el JSON a mano; el diff también
  corrige, como efecto colateral verificado, un artefacto de la
  herramienta de diff en la comparación de un bloque ya existente (`git
  diff` mostró líneas movidas, no perdidas — comprobado con `python3 -c
  "json.load(...)"` antes y después).

## Decisión Orejime vs. Klaro

**No se integró ninguna de las dos librerías; el banner es un componente
propio.** Comprobación de accesibilidad (documentada en
`docs/accesibilidad.md`): Orejime es un fork de Klaro creado explícitamente
para corregir problemas de accesibilidad de Klaro (gestión de foco,
navegación por teclado). En vez de instalar cualquiera de las dos y auditar
una caja negra de terceros, el banner (`CookieBanner`) se construyó con los
mismos bloques que el resto del panel (`app-button`, signals,
`afterNextRender`), lo que permite verificar directamente cada criterio WCOG
citado (foco, sin trampa, mismo peso visual) con tests propios, en vez de
depender de que una librería externa los cumpla. Justificación completa y
checklist en `docs/accesibilidad.md`, sección "Fase 5 del PRD, fase 3".

## Desviación del plan: render de Markdown en SSR

El plan/validación de sesión fijó `marked` + `DOMPurify` como mecanismo,
pero no especificó cómo convive `DOMPurify` (necesita un DOM de navegador
real) con el SSR real que exige el requisito no funcional. Decisión tomada
en esta fase, no prevista explícitamente: el contenido se muestra primero
como **texto plano interpolado por Angular** (SSR y antes de hidratar,
siempre escapado) y solo se sustituye por HTML saneado en el navegador
(`afterNextRender`, que nunca corre en el servidor). Alternativa descartada:
usar `jsdom` en el bundle de SSR (ya está como devDependency) para sanear
también en servidor — se descartó por added complejidad/tamaño de bundle
del servidor sin necesidad real, ya que el texto plano ya es 100% seguro y
la mejora progresiva a Markdown solo aporta formato visual, no contenido
distinto.

## Resultado de tests

- Backend: suite completa `apps/api` en verde — **349 tests** (10 nuevos de
  esta fase + 339 existentes, sin romper ninguno). `ruff check`, `ruff
  format --check` y `mypy app`: sin errores.
- Frontend: suite completa `apps/web` en verde — **158 tests** (19 nuevos:
  6 de `sanitize-markdown`, 7 de `cookie-banner`, 3 de `legal-page`, 3 de
  `legal-pages-page`, más `shells.spec.ts` sin cambio de conteo). `ng lint`
  y `ng build` (prod, SSR) sin errores. `format:check`: limpio en todos los
  ficheros de esta fase (5 ficheros con avisos preexistentes de la fase 2,
  fuera de mi ámbito, no tocados).
- Axe: cero violaciones en banner (con y sin personalización), las cuatro
  páginas legales con contenido renderizado, y el editor del panel.
- Verificación manual contra la API de desarrollo real (Postgres/Redis
  reales, sin mocks): `GET /public/legal/aviso-legal` y `/cookies` con datos
  reales de la organización `iawic` (confirmado el texto de Turnstile);
  `POST /public/cookie-consent` con categoría válida → `204`; con categoría
  inválida → `422` con el mensaje de Pydantic esperado.

### Verificación no realizada (con matiz explícito en el phase file)

No se ejecutó un test de navegador real (Playwright no está instalado en
este proyecto) que confirme visualmente que Turnstile sigue cargando y el
formulario de inscripción se envía tras "Rechazar todo". Se verificó en su
lugar: (a) aislamiento arquitectónico — `CookieConsentService` no
referencia Turnstile en ningún punto (test explícito), (b)
`turnstile-widget.ts` solo depende de `environment.turnstileEnabled`, sin
ninguna dependencia de consentimiento, y (c) `TURNSTILE_ENABLED` está
desactivado en desarrollo (igual que en fases anteriores del PRD), así que
tampoco había forma de probarlo con una clave real en este entorno. Marcado
en el criterio de éxito correspondiente con el matiz explícito, no oculto.

## Ficheros modificados/creados (rutas absolutas)

Backend:
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/api/app/modules/legal/templates.py`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/api/app/modules/legal/schemas.py`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/api/app/modules/legal/router.py`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/api/app/core/ratelimit.py`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/api/app/main.py`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/api/tests/test_legal_pages_y_cookie_consent.py`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/api/openapi.json`

Frontend:
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/shared/legal/sanitize-markdown.ts` (+ `.spec.ts`)
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/core/cookies/cookie-category.ts`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/core/cookies/dummy-analytics.service.ts`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/core/cookies/cookie-consent.service.ts`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/shared/cookies/cookie-banner.ts` (+ `.spec.ts`)
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/features/public/legal/legal-page.ts` (+ `.spec.ts`)
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/features/admin/legal/legal-pages-page.ts` (+ `.spec.ts`)
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/public/assets/dummy-analytics.js`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/public/assets/i18n/es-ES.json`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/app.routes.ts`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/layouts/public/public-shell.ts`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/layouts/admin/admin-shell.ts`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/layouts/shells.spec.ts`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/package.json` / `pnpm-lock.yaml`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/apps/web/src/app/core/api/generated/**` (regenerado)

Docs:
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/docs/modelo-de-datos.md`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/docs/accesibilidad.md`
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/docs/arquitectura.md`

Plan:
- `/Volumes/EVO990/Proyectos/Personales/Humanitek - IA Week/ia-week/plans/260908-1610-prd-fase-5-patrocinadores-legal-superadmin/phase-03-legal-cookies-y-consentimientos.md`
  (status → `completed`, Success Criteria marcados)

## Aviso operativo (proceso)

Durante la verificación manual arranqué la API de desarrollo con
`./infra/scripts/dev.sh api` y la detuve con `./infra/scripts/dev.sh stop`
(mecanismo propio del repo). Ese `stop` también cerró un proceso `ng serve`
en el puerto 4200 que yo no había arrancado en esta sesión — probablemente
de otra sesión de desarrollo activa. Aviso explícito por si esa sesión
necesita reiniciar su servidor de Angular.

## No tocado (fuera de ámbito de esta fase)

Patrocinadores (fase 2, ya cerrada), superadmin/auditoría/RGPD y
revalidación de backups (fases 4-5). No se modificó ningún fichero de
`apps/api/app/modules/sponsors/` ni de `apps/api/app/modules/admin/`.

Status: DONE_WITH_CONCERNS
Summary: Backend y frontend de la fase 3 completos, con 349 tests de API y
158 de web en verde, axe limpio y el test explícito de XSS pasando en
backend y frontend. El único matiz es que la comprobación de que Turnstile
sigue funcionando tras rechazar cookies se hizo por aislamiento
arquitectónico y no con un navegador real, porque Playwright no está
instalado y Turnstile está desactivado en este entorno de desarrollo.
Concerns/Blockers: (1) Verificar en un entorno con `TURNSTILE_ENABLED=true`
y clave real, antes de producción, que el formulario de inscripción se
envía tras rechazar cookies (recomiendo hacerlo junto con la verificación
manual de Turnstile con lector de pantalla que ya quedó pendiente de la
fase 3 del PRD). (2) `./infra/scripts/dev.sh stop` cerró un `ng serve` en
:4200 que no arranqué yo — comprobar si otra sesión de desarrollo lo
necesitaba.
