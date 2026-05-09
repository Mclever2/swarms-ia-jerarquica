"""
Utilidades compartidas para todos los agentes del enjambre.

- run_agent_silently: ejecuta un swarms Agent suprimiendo stdout/stderr
- extract_json: extrae el primer objeto JSON válido de la respuesta del LLM
- call_with_backoff: reintenta una llamada con backoff exponencial
- use_groq_key: context manager que inyecta la API key de Groq adecuada
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from typing import Any, Callable, TypeVar

logger = logging.getLogger("mentoria")

T = TypeVar("T")


# ── Ejecución silenciosa ──────────────────────────────────────────────────────

def run_agent_silently(agent, task: str) -> str:
    """
    Ejecuta agent.run(task) suprimiendo toda salida a stdout/stderr.
    Retorna la respuesta como string limpio.
    """
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured_out), \
             contextlib.redirect_stderr(captured_err):
            result = agent.run(task)
    except Exception:
        raise

    if isinstance(result, str):
        return result.strip()
    if isinstance(result, list):
        # swarms a veces retorna lista de mensajes; tomar el último
        for item in reversed(result):
            if isinstance(item, dict):
                content = item.get("content") or item.get("text") or ""
                if content:
                    return str(content).strip()
            if isinstance(item, str) and item.strip():
                return item.strip()
    return str(result).strip()


# ── Extracción de JSON ────────────────────────────────────────────────────────

def extract_json(raw: str) -> dict:
    """
    Extrae el primer objeto JSON válido del texto producido por el LLM.
    Maneja: JSON puro, bloque ```json...```, y JSON embebido en prosa.
    """
    if not raw:
        return {}

    # 1. Bloque de código markdown
    md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. JSON directo desde el primer '{' hasta el último '}'
    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass

    # 3. Fallback: retornar dict vacío con el texto crudo para depuración
    logger.warning(f"extract_json: no se encontró JSON válido en: {raw[:200]!r}")
    return {"_raw": raw}


# ── Backoff exponencial ───────────────────────────────────────────────────────

def call_with_backoff(
    fn: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> T:
    """
    Llama fn() y reintenta hasta max_retries veces con backoff exponencial.
    Pensado para absorber errores 429 (rate limit) de APIs gratuitas.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"call_with_backoff: intento {attempt}/{max_retries} falló "
                f"({type(exc).__name__}: {exc}). Reintentando en {delay:.0f}s..."
            )
            time.sleep(delay)
    raise RuntimeError(f"Todos los intentos fallaron: {last_exc}") from last_exc


# ── Context manager de API key ────────────────────────────────────────────────

@contextmanager
def use_groq_key(api_key: str):
    """
    Inyecta temporalmente una clave Groq en el entorno para el agente activo.
    Restaura el valor anterior al salir del bloque.

    Uso:
        with use_groq_key(GROQ_KEY_AUDITOR):
            result = agent.run(task)
    """
    if not api_key:
        yield
        return

    prev_groq  = os.environ.get("GROQ_API_KEY")
    prev_oai   = os.environ.get("OPENAI_API_KEY")

    os.environ["GROQ_API_KEY"]  = api_key
    os.environ["OPENAI_API_KEY"] = api_key  # litellm también lo lee

    try:
        yield
    finally:
        if prev_groq is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = prev_groq

        if prev_oai is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = prev_oai
