"""
Genera el texto del mensaje de cobranza personalizado usando la API de Claude.
Usa Haiku 4.5 por defecto: es el modelo mas barato y es mas que suficiente para
mensajes cortos y directos como los de cobranza.
"""
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = (
    "Eres un asistente de cobranza financiera para una pequena empresa. "
    "Redactas mensajes breves (maximo 3 lineas), cordiales pero firmes, "
    "en espanol neutro, personalizados con el nombre del deudor y el monto exacto. "
    "Nunca uses lenguaje amenazante, agresivo ni legal. No incluyas saludos "
    "formales tipo 'Estimado/a'; ve directo al mensaje. No inventes datos que no "
    "se te dieron."
)


def generar_mensaje(nombre: str, monto: float, moneda: str, dias_mora: int,
                     numero_factura: str, segmento: str, canal: str,
                     urgencia: str) -> str:
    """
    Llama a Claude y devuelve el texto del mensaje ya listo para enviar.
    Si la llamada falla, devuelve un mensaje de respaldo generico (fallback)
    para que el proceso nunca se detenga por un error de red o de API.
    """
    prompt_usuario = (
        f"Redacta un mensaje de {urgencia} para {nombre}, quien tiene una deuda "
        f"de {moneda} {monto:,.2f} (factura {numero_factura}) vencida hace "
        f"{dias_mora} dias. El canal de envio es {canal}. "
        f"Tono segun segmento '{segmento}': "
        f"{'amable, recordatorio inicial' if segmento == 'leve' else ''}"
        f"{'de seguimiento, recordando el compromiso de pago' if segmento == 'media' else ''}"
        f"{'firme y directo, invitando a contactar urgentemente' if segmento == 'critica' else ''}"
    )

    try:
        respuesta = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt_usuario}],
        )
        return respuesta.content[0].text.strip()

    except Exception as error:
        print(f"  [WARN] Fallo la generacion con Claude ({error}). Uso mensaje de respaldo.")
        return (
            f"Hola {nombre}, te recordamos que tienes un saldo pendiente de "
            f"{moneda} {monto:,.2f} (factura {numero_factura}), vencido hace "
            f"{dias_mora} dias. Por favor contactanos para regularizar tu pago."
        )
