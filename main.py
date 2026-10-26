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
import os
import re
import sys
import unicodedata
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
from parametros import (parsear_parametros, canal_corresponde_hoy, umbrales_desde_parametros,
                        es_feriado_hoy, canales_configurados, elegir_canales,
                        reactivar_automatico, max_avisos,
                        ahora_ecuador, puede_enviar_ahora)
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

def _sin_tildes(texto: str) -> str:
    """Quita tildes y caracteres no ASCII. Un SMS con tildes se codifica distinto
    y se parte en mas segmentos (mas caro y mas propenso a fallar en el operador)."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def _separar_asunto(mensaje: str, asunto_defecto: str):
    """Si Claude escribio una linea 'Asunto: ...' al inicio del cuerpo, la usa como
    asunto del correo y la quita del cuerpo. Devuelve (asunto, cuerpo)."""
    lineas = mensaje.strip().splitlines()
    if lineas:
        r = re.match(r"^\W*asunto\W*:?\W*(.+?)\W*$", lineas[0].strip(), re.IGNORECASE)
        if r and r.group(1).strip():
            return r.group(1).strip(), "\n".join(lineas[1:]).strip()
    return asunto_defecto, mensaje.strip()


def _fecha_de(texto):
    try:
        return datetime.strptime(str(texto or "").strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def reactivar_filas(sheet_id, ws, deudores, col, parametros, hoy: date) -> int:
    """
    Reactivacion automatica (solo si reactivar_automatico = TRUE en Parametros).
    Las filas en 'enviado' cuyo ultimo contacto fue antes de hoy vuelven a
    'pendiente'; el flujo normal decide despues si su canal toca hoy.
    Estados como 'pagado', 'excluido', 'fallido' o 'sin_contacto' NUNCA se reactivan.
    Si max_avisos > 0, quien ya recibio ese numero de dias distintos de aviso
    pasa a 'limite_avisos' y no se vuelve a notificar.
    """
    if not reactivar_automatico(parametros):
        return 0
    tope = max_avisos(parametros)
    dias_avisados = {}
    if tope:
        for h in sheets.leer_historial(sheet_id):
            if str(h.get("exito")).strip().upper() == "TRUE":
                dias_avisados.setdefault(str(h.get("id_cliente")), set()).add(
                    str(h.get("fecha_hora", ""))[:10])
    reactivadas = 0
    for idx, d in enumerate(deudores):
        if str(d.get("estado_gestion", "")).strip().lower() != "enviado":
            continue
        ultimo = _fecha_de(d.get("ultimo_contacto"))
        if ultimo is None or ultimo >= hoy:
            continue
        fila = idx + 2
        if tope and len(dias_avisados.get(str(d.get("id_cliente")), ())) >= tope:
            ws.update_cell(fila, col["estado_gestion"], "limite_avisos")
            d["estado_gestion"] = "limite_avisos"
            continue
        ws.update_cell(fila, col["estado_gestion"], "pendiente")
        d["estado_gestion"] = "pendiente"
        reactivadas += 1
    return reactivadas


def _enviar_por_canal(canal, d, segmento, urgencia, dias_mora, monto, moneda, numero_factura):
    """Envia UN mensaje por UN canal. Devuelve (exito, detalle, mensaje)."""
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
        return exito, detalle, mensaje

    mensaje = generar_mensaje(
        nombre=d.get("nombre_completo"), monto=monto, moneda=moneda,
        dias_mora=dias_mora, numero_factura=numero_factura,
        segmento=segmento, canal=canal, urgencia=urgencia,
    )
    if canal == "email":
        asunto, cuerpo = _separar_asunto(mensaje, f"Recordatorio de pago - Factura {numero_factura}")
        exito, detalle = enviar_email(d.get("email"), asunto, cuerpo)
        return exito, detalle, cuerpo
    if canal == "sms":
        mensaje = _sin_tildes(mensaje)
        exito, detalle = enviar_sms(_normalizar_telefono(d.get("telefono_sms")), mensaje)
        return exito, detalle, mensaje
    return False, f"canal desconocido: {canal}", mensaje


def procesar_notificaciones(sheet_id: str):
    """Procesa las notificaciones pendientes de UNA entidad (su propio sheet_id)."""
    print("  Leyendo parametros de esta entidad...")
    parametros = parsear_parametros(sheets.leer_parametros(sheet_id))
    umbral_leve, umbral_media = umbrales_desde_parametros(
        parametros, UMBRAL_LEVE_DEFAULT, UMBRAL_MEDIA_DEFAULT)

    permitido, motivo_ventana = puede_enviar_ahora(parametros, ahora_ecuador())
    if not permitido:
        print(f"  No se envia nada: {motivo_ventana}. La gestion de cobranza solo se permite de "
              "lunes a viernes, de 07:00 a 20:00 (hora de Ecuador) y fuera de feriados "
              "(Art. 49 Ley Organica de Defensa del Consumidor). Los deudores siguen en 'pendiente'.")
        return

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

    ahora = ahora_ecuador()
    reactivadas = reactivar_filas(sheet_id, ws_deudores, deudores, col, parametros, ahora.date())
    if reactivadas:
        print(f"  Reactivadas automaticamente para este ciclo: {reactivadas}")
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
        segmento, canal_clasico, urgencia = info["segmento"], info["canal_enviar"], info["urgencia"]

        if canales_configurados(parametros, segmento):
            # Modo parametrizado: canales segun Parametros (canales_<segmento> + modo_envio)
            tiene = {
                "email": bool(str(d.get("email") or "").strip()),
                "whatsapp": bool(str(d.get("whatsapp") or "").strip()),
                "sms": bool(str(d.get("telefono_sms") or "").strip()),
            }
            canales, motivo = elegir_canales(parametros, segmento, canales_hoy, tiene)
            if motivo == "sin_contacto":
                print(f"    [SIN CONTACTO] {d.get('id_cliente')}: ningun canal de la lista "
                      f"tiene dato de contacto")
                ws_deudores.update_cell(fila_real, col["estado_gestion"], "sin_contacto")
                omitidos += 1
                continue
            if motivo == "no_toca_hoy":
                omitidos += 1
                continue
        else:
            # Modo clasico (sin parametros nuevos): un canal segun segmentar_deudor
            if not canales_hoy.get(canal_clasico, False):
                omitidos += 1
                continue
            canales = [canal_clasico]

        # Re-chequeo justo antes de enviar: una corrida larga no debe cruzar las 20:00
        ahora_envio = ahora_ecuador()
        permitido, motivo_ventana = puede_enviar_ahora(parametros, ahora_envio)
        if not permitido:
            print(f"    [ALTO] Se detiene el envio: {motivo_ventana}. "
                  "Los deudores restantes siguen en 'pendiente' para la proxima corrida.")
            break

        print(f"    [{d.get('id_cliente')}] {d.get('nombre_completo')} | {dias_mora}d mora | "
              f"segmento={segmento} | canal={'+'.join(canales)}")
        monto = float(d.get("monto_adeudado") or 0)
        moneda = d.get("moneda") or "USD"
        numero_factura = str(d.get("numero_factura"))

        resultados_canal = []
        for canal in canales:
            exito_c, detalle_c, mensaje_c = _enviar_por_canal(
                canal, d, segmento, urgencia, dias_mora, monto, moneda, numero_factura)
            resultados_canal.append((canal, exito_c, detalle_c, mensaje_c))
            sheets.registrar_envio(sheet_id, {
                "fecha_hora": ahora_envio.strftime("%Y-%m-%d %H:%M:%S"),
                "id_cliente": d.get("id_cliente"),
                "nombre_completo": d.get("nombre_completo"),
                "canal": canal, "segmento": segmento, "dias_mora": dias_mora,
                "monto_adeudado": monto, "moneda": moneda, "exito": exito_c,
                "detalle": detalle_c, "mensaje_enviado": mensaje_c,
                "semana_iso": semana_iso, "anio_mes": anio_mes,
            })

        exito = any(r[1] for r in resultados_canal)
        if len(resultados_canal) == 1:
            mensaje_hoja = resultados_canal[0][3]
        else:
            mensaje_hoja = "\n---\n".join(f"[{r[0]}] {r[3]}" for r in resultados_canal)

        sheets.actualizar_estado_deudor(
            ws_deudores, fila_real, col, segmento, "+".join(canales),
            "enviado" if exito else "fallido",
            ahora_envio.strftime("%Y-%m-%d %H:%M"), mensaje_hoja,
        )

        # Si hubo fallos, dejar el motivo en 'notas' (si la columna existe)
        fallos = [f"{r[0]}: {r[2]}" for r in resultados_canal if not r[1]]
        if fallos and "notas" in col:
            ws_deudores.update_cell(fila_real, col["notas"], " | ".join(fallos)[:500])

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
    from drive_uploader import subir_pdf_a_drive
    
    from datetime import datetime as _dt
    link_drive = subir_pdf_a_drive(ruta_pdf)
    if link_drive:
        sheets.registrar_reporte(sheet_id, _dt.now().strftime("%Y-%m-%d %H:%M"),
                                  os.path.basename(ruta_pdf), link_drive)
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
