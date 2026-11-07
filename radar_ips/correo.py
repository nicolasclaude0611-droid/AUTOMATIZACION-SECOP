"""Armado y envío del correo de alertas."""

import html
import os
import smtplib
from email.message import EmailMessage


def _pesos(valor: float | None) -> str:
    return f"${valor:,.0f}".replace(",", ".") if valor else "No informado"


def armar_html(oportunidades: list[dict], detectado: str) -> str:
    color = {"Alta": "#1b7f3b", "Media": "#b26a00", "Baja": "#666", "Muy baja": "#999"}
    bloques = []
    for o in oportunidades:
        e = lambda k: html.escape(str(o.get(k) or ""))  # noqa: E731
        razones = "".join(f"<li>{html.escape(r)}</li>" for r in o["razones"])
        enlace = (f'<a href="{e("url")}" style="color:#0b5cad">Ver proceso en {e("fuente")}</a>'
                  if o.get("url") else "Sin enlace disponible")
        bloques.append(f"""
<div style="border:1px solid #ddd;border-left:6px solid {color[o['nivel']]};border-radius:6px;padding:12px 16px;margin:0 0 16px">
  <div style="font-size:13px;color:{color[o['nivel']]};font-weight:bold">
    Afinidad {o['nivel']} &middot; {o['puntaje']}/100 &middot; {e('fuente')}
  </div>
  <div style="font-size:16px;font-weight:bold;margin:6px 0">{e('objeto')}</div>
  <table style="font-size:14px;border-collapse:collapse">
    <tr><td style="color:#666;padding-right:12px">Entidad</td><td>{e('entidad')}</td></tr>
    <tr><td style="color:#666;padding-right:12px">Lugar</td><td>{e('municipio')}, {e('departamento')}</td></tr>
    <tr><td style="color:#666;padding-right:12px">Presupuesto</td><td>{_pesos(o.get('valor'))}</td></tr>
    <tr><td style="color:#666;padding-right:12px">Modalidad</td><td>{e('modalidad')}</td></tr>
    <tr><td style="color:#666;padding-right:12px">Estado</td><td>{e('estado')}{'' if o.get('abierto') else ' <b style="color:#b00020">(puede estar cerrado: verifique en el portal)</b>'}</td></tr>
    <tr><td style="color:#666;padding-right:12px">Publicado</td><td>{e('fecha_publicacion')}</td></tr>
    <tr><td style="color:#666;padding-right:12px">Referencia</td><td>{e('referencia')}</td></tr>
  </table>
  <div style="font-size:13px;margin-top:8px">Por qué es relevante:<ul style="margin:4px 0">{razones}</ul></div>
  <div style="font-size:14px">{enlace}</div>
</div>""")
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;max-width:720px;margin:auto;color:#222">
<h2 style="margin-bottom:4px">RADAR IPS &ndash; {len(oportunidades)} oportunidad(es) nueva(s)</h2>
<p style="color:#666;font-size:13px;margin-top:0">Detectado: {html.escape(detectado)}.
Fuente: datos abiertos de SECOP (datos.gov.co), que pueden publicarse con días de retraso.
Verifique siempre fechas y requisitos en el portal oficial.</p>
{''.join(bloques)}
<p style="color:#999;font-size:12px">El puntaje es una afinidad comercial preliminar, no una garantía de que la IPS cumpla los requisitos para participar.</p>
</body></html>"""


def armar_texto(oportunidades: list[dict]) -> str:
    lineas = []
    for o in oportunidades:
        lineas += [
            f"[{o['nivel']} {o['puntaje']}/100] {o['objeto']}",
            f"  Entidad: {o['entidad']} ({o['municipio']}, {o['departamento']})",
            f"  Presupuesto: {_pesos(o.get('valor'))} | {o['modalidad']} | {o['estado']}"
            + ("" if o.get("abierto") else " (puede estar cerrado)"),
            f"  Publicado: {o['fecha_publicacion']} | {o['fuente']} {o['referencia']}",
            f"  {o.get('url') or 'Sin enlace'}",
            "",
        ]
    return "\n".join(lineas)


def enviar(asunto: str, cuerpo_html: str, cuerpo_texto: str) -> None:
    """Envía por SMTP usando variables de entorno (ver README)."""
    faltan = [v for v in ("SMTP_HOST", "SMTP_USUARIO", "SMTP_CLAVE", "CORREO_DESTINO") if not os.environ.get(v)]
    if faltan:
        raise RuntimeError("Faltan variables de entorno para el correo: " + ", ".join(faltan))
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = os.environ.get("CORREO_REMITENTE") or os.environ["SMTP_USUARIO"]
    msg["To"] = os.environ["CORREO_DESTINO"]
    msg.set_content(cuerpo_texto)
    msg.add_alternative(cuerpo_html, subtype="html")
    puerto = int(os.environ.get("SMTP_PUERTO", "587"))
    if puerto == 465:
        servidor = smtplib.SMTP_SSL(os.environ["SMTP_HOST"], puerto, timeout=60)
    else:
        servidor = smtplib.SMTP(os.environ["SMTP_HOST"], puerto, timeout=60)
        servidor.starttls()
    with servidor:
        servidor.login(os.environ["SMTP_USUARIO"], os.environ["SMTP_CLAVE"])
        servidor.send_message(msg)
