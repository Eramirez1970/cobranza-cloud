"""
Genera el texto del mensaje de cobranza personalizado usando la API de Claude.
Usa Haiku 4.5 por defecto: es el modelo mas barato y es mas que suficiente para
mensajes cortos y directos como los de cobranza.
"""
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT_GENERAL = (
    "Eres un asistente de cobranza financiera para una pequena empresa. "
    "Redactas mensajes breves (maximo 3 lineas), cordiales pero firmes, "
    "en espanol neutro, personalizados con el nombre del deudor y el monto exacto. "
    "Nunca uses lenguaje amenazante, agresivo ni legal. No incluyas saludos "
    "formales tipo 'Estimado/a'; ve directo al mensaje. No inventes datos que no "
    "se te dieron."
)

# SMS tiene un limite tecnico duro: un solo segmento son 160 caracteres sin
# tildes/enies (GSM-7) o solo 70 caracteres con tildes/enies (UCS-2). Ademas,
# algunas operadoras de Ecuador (confirmado: Movistar EC) NO soportan SMS
# concatenados -- si el mensaje ocupa mas de un segmento, simplemente no
# llega. Por eso el SMS usa un prompt distinto: sin tildes, sin enies, y muy
# corto, para quedar dentro de un solo segmento GSM-7 (160 caracteres).
SYSTEM_PROMPT_SMS = (
    "Eres un asistente de cobranza financiera. Redactas UN SOLO SMS, "
    "cordial pero directo, en espanol. "
    "LIMITE DURO: maximo 155 caracteres en total, contando espacios -- no lo "
    "excedas bajo ninguna circunstancia, cuenta los caracteres antes de responder. "
    "NUNCA uses tildes ni la letra enie (escribe 'anio' en vez de 'año', 'dias' "
    "en vez de 'dias' con tilde, 'contactanos' sin tilde) -- esto es obligatorio, "
    "no cosmetico: un SMS con tildes ocupa mas de un mensaje y varias operadoras "
    "en Ecuador no entregan mensajes divididos en varias partes. "
    "No uses saludos tipo 'Estimado'. No uses lenguaje amenazante ni legal. "
    "Responde UNICAMENTE con el texto del SMS, sin explicaciones ni comillas."
)

# Limite de seguridad aplicado siempre en codigo, sin depender de que el
# modelo respete el limite exactamente -- nunca se envia un SMS mas largo
# que esto, para garantizar que quepa en un solo segmento GSM-7.
SMS_MAX_CHARS = 155


def generar_mensaje(nombre: str, monto: float, moneda: str, dias_mora: int,
                     numero_factura: str, segmento: str, canal: str,
                     urgencia: str) -> str:
    """
    Llama a Claude y devuelve el texto del mensaje ya listo para enviar.
    Si la llamada falla, devuelve un mensaje de respaldo generico (fallback)
    para que el proceso nunca se detenga por un error de red o de API.

    Para canal == "sms" usa un prompt distinto (sin tildes, un solo
    segmento) y aplica un recorte de seguridad en codigo.
    """
    es_sms = (canal == "sms")

    if es_sms:
        system_prompt = SYSTEM_PROMPT_SMS
        prompt_usuario = (
            f"Redacta un SMS de cobranza para {nombre}, debe {moneda} {monto:,.2f} "
            f"(factura {numero_factura}), {dias_mora} dias de atraso. "
            f"Tono segun segmento '{segmento}': "
            f"{'amable' if segmento == 'leve' else ''}"
            f"{'de seguimiento' if segmento == 'media' else ''}"
            f"{'urgente, pedir contacto inmediato' if segmento == 'critica' else ''}. "
            f"Recuerda: SIN tildes, SIN enies, maximo 155 caracteres."
        )
        max_tokens = 100
    else:
        system_prompt = SYSTEM_PROMPT_GENERAL
        prompt_usuario = (
            f"Redacta un mensaje de {urgencia} para {nombre}, quien tiene una deuda "
            f"de {moneda} {monto:,.2f} (factura {numero_factura}) vencida hace "
            f"{dias_mora} dias. El canal de envio es {canal}. "
            f"Tono segun segmento '{segmento}': "
            f"{'amable, recordatorio inicial' if segmento == 'leve' else ''}"
            f"{'de seguimiento, recordando el compromiso de pago' if segmento == 'media' else ''}"
            f"{'firme y directo, invitando a contactar urgentemente' if segmento == 'critica' else ''}"
        )
        max_tokens = 300

    try:
        respuesta = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt_usuario}],
        )
        texto = respuesta.content[0].text.strip()

        if es_sms and len(texto) > SMS_MAX_CHARS:
            texto = texto[:SMS_MAX_CHARS].rstrip()

        return texto

    except Exception as error:
        print(f"  [WARN] Fallo la generacion con Claude ({error}). Uso mensaje de respaldo.")
        if es_sms:
            respaldo = (
                f"{nombre}, debes {moneda} {monto:,.2f} (fact. {numero_factura}), "
                f"{dias_mora}d atraso. Contactanos para regularizar."
            )
            return respaldo[:SMS_MAX_CHARS]
        return (
            f"Hola {nombre}, te recordamos que tienes un saldo pendiente de "
            f"{moneda} {monto:,.2f} (factura {numero_factura}), vencido hace "
            f"{dias_mora} dias. Por favor contactanos para regularizar tu pago."
        )
