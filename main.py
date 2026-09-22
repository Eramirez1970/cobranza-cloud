"""
Script principal -- version cloud MULTI-ENTIDAD (Google Sheets + GitHub Actions).

Flujo completo:
  1. Lee el Sheet MAESTRO (pestana "Entidades") y obtiene la lista de
     entidades financieras activas, cada una con su propio sheet_id.
  2. Para CADA entidad activa, de forma independiente:
     a. Lee su hoja "Parametros" (periodicidad propia de esa entidad).
     b. Decide que canales corresponden procesar hoy.
     c. Notifica a sus deudores pendientes (segun sus propios umbrales).
     d. Registra cada intento en su propio "Historial_Envios".
     e. Recalcula sus propias estadisticas (por deudor / semanal / mensual).
     f. Genera SU PROPIO PDF de evidencia, nombrado con el nombre de la entidad.
  3. Si una entidad falla (ej. su Sheet no tiene acceso compartido todavia),
     se registra el error y se sigue con las demas -- una entidad con
     problemas nunca detiene el proceso de las otras.

Ejecutar:
    python main.py

Se programa con GitHub Actions (ver .github/workflows/cobranza.yml) -- no
requiere ningun servidor propio encendido.
"""
import sys
from datetime import datetime, date

from config import MODO_PRUEBA, CARPETA_REPORTES
from config import UMBRAL_LEVE_MAX as UMBRAL_LEVE_DEFAULT, UMBRAL_MEDIA_MAX as UMBRAL_MEDIA_DEFAULT
from segmentacion import segmentar_deudor
from mensajes_claude import generar_mensaje
from canales.email_sender import enviar_email
from canales.whatsapp_sender import enviar_whatsapp
from canales.sms_sender import enviar_sms
from estadisticas import (
    calcular_estadisticas_por_deudor, calcular_resumen_semanal,
    calcular_resumen_mensual, semana_iso_de, anio_mes_de,
)
from reporte_pdf import generar_pdf_evidencia
from parametros import parsear_parametros, canal_corresponde_hoy, umbrales_desde_parametros
import sheets_client as sheets


def _mapear_encabezados(ws_deudores) -> dict:
    fila1 = ws_deudores.row_values(1)
    return {nombre.strip(): i + 1 for i, nombre in enumerate(fila1) if nombre.strip()}


def _dias_mora(fecha_vencimiento_str: str) -> int | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            fecha = datetime.strptime(str(fecha_vencimiento_str).strip(), fmt).date()
            return (date.today() - fecha).days
        except ValueError:
            continue
    return None

def _normalizar_telefono(valor) -> str:
    """
    Normaliza un numero de telefono venido de Google Sheets: lo convierte a
    texto y le agrega el '+' si falta. Existe porque Sheets convierte un '+'
    inicial en una formula, asi que en el Sheet se guarda SIN el '+' (solo
    codigo de pais + numero, ej: 593991234567) y el sistema se lo agrega aqui.
    """
    texto = str(valor).strip() if valor else ""
    if texto and not texto.startswith("+"):
        texto = "+" + texto
    return texto

