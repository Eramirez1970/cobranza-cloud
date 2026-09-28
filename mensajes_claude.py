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
    Llama a Claude y devuelve el texto del
