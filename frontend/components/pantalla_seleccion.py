"""
Pantalla 2: Selección de sección a evaluar.
Muestra las secciones disponibles con indicador de contenido.
"""
from __future__ import annotations
import streamlit as st

from backend.config import SECCIONES
from frontend import session_manager as sm


def render():
    st.title("🔍 Seleccionar Sección a Evaluar")

    nombre = sm.get("pdf_nombre")
    st.markdown(f"**Proyecto:** {nombre}")
    sections = sm.get("sections") or {}

    st.markdown("Selecciona la sección del proyecto de tesis que deseas analizar:")
    st.divider()

    # Mostrar secciones en grid de 2 columnas
    seccion_keys = list(SECCIONES.keys())
    cols = st.columns(2)

    seleccion = None
    for i, sec_key in enumerate(seccion_keys):
        info = SECCIONES[sec_key]
        texto = sections.get(sec_key, "")
        tiene_contenido = texto and not texto.startswith("[Sección")
        chars = len(texto) if tiene_contenido else 0

        with cols[i % 2]:
            estado = "✅" if tiene_contenido else "⚠️"
            label = f"{estado} **{info['label']}** — Ítems {min(info['nums'])}-{max(info['nums'])}"
            if tiene_contenido:
                label += f" | {chars:,} chars"

            if st.button(label, key=f"btn_{sec_key}", use_container_width=True,
                         disabled=not tiene_contenido):
                seleccion = sec_key

    if seleccion:
        sm.set("seccion_activa", seleccion)
        sm.set("iteracion_hitl", 0)
        sm.ir_a("procesando")

    st.divider()
    if st.button("⬅️ Volver / Cargar otro PDF"):
        sm.ir_a("upload")
