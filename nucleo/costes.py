"""Comisiones de operar por plataforma, para valorar cualquier compra o venta ANTES de hacerla.

Las comisiones se configuran en control/perfil.toml ([comisiones.<plataforma>]). No se guardan importes reales: se
pasa el importe que se esté valorando. El coste continuo de un fondo o ETF (TER) es aparte.

Uso:  python -m nucleo.costes 5000            coste de comprar y vender 5.000 en cada plataforma
      python -m nucleo.costes 100 divisa      ídem para un valor que cotiza en otra divisa
"""
import sys

from nucleo import perfil


def _tarifa(plataforma, tarifas=None):
    tarifas = perfil.comisiones() if tarifas is None else tarifas
    if isinstance(plataforma, dict):
        return plataforma
    if plataforma not in tarifas:
        raise KeyError(f"plataforma {plataforma!r} no está en perfil.toml (hay: {', '.join(tarifas) or 'ninguna'})")
    return tarifas[plataforma]


def comision(plataforma, importe, divisa_ajena=False, tarifas=None):
    """Coste de UNA operación (compra o venta) de `importe`. `plataforma`: nombre de perfil.toml o la tarifa (dict)."""
    c = _tarifa(plataforma, tarifas)
    pct, minimo, maximo = c.get("porcentaje", 0.0), c.get("minimo", 0.0), c.get("maximo", 0.0)
    base = importe * pct
    if pct:
        base = max(base, minimo)
        if maximo:
            base = min(base, maximo)
    return base + (importe * c.get("cambio_divisa", 0.0) if divisa_ajena else 0.0)


def ida_y_vuelta(plataforma, importe, divisa_ajena=False, tarifas=None):
    """(coste, fracción del importe) de comprar y vender `importe`. Valores para Sombra.coste."""
    coste = 2 * comision(plataforma, importe, divisa_ajena, tarifas)
    return coste, coste / importe


if __name__ == "__main__":
    importe = float(sys.argv[1]) if len(sys.argv) > 1 else 1000.0
    ajena = "divisa" in sys.argv[2:]
    for p in perfil.comisiones():
        e, f = ida_y_vuelta(p, importe, ajena)
        print(f"{p:18s} {importe:>9,.0f}{' (divisa ajena)' if ajena else ''}: ida y vuelta {e:7.2f} = {f:.2%}".replace(",", "."))
