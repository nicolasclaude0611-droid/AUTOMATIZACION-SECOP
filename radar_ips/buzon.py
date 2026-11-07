"""Lectura de las alertas oficiales de SECOP II que llegan a un buzón de correo.

SECOP II envía un correo cuando se publica un proceso con los códigos UNSPSC
a los que el proveedor está suscrito. Este módulo lee esos correos por IMAP
(sin marcarlos como leídos ni modificarlos) y los convierte en procesos con
el mismo formato que usan las fuentes de datos abiertos.
"""

import email
import email.policy
import email.utils
import hashlib
import imaplib
import logging
import os
import re
from datetime import date, timedelta
from email.message import EmailMessage
from html.parser import HTMLParser

log = logging.getLogger(__name__)

RE_NTC = re.compile(r"CO1\.NTC\.\d+")
RE_UNSPSC = re.compile(r"(?<!\d)(\d{8})(?!\d)")
RE_VALOR = re.compile(r"\$\s*([\d.,]+)")
BLOQUES = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "td", "th"}

# Etiquetas que suelen aparecer en las notificaciones (sin tildes, minúsculas).
ETIQUETAS = {
    "entidad": ["entidad estatal", "entidad compradora", "entidad", "comprador"],
    "objeto": ["objeto del proceso", "objeto", "descripcion", "nombre del proceso", "titulo"],
    "referencia": ["numero del proceso", "referencia del proceso", "referencia", "numero de proceso", "id del proceso"],
    "modalidad": ["modalidad de contratacion", "modalidad", "tipo de proceso"],
    "valor": ["precio estimado", "valor estimado", "presupuesto oficial", "precio base", "valor", "cuantia", "presupuesto"],
    "departamento": ["departamento"],
    "municipio": ["municipio", "ciudad", "lugar de ejecucion"],
    "cierre": ["fecha de cierre", "fecha de presentacion de ofertas", "fecha limite", "plazo para presentar ofertas", "cierre"],
}


class _Texto(HTMLParser):
    """Convierte HTML en texto conservando saltos de línea y la posición de los enlaces."""

    def __init__(self):
        super().__init__()
        self.partes: list[str] = []
        self.enlaces: list[tuple[str, int]] = []  # (url, posición en el texto al cerrar el enlace)
        self._href: str | None = None
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._ignorar += 1
        if tag in BLOQUES:
            self.partes.append("\n")
        if tag == "a":
            self._href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self._ignorar = max(0, self._ignorar - 1)
        if tag == "a" and self._href:
            self.enlaces.append((self._href, len(self.texto())))
            self._href = None
        if tag in BLOQUES:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)

    def texto(self) -> str:
        return "".join(self.partes)


def _sin_tildes(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _cuerpo(msg: EmailMessage) -> tuple[str, list[tuple[str, int]]]:
    """Devuelve el texto del correo y los enlaces con su posición."""
    parte = msg.get_body(preferencelist=("html", "plain"))
    if parte is None:
        return "", []
    contenido = parte.get_content()
    if parte.get_content_type() == "text/html":
        p = _Texto()
        p.feed(contenido)
        texto = p.texto()
        enlaces = p.enlaces
    else:
        texto = contenido
        enlaces = [(m.group(0), m.end()) for m in re.finditer(r"https?://\S+", texto)]
    return texto, enlaces


def _limpiar(texto: str) -> str:
    lineas = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in texto.splitlines()]
    return "\n".join(l for l in lineas if l)


def _campo(texto: str, nombre: str) -> str:
    """Busca 'Etiqueta: valor' (en la misma línea o en la siguiente)."""
    lineas = texto.splitlines()
    for etiqueta in ETIQUETAS[nombre]:
        for i, linea in enumerate(lineas):
            base = _sin_tildes(linea)
            if not base.startswith(etiqueta) or base[len(etiqueta):len(etiqueta) + 1].isalnum():
                continue
            resto = linea[len(etiqueta):].lstrip(" :.-\t")
            if resto:
                return resto.strip()
            if base.rstrip(" :") == etiqueta and i + 1 < len(lineas):
                return lineas[i + 1].strip()
    return ""


def _valor(texto: str) -> float | None:
    m = RE_VALOR.search(texto)
    if not m:
        return None
    numero = m.group(1)
    # Formato colombiano: 1.234.567,89
    numero = numero.replace(".", "").split(",")[0]
    try:
        v = float(numero)
        return v if v > 0 else None
    except ValueError:
        return None


