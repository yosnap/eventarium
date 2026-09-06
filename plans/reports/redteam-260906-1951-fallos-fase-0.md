# Red team — Análisis de modos de fallo del plan «Fase 0 — Scaffolding»

Fecha: 2026-09-06 · Revisor: code-reviewer (perspectiva FAILURE MODE ANALYST / Ley de Murphy)
Ámbito revisado: `plans/260906-1951-fase-0-scaffolding/*.md` contrastado con `docs/prd.md` y `docs/investigacion.md`.
El repositorio no contiene código todavía, así que toda la evidencia son citas a los documentos.

---

## Finding 1: El rol de aplicación se queda sin privilegios sobre las tablas creadas después de la migración 0001

- **Severity:** Critical
- **Location:** Fase 2, "Related Code Files" / "Implementation Steps" paso 10; Fase 3, "Related Code Files"
- **Flaw:** La migración `0001` crea el rol `app_user` y le concede privilegios "sobre el esquema `public`", pero las tablas se crean en `0002` con el rol propietario (`DATABASE_MIGRATIONS_URL`). Un `GRANT` ejecutado en `0001` no alcanza a objetos que aún no existen, y el plan no menciona `ALTER DEFAULT PRIVILEGES` ni un `GRANT` posterior a `0002`/`0003`.
- **Failure scenario:** `alembic upgrade head` termina en verde. La API arranca, `/api/v1/health` puede incluso dar `database: ok` (un `SELECT 1` no toca tablas), y el primer `GET /api/v1/organizations/me` revienta con `permission denied for table organizations`. El fallo aparece en runtime, no en la migración, y sólo en entornos donde app y migraciones usan roles distintos — es decir, no en la máquina del desarrollador si ahí se usa el mismo usuario por comodidad.
- **Evidence:**
  - `plans/260906-1951-fase-0-scaffolding/phase-02-backend-fastapi-base.md:51` — "`alembic/versions/0001_roles_de_base_de_datos.py` (crea rol de aplicación sin BYPASSRLS)"
  - `phase-02-backend-fastapi-base.md:66` — "migración `0001` que crea el rol de aplicación (`app_user`) sin `BYPASSRLS` y concede privilegios sobre el esquema `public`"
  - `phase-02-backend-fastapi-base.md:42` — "Dos URLs de BD: `DATABASE_URL` (rol de aplicación…) y `DATABASE_MIGRATIONS_URL` (rol propietario para Alembic)"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:48` — "`0002_esquema_base.py`, `0003_politicas_rls.py`"
- **Suggested fix:** Añadir a `0001` `ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO app_user` (y secuencias), y cerrar `0003` con un `GRANT` explícito sobre las tablas de `0002`. Criterio de éxito verificable: un test que conecte **como `app_user`** y ejecute un CRUD real sobre cada tabla nueva.

---

## Finding 2: `CREATE ROLE` dentro de Alembic hace irreversible el `downgrade` que el propio plan exige como criterio de éxito

- **Severity:** High
- **Location:** Fase 2, "Success Criteria" + paso 10; Fase 3, "Success Criteria"
- **Flaw:** Los roles de PostgreSQL son objetos de **clúster**, no de base de datos, y no son transaccionalmente equivalentes al resto de la migración. `DROP ROLE` falla si el rol posee objetos, tiene privilegios concedidos o hay sesiones abiertas. El plan exige `downgrade base` limpio sin resolver nada de esto, y tampoco dice de dónde sale la contraseña del rol (si va en el fichero de migración, es un secreto en el repositorio, contra la regla no funcional de la Fase 1).
- **Failure scenario:** En CI o en un entorno compartido, `alembic downgrade base` falla con `role "app_user" cannot be dropped because some objects depend on it`, o peor: pasa a medias dejando el clúster con el rol huérfano y los siguientes `upgrade` fallando por `role already exists`. En una máquina de desarrollo con la API corriendo, el `DROP ROLE` falla por sesiones activas del pool.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:76` — "[ ] `alembic upgrade head` / `downgrade base` funcionan con `DATABASE_MIGRATIONS_URL`"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:67` — "[ ] `alembic upgrade head` crea esquema y políticas; `downgrade` limpio"
  - `phase-01-monorepo-y-entorno.md:17` — "sin secretos en el repo"
- **Suggested fix:** Sacar la creación del rol de Alembic a un script de aprovisionamiento (`infra/scripts/bootstrap-db.sql` invocado por el init de Compose y por CI), idempotente (`DO $$ … IF NOT EXISTS`), con la contraseña desde variable de entorno. Dejar en Alembic sólo esquema, políticas y GRANTs.

---

## Finding 3: El seed no puede escribir con RLS activa y no se define su idempotencia

- **Severity:** Critical
- **Location:** Fase 3, "Implementation Steps" paso 10 + "Success Criteria"; Fase 1, `Makefile` target `db-seed`
- **Flaw:** El seed crea la **primera** organización. Con `FORCE ROW LEVEL SECURITY` y la política de `organizations` filtrando por `id = current_setting('app.organization_id')`, no existe todavía ningún valor válido que fijar: el `INSERT` inicial es imposible bajo el rol de aplicación. El plan no dice con qué rol corre el seed ni cómo se bootstrappea el primer tenant. Tampoco exige idempotencia en ninguna parte.
- **Failure scenario:** (a) Arranque en limpio: `make db-seed` falla con `new row violates row-level security policy for table "organizations"` y el proyecto no arranca — justo el criterio de éxito global del plan. (b) Si se resuelve conectando el seed como propietario, la segunda ejecución de `make db-seed` (que cualquiera hará tras un `git pull`) revienta con violación de `UNIQUE(organization_id, key)` en roles o de email único en `users`, dejando la transacción a medias y datos demo inconsistentes.
- **Evidence:**
  - `phase-03-multi-tenant-rls-y-modelos-base.md:41` — "`ENABLE + FORCE ROW LEVEL SECURITY` … `organizations` filtra por `id`"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:63` — "10. Seed demo." (sin más detalle)
  - `phase-03-multi-tenant-rls-y-modelos-base.md:68` — "[ ] `make db-seed` deja datos demo; login del owner OK"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:31,35` — "UNIQUE(organization_id, key)", "UNIQUE(org, user, role)"
  - `plan.md:107` — "`alembic upgrade head` + `make db-seed` crean organización demo…"
- **Suggested fix:** Especificar que el seed usa `DATABASE_MIGRATIONS_URL` (rol propietario, con `SET row_security = off` explícito o exención declarada), que es **idempotente** por `ON CONFLICT DO NOTHING`/upsert sobre claves naturales (`slug`, `host`, `email`, `(organization_id, key)`), y añadir criterio de éxito: "ejecutar `make db-seed` dos veces seguidas termina en verde y no duplica filas".

---

## Finding 4: El bypass de superadmin por variable de sesión es una puerta trasera sin control de acceso

- **Severity:** Critical
- **Location:** Fase 3, "Architecture → RLS"
- **Flaw:** `SET LOCAL app.bypass = 'on'` verificado dentro de la política convierte una GUC personalizada —que **cualquier** sentencia SQL ejecutable por el rol de aplicación puede fijar— en el único guardián del aislamiento multi-tenant. No hay permiso asociado, no hay punto único de fijación (a diferencia de `app.organization_id`, que sí lo tiene en `get_db`), no hay auditoría y no hay ningún test que lo cubra.
- **Failure scenario:** Cualquier inyección SQL futura, cualquier `text()` mal construido, o simplemente un desarrollador que copie el patrón en un repositorio de una fase posterior, activa el bypass y anula RLS en toda la transacción: lectura y escritura cruzada entre organizaciones. Es exactamente el riesgo que el PRD marca como el más grave del proyecto, y el plan lo introduce en la Fase 0 sin ninguna prueba.
- **Evidence:**
  - `phase-03-multi-tenant-rls-y-modelos-base.md:41` — "Superadmin: se implementa con `SET LOCAL app.bypass = 'on'` verificado en la política; sin UI en esta fase."
  - `docs/prd.md:276` — "Fuga de datos entre organizaciones (RLS + pool async) | Fijación de tenant centralizada; tests de aislamiento en CI desde la fase 0"
  - `docs/investigacion.md:114` — "**Fuga entre tenants** por RLS mal aplicado con pool async: tests de aislamiento desde el inicio."
  - `phase-03-multi-tenant-rls-y-modelos-base.md:64` — el test de aislamiento no menciona el bypass
- **Suggested fix:** O se elimina el bypass de la Fase 0 (no hay UI de superadmin; es alcance no necesario), o se implementa con un **rol de BD distinto** (`app_superadmin`, también sin `BYPASSRLS`, con políticas propias) al que sólo se conmuta desde una dependencia dedicada, y con dos tests obligatorios: usuario normal no puede activarlo, y su activación queda auditada.

---

## Finding 5: `users` y `user_social_links` quedan fuera de RLS sin ningún control compensatorio

- **Severity:** High
- **Location:** Fase 3, "Architecture → Esquema" y "RLS"
- **Flaw:** El plan declara `users` global y sin RLS "accedido a través de membresías", pero no define ninguna política de acceso equivalente en la capa de aplicación, ni un test que la verifique. `user_social_links` no se menciona siquiera. El catálogo de permisos incluye `users:read` sin acotarlo a la organización actual. Esto contradice el requisito no funcional del PRD.
- **Failure scenario:** El endpoint `GET /api/v1/users/me` de esta fase es inocuo, pero la Fase 1 del PRD añadirá listados y búsqueda de usuarios sobre estos repositorios. Como la red de seguridad de RLS no existe para esa tabla, un `SELECT` sin `JOIN organization_members` filtra emails y nombres de personas de otras organizaciones de la misma instalación (dato personal, RGPD). El test de aislamiento planificado no lo detecta porque sólo prueba tablas con `organization_id`.
- **Evidence:**
  - `phase-03-multi-tenant-rls-y-modelos-base.md:41` — "`users` es global (sin RLS) y se accede a través de membresías."
  - `phase-03-multi-tenant-rls-y-modelos-base.md:28-29` — tablas `users` y `user_social_links` sin `organization_id`
  - `phase-03-multi-tenant-rls-y-modelos-base.md:57` — "…`members:read|write`, `users:read`"
  - `docs/prd.md:190` — "`organization_id` en toda tabla de dominio + Row-Level Security en PostgreSQL … tests automáticos de aislamiento"
- **Suggested fix:** Aplicar RLS a `users` con una política basada en existencia de membresía en la organización activa (`EXISTS (SELECT 1 FROM organization_members m WHERE m.user_id = users.id AND m.organization_id = app_current_organization())`), más una excepción explícita para el propio usuario autenticado. Aplicar RLS a `user_social_links` por el `user_id` propietario. Añadir ambos casos al test de aislamiento.

---

## Finding 6: El fixture de test "transacción + rollback" es incompatible con el test de aislamiento RLS que se pretende ejecutar dentro de él

- **Severity:** High
- **Location:** Fase 2, "Implementation Steps" paso 11; Fase 3, paso 11
- **Flaw:** El patrón de fixture (una transacción externa por test con rollback) exige que la aplicación reutilice esa misma conexión y transacción. Pero `get_db` está definido como el punto que **abre** la transacción y ejecuta `SET LOCAL app.organization_id`, y `SET LOCAL` sólo admite un valor por transacción. El test de aislamiento necesita dos contextos de organización distintos y, además, conectar como `app_user`, mientras que las fixtures crearán los datos de partida con el rol propietario.
- **Failure scenario:** Al implementar `test_rls_isolation.py` el equipo descubre que dentro del fixture (a) no puede fijar A y luego B, (b) los datos sembrados por la fixture con el rol propietario no son visibles/insertables desde la sesión de aplicación con RLS, y (c) `SET LOCAL` del `get_db` de la app sobrescribe el del test. La salida menos costosa —y la que un agente tomará— es relajar el test hasta que sólo compruebe el camino feliz: un test fantasma que ejecuta código sin demostrar aislamiento, justo la garantía crítica del PRD.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:67` — "Tests con fixture de BD por test (transacción + rollback) y cliente HTTP"
  - `phase-02-backend-fastapi-base.md:41` — "`get_db` abre transacción y … ejecuta `SET LOCAL app.organization_id` **dentro de esa transacción** … Único punto de fijación"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:64` — "dos organizaciones, sesión fijada en A, consulta sin WHERE devuelve solo A, INSERT con `organization_id` de B falla, rol de BD sin `BYPASSRLS` verificado con `pg_roles`"
  - `plan.md:109` — criterio de éxito global que depende de ese test
- **Suggested fix:** Definir en el plan **dos** estrategias de test: fixture transaccional para los tests de dominio, y para `test_rls_isolation.py` un fixture con base de datos real por módulo (truncate entre tests), conexiones independientes como `app_user`, y datos sembrados fuera de la transacción bajo prueba. Añadir un test negativo de control ("el mismo `SELECT` sin fijar contexto devuelve 0 filas") para que el test no pueda pasar por vacuidad.

---

## Finding 7: El SSR resolverá el tenant equivocado porque la petición servidor→API no lleva el `Host` público

- **Severity:** High
- **Location:** Fase 4, paso 4 y "Success Criteria"; Fase 2, `core/tenant.py`
- **Flaw:** La organización se resuelve por la cabecera `Host`, y la cabecera de desarrollo `X-Organization-Slug` está deshabilitada en producción. Durante el SSR, la petición a `/api/v1/tenant/branding` la emite el proceso Node contra la API interna, con `Host: api:8000` (o `localhost`), no con el dominio del visitante. El plan no menciona en ningún punto la propagación del `Host` original desde el request entrante de SSR.
- **Failure scenario:** En producción tras Caddy, **todas** las páginas públicas renderizadas en servidor reciben 404 o el branding por defecto; el `timeout 2 s` lo enmascara como "tokens por defecto"; el `TransferState` transporta ese branding erróneo al cliente, que no vuelve a pedirlo al hidratar → la marca correcta nunca aparece, o aparece como flash de tema tras una interacción posterior. El criterio de éxito "sin flash de tema por defecto en SSR" se declarará cumplido en local (donde `localhost` sí coincide) y fallará en el primer despliegue real.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:28` — "`tenant.py` # resolve_organization(host | X-Organization-Slug)"
  - `plan.md:28` — "Por `Host` (dominio/subdominio); cabecera `X-Organization-Slug` solo fuera de producción"
  - `phase-04-frontend-angular-y-theming.md:62` — "`ThemingService.load()` en `provideAppInitializer` (timeout 2 s → tokens por defecto) … en servidor, `TransferState` para no repetir la petición al hidratar"
  - `phase-04-frontend-angular-y-theming.md:73` — "[ ] … sin flash de tema por defecto en SSR"
  - `phase-04-frontend-angular-y-theming.md:40` — "en SSR se inyectan como `<style>` inline en el HTML servido"
