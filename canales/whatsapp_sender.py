"""
Envio de plantillas de WhatsApp via Twilio (WhatsApp Business API).
Requiere que el numero de origen (TWILIO_WHATSAPP_FROM) este aprobado por Meta
y que exista una plantilla de tipo 'utility' aprobada si envias fuera de la
ventana de servicio de 24h -- ver README para el proceso de aprobacion.
"""
from twilio.rest import Client
from config import (
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, MODO_PRUEBA,
)

_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# DEBUG TEMPORAL: confirma, sin exponer el secreto completo, si
# TWILIO_WHATSAPP_FROM tiene el prefijo correcto y su longitud.
print(f"  [DEBUG] TWILIO_WHATSAPP_FROM -> longitud={len(TWILIO_WHATSAPP_FROM or '')}, "
      f"empieza_con_whatsapp:={str(TWILIO_WHATSAPP_FROM or '').startswith('whatsapp:')}, "
      f"ultimos_4={str(TWILIO_WHATSAPP_FROM or '')[-4:]}")

def enviar_whatsapp(numero_destino: str, cuerpo: str) -> tuple[bool, str]:
    """
    numero_destino debe incluir codigo de pais, ej: +593991234567
    Devuelve (exito: bool, detalle: str / sid del mensaje).
    """
    if not numero_destino or not numero_destino.startswith("+"):
        return False, "numero de whatsapp invalido (debe incluir +codigo_pais)"

    if MODO_PRUEBA:
        return True, "[MODO_PRUEBA] simulado, no enviado realmente"

    if _client is None:
        return False, "credenciales de Twilio no configuradas"

    try:
        mensaje = _client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{numero_destino}",
            body=cuerpo,
        )
        return True, f"enviado, sid={mensaje.sid}"

    except Exception as error:
        return False, f"error Twilio WhatsApp: {error}"
