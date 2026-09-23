"""
Lee la hoja "Parametros" del Google Sheet (funciona como un mini-formulario:
el usuario cambia valores ahi, sin tocar codigo) y decide, para la fecha de
hoy, que canales estan activos y deben procesarse en esta corrida.

Diseno clave-valor (no columnas fijas) para poder agregar nuevos parametros
en el futuro sin rediseñar la hoja.

Parametros soportados (se crean con estos valores por defecto la primera
vez que corre el script, si la hoja no existe todavia):

  activo_email        TRUE / FALSE
  frecuencia_email    diaria / semanal / quincenal / mensual
  dias_email          para 'semanal': dias de la semana separados por coma
                       (lunes,martes,...). Para 'quincenal'/'mensual': dias
                       del mes separados por coma (ej: 1,15)

  activo_whatsapp     ...mismo patron...
  frecuencia_whatsapp
  dias_whatsapp

  activo_sms
  frecuencia_sms
  dias_sms

  umbral_leve_max     dias de mora hasta los que un deudor es "leve"
  umbral_media_max    dias de mora hasta los que un deudor es "media"
                       (mas alla de esto, es "critica")
"""
from datetime import date

DIAS_SEMANA_ES = {
    0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
    4: "viernes", 5: "sabado", 6: "domingo",
}

VALORES_POR_DEFECTO = [
    ("activo_email", "TRUE", "Activa o desactiva el canal Email por completo"),
    ("frecuencia_email", "semanal", "diaria / semanal / quincenal / mensual"),
    ("dias_email", "lunes", "Dias de envio: nombres de dia (semanal) o numero de dia del mes (quincenal/mensual)"),

    ("activo_whatsapp", "TRUE", "Activa o desactiva el canal WhatsApp por completo"),
    ("frecuencia_whatsapp", "semanal", "diaria / semanal / quincenal / mensual"),
    ("dias_whatsapp", "lunes", "Dias de envio: nombres de dia (semanal) o numero de dia del mes (quincenal/mensual)"),

    ("activo_sms", "TRUE", "Activa o desactiva el canal SMS por completo"),
    ("frecuencia_sms", "mensual", "diaria / semanal / quincenal / mensual"),
    ("dias_sms", "1", "Dias de envio: nombres de dia (semanal) o numero de dia del mes (quincenal/mensual)"),

    ("umbral_leve_max", "30", "Dias de mora maximos para considerar un deudor 'leve'"),
    ("umbral_media_max", "60", "Dias de mora maximos para considerar un deudor 'media' (mas alla es 'critica')"),

    ("feriados", "", "Fechas AAAA-MM-DD separadas por coma en las que NO se procesa ningun envio (Art. 49 Ley Organica de Defensa del Consumidor: prohibido gestionar cobros en feriados). Actualizar cada año con el calendario oficial de feriados de Ecuador."),
]


def parsear_parametros(filas: list[dict]) -> dict:
    """filas viene de sheets_client.leer_parametros() -> [{'parametro':.., 'valor':..}, ...]"""
    return {f["parametro"].strip(): str(f["valor"]).strip() for f in filas if f.get("parametro")}


def canal_corresponde_hoy(parametros: dict, canal: str, hoy: date = None) -> bool:
    """
    Devuelve True si, segun la configuracion del usuario, el canal dado
    debe procesarse en la fecha de hoy.
    """
    hoy = hoy or date.today()

    activo = parametros.get(f"activo_{canal}", "TRUE").strip().upper() == "TRUE"
    if not activo:
        return False

    frecuencia = parametros.get(f"frecuencia_{canal}", "semanal").strip().lower()
    dias_raw = parametros.get(f"dias_{canal}", "").strip().lower()
    dias = [d.strip() for d in dias_raw.split(",") if d.strip()]

    if frecuencia == "diaria":
        return True

    if frecuencia == "semanal":
        dia_hoy_es = DIAS_SEMANA_ES[hoy.weekday()]
        return dia_hoy_es in dias

    if frecuencia in ("quincenal", "mensual"):
        try:
            dias_num = [int(d) for d in dias]
        except ValueError:
            return False
        return hoy.day in dias_num

    return False


def umbrales_desde_parametros(parametros: dict, umbral_leve_default: int,
                               umbral_media_default: int) -> tuple[int, int]:
    try:
        leve = int(parametros.get("umbral_leve_max", umbral_leve_default))
    except ValueError:
        leve = umbral_leve_default
    try:
        media = int(parametros.get("umbral_media_max", umbral_media_default))
    except ValueError:
        media = umbral_media_default
    return leve, media
