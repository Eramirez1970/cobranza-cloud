"""
Envio de correos via SMTP estandar -- funciona tanto con Amazon SES (SMTP),
SendGrid, Gmail, o cualquier proveedor que exponga un servidor SMTP.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    EMAIL_REMITENTE, EMAIL_NOMBRE_REMITENTE, MODO_PRUEBA,
)


def enviar_email(destinatario: str, asunto: str, cuerpo: str) -> tuple[bool, str]:
    """
    Devuelve (exito: bool, detalle: str).
    En MODO_PRUEBA no envia nada real, solo simula y confirma que los datos
    son validos -- util para probar todo el flujo antes de gastar dinero real.
    """
    if not destinatario or "@" not in destinatario:
        return False, "email invalido o vacio"

    if MODO_PRUEBA:
        return True, "[MODO_PRUEBA] simulado, no enviado realmente"

    try:
        msg = MIMEMultipart()
        msg["From"] = f"{EMAIL_NOMBRE_REMITENTE} <{EMAIL_REMITENTE}>"
        msg["To"] = destinatario
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_REMITENTE, destinatario, msg.as_string())

        return True, "enviado"

    except Exception as error:
        return False, f"error SMTP: {error}"
