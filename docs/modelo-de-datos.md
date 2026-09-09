# Modelo de datos

Esquema de la fase 0. Los eventos, sesiones, inscripciones y pagos llegan en fases
posteriores reutilizando estos cimientos.

## Diagrama

```mermaid
erDiagram
  organizations ||--o{ organization_domains : "resuelve por host"
  organizations ||--o| organization_branding : "identidad visual"
  organizations ||--o{ roles : "clona plantillas"
  organizations ||--o{ organization_members : "equipo"
  roles ||--o{ role_permissions : "concede"
  roles ||--o{ role_profile_fields : "define"
  roles ||--o{ organization_members : "asigna"
  users ||--o{ organization_members : "pertenece"
  users ||--o{ user_social_links : "perfil"
  organizations ||--o{ events : "publica"
  events ||--o{ event_sessions : "agenda"
  organizations ||--o{ event_members : "roster"
  organization_members ||--o{ event_members : "participa en"
  event_members ||--o{ event_session_participants : "asignado a"
  event_sessions ||--o{ event_session_participants : "tiene"
  users ||--o| speaker_public_profiles : "activa"

  organizations {
    uuid id PK
    text slug UK
    text name
    text legal_name
    text description
    text website
    text contact_email
    bool is_active
  }
  organization_domains {
    uuid id PK
    uuid organization_id FK
    text host UK
    bool is_primary
  }
  organization_branding {
    uuid organization_id PK
    text template_key
    text logo_object_key
    text favicon_object_key
    jsonb colors
    jsonb fonts
    jsonb social_links
    text organizer_blurb
  }
  users {
    uuid id PK
    text email UK
    text password_hash
    text first_name
    text last_name
    text avatar_object_key
    text locale
    bool is_active
    bool is_superadmin
    timestamptz email_verified_at
    timestamptz verification_warning_sent_at
  }
  user_social_links {
    uuid id PK
    uuid user_id FK
    text kind
    text url
  }
  roles {
    uuid id PK
    uuid organization_id FK
    text key
    text name
    text description
    bool is_system
    text system_template_key
  }
  role_permissions {
    uuid role_id PK_FK
    text permission PK
    uuid organization_id FK
  }
  role_profile_fields {
    uuid id PK
    uuid organization_id FK
    uuid role_id FK
    text key
    text label
    text field_type
    jsonb options
    bool is_required
    bool is_locked
    int sort_order
  }
  organization_members {
    uuid id PK
    uuid organization_id FK
    uuid user_id FK
    uuid role_id FK
    jsonb profile_data
  }
  events {
    uuid id PK
    uuid organization_id FK
    text slug UK
    text title
    text summary
    text description
    text cover_object_key
    text status
    text visibility
    text timezone
    timestamptz starts_at
    timestamptz ends_at
    text location_mode
    text location_name
    text location_address
    text online_url
    int capacity
    text registration_mode
    bool email_verification_required
  }
  event_sessions {
    uuid id PK
    uuid event_id FK
    uuid organization_id FK
    text session_type
    text title
    text description
    timestamptz starts_at
    timestamptz ends_at
    text room
    text video_platform
    text video_url
    jsonb materials
    int sort_order
  }
  event_members {
    uuid id PK
    uuid event_id FK
    uuid organization_id FK
    uuid organization_member_id FK
  }
  event_session_participants {
    uuid id PK
    uuid session_id FK
    uuid event_member_id FK
    uuid organization_id FK
    text role_key
    int sort_order
  }
  speaker_public_profiles {
    uuid id PK
    uuid organization_id FK
    uuid user_id FK
    text public_slug UK
    uuid source_organization_member_id FK
  }
```

Todas las tablas llevan `created_at` y `updated_at` con zona horaria.

## Decisiones

### UUID v7 como clave primaria

Incluye una marca temporal en los bits altos, así que las filas nuevas se insertan al
final del índice B-tree en lugar de dispersas por él. En tablas que crecen mucho eso
evita la fragmentación que produciría UUID v4.

