"""Tus reglas: qué vigila el bot y qué avisos te manda. Es el único archivo que hay que tocar para cambiarlas.

ESTO ES UN EJEMPLO: las reglas ilustran lo que permite el sistema, no son recomendaciones de inversión. Lo que no
cambies se queda como está. Manual completo: docs/bot.md («Alertas: reglas por activo»).

CÓMO AÑADIR UNA REGLA
1. Copia una línea de ACTIVOS (más abajo) y cambia el nombre, el ticker de Yahoo Finance y la condición.
   Ejemplo: Activo("Apple", "AAPL", alarma=Nivel(250)) avisa cuando Apple cierra por encima de 250 $.
2. Compruébalo: python -m nucleo.universo (dice si algo está mal escrito) y python bot/alertas.py --demo
   (muestra los avisos que saldrían hoy, sin enviar nada).
3. Súbelo a GitHub (o edítalo directamente en github.com): la siguiente ejecución ya usa la regla nueva.
También puedes pedírselo a una IA: «avísame si el oro cae un 10 % desde su máximo». Las instrucciones para la IA
están en ia/asistente-financiero/SKILL.md (ver README → «El día a día»).

CONDICIONES (nucleo/indicadores.py; los números son sesiones de bolsa o fracciones: 0.03 = 3 %)
  Cruce(6, 70)                 la media de 6 sesiones está por encima de la de 70 (Cruce(1, 200): precio > SMA200)
  Nivel(250)                   el precio está por encima de 250 (Nivel(250, encima=False): por debajo)
  Variacion(-0.03)             cae un 3 % o más en una sesión (Variacion(0.1, ventana=5): sube un 10 % en 5 sesiones)
  CaidaDesdeMaximo(0.2)        está un 20 % o más por debajo de su máximo de un año (252 sesiones)
  MaximoMovil(252)             cierra en máximo de 252 sesiones (MinimoMovil(60): en mínimo de 60 sesiones)
  SinNuevoMinimo(5, 60)        lleva 5 sesiones o más sin marcar un mínimo de 60 sesiones
  No(c)                        no se cumple c
  Todas((c1, c2))              se cumplen todas; Alguna((c1, c2)): se cumple alguna
                               (descripcion=("texto al cumplirse", "texto al dejar de cumplirse"), opcional)
Si te falta una condición, se añade como una clase nueva en nucleo/indicadores.py (ver docs/bot.md).

QUÉ PUEDE LLEVAR CADA ACTIVO (todo opcional salvo el nombre y el ticker)
  alarma=c, recordatorio="…"   aviso 🚨 cuando c pasa a cumplirse y ✅ cuando deja de cumplirse
  seguimiento={"nombre": c}    aviso 🔔 cuando cambia alguna; si no lo pones, se usa SEGUIMIENTO (dos tendencias)
  senal=c                      estrategia: 🟢 entrada cuando c pasa a cumplirse, 🔴 salida cuando deja de cumplirse
  en_cartera="AAAA-MM-DD"      fecha de tu compra real (la posición figura DENTRO hasta la primera salida)
  posicion="…"                 la fila de control/cartera.csv a la que corresponde (si es una posición tuya)
  divisa="EURUSD=X"            evalúa el precio en euros; continuo=True: cotiza 24 h, 7 días (cripto)
"""
from nucleo.indicadores import (Alguna, CaidaDesdeMaximo, Cruce, MaximoMovil, MinimoMovil, Nivel,  # noqa: F401
                                No, SinNuevoMinimo, Todas, Variacion)
from nucleo.reglas import Activo
from nucleo.sombra import Sombra  # noqa: F401

# ─────────────────────────────────────────── ALERTAS ───────────────────────────────────────────

# Seguimiento por defecto de cada activo: tendencia de corto vs medio plazo y de medio vs largo plazo.
SEGUIMIENTO = {
    "Corto vs medio": Cruce(6, 70),
    "Medio vs largo": Cruce(70, 200),
}

# Textos que acompañan a una alarma (opcionales). <b>…</b> se ve en negrita en Telegram.
RECORDATORIO_CRISIS = (
    "📌 <b>Recuerda</b>:\n"
    "• Es una alarma para revisar con calma, no una orden de venta.\n"
    "• Un cruce lento de medias (75/500) solo ayuda en caídas largas; en caídas rápidas llega tarde.\n"
    "• Antes de decidir, revisa tus notas (control/cartera.md) y tus límites (python -m nucleo.limites)."
)
RECORDATORIO_ORO = (
    "📌 <b>Oro: posible momento de aportar</b>\n"
    "• Es un aviso para estudiarlo, no una orden de compra.\n"
    "• Antes de operar: python -m nucleo.costes <importe> y python -m nucleo.limites."
)

