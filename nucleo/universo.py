"""Universo común al bot y a los análisis: variables de estado y activos de la cartera.

Es la única definición: la matriz de exposición (nucleo/exposiciones.py), el informe semanal y el resumen
diario la importan de aquí. Nada de esto se escribe en el código:
- las variables generales, sus aproximaciones diarias y las cestas se leen de control/variables.toml (el método
  es general; las variables concretas son configuración);
- los factores específicos de cada posición, de control/especificos.csv;
- los activos de la cartera, de control/cartera.csv, el registro único de posiciones (nombre, bloque, peso,
  nombre corto y aproximación en Yahoo); los bloques válidos, de control/perfil.toml.
`coherencia()` comprueba que todo cuadra (variables, específicos, perfil, matriz y reglas del bot).

Comprobación rápida de la configuración:  python -m nucleo.universo
"""
import csv
import sys

from nucleo import perfil
from nucleo.rutas import CARTERA_CSV, ESPECIFICOS_CSV, VARIABLES_TOML

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

FUENTES = ("fred", "yahoo")
CAMBIOS = ("dif", "log")


def leer_variables(ruta=VARIABLES_TOML):
    with open(ruta, "rb") as f:
        return tomllib.load(f)


_CONF = leer_variables()
_PARAM = _CONF.get("parametros", {})

# Variables de estado: nombre -> (fuente, código, tipo de cambio, ¿entra en la matriz?)
#   tipo de cambio: "dif" = diferencia (tipos, diferenciales, en puntos); "log" = cambio logarítmico (precios)
VARIABLES = {n: (v.get("fuente"), v.get("codigo"), v.get("cambio"), bool(v.get("matriz", True)))
             for n, v in _CONF.get("variables", {}).items()}
CORTO_VAR = {n: v.get("corto", n) for n, v in _CONF.get("variables", {}).items()}   # nombre en los mensajes
SIGNIFICADO = {n: v["sube"] for n, v in _CONF.get("variables", {}).items() if v.get("sube")}  # qué es «sube»

# Activos de la cartera (de control/cartera.csv)
COLUMNAS_CARTERA = ("activo", "bloque", "peso", "corto", "ticker", "divisa", "aproximacion")
BLOQUES = tuple(perfil.bloques())


def leer_cartera(ruta=CARTERA_CSV):
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


_CARTERA = leer_cartera()
ACTIVOS = {f["activo"]: (f["ticker"], f["divisa"] or None) for f in _CARTERA}   # nombre -> (ticker, divisa)
CORTO = {f["activo"]: f["corto"] or f["activo"] for f in _CARTERA}               # nombre -> nombre corto (mensajes)

INICIO = _PARAM.get("inicio", "2012-01-01")                # inicio de la muestra para estandarizar y estimar
CORTE_REGIMEN = _PARAM.get("corte_regimen", "2022-01-01")  # inicio del régimen actual

# Aproximaciones diarias para el resumen diario (comprobar si una variable se ha movido de verdad):
#   nombre -> (ticker o nombre de una cesta, tipo de cambio, variable que aproxima o None, signo)
DIARIAS = {n: (d.get("ticker"), d.get("cambio"), d.get("variable"), int(d.get("signo", 1)))
           for n, d in _CONF.get("diarias", {}).items()}

# Cestas: nombre -> {ticker: peso}; su cambio es la suma ponderada de los cambios logarítmicos de los tickers
CESTAS = {n: {t: float(w) for t, w in c.items()} for n, c in _CONF.get("cestas", {}).items()}



def leer_especificos(ruta=ESPECIFICOS_CSV):
    """Filas de especificos.csv: {"factor", "ticker", "posiciones": [nombres de cartera.csv]}."""
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return [{"factor": r["factor"].strip(), "ticker": r["ticker"].strip(),
                 "posiciones": [x.strip() for x in r.get("posiciones", "").split(";") if x.strip()]}
                for r in csv.DictReader(f)]


# Factores específicos (control/especificos.csv): los que explican a una o pocas posiciones concretas.
ESPECIFICOS = leer_especificos()
# Vista por posición, para los mensajes: posición -> {nombre del factor: ticker de Yahoo}
FACTORES = {}
for _e in ESPECIFICOS:
    for _p in _e["posiciones"]:
        FACTORES.setdefault(_p, {})[_e["factor"]] = _e["ticker"]


