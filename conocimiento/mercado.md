# Marco de seguimiento del mercado

Actualizado: 01/11/2026 (revisión del método: efecto típico, tipo a 2 años, comprobación con datos). Cómo estar informado de forma útil para la cartera: un conjunto pequeño y fijo de variables de estado, su efecto en cada posición y un protocolo para filtrar noticias y opiniones.

## Variables de estado

Variables generales que mueven a todos los activos. Los activos concretos (índices, oro, cripto…) no están aquí: son lo que estas variables explican, con la matriz de exposición, siguiendo el enfoque de arriba abajo (mercado → país → sector → índice → activo).

| Variable | Qué mide | Cómo se mide | Por qué importa |
|---|---|---|---|
| Tipos a largo | Coste del dinero y descuento del futuro | Bono a 10 años de EE. UU. (nominal y real) | Valora las acciones, sobre todo tecnología; mueve el precio del bono |
| Política monetaria | Expectativas sobre los bancos centrales | Bono a 2 años de EE. UU., Fed, BCE | Anticipa hacia dónde van los tipos |
| Inflación | Pérdida de poder adquisitivo | IPC de EE. UU. y zona euro, inflación esperada a 10 años | Objetivo de protegerse de ella; condiciona tipos y oro |
| Crecimiento | Fase del ciclo | PMI/ISM, empleo, revisiones de beneficios; cobre como aproximación de mercado | Sostiene la bolsa; las pequeñas empresas son las más sensibles |
| Dólar | Euro frente a dólar y ciclo global del dólar | EUR/USD y dólar amplio (frente a una cesta mundial) | ≈ 80 % de la cartera está en dólares sin cubrir; el dólar amplio afecta a materias primas y emergentes |
| Estrés | Riesgo de crédito y miedo | Diferencial de crédito corporativo (Baa frente al 10 años), VIX | Régimen del mercado; complementa la alarma de crisis |
| Sentimiento | Optimismo o pesimismo de los inversores | Encuestas (AAII), índices de miedo y codicia, ratio put/call | Útil sobre todo en los extremos, como señal contraria |
| Materias primas | Energía y metales | Petróleo, cobre, tierras raras | Alimentan la inflación; afectan a VanEck Rare Earth |
| Valoración | Lo caro que está el mercado | PER, CAPE, concentración en grandes empresas | Variable lenta: revisión trimestral |

## Matriz de exposición

Cómo responde cada posición a cada variable. Se estima con `python -m nucleo.exposiciones` (método en ese módulo; el cuaderno `analisis/exposiciones.ipynb` añade gráficos) y se guarda en `analisis/exposiciones.csv`: rentabilidad semanal de cada activo en euros frente a los cambios estandarizados de las variables (coeficiente = % semanal ante +1σ), desde 2012 y desde 2022 (régimen actual), con t de Newey-West y umbral del 1 %.

**Dos lecturas, cada una para un uso** (revisión del 01/11/2026):

| Lectura | Qué es | Para qué |
|---|---|---|
| **Efecto típico** (`efecto_*`, `lectura`) | regresión simple: qué hace el activo cuando la variable sube 1σ, con lo que suelen moverse a la vez las demás | interpretar noticias (una noticia nunca mueve una sola variable); leer la matriz |
| **Exposición directa** (`parcial_*`, `lectura_parcial`) | regresión múltiple: efecto de la variable con las demás fijas | repartir el movimiento de una semana entre variables (informe semanal), diagnosticar |

Con variables estandarizadas, $\gamma_k = \sum_j \beta_j \rho_{jk}$. Con variables correlacionadas difieren mucho: el EUR/USD y el dólar amplio tienen $\rho \approx -0{,}8$; los tipos reales y el tipo a 2 años también se mueven juntos.

Correspondencia entre variables y series (8 series para 7 de las 9 variables):

