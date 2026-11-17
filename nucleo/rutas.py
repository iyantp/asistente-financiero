"""Rutas del repositorio: el único sitio donde se dice dónde está cada archivo.

Si se mueve un archivo, se cambia aquí y en ningún otro sitio del código.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# control/: lo que decide y mantiene Iyán a mano (fuente de verdad)
CONTROL = RAIZ / "control"
PERFIL = CONTROL / "perfil.md"
CARTERA = CONTROL / "cartera.md"
CARTERA_CSV = CONTROL / "cartera.csv"          # registro único de posiciones: nombre, pesos, bloque, aproximación
CARTERA_LOCAL = CONTROL / "cartera.local.md"   # importes; ignorado por git
CALENDARIO = CONTROL / "calendario.csv"

# conocimiento/: marcos e investigación
CONOCIMIENTO = RAIZ / "conocimiento"
MERCADO = CONOCIMIENTO / "mercado.md"

# Resultados que generan los cuadernos y el bot
MATRIZ = RAIZ / "analisis" / "exposiciones.csv"  # la genera analisis/exposiciones.ipynb
REGISTRO = RAIZ / "registro" / "decisiones.csv"  # la escribe el bot (los workflows hacen commit de registro/)

# Copias locales de precios y series (ignorado por git)
DATOS = RAIZ / "datos"