def problemas_variables(variables=None, diarias=None, cestas=None):
    """Errores de forma de control/variables.toml. Lista vacía = todo bien."""
    variables = _CONF.get("variables", {}) if variables is None else variables
    diarias = _CONF.get("diarias", {}) if diarias is None else diarias
    cestas = _CONF.get("cestas", {}) if cestas is None else cestas
    p = []
    if not any(v.get("matriz", True) for v in variables.values()):
        p.append("variables.toml: ninguna variable entra en la matriz (matriz = true)")
    for n, v in variables.items():
        if v.get("fuente") not in FUENTES:
            p.append(f"variables.toml: {n!r} tiene fuente {v.get('fuente')!r} (válidas: {', '.join(FUENTES)})")
        if not v.get("codigo"):
            p.append(f"variables.toml: {n!r} no tiene codigo")
        if v.get("cambio") not in CAMBIOS:
            p.append(f"variables.toml: {n!r} tiene cambio {v.get('cambio')!r} (válidos: {', '.join(CAMBIOS)})")
    for n, d in diarias.items():
        if not d.get("ticker"):
            p.append(f"variables.toml: la aproximación diaria {n!r} no tiene ticker")
        if d.get("cambio") not in CAMBIOS:
            p.append(f"variables.toml: la aproximación diaria {n!r} tiene cambio {d.get('cambio')!r}")
        if d.get("variable") and d["variable"] not in variables:
            p.append(f"variables.toml: la aproximación diaria {n!r} apunta a la variable {d['variable']!r}, que no existe")
        if d.get("signo", 1) not in (1, -1):
            p.append(f"variables.toml: la aproximación diaria {n!r} tiene signo {d.get('signo')!r} (1 o -1)")
    for n, c in cestas.items():
        if not c:
            p.append(f"variables.toml: la cesta {n!r} está vacía")
    return p


def leer_matriz(ruta=None, columnas=("efecto_actual", "parcial_actual", "lectura")):
    """Lee analisis/exposiciones.csv y comprueba que tiene el formato y las variables actuales.

    Si se generó con otras variables (se cambió control/variables.toml y no se regeneró) o con una versión
    anterior del código, falla con un mensaje claro en vez de con un error de columna."""
    import pandas as pd
    from nucleo.rutas import MATRIZ
    exp = pd.read_csv(ruta or MATRIZ)
    faltan = [c for c in columnas if c not in exp.columns]
    esperadas = {n for n, v in VARIABLES.items() if v[3]}
    sobran, ausentes = set(exp.variable) - esperadas, esperadas - set(exp.variable)
    if faltan or sobran or ausentes:
        raise RuntimeError(
            "exposiciones.csv no corresponde a las variables de control/variables.toml o al código actual "
            f"(faltan columnas {faltan or '-'}; variables de más {sorted(sobran) or '-'}; "
            f"de menos {sorted(ausentes) or '-'}): regenera la matriz con python -m nucleo.exposiciones "
            "(en un cuaderno, reinicia antes el núcleo)")
    return exp



def coherencia(activos_bot=(), matriz=None, filas=None):
    """Problemas de coherencia entre control/cartera.csv y lo que depende de ella. Lista vacía = todo bien.

    `activos_bot`: config.ACTIVOS (sus `posicion` deben existir en la cartera; si una regla tiene
    `en_cartera`, debe decir a qué posición corresponde). `matriz`: DataFrame de exposiciones.csv
    (cada posición debe tener filas; si no, falta regenerar la matriz con python -m nucleo.exposiciones).
    `filas`: filas de la cartera (por defecto, las de cartera.csv; sirve para las pruebas)."""
    filas = _CARTERA if filas is None else filas
    nombres = [f.get("activo", "") for f in filas]
    problemas = (problemas_variables() + perfil.problemas()) if filas is _CARTERA else []
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
            problemas.append(f"especificos.csv: un factor apunta a {activo!r}, que no está en cartera.csv")
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
            problemas.append(f"exposiciones.csv: sin filas para {sin}: regenera la matriz: python -m nucleo.exposiciones")
    return problemas


if __name__ == "__main__":
    print(f"Variables generales ({VARIABLES_TOML.name}):")
    for n, (fuente, codigo, cambio, matriz) in VARIABLES.items():
        print(f"  {n:<26} {fuente}:{codigo:<14} {cambio}  {'matriz' if matriz else 'solo informe'}")
    print("Aproximaciones diarias:")
    for n, (ticker, cambio, var, signo) in DIARIAS.items():
        print(f"  {n:<26} {ticker:<12} → {var or '(informativa)'}{'' if signo == 1 else ' (signo -)'}")
    print("Específicos:", "; ".join(f"{a} ← {', '.join(f)}" for a, f in FACTORES.items()) or "ninguno")
    try:
        problemas = coherencia(matriz=leer_matriz())
    except RuntimeError as e:  # matriz generada con otras variables
        problemas = coherencia() + [str(e)]
    print("\n" + ("✅ Todo cuadra (variables, cartera y matriz; las reglas del bot las comprueban las pruebas y el "
                   "informe semanal)" if not problemas else "Problemas:\n" + "\n".join("  · " + x for x in problemas)))