ACTIVOS = [
    # Alarma de crisis sobre el mercado (no hace falta que sea una posición tuya):
    # salta cuando la media de 75 sesiones cae por debajo de la de 500.
    Activo("S&P 500 (€)", "SPY", divisa="EURUSD=X", alarma=No(Cruce(75, 500)), recordatorio=RECORDATORIO_CRISIS),

    # Las dos tendencias por defecto y una alarma de caída fuerte en un día.
    Activo("Nasdaq 100 (€)", "QQQ", divisa="EURUSD=X", alarma=Variacion(-0.03)),

    # Posición con estrategia: entra cuando SMA6 > SMA70 y sale cuando deja de cumplirse.
    # en_cartera es la fecha de la compra real y posicion, su fila de control/cartera.csv.
    # Alarma de salida previa: tendencia corta bajista y nuevo mínimo de 60 sesiones (solo mientras está DENTRO).
    Activo("Litio y baterías (€)", "LIT", divisa="EURUSD=X",
           senal=Cruce(6, 70), en_cartera="2026-06-01", posicion="Litio y baterías",
           alarma=Todas((No(Cruce(6, 70)), MinimoMovil(60)),
                        descripcion=("SMA6 bajo SMA70 y nuevo mínimo de 60 sesiones: salida previa",
                                     "deja de cumplirse la salida previa"))),

    # Seguimiento propio y una alarma compuesta: caída fuerte desde máximos y señales de suelo.
    Activo("Oro (€)", "GLD", divisa="EURUSD=X",
           seguimiento={
               "Corto vs corto": Cruce(6, 20),
               "Medio vs largo": Cruce(70, 200),
               "Mínimo de 60 sesiones": MinimoMovil(60),
           },
           alarma=Todas((CaidaDesdeMaximo(0.15, 252), Cruce(6, 20), Cruce(1, 6), SinNuevoMinimo(5, 60)),
                        descripcion=("con el oro ≥ 15 % bajo su máximo de un año, SMA6 supera a SMA20, el precio cierra "
                                     "sobre SMA6 y pasan 5 sesiones sin nuevo mínimo de 60 sesiones",
                                     "deja de cumplirse la señal")),
           recordatorio=RECORDATORIO_ORO),

    # Cripto: cotiza 24 h, 7 días (solo se evalúan velas cerradas). Aviso de nuevo máximo de un año.
    Activo("Bitcoin ($)", "BTC-USD", continuo=True, alarma=MaximoMovil(252)),
]

DIA_RESUMEN = 4  # día del resumen semanal de las alertas: 0 = lunes … 4 = viernes

# ───────────────────────────────────── CARTERA SOMBRA ─────────────────────────────────────

# Ideas en seguimiento simulado (sin dinero real), con su regla de salida desde el primer día.
# Se evalúan en el informe semanal (o en local con `python bot/informe.py --sombra`). El coste de ida y vuelta
# sale de python -m nucleo.costes (aquí, un ETF a 0,12 % por operación: 0,24 %).
SOMBRA = [
    Sombra("China (idea de ejemplo)", "MCHI", "2026-11-02", divisa="EURUSD=X", tesis="Valoración baja frente al resto del mundo",
           stop=0.12, plazo=250, coste=0.0024),
]

# ──────────────────────────────── RESUMEN DIARIO DE NOTICIAS ────────────────────────────────

# Proveedor de IA (bot/llm.py): "anthropic" u "openai"; con "openai" + DIARIO_URL sirve cualquier API compatible:
#   OpenAI:      DIARIO_PROVEEDOR = "openai";  DIARIO_MODELO = "gpt-4o-mini";  DIARIO_CLAVE = "OPENAI_API_KEY"
#   Gemini:      DIARIO_PROVEEDOR = "openai";  DIARIO_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
#   Ollama:      DIARIO_PROVEEDOR = "openai";  DIARIO_URL = "http://localhost:11434/v1";  DIARIO_MODELO = "llama3.1"
# Más detalles (y modelos que no aceptan temperature o max_tokens) en docs/bot.md → «Modelo de lenguaje».
DIARIO_PROVEEDOR = "anthropic"
DIARIO_MODELO = "claude-sonnet-4-5"   # cámbialo aquí si el proveedor retira el modelo
DIARIO_URL = None                     # None = la URL oficial del proveedor
DIARIO_CLAVE = "ANTHROPIC_API_KEY"    # variable de entorno (secret de GitHub) con la clave
DIARIO_PARAMETROS = {}                # campos extra o sustituidos de la petición (None quita uno)
DIARIO_MAX_TITULARES = 80             # titulares máximos que se pasan al modelo
# Quién es el inversor y ejemplos de noticia → posición, para las instrucciones del modelo (opcional).
DIARIO_INVERSOR = "un inversor particular español"
DIARIO_EJEMPLOS = ('resultados de grandes tecnológicas → "Tecnología EE. UU."; ventas de coches eléctricos → '
                   '"Litio y baterías"; regulación de las criptomonedas → "Bitcoin"')

# Fuentes del resumen diario (RSS): estas son un ejemplo; pon las que leas. Si alguna falla, el resumen lo indica.
FUENTES_RSS = {
    "Fed": "https://www.federalreserve.gov/feeds/press_all.xml",
    "BCE": "https://www.ecb.europa.eu/rss/press.xml",
    "CNBC Economía": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "CNBC Finanzas": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "CNBC Portada": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories",
    "Investing.com": "https://www.investing.com/rss/news_25.rss",
    "WSJ Mercados": "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
    "WSJ Economía": "https://feeds.content.dowjones.io/public/rss/socialeconomyfeed",
    "FT Mercados": "https://www.ft.com/markets?format=rss",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "The Block": "https://www.theblock.co/rss.xml",
    "Decrypt": "https://decrypt.co/feed",
}

# ───────────────────────────────────────── TÉCNICO ─────────────────────────────────────────

# Si los workflows se lanzan desde fuera con un token de GitHub (p. ej. cron-job.org, ver docs/bot.md), pon aquí su
# fecha de caducidad ("AAAA-MM-DD") y las alertas avisarán TOKEN_AVISO_DIAS días antes. None = sin aviso.
TOKEN_CADUCA = None
TOKEN_AVISO_DIAS = 14