| Variable | Serie en la regresión | Aproximación diaria (resumen diario) |
|---|---|---|
| Tipos a largo | Tipo real a 10 años (FRED DFII10) | Bono a 10 años nominal (^TNX) |
| Política monetaria | Tipo a 2 años (FRED DGS2) | Futuro del bono a 2 años (ZT=F, signo invertido) |
| Inflación | Inflación esperada a 10 años (FRED T10YIE) | — (se usa la marca de sorpresa) |
| Crecimiento | Cobre (HG=F) | Cobre |
| Dólar | EUR/USD (FRED DEXUSEU + cola de Yahoo) y dólar amplio (FRED DTWEXBGS) | EUR/USD; cesta de 6 divisas (`CESTA_DOLAR` en `control/variables.toml`) |
| Estrés | Diferencial Baa frente al 10 años (FRED BAA10Y) | Bonos de alto riesgo (HYG, signo invertido); el VIX es solo informativo |
| Materias primas | Brent (FRED DCOILBRENTEU) | Brent (BZ=F) |
| Sentimiento | No entra: no hay series diarias gratuitas y fiables | — |
| Valoración | No entra: demasiado lenta para datos semanales | — (revisión trimestral a mano: CAPE, rentabilidad por beneficios frente al tipo real) |

El tipo a 2 años sustituye a la pendiente 10a-2a: con el tipo real y la inflación esperada en la regresión, el 10 años nominal queda fijo y la pendiente solo recogía $-\Delta$(2 años), con el signo cambiado. El diferencial de bonos de alto riesgo (ICE BofA) solo tiene 3 años en FRED: por eso se usa el Baa.

**Lectura del régimen actual (desde 2022; provisional hasta reejecutar el cuaderno con DGS2 real):**
- **Renta variable** (Vanguard, MSCI World, Russell): estrés −−, tipos reales −−, cobre ++, inflación esperada ++. Tecnología: estrés −−, cobre ++.
- **Dólar:** el efecto típico del EUR/USD y del dólar amplio sobre la renta variable en euros **no es significativo**. Al pasar a euros, un euro fuerte resta casi uno a uno (exposición directa −−−), pero de media lo compensa el resto: el dólar se aprecia cuando la bolsa cae (refugio) y se debilita cuando sube. Cuidado con las noticias de divisa que no vienen del riesgo (p. ej., una sorpresa del BCE que sube el euro sin mover la bolsa): ahí sí pesa la conversión, ≈ −1 × la parte en dólares (≈ 80 %).
- **Bono EE. UU.:** tipos reales −−, inflación esperada −, tipo a 2 años −, EUR/USD −− (su riesgo de divisa no se compensa), dólar amplio ++, estrés ++ (refugio).
- **VanEck Rare Earth:** cobre +++, dólar amplio −−−. **ETH:** estrés −−−. **BTC:** nada significativo.
- La comprobación de cobertura (`analisis/riesgo_cartera.py`) confirma la lectura del dólar: cubrir la divisa no reduce el riesgo de la renta variable (desde 2022 lo aumenta) y sí el del bono.

**Revisión:** cada trimestre, y siempre que entre un activo nuevo en la cartera. Comparar con la anterior con `git diff analisis/exposiciones.csv`.

**Cripto (contraste de octubre de 2026, `analisis/candidatas.ipynb`):** las variables de estado explican menos del 10 % del movimiento semanal de ETH y BTC; de ellas, solo el estrés de crédito es significativo. Ninguna variable de liquidez (liquidez neta de la Fed, M2, dólar amplio, stablecoins) cumple el criterio de forma estable. Desde 2022, cripto se mueve más con el Nasdaq (R² +0,04–0,06), lo que indica que añade riesgo parecido al tecnológico. Conclusión: cripto es un activo de factor propio; se sigue sobre todo por la vía sectorial (noticias que le afectan directamente y su tendencia de precio), no por las variables macro. Las variables del sector que siguen al precio (flujos de ETF, *funding*, dominancia) no se usan como explicativas porque serían circulares.

