"""Alertas diarias por Telegram según las reglas de config.py.

Para cada activo evalúa sus condiciones (nucleo/indicadores.py) sobre los cierres diarios y avisa de:
- cambios en las condiciones de seguimiento (🔔);
- señales de la estrategia de una posición: entrada, confirmación y salida (🟢/🔴);
- alarmas (🚨) y su fin (✅).
Los viernes manda un resumen del estado de todo.

Se ejecuta a diario tras el cierre de EE. UU. Solo evalúa velas cerradas:
en los activos que cotizan 24 h (cripto) descarta la vela del día en curso.

Demo sin Telegram:  python bot/alertas.py --demo   (imprime los avisos y el resumen; no escribe en registro/)
"""

import html
import sys
from datetime import date, datetime, timedelta, timezone

from config import ACTIVOS, DIA_RESUMEN, SEGUIMIENTO, TOKEN_AVISO_DIAS, TOKEN_CADUCA
from telegram import DEMO, comprobar_secretos, enviar

from nucleo import registro
from nucleo.datos import precios


def flecha(arriba):
    return "🟢 ↑" if arriba else "🔴 ↓"


def periodo_para(activo):
    """Histórico a descargar según la condición que más sesiones necesita."""
    conds = list((activo.seguimiento or SEGUIMIENTO).values()) + [c for c in (activo.senal, activo.alarma) if c]
    sesiones = max(c.sesiones for c in conds) + 30
    for periodo, n in (("2y", 450), ("5y", 1150), ("10y", 2400)):
        if sesiones <= n:
            return periodo
    return "max"


def evaluar(activo, hoy):
    """Estado actual del activo y cambios ocurridos en la última vela nueva."""
    p = precios(activo.ticker, activo.divisa, periodo=periodo_para(activo))
    if activo.continuo:
        p = p[p.index.date < hoy]  # la vela de hoy aún no ha cerrado
    # Vela nueva desde la ejecución anterior: hoy en bolsa, ayer en cripto.
    # En fines de semana y festivos de bolsa no hay vela nueva y no se avisa.
    esperada = hoy - timedelta(days=1) if activo.continuo else hoy
    nueva = p.index[-1].date() == esperada

    estado, senal, salida = None, None, None
    if activo.senal:
        regla = activo.senal.serie(p)
        cambio = nueva and regla.iloc[-1] != regla.iloc[-2]
        sube = bool(regla.iloc[-1])
        if activo.en_cartera:
            # Posición real: DENTRO desde la entrada hasta que la condición deja de cumplirse por primera vez.
            baja = regla.shift(1, fill_value=False) & ~regla
            tras_entrada = regla.index.date > date.fromisoformat(activo.en_cartera)
            salidas = regla.index[baja.values & tras_entrada]
            salida = salidas[0].date() if len(salidas) else None
            estado = "dentro" if salida is None else "salida"
        else:
            estado = "sin posición"
        if cambio:
            if sube:
                senal = "confirmacion" if estado == "dentro" else "entrada"
            elif salida == p.index[-1].date():
                senal = "salida"

    tendencias, avisos = {}, []
    for nombre, cond in (activo.seguimiento or SEGUIMIENTO).items():
        s = cond.serie(p)
        tendencias[nombre] = bool(s.iloc[-1])
        ya_avisado = senal is not None and cond == activo.senal  # el mismo cambio ya va como señal
        if nueva and s.iloc[-1] != s.iloc[-2] and not ya_avisado:
            avisos.append((nombre, cond, bool(s.iloc[-1])))
    alarma, alarma_cambio = None, None
    # Si la alarma es de una posición real (en_cartera), solo vale mientras la posición sigue DENTRO.
    if activo.alarma and not (activo.en_cartera and estado == "salida"):
        s = activo.alarma.serie(p)
        alarma = bool(s.iloc[-1])
        if nueva and s.iloc[-1] != s.iloc[-2]:
            alarma_cambio = alarma
    return {"tendencias": tendencias, "estado": estado, "salida": salida, "avisos": avisos, "senal": senal,
            "alarma": alarma, "alarma_cambio": alarma_cambio, "fecha": p.index[-1].date()}


DIAS_ATRASO = 5  # más sesiones sin vela nueva que fines de semana y festivos largos: algo falla en los datos


def datos_atrasados(estados, hoy):
    """Activos cuya última vela es demasiado antigua (Yahoo sin datos, ticker retirado…)."""
    return [(a.nombre, e["fecha"]) for a, e in estados if (hoy - e["fecha"]).days > DIAS_ATRASO]


def filas_registro(estados):
    """Eventos de hoy para registro/decisiones.csv, con la dirección que se espera del precio."""
    filas = []
    for activo, e in estados:
        base = {"fecha": e["fecha"].isoformat(), "origen": "alertas", "activo": activo.nombre,
                "ticker": activo.ticker, "divisa": activo.divisa or "", "relevante": ""}
        if e["alarma_cambio"] is not None:
            filas.append({**base, "tipo": "alarma" if e["alarma_cambio"] else "fin_alarma",
                          "direccion": -1 if e["alarma_cambio"] else 1,
                          "detalle": activo.alarma.describir(e["alarma_cambio"])})
        if e["senal"] is not None:
            sube = e["senal"] != "salida"
            filas.append({**base, "tipo": e["senal"], "direccion": 1 if sube else -1,
                          "detalle": activo.senal.describir(sube)})
        for nombre, cond, arriba in e["avisos"]:
            filas.append({**base, "tipo": "cambio_tendencia", "direccion": 1 if arriba else -1,
                          "detalle": f"{nombre}: {cond.describir(arriba)}"})
    return filas


