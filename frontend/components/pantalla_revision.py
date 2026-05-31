"""
Pantalla 3 (HITL): Revisión y aprobación del mentor.

El mentor puede editar el texto antes de aprobar o rechazar para re-análisis.
Al aprobar, se calculan y guardan las métricas de coherencia en backend/logs/.
"""
from __future__ import annotations
import streamlit as st

from backend.config import SECCIONES, MAX_CONTEXT_CHARS
from backend.rag.tesis_store import query_context, query_cross_context
from backend.rag.library_store import recuperar_contexto_teorico
from frontend import session_manager as sm
from frontend.resources import get_orchestrator, get_library


def render():
    seccion_key  = sm.get("seccion_activa")
    info         = SECCIONES.get(seccion_key, {})
    nombre_label = sm.get("seccion_nombre_toc") or info.get("label", seccion_key)
    st.title(f"Revisión: {nombre_label}")

    resultado = sm.get("resultado")

    if resultado is None:
        _ejecutar_pipeline(seccion_key)
        return

    _mostrar_resultado(resultado, seccion_key)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _ejecutar_pipeline(seccion_key: str):
    store   = sm.get("tesis_store")
    rubrica = sm.get("rubrica_dinamica")

    if store is None:
        st.error("No hay tesis indexada. Vuelve a cargar el PDF.")
        sm.ir_a("upload")
        return

    ctx_rag     = query_context(store, seccion_key)[:MAX_CONTEXT_CHARS]
    ctx_cruzado = query_cross_context(store, seccion_key)[:MAX_CONTEXT_CHARS]
    ctx_teorico = recuperar_contexto_teorico(get_library(), seccion_key)[:MAX_CONTEXT_CHARS]
    sm.set("ctx_rag_actual", ctx_rag)

    progress_bar = st.progress(0.0, text="Iniciando pipeline jerárquico...")

    def _progress(pct, msg):
        if pct is not None:
            progress_bar.progress(min(pct, 1.0), text=msg)

    orchestrator = get_orchestrator()
    try:
        with st.spinner(f"Analizando '{seccion_key}'... (esto puede tardar 2-5 min)"):
            resultado = orchestrator.run(
                seccion_key=seccion_key,
                contexto_rag=ctx_rag,
                contexto_cruzado=ctx_cruzado,
                progress_cb=_progress,
                rubrica_dinamica=rubrica,
                contexto_teorico=ctx_teorico,
            )
        progress_bar.progress(1.0, "Análisis completado.")
        sm.set("resultado",     resultado)
        sm.set("texto_editado", resultado.get("texto_mejorado", ""))
        st.rerun()
    except Exception as exc:
        import logging
        logging.getLogger("mentoria").error(f"Error en pipeline: {exc}", exc_info=True)
        st.error(
            "⚠️ **Ocurrió un error inesperado en la evaluación del enjambre.**\n\n"
            f"Detalle del error: `{exc}`\n\n"
            "Esto suele ocurrir si se alcanzan los límites de cuota (Rate Limits / TPM) de la API gratuita de Groq. "
            "Por favor, espera 15-20 segundos a que se libere la cuota y presiona el botón de abajo para reintentar."
        )
        if st.button("Reintentar Evaluación", type="primary", use_container_width=True):
            st.rerun()


# ── Presentación del resultado ────────────────────────────────────────────────

