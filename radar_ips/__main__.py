"""RADAR IPS: revisa SECOP y envía por correo las oportunidades nuevas.

Uso:
    python -m radar_ips                 # revisa y envía correo
    python -m radar_ips --prueba        # no envía; guarda el correo en salida/
    python -m radar_ips --inicializar   # marca lo actual como visto sin enviar
"""

import argparse
import json
import logging
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import correo, fuentes
from .puntaje import Calificador, nivel

RAIZ = Path(__file__).resolve().parent.parent
log = logging.getLogger("radar_ips")
COLOMBIA = timezone(timedelta(hours=-5))
DIAS_RECORDAR = 120  # tiempo que se recuerda un proceso ya visto


def cargar_vistos(ruta: Path) -> dict[str, str]:
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))
    return {}


def guardar_vistos(ruta: Path, vistos: dict[str, str]) -> None:
    limite = (date.today() - timedelta(days=DIAS_RECORDAR)).isoformat()
    vistos = {k: v for k, v in vistos.items() if v >= limite}
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(vistos, indent=0, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(RAIZ / "config.toml"))
    ap.add_argument("--vistos", default=str(RAIZ / "data" / "vistos.json"))
    ap.add_argument("--prueba", action="store_true", help="No envía correo; lo guarda en salida/")
    ap.add_argument("--inicializar", action="store_true", help="Marca todo como visto sin enviar")
    ap.add_argument("--dias", type=int, help="Días hacia atrás a revisar (sobrescribe config)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    config = tomllib.loads(Path(args.config).read_text(encoding="utf-8"))
    gen = config["general"]
    desde = date.today() - timedelta(days=args.dias or gen["dias_a_revisar"])
    departamentos = config["cobertura"]["departamentos"]
    calificador = Calificador(config)
    ruta_vistos = Path(args.vistos)
    vistos = cargar_vistos(ruta_vistos)
    hoy = date.today().isoformat()

    # Una fuente que falla no detiene a la otra.
    procesos, errores = [], []
    for nombre, fn in (("SECOP II", fuentes.secop_ii), ("SECOP I", fuentes.secop_i)):
        try:
            lote = fn(desde, departamentos)
            log.info("%s: %d procesos desde %s", nombre, len(lote), desde)
            procesos += lote
        except Exception as e:
            log.error("%s no respondió: %s", nombre, e)
            errores.append(nombre)

    nuevos = [p for p in procesos if p["id"] not in vistos]
    oportunidades = []
    for p in nuevos:
        vistos[p["id"]] = hoy
        enviar, puntaje, razones = calificador.notificable(p)
        if enviar:
            oportunidades.append({**p, "puntaje": puntaje, "nivel": nivel(puntaje), "razones": razones})
    # Un mismo proceso de SECOP II puede aparecer una vez por cada fase:
    # en el correo se deja solo la versión más reciente.
    unicos: dict[tuple, dict] = {}
    for o in sorted(oportunidades, key=lambda o: o["fecha_publicacion"]):
        unicos[(o["entidad"], o["objeto"].strip().upper())] = o
    oportunidades = sorted(unicos.values(), key=lambda o: (-o["puntaje"], o["fecha_publicacion"]))
    log.info("Nuevos: %d | Oportunidades a notificar: %d", len(nuevos), len(oportunidades))

    if oportunidades and not args.inicializar:
        detectado = datetime.now(COLOMBIA).strftime("%Y-%m-%d %H:%M (hora Colombia)")
        cuerpo_html = correo.armar_html(oportunidades, detectado)
        cuerpo_texto = correo.armar_texto(oportunidades)
        asunto = f"{gen['asunto']} ({len(oportunidades)})"
        if args.prueba:
            salida = RAIZ / "salida"
            salida.mkdir(exist_ok=True)
            (salida / "correo.html").write_text(cuerpo_html, encoding="utf-8")
            print(cuerpo_texto)
            log.info("Modo prueba: correo guardado en %s", salida / "correo.html")
        else:
            correo.enviar(asunto, cuerpo_html, cuerpo_texto)
            log.info("Correo enviado a %s", "destinatarios configurados")

    if not args.prueba:
        guardar_vistos(ruta_vistos, vistos)
    return 1 if len(errores) == 2 else 0


if __name__ == "__main__":
    sys.exit(main())
