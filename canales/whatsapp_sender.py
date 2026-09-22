"""
Envio de WhatsApp via Twilio, usando una PLANTILLA aprobada por Meta
(Content Template Builder), no texto libre.

WhatsApp Business API exige que el primer contacto con cada destinatario
use una plantilla pre-aprobada -- un mensaje de texto libre (como los que
genera Claude para email/SMS) falla con el error 63016 ("Outside messaging
window") si el destinatario no te escribio primero en las ultimas 24h.

Por eso este modulo NO recibe un texto ya redactado -- recibe los valores
de las variables de la plantilla, y Twilio arma el mensaje final.
"""
from twilio.rest import Client
from config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM,
    TWILIO_WHATSAPP_CONTENT_SID, MODO_PRUEBA,
)

_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def enviar_whatsapp(numero_destino: str, content_variables: dict) -> tuple[bool, str]:
    """
    numero_destino debe incluir codigo de pais, ej: +593991234567
    content_variables: dict con las variables de la plantilla, ej:
        {"1": "Juan Perez", "2": "USD", "3": "450.00", "4": "F2201", "5": "45"}
    Devuelve (exito: bool, detalle: str / sid del mensaje).
    """
    if not numero_destino or not str(numero_destino).startswith("+"):
        return False, "numero de whatsapp invalido (debe incluir +codigo_pais)"

    if MODO_PRUEBA:
        return True, "[MODO_PRUEBA] simulado, no enviado realmente"

    if _client is None:
        return False, "credenciales de Twilio no configuradas"

    if not TWILIO_WHATSAPP_CONTENT_SID:
        return False, "falta TWILIO_WHATSAPP_CONTENT_SID (ID de la plantilla aprobada)"

    try:
        import json
        mensaje = _client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{numero_destino}",
            content_sid=TWILIO_WHATSAPP_CONTENT_SID,
            content_variables=json.dumps(content_variables),
        )
        return True, f"enviado (plantilla), sid={mensaje.sid}"

    except Exception as error:
        return False, f"error Twilio WhatsApp: {error}"
