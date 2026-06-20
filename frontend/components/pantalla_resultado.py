"""
Pantalla 4: Resultado final aprobado por el mentor.
Muestra el texto definitivo, métricas, análisis de consenso/disenso y permite descargarlo.
"""
from __future__ import annotations
import json
from datetime import datetime

import streamlit as st

from backend.config import SECCIONES
from frontend import session_manager as sm
from .pantalla_revision import (
    _render_tab_metodologico,
    _render_tab_veredicto,
    _render_tab_consenso_disenso,
    _render_tab_metricas,
)


def render():
    st.title("Mentoría Completada")
    st.success("El mentor aprobó el texto mejorado.")

    resultado   = sm.get("resultado") or {}
    seccion_key = sm.get("seccion_activa") or "?"
    info        = SECCIONES.get(seccion_key, {})
    aprobado    = resultado.get("aprobado", False)
    texto_final = resultado.get("texto_final_aprobado") or resultado.get("texto_mejorado", "")
    reporte     = resultado.get("reporte_auditor")
    reporte_revision = resultado.get("reporte_revision")

    # ── Métricas ──────────────────────────────────────────────────────────────
    puntaje_bruto = reporte.puntaje_total if reporte else 0
    puntaje_max   = len(reporte.items_evaluados) * 3 if reporte and reporte.items_evaluados else 0
    iteracion     = sm.get("iteracion_hitl") or 0
    errores_count = len([i for i in (reporte.items_evaluados if reporte else []) if i.puntaje < 2])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Re-análisis", f"{iteracion}x")
    with col2:
        st.metric("Errores detectados", errores_count, delta="Sin errores" if errores_count == 0 else None)
    with col3:
        if reporte:
            st.metric("Puntaje UPAO Inicial", sm.badge_puntaje(reporte.puntaje_total, puntaje_max))
        else:
            st.metric("Puntaje UPAO Inicial", "—")
    with col4:
        if reporte_revision:
            st.metric("Puntaje UPAO Sugerido", sm.badge_puntaje(reporte_revision.puntaje_total, puntaje_max))
        elif reporte:
            st.metric("Puntaje UPAO Sugerido", sm.badge_puntaje(reporte.puntaje_total, puntaje_max))
        else:
            st.metric("Puntaje UPAO Sugerido", "—")

    st.divider()

    # ── Texto final ───────────────────────────────────────────────────────────
    st.subheader(f"Texto Final Aprobado — {info.get('label', seccion_key)}")
    st.markdown(
        f"""<div style="background:#f0faf0;border-left:4px solid #28a745;
        padding:1.2rem 1.5rem;border-radius:6px;line-height:1.8;font-size:0.96rem;">
        {(texto_final or '_Sin texto producido_').replace(chr(10), '<br>')}
        </div>""",
        unsafe_allow_html=True,
    )
    st.code(texto_final or "", language=None)
    st.caption("Usa el ícono de copia para exportar el texto aprobado.")

    if "[COMPLETAR:" in (texto_final or ""):
        st.warning(
            "El texto contiene marcadores `[COMPLETAR: ...]`. "
            "Estos indican secciones que **el estudiante debe completar** "
            "con información real de su investigación."
        )

    st.divider()

    # ── Tabs de informe ───────────────────────────────────────────────────────
    tab_eval, tab_debate, tab_rag, tab_reportes = st.tabs([
        "📋 Evaluación",
        "⚖️ Debate",
        "📄 Contexto RAG",
        "📊 Reportes",
    ])

    with tab_eval:
        # Rúbrica UPAO Evaluada del Texto de Entrada (Original)
        if reporte and reporte.items_evaluados:
            st.subheader("📋 Rúbrica UPAO Evaluada del Texto de Entrada (Original)")
            from backend.config import RUBRICA_ITEMS_UPAO
            tabla_markdown = [
                "| Ítem ID | Criterio de la Rúbrica UPAO | Puntaje | Observación del Evaluador |",
                "| :--- | :--- | :--- | :--- |"
            ]
            for it in reporte.items_evaluados:
                desc = RUBRICA_ITEMS_UPAO.get(it.item_numero, "Ítem sin descripción")
                tabla_markdown.append(
                    f"| **{it.item_numero:02d}** | {desc} | **{it.puntaje}/3** | {it.observacion} |"
                )
            st.markdown("\n".join(tabla_markdown))
            st.divider()

        # Rúbrica UPAO Evaluada del Texto Sugerido / Final
        if reporte_revision and reporte_revision.items_evaluados:
            st.subheader("📋 Rúbrica UPAO Evaluada del Texto Sugerido / Final")
            from backend.config import RUBRICA_ITEMS_UPAO
            tabla_markdown_final = [
                "| Ítem ID | Criterio de la Rúbrica UPAO | Puntaje | Observación del Evaluador |",
                "| :--- | :--- | :--- | :--- |"
            ]
            for it in reporte_revision.items_evaluados:
                desc = RUBRICA_ITEMS_UPAO.get(it.item_numero, "Ítem sin descripción")
                tabla_markdown_final.append(
                    f"| **{it.item_numero:02d}** | {desc} | **{it.puntaje}/3** | {it.observacion} |"
                )
            st.markdown("\n".join(tabla_markdown_final))
            st.divider()

        # Feedback del auditor
        st.subheader("Feedback del Auditor")
        st.info(reporte.feedback_general if reporte else "—")
        st.divider()

        # Observaciones metodológicas
        st.subheader("Observaciones Metodológicas (rigor científico)")
        _render_tab_metodologico(resultado.get("obs_metodologica", ""))
        st.divider()

        # Veredicto del Director
        st.subheader("Veredicto del Director")
        _render_tab_veredicto(resultado.get("veredicto_director", ""))

    with tab_debate:
        _render_tab_consenso_disenso(resultado)
        st.divider()
        st.markdown("**Actividad del Enjambre Jerárquico:**")
        st.caption(resultado.get("log_debate", "—"))

    with tab_rag:
        rag_sub_tabs = st.tabs([
            "📄 Contexto de la sección (RAG)",
            "🔗 Contexto cruzado (Otras secciones)",
            "📚 Contexto metodológico (Libros)"
        ])

        with rag_sub_tabs[0]:
            st.markdown("**Contexto original extraído del PDF (sección evaluada):**")
            st.code(sm.get("ctx_rag_actual") or "—", language=None, wrap_lines=True)
            st.divider()
            st.markdown("**Fragmentos individuales:**")
            contexto_raw = sm.get("ctx_rag_actual") or ""
            for i, fragmento in enumerate(contexto_raw.split("---"), start=1):
                if fragmento.strip():
                    with st.expander(f"Fragmento {i}"):
                        st.code(fragmento.strip(), language=None, wrap_lines=True)

        with rag_sub_tabs[1]:
            st.markdown("**Contexto de secciones cruzadas relacionadas:**")
            st.code(sm.get("ctx_cruzado_actual") or "Sin contexto cruzado.", language=None, wrap_lines=True)

        with rag_sub_tabs[2]:
            st.markdown("**Contexto metodológico de libros de referencia:**")
            st.code(sm.get("ctx_teorico_actual") or "Sin contexto metodológico de libros.", language=None, wrap_lines=True)


    with tab_reportes:
        _render_tab_metricas(resultado, seccion_key, puntaje_bruto, puntaje_max)

    st.divider()

    # ── Descargas ─────────────────────────────────────────────────────────────
    st.subheader("Descargar")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    col_txt, col_json = st.columns(2)

    with col_txt:
        st.download_button(
            "Texto mejorado (.txt)",
            data=(texto_final or "").encode("utf-8"),
            file_name=f"mentoria_{seccion_key}_{timestamp}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    with col_json:
        export = {
            "seccion":           seccion_key,
            "aprobado":          aprobado,
            "puntaje_total":     reporte.puntaje_total if reporte else 0,
            "texto_final":       texto_final,
            "veredicto_director":resultado.get("veredicto_director", ""),
            "resultado_consenso":resultado.get("resultado_consenso", ""),
            "resultado_disenso": resultado.get("resultado_disenso",  ""),
            "timestamp":         timestamp,
        }
        st.download_button(
            "Informe completo (.json)",
            data=json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"informe_{seccion_key}_{timestamp}.json",
            mime="application/json",
            use_container_width=True,
        )

    st.divider()

    # ── Historial y botones ───────────────────────────────────────────────────
    historial = sm.get("historial_sesion") or []
    seccion_label = info.get("label", seccion_key)
    if not any(entry.get("seccion") == seccion_label for entry in historial):
        historial.append({
            "seccion": seccion_label,
            "puntaje": puntaje_bruto,
            "puntaje_max": puntaje_max,
            "estado": "Aprobado" if aprobado else "Observado"
        })
        sm.set("historial_sesion", historial)

    if len(historial) > 1:
        st.subheader("Historial de esta sesión")
        for entry in historial:
            st.markdown(f"- **{entry['seccion']}** — Puntaje: {entry['puntaje']}/{entry['puntaje_max']} ({entry['estado']})")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("Evaluar otra sección (mismo PDF)", use_container_width=True):
            sm.set("resultado",       None)
            sm.set("seccion_activa",  None)
            sm.set("seccion_preview", None)
            sm.ir_a("seleccion")
    with col_b2:
        if st.button("Nueva evaluación (nuevo PDF)", type="primary", use_container_width=True):
            sm.reiniciar()
