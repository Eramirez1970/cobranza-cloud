"""
Calcula las 3 vistas de estadisticas que pide la entidad financiera, a partir
del historial completo (append-only) de envios:

  1. Por deudor: cuantos intentos, por que canal, tasa de exito individual.
  2. Semanal: agregado de TODAS las notificaciones de cada semana ISO.
  3. Mensual: agregado de TODAS las notificaciones de cada mes calendario.

Se recalculan completas en cada corrida (no se acumulan a mano) para que
nunca queden desincronizadas del historial real.
"""
from collections import defaultdict
from datetime import datetime


def calcular_estadisticas_por_deudor(historial: list[dict]) -> list[dict]:
    agregados = defaultdict(lambda: {
        "nombre_completo": "", "total_intentos": 0, "exitosos": 0, "fallidos": 0,
        "intentos_email": 0, "intentos_whatsapp": 0, "intentos_sms": 0,
        "primer_contacto": None, "ultimo_contacto": None,
        "monto_adeudado_actual": 0,
    })

    for r in historial:
        idc = r["id_cliente"]
        a = agregados[idc]
        a["nombre_completo"] = r["nombre_completo"]
        a["total_intentos"] += 1
        exito = str(r.get("exito", "")).strip().lower() in ("true", "1", "si", "sí")
        a["exitosos" if exito else "fallidos"] += 1
        canal = str(r.get("canal", "")).lower()
        if canal in ("email", "whatsapp", "sms"):
            a[f"intentos_{canal}"] += 1
        fecha = r.get("fecha_hora", "")
        if fecha:
            if a["primer_contacto"] is None or fecha < a["primer_contacto"]:
                a["primer_contacto"] = fecha
            if a["ultimo_contacto"] is None or fecha > a["ultimo_contacto"]:
                a["ultimo_contacto"] = fecha
        try:
            a["monto_adeudado_actual"] = float(r.get("monto_adeudado", 0) or 0)
        except (TypeError, ValueError):
            pass

    filas = []
    for idc, a in agregados.items():
        estado = "sin intentos" if a["total_intentos"] == 0 else (
            "totalmente notificado" if a["fallidos"] == 0 else "con fallos pendientes"
        )
        filas.append({
            "id_cliente": idc,
            "nombre_completo": a["nombre_completo"],
            "total_intentos": a["total_intentos"],
            "exitosos": a["exitosos"],
            "fallidos": a["fallidos"],
            "intentos_email": a["intentos_email"],
            "intentos_whatsapp": a["intentos_whatsapp"],
            "intentos_sms": a["intentos_sms"],
            "primer_contacto": a["primer_contacto"] or "",
            "ultimo_contacto": a["ultimo_contacto"] or "",
            "estado_actual": estado,
            "monto_adeudado_actual": a["monto_adeudado_actual"],
        })
    return sorted(filas, key=lambda f: f["id_cliente"])


def _agregar_periodo(historial: list[dict], clave_periodo_fn) -> list[dict]:
    agregados = defaultdict(lambda: {
        "deudores": set(), "total": 0, "exitosas": 0, "fallidas": 0,
        "email": 0, "whatsapp": 0, "sms": 0,
        "leve": 0, "media": 0, "critica": 0, "monto": 0.0,
    })

    for r in historial:
        periodo = clave_periodo_fn(r)
        if periodo is None:
            continue
        a = agregados[periodo]
        a["deudores"].add(r["id_cliente"])
        a["total"] += 1
        exito = str(r.get("exito", "")).strip().lower() in ("true", "1", "si", "sí")
        a["exitosas" if exito else "fallidas"] += 1
        canal = str(r.get("canal", "")).lower()
        if canal in ("email", "whatsapp", "sms"):
            a[canal] += 1
        segmento = str(r.get("segmento", "")).lower()
        if segmento in ("leve", "media", "critica"):
            a[segmento] += 1
        try:
            a["monto"] += float(r.get("monto_adeudado", 0) or 0)
        except (TypeError, ValueError):
            pass

    filas = []
    for periodo, a in sorted(agregados.items()):
        tasa = round((a["exitosas"] / a["total"]) * 100, 1) if a["total"] else 0.0
        filas.append({
            "periodo": periodo,
            "total_deudores_gestionados": len(a["deudores"]),
            "total_notificaciones": a["total"],
            "exitosas": a["exitosas"],
            "fallidas": a["fallidas"],
            "tasa_exito_pct": tasa,
            "por_email": a["email"],
            "por_whatsapp": a["whatsapp"],
            "por_sms": a["sms"],
            "leve": a["leve"],
            "media": a["media"],
            "critica": a["critica"],
            "monto_total_cartera_gestionada": round(a["monto"], 2),
        })
    return filas


def calcular_resumen_semanal(historial: list[dict]) -> list[dict]:
    return _agregar_periodo(historial, lambda r: r.get("semana_iso") or None)


def calcular_resumen_mensual(historial: list[dict]) -> list[dict]:
    return _agregar_periodo(historial, lambda r: r.get("anio_mes") or None)


def semana_iso_de(fecha: datetime) -> str:
    iso = fecha.isocalendar()  # (anio, semana, dia)
    return f"{iso[0]}-W{iso[1]:02d}"


def anio_mes_de(fecha: datetime) -> str:
    return fecha.strftime("%Y-%m")
