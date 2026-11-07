"""Puntaje de afinidad explicable (0-100)."""

from .texto import Buscador, normalizar


def nivel(puntaje: int) -> str:
    if puntaje >= 85:
        return "Alta"
    if puntaje >= 65:
        return "Media"
    if puntaje >= 40:
        return "Baja"
    return "Muy baja"


class Calificador:
    def __init__(self, config: dict):
        self.pesos = config["puntaje"]
        self.servicios = {
            s["nombre"]: Buscador(s["palabras"])
            for s in config["servicios"].values() if s.get("activo", True)
        }
        self.sector = Buscador(config["sector_salud"]["palabras"])
        self.exclusiones = Buscador(config["exclusiones"]["palabras"])
        self.individuales = Buscador(config.get("contratos_individuales", {}).get("palabras", []))
        self.requerir_servicio = config["general"].get("requerir_servicio", True)
        self.minimo = config["general"]["puntaje_minimo"]
        cob = config["cobertura"]
        self.departamentos = {normalizar(d).strip() for d in cob["departamentos"]}
        self.lugares = Buscador(cob["departamentos"] + cob["municipios"])
        self.requerir_ubicacion = config["general"].get("requerir_ubicacion", True)
        self.prefijos = config["unspsc"]["prefijos"]
        self.modalidades_excluidas = {normalizar(m).strip() for m in config["modalidades"]["excluir"]}

    def modalidad_excluida(self, proceso: dict) -> bool:
        return normalizar(proceso["modalidad"]).strip() in self.modalidades_excluidas

    def notificable(self, proceso: dict) -> tuple[bool, int, list[str]]:
        """Indica si el proceso debe enviarse por correo, con su puntaje y razones."""
        if self.modalidad_excluida(proceso):
            return False, 0, ["Modalidad excluida: " + proceso["modalidad"]]
        puntaje, razones = self.calificar(proceso)
        tiene_servicio = any(r.startswith(f"+{self.pesos['servicios']} Servicios") for r in razones)
        if self.requerir_servicio and not tiene_servicio:
            return False, puntaje, razones
        tiene_ubicacion = any(r.startswith(f"+{self.pesos['ubicacion']} ") for r in razones)
        if self.requerir_ubicacion and not tiene_ubicacion:
            return False, puntaje, razones
        return puntaje >= self.minimo, puntaje, razones

    def calificar(self, proceso: dict) -> tuple[int, list[str]]:
        """Devuelve (puntaje, razones). Las razones explican cada suma o resta."""
        p = self.pesos
        texto = normalizar(f"{proceso['objeto']} {proceso['descripcion']}")
        texto_entidad = normalizar(proceso["entidad"])
        puntaje = 0
        razones: list[str] = []

        servicios = [n for n, b in self.servicios.items() if b.encontrados(texto)]
        if servicios:
            puntaje += p["servicios"]
            razones.append(f"+{p['servicios']} Servicios: {', '.join(servicios)}")

        if normalizar(proceso["departamento"]).strip() in self.departamentos:
            puntaje += p["ubicacion"]
            razones.append(f"+{p['ubicacion']} Ubicación: {proceso['municipio']}, {proceso['departamento']}")
        elif lugares := self.lugares.encontrados(texto + normalizar(proceso["municipio"])):
            puntaje += p["ubicacion"]
            razones.append(f"+{p['ubicacion']} Ejecución mencionada en: {', '.join(lugares[:3])}")

        if proceso["unspsc"] and any(proceso["unspsc"].startswith(x) for x in self.prefijos):
            puntaje += p["unspsc"]
            razones.append(f"+{p['unspsc']} Código UNSPSC de salud ({proceso['unspsc']})")

        sector = self.sector.encontrados(texto) or self.sector.encontrados(texto_entidad)
        if sector:
            puntaje += p["sector_salud"]
            razones.append(f"+{p['sector_salud']} Sector salud ({', '.join(t.rstrip('*') for t in sector[:3])})")

        if proceso["abierto"]:
            puntaje += p["estado"]
            razones.append(f"+{p['estado']} Proceso abierto ({proceso['estado']})")

        excl = self.exclusiones.encontrados(texto)
        if excl:
            resta = p["penalizacion_mixto"] if servicios else p["penalizacion_exclusion"]
            puntaje -= resta
            tipo = "posible proceso mixto" if servicios else "probablemente fuera de interés"
            razones.append(f"-{resta} Exclusión, {tipo}: {', '.join(excl[:3])}")

        indiv = self.individuales.encontrados(texto)
        if indiv:
            puntaje -= p["penalizacion_exclusion"]
            razones.append(f"-{p['penalizacion_exclusion']} Parece contrato con una sola persona: "
                           f"{', '.join(t.rstrip('*') for t in indiv[:2])}")

        return max(0, min(100, puntaje)), razones
