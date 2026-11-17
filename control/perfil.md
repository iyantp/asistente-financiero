# Perfil inversor (ejemplo)

> **Perfil de ejemplo.** En el repositorio público, `control/` contiene datos ficticios que muestran el formato. El sistema real usa los mismos archivos con los datos de su dueño, que no se publican.

## Objetivos

- **Ahorro a largo plazo** (horizonte de más de 10 años): crecer con la renta variable global, sin intentar adivinar el mercado.
- **Especulación acotada**: ideas con tesis escrita y salida definida desde el primer día, con un peso pequeño y limitado.
- Las reglas del bot son **avisos para revisar**, no órdenes automáticas: la decisión siempre es manual.

## Estructura de la cartera

Tres bloques (columna `bloque` de `cartera.csv`):

| Bloque | Qué es | Peso |
|---|---|---|
| `ahorro` | Fondos indexados y renta fija; se mantienen | ≥ 85 % |
| `cripto` | ETH y BTC, como apuesta de largo plazo de alta volatilidad | dentro del 15 % |
| `especulacion` | Ideas con tesis y salida | dentro del 15 %; ≤ 8 % cada una |

## Reglas

### Ahorro
- Aportaciones periódicas; no se vende por movimientos de mercado.
- La alarma de crisis del S&P 500 (cruce 75/500) solo obliga a **revisar** la situación.

### Cripto
- Peso máximo conjunto con la especulación: 15 %.

### Especulación
- Toda posición entra con: tesis escrita en `cartera.md`, regla de salida (en `bot/config.py`) y coste de ida y vuelta calculado (`python -m nucleo.costes`).
- Antes de entrar, la idea puede seguirse en la **cartera sombra** (`SOMBRA` en `bot/config.py`).

## Límites

Los comprueba `nucleo/limites.py` y salen en el informe semanal:

- Cripto + especulación ≤ 15 % del total.
- Cada posición especulativa ≤ 8 %.
- Ahorro ≥ 85 %.

## Plataformas

| Uso | Tipo de plataforma |
|---|---|
| Fondos indexados y ETF | Bróker con traspasos de fondos sin comisión |
| Renta fija | Bróker con acceso a bonos |
| Cripto | Cartera propia |

## Comisiones y costes de operar

Las comisiones por plataforma están en `nucleo/costes.py` (ETF: 0,12 % por operación, mínimo 1 €, máximo 25 €; cambio de divisa: 0,30 %; fondos: sin comisión de compra, venta ni traspaso). Para valorar una operación antes de hacerla:

```bash
python -m nucleo.costes 5000          # coste de comprar y vender 5.000 € de un ETF
python -m nucleo.costes 5000 divisa   # ídem si cotiza en otra divisa
```
