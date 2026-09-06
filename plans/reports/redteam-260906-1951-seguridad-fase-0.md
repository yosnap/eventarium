---
title: "Red team de seguridad — Plan Fase 0 (scaffolding)"
plan: plans/260906-1951-fase-0-scaffolding/
reviewer: code-reviewer (perspectiva: adversario de seguridad / fact checker)
date: 2026-09-06
---

# Red team de seguridad — Fase 0 scaffolding

Ámbito: los seis ficheros del plan `plans/260906-1951-fase-0-scaffolding/`, contrastados
contra `docs/prd.md` y `docs/investigacion.md`. El repositorio no tiene código todavía, así
que toda la evidencia son citas a los documentos.

---

## Finding 1: Creación de roles y membresías sin regla anti-escalada de privilegios

- **Severity:** Critical
- **Location:** Fase 3, secciones "Requirements" e "Implementation Steps" (pasos 7-8)
- **Flaw:** El plan entrega `POST/PATCH /api/v1/roles` (roles personalizados con permisos
  elegidos de un catálogo) y `POST /api/v1/organizations/me/members` sin enunciar en ningún
  punto la invariante clásica de todo sistema de permisos: **nadie puede conceder un permiso
  que no posee, ni asignar un rol más privilegiado que el suyo**. `require_permission` solo
  comprueba que el llamante tenga `roles:write` / `members:write`.
- **Failure scenario:** Una organización crea el rol personalizado "coordinador" con
  `roles:write` y `members:write` (razonable: gestiona a los voluntarios). Ese coordinador
  llama a `POST /api/v1/roles` creando el rol "x" con **todos** los permisos del catálogo
  (`organizations:write`, `branding:write`, y mañana `accounting:read`, `registrations:*`),
  y acto seguido se lo autoasigna con `POST /organizations/me/members`. Resultado: `owner`
  de facto sin pasar por el `owner`. El mismo camino sirve para expulsar al propietario
  legítimo cuando exista `members:delete`.
