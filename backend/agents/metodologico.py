"""
Agente Metodólogo: evalúa rigor científico y coherencia entre secciones.
Solo responde cuando el Director lo convoca. Output: texto narrativo.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path

from swarms import Agent

from backend.config import WORKER_MODEL as MODEL_NAME, SLEEP_BETWEEN_AGENTS
from backend.utils import run_agent_silently, call_with_backoff, use_groq_key

logger = logging.getLogger("mentoria")
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "metodologico_prompt.md"
_API_KEY = os.getenv("GROQ_KEY_METODOLOGICO") or os.getenv("GROQ_API_KEY", "")


def build_metodologico() -> Agent:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent(
        agent_name="Metodólogo UPAO",
        system_prompt=prompt,
        model_name=MODEL_NAME,
        max_loops=1,
        temperature=0.2,
        streaming_on=False,
        verbose=False,
        return_history=False,
        print_every_step=False,
        autosave=False,
        saved_state_path=None,
    )


def analizar_coherencia(
    agent: Agent,
    seccion_key: str,
    contexto_rag: str,
    contexto_cruzado: str,
    contexto_teorico: str = "",
) -> str:
    """
    Convoca al Metodólogo para analizar la coherencia científica.
    Retorna texto narrativo con observaciones numeradas.
    """
    task = (
        f"Analiza el rigor científico y la coherencia cruzada de la sección '{seccion_key}'.\n\n"
        f"CONTEXTO PRINCIPAL:\n{contexto_rag}\n\n"
        f"CONTEXTO CRUZADO (otras secciones relacionadas):\n{contexto_cruzado}\n\n"
        + (f"REFERENCIA TEÓRICA (biblioteca metodológica):\n{contexto_teorico}\n\n" if contexto_teorico else "")
        + "Identifica inconsistencias entre secciones según las dependencias cruzadas de la rúbrica UPAO. "
        "Sé específico y concreto. Máximo 400 palabras."
    )

    logger.info(f"[Metodólogo] Analizando coherencia de '{seccion_key}'")
    time.sleep(SLEEP_BETWEEN_AGENTS)

    def _call():
        with use_groq_key(_API_KEY):
            result = run_agent_silently(agent, task)
        logger.info(f"[Metodólogo] OK — {len(result)} chars")
        return result.strip()

    try:
        return call_with_backoff(_call)
    except Exception as e:
        logger.error(f"[Metodólogo] Fallo: {e}")
        return f"Error en análisis metodológico: {str(e)[:100]}"
