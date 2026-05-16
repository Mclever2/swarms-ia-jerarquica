"""
Pantalla 1: Carga del PDF de tesis + carga opcional de rúbrica personalizada.

Flujo en 2 pasos:
  Paso 1 — PDF de tesis: extrae texto, segmenta secciones, construye RAG.
  Paso 2 — PDF de rúbrica (opcional): parsea ítems, secciones y tabla vigesimal.
           Si no se sube, el sistema usa la rúbrica oficial UPAO de 33 ítems.
"""
from __future__ import annotations
import hashlib

import streamlit as st

from backend.rag.extractor import extraer_texto_pdf, split_into_sections
from backend.rag.tesis_store import build_tesis_store
from backend.rag.rubric_parser import parse_rubrica_pdf
from frontend import session_manager as sm


def render():
    st.title("Cargar Proyecto de Tesis")

    _paso_1_tesis()

    if sm.get("tesis_store") is not None:
        st.divider()
        _paso_2_rubrica()
        st.divider()
        _boton_continuar()


# ── Paso 1: PDF de tesis ──────────────────────────────────────────────────────

def _paso_1_tesis():
    st.subheader("Paso 1 — PDF del proyecto de tesis")
    st.caption("El sistema segmentará el PDF en las 7 secciones UPAO automáticamente.")

    uploaded = st.file_uploader(
        "Selecciona el PDF del proyecto de tesis",
        type=["pdf"],
        key="tesis_uploader",
    )

    if uploaded:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.success(f"Archivo: **{uploaded.name}** ({uploaded.size:,} bytes)")
        with col2:
            if st.button("Procesar PDF", type="primary", use_container_width=True):
                _procesar_tesis(uploaded)

    # Mostrar resultado si ya fue procesado
    if sm.get("tesis_store") is not None:
        sections = sm.get("sections") or {}
        detectadas    = [k for k, v in sections.items() if not v.startswith("[Sección")]
        no_detectadas = [k for k, v in sections.items() if v.startswith("[Sección")]

        from backend.config import SECCIONES
        st.success(f"PDF cargado: **{sm.get('pdf_nombre')}**")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**Secciones detectadas ({len(detectadas)}/7):**")
            for k in detectadas:
                label = SECCIONES.get(k, {}).get("label", k)
                texto = sections.get(k, "")
                st.markdown(f"- {label} ({len(texto):,} chars)")
        with col_b:
            if no_detectadas:
                st.markdown(f"**No detectadas ({len(no_detectadas)}):**")
                for k in no_detectadas:
                    label = SECCIONES.get(k, {}).get("label", k)
                    st.markdown(f"- {label}")
            else:
                st.success("Todas las secciones detectadas.")


def _procesar_tesis(uploaded):
    pdf_bytes = uploaded.getvalue()
    with st.spinner("Extrayendo texto y segmentando secciones..."):
        raw_text = extraer_texto_pdf(pdf_bytes)
        sections = split_into_sections(raw_text)

    with st.spinner("Construyendo índice RAG de la tesis..."):
        tesis_store = build_tesis_store(sections)

    sm.set("pdf_bytes",   pdf_bytes)
    sm.set("pdf_nombre",  uploaded.name)
    sm.set("sections",    sections)
    sm.set("tesis_store", tesis_store)
    # Limpiar evaluación anterior si cambian de PDF
    sm.set("resultado",        None)
    sm.set("seccion_activa",   None)
    sm.set("seccion_preview",  None)
    st.rerun()


# ── Paso 2: PDF de rúbrica (opcional) ────────────────────────────────────────

def _paso_2_rubrica():
    st.subheader("Paso 2 — Rúbrica de evaluación (opcional)")

    rubrica_actual = sm.get("rubrica_dinamica")
    if rubrica_actual:
        st.success(
            f"Rúbrica activa: **{sm.get('rubrica_nombre')}** "
            f"({rubrica_actual['total_items']} ítems · "
            f"puntaje máx: {rubrica_actual['puntaje_maximo']})"
        )
        if st.button("Cambiar rúbrica", use_container_width=False):
            sm.set("rubrica_dinamica", None)
            sm.set("rubrica_hash",     None)
            sm.set("rubrica_nombre",   None)
            st.rerun()
        return

    st.caption(
        "Si tu institución usa una rúbrica diferente a la UPAO, súbela aquí. "
        "El sistema la usará para evaluación y agrupará los errores por sus secciones. "
        "Si no subes ninguna, se usará la **rúbrica oficial UPAO (33 ítems)**."
    )

    uploaded_rubrica = st.file_uploader(
        "PDF de rúbrica personalizada (opcional)",
        type=["pdf"],
        key="rubrica_uploader",
    )

    if uploaded_rubrica:
        pdf_bytes = uploaded_rubrica.getvalue()
        nuevo_hash = hashlib.md5(pdf_bytes).hexdigest()

        if nuevo_hash != sm.get("rubrica_hash"):
            with st.spinner("Parseando rúbrica..."):
                rubrica = parse_rubrica_pdf(pdf_bytes)

            if rubrica:
                sm.set("rubrica_dinamica", rubrica)
                sm.set("rubrica_hash",     nuevo_hash)
                sm.set("rubrica_nombre",   uploaded_rubrica.name)
                st.success(
                    f"Rúbrica cargada: **{uploaded_rubrica.name}** — "
                    f"{rubrica['total_items']} ítems en {len(rubrica['secciones'])} secciones."
                )
                st.rerun()
            else:
                st.error(
                    "No se pudieron extraer ítems del PDF. "
                    "Verifica que el archivo contenga una tabla de evaluación con números de ítem. "
                    "Se usará la rúbrica UPAO por defecto."
                )
    else:
        st.info("Rúbrica activa: **UPAO oficial (33 ítems)** — puedes subir una personalizada arriba.")


# ── Botón continuar ───────────────────────────────────────────────────────────

def _boton_continuar():
    if st.button("Continuar a selección de sección", type="primary", use_container_width=True):
        sm.ir_a("seleccion")
