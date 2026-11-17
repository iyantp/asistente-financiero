"""Condiciones que el bot puede vigilar sobre la serie de precios de un activo.

Cada condición devuelve, para cada sesión, si se cumple (True) o no (False). El bot
usa las condiciones de tres formas (ver config.py):
- seguimiento: avisa cuando una condición cambia (p. ej., tendencia que se gira);
- señal de una estrategia: entrada cuando pasa a cumplirse, salida cuando deja de cumplirse;
- alarma: avisa cuando pasa a cumplirse (si el activo tiene en_cartera, solo mientras la posición está DENTRO).

Para añadir un tipo de condición nuevo: una clase con `serie(precio)`, `sesiones`
(histórico que necesita) y `describir(cumple)` (texto del cambio para los mensajes).
"""
from dataclasses import dataclass

import pandas as pd


def _sma(n):
    return "precio" if n == 1 else f"SMA{n}"


@dataclass(frozen=True)
class Cruce:
    """Media móvil rápida por encima de la lenta: SMA(rapida) > SMA(lenta). rapida=1 es el precio."""
    rapida: int
    lenta: int

    @property
    def sesiones(self):
        return self.lenta

    def serie(self, precio):
        r, l = precio.rolling(self.rapida).mean(), precio.rolling(self.lenta).mean()
        ok = r.notna() & l.notna()
        return (r > l)[ok]

    def describir(self, cumple):
        return f"{_sma(self.rapida)} cruza por {'encima' if cumple else 'debajo'} de {_sma(self.lenta)}"


@dataclass(frozen=True)
class Nivel:
    """Precio por encima (encima=True) o por debajo (encima=False) de un nivel fijo."""
    nivel: float
    encima: bool = True

    sesiones = 1

    def serie(self, precio):
        return precio > self.nivel if self.encima else precio < self.nivel

    def describir(self, cumple):
        sube = cumple == self.encima
        return f"el precio {'supera' if sube else 'cae por debajo de'} {self.nivel:g}"


@dataclass(frozen=True)
class CaidaDesdeMaximo:
    """Caída desde el máximo de las últimas `ventana` sesiones igual o mayor que `pct` (0,2 = 20 %)."""
    pct: float
    ventana: int = 252

    @property
    def sesiones(self):
        return self.ventana

    def serie(self, precio):
        maximo = precio.rolling(self.ventana, min_periods=1).max()
        return precio / maximo - 1 <= -self.pct

    def describir(self, cumple):
        return (f"cae más de un {self.pct:.0%} desde su máximo" if cumple
                else f"recupera hasta menos de un {self.pct:.0%} de su máximo")


@dataclass(frozen=True)
class MinimoMovil:
    """El cierre queda por debajo del mínimo de los `ventana` cierres anteriores (ruptura de un suelo reciente).

    Sirve como salida de seguridad genérica: a la bolsa le va mal si pierde los mínimos de los últimos meses.
    El mínimo se calcula con las sesiones anteriores, sin contar la de hoy.
    """
    ventana: int = 60

    @property
    def sesiones(self):
        return self.ventana + 1

    def serie(self, precio):
        minimo = precio.shift(1).rolling(self.ventana).min()
        return (precio < minimo)[minimo.notna()]

    def describir(self, cumple):
        return (f"el precio cierra por debajo de su mínimo de {self.ventana} sesiones" if cumple
                else f"el precio vuelve por encima de su mínimo de {self.ventana} sesiones")


@dataclass(frozen=True)
class MaximoMovil:
    """El cierre supera el máximo de los `ventana` cierres anteriores (ruptura de un techo reciente).

    El máximo se calcula con las sesiones anteriores, sin contar la de hoy. Simétrica de MinimoMovil.
    """
    ventana: int = 60

    @property
    def sesiones(self):
        return self.ventana + 1

    def serie(self, precio):
        maximo = precio.shift(1).rolling(self.ventana).max()
        return (precio > maximo)[maximo.notna()]

    def describir(self, cumple):
        return (f"el precio cierra por encima de su máximo de {self.ventana} sesiones" if cumple
                else f"el precio vuelve por debajo de su máximo de {self.ventana} sesiones")


