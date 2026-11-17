"""Riesgo de la cartera en conjunto (no activo a activo), con los pesos de cartera.csv.

Responde a las preguntas que deciden el 85 % del ahorro, antes que cualquier idea especulativa:
  1. Volatilidad y caída de la cartera actual, y qué posición aporta cada parte del riesgo.
  2. Qué variables de estado explican el riesgo de la cartera (exposición directa de la matriz).
  3. Cubrir o no el dólar: volatilidad de cada activo en euros (sin cubrir) y en dólares (≈ cubierto,
     sin contar el coste de la cobertura, que es aproximadamente el diferencial de tipos EE. UU.–zona euro).
  4. Episodios de tensión: qué habría hecho la cartera actual en 2020, 2022 y 2025.
  5. Diversificadores: efecto de sustituir un 5-10 % de renta variable por oro (GLD) o por cubrir el bono.

Datos semanales en euros (aproximaciones de universo.ACTIVOS; oro con GLD). Las relaciones cambian con el
régimen: se muestran desde 2012 y desde 2022. No predice rentabilidades: mide riesgo.

Uso:  python analisis/riesgo_cartera.py         (sin conexión usa las copias de datos/)
"""

import numpy as np
import pandas as pd

from nucleo.datos import precios, variable
from nucleo.rutas import CARTERA_CSV
from nucleo.universo import ACTIVOS, CORTE_REGIMEN, INICIO, VARIABLES

pd.set_option("display.width", 200)
EPISODIOS = {"Covid (feb–mar 2020)": ("2020-02-14", "2020-03-20"),
             "Inflación (2022)": ("2021-12-31", "2022-10-14"),
             "Aranceles (feb–abr 2025)": ("2025-02-14", "2025-04-11")}


def semanal(s):
    return s.resample("W-FRI").last()


def cargar():
    pesos = pd.read_csv(CARTERA_CSV).set_index("activo")["peso"] / 100
    eur = pd.DataFrame({a: semanal(precios(t, d, periodo="max")) for a, (t, d) in ACTIVOS.items()})
    usd = pd.DataFrame({a: semanal(precios(t, periodo="max")) for a, (t, d) in ACTIVOS.items()})
    eur["Oro (GLD)"] = semanal(precios("GLD", "EURUSD=X", periodo="max"))
    usd["Oro (GLD)"] = semanal(precios("GLD", periodo="max"))
    return pesos, np.log(eur).diff().loc[INICIO:], np.log(usd).diff().loc[INICIO:]


def cartera(r, w):
    """Rentabilidad semanal de la cartera con pesos fijos (renormalizados a los activos con dato)."""
    w = w.reindex(r.columns).fillna(0)
    disponibles = r.notna()
    peso_ok = (disponibles * w).sum(axis=1)
    return (r.fillna(0) * w).sum(axis=1) / peso_ok.where(peso_ok > 0)


def caida_max(r):
    v = np.exp(r.cumsum())
    return (v / v.cummax() - 1).min()


def contribuciones(r, w):
    """Parte de la varianza de la cartera que aporta cada activo: w_i (Σw)_i / w'Σw."""
    datos = r[w.index].dropna()
    S = datos.cov() * 52
    w = w.reindex(S.index)
    total = float(w @ S @ w)
    return (w * (S @ w) / total), np.sqrt(total)


