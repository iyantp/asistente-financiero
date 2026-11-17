"""Modelo de factores de riesgo: construcción y ortogonalización de los factores (pasos 1 y 2).

Los factores se definen en control/factores.toml. Aquí:
- `factores()` construye la serie diaria de cada factor general (rentabilidad o cambio al cierre de EE. UU.);
- `especificos()` construye los de una posición concreta (control/especificos.csv), limpios de los generales;
- `ortogonalizar()` los limpia en orden: el primero queda igual y cada siguiente se queda solo con la parte que
  no explican los anteriores (Gram-Schmidt con regresiones). Devuelve también los coeficientes de esa limpieza y
  qué fracción de cada factor es «nueva», para ver qué aporta cada uno;
- `rentabilidades_activos()` da las rentabilidades diarias de la cartera, en la moneda de cada activo o ya
  convertidas a la del inversor; `conversion_divisa()` da el término exacto de la conversión.

Calendario común ([parametros] calendario): todas las series (factores y activos) se toman en las mismas fechas, las
sesiones de la bolsa de EE. UU., y cada rentabilidad va de una sesión a la siguiente. Lo que cotiza fines de semana o
festivos (cripto, divisas) acumula esos días en la sesión siguiente: el lunes lleva el movimiento desde el viernes.
Sin esto, los días sueltos se perdían y la serie de un activo y la de su factor no cubrían el mismo periodo.

Conversión ([parametros] conversion en control/factores.toml):
  "exacta"    el modelo se estima en la moneda de cada activo y la conversión se suma después, sin estimarla:
              r_inversor = r_local − Δlog(tipo de cambio)   (tipo de cambio = unidades de la divisa por unidad tuya)
  "estimada"  se estima sobre rentabilidades ya convertidas, con la divisa como un factor más.

Exposiciones en el tiempo (paso 3, [parametros] estimacion): `betas_moviles()` estima las β de cada fecha con los datos
hasta esa fecha; `error_fuera_de_muestra()` mide cómo explican el día siguiente. Las relaciones cambian (la tecnología
pasó de β ≈ 0 a −0,6 frente al crédito entre 2017 y 2026), así que β fijas describen mal el presente.

Guía de uso y decisiones: analisis/factores.ipynb.
"""
import sys

import numpy as np
import pandas as pd

from nucleo.datos import _cierres, alinear_fx, cambio, cambio_eurusd, precios, variable
from nucleo.rutas import FACTORES_TOML
from nucleo.universo import ACTIVOS, CESTAS, ESPECIFICOS

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
    if c == "estimada" and not any(d.get("tipo") == "eurusd" and d.get("usar", True)
                                   for d in leer_definiciones(ruta).values()):
        raise ValueError('conversion = "estimada" necesita un factor de divisa (tipo = "eurusd") con usar = true')
    return c


def sesiones(ruta=FACTORES_TOML):
    """Fechas comunes del modelo: las sesiones de [parametros] calendario (por defecto, SPY: bolsa de EE. UU.)."""
    return precios(parametros(ruta).get("calendario", "SPY"), periodo="max").index


def en_sesiones(nivel, fechas):
    """Último valor disponible en cada fecha de `fechas`. Lo que cotiza en días que no están en `fechas` (fines de
    semana, festivos) queda dentro del cambio hasta la fecha siguiente. Sin valor antes del primer dato ni más de una
    semana después del último (una serie que deja de publicarse no se rellena)."""
    nivel = nivel.dropna()
    if nivel.empty:
        return pd.Series(np.nan, index=fechas)
    s = nivel.reindex(nivel.index.union(fechas)).ffill().reindex(fechas)
    s[s.index > nivel.index[-1] + pd.Timedelta(days=7)] = np.nan
    return s


def _log_rent(ticker, fechas):
    return np.log(en_sesiones(precios(ticker, periodo="max"), fechas)).diff()


def serie_factor(d, fechas=None):
    """Serie de un factor en las sesiones del calendario común, a partir de su definición (ver control/factores.toml)."""
    fechas = sesiones() if fechas is None else fechas
    tipo = d.get("tipo")
    if tipo == "precio":
        s = _log_rent(d["ticker"], fechas)
    elif tipo == "diferencial":
        s = _log_rent(d["largo"], fechas) - _log_rent(d["corto"], fechas)
    elif tipo == "nivel":
        s = en_sesiones(variable(d["fuente"], d["codigo"]), fechas).diff()
    elif tipo == "cesta":
        pesos = CESTAS[d["cesta"]]
        partes = {t: np.log(en_sesiones(alinear_fx(_cierres(t, "max")) if t.endswith("=X") else _cierres(t, "max"),
                                        fechas)).diff()
                  for t in pesos}
        s = sum(w * partes[t] for t, w in pesos.items())
    elif tipo == "eurusd":
        s = np.log(en_sesiones(cambio_eurusd("max"), fechas)).diff()
    else:
        raise ValueError(f"tipo {tipo!r} no válido (válidos: {', '.join(TIPOS)})")
    s = (d.get("signo", 1) * s).dropna()
    return s.loc[d["desde"]:] if d.get("desde") else s


def factores(definiciones=None, todos=False, alternativas=False):
    """(DataFrame diario con un factor por columna, {factor: error o aviso}).

    Solo los de `usar = true`, salvo `todos=True`. Columnas en el orden del archivo. Con `alternativas=True`
    (solo para análisis), un factor sin datos usa su `alternativa` y queda anotado en el segundo valor."""
    definiciones = leer_definiciones() if definiciones is None else definiciones
    fechas = sesiones()
    series, avisos = {}, {}
    for nombre, d in definiciones.items():
        if not (todos or d.get("usar", True)):
            continue
        try:
            series[nombre] = serie_factor(d, fechas)
        except Exception as e:  # noqa: BLE001 (un factor sin datos no debe tumbar el resto)
            if alternativas and d.get("alternativa"):
                try:
                    series[nombre] = serie_factor(d["alternativa"], fechas)
                    avisos[nombre] = f"sin datos ({str(e)[:60]}); se usa la alternativa {d['alternativa']}"
                    continue
                except Exception as e2:  # noqa: BLE001
                    e = e2
            avisos[nombre] = str(e)[:120]
    return pd.DataFrame(series), avisos


