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

  canales_leve / canales_media / canales_critica
                       (OPCIONAL) lista ordenada de canales para cada segmento,
                       separados por coma. Ej: whatsapp,sms,email
  modo_envio          (OPCIONAL) 'uno' = usa SOLO el primer canal de la lista que
                       tenga dato de contacto; 'todos' = usa todos los de la lista
                       que tengan dato y toquen hoy.
  reactivar_automatico (OPCIONAL) TRUE/FALSE. Si es TRUE, los deudores en
                       'enviado' vuelven a 'pendiente' en la siguiente fecha
                       programada, para recibir el siguiente recordatorio.
  max_avisos          (OPCIONAL) numero maximo de dias distintos en que se
                       notifica a un deudor. 0 = sin tope.

  umbral_leve_max     dias de mora hasta los que un deudor es "leve"
  umbral_media_max    dias de mora hasta los que un deudor es "media"
                       (mas alla de esto, es "critica")
"""
from datetime import date, datetime

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

    ("canales_leve", "email", "Canales (en orden de prioridad, separados por coma) para mora leve: email / whatsapp / sms"),
    ("canales_media", "whatsapp,email", "Canales (en orden de prioridad) para mora media"),
    ("canales_critica", "whatsapp,sms,email", "Canales (en orden de prioridad) para mora critica"),
    ("modo_envio", "uno", "uno = solo el primer canal de la lista con dato de contacto; todos = todos los canales de la lista con dato"),
    ("reactivar_automatico", "FALSE", "TRUE = los deudores en 'enviado' vuelven a 'pendiente' en la siguiente fecha programada"),
    ("max_avisos", "0", "Maximo de dias distintos en que se notifica a un deudor (0 = sin tope)"),

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

def es_feriado_hoy(parametros: dict, hoy: date = None) -> bool:
    """
    Cumple el Art. 49 de la Ley Organica de Defensa del Consumidor: prohibido
    gestionar cobros en feriados. Lee la lista de fechas del parametro
    "feriados" (AAAA-MM-DD separadas por coma) y devuelve True si hoy esta
    en esa lista.
    """
    hoy = hoy or date.today()
    feriados_raw = parametros.get("feriados", "").strip()
    if not feriados_raw:
        return False

    fechas = [f.strip() for f in feriados_raw.split(",") if f.strip()]
    for fecha_str in fechas:
        try:
            fecha_feriado = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            if fecha_feriado == hoy:
                return True
        except ValueError:
            continue
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


# ---------------------------------------------------------------------------
# Canales parametrizados por segmento + reactivacion automatica
# ---------------------------------------------------------------------------
CANALES_VALIDOS = ("email", "whatsapp", "sms")


def _lista_canales(valor) -> list:
    """'whatsapp, SMS;email' -> ['whatsapp', 'sms', 'email'] (sin repetidos ni invalidos)."""
    resultado = []
    for c in str(valor or "").lower().replace(";", ",").split(","):
        c = c.strip()
        if c in CANALES_VALIDOS and c not in resultado:
            resultado.append(c)
    return resultado


def canales_configurados(parametros: dict, segmento: str) -> list:
    """Lista ordenada de canales configurada para el segmento. [] si no hay parametro."""
    return _lista_canales(parametros.get(f"canales_{segmento}", ""))


def modo_envio(parametros: dict) -> str:
    return "todos" if parametros.get("modo_envio", "uno").strip().lower() == "todos" else "uno"


def elegir_canales(parametros: dict, segmento: str, canales_hoy: dict, tiene: dict):
    """
    Decide por que canal(es) notificar a un deudor.

    Devuelve (lista_de_canales, motivo), con motivo:
      'ok'           -> hay canal(es) para usar ahora.
      'sin_contacto' -> ningun canal de la lista tiene dato de contacto.
      'no_toca_hoy'  -> hay dato, pero el canal elegido no corresponde hoy.

    modo 'uno':   el primer canal de la lista que tenga dato. Si ese canal no
                  toca hoy, se espera a su dia (no se salta a otro).
    modo 'todos': todos los canales de la lista con dato que toquen hoy.
    """
    con_dato = [c for c in canales_configurados(parametros, segmento) if tiene.get(c)]
    if not con_dato:
        return [], "sin_contacto"
    if modo_envio(parametros) == "uno":
        canal = con_dato[0]
        return ([canal], "ok") if canales_hoy.get(canal) else ([], "no_toca_hoy")
    activos = [c for c in con_dato if canales_hoy.get(c)]
    return (activos, "ok") if activos else ([], "no_toca_hoy")


def reactivar_automatico(parametros: dict) -> bool:
    return parametros.get("reactivar_automatico", "FALSE").strip().upper() == "TRUE"


def max_avisos(parametros: dict) -> int:
    """Tope de dias distintos de notificacion por deudor. 0 = sin tope."""
    try:
        return max(0, int(parametros.get("max_avisos", "0")))
    except ValueError:
        return 0
