"""RADAR IPS: revisa SECOP y envía por correo las oportunidades nuevas.

Uso:
    python -m radar_ips                     # datos abiertos de SECOP I y II
    python -m radar_ips --buzon             # alertas de SECOP II que llegan al buzón
    python -m radar_ips --buzon --continuo 60   # revisa el buzón cada 60 segundos
    python -m radar_ips --buzon --archivo alerta.eml --prueba   # probar con un correo guardado
    python -m radar_ips --prueba            # no envía; guarda el correo en salida/
    python -m radar_ips --inicializar       # marca lo actual como visto sin enviar
"""

import argparse
import json
import logging
import sys
import time
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import buzon, correo, fuentes
from .puntaje import Calificador, nivel

RAIZ = Path(__file__).resolve().parent.parent
log = logging.getLogger("radar_ips")
COLOMBIA = timezone(timedelta(hours=-5))
DIAS_RECORDAR = 120  # tiempo que se recuerda un proceso ya visto
VISTOS_DATOS = RAIZ / "data" / "vistos.json"
VISTOS_BUZON = RAIZ / "data" / "vistos_buzon.json"


def cargar_vistos(ruta: Path) -> dict[str, str]:
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return {}


def guardar_vistos(ruta: Path, vistos: dict[str, str]) -> None:
    limite = (date.today() - timedelta(days=DIAS_RECORDAR)).isoformat()
    vistos = {k: v for k, v in vistos.items() if v >= limite}
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(vistos, indent=0, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def procesos_datos_abiertos(config: dict, dias: int) -> tuple[list[dict], bool]:
    """Consulta SECOP I y II. Devuelve (procesos, todas_fallaron)."""
    desde = date.today() - timedelta(days=dias)
    departamentos = config["cobertura"]["departamentos"]
    procesos, errores = [], 0
    for nombre, fn in (("SECOP II", fuentes.secop_ii), ("SECOP I", fuentes.secop_i)):
        try:  # una fuente que falla no detiene a la otra
            lote = fn(desde, departamentos)
            log.info("%s: %d procesos desde %s", nombre, len(lote), desde)
            procesos += lote
        except Exception as e:
            log.error("%s no respondió: %s", nombre, e)
            errores += 1
    return procesos, errores == 2


def procesos_buzon(config: dict, vistos: dict[str, str], archivo: str | None) -> list[dict]:
    """Lee las alertas de SECOP II del buzón (o de un archivo .eml)."""
    correos = buzon.leer_archivo(archivo) if archivo else buzon.leer_buzon(config.get("buzon", {}))
    hoy = date.today().isoformat()
    procesos = []
    for ident, msg in correos:
        clave = "CORREO:" + ident
        if clave in vistos and not archivo:
            continue
        lote = buzon.procesos_de_correo(msg)
        log.info("Correo '%s': %d proceso(s)", msg.get("Subject", ""), len(lote))
        procesos += lote
        vistos[clave] = hoy
    log.info("Buzón: %d correo(s) revisado(s), %d proceso(s) encontrados", len(correos), len(procesos))
    return procesos


def seleccionar(procesos: list[dict], calificador: Calificador, ya_vistos, vistos: dict[str, str]) -> list[dict]:
    """Filtra y califica los procesos que no se han visto antes."""
    hoy = date.today().isoformat()
    oportunidades = []
    for p in procesos:
        if p["id"] in ya_vistos:
            continue
        vistos[p["id"]] = hoy
        enviar, puntaje, razones = calificador.notificable(p)
        if enviar:
            oportunidades.append({**p, "puntaje": puntaje, "nivel": nivel(puntaje), "razones": razones})
        else:
            log.debug("Descartado (%s): %s | %s", puntaje, p["objeto"][:80], razones)
    # Un mismo proceso de SECOP II puede aparecer una vez por cada fase:
    # en el correo se deja solo la versión más reciente.
    unicos: dict[tuple, dict] = {}
    for o in sorted(oportunidades, key=lambda o: o["fecha_publicacion"]):
        unicos[(o["entidad"], o["objeto"].strip().upper())] = o
    return sorted(unicos.values(), key=lambda o: (-o["puntaje"], o["fecha_publicacion"]))


def notificar(oportunidades: list[dict], asunto: str, nota: str, prueba: bool) -> None:
    detectado = datetime.now(COLOMBIA).strftime("%Y-%m-%d %H:%M (hora Colombia)")
    cuerpo_html = correo.armar_html(oportunidades, detectado, nota)
    cuerpo_texto = correo.armar_texto(oportunidades)
    asunto = f"{asunto} ({len(oportunidades)})"
    if prueba:
        salida = RAIZ / "salida"
        salida.mkdir(exist_ok=True)
        (salida / "correo.html").write_text(cuerpo_html, encoding="utf-8")
        print(cuerpo_texto)
        log.info("Modo prueba: correo guardado en %s", salida / "correo.html")
    else:
        correo.enviar(asunto, cuerpo_html, cuerpo_texto)
        log.info("Correo enviado (%d oportunidades)", len(oportunidades))


def ejecutar(args, config: dict) -> int:
    calificador = Calificador(config)
    propio = VISTOS_BUZON if args.buzon else VISTOS_DATOS
    otro = VISTOS_DATOS if args.buzon else VISTOS_BUZON
    vistos = cargar_vistos(propio)
    # Lo que ya notificó el otro modo tampoco se repite.
    ya_vistos = set(vistos) | set(cargar_vistos(otro))

    if args.buzon:
        procesos = procesos_buzon(config, vistos, args.archivo)
        fallo_total = False
        asunto = config.get("buzon", {}).get("asunto", config["general"]["asunto"])
        nota = correo.NOTA_ALERTA
    else:
        procesos, fallo_total = procesos_datos_abiertos(config, args.dias or config["general"]["dias_a_revisar"])
        asunto, nota = config["general"]["asunto"], correo.NOTA_DATOS_ABIERTOS

    if args.archivo:  # al probar con un archivo se ignora lo ya visto
        ya_vistos = set()
    oportunidades = seleccionar(procesos, calificador, ya_vistos, vistos)
    log.info("Oportunidades a notificar: %d", len(oportunidades))

    if oportunidades and not args.inicializar:
        notificar(oportunidades, asunto, nota, args.prueba)
    if not args.prueba:
        guardar_vistos(propio, vistos)
    return 1 if fallo_total else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(RAIZ / "config.toml"))
    ap.add_argument("--buzon", action="store_true", help="Leer alertas de SECOP II del buzón de correo")
    ap.add_argument("--archivo", help="Con --buzon: leer un correo guardado (.eml) en vez del buzón")
    ap.add_argument("--continuo", type=int, metavar="SEG", help="Repetir cada SEG segundos sin detenerse")
    ap.add_argument("--prueba", action="store_true", help="No envía correo; lo guarda en salida/")
    ap.add_argument("--inicializar", action="store_true", help="Marca todo como visto sin enviar")
    ap.add_argument("--dias", type=int, help="Días hacia atrás a revisar en datos abiertos")
    ap.add_argument("--detalle", action="store_true", help="Mostrar por qué se descarta cada proceso")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.detalle else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    config = tomllib.loads(Path(args.config).read_text(encoding="utf-8"))

    if not args.continuo:
        return ejecutar(args, config)
    log.info("Modo continuo: revisando cada %d segundos (Ctrl+C para detener)", args.continuo)
    while True:
        try:
            ejecutar(args, config)
        except Exception as e:  # un fallo puntual no detiene el radar
            log.error("Error en la revisión: %s", e)
        time.sleep(args.continuo)


if __name__ == "__main__":
    sys.exit(main())
