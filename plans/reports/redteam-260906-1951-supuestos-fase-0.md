# Red team — Destrucción de supuestos: Fase 0 (scaffolding)

Fecha: 2026-09-06 · Perspectiva: **Assumption Destroyer** (escéptico) · Rol de verificación: **fact checker**
Objeto: `plans/260906-1951-fase-0-scaffolding/` (plan.md + fases 1-5)
Fuentes de contraste: `docs/prd.md`, `docs/investigacion.md`, `plans/reports/researcher-260906-1806-tecnica-stack-eventos.md`

Sin código en el repo: toda la evidencia son citas `fichero:línea` de plan, PRD e investigación.

---

## Finding 1: El modelo de roles del sistema queda sin decidir y el esquema se contradice a sí mismo

- **Severity:** Critical
- **Location:** Fase 3, "Architecture → Esquema" y "Risk Assessment"
- **Flaw:** El plan deja explícitamente sin cerrar la decisión estructural entre **roles del sistema compartidos** (`organization_id NULL`) y **roles clonados por organización**, pero al mismo tiempo ya escribe un esquema, un seed, unas políticas RLS y unos criterios de éxito que solo son coherentes con la variante compartida. Peor: dentro de la misma fase, el DDL de `role_profile_fields` **no tiene columna `organization_id`** (`phase-03:33-34`) y tres líneas después el texto afirma que "`role_profile_fields` lleva `organization_id NULL`" (`phase-03:38`). Es una fase P1 de 2 días cuyo artefacto central (migraciones `0002` y `0003`) no está determinado.
- **Failure scenario:** El implementador sigue la recomendación ("preferir la clonación") y escribe `roles.organization_id NOT NULL`. Al instante quedan inválidos: (a) la definición `roles … organization_id NULL (NULL = rol del sistema)` de `phase-03:30`, (b) el seed de "5 roles del sistema" descrito en `phase-03:16` y en `plan.md:33` (pasarían a ser 5 roles **por organización**, creados en el alta de organización, no en el seed), (c) la unicidad `UNIQUE(organization_id, key)` con `organization_id` nulo, que en PostgreSQL **no** impide duplicados si se elige la variante compartida, y (d) el criterio "añadir campo a `speaker` en la organización → OK" (`phase-03:72`), que en la variante compartida requiere una política RLS con `OR organization_id IS NULL` —justo el antipatrón que el propio plan marca como señal de alarma (`phase-03:75`). Resultado: retrabajo de las dos migraciones y del seed a mitad de fase, o —peor— una migración `0002` ya aplicada en entornos y un `0004` correctivo.
- **Evidence:**
  - `plans/260906-1951-fase-0-scaffolding/phase-03-multi-tenant-rls-y-modelos-base.md:38` — "**Decidir en implementación; preferir la clonación**"
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:30` — "roles  id, organization_id NULL (NULL = rol del sistema)"
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:33-34` — DDL de `role_profile_fields` sin `organization_id`, frente a `:38` "`role_profile_fields` lleva `organization_id NULL`"
  - `plan.md:33` — "Seed de los 5 roles del sistema con sus `role_profile_fields`"
  - `docs/prd.md:66` — "no se pueden borrar … La organización puede añadir campos a estos roles, pero no quitar los básicos" (requisito que cambia de mecanismo de aplicación según la variante)
- **Suggested fix:** Cerrar la decisión **antes** de arrancar la fase 3 (clonación por organización, coherente con "RLS uniforme"), reescribir el bloque de esquema con `roles.organization_id NOT NULL`, `role_profile_fields.organization_id NOT NULL`, mover la creación de roles del seed a un servicio `provision_organization()` y ajustar los criterios de éxito. Añadir `is_system` + `key` como base del 409 al borrar.

---

## Finding 2: Con `FORCE ROW LEVEL SECURITY` y sin ruta de bypass definida, el seed y el alta de organizaciones son imposibles