- **Suggested fix:** Especificar la propagación explícita: en SSR, leer `REQUEST` (token de `@angular/ssr`) y reenviar `Host`/`X-Forwarded-Host` a la API; documentar en el Caddyfile que `X-Forwarded-Host` es obligatorio. Además, definir el comportamiento en fallo: si el branding no se resuelve en servidor, **no** sembrar `TransferState` con el valor por defecto, para que el cliente reintente en lugar de fijar la marca equivocada.

---

## Finding 8: La Fase 4 no puede completarse en paralelo con la 3; sus criterios de éxito dependen de datos y contratos que sólo existen tras la 3

- **Severity:** High
- **Location:** `plan.md`, sección "Phases" (línea de dependencias); Fase 4, "Success Criteria"
- **Flaw:** El plan declara que 3 y 4 pueden ejecutarse en paralelo porque 4 sólo depende del contrato de la Fase 2. Pero en la Fase 2 `/tenant/branding` devuelve "branding por defecto" y en la Fase 3 pasa a devolver el objeto real (colores, fuentes, `template_key`, `social_links`, URL de logo). Los criterios de éxito de la Fase 4 exigen precisamente ese objeto real y datos de seed.
- **Failure scenario:** El equipo/agente que ejecute la Fase 4 en paralelo genera los tipos desde el OpenAPI de la Fase 2, construye `ThemingService` contra un contrato provisional y no puede validar ningún criterio de éxito ("cambiar `colors.primary` en BD", "login del seed", "logo servido desde SeaweedFS"). Al mergear la Fase 3, el `git diff --exit-code` sobre los tipos generados rompe CI y hay que rehacer el trabajo de theming. El paralelismo declarado produce retrabajo garantizado, no ahorro.
- **Evidence:**
  - `plan.md:61` — "Dependencias: 1 → 2 → 3; 4 depende de 2 … 3 y 4 pueden ejecutarse en paralelo."
  - `phase-02-backend-fastapi-base.md:64` — "`tenant/branding` devuelve branding por defecto hasta la fase 3"
  - `phase-03-multi-tenant-rls-y-modelos-base.md:62` — "9. `tenant/branding` real desde `organization_branding` (+ URL pública del logo)"
  - `phase-04-frontend-angular-y-theming.md:73,75,76` — "Cambiar `colors.primary` en BD…", "login del seed → dashboard", "Logo servido desde SeaweedFS"
  - `phase-04-frontend-angular-y-theming.md:84` — "`make api-types` en CI compara con el commit (`git diff --exit-code`)"
