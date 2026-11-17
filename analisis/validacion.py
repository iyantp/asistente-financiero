"""Validación fuera de muestra (walk-forward) de la regla «dentro si SMA(rápida) > SMA(lenta)».

Un barrido elige la mejor combinación mirando todo el histórico a la vez, y eso sobreestima lo que
cabe esperar: la combinación se ha elegido precisamente por lo bien que le fue en esos datos.
Aquí se repite el proceso como se haría en la vida real:
  1. en cada tramo se elige la mejor combinación solo con los años anteriores (entrenamiento);
  2. se aplica al tramo siguiente, que no se ha visto (prueba);
  3. se unen todos los tramos de prueba y se comparan con mantener siempre y con la «mejor a posteriori».
La diferencia entre la mejor a posteriori y el resultado fuera de muestra es el optimismo del barrido.

Uso:  python analisis/validacion.py [TICKER] [DIVISA]      (por defecto SPY EURUSD=X)
Descarga con yfinance; sin conexión (o con FINANZAS_SIN_RED=1) usa las copias de datos/.
"""
import sys

import pandas as pd

from nucleo.backtest import metricas, simular

RAPIDAS = [6, 20, 50, 75, 100, 150]
LENTAS = [70, 100, 200, 300, 400, 500]
RETRASO = 2           # sesiones entre la señal y la ejecución (como barrido.ipynb)
ENTRENAMIENTO = 8     # años para elegir
PRUEBA = 1            # años de cada tramo de prueba
COMISIONES = [0.0, 0.001, 0.005]
CRITERIOS = {"rent./vol.": lambda m: m["rent./vol."], "rent./caída": lambda m: m["rent./caída"]}


def cierres(ticker, divisa=None):
    """Cierres diarios (en euros si se da la divisa). Descarga con yfinance o, sin red, usa datos/."""
    from nucleo.datos import precios
    return precios(ticker, divisa, periodo="max")


def combinaciones(precio, rapidas, lentas):
    sma = {n: precio.rolling(n).mean() for n in set(rapidas) | set(lentas)}
    return {(a, b): (sma[a] > sma[b])[sma[a].notna() & sma[b].notna()] for a in rapidas for b in lentas if a < b}


def liquidez():
    """Tipo de la liquidez en euros (datos.liquidez_eur); si no está disponible, 0 con aviso."""
    try:
        from nucleo.datos import liquidez_eur
        return liquidez_eur()
    except Exception as e:
        print(f"Aviso: sin tipo de la liquidez ({e}); estar fuera rinde 0 % y se infravalora la regla")
        return 0.0


def walk_forward(precio, comision=0.0, criterio="rent./vol.", entrenamiento=ENTRENAMIENTO, prueba=PRUEBA,
                 rapidas=RAPIDAS, lentas=LENTAS, tipo_liquidez=0.0):
    """Devuelve (rent. fuera de muestra, operaciones, elegidas por tramo, rent. de cada combinación, mantener)."""
    rent = precio.pct_change().dropna()
    inicio = rent.index[max(lentas) + RETRASO + 2]          # todas las combinaciones ya tienen señal
    rent = rent[rent.index >= inicio]
    sim = {k: simular(rent, d, RETRASO, comision, tipo_liquidez) for k, d in combinaciones(precio, rapidas, lentas).items()}
    f = CRITERIOS[criterio]
    elegidas, partes_r, partes_o = [], [], []
    ini = rent.index[0]
    while True:
        fin_ent = ini + pd.DateOffset(years=entrenamiento)
        fin_pru = fin_ent + pd.DateOffset(years=prueba)
        if fin_ent >= rent.index[-1]:
            break
        ent = (rent.index >= ini) & (rent.index < fin_ent)
        pru = (rent.index >= fin_ent) & (rent.index < fin_pru)
        if pru.sum() < 100:
            break
        mejor = max(sim, key=lambda k: f(metricas(sim[k][0][ent], sim[k][1][ent])))
        elegidas.append((fin_ent.year, mejor))
        partes_r.append(sim[mejor][0][pru])
        partes_o.append(sim[mejor][1][pru])
        ini = ini + pd.DateOffset(years=prueba)
    return pd.concat(partes_r), pd.concat(partes_o), elegidas, sim, rent


def informe(ticker="SPY", divisa="EURUSD=X"):
    p = cierres(ticker, divisa)
    tipo = liquidez()
    print(f"{ticker}{' en ' + divisa if divisa else ''} · {p.index[0]:%Y-%m-%d} a {p.index[-1]:%Y-%m-%d} · "
          f"entrenamiento {ENTRENAMIENTO} años, prueba {PRUEBA} año")
    for criterio in CRITERIOS:
        filas = {}
        for c in COMISIONES:
            r, ops, elegidas, sim, rent = walk_forward(p, c, criterio, tipo_liquidez=tipo)
            oos = r.index
            mantener = metricas(rent.loc[oos], pd.Series(False, index=oos))
            post = max(sim, key=lambda k: CRITERIOS[criterio](metricas(sim[k][0].loc[oos], sim[k][1].loc[oos])))
            filas[f"fuera de muestra (comisión {c:.1%})"] = metricas(r, ops)
            filas[f"mejor a posteriori {post} (comisión {c:.1%})"] = metricas(sim[post][0].loc[oos], sim[post][1].loc[oos])
            if c == 0:
                filas["mantener siempre"] = mantener
                print(f"\nCriterio de elección: {criterio} · {len(elegidas)} tramos "
                      f"({oos[0]:%Y}–{oos[-1]:%Y}); combinaciones elegidas: {sorted(set(k for _, k in elegidas))}")
                cambios = sum(a != b for (_, a), (_, b) in zip(elegidas, elegidas[1:]))
                print(f"La elegida cambia {cambios} veces en {len(elegidas) - 1} renovaciones")
        t = pd.DataFrame(filas).T
        for col in ("rent. anual", "volatilidad", "caída máx."):
            t[col] = (t[col] * 100).round(1)
        t["rent./vol."], t["rent./caída"], t["traspasos/año"] = t["rent./vol."].round(2), t["rent./caída"].round(2), t["traspasos/año"].round(2)
        print(t.to_string())


if __name__ == "__main__":
    informe(*(sys.argv[1:3] or ["SPY", "EURUSD=X"]))
