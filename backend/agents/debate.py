"""
Módulo de debate jerárquico.
El Director facilita el debate entre Redactor y panel evaluador (Auditor + Metodólogo).
Ningún agente habla directamente con otro; todo pasa por el Director.
"""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path
from typing import List

from swarms import Agent

from backend.config import MAX_RONDAS_DEBATE
from backend.utils import extract_json, run_agent_silently, call_with_backoff, use_openai_key

logger = logging.getLogger("mentoria")
_DEBATE_EVAL_PROMPT = Path(__file__).parent.parent / "prompts" / "debate_evaluador_prompt.md"
_api_key = lambda: os.environ.get("OPENAI_API_KEY", "")


def _solicitar_veredicto(evaluador: Agent, api_key: str, argumento_redactor: str,
                          items_disputados: List[int]) -> dict:
    """El Director presenta el argumento del Redactor al evaluador y pide veredicto."""
    prompt_eval = _DEBATE_EVAL_PROMPT.read_text(encoding="utf-8")
    task = (
        f"{prompt_eval}\n\n"
        f"ARGUMENTO DEL REDACTOR:\n{argumento_redactor}\n\n"
        f"ÍTEMS EN DISPUTA: {items_disputados}\n\n"
        "Emite tu VEREDICTO en el formato JSON indicado."
    )
    time.sleep(5)

    def _call():
        with use_openai_key(_api_key()):
            raw = run_agent_silently(evaluador, task)
        return extract_json(raw)

    try:
        return call_with_backoff(_call)
    except Exception as e:
        logger.error(f"[debate] Error obteniendo veredicto: {e}")
        return {"veredictos": [], "observaciones_pendientes": []}


def facilitar_debate(
    director_agent: Agent,
    auditor_agent: Agent,
    metodologico_agent: Agent,
    redactor_agent,          # evitar import circular; se pasa como objeto
    texto_redactor: str,
    errores_pendientes: List[str],
    argumento_redactor_fn,   # callable: (agent, observaciones) -> str
    director_key: str,
) -> tuple[List[str], str]:
    """
    Facilita hasta MAX_RONDAS_DEBATE rondas de debate.

    Flujo por ronda:
    1. Director solicita argumento al Redactor
    2. Director presenta argumento al Auditor → veredicto
    3. Director presenta argumento al Metodólogo → veredicto
    4. Director sintetiza veredictos → actualiza errores_pendientes
    5. Director informa resultado al Redactor

    Retorna (errores_pendientes_actualizados, log_debate).
    """
    if not errores_pendientes:
        return [], ""

    log_debate: List[str] = []
    items_disputados = _extraer_numeros_item(errores_pendientes)

    for ronda in range(1, MAX_RONDAS_DEBATE + 1):
        logger.info(f"[debate] Ronda {ronda}/{MAX_RONDAS_DEBATE}")
        log_debate.append(f"\n=== RONDA DE DEBATE {ronda} ===")

        # Paso 1: Director solicita argumento al Redactor
        observaciones_str = "\n".join(errores_pendientes)
        argumento = argumento_redactor_fn(redactor_agent, observaciones_str)
        log_debate.append(f"ARGUMENTO REDACTOR:\n{argumento[:400]}")

        # Paso 2: Auditor emite veredicto
        time.sleep(5)
        veredicto_auditor = _solicitar_veredicto(
            auditor_agent, _AUDITOR_KEY, argumento, items_disputados
        )
        log_debate.append(f"VEREDICTO AUDITOR: {veredicto_auditor.get('veredictos', [])}")

        # Paso 3: Metodólogo emite veredicto
        time.sleep(5)
        veredicto_metod = _solicitar_veredicto(
            metodologico_agent, _METOD_KEY, argumento, items_disputados
        )
        log_debate.append(f"VEREDICTO METODÓLOGO: {veredicto_metod.get('veredictos', [])}")

        # Paso 4: Director sintetiza → actualiza errores_pendientes
        errores_previos = list(errores_pendientes)
        errores_pendientes = _sintetizar_veredictos(
            errores_previos,
            veredicto_auditor.get("veredictos", []),
            veredicto_metod.get("veredictos", []),
        )
        log_debate.append(f"ERRORES RESTANTES: {len(errores_pendientes)}")

        if not errores_pendientes:
            log_debate.append("✓ Todas las observaciones fueron levantadas")
            break

    return errores_pendientes, "\n".join(log_debate)


def _extraer_numeros_item(errores: List[str]) -> List[int]:
    import re
    nums = []
    for e in errores:
        m = re.findall(r"\d+", e)
        nums.extend(int(n) for n in m if int(n) <= 33)
    return list(set(nums))


def _sintetizar_veredictos(
    errores: List[str],
    veredictos_auditor: list,
    veredictos_metod: list,
) -> List[str]:
    """
    Elimina de errores los ítems aceptados por AMBOS evaluadores.
    Si uno dice MANTENIDO, el error persiste.
    """
    aceptados_auditor = {
        v["item_numero"] for v in veredictos_auditor if v.get("decision") == "ACEPTADO"
    }
    aceptados_metod = {
        v["item_numero"] for v in veredictos_metod if v.get("decision") == "ACEPTADO"
    }
    aceptados = aceptados_auditor & aceptados_metod  # ambos deben aceptar

    import re
    nuevos_errores = []
    for error in errores:
        nums = [int(n) for n in re.findall(r"\d+", error) if int(n) <= 33]
        if not nums or not all(n in aceptados for n in nums):
            nuevos_errores.append(error)
    return nuevos_errores