### Marcas temporales calculadas en la aplicación

`TimestampMixin` define `default` en Python **además** de `server_default`. No es
redundancia: si dependieran solo del servidor, SQLAlchemy añadiría `RETURNING` a cada
`INSERT`, y en PostgreSQL un `INSERT … RETURNING` exige superar también la política
`SELECT` de RLS. Al dar de alta a una persona, su fila de `users` todavía no tiene
membresía y por tanto aún no es visible, así que ese `RETURNING` fallaría. El
`server_default` se conserva como red de seguridad para inserciones fuera del ORM.

### Roles clonados, no compartidos

Las plantillas (`owner`, `organizer`, `speaker`, `volunteer`, `attendee`) viven en
`modules/roles/system_roles.py` y se copian como filas propias al crear cada
organización.

La alternativa —filas compartidas con `organization_id` nulo— obligaría a que cada
política RLS tuviera una excepción, y esas excepciones son justo donde se cuelan los
fallos de aislamiento. Con la clonación, `organization_id` es `NOT NULL` en todas las
filas y la política es idéntica en todas las tablas.

Coste: cambiar una plantilla solo afecta a las organizaciones nuevas. Es el
comportamiento correcto, porque una organización puede haber personalizado su copia.

### Campos de perfil por rol

Cada rol define qué se pide a quien lo tiene. `speaker` trae biografía, currículum, web
y contacto; `volunteer`, disponibilidad y talla de camiseta. Los campos que vienen de la
plantilla llevan `is_locked = true` y no se pueden borrar, aunque sí se pueden añadir
otros.

Las respuestas van en `organization_members.profile_data` (JSONB), validadas contra la
definición del rol por `shared/dynamic_fields.py`. Las claves no definidas se rechazan
en lugar de ignorarse: un dato que no corresponde a ningún campo suele ser un error del
cliente, y aceptarlo dejaría basura que nadie volvería a mirar.

Ese `profile_data` se reutiliza entre ediciones del evento; el historial de
participación se resuelve con `event_members`/`event_session_participants`, ver
más abajo.

### Eventos, agenda, roster y perfil público de ponente (fase 2 del PRD)

Cinco tablas nuevas: `events`, `event_sessions`, `event_members`,
`event_session_participants`, `speaker_public_profiles`. Todas llevan
`organization_id` **denormalizado**, igual que `role_permissions` lo lleva pese a
tener `role_id` — es lo que permite a la política RLS filtrar en la propia tabla,
sin subconsultas.

**FK compuestas contra `(id, organization_id)` del padre, no simples contra `id`.**
La integridad referencial de PostgreSQL no pasa por RLS: una FK simple no
impediría que una fila hija con `organization_id` propio apuntara al recurso de
otra organización. Cada tabla hija (`event_sessions.event_id`,
`event_members.event_id`, `event_members.organization_member_id`,
`event_session_participants.session_id`,
`event_session_participants.event_member_id`,
`speaker_public_profiles.source_organization_member_id`) usa una FK compuesta, así
que la propia base de datos garantiza que el padre referenciado pertenece a la
misma organización. `organization_members` ganó un `UNIQUE(id, organization_id)`
propio para ser el objetivo de esas FK.

**Identidad del ponente: por persona, no por membresía.** `is_public`/`public_slug`
no viven en `organization_members` (una fila por *rol*: la misma persona puede
tener varias, y el slug quedaría fragmentado o duplicado entre ellas). Viven en
`speaker_public_profiles`, una fila por `(organization_id, user_id)`, con
`source_organization_member_id` indicando de qué membresía en concreto se toma la
biografía a publicar. El historial de sesiones (`speakers_repository`) se resuelve
por `user_id` a través de **todas** las membresías de esa persona en la
organización, no solo la que activó el perfil.

