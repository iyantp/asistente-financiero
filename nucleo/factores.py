"""Modelo de factores de riesgo: construcción y ortogonalización de los factores (pasos 1 y 2).

Los factores se definen en control/factores.toml. Aquí:
- `factores()` construye la serie diaria de cada factor general (rentabilidad o cambio al cierre de EE. UU.);
- `especificos()` construye los de una posición concreta, limpios de los generales;
- `ortogonalizar()` los limpia en orden: el primero queda igual y cada siguiente se queda solo con la parte que
  no explican los anteriores (Gram-Schmidt con regresiones). Devuelve también los coeficientes de esa limpieza y
  qué fracción de cada factor es «nueva», para ver qué aporta cada uno;
- `rentabilidades_activos()` da las rentabilidades diarias de la cartera, en la moneda de cada activo o ya
  convertidas a la del inversor; `conversion_divisa()` da el término exacto de la conversión.

Conversión ([parametros] conversion en control/factores.toml):
  "exacta"    el modelo se estima en la moneda de cada activo y la conversión se suma después, sin estimarla:
              r_inversor = r_local − Δlog(tipo de cambio)   (tipo de cambio = unidades de la divisa por unidad tuya)
  "estimada"  se estima sobre rentabilidades ya convertidas, con la divisa como un factor más.

Guía de uso y decisiones: analisis/factores.ipynb.
"""
import sys

import numpy as np
import pandas as pd

from nucleo.datos import _cierres, alinear_fx, cambio, cambio_eurusd, precios, variable
from nucleo.rutas import FACTORES_TOML
from nucleo.universo import ACTIVOS, CESTAS

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

TIPOS = ("precio", "diferencial", "nivel", "cesta", "eurusd")


def _leer(ruta=FACTORES_TOML):
    with open(ruta, "rb") as f:
        return tomllib.load(f)


def leer_definiciones(ruta=FACTORES_TOML):
    """{nombre: definición} en el orden del archivo (que es el orden de ortogonalización)."""
    return _leer(ruta).get("factores", {})


def parametros(ruta=FACTORES_TOML):
    return _leer(ruta).get("parametros", {})


def inicio(ruta=FACTORES_TOML):
    """Inicio de la muestra ([parametros] inicio)."""
    return parametros(ruta).get("inicio", "2015-01-01")


def conversion(ruta=FACTORES_TOML):
    """"exacta" o "estimada" ([parametros] conversion)."""
    c = parametros(ruta).get("conversion", "exacta")
    if c not in ("exacta", "estimada"):
        raise ValueError(f"conversion = {c!r} no válida (\"exacta\" o \"estimada\")")
    return c


def _log_rent(ticker):
    return np.log(precios(ticker, periodo="max")).diff()


def serie_factor(d):
    """Serie diaria de un factor a partir de su definición (ver control/factores.toml)."""
    tipo = d.get("tipo")
    if tipo == "precio":
        s = _log_rent(d["ticker"])
    elif tipo == "diferencial":
        s = _log_rent(d["largo"]) - _log_rent(d["corto"])
    elif tipo == "nivel":
        s = variable(d["fuente"], d["codigo"]).diff()
    elif tipo == "cesta":
        pesos = CESTAS[d["cesta"]]
        partes = {t: np.log(alinear_fx(_cierres(t, "max")) if t.endswith("=X") else _cierres(t, "max")).diff()
                  for t in pesos}
        s = sum(w * partes[t] for t, w in pesos.items())
    elif tipo == "eurusd":
        s = np.log(cambio_eurusd("max")).diff()
    else:
        raise ValueError(f"tipo {tipo!r} no válido (válidos: {', '.join(TIPOS)})")
    s = (d.get("signo", 1) * s).dropna()
    return s.loc[d["desde"]:] if d.get("desde") else s


def factores(definiciones=None, todos=False, alternativas=False):
    """(DataFrame diario con un factor por columna, {factor: error o aviso}).

    Solo los de `usar = true`, salvo `todos=True`. Columnas en el orden del archivo. Con `alternativas=True`
    (solo para análisis), un factor sin datos usa su `alternativa` y queda anotado en el segundo valor."""
    definiciones = leer_definiciones() if definiciones is None else definiciones
    series, avisos = {}, {}
    for nombre, d in definiciones.items():
        if not (todos or d.get("usar", True)):
            continue
        try:
            series[nombre] = serie_factor(d)
        except Exception as e:  # noqa: BLE001 (un factor sin datos no debe tumbar el resto)
            if alternativas and d.get("alternativa"):
                try:
                    series[nombre] = serie_factor(d["alternativa"])
                    avisos[nombre] = f"sin datos ({str(e)[:60]}); se usa la alternativa {d['alternativa']}"
                    continue
                except Exception as e2:  # noqa: BLE001
                    e = e2
            avisos[nombre] = str(e)[:120]
    return pd.DataFrame(series), avisos


