"""Estadística común: regresión por MCO con errores de Newey-West (la usa la matriz de exposición)."""
import numpy as np
import pandas as pd


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