**Rol libre por asignación, no un catálogo cerrado.** `role_key` en
`event_session_participants` es texto libre (p. ej. "speaker", "moderator"),
independiente del rol de la persona en la organización: cada organización puede
llamarlo como necesite. `UNIQUE(session_id, event_member_id, role_key)` permite que
la misma persona aparezca varias veces en la misma sesión con roles distintos (p.
ej. ponente y moderadora a la vez), pero nunca duplicada con el mismo rol.

**Sin `ondelete` en `event_session_participants.event_member_id`** (`RESTRICT` por
defecto): quitar a alguien del roster de un evento mientras tiene participaciones
activas se rechaza a nivel de base de datos como último cinturón de seguridad — el
servicio ya lo comprueba antes y responde 409 legible, esto es la red por si algo
se salta esa capa.

**Validación de `video_url` y `materials` por esquema y dominio.**
`validate_video_url`/`validate_materials`
(`apps/api/app/modules/events/schemas.py`) exigen `https` siempre y, si la
plataforma declarada es conocida (`youtube`, `vimeo`, `twitch`), un dominio de su
lista (`youtube.com`/`youtu.be`, `vimeo.com`, `twitch.tv`); para `other` basta con
`https`. Sin esto, una sesión podría embeber un `iframe`/enlace controlado por
terceros desde el propio dominio de la organización. Se aplica tanto al alta
(`EventSessionCreate`) como a la edición — un `PATCH` parcial que solo toca uno de
los dos campos se revalida en `service.update_session` contra el valor ya
guardado del otro, no solo campo a campo.

### Patrocinadores: niveles por organización, patrocinio por edición (fase 5 del PRD)

Dos tablas: `sponsor_tiers` (organización) y `sponsors` (evento + nivel).
`sponsor_tiers` es por organización porque los niveles se reutilizan entre
ediciones (ej. "Oro" siempre significa lo mismo); `sponsors` cuelga de
`(event_id, tier_id)` porque un patrocinio es por edición concreta, no
permanente — una empresa puede patrocinar una edición y no la siguiente.
Mismo patrón de FK compuesta que `event_sessions`/`event_members`:
`sponsors.organization_id` denormalizado, `UNIQUE(id, organization_id)` en
`sponsor_tiers` para que la FK compuesta de `sponsors.tier_id` pueda
crearse.

**Borrar un nivel con patrocinadores activos es un 409, no un 500.**
`sponsors.tier_id` es `RESTRICT` (sin `ondelete`): la base de datos rechaza el
borrado si algún patrocinador sigue apuntando a ese nivel.
`sponsors/service.py:delete_tier` traduce el `IntegrityError` resultante a un
mensaje legible en vez de dejarlo subir como error de servidor.

**La aportación es mutuamente excluyente por tipo.**
`contribution_type` (`monetaria`/`en_especie`) determina cuál de
`contribution_amount`/`contribution_description` va relleno — nunca los dos,
nunca ninguno. Se valida en el esquema Pydantic para el alta
(`SponsorCreate`) y se revalida en el servicio para el `PATCH` parcial
(`update_sponsor`), donde la combinación final solo se conoce tras fusionar
con lo que el patrocinador ya tenía guardado — mismo motivo que
`events/service.py:update_session` con `video_platform`/`video_url`.

**El bloque público nunca expone la aportación.** El endpoint público de
detalle de evento (`GET /public/events/{slug}`) agrupa los patrocinadores por
nivel y los ordena por `sponsor_tiers.display_order`, pero solo expone
`name`/`logo_url`/`website` (`PublicSponsor`) — nunca importe ni descripción:
el PRD no pide hacer pública la valoración económica de nadie. El filtro de
publicación del evento (`published` + `public`) ya se aplica al resolver el
evento antes de construir este bloque, así que un borrador u oculto no expone
tampoco sus patrocinadores.

### Pagos con Stripe Connect, tipos de entrada, descuentos y reembolsos (fase 6 del PRD)

Seis tablas nuevas. Cinco de dominio, con RLS y `UNIQUE(id, organization_id)`
igual que el resto del esquema, más una de instalación:

