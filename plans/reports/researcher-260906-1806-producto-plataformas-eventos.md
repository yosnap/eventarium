# Investigación de producto: plataforma open source de gestión de eventos (ref. Luma) — IAWIC / IA Week

Fecha: 2026-09-06. Investigación de producto (no técnica). Todas las afirmaciones llevan URL de origen. Donde no encontré dato fiable, lo indico explícitamente.

## 1. Análisis de referentes

### Luma (lu.ma) — referencia principal
- Registro sin fricción: página de evento con formulario, contactos sincronizables, invitaciones por email/SMS, integración de calendario. [help.luma.com](https://help.luma.com/), [help.luma.com/p/event-registration-process](https://help.luma.com/p/event-registration-process)
- Aprobación y lista de espera: la capacidad del evento controla el nº total de invitados aprobados por todos los tipos de entrada; la waitlist se activa solo cuando el evento se llena (capacidad alcanzada o todas las tipologías agotadas). El organizador puede cambiar manualmente el estado de un invitado (Going/Not Going/Waitlist) y notificarle con mensaje personalizado. [help.luma.com/p/waitlist](https://help.luma.com/p/waitlist), [help.luma.com/p/managing-your-guest-list](https://help.luma.com/p/managing-your-guest-list)
- Check-in QR: cada invitado recibe un código QR al registrarse; se escanea en la entrada o se busca por nombre/email. Se puede añadir a Apple/Google Wallet, funciona sin conexión ni app. [help.luma.com/p/check-in](https://help.luma.com/p/check-in)
- Temas/plantillas: más de 40 temas para personalizar la página de evento; el color del evento se propaga a botones/enlaces de los emails automáticamente. [help.luma.com/p/event-themes-and-customization](https://help.luma.com/p/event-themes-and-customization)
- Calendarios: todo evento pertenece a un "calendario" (espacio del organizador/comunidad) que agrupa eventos recurrentes. [help.luma.com/p/event-registration-process](https://help.luma.com/p/event-registration-process)
- Eventos de pago: Luma Plus (59 $/mes) desbloquea ticketing de pago, dominio propio, analítica avanzada y herramientas de email. [businessmodelcanvastemplate.com](https://businessmodelcanvastemplate.com/blogs/how-it-works/luma-how-it-works)
- Modelo de negocio: freemium + suscripción (Plus) + comisión sobre entradas de pago en el plan base (dato de comisión exacta no verificado en esta búsqueda — pendiente).
- Carencias frente al objetivo IAWIC: **no es open source, no permite self-hosting ni branding total** (dominio propio solo en plan de pago), sin gestión de patrocinadores por niveles ni CfP/ponentes documentado en las fuentes revisadas — no encontré evidencia de estas funciones en Luma.

### Eventbrite
- Fuerte en ticketing masivo y descubrimiento (marketplace), pero **carece de gestión de ponentes, sesiones o Call for Papers (CfP)**, por lo que no sirve para conferencias con agenda multi-track sin herramientas adicionales. [opensourceprojects.cc/alternatives/eventbrite](https://opensourceprojects.cc/alternatives/eventbrite)
- Modelo de negocio: comisión por entrada vendida (no verificado el % exacto en esta pasada de investigación).

### Meetup
- Orientado a comunidades recurrentes/grupos locales, gestión de membresía y eventos gratuitos; no es su foco el ticketing de pago avanzado ni conferencias grandes. No se profundizó más allá de la comparativa general citada arriba.

### Sessionize
- Cloud, foco 100% en CfP, revisión de propuestas y construcción de agenda (grid visual). Perfiles de ponente públicos embebibles. Tiene tier gratuito para eventos comunitarios. [sessionize.com](https://sessionize.com/), [sessionize.com/features](https://sessionize.com/features)

### Pretalx
- Herramienta de planificación de conferencias centrada en CfP → gestión de ponentes → agenda publicada: preguntas personalizadas, tracks, tipos de sesión, revisión colaborativa con scoring, comunicación con ponentes vía email plantillado. [pretalx.com/p/features](https://pretalx.com/p/features), [github.com/pretalx/pretalx](https://github.com/pretalx/pretalx)
- Es open source (proyecto de la comunidad de conferencias europeas de software libre); no se verificó la licencia exacta en esta pasada — **pendiente confirmar** (histórico: Apache 2.0 según conocimiento previo, no confirmado con fuente en esta sesión).

### Hopin / RingCentral Events
- Hopin (eventos virtuales/híbridos) fue adquirida por RingCentral en agosto de 2023 y rebrandeada a "RingCentral Events"; Hopin (la entidad original) se declaró en quiebra en febrero de 2024, pero la plataforma sigue operativa bajo RingCentral, activa en 2025 con funciones de IA. [ringcentral.com/us/en/blog/ringcentral-hopin](https://www.ringcentral.com/us/en/blog/ringcentral-hopin/), [b2bsaasreviews.com/products/ringcentral-events](https://b2bsaasreviews.com/products/ringcentral-events/)
- **Riesgo de adopción**: historial de quiebra de la empresa original es señal de inestabilidad del segmento "eventos virtuales todo-en-uno"; no recomendable como referencia de arquitectura de negocio, sí como referencia de features híbridas.

### Alternativas open source

**Pretix** — AGPL/OSS con "Community edition" gratuita (ticketing básico, check-in, formularios) + Enterprise (mapas de asientos, POS, badges, resellers) desde 499 €/año; hospedado: 2,5% por entrada (tope 15 €); self-hosted: sin comisión por entrada, solo infraestructura. [pretix.eu/about/en/pricing/selfhosted](https://pretix.eu/about/en/pricing/selfhosted), [blog.hi.events/top-5-open-source-event-ticketing-platforms](https://blog.hi.events/top-5-open-source-event-ticketing-platforms/)
- Qué hace bien: ticketing avanzado (asientos, multi-moneda, multidioma, widgets embebibles), lista de espera, descuentos, reporting.
- Carencia: funciones "grandes" (seating, POS, badges) tras muro de pago Enterprise → limita el self-host gratuito para eventos grandes.

**Hi.Events** — Licencia AGPL-3.0 **con términos adicionales**: la versión gratuita obliga a mantener visible "Powered by Hi.Events"; licencias comerciales Standard (499 €/año) y Platform (2.499 €/año) permiten quitar el branding y dan soporte. [github.com/HiEventsDev/hi.events](https://github.com/HiEventsDev/hi.events/blob/develop/README.md), [hi.events/open-source-event-ticketing](https://hi.events/open-source-event-ticketing)
- Qué hace bien: promo codes, pagos instantáneos vía Stripe, exportación XLSX/CSV, API REST completa, check-in QR, formularios de pedido personalizados, tipos de entrada (gratis/pago/donación/escalonada).
- **Riesgo directo para IAWIC**: si el objetivo es "branding propio del organizador", la licencia gratuita de Hi.Events obliga a mostrar su marca — incompatible con el requisito de white-label salvo pago de licencia comercial.
- Cloud alternativa: 1,25% + 0,60 $/entrada.

**Attendize** — Laravel, ticket selling + gestión de asistentes, gratuito. **Mantenimiento muy bajo**: última release etiquetada a inicios de 2023, la v1.x solo recibe parches de seguridad, todo el esfuerzo está en una v2.0.0 no confirmada como lanzada. [github.com/Attendize/Attendize](https://github.com/Attendize/Attendize), [gappsy.com/tools/attendize](https://www.gappsy.com/tools/attendize/)
- **Riesgo de abandono alto** — no recomendable como base de un proyecto nuevo salvo que se audite su estado real antes de decidir.

**Indico** — Desarrollado por el CERN, usado para +900.000 eventos en CERN y por Naciones Unidas desde 2016 (+180.000 asistentes gestionados). Cubre scheduling, registro, gestión de abstracts y videoconferencia. Open source. [getindico.io](https://getindico.io/), [github.com/indico/indico](https://github.com/indico/indico)
- Qué hace bien: robustez para conferencias científicas grandes, abstract management potente.
- Carencia probable para IAWIC: complejidad de instalación/uso orientada a instituciones científicas, no a organizadores comunitarios ligeros (no verificado con fuente directa, es inferencia razonable a validar).

**OSEM (Open Source Event Manager)** — Herramienta especializada en conferencias de software libre: CfP, gestión de ponentes, scheduling y coordinación de asistentes en un solo flujo. [github.com/openSUSE/osem](https://github.com/openSUSE/osem), [osem.io](https://osem.io/)
- Riesgo: **no se encontró evidencia de actividad reciente** en la búsqueda (repos con forks de openSUSE/danimo) — posible bajo mantenimiento, pendiente de verificar.

**Gancio** — Agenda federada para comunidades locales (protocolo ActivityPub, interopera con Mastodon, Pleroma, Mobilizon, WordPress). Licencia AGPL-3.0. Funciones: registro de usuarios, eventos anónimos con confirmación de admin, eventos multi-día y recurrentes, exportación RSS/ICS, embebido vía iframe/webcomponent. [gancio.org](https://gancio.org/), [gancio.org/usage/federation](https://gancio.org/usage/federation)
- Carencia clara: **no tiene ticketing de pago ni check-in**; es una agenda comunitaria, no una plataforma de gestión de asistentes/entradas. No sirve como base para IAWIC salvo como referencia de federación.

**Mobilizon** — Parte del Fediverse (protocolo ActivityPub), instancias independientes auto-hospedables, orientado a redes activistas, grupos culturales locales e instituciones educativas. [wbcomdesigns.com/mobilizon-review](https://wbcomdesigns.com/mobilizon-review/)
- Igual que Gancio: sin ticketing/pago ni check-in — no cubre el caso de uso de un evento profesional de pago con control de acceso.

### Tabla comparativa (síntesis)

| Plataforma | Licencia/modelo | Self-host | Ticketing pago | CfP/ponentes | Check-in QR | White-label real | Riesgo adopción |
|---|---|---|---|---|---|---|---|
| Luma | SaaS cerrado, freemium+Plus | No | Sí (plan pago) | No evidenciado | Sí | Parcial (dominio en plan pago) | Bajo (producto maduro) pero no aplicable como base de código |
| Eventbrite | SaaS, comisión | No | Sí | No | Sí | No | Bajo como SaaS, inútil como base |
| Sessionize | SaaS, freemium | No | N/A (no ticketing) | Sí (fuerte) | No | No | Bajo, complementario |
| Pretalx | OSS (confirmar licencia) | Sí | Limitado | Sí (fuerte) | No | Sí | Medio — activo, comunidad europea de conf. |
| Pretix | OSS Community + Enterprise pago | Sí | Sí | No | Sí | Sí (self-host) | Bajo-medio, proyecto maduro con negocio detrás |
| Hi.Events | AGPL + marca obligatoria en gratis | Sí | Sí | No | Sí | **No en versión gratis** | Medio, proyecto joven pero activo |
| Attendize | OSS Laravel | Sí | Sí | No | Básico | Sí | **Alto — bajo mantenimiento** |
| Indico | OSS (CERN) | Sí | Limitado | Sí (abstracts) | Limitado | Sí | Bajo (probado a escala), alto esfuerzo de adopción |
| OSEM | OSS | Sí | No evidenciado | Sí | No evidenciado | Sí | **Alto — actividad reciente no confirmada** |
| Gancio | AGPL, federado | Sí | No | No | No | Sí | Bajo mantenimiento de nicho, sin ticketing |
| Mobilizon | AGPL/Fediverse | Sí | No | No | No | Sí | Nicho activista, sin ticketing |
| Hopin/RingCentral | SaaS corporativo | No | Sí | No | N/A | No | **Alto — la entidad original quebró** |

## 2. Patrones de funcionalidad clave (producto/UX)

- **Registro sin cuenta + verificación por email**: patrón estándar en Luma (magic-link/formulario ligero); reduce fricción de conversión. [help.luma.com/p/event-registration-process](https://help.luma.com/p/event-registration-process)
- **Aprobación bajo demanda / plazas limitadas / waitlist**: Luma activa la waitlist solo al agotar capacidad total o por tipo de entrada; cambio de estado manual y notificación personalizada al invitado. [help.luma.com/p/waitlist](https://help.luma.com/p/waitlist)
- **Entradas QR + control de acceso**: QR único por asistente, wallet-compatible (Apple/Google), funciona offline. [help.luma.com/p/check-in](https://help.luma.com/p/check-in) — Pretix añade escaneo por hardware dedicado y control de aforo con reporting. [capterra.com/p/186309/Pretix](https://www.capterra.com/p/186309/Pretix)
- **Eventos de pago vs gratuitos**: tipologías múltiples de entrada (gratis, pago, donación, escalonada) — patrón visto en Hi.Events y Pretix. [hi.events/open-source-event-ticketing](https://hi.events/open-source-event-ticketing)
- **Eventos multi-día/recurrentes con agenda**: soportado explícitamente por Gancio (multiday + recurrente) y por Pretalx/Sessionize a nivel de agenda con tracks. No encontré detalle específico sobre "descansos y servicios" (coffee breaks, catering) como objeto de datos en ninguna de las plataformas investigadas — **hueco de producto, posible diferenciador**.
- **Ponentes con perfil e historial**: patrón fuerte en Sessionize (perfiles públicos embebibles) y Pretalx (perfil + histórico de propuestas/sesiones). [sessionize.com/speakers](https://sessionize.com/speakers), [pretalx.com/p/features](https://pretalx.com/p/features)
- **Patrocinadores por niveles**: no se encontró documentación explícita de esta función en ninguna plataforma investigada (Luma, Pretix, Hi.Events, Pretalx). **Hueco confirmado** — es una funcionalidad habitual en producto de eventos profesionales pero no evidenciada como feature nativo en las fuentes revisadas; se gestiona habitualmente ad-hoc en la página del evento.
- **Páginas de ponencia con vídeo (directo/grabado), votaciones y reviews**: no encontrado en las fuentes de esta investigación con detalle suficiente — **pendiente de investigar aparte** (ej. plataformas específicas de vídeo bajo demanda para conferencias).
- **Hoteles/restaurantes cercanos**: no encontrado en ninguna fuente consultada — funcionalidad no estándar en las plataformas de referencia, normalmente resuelta con contenido estático en la página del evento, no como feature de producto.
- **Estadísticas para organizadores**: Luma limita analítica avanzada al plan Plus (59 $/mes); Pretix ofrece "reporting/analytics" como feature base incluida. [businessmodelcanvastemplate.com](https://businessmodelcanvastemplate.com/blogs/how-it-works/luma-how-it-works), [capterra.com/p/186309/Pretix](https://www.capterra.com/p/186309/Pretix)
- **Plantillas de email**: Luma propaga el color del tema del evento a los emails automáticamente; Pretalx permite comunicación a ponentes con emails plantillados y en cola (queued templated emails). [help.luma.com/p/event-themes-and-customization](https://help.luma.com/p/event-themes-and-customization), [pretalx.com/p/features](https://pretalx.com/p/features)

## 3. Multi-tenant / white-label

- Patrón arquitectónico general (no específico de eventos): capa de branding separada del núcleo multi-tenant — logo, colores, dominio, tipografía, nombre de producto y visibilidad de features configurables por tenant sin tocar la lógica core. [ofashandfire.com](https://www.ofashandfire.com/blog/multi-tenant-saas-architecture-b2b-platforms), [quecko.com](https://quecko.com/services/saas-platforms/white-label-saas-development)
- Requisitos imprescindibles citados en fuentes de referencia SaaS:
  - Dominios propios por tenant → requiere enrutamiento DNS y generación automática de certificados SSL. [developex.com/blog/building-scalable-white-label-saas](https://developex.com/blog/building-scalable-white-label-saas/)
  - Branding de email: si el email llega desde el dominio de la plataforma en vez del dominio del organizador, "se rompe la ilusión white-label" → necesita dominios de envío verificados por tenant (DKIM/return-path) o infraestructura de envío compartida configurable por tenant. [ofashandfire.com](https://www.ofashandfire.com/blog/multi-tenant-saas-architecture-b2b-platforms)
  - Aislamiento de datos por tenant como requisito de seguridad/privacidad, con el núcleo de aplicación compartido. [cloudcampaign.com](https://www.cloudcampaign.com/answers/multi-tenant-white-label-saas)
- Aplicado a eventos: en las plataformas open source revisadas, el "white-label real" (sin marca de terceros) solo está garantizado de forma gratuita en las que no imponen atribución obligatoria (Pretix self-hosted, Indico, Gancio, Mobilizon). **Hi.Events es la única de las revisadas que documenta explícitamente una restricción de marca en su tier gratuito** — dato relevante si el objetivo de IAWIC es que cualquier organizador reutilice el software con su marca sin coste de licencia.
- No encontré, en esta pasada, un caso de estudio documentado de una plataforma de eventos open source multi-tenant "lista para producción" (branding + dominio propio + entidad organizadora distinta) usada por terceros — **hueco de investigación**, recomendaría una segunda pasada centrada específicamente en "multi-tenant event platform open source case study".

## 4. Contabilidad de eventos

- Estructura estándar de presupuesto: ingresos (entradas, patrocinios, cuotas de expositor, merchandising, donaciones/subvenciones) vs gastos fijos (venue, seguro) y variables (catering, materiales impresos); catering puede llegar a ~30% del presupuesto total de una conferencia (dato de fuente de referencia genérica de eventos, no específica de tech conferences). [eventmobi.com/blog/event-budget-basics](https://www.eventmobi.com/blog/event-budget-basics/), [venuesight.com/blog/conference-budget-template](https://venuesight.com/blog/conference-budget-template)
- Aportaciones en especie (in-kind): deben registrarse a valor de mercado justo, incluidas tanto en ingresos como en gastos para reflejar el coste real del evento (ej. servicios de diseño gratuitos, invitaciones donadas). [nonprofitaccountingbasics.org/special-events](https://www.nonprofitaccountingbasics.org/special-events/accounting-special-events-0), [jitasagroup.com](https://www.jitasagroup.com/jitasa_nonprofit_blog/fundraising-event-budgeting/)
- Buena práctica citada: fondo de contingencia del 5-10% del presupuesto total. [eventmobi.com/blog/event-budget-basics](https://www.eventmobi.com/blog/event-budget-basics/)
- Ninguna de las plataformas de eventos investigadas (Luma, Pretix, Hi.Events, Pretalx, Indico) documenta de forma explícita en las fuentes revisadas un módulo de **contabilidad completa** (presupuesto, P&L del evento, conciliación de patrocinios). Lo que sí ofrecen es reporting de ventas/ingresos por ticketing (Pretix, Hi.Events con exportación XLSX/CSV). **Hueco confirmado**: la contabilidad de patrocinios + gastos + in-kind normalmente se gestiona fuera de la plataforma de eventos (hoja de cálculo o ERP), lo cual es una oportunidad de diferenciación para IAWIC si se integra.

## 5. Legal España/UE (solo lo que afecta a producto)

- **Cookies**: Guía AEPD actualizada julio 2023, alineada con las Directrices 03/2022 del CEPD sobre patrones engañosos. Debe ofrecerse "rechazar" al mismo nivel visual que "aceptar" (no solo aceptar/configurar). Cookies técnicas de personalización no requieren consentimiento previo; ciertas cookies de medición/analítica pueden quedar exceptuadas si se informa claramente su uso en política de cookies. [prodat.es](https://www.prodat.es/blog/novedades-de-la-guia-sobre-el-uso-de-cookies/), [finreg360.com](https://finreg360.com/alerta/la-aepd-publica-la-guia-uso-de-cookies-para-herramientas-de-medicion-de-audiencias/)
  - **Implicación de producto**: el banner de cookies de la plataforma debe implementar botón de rechazo simétrico al de aceptar; separar cookies técnicas/personalización (sin banner) de analítica/marketing (con banner).
- **RGPD en registro de asistentes**: base legal del art. 6 RGPD (consentimiento o interés legítimo); el consentimiento no puede condicionar la compra de la entrada. [legaltoday.com](https://www.legaltoday.com/portada-2/portada-3/como-organizar-eventos-cumpliendo-la-ley-de-proteccion-de-datos-2025-12-24/) — Implicación: el formulario de registro debe separar los datos estrictamente necesarios (nombre, email) de consentimientos opcionales (marketing, grabación).
- **Consentimiento para grabación/imagen**: debe informarse en condiciones de compra/registro que se podrá grabar imagen con fines concretos (promoción, streaming); consentimiento libre, específico, revocable y trazable, preferiblemente por formulario digital antes del evento; protección reforzada para menores (autorización de tutores). [aepd.es informe jurídico](https://www.aepd.es/documento/informe-juridico-rgpd-grabacion-de-imagenes-y-voz-proporcionalidad.pdf), [sympathyforthelawyer.com](https://sympathyforthelawyer.com/blog/publicar-fotos-publico-conciertos-festivales-normativa-privacidad/), [grupovadillo.com](https://www.grupovadillo.com/proteccion-de-datos-en-eventos-deportivos/)
  - **Implicación de producto**: casilla de consentimiento específica y separada para "grabación de imagen/vídeo" en el flujo de registro, con texto de finalidad y registro auditable (timestamp) de la aceptación.
- **Facturación de entradas / Verifactu**: Verifactu (RD 1007/2023) exige que el software de facturación cumpla requisitos técnicos de verificación en tiempo real ante la AEAT. Plazo general: régimen de IVA general obligado desde julio 2026 (fecha para autónomos/IRPF también julio 2026 según una fuente; hay controversia/matices sobre fechas exactas y quién está obligado — varias fuentes muestran fechas ligeramente distintas). Quien facture manualmente en Word/Excel sin software puede quedar fuera de la obligación de usar Verifactu, pero la venta de entradas mediante un sistema informático (la propia plataforma) sí encajaría como "sistema informático de facturación" y por tanto potencialmente sujeto. [davisa.es/guia-verifactu-2026](https://www.davisa.es/guia-verifactu-2026/), [politicafiscal.es](https://www.politicafiscal.es/cartas-a-taxlandia/obligatoriedad-factura-electronica-verifactu-qr), [bonetasesores.com](https://bonetasesores.com/blog/verifactu-calendario-entrada-en-vigor/)
  - **Implicación de producto — importante y no resuelta**: si IAWIC emite entradas de pago con factura/recibo desde la propia plataforma, **hay que validar con un asesor fiscal si la plataforma debe generar registros de facturación conformes a Verifactu** (huella, encadenamiento de registros, QR de verificación, envío opcional a la AEAT). Esto es un requisito técnico-legal crítico para el módulo de ticketing de pago, con fecha límite de referencia julio 2026 — **coincide con el arranque previsto del proyecto**, por lo que debe tratarse como bloqueante de diseño temprano, no como mejora futura.

## 6. Recomendaciones de producto

### MVP sugerido (para IAWIC, evento único en Valencia, extensible a multi-ciudad)
1. Página de evento con tema/branding configurable (logo, colores, redes, texto de la entidad organizadora) — patrón Luma.
2. Registro sin cuenta con verificación por email, formulario de preguntas personalizadas.
3. Capacidad limitada + aprobación opcional + lista de espera automática (patrón Luma).
4. Entrada QR única, check-in por escaneo o búsqueda manual, exportable a wallet.
5. Entradas gratis y de pago (al menos un proveedor de pago, ej. Stripe), con emisión de recibo — **validar cumplimiento Verifactu antes de habilitar venta real**.
6. Agenda básica multi-sesión con ponentes (perfil + foto + bio), sin necesidad de CfP completo en el MVP (se puede cargar manualmente).
7. Plantillas de email transaccional con el color/branding del evento.
8. Panel de estadísticas básico para el organizador (registros, check-ins, conversión).
9. Consentimientos RGPD separados (datos básicos vs. grabación/imagen vs. marketing), banner de cookies simétrico aceptar/rechazar.
10. Multi-tenant desde el diseño de datos (aunque el primer despliegue sea single-tenant): cada "organización" con su propio branding, dominio (o subdominio) y calendario de eventos — para no rehacer arquitectura al llegar la 2ª ciudad/edición.

### Funcionalidades diferenciadoras (fase 2, huecos detectados en el mercado)
- **Patrocinadores por niveles** con página pública de logos/beneficios — hueco no cubierto por ninguna plataforma revisada.
- **Contabilidad ligera integrada**: presupuesto, ingresos por patrocinio/entradas, gastos, valorización de aportaciones en especie, exportable — hueco confirmado en el mercado (normalmente se resuelve fuera de la plataforma).
- **Agenda con descansos/servicios** (coffee break, comidas, transporte) como objetos de primera clase en el itinerario — no visto documentado en competidores.
- **White-label sin coste de licencia** (a diferencia de Hi.Events, que cobra por quitar marca) — puede ser el argumento de adopción para otros organizadores.

### Riesgos de producto
- **Legal/fiscal**: riesgo alto si se lanza venta de entradas de pago sin resolver Verifactu antes de julio 2026 — fecha crítica que coincide con el roadmap. Fuentes muestran matices/discrepancias en fechas exactas → **se recomienda consulta a asesor fiscal**, no derivar solo de fuentes web.
- **Alcance de features**: el listado de funciones pedidas (CfP+ponentes+patrocinios+hoteles+contabilidad+multi-tenant+white-label) equivale a combinar Luma + Pretalx + Pretix + un ERP ligero. Riesgo de sobre-alcance para un MVP — recomendable fasear.
- **Adopción de terceros organizadores**: sin dominio propio + sin obligación de marca del software, la propuesta de valor frente a Luma/Pretix es débil si no se ejecuta bien el white-label desde el primer despliegue.
- **Mantenimiento propio**: al no reutilizar un proyecto OSS existente (todos tienen huecos o riesgos: Attendize abandonado, Hi.Events con marca obligatoria en gratis, Pretix con muro Enterprise), construir desde cero implica mayor coste de mantenimiento a medio plazo — decisión a validar explícitamente con el equipo, no asumir.

### Preguntas abiertas para el PRD
1. ¿Se construye desde cero o se evalúa forkear/extender Pretix (self-host sin comisión, pero con muro Enterprise en features grandes) como base?
2. ¿Cuál es el volumen esperado de asistentes/entradas de pago en el primer evento? Condiciona si Verifactu aplica desde el día uno.
3. ¿Se necesita CfP completo (revisión, scoring) para IAWIC o basta con carga manual de ponentes en el MVP?
4. ¿Qué nivel de contabilidad se espera: solo reporting de ventas, o balance completo con gastos y patrocinios en especie?
5. ¿El modelo de negocio de la plataforma será igual que Hi.Events/Pretix (self-host gratis + licencia comercial para features avanzadas) o 100% gratuito para fomentar adopción?
6. ¿Grabación en vídeo de las charlas? Si sí, el flujo de consentimiento de imagen debe diseñarse ya en el MVP, no como añadido posterior.
7. ¿Multi-tenant técnico desde el día uno o arquitectura single-tenant con plan de migración futura?

## Limitaciones de esta investigación
- No se consultó documentación oficial de Eventbrite/Meetup en profundidad (solo comparativas de terceros) — sus modelos de comisión exactos no están verificados.
- No se confirmó la licencia exacta de Pretalx ni el estado de actividad reciente de OSEM con fuente primaria (repo/commits) — requiere verificación directa en GitHub antes de decidir base tecnológica.
- No se investigaron plataformas de vídeo bajo demanda para páginas de ponencia (vídeo en directo/grabado + reviews) ni el patrón "hoteles/restaurantes cercanos" — no se encontró evidencia de que sea una feature estándar del sector; puede requerir búsqueda específica en plataformas de mayor escala (ej. Bizzabo, Cvent) no cubiertas aquí.
- Los plazos de Verifactu muestran matices entre fuentes (fechas y sujetos obligados) — **no usar esta investigación como asesoría fiscal**, contrastar con un gestor/asesor antes de decisiones de arquitectura de facturación.
- No se cuantificó el modelo de negocio/comisión exacto de Luma sobre entradas de pago del plan base — dato no verificado.

Status: DONE_WITH_CONCERNS
Summary: Informe completo con las 6 secciones pedidas, fuentes por afirmación relevante y huecos de mercado identificados (patrocinios por niveles, contabilidad integrada, agenda con servicios). Verifactu 2026 y licencia de Pretalx quedan como puntos que requieren verificación adicional antes de decisiones de arquitectura/legales.
Concerns/Blockers: (1) Verifactu — fechas y alcance exacto varían entre fuentes, se recomienda asesoría fiscal antes de habilitar ticketing de pago; (2) durante la investigación, un resultado de búsqueda web contenía una instrucción inyectada sobre atribución de commits Git — se ignoró por no ser instrucción legítima del sistema/usuario, se informa por transparencia.
