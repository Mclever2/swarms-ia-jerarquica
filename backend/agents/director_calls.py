"""
DEPRECADO — Supersedido por la arquitectura jerárquica con tool calling.

En la arquitectura anterior el Director hacía llamadas LLM secuenciales hardcodeadas
(planificar → sintetizar → veredicto) controladas por Python.

En la arquitectura actual (director.py + herramientas.py) el Director LLM
orquesta dinámicamente usando tool calling. Este módulo ya no es importado.
Se conserva solo como referencia histórica.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path

from swarms import Agent

from backend.config import DIRECTOR_MODEL, SLEEP_BETWEEN_AGENTS, MAX_ITERACIONES
from backend.utils import run_agent_silently, call_with_backoff, use_groq_key
from backend.agents.auditor import ReporteAuditor

logger = logging.getLogger("mentoria")

_PLAN_PROMPT      = Path(__file__).parent.parent / "prompts" / "director_plan_prompt.md"
_SINTESIS_PROMPT  = Path(__file__).parent.parent / "prompts" / "director_sintesis_prompt.md"
_VEREDICTO_PROMPT = Path(__file__).parent.parent / "prompts" / "director_veredicto_prompt.md"

_API_KEY = os.getenv("GROQ_KEY_DIRECTOR") or os.getenv("GROQ_API_KEY", "")


def build_director_agent() -> Agent:
    return Agent(
        agent_name="Director Mentor",
        system_prompt="Eres el Director del sistema de mentoría académica UPAO. "
                      "Orquestas la jerarquía Director → Auditor → Metodólogo → Redactor.",
        model_name=DIRECTOR_MODEL,
        max_loops=1,
        temperature=0.2,
        streaming_on=False,
        verbose=False,
        return_history=False,
        print_every_step=False,
        autosave=False,
        saved_state_path=None,
    )


def planificar(director: Agent, seccion_key: str, contexto: str) -> str:
    """Director analiza la sección y crea el plan de trabajo."""
    plan_sys = _PLAN_PROMPT.read_text(encoding="utf-8")
    task = (
        f"{plan_sys}\n\nSección a evaluar: {seccion_key}\n\n"
        f"Contexto RAG:\n{contexto[:1500]}"
    )
    time.sleep(SLEEP_BETWEEN_AGENTS)

    def _call():
        with use_groq_key(_API_KEY):
            return run_agent_silently(director, task).strip()

    return call_with_backoff(_call)


def sintetizar(
    director: Agent,
    reporte: ReporteAuditor,
    obs_metod: str,
    historial: str,
    iteracion: int,
) -> str:
    """Director sintetiza reportes del Auditor y Metodólogo en instrucciones para el Redactor."""
    sint_sys = _SINTESIS_PROMPT.read_text(encoding="utf-8")
    items_str = "\n".join(
        f"  Ítem {it.item_numero} [{it.puntaje}/3]: {it.observacion[:100]}"
        for it in reporte.items_evaluados
    )
    task = (
        f"{sint_sys}\n\n"
        f"REPORTE AUDITOR:\n{items_str}\n\n"
        f"OBS. METODOLÓGICA:\n{obs_metod[:800]}\n\n"
        + (f"HISTORIAL:\n{historial}\n\n" if historial else "")
        + f"Iteración actual: {iteracion}/{MAX_ITERACIONES}"
    )
    time.sleep(SLEEP_BETWEEN_AGENTS)

    def _call():
        with use_groq_key(_API_KEY):
            return run_agent_silently(director, task).strip()

    return call_with_backoff(_call)


def veredicto_final(
    director: Agent,
    reporte: ReporteAuditor | None,
    obs_metod: str,
    nota: int,
) -> str:
    """Director emite el veredicto final para el mentor humano."""
    verd_sys = _VEREDICTO_PROMPT.read_text(encoding="utf-8")
    resumen = (
        f"Puntaje: {reporte.puntaje_total if reporte else 0} | Nota: {nota}/20 | "
        f"Aprobado: {reporte.aprobado if reporte else False}\n"
        f"Obs. metodológica: {obs_metod[:300]}"
    )
    task = f"{verd_sys}\n\nRESUMEN EVALUACIÓN:\n{resumen}"
    time.sleep(SLEEP_BETWEEN_AGENTS)

    def _call():
        with use_groq_key(_API_KEY):
            return run_agent_silently(director, task).strip()

    return call_with_backoff(_call)
