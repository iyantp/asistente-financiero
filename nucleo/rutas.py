"""Rutas del repositorio: el único sitio donde se dice dónde está cada archivo.

Si se mueve un archivo, se cambia aquí y en ningún otro sitio del código.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# control/: lo que decide y mantiene el usuario a mano (fuente de verdad)
CONTROL = RAIZ / "control"
PERFIL_TOML = CONTROL / "perfil.toml"          # bloques, límites de riesgo y comisiones
CARTERA = CONTROL / "cartera.md"               # notas de la cartera (tesis, salidas): las lee el resumen diario
CARTERA_CSV = CONTROL / "cartera.csv"          # registro único de posiciones: nombre, pesos, bloque, aproximación
CALENDARIO = CONTROL / "calendario.csv"
VARIABLES_TOML = CONTROL / "variables.toml"   # variables generales, aproximaciones diarias y cestas
ESPECIFICOS_CSV = CONTROL / "especificos.csv"  # factores específicos de una o pocas posiciones

# Reglas del bot (solo las lee el bot y la comprobación de python -m nucleo.universo; nucleo/ no importa de bot/)
CONFIG_BOT = RAIZ / "bot" / "config.py"

# Resultados que generan el bot y los análisis
MATRIZ = RAIZ / "analisis" / "exposiciones.csv"  # la genera nucleo/exposiciones.py (python -m nucleo.exposiciones)
REGISTRO = RAIZ / "registro" / "decisiones.csv"  # la escribe el bot (los workflows hacen commit de registro/)

# Copias locales de precios y series (ignorado por git)
DATOS = RAIZ / "datos"
