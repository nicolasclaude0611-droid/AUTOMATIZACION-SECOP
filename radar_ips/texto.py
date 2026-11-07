"""Utilidades para comparar texto sin tildes ni mayúsculas."""

import re
import unicodedata


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin tildes y con la puntuación convertida en espacios."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower())
    return f" {texto.strip()} "


def _patron(termino: str) -> re.Pattern:
    prefijo = termino.endswith("*")
    base = normalizar(termino.rstrip("*")).strip()
    fin = "" if prefijo else r"(?![a-z0-9])"
    return re.compile(r"(?<![a-z0-9])" + re.escape(base) + fin)


class Buscador:
    """Busca una lista de términos dentro de un texto ya normalizado."""

    def __init__(self, terminos: list[str]):
        self.terminos = [(t, _patron(t)) for t in terminos if t.strip("* ")]

    def encontrados(self, texto_normalizado: str) -> list[str]:
        return [t for t, p in self.terminos if p.search(texto_normalizado)]
