"""Registro de decisiones: cada alerta y cada noticia clasificada queda anotada para evaluarla después.

Un CSV (registro/decisiones.csv, sin importes, versionado) con una fila por evento:
    fecha     día del evento (alertas: vela que lo provoca; diario: día de publicación)
    origen    "alertas" o "diario"
    tipo      alarma, fin_alarma, entrada, confirmacion, salida, cambio_tendencia, noticia
    activo    nombre legible
    ticker    ticker de Yahoo; "CARTERA" = la cartera ponderada con cartera.csv
    divisa    divisa de conversión a euros (o vacío)
    direccion +1 / -1: hacia dónde debería moverse el precio si la señal sirve
    detalle   texto de la regla o titular
    relevante True/False: lo decidió el código del diario (vacío en alertas)
    variable  variable de estado de la noticia (diario; vacío si es sectorial)
    z         movimiento medido de esa variable el día de la noticia (diario; vacío sin dato diario)

analisis/evaluar_registro.py mide qué hizo el precio después (ver allí qué horizonte tiene sentido en cada caso).
Registrar nunca debe impedir que el bot avise: quien llama captura los errores.
"""
from pathlib import Path

import pandas as pd

from nucleo.rutas import REGISTRO

RUTA = REGISTRO
COLUMNAS = ["fecha", "origen", "tipo", "activo", "ticker", "divisa", "direccion", "detalle", "relevante", "variable", "z"]
CLAVE = ["fecha", "origen", "tipo", "activo", "detalle"]


def leer(ruta=None):
    ruta = ruta or RUTA
    if not Path(ruta).exists():
        return pd.DataFrame(columns=COLUMNAS)
    return pd.read_csv(ruta, keep_default_na=False)


def registrar(filas, ruta=None):
    """Añade filas (lista de dicts) sin duplicar eventos ya anotados. Devuelve cuántas añadió."""
    if not filas:
        return 0
    ruta = Path(ruta or RUTA)
    nuevas = pd.DataFrame(filas).reindex(columns=COLUMNAS).fillna("")
    previas = leer(ruta)
    todas = pd.concat([previas, nuevas], ignore_index=True)
    todas = todas.drop_duplicates(subset=CLAVE, keep="first").reindex(columns=COLUMNAS).fillna("")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    todas.to_csv(ruta, index=False)
    return len(todas) - len(previas)
