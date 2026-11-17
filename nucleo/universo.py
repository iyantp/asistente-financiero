"""Universo común al bot y a los cuadernos: variables de estado y activos de la cartera.

Es la única definición: el cuaderno de exposiciones, el informe semanal y el
resumen diario la importan de aquí. El marco conceptual está en conocimiento/mercado.md.

Los activos de la cartera NO se escriben aquí: se leen de control/cartera.csv, que es el registro único
de posiciones (nombre, bloque, peso, nombre corto y aproximación en Yahoo). Para dar de alta o de baja
una posición basta con su fila en cartera.csv; `coherencia()` comprueba que lo demás (factores, matriz,
reglas del bot) sigue cuadrando.
"""
import csv

from nucleo.rutas import CARTERA_CSV

# Variables de estado: nombre -> (fuente, código, tipo de cambio, ¿entra en la regresión?)
#   tipo de cambio: "dif" = diferencia (tipos, diferenciales, en puntos); "log" = cambio logarítmico (precios)
VARIABLES = {
    "Tipos reales 10a": ("fred", "DFII10", "dif", True),
    "Inflación esperada 10a": ("fred", "T10YIE", "dif", True),
    "Tipo 2a": ("fred", "DGS2", "dif", True),                   # expectativas de política monetaria (Fed)
    "Dólar (EUR/USD)": ("fred", "DEXUSEU", "log", True),        # sube = euro más fuerte
    "Dólar amplio": ("fred", "DTWEXBGS", "log", True),          # dólar frente a una cesta mundial; sube = dólar más fuerte
    "Estrés de crédito": ("fred", "BAA10Y", "dif", True),       # diferencial Baa frente al 10 años
    "Crecimiento (cobre)": ("yahoo", "HG=F", "log", True),
    "Petróleo (Brent)": ("fred", "DCOILBRENTEU", "log", True),
    "VIX": ("fred", "VIXCLS", "dif", False),                    # estrés de mercado; solo en los informes
}

# Activos de la cartera (de control/cartera.csv)
COLUMNAS_CARTERA = ("activo", "bloque", "peso", "corto", "ticker", "divisa", "aproximacion")
BLOQUES = ("ahorro", "cripto", "especulacion")


def leer_cartera(ruta=CARTERA_CSV):
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


_CARTERA = leer_cartera()
ACTIVOS = {f["activo"]: (f["ticker"], f["divisa"] or None) for f in _CARTERA}   # nombre -> (ticker, divisa)
CORTO = {f["activo"]: f["corto"] or f["activo"] for f in _CARTERA}               # nombre -> nombre corto (mensajes)

INICIO = "2012-01-01"          # inicio de la muestra para estandarizar y estimar
CORTE_REGIMEN = "2022-01-01"   # cambio de régimen de inflación

# Aproximaciones de mercado con dato diario fresco (Yahoo) para el resumen diario: sirven para comprobar
# si una variable de la matriz se ha movido de verdad (protocolo, pasos 2 y 3). FRED publica con 1-7 días
# de retraso; estas cotizan cada día.
#   nombre -> (ticker, tipo de cambio, variable de la matriz o None si solo es informativa,
#              signo: +1 si sube cuando sube la variable, -1 si va al revés)
# Notas: ^TNX es el tipo NOMINAL a 10 años (aproxima el movimiento del real, que no tiene dato diario);
# ZT=F es el precio del futuro del bono a 2 años (sube cuando baja el tipo); la cesta del dólar está en
# CESTA_DOLAR; los tipos de cambio de Yahoo se comparan tal cual (vela fechada al inicio del día en Londres:
# el último cambio cubre la sesión de ayer y la noche). La inflación esperada no tiene aproximación diaria.
DIARIAS = {
    "Bono 10a EE. UU. (nominal)": ("^TNX", "dif", "Tipos reales 10a", 1),
    "Futuro bono 2a EE. UU.": ("ZT=F", "log", "Tipo 2a", -1),
    "EUR/USD": ("EURUSD=X", "log", "Dólar (EUR/USD)", 1),
    "Dólar amplio (cesta)": ("CESTA_DOLAR", "log", "Dólar amplio", 1),
    "Crédito alto riesgo (HYG)": ("HYG", "log", "Estrés de crédito", -1),
    "VIX": ("^VIX", "dif", None, 1),
    "Cobre": ("HG=F", "log", "Crecimiento (cobre)", 1),
    "Brent": ("BZ=F", "log", "Petróleo (Brent)", 1),
}