- **Severity:** Critical
- **Location:** Fase 3, "Requirements" / "Implementation Steps" paso 10; Fase 2, "Architecture"
- **Flaw:** La fase 3 exige `FORCE ROW LEVEL SECURITY` (afecta también al propietario de la tabla) y políticas `WITH CHECK (organization_id = current_setting('app.organization_id')::uuid)` para INSERT. El seed (`make db-seed`) debe crear la **primera** organización, cuando por definición **no existe todavía** un `app.organization_id` que fijar. El plan nunca define con qué rol ni con qué contexto corre el seed ni el futuro alta de organizaciones; `phase-02:42` solo distingue rol de aplicación y rol de migraciones (Alembic), y `phase-02:41` fija el GUC únicamente "si hay organización resuelta".
- **Failure scenario:** `make db-seed` ejecuta `INSERT INTO organizations …` con el rol de aplicación sin GUC fijado: la política `WITH CHECK` evalúa `current_setting('app.organization_id')` sin valor → error `42704 unrecognized configuration parameter` (o violación de política si se usa la variante `missing_ok`), y el seed peta. Se cae el criterio de éxito `plan.md:107` y en cascada el `plan.md:111`, `phase-03:68`, `phase-03:72` y el login de la fase 4 (`phase-04:75`). La reacción típica bajo presión es el atajo peligroso: dar `BYPASSRLS` al rol de aplicación, que anula todo el objetivo de la fase y contradice `plan.md:27`.
- **Evidence:**
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:17` — "RLS activada con `FORCE ROW LEVEL SECURITY`"
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:41` — "política `USING (…)` para SELECT/UPDATE/DELETE y `WITH CHECK` para INSERT/UPDATE"
  - `…/phase-02-backend-fastapi-base.md:41` — "`get_db` … **si hay organización resuelta**, ejecuta `SET LOCAL app.organization_id`"
  - `…/plan.md:107` — "`alembic upgrade head` + `make db-seed` crean organización demo…"
  - `docs/prd.md:190` — "RLS en PostgreSQL fijada por transacción en un único punto"
- **Suggested fix:** Definir explícitamente el camino de escritura sin tenant: un tercer rol/contexto de administración (o `SET LOCAL app.bypass='on'` concedido solo a una sesión CLI que **no** sea la del rol web) y una política `USING (… OR current_setting('app.bypass', true) = 'on')` con test que verifique que el rol de la API **no puede** activar ese GUC. Documentarlo como paso de fase 3, no como detalle de implementación.

---

## Finding 3: `users` y `user_social_links` quedan fuera de RLS — fuga de PII entre organizaciones por diseño

- **Severity:** High
- **Location:** Fase 3, "Architecture → RLS"
- **Flaw:** El plan declara `users` como tabla global sin RLS y no menciona `user_social_links` en ninguna política. Simultáneamente, la propia fase 3 institucionaliza consultas **sin filtro por organización** (paso 6) apoyándose en que "RLS protege". En `users` no protege nada: no hay política.
- **Failure scenario:** Endpoint `GET /api/v1/organizations/me/members` (o cualquier búsqueda de usuario por email para invitar a un miembro) hace un `JOIN`/lookup sobre `users` sin `EXISTS (membresía en la organización actual)`. La organización A obtiene nombre, email y avatar de usuarios que solo pertenecen a la organización B. Es exactamente el riesgo que el PRD registra como riesgo #1 (`prd.md:276`) y que el plan afirma cubrir con "aislamiento demostrado por tests automáticos" (`plan.md:46`) — pero el test descrito (`phase-03:64`) solo prueba tablas con `organization_id`, así que **CI se pone en verde con la fuga presente**. Contradice además `prd.md:190`, que exige `organization_id` + RLS en toda tabla de dominio, y la minimización RGPD de `prd.md:192`.
- **Evidence:**
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:41` — "`users` es global (sin RLS) y se accede a través de membresías"
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:28-29` — `users … email*, full_name, avatar_object_key`; `user_social_links` sin `organization_id` ni política
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:59` — "consultas sin filtro manual por organización **deliberadamente**"
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:64` — el test de aislamiento cubre "dos organizaciones … consulta sin WHERE" (tablas con `organization_id`), no `users`
  - `docs/prd.md:190` — "`organization_id` en toda tabla de dominio + Row-Level Security"