**Tierras raras (contraste de octubre de 2026, `analisis/candidatas.ipynb`):** las variables de estado explican el 27 % del VanEck Rare Earth (sobre todo el cobre). Lo que más explica son dos activos sectoriales: baterías y litio (LIT; el R² sube a 0,63, y a 0,74 desde 2022) y mineras globales (PICK; 0,51). También aportan, de forma estable, la bolsa china (+0,11) y el dólar amplio (+0,055, negativo: un dólar fuerte frente a la cesta mundial perjudica al ETF). Conclusión: el ETF se comporta sobre todo como una apuesta por el ciclo de los metales para baterías y la minería, con exposición a China; no como una apuesta específica por las tierras raras o la geopolítica de EE. UU. y sus aliados.

## Factores sectoriales

Capa intermedia entre las variables de estado y cada activo (mercado → sector → activo). Son activos de referencia que explican una posición mejor que las variables generales; no entran en la matriz, pero se siguen en el informe semanal y orientan el resumen diario (una noticia que mueve el factor afecta directamente a la posición). Se descubren contrastando candidatas con la misma regresión que la matriz (cuánto R² añaden a las variables de estado) y se definen en `control/variables.toml` (`[factores]`).

| Posición | Factores | Evidencia |
|---|---|---|
| VanEck Rare Earth | Baterías y litio (LIT), mineras globales (PICK), bolsa china (MCHI) | R² de 0,27 a 0,63 con LIT; estables en ambos regímenes |
| ETH, BTC | Nasdaq 100 (QQQ) | Desde 2022, R² +0,04–0,06 |

## Protocolo para noticias y opiniones

Cinco preguntas en orden; si la respuesta es "no", se descarta:

1. ¿Qué variable mueve y en qué dirección?
2. ¿Se ha movido de verdad? Comprobarlo en los datos, frente a lo que es normal para esa variable.
3. ¿Era una sorpresa o ya estaba descontado? La mejor prueba es la propia reacción del mercado: un movimiento grande para lo normal ($|z|$ alto) es sorpresa; uno normal, descontado.
4. ¿A qué posiciones afecta, según el **efecto típico** de la matriz, y cuánto pesa en la cartera?
5. ¿Toca alguna tesis o condición de salida de `control/cartera.md`?

Cómo lo aplica el resumen diario (`bot/diario.py`): el modelo solo clasifica (pregunta 1); el código decide el resto. Pasos 2 y 3: $|z| \ge 1{,}5$ en la aproximación diaria de la variable (la dirección es la del dato, no la del titular); si la variable no tiene dato diario, se usa la marca de sorpresa del modelo. Paso 4: suma de peso × efecto típico, y se descarta si es menor que 0,1 % por σ. El mensaje muestra el $z$ y el efecto estimado en la cartera.

Las opiniones de expertos (José Luis Cava, otros) se traducen a variable, dirección y horizonte para poder contrastarlas con los datos.

Recordatorio: el sentimiento de las noticias no predice los precios (en un estudio con 14 modelos y 1.350 noticias, ninguno lo hizo mejor que el azar; arXiv 2505.14918). Las noticias sirven para entender qué variable se ha movido y por qué, no para decidir operaciones. Por eso `analisis/evaluar_registro.py` no mide si una noticia anticipa el precio a semanas vista, sino si la cartera se movió como decía la matriz en la sesión medida y en la de publicación.

## Cadencia

| Frecuencia | Contenido |
|---|---|
| Diario | Vídeo de José Luis Cava y alertas del bot |
| **Lunes** | Informe semanal: variables con movimientos anómalos, impacto en la cartera según la matriz, tesis afectadas y eventos de la semana |
| Por evento | Comunicados de la Fed y del BCE tras sus reuniones; sorpresas en datos clave (IPC, empleo) |
| Trimestral | Previsiones de las grandes gestoras, valoración, revisión de pesos y tesis, y actualización de la matriz |

En cada producto, un concepto técnico explicado.

## Fuentes

- **José Luis Cava**: diario; mercado, análisis técnico y sus propias estrategias.
- **Juan Ramón Rallo**: economía.
- **Odd Lots** (Bloomberg, pódcast): pendiente de probar; funcionamiento de mercados con expertos.
- **Fed y BCE**: comunicados oficiales.
- **Grandes gestoras** (Vanguard, BlackRock…): previsiones trimestrales.
