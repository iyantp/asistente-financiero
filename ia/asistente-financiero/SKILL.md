---
name: asistente-financiero
description: Úsala para mantener este repositorio del asistente financiero (alertas por Telegram, resumen de noticias, informe semanal): actualizar la cartera tras una compra, venta o aportación, crear o cambiar una alerta, ajustar límites, comisiones, variables o fuentes de noticias, o explicar un aviso del bot.
---

# Mantener el asistente financiero

Ayudas a una persona a mantener su copia de este repositorio. El bot se ejecuta en GitHub Actions y lee lo que hay en GitHub: **un cambio no tiene efecto hasta que está subido**. Tu trabajo es traducir lo que pide en lenguaje normal («he comprado 300 € de oro», «avísame si el bitcoin cae un 10 % en una semana») a cambios en los archivos de configuración, comprobarlos y dejarlos listos para subir.

No eres asesor financiero: das información y ejecutas lo que la persona decide. Si una regla o una operación contradice sus propios límites o notas, díselo antes de hacerla. Responde en su idioma, de forma breve y sin tecnicismos innecesarios.

## Dónde está cada cosa

Lee primero `README.md` (sección «Configúralo para ti») y, para las reglas, `docs/bot.md` («Alertas: reglas por activo»). Lo que vas a tocar casi siempre:

| Archivo | Qué es |
|---|---|
| `control/cartera.csv` | Las posiciones: `activo` (nombre), `bloque` (de `perfil.toml`), `peso` en % (suman 100), `corto` (nombre breve para los mensajes), `ticker` de Yahoo Finance que la aproxima, `divisa` (`EURUSD=X` si el ticker cotiza en dólares y la cartera se mide en euros; vacía si ya está en la moneda de la cartera), `aproximacion` (nota opcional). |
| `control/cartera.md` | Notas en texto libre: tesis y condición de salida de cada posición. El resumen diario se las pasa al modelo, así que deben ser breves. Sin pesos ni importes. |
| `bot/config.py` | Las reglas de alertas (`ACTIVOS`), la cartera sombra (`SOMBRA`), las fuentes de noticias (`FUENTES_RSS`) y el proveedor de IA (`DIARIO_*`). La cabecera del archivo resume todas las condiciones. |
| `control/perfil.toml` | Bloques de la cartera, límites de riesgo y comisiones del bróker. |
| `control/variables.toml`, `control/especificos.csv` | Variables de mercado generales y factores específicos de algunas posiciones. |
| `control/calendario.csv` | Eventos de la semana (bancos centrales, IPC…). |

No edites el código de `nucleo/` ni de `bot/` salvo que haga falta una condición nueva (ver más abajo).

## Privacidad

- Si el repositorio es público, todo lo que escribas en él es público. Antes de poner pesos o notas reales, comprueba (o pregunta) si el repositorio es privado.
- **Nunca escribas importes en euros, saldos ni datos de cuentas** en archivos versionados. La cartera se guarda en pesos. Si la persona quiere guardar importes, van en un archivo `*.local.*` (git lo ignora).
- Las claves (Telegram, IA) van en los *secrets* de GitHub o en `.env`, nunca en el código.

## Tareas habituales

### Actualizar la cartera (compra, venta, aportación, traspaso)

1. Pide solo lo que falte para recalcular los pesos: el **valor actual de cada posición** (o al menos de las que cambian y el total). Sin valores no se pueden recalcular los pesos: no los inventes.
2. Recalcula los pesos para que sumen 100 (un decimal) y actualiza `control/cartera.csv`.
3. Si entra una posición nueva: elige con la persona el `ticker` de Yahoo que mejor la aproxima (para un fondo sin ticker, un ETF del mismo índice), su `bloque`, su `corto` y su `divisa`. Añade su tesis y su salida a `control/cartera.md`.
4. Si sale una posición: quita su fila, sus notas y, en `bot/config.py`, sus reglas ligadas (`en_cartera`, `posicion` y la alarma de salida si la tenía).
5. Comprueba los límites: `python -m nucleo.limites`. Para valorar una operación antes de hacerla: `python -m nucleo.limites "Nombre=+2" "Otro=-2"` (puntos de peso) y `python -m nucleo.costes <importe>` (comisión de ida y vuelta, con `divisa` si hay cambio de moneda).
6. Si entra o sale una posición, o cambia un ticker, la matriz de exposición se regenera sola al subir el cambio (workflow `matriz`). En local: `python -m nucleo.exposiciones`.

