"""
Agente Redactor: ÚNICA fuente de texto académico mejorado.
Actúa SOLO bajo instrucciones del Director. Output: texto + argumento.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path

from swarms import Agent

from backend.config import WORKER_MODEL as MODEL_NAME, SLEEP_BETWEEN_AGENTS
from backend.utils import run_agent_silently, call_with_backoff, use_openai_key

logger = logging.getLogger("mentoria")
_PROMPT_PATH    = Path(__file__).parent.parent / "prompts" / "redactor_prompt.md"
_DEBATE_PROMPT  = Path(__file__).parent.parent / "prompts" / "debate_redactor_prompt.md"
_api_key = lambda: os.environ.get("OPENAI_API_KEY", "")


def build_redactor() -> Agent:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent(
        agent_name="Redactor Académico",
        system_prompt=prompt,
        model_name=MODEL_NAME,
        max_loops=1,
        temperature=0.4,
        streaming_on=False,
        verbose=False,
        return_history=False,
        print_every_step=False,
        autosave=False,
        saved_state_path=None,
    )


def redactar(
    agent: Agent,
    instrucciones_director: str,
    contexto_rag: str,
    historial: str = "",
    contexto_teorico: str = "",
) -> tuple[str, str]:
    """
    Produce texto mejorado según instrucciones del Director.
    Retorna (texto_mejorado, argumento).
    """
    task = (
        f"INSTRUCCIONES DEL DIRECTOR:\n{instrucciones_director}\n\n"
        f"CONTEXTO DEL DOCUMENTO (RAG):\n{contexto_rag}\n\n"
        + (f"REFERENCIA TEÓRICA (biblioteca metodológica):\n{contexto_teorico}\n\n" if contexto_teorico else "")
        + (f"HISTORIAL DE CORRECCIONES:\n{historial}\n\n" if historial else "")
        + "Produce el TEXTO MEJORADO y el ARGUMENTO según tu formato de respuesta."
    )

    logger.info("[Redactor] Generando texto mejorado")
    time.sleep(SLEEP_BETWEEN_AGENTS)

    def _call():
        with use_openai_key(_api_key()):
            raw = run_agent_silently(agent, task)
        texto, argumento = _parse_redactor_output(raw)
        logger.info(f"[Redactor] OK — texto: {len(texto)} chars")
        return texto, argumento

    try:
        return call_with_backoff(_call)
    except Exception as e:
        logger.error(f"[Redactor] Fallo: {e}")
        return f"Error en redacción: {str(e)[:100]}", ""


def argumentar(agent: Agent, observaciones: str) -> str:
    """Produce el argumento del Redactor para el debate facilitado por el Director."""
    debate_system = _DEBATE_PROMPT.read_text(encoding="utf-8")
    task = (
        f"{debate_system}\n\n"
        f"OBSERVACIONES DEL DIRECTOR (transmitidas del panel evaluador):\n{observaciones}\n\n"
        "Produce tu ARGUMENTO PARA EL PANEL y tus CONCESIONES si aplica."
    )
    time.sleep(SLEEP_BETWEEN_AGENTS)

    def _call():
        with use_openai_key(_api_key()):
            return run_agent_silently(agent, task).strip()

    try:
        return call_with_backoff(_call)
    except Exception as e:
        return f"Error en argumentación: {str(e)[:100]}"


def _parse_redactor_output(raw: str) -> tuple[str, str]:
    """Separa TEXTO MEJORADO y ARGUMENTO de la respuesta del Redactor."""
    texto, argumento = "", ""
    if "TEXTO MEJORADO:" in raw and "ARGUMENTO:" in raw:
        partes = raw.split("ARGUMENTO:", 1)
        texto = partes[0].replace("TEXTO MEJORADO:", "").strip()
        argumento = partes[1].strip()
    else:
        texto = raw.strip()
    return texto, argumento