- **Suggested fix:** O bien una política RLS en `users` basada en `EXISTS (SELECT 1 FROM organization_members m WHERE m.user_id = users.id AND m.organization_id = app_current_organization())`, o bien una regla dura de arquitectura: **ningún repositorio accede a `users` sin pasar por `organization_members`**, con test negativo que lo demuestre (usuario huérfano en B invisible desde A). Añadir ese caso a `test_rls_isolation.py` como criterio de éxito de la fase 3.

---

## Finding 4: La política RLS y la función de contexto usan variantes incompatibles de `current_setting` → 500 en vez de aislamiento

- **Severity:** High
- **Location:** Fase 3, "Architecture → RLS" vs "Implementation Steps" paso 3; Fase 2, "Architecture"
- **Flaw:** `phase-03:41` escribe la política con `current_setting('app.organization_id')::uuid` (sin `missing_ok`), mientras que `phase-03:56` define la función `app_current_organization()` con `current_setting('app.organization_id', true)`. Las dos variantes fallan de forma distinta y ninguna está definida para el caso "sin tenant": la primera lanza `42704`, la segunda devuelve `''` y revienta al castear a `uuid` (`22P02`). Y `phase-02:41` garantiza que ese caso ocurre: el GUC solo se fija "si hay organización resuelta".
- **Failure scenario:** Petición con `Host` no registrado (health checks de Caddy, curl a la IP, un dominio aún no dado de alta, o el `Host` de un test). `get_db` no fija el GUC; el primer `SELECT` sobre una tabla con RLS devuelve un **500 con traza de PostgreSQL**, no un 404 limpio. Doble impacto: indisponibilidad y filtración de detalles internos al consumidor externo, contra `prd.md:191` (ASVS L2). El propio plan preveía "404 en `/tenant/branding`" como señal (`phase-02:81`), lo que muestra que la ruta de error esperada no coincide con la real.
- **Evidence:**
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:41` — "`USING (organization_id = current_setting('app.organization_id')::uuid)`"
  - `…/phase-03-multi-tenant-rls-y-modelos-base.md:56` — "función SQL `app_current_organization()` que lee `current_setting('app.organization_id', true)`"
  - `…/phase-02-backend-fastapi-base.md:41` — "si hay organización resuelta, ejecuta `SET LOCAL`"
  - `…/phase-02-backend-fastapi-base.md:81` — "señal: 404 en `/tenant/branding`"
  - `docs/prd.md:191` — "OWASP ASVS nivel 2 como referencia"
- **Suggested fix:** Una sola forma: todas las políticas invocan `app_current_organization()`, que devuelve `NULL` con `nullif(current_setting('app.organization_id', true), '')::uuid`; con `NULL` la política no casa y devuelve 0 filas. Y en `core/tenant.py`, host no resuelto ⇒ 404 explícito antes de tocar la BD. Añadir test: petición con `Host` desconocido → 404, no 500.

---

## Finding 5: La fase 4 se declara paralelizable con la 3, pero cuatro de sus seis criterios de éxito requieren la fase 3

- **Severity:** High
- **Location:** plan.md, "Phases → Dependencias"; Fase 4, "Success Criteria"
- **Flaw:** `plan.md:61` afirma "4 depende de 2 … 3 y 4 pueden ejecutarse en paralelo", y `phase-04:7` declara `dependencies: [2]`. Pero la fase 2 sirve branding **por defecto**, no real (`phase-02:64`), y no existe seed, ni tabla `organization_branding`, ni subida de logo hasta la fase 3.
- **Failure scenario:** Se lanzan 3 y 4 en paralelo (que es el atractivo declarado del plan para caber en 6-8 días). Al cerrar la fase 4, sus criterios "cambiar `colors.primary` en BD y recargar cambia el color", "login del seed → dashboard" y "logo servido desde SeaweedFS" son **imposibles de evaluar**: no hay BD con branding, ni usuario de seed, ni logo. La fase 4 se marca "hecha" con tres criterios no verificados, y el fallo aparece al integrar. Agravante de tipos: `make api-types` genera el cliente contra el OpenAPI de la fase 2 (`phase-04:61`), y la fase 3 añade `organizations`, `roles`, `members`, `users` y cambia `tenant/branding`; con la puerta de CI `git diff --exit-code` sobre los tipos generados (`phase-04:84`, `phase-05:31`), **cada merge de la fase 3 rompe el CI de la rama de la fase 4**.
- **Evidence:**
  - `…/plan.md:61` — "3 y 4 pueden ejecutarse en paralelo"
  - `…/phase-02-backend-fastapi-base.md:64` — "`tenant/branding` devuelve branding por defecto hasta la fase 3"
  - `…/phase-04-frontend-angular-y-theming.md:73,75,76` — "Cambiar `colors.primary` en BD…", "login del seed → dashboard", "Logo servido desde SeaweedFS"
  - `…/phase-04-frontend-angular-y-theming.md:84` — "`make api-types` en CI compara con el commit (`git diff --exit-code`)"
- **Suggested fix:** O declarar `dependencies: [2, 3]` en la fase 4, o partirla: 4a (scaffolding Angular, tokens, auth, a11y — verificable con mocks y contrato congelado) y 4b (integración con branding/seed real), con los cuatro criterios dependientes movidos a 4b. Congelar el contrato `Branding` en la fase 2 como schema Pydantic definitivo para que la generación de tipos no derive.

---

## Finding 6: El almacenamiento del refresh token se decide "según lo que soporte el backend", con `localStorage` como plan B — contra el ASVS L2 del PRD

- **Severity:** High
- **Location:** Fase 4, "Architecture → Auth"; Fase 2, "Architecture"
- **Flaw:** La fase 4 planifica contra un contrato inexistente: "refresh en cookie `HttpOnly` **si el backend lo soporta**, si no en `localStorage`". La fase 2, que es quien define el backend, nunca dice si el refresh viaja en cookie o en cuerpo; solo menciona rotación y lista de revocación en Redis. La decisión de seguridad más importante de la autenticación queda como consecuencia accidental del orden de implementación.
- **Failure scenario:** La fase 2 se implementa primero devolviendo el refresh en el JSON de `/auth/login` (lo más rápido con `httpx.AsyncClient` en tests). La fase 4 aplica el fallback y guarda un credencial de larga vida en `localStorage`. Cualquier XSS —en una app que después renderizará descripciones de evento, blurbs de organizador y enlaces de ponentes suministrados por usuarios— exfiltra sesiones persistentes de administradores de organización. Contradice `prd.md:191` ("OWASP ASVS nivel 2 como referencia"; ASVS prohíbe almacenar tokens de sesión en almacenamiento accesible por JS) y deja el scaffolding con una decisión de seguridad que las fases 1-9 heredan sin revisión.
- **Evidence:**
  - `…/phase-04-frontend-angular-y-theming.md:42` — "refresh en cookie `HttpOnly` si el backend lo soporta, si no en `localStorage` con rotación"
  - `…/phase-02-backend-fastapi-base.md:43` — "Refresh tokens con rotación y lista de revocación en Redis (`logout`)" (sin definir transporte)
  - `…/phase-02-backend-fastapi-base.md:16` — contrato de `/auth/login|refresh|logout` sin mención de cookies
  - `docs/prd.md:191` — "OWASP ASVS nivel 2 como referencia"
- **Suggested fix:** Cerrarlo en la fase 2: refresh **siempre** en cookie `HttpOnly; Secure; SameSite=Lax`, path acotado a `/api/v1/auth`, con CSRF por doble envío o `SameSite=Strict` para `/auth/refresh`; access token en memoria. Eliminar el fallback de `localStorage` del plan y añadir test que verifique la cabecera `Set-Cookie` y la ausencia del refresh en el cuerpo.

---

## Finding 7: El requisito de accesibilidad del PRD se sustituye por un umbral más débil, y el plan usa dos umbrales distintos

- **Severity:** High
- **Location:** plan.md, "Success Criteria"; Fase 4, "Success Criteria"; Fase 5, "Requirements"
- **Flaw:** El PRD exige **WCAG 2.1 AA en toda la aplicación** con "auditoría automática (axe) en CI **y revisión manual por fase**". El plan reduce el requisito a violaciones de axe y, además, no es consistente consigo mismo: `plan.md:112` dice "sin violaciones críticas" y `phase-04:77` dice "0 violaciones críticas/serias". Ninguna fase programa la revisión manual. axe detecta como mucho ~30-40 % de los criterios WCAG y **no** cubre orden de foco, gestión de foco al navegar, contraste sobre imágenes ni etiquetado de errores de formulario.
- **Failure scenario:** La fase 5 se cierra con CI en verde y "auditoría a11y" marcada. En la fase 1-3 del PRD (branding, eventos, inscripción) se construyen formularios y modales sobre unos `shared/ui` que nunca pasaron revisión manual; el defecto (p. ej. trampa de foco en el modal, o contraste del color primario del organizador contra `surface`) se propaga a toda la app y sale a la luz en la auditoría real, con coste de rediseño de tokens. Nota adicional: el criterio "contraste verificado para la paleta **por defecto**" (`phase-04:43`) es insuficiente por construcción — el branding es definible por cada organización, así que la conformidad AA depende de datos de usuario y el plan no prevé ninguna validación de contraste en el guardado del branding.
- **Evidence:**
  - `docs/prd.md:195` — "**WCAG 2.1 AA en toda la aplicación** … auditoría automática (axe) en CI **y revisión manual por fase**"
  - `…/plan.md:112` — "auditoría axe sin violaciones críticas"
  - `…/phase-04-frontend-angular-y-theming.md:77` — "0 violaciones axe críticas/serias"
  - `…/phase-04-frontend-angular-y-theming.md:43` — "contraste verificado para la paleta por defecto"
  - `…/phase-05-documentacion-y-ci.md:41` — CI "falla si se rompe … a11y" (sin definir el umbral)
- **Suggested fix:** Un único umbral explícito (0 violaciones axe de cualquier impacto en `shared/ui` y shells, con lista de excepciones justificadas), añadir a la fase 4 un paso de revisión manual con teclado y lector de pantalla y su checklist en `CONTRIBUTING.md`, y añadir validación de ratio de contraste (APCA o WCAG 2.x) en el servicio de branding para que un organizador no pueda guardar una paleta que incumpla AA.

---

## Finding 8: El job `web` del CI consume un artefacto que el job `api` no está planificado para producir, y se describe como matriz sin dependencia

- **Severity:** Medium
- **Location:** Fase 5, "Architecture" e "Implementation Steps" paso 1
- **Flaw:** El paso 1 describe "matriz de dos jobs" y a la vez exige que el job `web` genere tipos "contra un `openapi.json` exportado por el job `api` (artefacto)". Una matriz en GitHub Actions ejecuta variantes **en paralelo, sin `needs:`**, y los pasos enumerados del job `api` (`alembic upgrade head` + `pytest`) no incluyen ninguna exportación del `openapi.json`.
- **Failure scenario:** Primer PR: el job `web` arranca simultáneamente al `api`, `actions/download-artifact` falla porque el artefacto no existe (ni existiría, porque nadie lo sube), y la puerta de calidad de deriva de tipos —el mecanismo que sostiene el criterio "falla si … se rompen los tipos generados" (`phase-05:41`)— queda rota o se desactiva para desbloquear el merge. Con ella desaparece la única defensa contra la deriva contrato ↔ frontend que la fase 4 identificaba como riesgo (`phase-04:84`).
- **Evidence:**
  - `…/phase-05-documentacion-y-ci.md:31` — "matriz de dos jobs; `api` ejecuta `alembic upgrade head` + `pytest` …; `web` ejecuta `make api-types` contra un `openapi.json` exportado por el job `api` (artefacto)"
  - `…/phase-05-documentacion-y-ci.md:16` — descripción de los jobs, sin paso de exportación de OpenAPI
  - `…/phase-05-documentacion-y-ci.md:41` — "CI en verde … falla si se rompe … tipos generados"
- **Suggested fix:** Dos jobs con `needs: api` (no matriz), paso explícito en `api` que genere el `openapi.json` sin levantar servidor (`python -c "…app.openapi()"`) y lo suba como artefacto; y committear `openapi.json` en el repo para que la comparación `git diff --exit-code` sea reproducible en local con `make api-types`.

---

## Finding 9: La política de lectura pública en SeaweedFS es un supuesto no verificado y bloquea el arranque del entorno

- **Severity:** Medium
- **Location:** Fase 1, "Architecture" y "Implementation Steps" paso 2
- **Flaw:** El plan da por hecho que un contenedor `storage-init` con `amazon/aws-cli` o `minio/mc` puede crear el bucket **y una política de lectura pública** para `media/public/*` contra el endpoint S3 de SeaweedFS. SeaweedFS implementa un subconjunto de la API S3; el acceso anónimo se configura típicamente mediante la identidad `anonymous` en `s3.json`, no vía `PutBucketPolicy`. La investigación advierte explícitamente de que las versiones y capacidades deben re-verificarse al iniciar el scaffolding.
- **Failure scenario:** `storage-init` sale con código ≠ 0 al aplicar la política; con `depends_on: service_healthy` encadenado, `docker compose up -d` no llega al estado "todos healthy" y falla el primer criterio de éxito del plan (`plan.md:105`, `phase-01:38`) en la primerísima fase. Segundo problema, más silencioso: el plan mantiene a la vez `S3_PUBLIC_BASE_URL` (servido público directo) y "presigned URLs" (`plan.md:29`, alineado con `prd.md:210`), y el criterio de éxito de la fase 4 acepta **cualquiera de los dos** ("URL pública/presignada"), de modo que el criterio no puede fallar y no prueba nada: se puede cerrar la fase con logos servidos por una ruta pública no prevista por el PRD o con un bucket entero público.
- **Evidence:**
  - `…/phase-01-monorepo-y-entorno.md:22` — "contenedor `storage-init` … crea el bucket `media` y **política de lectura pública** para `media/public/*`"
  - `…/phase-01-monorepo-y-entorno.md:33` — variable `S3_PUBLIC_BASE_URL`
  - `…/phase-04-frontend-angular-y-theming.md:76` — "Logo servido desde SeaweedFS mediante URL **pública/presignada**"
  - `docs/prd.md:210` — "SeaweedFS por defecto tras interfaz `StorageProvider` … **Presigned URLs**"
  - `docs/investigacion.md:139` — "Cifras de rendimiento y versiones proceden de fuentes de terceros; **re-verificar versiones al iniciar el scaffolding**"
- **Suggested fix:** Verificar contra la documentación de la versión fijada de SeaweedFS antes de escribir el compose; si no soporta `PutBucketPolicy`, configurar el acceso anónimo en `s3.json` y no vía `mc`. Y elegir **una** estrategia de servido (presigned GET por defecto, según el PRD) y reescribir el criterio de la fase 4 en términos falsables: "el `<img>` del logo carga con 200 desde una URL presignada con caducidad ≤ N".

---

## Finding 10: Estimaciones sin margen para los riesgos que el propio plan declara abiertos, y criterios de éxito no verificables

- **Severity:** Medium
- **Location:** plan.md, frontmatter `effort`; Fase 2 y Fase 4, frontmatter y "Risk Assessment"; Fase 5, "Success Criteria"
- **Flaw:** El total declarado (6-8 d) coincide con la suma exacta de fases (0,5 + 1,5 + 2 + 2 + 1 = 7 d), es decir, **cero margen**. La fase 2 asigna 1,5 días a: proyecto FastAPI con `mypy --strict`, config tipada, engine async, Argon2 + JWT con rotación de refresh y revocación en Redis, `StorageProvider` con cuatro operaciones y presigned URLs, broker Taskiq + worker, resolución de tenant, rate limiting, handlers `problem+json`, Alembic async con migración de roles de BD, CLI Typer, Dockerfile multi-stage y cinco módulos de test contra PostgreSQL **y SeaweedFS reales**. La fase 4 asigna 2 días incluyendo una integración que el propio plan reconoce como incierta ("Tailwind v4 con Angular CLI: la integración PostCSS varía por versión … fallback a Tailwind v3") y una elección de versión mayor sin cerrar (Angular 22 vs 21). Además, dos criterios de cierre no son verificables por nadie durante la ejecución.
- **Failure scenario:** La integración Tailwind v4 + Angular CLI falla en la versión elegida y se ejecuta el fallback a v3: eso invalida el enfoque `@theme` sobre CSS vars descrito en `phase-04:23`, obliga a reescribir `tokens.css`/`tailwind.css` y la configuración de PostCSS, y consume por sí solo la mitad del presupuesto de la fase. Al no haber margen, la compresión cae sobre lo que no tiene defensa automática: la revisión de accesibilidad y los tests de la fase 3. Y los criterios "una persona ajena levanta el entorno siguiendo solo `docs/desarrollo.md`" y "`docs/desarrollo.md` permite levantar el entorno sin ayuda" no definen quién es esa persona, en qué máquina, ni qué evidencia se registra: en la práctica se marcan solos.
- **Evidence:**
  - `…/plan.md:6` — `effort: "6-8d"`; `phase-02:6` `"1.5d"`; `phase-04:6` `"2d"`
  - `…/phase-02-backend-fastapi-base.md:56-68` — doce pasos de implementación en 1,5 d
  - `…/phase-04-frontend-angular-y-theming.md:81` — "integración PostCSS varía por versión → … **fallback a Tailwind v3**"
  - `…/phase-04-frontend-angular-y-theming.md:83` — "Angular 22 muy reciente rompe dependencias … usar 21 LTS" (versión no cerrada; cf. `researcher-260906-1806-tecnica-stack-eventos.md:88`)
  - `…/phase-05-documentacion-y-ci.md:43` y `…/plan.md:114` — criterios de "tercera persona" sin protocolo
  - `docs/prd.md:278` — riesgo declarado: "Volatilidad de dependencias … **versiones fijadas**"
- **Suggested fix:** Cerrar la versión de Angular y la de Tailwind **antes** de la fase 4 con una prueba de concepto de medio día (fase 0 técnica), fijarlas en el plan, subir la fase 2 a 2,5-3 d y añadir 1,5 d de margen explícito. Convertir el criterio de documentación en algo falsable: "un contenedor/VM limpia ejecuta el `docs/desarrollo.md` como script y `GET /api/v1/health` devuelve `ok` en los tres servicios", verificado en CI nocturno.

---

## Resumen de severidades

| # | Título | Severidad |
|---|---|---|
| 1 | Modelo de roles del sistema sin decidir + esquema contradictorio | Critical |
| 2 | Seed y alta de organizaciones imposibles con `FORCE RLS` sin ruta de bypass | Critical |
| 3 | `users`/`user_social_links` fuera de RLS → fuga de PII entre organizaciones | High |
| 4 | Variantes incompatibles de `current_setting` → 500 en peticiones sin tenant | High |
| 5 | Fase 4 "paralela" a la 3 con criterios de éxito dependientes de la 3 | High |
| 6 | Refresh token: contrato indefinido y fallback a `localStorage` contra ASVS L2 | High |
| 7 | WCAG 2.1 AA del PRD degradado a axe, con umbrales inconsistentes | High |
| 8 | Job `web` del CI consume un artefacto que nadie produce | Medium |
| 9 | Política pública de SeaweedFS no verificada + criterio de logo no falsable | Medium |
| 10 | Estimaciones sin margen frente a riesgos abiertos + criterios no verificables | Medium |
