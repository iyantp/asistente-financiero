"""Simulación histórica de estrategias dentro/fuera y sus métricas (para los cuadernos)."""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Regla:
    """Se está DENTRO del mercado cuando se cumplen todas las condiciones.

    Cada condición (a, b) significa SMA(a) > SMA(b). La SMA de 1 sesión es el
    propio precio, así que (1, 200) es "precio por encima de la SMA200".
    """
    nombre: str
    ticker: str
    condiciones: tuple
    divisa: str | None = None  # p. ej. "EURUSD=X": pasa el precio de dólares a euros


def simular(rent, dentro, retraso=2, comision=0.0, tipo_liquidez=0.0):
    """Rentabilidades diarias de la estrategia y serie de operaciones ejecutadas.

    La rentabilidad del día s se cobra si la señal de `retraso + 1` sesiones antes
    era "dentro"; si no, se cobra la de la liquidez. `tipo_liquidez` es el tipo anual en tanto por uno:
    un número fijo o una serie temporal (p. ej. datos.liquidez_eur()). Con 0 se infravalora estar fuera
    cuando los tipos son altos (2023-2025: ~3-4 % en euros).
    """
    expuesto = dentro.shift(retraso + 1).reindex(rent.index).eq(True)  # sin señal aún (NaN) = fuera
    operacion = expuesto.ne(expuesto.shift())
    operacion.iloc[0] = False
    if isinstance(tipo_liquidez, pd.Series):
        tipo_liquidez = tipo_liquidez.reindex(rent.index.union(tipo_liquidez.index)).ffill().reindex(rent.index).fillna(0.0)
    liquidez = (1 + tipo_liquidez) ** (1 / 252) - 1
    return rent.where(expuesto, liquidez) - comision * operacion, operacion


def metricas(r, operaciones):
    valor = (1 + r).cumprod()
    anios = (r.index[-1] - r.index[0]).days / 365.25
    rent_anual = valor.iloc[-1] ** (1 / anios) - 1
    vol = r.std() * np.sqrt(252)
    caida = (valor / valor.cummax() - 1).min()
    return {
        "rent. anual": rent_anual,
        "volatilidad": vol,
        "rent./vol.": rent_anual / vol,
        "caída máx.": caida,
        "rent./caída": rent_anual / -caida,
        "traspasos/año": operaciones.sum() / anios,
    }


def rent_movil(r, anios):
    """Rentabilidad anualizada en ventanas móviles de `anios` años."""
    n = int(252 * anios)
    return np.exp(np.log1p(r).rolling(n).sum() / anios) - 1


def mco(y, X, rezagos=4):
    """MCO con t-estadísticos de Newey-West. Devuelve (coeficientes, t, R², n)."""
    datos_ok = pd.concat([y, X], axis=1, sort=True).dropna()
    y_, X_ = datos_ok.iloc[:, 0].values, datos_ok.iloc[:, 1:].values
    X_ = np.column_stack([np.ones(len(X_)), X_])
    beta, *_ = np.linalg.lstsq(X_, y_, rcond=None)
    e = y_ - X_ @ beta
    XtX_inv = np.linalg.inv(X_.T @ X_)
    S = (X_ * e[:, None]).T @ (X_ * e[:, None])
    for l in range(1, rezagos + 1):
        w = 1 - l / (rezagos + 1)
        G = (X_[l:] * e[l:, None]).T @ (X_[:-l] * e[:-l, None])
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    t = beta / np.sqrt(np.diag(cov))
    r2 = 1 - e.var() / y_.var()
    return pd.Series(beta[1:], X.columns), pd.Series(t[1:], X.columns), r2, len(y_)