### Crear o cambiar una alerta

1. Traduce lo que pide a una condición de la cabecera de `bot/config.py` (lista completa en `nucleo/indicadores.py`). Ejemplos:
   - «si el oro cae un 10 % desde su máximo» → `Activo("Oro", "GLD", alarma=CaidaDesdeMaximo(0.10))`
   - «si el bitcoin cae un 10 % en una semana» → `Activo("Bitcoin", "BTC-USD", continuo=True, alarma=Variacion(-0.10, ventana=7))` (en cripto, 7 velas son 7 días; en bolsa, una semana son 5 sesiones)
   - «si el S&P 500 pierde la media de 200 sesiones» → `Activo("S&P 500", "SPY", alarma=No(Cruce(1, 200)))`
   - «si Apple supera 250 $» → `Activo("Apple", "AAPL", alarma=Nivel(250))`
2. Si hay ambigüedad que cambia la regla (¿precio en euros o en dólares?, ¿cierre diario o en el momento?), pregunta. Recuerda a la persona que el bot evalúa **cierres diarios**: no avisa en el momento en que se cruza un nivel.
3. Para una posición suya, añade `posicion="<nombre exacto en cartera.csv>"`; si es una estrategia con fecha de compra, `senal=` y `en_cartera="AAAA-MM-DD"`.
4. Enséñale la línea y explícale en una frase qué mensaje recibirá y cuándo (🚨 al cumplirse, ✅ al dejar de cumplirse).
5. Si ninguna condición expresa la regla, añade una clase en `nucleo/indicadores.py` (con `serie`, `sesiones` y `describir`, como las demás) y su prueba en `tests/test_reglas.py` con una serie inventada de resultado conocido. No cambies el comportamiento de las condiciones existentes.

### Otros cambios

- Límites, bloques o comisiones: `control/perfil.toml`.
- Fuentes de noticias: `FUENTES_RSS` en `bot/config.py` (URL de un feed RSS).
- Proveedor o modelo de IA: `DIARIO_*` en `bot/config.py` y el secret con la clave (ver `docs/bot.md` → «Modelo de lenguaje»).
- Variables de mercado o factores específicos: `control/variables.toml` y `control/especificos.csv` (ver `docs/bot.md`). Es un cambio de método: explica a la persona qué implica antes de hacerlo.

### Explicar un aviso o un informe

Explica de dónde sale cada dato con `docs/bot.md` («Mensajes» e «Informes») y la regla correspondiente de `bot/config.py`. Un aviso es una señal para revisar, no una orden.

## Antes de terminar

1. `python -m nucleo.universo`: debe decir «Todo cuadra». Si no, corrige lo que indique.
2. `python bot/alertas.py --demo`: muestra los avisos que saldrían hoy, sin enviar nada.
3. `python tests/test_reglas.py`: todas las pruebas deben pasar.
4. Resume los cambios en dos o tres líneas. Si tienes acceso a git, haz un commit con un mensaje claro; súbelo (`git pull --rebase` y `git push`) si la persona lo quiere, o dile que lo haga. El bot también hace commits (registro, matriz), por eso el `pull --rebase`.

Si no puedes ejecutar órdenes (por ejemplo, en un chat sin acceso a los archivos), pide a la persona que te pegue el archivo que hay que cambiar, devuélvelo **completo** con el cambio hecho y dile que lo pegue en GitHub (botón del lápiz en el archivo → *Commit changes*). Al subirlo, el workflow `matriz` comprueba la configuración y GitHub le avisará por correo si algo no cuadra.
