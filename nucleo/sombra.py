"""Cartera sombra: seguimiento simulado de ideas con su regla de salida definida desde el primer día.

Las posiciones se definen en bot/config.py (SOMBRA). Aquí se define el tipo `Sombra` y se evalúan sobre
los cierres diarios (en euros si llevan divisa): estado, rentabilidad neta de costes, máximo alcanzado y
motivo/fecha de salida.
Uso en local:  python bot/informe.py --sombra
"""
import html
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Sombra:
    """Posición simulada («cartera sombra»): se sigue sin dinero real, con su regla de salida desde el primer día.

    La entrada se simula al cierre de `entrada`. La salida se ejecuta en la sesión siguiente a la primera
    señal de: `salida` (condición de indicadores.py que, al cumplirse, manda salir), `senal` (como la
    estrategia de una posición real: se sale en el primer cruce a la baja de la condición tras la entrada),
    `caida_max` (caída desde el máximo alcanzado desde la entrada, 0,15 = 15 %), `stop` (caída desde el PRECIO
    DE ENTRADA, 0,12 = 12 %; no sube con el precio) o `plazo` (sesiones).
    Hace falta al menos una. `coste` es OBLIGATORIO: coste de ida y vuelta (comisión, cambio de divisa y
    diferencial) en tanto por uno; sácalo de nucleo/costes.py / control/perfil.md, no lo estimes a ojo.
    """
    nombre: str
    ticker: str
    entrada: str                     # "AAAA-MM-DD"
    divisa: str | None = None
    tesis: str = ""
    salida: object = None
    senal: object = None
    caida_max: float | None = None
    stop: float | None = None        # caída desde el precio de entrada (tope de pérdida fijo)
    plazo: int | None = None
    coste: float | None = None


def evaluar(s: Sombra, precio: pd.Series, retraso=1):
    """Simula la posición `s` sobre la serie `precio`. La salida se ejecuta `retraso` sesiones después."""
    if not (s.salida or s.senal or s.caida_max or s.stop or s.plazo):
        raise ValueError(f"{s.nombre}: toda posición necesita al menos una condición de salida")
    if s.coste is None:
        raise ValueError(f"{s.nombre}: indica el coste de ida y vuelta (ver nucleo/costes.py y control/perfil.md, «Comisiones»)")
    desde = precio[precio.index >= pd.Timestamp(s.entrada)]
    if desde.empty:
        return {"nombre": s.nombre, "estado": "pendiente"}
    cond = s.salida.serie(precio) if s.salida else None
    if s.senal:
        reg = s.senal.serie(precio)
        cruce_baja = reg.shift(1, fill_value=False) & ~reg  # primer día en que la condición deja de cumplirse
    else:
        cruce_baja = None
    p0, maximo, motivo, i_salida = desde.iloc[0], desde.iloc[0], None, None
    for i, (fecha, valor) in enumerate(desde.items()):
        maximo = max(maximo, valor)
        if i == 0:
            continue
        if s.caida_max and valor / maximo - 1 <= -s.caida_max:
            motivo = f"cayó un {s.caida_max:.0%} desde su máximo"
        elif s.stop and valor / p0 - 1 <= -s.stop:
            motivo = f"cayó un {s.stop:.0%} desde su precio de entrada"
        elif cond is not None and fecha in cond.index and bool(cond.loc[fecha]):
            motivo = s.salida.describir(True)
        elif cruce_baja is not None and fecha in cruce_baja.index and bool(cruce_baja.loc[fecha]):
            motivo = s.senal.describir(False)
        elif s.plazo and i >= s.plazo:
            motivo = f"se cumplió el plazo de {s.plazo} sesiones"
        if motivo:
            i_salida = i
            break
    n = len(desde)
    cerrada = i_salida is not None
    j = min(i_salida + retraso, n - 1) if cerrada else n - 1
    ejecutada = (not cerrada) or (i_salida + retraso <= n - 1)  # ¿ya hubo sesión para ejecutar la salida?
    p1 = desde.iloc[j]
    bruto = p1 / p0 - 1
    return {
        "nombre": s.nombre, "estado": "cerrada" if (cerrada and ejecutada) else ("salida pendiente" if cerrada else "abierta"),
        "entrada": desde.index[0].date(), "p0": p0, "ult": desde.iloc[-1], "ultima": desde.index[-1].date(),
        "bruto": bruto, "neto": bruto - s.coste,
        "pico": maximo / p0 - 1, "desde_pico": desde.iloc[-1] / maximo - 1,
        "motivo": motivo, "senal": desde.index[i_salida].date() if cerrada else None,
        "salida": desde.index[j].date() if cerrada else None, "sesiones": j,
    }


def _pc(x):
    return f"{x * 100:+.1f}".replace(".", ",") + " %"


def linea(r):
    if r["estado"] == "pendiente":
        return f"{r['nombre']}: aún no ha llegado la fecha de entrada"
    base = f"{r['nombre']}: {_pc(r['neto'])} neto ({r['sesiones']} sesiones)"
    if r["estado"] == "abierta":
        return base + f" · abierta · pico {_pc(r['pico'])}, {_pc(r['desde_pico'])} desde el pico"
    return base + f" · {r['estado']} · salida {r['salida']:%d/%m/%Y}: {r['motivo']}"


def bloque(posiciones, fuente):
    """Texto HTML para el informe semanal; `fuente(ticker, divisa)` devuelve los cierres."""
    filas = [linea(evaluar(s, fuente(s.ticker, s.divisa))) for s in posiciones]
    if not filas:
        return None
    return "🕶️ <b>Cartera sombra</b>\n" + "\n".join(html.escape(f) for f in filas)