def msg_resumen(estados, hoy):
    bloques = [f"📋 <b>Resumen</b> · {hoy:%d/%m/%Y}"]
    for activo, e in estados:
        cab = f"<b>{html.escape(activo.nombre)}</b>"
        if e["estado"] == "dentro":
            cab += "  ·  🟢 DENTRO"
        elif e["estado"] == "salida":
            cab += f"  ·  🔴 FUERA (salida el {e['salida']:%d/%m})"
        elif e["estado"] == "sin posición":
            cab += "  ·  ⚪ sin posición"
        lineas = [f"    {n}: {flecha(v)}" for n, v in e["tendencias"].items()]
        if e["alarma"]:
            lineas.append("    🚨 Alarma activa")
        bloques.append("\n".join([cab] + lineas))
    bolsa = [e["fecha"] for a, e in estados if not a.continuo]
    if bolsa:
        bloques.append(f"<i>Datos de bolsa hasta el {min(bolsa):%d/%m/%Y}</i>")
    return "\n\n".join(bloques)


def msg_avisos(estados):
    bloques = ["🔔 <b>Cambio de tendencia</b>"]
    for activo, e in estados:
        for nombre, cond, arriba in e["avisos"]:
            bloques.append(f"<b>{html.escape(activo.nombre)}</b> · {e['fecha']:%d/%m}\n"
                           f"{nombre}: {flecha(arriba)}\n{html.escape(cond.describir(arriba))}")
    return "\n\n".join(bloques) if len(bloques) > 1 else None


def msg_senal(activo, e):
    titulo, sube, nota = {
        "entrada": ("🟢 Señal de <b>ENTRADA</b>", True, ""),
        "confirmacion": ("🟢 <b>Tendencia confirmada</b>", True,
                         "\n\nA partir de ahora, la salida es cuando la condición deje de cumplirse."),
        "salida": ("🔴 Señal de <b>SALIDA</b>", False,
                   "\n\nCuando vendas, actualiza la cartera y quita la fecha de entrada (y la alarma de salida previa) en config.py."),
    }[e["senal"]]
    detalle = html.escape(activo.senal.describir(sube))
    return (f"{titulo}\n\n<b>{html.escape(activo.nombre)}</b>\n{detalle}\n"
            f"Cierre del {e['fecha']:%d/%m/%Y}{nota}")


def msg_alarma(activo, e):
    nombre = f"<b>{html.escape(activo.nombre)}</b> · {e['fecha']:%d/%m/%Y}"
    detalle = html.escape(activo.alarma.describir(e["alarma_cambio"]))
    if e["alarma_cambio"]:
        nota = f"\n\n{activo.recordatorio}" if activo.recordatorio else ""
        return f"🚨 <b>Alarma</b>\n\n{nombre}\n{detalle}{nota}"
    return f"✅ <b>Fin de la alarma</b>\n\n{nombre}\n{detalle}"


def aviso_token(hoy, caduca=TOKEN_CADUCA, dias=TOKEN_AVISO_DIAS):
    """Recordatorio de renovar el token de GitHub que usa cron-job.org (None si aún no toca o no hay token)."""
    if not caduca:
        return None
    quedan = (date.fromisoformat(caduca) - hoy).days
    if quedan > dias:
        return None
    cuando = f"caduca en {quedan} días ({date.fromisoformat(caduca):%d/%m/%Y})" if quedan > 0 else "caduca hoy"
    return (f"🔑 <b>Renueva el token de GitHub</b>: {cuando}.\n"
            "Sin él, cron-job.org no puede lanzar el bot y dejarás de recibir mensajes sin aviso.\n"
            "1) GitHub → Settings → Developer settings → Fine-grained tokens → «Regenerate» (o uno nuevo: solo "
            "finanzas, Actions: Read and write).\n2) Pega el token en los tres trabajos de cron-job.org.\n"
            "3) Cambia TOKEN_CADUCA en bot/config.py.\n"
            "4) Revisa la cabecera X-GitHub-Api-Version de cron-job.org: la versión 2022-11-28 deja de "
            "funcionar el 10/03/2028; pon la vigente (docs.github.com → REST API → API versions).")


def main():
    comprobar_secretos()
    hoy = datetime.now(timezone.utc).date()

    estados, errores = [], []
    for activo in ACTIVOS:
        try:
            estados.append((activo, evaluar(activo, hoy)))
        except Exception as e:
            errores.append(f"{activo.nombre}: {e}")

    for activo, e in estados:
        if e["alarma_cambio"] is not None:
            enviar(msg_alarma(activo, e))
        if e["senal"] is not None:
            enviar(msg_senal(activo, e))
    if (avisos := msg_avisos(estados)):
        enviar(avisos)
    if estados and (DEMO or "--resumen" in sys.argv or hoy.weekday() == DIA_RESUMEN):
        enviar(msg_resumen(estados, hoy))
    if (token := aviso_token(hoy)):
        enviar(token)
    if (atrasados := datos_atrasados(estados, hoy)):
        enviar("⚠️ <b>Datos desactualizados</b>\n\n" + html.escape("\n".join(
            f"{n}: última vela del {f:%d/%m/%Y}" for n, f in atrasados)) + "\n\nLas alertas de estos activos no son fiables.")
    try:
        if not DEMO:
            registro.registrar(filas_registro(estados))
    except Exception as e:  # el registro nunca debe impedir los avisos
        errores.append(f"Registro: {e}")
    if errores:
        enviar("❌ <b>Error en las alertas</b>\n\n" + html.escape("\n".join(errores)))
        sys.exit(1)  # marca la ejecución como fallida en GitHub Actions


if __name__ == "__main__":
    main()
