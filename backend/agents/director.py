"""
Director Orquestador — Nodo raíz de la jerarquía multi-agente.

ARQUITECTURA ANTERIOR (pipeline secuencial):
    Python → Auditor → Metodólogo → Sintetizar → Redactor → Veredicto
    (el flujo estaba hardcodeado en Python, el Director LLM solo generaba texto)

ARQUITECTURA ACTUAL (jerarquía real con tool calling):
    Director LLM (raíz)
    ├── tool: convocar_auditor()               → evalúa rúbrica UPAO
    ├── tool: convocar_metodologico()          → analiza coherencia
    ├── tool: convocar_redactor(instrucciones) → genera texto mejorado
    └── tool: solicitar_revision_panel(...)    → panel valida texto propuesto

El Director LLM DECIDE dinámicamente:
- A quién convocar y en qué orden
- Cuántas veces iterar
- Cuándo convocar al panel de revisión
- Cuándo tiene suficiente información para el veredicto final

No hay orquestación hardcodeada en Python. El flujo emerge del razonamiento del LLM.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from swarms import Agent

from backend.config import WORKER_MODEL, puntaje_a_nota
from backend.agents.auditor import build_auditor, ReporteAuditor
from backend.agents.metodologico import build_metodologico
from backend.agents.redactor import build_redactor
from backend.agents.herramientas import crear_herramientas
from backend.utils import run_agent_silently, use_groq_key

logger = logging.getLogger("mentoria")

_WS = Path(__file__).parent.parent.parent / "agent_workspace"
_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "director_jerarquico_prompt.md"
_API_KEY = os.getenv("GROQ_KEY_DIRECTOR") or os.getenv("GROQ_API_KEY", "")

# El Director usa el modelo más capaz para tomar decisiones de orquestación
_DIRECTOR_MODEL = WORKER_MODEL  # groq/llama-3.3-70b-versatile


def _build_director_con_herramientas(herramientas: list) -> Agent:
    """
    Construye el agente Director con las herramientas de los sub-agentes.
    max_loops alto porque el Director puede iterar: auditor → metodólogo →
    redactor → panel → redactor de nuevo, según decida.
    """
    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent(
        agent_name="Director Mentor UPAO",
        system_prompt=system_prompt,
        model_name=_DIRECTOR_MODEL,
        tools=herramientas,
        max_loops=12,
        temperature=0.2,
        streaming_on=False,
        verbose=False,
        return_history=False,
        print_every_step=False,
        autosave=False,
        saved_state_path=None,
    )


class DirectorOrchestrator:
    """
    Punto de entrada único del sistema multi-agente jerárquico.

    Los sub-agentes se construyen UNA sola vez en __init__ y se reutilizan
    entre llamadas a run() para evitar el overhead de re-inicialización.
    En cada run(), se crean nuevas herramientas (closures con el contexto
    específico de la sección) y un nuevo Director que las usa.
    """

    def __init__(self):
        logger.info("[Director] Construyendo sub-agentes del enjambre jerárquico...")
        self._auditor      = build_auditor()
        self._metodologico = build_metodologico()
        self._redactor     = build_redactor()
        logger.info(
            "[Director] Jerarquía lista:\n"
            "  Director (raíz)\n"
            "  ├── Auditor UPAO\n"
            "  ├── Metodólogo UPAO\n"
            "  └── Redactor Académico"
        )

    def run(
        self,
        seccion_key: str,
        contexto_rag: str,
        contexto_cruzado: str,
        progress_cb: Callable | None = None,
        rubrica_dinamica: dict | None = None,
        contexto_teorico: str = "",
    ) -> dict[str, Any]:
        """
        Inicia la orquestación jerárquica para una sección del proyecto de tesis.

        El Director LLM recibe la tarea y usa sus herramientas para:
        1. Delegar la evaluación de rúbrica al Auditor
        2. Delegar el análisis de coherencia al Metodólogo
        3. Sintetizar y delegar la mejora textual al Redactor
        4. Opcionalmente, convocar al panel de revisión
        5. Emitir el veredicto final

        El ORDEN y la CANTIDAD de llamadas las decide el Director LLM, no Python.

        Returns:
            Dict con: texto_mejorado, reporte_auditor, obs_metodologica,
                      veredicto_director, nota_vigesimal, aprobado, log_herramientas
        """
        _clear_ws()

        # State compartido: las herramientas depositan sus resultados aquí
        state: dict = {
            "reporte":                 None,
            "texto":                   None,
            "obs_metod":               None,
            "resultado_consenso":      "",
            "resultado_disenso":       "",
            "iteraciones_auditor":     0,
            "iteraciones_metodologico":0,
            "iteraciones_redactor":    0,
            "iteraciones_consenso":    0,
            "iteraciones_disenso":     0,
        }

        # Crear herramientas con el contexto de esta sesión
        herramientas = crear_herramientas(
            seccion_key=seccion_key,
            contexto_rag=contexto_rag,
            contexto_cruzado=contexto_cruzado,
            auditor_agent=self._auditor,
            metodologico_agent=self._metodologico,
            redactor_agent=self._redactor,
            state=state,
            progress_cb=progress_cb,
            rubrica_dinamica=rubrica_dinamica,
            contexto_teorico=contexto_teorico,
        )

        # Construir el Director con sus herramientas para esta sesión
        director = _build_director_con_herramientas(herramientas)

        if progress_cb:
            progress_cb(0.05, "Director iniciando orquestación jerárquica...")

        # Tarea inicial: breve, sin el contexto RAG (los agentes lo tienen via closures)
        tarea_director = (
            f"Orquesta la evaluación completa de la sección '{seccion_key}' "
            f"del proyecto de tesis UPAO.\n\n"
            f"Tienes disponible contexto RAG de {len(contexto_rag)} chars (sección principal) "
            f"y {len(contexto_cruzado)} chars (secciones relacionadas). "
            f"Tus herramientas acceden a ese contexto automáticamente.\n\n"
            f"Sigue el flujo jerárquico: convoca al Auditor primero, luego al Metodólogo, "
            f"sintetiza ambos reportes, instruye al Redactor con observaciones específicas, "
            f"y opcionalmente convoca al panel de revisión si lo consideras necesario. "
            f"Finaliza con el veredicto en el formato indicado en tu sistema."
        )

        logger.info(
            f"[Director] Iniciando jerarquía | sección='{seccion_key}' | "
            f"rag={len(contexto_rag)}c | cruzado={len(contexto_cruzado)}c | "
            f"teorico={len(contexto_teorico)}c"
        )

        with use_groq_key(_API_KEY):
            veredicto = run_agent_silently(director, tarea_director)

        if progress_cb:
            progress_cb(0.97, "Director emitiendo veredicto final...")

        reporte: ReporteAuditor | None = state.get("reporte")
        nota = puntaje_a_nota(reporte.puntaje_total if reporte else 0)

        log_herramientas = (
            f"Llamadas del Director → "
            f"Auditor: {state['iteraciones_auditor']}x | "
            f"Metodólogo: {state['iteraciones_metodologico']}x | "
            f"Redactor: {state['iteraciones_redactor']}x"
        )
        logger.info(f"[Director] Jerarquía completada | {log_herramientas}")

        _clear_ws()

        return {
            "texto_mejorado":     state.get("texto") or "",
            "reporte_auditor":    reporte,
            "obs_metodologica":   state.get("obs_metod") or "",
            "resultado_consenso": state.get("resultado_consenso") or "",
            "resultado_disenso":  state.get("resultado_disenso") or "",
            "veredicto_director": veredicto,
            "nota_vigesimal":     nota,
            "aprobado":           reporte.aprobado if reporte else False,
            "log_debate":         log_herramientas,
        }


def _clear_ws():
    if _WS.exists():
        shutil.rmtree(_WS, ignore_errors=True)
