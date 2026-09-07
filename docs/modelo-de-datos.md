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

### Permisos como texto validado en código

`role_permissions.permission` guarda una cadena, pero solo se aceptan valores del enum
`Permission`. Un permiso retirado del catálogo se ignora al calcular los efectivos, en
lugar de romper la sesión de quien lo tuviera.

## Row-Level Security

| Tabla | Política |
|---|---|
| `organizations` | `id = app_current_organization()` |
| `organization_domains`, `organization_branding`, `organization_members`, `roles`, `role_permissions`, `role_profile_fields`, `events`, `event_sessions`, `event_members`, `event_session_participants`, `speaker_public_profiles` | `organization_id = app_current_organization()` |
| `users` | Uno mismo (`id = app_current_user()`) o quien comparta organización |
| `user_social_links` | Según la visibilidad de su usuario |

Todas con `ENABLE` + `FORCE ROW LEVEL SECURITY`.

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
