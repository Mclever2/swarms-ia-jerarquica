"""
Pantalla 1: Carga del PDF de tesis.
El mentor sube el documento y el sistema construye el store RAG.
"""
from __future__ import annotations
import streamlit as st

from backend.rag.extractor import extraer_texto_pdf, split_into_sections
from backend.rag.tesis_store import build_tesis_store
from frontend import session_manager as sm


def render():
    st.title("📄 Cargar Proyecto de Tesis")
    st.markdown(
        "Sube el PDF del proyecto de tesis UPAO que deseas evaluar. "
        "El sistema lo segmentará automáticamente por secciones."
    )

    uploaded = st.file_uploader(
        "Selecciona el PDF del proyecto de tesis",
        type=["pdf"],
        key="tesis_uploader",
    )

    if uploaded:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.success(f"✅ Archivo: **{uploaded.name}** ({uploaded.size:,} bytes)")
        with col2:
            if st.button("🚀 Procesar PDF", type="primary", use_container_width=True):
                _procesar(uploaded)


def _procesar(uploaded):
    pdf_bytes = uploaded.getvalue()
    with st.spinner("Extrayendo texto y segmentando secciones..."):
        raw_text = extraer_texto_pdf(pdf_bytes)
        sections = split_into_sections(raw_text)

    # Resumen de secciones detectadas
    detectadas = [k for k, v in sections.items() if not v.startswith("[Sección")]
    no_detectadas = [k for k, v in sections.items() if v.startswith("[Sección")]

    if detectadas:
        st.info(f"✅ Secciones detectadas: {', '.join(detectadas)}")
    if no_detectadas:
        st.warning(f"⚠️ No detectadas: {', '.join(no_detectadas)} — se evaluarán con texto vacío.")

    with st.spinner("Construyendo índice RAG de la tesis..."):
        tesis_store = build_tesis_store(sections)

    sm.set("pdf_bytes", pdf_bytes)
    sm.set("pdf_nombre", uploaded.name)
    sm.set("sections", sections)
    sm.set("tesis_store", tesis_store)
    sm.ir_a("seleccion")
