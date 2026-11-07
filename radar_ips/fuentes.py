"""Consulta de SECOP I y SECOP II en datos abiertos (datos.gov.co).

Cada fuente devuelve procesos en un formato común (diccionario Proceso).
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import date

log = logging.getLogger(__name__)

BASE = "https://www.datos.gov.co/resource"
SECOP_II = "p6dx-8zbt"  # SECOP II - Procesos de Contratación
SECOP_I = "f789-7hwg"   # SECOP I - Procesos de Compra Pública
PAGINA = 1000


def _consultar(dataset: str, where: str, orden: str) -> list[dict]:
    """Descarga todas las filas que cumplen el filtro, página por página."""
    filas: list[dict] = []
    offset = 0
    while True:
        params = {"$where": where, "$order": orden, "$limit": PAGINA, "$offset": offset}
        url = f"{BASE}/{dataset}.json?" + urllib.parse.urlencode(params)
        lote = _get_json(url)
        filas.extend(lote)
        if len(lote) < PAGINA:
            return filas
        offset += PAGINA


def _get_json(url: str, intentos: int = 4) -> list[dict]:
    for intento in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "radar-ips/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # red, tiempo de espera o error del servidor
            if intento == intentos - 1:
                raise
            espera = 2 ** (intento + 1)
            log.warning("Fallo consultando datos.gov.co (%s). Reintento en %ss", e, espera)
            time.sleep(espera)
    return []


def _lista_sql(valores: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in valores)


def _url(campo) -> str:
    if isinstance(campo, dict):
        return campo.get("url", "")
    return campo or ""


def _numero(valor) -> float | None:
    try:
        n = float(valor)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def secop_ii(desde: date, departamentos: list[str]) -> list[dict]:
    where = (
        f"fecha_de_publicacion_del >= '{desde.isoformat()}' "
        f"AND departamento_entidad in ({_lista_sql(departamentos)})"
    )
    filas = _consultar(SECOP_II, where, "fecha_de_publicacion_del DESC")
    procesos = []
    for f in filas:
        codigo = (f.get("codigo_principal_de_categoria") or "").replace("V1.", "")
        procesos.append({
            "fuente": "SECOP II",
            "id": "SECOPII:" + (f.get("id_del_proceso") or f.get("referencia_del_proceso", "")),
            "referencia": f.get("referencia_del_proceso", ""),
            "entidad": f.get("entidad", ""),
            "departamento": f.get("departamento_entidad", ""),
            "municipio": f.get("ciudad_entidad", ""),
            "objeto": f.get("nombre_del_procedimiento", ""),
            "descripcion": f.get("descripci_n_del_procedimiento", ""),
            "modalidad": f.get("modalidad_de_contratacion", ""),
            "estado": f.get("fase") or f.get("estado_del_procedimiento", ""),
            "abierto": (f.get("estado_de_apertura_del_proceso") == "Abierto"
                        and f.get("adjudicado") != "Si"),
            "fecha_publicacion": (f.get("fecha_de_publicacion_del") or "")[:10],
            "valor": _numero(f.get("precio_base")),
            "unspsc": "" if codigo == "UNSPECIFIED" else codigo,
            "url": _url(f.get("urlproceso")),
        })
    return procesos


def secop_i(desde: date, departamentos: list[str]) -> list[dict]:
    where = (
        f"fecha_de_cargue_en_el_secop >= '{desde.isoformat()}' "
        f"AND departamento_entidad in ({_lista_sql(departamentos)})"
    )
    filas = _consultar(SECOP_I, where, "fecha_de_cargue_en_el_secop DESC")
    procesos = []
    for f in filas:
        municipio = f.get("municipios_ejecucion") or f.get("municipio_entidad", "")
        procesos.append({
            "fuente": "SECOP I",
            "id": "SECOPI:" + (f.get("numero_de_constancia") or f.get("uid", "")),
            "referencia": f.get("numero_de_proceso", ""),
            "entidad": f.get("nombre_entidad", ""),
            "departamento": f.get("departamento_entidad", ""),
            "municipio": municipio,
            "objeto": f.get("detalle_del_objeto_a_contratar", ""),
            "descripcion": f"{f.get('objeto_a_contratar', '')} - {f.get('nombre_clase', '')}",
            "modalidad": f.get("modalidad_de_contratacion", ""),
            "estado": f.get("estado_del_proceso", ""),
            "abierto": f.get("estado_del_proceso") == "Convocado",
            "fecha_publicacion": (f.get("fecha_de_cargue_en_el_secop") or "")[:10],
            "valor": _numero(f.get("cuantia_proceso")),
            "unspsc": f.get("id_clase", ""),
            "url": _url(f.get("ruta_proceso_en_secop_i")),
        })
    return procesos
