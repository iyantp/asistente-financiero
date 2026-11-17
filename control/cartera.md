# Notas de la cartera (ejemplo)

> **Cartera de ejemplo**, típica de un inversor indexado con algunos satélites. Los pesos están en `cartera.csv`; aquí van las tesis y las condiciones de salida, en texto libre. **El resumen diario envía este archivo al modelo de lenguaje** para que avise si una noticia toca alguna tesis o salida, así que conviene que sea breve y concreto. Los importes nunca se versionan: si quieres guardarlos, usa un archivo `*.local.*`, que git ignora.

## Núcleo (91 %)

Inversión a largo plazo con aportaciones periódicas; no se vende por movimientos de mercado.

- **Renta variable mundial (51 %)** y **pequeñas empresas de EE. UU. (5 %)**: crecimiento a largo plazo. La alarma de crisis del S&P 500 obliga a revisar, no a vender.
- **Bonos del Tesoro de EE. UU. (25 %)**: amortiguan las caídas de la bolsa cuando bajan los tipos.
- **Oro (10 %)**: diversificación frente a la inflación y a las crisis.

## Satélites (9 %)

Cada uno con tesis y salida definidas antes de entrar (límites en `perfil.toml`: 15 % en total y 5 % por posición).

- **Tecnología EE. UU. (Nasdaq 100, 4 %)**. Tesis: las grandes tecnológicas siguen creciendo más que el mercado. Salida: si su peso llega al límite del 5 % por satélite, se vende lo que exceda.
- **Litio y baterías (2 %)**. Tesis: demanda de baterías por el coche eléctrico y el almacenamiento de energía. Salida: cruce a la baja SMA6/SMA70 (estrategia en `bot/config.py`), con salida previa si además marca un mínimo de 60 sesiones. La tesis se invalida si se frena la venta de coches eléctricos en China.
- **Bitcoin (3 %)**. Tesis: reserva de valor alternativa a largo plazo. Sin salida por precio; se revisa si cambia la regulación en EE. UU. o en la UE.
