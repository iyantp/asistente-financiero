"""Envío de mensajes a Telegram y comprobación de secrets.

Modo demo (`--demo` en la línea de órdenes o FINANZAS_DEMO=1): no hace falta Telegram; los mensajes
se imprimen por pantalla en texto plano y los programas no escriben en registro/.
"""
import html
import os
import re
import sys

import requests
try:
    from dotenv import load_dotenv
    load_dotenv()  # lee .env en local; en GitHub Actions las variables vienen de los secrets
except ImportError:  # sin python-dotenv (pruebas): las variables se leen del entorno
    pass
LIMITE = 4096  # longitud máxima de un mensaje de Telegram
DEMO = "--demo" in sys.argv or os.environ.get("FINANZAS_DEMO") == "1"


def comprobar_secretos(*extra):
    """Sale si faltan variables de entorno. En modo demo no se piden las de Telegram, solo `extra`."""
    necesarias = extra if DEMO else ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", *extra)
    faltan = [v for v in necesarias if not os.environ.get(v)]
    if faltan:
        sys.exit(f"Faltan variables de entorno: {', '.join(faltan)}")


def texto_plano(msg):
    """Mensaje HTML de Telegram pasado a texto para la consola."""
    return html.unescape(re.sub(r"<[^>]+>", "", msg))


def enviar(msg):
    if DEMO:
        print(texto_plano(msg), end="\n\n" + "─" * 60 + "\n\n")
        return
    if len(msg) > LIMITE:
        msg = msg[: LIMITE - 20] + "\n…(recortado)"
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    datos = {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": msg, "parse_mode": "HTML",
             "disable_web_page_preview": True}
    requests.post(url, data=datos, timeout=15).raise_for_status()
