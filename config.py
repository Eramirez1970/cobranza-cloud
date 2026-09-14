"""
Configuracion central del bot de cobranza -- version cloud (Google Sheets).
Todas las credenciales se leen de variables de entorno / GitHub Secrets.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Claude API ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# --- Google Sheets ---
# Metodo de autenticacion PRINCIPAL: Workload Identity Federation (sin clave
# JSON). Cuando corre en GitHub Actions con google-github-actions/auth, las
# credenciales se inyectan automaticamente -- GOOGLE_CREDENTIALS_JSON NO se
# necesita y puede quedar vacio.
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # opcional, ver sheets_client.py

# GOOGLE_SHEET_ID_MAESTRO: el Sheet de control que lista todas las entidades
# financieras activas y el sheet_id propio de cada una (pestana "Entidades").
GOOGLE_SHEET_ID_MAESTRO = os.getenv("GOOGLE_SHEET_ID_MAESTRO")

# --- Email (Amazon SES via SMTP) ---
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_REMITENTE = os.getenv("EMAIL_REMITENTE")
EMAIL_NOMBRE_REMITENTE = os.getenv("EMAIL_NOMBRE_REMITENTE", "Cobranzas")

# --- Twilio (WhatsApp + SMS) ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
TWILIO_SMS_FROM = os.getenv("TWILIO_SMS_FROM")

# --- Reglas de negocio ---
UMBRAL_LEVE_MAX = int(os.getenv("UMBRAL_LEVE_MAX", "30"))
UMBRAL_MEDIA_MAX = int(os.getenv("UMBRAL_MEDIA_MAX", "60"))

# --- Datos de la empresa (para el PDF de evidencia) ---
# NOMBRE_EMPRESA es fijo (tu emprendimiento). El nombre de la entidad
# financiera destinataria ya NO es fijo -- se toma de la fila de cada
# entidad en la pestana "Entidades" del Sheet maestro.
NOMBRE_EMPRESA = os.getenv("NOMBRE_EMPRESA", "Mi Empresa")

# --- Carpeta de salida para reportes generados (Excel resumen + PDF) ---
CARPETA_REPORTES = os.getenv("CARPETA_REPORTES", "reportes")

# --- Modo de prueba: True = no envia nada real, solo simula y registra ---
MODO_PRUEBA = os.getenv("MODO_PRUEBA", "true").lower() == "true"
