"""
Wrapper sobre gspread para leer/escribir en los Google Sheets del sistema.

Hay DOS TIPOS de Sheet:

  1. Sheet MAESTRO (uno solo): pestana "Entidades" con la lista de entidades
     financieras activas y el ID del Sheet propio de cada una. Es el punto
     de entrada -- el script lo lee primero para saber por cuales entidades
     iterar.

  2. Sheet POR ENTIDAD (uno por cada entidad financiera): mismas 6 pestanas
     que ya conoces -- "Deudores", "Historial_Envios", "Parametros",
     "Estadisticas_Por_Deudor", "Resumen_Semanal", "Resumen_Mensual".
     Cada una es independiente: su propia cartera, su propia periodicidad,
     su propio historial y su propio PDF de evidencia.

Todas las funciones de este modulo reciben el sheet_id de la entidad como
parametro explicito -- asi el mismo codigo sirve para cualquier cantidad de
entidades sin duplicar nada.

Autenticacion: una sola Service Account de Google Cloud sirve para todas
las entidades -- solo hay que compartirle acceso de Editor a cada Sheet
(el maestro y el de cada entidad) la primera vez que se agrega.
"""
import json
import gspread
import google.auth
from google.oauth2.service_account import Credentials

from config import GOOGLE_CREDENTIALS_JSON, GOOGLE_SHEET_ID_MAESTRO

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HOJA_ENTIDADES = "Entidades"
HOJA_DEUDORES = "Deudores"
HOJA_HISTORIAL = "Historial_Envios"
HOJA_STATS_DEUDOR = "Estadisticas_Por_Deudor"
HOJA_RESUMEN_SEMANAL = "Resumen_Semanal"
HOJA_RESUMEN_MENSUAL = "Resumen_Mensual"
HOJA_PARAMETROS = "Parametros"

COLUMNAS_ENTIDADES = ["nombre_entidad", "sheet_id", "activo", "notas"]

COLUMNAS_HISTORIAL = [
    "fecha_hora", "id_cliente", "nombre_completo", "canal", "segmento",
    "dias_mora", "monto_adeudado", "moneda", "exito", "detalle", "mensaje_enviado",
    "semana_iso", "anio_mes",
]

COLUMNAS_STATS_DEUDOR = [
    "id_cliente", "nombre_completo", "total_intentos", "exitosos", "fallidos",
    "intentos_email", "intentos_whatsapp", "intentos_sms",
    "primer_contacto", "ultimo_contacto", "estado_actual", "monto_adeudado_actual",
]

COLUMNAS_RESUMEN = [
    "periodo", "total_deudores_gestionados", "total_notificaciones",
    "exitosas", "fallidas", "tasa_exito_pct",
    "por_email", "por_whatsapp", "por_sms",
    "leve", "media", "critica",
    "monto_total_cartera_gestionada",
]


def _client():
    """
    Soporta 2 metodos de autenticacion:
      1. Workload Identity Federation (recomendado, sin archivo de clave) --
         cuando corre en GitHub Actions con google-github-actions/auth, las
         credenciales quedan disponibles automaticamente via Application
         Default Credentials (ADC); no se necesita GOOGLE_CREDENTIALS_JSON.
      2. Clave JSON de Service Account (metodo clasico) -- se usa solo si
         GOOGLE_CREDENTIALS_JSON esta definido (ej. para pruebas locales si
         en algun momento consigues una clave).
    """
    if GOOGLE_CREDENTIALS_JSON:
        info = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds, _ = google.auth.default(scopes=SCOPES)
    return gspread.authorize(creds)


def _abrir_sheet(sheet_id: str):
    if not sheet_id:
        raise RuntimeError("Se requiere un sheet_id valido")
    return _client().open_by_key(sheet_id)


def _obtener_o_crear_hoja(sheet, nombre, encabezados):
    try:
        ws = sheet.worksheet(nombre)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=nombre, rows=1000, cols=len(encabezados) + 2)
        ws.append_row(encabezados)
        return ws
    if not ws.get_all_values():
        ws.append_row(encabezados)
    return ws


# ------------------------------------------------------------------
# Sheet MAESTRO -- lista de entidades financieras
# ------------------------------------------------------------------