- **`organization_stripe_accounts`**: una fila por cuenta Stripe Connect
  conectada. La unicidad no es `UNIQUE(organization_id)` sino un índice único
  **parcial** `WHERE deauthorized_at IS NULL`: así una organización que
  desconecta su cuenta (`account.application.deauthorized`) puede volver a
  conectarse sin tocar la base de datos a mano, y la fila antigua sobrevive
  para poder seguir reembolsando los pagos cobrados con ella —
  `event_payments` guarda su propio `stripe_account_id`, así que el
  reembolso se resuelve por la cuenta **del pago**, no por la cuenta activa
  actual de la organización.
- **`event_ticket_types`**: nombre, precio en céntimos, `currency` fija por
  evento, cupo (`max_quantity` nullable = sin límite) y ventana de venta.
- **`event_discount_codes`**: código único por evento (comparado en
  mayúsculas), tipo de descuento, límite de usos total (sin límite por
  persona: las inscripciones no requieren cuenta de usuario). **Sin columna
  `used_count`**: el consumo se deriva con un `COUNT` sobre
  `event_payments` en los estados consumibles, ejecutado con la fila del
  código bloqueada (`FOR UPDATE`) — un contador que la compra incrementa y el
  barrido de caducados decrementa se desajusta en cuanto dos ejecuciones del
  cron se solapan, y el derivado no puede desajustarse porque sale de la
  misma tabla que decide si se cobró. El cupo de `event_ticket_types` se
  deriva igual.
- **`event_payments`**: registro de cada intento de compra
  (`registration_id` nullable, `ondelete SET NULL` para que el borrado RGPD
  no falle), con `stripe_account_id` propio, `stripe_checkout_session_id` y
  `stripe_payment_intent_id` (nullable hasta que el pago completa),
  importes en céntimos y `status`
  (`pending`/`paid`/`refunded`/`partially_refunded`/`expired`).
- **`event_payment_refunds`**: el outbox de reembolsos — la intención
  persistida **antes** de llamar a Stripe (`payment_id`, importe, motivo,
  `revoke_ticket`, `status`), para que ninguna llamada de red ocurra con un
  bloqueo de fila abierto y para que un reembolso no pueda perderse entre la
  respuesta de Stripe y la escritura en base de datos.
- **`stripe_webhook_events`** (instalación, sin RLS): antirreplay del
  webhook, con `REVOKE ALL ... FROM app_user` — solo `app_maintainer` (el
  endpoint de webhooks y la tarea de fondo) lee/escribe, mismo patrón que
  `audit_log`/`cookie_consents` de la fase 5. Su `payload` **no es el evento
  crudo de Stripe**: es una proyección con lista blanca de los campos que el
  handler procesa (nunca `customer_details.email` ni ningún otro dato
  personal), y una tarea diaria purga las filas con más de
  `stripe_webhook_retention_days` (90 por defecto).

**`pending_payment` es un estado nuevo de `EventRegistration` que cuenta
como plaza reservada.** El flujo es: formulario público → `pending_payment`
→ Checkout Session → webhook `checkout.session.completed` → `confirmed`.
Si `pending_payment` no contara para el aforo, varias personas podrían abrir
Checkout a la vez sobre la última plaza y todas pagar. Por eso
`count_reserved_registrations` incluye `pending_payment` cuya ventana no
haya expirado (`payment_expires_at`), igual que ya hacía con una promoción
de lista de espera vigente, y `_cancelar_inscripcion` libera esa misma
condición al expirar. La ventana de pago es la columna
`events.payment_checkout_window_minutes` (`NOT NULL DEFAULT 30`, `CHECK
BETWEEN 30 AND 1439`) — por evento, no una variable de entorno: el aforo y
la fila que lo retiene son ambos de nivel evento, y un pago solo afecta a un
tipo de entrada.

**La revocación de una entrada es la de la fase 4, reutilizada, no una
nueva.** `event_tickets.revoked_at` ya existía; el reembolso total llama a
la `revocar_entrada` ya existente en vez de añadir un segundo estado de
validez que el escáner tendría que consultar por separado. Un reembolso
parcial no revoca salvo que el organizador marque la casilla explícita del
panel — es un ajuste de precio, no una anulación.

