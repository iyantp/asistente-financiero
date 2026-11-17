"""Informe semanal de mercado (lunes): variables de estado, qué ha movido la cartera y eventos.

Solo cálculo, sin IA:
- Variables: cambio de la última semana completa, z-score frente a su historial
  y percentil del nivel en los últimos 5 años.
- Cartera: rentabilidad semanal de cada posición (por su aproximación en euros) y
  parte explicada por las variables con la matriz de analisis/exposiciones.csv.
- Eventos de los próximos 7 días según control/calendario.csv.

Demo sin Telegram:  python bot/informe.py --demo   (imprime el informe por pantalla)
"""
import html
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from config import ACTIVOS as REGLAS
from config import SOMBRA
from telegram import comprobar_secretos, enviar

from nucleo import limites, sombra
from nucleo.datos import precios, variable
from nucleo.rutas import CALENDARIO, CARTERA_CSV, MATRIZ
from nucleo.universo import ACTIVOS, CORTO, FACTORES, INICIO, VARIABLES, coherencia, leer_matriz

UMBRAL_Z = 2.0


CORTO_VAR = {"Tipos reales 10a": "Tipos reales", "Inflación esperada 10a": "Inflación esperada",
             "Tipo 2a": "Tipo 2a", "Dólar (EUR/USD)": "Euro/dólar", "Dólar amplio": "Dólar amplio", "Estrés de crédito": "Estrés de crédito",
             "Crecimiento (cobre)": "Cobre", "Petróleo (Brent)": "Petróleo", "VIX": "VIX"}
PCT_EXTREMO = 90


def num(x, dec=1, signo=True):
    return (f"{x:+.{dec}f}" if signo else f"{x:.{dec}f}").replace(".", ",")


def cambios_semanales(nivel, tipo, hasta):
    sem = nivel[nivel.index.date <= hasta].resample("W-FRI").last()
    return (sem.diff() if tipo == "dif" else np.log(sem).diff()), sem


def datos_variables(hasta):
    """Por variable: cambio de la semana, z-score frente a su historial y percentil del nivel en 5 años."""
    filas = {}
    for nombre, (fuente, codigo, tipo, _) in VARIABLES.items():
        try:  # una serie caída no debe tumbar el resto del informe
            cambio, nivel = cambios_semanales(variable(fuente, codigo), tipo, hasta)
        except Exception as e:
            filas[nombre] = {"error": str(e)[:60]}
            continue
        if cambio.dropna().index[-1].date() != hasta:  # FRED publica con retraso: no usar la semana anterior
            filas[nombre] = {"error": f"último dato de la semana del {cambio.dropna().index[-1]:%d/%m}"}
            continue
        hist = cambio.loc[INICIO:].dropna()
        cinco = nivel.dropna().iloc[-260:]
        filas[nombre] = {
            "cambio": hist.iloc[-1], "tipo": tipo,
            "z": (hist.iloc[-1] - hist.mean()) / hist.std(),
            "pct": (cinco <= cinco.iloc[-1]).mean() * 100,
        }
    return filas


def bloque_variables(filas):
    lineas, tranquilas = [], []
    sin_datos = [f"{CORTO_VAR.get(n, n)} ({f['error']})" for n, f in filas.items() if "error" in f]
    for nombre, f in filas.items():
        if "error" in f:
            continue
        corto = CORTO_VAR.get(nombre, nombre)
        valor = f"{num(f['cambio'], 2)} pp" if f["tipo"] == "dif" else f"{num(f['cambio'] * 100)} %"
        if abs(f["z"]) > UMBRAL_Z:
            lineas.append(f"⚠️ <b>{corto}</b> {valor} · movimiento anómalo")
        elif f["pct"] >= PCT_EXTREMO:
            lineas.append(f"🔺 <b>{corto}</b> en zona alta de 5 años (p{f['pct']:.0f})")
        elif f["pct"] <= 100 - PCT_EXTREMO:
            lineas.append(f"🔻 <b>{corto}</b> en zona baja de 5 años (p{f['pct']:.0f})")
        else:
            tranquilas.append(corto)
    if tranquilas:
        lineas.append(f"<i>Sin cambios relevantes: {', '.join(tranquilas)}</i>")
    if sin_datos:
        lineas.append(f"⚠️ <i>Sin dato de esta semana (no entran en el cálculo): {'; '.join(sin_datos)}</i>")
    return lineas