def leer_especificos(ruta=FACTORES_TOML):
    """{posición: {factor: definición}} de [especificos] (factores que solo se usan para esa posición)."""
    return _leer(ruta).get("especificos", {})


def especificos(activo, generales, definiciones=None, alternativas=False):
    """Factores específicos de `activo`, limpios de los generales: (DataFrame, avisos).

    Se ortogonalizan detrás de todos los generales (y entre sí, en su orden), así que solo recogen lo que los
    generales no explican. Sin específicos, DataFrame vacío."""
    definiciones = leer_especificos().get(activo, {}) if definiciones is None else definiciones
    if not definiciones:
        return pd.DataFrame(index=generales.index), {}
    E, avisos = factores(definiciones, todos=True, alternativas=alternativas)
    if E.empty:
        return E, avisos
    Fo, _, _ = ortogonalizar(pd.concat([generales, E], axis=1, sort=True), list(generales.columns) + list(E.columns))
    return Fo[list(E.columns)], avisos


def problemas_especificos(activos=None, ruta=FACTORES_TOML):
    """Posiciones de [especificos] que no están en control/cartera.csv. Lista vacía = todo bien."""
    activos = ACTIVOS if activos is None else activos
    return [f"factores.toml: [especificos] tiene {a!r}, que no está en cartera.csv"
            for a in leer_especificos(ruta) if a not in activos]


def rentabilidades_activos(activos=None, moneda="inversor"):
    """Rentabilidades logarítmicas diarias de los activos: moneda="local" (la de cada activo) o "inversor"
    (convertidas con la `divisa` de control/cartera.csv; igual que la local si el activo no lleva divisa)."""
    activos = ACTIVOS if activos is None else activos
    conv = moneda == "inversor"
    return pd.DataFrame({n: np.log(precios(t, d if conv else None, periodo="max")).diff()
                         for n, (t, d) in activos.items()})


def conversion_divisa(activos=None):
    """Término exacto de la conversión por activo: −Δlog(tipo de cambio) en las fechas de cotización del activo,
    de modo que r_inversor = r_local + este término (cero si el activo no lleva divisa)."""
    activos = ACTIVOS if activos is None else activos
    columnas = {}
    for n, (t, d) in activos.items():
        p = precios(t, periodo="max")
        if not d:
            columnas[n] = pd.Series(0.0, index=p.index)
            continue
        fx = cambio(d, "max")
        fx = fx.reindex(p.index.union(fx.index)).ffill().reindex(p.index)   # igual que nucleo.datos.precios
        columnas[n] = -np.log(fx).diff()
    return pd.DataFrame(columnas)


def ortogonalizar(F, orden=None):
    """Ortogonaliza los factores en `orden` (por defecto, el de las columnas) sobre las fechas con todos los datos.

    f*_1 = f_1;  f*_k = f_k − (a_k + Σ_{j<k} c_kj · f*_j), con los c_kj de la regresión de f_k sobre f*_1..f*_{k-1}.
    Devuelve:
      Fo         factores ortogonalizados (correlación cero entre sí en la muestra)
      C          coeficientes c_kj: cuánto de cada factor anterior había dentro de f_k
      propia     fracción de la varianza de f_k que es nueva, var(f*_k)/var(f_k) = 1 − R²_k
    """
    orden = list(F.columns) if orden is None else list(orden)
    X = F[orden].dropna()
    Fo = pd.DataFrame(index=X.index)
    C = pd.DataFrame(0.0, index=orden, columns=orden)
    propia = {}
    for k in orden:
        y = X[k] - X[k].mean()
        if Fo.shape[1]:
            Z = Fo - Fo.mean()
            c, *_ = np.linalg.lstsq(Z.values, y.values, rcond=None)
            C.loc[k, Fo.columns] = c
            resto = y - Z.values @ c
        else:
            resto = y
        Fo[k] = resto
        propia[k] = resto.var() / y.var()
    return Fo, C, pd.Series(propia, name="fracción propia")


def ajustar(y, X):
    """MCO de y sobre X con constante: (betas, R², observaciones) en las fechas comunes."""
    datos = pd.concat([y, X], axis=1).dropna()
    Y, Z = datos.iloc[:, 0].values, datos.iloc[:, 1:].values
    Z1 = np.column_stack([np.ones(len(Z)), Z])
    b, *_ = np.linalg.lstsq(Z1, Y, rcond=None)
    r2 = 1 - (Y - Z1 @ b).var() / Y.var()
    return pd.Series(b[1:], index=X.columns), r2, len(Y)


def r2_por_factor(R, F):
    """R² de cada activo (filas) explicado por cada factor por separado (columnas)."""
    return pd.DataFrame({f: {a: ajustar(R[a], F[[f]])[1] for a in R.columns} for f in F.columns})