def especificos(activo, generales, definiciones=None, alternativas=False):
    """Factores específicos de `activo` (control/especificos.csv), limpios de los generales: (DataFrame, avisos).

    Se ortogonalizan detrás de todos los generales (y entre sí, en el orden del archivo), así que solo recogen lo
    que los generales no explican. Un mismo específico puede servir a varias posiciones (p. ej., el bitcoin al ether
    y al propio bitcoin): así el modelo ve que esas posiciones se mueven juntas. Sin específicos, DataFrame vacío."""
    if definiciones is None:
        definiciones = {e["factor"]: {"tipo": "precio", "ticker": e["ticker"]}
                        for e in ESPECIFICOS if activo in e["posiciones"]}
    if not definiciones:
        return pd.DataFrame(index=generales.index), {}
    E, avisos = factores(definiciones, todos=True, alternativas=alternativas)
    if E.empty:
        return E, avisos
    Fo, _, _ = ortogonalizar(pd.concat([generales, E], axis=1, sort=True), list(generales.columns) + list(E.columns))
    return Fo[list(E.columns)], avisos


def rentabilidades_activos(activos=None, moneda="inversor", fechas=None):
    """Rentabilidades logarítmicas de los activos entre sesiones del calendario común: moneda="local" (la de cada
    activo) o "inversor" (convertidas con la `divisa` de control/cartera.csv; igual que la local sin divisa)."""
    activos = ACTIVOS if activos is None else activos
    fechas = sesiones() if fechas is None else fechas
    conv = moneda == "inversor"
    return pd.DataFrame({n: np.log(en_sesiones(precios(t, d if conv else None, periodo="max"), fechas)).diff()
                         for n, (t, d) in activos.items()})


def conversion_divisa(activos=None, fechas=None):
    """Término exacto de la conversión por activo: −Δlog(tipo de cambio) en las fechas de cotización del activo,
    de modo que r_inversor = r_local + este término (cero si el activo no lleva divisa)."""
    activos = ACTIVOS if activos is None else activos
    fechas = sesiones() if fechas is None else fechas
    columnas = {}
    for n, (t, d) in activos.items():
        p = precios(t, periodo="max")
        if not d:
            columnas[n] = (0 * np.log(en_sesiones(p, fechas)).diff())
            continue
        fx = cambio(d, "max")
        fx = fx.reindex(p.index.union(fx.index)).ffill().reindex(p.index)   # igual que nucleo.datos.precios
        columnas[n] = -np.log(en_sesiones(fx, fechas)).diff()
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


def estimacion(ruta=FACTORES_TOML):
    """(método, n) de [parametros] estimacion: cómo se estiman las β en el tiempo (paso 3)."""
    e = parametros(ruta).get("estimacion", {"metodo": "ewma", "vida_media": 252})
    metodo = e.get("metodo", "ewma")
    if metodo not in ("acumulada", "ventana", "ewma"):
        raise ValueError(f"estimacion.metodo = {metodo!r} no válido (\"acumulada\", \"ventana\" o \"ewma\")")
    return metodo, int(e.get("vida_media" if metodo == "ewma" else "sesiones", 252))


def betas_moviles(y, X, metodo="ewma", n=252, minimo=252):
    """β de y sobre X (con constante, columna "α") estimadas en cada fecha con los datos hasta esa fecha, incluida.

    metodo:  "acumulada"  toda la historia anterior con el mismo peso (β fijas que solo se van afinando)
             "ventana"    las últimas `n` sesiones con el mismo peso
             "ewma"       todas, con peso que se reduce a la mitad cada `n` sesiones (vida media)
    Las fechas sin dato de y o de algún factor se saltan (no cuentan para la ventana ni para el descuento). Sin β
    hasta tener `minimo` observaciones. Para usarlas al día siguiente (sin mirar el futuro), desplazar con .shift(1).
    """
    d = pd.concat([y.rename("_y"), X], axis=1).dropna()
    Y = d["_y"].values
    Z = np.column_stack([np.ones(len(d)), d.drop(columns="_y").values])
    k = Z.shape[1]
    S, s = np.zeros((k, k)), np.zeros(k)
    salida = np.full((len(d), k), np.nan)
    lam = 0.5 ** (1 / n) if metodo == "ewma" else 1.0
    for t in range(len(d)):
        S = lam * S + np.outer(Z[t], Z[t])
        s = lam * s + Z[t] * Y[t]
        if metodo == "ventana" and t >= n:
            S -= np.outer(Z[t - n], Z[t - n])
            s -= Z[t - n] * Y[t - n]
        if t + 1 >= minimo:
            salida[t] = np.linalg.lstsq(S, s, rcond=None)[0]
    return pd.DataFrame(salida, index=d.index, columns=["α"] + list(X.columns))


def error_fuera_de_muestra(y, X, B):
    """Error de explicar cada día con las β de la víspera: y_t − α_{t−1} − Σ β_{t−1}·f_t (sin mirar el futuro)."""
    d = pd.concat([y.rename("_y"), X], axis=1).dropna()
    Bp = B.shift(1).reindex(d.index)
    return (d["_y"] - Bp["α"] - (Bp[X.columns] * d[X.columns]).sum(axis=1, min_count=1)).dropna()