def leer_entidades_activas() -> list[dict]:
    """
    Lee la pestana 'Entidades' del Sheet MAESTRO. Si no existe, la crea
    con una fila de ejemplo (comentada via notas) para que el usuario
    sepa como llenarla.
    Devuelve solo las filas con activo = TRUE.
    """
    sheet = _abrir_sheet(GOOGLE_SHEET_ID_MAESTRO)
    try:
        ws = sheet.worksheet(HOJA_ENTIDADES)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=HOJA_ENTIDADES, rows=50, cols=4)
        ws.append_row(COLUMNAS_ENTIDADES)
        ws.append_row([
            "Banco Ejemplo S.A.", "PEGA_AQUI_EL_SHEET_ID_DE_ESTA_ENTIDAD", "FALSE",
            "Fila de ejemplo -- reemplaza con tu entidad real y pon activo=TRUE",
        ])
        print(f"  [INFO] Hoja '{HOJA_ENTIDADES}' creada en el Sheet maestro con una fila "
              f"de ejemplo. Agrega ahi cada entidad financiera real.")
        return []

    todas = ws.get_all_records()
    activas = [e for e in todas if str(e.get("activo", "")).strip().upper() == "TRUE"]
    return activas


# ------------------------------------------------------------------
# Sheet POR ENTIDAD -- Parametros, Deudores, Historial, Estadisticas
# ------------------------------------------------------------------

def leer_parametros(sheet_id: str) -> list[dict]:
    from parametros import VALORES_POR_DEFECTO

    sheet = _abrir_sheet(sheet_id)
    encabezados = ["parametro", "valor", "descripcion"]
    try:
        ws = sheet.worksheet(HOJA_PARAMETROS)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=HOJA_PARAMETROS, rows=50, cols=3)
        ws.append_row(encabezados)
        ws.append_rows([list(fila) for fila in VALORES_POR_DEFECTO],
                        value_input_option="USER_ENTERED")
        print(f"  [INFO] Hoja '{HOJA_PARAMETROS}' creada con valores por defecto para esta entidad.")
    return ws.get_all_records()


def leer_deudores(sheet_id: str) -> list[dict]:
    sheet = _abrir_sheet(sheet_id)
    ws = sheet.worksheet(HOJA_DEUDORES)
    return ws.get_all_records()


def obtener_worksheet_deudores(sheet_id: str):
    sheet = _abrir_sheet(sheet_id)
    return sheet.worksheet(HOJA_DEUDORES)


def actualizar_estado_deudor(ws_deudores, fila_index: int, encabezados: dict,
                              segmento: str, canal: str, estado: str,
                              ultimo_contacto: str, mensaje: str):
    ws_deudores.update_cell(fila_index, encabezados["segmento"], segmento)
    ws_deudores.update_cell(fila_index, encabezados["canal_enviar"], canal)
    ws_deudores.update_cell(fila_index, encabezados["estado_gestion"], estado)
    ws_deudores.update_cell(fila_index, encabezados["ultimo_contacto"], ultimo_contacto)
    ws_deudores.update_cell(fila_index, encabezados["mensaje_enviado"], mensaje)


def registrar_envio(sheet_id: str, registro: dict):
    sheet = _abrir_sheet(sheet_id)
    ws = _obtener_o_crear_hoja(sheet, HOJA_HISTORIAL, COLUMNAS_HISTORIAL)
    fila = [registro.get(c, "") for c in COLUMNAS_HISTORIAL]
    ws.append_row(fila, value_input_option="USER_ENTERED")


def leer_historial(sheet_id: str) -> list[dict]:
    sheet = _abrir_sheet(sheet_id)
    ws = _obtener_o_crear_hoja(sheet, HOJA_HISTORIAL, COLUMNAS_HISTORIAL)
    return ws.get_all_records()


def escribir_estadisticas_por_deudor(sheet_id: str, filas: list[dict]):
    sheet = _abrir_sheet(sheet_id)
    ws = _obtener_o_crear_hoja(sheet, HOJA_STATS_DEUDOR, COLUMNAS_STATS_DEUDOR)
    ws.clear()
    ws.append_row(COLUMNAS_STATS_DEUDOR)
    if filas:
        ws.append_rows([[f.get(c, "") for c in COLUMNAS_STATS_DEUDOR] for f in filas],
                        value_input_option="USER_ENTERED")


def escribir_resumen(sheet_id: str, hoja_nombre: str, filas: list[dict]):
    sheet = _abrir_sheet(sheet_id)
    ws = _obtener_o_crear_hoja(sheet, hoja_nombre, COLUMNAS_RESUMEN)
    ws.clear()
    ws.append_row(COLUMNAS_RESUMEN)
    if filas:
        ws.append_rows([[f.get(c, "") for c in COLUMNAS_RESUMEN] for f in filas],
                        value_input_option="USER_ENTERED")
