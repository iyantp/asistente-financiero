# Manual del bot y guía de puesta en marcha

**Español** · [English](bot.en.md)

Qué hace cada programa y cómo montar tu propio bot. El mapa del repositorio está en el [README](../README.md).

## Índice

1. [Datos](#datos)
2. [Alertas: reglas por activo](#alertas-reglas-por-activo)
3. [Mensajes](#mensajes)
4. [Variables generales, factores específicos y matriz de exposición](#variables-generales-factores-específicos-y-matriz-de-exposición)
5. [Informes](#informes)
6. [Modelo de lenguaje](#modelo-de-lenguaje)
7. [Disciplina: límites, registro y cartera sombra](#disciplina-límites-registro-y-cartera-sombra)
8. [Puesta en marcha paso a paso](#puesta-en-marcha-paso-a-paso)
9. [Programar las ejecuciones](#programar-las-ejecuciones)
10. [Adaptar el sistema a tu cartera](#adaptar-el-sistema-a-tu-cartera)
11. [Dependencias](#dependencias)

Todo lo que se configura tiene un valor de ejemplo (el mío): lo que no cambies se queda así.

## Datos

- **Precios:** Yahoo Finance (`yfinance`), cierres diarios ajustados por dividendos. **Series macro:** FRED, sin clave.
- Cada descarga se guarda en `datos/<ticker>_<periodo>.csv` (carpeta ignorada por git). Si una descarga falla, se usa esa copia con un aviso; con `FINANZAS_SIN_RED=1` se usan siempre las copias, lo que sirve para trabajar sin conexión.
- **Paso a euros:** `nucleo.datos.cambio_eurusd()` toma el histórico de FRED (DEXUSEU, mediodía de Nueva York) y completa los últimos días, que FRED aún no ha publicado, con Yahoo. Desde 2011, aproximadamente, Yahoo fecha las velas de divisas al inicio del día en Londres (su valor del día $t$ es el de la noche de $t-1$), así que esa cola se desplaza una vela (`alinear_fx`).

## Alertas: reglas por activo

Las reglas son tuyas: cada activo de `bot/config.py` es un `Activo(nombre, ticker, divisa=…, …)` sobre cualquier ticker de Yahoo Finance (acciones, ETF, índices, divisas, materias primas, cripto), y puede tener cuatro tipos de regla. Todas usan **condiciones** de `nucleo/indicadores.py`, que se evalúan sobre los cierres diarios (en euros si el activo lleva `divisa`):

| Regla | Para qué | Aviso |
|---|---|---|
| `seguimiento` | Información de contexto (por defecto, `SEGUIMIENTO`: tendencias de corto vs medio y de medio vs largo plazo) | 🔔 cuando alguna condición cambia |
| `senal` | Estrategia de una posición | 🟢 entrada al cumplirse, 🔴 salida al dejar de cumplirse |
| `en_cartera` | Fecha de la compra real | La posición figura DENTRO hasta la primera salida posterior, aunque se entrara antes de que la condición se cumpliera |
| `alarma` | Situaciones que obligan a revisar | 🚨 al cumplirse (con `recordatorio` opcional), ✅ al dejar de cumplirse |

Además, `posicion` indica a qué fila de `control/cartera.csv` corresponde la regla (el informe semanal avisa si la posición ya no está en la cartera y la regla sigue puesta), y `continuo=True` marca los activos que cotizan 24 horas (cripto).

Condiciones disponibles (ampliables con una clase nueva en `nucleo/indicadores.py` y su prueba en `tests/`):

| Condición | Se cumple cuando… |
|---|---|
| `Cruce(a, b)` | la media de `a` sesiones está por encima de la de `b` (`a=1` es el precio) |
| `Nivel(x, encima=True)` | el precio está por encima (o por debajo) de `x` |
| `Variacion(-0.03)` / `Variacion(0.1, ventana=5)` | el precio cae un 3 % o más en una sesión / sube un 10 % o más en 5 sesiones |
| `CaidaDesdeMaximo(0.2, 252)` | el precio ha caído un 20 % o más desde su máximo de 252 sesiones |
| `MaximoMovil(252)` | el cierre supera el máximo de los 252 cierres anteriores (nuevo máximo de un año) |
| `MinimoMovil(60)` | el cierre queda por debajo del mínimo de los 60 cierres anteriores |
| `SinNuevoMinimo(5, 60)` | han pasado al menos 5 sesiones desde el último cierre en mínimo de 60 sesiones |
| `No(c)` | no se cumple `c` |
| `Todas((c1, c2, …), descripcion=(si, no))` | se cumplen todas (`descripcion`, opcional, es el texto de los mensajes) |
| `Alguna((c1, c2, …), descripcion=(si, no))` | se cumple al menos una |

Ejemplos:

```python
Activo("Apple", "AAPL", alarma=Nivel(250))                                     # el precio supera 250 $
Activo("Nasdaq 100", "QQQ", alarma=Variacion(-0.03))                           # cae un 3 % o más en un día
Activo("Bitcoin", "BTC-USD", continuo=True, alarma=MaximoMovil(252))           # nuevo máximo de un año
Activo("Oro", "GLD", seguimiento={"Corto": Cruce(6, 20), "Largo": Cruce(70, 200)})   # tendencias propias
```

Una posición con estrategia y salida previa:

```python
Activo("Litio y baterías (€)", "LIT", divisa="EURUSD=X",
       senal=Cruce(6, 70), en_cartera="2026-06-01", posicion="Litio y baterías",
       alarma=Todas((No(Cruce(6, 70)), MinimoMovil(60))))
```

**Cuándo se evalúa.** Solo velas cerradas: en bolsa, la sesión del día (fines de semana y festivos no hay sesión nueva); en cripto, la vela del día anterior, que cierra a las 00:00 UTC. El bot no guarda estado: cada ejecución reconstruye las medias con el histórico. Si se salta una ejecución, ese cambio no se avisa, pero el resumen semanal muestra el estado correcto.

## Mensajes

- 🚨 **Alarma** / ✅ **Fin de la alarma**: la condición de alarma pasa a cumplirse o deja de hacerlo, con su recordatorio.
- 🟢 **Señal de ENTRADA**: la condición de la estrategia pasa a cumplirse en un activo sin posición.
- 🟢 **Tendencia confirmada**: la condición pasa a cumplirse estando ya dentro; desde entonces, la salida es cuando deje de cumplirse.
- 🔴 **Señal de SALIDA**: la condición deja de cumplirse por primera vez tras la entrada.
- 🔔 **Cambio de tendencia**: alguna condición de seguimiento cambia. Agrupa los cambios del día.
- 📋 **Resumen**: el día `DIA_RESUMEN` (por defecto, el viernes), el estado de cada condición, de las posiciones (🟢 DENTRO, 🔴 FUERA con la fecha de salida, ⚪ sin posición) y las alarmas activas.
- ⚠️ **Datos desactualizados**: la última vela de un activo tiene más de 5 días.
- 🔑 **Renueva el token**: si configuras `TOKEN_CADUCA`, desde 14 días antes de que caduque.
- ❌ **Error**: algo ha fallado; la ejecución queda en rojo en GitHub Actions.

## Variables generales, factores específicos y matriz de exposición

El método es fijo; las variables son configuración. Hay dos capas:

**Variables generales** (`control/variables.toml`), que mueven a todos los activos:

- **`[variables]`**: las variables de estado, cada una con su fuente (`fred` o `yahoo`), su código, cómo se mide su cambio (`dif` para tipos y diferenciales, `log` para precios), si entra en la matriz y, opcionalmente, un nombre corto y qué significa que suba (se lo dice al modelo que clasifica noticias).
- **`[diarias]`**: aproximaciones con dato diario fresco para comprobar si una variable se ha movido de verdad el día de una noticia (FRED publica con retraso). Pueden ser un ticker o una **cesta** (`[cestas]`: suma ponderada de cambios logarítmicos).
- **`[parametros]`**: inicio de la muestra y fecha de cambio de régimen.

**Factores específicos** (`control/especificos.csv`): activos de referencia que explican una o pocas posiciones mejor que las variables generales. En el ejemplo, las mineras y la bolsa china para el ETF de litio, y el Nasdaq para el bitcoin. Es una tabla con tres columnas: `factor` (nombre), `ticker` (Yahoo Finance) y `posiciones` (las de `cartera.csv` a las que explica, separadas por `;`). Se siguen en el informe semanal y orientan el resumen diario: una noticia que mueve el factor afecta directamente a esas posiciones. Un mismo factor puede servir a varias posiciones.

Con las variables, `python -m nucleo.exposiciones` calcula la **matriz de exposición** (`analisis/exposiciones.csv`): para cada activo de la cartera y cada variable, cuánto se mueve el activo en una semana cuando la variable se mueve una desviación típica. Da dos lecturas: el **efecto típico** (regresión simple, incluye cómo se mueven a la vez las demás variables; es lo que usa el resumen diario para las noticias) y la **exposición directa** (regresión múltiple, con las demás fijas; es lo que usa el informe semanal para atribuir la semana). El método completo está documentado en [`nucleo/exposiciones.py`](../nucleo/exposiciones.py).

Regenera la matriz al cambiar las variables o la cartera, y cada trimestre. `python -m nucleo.universo` comprueba que el archivo está bien escrito y que todo cuadra; si la matriz no corresponde a las variables actuales, los programas lo dicen en vez de fallar sin explicación.

## Informes

| Informe | Qué contiene |
|---|---|
| 📰 **Resumen diario** (`bot/diario.py`) | Titulares de las fuentes RSS de `config.FUENTES_RSS` desde el último cierre de Wall Street. El modelo (temperatura 0, sin búsqueda web) solo agrupa y clasifica por variable de estado; el código decide con reglas fijas: la variable debe haberse movido de verdad ($\lvert z \rvert \ge 1{,}5$ en su aproximación diaria; si no tiene dato diario, se usa la marca de sorpresa del modelo) y tener un efecto típico en la cartera de al menos un 0,1 % por desviación típica semanal. Hasta 3 noticias con su $z$, el efecto estimado en la cartera, las posiciones afectadas y las fuentes. Si la API falla (por ejemplo, sin saldo), avisa por Telegram. Prueba de consistencia: `python bot/diario.py --prueba 3`. |
| 📊 **Informe semanal** (`bot/informe.py`) | Límites del perfil, cartera sombra, coherencia de la cartera (solo si algo no cuadra), variables destacadas (movimiento anómalo o nivel extremo en 5 años), qué parte de la semana de la cartera explica cada variable, factores sectoriales de cada posición y eventos de la semana (`control/calendario.csv`). Las series que aún no tienen dato de la semana (FRED publica con retraso) se indican y no entran en el cálculo. Solo cálculo, sin IA. |

Las variables y la matriz se explican en [Variables generales, factores específicos y matriz de exposición](#variables-generales-factores-específicos-y-matriz-de-exposición); el resumen técnico, en el [apéndice del README](../README.md#apéndice-técnico).

## Modelo de lenguaje

Solo lo usa el resumen diario, y solo para agrupar y clasificar titulares. Se configura en `bot/config.py`:

| Opción | Qué es | Por defecto |
|---|---|---|
| `DIARIO_PROVEEDOR` | `"anthropic"` u `"openai"`; este último sirve para cualquier API compatible con la de OpenAI | `"anthropic"` |
| `DIARIO_MODELO` | Nombre del modelo en ese proveedor | `"claude-sonnet-4-5"` |
| `DIARIO_URL` | URL de la API; `None` = la oficial del proveedor | `None` |
| `DIARIO_CLAVE` | Nombre de la variable de entorno (y del secret de GitHub) con la clave | la habitual del proveedor |
| `DIARIO_PARAMETROS` | Campos extra o sustituidos de la petición; `None` quita uno | `{}` |
| `DIARIO_INVERSOR`, `DIARIO_EJEMPLOS` | Quién es el inversor y ejemplos de noticia → posición, para las instrucciones del modelo | genéricos |

Ejemplos:

```python
# OpenAI
DIARIO_PROVEEDOR, DIARIO_MODELO, DIARIO_CLAVE = "openai", "gpt-4o-mini", "OPENAI_API_KEY"
# Google Gemini (API compatible con OpenAI)
DIARIO_PROVEEDOR, DIARIO_MODELO = "openai", "gemini-2.5-flash"
DIARIO_URL, DIARIO_CLAVE = "https://generativelanguage.googleapis.com/v1beta/openai", "LLM_API_KEY"
# Ollama en tu ordenador (sin clave; solo para pruebas en local, GitHub Actions no lo ve)
DIARIO_PROVEEDOR, DIARIO_MODELO, DIARIO_URL = "openai", "llama3.1", "http://localhost:11434/v1"
# Modelos de razonamiento de OpenAI, que no aceptan temperature ni max_tokens
DIARIO_PARAMETROS = {"temperature": None, "max_tokens": None, "max_completion_tokens": 4000}
```

El workflow `diario` pasa al programa los secrets `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` y `LLM_API_KEY`: crea el que nombre `DIARIO_CLAVE`. Los nombres de los modelos cambian con el tiempo; si uno se retira, el resumen avisa por Telegram con la pista de qué cambiar.

## Disciplina: límites, registro y cartera sombra

| Herramienta | Qué hace | Cómo se usa |
|---|---|---|
| **Límites** (`nucleo/limites.py`) | Compara los pesos de `control/cartera.csv` con los límites de `control/perfil.toml`: máximos para la suma de unos bloques, máximos por posición y mínimos (en el ejemplo, satélites ≤ 15 % y ≤ 5 % cada uno). Avisa «cerca» desde el 90 % del límite. | Sale en el informe semanal. En local, `python -m nucleo.limites "Bitcoin=+1" "Renta variable mundial=-1"` simula una operación antes de hacerla. |
| **Registro de decisiones** (`nucleo/registro.py`) | Cada alerta y cada noticia del resumen diario (también las descartadas, como control) se anota con la dirección que se espera del precio, la variable y su $z$. | `python analisis/evaluar_registro.py`: qué hizo el precio después. Con pocas filas no se concluye nada. |
| **Cartera sombra** (`nucleo/sombra.py`, `SOMBRA` en `bot/config.py`) | Sigue ideas sin dinero real, con su regla de salida desde el primer día: condición de `indicadores.py`, caída máxima desde el pico, `stop` (caída fija desde el precio de entrada) o plazo. Descuenta costes (`coste` es obligatorio). | Añadir `Sombra(...)` a `SOMBRA`; sale en el informe semanal. En local, `python bot/informe.py --sombra`. |
| **Costes** (`nucleo/costes.py`) | Comisiones por plataforma, configuradas en `control/perfil.toml` (en el ejemplo: ETF al 0,12 %, mínimo 1 €, máximo 25 €, cambio de divisa 0,30 %; fondos sin comisión). | `python -m nucleo.costes 5000` o `python -m nucleo.costes 100 divisa`. |

## Puesta en marcha paso a paso

Antes de nada, prueba en local con `--demo` (ver el [README](../README.md#pruébalo)): imprime los mensajes en vez de enviarlos y no escribe en `registro/`.

### 1. Copia el repositorio

Haz un *fork* en GitHub (o crea un repositorio a partir de una copia). Si vas a poner tus pesos reales, que sea **privado**. Los importes en euros no se versionan nunca: si quieres guardarlos, usa un archivo `*.local.*`, que está en `.gitignore`.

### 2. Crea el bot de Telegram

1. En Telegram, abre una conversación con **@BotFather**, envía `/newbot` y sigue las instrucciones. Te dará el **token** del bot (algo como `123456789:AA…`).
2. Abre una conversación con tu bot nuevo y envíale cualquier mensaje.
3. Visita `https://api.telegram.org/bot<TOKEN>/getUpdates` en el navegador: en la respuesta, `"chat":{"id": …}` es tu **chat_id**.

### 3. (Opcional) Clave del modelo de lenguaje

Solo para el resumen diario. Por defecto usa Anthropic: crea una clave en [console.anthropic.com](https://console.anthropic.com) y añade saldo. Para otro proveedor, ver [Modelo de lenguaje](#modelo-de-lenguaje). Cada resumen es una sola llamada con, como mucho, 80 titulares.

### 4. Añade los secrets

En tu repositorio: *Settings → Secrets and variables → Actions → New repository secret*:

| Secret | Para |
|---|---|
| `TELEGRAM_BOT_TOKEN` | todos |
| `TELEGRAM_CHAT_ID` | todos |
| `ANTHROPIC_API_KEY` (u `OPENAI_API_KEY` o `LLM_API_KEY`, el que nombre `DIARIO_CLAVE`) | resumen diario |

En local, copia `.env.example` a `.env` y rellénalo (`.env` está en `.gitignore`).

### 5. Pruébalo

*Actions → alertas → Run workflow*, marcando «resumen», debería mandarte el resumen del estado de cada activo. Haz lo mismo con `informe` y `diario`.

Los workflows `alertas` y `diario` hacen commit de `registro/` al terminar (necesitan `permissions: contents: write`, que ya llevan). Por eso, antes de hacer push en local, conviene hacer `git pull --rebase`.

## Programar las ejecuciones

Los workflows solo tienen `workflow_dispatch` (lanzamiento manual o por la API). Hay dos formas de programarlos:

**Opción A: `schedule` de GitHub (la más sencilla).** Añade al bloque `on:` de cada workflow, por ejemplo en `alertas.yml`:

```yaml
on:
  schedule:
    - cron: "15 22 * * *"   # todos los días a las 22:15 UTC
  workflow_dispatch:
```

Ojo: GitHub no garantiza la hora. En mi caso retrasaba las ejecuciones varias horas o se las saltaba, y por eso uso la opción B.

**Opción B: cron-job.org (hora exacta).** [cron-job.org](https://console.cron-job.org) es gratuito y lanza el workflow con la misma llamada que el botón *Run workflow*:

1. Crea en GitHub un **token fine-grained** (*Settings → Developer settings → Fine-grained tokens*) con acceso **solo a tu repositorio** y el permiso **Actions: Read and write**. No puede tocar el código ni leer los secrets.
2. En cron-job.org, crea un trabajo por workflow:
   - URL: `https://api.github.com/repos/<usuario>/<repo>/actions/workflows/<workflow>.yml/dispatches` (siempre `https`: cron-job.org no sigue redirecciones).
   - Método `POST`; cuerpo `{"ref":"main"}`.
   - Cabeceras: `Accept: application/vnd.github+json`, `Authorization: Bearer <token>`, `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.
   - Respuesta correcta: `204`. Activa el aviso por correo si falla.
3. Pon la fecha de caducidad del token en `TOKEN_CADUCA` (`bot/config.py`): las alertas te avisarán 14 días antes. Si el token caduca, el bot deja de ejecutarse sin avisar.

El horario es tuyo, con dos condiciones que imponen los programas:

- **`alertas`**: después del cierre de EE. UU. (16:00 en Nueva York: 21:00 UTC, o 20:00 UTC con el horario de verano de EE. UU.) y antes de las 00:00 UTC. Compara la última vela con la fecha del día en UTC: si se ejecuta pasada la medianoche UTC, ese día no avisa de los cambios en bolsa.
- **`diario`**: lee los titulares publicados desde el cierre de Wall Street del día hábil anterior, así que tiene sentido antes de la apertura.

El `informe` puede ir cualquier día; resume la última semana completa. Horario de ejemplo (Europe/Madrid): `diario` de lunes a viernes a las 06:20; `informe` los lunes a las 06:40; `alertas` todos los días a las 23:15. El día del resumen semanal de las alertas es `DIA_RESUMEN` en `bot/config.py` (por defecto, el viernes).

## Adaptar el sistema a tu cartera

| Si cambias… | Haz esto |
|---|---|
| Una posición | Su fila en `control/cartera.csv` (nombre, bloque, peso, nombre corto, ticker de Yahoo que la aproxima, divisa: vacía si ya está en tu moneda) y su tesis en `control/cartera.md`. Después, `python -m nucleo.exposiciones` para regenerar la matriz. |
| Una regla del bot | `bot/config.py` (con `posicion=` si es de una posición de la cartera). |
| Un tipo de condición | Una clase en `nucleo/indicadores.py` con `serie()`, `describir()` y `sesiones`, y su prueba en `tests/`. |
| Una variable general o una aproximación diaria | `control/variables.toml`; después, `python -m nucleo.exposiciones`. |
| Un factor específico | Su fila en `control/especificos.csv`. |
| Los bloques, los límites o las comisiones | `control/perfil.toml`. |
| Fuentes de noticias | `FUENTES_RSS` en `bot/config.py`. |
| El modelo de lenguaje | `DIARIO_*` en `bot/config.py` (ver [Modelo de lenguaje](#modelo-de-lenguaje)). |
| Un archivo nuevo que lea el código | Su ruta en `nucleo/rutas.py`, y en ningún otro sitio. |

Tras cualquier cambio: `python -m nucleo.universo` (¿cuadra todo?) y `python tests/test_reglas.py`. La prueba `test_coherencia_de_los_archivos_reales` comprueba que la cartera, las variables, la matriz y las reglas del bot cuadran entre sí.

Mantenimiento: `control/calendario.csv` cada trimestre y la matriz de exposición cada trimestre o al entrar un activo nuevo.

## Dependencias

`requirements.txt` lista lo que usa el bot (e instala el paquete `nucleo` en modo editable); `requirements.lock` fija las versiones exactas (Python 3.12, Linux) que instalan los workflows, para que una versión nueva de `yfinance` o `pandas` no rompa el bot sin haber tocado el código. Para actualizarlas:

```bash
uv pip compile requirements.txt --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --no-emit-package finanzas --upgrade -o requirements.lock
```

Al hacer push, el workflow `tests` ejecuta `tests/` con esas versiones. Va aparte de los del bot, para que una prueba rota no bloquee las alertas.
