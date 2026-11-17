"""Resumen diario de noticias con la API de Anthropic.

Reparto de tareas para que el resultado sea consistente:
- El código descarga los titulares de una lista fija de fuentes RSS (config.FUENTES_RSS),
  publicados desde el último cierre de Wall Street.
- El modelo (temperatura 0, sin búsqueda web) solo agrupa y clasifica esos titulares:
  variable de estado que mueven, dirección, sorpresa e impacto.
- El código decide con reglas fijas qué es relevante, el efecto en la cartera y las
  posiciones afectadas, a partir de analisis/exposiciones.csv y cartera.csv:
  · usa el EFECTO TÍPICO de cada variable (regresión simple, incluye cómo se mueven a la vez las
    demás), no la exposición directa (que supone las demás variables quietas);
  · comprueba con datos si la variable se movió de verdad (pasos 2 y 3 del protocolo): |z| del
    último cambio de su aproximación diaria (universo.DIARIAS) ≥ UMBRAL_Z; la dirección es la del
    dato. Si la variable no tiene dato diario, se usa la marca de sorpresa del modelo.
Si algo falla (por ejemplo, sin saldo en la API), avisa por Telegram.

Configurable sin tocar este archivo: las variables, aproximaciones diarias y factores (control/variables.toml),
las fuentes RSS, el proveedor y el modelo de lenguaje y el texto que describe al inversor (bot/config.py).

Prueba de consistencia en local:  python bot/diario.py --prueba 3 [--modelo claude-haiku-4-5]
Demo sin Telegram:  python bot/diario.py --demo   (necesita la clave del modelo; imprime el resumen y no escribe en registro/)
(clasifica los mismos titulares varias veces y mide la coincidencia; no envía nada).
"""
import argparse
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

import config
import llm
from telegram import DEMO, comprobar_secretos, enviar

from nucleo import registro
from nucleo.datos import precios
from nucleo.rutas import CARTERA, CARTERA_CSV, MATRIZ
from nucleo.universo import ACTIVOS as UNIVERSO_ACTIVOS
from nucleo.universo import CESTAS, CORTO, DIARIAS, FACTORES, INICIO, SIGNIFICADO, VARIABLES, leer_matriz

# Configuración de bot/config.py; lo que no esté definido allí toma estos valores.
FUENTES_RSS = getattr(config, "FUENTES_RSS", {})
DIARIO_MAX_TITULARES = getattr(config, "DIARIO_MAX_TITULARES", 80)
DIARIO_PROVEEDOR = getattr(config, "DIARIO_PROVEEDOR", "anthropic")   # "anthropic" u "openai" (o compatible)
DIARIO_MODELO = getattr(config, "DIARIO_MODELO", "claude-sonnet-4-5")
DIARIO_URL = getattr(config, "DIARIO_URL", None)                      # None = la URL oficial del proveedor
DIARIO_CLAVE = getattr(config, "DIARIO_CLAVE", None) or llm.PROVEEDORES[DIARIO_PROVEEDOR][1]  # variable de entorno
DIARIO_PARAMETROS = getattr(config, "DIARIO_PARAMETROS", {})          # campos extra o sustituidos de la petición
DIARIO_INVERSOR = getattr(config, "DIARIO_INVERSOR", "un inversor particular")
DIARIO_EJEMPLOS = getattr(config, "DIARIO_EJEMPLOS", "")
VARIABLES_MATRIZ = [n for n, v in VARIABLES.items() if v[3]]
OTRAS = ["Sentimiento", "ninguna"]
UMBRAL_Z = 1.5   # |z| mínimo del movimiento diario para dar por movida una variable (≈ 13 % de los días)
UMBRAL_CARTERA = 0.001  # efecto típico mínimo en la cartera (0,1 % por σ semanal) para que importe
ACTIVOS_CARTERA = list(pd.read_csv(CARTERA_CSV).activo)

