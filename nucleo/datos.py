"""Datos y cálculos comunes: descarga de precios, medias móviles y posición dentro/fuera.

Lo usan el bot (bot/alertas.py) y los cuadernos de analisis/, así que las alertas
y el análisis histórico aplican exactamente las mismas reglas.

Cada descarga se guarda también en datos/<ticker>_<periodo>.csv (carpeta ignorada
por git), para poder analizar los precios sin volver a descargarlos.
"""
import os
import re
import sys

import pandas as pd

from nucleo.rutas import DATOS

CARPETA_DATOS = DATOS
# FINANZAS_SIN_RED=1 lee siempre las copias de datos/ (pruebas sin conexión). Sin la variable, se
# descarga y, si la descarga falla, se usa la copia local avisando por la salida de errores.
SIN_RED = os.environ.get("FINANZAS_SIN_RED") == "1"


def alinear_fx(s):
    """Alinea un tipo de cambio de Yahoo (desde ~2011) con el cierre de la bolsa de EE. UU. del mismo día.

    Desde ~2011 Yahoo fecha cada vela diaria de divisas al inicio del día en Londres: el valor con fecha t
    es, en la práctica, el cambio de las 00:00 de t, es decir, el de la noche de t-1. Comprobado con FRED
    DEXUSEU (mediodía de Nueva York): correlación diaria de los cambios 0,19 en la misma fecha y 0,77 con
    la vela siguiente (la subida del dólar del 06/11/2024 aparece en la vela del 07/11). Antes de ~2010 no
    pasaba (correlación 0,8 en la misma fecha), así que esta función solo vale para datos recientes: el
    histórico se toma de FRED (ver cambio_eurusd). Al valor de t se le asigna el de la vela siguiente
    (00:00 de t+1, 2-3 h después del cierre de Nueva York); la última vela se queda como está (en vivo
    es el precio más reciente).
    """
    s = s.dropna()
    alineada = s.shift(-1)
    if len(s):
        alineada.iloc[-1] = s.iloc[-1]
    return alineada


def _copia(ticker, periodo):
    """Cierres guardados en datos/ (la copia del periodo, o la de 'max' recortada al periodo)."""
    exacta, maxima = CARPETA_DATOS / f"{ticker}_{periodo}.csv", CARPETA_DATOS / f"{ticker}_max.csv"
    ruta = exacta if exacta.exists() else maxima
    if not ruta.exists():
        raise FileNotFoundError(f"sin copia local de {ticker} en {CARPETA_DATOS}")
    s = pd.read_csv(ruta, index_col=0, parse_dates=True).iloc[:, 0].dropna()
    m = re.fullmatch(r"(\d+)(y|mo|d)", periodo)
    if ruta == maxima and m:
        n, u = int(m.group(1)), m.group(2)
        delta = {"y": pd.DateOffset(years=n), "mo": pd.DateOffset(months=n), "d": pd.DateOffset(days=n)}[u]
        s = s[s.index >= s.index[-1] - delta]
    return s


def _descargar(ticker, periodo):
    import yfinance as yf  # importación diferida: los cuadernos y pruebas pueden trabajar sin ella
    df = yf.download(ticker, period=periodo, auto_adjust=True, progress=False)
    cierres = df["Close"].squeeze().dropna()
    if not cierres.empty:
        try:
            CARPETA_DATOS.mkdir(exist_ok=True)
            tabla = cierres.rename("cierre").to_frame()
            if "Volume" in df:  # el volumen va en la 2.ª columna: las lecturas de cierres (iloc[:, 0]) no cambian
                tabla["volumen"] = df["Volume"].squeeze().reindex(tabla.index)
            tabla.to_csv(CARPETA_DATOS / f"{ticker}_{periodo}.csv")
        except OSError:
            pass  # guardar es opcional: nunca debe impedir el cálculo
    return cierres


def volumen(ticker, periodo="max"):
    """Volumen diario guardado en datos/ (existe solo en copias descargadas con volumen); vacío si no hay."""
    for ruta in (CARPETA_DATOS / f"{ticker}_{periodo}.csv", CARPETA_DATOS / f"{ticker}_max.csv"):
        if ruta.exists():
            t = pd.read_csv(ruta, index_col=0, parse_dates=True)
            if "volumen" in t:
                return t["volumen"].dropna()
    return pd.Series(dtype=float, name="volumen")


def gld_spdr():
    """GLD diario de SPDR (archivo oficial descargado a mano): cierre en $, volumen y toneladas en custodia."""
    return pd.read_csv(CARPETA_DATOS / "GLD_spdr.csv", index_col=0, parse_dates=True)


