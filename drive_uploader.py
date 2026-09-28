"""
Sube el PDF de evidencia generado a una carpeta de Google Drive, para que
quede guardado de forma permanente -- los Artifacts de GitHub Actions se
borran solos a los 90 dias, esto no.

Usa las MISMAS credenciales que ya tenemos para Google Sheets (Workload
Identity Federation via ADC, o la clave JSON si se usa localmente) -- no
se necesita ninguna credencial nueva, solo que la carpeta de Drive este
compartida con el email de la Service Account, igual que los Sheets.
"""
import os
import json
import google.auth
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import GOOGLE_CREDENTIALS_JSON, GOOGLE_DRIVE_FOLDER_ID

SCOPES = ["https://www.googleapis.com/auth/drive"]

_service = None


def _drive_service():
    global _service
    if _service is not None:
        return _service

    if GOOGLE_CREDENTIALS_JSON:
        info = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds, _ = google.auth.default(scopes=SCOPES)

    _service = build("drive", "v3", credentials=creds)
    return _service


def subir_pdf_a_drive(ruta_local: str) -> str:
    """
    Sube el archivo PDF indicado a la carpeta de Drive configurada
    (GOOGLE_DRIVE_FOLDER_ID). Devuelve el link para verlo en Drive, o
    cadena vacia si la carpeta no esta configurada o algo falla -- nunca
    detiene el resto del proceso por esto.
    """
    if not GOOGLE_DRIVE_FOLDER_ID:
        print("  [INFO] GOOGLE_DRIVE_FOLDER_ID no configurado -- se omite la subida a Drive.")
        return ""

    if not os.path.exists(ruta_local):
        print(f"  [WARN] No se encontro el archivo a subir: {ruta_local}")
        return ""

    try:
        service = _drive_service()
        nombre_archivo = os.path.basename(ruta_local)
        metadata = {"name": nombre_archivo, "parents": [GOOGLE_DRIVE_FOLDER_ID]}
        media = MediaFileUpload(ruta_local, mimetype="application/pdf")

        archivo = service.files().create(
            body=metadata, media_body=media, fields="id, webViewLink"
        ).execute()

        link = archivo.get("webViewLink", "")
        print(f"  PDF subido a Google Drive: {link}")
        return link

    except Exception as error:
        print(f"  [WARN] No se pudo subir el PDF a Drive: {error}")
        return ""
