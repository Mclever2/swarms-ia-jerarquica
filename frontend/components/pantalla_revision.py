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
    seccion_key = sm.get("seccion_activa")
    info        = SECCIONES.get(seccion_key, {})
    st.title(f"Revisión: {info.get('label', seccion_key)}")

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


# ── Presentación del resultado ────────────────────────────────────────────────

def _mostrar_resultado(resultado: dict, seccion_key: str):
    reporte  = resultado.get("reporte_auditor")
    nota     = resultado.get("nota_vigesimal", 0)
    aprobado = resultado.get("aprobado", False)
    rubrica  = sm.get("rubrica_dinamica")

    # ── Métricas ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nota Vigesimal",   f"{nota}/20")
    c2.metric("Puntaje Bruto",    f"{reporte.puntaje_total if reporte else 0} pts")
    c3.metric("Estado",           "APROBADO" if aprobado else "Observado")
    c4.metric("Re-análisis HITL", f"{sm.get('iteracion_hitl', 0)}x")

    st.divider()

    # ── Tabs de informe ───────────────────────────────────────────────────────
    tabs = st.tabs([
        "Informe del Auditor",
        "Observaciones Metodológicas",
        "Consenso / Disenso",
        "Veredicto del Director",
    ])

    with tabs[0]:
        _render_tab_auditor(reporte, seccion_key, rubrica)

    with tabs[1]:
        obs = resultado.get("obs_metodologica", "")
        if obs:
            st.markdown(obs)
        else:
            st.info("Sin observaciones metodológicas disponibles.")

    with tabs[2]:
        _render_tab_consenso_disenso(resultado)

    with tabs[3]:
        st.markdown(resultado.get("veredicto_director", "_Sin veredicto._"))

    st.divider()

    # ── Editor de texto ───────────────────────────────────────────────────────
    sec_label = SECCIONES.get(seccion_key, {}).get("label", seccion_key)
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
