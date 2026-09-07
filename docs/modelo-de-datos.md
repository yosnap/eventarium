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
    text full_name
    text avatar_object_key
    text locale
    bool is_active
    bool is_superadmin
    timestamptz email_verified_at
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
participación llegará con `event_members` en la fase 2 del PRD.

### Permisos como texto validado en código

`role_permissions.permission` guarda una cadena, pero solo se aceptan valores del enum
`Permission`. Un permiso retirado del catálogo se ignora al calcular los efectivos, en
lugar de romper la sesión de quien lo tuviera.

## Row-Level Security

| Tabla | Política |
|---|---|
| `organizations` | `id = app_current_organization()` |
| `organization_domains`, `organization_branding`, `organization_members`, `roles`, `role_permissions`, `role_profile_fields` | `organization_id = app_current_organization()` |
| `users` | Uno mismo (`id = app_current_user()`) o quien comparta organización |
| `user_social_links` | Según la visibilidad de su usuario |

Todas con `ENABLE` + `FORCE ROW LEVEL SECURITY`.

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
| `app_create_unverified_user(id, email, hash, nombre)` | Crear la cuenta con `email_verified_at = NULL` |
| `app_verify_user_email(user_id)` | Marcar el correo como verificado; devuelve si cambió algo |

`app_create_unverified_user` fija a mano `locale` e `is_superadmin`: son columnas
`NOT NULL` sin `server_default` (su valor por defecto solo existe en el ORM), así que un
`INSERT` en SQL crudo tiene que darlos explícitamente.