**Dinero en céntimos, `currency` fija por evento.** Enteros, nunca `float`
ni `Numeric` con decimales libres: es lo que espera la API de Stripe y
elimina cualquier desajuste de redondeo entre lo que la plataforma calcula
(precio − descuento) y lo que Stripe cobra. `currency` es fija por evento
para que dos tipos de entrada en divisas distintas no puedan compartir una
misma Checkout Session.

### Páginas legales, cookies y consentimientos (fase 5 del PRD)

Las cuatro páginas legales (`legal_notice_content`, `privacy_policy_content`,
`cookies_policy_content`, `registration_terms_content`) son columnas `Text`
nullable de `Organization`, no tablas aparte: son contenido de la entidad
responsable, no del evento, y `NULL` significa "usar la plantilla por
defecto" — el mismo patrón que un campo opcional editable desde el panel, sin
una tabla de "página" genérica para cuatro casos fijos.

**Plantillas en Python, no en base de datos ni con un motor nuevo.** Las
plantillas (`apps/api/app/modules/legal/templates.py`) son f-strings de
Python rellenadas con `legal_name`/`contact_email`/`legal_address`/`tax_id`
de la organización — mismo patrón que los emails de `app/core/tasks.py`, sin
Jinja2 ni ningún motor de plantillas: el contenido es editable por
`owner`/`organizer` y se sirve en SSR público, así que un motor que
interprete el texto guardado como plantilla (en vez de como variable)
abriría SSTI, y un escapado manual mal hecho abriría XSS. El contenido
Markdown se sanea en el frontend (`marked` + `DOMPurify`, lista blanca de
párrafos/negrita/cursiva/listas/enlaces) antes de mostrarse — nunca se
interpreta como HTML en el backend.

**`cookie_consents` es anónima por diseño.** Solo `organization_id`,
`categories_accepted` (JSONB) y `created_at` — sin `user_id`, sin email y sin
ningún campo de IP o su hash: RGPD no exige identificar a quien acepta o
rechaza cookies, es la decisión de un navegador, no un consentimiento de
inscripción ligado a una persona. La tabla no lleva RLS (es de instalación,
no de organización) pero tampoco el acceso por defecto de `app_user`: la
migración `0012` hace `REVOKE ALL ON cookie_consents FROM app_user` seguido
de `GRANT INSERT` puntual, lo mínimo que el endpoint público necesita para
escribir sin poder leer ni borrar filas ajenas ni propias. El endpoint
(`POST /public/cookie-consent`) inserta con `sqlalchemy.insert()` de Core, no
con `session.add()`: el ORM añadiría `RETURNING` para leer `created_at`
(`server_default`), y `INSERT ... RETURNING` exige además `SELECT` sobre las
columnas devueltas, que este rol no tiene a propósito.

### Permisos como texto validado en código

`role_permissions.permission` guarda una cadena, pero solo se aceptan valores del enum
`Permission`. Un permiso retirado del catálogo se ignora al calcular los efectivos, en
lugar de romper la sesión de quien lo tuviera.

## Row-Level Security

| Tabla | Política |
|---|---|
| `organizations` | `id = app_current_organization()` |
| `organization_domains`, `organization_branding`, `organization_members`, `roles`, `role_permissions`, `role_profile_fields`, `events`, `event_sessions`, `event_members`, `event_session_participants`, `speaker_public_profiles`, `event_registrations`, `event_registration_answers`, `event_registration_consents`, `event_tickets`, `event_ticket_scans`, `sponsor_tiers`, `sponsors` | `organization_id = app_current_organization()` |
| `users` | Uno mismo (`id = app_current_user()`) o quien comparta organización |
| `user_social_links` | Según la visibilidad de su usuario |

Todas con `ENABLE` + `FORCE ROW LEVEL SECURITY`.

