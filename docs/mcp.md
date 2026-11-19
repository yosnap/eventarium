# Servidor MCP

Eventarium expone un servidor [MCP](https://modelcontextprotocol.io) para que
un asistente (Claude, ChatGPT, Cursor, n8n…) trabaje con los eventos de una
organización en nombre de una persona: leerlos, prepararlos en borrador,
publicarlos o cancelarlos y consultar cifras de inscripción. Nunca ve datos
personales de asistentes.

- **URL**: `https://eventarium.org/mcp` (en local, `http://localhost:8080/mcp`).
- **Transporte**: Streamable HTTP sin estado, respuestas JSON.
- **Credenciales**: OAuth 2.1 (lo normal en asistentes) o clave de API
  (`evtm_…`, para scripts y automatizaciones).

## Quién puede conectarse

Hace falta el permiso **«Conectar asistentes por MCP»** (`mcp:connect`). Lo
tiene el dueño de la organización y es él quien lo asigna a otros roles en
*Roles*. Una conexión nunca da más de lo que la persona puede hacer en la web:
en cada llamada se recalculan los ámbitos como *concedidos ∩ rol actual*, así
que quitar un rol o el permiso corta la siguiente llamada.

## Ámbitos

| Ámbito | Permite | Exige en el rol |
|---|---|---|
| `eventos:leer` | Listar y ver eventos | `events:read` |
| `inscripciones:cifras` | Totales de inscripción y aforo, sin personas | `registrations:read` |
| `eventos:editar` | Crear eventos (siempre en borrador), editar ficha, sesiones y sedes | `events:write` |
| `eventos:publicar` | Publicar y despublicar | `events:write` |
| `patrocinadores:editar` | Añadir y editar patrocinadores | `sponsors:write` |
| `eventos:cancelar` | Cancelar un evento (definitivo, reembolsa) | `events:write` y, con cobros, `payments:write` |

Por defecto solo se marcan `eventos:leer` e `inscripciones:cifras`;
`eventos:cancelar` nunca viene marcado. La conexión puede limitarse a unos
eventos concretos; en ese caso no puede crear eventos nuevos.

## Herramientas

- Lectura: `listar_eventos`, `ver_evento`, `cifras_de_inscripcion`,
  `listar_niveles_de_patrocinio`, `listar_categorias`, `listar_tipos_de_sesion`.
  `ver_evento` devuelve
  `enlace_publico` con la URL pública del evento, `/{organización}/{evento}` (vacío si es
  privado), y los ajustes del recordatorio (`recordatorio`, `recordatorio_horas`).
  `listar_eventos` filtra por `estado`, por `categoria` (slug) y por hasta 3
  `etiquetas` (el evento debe tener todas). No hay filtro por organización:
  una conexión pertenece a una sola.
- Escritura: `crear_evento`, `editar_evento`, `asignar_portada_evento`,
  `anadir_sesion`, `editar_sesion`, `quitar_sesion`, `anadir_sede`,
  `anadir_patrocinador`, `editar_patrocinador`.
- Estado: `publicar_evento`, `despublicar_evento` (se niega si hay
  inscripciones vivas) y `cancelar_evento`.
- Traducción: `traducir_evento` (ver «Idioma del contenido»).

**Tipos de sesión.** Cada organización tiene su catálogo (Charla, Taller, Mesa
redonda…; ver `listar_tipos_de_sesion`). `anadir_sesion` y `editar_sesion`
aceptan `tipo` con el nombre (sin distinguir mayúsculas), el id o la clave base
(`talk`, `workshop`, `break`, `service`, `other`) de un tipo **activo**; sin
`tipo`, `anadir_sesion` usa el primero activo que no es una pausa. Un tipo
desconocido se rechaza con la lista de los disponibles. Las sesiones devuelven
en `tipo` el nombre que le dio la organización. `editar_evento` acepta
`mover_sesiones=True` para mover la agenda con el evento al cambiar sus fechas.

**Visibilidad.** `editar_evento` acepta `visibilidad`: `public` (sale en listados y
buscadores), `hidden` («solo con enlace»: se abre por su URL, no sale en ningún listado y
se marca `noindex`) o `private` (no se abre).

**Sitios cercanos.** `listar_sitios_cercanos`, `anadir_sitio_cercano` y
`quitar_sitio_cercano` (delicada) gestionan lo que hay cerca del evento: `tipo` hotel,
restaurant, bar, parking, transport, pharmacy u other (con `tipo_libre`), nombre,
dirección, teléfono, web y nota; hasta 50 por evento. `ver_evento` los incluye.

**Recordatorio a los inscritos.** `crear_evento` y `editar_evento` aceptan
`recordatorio` (si se envía; por defecto, sí) y `recordatorio_horas` (2, 6, 12,
24, 48 o 72 horas antes; por defecto 24, o 48 en eventos de pago). Otro valor se
rechaza. El historial de ausencias no se expone por el MCP.

**Categoría y etiquetas.** `crear_evento` y `editar_evento` aceptan
`categoria` (el `slug` de una categoría activa, tal como lo devuelve
`listar_categorias`) y `etiquetas` (hasta 10, de 2 a 30 caracteres, en
minúsculas; solo letras, números, espacios y guiones). Una categoría
inexistente o desactivada se rechaza. En `editar_evento`, omitir el campo no
cambia nada; `categoria=""` quita la categoría y `etiquetas=[]` las quita todas.
La categoría que un evento ya tiene se conserva aunque se desactive (y
volver a indicarla en `editar_evento` no da error, igual que en el panel). Filtrar
`listar_eventos` por una categoría inexistente o desactivada da error, no una
lista vacía. El tope de 3 etiquetas del filtro se cuenta antes de quitar
repetidas. El catálogo
de categorías solo lo gestiona la superadministración desde el panel: el MCP
no lo modifica.

**Portada.** `asignar_portada_evento` pone o cambia la imagen destacada del
evento a partir de una URL https pública (PNG, JPEG o WebP, hasta 5 MB): el
servidor la descarga, la valida y la guarda él mismo — el MCP no admite
mandar un fichero. Devuelve la URL ya servida desde Eventarium.

`cancelar_evento` va en dos pasos: la primera llamada devuelve un resumen
(inscripciones y cobros afectados) y un código de confirmación válido unos
minutos; solo la segunda, con ese código, cancela. Cada escritura queda en el
registro de auditoría con la conexión que la hizo, igual que las de la web.

## Conectar un asistente (OAuth)

1. En el asistente, añade un conector o servidor MCP remoto con la URL
   `https://eventarium.org/mcp`.
   - **Claude**: *Ajustes → Conectores → Añadir conector personalizado*.
   - **ChatGPT**: *Ajustes → Aplicaciones → Modo desarrollador → Crear*.
   - **Cursor**: en `mcp.json`, `{"mcpServers": {"eventarium": {"url": "https://eventarium.org/mcp"}}}`.
   - **Hermes**: en `~/.hermes/config.yaml`, bajo `mcp_servers`, una entrada
     `eventarium` con `url: "https://eventarium.org/mcp"` y `auth: oauth`;
     recarga con `/reload-mcp`. Si Hermes corre sin navegador (bot de Telegram,
     servidor), usa una clave de API en `headers.Authorization` (ver abajo).
2. El asistente abre Eventarium. Inicia sesión si hace falta.
3. En la pantalla de consentimiento comprueba quién lo pide y adónde volverá
   (un cliente «no verificado» se ha registrado solo y su nombre lo pone él),
   elige ámbitos y eventos y pulsa **Permitir**. Solo se ofrecen los ámbitos
   que el asistente ha pedido y que tu rol permite.

La conexión dura 90 días. El asistente renueva sus tokens solo; si alguien
reutiliza un token de renovación ya usado, la conexión se revoca entera.

## Clave de API

En *Panel → Asistentes (MCP) → Nueva clave de API* se eligen nombre, ámbitos y
eventos. La clave se muestra **una sola vez** y caduca a los 90 días. Se envía
como cabecera:

```bash
curl -X POST https://eventarium.org/mcp \
  -H "Authorization: Bearer $EVENTARIUM_MCP_KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

En Hermes (`~/.hermes/config.yaml`; la variable se lee de `~/.hermes/.env`):

```yaml
mcp_servers:
  eventarium:
    url: "https://eventarium.org/mcp"
    headers:
      Authorization: "Bearer ${EVENTARIUM_MCP_KEY}"
```

Lo que Hermes puede hacer (crear o editar eventos, publicar, cancelar…) lo
deciden los ámbitos y eventos elegidos al crear la clave.

## Revocar

- Cada persona ve y revoca sus conexiones en *Panel → Asistentes (MCP)*, con
  el historial de lo que ha hecho cada una.
- El dueño ve y revoca las de todos los miembros de la organización.
- Cambiar la contraseña o el correo, restablecerla o desactivar la cuenta
  revoca todas las conexiones de la persona.

## Límites

120 llamadas por minuto por conexión y 600 por IP. Al pasarse, la herramienta
devuelve un error y el asistente debe esperar.

## Idioma del contenido

Los mensajes propios del servidor (`ErrorDeHerramienta`) van siempre en español: no
pasan por el catálogo de traducciones y la mayoría de los clientes MCP no mandan
`Accept-Language`. El contenido de los eventos sí admite idioma, con el parámetro
`idioma` (`es-ES` o `en-US`; también vale `en` o `es`). Cómo se guardan y sirven las
traducciones está en [i18n.md](i18n.md).

- **Lectura.** `listar_eventos` y `ver_evento` devuelven cada texto traducido si su
  traducción está al día; si no, el original. Todas las respuestas de evento llevan
  `idioma_original`. Con `idioma`, llevan también `idioma_servido`, y `ver_evento`
  añade `idiomas_al_dia` y `textos_sin_traducir`.
- **Editar.** `editar_evento` (título, resumen, descripción y lugar), `editar_sesion`
  (título, sala y descripción) y `editar_patrocinador` (nombre y descripción de la
  aportación) aceptan `idioma`, el idioma en que vienen los textos. Si no se indica o
  es el original del evento, se escribe el original como siempre. Si es otro, los
  textos se guardan como traducción manual, que la IA ya no toca, y el original no
  cambia. Lo que no es texto (fechas, aforo…) se cambia en cualquier caso.
- **Crear.** En `crear_evento`, `idioma` es el idioma original del nuevo evento (por
  defecto, el de la organización). `anadir_sesion`, `anadir_sede`,
  `anadir_patrocinador`, `anadir_sitio_cercano` y el `motivo` de `cancelar_evento`
  tienen que escribirse en el idioma original del evento: con otro `idioma` se
  rechazan, y lo creado se traduce después con la herramienta de editar.
- **`traducir_evento`.** Con `accion="estado"` (ámbito `eventos:leer`), dice cuántos
  textos del evento y de lo que cuelga de él hay que traducir a `idioma` y cuántos
  están al día. Con `accion="lanzar"` (ámbito `eventos:editar`), además pone el
  evento en la cola de traducción con IA. Solo funciona si la organización tiene su
  propia clave de IA y respeta los mismos topes de coste que el panel.

## Detalles técnicos

- Código en `apps/api/app/modules/mcp/` (herramientas, verificación, ámbitos)
  y `mcp/oauth/` (servidor de autorización). Tablas `mcp_connections` y
  `mcp_oauth_clients`, migraciones 0055 y 0056.
- El emisor OAuth es `…/mcp/oauth`. Metadatos RFC 9728 en
  `/.well-known/oauth-protected-resource/mcp` y RFC 8414 en
  `/.well-known/oauth-authorization-server/mcp/oauth`.
- Clientes por CIMD (el `client_id` es una URL; se descarga con protección
  SSRF) o por registro dinámico. PKCE S256 obligatorio.
- Los tokens de acceso son JWT de 15 minutos con `type=mcp_access`,
  audiencia = URL del MCP y un secreto propio (`MCP_JWT_SECRET`, derivado de
  `JWT_SECRET` si falta). No sirven en la API web ni al revés.
- El secreto de un cliente dinámico confidencial no se guarda: es un HMAC de
  su `client_id` con ese mismo secreto. Rotar `MCP_JWT_SECRET` (o
  `JWT_SECRET` si aquel está vacío) invalida los tokens y obliga a esos
  clientes a registrarse de nuevo.
- El proxy debe mandar `/mcp*` y `/.well-known/oauth-*` a la API sin
  bufferizar (`infra/caddy/Caddyfile`).