- **Evidence:**
  - `plans/260906-1951-fase-0-scaffolding/phase-03-multi-tenant-rls-y-modelos-base.md:16` —
    "`GET/POST/PATCH/DELETE /api/v1/roles`, `GET/POST /api/v1/organizations/me/members`"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:60` — "roles (crear personalizado desde cero
    o desde plantilla, editar campos no bloqueados, impedir borrar `is_system`), membresías
    (alta con validación de `profile_data`)" — la única regla de negocio citada es no borrar
    roles del sistema.
  - `phase-03-multi-tenant-rls-y-modelos-base.md:57` — el catálogo "reserva prefijos para
    fases futuras (`events:*`, `registrations:*`, `accounting:*`)", con lo que el agujero se
    amplía solo al añadir fases.
  - `phase-02-backend-fastapi-base.md:73` — el único criterio de autorización probado es
    "403 sin permiso (test con permiso inexistente)"; no hay caso de escalada.
  - `docs/prd.md:77` — el PRD sí define el modelo ("sus **permisos** de un catálogo fijo
    definido en código") pero no exime de la comprobación.
- **Suggested fix:** Añadir a la Fase 3 la regla explícita "el conjunto de permisos del rol
  creado/editado debe ser un subconjunto de los permisos efectivos del actor" y "solo `owner`
  puede asignar roles que incluyan `roles:write`/`members:write`", más dos tests negativos en
  los Success Criteria. Alternativa más simple y coherente con el PRD: en la fase 0, restringir
  la escritura de roles y membresías al rol `owner` y aplazar la delegación fina.

---

## Finding 2: Resolución de organización por `Host` con tres vías de suplantación de tenant

- **Severity:** Critical
- **Location:** Fase 2, "Architecture" (`core/tenant.py`) y "Risk Assessment"; plan.md, tabla
  "Decisiones de arquitectura aplicadas"
- **Flaw:** El tenant —y con él el valor de `SET LOCAL app.organization_id` que gobierna todo
  el RLS— se deriva de una cabecera controlada por el cliente, y el plan no define: (a) que el
  `Host`/`X-Forwarded-Host` deba validarse contra una allowlist (`TrustedHostMiddleware`) ni
  qué proxy es de confianza; (b) que `X-Organization-Slug` se deshabilite por algo más robusto
  que el valor de una variable de entorno; (c) que el claim `org` del JWT deba **coincidir**
  con la organización resuelta; (d) qué ocurre cuando el `Host` no resuelve, existiendo un
  `DEFAULT_ORGANIZATION_SLUG` que invita al fail-open.
- **Failure scenario:** Tres escenarios concretos.
  1. Un usuario legítimo de la organización A obtiene su JWT (claims `sub`, `org`) y repite la
     petición con `Host: b.ejemplo.com`. `get_db` fija `app.organization_id = B`;
     `get_current_user` valida el token (firma correcta) y `require_permission` consulta
     membresías bajo el contexto B. La defensa es incidental: depende de que no exista membresía
     en B. Cualquier endpoint que lea `users` (tabla **sin RLS**, ver Finding 5) o que cachee
     permisos por `token.org` opera con dos identidades de tenant distintas en la misma petición.
  2. Un despliegue con `APP_ENV` mal fijado (o un `staging` accesible) acepta
     `X-Organization-Slug`: salto de tenant de un solo header, sin autenticación, contra
     `/tenant/branding` y todo lo demás.
  3. Detrás de Caddy (Fase 5), si el backend confía en `X-Forwarded-Host` sin allowlist, un
     `Host:` arbitrario del atacante llega al resolvedor; si además se cae al
     `DEFAULT_ORGANIZATION_SLUG`, peticiones de dominios desconocidos se sirven —y se escriben—
     contra la organización por defecto.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:28` — "`tenant.py` # resolve_organization(host |
    X-Organization-Slug)"
  - `phase-02-backend-fastapi-base.md:41` — "si hay organización resuelta, ejecuta `SET LOCAL
    app.organization_id = :id`" (el tenant del RLS sale del Host, no del token)
  - `phase-02-backend-fastapi-base.md:60` — el token lleva claim `org`, que nunca se contrasta
    con la organización resuelta en ningún paso del plan
  - `phase-02-backend-fastapi-base.md:81` — "Resolución por `Host` rompe en local →
    `DEFAULT_ORGANIZATION_SLUG` + cabecera de desarrollo" (mitigación de DX, no de seguridad)
  - `phase-01-monorepo-y-entorno.md:33` — `DEFAULT_ORGANIZATION_SLUG` es una variable de entorno
    normal, sin restricción a `development`
  - `plan.md:28` — "cabecera `X-Organization-Slug` solo fuera de producción"; el mecanismo de
    ese "solo" no se especifica en ninguna fase
  - `docs/prd.md:190` — el PRD exige RLS "fijada por transacción en un único punto"; no cubre
    la confianza en la entrada que alimenta ese punto
- **Suggested fix:** En la Fase 2: (1) `TrustedHostMiddleware` con los hosts de
  `organization_domains` + rechazo 421/404 si no resuelve, **sin** fallback al slug por defecto
  fuera de `development`; (2) `X-Organization-Slug` compilado tras `if settings.APP_ENV ==
  "development"` con test que verifique 400 en `production`; (3) invariante `token.org ==
  organización resuelta → 401` en `get_current_user`, con test; (4) documentar en Fase 5 la
  configuración de `forwarded_allow_ips`/`--proxy-headers` de uvicorn tras Caddy.

---

## Finding 3: Bypass global de RLS mediante un GUC (`app.bypass`) sin control de acceso

- **Severity:** Critical
- **Location:** Fase 3, "Architecture" → apartado **RLS**
- **Flaw:** El plan propone implementar el superadministrador con `SET LOCAL app.bypass = 'on'`
  comprobado dentro de la política de RLS. Un parámetro de configuración de sesión no es una
  credencial: cualquier rol de base de datos puede fijar un GUC personalizado, y en la
  aplicación basta con un único camino de código que ejecute ese `SET` para que todas las
  políticas de todas las tablas queden anuladas. El plan no define quién puede activarlo, ni
  test alguno que demuestre que un usuario normal no puede.
- **Failure scenario:** La bandera se introduce en la Fase 3 "sin UI". En una fase posterior,
  alguien añade un endpoint de exportación/soporte que llama al helper de bypass detrás de un
  `if user.is_superadmin` en Python. Cualquier fallo de autorización en ese único punto —o una
  inyección SQL en cualquier consulta futura del monolito, que normalmente solo leería una
  tabla— se convierte en lectura y escritura de **todas** las organizaciones, porque el atacante
  puede anteponer `SET app.bypass='on'` o simplemente alcanzar el helper. El propio PRD marca la
  fuga entre organizaciones como riesgo principal del proyecto.
- **Evidence:**
  - `phase-03-multi-tenant-rls-y-modelos-base.md:41` — "Superadmin: se implementa con `SET LOCAL
    app.bypass = 'on'` verificado en la política; sin UI en esta fase."
  - `phase-03-multi-tenant-rls-y-modelos-base.md:64` — el test de aislamiento cubre "dos
    organizaciones… rol de BD sin `BYPASSRLS` verificado con `pg_roles`", pero **no** que un
    usuario no privilegiado sea incapaz de activar `app.bypass`
  - `docs/prd.md:276` — riesgo declarado "Fuga de datos entre organizaciones (RLS + pool async)"
  - `docs/prd.md:173` — el superadmin es alcance de la **fase 5** del PRD, no de la 0
  - `plan.md:101` — los non-goals ya excluyen "superadmin UI", pero no el mecanismo de bypass
- **Suggested fix:** Eliminar `app.bypass` de la Fase 0 (no hay caso de uso: el superadmin es
  fase 5 del PRD). Cuando llegue, implementarlo con una **segunda conexión con rol de BD
  distinto y credenciales propias** (`DATABASE_SUPERADMIN_URL`, rol con `BYPASSRLS`), auditada,
  nunca con un GUC que cualquier sentencia pueda fijar.

---

## Finding 4: Subida de ficheros y presigned URLs sin validación, sin namespacing por tenant y sobre un prefijo público

- **Severity:** Critical
- **Location:** Fase 1, "Architecture" (bucket `media`); Fase 2, "Requirements"
  (`StorageProvider`); Fase 3, "Requirements" (subida de logo)
- **Flaw:** El plan define `presigned_put_url` y una subida de logo/favicon, y crea una
  "política de lectura pública para `media/public/*`", sin especificar en ninguna fase: tipos
  MIME permitidos, tamaño máximo, sanitización de SVG, derivación de la clave de objeto en
  servidor (`org/{organization_id}/...`) ni caducidad de la URL firmada. `Pillow`, que el PRD
  contempla para procesar imágenes, no aparece en las dependencias de la Fase 2.
- **Failure scenario:** Dos escenarios.
  1. **XSS almacenado cross-tenant.** Un `organizer` de la organización A sube como logo un
     SVG con `<script>`. El fichero queda en `media/public/...` y se sirve desde
     `S3_PUBLIC_BASE_URL`; el `public-shell` de Angular lo pinta en el header. Si ese origen se
     comparte con la app (o el SVG se incrusta inline), el script se ejecuta con acceso al
     `localStorage` donde el plan permite guardar el refresh token (Finding 6).
  2. **Sobrescritura entre organizaciones y carga arbitraria.** Si la clave del objeto se
     acepta del cliente en `presigned_put_url` (el plan no dice lo contrario), la organización A
     firma una PUT sobre `media/public/org-b/logo.png`, reemplazando la marca de B; y sin
     límite de `Content-Length`/`Content-Type` el bucket público se convierte en alojamiento
     gratuito de contenido arbitrario servido desde el dominio del organizador.
- **Evidence:**
  - `phase-01-monorepo-y-entorno.md:22` — "crea el bucket `media` y política de lectura pública
    para `media/public/*`"
  - `phase-02-backend-fastapi-base.md:16` — "`StorageProvider` con `put_object`,
    `presigned_get_url`, `presigned_put_url`, `delete_object`, `public_url`" (sin restricciones)
  - `phase-03-multi-tenant-rls-y-modelos-base.md:16` — "`GET/PUT /api/v1/organizations/me/branding`
    (con subida de logo a storage)"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:34` — `role_profile_fields` admite ya
    `field_type` `image|file`, así que la superficie de subida no se limita al logo
  - `phase-02-backend-fastapi-base.md:48` — la lista de dependencias incluye `python-multipart`
    pero **no** `Pillow`, pese a `docs/prd.md:210` ("Presigned URLs; Pillow para miniaturas")
  - `docs/prd.md:191` — "OWASP ASVS nivel 2 como referencia" (ASVS V12 exige justo estas
    validaciones)
- **Suggested fix:** En la Fase 3, fijar: allowlist de MIME (`png`, `jpeg`, `webp`; SVG solo
  sanitizado o directamente prohibido), verificación del contenido real con Pillow y no de la
  extensión, límite de tamaño, clave de objeto **generada en servidor** con prefijo
  `org/{organization_id}/`, TTL corto en las URLs firmadas, y `Content-Disposition`/
  `X-Content-Type-Options` en el servidor público. Añadir un test negativo por cada regla.

---

## Finding 5: `users` sin RLS combinado con repositorios que omiten el filtro deliberadamente

- **Severity:** High
- **Location:** Fase 3, "Architecture" → RLS, e "Implementation Steps" paso 6
- **Flaw:** El plan declara `users` tabla global sin RLS ("se accede a través de membresías"),
  y a la vez establece como práctica que los repositorios pueden consultar sin filtro por
  organización porque "RLS protege". Ambas afirmaciones son incompatibles: sobre `users` no hay
  red de seguridad en la base de datos, solo la disciplina del desarrollador.
- **Failure scenario:** En la Fase 1 del PRD (siguiente plan) alguien implementa un buscador de
  personas para invitar a un miembro: `SELECT ... FROM users WHERE email ILIKE :q`. Como la
  convención establecida dice que RLS protege, el filtro por membresía se olvida o se pierde en
  una refactorización. Resultado: cualquier organización de la instalación enumera los emails y
  nombres de todos los usuarios del resto de organizaciones —PII, RGPD— y confirma si una
  persona concreta está registrada. Los tests de aislamiento propuestos no lo detectan porque
  solo prueban tablas con `organization_id`.
- **Evidence:**
  - `phase-03-multi-tenant-rls-y-modelos-base.md:41` — "`users` es global (sin RLS) y se accede
    a través de membresías"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:59` — "Repositorios: consultas sin filtro
    manual por organización **deliberadamente** en un helper de test para demostrar que RLS
    protege"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:64` — el test de aislamiento se describe sobre
    "dos organizaciones… INSERT con `organization_id` de B falla"; `users` queda fuera
  - `docs/prd.md:190` — "`organization_id` en toda tabla de dominio + Row-Level Security"
  - `docs/prd.md:192` — "RGPD: minimización de datos…"
- **Suggested fix:** Activar RLS también en `users` con una política basada en la existencia de
  una fila en `organization_members` para `app.organization_id` (o exponer una vista
  `tenant_users` y prohibir el acceso directo al rol de aplicación). Añadir al criterio de éxito
  un test que consulte `users` sin filtro desde el contexto A y verifique que no aparece el
  usuario exclusivo de B.

---

## Finding 6: Refresh token en `localStorage`, revocación fail-open en Redis y CORS incompatible con multi-dominio

- **Severity:** High
- **Location:** Fase 2, "Architecture" (refresh + rotación) y paso 9; Fase 4, "Architecture" → Auth
- **Flaw:** La Fase 4 deja el almacenamiento del refresh token como condicional ("cookie
  HttpOnly **si el backend lo soporta**, si no `localStorage`") mientras la Fase 2 no define
  ninguna cookie: el resultado por defecto es `localStorage`. Además, la revocación vive
  exclusivamente en Redis, sin definir TTL ni comportamiento ante Redis caído (fail-open: los
  tokens revocados vuelven a valer). Y `CORS_ORIGINS` es una lista estática, incompatible con el
  modelo de un dominio por organización que el propio PRD exige.
- **Failure scenario:** (a) El XSS del Finding 4 —o cualquier dependencia npm comprometida—
  exfiltra el refresh token del `localStorage`; con rotación pero sin cookie ni binding, el
  atacante mantiene sesión indefinida. (b) Se reinicia Redis en producción durante un incidente:
  todos los refresh tokens de las sesiones cerradas (`logout`) vuelven a ser aceptados, porque
  la lista de revocación era el único registro. (c) Al conectar la segunda organización con su
  dominio, `CORS_ORIGINS` no la contempla; la salida rápida y previsible será `allow_origins=["*"]`
  o una regex laxa con `allow_credentials=True`, lo que anula el aislamiento de origen.
- **Evidence:**
  - `phase-04-frontend-angular-y-theming.md:42` — "refresh en cookie `HttpOnly` si el backend lo
    soporta, si no en `localStorage` con rotación"
  - `phase-02-backend-fastapi-base.md:43` — "Refresh tokens con rotación y lista de revocación en
    Redis (`logout`)" — ninguna mención a cookies, `SameSite`, CSRF ni persistencia
  - `phase-01-monorepo-y-entorno.md:33` — `CORS_ORIGINS` como variable simple del `.env.example`
  - `phase-02-backend-fastapi-base.md:58` — "`CORS_ORIGINS` lista"
  - `docs/prd.md:96` y `docs/investigacion.md:50` — "Dominio propio con TLS automático" /
    "Caddy con TLS on-demand": el conjunto de orígenes legítimos es dinámico por diseño
  - `docs/prd.md:191` — "OWASP ASVS nivel 2 como referencia"
- **Suggested fix:** Decidir **en la Fase 2** (no en la 4): refresh token en cookie `HttpOnly;
  Secure; SameSite=Strict` con ruta `/api/v1/auth/refresh` y protección CSRF; persistir la
  revocación en PostgreSQL (o al menos exigir Redis con AOF y tratar el fallo de Redis como
  fail-closed en `refresh`). Resolver CORS contra `organization_domains` en runtime, con
  `allow_credentials` solo para orígenes registrados, y test que verifique el rechazo de un
  origen desconocido.

---

## Finding 7: No hay `.dockerignore` ni gestión de secretos para imágenes publicadas en GHCR

- **Severity:** High
- **Location:** Fase 2, "Related Code Files" (Dockerfile); Fase 4, "Related Code Files";
  Fase 5, "Implementation Steps" paso 2
- **Flaw:** Las tres fases que crean Dockerfiles y el workflow que publica imágenes en un
  registro no listan **ningún** `.dockerignore`, y el plan sitúa el fichero de entorno real en
  `infra/env/` dentro del propio repositorio, junto a `infra/seaweedfs/s3.json.example` con las
  credenciales S3. Tampoco se define de dónde salen `JWT_SECRET`, `S3_SECRET_KEY` o la
  contraseña de Postgres en el `docker-compose.prod.yml`.
- **Failure scenario:** El `Dockerfile` multi-stage hace el habitual `COPY . .` sobre el
  contexto de build. Sin `.dockerignore`, la capa incluye `infra/env/.env` (con `JWT_SECRET` y
  credenciales de Postgres/S3 de producción) y `.git`. `build-images.yml` publica esa imagen en
  GHCR. Si el repositorio es público —MIT, orientado a que terceros lo autoinstalen— cualquiera
  hace `docker pull` y extrae las claves con `docker save | tar x`. Falsificar un JWT con el
  `JWT_SECRET` obtenido permite suplantar al `owner` de cualquier organización.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:53` — "Create: `apps/api/Dockerfile` (multi-stage con uv…)"
    — no hay `.dockerignore` en la lista
  - `phase-04-frontend-angular-y-theming.md:55` — "Create: `apps/web/Dockerfile`" — ídem
  - `phase-01-monorepo-y-entorno.md:26-27` — se crea `.gitignore` y
    `infra/env/.env.example` + `infra/seaweedfs/s3.json.example`, pero ningún `.dockerignore`
  - `phase-05-documentacion-y-ci.md:32` — "build-images.yml: build y push de `api` y `web` a
    GHCR en `main` y tags" — sin paso de verificación de contenido
  - `phase-05-documentacion-y-ci.md:16` — el `docker-compose.prod.yml` se enumera sin decir cómo
    se inyectan los secretos
  - `phase-01-monorepo-y-entorno.md:17` — el requisito no funcional es solo "sin secretos en el
    repo", que no cubre el contenido de la imagen
  - `docs/prd.md:199` — licencia MIT / proyecto abierto: el registro y el repo son públicos
- **Suggested fix:** Añadir `.dockerignore` (raíz y por app) a la Fase 2 y 4, con
  `.git`, `infra/env/*`, `**/.env*`, `**/*.json` de credenciales y `plans/`. En la Fase 5:
  secretos por variables del runtime o `docker secrets`, `env_file` fuera del contexto de build,
  y un paso de CI que falle si la imagen contiene `.env` o `.git`. Documentar la generación de
  `JWT_SECRET` (`openssl rand -hex 32`) en `docs/desarrollo.md`.

---

## Finding 8: Comportamiento indefinido del contexto RLS cuando no hay organización fijada

- **Severity:** High
- **Location:** Fase 2, "Architecture" (`get_db`) y "Risk Assessment"; Fase 3,
  "Implementation Steps" paso 3
- **Flaw:** `get_db` fija `app.organization_id` **solo "si hay organización resuelta"**, y la
  política se apoya en `current_setting('app.organization_id', true)`, que devuelve `NULL` o
  cadena vacía cuando no se ha fijado. El plan no define qué debe pasar entonces: ni fail-closed
  explícito, ni error controlado. Con `''::uuid` Postgres lanza `invalid input syntax` (error 500
  en cada consulta); con `NULL` la comparación es `NULL` y devuelve cero filas de forma
  silenciosa. Ninguna de las dos ramas está en los criterios de éxito.
- **Failure scenario:** Dos consecuencias opuestas y ambas malas. (1) Ruta silenciosa: un job de
  Taskiq (worker sin petición HTTP, por tanto sin `Host`) escribe o lee sin contexto; las
  lecturas devuelven vacío y los `INSERT` fallan el `WITH CHECK` en tiempo de ejecución, en
  producción, no en tests. (2) Ruta ruidosa: cualquier petición a un endpoint que no requiere
  tenant, ejecutada sobre una tabla con política, revienta con 500 y el manejador
  `problem+json` puede filtrar el mensaje de Postgres. Además, el test propuesto para el pool
  ("dos sesiones consecutivas") es secuencial y no prueba el escenario que el PRD marca como
  riesgo: concurrencia sobre el pool async.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:41` — "si hay organización resuelta, ejecuta `SET LOCAL
    app.organization_id = :id`"
  - `phase-02-backend-fastapi-base.md:79` — el riesgo registrado es solo "`SET LOCAL` fuera de
    transacción no tiene efecto"; no cubre "sin `SET LOCAL` en absoluto"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:56` — "función SQL `app_current_organization()`
    que lee `current_setting('app.organization_id', true)`" — sin definir el caso vacío
  - `phase-03-multi-tenant-rls-y-modelos-base.md:76` — "test que abre dos sesiones **consecutivas**"
  - `phase-02-backend-fastapi-base.md:62` — el worker Taskiq no tiene resolución de tenant descrita
  - `docs/prd.md:276` — "Fuga de datos entre organizaciones (**RLS + pool async**)"
  - `docs/investigacion.md:49` — "Riesgo conocido: RLS + pool async exige tests de aislamiento
    automatizados desde el primer sprint"
- **Suggested fix:** Definir `app_current_organization()` para devolver `NULL` ante cadena vacía
  (`NULLIF(current_setting(...,true),'')::uuid`) y que las políticas sean fail-closed; añadir un
  contexto explícito para tareas Taskiq (`with organization_context(org_id)`) y prohibir
  consultas de dominio sin él; sustituir el test secuencial por uno **concurrente**
  (`asyncio.gather` de N peticiones alternando organizaciones sobre el mismo pool) que compruebe
  que ninguna respuesta contiene datos de la otra.

---

## Finding 9: Rate limiting por debajo de lo que exige el PRD y sin identificación fiable del cliente

- **Severity:** High
- **Location:** Fase 2, "Implementation Steps" paso 9; Fase 5, "Architecture" (Caddy)
- **Flaw:** El plan limita el rate limiting a "global suave en `/auth/*`", cuando el PRD lo
  exige en **endpoints públicos** en general; y no define cómo se identifica al cliente detrás
  de Caddy. `fastapi-limiter` usa por defecto la IP del socket, que tras el proxy es la del
  propio proxy.
- **Failure scenario:** (a) Tras Caddy, todas las peticiones comparten la IP del contenedor
  proxy: o bien el límite no distingue clientes y un solo atacante agota la cuota de **todos**
  los usuarios (denegación de servicio trivial), o bien se sube tanto el umbral que deja de
  proteger el login contra fuerza bruta / password spraying. (b) `GET /api/v1/tenant/branding`
  es público y sin límite; con SSR consultándolo en cada render, es un amplificador directo
  contra la base de datos. (c) Si Redis no está disponible, el plan no dice si el limitador
  falla abierto (sin protección) o cerrado (caída total).
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:65` — "rate limiting global **suave** en `/auth/*`"
  - `phase-02-backend-fastapi-base.md:16` — "`GET /api/v1/tenant/branding` público"
  - `phase-05-documentacion-y-ci.md:16` — Caddy como reverse proxy delante de api y web, sin
    mención de cabeceras de proxy ni de `forwarded_allow_ips` en uvicorn
  - `docs/prd.md:191` — "Turnstile y **rate limiting en endpoints públicos**"
  - `docs/investigacion.md:64` — "Rate limiting | fastapi-limiter (Redis)"
- **Suggested fix:** Especificar en la Fase 2 la clave del limitador (IP real obtenida de
  `X-Forwarded-For` **solo** cuando el peer está en `forwarded_allow_ips`), límites concretos y
  distintos para `/auth/login` (por IP y por email), `/auth/refresh` y endpoints públicos, y el
  comportamiento ante Redis caído (fail-closed en `/auth/*`). Documentar en Fase 5 las cabeceras
  que Caddy debe fijar y las que debe **borrar** del cliente (`X-Forwarded-*`, `X-Organization-Slug`).

---

## Finding 10: CI sin auditoría de dependencias ni detección de secretos, en un proyecto que se distribuye para autoinstalación

- **Severity:** Medium
- **Location:** Fase 5, "Requirements" e "Implementation Steps" pasos 1-2
- **Flaw:** El workflow de CI descrito cubre lint, tipos, tests, build y a11y, pero no incluye
  ningún control de cadena de suministro: sin `pip-audit`/`uv` audit, sin `pnpm audit`, sin
  instalación con lockfile congelado (`--frozen-lockfile`), sin escaneo de secretos ni escaneo
  de las imágenes que se publican en GHCR. La Fase 4 además ejecuta `pnpm dlx
  @angular/cli@latest`, que resuelve una versión no determinista en el momento del scaffolding.
- **Failure scenario:** Una dependencia transitiva de Angular o de la cadena de build recibe una
  publicación maliciosa (patrón ya visto repetidamente en npm). Sin `--frozen-lockfile` en CI ni
  auditoría, el postinstall se ejecuta en el runner que **tiene credenciales de push a GHCR**, y
  la imagen comprometida se publica como release oficial de un proyecto MIT pensado para que
  terceros lo instalen. El plan no tiene ninguna puerta que lo detecte.
- **Evidence:**
  - `phase-05-documentacion-y-ci.md:16` — jobs `api` ("uv, ruff, mypy, pytest…") y `web`
    ("pnpm, lint, test con axe, build SSR, verificación de tipos generados"): ninguna auditoría
  - `phase-05-documentacion-y-ci.md:31-32` — pasos de CI y push a GHCR sin escaneo
  - `phase-04-frontend-angular-y-theming.md:59` — "`pnpm dlx @angular/cli@latest new web`"
  - `phase-02-backend-fastapi-base.md:57` — "`pyproject.toml` con rangos de versión"
  - `plan.md:38` — "Lockfiles versionados" (se versionan, pero nada obliga a CI a respetarlos)
  - `docs/prd.md:278` — mitigación declarada: "Interfaces de abstracción, **versiones fijadas**"
  - `docs/investigacion.md:58` — "rango pineado, `uv` + lockfile… no seguir 'latest' sin CI"
  - `docs/prd.md:44` — objetivo de calidad open source: "CI verde, cobertura de tests de
    aislamiento multi-tenant, docs…"
- **Suggested fix:** Añadir al `ci.yml` de la Fase 5: `uv sync --frozen` / `pnpm install
  --frozen-lockfile`, `pip-audit` y `pnpm audit --audit-level=high` como pasos bloqueantes,
  `gitleaks` o el secret scanning de GitHub, y escaneo de la imagen (Trivy/Grype) antes del push
  a GHCR. Fijar la versión mayor del Angular CLI en la Fase 4 en lugar de `@latest`.

---

## Nota de alcance (contexto, no finding independiente)

`plan.md:19` afirma "**Sin funcionalidad de negocio**", pero la Fase 3 entrega organizaciones,
branding con subida de logo, roles, campos de perfil, membresías y usuarios
(`phase-03-multi-tenant-rls-y-modelos-base.md:16`), que es literalmente el contenido de la
**fase 1 del PRD** (`docs/prd.md:255`: "Organizaciones, branding, plantillas, roles y campos de
perfil, usuarios"). Esto importa para seguridad porque arrastra endpoints de escritura con
implicaciones de autorización (Finding 1) y de subida de ficheros (Finding 4) a una fase cuyo
modelo de permisos se declara todavía "interfaz + implementación mínima"
(`phase-02-backend-fastapi-base.md:63`). O se reduce la Fase 3 al mínimo verificable para RLS
(organizaciones + membresías de solo lectura + seed), o se reconoce que absorbe la fase 1 del
PRD y se le exigen las mismas garantías de autorización.