def _mostrar_resultado(resultado: dict, seccion_key: str):
    reporte  = resultado.get("reporte_auditor")
    nota     = resultado.get("nota_vigesimal", 0)
    aprobado = resultado.get("aprobado", False)
    rubrica  = sm.get("rubrica_dinamica")

    # ── Métricas ──────────────────────────────────────────────────────────────
    puntaje_bruto = reporte.puntaje_total if reporte else 0
    puntaje_max   = len(reporte.items_evaluados) * 3 if reporte and reporte.items_evaluados else 0
    iteracion     = sm.get("iteracion_hitl") or 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Nota Vigesimal",
        f"{nota}/20",
        help="Calificación sobre 20 puntos, calculada en proporción a los ítems evaluados en esta sección.",
    )
    c2.metric(
        "Puntaje Bruto",
        f"{puntaje_bruto}/{puntaje_max} pts",
        help=f"Suma de puntajes obtenidos (0-3 por ítem). Máximo posible: {puntaje_max} pts ({puntaje_max // 3} ítems × 3).",
    )
    c3.metric(
        "Estado",
        "APROBADO ✅" if aprobado else "Observado ⚠️",
        help="APROBADO: todos los ítems tienen puntaje ≥ 2. Observado: uno o más ítems con puntaje 0-1 requieren corrección.",
    )
    c4.metric(
        "Re-análisis",
        f"{iteracion}x",
        help="Número de veces que el Mentor rechazó el resultado y solicitó un nuevo análisis del Director.",
    )

    st.divider()

    # ── Tabs de informe ───────────────────────────────────────────────────────
    tabs = st.tabs([
        "Informe del Auditor",
        "Observaciones Metodológicas",
        "Consenso / Disenso",
        "Veredicto del Director",
        "Métricas del Ciclo",
    ])

    with tabs[0]:
        _render_tab_auditor(reporte, seccion_key, rubrica)

    with tabs[1]:
        _render_tab_metodologico(resultado.get("obs_metodologica", ""))

    with tabs[2]:
        _render_tab_consenso_disenso(resultado)

    with tabs[3]:
        _render_tab_veredicto(resultado.get("veredicto_director", ""))

    with tabs[4]:
        _render_tab_metricas(resultado, seccion_key, puntaje_bruto, puntaje_max)

    st.divider()

    # ── Editor de texto ───────────────────────────────────────────────────────
    sec_label = sm.get("seccion_nombre_toc") or SECCIONES.get(seccion_key, {}).get("label", seccion_key)
    st.subheader(f"Texto mejorado — Sección: *{sec_label}*")
    st.caption(
        "El sistema mejoró el texto del estudiante basándose en su contenido original y la rúbrica activa. "
        "Puedes editarlo antes de aprobar. Los marcadores [COMPLETAR: ...] indican que el estudiante "
        "debe completar esa parte con información real de su investigación."
    )

    texto_editado = st.text_area(
        label="Texto para aprobación:",
        value=sm.get("texto_editado") or resultado.get("texto_mejorado", ""),
        height=400,
        key="area_texto_editado",
        label_visibility="collapsed",
    )
    sm.set("texto_editado", texto_editado)

    if "[COMPLETAR:" in texto_editado:
        st.warning(
            "El texto contiene marcadores `[COMPLETAR: ...]`. "
            "Estos indican secciones que **el estudiante debe completar** "
            "con información real de su investigación."
        )

    st.divider()

    # ── Decisión HITL ─────────────────────────────────────────────────────────
    st.subheader("Decisión del Mentor")
    col_ap, col_re = st.columns(2)

    with col_ap:
        st.markdown("**Aprobar:** El texto (con tus ediciones) queda como versión final.")
        if st.button("Aprobar Texto Final", type="primary", use_container_width=True):
            resultado["texto_final_aprobado"] = texto_editado
            sm.set("resultado", resultado)
            _guardar_metricas(resultado, seccion_key, texto_editado)
            sm.ir_a("resultado")

    with col_re:
        it = sm.get("iteracion_hitl") or 0
        st.markdown("**Rechazar:** Descarta este resultado. El Director re-analiza.")
        if st.button(f"Re-analizar (#{it + 1})", type="secondary", use_container_width=True):
            sm.set("resultado",      None)
            sm.set("iteracion_hitl", it + 1)
            st.rerun()


# ── Tabs internos ─────────────────────────────────────────────────────────────

def _render_tab_auditor(reporte, seccion_key: str, rubrica) -> None:
    if not reporte or not reporte.items_evaluados:
        st.info("Sin reporte del Auditor disponible.")
        return

    observados = [i for i in reporte.items_evaluados if i.puntaje < 2]
    aprobados  = [i for i in reporte.items_evaluados if i.puntaje >= 2]

    if not observados:
        tipo = "la rúbrica subida" if rubrica else "la rúbrica UPAO"
        st.success(f"El Auditor declaró el texto conforme a {tipo} para la sección *{seccion_key}*.")
    else:
        st.warning(f"El Auditor detectó **{len(observados)} ítem(s)** con puntaje 0-1.")

        if rubrica:
            secciones_rub = rubrica.get("secciones", {})
            item_a_sec    = {n: sec for sec, nums in secciones_rub.items() for n in nums}
            por_sec: dict = {}
            for item in observados:
                sec = item_a_sec.get(item.item_numero, "General")
                por_sec.setdefault(sec, []).append(item)
            for sec_nombre, items in por_sec.items():
                st.markdown(f"**{sec_nombre}**")
                for item in items:
                    _render_item_card(item)
        else:
            for item in observados:
                _render_item_card(item)

    st.divider()
    st.markdown("**Feedback general del Auditor:**")
    st.info(reporte.feedback_general or "—")

    if aprobados:
        with st.expander(f"Ítems aprobados ({len(aprobados)})"):
            for item in aprobados:
                st.markdown(
                    f"- Ítem **{item.item_numero:02d}** [**{item.puntaje}**/3]: {item.observacion}"
                )


def _render_item_card(item) -> None:
    nivel = "Insuficiente (0)" if item.puntaje == 0 else "Regular (1)"
    with st.container(border=True):
        st.markdown(
            f"**Ítem {item.item_numero:02d}** &nbsp; {nivel}\n\n"
            f"{item.observacion}"
        )


