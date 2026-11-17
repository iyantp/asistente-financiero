"""Matriz de exposición: cómo se mueve cada activo de la cartera cuando se mueve cada variable de estado.

La usan el resumen diario (qué noticias afectan a la cartera) y el informe semanal (qué parte de la semana explica
cada variable). Se regenera al cambiar las variables (control/variables.toml) o la cartera (control/cartera.csv), y
conviene hacerlo cada trimestre:

    python -m nucleo.exposiciones            (sin conexión, con FINANZAS_SIN_RED=1, usa las copias de datos/)

Método:
- Datos semanales (cierre del viernes) desde universo.INICIO; activos en euros si llevan divisa; rentabilidad
  logarítmica $r$. Cambios de las variables ("dif" o "log") estandarizados: $z_k = (\\Delta x_k - \\bar{\\Delta x}_k) / s_k$,
  así que cada coeficiente es «rentabilidad semanal ante +1σ de la variable».
- Dos lecturas:
  · EFECTO TÍPICO $\\gamma_k$: regresión simple del activo sobre una variable. «Cuando esta variable sube 1σ, con lo
    que suele moverse a la vez el resto, ¿qué hace el activo?». Para noticias: una noticia nunca mueve una sola variable.
  · EXPOSICIÓN DIRECTA $\\beta_k$: regresión múltiple sobre todas a la vez. «¿Qué parte del movimiento es de esta
    variable y no de las otras?». Para atribuir la semana en el informe ($\\sum_k \\beta_k z_k$).
  Se relacionan por $\\gamma_k = \\sum_j \\beta_j \\rho_{jk}$: con variables correlacionadas pueden diferir e incluso
  cambiar de signo.
- Inferencia: t de Newey-West (4 rezagos); se da por significativa una relación con $|t| > 2{,}58$ (1 %): con muchos
  pares activo-variable, al 5 % saldrían varias «significativas» por azar.
- Se estima en todo el periodo y en el régimen actual (desde universo.CORTE_REGIMEN); los informes usan el régimen
  actual. Una relación es inestable si es significativa al 5 % en algún periodo y cambia de signo entre periodos.
- Límites: relaciones contemporáneas; describen el riesgo que se lleva, no predicen rentabilidades.

Columnas de la matriz (analisis/exposiciones.csv): fecha, activo, variable, efecto_* (efecto típico) y parcial_*
(exposición directa) del periodo completo y del régimen actual, con su t; lectura / lectura_parcial (régimen
actual: 0 = no significativo; +, ++, +++ o −, −−, −−− según la fuerza); estable (del efecto típico).
"""
from datetime import date

import numpy as np
import pandas as pd

from nucleo.backtest import mco
from nucleo.datos import precios, variable
from nucleo.rutas import MATRIZ
from nucleo.universo import ACTIVOS, CESTAS, CORTE_REGIMEN, DIARIAS, INICIO, VARIABLES

UMBRAL_T = 2.58


def semanal(s):
    return s.resample("W-FRI").last()


def variables_matriz():
    return {n: v for n, v in VARIABLES.items() if v[3]}


def datos(activos=None, variables=None):
    """(rentabilidades semanales de los activos, cambios semanales estandarizados z, cambios sin estandarizar)."""
    activos = ACTIVOS if activos is None else activos
    variables = variables_matriz() if variables is None else variables
    precios_activos = pd.DataFrame({n: semanal(precios(t, d, periodo="max")) for n, (t, d) in activos.items()})
    niveles = pd.DataFrame({n: semanal(variable(f, c)) for n, (f, c, _, _) in variables.items()})
    rent = np.log(precios_activos).diff().loc[INICIO:]
    cambios = pd.DataFrame({
        n: niveles[n].diff() if variables[n][2] == "dif" else np.log(niveles[n]).diff()
        for n in variables
    }).loc[INICIO:]
    z = (cambios - cambios.mean()) / cambios.std()
    return rent, z, cambios


def estimar(rent, z, desde=None, hasta=None):
    """(beta, t_beta, gamma, t_gamma, R² y semanas) por activo, entre `desde` y `hasta`."""
    B, TB, G, TG, R2 = {}, {}, {}, {}, {}
    Z = z.loc[desde:hasta]
    for activo in rent.columns:
        y = rent[activo].loc[desde:hasta]
        b, t, r2, n = mco(y, Z)
        B[activo], TB[activo], R2[activo] = b, t, {"R²": r2, "semanas": n}
        g, tg = {}, {}
        for v in Z.columns:
            gv, tv, _, _ = mco(y, Z[[v]])
            g[v], tg[v] = gv[v], tv[v]
        G[activo], TG[activo] = pd.Series(g), pd.Series(tg)
    f = lambda d: pd.DataFrame(d).T
    return f(B), f(TB), f(G), f(TG), f(R2)


