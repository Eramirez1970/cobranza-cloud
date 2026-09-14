"""
Envio de SMS via Twilio. Se usa como canal de respaldo cuando el deudor
no tiene WhatsApp valido, o para casos criticos donde se quiere reforzar
el contacto por un canal adicional.
"""
from twilio.rest import Client
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_SMS_FROM, MODO_PRUEBA

_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def enviar_sms(numero_destino: str, cuerpo: str) -> tuple[bool, str]:
    """
    numero_destino debe incluir codigo de pais, ej: +593991234567
    Devuelve (exito: bool, detalle: str / sid del mensaje).
    """
    if not numero_destino or not numero_destino.startswith("+"):
        return False, "numero de sms invalido (debe incluir +codigo_pais)"

    if MODO_PRUEBA:
        return True, "[MODO_PRUEBA] simulado, no enviado realmente"

    if _client is None:
        return False, "credenciales de Twilio no configuradas"

    try:
        # SMS tiene limite practico de ~160 caracteres por segmento
        mensaje = _client.messages.create(
            from_=TWILIO_SMS_FROM,
            to=numero_destino,
            body=cuerpo[:300],
        )
        return True, f"enviado, sid={mensaje.sid}"

    except Exception as error:
        return False, f"error Twilio SMS: {error}"
