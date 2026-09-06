# Investigación técnica: stack plataforma de eventos open source multi-tenant

Fecha: 2026-09-06. Alcance: FastAPI + Angular + PostgreSQL + MinIO + Stripe + Turnstile, referencia Luma.com, self-hosted multi-tenant con branding personalizable por organizador.

---

## 1. Backend: FastAPI

### 1.1 Versión y estado
- FastAPI publica releases semanales/quincenales; a fecha de hoy la serie estable ronda 0.13x–0.14x (ej. 0.137.0 el 14 jun 2026, 0.141.1 en jul 2026), requiere Python ≥3.10. No fijar una versión exacta "final": pinnear con rango `>=0.115,<0.15` y actualizar en CI. Fuente: [Release Notes](https://fastapi.tiangolo.com/release-notes/), [Releasebot](https://releasebot.io/updates/tiangolo/fastapi).
- **Recomendación**: usar `uv` + lockfile, actualizar mensualmente, no seguir "latest" en producción sin CI verde.

### 1.2 Estructura para apps grandes modulares
Patrón consolidado en 2026 (Medium, dev.to, pratikpathak.com — múltiples fuentes coinciden): estructura por **dominio/módulo** (no por tipo de archivo) para monolitos grandes:
```
app/
  core/          # config, seguridad, excepciones, logging
  api/           # routers (capa fina, valida y delega)
  <dominio>/     # events/, tickets/, orgs/, payments/... cada uno con:
    router.py, service.py, repository.py, models.py, schemas.py
  db/            # engine, sesión, migrations/ (alembic)
  workers/       # tareas async (taskiq/arq)
  tests/
```
Capas: router (IO/validación) → service (lógica de negocio) → repository (acceso a datos) → models (ORM). Inyección de dependencias de FastAPI para desacoplar. Fuentes: [Medium - production FastAPI structure](https://medium.com/@devsumitg/the-perfect-structure-for-a-large-production-ready-fastapi-app-78c55271d15c), [dev.to guide 2026](https://dev.to/thesius_code_7a136ae718b7/production-ready-fastapi-project-structure-2026-guide-b1g), [pratikpathak.com](https://pratikpathak.com/fastapi-best-practices-building-production-ready-python-apis-in-2026/).
Para un proyecto **multi-tenant open source**, conviene un módulo `tenants/` (u `organizations/`) transversal cuyo `organization_id` se inyecta vía dependencia en cada request (ver §3).

### 1.3 SQLAlchemy 2 async + Alembic
- Motor async obligatorio: `create_async_engine` + `asyncpg` (driver recomendado para PostgreSQL, evita bloquear el event loop). Con drivers síncronos, 100 usuarios concurrentes = 100 queries en serie. Fuente: [testdriven.io](https://testdriven.io/blog/fastapi-sqlmodel/), [oneuptime.com](https://oneuptime.com/blog/post/2026-01-27-sqlalchemy-fastapi/view).
- Usar `Mapped[]`/`mapped_column` (tipado SQLAlchemy 2.0), patrón repositorio + inyección de sesión por request (`Depends`).
- Alembic: migraciones idempotentes, probadas en staging; para zero-downtime: añadir columnas nullable → backfill → constraint. No migrar en horas pico. Fuente: [towardsai.net guide](https://pub.towardsai.net/building-production-ready-apis-with-fastapi-sqlalchemy-and-alembic-a-complete-guide-a4656b7e700c).
- Pool de conexiones obligatorio (asyncpg + `pool_size`/`max_overflow` ajustados a réplicas de Postgres).
- **Riesgo**: mezclar RLS (§3) con pool de conexiones reutilizadas exige `SET LOCAL app.tenant_id` por transacción, no por conexión — fácil de hacer mal si no se centraliza en el middleware/dependencia de sesión.

### 1.4 Pydantic v2
Ya estándar en FastAPI moderno (validación en Rust vía `pydantic-core`, mucho más rápido que v1). No hay alternativa razonable a día de hoy; usar `model_config`, `computed_field`, y esquemas separados de los modelos ORM (DTO pattern) para no acoplar API a schema de BD.

### 1.5 Auth JWT: PyJWT vs python-jose
- **python-jose está prácticamente sin mantenimiento activo** (histórico de CVEs de parsing de algoritmos); **PyJWT** es la opción más mantenida, con CVEs recientes ya parcheadas: validación de `crit` header (fix en 2.12.0), confusión de algoritmo HMAC/JWK (fix en 2.13.0), fallo en `PyJWKClient` con URLs `file://`. **Recomendación: PyJWT ≥2.13.0**, fijar explícitamente `algorithms=["HS256"]` o `["RS256"]` al decodificar (nunca aceptar `alg` del token). Fuentes: [Snyk CVE-2026-48526](https://security.snyk.io/vuln/SNYK-PYTHON-PYJWT-17053408), [iamdevbox.com comparación](https://www.iamdevbox.com/posts/pyjwt-vs-python-jose-choosing-the-right-python-jwt-library/).
- Hashing de contraseñas: **Argon2** (vía `argon2-cffi`, ganador del Password Hashing Competition, recomendado sobre bcrypt para nuevos proyectos) + `passlib` opcional como wrapper (passlib tiene poco mantenimiento reciente, verificar antes de adoptar).

### 1.6 Tareas en segundo plano
Comparativa (múltiples fuentes coinciden, sept 2026):
| Opción | Cuándo usar | Riesgo |
|---|---|---|
| `BackgroundTasks` (nativo) | Tareas cortas, idempotentes, tolerantes a pérdida (ej. log de auditoría) | No sobrevive a reinicio del proceso, no reintenta |
| **Taskiq** | Nativo async, DI similar a FastAPI, brokers Redis/NATS/RabbitMQ/Postgres, soporta cron | Más joven que Celery, comunidad menor, breaking changes posibles entre minors |
| **arq** | Cola async simple sobre Redis, ligera | Menos features que Celery (sin routing avanzado) |
| Celery | Pipelines pesados, 10+ workers, ecosistema maduro | Overkill para MVP; requiere procesos dedicados y es síncrono por diseño (peor encaje con FastAPI async) |

**Recomendación**: **Taskiq + Redis** para MVP (envío de emails, generación de QR, notificaciones, recordatorios de eventos), migrar a Celery solo si aparece un caso de cómputo pesado (ej. transcodificación). Fuentes: [Medium - Celery vs ARQ vs RQ 2026](https://medium.com/@rameshkannanyt0078/fastapi-background-tasks-celery-vs-arq-vs-rq-2026-benchmarks-decision-guide-f99598aa21eb), [blog.rajpoot.dev 2026](https://blog.rajpoot.dev/posts/fastapi/fastapi-background-tasks-2026/), [GitHub taskiq-python](https://github.com/taskiq-python/taskiq), [pyrastra.com comparación 2026](https://pyrastra.com/posts/python-task-queues-celery-dramatiq-taskiq-2026/).

### 1.7 Email
`fastapi-mail` (wrapper sobre `aiosmtplib`, async nativo) para SMTP propio; para deliverability en producción (evitar spam) usar proveedor transaccional (**Resend** tiene integración documentada para FastAPI, o Postmark/SES). Recomendación open-source-friendly: abstraer detrás de una interfaz `EmailProvider` (SMTP genérico por defecto, para que un self-hoster use su propio SMTP; Resend/Postmark como opción). Fuentes: [fastapi-mail docs](https://sabuhish.github.io/fastapi-mail/), [Resend FastAPI](https://resend.com/docs/send-with-fastapi).

### 1.8 QR firmados
No hay librería única "todo en uno" madura y muy usada; el patrón estándar es **segno** (generación QR, pura Python, sin dependencias, sopor ta SVG/PNG) + firma propia con **HMAC-SHA256** o un **JWT compacto** (payload: `ticket_id`, `event_id`, `exp`, `nonce` anti-replay) usando PyJWT. Añadir: expiración corta o ligada al evento, marca de uso único (registrar `used_at` en BD al validar/hacer check-in) para evitar reutilización de capturas de pantalla. Fuentes: [segno docs](https://segno.readthedocs.io/en/latest/), [authgear HMAC guide](https://www.authgear.com/post/generate-verify-hmac-signatures/). (Se ha visto un proyecto de nicho "AdmitiQ" con esta idea empaquetada, pero es demasiado pequeño/no verificado para depender de él en producción — mejor implementarlo directamente, es ~30 líneas).

### 1.9 OCR de facturas/tickets
Relevante si la plataforma emite/gestiona facturas de organizador o ingiere recibos de gasto (confirmar con el PRD si aplica; Luma no lo hace nativamente). Comparativa 2026:
- **Tesseract**: más rápido en documentos limpios/estandarizados, pero peor en tablas y layouts mixtos.
- **PaddleOCR (v5 / PaddleOCR-VL)**: mejor precisión en facturas, tablas y layouts complejos; recomendado si hay OCR de documentos reales.
- **EasyOCR**: mejor en imágenes borrosas/naturales, pero "confunde sistemáticamente símbolos como $" — mal encaje para datos financieros.
- **LLM vision (GPT-4o, Mistral OCR, Qwen2.5-VL)**: mejor para casos borde y layouts muy variables, coste por documento pero cero mantenimiento de pipeline.
**Recomendación si aplica**: híbrido PaddleOCR (grueso, gratis, self-hosted) + fallback LLM vision para baja confianza — patrón ya validado en investigación previa del equipo (ver memoria). Fuentes: [codesota.com comparación 2026](https://www.codesota.com/ocr/paddleocr-vs-tesseract), [invoicedataextraction.com](https://invoicedataextraction.com/blog/python-ocr-library-comparison-invoices).

### 1.10 Stripe
`stripe-python` mantiene versión de API pineada por SDK (a fecha de hoy, versiones de API tipo `2026-06-24` / `2026-08-26`, con sufijo `.dahlia`); usar **Stripe Checkout** (hosted, minimiza superficie PCI) + **Stripe Connect** si cada organizador cobra directamente (relevante en multi-tenant tipo Luma, donde cada organizador tiene su propia cuenta Stripe). Webhooks: verificar firma siempre (`stripe.Webhook.construct_event`), nunca confiar en el payload sin verificar; nuevo `EventNotificationHandler` (2026) simplifica el manejo de "thin events". Fuentes: [stripe-python CHANGELOG](https://github.com/stripe/stripe-python/blob/master/CHANGELOG.md), [Stripe API Versioning docs](https://docs.stripe.com/api/versioning?lang=python).
**Decisión de PRD pendiente**: ¿pagos van a la cuenta de la plataforma (marketplace clásico) o Stripe Connect por organizador? Esto cambia arquitectura de webhooks y de KYC — es una decisión de producto/legal, no solo técnica.

### 1.11 Cloudflare Turnstile
Verificación **siempre server-side**: POST a `https://challenges.cloudflare.com/turnstile/v0/siteverify` con `secret`, `response` (token del cliente) y opcionalmente `remoteip`. Token válido 5 minutos, un solo uso. Nunca exponer el secret en frontend. Implementación trivial con `httpx` async en FastAPI. Fuente: [Cloudflare docs oficiales](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/).

### 1.12 Rate limiting
- **SlowAPI**: decorador simple, basado en `limits`, activo (última release jun 2026), usado en producción a media escala.
- **fastapi-limiter**: usa Redis + Lua script, mejor para límites distribuidos multi-instancia (necesario en cuanto haya >1 réplica del backend).
**Recomendación**: fastapi-limiter (Redis) desde el principio, porque Redis ya es dependencia obligada por Taskiq — evita mantener dos soluciones de rate limiting. SlowAPI si se descarta Redis. Fuentes: [slowapi PyPI](https://pypi.org/project/slowapi/), [fastapi-limiter PyPI](https://pypi.org/project/fastapi-limiter).

### 1.13 i18n backend
No se encontró un estándar dominante espec ífico para FastAPI (a diferencia de Django). Patrón habitual: `babel` o `python-i18n` para mensajes de servidor (emails, notificaciones), manteniendo el grueso de i18n en el frontend Angular. No profundizado más — bajo riesgo, decisión menor.

---

## 2. Frontend: Angular

### 2.1 Versión y LTS
- **Angular 22** es la versión estable actual (lanzada 3 jun 2026). **Angular 21** pasó a LTS en jun 2026 (soporte hasta 19 may 2027); Angular 20 LTS hasta 28 nov 2026. Fuente: [HeroDevs version history](https://www.herodevs.com/blog-posts/angular-version-history-every-release-date-support-window-and-end-of-life-date-from-angularjs-to-angular-22), [versions.dev](https://versions.dev/modernize/angular/upgrade-to-angular-22).
- **Recomendación**: empezar en **Angular 22** (o 21 si 22 es muy reciente y hay fricción de dependencias de terceros) — proyecto nuevo, sin motivo para partir de una LTS antigua.

### 2.2 Standalone + Signals
Standalone es el default desde hace varias versiones; Angular 20 estabilizó `effect()`, `linkedSignal()`, `toSignal()`; Angular 21 quita zone.js por defecto en apps nuevas y añade Signal Forms (experimental). **Recomendación**: standalone + signals desde el día 1, zoneless si el equipo tiene experiencia (si no, zone.js por defecto es más seguro para no perder velocidad al inicio). Fuente: [Medium Angular 21 deep dive](https://kkirtigoel01.medium.com/angular-21-deep-dive-comprehensive-upgrades-migration-guide-pros-cons-real-world-examples-5931e2013c32).

### 2.3 SSR/hydration: ¿desde el principio?
Argumentos a favor: SEO de páginas públicas de evento (crítico — cada evento necesita ser indexable y compartible en redes con OG tags correctos, como Luma), mejor LCP. Riesgos: hydration mismatches si hay lógica no determinista o acceso a `window`/`document` sin guard de plataforma; requiere disciplina desde el principio (usar `@defer`, "Event Replay" para inputs durante hidratación, evitar mismatches de `<tbody>` y estructuras DOM). **Recomendación**: activar SSR **desde el principio** solo para las rutas públicas (landing de evento, listado, perfil de organizador); el panel de administración puede ser CSR puro (no necesita SEO) — esto reduce superficie de riesgo de hydration a la parte que realmente lo necesita. Fuentes: [angulararchitects.io SSR guide](https://www.angulararchitects.io/blog/guide-for-ssr/), [onehorizon.ai 2026 playbook](https://onehorizon.ai/blog/angular-best-practices-2026-the-architects-playbook).

### 2.4 Theming dinámico multi-tenant
- **Tailwind v4**: los design tokens son variables CSS nativas por defecto; `@theme` define tokens que se pueden re-scopear por `[data-tenant="x"]` o inyectar en runtime vía `document.documentElement.style.setProperty(...)` — encaja perfectamente con "cada organizador define su color/logo" sin recompilar CSS. Fuente: [Tailwind v4 blog oficial](https://tailwindcss.com/blog/tailwindcss-v4), [simonswiss.com multi-theme](https://simonswiss.com/posts/tailwind-v4-multi-theme/).
- **Angular Material M3**: usa tokens CSS también (Sass API `mat.define-theme`), permite overrides granulares sin `!important`. Pero M3 añade una capa de indirección/complejidad (Sass + tokens) que puede ser innecesaria si ya se usa Tailwind para todo el layout.
**Recomendación**: **Tailwind v4 + CSS custom properties inyectadas por tenant, sin Angular Material** (o Material solo para 2-3 componentes complejos tipo date-picker, con overrides mínimos). Evita mantener dos sistemas de tokens en paralelo (Material tokens + Tailwind tokens) — decisión alineada con KISS. Fuente comparativa: [briebug.com Material 3 Angular 20](https://briebug.com/articles/material-3-theming/).
- Carga dinámica de plantillas de página: guardar layout como JSON/config por tenant en BD (bloques: hero, agenda, speakers, sponsors) + componentes Angular que renderizan por tipo de bloque — patrón "renderer de bloques", no motor de templates completo (evita reinventar un CMS).

### 2.5 i18n
**Transloco** (runtime, lazy-loaded scoped, signals-friendly) vs **@angular/localize** (build-time, un build por idioma, más rápido en runtime pero recarga completa al cambiar idioma). Para una plataforma donde el organizador y el asistente pueden estar en idiomas distintos **en la misma sesión sin recargar**, Transloco es más adecuado. Coste: ~93k descargas/semana (bastante menor que @angular/localize, pero activamente mantenido). **Recomendación: Transloco**. Fuente: [Lokalise Transloco guide](https://lokalise.com/blog/angular-localization-with-transloco/), [intlayer.org comparación 2026](https://intlayer.org/blog/i18n-technologies/frameworks/angular).

### 2.6 Generación de tipos desde OpenAPI
Tres opciones viables: `ng-openapi-gen` (maduro, específico Angular, compatible ≥16), `ng-openapi` (más moderno, Angular-first), `orval` (multi-framework, soporta Angular). **Recomendación: ng-openapi-gen** por madurez y estabilidad; revalorar `orval` si el equipo ya lo usa en otros stacks (menos fricción). Fuente: [npm ng-openapi-gen](https://www.npmjs.com/package/ng-openapi-gen), [orval.dev docs](https://orval.dev/docs/).

### 2.7 Testing
Angular CLI adoptó **Vitest** como test runner por defecto para proyectos nuevos desde finales de 2025, ya estable/production-ready; Karma+Jasmine quedan deprecados pero siguen funcionando. **Recomendación: Vitest** desde el inicio del proyecto (proyecto nuevo, sin deuda de migración). Fuente: [angular.dev migrating to Vitest](https://angular.dev/guide/testing/migrating-to-vitest).

### 2.8 PWA para escaneo de QR
`@angular/pwa` (`ng add @angular/pwa`) para service worker + manifest. Cámara vía `navigator.mediaDevices.getUserMedia` (API estándar, requiere HTTPS). Librería de decodificación: **ZXing (`@zxing/browser`)** o **`qr-scanner` (nimiq)** — ambas activamente mantenidas y con mejor tasa de detección que `jsQR` (que está sin mantenimiento activo aunque sigue funcionando para casos básicos); `qr-scanner` corre en Web Worker (no bloquea el hilo principal), recomendado para escaneo continuo en check-in de eventos. **Recomendación: `qr-scanner` (nimiq)**. Fuentes: [scanbot.io comparación librerías OSS](https://scanbot.io/blog/popular-open-source-javascript-barcode-scanners/), [GitHub nimiq/qr-scanner](https://github.com/nimiq/qr-scanner).

---

## 3. Multi-tenancy en PostgreSQL

Tres patrones, evaluados para un proyecto **open source auto-instalable** (el propio organizador puede instalarlo, no necesariamente una plataforma SaaS centralizada gestionada por vosotros):

| Patrón | Aislamiento | Complejidad operativa | Encaje self-hosted |
|---|---|---|---|
| Tabla compartida + `organization_id` (filtro en app) | Bajo (depende 100% de que el código nunca falle un WHERE) | Baja | Bueno si se refuerza con RLS |
| **Tabla compartida + RLS de Postgres** | Alto (el propio motor de BD filtra, incluso si el código olvida el WHERE) | Media (política RLS + `SET app.tenant_id` por transacción) | **Recomendado** |
| Schema por tenant | Alto, aislamiento lógico fuerte | Alta (N schemas, migraciones × N, backups más complejos) | Malo para instalación única self-hosted de un organizador con múltiples "sub-eventos" — sobra |
| BD por tenant | Máximo | Muy alta | Solo si cada organizador tiene su propia BD física — no aplica aquí, ya que el modelo es "un organizador instala una vez y gestiona sus propios eventos", no "una BD central multi-cliente" |

**Contexto clave**: dado que el proyecto es *"open source, cada organizador lo instala"*, en la práctica **cada instalación ya es de un solo tenant/organización** en el caso más simple (un organizador = una instancia). El multi-tenant real dentro de una instalación aparece si **una instancia aloja varios organizadores** (ej. SaaS gestionado por el propio equipo del proyecto, o un organizador que gestiona sub-marcas). Para cubrir ambos casos con el mismo código: **tabla compartida + RLS**, con `organization_id` en cada tabla de dominio y política RLS que filtra por `current_setting('app.tenant_id')`, seteado en middleware/dependencia de sesión de FastAPI al inicio de cada request. Es el patrón dominante recomendado en 2026 (>70% de brechas multi-tenant se deben a fallos de aislamiento solo a nivel de aplicación, según fuente citada). Fuentes: [queryplane.com RLS in practice](https://queryplane.com/blog/postgres-row-level-security-in-practice/), [nileshblog.tech RLS guide 2026](https://nileshblog.tech/multi-tenant-database-rls/), [adiagr.com patrones comparados](https://www.adiagr.com/blog/07-saas-postgres-multitenancy-patterns/).

**Riesgo técnico a documentar en PRD**: RLS + pool de conexiones asíncronas (asyncpg) exige disciplina: el `SET LOCAL` debe ir dentro de la misma transacción que la query, y SQLAlchemy async + pooling reutiliza conexiones — hay que centralizarlo en un único punto (dependencia de sesión), nunca dejarlo a discreción de cada endpoint.

### 3.1 Dominios personalizados por organizador (subdominio + dominio propio)
**Caddy con TLS "on-demand"** es la opción más simple: emite certificados Let's Encrypt en el momento en que llega una petición para un dominio nuevo, validando contra un endpoint interno ("¿este dominio está registrado?"). Evita certificados wildcard y encaja perfectamente con "cada organizador añade su dominio propio". **Traefik** es más apropiado si el despliegue objetivo es Kubernetes (auto-discovery vía labels/anotaciones); para Docker Compose simple, Caddy es más ligero y con menos configuración. **Recomendación: Caddy + on-demand TLS**, con endpoint de verificación de dominio en el backend FastAPI. Fuentes: [Caddy docs oficiales on-demand TLS](https://caddyserver.com/on-demand-tls), [skeptrune.com wildcard TLS multi-tenant](https://www.skeptrune.com/posts/wildcard-tls-for-multi-tenant-systems/).

---

## 4. MinIO — ALERTA de riesgo de adopción

**Hallazgo crítico, cambia la recomendación por defecto del stack acordado**: MinIO ya no es una opción segura para un proyecto open source nuevo a largo plazo.
- Mayo 2025: MinIO retira funcionalidad de la UI de la edición Community.
- Diciembre 2025: la Community Edition entra en **modo mantenimiento** (solo parches de seguridad, sin nuevas features).
- Principios de 2026: el repositorio de GitHub se **archiva como solo lectura**.
- Además, dejaron de publicar imágenes Docker precompiladas en registries públicos, obligando a compilar desde fuente.
- Licencia base ya era AGPLv3 desde 2021 (restrictiva para redistribución en un proyecto open source que otros instalan y modifican).

Fuentes: [itsfoss.com "MinIO moves away from open source"](https://itsfoss.com/news/minio-moves-away-from-open-source/), [bizety.com "MinIO in Maintenance Mode"](https://bizety.com/2025/12/06/minio-in-maintenance-mode-open-source-alternatives/), [pepitedata.com](https://pepitedata.com/minio-community-edition-end-agpl/), [cloudian.com bait-and-switch](https://cloudian.com/blog/minios-ui-removal-leaves-organizations-searching-for-alternatives/).

**Alternativas S3-compatibles**:
- **SeaweedFS** (Go, licencia Apache 2.0): muy buen rendimiento con grandes volúmenes de archivos pequeños (O(1) seek), maduro, usado en producción por terceros.
- **Garage** (Rust, AGPLv3 también pero proyecto activo — Deuxfleurs): diseñado para self-hosting distribuido, pensado explícitamente para comunidades pequeñas/self-hosters, buena documentación.
- **RustFS** (Rust, Apache 2.0): más nuevo, posicionado explícitamente como reemplazo drop-in de MinIO, soporta migración desde MinIO/Ceph — pero por ser reciente, madurez y comunidad aún por validar (mayor riesgo de adopción).

**Recomendación**: **SeaweedFS** como almacenamiento de objetos por defecto (licencia permisiva, maduro, comunidad establecida) — mejor encaje para un proyecto open source que otros van a redistribuir/modificar libremente. Diseñar la capa de acceso a almacenamiento detrás de una interfaz `StorageProvider` (ya usáis S3 API en ambos, boto3/aioboto3 funciona igual) para no bloquear la decisión y permitir que el self-hoster elija MinIO, SeaweedFS, Garage o un S3 real (AWS/Cloudflare R2/Backblaze) sin cambiar código. Fuente comparativa: [dev.to MinIO alternatives 2026](https://dev.to/ethan-carter/best-minio-alternatives-in-2026-6-options-that-actually-work-17p2).

**Presigned URLs y procesado de imágenes**: patrón estándar (subida directa del cliente vía presigned PUT, servir imágenes públicas vía presigned GET o proxy con cache-control). Procesado: **pyvips (libvips)** es hasta ~10x más rápido que Pillow y usa mucha menos memoria en redimensionado de imágenes (relevante para miniaturas de eventos/avatares a escala); Pillow sigue siendo más fácil de instalar/soporta más formatos "out of the box" sin pasos de compilación. **Recomendación**: Pillow para el MVP (simplicidad de despliegue, sin dependencias de sistema complejas); migrar a pyvips si el volumen de subida de imágenes se vuelve un cuello de botella medido. Fuentes: [GitHub libvips speed wiki](https://github.com/libvips/libvips/wiki/Speed-and-memory-use), [HN discusión pyvips vs pillow-simd](https://news.ycombinator.com/item?id=45322827).

---

## 5. Streaming de vídeo

- **Embeber directos/grabaciones de YouTube, Twitch, Vimeo**: vía sus iframes/embed oficiales — trivial, sin coste de infraestructura propia. Contadores de visualización: cada plataforma expone su propia API (YouTube Data API v3, Twitch Helix API, Vimeo API) — no hay un estándar unificado, hay que integrar cada una si se necesita el contador in-app (o confiar en el contador nativo visible en el embed).
- **Self-hosted**: **PeerTube** (federado vía ActivityPub, transcodificación propia, adecuado para vídeo bajo demanda/grabaciones) y **Owncast** (directo en vivo + chat, más ligero, pensado como alternativa a Twitch). PeerTube 8.1 (mar 2026) añadió embeds restringidos por dominio, mejor soporte podcast, reproducción 3x.
**Recomendación**: para un MVP, **embeber plataformas externas** (cero mantenimiento, cero coste de transcodificación/CDN) y dejar self-hosted (PeerTube/Owncast) como opción avanzada/plugin para organizadores que quieran control total — no meterlo en el core del MVP (YAGNI). Fuentes: [pistack.xyz guía PeerTube 2026](https://www.pistack.xyz/posts/peertube-self-hosted-youtube-alternative-guide/), [openaltfinder.com Owncast vs PeerTube](https://openaltfinder.com/compare/owncast-vs-peertube).

---

## 6. Cookies y legal técnico

- **Klaro**: BSD-3, ~57kB, control granular, bloquea scripts externos hasta consentimiento — opción más completa y neutra para un proyecto open source (no depende de servicio de pago para lo esencial).
- **Orejime**: fork de Klaro centrado en accesibilidad (WCAG/RGAA francés) — interesante si la accesibilidad es requisito explícito.
- **CookieConsent (OrestBida)**: más simple, más fácil de restylar visualmente.
- **tarteaucitron**: activo pero con documentación/comunidad más centrada en Francia.
**Recomendación: Klaro** (equilibrio entre completitud, licencia permisiva y mantenimiento activo). Fuente: [libhunt Klaro alternatives](https://www.libhunt.com/r/klaro), [merginit.com comparación 2026](https://merginit.com/blog/15062026-free-cookie-consent-cmp-comparison).
- **Escaneo automático de cookies**: no se encontró herramienta open source madura y fiable para escaneo automático continuo (las soluciones serias de "cookie scanning" son de pago — Cookiebot, OneTrust). Viabilidad de hacerlo in-house: baja prioridad/alto esfuerzo — recomendación: mantenimiento manual de la lista de cookies/categorías en el propio Klaro config, revisada en cada release. No profundizado más — riesgo bajo pero **no resuelto**, ver preguntas abiertas.
- **Páginas legales** (aviso legal, privacidad, cookies): no existe generador OSS de confianza y actualizado normativamente citado en las fuentes consultadas; recomendación estándar del sector es plantilla + revisión legal humana, no generador automático — fuera del alcance técnico de esta investigación.

---

## 7. Despliegue open source

- **Docker Compose de producción**: patrón estándar — servicios `api`, `web` (o servido por el propio Caddy si SSR), `db` (postgres), `redis`, `storage` (seaweedfs/minio), `worker` (taskiq), reverse proxy (`caddy`).
- **Backups**: Postgres vía `pg_dump`/`pg_basebackup` + WAL archiving a almacenamiento de objetos; MinIO/SeaweedFS vía snapshot o replicación a un segundo bucket/proveedor. No hay atajo: hay que automatizar cron + verificación de restauración periódica (no solo generar backups, probarlos).
- **Dokploy vs Coolify** (ambos self-hosted PaaS, alternativas a Vercel/Heroku):
  - **Coolify**: más maduro, mayor comunidad, PHP/Laravel + Traefik, catálogo de un-click apps más amplio; CVEs de enero 2026 ya parcheadas en v4.0.0 (abril 2026) — **no exponer el dashboard públicamente**.
  - **Dokploy**: más joven, TypeScript, Docker Swarm nativo desde el día 1 (mejor si se prevé escalar a multi-nodo), soporte Compose de primera clase.
  **Recomendación**: **Coolify** para un proyecto que prioriza estabilidad/comunidad ahora mismo; **Dokploy** si el equipo ya usa Docker Compose como unidad de despliegue y valora simplicidad Swarm. Ninguno es obligatorio — Docker Compose "a pelo" + Caddy sigue siendo válido y más portable para que cualquier organizador lo autoinstale sin depender de una capa PaaS adicional (más alineado con "instalación simple por terceros"). Fuentes: [introserv.com comparación 2026](https://introserv.com/blog/dokploy-vs-coolify-complete-comparison-of-the-best-self-hosted-paas-platforms-for-vps-and-dedicated-servers-2026/), [cloudzy.com CVEs y licencia](https://cloudzy.com/blog/coolify-vs-dokploy/).
- **CI**: GitHub Actions estándar (build+test+lint en PR, build+push imagen en merge a main, deploy manual o webhook).
- **Observabilidad mínima**: **Prometheus + Grafana + Loki** cabe en un único VPS pequeño (4GB RAM cubre métricas + logs + dashboards + alertas); alternativa "todo en uno" más simple de operar: **OpenObserve** (un solo binario, cubre métricas+logs+trazas). **Recomendación para MVP**: empezar con Grafana+Loki+Prometheus vía Docker Compose (encaja con el resto del stack ya containerizado); considerar OpenObserve si se quiere reducir el número de contenedores. Fuentes: [dev.to stack self-hosted 2026](https://dev.to/enfernandes/the-ultimate-self-hosted-observability-stack-prometheus-grafana-loki-uptime-kuma-4bmc), [ossalt.com guía 2026](https://ossalt.com/guides/how-to-self-host-grafana-prometheus-metrics-stack-2026/).

---

## 8. Recomendaciones finales (ranking y trade-offs)

### Tabla resumen de decisiones
| Área | Elección recomendada | Alternativa válida | Motivo del ranking |
|---|---|---|---|
| Backend framework | FastAPI (ya decidido) | — | — |
| ORM/migraciones | SQLAlchemy 2 async + Alembic + asyncpg | SQLModel (menos maduro para apps grandes) | Madurez, tipado, ecosistema |
| Auth JWT | PyJWT ≥2.13.0 + Argon2 | python-jose (descartar, menor mantenimiento) | Seguridad, mantenimiento activo |
| Colas/tareas | Taskiq + Redis | arq (más simple pero menos features), Celery (solo si hay carga pesada de cómputo) | Nativo async, DI similar a FastAPI |
| Rate limiting | fastapi-limiter (Redis) | SlowAPI (si se evita Redis) | Reutiliza Redis ya presente por Taskiq |
| Email | fastapi-mail (SMTP) tras interfaz propia | Resend/Postmark como proveedor plug-in | Self-hosting sin atarse a proveedor de pago |
| QR firmados | segno + HMAC/JWT propio | — | Simplicidad, no añadir dependencia de nicho |
| Pagos | stripe-python, Checkout + revisar Connect | — | Estándar de facto, decisión de modelo (marketplace vs Connect) pendiente en PRD |
| Frontend framework | Angular 22 (o 21 si hay fricción) | — | Última estable con soporte largo |
| Testing frontend | Vitest | Karma/Jasmine (deprecado) | Default oficial actual |
| Theming | Tailwind v4 + CSS custom properties por tenant, sin Angular Material (o mínimo) | Angular Material M3 completo | Evita doble sistema de tokens |
| i18n frontend | Transloco | @angular/localize | Cambio de idioma en runtime sin rebuild |
| Tipos OpenAPI | ng-openapi-gen | orval, ng-openapi | Madurez |
| Escáner QR PWA | qr-scanner (nimiq) | ZXing (@zxing/browser) | Web Worker, mejor tasa detección que jsQR |
| Multi-tenancy DB | Tabla compartida + RLS Postgres | Schema-per-tenant (solo si aislamiento legal fuerte lo exige) | Escalabilidad + aislamiento reforzado a nivel motor |
| Dominios propios | Caddy on-demand TLS | Traefik (si se pasa a Kubernetes) | Simplicidad Compose |
| Almacenamiento objetos | SeaweedFS (Apache 2.0) tras interfaz StorageProvider | Garage, MinIO (evitar como default), RustFS (inmaduro aún) | MinIO ya no es seguro adoptar de cero; SeaweedFS más maduro que RustFS |
| Procesado imágenes | Pillow (MVP) → pyvips si hay cuello de botella medido | pyvips desde el inicio | Simplicidad de despliegue primero |
| Vídeo | Embeds externos (YouTube/Vimeo/Twitch) | PeerTube/Owncast como opción avanzada futura | YAGNI para MVP |
| Cookies | Klaro | Orejime (si accesibilidad es requisito duro) | Licencia permisiva + completitud |
| Despliegue | Docker Compose + Caddy (portable) | Coolify (estabilidad) o Dokploy (Swarm-first) como capa opcional | Máxima portabilidad para autoinstalación por terceros |
| Observabilidad | Prometheus + Grafana + Loki | OpenObserve (menos contenedores) | Encaja con Compose ya usado |

### Riesgos de adopción a vigilar
1. **MinIO**: cambio de rumbo de licencia/mantenimiento demuestra que el ecosistema de almacenamiento S3-compatible OSS es volátil — diseñar la capa de storage desacoplada es obligatorio, no opcional.
2. **Taskiq**: proyecto más joven que Celery/arq, verificar antes de cada actualización mayor que no rompe la API de tareas (menor historial de compatibilidad hacia atrás).
3. **RLS + pooling async**: fuente de bugs sutiles de fuga entre tenants si no se centraliza correctamente — requiere tests de aislamiento automatizados desde el primer sprint.
4. **Angular Signal Forms / zoneless**: siguen "experimental"/"developer preview" en las versiones actuales — no construir la capa de formularios crítica (checkout, alta de evento) sobre APIs marcadas como experimentales todavía.
5. **RustFS**: muy nuevo, sin historial de producción demostrado en las fuentes consultadas — no usar como default, solo vigilar su evolución.

### Preguntas abiertas (para el PRD)
- ¿Modelo de pagos: la plataforma cobra y liquida a organizadores (marketplace clásico) o Stripe Connect con cuenta propia por organizador? Cambia el diseño de webhooks, KYC y compliance.
- ¿La instancia self-hosted es "un organizador = una instalación" o "una instalación aloja múltiples organizadores" (multi-tenant real)? Cambia el alcance real de RLS/dominios personalizados.
- ¿Hay caso de uso de OCR de facturas/recibos en el producto, o era solo referencia de investigación previa? Si no aplica, se puede eliminar del alcance técnico.
- ¿Requisito legal de accesibilidad (WCAG/RGAA) explícito? Determina Klaro vs Orejime y nivel de esfuerzo en Angular Material vs Tailwind puro.
- ¿Se espera que un mismo organizador escale a multi-nodo pronto? Determina si vale la pena la complejidad de Dokploy/Swarm desde ya o Compose simple es suficiente.
- Escaneo automático/continuo de cookies: no resuelto con herramienta OSS fiable — decidir si se acepta mantenimiento manual o se evalúa un proveedor de pago puntual.

### Limitaciones de esta investigación
- No se ha verificado con benchmarks propios ninguna cifra de rendimiento citada (todas proceden de fuentes de terceros, ver enlaces).
- No se ha explorado a fondo cumplimiento normativo específico de España/UE (LOPD-GDD, ePrivacy) más allá de mencionar la necesidad de banner de cookies — requeriría consulta legal, no solo técnica.
- No se ha probado la integración real Caddy on-demand TLS + FastAPI (patrón documentado por terceros, no verificado end-to-end aquí).
- Versiones exactas de librerías Python/Node deben re-verificarse en el momento de iniciar el scaffolding (el ecosistema se mueve rápido; esta investigación es una foto de 2026-09-06).
