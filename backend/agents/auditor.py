"""
Agente Auditor: evalúa los ítems de la rúbrica UPAO de forma estricta.
Output tipado con Pydantic. Solo responde cuando el Director lo convoca.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from swarms import Agent

from backend.config import WORKER_MODEL as MODEL_NAME, SLEEP_BETWEEN_AGENTS, items_de_seccion
from backend.utils import extract_json, run_agent_silently, call_with_backoff, use_groq_key

logger = logging.getLogger("mentoria")
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "auditor_prompt.md"
_API_KEY = os.getenv("GROQ_KEY_AUDITOR") or os.getenv("GROQ_API_KEY", "")


# ── Pydantic output ───────────────────────────────────────────────────────────

class ItemEvaluado(BaseModel):
    item_numero: int
    puntaje: int = Field(..., ge=0, le=3)
    observacion: str


class ReporteAuditor(BaseModel):
    items_evaluados: List[ItemEvaluado] = Field(default_factory=list)
    aprobado: bool = False
    feedback_general: str = ""
    puntaje_total: int = 0


# ── Factory del agente ────────────────────────────────────────────────────────

def build_auditor() -> Agent:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent(
        agent_name="Auditor UPAO",
        system_prompt=prompt,
        model_name=MODEL_NAME,
        max_loops=1,
        temperature=0.1,
        streaming_on=False,
        verbose=False,
        return_history=False,
        print_every_step=False,
        autosave=False,
        saved_state_path=None,
    )


# ── Función principal ─────────────────────────────────────────────────────────

def evaluar_seccion(
    agent: Agent,
    seccion_key: str,
    contexto_rag: str,
    contexto_cruzado: str = "",
    rubrica_dinamica: dict | None = None,
) -> ReporteAuditor:
    """
    Convoca al Auditor con el contexto RAG de la sección.
    Si rubrica_dinamica está presente, usa sus ítems en lugar de la UPAO hardcodeada.
    Retorna un ReporteAuditor Pydantic validado.
    """
    if rubrica_dinamica:
        from backend.rag.rubric_parser import rubrica_a_texto_prompt
        items_str = rubrica_a_texto_prompt(rubrica_dinamica)
        puntaje_max = rubrica_dinamica.get("puntaje_maximo", 0)
        n_items = rubrica_dinamica.get("total_items", 0)
        logger.info(f"[Auditor] Usando rúbrica dinámica: {n_items} ítems, max={puntaje_max}")
    else:
        items = items_de_seccion(seccion_key)
        items_str = "\n".join(f"- Ítem {it['n']:02d}: {it['desc']}" for it in items)
        puntaje_max = len(items) * 3
        n_items = len(items)
        logger.info(f"[Auditor] Usando rúbrica UPAO: {n_items} ítems")

    regla_placeholder = (
        "\nREGLA: Si el texto contiene '[COMPLETAR: ...]', evalúa ese ítem con puntaje 0 o 1.\n"
    )

    task = (
        f"Evalúa SOLO los siguientes ítems de la rúbrica para la sección indicada:\n\n"
        f"{items_str}\n\n"
        f"{regla_placeholder}"
        f"CONTEXTO DE LA SECCIÓN (RAG):\n{contexto_rag}\n\n"
        + (f"CONTEXTO CRUZADO:\n{contexto_cruzado}\n\n" if contexto_cruzado else "")
        + "Responde ÚNICAMENTE con el objeto JSON."
    )

    logger.info(f"[Auditor] Evaluando '{seccion_key}' — {n_items} ítems")
    time.sleep(SLEEP_BETWEEN_AGENTS)

    def _call():
        with use_groq_key(_API_KEY):
            raw = run_agent_silently(agent, task)
        data = extract_json(raw)
        items_ev = [ItemEvaluado(**i) for i in data.get("items_evaluados", [])]
        reporte = ReporteAuditor(
            items_evaluados=items_ev,
            aprobado=data.get("aprobado", all(i.puntaje >= 2 for i in items_ev)),
            feedback_general=data.get("feedback_general", ""),
            puntaje_total=data.get("puntaje_total", sum(i.puntaje for i in items_ev)),
        )
        logger.info(f"[Auditor] OK — Puntaje: {reporte.puntaje_total} | Aprobado: {reporte.aprobado}")
        return reporte

    try:
        return call_with_backoff(_call)
    except Exception as e:
        logger.error(f"[Auditor] Fallo: {e}")
        return ReporteAuditor(feedback_general=f"Error en evaluación: {str(e)[:100]}")
