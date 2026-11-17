"""Comprobación de los límites de riesgo de control/perfil.toml sobre los pesos de control/cartera.csv.

Los límites, sus bloques y el aviso «cerca» se configuran en perfil.toml (sección [[limites]]):
  maximo_conjunto  la suma de varios bloques no pasa de un valor (p. ej., cripto + especulación ≤ 15 %);
  maximo_posicion  ninguna posición de esos bloques pasa de un valor (p. ej., cada especulación ≤ 8 %);
  minimo_conjunto  la suma de esos bloques no baja de un valor (p. ej., ahorro ≥ 85 %).

Uso en local:
    python -m nucleo.limites                           estado actual
    python -m nucleo.limites "<posición>=+1.5" "<otra posición>=-1.5"
        simula cambios en puntos de peso (se renormaliza a 100) antes de operar.
"""
import sys

import pandas as pd

from nucleo import perfil
from nucleo.rutas import CARTERA_CSV


def cargar():
    return pd.read_csv(CARTERA_CSV)


def aplicar(df, cambios):
    """Suma `cambios` ({activo: puntos de peso}) y renormaliza a 100. Para simular una operación."""
    df = df.copy().set_index("activo")
    for activo, delta in cambios.items():
        if activo not in df.index:
            raise KeyError(f"{activo!r} no está en cartera.csv: {list(df.index)}")
        df.loc[activo, "peso"] += delta
    df["peso"] = df["peso"] / df["peso"].sum() * 100
    return df.reset_index()


def _etiqueta(lim, nombres):
    n = [nombres.get(x, x) for x in lim["bloques"]]
    return n[0] + "".join(" + " + x.lower() for x in n[1:])


def calcular(df, lims=None):
    """Una entrada por límite: {"limite", "valor"} y, en los de posición, "posicion" (la de más peso o None)."""
    lims = perfil.limites() if lims is None else lims
    peso, bloque = df.set_index("activo")["peso"], df.set_index("activo")["bloque"]
    resultado = []
    for lim in lims:
        dentro = peso[bloque.isin(lim["bloques"])]
        if lim["tipo"] == "maximo_posicion":
            resultado.append({"limite": lim, "valor": dentro.max() if len(dentro) else 0.0,
                              "posicion": dentro.idxmax() if len(dentro) else None})
        else:
            resultado.append({"limite": lim, "valor": dentro.sum()})
    return resultado


def _marca(valor, limite, minimo=False, cerca=0.9):
    if minimo:  # un mínimo solo importa si se incumple
        return "🚨 incumple" if valor < limite - 0.05 else "✅"
    if valor > limite + 0.05:
        return "🚨 supera"
    if valor >= limite - 0.05:
        return "⚠️ en el límite"
    return "⚠️ cerca" if valor >= limite * cerca - 1e-9 else "✅"


def _n(x):
    return f"{x:.1f}".replace(".", ",")


def lineas(df, lims=None, nombres=None, cerca=None):
    nombres = perfil.bloques() if nombres is None else nombres
    cerca = perfil.aviso_cerca() if cerca is None else cerca
    filas = []
    for r in calcular(df, lims):
        lim, v, valor = r["limite"], r["valor"], float(r["limite"]["valor"])
        etiqueta = _etiqueta(lim, nombres)
        if lim["tipo"] == "maximo_conjunto":
            filas.append(f"· {etiqueta}: {_n(v)} % de {_n(valor)} % {_marca(v, valor, cerca=cerca)}")
        elif lim["tipo"] == "maximo_posicion":
            filas.append(f"· Mayor {etiqueta.lower()} ({r['posicion']}): {_n(v)} % de {_n(valor)} % "
                         f"{_marca(v, valor, cerca=cerca)}" if r["posicion"] else f"· Sin posiciones de {etiqueta.lower()}")
        else:
            filas.append(f"· {etiqueta}: {_n(v)} % (mínimo {_n(valor)} %) {_marca(v, valor, minimo=True)}")
    return filas


def bloque(df=None):
    """Texto HTML para el informe semanal."""
    import html
    return "🛡️ <b>Límites del perfil</b>\n" + "\n".join(html.escape(l) for l in lineas(cargar() if df is None else df))


def reparto(df):
    """Pesos por bloque y posición, para leerlos por pantalla (cartera.csv es el único sitio de los pesos)."""
    filas = []
    for b, g in df.groupby("bloque", sort=False):
        filas.append(f"{b}: {_n(g.peso.sum())} %")
        filas += [f"    {a:<24} {_n(p):>5} %" for a, p in zip(g.activo, g.peso)]
    return filas


if __name__ == "__main__":
    df = cargar()
    if (errores := perfil.problemas()):
        sys.exit("\n".join(errores))
    print("Reparto (control/cartera.csv)\n" + "\n".join(reparto(df)) + "\n")
    print("Estado actual\n" + "\n".join(lineas(df)))
    if len(sys.argv) > 1:
        cambios = {}
        for a in sys.argv[1:]:
            nombre, valor = a.rsplit("=", 1)
            cambios[nombre] = float(valor)
        print(f"\nTras {cambios} (renormalizado a 100)\n" + "\n".join(lineas(aplicar(df, cambios))))
