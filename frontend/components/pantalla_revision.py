"""
Pantalla 3 (HITL): Revisión y aprobación del mentor.
El mentor puede editar el texto antes de aprobar o rechazar para re-análisis.
"""
from __future__ import annotations
import streamlit as st

from backend.config import SECCIONES, MAX_CONTEXT_CHARS
from backend.rag.tesis_store import query_context, query_cross_context
from frontend import session_manager as sm
from frontend.resources import get_orchestrator


def render():
    seccion_key = sm.get("seccion_activa")
    info = SECCIONES.get(seccion_key, {})
    st.title(f"🔎 Revisión: {info.get('label', seccion_key)}")

    resultado = sm.get("resultado")

    # Si no hay resultado aún → ejecutar pipeline
    if resultado is None:
        _ejecutar_pipeline(seccion_key)
        return  # rerun ocurrirá al final de _ejecutar_pipeline

    _mostrar_resultado(resultado, seccion_key)


def _ejecutar_pipeline(seccion_key: str):
    store     = sm.get("tesis_store")
    iteracion = sm.get("iteracion_hitl")

    if store is None:
        st.error("No hay tesis indexada. Vuelve a cargar el PDF.")
        sm.ir_a("upload")
        return

    ctx_rag     = query_context(store, seccion_key)[:MAX_CONTEXT_CHARS]
    ctx_cruzado = query_cross_context(store, seccion_key)[:MAX_CONTEXT_CHARS]

    progress_bar = st.progress(0.0, text="Iniciando pipeline...")

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
        )

    progress_bar.progress(1.0, "¡Análisis completado!")
    sm.set("resultado", resultado)
    sm.set("texto_editado", resultado.get("texto_mejorado", ""))
    st.rerun()


def _mostrar_resultado(resultado: dict, seccion_key: str):
    reporte = resultado.get("reporte_auditor")
    nota    = resultado.get("nota_vigesimal", 0)
    aprobado= resultado.get("aprobado", False)

    # ── Métricas ──────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Nota Vigesimal", f"{nota}/20")
    with col2:
        pts = reporte.puntaje_total if reporte else 0
        st.metric("Puntaje Bruto", f"{pts}/99")
    with col3:
        st.metric("Estado", "✅ APROBADO" if aprobado else "⚠️ Observado")

    # ── Veredicto del Director ────────────────────────────────────────────────
    st.subheader("📋 Veredicto del Director Mentor")
    st.markdown(resultado.get("veredicto_director", ""))

    # ── Texto mejorado (editable) ─────────────────────────────────────────────
    st.subheader("✍️ Texto Mejorado por el Redactor")
    texto_editado = st.text_area(
        "El mentor puede editar el texto antes de aprobarlo:",
        value=sm.get("texto_editado") or resultado.get("texto_mejorado", ""),
        height=300,
        key="area_texto_editado",
    )
    sm.set("texto_editado", texto_editado)

    # ── Detalle de ítems ──────────────────────────────────────────────────────
    with st.expander("Ver detalle de ítems evaluados"):
        if reporte and reporte.items_evaluados:
            for item in reporte.items_evaluados:
                color = "🟢" if item.puntaje == 3 else ("🟡" if item.puntaje == 2 else "🔴")
                st.markdown(f"{color} **Ítem {item.item_numero}** [{item.puntaje}/3]: {item.observacion}")
        st.markdown(f"**Obs. Metodológica:** {resultado.get('obs_metodologica', '')[:500]}")

    st.divider()

    # ── Botones HITL ──────────────────────────────────────────────────────────
    col_aprueba, col_rechaza = st.columns(2)
    with col_aprueba:
        if st.button("✅ Aprobar y finalizar", type="primary", use_container_width=True):
            resultado["texto_final_aprobado"] = texto_editado
            sm.set("resultado", resultado)
            sm.ir_a("resultado")

    with col_rechaza:
        it = sm.get("iteracion_hitl")
        if st.button(f"🔄 Re-analizar (HITL #{it + 1})", use_container_width=True):
            sm.set("resultado", None)
            sm.set("iteracion_hitl", it + 1)
            st.rerun()