`audit_log` y `cookie_consents` (fase 5 del PRD) son la excepción deliberada: **sin**
política RLS, porque son tablas de instalación, no de dominio por organización, pero
tampoco con el `GRANT` automático que `app_user` recibiría de otro modo — la migración
`0012` ejecuta `REVOKE ALL ... FROM app_user` explícito sobre ambas (con `GRANT INSERT`
puntual sobre `cookie_consents` para el endpoint público de consentimiento). Sin ese
`REVOKE`, `ALTER DEFAULT PRIVILEGES` (`infra/postgres/sql/roles.sql`) le habría dado a
`app_user` acceso de lectura y **borrado** sobre el registro de auditoría completo de la
instalación — ver `docs/arquitectura.md` § Auditoría y RGPD.

RLS aísla por **organización**, no por si un evento está publicado: un borrador de
la propia organización sigue siendo visible bajo RLS para cualquiera que resuelva
el host correcto (incluido el contexto anónimo de los endpoints públicos, que solo
fija `app.organization_id`, sin usuario). El filtro `status = 'published' AND
visibility = 'public'` de las páginas públicas (`public_router.py`) es por tanto
explícito en cada consulta, nunca delegado a RLS — ver
`docs/arquitectura.md` § Páginas públicas con datos.

`users` tiene además una política solo de `INSERT` que permite crear la fila cuando hay
contexto de organización: dar de alta a alguien crea primero el usuario y después la
membresía, así que en el momento del `INSERT` todavía no comparte organización con
nadie. Las políticas permisivas se combinan con OR, de modo que esa excepción no amplía
la visibilidad: la fila solo será legible cuando exista la membresía.

Índice `(organization_id, user_id)` sobre `organization_members` porque la política de
`users` consulta esa tabla en cada lectura.

## Migraciones

| Revisión | Qué hace |
|---|---|
| `0001_verificar_roles` | Comprueba que existen `app_user` y `app_maintainer` y que el primero **no** tiene `BYPASSRLS`. Falla pronto y con mensaje claro si el entorno no está preparado |
| `0002_esquema_base` | Tablas, índices y constraints; verifica que `ALTER DEFAULT PRIVILEGES` concedió acceso a `app_user` |
| `0003_politicas_rls` | Funciones de contexto y resolución, y políticas de todas las tablas |
| `0004_correo_y_verificacion` | `users.email_verified_at` + índice parcial; tres funciones `SECURITY DEFINER` para el registro público (ver más abajo) |
| `0005_nombre_y_apellidos` | Sustituye `users.full_name` por `first_name` y `last_name` (con backfill por `split_part`); `app_create_unverified_user` pasa a 3 argumentos, sin nombre |
| `0006_autoservicio_organizaciones` | Tres funciones `SECURITY DEFINER` para el alta de organización desde el propio registro público (ver más abajo) |
| `0007_barrido_no_verificados` | `users.verification_warning_sent_at`, para el barrido de cuentas sin verificar |
| `0008_cuenta_y_recuperacion` | Tres funciones `SECURITY DEFINER` para cuenta propia y recuperación de contraseña (ver más abajo) |
| `0009_eventos_agenda_y_ponentes` | `events`, `event_sessions`, `event_members`, `event_session_participants`, `speaker_public_profiles`; políticas RLS y FK compuestas del mismo patrón que las tablas anteriores |
| `0010_inscripcion_de_asistentes` | `event_registrations`, `event_registration_answers`, `event_registration_consents`; funciones `SECURITY DEFINER` para el formulario público de inscripción |
| `0011_entradas_qr` | `event_tickets`, `event_ticket_scans`; emisión automática de entrada al confirmarse una inscripción |
| `0012_patrocinio_legal_auditoria` | `sponsor_tiers`, `sponsors` (con `UNIQUE(id, organization_id)` en `sponsor_tiers`), `audit_log`, `cookie_consents` (`REVOKE ALL ... FROM app_user` explícito en ambas, `GRANT INSERT` puntual en `cookie_consents`), columnas legales en `organizations`; backfill de `sponsors:read`/`write` a roles existentes con `organizations:write` |