- **Suggested fix:** Congelar el **esquema Pydantic completo de `BrandingResponse`** en la Fase 2 (con valores por defecto rellenos, no un DTO reducido) y declararlo contrato bloqueado; o reconocer la dependencia real y marcar 4 como dependiente de 3 para sus tres últimos criterios de éxito, dividiéndolos en "4a: shells y tokens" (paralelizable) y "4b: verificación end-to-end" (posterior a 3).

---

## Finding 9: `ListQueueBroker` no ofrece durabilidad ni reintentos, y el PRD exige ambos para la cola que se construirá encima

- **Severity:** Medium
- **Location:** Fase 2, "Implementation Steps" paso 6
- **Flaw:** El broker elegido es una lista de Redis con semántica *pop* sin confirmación. Si el worker cae después de extraer el mensaje y antes de terminar, la tarea se pierde silenciosamente. El plan lo elige para una tarea `ping` trivial, pero declara explícitamente que todo lo de la Fase 0 debe reutilizarse tal cual en las fases siguientes, donde la cola transporta emails de verificación y entradas QR.
- **Failure scenario:** Fase 3 del PRD: un reinicio del worker durante un pico de inscripciones (el objetivo es 1.000 inscripciones/hora) hace desaparecer los emails de verificación de las personas cuya tarea estaba en vuelo. No hay error, no hay log, no hay reintento: el usuario simplemente nunca recibe su entrada y el organizador no se entera. La corrección obliga a cambiar de broker después, invalidando la premisa de reutilización.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:62` — "`core/tasks.py`: broker `ListQueueBroker` (Redis), `@broker.task ping`"
  - `plan.md:19` — "Todo lo que se construye aquí debe reutilizarse tal cual por esas fases."
  - `docs/prd.md:162` — "Cola de envío con reintentos; métricas de envío/apertura."
  - `docs/prd.md:193` — "1.000 inscripciones/hora sin degradación"
  - `docs/investigacion.md:118` — "**Taskiq** joven: fijar versiones y probar en cada actualización mayor."
- **Suggested fix:** Usar desde el inicio un broker con confirmación (`RedisStreamBroker` de `taskiq-redis`, con grupo de consumidores y reclamación de mensajes pendientes) y un `result_backend` persistente; añadir a los criterios de éxito un test que mate el worker a mitad de tarea y verifique que la tarea se reprocesa.

---

## Finding 10: Sin política definida ante Redis caído, y con Redis como punto único de fallo para auth y rate limiting

- **Severity:** Medium
- **Location:** Fase 2, "Architecture" (refresh tokens) y paso 9
- **Flaw:** La lista de revocación de refresh tokens y el rate limiting viven ambos en Redis, y el plan no define el comportamiento cuando Redis no responde. Tampoco define TTL de las entradas de revocación (una lista que sólo crece), ni si la revocación es una lista de denegación o de permitidos.
- **Failure scenario:** Redis se reinicia (o se le agota la memoria y aplica `maxmemory-policy allkeys-lru`, que es lo que hará una configuración por defecto de un VPS de 4 GB). Con una lista de denegación, todos los tokens revocados —incluidos los de sesiones cerradas o comprometidas— vuelven a ser válidos hasta su expiración: fail-open silencioso en el mecanismo de logout. Simultáneamente, `fastapi-limiter` o bien deja pasar todo (sin límite en `/auth/*`, habilitando fuerza bruta) o bien devuelve 500 en cada login. Ninguna de las dos ramas está decidida en el plan.
- **Evidence:**
  - `phase-02-backend-fastapi-base.md:43` — "Refresh tokens con rotación y lista de revocación en Redis (`logout`)."
  - `phase-02-backend-fastapi-base.md:65` — "rate limiting global suave en `/auth/*`"
  - `phase-01-monorepo-y-entorno.md:23` — "Redis 7 para Taskiq y rate limiting."
  - `docs/prd.md:194` — "Instalación en un VPS de 4 GB"
  - `docs/prd.md:191` — "Turnstile y rate limiting en endpoints públicos; OWASP ASVS nivel 2 como referencia"
- **Suggested fix:** Decidir y documentar en el plan: revocación con TTL igual a la vida del refresh token; ante indisponibilidad de Redis, **fail-closed** para refresh (rechazar la renovación, forzar re-login) y política explícita para el limitador (fail-closed en `/auth/*`); configurar Redis con `maxmemory-policy noeviction` en Compose y añadir un test que simule Redis caído.

---

## Finding 11: El pipeline de despliegue no define migraciones ni rollback, y las imágenes se etiquetan de forma no inmutable

- **Severity:** Medium
- **Location:** Fase 5, "Architecture" y "Implementation Steps" pasos 2-3
- **Flaw:** `docker-compose.prod.yml` incluye `api`, `worker`, `web`, `postgres`, `redis`, `seaweedfs` y `caddy`, pero el plan no dice **quién ejecuta `alembic upgrade head` en producción**, ni en qué orden respecto al arranque de `api` y `worker`, ni cómo se revierte un despliegue fallido. Las imágenes se publican "en `main` y tags", lo que en la práctica significa un tag móvil.
- **Failure scenario:** (a) `docker compose up -d` arranca dos réplicas o api+worker que ejecutan migraciones a la vez → carrera sobre `alembic_version` y esquema a medias. (b) Nadie ejecuta las migraciones y la API arranca contra un esquema viejo, fallando en runtime. (c) Un despliegue rompe producción: con tag móvil no hay forma de volver a la imagen anterior, y aunque la hubiera, el `downgrade` de Alembic ya se demostró frágil (Finding 2) → no existe camino de vuelta. Además `backup.sh` queda "documentado" y sin automatizar, así que en ese momento tampoco hay una copia reciente garantizada.
- **Evidence:**
  - `phase-05-documentacion-y-ci.md:16` — "`docker-compose.prod.yml` con `api`, `worker`, `web`, `postgres`, `redis`, `seaweedfs`, `caddy`"
  - `phase-05-documentacion-y-ci.md:21` — "imágenes construidas en CI al mergear a `main` (GHCR); despliegue manual o vía Coolify/Dokploy"
  - `phase-05-documentacion-y-ci.md:22` — "Backups: script `infra/scripts/backup.sh` … documentado; automatización en fase de plataforma del PRD."
  - `phase-05-documentacion-y-ci.md:32` — "build y push de `api` y `web` a GHCR en `main` y tags"
  - `docs/prd.md:174` — "Instalación con Docker Compose + Caddy; backups automatizados de PostgreSQL y almacenamiento con restauración probada — **M**"
- **Suggested fix:** Añadir a la Fase 5: un servicio `migrate` de un solo uso en `docker-compose.prod.yml` con `depends_on: postgres service_healthy` del que dependan `api` y `worker`; etiquetado de imágenes por SHA de commit además de `latest`; y una sección "Rollback" en `docs/desarrollo.md` con el procedimiento probado (imagen anterior + restauración de `pg_dump`), ya que el `downgrade` de Alembic no es un mecanismo de rollback fiable.

---

## Finding 12: El contrato de tipos entre jobs de CI es frágil y el comando local diverge del de CI

- **Severity:** Medium
- **Location:** Fase 5, paso 1; Fase 4, paso 3 y "Risk Assessment"
- **Flaw:** El plan describe "matriz de dos jobs" y, a la vez, que el job `web` consume un artefacto `openapi.json` producido por el job `api`: una matriz ejecuta trabajos en paralelo, así que hace falta un `needs:` explícito que el plan no declara. Además el comando local genera tipos contra `http://localhost:8000/openapi.json` (servidor vivo) mientras CI lo hace desde un fichero: dos rutas de código distintas para el mismo `make api-types`, con `git diff --exit-code` como juez.
- **Failure scenario:** Si `api` falla o tarda, `web` arranca sin artefacto y falla con un error de descarga que no explica nada. Si el generador emite cabeceras con fecha, o el orden de claves del `openapi.json` varía entre ejecuciones (orden de registro de routers, versión de FastAPI), `git diff --exit-code` falla de forma intermitente en PRs que no tocan la API: la reacción habitual será desactivar la comprobación, perdiendo la única defensa contra la deriva de tipos.
- **Evidence:**
  - `phase-05-documentacion-y-ci.md:31` — "matriz de dos jobs; … `web` ejecuta `make api-types` contra un `openapi.json` exportado por el job `api` (artefacto) y `git diff --exit-code`"
  - `phase-04-frontend-angular-y-theming.md:61` — "`ng-openapi-gen --input http://localhost:8000/openapi.json --output …`"
  - `phase-04-frontend-angular-y-theming.md:84` — "Deriva de tipos API ↔ front → `make api-types` en CI compara con el commit"
- **Suggested fix:** Un único camino: un comando `make openapi` que exporte el esquema **sin levantar servidor** (`python -c "import json; from app.main import create_app; print(json.dumps(create_app().openapi(), sort_keys=True))"`), versionar `openapi.json` en el repositorio, y que `api-types` lo consuma siempre desde el fichero. Declarar `needs: api` en el job `web` y desactivar cabeceras con fecha en el generador.

---

## Resumen de prioridades

| # | Severidad | Título abreviado |
|---|---|---|
| 1 | Critical | GRANTs del rol de aplicación no alcanzan a las tablas de 0002/0003 |
| 3 | Critical | Seed imposible bajo RLS y sin idempotencia |
| 4 | Critical | Bypass de superadmin por GUC sin control de acceso |
| 2 | High | `CREATE ROLE` en Alembic rompe el `downgrade` exigido |
| 5 | High | `users` / `user_social_links` sin RLS ni control compensatorio |
| 6 | High | Fixture transaccional incompatible con el test de aislamiento RLS |
| 7 | High | SSR resuelve el tenant equivocado por `Host` interno |
| 8 | High | Paralelismo 3‖4 falso: contrato y datos de branding |
| 9 | Medium | `ListQueueBroker` sin durabilidad frente al requisito de reintentos |
| 10 | Medium | Redis caído: fail-open no decidido en auth y rate limiting |
| 11 | Medium | Despliegue sin paso de migración, sin tags inmutables ni rollback |
| 12 | Medium | Contrato de tipos en CI frágil y divergente del comando local |
