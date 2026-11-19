"""Texto del correo de recordatorio.

Título, lugar y dirección los escribe el organizador: pasan por
`neutralizar_texto_de_usuario` para que una URL dentro no se convierta en el
botón de un correo que sale con el remitente de la plataforma. El botón es la
primera URL del cuerpo, así que el orden es: «mi entrada», cancelar y, al
final, el enlace para conectarse a un evento en línea (sin neutralizar: tiene
que funcionar).

Los textos y las fechas van en el idioma de la inscripción (`idioma`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.email_template import neutralizar_texto_de_usuario
from app.core.fechas import fecha_y_hora
from app.core.locale import DEFAULT_LOCALE, Locale
from app.core.mensajes import t


@dataclass(frozen=True, slots=True)
class DatosDelRecordatorio:
    titulo: str
    inicio: datetime
    zona: str
    modalidad: str
    lugar: str | None
    direccion: str | None
    ciudad: str | None
    url_online: str | None
    enlace_mi_entrada: str
    enlace_cancelacion: str
    hay_lista_de_espera: bool
    con_qr: bool
    # `en_curso`: se devolvería el importe; `sin_reembolso`: ya no; `None`: sin pago.
    reembolso: str | None
    limite_de_reembolso: datetime | None
    idioma: Locale = DEFAULT_LOCALE


def _donde(datos: DatosDelRecordatorio) -> str | None:
    if datos.modalidad == "online":
        return t("En línea (el enlace para conectarte está al final de este correo).", datos.idioma)
    partes = [
        neutralizar_texto_de_usuario(parte)
        for parte in (datos.lugar, datos.direccion, datos.ciudad)
        if parte and parte.strip()
    ]
    if not partes:
        return None
    sede = ", ".join(partes)
    if datos.modalidad == "hybrid":
        return t(
            "{sede} (o en línea: el enlace está al final de este correo).", datos.idioma, sede=sede
        )
    return sede


def asunto_y_cuerpo(datos: DatosDelRecordatorio) -> tuple[str, str]:
    idioma = datos.idioma
    titulo = neutralizar_texto_de_usuario(datos.titulo)
    cuando = fecha_y_hora(datos.inicio, datos.zona, idioma)
    asunto = t("Recordatorio: {titulo} — {cuando}", idioma, titulo=titulo, cuando=cuando)

    lineas = [
        t("Hola,", idioma),
        t("Te recordamos tu inscripción a «{titulo}».", idioma, titulo=titulo),
        t("Cuándo: {cuando} (hora del evento)", idioma, cuando=cuando),
    ]
    donde = _donde(datos)
    if donde:
        lineas.append(t("Dónde: {donde}", idioma, donde=donde))
    parrafos = [
        lineas[0],
        "\n".join(lineas[1:]),
        (
            t(
                "Tu entrada es el código QR de este correo: muéstrala en la puerta. "
                "También puedes verla aquí:\n{enlace}",
                idioma,
                enlace=datos.enlace_mi_entrada,
            )
            if datos.con_qr
            else t(
                "Puedes consultar tu inscripción aquí:\n{enlace}",
                idioma,
                enlace=datos.enlace_mi_entrada,
            )
        ),
    ]
    parrafos.append(
        t(
            "¿No puedes ir? Cancela tu inscripción y tu plaza quedará libre para otra "
            "persona de la lista de espera:\n{enlace}",
            idioma,
            enlace=datos.enlace_cancelacion,
        )
        if datos.hay_lista_de_espera
        else t(
            "¿No puedes ir? Cancela tu inscripción y tu plaza quedará libre:\n{enlace}",
            idioma,
            enlace=datos.enlace_cancelacion,
        )
    )
    if datos.reembolso == "en_curso" and datos.limite_de_reembolso is not None:
        parrafos.append(
            t(
                "Si cancelas antes del {limite}, se te devuelve el importe.",
                idioma,
                limite=fecha_y_hora(datos.limite_de_reembolso, datos.zona, idioma),
            )
        )
    elif datos.reembolso == "sin_reembolso":
        parrafos.append(
            t(
                "Ya ha pasado el plazo de reembolso: si cancelas, no se devuelve el importe.",
                idioma,
            )
        )
    parrafos.append(
        t(
            "Las ausencias sin avisar pueden tenerse en cuenta al revisar tus próximas "
            "inscripciones.",
            idioma,
        )
    )
    if datos.url_online and datos.modalidad in ("online", "hybrid"):
        parrafos.append(t("Enlace para conectarte:\n{enlace}", idioma, enlace=datos.url_online))
    return asunto, "\n\n".join(parrafos)