Se ejecutan siempre con `DATABASE_MIGRATIONS_URL` (rol `app_maintainer`). Con el rol de
la API fallarían, y eso es deliberado. El ciclo `upgrade head` → `downgrade base` →
`upgrade head` está probado.

### Registro público y RLS: tres funciones `SECURITY DEFINER` más

La política `tenant_users` exige compartir organización con quien pregunta (o ser uno
mismo, vía `app_current_user()`). En el registro público eso no se cumple todavía: la
persona no ha iniciado sesión y no pertenece a ninguna organización, así que no puede
ver, crear ni actualizar su propia fila por la vía normal.

Se resuelve con el mismo patrón que `app_resolve_organization` (alcance mínimo,
`REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE TO app_user`), no dando `BYPASSRLS` al rol de
la API:

| Función | Uso |
|---|---|
| `app_find_user_by_email(email)` | Comprobar si ya existe una cuenta (registro, reenvío de verificación) |
| `app_create_unverified_user(id, email, hash)` | Crear la cuenta con `email_verified_at = NULL` |
| `app_verify_user_email(user_id)` | Marcar el correo como verificado; devuelve si cambió algo |

`app_create_unverified_user` fija a mano `locale` e `is_superadmin`: son columnas
`NOT NULL` sin `server_default` (su valor por defecto solo existe en el ORM), así que un
`INSERT` en SQL crudo tiene que darlos explícitamente. Ya no recibe nombre: el registro
público solo pide correo y contraseña. `first_name`/`last_name` quedan `NULL` hasta que
la persona crea una organización o (fase 3 del PRD) se inscribe en un evento, momento en
el que un evento u organización se lo exige.

### Alta de organización y RLS: tres funciones `SECURITY DEFINER` más

Verificar el correo no da todavía organización: el token de acceso que emite
`verify-email` es un JWT «puente» con `organization_id` nulo, solo para poder llamar al
endpoint de alta de organización sin loguear de nuevo. Sin organización no hay contexto
RLS, así que crear la fila de `organizations`, comprobar la disponibilidad de un slug y
leer los propios datos de usuario no pueden pasar por las políticas normales. Se resuelve
con el mismo patrón que `app_resolve_organization` y las funciones de la fase anterior:

| Función | Uso |
|---|---|
| `app_create_organization_row(id, slug, name)` | Insertar la fila de `organizations`, antes de que exista ningún contexto RLS que la haga visible |
| `app_check_slug_available(slug)` | Comprobación pública (sin autenticar) de si un slug está libre, usada por el formulario en vivo |
| `app_find_user_by_id(id)` | Leer el propio usuario (email, verificación) para la dependencia `require_verified_user`, sin que exista aún membresía alguna |

### Cuenta propia y recuperación: tres funciones `SECURITY DEFINER` más

Confirmar un cambio de correo o completar una recuperación de contraseña llega por un
enlace de correo, sin sesión ni contexto RLS (igual que el registro público). Listar
"mis organizaciones" tiene el problema inverso: el contexto lo fija el host, no la
persona. Mismo patrón que las funciones anteriores:

| Función | Uso |
|---|---|
| `app_change_user_email(user_id, new_email)` | Aplicar un cambio de correo ya confirmado por token; devuelve si cambió algo |
| `app_set_user_password(user_id, password_hash)` | Aplicar una contraseña nueva (cambio autenticado con RLS normal; recuperación, sin sesión) |
| `app_user_organizations(p_user_id)` | Listar las organizaciones de una persona con independencia del host; solo responde si `p_user_id` coincide con `app.user_id` de la sesión |

Tras `app_create_organization_row`, el resto del alta (clonar roles, crear el dominio y
el branding por defecto, dar de alta a la persona como `owner`) ya ocurre con contexto
RLS normal, fijado por `set_organization_context` con la organización recién creada.
