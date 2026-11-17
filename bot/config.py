"""Configuración del bot: qué se vigila en cada activo y qué avisos se envían.

ESTA ES UNA CONFIGURACIÓN DE EJEMPLO: las reglas ilustran lo que permite el sistema, no son recomendaciones de
inversión. Pon las tuyas: cualquier activo de Yahoo Finance, con las condiciones que quieras (combinables con Todas,
Alguna y No). Lo que no cambies se queda como está aquí. Manual completo: docs/bot.md.

Cada activo puede tener:
- seguimiento: condiciones informativas; se avisa cuando cambian (por defecto, SEGUIMIENTO);
- senal: condición de la estrategia de una posición (entrada al cumplirse, salida al dejar de cumplirse);
- en_cartera: fecha de la entrada real; la posición figura DENTRO hasta la primera salida posterior;
- alarma: condición que, al cumplirse, envía una alarma (con un recordatorio opcional).
Las condiciones disponibles (cruces de medias, niveles de precio, caídas desde máximos, combinaciones…)
están en nucleo/indicadores.py. Para añadir un activo o cambiar una regla basta con editar este archivo.
"""
from dataclasses import dataclass

from nucleo.indicadores import (Alguna, CaidaDesdeMaximo, Cruce, MaximoMovil, MinimoMovil, Nivel,  # noqa: F401 (disponibles
                                No, SinNuevoMinimo, Todas, Variacion)                              # para las reglas)
from nucleo.sombra import Sombra  # noqa: F401 (para definir SOMBRA)


@dataclass(frozen=True)
class Activo:
    nombre: str
    ticker: str
    divisa: str | None = None        # "EURUSD=X" pasa el precio de dólares a euros
    continuo: bool = False           # True si cotiza 24 h, 7 días (cripto)
    seguimiento: dict | None = None  # {nombre: condición}; None = SEGUIMIENTO
    senal: object = None             # condición de la estrategia; None = sin estrategia
    en_cartera: str | None = None    # "AAAA-MM-DD" de la entrada real
    alarma: object = None            # condición que dispara una alarma al cumplirse
    recordatorio: str = ""           # texto que acompaña a la alarma
    posicion: str | None = None      # nombre de la posición en control/cartera.csv a la que corresponde (si la hay)


# Seguimiento por defecto de cada activo: tendencia de corto vs medio plazo y de medio vs largo plazo.
SEGUIMIENTO = {
    "Corto vs medio": Cruce(6, 70),
    "Medio vs largo": Cruce(70, 200),
}

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
    # Alarma de crisis sobre el mercado (no hace falta que sea una posición): salta cuando la media de 75 sesiones
    # cae por debajo de la de 500.
    Activo("S&P 500 (€)", "SPY", divisa="EURUSD=X",
           alarma=No(Cruce(75, 500)), recordatorio=RECORDATORIO_CRISIS),
    # Tendencias por defecto y una alarma de caída fuerte en un día.
    Activo("Nasdaq 100 (€)", "QQQ", divisa="EURUSD=X", alarma=Variacion(-0.03)),
    # Posición con estrategia: entra cuando SMA6 > SMA70 y sale cuando deja de cumplirse. `en_cartera` es la fecha de
    # la compra real y `posicion` la fila de control/cartera.csv a la que corresponde (lo comprueba universo.coherencia).
    Activo("Litio y baterías (€)", "LIT", divisa="EURUSD=X",
           senal=Cruce(6, 70), en_cartera="2026-06-01", posicion="Litio y baterías",
           # Salida previa: tendencia corta bajista y nuevo mínimo de 60 sesiones (solo mientras la posición está DENTRO).
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

# Cartera sombra: ideas en seguimiento simulado (sin dinero real), con su regla de salida desde el primer día.
# Se evalúan en el informe semanal (o en local con `python bot/informe.py --sombra`). El coste de ida y vuelta
# sale de python -m nucleo.costes (aquí, un ETF a 0,12 % por operación: 0,24 %).
SOMBRA = [
    Sombra("China (idea de ejemplo)", "MCHI", "2026-11-02", divisa="EURUSD=X", tesis="Valoración baja frente al resto del mundo",
           stop=0.12, plazo=250, coste=0.0024),
]
DIA_RESUMEN = 4  # 0 = lunes … 4 = viernes: día del resumen semanal de las alertas

# Si los workflows se lanzan desde fuera con un token de GitHub (p. ej. cron-job.org, ver docs/bot.md), pon aquí su
# fecha de caducidad ("AAAA-MM-DD") y las alertas avisarán TOKEN_AVISO_DIAS días antes. None = sin aviso.
TOKEN_CADUCA = None
TOKEN_AVISO_DIAS = 14

# --- Resumen diario con un modelo de lenguaje (bot/diario.py, bot/llm.py) ---
# Proveedor: "anthropic" u "openai"; con "openai" + DIARIO_URL sirve cualquier API compatible. Ejemplos:
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
