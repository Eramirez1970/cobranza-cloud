"""
Segmenta cada deudor por dias de mora y decide:
  - segmento: leve / media / critica
  - canal_enviar: email / whatsapp / sms
  - urgencia: texto que se usa luego en el prompt de Claude

Regla de negocio (los umbrales ahora se leen de la hoja "Parametros" del
Google Sheet en cada corrida -- no estan fijos en el codigo):
  - leve   (<= umbral_leve_max dias):  email          -> costo minimo
  - media  (<= umbral_media_max dias): email primero, escala a whatsapp si "reintento" = True
  - critica (mas de umbral_media_max): whatsapp       -> canal de mayor urgencia/entrega
  - Si no hay whatsapp valido pero si telefono_sms, se usa sms como respaldo.
"""
from config import UMBRAL_LEVE_MAX as _DEFAULT_LEVE, UMBRAL_MEDIA_MAX as _DEFAULT_MEDIA


def segmentar_deudor(dias_mora: int, tiene_whatsapp: bool, tiene_sms: bool,
                      es_reintento: bool = False,
                      umbral_leve_max: int = _DEFAULT_LEVE,
                      umbral_media_max: int = _DEFAULT_MEDIA) -> dict:
    """
    Devuelve un dict con segmento, canal_enviar y urgencia para un deudor.
    dias_mora: entero, resultado de (hoy - fecha_vencimiento)
    tiene_whatsapp / tiene_sms: booleanos, si el dato de contacto existe y es valido
    es_reintento: True si ya se envio email antes y no hubo respuesta (para escalar)
    umbral_leve_max / umbral_media_max: vienen de la hoja "Parametros" en
      produccion; si no se pasan, usa los defaults de config.py.
    """
    if dias_mora <= umbral_leve_max:
        segmento = "leve"
        urgencia = "recordatorio amable de pago"
        canal = "email"

    elif dias_mora <= umbral_media_max:
        segmento = "media"
        urgencia = "aviso de seguimiento, recordando el compromiso de pago"
        if es_reintento and tiene_whatsapp:
            canal = "whatsapp"
        else:
            canal = "email"

    else:
        segmento = "critica"
        urgencia = "aviso urgente, invitando a contactar de inmediato para regularizar"
        if tiene_whatsapp:
            canal = "whatsapp"
        elif tiene_sms:
            canal = "sms"
        else:
            canal = "email"

    return {"segmento": segmento, "canal_enviar": canal, "urgencia": urgencia}
