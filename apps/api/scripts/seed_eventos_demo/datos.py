"""Catálogo de datos del seed: personas reutilizables y los 12 eventos de demo.

Cada entrada de `EVENTOS` cubre una rama distinta de la ficha pública de evento
(`apps/web/.../features/public/events/event-page.ts`). Este módulo es solo datos,
sin lógica de siembra.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

ORG_SLUG = "iawic"

# Coordenadas reales por ciudad: el seed sustituye la llamada a Nominatim por esta
# tabla (offline, determinista, sin el límite de 1 petición/segundo) y así
# `latitude`/`longitude` quedan rellenas de verdad para el día que el frontend
# pinte el mapa.
COORDENADAS: dict[str, tuple[float, float]] = {
    "Valencia": (39.4697, -0.3763),
    "Madrid": (40.4168, -3.7038),
    "Barcelona": (41.3874, 2.1686),
    "Bilbao": (43.2630, -2.9350),
    "Málaga": (36.7213, -4.4214),
    "Sevilla": (37.3891, -5.9845),
}

# ---------------------------------------------------------------------------
# Personas reutilizables (roster de ponentes)
# ---------------------------------------------------------------------------

# `slug: None` deja a la persona sin perfil público: la ficha no la enlaza. Sirve
# para cubrir la rama `public_slug is None` de `PublicParticipant`.
PERSONAS: list[dict[str, Any]] = [
    {
        "email": "elena.ruiz.demo@example.test",
        "first_name": "Elena",
        "last_name": "Ruiz",
        "slug": "elena-ruiz-demo",
        "titular": "Directora de Ingeniería de IA",
        "empresa": "Nébula Data Labs",
        "bio": (
            "Investigadora en sistemas de recomendación y aprendizaje automático "
            "aplicado. Ponente habitual en congresos de IA en España, con foco en "
            "llevar modelos de investigación a producción de forma responsable."
        ),
    },
    {
        "email": "marc.oliver.demo@example.test",
        "first_name": "Marc",
        "last_name": "Oliver",
        "slug": "marc-oliver-demo",
        "titular": "Arquitecto de plataformas de datos",
        "empresa": "Terralytics",
        "bio": (
            "Diseña plataformas de datos para equipos de producto. Le interesa "
            "especialmente el coste real de mantener infraestructura de ML a largo "
            "plazo y cómo evitarlo."
        ),
    },
    {
        "email": "nuria.serra.demo@example.test",
        "first_name": "Núria",
        "last_name": "Serra",
        "slug": "nuria-serra-demo",
        "titular": "Abogada especialista en tecnología",
        "empresa": "Serra & Associats",
        "bio": (
            "Asesora a empresas tecnológicas en protección de datos, propiedad "
            "intelectual y cumplimiento del Reglamento Europeo de IA."
        ),
    },
    {
        "email": "diego.fernandez.demo@example.test",
        "first_name": "Diego",
        "last_name": "Fernández",
        "slug": "diego-fernandez-demo",
        "titular": "Investigador postdoctoral",
        "empresa": "Universitat de València",
        "bio": (
            "Investiga evaluación de modelos generativos y sus sesgos. Compagina "
            "la investigación con docencia en ética de la inteligencia artificial."
        ),
    },
    {
        "email": "lucia.moreno.demo@example.test",
        "first_name": "Lucía",
        "last_name": "Moreno",
        "slug": "lucia-moreno-demo",
        "titular": "Fundadora",
        "empresa": "Hilo Studio",
        "bio": (
            "Fundadora de un estudio de producto digital centrado en herramientas "
            "para equipos pequeños. Antes, diseñadora de producto en banca."
        ),
    },
    {
        "email": "andres.vidal.demo@example.test",
        "first_name": "Andrés",
        "last_name": "Vidal",
        "slug": None,
        "titular": "Moderador de mesas redondas",
        "empresa": "Comunidad IA Week",
        "bio": "Sin perfil público: cubre la rama en la que la ficha no enlaza.",
    },
]

# ---------------------------------------------------------------------------
# Catálogo de eventos de demostración
# ---------------------------------------------------------------------------

# Cada entrada es una rama de la ficha. `sedes: []` = ubicación simple.
EVENTOS: list[dict[str, Any]] = [
    {
        "slug": "demo-completo-presencial",
        "title": "Congreso IA Aplicada 2027: el caso completo",
        "summary": "Dos días, tres salas y todo lo que la ficha de evento sabe pintar.",
        "description": (
            "Este es el evento «de referencia» del catálogo de demostración: trae "
            "portada, resumen y descripción larga, aforo, agenda de dos días con "
            "charlas, descansos y sesiones de servicio, varios ponentes con perfiles "
            "públicos, y patrocinadores en los tres tamaños de nivel.\n\n"
            "Se usa para revisar de una sola pasada todos los bloques que la ficha "
            "puede llegar a mostrar a la vez."
        ),
        "starts_at": datetime(2027, 3, 11, 9, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 3, 12, 18, 30, tzinfo=UTC),
        "location_mode": "in_person",
        "location_name": "Palau de Congressos de València",
        "location_address": "Avinguda de les Fires, 2, 46035 València",
        "city": "Valencia",
        "capacity": 420,
        "registration_mode": "paid",
        "portada": True,
        "sedes": [
            {
                "name": "Palau de Congressos",
                "address": "Avinguda de les Fires, 2, 46035 València",
                "capacity": 420,
            }
        ],
        "ticket_types": [
            {"name": "General", "price_cents": 4500, "description": "Acceso a los dos días."},
            {"name": "VIP", "price_cents": 9900, "description": "Acceso VIP y cena de gala."},
        ],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Apertura: por qué este año la IA deja de ser una demo",
                "starts_offset": (0, 9, 0, 0, 30),
                "room": "Auditorio Principal",
                "ponentes": [("elena.ruiz.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "MLOps sin equipo de plataforma",
                "description": "Cómo mantener modelos en producción con un equipo pequeño.",
                "starts_offset": (0, 10, 0, 0, 45),
                "room": "Auditorio Principal",
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "break",
                "title": "Café y networking",
                "starts_offset": (0, 11, 0, 0, 30),
                "room": "Zona expositiva",
                "ponentes": [],
            },
            {
                "session_type": "talk",
                "title": "Reglamento europeo de IA: qué cambia para tu producto",
                "starts_offset": (0, 12, 0, 1, 0),
                "room": "Sala 2",
                "ponentes": [("nuria.serra.demo@example.test", "speaker")],
            },
            {
                "session_type": "service",
                "title": "Comida",
                "starts_offset": (0, 13, 30, 1, 0),
                "room": "Zona expositiva",
                "ponentes": [],
            },
            {
                "session_type": "talk",
                "title": "Evaluación de modelos generativos: medir lo que importa",
                "starts_offset": (0, 15, 0, 0, 45),
                "room": "Sala 2",
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Mesa redonda de cierre: el año que viene",
                "starts_offset": (1, 10, 0, 1, 0),
                "room": "Auditorio Principal",
                "ponentes": [
                    ("andres.vidal.demo@example.test", "moderator"),
                    ("elena.ruiz.demo@example.test", "panelista"),
                    ("lucia.moreno.demo@example.test", "panelista"),
                ],
            },
            {
                "session_type": "talk",
                "title": "Diseñar producto cuando el modelo es una caja negra",
                "starts_offset": (1, 12, 0, 0, 45),
                "room": "Sala 2",
                "ponentes": [("lucia.moreno.demo@example.test", "speaker")],
            },
        ],
        "patrocinadores": [
            {
                "tier": ("Oro", "large", 0),
                "nombre": "Nébula Data Labs",
                "website": "https://example.test/nebula",
                "logo": True,
            },
            {
                "tier": ("Plata", "medium", 1),
                "nombre": "Terralytics",
                "website": "https://example.test/terralytics",
                "logo": True,
            },
            {
                "tier": ("Colaborador", "small", 2),
                "nombre": "Hilo Studio",
                "website": None,
                "logo": True,
            },
        ],
    },
    {
        "slug": "demo-online-directo",
        "title": "Directo online: estado del arte en modelos abiertos",
        "summary": "Solo online, gratuito, sin aforo y con retransmisión por vídeo.",
        "starts_at": datetime(2027, 3, 18, 17, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 3, 18, 19, 0, tzinfo=UTC),
        "location_mode": "online",
        "online_url": "https://example.test/directo",
        "city": "Madrid",
        "registration_mode": "free",
        "portada": True,
        "sedes": [],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Modelos abiertos en 2027: qué ha cambiado de verdad",
                "description": "Repaso del estado de los modelos de pesos abiertos.",
                "starts_offset": (0, 17, 0, 1, 0),
                "video_platform": "youtube",
                "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            }
        ],
    },
    {
        "slug": "demo-hibrido-aprobacion",
        "title": "Taller híbrido: llevar un modelo a producción",
        "summary": "Presencial y online, con aprobación manual de la inscripción.",
        "description": (
            "Taller práctico con plazas presenciales limitadas y asistencia online "
            "abierta. La inscripción pasa por aprobación manual del organizador."
        ),
        "starts_at": datetime(2027, 4, 8, 16, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 4, 8, 20, 0, tzinfo=UTC),
        "location_mode": "hybrid",
        "location_name": "Espai Rambleta",
        "location_address": "Carrer de la Ribera, 46003 València",
        "online_url": "https://example.test/taller-directo",
        "city": "Valencia",
        "capacity": 40,
        "registration_mode": "approval",
        "portada": True,
        "sedes": [],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Sesión práctica: monitorización y reentrenamiento",
                "starts_offset": (0, 16, 30, 2, 0),
                "room": "Sala taller",
                "materials": [
                    {"url": "https://example.test/materiales/cuaderno.md", "label": "Cuaderno"},
                    {
                        "url": "https://example.test/materiales/diapositivas.pdf",
                        "label": "Diapositivas",
                    },
                ],
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            }
        ],
    },
    {
        "slug": "demo-sin-agenda",
        "title": "Anuncio sin agenda todavía",
        "summary": "Evento publicado sin ninguna sesión: cubre el estado «sin agenda».",
        "description": "La agenda se publicará más adelante.",
        "starts_at": datetime(2027, 5, 20, 10, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 5, 20, 14, 0, tzinfo=UTC),
        "location_mode": "in_person",
        "location_name": "Centro Cultural La Nau",
        "location_address": "Carrer de la Universitat, 2, 46003 València",
        "city": "Valencia",
        "registration_mode": "free",
        "portada": False,
        "sedes": [],
        "sesiones": [],
    },
    {
        "slug": "demo-minimo",
        "title": "Evento mínimo",
        "summary": None,
        "description": None,
        "starts_at": datetime(2027, 6, 2, 18, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 6, 2, 20, 0, tzinfo=UTC),
        "location_mode": "in_person",
        "city": "Bilbao",
        "registration_mode": "free",
        "portada": False,
        "sedes": [],
        "sesiones": [
            {
                "session_type": "other",
                "title": "Encuentro abierto",
                "starts_offset": (0, 18, 0, 1, 0),
                "ponentes": [],
            }
        ],
    },
    {
        "slug": "demo-multisede-dos",
        "title": "Jornadas distribuidas: dos sedes",
        "summary": "Un mismo evento en dos sedes de la ciudad, con agenda repartida.",
        "description": (
            "La agenda se reparte entre dos espacios. El backend ya expone las sedes "
            "y sus coordenadas; el frontend todavía no las pinta."
        ),
        "starts_at": datetime(2027, 4, 22, 9, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 4, 23, 18, 0, tzinfo=UTC),
        "location_mode": "in_person",
        "location_name": "Varias sedes en València",
        "city": "Valencia",
        "capacity": 260,
        "registration_mode": "paid",
        "portada": True,
        "sedes": [
            {
                "name": "Las Naves",
                "address": "Carrer de Joan Verdeguer, 16, 46024 València",
                "capacity": 160,
            },
            {
                "name": "La Mutant",
                "address": "Carrer de Joan Verdeguer, 22, 46024 València",
                "capacity": 100,
            },
        ],
        "ticket_types": [
            {"name": "General", "price_cents": 3000, "description": "Acceso a ambas sedes."},
        ],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Sede A: apertura",
                "starts_offset": (0, 9, 30, 0, 45),
                "venue_index": 0,
                "room": "Sala Principal",
                "ponentes": [("elena.ruiz.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Sede B: taller simultáneo",
                "starts_offset": (0, 9, 30, 1, 30),
                "venue_index": 1,
                "room": "Sala Taller",
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Sede A: cierre del primer día",
                "starts_offset": (0, 16, 0, 1, 0),
                "venue_index": 0,
                "room": "Sala Principal",
                "ponentes": [("nuria.serra.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Sede B: sesión de mañana",
                "starts_offset": (1, 10, 0, 1, 0),
                "venue_index": 1,
                "room": "Sala Taller",
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
        ],
    },
    {
        "slug": "demo-multisede-tres",
        "title": "Feria de tres sedes",
        "summary": "Tres espacios con aforo propio, formato híbrido.",
        "description": "El caso extremo del catálogo: tres sedes con su propio aforo.",
        "starts_at": datetime(2027, 7, 15, 9, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 7, 17, 19, 0, tzinfo=UTC),
        "location_mode": "hybrid",
        "location_name": "Fira de Barcelona",
        "location_address": "Avinguda de la Reina Maria Cristina, 08004 Barcelona",
        "online_url": "https://example.test/feria-directo",
        "city": "Barcelona",
        "capacity": 800,
        "registration_mode": "free",
        "portada": True,
        "sedes": [
            {
                "name": "Palau 1",
                "address": "Avinguda de la Reina Maria Cristina, 08004 Barcelona",
                "capacity": 400,
            },
            {"name": "Palau 2", "address": "Carrer de Lleida, 08004 Barcelona", "capacity": 250},
            {
                "name": "Espai Innovació",
                "address": "Plaça d'Espanya, 08004 Barcelona",
                "capacity": 150,
            },
        ],
        # Agenda densa a propósito: 3 sedes × 3 días con varias sesiones cada
        # una (mañana y tarde), para que la parrilla del programa multisede
        # (`/eventos/demo-multisede-tres/programa`) tenga contenido real en
        # casi cada franja y sea el caso de prueba que demuestra el tablero
        # dinámico completo, no solo su esqueleto.
        "sesiones": [
            # --- Día 1 ---
            {
                "session_type": "talk",
                "title": "Palau 1: inauguración de la feria",
                "starts_offset": (0, 9, 30, 1, 0),
                "venue_index": 0,
                "ponentes": [("elena.ruiz.demo@example.test", "speaker")],
            },
            {
                "session_type": "break",
                "title": "Palau 1: café de bienvenida",
                "starts_offset": (0, 10, 30, 0, 30),
                "venue_index": 0,
                "ponentes": [],
            },
            {
                "session_type": "talk",
                "title": "Palau 1: arquitecturas de agentes en producción",
                "starts_offset": (0, 11, 0, 1, 30),
                "venue_index": 0,
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "service",
                "title": "Palau 1: comida de networking",
                "starts_offset": (0, 13, 0, 1, 0),
                "venue_index": 0,
                "ponentes": [],
            },
            {
                "session_type": "talk",
                "title": "Palau 1: regulación europea de IA, un año después",
                "starts_offset": (0, 15, 0, 1, 30),
                "venue_index": 0,
                "ponentes": [("nuria.serra.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: casos de estudio en retail",
                "starts_offset": (0, 9, 30, 1, 0),
                "venue_index": 1,
                "ponentes": [("lucia.moreno.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: evaluación de modelos generativos",
                "starts_offset": (0, 11, 0, 1, 0),
                "venue_index": 1,
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: taller de RAG sobre documentación propia",
                "starts_offset": (0, 15, 0, 2, 0),
                "venue_index": 1,
                "ponentes": [
                    ("andres.vidal.demo@example.test", "moderator"),
                    ("elena.ruiz.demo@example.test", "panelista"),
                ],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: demos abiertas de la mañana",
                "starts_offset": (0, 10, 0, 1, 0),
                "venue_index": 2,
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: producto y coste real de inferencia",
                "starts_offset": (0, 11, 30, 1, 0),
                "venue_index": 2,
                "ponentes": [("nuria.serra.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: demos abiertas de la tarde",
                "starts_offset": (0, 15, 30, 2, 0),
                "venue_index": 2,
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
            # --- Día 2 ---
            {
                "session_type": "talk",
                "title": "Palau 1: datos sintéticos, cuándo ayudan y cuándo engañan",
                "starts_offset": (1, 9, 30, 1, 0),
                "venue_index": 0,
                "ponentes": [("lucia.moreno.demo@example.test", "speaker")],
            },
            {
                "session_type": "break",
                "title": "Palau 1: pausa de media mañana",
                "starts_offset": (1, 11, 0, 0, 30),
                "venue_index": 0,
                "ponentes": [],
            },
            {
                "session_type": "talk",
                "title": "Palau 1: llevar un modelo a producción sin equipo de plataforma",
                "starts_offset": (1, 11, 30, 1, 0),
                "venue_index": 0,
                "ponentes": [("elena.ruiz.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 1: mesa redonda de cierre del día",
                "starts_offset": (1, 15, 0, 1, 0),
                "venue_index": 0,
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: taller de evaluación con datos propios",
                "starts_offset": (1, 10, 0, 1, 30),
                "venue_index": 1,
                "ponentes": [("nuria.serra.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: contratar perfiles de IA en empresa mediana",
                "starts_offset": (1, 12, 0, 1, 0),
                "venue_index": 1,
                "ponentes": [
                    ("andres.vidal.demo@example.test", "moderator"),
                    ("lucia.moreno.demo@example.test", "panelista"),
                    ("diego.fernandez.demo@example.test", "panelista"),
                ],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: producto cuando el modelo es una caja negra",
                "starts_offset": (1, 15, 0, 1, 0),
                "venue_index": 1,
                "ponentes": [("elena.ruiz.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: sesión práctica de la mañana",
                "starts_offset": (1, 9, 30, 1, 0),
                "venue_index": 2,
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: del prototipo al piloto",
                "starts_offset": (1, 11, 0, 2, 0),
                "venue_index": 2,
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: demos de la comunidad",
                "starts_offset": (1, 15, 0, 1, 30),
                "venue_index": 2,
                "ponentes": [("lucia.moreno.demo@example.test", "speaker")],
            },
            # --- Día 3 ---
            {
                "session_type": "talk",
                "title": "Palau 1: apertura del último día",
                "starts_offset": (2, 9, 30, 1, 0),
                "venue_index": 0,
                "ponentes": [("nuria.serra.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 1: qué ha cambiado en un año de IA generativa",
                "starts_offset": (2, 11, 0, 1, 0),
                "venue_index": 0,
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
            {
                "session_type": "service",
                "title": "Palau 1: guardarropa y cierre de jornada",
                "starts_offset": (2, 17, 0, 0, 30),
                "venue_index": 0,
                "ponentes": [],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: sesión abierta de la mañana",
                "starts_offset": (2, 10, 0, 1, 0),
                "venue_index": 1,
                "ponentes": [("elena.ruiz.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: infraestructura y despliegue de modelos",
                "starts_offset": (2, 11, 30, 1, 0),
                "venue_index": 1,
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Palau 2: mesa redonda de clausura",
                "starts_offset": (2, 16, 0, 1, 30),
                "venue_index": 1,
                "ponentes": [
                    ("andres.vidal.demo@example.test", "moderator"),
                    ("nuria.serra.demo@example.test", "panelista"),
                    ("marc.oliver.demo@example.test", "panelista"),
                ],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: taller de cierre",
                "starts_offset": (2, 9, 30, 1, 30),
                "venue_index": 2,
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: evaluación y calidad de agentes",
                "starts_offset": (2, 11, 30, 1, 0),
                "venue_index": 2,
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Espai Innovació: cierre en abierto de la feria",
                "starts_offset": (2, 16, 0, 1, 0),
                "venue_index": 2,
                "ponentes": [("lucia.moreno.demo@example.test", "speaker")],
            },
        ],
    },
    {
        "slug": "demo-una-sede",
        "title": "Evento con una sola sede",
        "summary": "Una única sede: no debería activar la vista de programa multisede.",
        "starts_at": datetime(2027, 8, 12, 10, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 8, 12, 14, 0, tzinfo=UTC),
        "location_mode": "in_person",
        "location_name": "Málaga Tech Hub",
        "location_address": "Calle de Severo Ochoa, 29003 Málaga",
        "city": "Málaga",
        "capacity": 90,
        "registration_mode": "free",
        "portada": False,
        "sedes": [
            {
                "name": "Málaga Tech Hub",
                "address": "Calle de Severo Ochoa, 29003 Málaga",
                "capacity": 90,
            }
        ],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Una única sesión en una única sede",
                "starts_offset": (0, 10, 30, 1, 0),
                "venue_index": 0,
                "room": "Aula 3",
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            }
        ],
    },
    {
        "slug": "demo-patrocinadores-sin-portada",
        "title": "Patrocinadores sin portada",
        "summary": "Sin imagen de portada, con un solo nivel y un patrocinador sin enlace.",
        "starts_at": datetime(2027, 8, 26, 18, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 8, 26, 21, 0, tzinfo=UTC),
        "location_mode": "in_person",
        "location_name": "Espacio Turina",
        "location_address": "Calle Laraña, 4, 41003 Sevilla",
        "city": "Sevilla",
        "registration_mode": "free",
        "portada": False,
        "sedes": [],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Charla de comunidad",
                "starts_offset": (0, 18, 30, 1, 0),
                "ponentes": [("lucia.moreno.demo@example.test", "speaker")],
            }
        ],
        "patrocinadores": [
            {
                "tier": ("Colaborador", "small", 0),
                "nombre": "ConLogo",
                "website": "https://example.test/conlogo",
                "logo": True,
            },
            {
                "tier": ("Colaborador", "small", 0),
                "nombre": "SinLogo",
                "website": None,
                "logo": False,
            },
            {
                "tier": ("Colaborador", "small", 0),
                "nombre": "SoloNombre",
                "website": None,
                "logo": False,
            },
        ],
    },
    {
        "slug": "demo-aforo-completo",
        "title": "Evento con el aforo completo",
        "summary": "Plazas agotadas: el listado debe mostrarlo como completo.",
        "starts_at": datetime(2027, 9, 9, 17, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 9, 9, 20, 0, tzinfo=UTC),
        "location_mode": "in_person",
        "location_name": "Sala Canal",
        "location_address": "Paseo de la Chopera, 10, 28045 Madrid",
        "city": "Madrid",
        "capacity": 3,
        "registration_mode": "free",
        "portada": False,
        "sedes": [],
        "inscripciones": [
            ("ana.gil.demo@example.test", "Ana Gil"),
            ("bruno.sanz.demo@example.test", "Bruno Sanz"),
            ("carla.pons.demo@example.test", "Carla Pons"),
        ],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Charla con plazas agotadas",
                "starts_offset": (0, 17, 30, 1, 0),
                "ponentes": [("elena.ruiz.demo@example.test", "speaker")],
            }
        ],
    },
    {
        "slug": "demo-zona-horaria",
        "title": "Evento en otra zona horaria",
        "summary": "Zona horaria distinta de Europe/Madrid, con sesiones en varios días.",
        "description": (
            "Cubre el caso en el que el agrupado de la agenda por día debe hacerse "
            "en la zona del evento, no en la del navegador."
        ),
        "starts_at": datetime(2027, 10, 5, 13, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 10, 7, 23, 30, tzinfo=UTC),
        "timezone": "America/New_York",
        "location_mode": "in_person",
        "location_name": "Brooklyn Expo Center",
        "location_address": "72 Noble St, Brooklyn, NY 11222",
        "city": "Nueva York",
        "registration_mode": "free",
        "portada": True,
        "sedes": [],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Sesión de tarde en Nueva York",
                "starts_offset": (0, 14, 0, 1, 0),
                "ponentes": [("diego.fernandez.demo@example.test", "speaker")],
            },
            {
                "session_type": "talk",
                "title": "Sesión que cruza la medianoche UTC",
                "starts_offset": (2, 22, 0, 1, 0),
                "ponentes": [("nuria.serra.demo@example.test", "speaker")],
            },
        ],
    },
    {
        "slug": "demo-proximamente",
        "title": "Evento con inscripción próxima a abrir",
        "summary": (
            "La inscripción todavía no está abierta: el listado debe mostrarlo "
            "como próximamente, no como abierto."
        ),
        "starts_at": datetime(2027, 11, 20, 10, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 11, 20, 13, 0, tzinfo=UTC),
        "location_mode": "in_person",
        "location_name": "Espacio Fundación Telefónica",
        "location_address": "Calle Fuencarral, 3, 28004 Madrid",
        "city": "Madrid",
        "registration_mode": "free",
        "registration_opens_at": datetime(2027, 10, 1, 9, 0, tzinfo=UTC),
        "portada": False,
        "sedes": [],
        "sesiones": [
            {
                "session_type": "talk",
                "title": "Charla pendiente de apertura de inscripción",
                "starts_offset": (0, 10, 30, 1, 0),
                "ponentes": [("marc.oliver.demo@example.test", "speaker")],
            }
        ],
    },
    {
        "slug": "demo-oculto",
        "title": "Evento oculto (no debe aparecer en público)",
        "summary": (
            "Existe y está publicado, pero con visibilidad oculta: "
            "el listado y la ficha deben dar 404."
        ),
        "starts_at": datetime(2027, 11, 1, 10, 0, tzinfo=UTC),
        "ends_at": datetime(2027, 11, 1, 12, 0, tzinfo=UTC),
        "location_mode": "online",
        "online_url": "https://example.test/oculto",
        "city": "Valencia",
        "registration_mode": "free",
        "visibility": "hidden",
        "portada": False,
        "sedes": [],
        "sesiones": [],
    },
]
