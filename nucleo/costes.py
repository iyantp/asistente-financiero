"""Comisiones de operar por plataforma, para valorar cualquier compra o venta ANTES de hacerla.

Fuente: lo confirmado por Iyán (31/10/2026); resumen legible en perfil.md, «Comisiones».
Las comisiones por operación dependen del importe, así que aquí no se guardan importes reales:
se pasa el importe que se esté valorando. El coste continuo de un fondo o ETF (TER) es aparte.

Uso:  python -m nucleo.costes 5000            coste de comprar y vender 5.000 € de un ETF en MyInvestor
      python -m nucleo.costes 100 divisa      ídem para un ETF que cotiza en otra divisa
"""
import sys

PLATAFORMAS = {
    # ETF en MyInvestor: 0,12 % por operación, mínimo 1 €, máximo 25 €. Cambio de divisa: 0,30 % (si el
    # valor cotiza en otra divisa). Sin comisión de custodia de valores.
    "myinvestor_etf": {"porcentaje": 0.0012, "minimo": 1.0, "maximo": 25.0, "cambio_divisa": 0.0030},
    # Fondos en MyInvestor: sin comisión de compra, venta ni traspaso por parte de MyInvestor
    # (la comisión de gestión del propio fondo va dentro del precio y no se calcula aquí).
    "myinvestor_fondo": {"porcentaje": 0.0, "minimo": 0.0, "maximo": 0.0, "cambio_divisa": 0.0},
}


def comision(plataforma, importe, divisa_ajena=False):
    """Euros que cuesta UNA operación (compra o venta) de `importe` euros."""
    c = PLATAFORMAS[plataforma]
    base = min(max(importe * c["porcentaje"], c["minimo"] if c["porcentaje"] else 0.0),
               c["maximo"] if c["porcentaje"] else 0.0)
    return base + (importe * c["cambio_divisa"] if divisa_ajena else 0.0)


def ida_y_vuelta(plataforma, importe, divisa_ajena=False):
    """(euros, fracción del importe) de comprar y vender `importe` euros. Valores para Sombra.coste."""
    euros = 2 * comision(plataforma, importe, divisa_ajena)
    return euros, euros / importe


if __name__ == "__main__":
    importe = float(sys.argv[1]) if len(sys.argv) > 1 else 1000.0
    ajena = "divisa" in sys.argv[2:]
    for p in PLATAFORMAS:
        e, f = ida_y_vuelta(p, importe, ajena)
        print(f"{p:18s} {importe:>9,.0f} €{' (divisa ajena)' if ajena else ''}: ida y vuelta {e:7.2f} € = {f:.2%}".replace(",", "."))
