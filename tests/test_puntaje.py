import tomllib
import unittest
from pathlib import Path

from radar_ips.puntaje import Calificador
from radar_ips.texto import Buscador, normalizar

CONFIG = tomllib.loads((Path(__file__).resolve().parent.parent / "config.toml").read_text(encoding="utf-8"))


def proceso(objeto, **extra):
    base = {
        "fuente": "SECOP II", "id": "x", "referencia": "R-1", "entidad": "ALCALDIA DE VALLEDUPAR",
        "departamento": "Cesar", "municipio": "Valledupar", "objeto": objeto, "descripcion": "",
        "modalidad": "Mínima cuantía", "estado": "Presentación de oferta", "abierto": True,
        "fecha_publicacion": "2026-11-05", "valor": 1000000.0, "unspsc": "", "url": "",
    }
    return {**base, **extra}


class TextoTest(unittest.TestCase):
    def test_normaliza_tildes_y_puntuacion(self):
        self.assertEqual(normalizar("E.S.E. Clínica"), " e s e clinica ")

    def test_palabra_completa_y_comodin(self):
        b = Buscador(["obra", "medic*"])
        self.assertEqual(b.encontrados(normalizar("maniobras")), [])
        self.assertEqual(b.encontrados(normalizar("Médicos generales")), ["medic*"])


class PuntajeTest(unittest.TestCase):
    def setUp(self):
        self.c = Calificador(CONFIG)

    def test_oportunidad_de_salud_se_notifica(self):
        enviar, puntaje, razones = self.c.notificable(
            proceso("Prestación de servicios de exámenes médicos ocupacionales", unspsc="85121501"))
        self.assertTrue(enviar)
        self.assertEqual(puntaje, 100)
        self.assertTrue(any("Salud ocupacional" in r for r in razones))

    def test_contrato_de_una_persona_no_se_notifica(self):
        enviar, _, _ = self.c.notificable(
            proceso("Prestar los servicios profesionales como médico en consulta externa"))
        self.assertFalse(enviar)

    def test_modalidad_directa_excluida(self):
        enviar, _, _ = self.c.notificable(
            proceso("Jornadas de salud extramural", modalidad="Contratación directa"))
        self.assertFalse(enviar)

    def test_sin_servicio_no_se_notifica(self):
        enviar, _, _ = self.c.notificable(proceso("Fortalecimiento de la biblioteca pública"))
        self.assertFalse(enviar)

    def test_obra_con_palabra_rehabilitacion_no_pasa(self):
        enviar, _, _ = self.c.notificable(
            proceso("Rehabilitación del sistema de acueducto", modalidad="Selección Abreviada de Menor Cuantía"))
        self.assertFalse(enviar)


if __name__ == "__main__":
    unittest.main()
