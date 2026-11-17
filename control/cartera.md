# Cartera (ejemplo)

> **Cartera ficticia.** Los activos son reales (para que el bot y los análisis funcionen con datos de mercado), pero los pesos, fechas y tesis son de ejemplo. Los importes nunca se versionan: irían en `cartera.local.md`, ignorado por git.

## Pesos

Los pesos (y el bloque de cada posición) están **solo en `cartera.csv`**, el registro único que leen el bot, los informes y los límites. Para verlos: `python -m nucleo.limites`.

## Posiciones

| Posición | Bloque | Aproximación en Yahoo |
|---|---|---|
| Vanguard U.S. 500 (fondo indexado) | Ahorro | SPY |
| Amundi MSCI World (fondo indexado) | Ahorro | URTH |
| Fidelity Global Tech (fondo sectorial) | Ahorro | IXN |
| Bono del Tesoro de EE. UU. 2035 | Ahorro (renta fija) | IEF |
| ETH | Cripto | ETH-USD |
| BTC (WBTC) | Cripto | BTC-USD |
| VanEck Rare Earth (ETF) | Especulación | REMX |

## Estrategia por posición

### Ahorro: renta variable
Se mantiene a largo plazo con aportaciones periódicas. Sin regla de salida; la alarma de crisis del S&P 500 obliga a revisar, no a vender.

### Ahorro: renta fija
Bono a vencimiento: amortigua las caídas de la renta variable cuando bajan los tipos.

### Cripto
Apuesta de largo plazo con peso pequeño. El bot sigue sus tendencias; no hay regla de salida.

### Especulación
**VanEck Rare Earth.** Tesis: la demanda de tierras raras para baterías y defensa y la búsqueda de proveedores fuera de China. Factores que la explican (en `control/variables.toml`, `[factores]`): baterías y litio (LIT), mineras globales (PICK) y bolsa china (MCHI).
Salida: cruce a la baja SMA6/SMA70 (`senal` en `bot/config.py`), con salida previa si además marca un nuevo mínimo de 60 sesiones. La tesis se invalida si cambia la política de exportaciones de China.

## Seguimiento en el bot

Las reglas de cada activo están en `bot/config.py`; el manual, en `docs/bot.md`.