INSTRUCCIONES = """Eres el documentalista de noticias financieras de {inversor}. \
Recibes una lista numerada de titulares recientes. Tu trabajo es AGRUPAR y CLASIFICAR; la decisión de \
qué es relevante la toma después un programa con reglas fijas. Sé consistente: ante la misma noticia, \
la misma clasificación.

1. Agrupa los titulares que tratan del mismo hecho (de distintas fuentes) en una sola noticia.
2. Quédate con las noticias importantes (máximo 6) e ignora el resto (opinión, consejos, empresas \
pequeñas, noticias sin novedad).
3. Clasifica cada una:
- "variable": la variable de estado que mueve principalmente. DEBE ser exactamente una de: {variables}. \
Usa "ninguna" si no mueve ninguna de forma clara (p. ej., noticias de una sola empresa sin efecto macro, \
hackeos de plataformas, nombramientos a largo plazo).
- "direccion": "sube" o "baja"{significados}.
- "sorpresa": true solo si el titular indica que el dato o hecho se aparta de lo esperado.
- "impacto": "alto" (aparece en varias fuentes, mueve índices > 1 % o es un dato macro clave o una \
decisión de un banco central), "medio" o "bajo".
- "activo": si la noticia afecta DIRECTAMENTE a una de las posiciones de la cartera (por su sector o \
por el propio activo, aunque no mueva ninguna variable macro), su nombre exacto entre: {activos}; si no, null. \
{ejemplos}Factores sectoriales conocidos de cada posición \
(una noticia que mueve el factor afecta directamente a la posición): {factores}.
- "efecto_activo": "sube" o "baja" (efecto esperado en el precio de ese activo), o null.
- "titular": máximo 10 palabras, en español, sin Markdown.
- "ids": números de los titulares de la lista que respaldan la noticia.

Además, "tesis": una frase solo si alguna noticia toca directamente una tesis o condición de salida de \
cartera.md; si no, null. No inventes datos que no estén en los titulares.

Responde ÚNICAMENTE con un objeto JSON válido, sin texto antes ni después:
{{"noticias": [{{"titular": "...", "variable": "...", "direccion": "sube", "sorpresa": false, \
"impacto": "alto", "activo": null, "efecto_activo": null, "ids": [1, 4]}}], "tesis": null}}
""".format(inversor=DIARIO_INVERSOR,
           variables=", ".join(f'"{v}"' for v in VARIABLES_MATRIZ + OTRAS),
           significados=(" (" + "; ".join(f'en {v}, "sube" = {t}' for v, t in SIGNIFICADO.items()
                                          if v in VARIABLES_MATRIZ) + ")") if SIGNIFICADO else "",
           activos=", ".join(f'"{a}"' for a in ACTIVOS_CARTERA),
           ejemplos=f"Ejemplos: {DIARIO_EJEMPLOS}. " if DIARIO_EJEMPLOS else "",
           factores="; ".join(f'"{a}" ← {", ".join(f)}' for a, f in FACTORES.items()) or "ninguno")


# --- Titulares ---------------------------------------------------------------

def desde_ultimo_cierre(ahora):
    """Inicio de la ventana: cierre de Wall Street (20:00 UTC aprox.) del último día hábil anterior."""
    dia = ahora.date() - timedelta(days=1)
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    return datetime(dia.year, dia.month, dia.day, 20, tzinfo=timezone.utc)


def _fecha(texto):
    if not texto:
        return None
    try:
        f = parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        try:
            f = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except ValueError:
            return None
    return f if f.tzinfo else f.replace(tzinfo=timezone.utc)


def _limpio(texto, n):
    texto = re.sub(r"<[^>]+>", " ", html.unescape(texto or ""))
    return re.sub(r"\s+", " ", texto).strip()[:n]


def leer_rss(url):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (bot personal de noticias)"})
    r.raise_for_status()
    raiz = ET.fromstring(r.content)
    entradas = []
    for it in raiz.iter():
        etiqueta = it.tag.split("}")[-1]
        if etiqueta not in ("item", "entry"):
            continue
        campos = {c.tag.split("}")[-1]: c for c in it}
        enlace = campos.get("link")
        href = (enlace.get("href") or enlace.text) if enlace is not None else ""
        fecha = next((_fecha(campos[k].text) for k in ("pubDate", "published", "updated", "date")
                      if k in campos), None)
        resumen = next((campos[k].text for k in ("description", "summary") if k in campos), "")
        entradas.append({"titulo": _limpio(campos["title"].text if "title" in campos else "", 200),
                         "resumen": _limpio(resumen, 200), "url": (href or "").strip(), "fecha": fecha})
    return entradas


