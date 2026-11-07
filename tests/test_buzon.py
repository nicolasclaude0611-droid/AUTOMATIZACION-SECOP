import email
import email.policy
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from radar_ips import buzon
from radar_ips.puntaje import Calificador

AQUI = Path(__file__).resolve().parent
CONFIG = tomllib.loads((AQUI.parent / "config.toml").read_text(encoding="utf-8"))


def leer(nombre):
    return buzon.leer_archivo(str(AQUI / "correos" / nombre))[0][1]


class LecturaCorreoTest(unittest.TestCase):
    def test_un_proceso_con_campos(self):
        [p] = buzon.procesos_de_correo(leer("alerta_un_proceso.eml"))
        self.assertEqual(p["id"], "SECOPII:CO1.NTC.9990001")
        self.assertEqual(p["referencia"], "IP-045-2026")
        self.assertIn("ROSARIO PUMAREJO", p["entidad"])
        self.assertIn("LABORATORIO CLÍNICO", p["objeto"])
        self.assertEqual(p["valor"], 250000000)
        self.assertEqual(p["unspsc"], "85121800")
        self.assertEqual(p["cierre"], "12/11/2026 5:00 PM")
        self.assertEqual(p["fecha_publicacion"], "2026-11-07")

    def test_varios_procesos_se_separan(self):
        procesos = buzon.procesos_de_correo(leer("alerta_varios.eml"))
        self.assertEqual([p["id"][-7:] for p in procesos], ["9990002", "9990003", "9990004"])
        self.assertIn("MEDELLÍN", procesos[0]["entidad"])
        self.assertIn("RIOHACHA", procesos[1]["entidad"])
        self.assertEqual(procesos[1]["valor"], 480500000)

    def test_filtro_deja_solo_la_region(self):
        c = Calificador(CONFIG)
        procesos = buzon.procesos_de_correo(leer("alerta_varios.eml"))
        enviados = [p["id"][-7:] for p in procesos if c.notificable(p)[0]]
        self.assertEqual(enviados, ["9990003"])

    def test_etiqueta_no_confunde_palabras_parecidas(self):
        self.assertEqual(buzon._campo("Valoración técnica\nValor: $ 10", "valor"), "$ 10")

    def test_texto_plano_sin_html(self):
        msg = email.message_from_string(
            "From: secop@secop.gov.co\nSubject: Alerta\nContent-Type: text/plain; charset=utf-8\n\n"
            "Entidad: ESE HOSPITAL DE AGUACHICA\nObjeto: Servicios de fisioterapia\n"
            "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CO1.NTC.1\n",
            policy=email.policy.default)
        [p] = buzon.procesos_de_correo(msg)
        self.assertEqual(p["id"], "SECOPII:CO1.NTC.1")
        self.assertEqual(p["objeto"], "Servicios de fisioterapia")


class LecturaImapTest(unittest.TestCase):
    def test_lee_sin_marcar_como_leido(self):
        crudo = (AQUI / "correos" / "alerta_un_proceso.eml").read_bytes()
        imap = mock.MagicMock()
        imap.__enter__.return_value = imap
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = ("OK", [b"1"])
        imap.fetch.return_value = ("OK", [(b"1 (BODY[] {100}", crudo), b")"])
        env = {"IMAP_USUARIO": "u", "IMAP_CLAVE": "c"}
        with mock.patch.dict("os.environ", env), mock.patch("imaplib.IMAP4_SSL", return_value=imap):
            correos = buzon.leer_buzon({"remitentes": ["secop"], "carpetas": ["INBOX"]})
        self.assertEqual(len(correos), 1)
        imap.select.assert_called_with('"INBOX"', readonly=True)
        self.assertIn("BODY.PEEK[]", imap.fetch.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