def _cierres(ticker, periodo):
    """Cierres diarios en bruto (descarga o copia local); las divisas (=X) se alinean con alinear_fx."""
    if SIN_RED:
        cierres = _copia(ticker, periodo)
    else:
        try:
            cierres = _descargar(ticker, periodo)
            if cierres.empty:
                raise RuntimeError("descarga vacía")
        except Exception as e:
            try:
                cierres = _copia(ticker, periodo)
            except FileNotFoundError:
                raise RuntimeError(f"sin datos para {ticker}: {e}") from e
            print(f"Aviso: {ticker} sin descarga ({e}); uso la copia local hasta {cierres.index[-1]:%d/%m/%Y}",
                  file=sys.stderr)
    cierres.index = pd.DatetimeIndex(cierres.index).tz_localize(None)
    return cierres


def cambio_eurusd(periodo="max"):
    """Dólares por euro alineado con el cierre de EE. UU.: FRED DEXUSEU (mediodía de Nueva York, fechas
    coherentes en todo el histórico) y, para los últimos días que FRED aún no ha publicado (va con una
    semana de retraso), la vela de Yahoo alineada con alinear_fx. Sin FRED, solo Yahoo alineado."""
    yahoo = alinear_fx(_cierres("EURUSD=X", periodo))
    try:
        f = fred("DEXUSEU")
    except Exception as e:
        print(f"Aviso: sin FRED DEXUSEU ({e}); uso solo Yahoo alineado", file=sys.stderr)
        return yahoo
    f = f[f.index >= yahoo.index[0]] if periodo != "max" else f
    return pd.concat([f, yahoo[yahoo.index > f.index[-1]]]).rename("EURUSD")


def cambio(divisa, periodo="max"):
    """Tipo de cambio para pasar a euros (unidades de la divisa por euro), alineado con el cierre de EE. UU."""
    if divisa == "EURUSD=X":
        return cambio_eurusd(periodo)
    print(f"Aviso: {divisa} no tiene histórico alineado; uso Yahoo con alinear_fx", file=sys.stderr)
    return alinear_fx(_cierres(divisa, periodo))


def fred(codigo):
    """Serie diaria de FRED (sin clave). Se guarda en datos/; si falla la descarga, se usa la copia."""
    copia = CARPETA_DATOS / f"fred_{codigo}.csv"
    try:
        if SIN_RED:
            raise RuntimeError("modo sin red")
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={codigo}"
        s = pd.read_csv(url, na_values=".", index_col=0, parse_dates=True).iloc[:, 0]
        try:
            CARPETA_DATOS.mkdir(exist_ok=True)
            s.to_csv(copia)
        except OSError:
            pass
    except Exception:
        if not copia.exists():
            raise
        s = pd.read_csv(copia, index_col=0, parse_dates=True, na_values=".").iloc[:, 0]
    return s.dropna().rename(codigo)


def liquidez_eur():
    """Tipo anual de la liquidez en euros (tanto por uno), para lo que rinde estar fuera del mercado:
    euríbor a 3 meses mensual de la OCDE en FRED (IR3TIB01EZM156N), desde 1994. Aproxima un monetario."""
    return (fred("IR3TIB01EZM156N") / 100).rename("liquidez_eur")


def variable(fuente, codigo):
    """Nivel diario de una variable de estado (ver universo.py).

    El EUR/USD de FRED va con una semana de retraso: se completa con la cola de Yahoo alineada."""
    if fuente == "fred" and codigo == "DEXUSEU":
        return cambio_eurusd()
    return fred(codigo) if fuente == "fred" else precios(codigo, periodo="max")


def precios(ticker, divisa=None, periodo="2y"):
    """Cierres diarios ajustados (incluyen dividendos), convertidos a euros si se da `divisa` (con cambio()).

    Ojo: para un tipo de cambio pedido directamente (p. ej. precios("EURUSD=X")) devuelve la vela de Yahoo
    tal cual, fechada al inicio del día en Londres (ver alinear_fx)."""
    p = _cierres(ticker, periodo)
    if divisa:
        fx = cambio(divisa, periodo)
        fx = fx.reindex(p.index.union(fx.index)).ffill().reindex(p.index)
        p = (p / fx).dropna()
    if p.empty:
        raise RuntimeError(f"sin datos para {ticker}")
    return p


def medias(precio, condiciones):
    """Tabla con las SMA que usan las condiciones (una columna por nº de sesiones)."""
    ventanas = sorted({n for cond in condiciones for n in cond})
    return pd.DataFrame({n: precio.rolling(n).mean() for n in ventanas}).dropna()


def posicion(precio, condiciones):
    """Serie booleana por sesión: True = dentro, False = fuera."""
    sma = medias(precio, condiciones)
    dentro = pd.Series(True, index=sma.index)
    for a, b in condiciones:
        dentro &= sma[a] > sma[b]
    return dentro


def etiqueta(n):
    return "precio" if n == 1 else f"SMA{n}"