def titulares(ahora):
    inicio = desde_ultimo_cierre(ahora)
    lista, vistos, caidas = [], set(), []
    for fuente, url in FUENTES_RSS.items():
        try:
            entradas = leer_rss(url)
        except Exception:
            caidas.append(fuente)
            continue
        for e in entradas:
            clave = re.sub(r"\W+", "", e["titulo"].lower())
            if not e["titulo"] or clave in vistos or (e["fecha"] and e["fecha"] < inicio):
                continue
            vistos.add(clave)
            lista.append({**e, "fuente": fuente})
    lista.sort(key=lambda e: e["fecha"] or ahora, reverse=True)
    return lista[:DIARIO_MAX_TITULARES], caidas


# --- Contexto y llamada al modelo ---------------------------------------------

def leer(ruta):
    return ruta.read_text(encoding="utf-8") if ruta.exists() else f"({ruta.name} no disponible)"


def _cambios_diarios(ticker, tipo):
    """Cambios diarios de una aproximación de universo.DIARIAS (las cestas se construyen aquí)."""
    if ticker in CESTAS:
        partes = {t: np.log(precios(t, periodo="max")).diff() for t in CESTAS[ticker]}
        return sum(w * partes[t] for t, w in CESTAS[ticker].items()).dropna()
    nivel = precios(ticker, periodo="max").dropna()
    return nivel.diff() if tipo == "dif" else np.log(nivel).diff()


SESIONES_NORMAL = 252  # «lo normal» para una variable: su volatilidad diaria del último año


def movimientos():
    """Último cambio de cada aproximación diaria y su z frente a lo normal: media y desviación de los
    cambios del último año, sin incluir el de hoy (la volatilidad cambia por régimen; desde 2022 los tipos
    se mueven bastante más que en 2012-2021, y medir contra todo el historial inflaría los z)."""
    mov = {}
    for nombre, (ticker, tipo, var, signo) in DIARIAS.items():
        try:
            hist = _cambios_diarios(ticker, tipo).loc[INICIO:].dropna()
            previo = hist.iloc[-SESIONES_NORMAL - 1:-1]
            z = (hist.iloc[-1] - previo.mean()) / previo.std()
            mov[nombre] = {"cambio": hist.iloc[-1], "z": z, "fecha": hist.index[-1], "tipo": tipo,
                           "variable": var, "signo": signo}
        except Exception as e:
            mov[nombre] = {"error": str(e)[:80], "variable": var}
    return mov


def z_por_variable(mov):
    """{variable de la matriz: z en el sentido de la variable (sube = sube la variable)}."""
    return {m["variable"]: m["signo"] * m["z"] for m in mov.values() if m.get("variable") and "z" in m}


def variables_texto(mov):
    filas = []
    for nombre, m in mov.items():
        if "error" in m:
            filas.append(f"- {nombre}: sin datos ({m['error']})")
            continue
        valor = f"{m['cambio']:+.2f} pp" if m["tipo"] == "dif" else f"{m['cambio'] * 100:+.2f} %"
        filas.append(f"- {nombre}: {valor} (z {m['z']:+.1f}) el {m['fecha']:%d/%m}")
    return "Movimiento de la última sesión (|z| > 2 = anómalo):\n" + "\n".join(filas)


def contexto(hoy, lista, vars_txt):
    filas = [f"{i}. [{e['fuente']}] {e['titulo']}" + (f" — {e['resumen']}" if e["resumen"] else "")
             for i, e in enumerate(lista, 1)]
    return "\n\n".join([
        f"Fecha de hoy: {hoy:%d/%m/%Y}",
        vars_txt,
        "=== cartera.md ===\n" + leer(CARTERA),
        "=== cartera.csv (pesos) ===\n" + leer(CARTERA_CSV),
        "=== Titulares ===\n" + "\n".join(filas),
    ])


