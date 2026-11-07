# RADAR IPS – Alertas de SECOP por correo

Revisa SECOP I y SECOP II cada hora y envía un correo con los procesos
**nuevos** de servicios de salud en **Cesar y La Guajira**, ordenados por un
puntaje de afinidad (0–100) que explica por qué cada uno es relevante.

## Cómo funciona

1. Consulta los datos abiertos de SECOP en datos.gov.co
   (SECOP II: `p6dx-8zbt`, SECOP I: `f789-7hwg`).
2. Descarta modalidades sin competencia abierta (contratación directa,
   régimen especial sin ofertas, obra pública) y contratos de una sola
   persona (OPS de médicos, auxiliares, etc.).
3. Califica cada proceso:
   servicios de interés 35 · ubicación 20 · código UNSPSC 20 · sector salud 15 · proceso abierto 10,
   con restas por términos de exclusión (obras, compras, aseo…).
4. Envía un solo correo con lo que supere el puntaje mínimo (65 por defecto).
5. Recuerda lo ya enviado en `data/vistos.json` para no repetir.

> **Retraso de la fuente:** los datos abiertos de SECOP se actualizan una vez
> al día y suelen ir 1–2 días detrás del portal. Revisar cada hora no
> adelanta eso. Verifique siempre fechas y requisitos en el portal oficial.

## Ajustar qué le llega

Todo se configura en [`config.toml`](config.toml): servicios y sinónimos,
municipios, exclusiones, modalidades, pesos y puntaje mínimo.

## Ponerlo a funcionar en GitHub (gratis)

1. En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**
   y cree estos secretos:

   | Secreto | Ejemplo (Gmail) |
   |---|---|
   | `SMTP_HOST` | `smtp.gmail.com` |
   | `SMTP_PUERTO` | `587` |
   | `SMTP_USUARIO` | `alertas.ips@gmail.com` |
   | `SMTP_CLAVE` | Contraseña de aplicación de 16 letras (no la clave normal) |
   | `CORREO_DESTINO` | `gerencia@ips.com, contratacion@ips.com` |
   | `CORREO_REMITENTE` | (opcional) nombre/correo que aparece como remitente |

   Para Gmail: active la verificación en dos pasos y cree una
   *contraseña de aplicación* en https://myaccount.google.com/apppasswords

2. El flujo `.github/workflows/radar.yml` corre cada hora. GitHub solo ejecuta
   tareas programadas desde la **rama principal**, así que estos archivos deben
   estar en ella (fusionar esta rama).
3. Para probar de inmediato: pestaña **Actions → Radar SECOP → Run workflow**.

## Uso en un computador

Requiere Python 3.11 o superior; no necesita librerías adicionales.

```bash
python -m radar_ips --prueba --dias 30   # no envía; guarda salida/correo.html
python -m radar_ips                      # revisa y envía (usa las variables SMTP_*)
python -m radar_ips --inicializar        # marca todo lo actual como visto, sin enviar
python -m unittest discover -s tests     # pruebas
```