def procesar_notificaciones(sheet_id: str):
    """Procesa las notificaciones pendientes de UNA entidad (su propio sheet_id)."""
    print("  Leyendo parametros de esta entidad...")
    parametros = parsear_parametros(sheets.leer_parametros(sheet_id))
    umbral_leve, umbral_media = umbrales_desde_parametros(
        parametros, UMBRAL_LEVE_DEFAULT, UMBRAL_MEDIA_DEFAULT)

    canales_hoy = {
        canal: canal_corresponde_hoy(parametros, canal)
        for canal in ("email", "whatsapp", "sms")
    }
    print(f"  Umbrales: leve <= {umbral_leve}d, media <= {umbral_media}d, critica > {umbral_media}d")
    print(f"  Canales activos hoy: {[c for c, v in canales_hoy.items() if v] or 'ninguno'}")

    if not any(canales_hoy.values()):
        print("  Ningun canal corresponde procesar hoy para esta entidad. Se omite.")
        return

    deudores = sheets.leer_deudores(sheet_id)
    ws_deudores = sheets.obtener_worksheet_deudores(sheet_id)
    col = _mapear_encabezados(ws_deudores)

    requeridas = ["id_cliente", "nombre_completo", "email", "whatsapp", "telefono_sms",
                  "monto_adeudado", "moneda", "numero_factura", "fecha_vencimiento",
                  "estado_gestion", "segmento", "canal_enviar", "ultimo_contacto",
                  "mensaje_enviado"]
    faltantes = [c for c in requeridas if c not in col]
    if faltantes:
        print(f"  [ERROR] Faltan columnas en la hoja Deudores: {faltantes}")
        return

    ahora = datetime.now()
    semana_iso = semana_iso_de(ahora)
    anio_mes = anio_mes_de(ahora)
    procesados = enviados = fallidos = omitidos = 0

    for idx, d in enumerate(deudores):
        fila_real = idx + 2

        if str(d.get("estado_gestion", "")).strip().lower() != "pendiente":
            omitidos += 1
            continue

        dias_mora = _dias_mora(d.get("fecha_vencimiento"))
        if dias_mora is None:
            print(f"    [SKIP] {d.get('id_cliente')}: fecha_vencimiento invalida")
            omitidos += 1
            continue

        info = segmentar_deudor(
            dias_mora=dias_mora,
            tiene_whatsapp=bool(d.get("whatsapp")),
            tiene_sms=bool(d.get("telefono_sms")),
            umbral_leve_max=umbral_leve,
            umbral_media_max=umbral_media,
        )
        segmento, canal, urgencia = info["segmento"], info["canal_enviar"], info["urgencia"]

        if not canales_hoy.get(canal, False):
            omitidos += 1
            continue

        print(f"    [{d.get('id_cliente')}] {d.get('nombre_completo')} | {dias_mora}d mora | "
              f"segmento={segmento} | canal={canal}")
        monto = float(d.get("monto_adeudado") or 0)
        moneda = d.get("moneda") or "USD"
        numero_factura = str(d.get("numero_factura"))

        if canal == "whatsapp":
            content_variables = {
                "1": str(d.get("nombre_completo") or ""),
                "2": moneda,
                "3": f"{monto:,.2f}",
                "4": numero_factura,
                "5": str(dias_mora),
            }
            mensaje = (f"Hola {d.get('nombre_completo')}, tienes un saldo pendiente de "
                       f"{moneda} {monto:,.2f} (factura {numero_factura}), vencido hace "
                       f"{dias_mora} dias. Por favor contactanos para regularizar tu pago.")
            exito, detalle = enviar_whatsapp(_normalizar_telefono(d.get("whatsapp")), content_variables)
        else:
            mensaje = generar_mensaje(
                nombre=d.get("nombre_completo"), monto=monto, moneda=moneda,
                dias_mora=dias_mora, numero_factura=numero_factura,
                segmento=segmento, canal=canal, urgencia=urgencia,
            )
            if canal == "email":
                exito, detalle = enviar_email(d.get("email"),
                                               f"Recordatorio de pago - Factura {numero_factura}",
                                               mensaje)
            elif canal == "sms":
                exito, detalle = enviar_sms(_normalizar_telefono(d.get("telefono_sms")), mensaje)
            else:
                exito, detalle = False, f"canal desconocido: {canal}"

        sheets.actualizar_estado_deudor(
            ws_deudores, fila_real, col, segmento, canal,
            "enviado" if exito else "fallido",
            ahora.strftime("%Y-%m-%d %H:%M"), mensaje,
        )

        sheets.registrar_envio(sheet_id, {
            "fecha_hora": ahora.strftime("%Y-%m-%d %H:%M:%S"),
            "id_cliente": d.get("id_cliente"),
            "nombre_completo": d.get("nombre_completo"),
            "canal": canal, "segmento": segmento, "dias_mora": dias_mora,
            "monto_adeudado": monto, "moneda": moneda, "exito": exito,
            "detalle": detalle, "mensaje_enviado": mensaje,
            "semana_iso": semana_iso, "anio_mes": anio_mes,
        })

        procesados += 1
        enviados += 1 if exito else 0
        fallidos += 0 if exito else 1

    print(f"  Procesados: {procesados}  Enviados: {enviados}  Fallidos: {fallidos}  "
          f"Omitidos: {omitidos}")


def recalcular_estadisticas_y_pdf(sheet_id: str, nombre_entidad: str) -> str:
    print("  Recalculando estadisticas desde el historial completo...")
    historial = sheets.leer_historial(sheet_id)

    stats_deudor = calcular_estadisticas_por_deudor(historial)
    resumen_semanal = calcular_resumen_semanal(historial)
    resumen_mensual = calcular_resumen_mensual(historial)

    sheets.escribir_estadisticas_por_deudor(sheet_id, stats_deudor)
    sheets.escribir_resumen(sheet_id, sheets.HOJA_RESUMEN_SEMANAL, resumen_semanal)
    sheets.escribir_resumen(sheet_id, sheets.HOJA_RESUMEN_MENSUAL, resumen_mensual)

    carpeta = f"{CARPETA_REPORTES}"
    ruta_pdf = generar_pdf_evidencia(resumen_semanal, resumen_mensual, stats_deudor,
                                      carpeta, nombre_entidad)
    print(f"  PDF de evidencia generado: {ruta_pdf}")
    return ruta_pdf


def main():
    print(f"Modo prueba: {MODO_PRUEBA}")
    print("Leyendo el Sheet maestro (pestana 'Entidades')...")
    entidades = sheets.leer_entidades_activas()

    if not entidades:
        print("No hay entidades activas configuradas en el Sheet maestro. "
              "Agrega filas con activo=TRUE en la pestana 'Entidades'.")
        return

    print(f"Entidades activas encontradas: {len(entidades)}")
    resultados = {"ok": [], "error": []}

    for entidad in entidades:
        nombre = entidad.get("nombre_entidad", "Sin nombre")
        sheet_id = entidad.get("sheet_id", "").strip()
        print(f"\n=== Procesando entidad: {nombre} ===")

        if not sheet_id or "PEGA_AQUI" in sheet_id:
            print(f"  [ERROR] sheet_id invalido o de ejemplo para '{nombre}', se omite.")
            resultados["error"].append(nombre)
            continue

        try:
            procesar_notificaciones(sheet_id)
            recalcular_estadisticas_y_pdf(sheet_id, nombre)
            resultados["ok"].append(nombre)
        except Exception as error:
            # Una entidad con problemas (ej. Sheet sin compartir con la
            # Service Account) NUNCA debe tumbar el proceso de las demas.
            detalle = str(error) or f"{type(error).__name__} (sin mensaje -- revisa que el Sheet este compartido con la Service Account y que el sheet_id sea correcto)"
            print(f"  [ERROR] Fallo procesando '{nombre}': {detalle}")
      
            resultados["error"].append(nombre)

    print("\n=== RESUMEN GENERAL DE LA CORRIDA ===")
    print(f"Entidades procesadas OK: {resultados['ok']}")
    if resultados["error"]:
        print(f"Entidades con error (revisar): {resultados['error']}")


if __name__ == "__main__":
    main()
