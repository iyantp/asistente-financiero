"""Evalúa el registro de decisiones: ¿qué hizo el precio alrededor de cada señal o noticia?

Cada tipo de evento promete algo distinto, y se mide solo eso:
- Alertas (reglas de medias, alarmas): prometen que la tendencia sigue → rentabilidad a 1, 5 y 20
  sesiones desde el cierre del día del evento.
- Noticias del resumen diario: NO prometen predecir el precio (mercado.md). Prometen que la variable
  movida afecta a la cartera en la dirección indicada por el efecto típico de la matriz. Se mide:
    h = 0  la sesión anterior a la publicación (la que midió el z del filtro): ¿la cartera se movió en la
           dirección esperada? Comprueba que el efecto típico de la matriz acierta el signo.
    h = 1  la sesión del día de publicación (el resumen sale antes de la apertura de EE. UU.): para
           noticias de la noche o sin dato diario, ¿se terminó de reflejar en los precios?
Para cada fila con dirección esperada d (+1/-1) y horizonte h:
    rendimiento dirigido = d * rentabilidad;  exceso = d * (rentabilidad - rentabilidad media de h sesiones)
El exceso descuenta la tendencia general. Las noticias descartadas por el filtro (relevante=False) son el
grupo de control: si el filtro sirve, las relevantes deben acertar más y moverse más que las descartadas.

Uso:  python analisis/evaluar_registro.py [ruta_al_csv]
Descarga precios con yfinance; sin conexión usa las copias de datos/.
"""
import sys

import numpy as np
import pandas as pd

from nucleo.registro import leer
from nucleo.rutas import CARTERA_CSV

HORIZONTES = {"alertas": (1, 5, 20), "diario": (0, 1)}


def serie_cartera(fuente):
    """Índice de la cartera ponderada con cartera.csv (por sus aproximaciones de universo.py)."""
    from nucleo.universo import ACTIVOS
    pesos = pd.read_csv(CARTERA_CSV).set_index("activo")["peso"]
    # Precios en días hábiles (cripto cotiza también el fin de semana: su cierre del viernes se arrastra
    # y el cambio del fin de semana se suma al lunes, en vez de perderse).
    niveles = pd.DataFrame({a: fuente(t, d) for a, (t, d) in ACTIVOS.items() if a in pesos.index}).ffill()
    niveles = niveles[niveles.index.dayofweek < 5]
    r = niveles.pct_change().dropna()
    w = pesos.reindex(r.columns) / pesos.reindex(r.columns).sum()
    return (1 + (r * w).sum(axis=1)).cumprod()


def rendimientos(precio, fecha, origen):
    """Rentabilidad en cada horizonte. Referencia: alertas, el cierre del propio día del evento (se emiten
    tras el cierre); diario, el último cierre anterior a la fecha (se emite antes de abrir EE. UU.).
    h = 0 (solo diario) es la sesión que termina en ese cierre de referencia."""
    idx = precio.index
    pos = idx.searchsorted(pd.Timestamp(fecha), side="left" if origen == "diario" else "right") - 1
    out = {}
    for h in HORIZONTES[origen]:
        a, b = (pos - 1, pos) if h == 0 else (pos, pos + h)
        out[h] = precio.iloc[b] / precio.iloc[a] - 1 if a >= 0 and b < len(precio) else np.nan
    return out


def evaluar(df, fuente):
    cache, filas = {}, []
    for _, f in df.iterrows():
        if f["direccion"] in ("", None) or f["origen"] not in HORIZONTES:
            continue
        clave = (f["ticker"], f["divisa"])
        if clave not in cache:
            cache[clave] = serie_cartera(fuente) if f["ticker"] == "CARTERA" else fuente(f["ticker"], f["divisa"] or None)
        p = cache[clave]
        d = int(float(f["direccion"]))
        for h, r in rendimientos(p, f["fecha"], f["origen"]).items():
            base = p.pct_change(max(h, 1)).dropna().mean()
            filas.append({**f.to_dict(), "h": h, "abs %": abs(r) * 100 if pd.notna(r) else np.nan,
                          "dirigido": d * r if pd.notna(r) else np.nan,
                          "exceso": d * (r - base) if pd.notna(r) else np.nan})
    return pd.DataFrame(filas)


def resumen(ev):
    ev = ev.dropna(subset=["dirigido"])
    if ev.empty:
        return pd.DataFrame()
    ev = ev.assign(grupo=ev["origen"] + " · " + ev["tipo"] + ev["relevante"].map(
        {"True": " (relevante)", "False": " (descartada)", True: " (relevante)", False: " (descartada)"}).fillna(""))
    g = ev.groupby(["grupo", "h"])
    out = pd.DataFrame({
        "n": g.size(),
        "acierto %": g["dirigido"].apply(lambda x: (x > 0).mean() * 100),
        "dirigido %": g["dirigido"].mean() * 100,
        "exceso %": g["exceso"].mean() * 100,
        "|mov.| medio %": g["abs %"].mean(),
        "error est. %": g["exceso"].apply(lambda x: x.std(ddof=1) / np.sqrt(len(x)) * 100 if len(x) > 1 else np.nan),
    })
    return out.round(2)


if __name__ == "__main__":
    from nucleo.datos import precios
    ruta = sys.argv[1] if len(sys.argv) > 1 else None
    df = leer(ruta)
    if df.empty:
        sys.exit("El registro está vacío: aún no hay eventos que evaluar.")
    fuente = lambda t, d=None: precios(t, d, periodo="max")  # noqa: E731
    print(resumen(evaluar(df, fuente)).to_string())
    print("\nLectura: con pocas filas (n < 30) no se concluye nada; compara 'exceso' con 'error est.'. "
          "En noticias, compara relevantes con descartadas (acierto y |mov.| medio). "
          "Varias noticias el mismo día no son independientes.")