def clasificar(texto_contexto, modelo):
    texto = llm.completar(INSTRUCCIONES, texto_contexto + "\n\nAgrupa y clasifica.", proveedor=DIARIO_PROVEEDOR,
                          modelo=modelo, url=DIARIO_URL, clave=os.environ.get(DIARIO_CLAVE, ""),
                          max_tokens=1500, temperatura=0, parametros=DIARIO_PARAMETROS)
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin < 0:
        raise RuntimeError(f"la respuesta no es JSON: {texto[:200]}")
    try:
        return json.loads(texto[inicio:fin + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON no válido ({e}): {texto[:200]}")


# --- Reglas y mensaje ----------------------------------------------------------

COLOR = {1: "🟢", -1: "🔴", 0: "🟡"}


def exposicion():
    """Efectos típicos del régimen actual (solo significativos) y pesos de la cartera."""
    exp = leer_matriz(MATRIZ)
    exp = exp[exp.lectura.astype(str) != "0"]
    pesos = pd.read_csv(CARTERA_CSV).set_index("activo")["peso"]
    return exp, pesos


def evaluar(n, exp, pesos, zvar):
    """Reglas fijas (protocolo de noticias: ver docs/bot.md, «Informes»). Relevante si:
    a) mueve una variable a la que la cartera reacciona (efecto típico significativo) y la variable se
       movió de verdad (|z| ≥ UMBRAL_Z en su aproximación diaria; sin dato diario, sorpresa según el modelo), o
    b) afecta directamente a una posición de la cartera y es de impacto alto.
    Devuelve (relevante, efecto, posiciones, motivo, signo, z): efecto = signo del efecto en la cartera;
    signo = dirección de la variable (la del dato si lo hay); z = movimiento medido o None."""
    var, activo = n.get("variable"), n.get("activo")
    signo_texto = 1 if n.get("direccion") == "sube" else -1
    if var not in VARIABLES_MATRIZ:
        if activo in pesos.index and n.get("impacto") == "alto":
            s = 1 if n.get("efecto_activo") == "sube" else -1
            return True, s, f"{CORTO.get(activo, activo)} {'↑' if s > 0 else '↓'}", None, s, None
        if var == "Sentimiento":
            return False, None, None, "solo sentimiento, sin efecto en tus variables", None, None
        return False, None, None, "no mueve tus variables ni toca tus posiciones", None, None
    afect = exp[exp.variable == var]
    z = zvar.get(var)
    signo = signo_texto if z is None or np.isnan(z) else (1 if z > 0 else -1)
    if afect.empty:
        return False, None, None, "tu cartera no reacciona de forma clara a esta variable", signo, z
    efecto = sum(signo * g * pesos.get(a, 0) / 100 for a, g in zip(afect.activo, afect.efecto_actual))
    if abs(efecto) < UMBRAL_CARTERA:
        return False, int(np.sign(efecto)), None, (f"efecto en tu cartera despreciable "
                                                   f"({efecto * 100:+.2f} % por σ)".replace(".", ",")), signo, z
    if z is not None and not np.isnan(z):
        if abs(z) < UMBRAL_Z:
            return False, int(np.sign(efecto)), None, f"la variable apenas se movió (z {z:+.1f})", signo, z
    elif not n.get("sorpresa"):
        return False, int(np.sign(efecto)), None, "ya estaba descontado (sin dato diario)", signo, None
    dentro = afect.assign(peso=afect.activo.map(pesos).fillna(0)).sort_values("peso", ascending=False)
    # Los efectos son semanales (por σ semanal de 2012-hoy); un movimiento diario de z σ diarias equivale a
    # unas z/√5 σ semanales si los días son independientes. Orientativo: z se mide frente al último año.
    escala = abs(z) / np.sqrt(5) if z is not None else 1
    cartera = f"Cartera ≈ {efecto * escala * 100:+.2f} %".replace(".", ",") + ("" if z is not None else " por σ")
    posiciones = cartera + " · " + " · ".join(f"{CORTO.get(a, a)} {'↑' if signo * g > 0 else '↓'}"
                                             for a, g in zip(dentro.activo, dentro.efecto_actual))
    return True, int(np.sign(efecto)), posiciones, None, signo, z


def decidir(datos, exp, pesos, zvar):
    """Hasta 3 relevantes (primero las de mayor |z|, luego por impacto) y hasta 2 de impacto alto descartadas."""
    relevantes, ruido = [], []
    for n in datos.get("noticias") or []:
        ok, efecto, posiciones, motivo, signo, z = evaluar(n, exp, pesos, zvar)
        if ok:
            relevantes.append((n, efecto, posiciones, signo, z))
        elif n.get("impacto") == "alto":
            ruido.append((n, motivo))
    orden = {"alto": 0, "medio": 1, "bajo": 2}
    relevantes.sort(key=lambda x: (-(abs(x[4]) if x[4] is not None else 0), orden.get(x[0].get("impacto"), 3)))
    return relevantes[:3], ruido[:2]


def filas_registro(datos, hoy, exp, pesos, zvar):
    """Una fila por noticia con dirección esperada, para registro/decisiones.csv.

    Incluye las descartadas por el código (relevante=False): son el grupo de control para
    comprobar después si el filtro sirve. Noticias sin efecto atribuible no se registran."""
    filas = []
    for n in datos.get("noticias") or []:
        relevante, efecto, _, _, signo, z = evaluar(n, exp, pesos, zvar)
        var = n.get("variable")
        base = {"fecha": hoy.isoformat(), "origen": "diario", "tipo": "noticia", "detalle": n.get("titular") or "",
                "relevante": relevante, "variable": var if var in VARIABLES_MATRIZ else "",
                "z": "" if z is None else round(float(z), 2)}
        if var in VARIABLES_MATRIZ:
            if efecto:
                filas.append({**base, "activo": "Cartera", "ticker": "CARTERA", "divisa": "", "direccion": efecto})
        elif n.get("activo") in UNIVERSO_ACTIVOS and n.get("efecto_activo") in ("sube", "baja"):
            ticker, divisa = UNIVERSO_ACTIVOS[n["activo"]]
            filas.append({**base, "activo": n["activo"], "ticker": ticker, "divisa": divisa or "",
                          "direccion": 1 if n["efecto_activo"] == "sube" else -1})
    return filas


def componer(datos, lista, caidas, hoy, zvar):
    """Mensaje de Telegram: relevancia, efecto, posiciones y fuentes los decide el código."""
    e = lambda t: html.escape(str(t or "").replace("*", "").strip())
    relevantes, ruido = decidir(datos, *exposicion(), zvar)

    def enlaces(n):
        urls = [lista[i - 1]["url"] for i in n.get("ids") or [] if isinstance(i, int) and 0 < i <= len(lista)]
        urls = [u for u in dict.fromkeys(urls) if u][:2]
        return " ".join(f'<a href="{html.escape(u, quote=True)}">'
                        f'{html.escape(urlparse(u).netloc.removeprefix("www."))}</a>' for u in urls)

    partes = [f"📰 <b>Resumen diario</b> · {hoy:%d/%m/%Y}"]
    for n, efecto, posiciones, signo, z in relevantes:
        flecha = "↑" if signo > 0 else "↓"
        if n.get("variable") in VARIABLES_MATRIZ:
            variable = f"{e(n.get('variable'))} {flecha}"
            prueba_mov = f"movimiento z {z:+.1f}".replace(".", ",") if z is not None else "sorpresa (sin dato diario)"
        else:
            variable, prueba_mov = "Sectorial", "impacto alto"
        fuente = enlaces(n)
        partes.append(f"{COLOR[efecto]} <b>{e(n.get('titular'))}</b>\n"
                      f"↳ {variable} · <i>{prueba_mov}</i>\n"
                      f"↳ {e(posiciones)}" + (f"\n🔗 {fuente}" if fuente else ""))
    if not relevantes:
        partes.append("⚪ <b>Sin novedades relevantes para tu cartera</b>")
    if ruido:
        partes.append("🔇 <b>Mucho ruido, sin efecto en tu cartera</b>\n"
                      + "\n".join(f"· {e(n.get('titular'))}: <i>{e(m)}</i>" for n, m in ruido))
    if relevantes and datos.get("tesis"):
        partes.append(f"📌 <b>Tesis:</b> {e(datos['tesis'])}")
    if caidas:
        partes.append(f"<i>⚠️ Fuentes sin respuesta: {e(', '.join(caidas))}</i>")
    return "\n\n".join(partes)


# --- Ejecución -------------------------------------------------------------------

def pista(error):
    e = str(error).lower()
    if "credit balance" in e or "billing" in e or "quota" in e or "insufficient" in e:
        return f"Parece que no queda saldo: recarga en la consola de tu proveedor ({DIARIO_PROVEEDOR})."
    if "401" in e or "authentication" in e or "api key" in e:
        return f"La clave de API no es válida o falta el secret {DIARIO_CLAVE} en GitHub (o en .env)."
    if "not_found" in e or "model" in e:
        return f"Puede que el modelo «{DIARIO_MODELO}» ya no exista: cámbialo en bot/config.py (DIARIO_MODELO)."
    if "overloaded" in e or "529" in e or "429" in e or "rate" in e:
        return "La API estaba saturada o se superó su límite de uso; mañana debería funcionar."
    if "400" in e and ("max_tokens" in e or "temperature" in e or "unsupported" in e):
        return "El modelo no acepta algún parámetro: ajústalo con DIARIO_PARAMETROS en bot/config.py (ver docs/bot.md)."
    if "json" in e:
        return "El modelo no respetó el formato; suele ser puntual. Si se repite, revisa las instrucciones."
    if "titulares" in e:
        return "Revisa las fuentes de FUENTES_RSS en bot/config.py."
    return "Revisa el registro de la ejecución en GitHub Actions."


def prueba(repeticiones, modelo):
    """Clasifica los mismos titulares varias veces y mide la coincidencia (no envía nada)."""
    ahora = datetime.now(timezone.utc)
    lista, caidas = titulares(ahora)
    print(f"{len(lista)} titulares · fuentes caídas: {caidas or 'ninguna'} · modelo {modelo}")
    mov = movimientos()
    zvar = z_por_variable(mov)
    ctx = contexto(ahora.date(), lista, variables_texto(mov))
    exp, pesos = exposicion()
    clasif, decisiones = [], []
    for k in range(repeticiones):
        datos = clasificar(ctx, modelo)
        por_id = {}
        for n in datos.get("noticias") or []:
            for i in n.get("ids") or []:
                por_id[i] = (n.get("variable"), n.get("direccion"), bool(n.get("sorpresa")), n.get("impacto"))
        relevantes, ruido = decidir(datos, exp, pesos, zvar)
        clasif.append(por_id)
        decisiones.append(sorted(n.get("titular") for n, *_ in relevantes))
        print(f"\nRepetición {k + 1}: relevantes = {decisiones[-1]}; ruido = {[n.get('titular') for n, _ in ruido]}")
    ids = set().union(*clasif)
    iguales = sum(1 for i in ids if len({c.get(i) for c in clasif}) == 1)
    print(f"\nTitulares clasificados igual en todas las repeticiones: {iguales}/{len(ids)}"
          f" ({iguales / max(len(ids), 1):.0%})")
    print("Misma lista de relevantes en todas:", "sí" if len({tuple(d) for d in decisiones}) == 1 else "no")


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--prueba", type=int, default=0)
    args.add_argument("--modelo", default=DIARIO_MODELO)
    args.add_argument("--demo", action="store_true", help="imprime por pantalla en vez de enviar a Telegram")
    a = args.parse_args()
    if a.prueba:
        return prueba(a.prueba, a.modelo)

    comprobar_secretos()
    ahora = datetime.now(timezone.utc)
    try:
        if not os.environ.get(DIARIO_CLAVE) and DIARIO_URL is None:  # con URL propia (p. ej., Ollama) puede no hacer falta
            raise RuntimeError(f"falta {DIARIO_CLAVE} (401)")
        lista, caidas = titulares(ahora)
        if not lista:
            raise RuntimeError(f"no se han obtenido titulares (fuentes caídas: {', '.join(caidas) or 'ninguna'})")
        mov = movimientos()
        zvar = z_por_variable(mov)
        datos = clasificar(contexto(ahora.date(), lista, variables_texto(mov)), a.modelo)
        mensaje = componer(datos, lista, caidas, ahora.date(), zvar)
    except Exception as e:
        enviar(f"❌ <b>Resumen diario: falló</b>\n\n{html.escape(str(e)[:600])}\n\n{pista(e)}")
        sys.exit(1)
    enviar(mensaje)
    if DEMO:
        return
    try:
        registro.registrar(filas_registro(datos, ahora.date(), *exposicion(), zvar))
    except Exception as e:  # el registro nunca debe impedir el resumen
        enviar(f"❌ <b>Registro de decisiones: falló</b>\n\n{html.escape(str(e)[:300])}")


if __name__ == "__main__":
    main()
