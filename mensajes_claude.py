"""
Genera el texto del mensaje de cobranza personalizado usando la API de Claude.
Usa Haiku 4.5 por defecto: es el modelo mas barato y es mas que suficiente para
mensajes cortos y directos como los de cobranza.
"""
import os
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Nombre con el que se firma el mensaje. Viene del Secret NOMBRE_EMPRESA.
_EMPRESA = os.getenv("NOMBRE_EMPRESA", "").strip()

SYSTEM_PROMPT = (
    "Eres un asistente de cobranza financiera para una pequena empresa. "
    "Redactas mensajes breves (maximo 3 lineas), cordiales pero firmes, "
    "en espanol neutro, personalizados con el nombre del deudor y el monto exacto. "
    "Nunca uses lenguaje amenazante, agresivo ni legal. No incluyas saludos "
    "formales tipo 'Estimado/a'; ve directo al mensaje. "
    "REGLAS ESTRICTAS SOBRE LOS HECHOS: usa unicamente los datos que se te dan "
    "(nombre, monto, moneda, factura, dias de mora). NO afirmes ni insinues "
    "compromisos de pago, acuerdos, promesas, llamadas, conversaciones o "
    "gestiones previas con el deudor, porque no tienes ese dato. "
    "NO inventes fechas limite, recargos, intereses, sanciones, consecuencias "
    "legales ni medios de pago. "
    "Habla siempre en nombre de la empresa, en primera persona del plural "
    "('te recordamos', 'te invitamos'), y no te presentes como asistente ni "
    "como inteligencia artificial."
    + (f" Si necesitas firmar, firma solo como '{_EMPRESA}'." if _EMPRESA else
       " No agregues firma ni nombre de empresa.")
)

_TONO_POR_SEGMENTO = {
    "leve": "amable, recordatorio inicial de un pago pendiente",
    "media": ("de seguimiento: indica que el pago sigue pendiente y pide "
              "regularizarlo. No menciones compromisos ni acuerdos previos"),
    "critica": "firme y directo, invitando a contactarnos con urgencia",
}


def generar_mensaje(nombre: str, monto: float, moneda: str, dias_mora: int,
                     numero_factura: str, segmento: str, canal: str,
                     urgencia: str) -> str:
    """
    Llama a Claude y devuelve el texto del mensaje ya listo para enviar.
    Si la llamada falla, devuelve un mensaje de respaldo generico (fallback)
    para que el proceso nunca se detenga por un error de red o de API.
    """
    tono = _TONO_POR_SEGMENTO.get(segmento, _TONO_POR_SEGMENTO["leve"])
    prompt_usuario = (
        f"Redacta un mensaje de {urgencia} para {nombre}, quien tiene una deuda "
        f"de {moneda} {monto:,.2f} (factura {numero_factura}) vencida hace "
        f"{dias_mora} dias. El canal de envio es {canal}. "
        f"Tono segun segmento '{segmento}': {tono}. "
        f"Usa solo estos datos; no agregues nada mas."
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
