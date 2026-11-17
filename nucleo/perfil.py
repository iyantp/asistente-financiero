"""Lectura de control/perfil.toml: bloques de la cartera, límites de riesgo y comisiones."""
import sys

from nucleo.rutas import PERFIL_TOML

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

TIPOS_LIMITE = ("maximo_conjunto", "maximo_posicion", "minimo_conjunto")


def leer(ruta=PERFIL_TOML):
    with open(ruta, "rb") as f:
        return tomllib.load(f)


def bloques(perfil=None):
    """{bloque: nombre en los mensajes}."""
    return dict((leer() if perfil is None else perfil).get("bloques", {}))


def limites(perfil=None):
    return list((leer() if perfil is None else perfil).get("limites", []))


def comisiones(perfil=None):
    return dict((leer() if perfil is None else perfil).get("comisiones", {}))


def aviso_cerca(perfil=None):
    return float((leer() if perfil is None else perfil).get("aviso_cerca", 0.9))


def problemas(perfil=None):
    """Errores de forma de perfil.toml. Lista vacía = todo bien."""
    perfil = leer() if perfil is None else perfil
    b, p = bloques(perfil), []
    if not b:
        p.append("perfil.toml: no hay [bloques]")
    for i, lim in enumerate(limites(perfil), 1):
        if lim.get("tipo") not in TIPOS_LIMITE:
            p.append(f"perfil.toml: el límite {i} tiene tipo {lim.get('tipo')!r} (válidos: {', '.join(TIPOS_LIMITE)})")
        if not lim.get("bloques") or any(x not in b for x in lim.get("bloques", [])):
            p.append(f"perfil.toml: el límite {i} usa bloques que no están en [bloques]: {lim.get('bloques')}")
        if not isinstance(lim.get("valor"), (int, float)):
            p.append(f"perfil.toml: el límite {i} no tiene `valor` numérico")
    for nombre, c in comisiones(perfil).items():
        if any(not isinstance(c.get(k, 0), (int, float)) for k in ("porcentaje", "minimo", "maximo", "cambio_divisa")):
            p.append(f"perfil.toml: la comisión {nombre!r} tiene valores no numéricos")
    return p
