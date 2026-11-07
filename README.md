# RADAR IPS – Alertas de SECOP por correo

Avisa por correo de los procesos de contratación **nuevos** de servicios de
salud en **Cesar y La Guajira**, ordenados por un puntaje de afinidad (0–100)
que explica por qué cada uno es relevante.

Trabaja con dos fuentes:

| Fuente | Rapidez | Qué cubre | Frecuencia |
|---|---|---|---|
| **Alertas oficiales de SECOP II** que llegan al correo de la IPS | Minutos después de la publicación | SECOP II, según los códigos UNSPSC suscritos | Cada 5 min (`buzon.yml`) |
| **Datos abiertos** (datos.gov.co) | 1–2 días de retraso | SECOP I y SECOP II, como respaldo | Cada hora (`radar.yml`) |

Un proceso que ya se notificó por una fuente no se repite por la otra.

## Cómo filtra

1. Descarta modalidades sin competencia abierta (contratación directa,
   régimen especial sin ofertas, obra pública) y contratos con una sola
   persona (OPS de médicos, auxiliares, etc.).
2. Exige que el proceso mencione un servicio de interés **y** un lugar de
   cobertura. Las alertas de SECOP II llegan de todo el país; aquí se dejan
   solo las de Cesar y La Guajira.
3. Califica: servicios 35 · ubicación 20 · código UNSPSC 20 · sector salud 15 · proceso abierto 10,
   con restas por términos de exclusión (obras, compras, aseo…).
4. Envía lo que supere el puntaje mínimo (65 por defecto).

Todo se ajusta en [`config.toml`](config.toml) sin tocar el código.

## Puesta en marcha

### 1. Activar las alertas en SECOP II

En la cuenta de proveedor de la IPS en SECOP II, configure las
notificaciones de oportunidades de negocio con los códigos UNSPSC de los
servicios que presta (segmento **85 – Servicios de salud**; por ejemplo las
familias 8510 *Servicios integrales de salud*, 8511 *Prevención y control de
enfermedades* y 8512 *Práctica médica*, más las clases específicas que
correspondan). Confirme los códigos en el clasificador de SECOP.

### 2. Preparar el buzón que leerá el radar

Recomendado: una cuenta de Gmail exclusiva para el radar (ej. `radar.ips@gmail.com`).

- Si las alertas de SECOP llegan a otro correo, cree en ese correo una regla
  de **reenvío automático** de los mensajes de SECOP hacia la cuenta del radar.
- En la cuenta del radar active la verificación en dos pasos y cree una
  **contraseña de aplicación** en https://myaccount.google.com/apppasswords.
  Se usa tanto para leer (IMAP) como para enviar (SMTP).
- El radar solo **lee** el buzón: no borra, no mueve y no marca correos como leídos.

> Outlook/Office 365 ya no permite este tipo de acceso con contraseña; por eso
> se recomienda reenviar a Gmail.

### 3. Crear los secretos en GitHub

En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**.

| Secreto | Ejemplo | Obligatorio |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | Sí |
| `SMTP_USUARIO` | `radar.ips@gmail.com` | Sí |
| `SMTP_CLAVE` | contraseña de aplicación de 16 letras | Sí |
| `CORREO_DESTINO` | `gerencia@ips.com, contratacion@ips.com` | Sí |
| `SMTP_PUERTO` | `587` | No (587 por defecto) |
| `IMAP_HOST` | `imap.gmail.com` | No (Gmail por defecto) |
| `IMAP_USUARIO` / `IMAP_CLAVE` | solo si el buzón a leer es distinto del que envía | No |
| `CORREO_REMITENTE` | nombre o correo que aparece como remitente | No |

### 4. Activar la ejecución automática

GitHub solo ejecuta tareas programadas desde la **rama principal**: fusione
esta rama. Para probar de inmediato: **Actions → Alertas SECOP II (buzón) → Run workflow**.

### Sobre la rapidez

GitHub permite ejecutar como mínimo cada 5 minutos, y en horas de mucha
carga puede retrasarse más. Para revisar **cada minuto**, ejecute el radar
en un computador o servidor que esté siempre encendido:

```bash
python -m radar_ips --buzon --continuo 60
```

## Comandos

Requiere Python 3.11 o superior; no necesita librerías adicionales.

```bash
python -m radar_ips --buzon --archivo alerta.eml --prueba   # probar con un correo de SECOP guardado
python -m radar_ips --buzon                 # leer el buzón y reenviar lo relevante
python -m radar_ips                         # datos abiertos de SECOP I y II
python -m radar_ips --prueba --dias 30      # no envía; guarda salida/correo.html
python -m radar_ips --detalle ...           # muestra por qué se descarta cada proceso
python -m radar_ips --inicializar           # marca lo actual como visto, sin enviar
python -m unittest discover -s tests        # pruebas
```