def bloque_cartera(hasta, filas):
    exp = leer_matriz(MATRIZ)
    betas = exp.pivot(index="activo", columns="variable", values="parcial_actual")  # atribución conjunta: exposición directa
    pesos = pd.read_csv(CARTERA_CSV).set_index("activo")["peso"]
    z = pd.Series({n: f["z"] for n, f in filas.items() if "z" in f}).reindex(betas.columns).fillna(0.0)

    posiciones, total_r, total_e, peso_ok = [], 0.0, 0.0, 0.0
    contrib = pd.Series(0.0, index=betas.columns)
    for activo, (ticker, divisa) in ACTIVOS.items():
        p = precios(ticker, divisa, periodo="1y")
        sem = p[p.index.date <= hasta].resample("W-FRI").last()
        r = np.log(sem).diff().iloc[-1]
        if activo not in betas.index or np.isnan(r):
            continue
        aporte = betas.loc[activo] * z
        posiciones.append((CORTO.get(activo, activo), r, aporte.sum()))
        w = pesos.get(activo, 0) / 100
        total_r, total_e, peso_ok = total_r + w * r, total_e + w * aporte.sum(), peso_ok + w
        contrib += w * aporte
    if peso_ok:
        total_r, total_e, contrib = total_r / peso_ok, total_e / peso_ok, contrib / peso_ok

    principales = [(v, c) for v, c in contrib.items() if abs(c) >= 0.001]
    principales.sort(key=lambda x: -abs(x[1]))
    texto = f"Las variables explican <b>{num(total_e * 100)} %</b>"
    if principales:
        detalle = [f"{CORTO_VAR.get(v, v).lower()} ({num(c * 100)} %)" for v, c in principales[:2]]
        texto += ", sobre todo " + " y ".join(detalle)
    texto += "; el resto es propio de cada activo."

    posiciones.sort(key=lambda x: -x[1])
    ancho = max(len(n) for n, *_ in posiciones)
    tabla = "\n".join(f"{n:<{ancho}}  {num(r * 100):>6} %   {num(e * 100):>6} %" for n, r, e in posiciones)
    cabecera = f"{'':<{ancho}}  {'semana':>8}   {'variables':>8}"
    return (f"💼 <b>Tu cartera: {num(total_r * 100)} %</b>\n{texto}\n\n"
            f"<pre>{html.escape(cabecera)}\n{html.escape(tabla)}</pre>")


def bloque_factores(hasta):
    """Movimiento semanal de los factores sectoriales, agrupado por posición (⚠️ si es anómalo)."""
    cache, grupos = {}, {}
    for activo, factores in FACTORES.items():
        partes = []
        for nombre, ticker in factores.items():
            if ticker not in cache:
                p = precios(ticker, periodo="max")
                sem = np.log(p[p.index.date <= hasta].resample("W-FRI").last()).diff().loc[INICIO:].dropna()
                cache[ticker] = (sem.iloc[-1], (sem.iloc[-1] - sem.mean()) / sem.std())
            r, z = cache[ticker]
            marca = "⚠️ " if abs(z) > UMBRAL_Z else ""
            partes.append(f"{marca}{nombre} {num(r * 100)} %")
        grupos.setdefault(" · ".join(partes), []).append(CORTO.get(activo, activo))
    return [f"<b>{', '.join(activos)}</b> ← {texto}" for texto, activos in grupos.items()]


def bloque_eventos(hoy):
    cal = pd.read_csv(CALENDARIO, parse_dates=["fecha"])
    prox = cal[(cal.fecha.dt.date >= hoy) & (cal.fecha.dt.date <= hoy + timedelta(days=7))]
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    filas = [f"· {dias[f.weekday()]} {f:%d/%m} · {html.escape(e)}" for f, e in zip(prox.fecha, prox.evento)]
    if cal.fecha.max().date() < hoy + timedelta(days=60):
        filas.append("⚠️ <i>El calendario se acaba pronto: añadir fechas en control/calendario.csv</i>")
    return filas or ["<i>Sin eventos marcados</i>"]


def main():
    comprobar_secretos()
    hoy = datetime.now(timezone.utc).date()
    viernes = hoy - timedelta(days=(hoy.weekday() - 4) % 7)  # última semana completa
    partes = [f"📊 <b>Informe semanal</b> · {viernes - timedelta(days=4):%d/%m} – {viernes:%d/%m}"]
    errores = []
    try:
        filas = datos_variables(viernes)
        partes.append("🧭 <b>Variables</b>\n" + "\n".join(bloque_variables(filas)))
        partes.append(bloque_cartera(viernes, filas))
        partes.append("🏭 <b>Factores sectoriales</b>\n" + "\n".join(bloque_factores(viernes)))
    except Exception as e:
        errores.append(f"Datos: {e}")
    try:
        partes.append(limites.bloque())
        if SOMBRA and (b := sombra.bloque(SOMBRA, lambda t, d: precios(t, d, periodo="max"))):
            partes.append(b)
    except Exception as e:
        errores.append(f"Límites o sombra: {e}")
    try:
        if (problemas := coherencia(REGLAS, leer_matriz(MATRIZ))):
            partes.append("🧩 <b>Coherencia de la cartera</b>\n" + "\n".join("· " + html.escape(p) for p in problemas))
    except Exception as e:
        errores.append(f"Coherencia: {e}")
    try:
        partes.append("📅 <b>Esta semana</b>\n" + "\n".join(bloque_eventos(hoy)))
    except Exception as e:
        errores.append(f"Calendario: {e}")
    if errores:
        partes.append("❌ " + html.escape("; ".join(errores)))
    enviar("\n\n".join(partes))
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    if "--sombra" in sys.argv:  # en local: solo la cartera sombra, por pantalla
        for s in SOMBRA:
            print(sombra.linea(sombra.evaluar(s, precios(s.ticker, s.divisa, periodo="max"))))
        if not SOMBRA:
            print("config.SOMBRA está vacío: añade ideas para seguirlas en simulado.")
    else:
        main()