# Aproximación diaria del dólar amplio (FRED DTWEXBGS va con una semana de retraso): media ponderada de
# los cambios logarítmicos frente a las seis mayores divisas del índice de la Fed (pesos aproximados,
# reescalados a 1). Signo: + = el dólar se fortalece. El DXY no sirve: el euro pesa el 58 %.
CESTA_DOLAR = {
    "EURUSD=X": -0.268,   # dólares por euro: si sube, el dólar se debilita
    "MXN=X": 0.211,       # pesos por dólar
    "CNY=X": 0.183,
    "CAD=X": 0.183,
    "JPY=X": 0.085,
    "GBPUSD=X": -0.070,   # dólares por libra
}


# Factores sectoriales: activos de referencia que explican una posición mejor que las variables
# de estado (contrastados en analisis/candidatas.ipynb). No son variables generales: son la capa
# intermedia entre las variables macro y cada activo (mercado → sector → activo).
#   posición -> {nombre del factor: ticker de Yahoo}
FACTORES = {
    "VanEck Rare Earth": {"Baterías y litio": "LIT", "Mineras globales": "PICK", "Bolsa china": "MCHI"},
    "ETH": {"Nasdaq 100": "QQQ"},          # relación desde 2022
    "BTC (WBTC)": {"Nasdaq 100": "QQQ"},   # relación desde 2022
}


def leer_matriz(ruta=None, columnas=("efecto_actual", "parcial_actual", "lectura")):
    """Lee analisis/exposiciones.csv y comprueba que tiene el formato y las variables actuales.

    Si la generó una versión anterior del cuaderno (p. ej., un núcleo de Jupyter abierto antes de un
    cambio de código), falla con un mensaje claro en vez de con un error de columna."""
    import pandas as pd
    from nucleo.rutas import MATRIZ
    exp = pd.read_csv(ruta or MATRIZ)
    faltan = [c for c in columnas if c not in exp.columns]
    esperadas = {n for n, v in VARIABLES.items() if v[3]}
    sobran, ausentes = set(exp.variable) - esperadas, esperadas - set(exp.variable)
    if faltan or sobran or ausentes:
        raise RuntimeError(
            "exposiciones.csv no corresponde al código actual "
            f"(faltan columnas {faltan or '-'}; variables de más {sorted(sobran) or '-'}; "
            f"de menos {sorted(ausentes) or '-'}): reinicia el núcleo y reejecuta analisis/exposiciones.ipynb")
    return exp



def coherencia(activos_bot=(), matriz=None, filas=None):
    """Problemas de coherencia entre control/cartera.csv y lo que depende de ella. Lista vacía = todo bien.

    `activos_bot`: config.ACTIVOS (sus `posicion` deben existir en la cartera; si una regla tiene
    `en_cartera`, debe decir a qué posición corresponde). `matriz`: DataFrame de exposiciones.csv
    (cada posición debe tener filas; si no, falta reejecutar analisis/exposiciones.ipynb).
    `filas`: filas de la cartera (por defecto, las de cartera.csv; sirve para las pruebas)."""
    filas = _CARTERA if filas is None else filas
    nombres = [f.get("activo", "") for f in filas]
    problemas = []
    if filas and (faltan := [c for c in COLUMNAS_CARTERA if c not in filas[0]]):
        problemas.append(f"cartera.csv: faltan columnas {faltan}")
    if (repetidos := sorted({n for n in nombres if nombres.count(n) > 1})):
        problemas.append(f"cartera.csv: nombres repetidos {repetidos}")
    for f in filas:
        if f.get("bloque") not in BLOQUES:
            problemas.append(f"cartera.csv: {f.get('activo')!r} tiene bloque {f.get('bloque')!r} (válidos: {', '.join(BLOQUES)})")
        if not f.get("ticker"):
            problemas.append(f"cartera.csv: {f.get('activo')!r} no tiene ticker de aproximación")
    try:
        total = sum(float(f["peso"]) for f in filas)
        if abs(total - 100) > 0.5:
            problemas.append(f"cartera.csv: los pesos suman {total:.1f} %, no 100 %")
    except (KeyError, ValueError) as e:
        problemas.append(f"cartera.csv: peso no válido ({e})")
    for activo in FACTORES:
        if activo not in nombres:
            problemas.append(f"universo.FACTORES: {activo!r} no está en cartera.csv")
    for a in activos_bot:
        posicion = getattr(a, "posicion", None)
        if posicion and posicion not in nombres:
            problemas.append(f"config.py: {a.nombre!r} apunta a la posición {posicion!r}, que no está en cartera.csv "
                             "(¿se vendió? quita en_cartera, posicion y su alarma)")
        elif getattr(a, "en_cartera", None) and not posicion:
            problemas.append(f"config.py: {a.nombre!r} tiene en_cartera pero no dice a qué posición de cartera.csv corresponde")
    if matriz is not None:
        en_matriz = set(matriz.activo)
        if (sin := [n for n in nombres if n not in en_matriz]):
            problemas.append(f"exposiciones.csv: sin filas para {sin}: reejecuta analisis/exposiciones.ipynb")
    return problemas