def main():
    pesos, r_eur, r_usd = cargar()
    w = pesos.reindex([a for a in ACTIVOS if a in pesos.index])
    print(f"Pesos de cartera.csv (suma {w.sum():.0%}); datos semanales en euros desde {INICIO[:4]}\n")

    print("1) Volatilidad, caída máxima y reparto del riesgo (cartera actual aplicada al pasado)")
    for nombre, desde in [(f"desde {INICIO[:4]}", INICIO), (f"desde {CORTE_REGIMEN[:4]}", CORTE_REGIMEN)]:
        rc = cartera(r_eur.loc[desde:, w.index], w)
        print(f"  {nombre}: volatilidad {rc.std() * np.sqrt(52):.1%}, caída máxima {caida_max(rc.dropna()):.1%}")
    contrib, _ = contribuciones(r_eur.loc[CORTE_REGIMEN:], w)
    tabla = pd.DataFrame({"peso": w, "parte del riesgo (desde 2022)": contrib})
    tabla["riesgo / peso"] = tabla.iloc[:, 1] / tabla["peso"]
    print(tabla.to_string(float_format=lambda x: f"{x:.2f}"))
    print("  (riesgo / peso > 1: la posición aporta más riesgo del que pesa)\n")

    print("2) Variables de estado detrás del riesgo de la cartera (desde 2022, exposición directa)")
    vs = {n: v for n, v in VARIABLES.items() if v[3]}
    niveles = pd.DataFrame({n: semanal(variable(f, c)) for n, (f, c, _, _) in vs.items()})
    cambios = pd.DataFrame({n: niveles[n].diff() if vs[n][2] == "dif" else np.log(niveles[n]).diff() for n in vs})
    z = ((cambios - cambios.loc[INICIO:].mean()) / cambios.loc[INICIO:].std()).loc[CORTE_REGIMEN:]
    rc = cartera(r_eur.loc[CORTE_REGIMEN:, w.index], w)
    d = pd.concat([rc.rename("cartera"), z], axis=1, sort=True).dropna()
    X = np.column_stack([np.ones(len(d)), d[z.columns].values])
    b = np.linalg.lstsq(X, d["cartera"].values, rcond=None)[0][1:]
    b = pd.Series(b, z.columns)
    C = d[z.columns].cov()
    parte = b * (C @ b) / d["cartera"].var()
    print(f"  R² {parte.sum():.2f}: el resto es riesgo propio de cada activo")
    print((parte.sort_values(ascending=False) * 100).round(1).rename("% de la varianza").to_string(), "\n")

    print("3) Cubrir el dólar: volatilidad anual en euros (sin cubrir) y en dólares (≈ cubierto, sin coste)")
    filas = {}
    for a in list(w.index) + ["Oro (GLD)"]:
        if a in ("ETH", "BTC (WBTC)"):
            continue
        for nombre, desde in [("desde 2012", INICIO), ("desde 2022", CORTE_REGIMEN)]:
            e, u = r_eur[a].loc[desde:].dropna(), r_usd[a].loc[desde:].dropna()
            filas[(a, nombre)] = {"sin cubrir": e.std() * np.sqrt(52), "cubierto": u.std() * np.sqrt(52)}
    t = pd.DataFrame(filas).T
    t["cubrir reduce"] = t["sin cubrir"] - t["cubierto"]
    print(t.to_string(float_format=lambda x: f"{x:.1%}"))
    eq = [a for a in w.index if a not in ("Bono EE. UU. 2035", "ETH", "BTC (WBTC)")]
    re_ = cartera(r_eur.loc[INICIO:, eq], w[eq]); ru = cartera(r_usd.loc[INICIO:, eq], w[eq])
    print(f"  Renta variable de la cartera: {re_.std()*np.sqrt(52):.1%} sin cubrir vs {ru.std()*np.sqrt(52):.1%} cubierta;"
          f" caída máxima {caida_max(re_.dropna()):.1%} vs {caida_max(ru.dropna()):.1%}")
    print("  Lectura: en acciones, el dólar tiende a subir cuando cae la bolsa y amortigua (cubrir apenas reduce"
          " riesgo y cuesta el diferencial de tipos); en el bono no hay ese efecto y la divisa domina su riesgo.\n")

    print("4) Episodios de tensión: rentabilidad de la cartera actual (euros)")
    ep = {}
    for nombre, (a, b_) in EPISODIOS.items():
        tramo = r_eur.loc[a:b_].iloc[1:]
        ep[nombre] = {"cartera": np.expm1(cartera(tramo[w.index], w).sum()),
                      **{k: np.expm1(tramo[k].sum()) for k in ["Vanguard U.S. 500", "Bono EE. UU. 2035", "Oro (GLD)"]}}
    print(pd.DataFrame(ep).T.to_string(float_format=lambda x: f"{x:+.1%}"), "\n")

    print("5) Diversificadores (desde 2012 y desde 2022; se resta peso a la renta variable de ahorro en proporción)")
    ahorro_rv = ["Vanguard U.S. 500", "Amundi MSCI World", "Fidelity Global Tech"]
    filas = {}
    for nombre, x in [("actual", 0.0), ("oro 5 %", 0.05), ("oro 10 %", 0.10)]:
        w2 = w.copy()
        w2[ahorro_rv] -= x * w[ahorro_rv] / w[ahorro_rv].sum()
        w2["Oro (GLD)"] = x
        for per, desde in [("2012", INICIO), ("2022", CORTE_REGIMEN)]:
            rc = cartera(r_eur.loc[desde:, w2.index], w2)
            filas[(nombre, per)] = {"vol.": rc.std() * np.sqrt(52), "caída máx.": caida_max(rc.dropna()),
                                    "rent. anual": np.expm1(rc.mean() * 52)}
    # bono cubierto: su rentabilidad en dólares en lugar de en euros (sin coste de cobertura)
    r_cub = r_eur.copy(); r_cub["Bono EE. UU. 2035"] = r_usd["Bono EE. UU. 2035"]
    for per, desde in [("2012", INICIO), ("2022", CORTE_REGIMEN)]:
        rc = cartera(r_cub.loc[desde:, w.index], w)
        filas[("bono cubierto", per)] = {"vol.": rc.std() * np.sqrt(52), "caída máx.": caida_max(rc.dropna()),
                                         "rent. anual": np.expm1(rc.mean() * 52)}
    print(pd.DataFrame(filas).T.to_string(float_format=lambda x: f"{x:+.1%}"))
    print("  Ojo: la rentabilidad pasada no es la esperada (el oro ha tenido una década excepcional); "
          "lo comparable entre filas es el riesgo.")


if __name__ == "__main__":
    main()
