"""El tipo `Activo`: un activo vigilado por el bot y sus reglas (se usan en bot/config.py).

Separado de bot/config.py para que ese archivo sea solo configuración. Al crear un `Activo` se comprueba que las
reglas están bien escritas, de modo que un error (una condición sin paréntesis, una fecha mal puesta…) se ve en
cuanto se ejecuta cualquier programa del bot, con un mensaje que dice qué activo y qué regla fallan.
"""
from dataclasses import dataclass
from datetime import date


def _problema_condicion(c):
    """Texto del problema si `c` no es una condición utilizable (ver nucleo/indicadores.py); None si lo es."""
    if isinstance(c, type):
        return f"{c.__name__} sin paréntesis: escribe {c.__name__}(…) con sus valores"
    if hasattr(c, "condiciones"):                     # Todas(...), Alguna(...)
        if not isinstance(c.condiciones, (tuple, list)) or not c.condiciones:
            return (f"{type(c).__name__} necesita la lista de condiciones entre dobles paréntesis: "
                    f"{type(c).__name__}((c1, c2))")
        for sub in c.condiciones:
            if (p := _problema_condicion(sub)):
                return p
    if hasattr(c, "condicion"):                       # No(...)
        if (p := _problema_condicion(c.condicion)):
            return p
    if not (callable(getattr(c, "serie", None)) and callable(getattr(c, "describir", None))
            and hasattr(c, "sesiones")):
        return f"{c!r} no es una condición (las disponibles están en nucleo/indicadores.py)"
    return None


@dataclass(frozen=True)
class Activo:
    nombre: str
    ticker: str                      # ticker de Yahoo Finance
    divisa: str | None = None        # "EURUSD=X" pasa el precio de dólares a euros
    continuo: bool = False           # True si cotiza 24 h, 7 días (cripto)
    seguimiento: dict | None = None  # {nombre: condición}; None = SEGUIMIENTO de bot/config.py
    senal: object = None             # condición de la estrategia; None = sin estrategia
    en_cartera: str | None = None    # "AAAA-MM-DD" de la entrada real
    alarma: object = None            # condición que dispara una alarma al cumplirse
    recordatorio: str = ""           # texto que acompaña a la alarma
    posicion: str | None = None      # nombre de la posición en control/cartera.csv a la que corresponde (si la hay)

    def __post_init__(self):
        errores = []
        if not isinstance(self.nombre, str) or not self.nombre.strip():
            errores.append("el nombre está vacío")
        if not isinstance(self.ticker, str) or not self.ticker.strip():
            errores.append("el ticker está vacío")
        if self.seguimiento is not None and not isinstance(self.seguimiento, dict):
            errores.append('seguimiento debe ser {"nombre": condición, …}')
        condiciones = [("senal", self.senal), ("alarma", self.alarma)]
        if isinstance(self.seguimiento, dict):
            condiciones += [(f"seguimiento «{n}»", c) for n, c in self.seguimiento.items()]
        for campo, c in condiciones:
            if c is not None and (p := _problema_condicion(c)):
                errores.append(f"{campo}: {p}")
        if self.en_cartera is not None:
            try:
                date.fromisoformat(self.en_cartera)
            except (TypeError, ValueError):
                errores.append(f"en_cartera debe ser una fecha AAAA-MM-DD, no {self.en_cartera!r}")
        if self.recordatorio and self.alarma is None:
            errores.append("tiene recordatorio pero no alarma (el recordatorio acompaña a la alarma)")
        if errores:
            raise ValueError(f"Regla del activo {self.nombre!r} en bot/config.py: " + "; ".join(errores))