def _render_tab_metodologico(obs: str) -> None:
    """Muestra las observaciones metodológicas de forma estructurada."""
    if not obs or not obs.strip():
        st.info("Sin observaciones metodológicas en este ciclo.")
        return

    # Separar inconsistencias por bloques "↔" para mostrar cada una como tarjeta
    import re
    bloques = re.split(r"\n(?=\d+\.\s|\*\*[^*]+↔|[A-ZÁÉÍÓÚ][^↔\n]+↔)", obs)
    if len(bloques) > 1:
        for bloque in bloques:
            bloque = bloque.strip()
            if bloque:
                with st.container(border=True):
                    st.markdown(bloque)
    else:
        # Sin estructura detectada — mostrar como texto normal
        st.markdown(obs)


def _render_tab_veredicto(veredicto_raw: str) -> None:
    """Muestra solo el bloque VEREDICTO DIRECTOR del output del agente,
    descartando los loops internos de razonamiento.

    El output de swarms puede contener todo el historial de conversación
    del Director. Solo nos interesa la sección 'VEREDICTO DIRECTOR —'.
    """
    import re
    if not veredicto_raw:
        st.info(
            "ℹ️ El Director no emitió veredicto en este ciclo. "
            "Esto suele ocurrir cuando el modelo alcanza el límite de tokens (Rate Limit) "
            "antes de completar todos los loops. Reintenta la evaluación."
        )
        return

    match = re.search(
        r"(VEREDICTO\s+DIRECTOR\s*[—–\-]+.*?)(?:\Z|\n{3,}###|\n{3,}Current Internal)",
        veredicto_raw,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        st.markdown(match.group(1).strip())
    else:
        # El Director procesó todo pero no respetó el formato obligatorio
        st.warning(
            "⚠️ El Director no emitió el veredicto en el formato estándar "
            "(`VEREDICTO DIRECTOR —`). Revisa el prompt del Director o aumenta "
            "`max_loops` para que complete todos los ciclos."
        )


def _render_tab_consenso_disenso(resultado: dict) -> None:
    cons = resultado.get("resultado_consenso", "")
    diss = resultado.get("resultado_disenso",  "")

    col_c, col_d = st.columns(2)
    with col_c:
        st.markdown("**Análisis de Consenso**")
        st.caption("Puntos de acuerdo entre Auditor y Metodólogo")
        if cons:
            st.info(cons)
        else:
            st.caption("El Director no activó el análisis de Consenso en este ciclo.")

    with col_d:
        st.markdown("**Análisis de Disenso**")
        st.caption("Conflictos entre Auditor y Metodólogo")
        if diss:
            st.warning(diss)
        else:
            st.caption("El Director no activó el análisis de Disenso en este ciclo.")


# ── Tab 5: Métricas del ciclo multiagente ─────────────────────────────────────

def _render_tab_metricas(
    resultado: dict,
    seccion_key: str,
    puntaje_bruto: int,
    puntaje_max: int,
) -> None:
    """
    Métricas NLP idénticas al proyecto LangGraph:
      Fila 1 — ROUGE-1, ROUGE-2, ROUGE-L, BLEU
      Fila 2 — Cos sim, Gain Score, Kappa, Puntaje 0-10

    Más la sección de actividad del enjambre (única de swarms).
    """
    import re as _re

    ctx_original   = sm.get("ctx_rag_actual") or ""
    texto_mejorado = resultado.get("texto_mejorado", "")
    log_debate     = resultado.get("log_debate", "")
    iteracion_hitl = sm.get("iteracion_hitl") or 0

    # ── Calcular métricas NLP ─────────────────────────────────────────────────
    metricas: dict = {}
    try:
        from backend.metrics.nlp_metrics import calcular_todas
        metricas = calcular_todas(
            texto_referencia=ctx_original,
            texto_generado=texto_mejorado,
            puntaje_inicial=0,
            puntaje_final=float(puntaje_bruto),
            puntaje_maximo=float(puntaje_max),
            historial_texto=[],   # swarms no tiene turnos de debate como texto
        )
    except Exception as _exc:
        import logging
        logging.getLogger("mentoria").warning(f"[NLP] Error calculando métricas: {_exc}")

    # ── Mostrar: Métricas NLP ─────────────────────────────────────────────────
    st.markdown("#### Métricas NLP")
    st.caption(
        "Comparan el *texto original* analizado vs el *texto sugerido* "
        "(reescritura propuesta por el pipeline)."
    )

    # Fila 1 — ROUGE-1, ROUGE-2, ROUGE-L, BLEU
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("ROUGE-1", f"{metricas.get('rouge1_f', 0.0):.3f}")
    col2.metric("ROUGE-2", f"{metricas.get('rouge2_f', 0.0):.3f}")
    col3.metric("ROUGE-L", f"{metricas.get('rougeL_f', 0.0):.3f}")
    col4.metric("BLEU",    f"{metricas.get('bleu_score', 0.0):.3f}")

    # Fila 2 — Cos sim, Gain Score, Kappa, Puntaje 0-10
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Cos sim",       f"{metricas.get('similitud_coseno', 0.0):.3f}")
    g = metricas.get("gain_score")
    col6.metric("Gain Score",    f"{g:.3f}" if g is not None else "—")
    k = metricas.get("kappa")
    col7.metric("Kappa",         f"{k:.3f}" if k is not None else "—")
    col8.metric("Puntaje 0-10",  f"{metricas.get('puntaje_10', 0.0):.1f}")

    st.caption(
        "*Kappa: requiere ≥2 iteraciones. Usa el botón Rechazar para re-analizar y activarlo.*"
    )

    st.divider()

    # ── Actividad del enjambre ────────────────────────────────────────────────
    st.markdown("#### Actividad del Enjambre Jerárquico")

    auditor_calls = metodologico_calls = redactor_calls = "—"
    if log_debate:
        m_a = _re.search(r"Auditor:\s*(\d+)x", log_debate)
        m_m = _re.search(r"Metodólogo:\s*(\d+)x", log_debate)
        m_r = _re.search(r"Redactor:\s*(\d+)x", log_debate)
        if m_a: auditor_calls      = m_a.group(1)
        if m_m: metodologico_calls = m_m.group(1)
        if m_r: redactor_calls     = m_r.group(1)

    ca, cm, cr, ch = st.columns(4)
    ca.metric("Auditor",       f"{auditor_calls}×",
              help="Llamadas del Director al Agente Auditor de rúbrica UPAO.")
    cm.metric("Metodólogo",    f"{metodologico_calls}×",
              help="Llamadas del Director al Agente Metodólogo de coherencia científica.")
    cr.metric("Redactor",      f"{redactor_calls}×",
              help="Llamadas del Director al Agente Redactor para generar texto mejorado.")
    ch.metric("Re-análisis",   f"{iteracion_hitl}×",
              help="Veces que el Mentor rechazó el resultado y solicitó un nuevo análisis.")

    st.divider()

    # ── Datos crudos ──────────────────────────────────────────────────────────
    with st.expander("Ver datos crudos del ciclo"):
        st.json({
            "seccion":          seccion_key,
            "puntaje_bruto":    puntaje_bruto,
            "puntaje_max":      puntaje_max,
            "rouge1_f":         metricas.get("rouge1_f", 0.0),
            "rouge2_f":         metricas.get("rouge2_f", 0.0),
            "rougeL_f":         metricas.get("rougeL_f", 0.0),
            "bleu_score":       metricas.get("bleu_score", 0.0),
            "similitud_coseno": metricas.get("similitud_coseno", 0.0),
            "gain_score":       metricas.get("gain_score"),
            "kappa":            metricas.get("kappa"),
            "puntaje_10":       metricas.get("puntaje_10", 0.0),
            "iteraciones_hitl": iteracion_hitl,
            "llamadas_agentes": {
                "auditor":      auditor_calls,
                "metodologico": metodologico_calls,
                "redactor":     redactor_calls,
            },
        })


# ── Métricas de coherencia (uso interno investigador) ─────────────────────────

def _guardar_metricas(resultado: dict, seccion_key: str, texto_final: str) -> None:
    try:
        from backend.metrics.coherencia import calcular_y_guardar_coherencia
        reporte = resultado.get("reporte_auditor")
        ctx_rag = sm.get("ctx_rag_actual") or ""

        errores = []
        if reporte:
            errores = [
                {
                    "item_numero":    item.item_numero,
                    "puntaje_actual": item.puntaje,
                    "descripcion":    item.observacion,
                }
                for item in reporte.items_evaluados
                if item.puntaje < 2
            ]

        calcular_y_guardar_coherencia({
            "seccion_objetivo":            seccion_key,
            "contexto_recuperado":         ctx_rag,
            "texto_iterado":               texto_final,
            "feedback_auditor":            reporte.feedback_general if reporte else "",
            "observaciones_metodologicas": resultado.get("obs_metodologica", ""),
            "errores_rubrica":             errores,
            "historial_debate":            [],
            "puntaje_estimado":            resultado.get("nota_vigesimal", 0),
            "_puntaje_max":                len(reporte.items_evaluados) * 3 if reporte else 0,
            "numero_iteracion":            sm.get("iteracion_hitl") or 0,
            "ronda_debate":                0,
        })
    except Exception as exc:
        import logging
        logging.getLogger("mentoria").warning(f"[Coherencia] No se pudo guardar: {exc}")