def estimaciones(rent, z):
    periodos = {"completo": (None, None), "antes": (None, CORTE_REGIMEN), "actual": (CORTE_REGIMEN, None)}
    return {k: estimar(rent, z, *v) for k, v in periodos.items()}


def cambia_signo(M1, T1, M2, T2):
    return (np.sign(M1) != np.sign(M2)) & ((T1.abs() > 1.96) | (T2.abs() > 1.96))


def lectura(b, t):
    if abs(t) < UMBRAL_T:
        return "0"
    fuerza = abs(b) * 100
    return ("+" if b > 0 else "−") * (3 if fuerza >= 1 else 2 if fuerza >= 0.4 else 1)


def matriz(est, fecha=None):
    """Tabla larga (una fila por activo y variable) con el formato de analisis/exposiciones.csv."""
    B, TB, G, TG, _ = est["actual"]
    Bc, TBc, Gc, TGc, _ = est["completo"]
    _, _, G1, TG1, _ = est["antes"]
    inestable = cambia_signo(G1, TG1, G, TG)
    filas = []
    for activo in B.index:
        for var in B.columns:
            filas.append({
                "activo": activo, "variable": var,
                "efecto_actual": G.loc[activo, var], "t_efecto_actual": TG.loc[activo, var],
                "efecto_completo": Gc.loc[activo, var], "t_efecto_completo": TGc.loc[activo, var],
                "parcial_actual": B.loc[activo, var], "t_parcial_actual": TB.loc[activo, var],
                "parcial_completo": Bc.loc[activo, var], "t_parcial_completo": TBc.loc[activo, var],
                "lectura": lectura(G.loc[activo, var], TG.loc[activo, var]),
                "lectura_parcial": lectura(B.loc[activo, var], TB.loc[activo, var]),
                "estable": not inestable.loc[activo, var],
            })
    salida = pd.DataFrame(filas)
    salida.insert(0, "fecha", fecha or date.today().isoformat())
    return salida


def comprobar_cestas(cambios):
    """Correlación semanal de cada cesta de variables.toml con la variable que aproxima (esperable > 0,9)."""
    from nucleo.datos import _cierres, alinear_fx
    resultado = {}
    for nombre, (ticker, _, var, signo) in DIARIAS.items():
        if ticker not in CESTAS or var not in cambios:
            continue
        try:
            partes = {t: np.log(alinear_fx(_cierres(t, "max")) if t.endswith("=X") else _cierres(t, "max")).diff()
                      for t in CESTAS[ticker]}
            cesta = sum(w * partes[t] for t, w in CESTAS[ticker].items()).dropna()
            cesta = semanal(cesta.cumsum()).diff().loc[INICIO:]
            resultado[nombre] = signo * cesta.corr(cambios[var])
        except Exception as e:  # noqa: BLE001 (comprobación informativa)
            resultado[nombre] = f"no se pudo comprobar ({e})"
    return resultado


def main():
    rent, z, cambios = datos()
    est = estimaciones(rent, z)
    salida = matriz(est)
    salida.to_csv(MATRIZ, index=False, float_format="%.5f")
    pd.set_option("display.width", 200)
    print(f"Guardada en {MATRIZ} ({len(salida)} filas: {rent.shape[1]} activos × {z.shape[1]} variables)\n")
    print("R² de la regresión múltiple:")
    print(pd.concat({k: e[4]["R²"] for k, e in est.items()}, axis=1).round(2).to_string(), "\n")
    for col, titulo in [("lectura", "EFECTO TÍPICO"), ("lectura_parcial", "EXPOSICIÓN DIRECTA")]:
        print(f"{titulo} (desde {CORTE_REGIMEN[:4]}; 0 = no significativo al 1 %):")
        print(salida.pivot(index="activo", columns="variable", values=col).to_string(), "\n")
    for nombre, c in comprobar_cestas(cambios).items():
        print(f"Cesta «{nombre}»: correlación semanal con su variable "
              + (f"{c:.2f}" if isinstance(c, float) else c))


if __name__ == "__main__":
    main()
