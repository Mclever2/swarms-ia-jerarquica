"""
Herramientas (tools) que el Director LLM invoca mediante tool-calling.

Cada función es un nodo HOJA del árbol jerárquico — solo ejecuta una acción atómica
y devuelve el resultado al Director. El Director sintetiza, decide y coordina.

    Director (raíz)
    ├── convocar_auditor()                      → evaluación inicial de rúbrica
    ├── convocar_metodologico()                 → análisis inicial de coherencia
    ├── convocar_redactor(instrucciones)        → mejora textual
    ├── revisar_texto_auditor(texto, items)     → auditor valida texto propuesto
    ├── revisar_texto_metodologico(texto, obs)  → metodólogo valida texto propuesto
    ├── convocar_consenso()                     → identifica acuerdos entre evaluadores
    └── convocar_disenso()                      → identifica conflictos entre evaluadores

REGLA DE ORO:
    Cada tool hace UNA sola llamada a UN solo agente (o LLM atómico).
    El Director es quien combina, sintetiza y decide qué hacer con los resultados.

DISEÑO DE TOKEN-ECONOMY:
    El contexto RAG viaja en los closures, NO en los parámetros de las tools.
    El Director solo ve resúmenes estructurados — no fragmentos crudos de PDF.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable

from backend.config import SLEEP_BETWEEN_AGENTS
from backend.agents.auditor import evaluar_seccion, ReporteAuditor
from backend.agents.metodologico import analizar_coherencia
from backend.agents.redactor import redactar

logger = logging.getLogger("mentoria")


def crear_herramientas(
    seccion_key: str,
    contexto_rag: str,
    contexto_cruzado: str,
    auditor_agent,
    metodologico_agent,
    redactor_agent,
    state: dict,
    progress_cb: Callable | None = None,
    rubrica_dinamica: dict | None = None,
    contexto_teorico: str = "",
) -> list:
    """
    Fábrica de herramientas para el Director.

    Las funciones capturan el contexto vía closure para que el Director
    no tenga que pasar fragmentos RAG como parámetros (economía de tokens).

    Args:
        seccion_key:       Clave de la sección a evaluar (ej. "planteamiento_problema")
        contexto_rag:      Fragmentos RAG de la sección del estudiante
        contexto_cruzado:  Fragmentos de secciones dependientes
        auditor_agent:     Instancia del agente Auditor (reutilizada)
        metodologico_agent:Instancia del agente Metodólogo (reutilizada)
        redactor_agent:    Instancia del agente Redactor (reutilizada)
        state:             Dict compartido para recoger resultados
        progress_cb:       Callback opcional para progreso en Streamlit
        rubrica_dinamica:  Dict parseado de rúbrica personalizada (None = usa UPAO)
        contexto_teorico:  Fragmentos de la biblioteca de libros metodológicos (puede ser "")

    Returns:
        Lista de callables listos para pasar como tools al Agent del Director.
    """

    # ── Tool 1: Auditor (evaluación inicial) ─────────────────────────────────

    def convocar_auditor() -> str:
        """
        Convoca al Agente Auditor para evaluar los ítems de la rúbrica de la sección actual.

        Si el estudiante subió su propia rúbrica, usa esos ítems.
        Si no, usa la rúbrica oficial UPAO (33 ítems, escala 0-3).
        Un ítem aprueba si puntaje >= 2. La sección aprueba si TODOS aprueban.

        Retorna reporte con puntajes, observaciones por ítem y feedback general.
        Usar como PRIMER PASO antes de cualquier mejora textual.
        """
        if progress_cb:
            progress_cb(None, "[Jerarquía] Director → Auditor: evaluando rúbrica...")
        logger.info(f"[Tool] Director delegó a Auditor | sección='{seccion_key}'")

        reporte: ReporteAuditor = evaluar_seccion(
            auditor_agent, seccion_key, contexto_rag, contexto_cruzado,
            rubrica_dinamica=rubrica_dinamica,
        )
        state["reporte"] = reporte
        state["iteraciones_auditor"] = state.get("iteraciones_auditor", 0) + 1

        lineas = [
            f"REPORTE AUDITOR — Sección: {seccion_key}",
            f"Puntaje total: {reporte.puntaje_total} | Aprobado: {reporte.aprobado}",
            "",
            "ÍTEMS EVALUADOS:",
        ]
        for item in reporte.items_evaluados:
            estado = "✅ APROBADO" if item.puntaje >= 2 else "❌ OBSERVADO"
            lineas.append(
                f"  Ítem {item.item_numero:02d} [{item.puntaje}/3] {estado}: "
                f"{item.observacion}"
            )
        lineas += ["", f"Feedback general: {reporte.feedback_general}"]

        logger.info(
            f"[Tool] Auditor completó | puntaje={reporte.puntaje_total} "
            f"| aprobado={reporte.aprobado}"
        )
        return "\n".join(lineas)

    # ── Tool 2: Metodólogo (análisis inicial) ────────────────────────────────

    def convocar_metodologico() -> str:
        """
        Convoca al Agente Metodólogo para analizar el rigor científico y la
        coherencia entre secciones del proyecto de tesis UPAO.

        El Metodólogo verifica consistencia con secciones relacionadas
        (título, problema, hipótesis, metodología) según dependencias cruzadas.
        Retorna observaciones narrativas numeradas.

        Usar DESPUÉS del Auditor, antes de instruir al Redactor.
        """
        if progress_cb:
            progress_cb(None, "[Jerarquía] Director → Metodólogo: analizando coherencia...")
        logger.info(f"[Tool] Director delegó a Metodólogo | sección='{seccion_key}'")

        obs = analizar_coherencia(
            metodologico_agent, seccion_key, contexto_rag, contexto_cruzado,
            contexto_teorico=contexto_teorico,
        )
        state["obs_metod"] = obs
        state["iteraciones_metodologico"] = state.get("iteraciones_metodologico", 0) + 1

        logger.info(f"[Tool] Metodólogo completó | {len(obs)} chars")
        return f"REPORTE METODÓLOGO — Sección: {seccion_key}\n\n{obs}"

    # ── Tool 3: Redactor ──────────────────────────────────────────────────────

    def convocar_redactor(instrucciones: str) -> str:
        """
        Convoca al Agente Redactor para producir texto académico mejorado
        según las instrucciones del Director.

        Args:
            instrucciones: Guía específica del Director que incluye los ítems
                a corregir, observaciones del Auditor y del Metodólogo,
                nivel académico esperado y sección del documento a mejorar.

        IMPORTANTE: El Redactor NO puede inventar contenido. Si falta información
        real del estudiante, usa placeholders [COMPLETAR: descripción].
        Retorna el texto mejorado. Puede llamarse más de una vez para refinamiento.
        Usar DESPUÉS de analizar los reportes del Auditor y el Metodólogo.
        """
        if not instrucciones or not instrucciones.strip():
            return "ERROR: instrucciones vacías. El Director debe proporcionar guía específica."

        if progress_cb:
            progress_cb(None, "[Jerarquía] Director → Redactor: generando texto mejorado...")
        logger.info(
            f"[Tool] Director delegó a Redactor | instrucciones={len(instrucciones)} chars"
        )

        texto, argumento = redactar(
            redactor_agent, instrucciones, contexto_rag,
            contexto_teorico=contexto_teorico,
        )
        state["texto"] = texto
        state["iteraciones_redactor"] = state.get("iteraciones_redactor", 0) + 1

        logger.info(f"[Tool] Redactor completó | texto={len(texto)} chars")
        return (
            f"TEXTO MEJORADO (para revisión del Director):\n{texto}\n\n"
            f"ARGUMENTO DEL REDACTOR:\n{argumento}"
        )

    # ── Tool 4: Auditor revisa texto propuesto ────────────────────────────────

    def revisar_texto_auditor(texto_propuesto: str, items_a_verificar: str) -> str:
        """
        Convoca al Agente Auditor para evaluar un texto propuesto por el Redactor.
        Acción atómica: UN solo agente, UN solo resultado.

        Args:
            texto_propuesto:   Texto producido por el Redactor que se somete a revisión.
            items_a_verificar: Ítems específicos a verificar
                               (ej: "Ítems 4, 5, 9 — verificar formulación del problema").

        Retorna reporte del Auditor sobre el texto propuesto.
        El Director debe llamar también a revisar_texto_metodologico() y sintetizar ambos.
        Usar después de que el Redactor produjo texto y se quiere validar antes de aprobar.
        """
        if progress_cb:
            progress_cb(None, "[Jerarquía] Director → Auditor: revisando texto propuesto...")
        logger.info(
            f"[Tool] Director delegó revisión a Auditor | ítems='{items_a_verificar[:60]}'"
        )

        contexto_revision = (
            f"TEXTO PROPUESTO POR EL REDACTOR:\n{texto_propuesto[:1500]}\n\n"
            f"ÍTEMS A VERIFICAR: {items_a_verificar}\n\n"
            f"CONTEXTO ORIGINAL DE LA SECCIÓN:\n{contexto_rag[:500]}"
        )

        reporte_rev: ReporteAuditor = evaluar_seccion(
            auditor_agent, seccion_key, contexto_revision, "",
            rubrica_dinamica=rubrica_dinamica,
        )
        state["reporte"] = reporte_rev
        state["iteraciones_auditor"] = state.get("iteraciones_auditor", 0) + 1

        lineas = [
            "REVISIÓN DEL AUDITOR sobre texto propuesto:",
            f"Puntaje: {reporte_rev.puntaje_total} | Aprobado: {reporte_rev.aprobado}",
            "",
        ]
        for item in reporte_rev.items_evaluados:
            estado = "✅" if item.puntaje >= 2 else "❌"
            lineas.append(
                f"  {estado} Ítem {item.item_numero:02d} [{item.puntaje}/3]: {item.observacion}"
            )

        logger.info(
            f"[Tool] Auditor (revisión) completó | aprobado={reporte_rev.aprobado}"
        )
        return "\n".join(lineas)

    # ── Tool 5: Metodólogo revisa texto propuesto ─────────────────────────────

    def revisar_texto_metodologico(texto_propuesto: str, observaciones_a_verificar: str) -> str:
        """
        Convoca al Agente Metodólogo para verificar que un texto propuesto por el
        Redactor levanta las observaciones metodológicas previas.
        Acción atómica: UN solo agente, UN solo resultado.

        Args:
            texto_propuesto:            Texto del Redactor a revisar.
            observaciones_a_verificar:  Observaciones metodológicas específicas
                                        que se quiere confirmar levantadas.

        Retorna análisis del Metodólogo sobre el texto propuesto.
        El Director debe llamar también a revisar_texto_auditor() y sintetizar ambos.
        Usar junto con revisar_texto_auditor() para validación completa antes de aprobar.
        """
        if progress_cb:
            progress_cb(None, "[Jerarquía] Director → Metodólogo: revisando texto propuesto...")
        logger.info(
            f"[Tool] Director delegó revisión a Metodólogo | obs='{observaciones_a_verificar[:60]}'"
        )

        contexto_revision = (
            f"TEXTO PROPUESTO POR EL REDACTOR:\n{texto_propuesto[:1500]}\n\n"
            f"OBSERVACIONES A VERIFICAR: {observaciones_a_verificar}\n\n"
            f"CONTEXTO ORIGINAL DE LA SECCIÓN:\n{contexto_rag[:500]}"
        )

        obs_rev = analizar_coherencia(
            metodologico_agent, seccion_key, contexto_revision, contexto_cruzado,
            contexto_teorico=contexto_teorico,
        )
        state["obs_metod"] = obs_rev
        state["iteraciones_metodologico"] = state.get("iteraciones_metodologico", 0) + 1

        logger.info(f"[Tool] Metodólogo (revisión) completó | {len(obs_rev)} chars")
        return f"REVISIÓN DEL METODÓLOGO sobre texto propuesto:\n\n{obs_rev}"

    # ── Tool 6: Consenso ─────────────────────────────────────────────────────
    # Herramienta OPCIONAL — el Director la usa cuando quiere identificar acuerdos
    # entre el Auditor y el Metodólogo para priorizar correcciones.

    def convocar_consenso() -> str:
        """
        Analiza los reportes del Auditor y el Metodólogo e identifica los PUNTOS DE ACUERDO.

        Útil cuando ambos evaluadores ya emitieron sus reportes y el Director quiere
        saber qué observaciones tienen mayor consenso para priorizar instrucciones al Redactor.
        Retorna: acuerdos detectados, fortalezas consensuadas, prioridad de corrección.

        Usar DESPUÉS de convocar_auditor() y convocar_metodologico().
        NO usar si ninguno de los dos evaluadores ha emitido reporte aún.
        """
        if progress_cb:
            progress_cb(None, "[Jerarquía] Director → Análisis de Consenso...")
        logger.info(f"[Tool] Director solicitó análisis de CONSENSO | sección='{seccion_key}'")

        feedback_aud = state["reporte"].feedback_general if state.get("reporte") else ""
        obs_metod    = state.get("obs_metod") or ""
        texto_act    = (state.get("texto") or "")[:600]

        if not feedback_aud and not obs_metod:
            return "CONSENSO: No hay reportes disponibles. Convoca al Auditor y al Metodólogo primero."

        from langchain_groq import ChatGroq
        llm = ChatGroq(
            api_key=os.getenv("GROQ_KEY_CONSENSO") or os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile",
            temperature=0.2,
        )

        prompt = (
            f"Eres un analista de coherencia académica. Identifica los PUNTOS DE ACUERDO "
            f"entre el Auditor de rúbrica y el Metodólogo.\n\n"
            f"FEEDBACK DEL AUDITOR:\n{feedback_aud or 'No disponible.'}\n\n"
            f"OBSERVACIONES DEL METODÓLOGO:\n{obs_metod or 'No disponible.'}\n\n"
            f"TEXTO ACTUAL:\n{texto_act or 'No generado aún.'}\n\n"
            f"Estructura tu respuesta exactamente así:\n\n"
            f"ACUERDOS DETECTADOS:\n- [punto donde ambos evaluadores coinciden]\n\n"
            f"FORTALEZAS CONSENSUADAS:\n- [aspectos que ambos reconocen como positivos]\n\n"
            f"PRIORIDAD DE CORRECCIÓN:\n"
            f"[qué ítems tienen mayor consenso de ambos evaluadores y deben corregirse primero]"
        )

        time.sleep(SLEEP_BETWEEN_AGENTS)
        resultado = llm.invoke(prompt).content
        state["resultado_consenso"] = resultado
        state["iteraciones_consenso"] = state.get("iteraciones_consenso", 0) + 1

        logger.info(f"[Tool] Consenso completó | {len(resultado)} chars")
        return f"ANÁLISIS DE CONSENSO — Sección: {seccion_key}\n\n{resultado}"

    # ── Tool 7: Disenso ──────────────────────────────────────────────────────
    # Herramienta OPCIONAL — el Director la usa cuando los evaluadores discrepan
    # y necesita arbitrar antes de instruir al Redactor.

    def convocar_disenso() -> str:
        """
        Analiza los reportes del Auditor y el Metodólogo e identifica los CONFLICTOS.

        Útil cuando las evaluaciones son contradictorias: el Auditor aprueba un ítem
        pero el Metodólogo detecta incoherencia, o viceversa. El Director recibe
        la síntesis del conflicto para arbitrar y decidir cómo instruir al Redactor.
        Retorna: conflictos detectados, brechas de evaluación, recomendación al Director.

        Usar DESPUÉS de convocar_auditor() y convocar_metodologico(), cuando sus
        reportes parecen contradecirse.
        """
        if progress_cb:
            progress_cb(None, "[Jerarquía] Director → Análisis de Disenso...")
        logger.info(f"[Tool] Director solicitó análisis de DISENSO | sección='{seccion_key}'")

        feedback_aud = state["reporte"].feedback_general if state.get("reporte") else ""
        obs_metod    = state.get("obs_metod") or ""
        n_errores    = len([i for i in (state["reporte"].items_evaluados if state.get("reporte") else []) if i.puntaje < 2])

        if not feedback_aud and not obs_metod:
            return "DISENSO: No hay reportes disponibles. Convoca al Auditor y al Metodólogo primero."

        from langchain_groq import ChatGroq
        llm = ChatGroq(
            api_key=os.getenv("GROQ_KEY_DISENSO") or os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile",
            temperature=0.2,
        )

        prompt = (
            f"Eres un árbitro académico. Identifica los CONFLICTOS entre el Auditor "
            f"de rúbrica y el Metodólogo.\n\n"
            f"FEEDBACK DEL AUDITOR ({n_errores} ítems con puntaje < 2):\n"
            f"{feedback_aud or 'No disponible.'}\n\n"
            f"OBSERVACIONES DEL METODÓLOGO:\n{obs_metod or 'No disponible.'}\n\n"
            f"Estructura tu respuesta exactamente así:\n\n"
            f"CONFLICTOS DETECTADOS:\n- [punto donde los evaluadores se contradicen]\n\n"
            f"BRECHAS DE EVALUACIÓN:\n- [aspecto que uno evalúa pero el otro ignora]\n\n"
            f"RECOMENDACIÓN AL DIRECTOR:\n"
            f"[cómo arbitrar el conflicto e instruir al Redactor]"
        )

        time.sleep(SLEEP_BETWEEN_AGENTS)
        resultado = llm.invoke(prompt).content
        state["resultado_disenso"] = resultado
        state["iteraciones_disenso"] = state.get("iteraciones_disenso", 0) + 1

        logger.info(f"[Tool] Disenso completó | {len(resultado)} chars")
        return f"ANÁLISIS DE DISENSO — Sección: {seccion_key}\n\n{resultado}"

    return [
        convocar_auditor,
        convocar_metodologico,
        convocar_redactor,
        revisar_texto_auditor,
        revisar_texto_metodologico,
        convocar_consenso,
        convocar_disenso,
    ]
