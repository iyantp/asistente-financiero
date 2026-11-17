"""Llamada a un modelo de lenguaje, sin depender de un proveedor concreto.

Dos formatos de API cubren casi todo:
- "anthropic": la API de Anthropic (Claude).
- "openai": la API de OpenAI y cualquier API compatible con ella, cambiando la URL (`url`): Google Gemini,
  Mistral, Groq, DeepSeek, OpenRouter, Ollama o LM Studio en local, etc.

Se configura en bot/config.py (DIARIO_PROVEEDOR, DIARIO_MODELO, DIARIO_URL, DIARIO_CLAVE, DIARIO_PARAMETROS).
Solo usa `requests`: no hace falta instalar el SDK de ningún proveedor.
"""
import os

import requests

PROVEEDORES = {
    # proveedor: (URL por defecto, variable de entorno por defecto con la clave)
    "anthropic": ("https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
}


def _url_openai(url):
    url = url.rstrip("/")
    return url if url.endswith("/chat/completions") else url + "/chat/completions"


def peticion(sistema, usuario, *, proveedor, modelo, url=None, clave=None, max_tokens=1500, temperatura=0,
             parametros=None):
    """(url, cabeceras, cuerpo) de la petición. `parametros` añade o sustituye campos del cuerpo; None quita uno."""
    if proveedor not in PROVEEDORES:
        raise ValueError(f"proveedor {proveedor!r} no válido (válidos: {', '.join(PROVEEDORES)})")
    if proveedor == "anthropic":
        destino = url or PROVEEDORES["anthropic"][0]
        cabeceras = {"x-api-key": clave or "", "anthropic-version": "2023-06-01", "content-type": "application/json"}
        cuerpo = {"model": modelo, "max_tokens": max_tokens, "temperature": temperatura, "system": sistema,
                  "messages": [{"role": "user", "content": usuario}]}
    else:
        destino = _url_openai(url or PROVEEDORES["openai"][0])
        cabeceras = {"content-type": "application/json"}
        if clave:  # los modelos locales (Ollama…) no necesitan clave
            cabeceras["authorization"] = f"Bearer {clave}"
        cuerpo = {"model": modelo, "max_tokens": max_tokens, "temperature": temperatura,
                  "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
    for k, v in (parametros or {}).items():
        if v is None:
            cuerpo.pop(k, None)
        else:
            cuerpo[k] = v
    return destino, cabeceras, cuerpo


def texto_respuesta(proveedor, datos):
    """Texto generado, a partir del JSON de la respuesta."""
    if proveedor == "anthropic":
        return "".join(b.get("text", "") for b in datos["content"] if b.get("type") == "text").strip()
    return (datos["choices"][0]["message"].get("content") or "").strip()


def clave_por_defecto(proveedor, nombre=None):
    """Clave de la variable de entorno `nombre` (o la habitual del proveedor). Vacío si no hay."""
    return os.environ.get(nombre or PROVEEDORES.get(proveedor, ("", ""))[1], "")


def completar(sistema, usuario, *, proveedor="anthropic", modelo, url=None, clave=None, max_tokens=1500,
              temperatura=0, parametros=None, timeout=180):
    """Envía las instrucciones (`sistema`) y el mensaje (`usuario`) y devuelve el texto de la respuesta."""
    destino, cabeceras, cuerpo = peticion(sistema, usuario, proveedor=proveedor, modelo=modelo, url=url, clave=clave,
                                          max_tokens=max_tokens, temperatura=temperatura, parametros=parametros)
    r = requests.post(destino, headers=cabeceras, json=cuerpo, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    return texto_respuesta(proveedor, r.json())
