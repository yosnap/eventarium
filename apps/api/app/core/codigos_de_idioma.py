"""Códigos de idioma ISO 639-1.

Las URL públicas llevan el idioma como primer segmento (`/en/…`), el mismo sitio que
ocupa el identificador de una organización (`/{org}/…`). Por eso ninguna organización
puede llamarse como un código de idioma: se reservan todos, no solo los que la
plataforma ofrece hoy, para que añadir un idioma no deje sin página a nadie. Incluye
también los retirados del estándar (`bh`, `sh`), que siguen pareciendo un idioma.
"""

from __future__ import annotations

from typing import Final

from app.core.locale import LOCALES

CODIGOS_ISO_639_1: Final[frozenset[str]] = frozenset(
    """
aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu
cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi
ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks
ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl
nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg sh si sk
sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz
ve vi vo wa wo xh yi yo za zh zu
    """.split()
)

#: Lo que no puede ser el identificador de una organización por coincidir con un
#: idioma: los códigos de dos letras y los códigos completos del catálogo (`en-us`).
IDENTIFICADORES_DE_IDIOMA: Final[frozenset[str]] = CODIGOS_ISO_639_1 | frozenset(
    locale.lower() for locale in LOCALES
)
