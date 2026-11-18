"""Mensajes del código que llegan a una persona, sacados del código fuente (AST).

Lo usan el test de calidad (todos son literales y todos están traducidos) y el
comando que genera los catálogos con IA. Cuenta como mensaje:

- el primer argumento (o `detail=`) al crear un error de dominio
  (`DomainError` y sus subclases, en cualquier módulo);
- el `title` de esas clases;
- el mensaje de un `ValueError` (o de un `ErrorDeValidacion`, su variante con
  parámetros) lanzado dentro de un validador de Pydantic (`field_validator`,
  `model_validator`), que Pydantic devuelve como error 422;
- el primer argumento de `t(...)`;
- las plantillas de `mensajes/validacion.py`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

RAIZ_APP = Path(__file__).resolve().parents[2]
BASE_DE_ERRORES = "DomainError"
VALIDADORES = {"field_validator", "model_validator", "validator", "root_validator"}
#: Comentario que exime a un mensaje no literal ya registrado con `marcar("…")`.
MARCA = "# mensaje marcado"
#: Comentario de un `ValueError` técnico que nunca llega a una persona.
MARCA_INTERNA = "# mensaje interno"


@dataclass
class Extraccion:
    mensajes: set[str] = field(default_factory=set)
    #: `fichero:línea` de los mensajes que no son un literal (f-string, variable…).
    no_literales: list[str] = field(default_factory=list)


#: La propia infraestructura de traducción, que trabaja con mensajes ya extraídos.
EXCLUIDOS = {RAIZ_APP / "shared" / "errors.py", *Path(__file__).resolve().parent.glob("*.py")}


def _ficheros() -> list[Path]:
    return sorted(p for p in RAIZ_APP.rglob("*.py") if "tests" not in p.parts)


def clases_de_error(arboles: dict[Path, ast.Module]) -> set[str]:
    """Nombres de `DomainError` y de todas sus subclases, a cualquier profundidad."""
    herencia: dict[str, set[str]] = {}
    for arbol in arboles.values():
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef):
                bases = {
                    b.id if isinstance(b, ast.Name) else b.attr
                    for b in nodo.bases
                    if isinstance(b, (ast.Name, ast.Attribute))
                }
                herencia.setdefault(nodo.name, set()).update(bases)
    clases = {BASE_DE_ERRORES}
    cambio = True
    while cambio:
        cambio = False
        for nombre, bases in herencia.items():
            if nombre not in clases and bases & clases:
                clases.add(nombre)
                cambio = True
    return clases


def _nombre(llamada: ast.Call) -> str | None:
    funcion = llamada.func
    if isinstance(funcion, ast.Name):
        return funcion.id
    if isinstance(funcion, ast.Attribute):
        return funcion.attr
    return None


def _mensaje(llamada: ast.Call) -> ast.expr | None:
    if llamada.args:
        return llamada.args[0]
    for argumento in llamada.keywords:
        if argumento.arg == "detail":
            return argumento.value
    return None


def _es_validador(funcion: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorador in funcion.decorator_list:
        objetivo = decorador.func if isinstance(decorador, ast.Call) else decorador
        nombre = (
            objetivo.id
            if isinstance(objetivo, ast.Name)
            else objetivo.attr
            if isinstance(objetivo, ast.Attribute)
            else None
        )
        if nombre in VALIDADORES:
            return True
    return False


def extraer() -> Extraccion:
    arboles = {ruta: ast.parse(ruta.read_text(encoding="utf-8")) for ruta in _ficheros()}
    errores = clases_de_error(arboles)
    resultado = Extraccion()
    # La propia infraestructura de traducción trabaja con mensajes ya extraídos
    # (`t(self.plantilla)`): de ella solo se recogen sus literales («Error
    # interno», los títulos de los errores), sin exigir que todo lo sea.
    lineas = {ruta: ruta.read_text(encoding="utf-8").splitlines() for ruta in arboles}

    def anotar(valor: ast.expr | None, ruta: Path) -> None:
        if valor is None:
            return
        if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
            resultado.mensajes.add(valor.value)
            return
        if ruta in EXCLUIDOS:
            return
        # `marcar("…")` ya registra su literal.
        if (
            isinstance(valor, ast.Call)
            and _nombre(valor) == "marcar"
            and valor.args
            and isinstance(valor.args[0], ast.Constant)
        ):
            return
        # Un valor elegido de mensajes ya registrados con `marcar("…")`.
        fin = getattr(valor, "end_lineno", valor.lineno) or valor.lineno
        # El mensaje, la línea siguiente y las dos anteriores (la marca va encima
        # del `raise`, y el mensaje puede ir en la línea de después).
        tramo = lineas[ruta][max(valor.lineno - 3, 0) : fin + 1]
        if any(MARCA in linea or MARCA_INTERNA in linea for linea in tramo):
            return
        resultado.no_literales.append(f"{ruta.relative_to(RAIZ_APP.parent)}:{valor.lineno}")

    for ruta, arbol in arboles.items():
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and nodo.name in errores:
                for sentencia in nodo.body:
                    if (
                        isinstance(sentencia, (ast.Assign, ast.AnnAssign))
                        and isinstance(sentencia.value, ast.Constant)
                        and isinstance(sentencia.value.value, str)
                        and any(
                            isinstance(objetivo, ast.Name) and objetivo.id == "title"
                            for objetivo in (
                                sentencia.targets
                                if isinstance(sentencia, ast.Assign)
                                else [sentencia.target]
                            )
                        )
                    ):
                        resultado.mensajes.add(sentencia.value.value)
            if not isinstance(nodo, ast.Call):
                continue
            nombre = _nombre(nodo)
            if nombre == "marcar":
                anotar(_mensaje(nodo), ruta)
            elif nombre in errores or nombre == "t":
                anotar(_mensaje(nodo), ruta)
            elif nombre in ("ValueError", "ErrorDeValidacion"):
                # Dentro o fuera de un validador: las funciones auxiliares que llaman
                # los validadores también acaban en un 422.
                anotar(_mensaje(nodo), ruta)

    from app.core.mensajes.validacion import PLANTILLAS

    resultado.mensajes.update(PLANTILLAS.values())
    return resultado