@dataclass(frozen=True)
class Variacion:
    """El precio ha cambiado `pct` o más en las últimas `ventana` sesiones (0,05 = 5 %).

    `pct` positivo: subida de al menos `pct`; negativo: caída de al menos |`pct`|. Con ventana=1, movimiento diario.
    """
    pct: float
    ventana: int = 1

    @property
    def sesiones(self):
        return self.ventana + 1

    def serie(self, precio):
        cambio = precio / precio.shift(self.ventana) - 1
        cumple = cambio >= self.pct if self.pct >= 0 else cambio <= self.pct
        return cumple[cambio.notna()]

    def describir(self, cumple):
        periodo = "en la última sesión" if self.ventana == 1 else f"en {self.ventana} sesiones"
        cifra = f"{abs(self.pct) * 100:g} %".replace(".", ",")
        verbo = "sube" if self.pct >= 0 else "cae"
        return (f"el precio {verbo} un {cifra} o más {periodo}" if cumple
                else f"el movimiento {periodo} vuelve a ser menor del {cifra}")


@dataclass(frozen=True)
class No:
    """Negación de otra condición (p. ej., alarma cuando una tendencia deja de cumplirse)."""
    condicion: object

    @property
    def sesiones(self):
        return self.condicion.sesiones

    def serie(self, precio):
        return ~self.condicion.serie(precio)

    def describir(self, cumple):
        return self.condicion.describir(not cumple)


@dataclass(frozen=True)
class Todas:
    """Se cumple cuando se cumplen todas las condiciones.

    `descripcion` (opcional): (texto si se cumple, texto si deja de cumplirse) para los mensajes, cuando la
    descripción automática de las partes no se lee bien (p. ej., «SMA6 cruza por debajo» para un estado).
    """
    condiciones: tuple
    descripcion: tuple | None = None

    @property
    def sesiones(self):
        return max(c.sesiones for c in self.condiciones)

    def serie(self, precio):
        series = [c.serie(precio) for c in self.condiciones]
        return pd.concat(series, axis=1, sort=True).dropna().all(axis=1)

    def describir(self, cumple):
        if self.descripcion:
            return self.descripcion[0 if cumple else 1]
        if cumple:
            return "se cumplen todas: " + "; ".join(c.describir(True) for c in self.condiciones)
        return "deja de cumplirse alguna: " + "; ".join(c.describir(False) for c in self.condiciones)


@dataclass(frozen=True)
class SinNuevoMinimo:
    """Han pasado al menos `dias` sesiones desde el último cierre en mínimo de `ventana` sesiones.

    Sirve como confirmación de que un suelo aguanta. «Cierre en mínimo» incluye el propio día
    (precio <= mínimo de las últimas `ventana` sesiones, contando la de hoy).
    """
    dias: int = 5
    ventana: int = 60

    @property
    def sesiones(self):
        return self.ventana + self.dias

    def serie(self, precio):
        minimo = precio.rolling(self.ventana).min()
        valido = minimo.notna()
        pos = pd.Series(range(len(precio)), index=precio.index, dtype=float)
        ultimo = pos.where((precio <= minimo) & valido).ffill()
        return ((pos - ultimo) >= self.dias)[valido & ultimo.notna()]

    def describir(self, cumple):
        if cumple:
            return f"pasan {self.dias} sesiones o más sin nuevo mínimo de {self.ventana} sesiones"
        return f"hay un nuevo mínimo de {self.ventana} sesiones de hace menos de {self.dias} sesiones"


@dataclass(frozen=True)
class Alguna:
    """Se cumple cuando se cumple alguna de las condiciones (misma `descripcion` opcional que Todas)."""
    condiciones: tuple
    descripcion: tuple | None = None

    @property
    def sesiones(self):
        return max(c.sesiones for c in self.condiciones)

    def serie(self, precio):
        series = [c.serie(precio) for c in self.condiciones]
        return pd.concat(series, axis=1, sort=True).dropna().any(axis=1)

    def describir(self, cumple):
        if self.descripcion:
            return self.descripcion[0 if cumple else 1]
        if cumple:
            return "se cumple alguna: " + "; ".join(c.describir(True) for c in self.condiciones)
        return "dejan de cumplirse todas: " + "; ".join(c.describir(False) for c in self.condiciones)
