"""Comprobación de los límites de perfil.md sobre los pesos de control/cartera.csv.

Límites: cripto + especulación <= 15 % del total; cada posición especulativa <= 8 %;
ahorro >= 85 % (es lo mismo que el primero). Avisa «cerca» a partir del 90 % del límite.

Uso en local:
    python -m nucleo.limites                           estado actual
    python -m nucleo.limites "ETH=+1.5" "Vanguard U.S. 500=-1.5"
        simula cambios en puntos de peso (se renormaliza a 100) antes de operar.
"""
import sys

import pandas as pd

from nucleo.rutas import CARTERA_CSV

LIMITE_CONJUNTO = 15.0   # cripto + especulación
LIMITE_POSICION = 8.0    # cada posición especulativa
AHORRO_MINIMO = 85.0
CERCA = 0.9              # fracción del límite a partir de la cual se avisa


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


def calcular(df):
    peso, bloque = df.set_index("activo")["peso"], df.set_index("activo")["bloque"]
    esp = peso[bloque == "especulacion"]
    return {
        "conjunto": peso[bloque.isin(["cripto", "especulacion"])].sum(),
        "ahorro": peso[bloque == "ahorro"].sum(),
        "mayor": (esp.idxmax(), esp.max()) if len(esp) else (None, 0.0),
    }


def _marca(valor, limite, minimo=False):
    if minimo:  # el mínimo de ahorro es el complemento del límite conjunto: solo importa si se incumple
        return "🚨 incumple" if valor < limite - 0.05 else "✅"
    if valor > limite + 0.05:
        return "🚨 supera"
    if valor >= limite - 0.05:
        return "⚠️ en el límite"
    return "⚠️ cerca" if valor >= limite * CERCA - 1e-9 else "✅"


def _n(x):
    return f"{x:.1f}".replace(".", ",")


def lineas(df):
    r = calcular(df)
    nombre, mayor = r["mayor"]
    filas = [
        f"· Cripto + especulación: {_n(r['conjunto'])} % de {_n(LIMITE_CONJUNTO)} % {_marca(r['conjunto'], LIMITE_CONJUNTO)}",
        f"· Mayor especulación ({nombre}): {_n(mayor)} % de {_n(LIMITE_POSICION)} % {_marca(mayor, LIMITE_POSICION)}"
        if nombre else "· Sin posiciones especulativas",
        f"· Ahorro: {_n(r['ahorro'])} % (mínimo {_n(AHORRO_MINIMO)} %) {_marca(r['ahorro'], AHORRO_MINIMO, minimo=True)}",
    ]
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
    print("Reparto (control/cartera.csv)\n" + "\n".join(reparto(df)) + "\n")
    print("Estado actual\n" + "\n".join(lineas(df)))
    if len(sys.argv) > 1:
        cambios = {}
        for a in sys.argv[1:]:
            nombre, valor = a.rsplit("=", 1)
            cambios[nombre] = float(valor)
        print(f"\nTras {cambios} (renormalizado a 100)\n" + "\n".join(lineas(aplicar(df, cambios))))
