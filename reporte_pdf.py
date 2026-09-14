"""
Genera el PDF formal que se entrega a la entidad financiera como evidencia
del trabajo de cobranza realizado, con el resumen semanal y mensual mas
reciente, mas el detalle por deudor.
"""
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from config import NOMBRE_EMPRESA


def _tabla_resumen(filas: list[dict], columnas: list[tuple[str, str]]) -> Table:
    """columnas: lista de (clave_dict, encabezado_visible)"""
    encabezados = [c[1] for c in columnas]
    data = [encabezados]
    for f in filas:
        data.append([str(f.get(c[0], "")) for c in columnas])

    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def generar_pdf_evidencia(resumen_semanal: list[dict], resumen_mensual: list[dict],
                           stats_por_deudor: list[dict], carpeta_salida: str,
                           nombre_entidad: str) -> str:
    os.makedirs(carpeta_salida, exist_ok=True)
    ahora = datetime.now()
    slug_entidad = "".join(c if c.isalnum() else "_" for c in nombre_entidad).strip("_")
    ruta = os.path.join(carpeta_salida,
                         f"evidencia_cobranza_{slug_entidad}_{ahora.strftime('%Y%m%d_%H%M')}.pdf")

    doc = SimpleDocTemplate(ruta, pagesize=letter,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle("TituloCustom", parent=styles["Title"], fontSize=16)
    subtitulo_style = ParagraphStyle("SubtituloCustom", parent=styles["Heading2"], fontSize=12,
                                      textColor=colors.HexColor("#1F4E78"))

    story = []
    story.append(Paragraph("Informe de Gestion de Cobranza", titulo_style))
    story.append(Paragraph(f"Emitido por: {NOMBRE_EMPRESA}", styles["Normal"]))
    story.append(Paragraph(f"Dirigido a: {nombre_entidad}", styles["Normal"]))
    story.append(Paragraph(f"Fecha de generacion: {ahora.strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "Este documento resume las notificaciones de cobranza realizadas por "
        "email, WhatsApp y SMS, incluyendo tasa de entrega, canal utilizado y "
        "monto de cartera gestionado, como evidencia del trabajo de seguimiento "
        "a la cartera de deudores.", styles["Normal"]))
    story.append(Spacer(1, 16))

    columnas_periodo = [
        ("periodo", "Periodo"), ("total_deudores_gestionados", "Deudores"),
        ("total_notificaciones", "Notif."), ("exitosas", "Exitosas"),
        ("fallidas", "Fallidas"), ("tasa_exito_pct", "% Exito"),
        ("por_email", "Email"), ("por_whatsapp", "WhatsApp"), ("por_sms", "SMS"),
        ("monto_total_cartera_gestionada", "Monto gestionado"),
    ]

    story.append(Paragraph("Resumen Semanal", subtitulo_style))
    if resumen_semanal:
        story.append(_tabla_resumen(resumen_semanal, columnas_periodo))
    else:
        story.append(Paragraph("Sin datos registrados en este periodo.", styles["Normal"]))
    story.append(Spacer(1, 20))

    story.append(Paragraph("Resumen Mensual", subtitulo_style))
    if resumen_mensual:
        story.append(_tabla_resumen(resumen_mensual, columnas_periodo))
    else:
        story.append(Paragraph("Sin datos registrados en este periodo.", styles["Normal"]))

    story.append(PageBreak())

    story.append(Paragraph("Detalle por Deudor", subtitulo_style))
    columnas_deudor = [
        ("id_cliente", "ID"), ("nombre_completo", "Nombre"),
        ("total_intentos", "Intentos"), ("exitosos", "Exitosos"),
        ("fallidos", "Fallidos"), ("estado_actual", "Estado"),
        ("ultimo_contacto", "Ultimo contacto"),
        ("monto_adeudado_actual", "Monto"),
    ]
    if stats_por_deudor:
        story.append(_tabla_resumen(stats_por_deudor, columnas_deudor))
    else:
        story.append(Paragraph("Sin deudores con intentos registrados.", styles["Normal"]))

    doc.build(story)
    return ruta