def _segmentos(texto: str, enlaces: list[tuple[str, int]]) -> list[tuple[str, str]]:
    """Separa el correo en (texto, url) por cada proceso enlazado.

    Si el correo enlaza un solo proceso, todo el correo es ese proceso.
    Si enlaza varios, cada proceso toma el texto que hay entre su enlace y el anterior.
    """
    por_ntc: dict[str, tuple[str, int]] = {}
    for url, pos in enlaces:
        m = RE_NTC.search(url)
        if m and m.group(0) not in por_ntc:
            por_ntc[m.group(0)] = (url, pos)
    if not por_ntc:
        # Sin enlace con identificador: buscar el identificador en el texto.
        ids = list(dict.fromkeys(RE_NTC.findall(texto)))
        url = next((u for u, _ in enlaces if "secop.gov.co" in u), "")
        if len(ids) <= 1:
            return [(texto, url)]
        enlaces_txt = [(i, texto.index(i) + len(i)) for i in ids]
        por_ntc = {i: ("", p) for i, p in enlaces_txt}
    if len(por_ntc) == 1:
        url, _ = next(iter(por_ntc.values()))
        return [(texto, url)]
    segmentos, inicio = [], 0
    for url, pos in sorted(por_ntc.values(), key=lambda x: x[1]):
        segmentos.append((texto[inicio:pos], url))
        inicio = pos
    return segmentos


def procesos_de_correo(msg: EmailMessage) -> list[dict]:
    """Extrae los procesos anunciados en un correo de alerta de SECOP II."""
    texto, enlaces = _cuerpo(msg)
    asunto = str(msg.get("Subject", ""))
    try:
        fecha = email.utils.parsedate_to_datetime(msg["Date"]).date().isoformat()
    except Exception:
        fecha = date.today().isoformat()
    id_correo = str(msg.get("Message-ID") or hashlib.sha1(texto.encode()).hexdigest())

    procesos = []
    for segmento, url in _segmentos(texto, enlaces):
        seg = _limpiar(segmento)
        ntc = RE_NTC.search(url) or RE_NTC.search(seg)
        ident = ("SECOPII:" + ntc.group(0)) if ntc else ("CORREO:" + hashlib.sha1((id_correo + seg).encode()).hexdigest()[:16])
        codigos = [c for c in RE_UNSPSC.findall(seg) if c.startswith(("4", "5", "7", "8", "9"))]
        if not url and ntc:
            url = f"https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID={ntc.group(0)}"
        procesos.append({
            "fuente": "SECOP II (alerta)",
            "id": ident,
            "referencia": _campo(seg, "referencia") or (ntc.group(0) if ntc else ""),
            "entidad": _campo(seg, "entidad"),
            "departamento": _campo(seg, "departamento"),
            "municipio": _campo(seg, "municipio"),
            "objeto": _campo(seg, "objeto") or asunto,
            "descripcion": seg,
            "modalidad": _campo(seg, "modalidad"),
            "estado": "Publicado (alerta de SECOP II)",
            "cierre": _campo(seg, "cierre"),
            "abierto": True,
            "fecha_publicacion": fecha,
            "valor": _valor(_campo(seg, "valor") or ""),
            "unspsc": codigos[0] if codigos else "",
            "url": url,
        })
    return procesos


def leer_buzon(cfg: dict) -> list[tuple[str, EmailMessage]]:
    """Descarga los correos de SECOP de los últimos días sin modificar el buzón."""
    host = os.environ.get("IMAP_HOST") or "imap.gmail.com"
    usuario = os.environ.get("IMAP_USUARIO") or os.environ.get("SMTP_USUARIO")
    clave = os.environ.get("IMAP_CLAVE") or os.environ.get("SMTP_CLAVE")
    if not usuario or not clave:
        raise RuntimeError("Faltan IMAP_USUARIO / IMAP_CLAVE (o SMTP_USUARIO / SMTP_CLAVE)")
    desde = (date.today() - timedelta(days=cfg.get("dias_a_revisar", 2))).strftime("%d-%b-%Y")
    correos = []
    with imaplib.IMAP4_SSL(host, int(os.environ.get("IMAP_PUERTO") or "993"), timeout=60) as m:
        m.login(usuario, clave)
        for carpeta in cfg.get("carpetas", ["INBOX"]):
            typ, _ = m.select(f'"{carpeta}"', readonly=True)
            if typ != "OK":
                log.warning("No se pudo abrir la carpeta %s", carpeta)
                continue
            for remitente in cfg.get("remitentes", ["secop"]):
                typ, datos = m.search(None, f'(SINCE {desde} FROM "{remitente}")')
                for num in (datos[0] or b"").split():
                    typ, partes = m.fetch(num, "(BODY.PEEK[])")
                    if typ != "OK" or not partes or not isinstance(partes[0], tuple):
                        continue
                    msg = email.message_from_bytes(partes[0][1], policy=email.policy.default)
                    ident = str(msg.get("Message-ID") or f"{carpeta}:{num.decode()}")
                    correos.append((ident, msg))
    # Un correo puede coincidir con varios remitentes: quitar repetidos.
    return list({i: (i, m) for i, m in correos}.values())


def leer_archivo(ruta: str) -> list[tuple[str, EmailMessage]]:
    """Lee un correo guardado como .eml (para pruebas)."""
    with open(ruta, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)
    return [(str(msg.get("Message-ID") or ruta), msg)]
